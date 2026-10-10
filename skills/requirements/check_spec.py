#!/usr/bin/env python3
"""Report circuit-spec fields that are too thin to test. Exit 1 when any are missing."""

import json
import sys


MEASURED = ("output_voltage_v", "gain", "bandwidth_hz", "output_current_a")

QUESTIONS = {
    "supply_voltage_v": "What is the supply voltage, in volts?",
    "output_voltage_v": "What output voltage should the circuit hold, in volts?",
    "gain": "What voltage gain should the circuit have?",
    "bandwidth_hz": "What bandwidth, in hertz, should the circuit meet?",
    "output_current_a": "What output current, in amperes, should the circuit deliver?",
    "load": "What load should that output be tested into?",
    "interfaces": "Which interfaces does the circuit use?",
    "board_max_mm": "What is the maximum board width and height, in millimeters?",
    "manufacturing.vendor": "Which manufacturer or assembly shop should the board use?",
    "tolerances.output_voltage_v": "What absolute error, in volts, is allowed on the output voltage?",
    "tolerances.gain": "What absolute error is allowed on the gain?",
    "tolerances.bandwidth_hz": "What absolute error, in hertz, is allowed on the bandwidth?",
    "tolerances.output_current_a": "What absolute error, in amperes, is allowed on the output current?",
}


def kinds(prompt):
    text = prompt.lower()
    found = []
    if any(word in text for word in ("regulator", "buck", "boost", "ldo", "converter")):
        found.append("regulator")
    if any(word in text for word in ("amplifier", "op-amp", "opamp", "gain")):
        found.append("amplifier")
    if any(word in text for word in ("filter", "cutoff")):
        found.append("filter")
    if any(word in text for word in ("sensor", "adc", "interface")):
        found.append("sensor")
    if any(word in text for word in ("mcu", "microcontroller", "peripheral")):
        found.append("mcu")
    return found or ["generic"]


def missing_fields(spec):
    prompt = spec.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return ["prompt"]
    text = prompt.lower()
    needed = []
    selected = kinds(prompt)
    if "passive" not in text:
        needed.append("supply_voltage_v")
    if "regulator" in selected:
        needed.extend(["output_voltage_v", "output_current_a", "load"])
    if "amplifier" in selected:
        needed.extend(["gain", "bandwidth_hz", "load"])
    if "filter" in selected:
        needed.append("bandwidth_hz")
    if "sensor" in selected or "mcu" in selected:
        needed.append("interfaces")
    if selected == ["generic"]:
        if not any(isinstance(spec.get(name), (int, float)) for name in MEASURED):
            needed.append("output_voltage_v")
        if "output_current_a" not in needed and "load" not in needed:
            if spec.get("output_current_a") is None and spec.get("load") is None:
                needed.append("load")
    if any(word in text for word in ("small", "compact", "tiny", "board size")):
        board = spec.get("board_max_mm")
        if not isinstance(board, dict) or not all(isinstance(board.get(side), (int, float)) for side in ("width", "height")):
            needed.append("board_max_mm")
    if any(word in text for word in ("jlcpcb", "pcbway", "oshpark", "manufactur")):
        vendor = spec.get("manufacturing")
        if not isinstance(vendor, dict) or not isinstance(vendor.get("vendor"), str) or not vendor["vendor"].strip():
            needed.append("manufacturing.vendor")
    tolerances = spec.get("tolerances")
    if not isinstance(tolerances, dict):
        tolerances = {}
    for name in MEASURED:
        if isinstance(spec.get(name), (int, float)) or name in needed:
            if not isinstance(tolerances.get(name), (int, float)):
                needed.append(f"tolerances.{name}")
    seen = []
    for name in needed:
        if name not in seen:
            seen.append(name)
    absent = []
    for name in seen:
        if name.startswith("tolerances."):
            absent.append(name)
            continue
        if name == "manufacturing.vendor":
            absent.append(name)
            continue
        if name == "board_max_mm":
            absent.append(name)
            continue
        value = spec.get(name)
        if name == "interfaces":
            if not isinstance(value, list) or not value:
                absent.append(name)
        elif name == "load":
            if not isinstance(value, str) or not value.strip():
                absent.append(name)
        elif value is None:
            absent.append(name)
    return absent


def main():
    if len(sys.argv) != 2:
        print("usage: check_spec.py <circuit-spec.json>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as handle:
        spec = json.load(handle)
    missing = missing_fields(spec)
    print(json.dumps({
        "ok": not missing,
        "missing": [{"field": name, "ask": QUESTIONS.get(name, f"What value should {name} have?")} for name in missing],
    }, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
