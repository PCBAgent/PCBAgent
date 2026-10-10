---
name: parts
description: Map a SPICE-passing circuit to real parts, KiCad symbols, and footprints. Use only after circuit verification passes and the user asks for manufacturable parts.
---

# Parts

Read `designs/<slug>/design/circuit-spec.json` and `designs/<slug>/design/skidl_sim.py`. Write `designs/<slug>/parts/`.

The part source is the local JLCPCB cache at `.tools/jlcpcb/economic-parts.csv`. If that file is missing, download it once:

```bash
.venv/bin/python skills/parts/fetch_catalog.py
```

Then choose parts without using the network:

```bash
.venv/bin/python skills/parts/lookup.py designs/<slug>
```

`parts/parts.json` is the catalog result. Every manufacturer part number, value, tolerance, voltage, current, power, package, stock, price, and basic or preferred status in that file was copied from the cache. Do not invent them. A part with `matched` false or `changes_measured_value` true stops this stage. A value change means `/design` has to run again. `on_board` false is the simulated load, not a board part.

Write `parts/skidl_kicad.py` from the matched on-board parts, using `from skidl import *` and `set_default_tool(KICAD)`. Use the `symbol` and `footprint` fields from `parts.json`. The file calls `ERC()` and `generate_netlist(file_="board.net")`. Then run:

```bash
.venv/bin/python skills/parts/netlist.py designs/<slug>
```

A missing footprint aborts the netlist. Do not place parts or draw traces.
