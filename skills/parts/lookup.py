#!/usr/bin/env python3
"""Choose catalog parts for one design and write designs/<slug>/parts/parts.json.

Reads designs/<slug>/design/. Does not use the network.
"""

import ast
import math
import json
import os
import re
import sys
from pathlib import Path

from catalog import (
    default_catalog,
    load_catalog,
    relative_error,
    search_diode,
    search_passive,
    search_regulator,
    si_from_skidl,
)
from pins import pin_roles, symbol_pins
from validation import digest, rating_checks, simulation_evidence


CALL = re.compile(r"\b([RCLD])\s*\(([^)]*)\)")
VALUE = re.compile(r"value\s*=\s*([0-9.]+)\s*@\s*(u_[A-Za-z]+)")
REF = re.compile(r'ref\s*=\s*"([^"]+)"')

KIND = {"R": "resistor", "C": "capacitor", "L": "inductor", "D": "diode"}
REGULATOR_WORDS = ("regulator", "buck", "boost", "ldo", "converter")

FOOTPRINT_DIR = Path(os.environ.get("KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints"))
SYMBOL_DIR = Path(os.environ.get("KICAD_SYMBOL_DIR", os.environ.get("KICAD10_SYMBOL_DIR", "/usr/share/kicad/symbols")))


def design_root(path):
    path = Path(path).resolve()
    if path.name == "design" and (path / "circuit-spec.json").is_file():
        return path.parent
    return path


def requests_from_sim(source, spec):
    """Conservative static fallback; executed circuit evidence is preferred.

    Never evaluate user Python to extract values. Reject expressions we cannot resolve.
    External components must be declared by reference, never guessed by resistance.
    """
    tree = ast.parse(source)
    constants = {}
    requests = []
    def number(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name) and node.id in constants:
            return constants[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -number(node.operand)
        raise ValueError("Unresolved component value; run verify.py to extract the executed circuit")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id not in KIND:
            continue
        args = {kw.arg: kw.value for kw in node.keywords}
        ref_node = args.get("ref")
        ref = ref_node.value if isinstance(ref_node, ast.Constant) and isinstance(ref_node.value, str) else None
        if not ref:
            raise ValueError("Component has no explicit ref; run verify.py to obtain generated references")
        kind = KIND[node.func.id]
        value = args.get("value")
        if kind == "diode":
            value_si = None
        elif isinstance(value, ast.BinOp) and isinstance(value.op, ast.MatMult) and isinstance(value.right, ast.Name):
            value_si = si_from_skidl(number(value.left), value.right.id)
        else:
            value_si = number(value)
        if value_si is not None and (not math.isfinite(value_si) or value_si <= 0):
            raise ValueError(f"{ref}: passive value must be finite and positive")
        requests.append({"ref": ref, "kind": kind, "value_si": value_si,
                         "requested_value": str(value_si),
                         "on_board": ref not in spec.get("external_components", [])})
    return requests


def blank(request, reason):
    return {
        "ref": request.get("ref"),
        "kind": request["kind"],
        "requested_value": request.get("requested_value"),
        "on_board": request.get("on_board", True),
        "matched": False,
        "reason": reason,
        "lcsc": None,
        "manufacturer_part_number": None,
        "manufacturer": None,
        "value": None,
        "tolerance": None,
        "voltage_rating_v": None,
        "current_rating_a": None,
        "power_rating_w": None,
        "package": None,
        "stock": None,
        "price": None,
        "availability": None,
        "symbol": None,
        "footprint": None,
        "changes_measured_value": False,
    }


def from_match(request, match):
    changed = False
    if request.get("value_si") is not None and match.get("value_si") is not None:
        changed = relative_error(match["value_si"], request["value_si"]) > 1e-9
    record = {
        "ref": request.get("ref"),
        "kind": request["kind"],
        "requested_value": request.get("requested_value"),
        "on_board": request.get("on_board", True),
        "matched": True,
        "reason": None,
        "changes_measured_value": changed,
    }
    for key in (
        "lcsc", "manufacturer_part_number", "manufacturer", "value", "value_si", "tolerance",
        "voltage_rating_v", "current_rating_a", "power_rating_w", "package",
        "stock", "price", "availability", "symbol", "footprint", "datasheet",
        "topology", "adjustable", "feedback_voltage_v", "external_diode", "footprint_match",
    ):
        record[key] = match.get(key)
    if record["symbol"] is None or record["footprint"] is None:
        record["matched"] = False
        record["reason"] = "catalog part has no KiCad symbol or footprint in the installed libraries"
    return record


def wants_regulator(spec):
    prompt = (spec.get("prompt") or "").lower()
    return any(word in prompt for word in REGULATOR_WORDS)


def regulator_request(spec):
    return {
        "ref": "U1",
        "kind": "regulator",
        "requested_value": f"{spec.get('output_voltage_v')} V at {spec.get('output_current_a')} A from {spec.get('supply_voltage_v')} V",
        "on_board": True,
    }


def saved_ic(circuit):
    path = circuit / "ic.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind") == "regulator" and data.get("matched") and data.get("manufacturer_part_number"):
        return data
    return None


def select(spec, sim_source, rows, footprint_dir, symbol_dir, ic=None, requests=None):
    chosen = []
    for request in requests if requests is not None else requests_from_sim(sim_source, spec):
        if request["kind"] == "diode":
            match = search_diode(
                rows, spec.get("supply_voltage_v"), spec.get("output_current_a"), footprint_dir, symbol_dir,
            )
            reason = "no cached Schottky diode is rated for the supply voltage and the output current"
            chosen.append(from_match(request, match) if match else blank(request, reason))
            continue
        match = search_passive(
            rows, request["kind"], request["value_si"], spec.get("supply_voltage_v"), footprint_dir, symbol_dir, request.get("stress"),
        )
        chosen.append(from_match(request, match) if match else blank(request, "no stocked catalog part meets the requested value, observed stress, and footprint requirements"))
    if ic is not None:
        chosen.append(ic)
    elif wants_regulator(spec):
        match = search_regulator(rows, spec, footprint_dir, symbol_dir)
        request = regulator_request(spec)
        chosen.append(from_match(request, match) if match else blank(request, "no cached regulator meets the output voltage, current, and supply"))
    needs_diode = ic.get("external_diode") if ic else any(part.get("external_diode") for part in chosen)
    if needs_diode and not any(part["kind"] == "diode" for part in chosen):
        chosen.append(blank(
            {"ref": "D1", "kind": "diode", "requested_value": "schottky catch diode", "on_board": True},
            "this regulator is asynchronous, so skidl_sim.py needs a catch diode from ground to the switch node",
        ))
    return chosen


def choose_ic(root, catalog_path=None, footprint_dir=FOOTPRINT_DIR, symbol_dir=SYMBOL_DIR):
    """Write design/ic.json from the spec. The simulation file is not required."""
    root = design_root(root)
    circuit = root / "design"
    spec_path = circuit / "circuit-spec.json"
    if not spec_path.is_file():
        raise FileNotFoundError(f"{spec_path} does not exist")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    destination = circuit / "ic.json"
    if not wants_regulator(spec):
        destination.unlink(missing_ok=True)
        return None
    catalog_path = Path(catalog_path) if catalog_path else default_catalog()
    if not catalog_path.is_file():
        raise FileNotFoundError(
            f"no JLCPCB cache at {catalog_path}. Run: .venv/bin/python skills/parts/fetch_catalog.py"
        )
    match = search_regulator(load_catalog(catalog_path), spec, footprint_dir, symbol_dir)
    if match is None:
        raise LookupError("no cached regulator meets the output voltage, current, and supply")
    record = from_match(regulator_request(spec), match)
    record["spec_sha256"] = digest(spec_path)
    record["pins"] = symbol_pins(record.get("symbol"), symbol_dir)
    record["roles"] = pin_roles(record["pins"], record.get("topology"))
    circuit.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def lookup(root, catalog_path=None, footprint_dir=FOOTPRINT_DIR, symbol_dir=SYMBOL_DIR):
    root = design_root(root)
    circuit = root / "design"
    spec_path = circuit / "circuit-spec.json"
    sim_path = circuit / "skidl_sim.py"
    if not spec_path.is_file() or not sim_path.is_file():
        raise FileNotFoundError(f"{circuit} needs circuit-spec.json and skidl_sim.py")
    catalog_path = Path(catalog_path) if catalog_path else default_catalog()
    if not catalog_path.is_file():
        raise FileNotFoundError(
            f"no JLCPCB cache at {catalog_path}. Run: .venv/bin/python skills/parts/fetch_catalog.py"
        )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    skip_verify = spec.get("skip_verify") is True
    evidence, evidence_error = simulation_evidence(circuit)
    requests = None
    if evidence is not None:
        requests = [dict(item, requested_value=str(item.get("value_si")),
                         on_board=item["ref"] not in spec.get("external_components", []))
                    for item in evidence.get("components", [])]
    ic = saved_ic(circuit)
    parts = select(
        spec,
        sim_path.read_text(encoding="utf-8"),
        load_catalog(catalog_path),
        footprint_dir,
        symbol_dir,
        ic,
        requests=requests,
    )
    stresses = {item["ref"]: item.get("stress", {}) for item in (requests or [])}
    for part in parts:
        part["rating_checks"] = rating_checks(part, stresses.get(part.get("ref"), {}))
    reasons = [] if skip_verify else ([evidence_error] if evidence_error else [])
    if ic and ic.get("spec_sha256") != digest(spec_path):
        reasons.append("Selected IC has no current spec provenance; rerun choose_ic.py and verify.py")
    if not parts or not any(p.get("on_board") for p in parts):
        reasons.append("No physical board components were selected")
    declared_external = set(spec.get("external_components", []))
    if declared_external - {p.get("ref") for p in parts}:
        reasons.append("external_components contains references absent from the simulation")
    for part in parts:
        ratings_block = any(c["status"] == "fail" or (not skip_verify and c["status"] != "pass") for c in part["rating_checks"])
        if part.get("on_board") and (not part.get("matched") or part.get("changes_measured_value")
                or part.get("footprint_match") != "exact"
                or ratings_block):
            reasons.append(f"{part.get('ref')}: selection, exact footprint mapping or observed-stress rating is unresolved")
    limitations = ["Ratings cover only simulated conditions; thermal derating, tolerances, IC model fidelity and datasheet limits require engineering review."]
    if skip_verify:
        limitations.insert(0, "skip_verify is set: ngspice checks and observed-stress ratings were not required.")
    payload = {"source": str(catalog_path), "parts": parts, "status": "unverified" if reasons else "pass",
               "verify": "skipped" if skip_verify else "checked",
               "reasons": reasons, "simulation_inputs": evidence.get("inputs") if evidence else None,
               "simulation_evidence_sha256": digest(circuit / "simulation-evidence.json") if evidence else None,
               "limitations": limitations}
    destination = root / "parts"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "parts.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main():
    if len(sys.argv) != 2:
        print("usage: lookup.py designs/<slug>", file=sys.stderr)
        return 2
    try:
        payload = lookup(sys.argv[1], os.environ.get("PCB_JLCPCB_CSV"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2))
    incomplete = [
        part for part in payload["parts"]
        if part.get("on_board") and (not part.get("matched") or part.get("changes_measured_value"))
    ]
    for part in incomplete:
        reason = part["reason"] or "selected value differs from the simulated value"
        print(f"{part['kind']} {part.get('ref') or ''} {reason}", file=sys.stderr)
    return 1 if incomplete or payload["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
