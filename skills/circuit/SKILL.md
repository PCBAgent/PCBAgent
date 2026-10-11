---
name: circuit
description: Turn a natural-language circuit request into a spec, a SKiDL simulation, catalog parts, and a KiCad netlist. Use during /design, before layout.
---

# Circuit

Read `schemas/circuit-spec.schema.json` and write a spec that validates against it. Load the `requirements` skill and run its check before any simulation file. If that check asks the user for missing requirements, stop there. After the check passes, run `skills/parts/choose_ic.py` on the design. When it writes `design/ic.json`, the simulation uses that topology. An LDO is not a buck. An asynchronous buck or boost includes the catch diode `ic.json` asks for, and an adjustable part includes the feedback divider around `feedback_voltage_v`. Connect those parts to the pin names in the file. Then load the `skidl` skill and write the simulation file it describes. Do not hand-write a SPICE deck. The KiCad netlist comes after pytest exits 0, from the parts skill.

Write these files in `designs/<slug>/design/`:

- `circuit-spec.json`
- `skidl_sim.py`, which defines `measure()`

`measure()` builds the circuit, runs the ngspice analyses it needs, and returns a dict from spec field name to measured number, such as `{"output_voltage_v": 3.29, "output_current_a": 2.01}`. Return a value for every measured field in the spec: `output_voltage_v`, `gain`, `bandwidth_hz`, `output_current_a`. Read each one from the simulation. The runner exits 2 if a returned number did not come from ngspice, including a copy of the spec target and a simulated value scaled back onto that target. If the simulation crashes or the circuit is wrong, fix `skidl_sim.py`. Do not replace it with a function that returns the spec.

Then run the tests for this design. The checks come from its `circuit-spec.json`:

```bash
.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>
```

The test runs `skills/circuit/verify.py` on `designs/<slug>`. The runner reads and writes `designs/<slug>/design/`. It writes `simulation-results.json` there, one object per measured field matching `schemas/simulation-result.schema.json`. Targets and tolerances come from `circuit-spec.json`. The runner sets `status`. On a failure it prints why: measured value, target, tolerance, and whether the measurement is high or low. Do not write or edit `simulation-results.json` yourself, and do not relax a requirement to make a failure pass.

Pytest exits 0 when every check passes. Otherwise read the failed measurements, change `skidl_sim.py` so those errors shrink, and run the tests again. Repeat until pytest exits 0. Exit 2 means there is no result: `skidl_sim.py` crashed, `measure()` is missing or skipped a field, or a tolerance is missing from the spec. Fix that cause before judging numbers.

After pytest exits 0, load the `parts` skill. `lookup.py` keeps the IC in `design/ic.json` and matches the simulated passives. Write `parts/skidl_kicad.py` with those symbols and the same nets, indexing the IC by pin number (`u1[1]`), then run `skills/parts/netlist.py`. That writes `parts/board.net`. Stop there until the user runs `/layout`.
