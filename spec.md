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
| `skills/parts` | Real parts, KiCad symbols, footprints. No catalog yet |
| `skills/layout` | Constraints, placement, routing, design-rule checks. No placer or router yet |
| `skills/circuit/verify.py` | Simulation runner: runs `measure()` in `skidl_sim.py`, judges each result, writes `simulation-results.json` |
| `skills/circuit/schemas/` | Circuit spec and one simulation measurement |
| `tests/` | Runner contract and checks on every `designs/<slug>/` |
| `skills/layout/schemas/constraints.schema.json` | Placement constraints |
| `prompts/` | `/design`, `/parts`, `/layout` |
| `requirements.txt`, `setup.sh` | SKiDL 2.3.0, KiCad MCP, Freerouting 2.5.0, Pi, and `uv` |
| `.pi/mcp.json` | `kicad-schematic` and `kicad-pcb` |
| `models.example.json` | Ollama endpoint for Nemotron |

Development is an SSH session on the GX10. Run `./setup.sh` in this checkout there. `source .venv/bin/activate` sets `KICAD9_SYMBOL_DIR` and puts `kicad-cli` on `PATH`. `~/.pi/agent/models.json` uses `baseUrl` `http://127.0.0.1:11434/v1` and the Nemotron id from `ollama list`.

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
3. `/design` runs `.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>`. The test reads that design's `circuit-spec.json` and runs `skills/circuit/verify.py` on it. The runner imports `skidl_sim.py`, calls `measure()`, and compares each measurement with that spec's targets and tolerances. It writes `simulation-results.json` and sets `status`. On a failure it prints the measured value, the target, and whether the measurement is high or low. A failed requirement fails pytest. The runner leaves no results file when the file crashes, `measure()` is missing, a measured field is missing, or the spec has no tolerance for a measured field. Simulator exit alone is not a pass. The model does not judge the numbers. `/design` does not select catalog parts or emit coordinates.

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

The model replaces ideal parts with real ones from a cached JLCPCB catalog. For each part it records the manufacturer part number, value, tolerance, voltage, current, power, package, stock, price, and preferred or basic status, plus a KiCad symbol and footprint. It does not invent stock, price, or footprint names. No catalog is in this package yet.

A second SKiDL file, separate from the simulation file, uses `from skidl import *` and `set_default_tool(KICAD)` and emits the KiCad netlist. `ERC()` runs before `generate_netlist(tool=KICAD)`. A missing footprint aborts that netlist. If a selected part changes a value the spec measures, the circuit stage runs again, with device models that match the selected parts.

### 3. Layout

`/layout` starts this stage, after part selection.

1. The model writes placement constraints that validate against `skills/layout/schemas/constraints.schema.json`: proximity, grouping, edge, keep-out, separation, loop area, high-current paths, differential pairs, and orientation. `weight` is relative importance. `hard` means a violation is illegal. The model does not assign coordinates or draw traces.
2. The placer chooses coordinates. Its cost covers wire length, overlap, constraint violations, board area, and loop area. The first candidate is force-directed initialization, then simulated annealing. No placer is in this package yet.
3. KiCad exports a Specctra `.dsn`. `freerouting-cli -de board.dsn -do board.ses` writes a session, and KiCad imports it. Trace width, clearance, vias, layers, differential pairs, high-current nets, and shop rules still have to be expressed in that design. The Freerouting binary is installed. Nothing in this package calls it yet.
4. Design-rule, electrical-rule, unrouted-net, footprint, clearance, board-edge, and shop checks run on the imported board. A failure goes back to the placer or to the constraint list. No checker is in this package yet.

If a step has no tool, the stage stops and names the file that step would read.

`kicad-schematic` and `kicad-pcb` connect only while KiCad is open with its API server enabled. They inspect and edit the open board. They are not the placer or the router. SKiDL can see the KiCad 9 symbols. It does not yet see a footprint library table. That table is part of part selection, not part of the SPICE milestone.

## Milestone

Natural-language specification, generated circuit, automated SPICE verification.

`/design` writes the spec and the SKiDL source, runs the tests, and repairs the SKiDL until they pass.

## Remaining work

Do these in order. Do not start placement or routing until the milestone holds on more than one circuit.

1. On the GX10, run `./setup.sh`, point `~/.pi/agent/models.json` at `http://127.0.0.1:11434/v1` with the id from `ollama list`, then `source .venv/bin/activate && pi`. Trust the project and send `/design` with the regulator sentence. Read the SKiDL before treating it as success.
2. Done: `skills/circuit/verify.py`. `/design` runs `.venv/bin/python -m pytest tests/test_verify.py --design designs/<slug>` for the design being checked. A plain pytest run does not sweep `designs/`.
3. Repeat the regulator, then one amplifier or filter, and record whether the SKiDL is syntactically valid, electrically valid, connected correctly, and accepted by ngspice.
4. After that loop is reliable: JLCPCB cache and footprint assignment, then the constraint schema against a real netlist, then a small placer and a KiCad export, then Freerouting on the exported `.dsn`, then the design-rule check on the imported `.ses`.

## Open questions

- Which constraint types are required, and which can wait?
- When is a constraint hard, and what happens when two hard constraints conflict?
- Do constraints name parts, nets, functional blocks, or all three?
- Does a simple placer get good enough once the constraints are good?
- Which unrouted or rule-breaking Freerouting results go back to the placer, and which go back to the constraint list?
