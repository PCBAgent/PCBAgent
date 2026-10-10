---
description: Map a passing circuit to real parts and a KiCad netlist
argument-hint: "[circuit]"
---

Follow the pcb-agent, parts, and skidl skills.

Circuit: ${1:-the passing simulation circuit}

Start from passing simulation results in `designs/<slug>/`. Record real parts in `parts.json` and write `skidl_kicad.py` there. Do not invent stock, price, or footprint names. If a selected part changes a measured value, say that the circuit stage has to run again. Do not place parts or draw traces.
