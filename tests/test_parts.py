"""Parts lookup reads designs/<slug>/design and writes designs/<slug>/parts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "parts"))

from catalog import footprint_for  # noqa: E402
from lookup import choose_ic, lookup  # noqa: E402
from pins import pin_roles, symbol_pins  # noqa: E402
from netlist import main as netlist_main  # noqa: E402


CSV = """\
code,brand,model,package,type,describe,price,stock,library,category,file
C11702,Example,0402WGF1001TCE,0402,Resistor,1kΩ 50V 62.5mW ±1% 0402,0.0031,100,base,Resistors,
C74192,Example,XL1509-ADJE1,SOIC-8,DC-DC,1.23V~37V 2A 4.5V~40V Adjustable Buck,0.2,50,expand,Power Management (PMIC),
C10002,Example,LM2596SX-5.0/NOPB,TO-263-5,DC-DC,3A 4.5V~40V 5V Fixed Buck,0.05,100,base,Power Management (PMIC),
"""

SIM = """
R(ref="R1", value=1 @ u_kOhm)["p", "n"] += vin, vout
R(ref="RL", value=1.65 @ u_Ohm)["p", "n"] += vout, gnd
"""

SPEC = {
    "prompt": "5 V to 3.3 V switching regulator",
    "supply_voltage_v": 5,
    "output_voltage_v": 3.3,
    "output_current_a": 2,
    "load": "1.65 ohm",
    "tolerances": {"output_voltage_v": 0.05},
}


def libraries(tmp_path):
    footprints = tmp_path / "footprints"
    symbols = tmp_path / "symbols"
    (footprints / "Resistor_SMD.pretty").mkdir(parents=True)
    (footprints / "Resistor_SMD.pretty" / "R_0402_1005Metric.kicad_mod").write_text("(footprint)")
    (footprints / "Package_SO.pretty").mkdir()
    (footprints / "Package_SO.pretty" / "SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod").write_text("(footprint)")
    symbols.mkdir()
    (symbols / "Regulator_Switching.kicad_sym").write_text('\t(symbol "XL1509-ADJ"\n')
    return footprints, symbols


def design(tmp_path):
    circuit = tmp_path / "proj" / "design"
    circuit.mkdir(parents=True)
    (circuit / "circuit-spec.json").write_text(json.dumps(SPEC))
    (circuit / "skidl_sim.py").write_text(SIM)
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(CSV)
    return tmp_path / "proj", catalog


def test_lookup_writes_parts_from_the_design_folder(tmp_path):
    root, catalog = design(tmp_path)
    footprints, symbols = libraries(tmp_path)
    payload = lookup(root, catalog, footprints, symbols)
    written = json.loads((root / "parts" / "parts.json").read_text())
    assert written == payload
    by_ref = {part["ref"]: part for part in payload["parts"]}
    resistor = by_ref["R1"]
    assert resistor["lcsc"] == "C11702"
    assert resistor["price"] == 0.0031
    assert resistor["stock"] == 100
    assert resistor["availability"] == "basic"
    assert resistor["symbol"] == "Device:R"
    assert resistor["footprint"] == "Resistor_SMD:R_0402_1005Metric"
    assert resistor["changes_measured_value"] is False
    assert by_ref["RL"]["on_board"] is False
    regulator = by_ref["U1"]
    assert regulator["manufacturer_part_number"] == "XL1509-ADJE1"
    assert regulator["symbol"] == "Regulator_Switching:XL1509-ADJ"
    assert regulator["footprint"] == "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
    assert "C10002" not in json.dumps(payload)


def test_lookup_reports_a_value_the_cache_does_not_have(tmp_path):
    root, catalog = design(tmp_path)
    sim = (root / "design" / "skidl_sim.py").read_text()
    (root / "design" / "skidl_sim.py").write_text(sim + "\nR(ref=\"R2\", value=0.85 @ u_Ohm)\n")
    footprints, symbols = libraries(tmp_path)
    payload = lookup(root, catalog, footprints, symbols)
    missing = next(part for part in payload["parts"] if part["ref"] == "R2")
    assert missing["matched"] is False
    assert missing["lcsc"] is None
    assert missing["price"] is None


def test_netlist_aborts_without_a_footprint(tmp_path, monkeypatch):
    root, catalog = design(tmp_path)
    footprints, symbols = libraries(tmp_path)
    lookup(root, catalog, footprints, symbols)
    parts_path = root / "parts" / "parts.json"
    payload = json.loads(parts_path.read_text())
    payload["parts"][0]["footprint"] = None
    parts_path.write_text(json.dumps(payload))
    monkeypatch.setattr(sys, "argv", ["netlist.py", str(root)])
    assert netlist_main() == 2
    assert not (root / "parts" / "board.net").exists()


SYMBOL = """
(kicad_symbol_lib
	(symbol "XL1509-3.3"
		(symbol "XL1509-3.3_1_1"
			(pin power_in line (name "VIN") (number "1"))
			(pin power_out line (name "OUT") (number "2"))
			(pin input line (name "FB") (number "3"))
			(pin input line (name "~{EN}") (number "4"))
			(pin power_in line (name "GND") (number "5"))
		)
	)
	(symbol "XL1509-ADJ" (extends "XL1509-3.3"))
)
"""


def test_symbol_pins_follow_extends_and_name_the_switch_pin():
    roles = pin_roles([
        {"number": "1", "name": "VIN", "type": "power_in"},
        {"number": "2", "name": "OUT", "type": "power_out"},
        {"number": "4", "name": "~{EN}", "type": "input"},
    ], "buck")
    assert roles["input"] == "VIN"
    assert roles["switch"] == "OUT"
    assert roles["enable"] == "~{EN}"
    ldo = pin_roles([
        {"number": "3", "name": "VI", "type": "power_in"},
        {"number": "2", "name": "VO", "type": "power_out"},
        {"number": "1", "name": "GND", "type": "power_in"},
    ], "ldo")
    assert ldo["input"] == "VI"
    assert ldo["output"] == "VO"
    assert "switch" not in ldo


def test_choose_ic_writes_the_regulator_before_the_simulation(tmp_path):
    root, catalog = design(tmp_path)
    (root / "design" / "skidl_sim.py").unlink()
    footprints, symbols = libraries(tmp_path)
    (symbols / "Regulator_Switching.kicad_sym").write_text(SYMBOL)
    chosen = choose_ic(root, catalog, footprints, symbols)
    assert not (root / "design" / "skidl_sim.py").exists()
    written = json.loads((root / "design" / "ic.json").read_text())
    assert written == chosen
    assert chosen["manufacturer_part_number"] == "XL1509-ADJE1"
    assert chosen["roles"]["input"] == "VIN"
    assert chosen["roles"]["switch"] == "OUT"
    assert chosen["roles"]["feedback"] == "FB"
    assert chosen["topology"] == "buck"
    assert chosen["external_diode"] is True
    assert chosen["feedback_voltage_v"] == 1.23
    assert symbol_pins(chosen["symbol"], symbols)[0]["name"] == "VIN"


def test_lookup_keeps_the_ic_chosen_before_the_simulation(tmp_path):
    root, catalog = design(tmp_path)
    footprints, symbols = libraries(tmp_path)
    ic = {
        "ref": "U1",
        "kind": "regulator",
        "matched": True,
        "on_board": True,
        "requested_value": "kept",
        "manufacturer_part_number": "LM2596SX-5.0/NOPB",
        "lcsc": "C10002",
        "symbol": "Regulator_Switching:LM2596",
        "footprint": "Package_TO_SOT_SMD:TO-263-5_TabPin3",
        "changes_measured_value": False,
    }
    (root / "design" / "ic.json").write_text(json.dumps(ic))
    payload = lookup(root, catalog, footprints, symbols)
    regulators = [part for part in payload["parts"] if part["kind"] == "regulator"]
    assert len(regulators) == 1
    assert regulators[0]["lcsc"] == "C10002"


LDO_SYMBOL = """
(kicad_symbol_lib
	(symbol "AMS1117-3.3"
		(symbol "AMS1117-3.3_1_1"
			(pin power_in line (name "GND") (number "1"))
			(pin power_out line (name "VO") (number "2"))
			(pin power_in line (name "VI") (number "3"))
		)
	)
)
"""


def test_choose_ic_picks_an_ldo_when_the_prompt_asks_for_one(tmp_path):
    root, catalog = design(tmp_path)
    spec = json.loads((root / "design" / "circuit-spec.json").read_text())
    spec["prompt"] = "5 V to 3.3 V LDO"
    spec["output_current_a"] = 0.1
    (root / "design" / "circuit-spec.json").write_text(json.dumps(spec))
    (root / "design" / "skidl_sim.py").unlink()
    catalog.write_text(
        CSV
        + "C14289,Example,HT7533-1,SOT-89-3,LDO,100mA 3.3V Fixed Positive LDO,0.01,100,base,Power Management (PMIC),\n"
        + "C6186,Example,AMS1117-3.3,SOT-223,LDO,1A 3.3V Fixed Positive LDO,0.2,100,base,Power Management (PMIC),\n"
    )
    footprints, symbols = libraries(tmp_path)
    (footprints / "Package_TO_SOT_SMD.pretty").mkdir()
    (footprints / "Package_TO_SOT_SMD.pretty" / "SOT-223-3_TabPin2.kicad_mod").write_text("(footprint)")
    (footprints / "Package_TO_SOT_SMD.pretty" / "SOT-89-3.kicad_mod").write_text("(footprint)")
    (symbols / "Regulator_Linear.kicad_sym").write_text(LDO_SYMBOL)
    (symbols / "power.kicad_sym").write_text('\t(symbol "HT"\n')
    chosen = choose_ic(root, catalog, footprints, symbols)
    assert chosen["manufacturer_part_number"] == "AMS1117-3.3"
    assert chosen["topology"] == "ldo"
    assert chosen["external_diode"] is False
    assert chosen["roles"]["output"] == "VO"
    assert "switch" not in chosen["roles"]


def test_lookup_matches_the_catch_diode_an_asynchronous_buck_needs(tmp_path):
    root, catalog = design(tmp_path)
    spec = json.loads((root / "design" / "circuit-spec.json").read_text())
    spec["output_current_a"] = 0.1
    (root / "design" / "circuit-spec.json").write_text(json.dumps(spec))
    sim = (root / "design" / "skidl_sim.py").read_text()
    (root / "design" / "skidl_sim.py").write_text(sim + '\nD(ref="D1")["p", "n"] += gnd, switch\n')
    catalog.write_text(CSV + "C191023,Example,1N5819WS,SOD-323,Schottky Diodes,1A 40V 600mV@1A Schottky,0.0137,100,base,Diodes,\n")
    footprints, symbols = libraries(tmp_path)
    (footprints / "Diode_SMD.pretty").mkdir()
    (footprints / "Diode_SMD.pretty" / "D_SOD-323.kicad_mod").write_text("(footprint)")
    payload = lookup(root, catalog, footprints, symbols)
    diode = next(part for part in payload["parts"] if part["kind"] == "diode")
    assert diode["matched"] is True
    assert diode["lcsc"] == "C191023"
    assert diode["symbol"] == "Device:D"
    assert diode["footprint"] == "Diode_SMD:D_SOD-323"
    assert diode["current_rating_a"] == 1.0


def test_lookup_rejects_an_asynchronous_buck_with_no_catch_diode(tmp_path):
    root, catalog = design(tmp_path)
    footprints, symbols = libraries(tmp_path)
    payload = lookup(root, catalog, footprints, symbols)
    diode = next(part for part in payload["parts"] if part["kind"] == "diode")
    assert diode["matched"] is False
    assert "catch diode" in diode["reason"]


def _mods(directory, names):
    directory.mkdir(parents=True)
    for name in names:
        (directory / f"{name}.kicad_mod").write_text("(footprint)")


def test_exact_package_footprint_wins_over_a_near_name(tmp_path):
    root = tmp_path / "fp"
    _mods(root / "Package_SO.pretty", [
        "SOIC-8_3.9x4.9mm_P1.27mm",
        "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.71x3.7mm",
    ])
    assert footprint_for("regulator", "SOIC-8", root) == "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"


def test_missing_package_uses_the_closest_footprint(tmp_path):
    root = tmp_path / "fp"
    _mods(root / "Package_SO.pretty", [
        "SOIC-14_3.9x8.7mm_P1.27mm",
        "SOIC-8_3.9x4.9mm_P1.27mm",
        "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.71x3.7mm_ThermalVias",
        "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.71x3.7mm",
    ])
    _mods(root / "Resistor_SMD.pretty", [
        "R_0402_1005Metric",
        "R_0201_0603Metric_Pad0.64x0.40mm_HandSolder",
        "R_0201_0603Metric",
    ])
    _mods(root / "Package_TO_SOT_SMD.pretty", ["SOT-23", "SOT-23-6", "SOT-23_Handsoldering"])
    assert footprint_for("regulator", "SOIC-8-EP", root) == "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.71x3.7mm"
    assert footprint_for("resistor", "0201", root) == "Resistor_SMD:R_0201_0603Metric"
    assert footprint_for("regulator", "SOT-23-3L", root) == "Package_TO_SOT_SMD:SOT-23"


def test_netlist_requires_board_net(tmp_path, monkeypatch):
    root, catalog = design(tmp_path)
    spec = json.loads((root / "design" / "circuit-spec.json").read_text())
    spec["output_current_a"] = 0.1
    (root / "design" / "circuit-spec.json").write_text(json.dumps(spec))
    sim = (root / "design" / "skidl_sim.py").read_text()
    (root / "design" / "skidl_sim.py").write_text(sim + '\nD(ref="D1")["p", "n"] += gnd, switch\n')
    catalog.write_text(CSV + "C191023,Example,1N5819WS,SOD-323,Schottky Diodes,1A 40V 600mV@1A Schottky,0.0137,100,base,Diodes,\n")
    footprints, symbols = libraries(tmp_path)
    (footprints / "Diode_SMD.pretty").mkdir()
    (footprints / "Diode_SMD.pretty" / "D_SOD-323.kicad_mod").write_text("(footprint)")
    lookup(root, catalog, footprints, symbols)
    script = root / "parts" / "skidl_kicad.py"
    script.write_text("from pathlib import Path\nPath('board.net').write_text('(netlist)')\n")
    monkeypatch.setattr(sys, "argv", ["netlist.py", str(root)])
    assert netlist_main() == 0
    assert (root / "parts" / "board.net").is_file()
