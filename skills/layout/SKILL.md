---
name: layout
description: Turn a placed-part circuit into placement constraints, then a routed KiCad board. Use only after part selection and when the user asks for layout.
---

# Layout

Read `schemas/constraints.schema.json` and the passing circuit in `designs/<slug>/design/`. Read `designs/<slug>/parts/parts.json` and `designs/<slug>/parts/board.net`. Write `designs/<slug>/layout/constraints.json`. Constraints say what a good placement is. Do not assign (x, y) coordinates or draw traces. Later board files (`board.dsn`, `board.ses`) stay in `designs/<slug>/layout/`.

Order:

1. Constraints from the circuit topology (proximity, grouping, edge placement, loop area, separation).
2. A placer minimizes wire length, overlap, constraint violations, board area, and loop area. No placer is in this package yet.
3. Freerouting routes the placed board. KiCad exports a Specctra `.dsn`. `freerouting-cli -de board.dsn -do board.ses` writes the session. KiCad imports that `.ses`. Do not draw traces. No caller for this command is in the package yet.
4. Design-rule, electrical-rule, unrouted-net, footprint, clearance, and board-edge checks. Failures return to the placer or the constraint list. No checker is in this package yet.

If a later step has no tool, stop and say which file would be its input.
