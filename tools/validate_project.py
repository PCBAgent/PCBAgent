"""Structural checks for the generated KiCad demo (does not replace ERC/DRC)."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import generate_project as design


ROOT = Path(__file__).resolve().parents[1]


def balanced_sexpr(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    depth = 0
    in_string = False
    escaped = False
    for offset, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise AssertionError(f"{path.name}: unexpected ')' at byte {offset}")
    assert not in_string, f"{path.name}: unterminated string"
    assert depth == 0, f"{path.name}: unbalanced parentheses ({depth})"


def unique_uuids(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    values = re.findall(r"\(uuid ([0-9a-f-]{36})\)", text)
    duplicates = sorted({value for value in values if values.count(value) > 1})
    assert not duplicates, f"{path.name}: duplicate UUIDs: {duplicates[:3]}"


def main() -> int:
    sch_path = ROOT / "astra-bldc.kicad_sch"
    pcb_path = ROOT / "astra-bldc.kicad_pcb"
    start_pcb_path = ROOT / "astra-bldc-demo-start.kicad_pcb"
    autoroute_input_path = ROOT / "astra-bldc-autoroute-input.kicad_pcb"
    pro_path = ROOT / "astra-bldc.kicad_pro"
    bom_path = ROOT / "BOM.csv"
    readme_path = ROOT / "README.md"
    demo_path = ROOT / "DEMO.md"
    automation_path = ROOT / "tools" / "run_ipc_demo.ps1"
    plugin_path = ROOT / "tools" / "ipc_demo.py"
    router_path = ROOT / "tools" / "run_freerouting_test.ps1"
    bridge_path = ROOT / "tools" / "specctra_bridge.py"
    autorouter_guide_path = ROOT / "AUTOROUTER_TEST.md"
    router_launcher_path = ROOT / "run-autorouter-test.cmd"
    launcher_path = ROOT / "run-demo.cmd"
    required = [
        sch_path, pcb_path, start_pcb_path, autoroute_input_path, pro_path,
        bom_path, readme_path, demo_path, automation_path, plugin_path,
        router_path, bridge_path, autorouter_guide_path, launcher_path,
        router_launcher_path,
    ]
    for path in required:
        assert path.exists() and path.stat().st_size > 0, f"missing/empty: {path.name}"

    balanced_sexpr(sch_path)
    balanced_sexpr(pcb_path)
    balanced_sexpr(start_pcb_path)
    balanced_sexpr(autoroute_input_path)
    unique_uuids(sch_path)
    unique_uuids(pcb_path)
    unique_uuids(start_pcb_path)
    unique_uuids(autoroute_input_path)
    json.loads(pro_path.read_text(encoding="utf-8"))

    sch = sch_path.read_text(encoding="utf-8")
    pcb = pcb_path.read_text(encoding="utf-8")
    expected_refs = {component[0] for component in design.COMPONENTS}
    sch_refs = set(re.findall(r'\(property "Reference" "([^"]+)"', sch))
    pcb_refs = set(re.findall(r'\(property "Reference" "([^"]+)"', pcb))
    sch_refs = {ref for ref in sch_refs if any(char.isdigit() for char in ref)}
    pcb_refs = {ref for ref in pcb_refs if any(char.isdigit() for char in ref)}
    assert expected_refs <= sch_refs, f"schematic missing refs: {expected_refs - sch_refs}"
    assert expected_refs <= pcb_refs, f"PCB missing refs: {expected_refs - pcb_refs}"

    with bom_path.open(newline="", encoding="utf-8") as handle:
        bom_refs = {row["Reference"] for row in csv.DictReader(handle)}
    assert bom_refs == expected_refs, f"BOM ref mismatch: {bom_refs ^ expected_refs}"

    expected_nets = {net for *_head, pins in design.COMPONENTS for _pad, net in pins}
    pcb_nets = set(re.findall(r'^\s*\(net \d+ "([^"]*)"\)', pcb, re.MULTILINE))
    schematic_labels = set(re.findall(r'^\s*\(label "([^"]+)"', sch, re.MULTILINE))
    assert expected_nets <= pcb_nets, f"PCB missing nets: {expected_nets - pcb_nets}"
    assert expected_nets <= schematic_labels, f"schematic missing labels: {expected_nets - schematic_labels}"

    pad_counts = {
        net: sum(1 for *_head, pins in design.COMPONENTS for _pad, pin_net in pins if pin_net == net)
        for net in expected_nets
    }
    for net, count in pad_counts.items():
        if count > 1 and net != "GND":
            net_id = design.NET_ID[net]
            assert re.search(rf"\(segment .*?\(net {net_id}\)", pcb, re.DOTALL), f"unrouted net: {net}"
    assert '(layer "F.Cu")' in pcb and '(layer "B.Cu")' in pcb
    assert pcb.count("(zone ") == 2, "expected top and bottom ground zones"
    assert pcb.count('(layer "Edge.Cuts")') >= 8, "board outline is incomplete"
    assert "DEMO DESIGN" in sch and "DEMO • REV A" in pcb
    start_pcb = start_pcb_path.read_text(encoding="utf-8")
    assert "(segment " not in start_pcb and "(via " not in start_pcb, "demo start board must be unrouted"
    assert "locked" not in start_pcb and "locked" not in pcb, "board objects must remain mouse/keyboard movable"
    assert "PLACE → ROUTE → REFILL" in start_pcb
    for ref in expected_refs:
        assert f'"{ref}"' in start_pcb, f"demo start board missing {ref}"
    autoroute_input = autoroute_input_path.read_text(encoding="utf-8")
    assert "(segment " not in autoroute_input and "(via " not in autoroute_input
    assert "FREEROUTING TEST INPUT" in autoroute_input
    automation = automation_path.read_text(encoding="utf-8")
    plugin = plugin_path.read_text(encoding="utf-8")
    assert "SetCursorPos" not in automation and "SendKeys" not in automation
    assert "KiCad" in plugin and "Track" in plugin and "refill_zones" in plugin
    assert "SetCursorPos" not in plugin and "SendKeys" not in plugin
    assert "run-demo.cmd" in readme_path.read_text(encoding="utf-8")

    lib_ids = re.findall(r'^\s*\(symbol "(Astra:[^"]+)"$', sch, re.MULTILINE)
    assert len(lib_ids) == len(set(lib_ids)), "duplicate embedded symbol definitions"

    print(f"OK: {len(expected_refs)} components, {len(expected_nets)} nets")
    print(f"OK: {pcb.count('(segment ')} tracks, {pcb.count('(via ')} vias, 2 ground zones")
    print("OK: S-expressions balanced, UUIDs unique, project JSON valid")
    if (ROOT / "astra-bldc-erc.rpt").exists() and (ROOT / "astra-bldc-drc.rpt").exists():
        print("OK: native KiCad ERC/DRC reports are present (demo violations documented)")
    else:
        print("NOTE: native KiCad ERC/DRC reports are not present")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
