# PCBAgent-GX10

Pi package for the PCB agent. Pi itself is installed on the machine. This repo is the agent: skills now, extensions and prompts when you add them.

## Development

Develop on the GX10 over SSH. Edit this checkout there. The GX10 runs Nemotron.

On the GX10, at its own keyboard, print the SSH user, short hostname, and LAN address:

```bash
whoami
hostname
hostname -I
```

`whoami` is the SSH user. `hostname` is the short name. `hostname -I` prints the LAN addresses; the first `192.168.` address is `<gx10-ip>`. From another machine on the LAN:

```bash
ssh <whoami>@<hostname>.local
```

If `.local` does not resolve, use `ssh <whoami>@<gx10-ip>`.

KiCad 9 or newer is installed separately. From this checkout on the GX10:

```bash
./setup.sh
source .venv/bin/activate
```

`requirements.txt` installs SKiDL and the KiCad MCP server into `.venv`. `setup.sh` also installs Pi and `uv` when they are missing, downloads Freerouting 2.5.0 into `.tools/freerouting`, and points the virtualenv at the local KiCad symbol libraries. `.pi/mcp.json` starts the schematic and board MCP servers. KiCad has to be open with its API server enabled before those tools connect.

Confirm the Nemotron id Ollama is serving:

```bash
ollama list
curl -s http://127.0.0.1:11434/v1/models
```

Copy `models.example.json` to `~/.pi/agent/models.json` and set `models[0].id` to that id. `baseUrl` stays `http://127.0.0.1:11434/v1`. Then:

```bash
pi
```

Trust the project when asked. `.pi/settings.json` loads this package. `/model` selects the Ollama model.

## Animated layout demonstration

Demo mode shows components moving into place and copper routes appearing in the **KiCad PCB Editor**.
It presents calculated results; the movement and drawing order illustrate the result rather than
recording the optimizer's actual history. The original board and check report remain the engineering outputs.

Use KiCad 10.0.7 and install the updated `requirements.txt` (or rerun `./setup.sh`). Enable
**Preferences → Plugins → Enable KiCad API** in KiCad. From a graphical desktop terminal on that
machine, after `parts/board.net` and `layout/constraints.json` exist:

```bash
# Generate, record, and automatically play the stage results
.venv/bin/python skills/layout/layout.py designs/<slug> --demo

# Replay the latest recording without running placement or routing again
.venv/bin/python skills/layout/demo.py designs/<slug> --replay

# Play twice as fast
.venv/bin/python skills/layout/demo.py designs/<slug> --replay --speed 2
```

The player opens a separate `demo.kicad_pcb`. Parts start beside the outline, move into place,
then tracks and vias appear. Captions show computation waits, checks, retries, and the selected
attempt's actual pass/fail result. Allow roughly 30 seconds of animation per attempt plus computation
time. Close any KiCad startup dialogs; the player waits up to 30 seconds for the editor's API.
Use KiCad's normal zoom/pan controls if needed. Rerun replay to restart; Ctrl+C stops replay.

Recordings live in `designs/<slug>/layout/demo/<run-id>/`: a versioned `manifest.json`, attempt snapshots,
and exact geometry in integer nanometers. Each playback gets a fresh directory under `playback/`,
preserving previous demos and generated boards. To replay an older run, pass
`--manifest <path/to/manifest.json> --replay` instead of a design directory.

An SSH session without a graphical display still records the run; playback reports that no desktop
is available. Replay from the machine's desktop afterward, or view that desktop remotely. If KiCad
closes or disconnects, generation and recording continue independently. Incomplete recordings are
labelled incomplete. KiCad's API preference is not changed automatically.
Live playback runs independently of the layout command; its progress and any connection errors are
saved in the recording's `playback.log`, whose path is printed when the run starts.

`KICAD_PCBNEW` selects the PCB Editor executable. `KICAD_API_SOCKET` can specify its IPC socket;
otherwise the player discovers local sockets and matches the **full demo document path** before
making changes. Ordinary layout runs without `--demo` need no running editor.

Test recording and playback logic with `.venv/bin/python -m pytest tests/test_demo.py`. To additionally
exercise a real editor and compare the resulting geometry with the source, run from the desktop:

```bash
PCBAGENT_TEST_GUI=1 .venv/bin/python -m pytest tests/test_demo.py -k real_editor -q
```

This opt-in test opens a disposable demo board and leaves it visible for inspection.
