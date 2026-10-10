"""Parts lookup reads designs/<slug>/design and writes designs/<slug>/parts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "parts"))

from lookup import lookup  # noqa: E402
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


def test_netlist_requires_board_net(tmp_path, monkeypatch):
    root, catalog = design(tmp_path)
    footprints, symbols = libraries(tmp_path)
    lookup(root, catalog, footprints, symbols)
    script = root / "parts" / "skidl_kicad.py"
    script.write_text("from pathlib import Path\nPath('board.net').write_text('(netlist)')\n")
    monkeypatch.setattr(sys, "argv", ["netlist.py", str(root)])
    assert netlist_main() == 0
    assert (root / "parts" / "board.net").is_file()
