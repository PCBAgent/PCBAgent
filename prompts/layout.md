---
description: Write placement constraints, then place, route, and check the board
argument-hint: "[board]"
---

Follow the pcb-agent and layout skills.

Board: ${1:-the part-selected circuit}

Read `designs/<slug>/design/` and `designs/<slug>/parts/`. Write `designs/<slug>/layout/constraints.json`. Do not assign coordinates or draw traces. Continue through placement, routing, and board checks only where a tool exists. If a step has no tool, stop and name the file that step would read.
