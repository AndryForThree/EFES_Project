# EFES — System Interconnect

Native KiCad schematic overview, with the three PCBs as *black boxes*.
The original KiCad projects are NOT modified.

## Open

Open `EFES_System_Interconnect.kicad_pro` in **KiCad 10** and then the
schematic editor. The `.kicad_sch` is editable, with actual board pin numbers
(`J8.6` means connector J8, pin 6). This is an assembly/interconnect drawing,
not a fourth PCB project.

## Verification and scope

- Board connector pin numbers were traced from the supplied KiCad 10 schematic
  symbol and wire geometry, including its hierarchy.
- CAN_H/CAN_L and SPI CLK/MOSI/MISO are paired by matching source net labels.
- Human `SENSOR_SPI_nCS` vs Sensor `SENSOR_SPI_CS` are assumed the same CS
  signal, but this name difference needs approval.
- Human `J8.8` is wired to `J10.1`; `J10.2` is 5 V. A fitted external
  link/short at **J10** is needed to supply 5 V to Sensor `J7.4`.
- Human-side J3/J4/J5/J6 are **two-pin breakouts** in series with the
  sensor SPI interface. Bridge J3 (nCS), J4 (CLK), J5 (MOSI) and J6 (MISO),
  pins 1-2, to establish the signal paths represented in the system view.
  Without those bridges, the MCU-side nets and the J8 harness pins are
  not connected. J7 is the analogous two-pin breakout for sensor nFault.
- Human `J8.9` is `SENSOR_nFault`, but Sensor `J7` does not expose it.
  It is deliberately *not connected* in the overview.
- Human `J8.2` is `nRST` and Road `J3` has no nRST counterpart. We do not
  connect it to the Road debug header `J4` without permission.
- Road `J3.7` is `ADC_MotorPosition`; its external destination is unknown.
- Road `J3.2` supplies 3V3 and `J3.4` is `INTERLOCK_END`. The representation
  shows an external two-terminal loop interface only. It does **not** specify
  which switch or whether/how many contacts are in series.
- Road motor-driver sheet has `J27.1` = `INTERLOCK_END` and `J27.2` =
  interlock sense input. Endstop interface contact type requires approval.
- Common 12 V/GND banana distribution to Human `J1` and Road `J1` is a
  **proposed harness**, not confirmed by a physical cable drawing. Confirm
  fuse placement, protection, voltage drop, and return current.
- Sensor additional GND pins `J7.8` and `J7.9` are shown as contact stubs;
  the actual number of ground conductors remains a harness design choice.
- Sensor `J7.6` 3V3 is a local board rail; do not wire it to another 3V3
  source without checking both regulators.
- Unused programming connectors and temporary test headers are intentionally
  omitted. All principal external interfaces are shown.

The source projects include a few outdated connector *Value* strings
(for example Road J1 says Conn_01x05 but has a 2-pin symbol and 2-pin
footprint). We used the actual symbol and footprint pin count, not that text.

## Cable colors

| Wire | AWG | Part number | Available | Intended service |
| --- | --- | --- | --- | --- |
| Black | 20 | C2040ABHR-06-HUA.48.01 | 3 m | 12 V return / motor - |
| Red | 20 | C2040A.48.03 | 3 m | 12 V feed / motor + |
| Black | 24 | C2100A.48.01 | 4 m | signal GND / speaker - |
| Red | 24 | C2015A.48.03 | 4 m | 5 V feed / speaker + |
| Blue | 24 | C2015A.48.07 | 4 m | CAN_H |
| Green | 24 | C2015A.48.06 | 4 m | CAN_L |
| Purple | 24 | C2015A.48.19 | 15 m | SPI / general signals |
| Yellow | 24 | C2015A.48.05 | 8 m | Interlock |

The lengths above are purchased stock, not the length of each harness run.
The AWG and colors follow the supplied inventory. The assignment of
red/black to speaker wires is a reasonable proposal; verify current and
cable lengths before building. `EFES_Wiring_Schedule.csv` lists the complete
traceable interface mapping and its confidence state.

## Notes

KiCad electrical wire colors are informational here, **not a guarantee of
harness correctness**. The external interlock boxes are passive two-terminal
interfaces and are intentionally not internally shorted. This is a draft for
pinout and system wiring review; do not manufacture cable assemblies from it
until the open items above are resolved.
