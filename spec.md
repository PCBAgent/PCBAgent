# PCBAgent

PCBAgent turns a natural-language circuit request into a SPICE-verified, real-parts-selected, placed, and routed board. The model does engineering reasoning. Deterministic tools simulate, check, place, route, and enforce design rules. The model does not emit board coordinates or traces.

The project was first proposed as OfflineOhm. Running the whole flow on a local model, so a confidential design never leaves the machine, is still a goal. The work now is to prove the pipeline on the ASUS Ascent GX10, over SSH. Nemotron is already installed there. There is no separate laptop workflow yet.

## Repository

This repo is a Pi package. Pi itself is installed on the GX10. Do not copy the Pi monorepo into this repo.

| Path | Role |
|---|---|
| `skills/pcb-agent` | Stage order and the rule that later stages wait until asked |
| `skills/circuit` | Spec, SKiDL simulation file, ngspice repair loop |
| `skills/skidl` | How to write SKiDL. Simulation files use `skidl.pyspice`. A KiCad netlist is a separate file |
| `skills/parts` | Local JLCPCB cache, lookup, and KiCad netlist runner |
| `skills/layout` | Constraints, placement, routing, design-rule checks. No placer or router yet |
| `skills/circuit/verify.py` | Simulation runner: runs `measure()` in `skidl_sim.py`, judges each result, writes `simulation-results.json` |
| `skills/circuit/schemas/` | Circuit spec and one simulation measurement |
| `tests/` | Runner contract. A design is checked with `pytest --design designs/<slug>` |
| `skills/layout/schemas/constraints.schema.json` | Placement constraints |
| `prompts/` | `/design`, `/parts`, `/layout` |
| `requirements.txt`, `setup.sh` | SKiDL 2.3.0, KiCad MCP, Freerouting 2.5.0, Pi, and `uv` |
| `.pi/mcp.json` | `kicad-schematic` and `kicad-pcb` |
| `models.example.json` | Ollama endpoint for Nemotron |

Development is an SSH session on the GX10. Run `./setup.sh` in this checkout there. `source .venv/bin/activate` sets `KICAD_SYMBOL_DIR` from the installed KiCad and puts `kicad-cli` on `PATH`. `~/.pi/agent/models.json` uses `baseUrl` `http://127.0.0.1:11434/v1` and the Nemotron id from `ollama list`.

## Design flow

A design starts from a natural-language request in `pi` on the GX10. Three stages run in order. A later stage starts when the user runs its command, and only after the previous stage has passed. The model writes engineering intent. Tools simulate, judge, place, route, and check. The model does not emit board coordinates or traces, and it does not claim a tool ran when this package has no runner for it.

Hackathon demonstrations stay inside a small family: op-amp amplifiers, voltage regulators, sensor interfaces, analog filters, and simple microcontroller peripherals. The long-term request is a compact USB environmental sensor (temperature, humidity, pressure) on I2C.

### Example

```text
/design 5 V to 3.3 V switching regulator, output 3.3 V within 0.05 V, at least 2 A within 0.1 A into a 1.65 ohm load, maximum board size 25 mm by 20 mm, JLCPCB
```

`/design` writes the SKiDL, runs the tests against that design's `circuit-spec.json`, and revises the SKiDL when a measurement misses. Then:

```text
/parts
/layout
```

`/design` does not select the JLCPCB parts named in that sentence. `/parts` does, after the circuit passes. `/layout` writes constraints, then stops at the first missing tool.

### 1. Circuit

`/design` takes the request.

1. The model writes a circuit spec that validates against `skills/circuit/schemas/circuit-spec.schema.json`. The spec keeps the original prompt and the acceptance numbers: supply and output voltage, gain, bandwidth, current, load, interfaces, preferred parts, package limits, board size, and manufacturing constraints. The `requirements` skill checks that spec. If a required value is missing, `/design` asks the user and does not write SKiDL until the user answers.
2. The model chooses the architecture and writes one SKiDL simulation file, using `from skidl.pyspice import *`. It does not hand-write a SPICE deck.
3. `/design` runs `.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>`. The test reads `designs/<slug>/design/circuit-spec.json` and runs `skills/circuit/verify.py` on that directory. The runner imports `design/skidl_sim.py`, calls `measure()`, and compares each measurement with that spec's targets and tolerances. It writes `design/simulation-results.json` and sets `status`. On a failure it prints the measured value, the target, and whether the measurement is high or low. A failed requirement fails pytest. The runner leaves no results file when the file crashes, `measure()` is missing, a measured field is missing, the spec has no tolerance for a measured field, or a returned number did not come from ngspice. A function that returns the spec targets is not a pass. The model does not judge the numbers. `/design` does not select catalog parts or emit coordinates.

```json
{
  "requirement": "output_voltage_v",
  "target": 3.3,
  "measured": 2.74,
  "tolerance": 0.05,
  "status": "fail"
}
```

A failure stays inside `/design`. The model reads why the measurement missed and changes the SKiDL so the same tests pass. It does not change the spec to hide a failure. `/design` repeats the tests until pytest exits 0. That ends the circuit stage. A SPICE pass does not establish footprint mapping, placement, or routing.

### 2. Parts

`/parts` starts this stage, from a circuit with passing simulation results.

`/parts` reads `designs/<slug>/design/` and writes `designs/<slug>/parts/`. It searches the local JLCPCB cache, `.tools/jlcpcb/economic-parts.csv`, with the spec and the simulated parts. The cache is basic and preferred parts downloaded once by `skills/parts/fetch_catalog.py`. A lookup does not use the network. `parts/parts.json` records the manufacturer part number, value, tolerance, voltage, current, power, package, stock, price, and basic or preferred status, plus a KiCad symbol and footprint copied from that cache and the installed KiCad 10 libraries. It does not invent stock, price, or footprint names.

`parts/skidl_kicad.py` uses `from skidl import *` and `set_default_tool(KICAD)`. `skills/parts/netlist.py` runs `ERC()` and writes `parts/board.net`. A missing footprint aborts that netlist. If a selected part changes a value the spec measures, the circuit stage runs again, with device models that match the selected parts.

### 3. Layout

`/layout` starts this stage, after part selection. It reads `designs/<slug>/design/` and `designs/<slug>/parts/`, and writes `designs/<slug>/layout/`.

1. The model writes placement constraints that validate against `skills/layout/schemas/constraints.schema.json`: proximity, grouping, edge, keep-out, separation, loop area, high-current paths, differential pairs, and orientation. `weight` is relative importance. `hard` means a violation is illegal. The model does not assign coordinates or draw traces.
2. The placer chooses coordinates. Its cost covers wire length, overlap, constraint violations, board area, and loop area. The first candidate is force-directed initialization, then simulated annealing. No placer is in this package yet.
3. KiCad exports a Specctra `.dsn`. `freerouting-cli -de board.dsn -do board.ses` writes a session, and KiCad imports it. Trace width, clearance, vias, layers, differential pairs, high-current nets, and shop rules still have to be expressed in that design. The Freerouting binary is installed. Nothing in this package calls it yet.
4. Design-rule, electrical-rule, unrouted-net, footprint, clearance, board-edge, and shop checks run on the imported board. A failure goes back to the placer or to the constraint list. No checker is in this package yet.

If a step has no tool, the stage stops and names the file that step would read.

`kicad-schematic` and `kicad-pcb` connect only while KiCad is open with its API server enabled. They inspect and edit the open board. They are not the placer or the router. Part selection copies a KiCad 10 symbol and footprint from the installed libraries when the catalog package matches a footprint file.

## Milestone

Natural-language specification, generated circuit, automated SPICE verification.

`/design` writes the spec and the SKiDL source, runs the tests, and repairs the SKiDL until they pass.

## Remaining work

Already implemented:

- **Machine.** `./setup.sh`, `.venv`, and Pi. `~/.pi/agent/models.json` uses `http://127.0.0.1:11434/v1` and `nemotron-3-super:latest`. KiCad 10.0.7 is installed with its symbol and footprint libraries. Freerouting 2.5.0 for Linux ARM64 is in `.tools/freerouting`. `.pi/mcp.json` starts `kicad-schematic` and `kicad-pcb` while KiCad is open with the API server enabled.
- **Circuit.** Each request is `designs/<slug>/design/`. The requirements check blocks SKiDL until the spec has measurable numbers. `/design` writes `circuit-spec.json` and `skidl_sim.py` there, then runs `.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>`. `skills/circuit/verify.py` calls `measure()`, writes `simulation-results.json` in that same folder, and on a miss prints the measured value, the target, and whether the result is high or low. A returned number that did not come from ngspice is not a result. `/design` revises `skidl_sim.py` until pytest exits 0. A plain pytest run does not sweep `designs/`. The regulator sentence has passed that loop, and so has one other circuit.
- **Parts.** `/parts` reads `designs/<slug>/design/` and writes `designs/<slug>/parts/parts.json` from the local JLCPCB cache. `skills/parts/netlist.py` runs `parts/skidl_kicad.py` and writes `parts/board.net`. Stock, price, and footprint names come from the cache and the installed KiCad libraries.
- **Layout.** `/layout` reads `design/` and `parts/`. It writes `designs/<slug>/layout/constraints.json` against `skills/layout/schemas/constraints.schema.json`. The schema covers proximity, grouping, edge, keep-out, separation, loop area, and the other placement rules. `/layout` stops when the next tool is missing.

Still to build, in pipeline order:

1. **Layout.** Add a placer that reads `designs/<slug>/layout/constraints.json` and `designs/<slug>/parts/board.net` and assigns coordinates. Its cost covers wire length, overlap, constraint violations, board area, and loop area, from a force-directed start and then simulated annealing. Export a Specctra `.dsn`, run `freerouting-cli -de board.dsn -do board.ses`, and import the session. Then check design rules, electrical rules, unrouted nets, footprints, clearance, and the board edge. A failure goes back to the placer or to the constraint list.

## Open questions

- Which constraint types are required, and which can wait?
- When is a constraint hard, and what happens when two hard constraints conflict?
- Do constraints name parts, nets, functional blocks, or all three?
- Does a simple placer get good enough once the constraints are good?
- Which unrouted or rule-breaking Freerouting results go back to the placer, and which go back to the constraint list?
