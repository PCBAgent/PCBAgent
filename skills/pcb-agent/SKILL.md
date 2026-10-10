---
name: pcb-agent
description: Orchestrate a PCB design from a natural-language specification. Use when the user asks to design, change, or review a board.
---

# PCB agent

Use the model for engineering intent. Use tools for simulation, placement, routing, and design-rule checks. Do not emit board coordinates or traces.

Pipeline, in order:

1. `circuit` — specification, then a SKiDL simulation file (`skidl`), then ngspice. This is the current milestone.
2. `parts` — map a passing circuit to real parts, symbols, and footprints.
3. `layout` — placement constraints, placement, routing, and design-rule checks.

Load the skill for the stage you are in. Do not start a later stage until the user asks, and do not claim a tool ran when this package has no runner for it.
