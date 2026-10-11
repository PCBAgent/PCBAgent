---
description: Specify a circuit, simulate it, and repair the SKiDL until the tests pass
argument-hint: "<specification>"
---

Follow the pcb-agent, requirements, circuit, and skidl skills.

This is `/design` only. `/parts` and `/layout` come later. Do not write a board netlist or emit coordinates.

Read `skills/circuit/schemas/circuit-spec.schema.json` before writing any file. The schema rejects unknown keys. Use these names and no others:

| What the user said | Key |
|---|---|
| the request, copied unchanged | `prompt` |
| supply voltage | `supply_voltage_v` |
| output voltage | `output_voltage_v` |
| "within X V" on that output | `tolerances.output_voltage_v` |
| output current | `output_current_a` |
| "within X A" on that current | `tolerances.output_current_a` |
| the load | `load`, a string such as `"33 ohm"` |
| board size, width then height | `board_max_mm`: `{"width", "height"}` |
| the shop | `manufacturing.vendor` |
| parts the user named, one string each | `preferred_components` |

Do not invent keys such as `input_voltage`, `inductance`, `input_capacitor1`, or `pcb_vendor`. A named inductor or capacitor belongs in `preferred_components`, not in its own field. `load` is the measurement load, not a preferred part.

Folder: `designs/<slug>/`. `<slug>` is a short kebab-case name from the spec, such as `buck-5v-3v3`. Do not ask for a name. Reuse the directory when one already exists.

Write `designs/<slug>/design/circuit-spec.json`, then run:

```bash
.venv/bin/python skills/requirements/check_spec.py designs/<slug>/design/circuit-spec.json
```

If `ok` is false, ask only for the fields in `missing`, then stop. If `ok` is true, read the skidl skill and write `designs/<slug>/design/skidl_sim.py`.

The simulation is the circuit the user asked for, including every preferred part at the value they gave. A resistor divider is not a buck regulator. Build it inside `measure()` and return numbers read from ngspice. Do not return the spec targets, and do not scale a simulated value onto a target.

`V` is a DC source and accepts `dc_value` only. A repeating pulse is `PULSEV` with `initial_value`, `pulsed_value`, `pulse_width`, and `period`. Passing pulse arguments to `V` emits `DC V` and ngspice rejects it. Fix the constructor. Do not write a side script to inspect the deck. `5 @ u_V` is 5 volts. A switch or diode model is `DeviceModel`, not a `.model` line. For a switcher, run a transient and return the average of the settled samples. Load current is the load voltage divided by the load resistance.

Specification: $@

Then run:

```bash
.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>
```

On a failure, read stderr and `simulation-results.json`. Exit 2 means the file crashed or `measure()` did not read ngspice: fix that before tuning values. Otherwise change `skidl_sim.py` so the reported error shrinks, and run pytest again until it exits 0. Do not edit `simulation-results.json` or change `circuit-spec.json` to hide a failure.
