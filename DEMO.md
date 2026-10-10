# 15-second KiCad demo choreography

This sequence evokes the Astra PCB clip without reusing its board, footage, branding, or exact layout. Use the native `astra-bldc-demo-start.kicad_pcb` in KiCad's PCB Editor.

## Autonomous playback

1. Close unrelated dialogs and save other work.
2. Double-click `run-demo.cmd`.

No interaction is required after launch. If needed, the launcher installs KiCad through Windows Package Manager and the official `kicad-python` bindings first. It creates `astra-bldc-playback.kicad_pcb`, opens that board, and connects through KiCad's supported IPC API. The controller moves native footprints and progressively adds tracks and vias before filling the ground zones and saving the result. No screen coordinates or simulated input are used.

The console reports the current phase (`placement`, `routing`, `copper-fill`, or `complete`).

## Controls

- Pan: middle-mouse drag; zoom: mouse wheel
- Move the footprint under the cursor: **M**, move mouse, left-click
- Rotate the footprint under the cursor: **R**
- Start routing from a pad or ratsnest: **X**
- Place a via while routing: **V**
- Finish a route: **K** or double-click; cancel: **Esc**
- Refill the copper zones: **B**
- Toggle ratsnest: toolbar “Show board ratsnest”

## Suggested capture

1. **0–3 s — Placement:** box-select the controller cluster, then use **M**. Individually nudge U2, U3, J1, and J2; use **R** once on a connector.
2. **3–11 s — Routing:** hover a bright ratsnest endpoint and press **X**. Route PWM/control lines first, then the wider VBUS and motor-phase connections. Press **V** on one control route to change layers.
3. **11–13 s — Copper:** press **B** to refill the top and bottom GND zones.
4. **13–15 s — Reveal:** zoom to fit with **Home**, hide the ratsnest, then open the 3D Viewer with **Alt+3** if available.

The supplied completed board is a reference rather than a locked result. Its footprints, tracks, vias, text, and zones can all be selected and edited with normal KiCad mouse and keyboard operations.
