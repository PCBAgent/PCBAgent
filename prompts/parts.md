---
description: Repeat the catalog lookup and KiCad netlist that /design already writes
argument-hint: "[design]"
---

Follow the pcb-agent, parts, and skidl skills.

`/design` already chooses the IC, simulates it, and writes `parts/board.net`. Run this only to repeat the catalog lookup and the KiCad netlist for a design whose simulation already passes.

Design: ${@:-the current designs/<slug> directory}

Read `designs/<slug>/design/`. Run `skills/parts/lookup.py` on that directory. It keeps `design/ic.json` when that file exists and matches a `D()` catch diode when that IC is asynchronous. Write `parts/skidl_kicad.py` from `parts/parts.json`, indexing the IC by the pin `number` in `ic.json` (`u1[1] += vin`, not `u1['VIN']`). Then run `skills/parts/netlist.py`. Do not invent stock, price, or footprint names. If lookup reports a value change or a missing part, stop and say what has to change. A missing catch diode means the simulation has to include one. Do not place parts or draw traces.
