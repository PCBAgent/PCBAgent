---
description: Specify a circuit, simulate it, select catalog parts, and write the KiCad netlist
argument-hint: "<specification>"
---

Follow the pcb-agent, requirements, circuit, skidl, and parts skills.

This is `/design`. It writes the spec, the simulation, the catalog parts, and `parts/board.net`. `/layout` comes later, after this command exits. Do not emit coordinates or draw traces.

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
| simulation-only load references | `external_components`, such as `["RL"]` |
| physical interface net names | `interfaces`, such as `["VIN", "VOUT", "GND"]` |
| board size, width then height | `board_max_mm`: `{"width", "height"}` |
| the shop | `manufacturing.vendor` |
| parts the user named, one string each | `preferred_components` |
| skip ngspice checks | `skip_verify`: `true` |

Do not invent keys such as `input_voltage`, `inductance`, `input_capacitor1`, or `pcb_vendor`. A named inductor or capacitor belongs in `preferred_components`, not in its own field. `load` is the measurement load, not a preferred part.

Folder: `designs/<slug>/`. `<slug>` is a short kebab-case name from the spec, such as `buck-5v-3v3`. Do not ask for a name. Reuse the directory when one already exists.

Write `designs/<slug>/design/circuit-spec.json`, then call `pcb_stage` with stage `prepare` (or use the CLI):

```bash
.venv/bin/python tools/pcb_stage.py designs/<slug> prepare
```

This checks requirements and chooses the IC before simulation. If requirements are missing, ask only for those fields. If no catalog regulator meets the spec, report the blocker. A non-regulator needs no IC. For a selected regulator, read `design/ic.json`: `topology`, `external_diode`, `adjustable`, `feedback_voltage_v`, `pins`, and `roles`. Use the compact stage result and its log path to diagnose failures.

`roles.input` is the supply pin and `roles.ground` is ground. Connect every pin whose name is that ground, including the hidden ones. Verify enable polarity and its required connection from the selected part’s datasheet. The role map identifies pin names, not polarity; do not automatically tie enable to VIN.

Build the external circuit the chosen IC actually needs:

- `topology` `ldo`: the output pin is the regulated rail. No inductor, no switch, and no diode. An ideal voltage source can represent an LDO output for a limited behavioral test, but it cannot verify regulation, dropout, current limit, stability or thermal behavior. Report those as unverified unless a suitable device model and checks cover them. An adjustable LDO uses the feedback divider below.
- `topology` `buck`: `roles.switch` is the inductor's upstream pin. When `switch` and `output` are the same name, that pin is not the regulated rail; the regulated rail is the other side of the inductor. The internal high-side switch is `S()` driven by `PULSEV`, from the input net to the switch net. `external_diode` true means the part is asynchronous and the simulation must include a catch diode, anode at ground and cathode at the switch net: `D(ref="D1")["p", "n"] += gnd, switch`. Lookup matches that diode to a catalog Schottky. Omitting it makes lookup fail, and a buck without it does not regulate.
- `topology` `boost`: use the selected IC’s actual boost topology and datasheet; a buck circuit is not interchangeable with a boost circuit.
- `adjustable` true: add a resistor divider from the regulated rail to `roles.feedback` to ground. `feedback_voltage_v` is the reference. The regulated voltage is that reference times `1 + Rtop / Rbottom`. Those resistors are board parts, not the load.

Then read the skidl skill and write `designs/<slug>/design/skidl_sim.py`.

The simulation is the circuit the user asked for, including every preferred part at the value they gave, connected to the pins in `ic.json` when that file exists. A resistor divider does not replace the switch, inductor, and catch diode. The feedback divider is added on top of that circuit when `adjustable` is true. Build it inside `measure()` and return numbers read from ngspice. Do not return the spec targets, and do not scale a simulated value onto a target.

`V` is a DC source and accepts `dc_value` only. A repeating pulse is `PULSEV` with `initial_value`, `pulsed_value`, `pulse_width`, and `period`. Passing pulse arguments to `V` emits `DC V` and ngspice rejects it. Fix the constructor. Do not write a side script to inspect the deck. `5 @ u_V` is 5 volts. A switch or diode model is `DeviceModel`, not a `.model` line. For a switcher, run a transient and return the average of the settled samples. Load current is the load voltage divided by the load resistance.

Specification: $@

If `skip_verify` is true, do not run verify and do not repair `skidl_sim.py` against measurements. Write the simulation, then go to parts and the netlist. Say that the electrical checks were skipped.

Otherwise run:

```bash
.venv/bin/python tools/pcb_stage.py designs/<slug> verify
```

On a failure, read stderr and `simulation-results.json`. Exit 2 means the file crashed or `measure()` did not read ngspice: fix that before tuning values. Otherwise make a justified correction and rerun the stage. Continue diagnosing failures and making justified repairs; only the user cancels execution. Do not change specified values, topology or tolerances to force a pass. Do not edit `simulation-results.json` or change `circuit-spec.json` to hide a failure. Do not continue to parts until verification returns a nonempty passing result and fresh simulation evidence.

Follow the parts skill. Run the `parts` stage with `pcb_stage` on `designs/<slug>`. It keeps the IC in `ic.json` and matches the passives in `skidl_sim.py`. With `skip_verify`, it does not require `simulation-evidence.json`. Write `parts/skidl_kicad.py` from `parts/parts.json` using the same nets. Index `U1` by the pin `number` in `ic.json` (`u1[1] += vin`), not by pin name. Then run the `netlist` stage with `pcb_stage`. Stop if a part is unmatched or `changes_measured_value` is true, and say what has to change. Do not start `/layout`.

Use the `pcb_stage` tool (or `.venv/bin/python tools/pcb_stage.py designs/<slug> <stage>`) for mechanical stages: `prepare` runs requirement checks and IC selection; after writing the simulation, `verify` produces measurements and stress evidence; `parts` selects components; after writing the manufacturing script, `netlist` validates it. Read full logs only when the compact result is insufficient. There is no automatic repair budget or session deadline.

Give passives explicit references. List simulation-only loads in `external_components`; a board resistor with the same resistance stays on the board. Include physical connectors or test points for VIN, VOUT, GND and each named interface. Set actual passive values in `skidl_kicad.py`, and use installed numbered KiCad pins (normally `1`, `2` for R/C/L, not SPICE `p`, `n`). Preserve the circuit connectivity.

`parts.json.status` must be `pass`, with known applicable ratings meeting observed stress. Unknown current stress, a heuristic footprint match, or stale evidence is unverified and blocks netlist generation. `netlist-report.json` must pass before `/layout`. A pass covers the listed checks, not all datasheet, thermal or worst-case behavior.
