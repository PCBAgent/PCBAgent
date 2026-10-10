# Freerouting orchestration test

This reproduces the workflow described in [NextPCB's GPT-6 Astra routing test](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test) on the educational BLDC board:

`KiCad fixed placement → Specctra DSN export → Freerouting → SES import → KiCad DRC`

## Run it

Double-click `run-autorouter-test.cmd`. The first run installs Java 25 and downloads Freerouting 2.5.0 if needed. Routing takes roughly one to two minutes on this machine and finishes by opening the imported board in KiCad.

## Preserved evidence

- `astra-bldc-autoroute-input.kicad_pcb`: fixed-placement, unrouted input
- `astra-bldc-autoroute-input.dsn`: KiCad's Specctra interchange export
- `astra-bldc-freerouted.ses`: Freerouting's routing session
- `astra-bldc-freerouted.kicad_pcb`: SES imported back into KiCad
- `astra-bldc-freerouting.log`: complete router execution history and score
- `astra-bldc-freerouted-drc.rpt`: independent KiCad DRC report

## Baseline result

Freerouting 2.5.0 started with 47 unrouted connections and completed 29, leaving 18 unrouted. It reported 32 pre-existing placement/footprint clearance violations and a score of 641.24 after approximately 67.2 seconds. KiCad's post-import DRC reported 142 violations and 42 unconnected items.

That is a valid hackathon result, not a fabrication-ready result. It demonstrates the same important distinction highlighted by NextPCB: the automation orchestrates the EDA workflow, while Freerouting performs the routing computation. Connecting some or all nets would still not establish electrical correctness, thermal adequacy, signal integrity, or manufacturability.
