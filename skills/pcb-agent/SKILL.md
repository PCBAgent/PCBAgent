---
name: pcb-agent
description: Orchestrate a PCB design from a natural-language specification. Use when the user asks to design, change, or review a board.
---

# PCB agent

Use the model for engineering intent. Use tools for simulation, placement, routing, and design-rule checks. Do not emit board coordinates or traces.

Pipeline, in order:

1. `circuit` — `/design`, then ngspice, then `/verify` when a result fails. This is the current milestone.
2. `parts` — `/parts`, after verification passes.
3. `layout` — `/layout`, after part selection.

Load the skill for the stage you are in. Do not start a later stage until the user runs its command, and do not claim a tool ran when this package has no runner for it.
