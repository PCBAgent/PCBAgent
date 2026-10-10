---
name: pcb-agent
description: Orchestrate a PCB design from a natural-language specification. Use when the user asks to design, change, or review a board.
---

# PCB agent

Use the model for engineering intent. Use tools for simulation, placement, routing, and design-rule checks. Do not emit board coordinates or traces.

Pipeline, in order:

1. `circuit` — `/design` writes the spec, the `requirements` skill asks for any missing detail, then SKiDL. It runs that design's tests and revises the SKiDL until they pass. A pass is an ngspice measurement. Copying the spec numbers into `measure()` is not a circuit and does not pass. This is the current milestone.
2. `parts` — `/parts`, after verification passes.
3. `layout` — `/layout`, after part selection.

Each request gets one directory, `designs/<slug>/`. `<slug>` is a short kebab-case name taken from the specification, such as `buck-5v-3v3`. The design step writes `designs/<slug>/design/`. The parts step reads that folder and writes `designs/<slug>/parts/`. Layout reads both and writes `designs/<slug>/layout/`. Do not write design files in the repository root or the home directory. Reuse the existing directory when the request already has one.

Load the skill for the stage you are in. Do not start a later stage until the user runs its command, and do not claim a tool ran when this package has no runner for it.
