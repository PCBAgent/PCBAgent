---
name: skidl
description: Write valid SKiDL Python for a circuit or its ngspice run. Use when creating, editing, or repairing a SKiDL file.
---

# SKiDL

SKiDL is Python that connects parts and then emits a netlist. Docs: https://devbisme.github.io/skidl/. SPICE details: https://github.com/devbisme/skidl/blob/master/tests/examples/spice-sim-intro/spice-sim-intro.ipynb.

Write one file for simulation and, later, a separate file for the KiCad netlist. Do not mix the two imports in one file.

## Simulation file

This is the file the circuit stage writes.

```python
from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    R(value=10 @ u_kOhm)["p", "n"] += vin, vout
    R(value=6.8 @ u_kOhm)["p", "n"] += vout, gnd
    circuit = generate_netlist()
    op = Simulator.factory().simulation(circuit).operating_point()
    return {"output_voltage_v": float(op.nodes["vout"][0])}
```

That import creates `gnd`, sets the tool to SKiDL, and defines SPICE parts as constructors (`R`, `C`, `V`, …). Build the circuit inside `measure()`, not at module level. `reset()` clears any circuit already built in this process. `generate_netlist()` returns an InSpice circuit. `print` that object to get the SPICE deck. Read a node with `node(pin_or_net)`.

Simulate with `Simulator.factory().simulation(circuit)`. `circuit.simulator()` is removed and raises `NameError`. The simulation object has `operating_point()`, `dc(...)`, `ac(...)`, and `transient(step_time=..., end_time=...)`. Results are indexed by lowercase net name, such as `analysis.nodes["vout"]`, and source currents by lowercase source name, such as `analysis.branches["vs"]`. A source that delivers power reads negative. For a load current, measure the voltage across the load resistor and divide by its resistance. Convert each measurement with `float(...)` before returning it. For a switching circuit, measure the average over the last part of a transient run, after the output settles.

Set values with InSpice units: `1 @ u_kOhm`, `100 @ u_nF`, `5 @ u_V`, `1 @ u_ms`.

Parts you can call, with their pins:

| Constructor | Pins | Set |
|---|---|---|
| `R`, `C`, `L`, `D` | `p`, `n` | `value` or, for `D`, `model` |
| `V`, `I` | `p`, `n` | `dc_value` |
| `SINEV`, `SINEI` | `p`, `n` | `amplitude`, `frequency` |
| `PULSEV`, `PULSEI` | `p`, `n` | `initial_value`, `pulsed_value`, `pulse_width`, `period` |
| `Q` | `c`, `b`, `e` | `model` |
| `M`, `J`, `Z` | `d`, `g`, `s` (`M` also `b`) | `model` |
| `E` (`VCVS`), `G` | `ip`, `in`, `op`, `on` | `gain` |
| `F`, `H` | `p`, `n` | `control`, `gain` or `transresistance` |

Connect the negative terminal of an independent source to `gnd`. Do not invent pin names beyond this table. For a vendor `.lib` subcircuit, load it with `Part(lib, name)` after appending its directory to `lib_search_paths[SPICE]`, then alias the pins from the symbol file before connecting them. ngspice often rejects unmodified PSPICE or LTspice libraries.

A second circuit in the same process starts with `reset()`.

## KiCad netlist file

Use this only when a later stage asks for a board netlist.

```python
from skidl import *

set_default_tool(KICAD)
```

`KICAD` means KiCad 10 libraries. Parts come from KiCad symbol libraries (`KICAD_SYMBOL_DIR`), not from the SPICE constructors:

```python
r = Part("Device", "R", value="1K", footprint="Resistor_SMD:R_0805_2012Metric")
```

Look up a part with `skidl-part-search` before guessing a library or name. A regular expression as the part name returns the first match and warns if several match. Print the part to see pin numbers and names. `Part.p[...]` is pin numbers. `Part.n[...]` is pin names.

`ERC()` before `generate_netlist(tool=KICAD)`. Attach unused pins to `NC`. Set `net.drive = POWER` on a supply net that is not driven by a `PWROUT` pin. A missing footprint aborts netlist generation. `ref`, `value`, and `footprint` are what the board file needs. Extra data that must survive in the netlist goes in `part.fields`.

## Connections

`+=` connects. `=` only binds a Python name.

```python
vin = Net("VIN")
vin += r1[1]
r1[2] += r2[1]
```

Pin-to-pin `+=` creates an implicit net. Connecting two nets merges them. A many-to-many connection must have the same count on both sides.

Series, parallel, and shunts are only for two-pin parts:

```python
vin & r1 & vout & r2 & gnd          # series
vcc & (r1 | r2) & gnd               # parallel
inp & tee(cs & gnd) & l & outp      # tee returns the first node
```

Name the pins when the part is polarized or has more than two pins: `d1["p", "n"]`, `q1["c", "e"]`. Insert a `Net` in the chain where a later measurement needs that node.

A slice includes both ends: `part[2:4]` is pins 2, 3, and 4.

## Copies and hierarchy

Build repeated parts from a template so the template itself stays out of the netlist:

```python
rt = Part("Device", "R", dest=TEMPLATE)
r1, r2 = rt(2, value="1K")
```

`2 * r1(value="1K")` creates three resistors. The call copies once, then `*` copies that result twice, and the first copy is discarded.

For a reusable block, use `@subcircuit` and return an `Interface`. A `SubCircuit` subclass must call `self.initialize()` and `self.finalize()`. Do not call `super().__init__()`.

## Checks before you finish

- Every source and measurement node is a named net, not only an implicit `N$` net.
- Power pins are connected, and unused pins are on `NC` in a KiCad file.
- The file calls `ERC()` for a KiCad netlist, or defines `measure()` and builds the deck through `generate_netlist()` for simulation.
- Pin names in the file were printed from the part or taken from the table above.
