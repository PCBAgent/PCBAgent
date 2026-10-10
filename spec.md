# PCBAgent

PCBAgent turns a natural-language circuit request into a SPICE-verified, real-parts-selected, placed, and routed board. The model does engineering reasoning. Deterministic tools simulate, check, place, route, and enforce design rules. The model does not emit board coordinates or traces.

The project was first proposed as OfflineOhm. Running the whole flow on a local model, so a confidential design never leaves the machine, is still a goal. The work now is to prove the pipeline. The ASUS Ascent GX10, with Nemotron already installed, is the local model machine. This laptop is where the agent package is edited.

## Repository

This repo is a Pi package. Pi itself is installed on each machine. Do not copy the Pi monorepo into this repo.

| Path | Role |
|---|---|
| `skills/pcb-agent` | Stage order and the rule that later stages wait until asked |
| `skills/circuit` | Spec, SKiDL simulation file, ngspice repair loop |
| `skills/skidl` | How to write SKiDL. Simulation files use `skidl.pyspice`. A KiCad netlist is a separate file |
| `skills/parts` | Real parts, KiCad symbols, footprints. No catalog yet |
| `skills/layout` | Constraints, placement, routing, design-rule checks. No placer or router yet |
| `skills/circuit/schemas/` | Circuit spec and one simulation measurement |
| `skills/layout/schemas/constraints.schema.json` | Placement constraints |
| `prompts/design.md`, `prompts/verify.md` | `/design` and `/verify` |
| `requirements.txt`, `setup.sh` | SKiDL 2.3.0, KiCad MCP, Freerouting 2.5.0, Pi, and `uv` |
| `.pi/mcp.json` | `kicad-schematic` and `kicad-pcb` |
| `models.example.json` | Ollama endpoint for Nemotron |

On this laptop, `./setup.sh` has been run. Pi 1.1.0, SKiDL, ngspice 45.2, KiCad 9.0.2, and the KiCad MCP server are installed. `source .venv/bin/activate` sets `KICAD9_SYMBOL_DIR` and puts `kicad-cli` on `PATH`.

## Division of work

| Task | Model | Tool |
|---|---|---|
| Interpret the specification | yes | |
| Choose the circuit architecture | yes | |
| Write SKiDL | yes | |
| Write layout constraints | yes | |
| Pick candidate parts | yes | |
| Run ngspice | | yes |
| Judge the measurement against the spec | | yes |
| Place parts | | yes |
| Check geometry | | yes |
| Route | | yes |
| Design-rule check | | yes |

A simulation failure comes back as JSON, not as raw simulator text:

```json
{
  "requirement": "output_voltage",
  "target": 3.3,
  "measured": 2.74,
  "tolerance": 0.05,
  "status": "fail"
}
```

The repair changes the SKiDL. It does not change the requirement to hide a failure.

## Pipeline

1. **Specification to circuit.** Natural language becomes `circuit-spec.schema.json`, then a `skidl.pyspice` file. Inputs include supply and output voltage, gain, bandwidth, current, load, interfaces, preferred parts, package limits, board size, and manufacturing constraints.
2. **Verification.** ngspice measures the spec. Failures re-enter step 1.
3. **Real parts.** A passing circuit maps to a cached JLCPCB catalog: manufacturer part number, value, tolerance, voltage, current, power, package, stock, price, and preferred or basic status, plus a KiCad symbol and footprint.
4. **Constraints.** The model writes proximity, grouping, edge, keep-out, separation, loop-area, high-current, differential-pair, and orientation constraints. Weight is relative importance. `hard` means a violation is illegal.
5. **Placement.** A cost over wire length, overlap, constraint violations, board area, and loop area chooses coordinates. First candidate is force-directed initialization, then simulated annealing.
6. **Routing.** Freerouting 2.5.0 is the autorouter. KiCad exports a Specctra `.dsn`. `freerouting-cli -de board.dsn -do board.ses` writes a session, and KiCad imports it. Trace width, clearance, vias, layers, differential pairs, high-current nets, and shop rules still have to be expressed in that design. The board opens in KiCad.
7. **Board checks.** Design rules, electrical rules, unrouted nets, footprints, clearance, board edge, and shop constraints. Failures go back to the placer or the constraint list.

Hackathon demonstrations stay inside a small family: op-amp amplifiers, voltage regulators, sensor interfaces, analog filters, and simple microcontroller peripherals. The example request is a 5 V to 3.3 V switching regulator, at least 2 A, small board, JLCPCB parts. The long-term request is a compact USB environmental sensor (temperature, humidity, pressure) on I2C.

## Milestone

Natural-language specification, generated circuit, automated SPICE verification.

`/design` stops after the spec, the SKiDL source, and the test list. `/verify` applies the simulation-result JSON. Neither command runs ngspice yet.

## Remaining work

Do these in order. Do not start placement or routing until the milestone holds on more than one circuit.

1. Give this laptop a model. Copy `models.example.json` to `~/.pi/agent/models.json` and point it at the GX10 Ollama URL, or run `/login` for a hosted provider. Set the model id from `ollama list`.
2. Run `source .venv/bin/activate && pi` in this checkout, trust the project, and send `/design` with the regulator sentence. Read the SKiDL before treating it as success.
3. Add a runner the `circuit` skill can call. It runs the pyspice file under `.venv/bin/python`, calls ngspice, and writes an array of simulation-result objects. `/verify` reads that file.
4. Repeat the regulator, then one amplifier or filter, and record whether the SKiDL is syntactically valid, electrically valid, connected correctly, and accepted by ngspice.
5. Push this repo and clone it on the GX10. Run `./setup.sh` there, point `models.json` at `http://127.0.0.1:11434/v1`, and repeat one `/design` against Nemotron.
6. After that loop is reliable: JLCPCB cache and footprint assignment, then the constraint schema against a real netlist, then a small placer and a KiCad export, then Freerouting on the exported `.dsn`, then the design-rule check on the imported `.ses`.

KiCad's MCP servers connect only while KiCad is open with its API server enabled. SKiDL can see the KiCad 9 symbols. It does not yet see a footprint library table. That table is part of part selection, not part of the SPICE milestone.

## Open questions

- Which constraint types are required, and which can wait?
- When is a constraint hard, and what happens when two hard constraints conflict?
- Do constraints name parts, nets, functional blocks, or all three?
- Does a simple placer get good enough once the constraints are good?
- Which unrouted or rule-breaking Freerouting results go back to the placer, and which go back to the constraint list?
