# PCBAgent

PCBAgent turns a natural-language circuit request into a SPICE-verified, real-parts-selected, placed, and routed board. The model does engineering reasoning. Deterministic tools simulate, check, place, route, and enforce design rules. The model does not emit board coordinates or traces.

The project was first proposed as OfflineOhm. Running the whole flow on a local model, so a confidential design never leaves the machine, is still a goal. The work now is to prove the pipeline on the ASUS Ascent GX10, over SSH. Nemotron is already installed there. There is no separate laptop workflow yet.

## Repository

This repo is a Pi package. Pi itself is installed on the GX10. Do not copy the Pi monorepo into this repo.


| Path                                            | Role                                                                                                                            |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `skills/pcb-agent`                              | Stage order and the rule that later stages wait until asked                                                                     |
| `skills/circuit`                                | Spec, SKiDL simulation file, ngspice repair loop                                                                                |
| `skills/skidl`                                  | How to write SKiDL. Simulation files use `skidl.pyspice`. A KiCad netlist is a separate file                                    |
| `skills/parts`                                  | Local JLCPCB cache, lookup, and KiCad netlist runner                                                                            |
| `skills/layout`                                 | Constraints, placement, routing, design-rule checks                                                                             |
| `skills/layout/layout.py`                       | Layout runner: places, builds the KiCad board, routes with Freerouting, runs DRC and routed checks, writes `layout/report.json` |
| `skills/layout/place.py`                        | Netlist reader, constraint checks, force-directed and simulated-annealing placer                                                |
| `skills/layout/kicad.py`                        | KiCad steps through `pcbnew`: footprint geometry, board build, rules and `.dsn` export, `.ses` import                           |
| `skills/circuit/verify.py`                      | Simulation runner: runs `measure()` in `skidl_sim.py`, judges each result, writes `simulation-results.json`                     |
| `skills/circuit/schemas/`                       | Circuit spec and one simulation measurement                                                                                     |
| `tests/`                                        | Runner contracts for circuit, parts, and layout. A design is checked with `pytest --design designs/<slug>`                      |
| `skills/layout/schemas/constraints.schema.json` | Placement constraints                                                                                                           |
| `prompts/`                                      | `/design`, `/layout`                                                                                                            |
| `requirements.txt`, `setup.sh`                  | SKiDL 2.3.0, KiCad MCP, Freerouting 2.5.0, Pi, and `uv`                                                                         |
| `.pi/mcp.json`                                  | `kicad-schematic` and `kicad-pcb`                                                                                               |
| `models.example.json`                           | Ollama endpoint for Nemotron                                                                                                    |


Development is an SSH session on the GX10. Run `./setup.sh` in this checkout there. `source .venv/bin/activate` sets `KICAD_SYMBOL_DIR` from the installed KiCad and puts `kicad-cli` on `PATH`. `~/.pi/agent/models.json` uses `baseUrl` `http://127.0.0.1:11434/v1` and the Nemotron id from `ollama list`.

## Design flow

A design starts from a natural-language request in `pi` on the GX10. Three stages run in order. A later stage starts when the user runs its command, and only after the previous stage has passed. The model writes engineering intent. Tools simulate, judge, place, route, and check. The model does not emit board coordinates or traces, and it does not claim a tool ran when this package has no runner for it.

Hackathon demonstrations stay inside a small family: op-amp amplifiers, voltage regulators, sensor interfaces, analog filters, and simple microcontroller peripherals. The long-term request is a compact USB environmental sensor (temperature, humidity, pressure) on I2C.

### Example

```text
/design 5 V supply to 3.3 V LDO using one linear regulator IC, a 10 µF input capacitor, a 100 nF regulator decoupling capacitor, and a 22 µF output capacitor, then one LM358 IC on that 3.3 V rail with a 100 nF decoupling capacitor, buffering a divider of two 10 kΩ resistors, output voltage 3.3 V within 0.05 V, output current 0.1 A within 0.01 A into a 33 ohm load, maximum board size 40 mm by 30 mm, JLCPCB. Use basic parts only.
```

`/design` writes the SKiDL, runs the tests against that design's `circuit-spec.json`, and revises the SKiDL when a measurement misses. Then:

```text
/layout
```

`/design` selects the JLCPCB parts named in that sentence after ngspice passes, and writes `parts/board.net`. `/layout` writes constraints, then places, routes, and checks the board.

### 1. Circuit

`/design` takes the request.

1. The model writes a circuit spec that validates against `skills/circuit/schemas/circuit-spec.schema.json`. The spec keeps the original prompt and the acceptance numbers: supply and output voltage, gain, bandwidth, current, load, interfaces, preferred parts, package limits, board size, and manufacturing constraints. The `requirements` skill checks that spec. If a required value is missing, `/design` asks the user and does not write SKiDL until the user answers.
2. For a regulator, `/design` runs `skills/parts/choose_ic.py`. That writes `design/ic.json`: the catalog IC, its topology, and its KiCad pin names. A prompt that says LDO or linear selects an LDO. A prompt that says buck, boost, or switching selects that converter. A bare regulator allows either. An asynchronous buck or boost sets `external_diode`, and the simulation includes the catch diode the converter needs to regulate. An adjustable part records `feedback_voltage_v` for its divider. The model then writes one SKiDL simulation file, using `from skidl.pyspice import *`, and connects the passives to those pins. It does not hand-write a SPICE deck.
3. `/design` runs `.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>`. The test reads `designs/<slug>/design/circuit-spec.json` and runs `skills/circuit/verify.py` on that directory. The runner imports `design/skidl_sim.py`, calls `measure()`, and compares each measurement with that spec's targets and tolerances. It writes `design/simulation-results.json` and sets `status`. On a failure it prints the measured value, the target, and whether the measurement is high or low. A failed requirement fails pytest. The runner leaves no results file when the file crashes, `measure()` is missing, a measured field is missing, the spec has no tolerance for a measured field, or a returned number did not come from ngspice. A function that returns the spec targets is not a pass. The model does not judge the numbers. `/design` does not emit coordinates.

```json
{
  "requirement": "output_voltage_v",
  "target": 3.3,
  "measured": 2.74,
  "tolerance": 0.05,
  "status": "fail"
}
```

A failure stays inside `/design`. The model reads why the measurement missed and changes the SKiDL so the same tests pass. It does not change the spec to hide a failure. `/design` repeats the tests until pytest exits 0. `skip_verify: true` in the spec skips this measurement loop. Parts selection and the netlist still run, and the report says the electrical checks were not run.

After pytest exits 0, `/design` searches the local JLCPCB cache, `.tools/jlcpcb/economic-parts.csv`, with the spec and the simulated parts, and writes `designs/<slug>/parts/`. The lookup keeps the IC in `design/ic.json`. The cache is basic and preferred parts downloaded once by `skills/parts/fetch_catalog.py`. A lookup does not use the network. `parts/parts.json` records the manufacturer part number, value, tolerance, voltage, current, power, package, stock, price, and basic or preferred status, plus a KiCad symbol and footprint copied from that cache and the installed KiCad 10 libraries. It does not invent stock, price, or footprint names.

`parts/skidl_kicad.py` uses `from skidl import *` and `set_default_tool(KICAD)`. `skills/parts/netlist.py` runs `ERC()` and writes `parts/board.net`. A missing footprint aborts that netlist. If a selected part changes a value the spec measures, the simulation runs again. A SPICE pass does not establish placement or routing. That ends `/design`.

### 2. Layout

`/layout` starts this stage, after `/design` has written `parts/board.net`. It reads `designs/<slug>/design/` and `designs/<slug>/parts/`, and writes `designs/<slug>/layout/`.

1. The model writes placement constraints that validate against `skills/layout/schemas/constraints.schema.json`: proximity, grouping, edge, keep-out, separation, loop area, high-current paths, differential pairs, and orientation. Constraints name parts by reference designator and nets by name. Distances are courtyard gaps. Edges are relative to the board outline, which is the placement's bounding box plus the edge clearance. `weight` is relative importance. `hard` means a violation is illegal. An optional `rules` object sets track width, clearance, vias, edge clearance, and the gap between parts; the defaults fit a JLCPCB 2-layer board. The model does not assign coordinates or draw traces.
2. `/layout` runs `.venv/bin/python skills/layout/layout.py designs/<slug>`. The runner rejects constraints that fail the schema or name a part or net missing from `board.net`. It then adds general rules the file does not already cover and writes them back: connectors, switches, LEDs, and test points on a board edge; a decoupling capacitor within 2 mm of its IC; a soft group around each IC; a switching loop when an inductor and a diode are present; an inductor kept 5 mm from an amplifier, sensor, crystal, or ADC; supply, switch, and ground nets widened from `output_current_a`; and differential pairs matched within 5 mm. A constraint already in the file is kept. It reads each footprint's courtyard and pads from the installed KiCad libraries. The placer chooses coordinates and rotations. Its cost covers wire length, overlap, constraint violations, board area against `board_max_mm` from the circuit spec, and loop area. It starts force-directed, then runs simulated annealing.
3. KiCad builds `layout/placed.kicad_pcb` with the nets, outline, design rules, and one netclass per `high_current` width, then exports `layout/board.dsn`. The runner removes component outlines from that file, because the Freerouting 2.5.0 native build crashes on them. `freerouting-cli -de board.dsn -do board.ses` routes with the board's copper-to-edge clearance. KiCad imports the session as `layout/board.kicad_pcb`. It writes the 2D placement view to `layout/placement.png` and a render of the routed board to `layout/board.png`.
4. `kicad-cli pcb drc` checks design rules, clearance, the board edge, footprints, and unrouted nets on the imported board. The runner also checks each `high_current` net's routed width, allowing narrower copper within 1 mm of its own pads, and each `differential_pair` length skew. DRC errors, unrouted nets, and failed checks fail the board. DRC warnings are reported only.

A failed attempt goes back to the placer, with a new seed and more room between parts that no proximity or group constraint ties together. After four attempts the runner keeps the best attempt and writes `layout/report.json`. Exit 0 is a passing board. Exit 1 sets `return_to: "constraints"` with the reasons, and `/layout` revises `constraints.json` and runs again. Exit 2 means no board: a missing input, an invalid constraint, or a missing tool.

`kicad-schematic` and `kicad-pcb` connect only while KiCad is open with its API server enabled. They inspect and edit the open board. They are not the placer or the router. Part selection copies a KiCad 10 symbol and footprint from the installed libraries. An exact package file is used when it exists. Otherwise the nearest footprint in that part's library is used. Layout does the same if a footprint named in the netlist is not on disk.

## Milestone

Natural-language specification, generated circuit, automated SPICE verification.

`/design` writes the spec, the SKiDL source, the catalog parts, and `parts/board.net`. It repairs the SKiDL until the tests pass.

## Remaining work

Already implemented:

- **Machine.** `./setup.sh`, `.venv`, and Pi. `~/.pi/agent/models.json` uses `http://127.0.0.1:11434/v1` and `nemotron-3-super:latest`. KiCad 10.0.7 is installed with its symbol and footprint libraries. Freerouting 2.5.0 for Linux ARM64 is in `.tools/freerouting`. `.pi/mcp.json` starts `kicad-schematic` and `kicad-pcb` while KiCad is open with the API server enabled.
- **Circuit.** Each request is `designs/<slug>/design/`. The requirements check blocks SKiDL until the spec has measurable numbers. `/design` writes `circuit-spec.json` and `skidl_sim.py` there, then runs `.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>`. `skills/circuit/verify.py` calls `measure()`, writes `simulation-results.json` in that same folder, and on a miss prints the measured value, the target, and whether the result is high or low. A returned number that did not come from ngspice is not a result. `/design` revises `skidl_sim.py` until pytest exits 0. A plain pytest run does not sweep `designs/`. The regulator sentence has passed that loop, and so has one other circuit.
- **Parts.** `/design` runs `skills/parts/choose_ic.py` before the simulation and `skills/parts/lookup.py` after pytest exits 0. The lookup writes `designs/<slug>/parts/parts.json` from the local JLCPCB cache and keeps the IC in `design/ic.json`. `skills/parts/netlist.py` runs `parts/skidl_kicad.py` and writes `parts/board.net`. Stock, price, and footprint names come from the cache and the installed KiCad libraries.
- **Layout.** `/layout` reads `design/` and `parts/`, writes `designs/<slug>/layout/constraints.json`, and runs `skills/layout/layout.py`. The runner places, builds the KiCad board, routes it with Freerouting, imports the session, runs DRC and the routed-width and skew checks, retries the placer, and writes `layout/report.json`. `tests/test_layout.py` covers the constraints, the placer, and an end-to-end LDO board from a SKiDL netlist that places, routes with no unrouted nets, and passes DRC.

Still to build, in pipeline order:

1. **Layout on a real design.** Run `/layout` on the regulator after `/design` writes its `board.net`, and on one more circuit. Record whether the model's constraints are valid on the first try and how many runs it takes to pass.
2. **Manufacturing output.** Gerbers, drill files, BOM, and the position file from `board.kicad_pcb` with `kicad-cli pcb export`, in the shop's format.



## Open questions

- Which constraint types are required, and which can wait?
- When is a constraint hard, and what happens when two hard constraints conflict?
- Constraints name parts and nets. Should they also name functional blocks?
- Does a simple placer get good enough once the constraints are good?
- The runner sends every failure back to the placer up to four times, then to the constraint list. Should some DRC errors, such as a footprint problem, go straight back to `/design` instead?

