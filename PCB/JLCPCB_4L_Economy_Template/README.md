# JLCPCB 4-Layer Economy — KiCad 9 template

This starter contains:

- `JLCPCB_4L_Economy.kicad_pro`: global Constraints, net class, routing presets and severities.
- `JLCPCB_4L_Economy.kicad_pcb`: empty four-copper-layer board with a nominal stackup.
- `JLCPCB_4L_Economy.kicad_sch`: empty schematic to start a normal KiCad project.
- `JLCPCB_4L_Economy.kicad_dru`: custom fabrication checks, including through-via-only and inner-hole spacing.
- `meta/info.html`: KiCad template-browser description.

## New projects

In KiCad use **File -> New Project from Template**. Browse to the folder that
contains `JLCPCB_4L_Economy`, select this template, and create your new project.
KiCad will rename the KiCad project files automatically.

## Existing projects

Open your existing PCB in PCB Editor and select **File -> Board Setup -> Import
Settings from Another Board...**. Choose this template's
`JLCPCB_4L_Economy.kicad_pcb` and select the settings to import. Importing
overwrites the selected categories in your existing board: make a project
backup first, especially if you already have special net classes/custom rules.

For self-contained settings, keep `.kicad_pro`, `.kicad_pcb`, and `.kicad_dru`
together. Use **Check Rule Syntax** under Board Setup -> Custom Rules after import.

The starter PCB has no board outline: the DRC will report an `invalid_outline`
error until you draw your own closed shape on `Edge.Cuts`.

## Parameters

- FR-4 nominal thickness 1.6mm, four copper layers.
- F.Cu, B.Cu: 1oz; In1.Cu, In2.Cu: 0.5oz.
- DRC absolute copper clearance/track width: 0.15mm.
- DRC via annular minimum: 0.12mm; plated through-hole pad: 0.20mm.
- Fee-safe small via lower bound 0.45/0.20mm; standard routing default 0.60/0.30mm.
- Default net-class clearance 0.20mm and track width 0.25mm.

The substrate thicknesses shown in the PCB editor are **approximations**, not
an impedance-controlled JLCPCB stackup. Do not assume trace impedance from
these numbers; use the manufacturer's final stackup when needed.

KiCad DRC does **not** verify current capacity, solderability, total quote
cost, or all of JLCPCB's CAM/DFM requirements. Verify Gerbers with the fab.

Sources (checked 2026-11-19):
- https://jlcpcb.com/capabilities/pcb-capabilities/
- https://cart.jlcpcb.com/quote
- https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html
