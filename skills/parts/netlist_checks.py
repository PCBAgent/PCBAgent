"""Validate manufacturing connectivity against simulated passives and selected parts."""

import math
import re

from catalog import parse_value
from pins import parse_sexpr, symbol_pins


def children(node, name):
    return [x for x in node[1:] if isinstance(x, list) and x and x[0] == name]


def value(node, name):
    found = children(node, name)
    return found[0][1] if found and len(found[0]) > 1 else None


def normalize(net):
    return "gnd" if str(net).lower() in {"0", "gnd"} else str(net).lower()


def component_value(kind, text):
    parsed = parse_value(kind, text or "")
    if parsed is not None:
        return parsed
    # KiCad commonly writes 10k, 22u, or a bare SI number.
    match = re.fullmatch(r"\s*(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)([pnumkKM]?)\s*", text or "")
    if match:
        return float(match[1]) * {"": 1, "p": 1e-12, "n": 1e-9, "u": 1e-6,
                                 "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6}[match[2]]
    return None


def validate(text, parts, evidence, spec, footprint_dir, symbol_dir):
    tree = parse_sexpr(text)
    if len(tree) != 1 or not isinstance(tree[0], list) or tree[0][0] != "export":
        raise ValueError("board.net must contain one KiCad (export ...) document")
    export = tree[0]
    comps = [c for s in children(export, "components") for c in children(s, "comp")]
    nets = [n for s in children(export, "nets") for n in children(s, "net")]
    errors = []
    by_ref = {value(c, "ref"): c for c in comps}
    if not comps or len(by_ref) != len(comps) or None in by_ref:
        errors.append("Missing or duplicate component references")
    if not nets:
        errors.append("Netlist contains no nets")
    connected = {}
    net_nodes = {}
    for net in nets:
        name = normalize(value(net, "name"))
        if name in net_nodes or value(net, "name") is None:
            errors.append(f"Duplicate or missing net name: {name}")
        nodes = [(value(n, "ref"), value(n, "pin")) for n in children(net, "node")]
        net_nodes[name] = nodes
        if len(nodes) < 2:
            errors.append(f"{name}: net has fewer than two pins")
        for ref, pin in nodes:
            if ref not in by_ref or not pin or (ref, pin) in connected:
                errors.append(f"{ref}.{pin}: unknown or multiply connected pin")
            connected[ref, pin] = name
    selected = {p.get("ref"): p for p in parts if p.get("on_board")}
    if None in selected or len(selected) != sum(bool(p.get("on_board")) for p in parts):
        errors.append("Selected board parts need unique references")
    for ref, comp in by_ref.items():
        source = children(comp, "libsource")
        symbol = f"{value(source[0], 'lib')}:{value(source[0], 'part')}" if source else ""
        is_interface = symbol.startswith(("Connector:", "Connector_Generic:", "Connector_Generic_MountingPin:"))
        fp = value(comp, "footprint")
        if not fp or ":" not in fp:
            errors.append(f"{ref}: footprint missing")
            continue
        library, name = fp.split(":", 1)
        path = footprint_dir / f"{library}.pretty" / f"{name}.kicad_mod"
        if not path.is_file():
            errors.append(f"{ref}: footprint {fp} is not installed")
        else:
            pads = set(re.findall(r'\(pad\s+"?([^\s"()]+)', path.read_text()))
            for (node_ref, pin), net in connected.items():
                if node_ref == ref and pin not in pads:
                    errors.append(f"{ref}.{pin}: symbol pin has no footprint pad")
        expected_pins = symbol_pins(symbol, symbol_dir)
        if not expected_pins:
            errors.append(f"{ref}: cannot resolve symbol pins for {symbol}")
        numbers = {p["number"] for p in expected_pins}
        for node_ref, pin in connected:
            if node_ref == ref and pin not in numbers:
                errors.append(f"{ref}.{pin}: pin does not exist in {symbol}")
        for pin in expected_pins:
            if pin["type"] != "no_connect" and (ref, pin["number"]) not in connected:
                errors.append(f"{ref}.{pin['number']} ({pin['name']}): unconnected; resolve explicitly")
        if ref not in selected:
            if not is_interface:
                errors.append(f"{ref}: physical part absent from selected BOM")
        elif selected[ref].get("footprint") != fp or selected[ref].get("symbol") != symbol:
            errors.append(f"{ref}: symbol or footprint differs from selected part")
    for ref in selected.keys() - by_ref.keys():
        errors.append(f"{ref}: selected board part missing from netlist")
    for component in evidence.get("components", []):
        ref = component["ref"]
        if ref in spec.get("external_components", []):
            if ref in by_ref:
                errors.append(f"{ref}: declared external but present on board")
            continue
        if ref not in by_ref:
            errors.append(f"{ref}: simulated board component missing")
            continue
        wanted = component.get("value_si")
        if wanted is not None:
            actual = component_value(component["kind"], value(by_ref[ref], "value"))
            if actual is None or not math.isclose(actual, wanted, rel_tol=1e-9):
                errors.append(f"{ref}: manufacturing value differs from simulated {wanted}")
        pin_order = ("2", "1") if component["kind"] == "diode" else ("1", "2")
        actual_nets = [connected.get((ref, pin)) for pin in pin_order]
        wanted_nets = [normalize(n) for n in component["nets"]]
        same = actual_nets == wanted_nets if component["kind"] == "diode" else sorted(str(n) for n in actual_nets) == sorted(wanted_nets)
        if not same:
            errors.append(f"{ref}: manufacturing connectivity differs from simulation")
    return list(dict.fromkeys(errors))
