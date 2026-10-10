---
description: Write placement constraints, then place, route, and check the board
argument-hint: "[board]"
---

Follow the pcb-agent and layout skills.

Board: ${1:-the part-selected circuit}

Read `designs/<slug>/design/` and `designs/<slug>/parts/`. Stop if `parts/board.net` is missing and say that `/parts` has to run first. Write `designs/<slug>/layout/constraints.json`. Do not assign coordinates or draw traces.

Run `.venv/bin/python skills/layout/layout.py designs/<slug>`. When it exits 1, read `layout/report.json`, change `constraints.json` for the reasons it lists, and run it again. When it exits 2, fix the error on stderr and run it again. Stop when it exits 0, or when the only way forward is a larger board or a different part, and ask the user. Report the board size, unrouted count, DRC errors, and every check in `report.json`.
