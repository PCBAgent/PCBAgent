#!/usr/bin/env python3
"""Place, route, and check a board from designs/<slug>/parts/board.net and designs/<slug>/layout/constraints.json.

Writes designs/<slug>/layout/: placement.json, placed.kicad_pcb, board.dsn, board.ses, board.kicad_pcb, drc.json, report.json.
Exit 0 when every check passes, 1 when the board was built but a check failed, 2 when there is no board.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

from place import LayoutError, Problem, parse_netlist, place, rules_from, semantic_errors  # noqa: E402


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMA = HERE / "schemas" / "constraints.schema.json"
KICAD_SCRIPT = HERE / "kicad.py"
MAX_ATTEMPTS = 4
GAP_STEP_MM = 0.5
FREEROUTING_PASSES = 100
FREEROUTING_TIMEOUT_S = 300
KICAD_TIMEOUT_S = 300
KICAD_PYTHONS = (
    "/usr/bin/python3",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
)
KICAD_CLIS = ("/usr/bin/kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
ARTIFACTS = (
    "placement.json",
    "placed.kicad_pcb",
    "placed.kicad_pro",
    "board.dsn",
    "board.ses",
    "board.kicad_pcb",
    "board.kicad_pro",
    "routing.json",
    "drc.json",
    "freerouting.log",
)


class NoBoard(Exception):
    pass


def design_root(path):
    path = Path(path).resolve()
    if path.name in {"design", "parts", "layout"} and (path.parent / "parts").is_dir():
        return path.parent
    return path


def kicad_python():
    candidates = [os.environ.get("KICAD_PYTHON")] + list(KICAD_PYTHONS)
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        probe = subprocess.run([candidate, "-c", "import pcbnew"], capture_output=True, text=True)
        if probe.returncode == 0:
            return candidate
    raise NoBoard("no Python with KiCad's pcbnew module. Set KICAD_PYTHON.")


def kicad_cli():
    found = shutil.which("kicad-cli")
    if found:
        return found
    for candidate in KICAD_CLIS:
        if Path(candidate).is_file():
            return candidate
    raise NoBoard("kicad-cli not found")


def freerouting_cli():
    candidates = [os.environ.get("FREEROUTING_CLI"), str(ROOT / ".tools" / "freerouting" / "freerouting-cli"), shutil.which("freerouting-cli")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise NoBoard("freerouting-cli not found. Run ./setup.sh.")


def run_kicad(python, args, cwd):
    proc = subprocess.run([python, str(KICAD_SCRIPT)] + [str(a) for a in args], cwd=cwd, capture_output=True, text=True, timeout=KICAD_TIMEOUT_S)
    if proc.returncode != 0:
        noise = [line for line in proc.stderr.splitlines() if "m_choices" not in line]
        raise NoBoard(f"kicad.py {args[0]} failed: " + "\n".join(noise[-15:]))


def strip_outlines(dsn):
    """Drop (outline ...) blocks. The Freerouting 2.5.0 native build crashes serializing component outlines."""
    out = []
    i = 0
    while True:
        j = dsn.find("(outline", i)
        if j < 0:
            out.append(dsn[i:])
            return "".join(out)
        out.append(dsn[i:j])
        depth = 0
        k = j
        while k < len(dsn):
            if dsn[k] == "(":
                depth += 1
            elif dsn[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1


def netclasses_for(constraints, rules):
    widths = {}
    for constraint in constraints.get("constraints", []):
        if constraint["type"] == "high_current":
            for net in constraint["nets"]:
                widths[net] = max(widths.get(net, 0.0), constraint["track_width_mm"])
    classes = {}
    for net, width in widths.items():
        classes.setdefault(width, []).append(net)
    result = []
    for index, (width, nets) in enumerate(sorted(classes.items())):
        via = max(rules["via_diameter_mm"], width)
        result.append({
            "name": f"HighCurrent{index + 1}",
            "nets": sorted(nets),
            "track_width_mm": width,
            "clearance_mm": rules["clearance_mm"],
            "via_diameter_mm": via,
            "via_drill_mm": max(rules["via_drill_mm"], round(via / 2, 2)),
        })
    return result


def drc_summary(drc):
    errors = []
    warnings = []
    for violation in drc.get("violations", []):
        entry = {
            "type": violation.get("type"),
            "description": violation.get("description"),
            "items": [item.get("description") for item in violation.get("items", [])],
        }
        (errors if violation.get("severity") == "error" else warnings).append(entry)
    unconnected = [
        {"description": item.get("description"), "items": [i.get("description") for i in item.get("items", [])]}
        for item in drc.get("unconnected_items", [])
    ]
    return errors, warnings, unconnected


def routed_checks(constraints, stats):
    checks = []
    nets = stats.get("nets", {})
    for constraint in constraints.get("constraints", []):
        if constraint["type"] == "high_current":
            for net in constraint["nets"]:
                routed = nets.get(net, {})
                width = routed.get("body_min_width_mm")
                required = constraint["track_width_mm"]
                ok = width is None or width + 1e-4 >= required
                necked = sum(
                    s["length_mm"] for s in routed.get("segments", []) if s["near_pad"] and s["width_mm"] + 1e-4 < required
                )
                checks.append({
                    "type": "high_current",
                    "net": net,
                    "required_width_mm": required,
                    "min_width_mm": width,
                    "necked_near_pads_mm": round(necked, 3),
                    "status": "pass" if ok else "fail",
                })
        if constraint["type"] == "differential_pair" and "max_skew_mm" in constraint:
            a, b = constraint["nets"]
            la = nets.get(a, {}).get("length_mm", 0.0)
            lb = nets.get(b, {}).get("length_mm", 0.0)
            skew = abs(la - lb)
            checks.append({
                "type": "differential_pair",
                "nets": [a, b],
                "skew_mm": round(skew, 3),
                "max_skew_mm": constraint["max_skew_mm"],
                "status": "pass" if skew <= constraint["max_skew_mm"] else "fail",
            })
    return checks


def attempt_board(work, problem, netlist, constraints, rules, seed, tools):
    """Place, build, route, import, and check once. Return the attempt record."""
    work.mkdir(parents=True, exist_ok=True)
    record = {"seed": seed, "extra_gap_mm": problem.extra_gap, "reasons": []}
    placement = place(problem, seed=seed)
    (work / "placement.json").write_text(json.dumps(placement, indent=2) + "\n")
    record["placement"] = {key: placement[key] for key in ("board_mm", "cost", "terms", "violations", "legal")}
    hard = [v for v in placement["violations"] if v["hard"]]
    if hard:
        record["stage"] = "placement"
        record["reasons"] = [v["message"] for v in hard]
        return record

    pads = {comp["ref"]: {} for comp in netlist["components"]}
    for name, nodes in netlist["nets"].items():
        for ref, pin in nodes:
            if ref in pads:
                pads[ref][str(pin)] = name
    job = {
        "components": [
            dict(comp, **placement["parts"][comp["ref"]], pads=pads[comp["ref"]])
            for comp in netlist["components"]
        ],
        "outline_mm": placement["outline_mm"],
        "rules": rules,
        "netclasses": netclasses_for(constraints, rules),
        "board": str(work / "placed.kicad_pcb"),
        "dsn": str(work / "board.dsn"),
    }
    (work / "job.json").write_text(json.dumps(job, indent=2))
    run_kicad(tools["python"], ["build", work / "job.json"], work)
    run_kicad(tools["python"], ["rules", work / "job.json"], work)
    dsn = work / "board.dsn"
    dsn.write_text(strip_outlines(dsn.read_text()))

    session = work / "board.ses"
    command = [
        tools["freerouting"],
        "-de", str(dsn),
        "-do", str(session),
        f"--router.autorouter.max_passes={FREEROUTING_PASSES}",
        f"--router.copper_to_edge_clearance_um={round(rules['edge_clearance_mm'] * 1000)}",
    ]
    try:
        proc = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=FREEROUTING_TIMEOUT_S)
        (work / "freerouting.log").write_text(proc.stdout + proc.stderr)
    except subprocess.TimeoutExpired as timeout:
        (work / "freerouting.log").write_text(str(timeout.stdout or "") + str(timeout.stderr or ""))
    if not session.is_file():
        record["stage"] = "routing"
        record["reasons"] = [f"Freerouting wrote no session in {FREEROUTING_TIMEOUT_S} s; see freerouting.log"]
        return record

    run_kicad(tools["python"], ["import", work / "placed.kicad_pcb", session, work / "board.kicad_pcb", work / "routing.json"], work)
    drc_path = work / "drc.json"
    subprocess.run(
        [tools["kicad_cli"], "pcb", "drc", "--format", "json", "--severity-all", "--units", "mm", "-o", str(drc_path), str(work / "board.kicad_pcb")],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=KICAD_TIMEOUT_S,
    )
    if not drc_path.is_file():
        raise NoBoard("kicad-cli pcb drc wrote no report")
    errors, warnings, unconnected = drc_summary(json.loads(drc_path.read_text()))
    stats = json.loads((work / "routing.json").read_text())
    checks = routed_checks(constraints, stats)
    record["stage"] = "checks"
    record["routing"] = {"unrouted": len(unconnected), "vias": stats.get("vias", 0)}
    record["drc"] = {"errors": errors, "warnings": warnings, "unconnected": unconnected}
    record["checks"] = checks
    if unconnected:
        record["reasons"].append(f"{len(unconnected)} unrouted connections")
    if errors:
        record["reasons"].append(f"{len(errors)} DRC errors: " + ", ".join(sorted({e['type'] for e in errors})))
    for check in checks:
        if check["status"] == "fail":
            record["reasons"].append(f"{check['type']} check failed: {json.dumps(check)}")
    return record


def badness(record):
    stage_rank = {"placement": 3, "routing": 2, "checks": 0}[record["stage"]]
    unrouted = record.get("routing", {}).get("unrouted", 0)
    errors = len(record.get("drc", {}).get("errors", []))
    return (stage_rank, unrouted, errors, len(record["reasons"]))


def run(root):
    netlist_path = root / "parts" / "board.net"
    constraints_path = root / "layout" / "constraints.json"
    spec_path = root / "design" / "circuit-spec.json"
    for path in (netlist_path, constraints_path):
        if not path.is_file():
            raise NoBoard(f"{path} does not exist")
    netlist = parse_netlist(netlist_path.read_text(encoding="utf-8"))
    if not netlist["components"]:
        raise NoBoard("board.net has no components")
    missing = [comp["ref"] for comp in netlist["components"] if not comp["footprint"]]
    if missing:
        raise NoBoard("no footprint in board.net for " + ", ".join(missing))

    constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text())
    schema_errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(constraints), key=lambda e: list(e.path))
    if schema_errors:
        raise NoBoard("constraints.json does not match the schema:\n" + "\n".join(f"{list(e.path)}: {e.message}" for e in schema_errors))
    problems = semantic_errors(constraints, netlist)
    if problems:
        raise NoBoard("constraints.json:\n" + "\n".join(problems))

    board_max = None
    if spec_path.is_file():
        board_max = json.loads(spec_path.read_text(encoding="utf-8")).get("board_max_mm")

    tools = {"python": kicad_python(), "kicad_cli": kicad_cli(), "freerouting": freerouting_cli()}
    layout = root / "layout"
    work_root = layout / ".work"
    shutil.rmtree(work_root, ignore_errors=True)
    work_root.mkdir(parents=True)

    fpids = sorted({comp["footprint"] for comp in netlist["components"]})
    (work_root / "footprints-job.json").write_text(json.dumps({"footprints": fpids}))
    run_kicad(tools["python"], ["footprints", work_root / "footprints-job.json", layout / "footprints.json"], work_root)
    geometry = json.loads((layout / "footprints.json").read_text())

    rules = rules_from(constraints)
    attempts = []
    for attempt in range(MAX_ATTEMPTS):
        problem = Problem(netlist, geometry, constraints, board_max, extra_gap_mm=GAP_STEP_MM * attempt)
        record = attempt_board(work_root / f"attempt-{attempt + 1}", problem, netlist, constraints, rules, attempt + 1, tools)
        record["attempt"] = attempt + 1
        record["status"] = "pass" if not record["reasons"] else "fail"
        attempts.append(record)
        if record["status"] == "pass":
            break

    best = min(attempts, key=badness)
    chosen = work_root / f"attempt-{best['attempt']}"
    for name in ARTIFACTS:
        target = layout / name
        if target.exists():
            target.unlink()
        if (chosen / name).exists():
            shutil.copy2(chosen / name, target)
    shutil.rmtree(work_root, ignore_errors=True)

    passed = best["status"] == "pass"
    report = {
        "status": "pass" if passed else "fail",
        "return_to": None if passed else "constraints",
        "chosen_attempt": best["attempt"],
        "board_mm": best["placement"]["board_mm"],
        "board_max_mm": board_max,
        "reasons": best["reasons"],
        "placement": best["placement"],
        "routing": best.get("routing"),
        "drc": best.get("drc"),
        "checks": best.get("checks", []),
        "attempts": [
            {key: a.get(key) for key in ("attempt", "seed", "extra_gap_mm", "stage", "status", "reasons")}
            for a in attempts
        ],
    }
    (layout / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    if len(sys.argv) != 2:
        print("usage: layout.py designs/<slug>", file=sys.stderr)
        return 2
    root = design_root(sys.argv[1])
    try:
        report = run(root)
    except (NoBoard, LayoutError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(error, file=sys.stderr)
        return 2
    summary = {key: report[key] for key in ("status", "return_to", "board_mm", "reasons", "routing", "attempts")}
    print(json.dumps(summary, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
