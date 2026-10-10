---
description: Map a passing circuit to real parts and a KiCad netlist
argument-hint: "[design]"
---

Follow the pcb-agent, parts, and skidl skills.

Design: ${@:-the current designs/<slug> directory}

Read `designs/<slug>/design/`. Run `skills/parts/lookup.py` on that directory. Write `parts/skidl_kicad.py` from `parts/parts.json`, then run `skills/parts/netlist.py`. Do not invent stock, price, or footprint names. If lookup reports a value change or a missing part, stop and say what has to change. Do not place parts or draw traces.
