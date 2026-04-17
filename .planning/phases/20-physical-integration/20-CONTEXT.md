# Phase 20: Physical Integration - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Move v2 hardware from bench pile to install-ready in the car. 3D-printed enclosures for
the main Pi board and screen, camera bracket, proper cable routing, and mounting everything
to survive thousands of kilometres of corrugated roads without anything flapping loose.

This phase is physical integration only — no software changes, no new features.

</domain>

<decisions>
## Implementation Decisions

### Pi Enclosure

- **D-01:** 3D-printed PETG case designed in OpenSCAD (consistent with existing `hardware/sensor-cluster.scad`)
- **D-02:** Case mounts to existing plywood electronics panel via screws. Panel is bolted permanently into the car (behind/between front seats)
- **D-03:** M2.5 rubber standoffs between Pi and case for vibration damping
- **D-04:** 30mm Noctua NF-A4 fan mount integrated into case design, with ventilation slots
- **D-05:** 1x GX12 (3-pin) aviation connector panel-mount cutout in case wall for external sensor loom
- **D-06:** SMA bulkhead pass-through for GPS antenna cable
- **D-07:** Cable exits for HDMI, USB (cameras, screen touch, keyboard), 1-Wire (DS18B20), I2C/Qwiic, and power input

### Screen Mounting

- **D-08:** Waveshare 7" HDMI LCD (H) — screen is in hand, can be measured
- **D-09:** 3D-printed integrated bezel + VESA 75mm backplate as a single piece (OpenSCAD). Edge protection for the panel, VESA holes on the back
- **D-10:** 3D-printed bracket bolted to passenger-side dash (left side, right-hand-drive car). No RAM Mount — direct bolt, no articulating joints
- **D-11:** Touch input active — co-driver uses touch for field notes, fuel logs, driver switching. Screen must be within reach and angled for interaction
- **D-12:** HDMI + USB cable run from Pi panel to dash-mounted screen

### ELP Camera

- **D-13:** ELP 4K front camera mounted via 3D-printed bracket bolted to dash
- **D-14:** Bracket only (no full enclosure) — simple cradle holding the camera module in position

### Claude's Discretion

- Cable exit approach for Pi case (individual grommeted holes vs single exit slot) — pick based on printability and number of cables
- Screen bracket angle (fixed) — pick based on touch interaction ergonomics and vibration constraints

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Hardware context

- `hardware/sensor-cluster.scad` — Existing OpenSCAD parametric design for ceiling-mounted Qwiic sensor cluster. Establishes the CAD workflow and PETG printing conventions
- `~/Brain/projects/shitbox-rally-2026.md` — Source of truth for physical stack dimensions, screen specs, mounting plans, and rally timeline

### Memory context

- `.claude/projects/-Users-tgreen-dev-shitbox/memory/project_v2_hardware.md` — Pi 5 physical stack order (NVMe HAT → Pi 5 → cooler → GPIO extension → perma-proto)
- `.claude/projects/-Users-tgreen-dev-shitbox/memory/project_v2_display.md` — Waveshare 7" screen specs, VESA 75mm, toughened glass, audio path
- `.claude/projects/-Users-tgreen-dev-shitbox/memory/project_i2c_hardening_plan.md` — TCA4307 bus buffer on Qwiic chain, cable considerations
- `.claude/projects/-Users-tgreen-dev-shitbox/memory/project_car_audio.md` — Audio path through Waveshare 3.5mm out

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `hardware/sensor-cluster.scad` — OpenSCAD parametric design. Reuse the same PETG material, mounting flange pattern, and parametric dimension approach for Pi case and screen bezel

### Established Patterns

- OpenSCAD for all 3D-printed parts — parametric, code-based, version-controlled
- PETG as the print material (heat-resistant, impact-resistant, suitable for automotive)

### Integration Points

- Pi case must accommodate the full stack: NVMe HAT → Pi 5 → active cooler → double-height GPIO extension → Adafruit perma-proto board
- Screen connects to Pi via HDMI (video) + USB (capacitive touch)
- GX12 connector carries sensor loom connections through case wall
- GPS SMA bulkhead connects external antenna to Pi's GPS module
- 1-Wire (DS18B20 temp probes), I2C/Qwiic, and power cables exit the case to reach sensors and power supply

</code_context>

<specifics>
## Specific Ideas

- The plywood electronics panel has a flux capacitor prop mounted on it — the Pi case sits alongside this on the same panel
- The Brio 100 cabin camera is already mounted on top of the panel — it stays there
- The GL.iNet portable router also lives on the panel
- The panel sits behind/between the front seats, so the Pi case is in a sheltered but warm location
- Edward (studying 3D art/game design) is available to collaborate on enclosure designs if the OpenSCAD approach needs more complex geometry

</specifics>

<deferred>
## Deferred Ideas

### Cable loom

Full cable loom design (routing, split tubing, connector choices for engine bay and exterior sensor runs) was not discussed. Could be its own planning scope or folded into this phase during planning.

### Power distribution

12V fused circuit from car battery, buck converter placement, ignition-linked vs always-on, clean shutdown — not discussed. Important but separable from the enclosure/mounting work.

### Reviewed Todos (not folded)

- "Investigate temperature sensors missing from dashboard SSE stream" — software/monitoring issue, not physical integration scope

</deferred>

---

*Phase: 20-physical-integration*
*Context gathered: 2026-04-17*
