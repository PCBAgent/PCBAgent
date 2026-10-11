"""General placement and routing rules inferred from the netlist and the circuit spec.

The model writes constraints.json. Rules already in that file are kept, including a looser
limit from a previous failed run. This module fills in the ones the file does not cover.
"""

import re

from place import DEFAULT_GROUP_GAP_MM, DEFAULT_RULES, EDGES


DECOUPLE_MM = 2.0
SEPARATION_MM = 5.0
PAIR_SKEW_MM = 5.0
POWER_NAMES = {
    "VIN", "VOUT", "VCC", "VDD", "VBAT", "VBUS", "VSYS",
    "SW", "SWITCH", "LX", "PH",
    "3V3", "5V", "12V", "+5V", "+3V3", "+3.3V",
}
SENSITIVE_WORDS = ("amplifier", "op-amp", "opamp", "sensor", "crystal", "adc")
PAIR_ENDS = (("+", "-"), ("_P", "_N"), ("_DP", "_DM"))


def copper_width_mm(current_a):
    """IPC-2221, 1 oz outer copper, 10 °C rise. None when the default track is already wide enough."""
    if not isinstance(current_a, (int, float)) or isinstance(current_a, bool) or current_a <= 0:
        return None
    width = 0.3 * current_a if current_a <= 1 else 0.3 + 0.5 * (current_a - 1)
    width = round(width, 2)
    if width <= DEFAULT_RULES["track_width_mm"]:
        return None
    return width


def ref_prefix(ref):
    match = re.match(r"[A-Za-z]+", ref or "")
    return match.group(0).upper() if match else ""


def blob(comp):
    return " ".join(str(comp.get(key) or "") for key in ("value", "description", "footprint", "lib", "part")).lower()


def is_led(comp):
    if ref_prefix(comp["ref"]) == "LED":
        return True
    text = blob(comp)
    return "light emitting" in text or re.search(r"\bled\b", text) is not None


def is_connector(comp):
    if ref_prefix(comp["ref"]) in {"J", "P", "CN"}:
        return True
    text = blob(comp)
    return "connector" in text or "pinheader" in text or "pin header" in text


def is_switch(comp):
    if ref_prefix(comp["ref"]) in {"SW", "BTN"}:
        return True
    if ref_prefix(comp["ref"]) in {"U", "IC", "Q", "L", "C", "R", "D"}:
        return False
    text = blob(comp)
    return "button" in text or re.search(r"\bswitch\b", text) is not None


def is_testpoint(comp):
    if ref_prefix(comp["ref"]) == "TP":
        return True
    text = blob(comp)
    return "test point" in text or "testpoint" in text


def is_io(comp):
    return is_connector(comp) or is_switch(comp) or is_led(comp) or is_testpoint(comp)


def is_ic(comp):
    return ref_prefix(comp["ref"]) in {"U", "IC"}


def is_capacitor(comp):
    return ref_prefix(comp["ref"]) == "C"


def is_inductor(comp):
    return ref_prefix(comp["ref"]) == "L"


def is_diode(comp):
    return ref_prefix(comp["ref"]) == "D" and not is_led(comp)


def is_passive(comp):
    return ref_prefix(comp["ref"]) in {"R", "C", "L", "FB"} or is_diode(comp)


def is_sensitive(comp):
    if is_inductor(comp) or is_io(comp):
        return False
    if ref_prefix(comp["ref"]) == "Y":
        return True
    return any(word in blob(comp) for word in SENSITIVE_WORDS)


def is_ground(name):
    key = (name or "").upper().replace(" ", "")
    return key in {"GND", "AGND", "PGND", "DGND", "GNDA", "GNDP", "VSS", "0"} or key.endswith("GND")


def is_power_name(name):
    key = (name or "").upper().replace(" ", "")
    return key in POWER_NAMES or key.startswith("+") or re.fullmatch(r"V\d.*", key) is not None


def nets_of(netlist, ref):
    return [name for name, nodes in netlist["nets"].items() if any(node_ref == ref for node_ref, _ in nodes)]


def refs_on(netlist, name):
    return [ref for ref, _ in netlist["nets"].get(name, [])]


def covered_edge(constraints, ref):
    return any(ref in _refs(item) for item in constraints if item["type"] == "board_edge")


def covered_proximity(constraints, anchor, other):
    for item in constraints:
        if item["type"] != "proximity":
            continue
        refs = _refs(item)
        if anchor in refs and other in refs:
            return True
    return False


def covered_group(constraints, ic):
    return any(item["type"] == "group" and ic in _refs(item) for item in constraints)


def covered_nets(constraints, kind):
    names = set()
    for item in constraints:
        if item["type"] == kind:
            names.update(item.get("nets") or [])
    return names


def _refs(item):
    refs = list(item.get("components") or [])
    if item.get("component"):
        refs.append(item["component"])
    return refs


def _io_rank(comp):
    if is_connector(comp):
        return 0
    if is_switch(comp):
        return 1
    if is_led(comp):
        return 2
    return 3


def edge_constraints(components, existing):
    used = [item["preferred_edge"] for item in existing if item["type"] == "board_edge" and item.get("preferred_edge") in EDGES]
    free = [edge for edge in EDGES if edge not in used]
    order = free + [edge for edge in EDGES if edge in used]
    pending = [comp for comp in components if is_io(comp) and not covered_edge(existing, comp["ref"])]
    pending.sort(key=lambda comp: (_io_rank(comp), comp["ref"]))
    added = []
    for index, comp in enumerate(pending):
        added.append({
            "type": "board_edge",
            "component": comp["ref"],
            "preferred_edge": order[index % len(order)],
            "max_distance_mm": 0.5,
            "weight": 3,
            "hard": True,
        })
    return added


def proximity_constraints(netlist, components, existing):
    by_ref = {comp["ref"]: comp for comp in components}
    by_anchor = {}
    for comp in components:
        if not is_capacitor(comp):
            continue
        names = nets_of(netlist, comp["ref"])
        others = [name for name in names if not is_ground(name)]
        if not any(is_ground(name) for name in names) or not others:
            continue
        present = [
            ref for name in others for ref in refs_on(netlist, name)
            if ref in by_ref
        ]
        ics = sorted(ref for ref in present if is_ic(by_ref[ref]))
        switches = sorted(ref for ref in present if ref_prefix(ref) in {"Q", "M"})
        anchor = (ics or switches or [None])[0]
        if anchor is None or covered_proximity(existing, anchor, comp["ref"]):
            continue
        by_anchor.setdefault(anchor, []).append(comp["ref"])
    added = []
    for anchor, caps in sorted(by_anchor.items()):
        added.append({
            "type": "proximity",
            "components": [anchor, *sorted(caps)],
            "max_distance_mm": DECOUPLE_MM,
            "weight": 3,
            "hard": True,
        })
    return added


def group_constraints(netlist, components, existing):
    by_ref = {comp["ref"]: comp for comp in components}
    added = []
    for ic in sorted(comp["ref"] for comp in components if is_ic(comp)):
        if covered_group(existing, ic):
            continue
        members = {ic}
        for name in nets_of(netlist, ic):
            for ref in refs_on(netlist, name):
                comp = by_ref.get(ref)
                if comp and is_passive(comp):
                    members.add(ref)
        if len(members) < 2:
            continue
        added.append({
            "type": "group",
            "components": sorted(members, key=lambda ref: (ref != ic, ref)),
            "max_distance_mm": DEFAULT_GROUP_GAP_MM,
        })
    return added


def loop_constraints(netlist, components, existing):
    by_ref = {comp["ref"]: comp for comp in components}
    inductors = [comp["ref"] for comp in components if is_inductor(comp)]
    diodes = [comp["ref"] for comp in components if is_diode(comp)]
    if not inductors or not diodes:
        return []
    switch_nets = []
    for diode in diodes:
        for name in nets_of(netlist, diode):
            if is_ground(name):
                continue
            refs = set(refs_on(netlist, name))
            if refs.intersection(inductors):
                switch_nets.append(name)
    if not switch_nets:
        return []
    output_nets = set()
    for inductor in inductors:
        for name in nets_of(netlist, inductor):
            if name not in switch_nets and not is_ground(name):
                output_nets.add(name)
    present = [
        ref for name in switch_nets for ref in refs_on(netlist, name)
        if ref in by_ref
    ]
    ics = sorted(ref for ref in present if is_ic(by_ref[ref]))
    switches = sorted(ref for ref in present if ref_prefix(ref) in {"Q", "M"})
    anchors = ics or switches
    if not anchors or any(ref in _refs(item) for item in existing if item["type"] == "loop_area" for ref in anchors):
        return []
    anchor = anchors[0]
    caps = []
    for comp in components:
        if not is_capacitor(comp):
            continue
        names = set(nets_of(netlist, comp["ref"]))
        if not any(is_ground(name) for name in names):
            continue
        rail = names - {name for name in names if is_ground(name)}
        if rail.intersection(switch_nets) or rail.intersection(output_nets):
            continue
        if any(anchor in refs_on(netlist, name) for name in rail):
            caps.append(comp["ref"])
    members = sorted(caps) + [anchor] + sorted(diodes)
    if len(members) < 3:
        return []
    return [{"type": "loop_area", "components": members}]


def separation_constraints(components, existing):
    inductors = [comp["ref"] for comp in components if is_inductor(comp)]
    sensitive = [comp["ref"] for comp in components if is_sensitive(comp)]
    if not inductors or not sensitive:
        return []
    if any(item["type"] == "separation" and set(_refs(item)).intersection(inductors) for item in existing):
        return []
    return [{
        "type": "separation",
        "components": sorted(inductors),
        "from": sorted(sensitive),
        "min_distance_mm": SEPARATION_MM,
    }]


def current_constraints(netlist, components, existing, spec):
    width = copper_width_mm((spec or {}).get("output_current_a"))
    if width is None:
        return []
    by_ref = {comp["ref"]: comp for comp in components}
    grounded_caps = {
        comp["ref"] for comp in components
        if is_capacitor(comp) and any(is_ground(name) for name in nets_of(netlist, comp["ref"]))
    }
    chosen = []
    for name, nodes in netlist["nets"].items():
        if len({ref for ref, _ in nodes}) < 2:
            continue
        refs = [ref for ref, _ in nodes if ref in by_ref]
        has_connector = any(is_connector(by_ref[ref]) for ref in refs)
        has_switch = any(is_ic(by_ref[ref]) or ref_prefix(ref) in {"Q", "M"} for ref in refs)
        has_cap = any(ref in grounded_caps for ref in refs)
        if is_ground(name) or is_power_name(name) or (has_connector and has_switch and has_cap):
            chosen.append(name)
    fresh = sorted(set(chosen) - covered_nets(existing, "high_current"))
    if not fresh:
        return []
    return [{"type": "high_current", "nets": fresh, "track_width_mm": width}]


def pair_pole(name):
    upper = (name or "").upper()
    for positive, negative in PAIR_ENDS:
        if upper.endswith(positive):
            return upper[:-len(positive)], "+"
        if upper.endswith(negative):
            return upper[:-len(negative)], "-"
    return None, None


def pair_constraints(netlist, existing):
    poles = {}
    for name in netlist["nets"]:
        stem, pole = pair_pole(name)
        if stem:
            poles.setdefault(stem, {})[pole] = name
    covered = covered_nets(existing, "differential_pair")
    added = []
    for stem, ends in sorted(poles.items()):
        if "+" not in ends or "-" not in ends:
            continue
        if ends["+"] in covered or ends["-"] in covered:
            continue
        added.append({
            "type": "differential_pair",
            "nets": [ends["+"], ends["-"]],
            "max_skew_mm": PAIR_SKEW_MM,
        })
    return added


def apply_general_rules(constraints, netlist, spec=None):
    """Return (merged constraints, rules added). Existing entries win."""
    existing = list(constraints.get("constraints") or [])
    components = netlist["components"]
    added = []
    added += edge_constraints(components, existing)
    added += proximity_constraints(netlist, components, existing)
    added += group_constraints(netlist, components, existing)
    added += loop_constraints(netlist, components, existing)
    added += separation_constraints(components, existing)
    added += current_constraints(netlist, components, existing, spec)
    added += pair_constraints(netlist, existing + added)
    merged = dict(constraints)
    merged["constraints"] = existing + added
    return merged, added
