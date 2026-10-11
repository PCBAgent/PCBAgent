---
name: skidl
description: Write valid SKiDL Python for a circuit or its ngspice run. Use when creating, editing, or repairing a SKiDL file.
---

# SKiDL

SKiDL is Python that connects parts and then emits a netlist. Docs: https://devbisme.github.io/skidl/. The SPICE section of that page points at the simulation notebook: https://github.com/devbisme/skidl/blob/master/tests/examples/spice-sim-intro/spice-sim-intro.ipynb. What `skidl.pyspice` puts in the namespace is https://devbisme.github.io/skidl/api/html/rst_output/skidl.pyspice.html.

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

Keep that import. Do not replace it with a list of names. `from skidl.pyspice import *` is what defines `reset`, `gnd`, `Net`, the part constructors, `DeviceModel`, `Simulator`, `generate_netlist`, and every unit. A named import drops whichever of those you left off, and the next pytest error is `NameError` for `reset`, `gnd`, or a unit. Put the star import back. Do not add the missing names one at a time.

That import creates `gnd` as SPICE node `0`. Use that `gnd`. Do not write `gnd = Net("GND")`; that is a different node and the sources no longer connect to ground. It also sets the tool to SKiDL and defines SPICE parts as constructors (`R`, `C`, `L`, `V`, `PULSEV`, …). Build the circuit inside `measure()`, not at module level. `reset()` clears any circuit already built in this process. `generate_netlist()` returns an InSpice circuit. `print` that object to get the SPICE deck. Read a node with `node(pin_or_net)`.

Simulate with `Simulator.factory().simulation(circuit)`. `circuit.simulator()` is removed and raises `NameError`. The simulation object has `operating_point()`, `dc(...)`, `ac(...)`, and `transient(step_time=..., end_time=...)`. Results are indexed by lowercase net name, such as `analysis.nodes["vout"]`, and source currents by lowercase source name, such as `analysis.branches["vs"]`. A source that delivers power reads negative. For a load current, measure the voltage across the load resistor and divide by its resistance. Convert each measurement with `float(...)` before returning it. For a switching circuit, measure the average over the last part of a transient run, after the output settles.

Set values with InSpice units, the same names as the simulation notebook. The letter before the unit is the prefix, and `u` means micro: `5 @ u_V` is 5 volts, `5 @ u_uV` is 5 microvolts. For this regulator, `10 @ u_uH` is 10 µH, `10 @ u_uF` is 10 µF, `100 @ u_nF` is 100 nF, `22 @ u_uF` is 22 µF, `33 @ u_Ohm` is 33 ohms, and `6.6 @ u_us` is 6.6 µs. `10 @ u_H` is 10 henries, not 10 µH.

| Value | Unit |
|---|---|
| volt, microvolt | `u_V`, `u_uV` |
| ohm, kilohm | `u_Ohm`, `u_kOhm` |
| farad, microfarad, nanofarad | `u_F`, `u_uF`, `u_nF` |
| henry, microhenry | `u_H`, `u_uH` |
| second, millisecond, microsecond | `u_s`, `u_ms`, `u_us` |
| hertz, kilohertz | `u_Hz`, `u_kHz` |

Parts you can call, with their pins:

| Constructor | Pins | Set |
|---|---|---|
| `R`, `C`, `L`, `D` | `p`, `n` | `value` or, for `D`, `model` |
| `S` | `ip`, `in`, `op`, `on` | `model` |
| `V`, `I` | `p`, `n` | `dc_value` |
| `SINEV`, `SINEI` | `p`, `n` | `amplitude`, `frequency` |
| `PULSEV`, `PULSEI` | `p`, `n` | `initial_value`, `pulsed_value`, `pulse_width`, `period` |
| `Q` | `c`, `b`, `e` | `model` |
| `M`, `J`, `Z` | `d`, `g`, `s` (`M` also `b`) | `model` |
| `E` (`VCVS`), `G` | `ip`, `in`, `op`, `on` | `gain` |
| `F`, `H` | `p`, `n` | `control`, `gain` or `transresistance` |

Connect the negative terminal of an independent source to `gnd`. Do not invent pin names beyond this table. A switch or diode model is a `DeviceModel`, not a line of SPICE text. This switch is on while its gate is above 2.5 V:

```python
sw_model = DeviceModel("SW", "SW", Vt=2.5, Ron=0.01, Roff=1e6)
S(model=sw_model)["ip", "in", "op", "on"] += gate, gnd, vin, switch
```

Drive `gate` with `PULSEV`, as the notebook does: `PULSEV(initial_value=0, pulsed_value=5 @ u_V, pulse_width=1 @ u_ms, period=2 @ u_ms)`. `pulse_width` and `period` are the on-time and the repeat time. A 100 kHz switch is `period=10 @ u_us`. A duty of 0.66 is `pulse_width=6.6 @ u_us`. `V` does not take those arguments.

When `design/ic.json` exists, follow its `topology`. An `ldo` has no inductor and no `S()`: a fixed part is a voltage source from `roles.output` to `gnd` at the regulated voltage, and an adjustable part uses the feedback divider. A `buck` or `boost` connects the supply to `roles.input`, the inductor to `roles.switch`, and `roles.ground` to `gnd`. `PULSEV` drives `S()`, and `S()` connects the input net to the switch net. When `external_diode` is true the part is asynchronous, so the off-time current needs a catch diode and the switch alone does not regulate:

```python
D(model=DeviceModel("D", "D"), ref="D1")["p", "n"] += gnd, switch
```

The anode is ground and the cathode is the switch node. The duty is about `(Vout + 0.4) / Vin` because of that diode, not `Vout / Vin`. Lookup matches `D1` to a catalog Schottky, so do not delete it to make the parts step pass. When `adjustable` is true, `feedback_voltage_v` is the reference: the divider from the regulated rail to `roles.feedback` to `gnd` sets `Vout = feedback_voltage_v * (1 + Rtop / Rbottom)`. A 22 µF capacitor into 33 ohms settles in about a millisecond, so a transient of a few hundred microseconds has not settled. Run long enough for the output to settle, then average the last part.

A Python line that starts with `.model` is a syntax error. Fix that syntax. Do not delete the circuit and return the spec targets instead. The runner rejects a returned number that did not come from the analysis, including a simulated value multiplied back to the spec target. Return the node voltage, `sum(samples) / len(samples)` for a waveform, or the load voltage divided by the load resistance.

For a vendor `.lib` subcircuit, load it with `Part(lib, name)` after appending its directory to `lib_search_paths[SPICE]`, then alias the pins from the symbol file before connecting them. ngspice often rejects unmodified PSPICE or LTspice libraries.

A second circuit in the same process starts with `reset()`.

## KiCad netlist file

Use this after pytest exits 0, when `/design` writes the board netlist. Connect the IC by pin number from `design/ic.json`. `u1[1]` is pin number 1. `u1['VIN']` and `u1['~{EN}']` are pin names and are not used in this file.

```python
from skidl import *

set_default_tool(KICAD)
```

`KICAD` means KiCad 10 libraries. Parts come from KiCad symbol libraries (`KICAD_SYMBOL_DIR`), not from the SPICE constructors:

```python
r = Part("Device", "R", value="1K", footprint="Resistor_SMD:R_0805_2012Metric")
```

Look up a part with `skidl-part-search` before guessing a library or name. A regular expression as the part name returns the first match and warns if several match. Print the part to see pin numbers. In `skidl_kicad.py`, index every IC pin by that number:

```python
u1 = Part("Regulator_Switching", "XL1509-ADJ", footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
u1[1] += vin
u1[5] += gnd
```

`Part.p[...]` is the same pin numbers. Do not use `Part.n[...]` here.

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
