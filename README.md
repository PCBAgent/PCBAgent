# PCBAgent-GX10

Pi package for the PCB agent. Pi itself is installed on the machine. This repo is the agent: skills now, extensions and prompts when you add them.

## GX10 (after development and PCBAgent-GX10 is setup on machine)

Install Pi once (Node 22.19 or newer; the installer can provide it):

```bash
curl -fsSL https://pi.dev/install.sh | sh
```

Confirm the Nemotron id Ollama is serving:

```bash
ollama list
curl -s http://127.0.0.1:11434/v1/models
```

Copy `models.example.json` to `~/.pi/agent/models.json` and set `models[0].id` to that id. Then, in this checkout:

```bash
pi
```

Trust the project when asked. `.pi/settings.json` loads this package. `/model` selects the Ollama model.

## Development

Edit this repo on the laptop. The GX10 runs Nemotron. This machine does not need that hardware.

KiCad 9 or newer is installed separately. From this checkout:

```bash
./setup.sh
source .venv/bin/activate
```

`requirements.txt` installs SKiDL and the KiCad MCP server into `.venv`. `setup.sh` also installs Pi and `uv` when they are missing, downloads Freerouting 2.5.0 into `.tools/freerouting`, and points the virtualenv at the local KiCad symbol libraries. `.pi/mcp.json` starts the schematic and board MCP servers. KiCad has to be open with its API server enabled before those tools connect.

On the GX10, at its own keyboard, print the three values the laptop needs:

```bash
whoami
hostname
hostname -I
```

`whoami` is the SSH user. `hostname` is the short name. `hostname -I` prints the LAN addresses; the first `192.168.` address is `<gx10-ip>`. From the laptop:

```bash
ssh <whoami>@<hostname>.local
```

If `.local` does not resolve, use `ssh <whoami>@<gx10-ip>`.

On the GX10, find the model id and let other machines reach Ollama:

```bash
ollama list
curl -s http://127.0.0.1:11434/v1/models
OLLAMA_HOST=0.0.0.0 ollama serve
```

From the laptop, `curl http://<gx10-ip>:11434/v1/models` should return that same id. Copy `models.example.json` to `~/.pi/agent/models.json`, set `baseUrl` to `http://<gx10-ip>:11434/v1`, and set `models[0].id` to that id. Then:

```bash
pi
```

Trust the project when asked. Pi on the laptop sends each model request to the GX10. Its tools still edit files on the laptop.

Push the repo when a change should run on the GX10. `ssh <whoami>@<hostname>.local`, `git pull`, and run `pi` there with `baseUrl` set to `http://127.0.0.1:11434/v1`. That session edits files on the GX10.
