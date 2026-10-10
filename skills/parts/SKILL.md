---
name: parts
description: Map a SPICE-passing circuit to real parts, KiCad symbols, and footprints. Use only after circuit verification passes and the user asks for manufacturable parts.
---

# Parts

Start from a circuit that has passing simulation results in its `designs/<slug>/` directory. Replace generic or ideal components with real parts. Add `parts.json` and the KiCad SKiDL file `skidl_kicad.py` in that same directory.

For each part, record the manufacturer part number, nominal value, tolerance, voltage rating, current rating, power rating, package, availability, price, stock, and whether it is a preferred or basic part. Then name the KiCad symbol and footprint.

The part source is an offline or cached JLCPCB catalog. No catalog and no lookup tool are in this package yet. Do not invent stock, price, or footprint names.
