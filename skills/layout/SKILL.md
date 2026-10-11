---
name: layout
description: Turn a part-selected circuit into placement constraints, then a placed, routed, and checked KiCad board. Use when the user runs /layout, after /design has written parts/board.net.
---

# Layout

Read `schemas/constraints.schema.json`, the passing circuit in `designs/<slug>/design/`, `designs/<slug>/parts/parts.json`, and `designs/<slug>/parts/board.net`. Write `designs/<slug>/layout/constraints.json`. Constraints say what a good placement is. Do not assign (x, y) coordinates or draw traces.

## Constraints

Name parts by the reference designators in `board.net` and nets by its net names. Distances are gaps between courtyards, in millimeters. The board outline is the placement's bounding box plus the edge clearance, so an edge is wherever the outermost parts end up.

| Type | Use it for | Fields |
|---|---|---|
| `proximity` | Decoupling capacitors, feedback dividers, crystals next to their IC | `components` (first is the anchor), `max_distance_mm` |
| `group` | Parts of one functional block | `components`, optional `max_distance_mm` (default 3) |
| `board_edge` | Connectors, buttons, LEDs that must be reachable | `component` or `components`, `preferred_edge`, optional `max_distance_mm` (default 0.5) |
| `keepout` | A part-free strip, for a clamp, label, or mounting area | `edge`, `depth_mm` |
| `separation` | Keep noisy parts away from sensitive ones | `components`, `from`, `min_distance_mm` |
| `loop_area` | The switching loop of a regulator: input capacitor, switch, diode or low-side switch | `components` (three or more), optional `max_area_mm2` |
| `high_current` | Supply and switch-node nets | `nets`, `track_width_mm` |
| `differential_pair` | USB D+/D-, other pairs | `nets` (two), optional `max_skew_mm` |
| `orientation` | Connectors that must face out, polarized parts in a row | `component` or `components`, `rotation_deg` |

`weight` is relative importance. `hard: true` makes a violation illegal. Use `hard` for what would break the board, such as a connector that must reach the edge or a decoupling capacitor that must sit at its pin. Leave the rest soft. Every hard constraint narrows what the placer can find.

Size `track_width_mm` from the current. IPC-2221, 1 oz outer copper, 10 °C rise: about 0.3 mm for 1 A, 0.8 mm for 2 A, 1.3 mm for 3 A. The optional `rules` object overrides the board rules. Its defaults in `place.py` fit a JLCPCB 2-layer board: 0.25 mm tracks, 0.15 mm minimum, 0.2 mm clearance, 0.6/0.3 mm vias, 0.5 mm edge clearance, 0.5 mm between courtyards. Change them only when the user or the shop asks.

The board size limit comes from `board_max_mm` in `design/circuit-spec.json`. The board may be rotated to fit it.

## Rules the runner adds

Shop rules in `place.py` apply to every board: 0.25 mm tracks, 0.15 mm minimum, 0.2 mm clearance, 0.6/0.3 mm vias, 0.5 mm copper-to-edge, and 0.5 mm between courtyards. DRC rejects shorts, clearance errors, copper past the outline, and unrouted nets. Warnings, such as silkscreen clipped by the edge, do not fail the board.

After `constraints.json` validates, the runner adds general rules the file does not already cover and writes them back into that file:

| Rule | What it adds |
|---|---|
| `board_edge`, hard, 0.5 mm | Connectors, switches, LEDs, and test points. Edges are assigned left, right, top, bottom |
| `proximity`, hard, 2 mm | A capacitor from a supply net to ground, next to the IC on that net, or the switch transistor when there is no IC |
| `group`, soft, 3 mm | Each IC and the passives on its nets |
| `loop_area`, soft | The input capacitor, switch, and diode when the board has an inductor and a diode |
| `separation`, soft, 5 mm | An inductor and a sensitive part: amplifier, sensor, crystal, or ADC |
| `high_current` | Supply, output, switch, and ground nets, when `output_current_a` needs copper wider than 0.25 mm. Width is about 0.3 mm at 1 A, 0.8 mm at 2 A, and 1.3 mm at 3 A |
| `differential_pair`, 5 mm skew | Nets named as a pair, such as `D+`/`D-` or `USB_D_P`/`USB_D_N` |

A rule already in the file is left as written. On exit 1, loosen one of these the same way as a rule you wrote.

## Run

```bash
.venv/bin/python skills/layout/layout.py designs/<slug>
```

The runner validates `constraints.json`, reads footprint courtyards and pads from the installed KiCad libraries, and places the parts: force-directed start, then simulated annealing over wire length, overlap, constraint violations, board area, and loop area. KiCad builds `placed.kicad_pcb` and exports `board.dsn`. Freerouting writes `board.ses`. KiCad imports it as `board.kicad_pcb`. `placement.png` is the 2D board view of `placed.kicad_pcb` before routing: copper, silk, courtyard, fabrication, and the outline. `board.png` is the 3D view of the routed board. `kicad-cli pcb drc` checks design rules, clearance, the board edge, and unrouted nets. The runner also checks each `high_current` net's routed width and each `differential_pair` skew.

A failed attempt goes back to the placer: a new seed, and more room between parts that no `proximity` or `group` ties together. After four attempts the runner keeps the best one in `designs/<slug>/layout/` and writes `report.json`.

Exit 0 means the board passed. Exit 1 means a board or placement exists but a check failed. `report.json` has `return_to: "constraints"` and `reasons`. Read the reasons and change `constraints.json`: loosen or drop a hard constraint the placer could not meet, raise a too-small `max_distance_mm`, or ask the user for a larger board when the board does not fit `board_max_mm`. Do not change `circuit-spec.json`. Run the runner again. Exit 2 means there is no board: a missing file, a schema error, an unknown part or net, or a missing tool. The error is on stderr.

`high_current` allows a narrower trace within 1 mm of a pad on that net, where fine-pitch pins force it. `report.json` lists that length as `necked_near_pads_mm`. DRC warnings, such as silkscreen clipped by the board edge, are reported and do not fail the board.

Do not edit `board.kicad_pcb`, `placement.json`, or `report.json` by hand. Do not claim a check passed unless `report.json` says so.

When the user asks to demonstrate placement and routing, add `--demo` to the layout command.
It records stage results and opens an animated copy in KiCad 10 with its API enabled. Replay with
`.venv/bin/python skills/layout/demo.py designs/<slug> --replay`; use `--speed 2` for faster playback.
This animation presents calculated results, not the optimizer's decision history. Runs from SSH
without a desktop still save the recording for later replay. Connection errors are in the run's
`layout/demo/<run-id>/playback.log`; the layout pipeline continues independently.
