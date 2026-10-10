---
name: circuit
description: Turn a natural-language circuit request into a structured spec, SKiDL, and ngspice checks. Use for the first milestone, before parts or layout.
---

# Circuit

Read `schemas/circuit-spec.schema.json` and write a spec that validates against it. Load the `skidl` skill and write the simulation file it describes. Do not hand-write a SPICE deck or a KiCad netlist.

Then define tests against the spec. Each measured requirement uses `schemas/simulation-result.schema.json`. Compare measured values to the spec. Do not relax a requirement to make a failure pass.

Repair loop: failed checks come back as that JSON, the SKiDL changes, and the same tests run again.

There is no SKiDL or ngspice runner in this package yet. Produce the spec, the SKiDL source, and the test list, and say that simulation still has to be run outside the agent.
