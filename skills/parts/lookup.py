#!/usr/bin/env python3
"""Choose catalog parts for one design and write designs/<slug>/parts/parts.json.

Reads designs/<slug>/design/. Does not use the network.
"""

import json
import os
import re
import sys
from pathlib import Path

from catalog import (
    default_catalog,
    load_catalog,
    parse_ohms,
    relative_error,
    search_diode,
    search_passive,
    search_regulator,
    si_from_skidl,
)
from pins import pin_roles, symbol_pins


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
    requests = []
    load_ohms = parse_ohms(spec.get("load") or "")
    for match in CALL.finditer(source):
        body = match.group(2)
        kind = KIND[match.group(1)]
        ref = REF.search(body)
        value = VALUE.search(body)
        if kind == "diode":
            requests.append({
                "ref": ref.group(1) if ref else None,
                "kind": "diode",
                "value_si": None,
                "requested_value": "schottky catch diode",
                "on_board": True,
            })
            continue
        if value is None:
            continue
        value_si = si_from_skidl(value.group(1), value.group(2))
        on_board = True
        if kind == "resistor" and load_ohms is not None and relative_error(value_si, load_ohms) <= 0.01:
            on_board = False
        requests.append({
            "ref": ref.group(1) if ref else None,
            "kind": kind,
            "value_si": value_si,
            "requested_value": f"{value.group(1)} {value.group(2)}",
            "on_board": on_board,
        })
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
        changed = relative_error(match["value_si"], request["value_si"]) > 0.01
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
        "lcsc", "manufacturer_part_number", "manufacturer", "value", "tolerance",
        "voltage_rating_v", "current_rating_a", "power_rating_w", "package",
        "stock", "price", "availability", "symbol", "footprint", "datasheet",
        "topology", "adjustable", "feedback_voltage_v", "external_diode",
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


def select(spec, sim_source, rows, footprint_dir, symbol_dir, ic=None):
    chosen = []
    for request in requests_from_sim(sim_source, spec):
        if request["kind"] == "diode":
            match = search_diode(
                rows, spec.get("supply_voltage_v"), spec.get("output_current_a"), footprint_dir, symbol_dir,
            )
            reason = "no cached Schottky diode is rated for the supply voltage and the output current"
            chosen.append(from_match(request, match) if match else blank(request, reason))
            continue
        match = search_passive(
            rows, request["kind"], request["value_si"], spec.get("supply_voltage_v"), footprint_dir, symbol_dir,
        )
        chosen.append(from_match(request, match) if match else blank(request, "no catalog part within 1% of the requested value"))
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
    parts = select(
        spec,
        sim_path.read_text(encoding="utf-8"),
        load_catalog(catalog_path),
        footprint_dir,
        symbol_dir,
        saved_ic(circuit),
    )
    payload = {"source": str(catalog_path), "parts": parts}
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
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
