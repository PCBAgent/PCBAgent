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
