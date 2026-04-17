---
phase: 20-physical-integration
plan: 01
status: complete
started: 2026-04-17
completed: 2026-04-17
commits:
  - 3b49bac
---

# Plan 20-01 Summary: Pi 5 Stack Enclosure

## What was built

`hardware/pi-case.scad` — parametric OpenSCAD design for a 3D-printed PETG enclosure housing
the full Pi 5 stack (NVMe HAT, Pi 5, active cooler, double-height GPIO extension, perma-proto).

## Key features

- Tray + lid design (matches sensor-cluster.scad conventions)
- 40mm Noctua NF-A4x10 fan mount on left wall with exhaust vents on opposite wall
- GX12 3-pin aviation connector cutout for sensor loom (rear wall)
- SMA bulkhead pass-through for GPS antenna (rear wall)
- Sized cable exit slots: HDMI (x2), USB-A stack, USB-C power, Qwiic, 1-Wire
- M2.5 rubber standoff through-holes for vibration-isolated Pi mounting (per D-03)
- M4 mounting flanges for plywood electronics panel
- Lid with ventilation slots above cooler area and M2.5 screw-down retention

## Measurements used

- Total stack height: 65mm (measured 2026-04-17)
- NVMe HAT height: 20mm (measured 2026-04-17)
- Pi 5 board: 85 x 56mm, mounting holes 58 x 49mm spacing (RPi mechanical drawing)
- Connector positions derived from RPi mechanical drawing

## Notes

- Fan not yet purchased — design uses parametric `FAN_W = 40` for easy change
- STL export not verified (OpenSCAD requires Rosetta on Apple Silicon, not installed)
- Visual verification in OpenSCAD GUI pending

## Deviations

- Skipped individual sub-component height measurements (HAT standoff, cooler, GPIO extension)
  as only the total stack height matters for case interior sizing
- Connector positions from mechanical drawing rather than caliper measurement — sufficient
  accuracy for cable exit slots which have generous clearance
