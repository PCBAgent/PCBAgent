---
name: requirements
description: Check a circuit spec for enough measurable detail before SKiDL. Use during /design, after circuit-spec.json is drafted and before the simulation file. Ask the user for every missing requirement.
---

# Requirements

Write `circuit-spec.json` first, using only values the user stated. Then run:

```bash
.venv/bin/python skills/requirements/check_spec.py designs/<slug>/design/circuit-spec.json
```

The script prints JSON. `missing` lists each field that is still too thin to test, with the question to ask.

When `ok` is false, ask the user those questions and stop. Do not write `skidl_sim.py` or run the simulation. Do not invent the missing numbers, loads, tolerances, or board size. Do not ask again for a field that is already present.

When the user answers, add those values to `circuit-spec.json` and run the script again. Continue to SKiDL only after `ok` is true.

A qualitative word is not a requirement. "Small" does not set `board_max_mm`. A shop named in the prompt still needs `manufacturing.vendor` filled in. Each measured number needs a `tolerances` entry, and that tolerance has to come from the user.
