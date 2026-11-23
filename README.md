# EFES_Project
Final Project for "Electronics for Embedded Systems" course of PoliTO 2026-2027. Automotive Steering System 


## File versionati e rigenerazione

Le regole sono commentate in `.gitignore`, `Firmware/.gitignore` e nel
`.gitignore` del firmware HumanSide.

- **KiCad:** schemi, PCB, progetti, regole e librerie (inclusi i modelli 3D).
  History locali, backup, lock, preferenze `.kicad_prl`, PDF e Gerber sono esclusi.
- **FreeCAD:** macro, script, JSON e documenti `.FCStd`; STEP/STL in `CAD/`
  e anteprime generate sono esclusi. Rigenerarli eseguendo le macro FreeCAD.
  I modelli in `PCB/CustomLibs/3D/` sono invece dipendenze del progetto KiCad.
- **Quartus/ModelSim:** HDL, testbench, script, `.qpf`, `.qsf`, IP e vincoli;
  database, prodotti di compilazione e simulazione sono esclusi.
- **STM32CubeMX/CMake:** `.ioc`, codice custom e configurazioni manuali;
  SDK, scaffolding rigenerabile e prodotti di build sono esclusi.
  Per HumanSide seguire `Firmware/EFES_FW_HumanSide/README.md`.
  Prima di compilare rigenerare anche font e asset con
  `python3 generate_font.py` in `Firmware/Scripts/FontGeneration/` e
  `python3 generate_assets.py` in `Firmware/Scripts/SymbolsGeneration/`.
- **Python:** sorgenti, test, configurazioni e dipendenze; ambienti virtuali,
  cache e prodotti di packaging sono esclusi.
- **LaTeX:** `.tex`, bibliografie e figure; file intermedi e PDF compilati
  dei report sono esclusi. Datasheet, riferimenti e allegati restano versionati.

I file ignorati restano disponibili sul disco ma non entrano nei commit.
