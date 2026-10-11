#!/usr/bin/env python3
"""Run a design's skidl_sim.py, judge each measurement against its spec, and write simulation-results.json.

Exit 0 when every check passes, 1 when any check fails, 2 when there is no trustworthy result.
"""

import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path


MEASURED = ("output_voltage_v", "gain", "bandwidth_hz", "output_current_a")

TIMEOUT_S = None  # No deadline; cancellation belongs to the user.
PROBE = Path(__file__).with_name("probe.py")

HINTS = (
    (
        r"name 'u_\w+' is not defined",
        "Unit names are case-sensitive: u_V, u_mV, u_A, u_mA, u_Ohm, u_kOhm, u_F, u_uF, u_nF, u_pF, "
        "u_H, u_uH, u_mH, u_s, u_ms, u_us, u_ns, u_Hz, u_kHz, u_MHz.",
    ),
    (
        r"has no attribute '(transient|operating_point|dc|ac|simulator)'",
        "Simulate with sim = Simulator.factory().simulation(circuit), then call sim.operating_point() "
        "or sim.transient(step_time=..., end_time=...).",
    ),
    (
        r"(nodes|branches)\[[^\n]*\n[^\n]*KeyError",
        "Index nodes by lowercase net name, such as analysis.nodes['vout'], "
        "and source currents by lowercase source ref, such as analysis.branches['vs'].",
    ),
    (
        r"missing \d+ required positional arguments?: 'node_plus'",
        "A source was created but its pins were never connected. "
        "Connect it in the same statement, such as PULSEV(...)[\"p\", \"n\"] += gate, gnd, or delete it.",
    ),
)


class NoResult(Exception):
    pass


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def judge(requirement, target, measured, tolerance):
    if tolerance < 0:
        raise ValueError(f"{requirement}: tolerance must not be negative")
    inside = math.isfinite(measured) and abs(measured - target) <= tolerance
    return {
        "requirement": requirement,
        "target": target,
        "measured": measured,
        "tolerance": tolerance,
        "status": "pass" if inside else "fail",
    }


def expected_checks(spec):
    tolerances = spec.get("tolerances")
    if not isinstance(tolerances, dict):
        tolerances = {}
    checks = []
    missing = []
    for name in MEASURED:
        if not is_number(spec.get(name)):
            continue
        if not is_number(tolerances.get(name)):
            missing.append(name)
            continue
        checks.append({"requirement": name, "target": spec[name], "tolerance": tolerances[name]})
    if missing:
        raise ValueError("circuit-spec.json has no tolerance for " + ", ".join(missing))
    return checks


def circuit_dir(root):
    root = Path(root).resolve()
    if root.name == "design" and (root / "circuit-spec.json").is_file():
        return root
    return root / "design"


def brief(stderr):
    lines = [line for line in stderr.splitlines() if line.strip() and not line.startswith("WARNING:")]
    starts = [i for i, line in enumerate(lines) if line.startswith("Traceback (most recent call last)")]
    if not starts:
        return "\n".join(lines)
    trace = lines[starts[-1] + 1:]
    shown = []
    for i, line in enumerate(trace):
        match = re.match(r'\s*File "([^"]+)", line (\d+), in (\S+)', line)
        if match and Path(match.group(1)).name == "skidl_sim.py":
            code = trace[i + 1].strip() if i + 1 < len(trace) else ""
            shown.append(f"skidl_sim.py line {match.group(2)}, in {match.group(3)}: {code}")
    error = next((line for line in reversed(trace) if not line.startswith(" ")), trace[-1] if trace else "")
    text = "\n".join(shown + [error])
    for pattern, hint in HINTS:
        if re.search(pattern, "\n".join(trace)):
            text += "\nHint: " + hint
            break
    return text


def measure(design):
    design = circuit_dir(design)
    sim = design / "skidl_sim.py"
    if not sim.is_file():
        raise NoResult(f"{sim} does not exist")
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "measurements.json"
        evidence_path = Path(scratch) / "evidence.json"
        (design / "simulation-evidence.json").unlink(missing_ok=True)
        try:
            proc = subprocess.run(
                [sys.executable, str(PROBE), str(sim), str(out), str(evidence_path)],
                cwd=design,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            raise NoResult(f"skidl_sim.py did not finish in {TIMEOUT_S} s")
        (design / "simulation.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise NoResult(f"skidl_sim.py exited {proc.returncode}\n{brief(proc.stderr)}")
        if not out.exists():
            raise NoResult("measure() returned without writing measurements")
        measurements = json.loads(out.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text())
        evidence.update(version=1, status="unverified", inputs={
            name: hashlib.sha256((design / name).read_bytes()).hexdigest()
            for name in ("skidl_sim.py", "circuit-spec.json", "ic.json") if (design / name).is_file()
        })
        (design / "simulation-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if not isinstance(measurements, dict):
        raise NoResult("measure() must return a dict of spec field to measured number")
    return measurements


def run(design):
    design = circuit_dir(design)
    spec = json.loads((design / "circuit-spec.json").read_text(encoding="utf-8"))
    checks = expected_checks(spec)
    if not checks:
        raise ValueError("circuit-spec.json has no measured requirement to test")
    measurements = measure(design)
    results = []
    for check in checks:
        name = check["requirement"]
        value = measurements.get(name)
        if not is_number(value) or not math.isfinite(value):
            raise NoResult(f"measure() returned no finite number for {name}: {value!r}")
        results.append(judge(name, check["target"], float(value), check["tolerance"]))
    evidence_path = design / "simulation-evidence.json"
    if evidence_path.is_file():
        evidence = json.loads(evidence_path.read_text())
        evidence.update(status="pass" if all(r["status"] == "pass" for r in results) else "fail", checks=results)
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    return results


def explain(result):
    measured = result["measured"]
    target = result["target"]
    name = result["requirement"]
    if not math.isfinite(measured):
        return f"{name} failed: measured {measured} is not finite, target {target}"
    error = measured - target
    direction = "high" if error > 0 else "low"
    return (
        f"{name} failed: measured {measured}, target {target}, "
        f"tolerance {result['tolerance']}, {abs(error)} {direction}"
    )


def main():
    if len(sys.argv) != 2:
        print("usage: verify.py designs/<slug>", file=sys.stderr)
        return 2
    design = circuit_dir(Path(sys.argv[1]))
    out = design / "simulation-results.json"
    try:
        results = run(design)
    except (ValueError, NoResult, OSError) as error:
        out.unlink(missing_ok=True)
        print(error, file=sys.stderr)
        return 2
    text = json.dumps(results, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    print(text, end="")
    failed = [result for result in results if result["status"] != "pass"]
    for result in failed:
        print(explain(result), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
