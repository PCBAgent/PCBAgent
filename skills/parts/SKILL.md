---
name: parts
description: Map a SPICE-passing circuit to real parts, KiCad symbols, and footprints. Use during /design, after ngspice passes, and before layout.
---

# Parts

Read `designs/<slug>/design/circuit-spec.json`, `designs/<slug>/design/ic.json` when it exists, and `designs/<slug>/design/skidl_sim.py`. Write `designs/<slug>/parts/`. `/design` runs this after pytest exits 0.

The part source is the local JLCPCB cache at `.tools/jlcpcb/economic-parts.csv`. If that file is missing, download it once:

```bash
.venv/bin/python skills/parts/fetch_catalog.py
```

Then choose parts without using the network:

```bash
.venv/bin/python skills/parts/lookup.py designs/<slug>
```

`parts/parts.json` is the catalog result. Every manufacturer part number, value, tolerance, voltage, current, power, package, stock, price, and basic or preferred status in that file was copied from the cache. Do not invent them. The footprint is the exact KiCad file for the package when that file exists, and the nearest footprint in that part's library otherwise. When `design/ic.json` exists, the regulator in `parts.json` is that same part. A part with `matched` false or `changes_measured_value` true stops this stage. A value change means the simulation has to be revised. `on_board` false is the simulated load, not a board part. A `D()` in the simulation is the catch diode of an asynchronous regulator. Lookup matches it to a Schottky rated for the supply and the load current. `external_diode` true on `ic.json` with no `D()` in the simulation stops this stage: add the diode and simulate again. The KiCad netlist places that diode anode to ground and cathode on the switch net.

Write `parts/skidl_kicad.py` from the matched on-board parts, using `from skidl import *` and `set_default_tool(KICAD)`. Use the `symbol` and `footprint` fields from `parts.json`. Connect `U1` by the pin `number` in `design/ic.json`, on the same nets as `skidl_sim.py`: `u1[1] += vin`, not `u1['VIN']` or `u1['~{EN}']`. Tie every ground pin number, including hidden ones, to ground. Tie the enable pin number to the input net. An adjustable part keeps the feedback divider. An asynchronous part keeps the catch diode. The file calls `ERC()` and `generate_netlist(file_="board.net")`. Then run:

```bash
.venv/bin/python skills/parts/netlist.py designs/<slug>
```

A missing footprint aborts the netlist. Do not place parts or draw traces.
