# Astra BLDC — Educational KiCad Demo

An original KiCad project inspired by the PCB-layout sequence in the GPT-6 Astra launch demo. The public clip only identifies its board as **BLDC** and does not include design files, a schematic, or a BOM, so this project recreates the concept rather than claiming to be the source board.

## What is included

- Editable native KiCad schematic and two-layer PCB
- Unrouted `astra-bldc-demo-start.kicad_pcb` for a placement/routing playback
- Fixed-placement `astra-bldc-autoroute-input.kicad_pcb` for the DSN/Freerouting/SES test
- 12 V nominal input and approximately 2 A educational target
- STM32G031K8 controller and DRV8313 integrated three-phase driver
- Hall sensor header, speed potentiometer, SWD header, status LED
- Routed phase/power/control nets, top and bottom ground pours, and thermal pad
- Deterministic BOM and a reproducible generator in `tools/generate_project.py`

## Connectors

| Connector | Pins |
| --- | --- |
| J1 POWER IN | 1: +12 V, 2: GND |
| J2 MOTOR | 1: Phase A, 2: Phase B, 3: Phase C |
| J3 HALL | 1: 3V3, 2: GND, 3: Hall A, 4: Hall B, 5: Hall C |
| J4 SWD | 1: 3V3, 2: SWDIO, 3: SWCLK, 4: NRST, 5: GND |

## Architecture

`12 V input → fuse/TVS → DRV8313 → motor phases`

`12 V input → 3.3 V DC/DC → STM32 + Hall/SWD/control`

The MCU is intended to run Hall-sensored six-step commutation. Firmware is outside this PCB demo's scope.

## Open and validate

Open `astra-bldc.kicad_pro` with KiCad 8 or newer, refill zones with **B**, then inspect the schematic and PCB.

For an Astra-style hands-on sequence, open `astra-bldc-demo-start.kicad_pcb` and follow `DEMO.md`. All components are ordinary unlocked KiCad footprints: hover and press **M** to move, **R** to rotate, and **X** to route. The completed `astra-bldc.kicad_pcb` remains available as the reference end state.

For a no-interaction playback on Windows, double-click `run-demo.cmd`. If KiCad is missing, the launcher installs the current stable release with `winget`, enables KiCad's supported IPC API, and opens a disposable playback board. The external controller edits native board objects directly—placing footprints, adding tracks and vias, and filling copper—without controlling the mouse or keyboard.

To reproduce the external-autorouter workflow discussed by NextPCB, double-click `run-autorouter-test.cmd`. It performs `KiCad DSN export → Freerouting → KiCad SES import → DRC` and preserves every intermediate artifact. See `AUTOROUTER_TEST.md`.

The files were successfully parsed by KiCad CLI 10.0.6. The included `astra-bldc-erc.rpt` and `astra-bldc-drc.rpt` intentionally show warnings and violations because this remains a visual demo rather than a fabrication release. After making engineering corrections, rerun:

```powershell
kicad-cli sch erc astra-bldc.kicad_sch -o astra-bldc-erc.rpt
kicad-cli pcb drc astra-bldc.kicad_pcb -o astra-bldc-drc.rpt
```

## Safety and engineering status

**This is a demo design, not a fabrication release. Do not order or energize it without an engineer reviewing the actual DRV8313 and STM32 pin mapping, footprints, power dissipation, protection, creepage, current capacity, firmware fault handling, and component sourcing.** The schematic uses simplified custom symbols to keep the project self-contained. In particular, validate every IC pin against the current manufacturer datasheet and replace the illustrative DC/DC choice as required.
