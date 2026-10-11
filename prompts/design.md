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
| board size, width then height | `board_max_mm`: `{"width", "height"}` |
| the shop | `manufacturing.vendor` |
| parts the user named, one string each | `preferred_components` |

Do not invent keys such as `input_voltage`, `inductance`, `input_capacitor1`, or `pcb_vendor`. A named inductor or capacitor belongs in `preferred_components`, not in its own field. `load` is the measurement load, not a preferred part.

Folder: `designs/<slug>/`. `<slug>` is a short kebab-case name from the spec, such as `buck-5v-3v3`. Do not ask for a name. Reuse the directory when one already exists.

Write `designs/<slug>/design/circuit-spec.json`, then run:

```bash
.venv/bin/python skills/requirements/check_spec.py designs/<slug>/design/circuit-spec.json
```

If `ok` is false, ask only for the fields in `missing`, then stop. If `ok` is true, choose the IC before writing the simulation:

```bash
.venv/bin/python skills/parts/choose_ic.py designs/<slug>
```

Exit 1 means the cache has no regulator that meets the spec: stop and say so. Exit 0 with `"ic": null` means this circuit has no regulator. A written `designs/<slug>/design/ic.json` is the catalog part. Read `topology`, `external_diode`, `adjustable`, `feedback_voltage_v`, `pins`, and `roles`.

`roles.input` is the supply pin and `roles.ground` is ground. Connect every pin whose name is that ground, including the hidden ones. Connect `roles.enable` to `roles.input` so the chip is on. On the XL1509 the symbol draws that pin as `~{EN}`, and the datasheet still enables the chip when the pin is high.

Build the external circuit the chosen IC actually needs:

- `topology` `ldo`: the output pin is the regulated rail. No inductor, no switch, and no diode. A fixed LDO is a voltage source from `roles.output` to ground at its regulated voltage. An adjustable LDO uses the feedback divider below.
- `topology` `buck` or `boost`: `roles.switch` is the inductor's upstream pin. When `switch` and `output` are the same name, that pin is not the regulated rail; the regulated rail is the other side of the inductor. The internal high-side switch is `S()` driven by `PULSEV`, from the input net to the switch net. `external_diode` true means the part is asynchronous and the simulation must include a catch diode, anode at ground and cathode at the switch net: `D(ref="D1")["p", "n"] += gnd, switch`. Lookup matches that diode to a catalog Schottky. Omitting it makes lookup fail, and a buck without it does not regulate.
- `adjustable` true: add a resistor divider from the regulated rail to `roles.feedback` to ground. `feedback_voltage_v` is the reference. The regulated voltage is that reference times `1 + Rtop / Rbottom`. Those resistors are board parts, not the load.

Then read the skidl skill and write `designs/<slug>/design/skidl_sim.py`.

The simulation is the circuit the user asked for, including every preferred part at the value they gave, connected to the pins in `ic.json` when that file exists. A resistor divider does not replace the switch, inductor, and catch diode. The feedback divider is added on top of that circuit when `adjustable` is true. Build it inside `measure()` and return numbers read from ngspice. Do not return the spec targets, and do not scale a simulated value onto a target.

`V` is a DC source and accepts `dc_value` only. A repeating pulse is `PULSEV` with `initial_value`, `pulsed_value`, `pulse_width`, and `period`. Passing pulse arguments to `V` emits `DC V` and ngspice rejects it. Fix the constructor. Do not write a side script to inspect the deck. `5 @ u_V` is 5 volts. A switch or diode model is `DeviceModel`, not a `.model` line. For a switcher, run a transient and return the average of the settled samples. Load current is the load voltage divided by the load resistance.

Specification: $@

Then run:

```bash
.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>
```

On a failure, read stderr and `simulation-results.json`. Exit 2 means the file crashed or `measure()` did not read ngspice: fix that before tuning values. Otherwise change `skidl_sim.py` so the reported error shrinks, and run pytest again until it exits 0. Do not edit `simulation-results.json` or change `circuit-spec.json` to hide a failure.

When pytest exits 0, follow the parts skill. Run `skills/parts/lookup.py` on `designs/<slug>`. It keeps the IC in `ic.json` and matches the passives in `skidl_sim.py`. Write `parts/skidl_kicad.py` from `parts/parts.json` using the same nets. Index `U1` by the pin `number` in `ic.json` (`u1[1] += vin`), not by pin name. Then run `skills/parts/netlist.py`. Stop if a part is unmatched or `changes_measured_value` is true, and say what has to change. Do not start `/layout`.
