"""Operating stress from the actual generated SPICE circuit and analysis samples.

These are observed stresses for the simulated conditions, not worst-case ratings.
AC small-signal results cannot establish absolute operating stress.
"""

import math

REAL_FLOAT = float


def capture(circuit, analysis, method):
    nodes = {str(k).lower(): list(v) for k, v in analysis.nodes.items()}
    components = []
    for element in circuit.elements:
        name = type(element).__name__
        kind, field = {
            "Resistor": ("resistor", "resistance"),
            "Capacitor": ("capacitor", "capacitance"),
            "Inductor": ("inductor", "inductance"),
            "Diode": ("diode", None),
        }.get(name, (None, None))
        if kind is None:
            continue
        nets = [str(pin.node) for pin in element.pins]
        value = REAL_FLOAT(getattr(element, field)) if field else None
        record = {"ref": element.name, "kind": kind, "value_si": value, "nets": nets,
                  "stress": {}, "analysis": method}
        if method in {"operating_point", "transient", "dc"} and len(nets) == 2:
            count = max((len(v) for v in nodes.values()), default=0)
            waves = [[0.0] * count if net.lower() in {"0", "gnd"} else nodes.get(net.lower()) for net in nets]
            if all(w is not None and len(w) == count for w in waves) and count:
                voltages = [abs(REAL_FLOAT(a) - REAL_FLOAT(b)) for a, b in zip(*waves)]
                if all(math.isfinite(v) for v in voltages):
                    peak = max(voltages)
                    record["stress"]["voltage_v"] = peak
                    if kind == "resistor" and value > 0:
                        record["stress"].update(power_w=peak * peak / value, current_a=peak / value)
        components.append(record)
    return components


def merge(previous, current):
    """Keep peak stress across analyses; refuse two incompatible circuits under one ref."""
    by_ref = {item["ref"]: item for item in previous}
    for item in current:
        old = by_ref.get(item["ref"])
        if old and any(old[key] != item[key] for key in ("kind", "value_si", "nets")):
            raise ValueError(f"{item['ref']}: simulation changed the circuit between analyses")
        if old:
            item["stress"] = {key: max(old["stress"].get(key, 0), item["stress"].get(key, 0))
                              for key in old["stress"].keys() | item["stress"].keys()}
        by_ref[item["ref"]] = item
    return list(by_ref.values())
