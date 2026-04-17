# Phase 20: Physical Integration - Patterns

**Extracted:** 2026-04-17
**Source files analysed:** `hardware/sensor-cluster.scad` (sole existing analog)

---

## Files to Create / Modify

From CONTEXT.md and RESEARCH.md:

| File | Role | Status |
|------|------|--------|
| `hardware/pi-case.scad` | Pi 5 stack enclosure with fan, GX12, SMA, cable exits | NEW |
| `hardware/screen-bezel.scad` | Waveshare 7" integrated bezel + VESA 75mm backplate | NEW |
| `hardware/camera-bracket.scad` | ELP 4K front camera cradle for dash | NEW |

No existing files are modified. `hardware/sensor-cluster.scad` is the reference analog only.

---

## OpenSCAD File Anatomy

Every SCAD file in this project follows the same layout. Extracted verbatim from `sensor-cluster.scad`:

```
1. File header comment (project, part name, orientation note, units)
2. $fn = 64;  ← global arc resolution, always present
3. Constant blocks (grouped by concern, named in SCREAMING_SNAKE_CASE)
4. Derived dimension block (constants computed from earlier constants)
5. Main render call(s) — tray() and translate([...]) lid() side by side
6. Top-level module definitions (tray, lid)
7. Component sub-modules (base_plate, outer_walls, posts, etc.)
```

### File Header Pattern

```openscad
// Shitbox Rally — ceiling-mounted Qwiic sensor cluster
//
// 4x2 grid, driver-facing front (floor of this tray = driver-facing down
// when mounted to the car roof).
//
// Sensors:
//   Row 1 (back, from driver's left): INA226 | BME690 | VEML7700 | TCA4307
//   Row 2 (front, from driver's left): Buzzer | SSD1306 | empty   | LIS3MDL
//
// Units: mm.
```

Apply same pattern for new files: project name, part description, orientation note (which way is "up" when installed), units.

### Arc Resolution

```openscad
$fn = 64;
```

Always the first non-comment line. Do not vary this per-module.

---

## Parametric Constants Pattern

Constants are declared as top-level variables in named blocks, **before** any module definitions. Derived dimensions are computed in a separate block after the primitives.

### Print / Material Block

```openscad
// ---- PCB sizes ----
PCB_SMALL  = [25, 20];   // INA226, BME690, VEML7700, Buzzer, LIS3MDL
PCB_LARGE  = [25, 25];   // TCA4307, SSD1306
PCB_TOL    = 0.6;        // total clearance (0.3mm per side)

// ---- Cell geometry ----
CELL_W     = 38;         // cable-direction pitch
CELL_H     = 10;         // interior height

WALL       = 1.5;        // between internal dividers
OUTER_WALL = 2.0;
FLOOR      = 2.0;
```

The convention: `OUTER_WALL = 2.0` for exterior walls, `WALL = 1.5` for interior dividers, `FLOOR = 2.0` for base thickness. Reuse these exact values unless there is a specific reason to change them.

### PCB Mounting Post Block

```openscad
// ---- PCB mounting posts (M2.5 self-tap, 4 corners of each PCB) ----
POST_H         = 4.0;    // standoff height (PCB off floor = Qwiic connector clearance)
POST_OD        = 4.5;    // outer diameter
POST_PILOT     = 2.1;    // self-tap pilot for M2.5
HOLE_INSET     = 2.5;    // distance from PCB edge to hole centre
```

For Phase 20: the Pi uses M2.5 rubber standoffs (D-03) instead of self-tap posts. The `POST_PILOT = 2.1` value is for self-tapping — Pi case will need a different mount strategy (threaded insert or through-hole + nut), but `HOLE_INSET = 2.5` can be reused for the Pi 5's 3.5mm inset (adjust to `PI5_INSET = 3.5`).

### Mounting Flange Block

```openscad
// ---- Mounting flanges (M4 to roof frame) ----
FLANGE_W      = 12;
FLANGE_THICK  = FLOOR;
BOLT_D        = 4.5;     // M4 clearance
BOLT_HEAD_D   = 8.5;     // M4 washer / head clearance (counterbore)
```

Reuse these values verbatim for all panel-mount flanges (plywood panel, dash bracket). `BOLT_D = 4.5` is M4 clearance; `BOLT_HEAD_D = 8.5` accommodates an M4 washer head or standard hex head. Counterbore from bottom so head sits flush.

### Lid Constants Block

```openscad
// ---- Lid ----
LID_THICK     = 1.6;
LID_SCREW_D   = 2.7;     // M2.5 clearance
LID_BOSS_D    = 6;       // boss OD for self-tap M2.5
LID_BOSS_HOLE = 2.1;     // pilot hole for M2.5 self-tap
```

Lid is 1.6mm thick. Lid bosses sit in end zones (clear of PCB cells). Lid screws self-tap into the bosses from above.

### Derived Dimensions Block

```openscad
// ---- Derived overall dims ----
GRID_COLS = 4;
GRID_ROWS = 2;
GRID_W  = GRID_COLS * CELL_W;
INNER_W = 2 * END_ZONE + GRID_W;
INNER_D = GRID_ROWS * CELL_D + (GRID_ROWS - 1) * WALL;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;
```

Derived dims come after all primitives. Never hardcode a value that can be expressed as a formula. If `OUTER_W` changes, everything downstream updates automatically.

---

## Tray + Lid Module Pattern

The render entry point calls `tray()` and a translated `lid()` side by side — this produces a printable preview showing both parts:

```openscad
tray();
translate([0, OUTER_D + FLANGE_W + 10, 0]) lid();
```

The `lid()` module is simple: a flat plate with an inner lip that drops into the tray, and clearance holes aligned to the boss centres.

```openscad
module lid() {
    difference() {
        union() {
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            // inner lip drops into tray opening
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -0.8])
                cube([INNER_W, INNER_D, 0.8 + 0.01]);
        }
        // screw holes aligned to boss centres
        for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_T, BOSS_Y_B])
            translate([x, y, -0.1])
                cylinder(d = LID_SCREW_D, h = LID_THICK + 1);
    }
}
```

The inner lip is 0.8mm — enough to locate the lid without requiring a tight fit.

---

## Lid Boss Pattern

Lid bosses live in end zones (clear of PCB cells). Each boss is a solid cylinder with a pilot hole drilled from `z = 2` (leaves 2mm solid base for thread engagement):

```openscad
module lid_bosses() {
    boss_h = CELL_H;
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_T, BOSS_Y_B])
        translate([x, y, FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = boss_h);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = boss_h);
            }
}
```

Note: pilot hole starts at `z = 2`, not `z = 0` — that 2mm solid base stops the screw from punching through the floor.

---

## PCB Post Pattern

Four posts per PCB, positioned symmetrically from the PCB centre using `HOLE_INSET` from the edge:

```openscad
module pcb_posts() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; pcb = c[3];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        dx = pcb[0]/2 - HOLE_INSET;
        dy = pcb[1]/2 - HOLE_INSET;
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx * dx, cy + sy * dy, FLOOR])
                cylinder(d = POST_OD, h = POST_H);
    }
}

module pcb_post_holes() {
    for (c = CELLS) {
        // ... same loop ...
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx * dx, cy + sy * dy, FLOOR + 0.5])
                cylinder(d = POST_PILOT, h = POST_H + 0.5);
    }
}
```

Posts and holes are separate modules — posts go in the `union()`, holes go in the `difference()` of `tray()`. This is consistent with the broader tray() structure.

---

## Tray Module Structure

The tray is always a `difference()` of a `union()` of solid features, minus a list of cutout modules:

```openscad
module tray() {
    difference() {
        union() {
            base_plate();
            outer_walls();
            row_divider();
            lid_bosses();
            pcb_posts();
        }
        cell_floor_cutouts();
        side_wall_cutouts();
        flange_holes();
        pcb_post_holes();
    }
}
```

Apply the same pattern for `pi_case()`: one `union()` of solid geometry, one `difference()` subtracting connector cutouts, cable slots, fan hole, flange holes.

---

## Flange + Bolt Hole Pattern

Flanges are flat extensions of the floor, same thickness as `FLOOR`:

```openscad
module base_plate() {
    union() {
        // Main floor
        translate([FLANGE_W, 0, 0])
            cube([OUTER_W, OUTER_D, FLOOR]);
        // Flanges (left and right)
        for (side = [0, 1])
            translate([side == 0 ? 0 : FLANGE_W + OUTER_W, 0, 0])
                cube([FLANGE_W, OUTER_D, FLANGE_THICK]);
    }
}
```

Bolt holes with counterbore at flange corners:

```openscad
module flange_holes() {
    margin = 6;
    for (x = [margin, TOTAL_W - margin],
         y = [margin, OUTER_D - margin])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            // counterbore from bottom so head sits flush
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = 1.5);
        }
}
```

`margin = 6` keeps bolt holes 6mm from flange edges. Counterbore depth is 1.5mm — enough for M4 head + washer.

---

## Side Wall Cutout Pattern (Wire / Cable Exits)

Cable exits are rectangular slots cut through the outer wall. From the sensor-cluster analog:

```openscad
WIRE_SLOT = [8, 3];   // [width, height]

module side_wall_cutouts() {
    // INA226 shunt wires exit through the BACK outer wall (y=0)
    translate([cx - WIRE_SLOT[0]/2, -0.1, FLOOR + 2])
        cube([WIRE_SLOT[0], OUTER_WALL + 0.2, WIRE_SLOT[1]]);

    // Pi Qwiic cable entry: slot in LEFT outer wall into end zone
    translate([FLANGE_W - 0.1, entry_y - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 3]);
}
```

Key conventions:
- Slot starts 2mm above floor (`FLOOR + 2`) — prevents floor delamination at cutout corner
- Cutout depth is `OUTER_WALL + 0.2` — the `+ 0.2` is a standard boolean safety margin (epsilon)
- All cutouts use `-0.1` on the entry face for clean boolean subtraction

Apply these conventions to every cable slot in the Pi case: HDMI slot, USB slots, power slot, Qwiic slot.

---

## Connector Cutout Patterns (New for Phase 20)

These are not in sensor-cluster.scad but follow its conventions directly. They go in the `difference()` block of `pi_case()`.

### GX12 3-pin Aviation Connector (D-05)

```openscad
GX12_D = 12.5;  // 12mm nominal + 0.5mm clearance

module gx12_cutout(wall_thickness) {
    // Centred on connector position in wall face
    cylinder(d = GX12_D, h = wall_thickness + 0.2, $fn = 32);
}
```

The nut flats are ~17mm — ensure no structure within 8.5mm radius of cutout centre on the inner wall face.

### SMA Bulkhead Pass-through (D-06)

```openscad
SMA_HOLE_D = 6.7;  // 6.35mm thread + 0.35mm clearance

module sma_cutout(wall_thickness) {
    cylinder(d = SMA_HOLE_D, h = wall_thickness + 0.2, $fn = 32);
}
```

### 40mm Fan Cutout (D-04, defaulting to NF-A4x10)

```openscad
FAN_W         = 40;
FAN_MOUNT_SPG = 32;  // mounting hole centre spacing (NF-A4x10)
FAN_SCREW_D   = 3.4; // M3 clearance

module fan_cutout(wall_thickness) {
    // Airflow aperture, slightly inside blade circle
    translate([0, 0, -0.1])
        cylinder(d = 37, h = wall_thickness + 0.2);
    // M3 mounting holes
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * FAN_MOUNT_SPG/2, sy * FAN_MOUNT_SPG/2, -0.1])
            cylinder(d = FAN_SCREW_D, h = wall_thickness + 0.2);
}
```

If the fan turns out to be 30×30mm, change `FAN_W = 30`, `FAN_MOUNT_SPG = 24`, keep structure identical.

### VESA 75mm Hole Pattern (D-09, screen bezel)

```openscad
VESA_75_SPACING = 75;
VESA_HOLE_D     = 4.5;  // M4 clearance

module vesa_75_holes(depth) {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * VESA_75_SPACING/2, sy * VESA_75_SPACING/2, -0.1])
            cylinder(d = VESA_HOLE_D, h = depth + 0.2, $fn = 32);
}
```

---

## Outer Walls Module Pattern

```openscad
module outer_walls() {
    translate([FLANGE_W, 0, FLOOR])
        difference() {
            cube([OUTER_W, OUTER_D, CELL_H]);
            translate([OUTER_WALL, OUTER_WALL, -0.1])
                cube([INNER_W, INNER_D, CELL_H + 1]);
        }
}
```

A hollow box: outer cube minus inner cube. The inner cutout extends `CELL_H + 1` to ensure clean boolean — the extra 1mm above the wall height is intentional, it means the inner void is open-topped.

---

## Boolean Safety Margin Convention

Every boolean subtraction uses `+ 0.2` on the depth and `-0.1` on the entry face:

```openscad
// Floor cutout: goes through floor, -0.1 entry, FLOOR + 0.2 depth
translate([cx, cy, -0.1])
    cylinder(d = LIGHT_HOLE, h = FLOOR + 0.2);

// Wall cutout: -0.1 on entry face, OUTER_WALL + 0.2 depth
translate([cx - WIRE_SLOT[0]/2, -0.1, FLOOR + 2])
    cube([WIRE_SLOT[0], OUTER_WALL + 0.2, WIRE_SLOT[1]]);
```

Apply this consistently. It prevents zero-face intersection artefacts in the OpenSCAD preview and ensures clean STL export.

---

## Naming Conventions

From `sensor-cluster.scad`:

| Convention | Example |
|------------|---------|
| Constants | `OUTER_WALL`, `POST_H`, `FLANGE_W` |
| Modules | `tray()`, `lid()`, `base_plate()`, `outer_walls()` |
| Comment blocks | `// ---- Section name ----` |
| Inline units | `// standoff height (PCB off floor = Qwiic connector clearance)` |
| Tolerance suffix | `+ 0.2`, `- 0.1` — never a bare `0`, always the intent in a comment |

New files should follow identical conventions. Module names should describe geometry (`fan_cutout`, `gx12_cutout`, `vesa_75_holes`), not intent.

---

## Hardware Directory Structure

```
hardware/
├── sensor-cluster.scad    // ceiling Qwiic cluster (existing)
├── pi-case.scad           // Pi 5 stack enclosure (Phase 20, NEW)
├── screen-bezel.scad      // Waveshare 7" bezel + VESA backplate (Phase 20, NEW)
└── camera-bracket.scad    // ELP 4K dash cradle (Phase 20, NEW)
```

No subdirectory structure. No separate STL files committed — only SCAD source. STL export happens locally in the slicer workflow.

---

## Pre-Measurement Template (Wave 0 Task)

Before writing any constant into a SCAD file, the measured values need to be recorded in the file header. Pattern from sensor-cluster.scad comment style:

```openscad
// Shitbox Rally — Pi 5 stack enclosure
//
// Stack (bottom to top): NVMe HAT → Pi 5 → active cooler → GPIO ext → perma-proto
// Installed orientation: NVMe HAT down (floor of case), HDMI/USB ports face RIGHT
//
// All key dimensions measured with calipers 2026-XX-XX ±0.5mm:
//   PI5_W         = 85.0   // Pi 5 PCB width (verified Raspberry Pi mechanical drawing)
//   PI5_D         = 56.0   // Pi 5 PCB depth
//   STACK_H       = ?.?    // MEASURE: assembled stack, NVMe HAT bottom to perma-proto top
//   COOLER_H      = ?.?    // MEASURE: Pi 5 cooler height above Pi 5 PCB
//   GPIO_EXT_H    = ?.?    // MEASURE: double-height GPIO extension above Pi 5 GPIO pins
//
// Units: mm.
```

Fill in the `?.?` measurements before writing the enclosure geometry. Do not estimate from data sheets for the stack height.
