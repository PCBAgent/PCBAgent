---
name: circuit
description: Turn a natural-language circuit request into a spec, a SKiDL simulation, and passing ngspice checks. Use during /design, before parts or layout.
---

# Circuit

Read `schemas/circuit-spec.schema.json` and write a spec that validates against it. Load the `requirements` skill and run its check before any simulation file. If that check asks the user for missing requirements, stop there. After the check passes, load the `skidl` skill and write the simulation file it describes. Do not hand-write a SPICE deck or a KiCad netlist.

Write these files in the design directory from the pcb-agent skill:

- `circuit-spec.json`
- `skidl_sim.py`, which defines `measure()`

`measure()` builds the circuit, runs the ngspice analyses it needs, and returns a dict from spec field name to measured number, such as `{"output_voltage_v": 3.29, "output_current_a": 2.01}`. Return a value for every measured field in the spec: `output_voltage_v`, `gain`, `bandwidth_hz`, `output_current_a`. Measure each one from the simulation. Do not return the spec target.

Then run the tests for this design. The checks come from its `circuit-spec.json`:

```bash
.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>
```

The test runs `skills/circuit/verify.py` on that directory. The runner writes `simulation-results.json`, one object per measured field matching `schemas/simulation-result.schema.json`. Targets and tolerances come from `circuit-spec.json`. The runner sets `status`. On a failure it prints why: measured value, target, tolerance, and whether the measurement is high or low. Do not write or edit `simulation-results.json` yourself, and do not relax a requirement to make a failure pass.

Pytest exits 0 when every check passes. Otherwise read the failed measurements, change `skidl_sim.py` so those errors shrink, and run the tests again. Repeat until pytest exits 0. Exit 2 means there is no result: `skidl_sim.py` crashed, `measure()` is missing or skipped a field, or a tolerance is missing from the spec. Fix that cause before judging numbers.
