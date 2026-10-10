#!/usr/bin/env python3
"""Run a design's skidl_sim.py, judge each measurement against its spec, and write simulation-results.json.

Exit 0 when every check passes, 1 when any check fails, 2 when there is no trustworthy result.
"""

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


MEASURED = ("output_voltage_v", "gain", "bandwidth_hz", "output_current_a")

TIMEOUT_S = 600

PROBE = """
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("skidl_sim", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if not callable(getattr(module, "measure", None)):
    sys.exit("skidl_sim.py does not define measure()")
measurements = module.measure()
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(measurements, handle)
"""


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


def measure(design):
    sim = design / "skidl_sim.py"
    if not sim.is_file():
        raise NoResult(f"{sim} does not exist")
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "measurements.json"
        try:
            proc = subprocess.run(
                [sys.executable, "-c", PROBE, str(sim), str(out)],
                cwd=design,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            raise NoResult(f"skidl_sim.py did not finish in {TIMEOUT_S} s")
        if proc.returncode != 0:
            raise NoResult(f"skidl_sim.py exited {proc.returncode}\n{proc.stderr.strip()}")
        if not out.exists():
            raise NoResult("measure() returned without writing measurements")
        measurements = json.loads(out.read_text(encoding="utf-8"))
    if not isinstance(measurements, dict):
        raise NoResult("measure() must return a dict of spec field to measured number")
    return measurements


def run(design):
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
        print("usage: verify.py <design-dir>", file=sys.stderr)
        return 2
    design = Path(sys.argv[1]).resolve()
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
