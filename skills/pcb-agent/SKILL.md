---
name: pcb-agent
description: Orchestrate a PCB design from a natural-language specification. Use when the user asks to design, change, or review a board.
---

# PCB agent

Use the model for engineering intent. Use tools for simulation, placement, routing, and design-rule checks. Do not emit board coordinates or traces.

Pipeline, in order:

1. `circuit` — `/design` writes the spec, the `requirements` skill asks for any missing detail, then SKiDL. It runs that design's tests and revises the SKiDL until they pass. This is the current milestone.
2. `parts` — `/parts`, after verification passes.
3. `layout` — `/layout`, after part selection.

Each request gets one directory, `designs/<slug>/`. `<slug>` is a short kebab-case name, such as `buck-5v-3v3`. Circuit, parts, and layout all write in that directory. Do not add a subdirectory per stage, and do not write design files in the repository root or the home directory. Reuse the existing directory when the request already has one.

Load the skill for the stage you are in. Do not start a later stage until the user runs its command, and do not claim a tool ran when this package has no runner for it.
