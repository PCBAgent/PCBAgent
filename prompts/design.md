---
description: Specify a circuit, simulate it, and repair the SKiDL until the tests pass
argument-hint: "<specification>"
---

Follow the pcb-agent, requirements, circuit, and skidl skills.

The text below is the user's request. Write `circuit-spec.json` in one `designs/<slug>/` directory from it. Run the requirements check before writing `skidl_sim.py`. Ask only for requirements the check reports as missing, then stop. Do not ask the user to repeat a requirement that is already in the spec.

Specification: $@

After `skidl_sim.py` exists, run:

```bash
.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>
```

If pytest fails, read `simulation-results.json` and the runner's stderr. Each failed line says the measured value, the target, and whether the measurement is high or low. Change `skidl_sim.py` to close that error. If the runner exits 2, fix the crash or missing measurement before changing circuit values. Run the tests again. Repeat until pytest exits 0. Do not edit `simulation-results.json` by hand, and do not change `circuit-spec.json` to hide a failure. Do not select catalog parts or emit board coordinates.
