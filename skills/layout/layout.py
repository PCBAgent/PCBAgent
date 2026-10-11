#!/usr/bin/env python3
"""Place, route, and check a board from designs/<slug>/parts/board.net and designs/<slug>/layout/constraints.json.

Writes designs/<slug>/layout/: placement.json, placed.kicad_pcb, placement.png, board.dsn, board.ses, board.kicad_pcb, board.png, drc.json, report.json.
Exit 0 when every check passes, 1 when the board was built but a check failed, 2 when there is no board.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))

from place import LayoutError, Problem, parse_netlist, place, rules_from, semantic_errors  # noqa: E402
from rules import apply_general_rules  # noqa: E402


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


def attempt_board(work, problem, netlist, constraints, rules, seed, tools, recorder=None):
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
    if recorder:
        recorder.emit("placement-ready", seed, work, "placed.kicad_pcb")
    dsn = work / "board.dsn"
    dsn.write_text(strip_outlines(dsn.read_text()))

    session = work / "board.ses"
    command = [
        tools["freerouting"],
        "-de", str(dsn),
        "-do", str(session),
        f"--router.autorouter.max_passes={FREEROUTING_PASSES}",
        "--router.fanout.enabled=false",
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
    if recorder:
        recorder.emit("routing-ready", seed, work, "board.kicad_pcb")
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
    if recorder:
        recorder.emit("check-result", seed, work, status="pass" if not record["reasons"] else "fail",
                      reasons=record["reasons"])
    return record


def render_view(layout, kicad, source_name, image_name):
    source = layout / source_name
    if not source.is_file():
        return None
    image = (layout / image_name).resolve()
    proc = subprocess.run(
        [
            kicad, "pcb", "render",
            "--output", str(image),
            "--width", "1600",
            "--height", "1200",
            "--side", "top",
            "--background", "opaque",
            "--quality", "basic",
            str(source.resolve()),
        ],
        cwd=layout,
        capture_output=True,
        text=True,
        timeout=KICAD_TIMEOUT_S,
    )
    if proc.returncode != 0 or not image.is_file():
        detail = (proc.stderr or proc.stdout).strip()
        raise NoBoard(f"kicad-cli pcb render wrote no {image.name}\n{detail}")
    return image.name


LAYOUT_LAYERS = "F.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts,F.CrtYd,F.Fab"
PLOT_BACKGROUND = "#1a1a1a"
PLOT_LONG_EDGE_PX = 900
PLOT_MARGIN_MM = 1.2
RASTER_SVG = r"""
import re
import sys
import warnings
import cairo
import gi
gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg

svg_path, png_path, color, long_edge, margin = sys.argv[1:]
long_edge = float(long_edge)
pad = float(margin)
svg = open(svg_path, encoding="utf-8").read()
def short_label(match):
    return "" if len(match.group(1)) > 16 else match.group(0)
svg = re.sub(r'<g class="stroked-text"><desc>(.*?)</desc>.*?</g>', short_label, svg, flags=re.S)
frame = re.search(
    r'width="([0-9.]+)mm"\s+height="([0-9.]+)mm"\s+viewBox="([0-9.\-]+) ([0-9.\-]+) ([0-9.]+) ([0-9.]+)"',
    svg,
)
if frame is None:
    raise SystemExit("placement plot has no board-sized viewBox")
width, height, origin_x, origin_y, box_w, box_h = (float(value) for value in frame.groups())
svg = svg.replace(frame.group(0),
    f'width="{width + 2 * pad:.4f}mm" height="{height + 2 * pad:.4f}mm" '
    f'viewBox="{origin_x - pad:.4f} {origin_y - pad:.4f} {box_w + 2 * pad:.4f} {box_h + 2 * pad:.4f}"',
    1)
handle = Rsvg.Handle.new_from_data(svg.encode())
ok, pixel_w, pixel_h = handle.get_intrinsic_size_in_pixels()
if not ok or pixel_w <= 0 or pixel_h <= 0:
    raise SystemExit("placement plot has no size")
scale = long_edge / max(pixel_w, pixel_h)
surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, int(pixel_w * scale)), max(1, int(pixel_h * scale)))
ctx = cairo.Context(surface)
red = int(color.lstrip("#")[0:2], 16) / 255
green = int(color.lstrip("#")[2:4], 16) / 255
blue = int(color.lstrip("#")[4:6], 16) / 255
ctx.set_source_rgb(red, green, blue)
ctx.paint()
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    ctx.scale(scale, scale)
    handle.render_cairo(ctx)
surface.write_to_png(png_path)
"""


def plot_layout(layout, kicad, source_name, image_name):
    """Write a 2D board plot: copper, silk, courtyard, fabrication, and the outline."""
    source = layout / source_name
    if not source.is_file():
        return None
    image = (layout / image_name).resolve()
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        svg = scratch / "plot.svg"
        proc = subprocess.run(
            [
                kicad, "pcb", "export", "svg",
                "--mode-single",
                "--page-size-mode", "2",
                "--fit-page-to-board",
                "--exclude-drawing-sheet",
                "--output", str(svg),
                "--layers", LAYOUT_LAYERS,
                str(source.resolve()),
            ],
            cwd=layout,
            capture_output=True,
            text=True,
            timeout=KICAD_TIMEOUT_S,
        )
        if proc.returncode != 0 or not svg.is_file():
            detail = (proc.stderr or proc.stdout).strip()
            raise NoBoard(f"kicad-cli pcb export svg wrote no plot for {source_name}\n{detail}")
        raster = subprocess.run(
            ["/usr/bin/python3", "-c", RASTER_SVG, str(svg), str(image), PLOT_BACKGROUND,
             str(PLOT_LONG_EDGE_PX), str(PLOT_MARGIN_MM)],
            capture_output=True,
            text=True,
            timeout=KICAD_TIMEOUT_S,
        )
        if raster.returncode != 0 or not image.is_file():
            detail = (raster.stderr or raster.stdout).strip()
            raise NoBoard(f"could not rasterize {image.name}\n{detail}")
    return image.name


def render_board(layout, kicad):
    """Write placement.png, the 2D layout before routing, then board.png of the routed board."""
    images = []
    placed = plot_layout(layout, kicad, "placed.kicad_pcb", "placement.png")
    if placed:
        images.append(placed)
    routed = render_view(layout, kicad, "board.kicad_pcb", "board.png")
    if routed:
        images.append(routed)
    return images or None


def badness(record):
    stage_rank = {"placement": 3, "routing": 2, "checks": 0}[record["stage"]]
    unrouted = record.get("routing", {}).get("unrouted", 0)
    errors = len(record.get("drc", {}).get("errors", []))
    return (stage_rank, unrouted, errors, len(record["reasons"]))


def run(root, demo=False, speed=1, demo_launch=True):
    recorder = None
    if demo:
        from demo_record import Recorder
        try:
            recorder = Recorder(root, kicad_python(), launch=demo_launch, speed=speed)
            print(f"Demo recording: {recorder.path}", file=sys.stderr)
        except Exception as error:
            print(f"Demo unavailable: {error}. Layout continues.", file=sys.stderr)
    try:
        return _run(root, recorder)
    except BaseException as error:
        if recorder:
            recorder.emit("aborted", message=str(error) or type(error).__name__)
        raise


def check_netlist_provenance(root):
    """Catalog-generated designs need a current manufacturing validation report."""
    parts = root / "parts"
    if not (parts / "parts.json").is_file():
        return  # Standalone externally supplied netlists retain the existing layout API.
    report_path = parts / "netlist-report.json"
    if not report_path.is_file():
        raise NoBoard("Run parts/netlist.py: manufacturing validation report is missing")
    report = json.loads(report_path.read_text())
    def hashes(folder, names):
        return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                for name in names if (folder / name).is_file()}
    inputs = hashes(parts, ("board.net", "parts.json", "skidl_kicad.py"))
    if report.get("status") != "pass" or len(inputs) != 3 or report.get("inputs") != inputs:
        raise NoBoard("Manufacturing validation is failed or stale; rerun verification, parts lookup and netlist generation")
    spec_path = root / "design" / "circuit-spec.json"
    spec = json.loads(spec_path.read_text()) if spec_path.is_file() else {}
    parts_payload = json.loads((parts / "parts.json").read_text())
    if spec.get("skip_verify") is True and parts_payload.get("verify") == "skipped":
        return
    evidence_path = root / "design" / "simulation-evidence.json"
    if not evidence_path.is_file():
        raise NoBoard("Simulation evidence is missing; rerun verification and parts stages")
    evidence = json.loads(evidence_path.read_text())
    checks = evidence.get("checks")
    if evidence.get("status") != "pass" or not checks or any(c.get("status") != "pass" for c in checks):
        raise NoBoard("Current simulation evidence does not pass")
    if report.get("simulation_evidence_sha256") != hashlib.sha256(evidence_path.read_bytes()).hexdigest():
        raise NoBoard("Simulation evidence changed; rerun parts lookup and netlist generation")
    simulation = hashes(root / "design", ("circuit-spec.json", "skidl_sim.py", "ic.json"))
    if report.get("status") != "pass" or len(inputs) != 3 or report.get("inputs") != inputs or report.get("simulation_inputs") != simulation:
        raise NoBoard("Manufacturing validation is failed or stale; rerun verification, parts lookup and netlist generation")


def _run(root, recorder=None):
    check_netlist_provenance(root)
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

    spec = {}
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    constraints, general_rules = apply_general_rules(constraints, netlist, spec)
    problems = semantic_errors(constraints, netlist)
    if problems:
        raise NoBoard("constraints.json:\n" + "\n".join(problems))
    if general_rules:
        constraints_path.write_text(json.dumps(constraints, indent=2) + "\n", encoding="utf-8")
    board_max = spec.get("board_max_mm")

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
        work = work_root / f"attempt-{attempt + 1}"
        record = attempt_board(work, problem, netlist, constraints, rules, attempt + 1, tools, recorder)
        record["attempt"] = attempt + 1
        record["status"] = "pass" if not record["reasons"] else "fail"
        attempts.append(record)
        if recorder:
            recorder.emit("attempt-result", attempt + 1, work, status=record["status"],
                          stage=record["stage"], reasons=record["reasons"])
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
    render = render_board(layout, tools["kicad_cli"])

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
        "general_rules": general_rules,
        "render": render,
        "attempts": [
            {key: a.get(key) for key in ("attempt", "seed", "extra_gap_mm", "stage", "status", "reasons")}
            for a in attempts
        ],
    }
    (layout / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if recorder:
        recorder.emit("finished", chosen_attempt=best["attempt"], status=report["status"], reasons=report["reasons"])
    return report


def main():
    from demo import positive_speed
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design")
    parser.add_argument("--demo", action="store_true", help="record results and animate them in KiCad")
    parser.add_argument("--speed", type=positive_speed, default=1, help="demo playback speed multiplier")
    args = parser.parse_args()
    root = design_root(args.design)
    try:
        report = run(root, demo=args.demo, speed=args.speed)
    except (NoBoard, LayoutError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(error, file=sys.stderr)
        return 2
    summary = {key: report[key] for key in ("status", "return_to", "board_mm", "reasons", "routing", "attempts")}
    print(json.dumps(summary, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
