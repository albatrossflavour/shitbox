# Phase 20: Physical Integration - Research

**Researched:** 2026-04-17
**Domain:** 3D-printed PETG enclosures, connector hardware, OpenSCAD CAD, automotive vibration isolation
**Confidence:** HIGH (decisions locked, hardware in hand, OpenSCAD patterns established in codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pi Enclosure**

- D-01: 3D-printed PETG case designed in OpenSCAD (consistent with existing `hardware/sensor-cluster.scad`)
- D-02: Case mounts to existing plywood electronics panel via screws. Panel is bolted permanently into the car (behind/between front seats)
- D-03: M2.5 rubber standoffs between Pi and case for vibration damping
- D-04: 30mm Noctua NF-A4 fan mount integrated into case design, with ventilation slots
- D-05: 1x GX12 (3-pin) aviation connector panel-mount cutout in case wall for external sensor loom
- D-06: SMA bulkhead pass-through for GPS antenna cable
- D-07: Cable exits for HDMI, USB (cameras, screen touch, keyboard), 1-Wire (DS18B20), I2C/Qwiic, and power input

**Screen Mounting**

- D-08: Waveshare 7" HDMI LCD (H) — screen is in hand, can be measured
- D-09: 3D-printed integrated bezel + VESA 75mm backplate as a single piece (OpenSCAD). Edge protection for the panel, VESA holes on the back
- D-10: 3D-printed bracket bolted to passenger-side dash (left side, right-hand-drive car). No RAM Mount — direct bolt, no articulating joints
- D-11: Touch input active — co-driver uses touch for field notes, fuel logs, driver switching. Screen must be within reach and angled for interaction
- D-12: HDMI + USB cable run from Pi panel to dash-mounted screen

**ELP Camera**

- D-13: ELP 4K front camera mounted via 3D-printed bracket bolted to dash
- D-14: Bracket only (no full enclosure) — simple cradle holding the camera module in position

### Claude's Discretion

- Cable exit approach for Pi case (individual grommeted holes vs single exit slot) — pick based on printability and number of cables
- Screen bracket angle (fixed) — pick based on touch interaction ergonomics and vibration constraints

### Deferred Ideas (OUT OF SCOPE)

- Full cable loom design (routing, split tubing, connector choices for engine bay and exterior sensor runs)
- Power distribution (12V fused circuit from car battery, buck converter placement, ignition-linked vs always-on, clean shutdown)

</user_constraints>

---

## Summary

This phase is pure physical integration: design and print enclosures, cut/mount hardware, route cables, and verify
the system survives a multi-hour drive. There is no software work. The decisions are locked, the hardware is either
in hand or well-specified, and the codebase already has an established OpenSCAD workflow in `hardware/sensor-cluster.scad`.

The primary risk is dimensional. The Pi 5 stack (NVMe HAT + Pi 5 + active cooler + double-height GPIO extension +
perma-proto) is tall and needs accurate internal height clearance. The screen bezel requires physical measurement of
the in-hand Waveshare panel before the SCAD can be written. The Brio 100 and GL.iNet router stay where they are —
only the Pi case, screen bezel+bracket, and ELP camera bracket are new prints.

One flag the planner must resolve: D-04 references a "30mm Noctua NF-A4 fan". The NF-A4 series is a 40mm fan
(40×40×10mm). Either the CONTEXT.md contains a transposition error (30mm thickness was meant, referring to the
official Pi 5 active cooler), or an actual Noctua 30mm fan is intended. This must be clarified before the fan
mount is modelled.

**Primary recommendation:** Measure all in-hand hardware before writing any SCAD. Get accurate dimensions for the
Waveshare panel face and the full Pi stack height. Then parametrise from those measurements, same as sensor-cluster.scad.

---

## Hardware Dimensions Reference

> All dimensions needed for OpenSCAD design. Measure in-hand hardware to verify or supersede these.

### Raspberry Pi 5 Board

| Property | Value | Source |
|----------|-------|--------|
| Board size | 85 × 56 mm | [VERIFIED: Raspberry Pi mechanical drawing] |
| Mounting hole dia | 2.9 mm (M2.5 clearance) | [VERIFIED: Raspberry Pi mechanical drawing] |
| Mounting hole inset | 3.5 mm from each edge | [VERIFIED: Raspberry Pi mechanical drawing] |
| Hole spacing | 49 × 58 mm | [VERIFIED: Raspberry Pi mechanical drawing] |
| Tallest component (USB/HDMI side) | ~15 mm above PCB | [ASSUMED] |

### Pi 5 Active Cooler (Official Raspberry Pi)

| Property | Value | Source |
|----------|-------|--------|
| Footprint | ~63.5 × 42.5 mm | [VERIFIED: Raspberry Pi product page] |
| Height (heatsink + fan blower) | ~30 mm | [VERIFIED: Raspberry Pi product page, mechanical drawing reference] |
| Mounts on Pi SoC via clips | yes — no separate screws | [ASSUMED: standard active cooler design] |

### Adafruit Perma-Proto Half-size PCB

| Property | Value | Source |
|----------|-------|--------|
| Board size | 81 × 51 mm | [VERIFIED: Adafruit product datasheet] |
| Thickness | ~1.6 mm | [ASSUMED: standard FR4] |
| Mounting holes | #4 / M3 size, 2.9" (73.6 mm) spacing | [VERIFIED: Adafruit product listing] |

### Double-Height GPIO Extension Header

| Property | Value | Source |
|----------|-------|--------|
| Height above Pi GPIO | ~15–20 mm (varies by part) | [ASSUMED: measure in hand] |
| Footprint | 51 × 5 mm (2×20 pin) | [ASSUMED: standard GPIO footprint] |

### Estimated Full Stack Height (NVMe HAT + Pi 5 + cooler + GPIO ext + perma-proto)

| Component | Height contribution |
|-----------|---------------------|
| NVMe HAT PCB | ~1.6 mm |
| HAT standoffs to Pi 5 | ~5–8 mm |
| Pi 5 PCB | 1.6 mm |
| Active cooler | ~30 mm |
| Double-height GPIO extension | ~15–20 mm |
| Perma-proto PCB | ~1.6 mm |
| **Estimated total** | **~55–65 mm** |

> [ASSUMED] — physical measurement of assembled stack is required before modelling enclosure height. This is the single
> most important dimension to verify before writing the Pi case SCAD.

### GX12 3-pin Aviation Connector (Panel Mount)

| Property | Value | Source |
|----------|-------|--------|
| Panel cutout diameter | 12 mm | [VERIFIED: multiple suppliers] |
| Thread | M12 × 1.0 | [VERIFIED: Renhotec/HandsOn Tech product specs] |
| Lock nut OD (hex) | ~17 mm | [ASSUMED: standard M12 lock nut] |
| Minimum panel thickness | ~1–3 mm | [ASSUMED: standard GX12 install] |

### SMA Bulkhead Pass-through

| Property | Value | Source |
|----------|-------|--------|
| Panel cutout diameter | 6.35–6.55 mm | [VERIFIED: multiple RF connector sources] |
| Thread | 1/4–36 UNS-2A | [VERIFIED: connector spec sources] |
| Wrench flats (hex nut) | ~8 mm across flats | [VERIFIED: industry-standard SMA bulkhead] |
| Panel thickness range | 0.5–3 mm | [ASSUMED: standard SMA bulkhead] |

### Noctua NF-A4x10 5V Fan (D-04 flag — see below)

| Property | Value | Source |
|----------|-------|--------|
| Frame size | 40 × 40 × 10 mm | [VERIFIED: Noctua product page] |
| Mounting hole spacing | 32 × 32 mm | [VERIFIED: Noctua product page / community] |
| Screw size | M3 | [VERIFIED: standard 40mm fan] |
| Blade diameter | 38.5 mm | [ASSUMED: standard 40mm frame] |

**D-04 discrepancy:** CONTEXT.md says "30mm Noctua NF-A4 fan." The NF-A4 series is a 40mm fan (40×40×10mm). Noctua
does not make a 30mm variant in this series. The most likely interpretations are:

1. D-04 meant the fan is 10mm thick (the `x10` variant), and "30mm" was a transposition of the active cooler height
2. An actual 30mm fan from a different vendor is intended (30×30×7mm = smaller, noisier, less static pressure)
3. The intent is a 40×40 cutout but the note was written casually

**Planner action required:** Confirm with user which fan is intended, or clarify D-04 means the 40mm NF-A4x10.
Until resolved, plan the fan mount for 40×40mm (NF-A4x10) as the safer interpretation — 40mm is the standard
"small quality fan" for Pi enclosures and the NF-A4x10 5V is a known-good Pi pairing.

### Waveshare 7" HDMI LCD (H) with Case (WS-13857)

| Property | Value | Source |
|----------|-------|--------|
| Display resolution | 1024 × 600 px | [VERIFIED: Waveshare product page] |
| Panel type | IPS, toughened glass 6H | [VERIFIED: project memory / Waveshare listing] |
| VESA hole pattern | 75 × 75 mm | [VERIFIED: project memory / Waveshare listing] |
| Audio out | 3.5 mm jack | [VERIFIED: project memory] |
| Touch interface | Capacitive, USB | [VERIFIED: Waveshare listing] |
| Overall case dimensions | **Measure in hand** | Waveshare wiki returns 403; exact mm unavailable online |

> The screen is physically in hand. Measure the face dimensions, bezel edge-to-glass distances, VESA hole
> positions, and connector locations before writing the bezel SCAD. The wiki is inaccessible; don't assume
> dimensions from training data.

---

## Architecture Patterns

### Established OpenSCAD Workflow (`hardware/sensor-cluster.scad`)

The existing design establishes all conventions this phase must follow. Key patterns to reuse:

**Parametric top-level constants**

```openscad
// Source: hardware/sensor-cluster.scad
$fn = 64;               // arc resolution — reuse this
WALL       = 1.5;       // between internal dividers
OUTER_WALL = 2.0;       // case outer wall
FLOOR      = 2.0;       // base floor thickness
PCB_TOL    = 0.6;       // clearance per pair of sides (0.3mm per side)
```

**PCB mounting posts (M2.5 self-tap)**

```openscad
// Source: hardware/sensor-cluster.scad
POST_H     = 4.0;       // standoff height
POST_OD    = 4.5;       // outer cylinder diameter
POST_PILOT = 2.1;       // self-tap pilot hole diameter for M2.5
HOLE_INSET = 2.5;       // distance from PCB edge to hole centre
```

**Mounting flanges**

```openscad
// Source: hardware/sensor-cluster.scad
FLANGE_W    = 12;       // flange width for bolting to structure
BOLT_D      = 4.5;      // M4 clearance hole
BOLT_HEAD_D = 8.5;      // counterbore for M4 washer/head
```

**Tray + lid pattern** — two separate modules, `tray()` and `lid()`, rendered side by side for printing preview.

**General structure:**

```
hardware/
├── sensor-cluster.scad    // ceiling Qwiic cluster (complete)
├── pi-case.scad           // NEW: Pi + HAT + cooler enclosure
├── screen-bezel.scad      // NEW: Waveshare bezel + VESA backplate
└── camera-bracket.scad    // NEW: ELP camera cradle
```

### Pi Case Design Approach

The Pi 5 stack (NVMe HAT → Pi 5 → cooler → GPIO extension → perma-proto) is too tall for a simple box. Approach:

1. The **floor** of the case holds the NVMe HAT (Pi mounts on top via HAT standoffs)
2. The **cooler** sits on top of Pi SoC — the case must be open or vented above the cooler, not a sealed lid
3. The **perma-proto** is at the top of the stack — treat it as the GPIO breakout level, not a second enclosed PCB
4. The **fan mount** integrates into one side wall, drawing air across the cooler fins

Alternative if stack height exceeds case printability: orient the stack horizontally with the Pi mounted to the
case side wall. Research shows community enclosures for Pi 5 + NVMe do this. Confirm after measuring the assembled
stack.

### Screen Bezel + VESA Backplate

Single-piece PETG print (D-09). The design must:

1. Accept the Waveshare panel's face dimensions (measure in hand)
2. Provide glass-edge retention lips on all four sides (not screws into the glass panel)
3. Have VESA 75mm hole pattern (75×75mm, M4 screws) on the back face
4. Allow USB and HDMI cables to exit without sharp bends
5. Leave the speaker grille and 3.5mm audio port accessible

The panel lacks usable rear attachment points (confirmed in Brain vault + memory). The bezel wraps the edges
from the front and the VESA backplate is cast into the rear of the same print.

Print orientation: face-down on bed (VESA backplate facing up) for optimal layer adhesion on the face lip.

### Cable Exit Strategy (Claude's Discretion)

CONTEXT.md leaves cable exits to discretion. Assessment:

| Option | Pros | Cons |
|--------|------|------|
| Individual grommeted holes | Clean, strain relief per cable | Many drill-like features to model, one per cable type |
| Single wide slot with TPU insert | Printable, flexible seal | Requires TPU print or sourced grommet strip |
| Cable-specific keyed slots (snap-in) | No loose grommets, good PETG printability | More complex SCAD |
| One-per-side exit panels (removable) | Serviceable, modular | More parts |

**Recommendation:** Individual slots sized per cable type (HDMI ~20mm wide, USB ~10mm, power ~8mm, Qwiic ~5mm),
each with an internal strain-relief tab that a zip-tie cinches against. This is the printable, zero-hardware
approach and matches what the sensor-cluster.scad does for its wire exits. Label each slot in the SCAD with a
comment per cable.

### Screen Bracket Angle (Claude's Discretion)

The screen is on the passenger-side dash, co-driver reaches touch. Constraints:

- Rally car, right-hand drive: passenger-side dash is left of driver looking forward
- Vibration: no articulating joints — fixed angle, stiff print
- Touch: must be reachable by a seated passenger without leaning far forward
- Glare: forward-facing screens catch direct sun in an east-facing morning rally

**Recommendation:** 15–20 degrees back from vertical (tilted toward driver/passenger, not fully upright). This
is a comfortable touch interaction angle, reduces forward glare, and a fixed bracket at this angle is a simple
trapezoid print. If it proves wrong on the day, the bracket is a 2-hour reprint.

---

## Standard Stack

### Core Tools / Materials

| Item | Version/Spec | Purpose | Notes |
|------|-------------|---------|-------|
| OpenSCAD | 2021.01+ | Parametric CAD | [ASSUMED: version in use — check `openscad --version`] |
| PETG filament | Generic / eSUN | Print material | Heat-resistant to ~80°C, impact-resistant, correct for automotive |
| M2.5 rubber standoffs | Standard | Pi vibration isolation (D-03) | Sourced separately |
| GX12 3-pin | Panel mount pair | Sensor loom connector (D-05) | 12mm cutout |
| SMA bulkhead | F-F pass-through | GPS antenna (D-06) | 6.5mm cutout |
| M4 screws | ~10mm length | VESA mounting, flange bolts | Standard |
| M2.5 screws | ~6mm length | PCB post self-tap | Standard |
| Zip ties | 2.5mm width | Cable strain relief in slots | Standard |

### Print Settings (PETG, from sensor-cluster.scad convention)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Material | PETG | Heat resistance, impact resistance for car environment |
| Layer height | 0.2 mm | Standard quality / speed balance |
| Infill | 30–40% | Structural parts — walls do most of the work |
| Perimeters / walls | 3–4 | Stiffness at connector cutouts |
| Support | Yes for overhangs > 45° | Fan mount recess, connector holes |
| Bed temp | 70–80°C | Standard PETG bed adhesion |
| Print temp | 230–240°C | Standard PETG |
| Cooling | Moderate (50–70% fan) | PETG warps with too much cooling |

### Fan Selection Note

D-04 references "30mm Noctua NF-A4" — the NF-A4 is 40×40×10mm. [VERIFIED: Noctua product line]

If the intent is airflow across the Pi cooler with minimal enclosure volume: the **40mm NF-A4x10 5V**
(32×32mm mount spacing, M3 screws) is the correct interpretation.

If a 30×30mm fan is specifically required (smaller cutout), a non-Noctua 30×30mm fan (e.g. Sunon 3010) would
be used instead — these are noisier and lower quality. [ASSUMED: Noctua does not make a 30mm fan]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vibration isolation | Silicone blobs, foam tape | M2.5 rubber standoffs (D-03) | Sized for M2.5, consistent compliance, survives heat |
| Cable organisation | Loose bundles | Braided split tubing + zip-tie mounts printed into case | Proven rally car practice |
| GPS cable pass-through | Bare wire through hole | SMA bulkhead connector (D-06) | Strain relief, reconnectable, proper RF shield |
| Sensor loom connection | Dupont jumpers | GX12 aviation connector (D-05) | Locking, IP52 rated, survives vibration |
| Screen edge retention | Glue / tape | PETG printed retention lips | Removable, inspectable, repeatable |
| Fan mounting | Hot glue to case | Integrated screw bosses, M3 screws | Survives vibration, serviceable |

**Key insight:** Automotive electronics fail at joints and connections, not in the middle of PCBs. Every mechanical
interface is an opportunity for a vibration failure. The hardware choices (GX12, SMA bulkhead, rubber standoffs)
are specifically designed to eliminate the failure modes that dupont jumpers and hot glue create.

---

## Common Pitfalls

### Pitfall 1: Printing Before Measuring

**What goes wrong:** Write the SCAD from nominal dimensions, print it, discover the Pi cooler is 2mm taller
than expected and the case lid doesn't close.

**Why it happens:** PETG prints are permanent (no edit-and-recompile). Parametric SCAD only saves you if the
parameters are correct.

**How to avoid:** Measure the assembled Pi stack in the actual configuration before writing a single dimension
into pi-case.scad. Use calipers. Write all measurements into the SCAD header as comments with the source
("measured 2026-04-17, caliper, ±0.5mm").

**Warning signs:** Jumping to OpenSCAD before picking up the hardware.

### Pitfall 2: Fan Mount Airflow Direction

**What goes wrong:** Fan integrated into case blows air toward cooler fins (correct), but no exit vents on
the opposite wall — hot air has nowhere to go. Case becomes an oven.

**Why it happens:** Thinking about fan intake without modelling the full airflow path.

**How to avoid:** Model intake slots on one face, exhaust slots on the opposite face (or top), with fan
forcing air from intake toward exhaust across the cooler fins. The cooler fins should sit inline with the
airflow path.

**Warning signs:** SCAD has intake cutout but no exhaust vents.

### Pitfall 3: HDMI Cable Radius at Case Exit

**What goes wrong:** HDMI cable is printed into a corner or 90-degree exit. Standard HDMI cables have a
minimum bend radius of ~30–40mm. The cable fights the print, stresses the connector, or the case lid
interferes.

**Why it happens:** Looking at connector dimensions in 2D cross-section, not modelling the cable exit
radius in 3D.

**How to avoid:** Use right-angle HDMI adapters (already ordered per Brain vault, 2026-04-13 session) at
the Pi end. Model the case exit slot to accept the right-angle adapter body, not a straight cable.

**Warning signs:** Straight HDMI exit routed through a wall without enough clearance for the plug body.

### Pitfall 4: Print Orientation and Layer Delamination Under Vibration

**What goes wrong:** Critical features (fan mount bosses, flange bolt holes) are printed with layer lines
running perpendicular to the stress direction. Vibration causes inter-layer delamination.

**Why it happens:** Default orientation optimises print speed, not part strength.

**How to avoid:** Orient each print so the primary stress direction is along layer lines (XY), not between
them (Z). Fan mount: print the fan wall as a vertical wall (layer lines parallel to face). Flange bolt holes:
print flanges horizontally.

**Warning signs:** A mounting boss that prints as a horizontal cylinder (weak in shear at the base).

### Pitfall 5: Screen Bracket Resonant Frequency

**What goes wrong:** Bracket resonates at corrugated-road frequency (~4–8 Hz), causing the screen to blur
or buzz during driving.

**Why it happens:** Long thin bracket (high aspect ratio, low mass) is essentially a tuned spring-mass system.

**How to avoid:** Keep the bracket short (less cantilever distance), use thicker wall sections at the bend,
add a cross-brace or gusset in the design. 40% infill minimum in the bracket geometry. PETG has better
damping than PLA.

**Warning signs:** Bracket is more than ~100mm long with no cross-support.

### Pitfall 6: PETG Warping on Large Flat Surfaces

**What goes wrong:** Large flat case base warps off the bed during printing.

**Why it happens:** PETG has more thermal expansion than PLA. Long flat parts curl at corners.

**How to avoid:** Add a 3–5mm brim in slicer. Ensure bed is levelled and 70°C+ (PETG needs hot bed).
Break large flat surfaces into smaller tiles if needed, or add ribs on the underside to stiffen.

**Warning signs:** Enclosure footprint larger than 120mm without ribs.

---

## Runtime State Inventory

> Phase 20 is physical integration only — no software changes. This section is not applicable.

None required. This phase contains zero code changes, zero database migrations, zero renamed symbols.
The only "state" is physical: hardware moves from bench to car.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| OpenSCAD | All 3D print SCAD files | [CHECK: `openscad --version`] | Unknown | Install via brew: `brew install openscad` |
| Slicer (PrusaSlicer/Cura) | STL → gcode for printing | [CHECK: local machine] | Unknown | Download PrusaSlicer free |
| 3D printer + PETG | All print tasks | [CHECK: physical hardware available] | N/A | Find local print service |
| Calipers | Measuring hardware before SCAD | [CHECK: physical tool] | N/A | Ruler (lower precision, acceptable for first draft) |
| HDMI right-angle adapter | Pi case HDMI exit | Ordered 2026-04-13 per Brain vault | — | Straight cable with wider slot |
| Soldering iron | Perma-proto wiring | Horusdy 2-in-1 ordered 2026-04-12 | — | None (blocks wiring tasks) |

**Missing dependencies with no fallback:**
- Soldering iron must be confirmed in hand before perma-proto wiring tasks are scheduled.
- 3D printer access must be confirmed (local printer or print service). PETG print quality matters for structural parts.

**Missing dependencies with fallback:**
- OpenSCAD: install via `brew install openscad` if not present (macOS, matches dev environment)

---

## Validation Architecture

> Phase 20 is physical integration — no automated tests are possible. Physical verification replaces automated testing.

### Validation Approach

This phase has no testable code. Validation is entirely physical (shake-down drive, hardware inspection).
The nyquist_validation framework does not apply here. The planner should treat each success criterion as
a manual verification checklist item rather than an automated test.

### Phase Gate Criteria (Physical Verification)

| Criterion | Verification Method |
|-----------|---------------------|
| Pi enclosure assembled | Visual inspection: case closes, fan spins, all cables exit cleanly |
| No thermal shutdown in enclosure | SSH to Pi, run `vcgencmd measure_temp`, confirm < 80°C after 30 min idle in enclosed case |
| Screen bracket holds under vibration | Drive test: screen readable and non-buzzing after corrugated section |
| GX12 connector mates/de-mates | Physical test: loom connects and disconnects under load |
| SMA GPS antenna reception | `cgps` / `gpsmon` confirms 3D fix with antenna connected via bulkhead |
| Full system boot in car | `systemctl status shitbox-telemetry` confirms active after boot in installed position |
| Multi-hour shake-down | System logs show continuous telemetry for duration of shake-down drive without crash/restart |

### Wave 0 Gaps

None — no test infrastructure needed. This phase produces STL files and physical hardware, not code.

---

## Security Domain

> Phase 20 is physical integration only — no network-exposed code, no authentication surfaces, no new data paths.
> ASVS categories do not apply. Security considerations are physical:

- **Physical access:** The Pi case should be difficult to open without tools (lid screws, not friction-fit) to
  prevent accidental disconnection at a rally pit stop.
- **Cable security:** All cables that carry sensitive data (GPS, cameras) exit through keyed slots or connectors.
  No USB storage ports should be accessible from outside the case without opening it.

---

## Code Examples

### OpenSCAD Parametric Constants Pattern (from codebase)

```openscad
// Source: hardware/sensor-cluster.scad — established project convention
$fn = 64;

// ---- Material / print constants ----
WALL       = 1.5;
OUTER_WALL = 2.0;
FLOOR      = 2.0;
PCB_TOL    = 0.6;    // total side clearance (0.3mm per side)

// ---- Pi 5 board ----
PI5_W      = 85.0;   // board width
PI5_D      = 56.0;   // board depth
PI5_HOLE_D = 2.9;    // mounting hole clearance
PI5_INSET  = 3.5;    // hole inset from edge
```

### Fan Mount Cutout Pattern

```openscad
// Standard 40mm fan: 40×40mm frame, 32×32mm mounting holes, M3 screws
FAN_W         = 40;
FAN_MOUNT_SPG = 32;  // mounting hole centre spacing
FAN_SCREW_D   = 3.4; // M3 clearance hole

module fan_cutout() {
    // Airflow hole slightly smaller than blade to avoid catching fingers
    translate([0, 0, -0.1])
        cylinder(d = 37, h = OUTER_WALL + 0.2);
    // Mount bosses or simple clearance holes
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * FAN_MOUNT_SPG/2, sy * FAN_MOUNT_SPG/2, -0.1])
            cylinder(d = FAN_SCREW_D, h = OUTER_WALL + 0.2);
}
```

### GX12 Panel Cutout

```openscad
// GX12 connector: 12mm cutout, add tolerance
GX12_D = 12.5;  // 12mm + 0.5mm clearance

module gx12_cutout(wall_thickness) {
    cylinder(d = GX12_D, h = wall_thickness + 0.2, $fn = 32);
}
```

### SMA Bulkhead Cutout

```openscad
// SMA bulkhead: 6.35mm thread, 6.55mm clearance hole
SMA_HOLE_D = 6.7;  // 6.35 + 0.35mm clearance for self-tap into PETG

module sma_cutout(wall_thickness) {
    cylinder(d = SMA_HOLE_D, h = wall_thickness + 0.2, $fn = 32);
}
```

### VESA 75mm Hole Pattern

```openscad
// VESA 75×75mm, M4 holes
VESA_75_SPACING = 75;
VESA_HOLE_D     = 4.5;  // M4 clearance

module vesa_75_holes(depth) {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * VESA_75_SPACING/2, sy * VESA_75_SPACING/2, -0.1])
            cylinder(d = VESA_HOLE_D, h = depth + 0.2, $fn = 32);
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Dupont jumpers for inter-module wiring | Aviation connectors (GX12) at case boundary | D-05 in CONTEXT.md | Survives rally vibration; serviceable |
| Pi 4 on plywood, no enclosure | Pi 5 in PETG printed case | v2 rebuild (2026-04-04) | Thermal, mechanical protection |
| RAM Mount for screen | Direct-bolt PETG bracket | D-10 in CONTEXT.md | No articulating joint to loosen on corrugations |
| i2c_designware (buggy on Pi 5) | i2c-gpio bitbang overlay | 2026-04-10 out-of-band | Stable sensor bus (all 6 sensors confirmed) |

**Noted from hardware sessions:**

- CPU at 70.5°C idle without enclosure — active cooling is non-optional. The enclosure fan must provide
  positive airflow, not just vents. [VERIFIED: STATE.md out-of-band hardware work section]
- Right-angle HDMI and USB adapters already ordered — the SCAD should assume right-angle connectors, not
  straight cable exits. [VERIFIED: Brain vault 2026-04-13 session]
- Brio 100 cabin camera stays on the existing panel position — not in scope for this phase. [VERIFIED: CONTEXT.md specifics]
- GL.iNet router also stays — not in scope. [VERIFIED: CONTEXT.md specifics]
- GPS wiring to perma-proto not confirmed end-to-end (TX/RX check still outstanding per Brain vault). The
  case design must leave GPIO header and perma-proto accessible for any remaining bench wiring.

---

## Open Questions

1. **Fan size in D-04**
   - What we know: D-04 says "30mm Noctua NF-A4 fan." The NF-A4 is a 40mm product line. Noctua does not make a 30mm fan in this series.
   - What's unclear: Was 30mm a transposition error for 10mm (the thickness), meaning a 40×40×10mm NF-A4x10? Or is a 30×30mm fan from a different vendor intended?
   - Recommendation: Default the SCAD to a 40mm (NF-A4x10) fan mount. Add a parametric `FAN_W = 40` constant so it can be trivially changed to 30 if needed.

2. **Pi stack height not confirmed**
   - What we know: Individual component heights estimated, but the full assembled stack has not been measured.
   - What's unclear: Double-height GPIO extension headers vary from 15mm to 22mm. NVMe HAT standoff heights also vary. Total assembled stack height could be 55–70mm.
   - Recommendation: Measure assembled stack before writing pi-case.scad. This is the critical path blocker for the Pi case design.

3. **Waveshare screen dimensions not publicly accessible**
   - What we know: VESA 75mm, 1024×600, toughened glass. Screen is in hand.
   - What's unclear: Exact panel face dimensions, bezel-to-glass inset, connector locations on PCB.
   - Recommendation: Measure the in-hand unit with calipers before writing screen-bezel.scad. The Waveshare wiki returns 403 and no reliable dimension source was found online.

4. **GPS wiring to perma-proto still outstanding**
   - What we know: GPS works via `/dev/ttyAMA0` in software. TX/RX wiring to GPIO 14/15 on the perma-proto needs physical verification (Brain vault 2026-04-17).
   - What's unclear: Is the perma-proto wiring complete enough to enclose, or will the case need to be reopened for GPS wiring?
   - Recommendation: GPS wiring check should be a Wave 0 task (before any case is sealed). Do not enclose the Pi until all bench wiring is confirmed.

5. **Plywood panel mounting point dimensions**
   - What we know: The panel exists in the car, between front seats. Pi case bolts to it.
   - What's unclear: Exact available footprint on the panel, position of existing holes, clearance around the flux capacitor prop and GL.iNet router.
   - Recommendation: Measure the panel on the next car visit before finalising flange design.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pi 5 tallest component (USB/HDMI side) is ~15mm above PCB | Hardware Dimensions | Case too short — cannot close lid |
| A2 | Double-height GPIO extension adds ~15–20mm | Hardware Dimensions | Full stack height miscalculated |
| A3 | NVMe HAT standoffs are ~5–8mm | Hardware Dimensions | Full stack height miscalculated |
| A4 | GX12 lock nut OD is ~17mm | Hardware Dimensions | Nut fouls on case wall, won't tighten |
| A5 | GX12 minimum panel thickness is 1–3mm | Hardware Dimensions | Connector doesn't seat correctly in PETG wall |
| A6 | SMA bulkhead panel thickness range is 0.5–3mm | Hardware Dimensions | PETG wall too thick for standard SMA nut |
| A7 | Perma-proto PCB is half-size (81×51mm) | Hardware Dimensions | Case footprint wrongly sized |
| A8 | Noctua does not make a 30mm fan in NF-A4 series | Fan Selection | Wrong fan mount modelled |
| A9 | OpenSCAD version on dev machine is 2021.01+ | Environment | SCAD syntax incompatibility |
| A10 | Soldering iron is now in hand (ordered 2026-04-12) | Environment | Wiring tasks blocked |
| A11 | Screen bracket angle 15–20° back from vertical is ergonomically acceptable | Screen Bracket | Bracket must be reprinted after shake-down |

---

## Sources

### Primary (HIGH confidence)

- Official Raspberry Pi mechanical drawing — Pi 5 board dimensions, mounting hole spacing
- Raspberry Pi active cooler product page — cooler dimensions (~63.5×42.5×30mm)
- Noctua product pages — NF-A4x10 dimensions (40×40×10mm, 32×32mm mount spacing, M3)
- Multiple RF connector supplier spec pages — SMA bulkhead cutout diameter (6.35–6.55mm)
- Multiple aviation connector supplier pages — GX12 cutout 12mm, thread M12×1.0
- `hardware/sensor-cluster.scad` — established OpenSCAD conventions and parameters

### Secondary (MEDIUM confidence)

- Adafruit product listing + Mouser datasheet — perma-proto half-size 81×51mm
- Waveshare product listings (accessible pages) — VESA 75mm confirmed, resolution 1024×600 confirmed
- Brain vault + project memory — display specs, hardware session notes, outstanding wiring items

### Tertiary (LOW confidence / ASSUMED)

- Pi 5 component heights above PCB (USB, HDMI side) — training knowledge, measure in hand
- Double-height GPIO extension header height — varies by vendor; measure in hand
- NVMe HAT standoff heights — varies by HAT; measure in hand
- GX12 lock nut dimensions — common M12 hardware, verify against purchased part

---

## Metadata

**Confidence breakdown:**

- Hardware dimensions: MEDIUM-HIGH — board sizes and standard connector specs verified; stack heights assumed
- Architecture (OpenSCAD patterns): HIGH — conventions directly from codebase
- Pitfalls: HIGH — all common 3D-print-for-automotive failure modes, backed by physical reasoning
- Fan selection discrepancy: HIGH — NF-A4 = 40mm is verified fact

**Research date:** 2026-04-17
**Valid until:** No expiry — hardware specs don't change. Fan selection query should be resolved before planning starts.
