#!/usr/bin/env python3
"""Generate a fresh netlist, then validate parts, pins, interfaces and connectivity."""

import json
import os
import subprocess
import sys
from pathlib import Path

from netlist_checks import validate
from validation import digest, rating_checks, simulation_evidence


def design_root(path):
    path = Path(path).resolve()
    if path.name in {"design", "parts"} and (path.parent / "design" / "circuit-spec.json").is_file():
        return path.parent
    return path


def run(root):
    root = design_root(root)
    folder = root / "parts"
    netlist = folder / "board.net"
    report_path = folder / "netlist-report.json"
    folder.mkdir(parents=True, exist_ok=True)
    report_path.unlink(missing_ok=True)
    # Do not let a previous successful artifact survive a failed generation.
    netlist.unlink(missing_ok=True)
    report = {"version": 1, "status": "fail", "errors": []}
    try:
        payload = json.loads((folder / "parts.json").read_text())
        spec = json.loads((root / "design" / "circuit-spec.json").read_text())
        skip_verify = spec.get("skip_verify") is True and payload.get("verify") == "skipped"
        if skip_verify:
            if payload.get("status") != "pass":
                raise ValueError("Parts are unresolved; rerun lookup.py and resolve its reasons")
            evidence = {"components": []}
        else:
            evidence, error = simulation_evidence(root / "design")
            if error:
                raise ValueError(error)
            if (payload.get("status") != "pass" or payload.get("simulation_inputs") != evidence["inputs"]
                    or payload.get("simulation_evidence_sha256") != digest(root / "design" / "simulation-evidence.json")):
                raise ValueError("Parts are unverified or stale; rerun lookup.py and resolve its reasons")
        parts = payload["parts"]
        if not skip_verify:
            stresses = {item["ref"]: item.get("stress", {}) for item in evidence.get("components", [])}
            for part in parts:
                if part.get("on_board") and any(c["status"] != "pass" for c in rating_checks(part, stresses.get(part.get("ref"), {}))):
                    raise ValueError(f"{part.get('ref')}: rating evidence does not pass")
        def unresolved(part):
            if not part.get("on_board"):
                return False
            ratings_block = any(c["status"] == "fail" or (not skip_verify and c["status"] != "pass") for c in part.get("rating_checks", []))
            return not part.get("matched") or not part.get("footprint") or part.get("changes_measured_value") or ratings_block
        if not parts or any(unresolved(part) for part in parts):
            raise ValueError("A board part is unmatched, unrated, or differs from its simulated value")
        script = folder / "skidl_kicad.py"
        env = os.environ.copy()
        symbol_dir = env.get("KICAD10_SYMBOL_DIR") or env.get("KICAD_SYMBOL_DIR") or "/usr/share/kicad/symbols"
        env.update(KICAD_SYMBOL_DIR=symbol_dir, KICAD10_SYMBOL_DIR=symbol_dir)
        proc = subprocess.run([sys.executable, str(script)], cwd=folder, env=env, text=True,
                              capture_output=True)
        (folder / "netlist.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode or not netlist.is_file():
            raise ValueError("Generator failed or did not write a fresh board.net; see parts/netlist.log")
        report["errors"] = validate(netlist.read_text(), parts, evidence, spec,
            Path(env.get("KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints")), Path(symbol_dir))
        if report["errors"]:
            (folder / "rejected.net").write_bytes(netlist.read_bytes())
            netlist.unlink()
        else:
            passed = {"status": "pass", "inputs": {"board.net": digest(netlist), "parts.json": digest(folder / "parts.json"),
                                                   "skidl_kicad.py": digest(script)},
                      "simulation_inputs": evidence.get("inputs")}
            evidence_path = root / "design" / "simulation-evidence.json"
            if evidence_path.is_file():
                passed["simulation_evidence_sha256"] = digest(evidence_path)
            report.update(passed)
            report["limitations"] = payload.get("limitations", [])
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        netlist.unlink(missing_ok=True)
        report["errors"].append(str(error))
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    if len(sys.argv) != 2:
        print("usage: netlist.py designs/<slug>", file=sys.stderr)
        return 2
    report = run(sys.argv[1])
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
