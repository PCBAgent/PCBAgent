---
name: pcb-agent
description: Orchestrate a PCB design from a natural-language specification. Use when the user asks to design, change, or review a board.
---

# PCB agent

Use the model for engineering intent. Use tools for simulation, placement, routing, and design-rule checks. Do not emit board coordinates or traces.

Pipeline, in order:

1. `circuit` and `parts` — `/design` writes the spec, the `requirements` skill asks for any missing detail, then chooses a catalog IC when the request is a regulator. It writes the SKiDL simulation around that IC's pins and revises it until ngspice passes. A pass is an ngspice measurement. Copying the spec numbers into `measure()` is not a circuit and does not pass. After that pass it selects the remaining catalog parts and writes `parts/board.net`.
2. `layout` — `/layout`, after `/design` has written `parts/board.net`.

Each request gets one directory, `designs/<slug>/`. `<slug>` is a short kebab-case name taken from the specification, such as `buck-5v-3v3`. `/design` writes `designs/<slug>/design/` and `designs/<slug>/parts/`. Layout reads both and writes `designs/<slug>/layout/`. Do not write design files in the repository root or the home directory. Reuse the existing directory when the request already has one.

Load the skill for the stage you are in. Do not start layout until the user runs `/layout`, and do not claim a tool ran when this package has no runner for it.
