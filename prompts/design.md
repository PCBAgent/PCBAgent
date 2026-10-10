---
description: Specify a circuit, simulate it, and repair the SKiDL until the tests pass
argument-hint: "<specification>"
---

Follow the pcb-agent, requirements, circuit, and skidl skills.

The text below is the user's request. Write `designs/<slug>/design/circuit-spec.json` from it. Run the requirements check before writing `designs/<slug>/design/skidl_sim.py`. Ask only for requirements the check reports as missing, then stop. Do not ask the user to repeat a requirement that is already in the spec.

Specification: $@

After `designs/<slug>/design/skidl_sim.py` exists, run:

```bash
.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>
```

If pytest fails, read `designs/<slug>/design/simulation-results.json` and the runner's stderr. Each failed line says the measured value, the target, and whether the measurement is high or low. Change `designs/<slug>/design/skidl_sim.py` to close that error. If the runner exits 2, fix the crash or missing measurement before changing circuit values. If stderr says the measurement did not come from ngspice, `measure()` is returning a constant: write the circuit, simulate it, and return the simulated numbers. Do not return the spec targets. Run the tests again. Repeat until pytest exits 0. Do not edit `simulation-results.json` by hand, and do not change `circuit-spec.json` to hide a failure. Do not select catalog parts or emit board coordinates.
