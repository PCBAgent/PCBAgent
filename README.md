# PCBAgent-GX10

PCBAgent takes one circuit request and, with no further input, designs a private board on the ASUS Ascent GX10: simulated, sourced, and routed offline.

A schematic is the product. Part values, pinouts, and the board outline should not have to leave the machine before software can help. PCBAgent runs that work on the GX10, an ultra-small AI computer with the NVIDIA GB10 Grace Blackwell Superchip and 128 GB of unified memory. Nemotron, ngspice, a local JLCPCB catalog, KiCad, and Freerouting all run on the box. Unplugging the network does not stop a design.

## Why local

Cloud schematic tools upload the design before they answer. Here the model and the checkers share the machine where the design is created. There is no cloud round trip, no vendor API for the netlist, and no infrastructure to keep up for a single board. The same flow still runs with the network disconnected.

## What it does

One request moves through four checks. The model writes engineering intent. Deterministic tools decide whether it is true.

1. **Specify and simulate.** `/design` writes a circuit spec and a SKiDL simulation, then runs it in ngspice. A measured value counts only when it came from the simulation.
2. **Select parts.** Passives and the regulator are matched to a local JLCPCB catalog. Stock, price, and footprint names are copied from that cache and from the installed KiCad libraries.
3. **Netlist.** The same connections become a KiCad netlist with real symbols and footprints.
4. **Place and route.** The model writes placement constraints, such as a capacitor next to its IC. It does not emit coordinates or traces. A placer chooses positions, Freerouting draws the copper, and KiCad's design-rule check scores the board.

After that first request, the agent keeps going. A failed check is reported and repaired in the same session. The run stops when you cancel it.

## Demo

Two finished boards are in `designs/`:

- `5v-to-3v3-divider`, a 5 V to 3.3 V divider into a 33 ohm load
- `5v-to-3v3-ldo-10uf-22uf-33ohm-25x20mm-jlcpcb`, the same request on an AMS1117-3.3 with 10 µF in and 22 µF out

Replay the routed board in the KiCad PCB Editor from the GX10 desktop. Enable **Preferences → Plugins → Enable KiCad API** first.

```bash
source .venv/bin/activate
.venv/bin/python skills/layout/demo.py designs/5v-to-3v3-ldo-10uf-22uf-33ohm-25x20mm-jlcpcb --replay
```

Parts move into place, then the copper appears. `layout/board.png` in the same design is the still image of the routed board. To record a new animation while laying out again, run `skills/layout/layout.py designs/<slug> --demo`.

A new design starts in Pi with a single command, for example:

```text
/design 5 V supply to 3.3 V LDO using one linear regulator IC, a 10 µF input capacitor, and a 22 µF output capacitor, output voltage 3.3 V within 0.05 V, output current 0.1 A within 0.01 A into a 33 ohm load, maximum board size 25 mm by 20 mm, JLCPCB
```

## Run it on the GX10

KiCad 9 or newer is installed separately. From this checkout:

```bash
./setup.sh
source .venv/bin/activate
ollama list
```

`setup.sh` installs Pi and `uv` when they are missing, installs SKiDL into `.venv`, and downloads Freerouting 2.5.0. Use an exact model id from `ollama list`. Start the Ollama bridge in one terminal:

```bash
export PCB_OLLAMA_MODEL=<id from ollama list>
.venv/bin/python tools/ollama_bridge.py
```

In another terminal, from this checkout:

```bash
export PCB_OLLAMA_MODEL=<id from ollama list>
pi --provider pcb-ollama --model "$PCB_OLLAMA_MODEL" --thinking off
```

Trust the project when asked. `.pi/settings.json` loads this package. Restart Pi after pulling extension changes, or run `/reload` in a session that is already open. Stop a run yourself with Escape in Pi, or Ctrl+C in a CLI process.

From another machine on the LAN, the GX10 is reached with `ssh <user>@<hostname>.local`, or `ssh <user>@<gx10-ip>` if `.local` does not resolve. At the GX10 keyboard, `whoami`, `hostname`, and `hostname -I` print those values.

## Checks

```bash
.venv/bin/python -m pytest tests -q
node --test tests/test_policy.mjs
```

Stage commands, when you want to run them without the agent:

```bash
.venv/bin/python tools/pcb_stage.py designs/<slug> prepare
.venv/bin/python tools/pcb_stage.py designs/<slug> verify
.venv/bin/python tools/pcb_stage.py designs/<slug> parts
.venv/bin/python tools/pcb_stage.py designs/<slug> netlist
.venv/bin/python skills/layout/layout.py designs/<slug>
```

Each stage prints a short JSON result and writes a full log. Simulation evidence, part ratings, and the netlist report stay next to the design. A passing check covers the measurements and rules the runners implement.
