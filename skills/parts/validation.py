"""Evidence freshness and observed-stress checks shared by parts and netlist stages."""

import hashlib
import json
import math
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simulation_evidence(circuit):
    path = circuit / "simulation-evidence.json"
    if not path.is_file():
        return None, "Run verify.py: simulation evidence is missing"
    evidence = json.loads(path.read_text())
    expected = {name: digest(circuit / name) for name in
                ("skidl_sim.py", "circuit-spec.json", "ic.json") if (circuit / name).is_file()}
    if evidence.get("version") != 1 or evidence.get("inputs") != expected:
        return None, "Run verify.py: simulation evidence is stale"
    checks = evidence.get("checks")
    if evidence.get("status") != "pass" or not checks or any(c.get("status") != "pass" for c in checks):
        return None, "Simulation has no nonempty, passing check results"
    return evidence, None


def rating_checks(part, stress):
    required = {"resistor": [("power_w", "power_rating_w"), ("voltage_v", "voltage_rating_v")],
                "capacitor": [("voltage_v", "voltage_rating_v")],
                "inductor": [("current_a", "current_rating_a")],
                "diode": [("current_a", "current_rating_a"), ("voltage_v", "voltage_rating_v")]}
    checks = []
    for measured_key, rating_key in required.get(part["kind"], []):
        measured, rating = stress.get(measured_key), part.get(rating_key)
        valid = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    and v >= 0 for v in (measured, rating))
        status = "unverified" if not valid else "pass" if measured <= rating else "fail"
        checks.append({"quantity": measured_key, "measured": measured, "rating": rating, "status": status})
    return checks
