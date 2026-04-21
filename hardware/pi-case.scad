// Shitbox Rally — Pi 5 stack enclosure — GAME OF THRONES EDITION
//
// Castle fortress aesthetic: stone block cladding with running bond mortar,
// crenellated battlements, portcullis exhaust vents, sword relief carvings,
// heater shield sigil, and arrow slit lid ventilation.
//
// All internal dimensions, mounting points, and functional cutouts are
// identical to the original design. External walls are 0.5mm thicker
// (2.5mm total) to accommodate stone mortar grooves (0.5mm deep) without
// breaching 2mm minimum wall thickness anywhere.
//
// Stack (bottom to top): NVMe HAT → Pi 5 → active cooler → GPIO ext → perma-proto
// Installed orientation: NVMe HAT on floor, HDMI ports face LONG EDGE (front),
//                        USB/Ethernet face SHORT EDGE (right)
//
// All key dimensions measured with calipers 2026-04-17 +/-0.5mm:
//   Total stack height  = 65.0  (NVMe HAT bottom to perma-proto top)
//   NVMe HAT height     = 20.0  (floor to Pi 5 PCB bottom)
//   Pi 5 board          = 85.0 x 56.0  (verified RPi mechanical drawing)
//   Mounting holes       = 58.0 x 49.0 spacing, 3.5mm inset
//
// Fan: 40mm Noctua NF-A4x10 5V (to be purchased). Parametric.
//
// Units: mm.

$fn = 64;

// ---- Print / material ----
OUTER_WALL = 2.5;        // 2mm structural + 0.5mm stone relief allowance
FLOOR      = 2.0;
PCB_TOL    = 1.0;        // total clearance (0.5mm per side — first-print margin)

// ---- Pi 5 board (verified RPi mechanical drawing) ----
PI5_W      = 85.0;       // board width (long edge)
PI5_D      = 56.0;       // board depth (short edge)
PI5_HOLE_D = 2.9;        // mounting hole clearance (M2.5)
PI5_INSET  = 3.5;        // hole inset from edge
PI5_HOLE_W = 58.0;       // hole spacing along width
PI5_HOLE_D_SPACING = 49.0; // hole spacing along depth

// ---- Stack (measured 2026-04-17) ----
STACK_H       = 65;       // full stack height
HAT_H         = 20;       // NVMe HAT: floor to Pi 5 PCB bottom

// ---- Connector positions (from RPi mechanical drawing) ----
// HDMI, USB-C, AV and fan header all sit on the same long edge as HDMI.
// HDMI/USB-C X offsets are measured INWARD FROM THE USB/ETHERNET SHORT EDGE
// (case right wall) — this is how the Pi 5 mech drawing dimensions them.
HDMI1_OFFSET  = 26.0;    // HDMI0 centre, from USB/Ethernet short edge
HDMI2_OFFSET  = 39.5;    // HDMI1 centre, from USB/Ethernet short edge
HDMI_PORT_H   = 3.5;     // port body height above Pi PCB top

USB_OFFSET    = 29.0;    // USB-A stack centre, along Pi short axis (Y)
USB_PORT_H    = 15.5;    // stacked USB-A height above PCB (ref only)

PWR_OFFSET    = 11.5;    // USB-C centre, from USB/Ethernet short edge
PWR_PORT_H    = 3.5;     // USB-C port body height above Pi PCB top

// ---- Fan (Noctua NF-A4x10 5V, to be purchased) ----
FAN_W         = 40;
FAN_MOUNT_SPG = 32;       // mounting hole centre spacing
FAN_SCREW_D   = 3.4;      // M3 clearance
FAN_APERTURE  = 37;        // airflow hole diameter

// ---- Connector cutouts ----
GX12_D        = 12.5;     // 12mm + 0.5mm clearance (per D-05)
SMA_HOLE_D    = 6.7;      // 6.35mm + 0.35mm clearance (per D-06)

// ---- Rubber standoffs (per D-03 — through-hole + nut, not self-tap) ----
STANDOFF_HOLE_D = 2.7;    // M2.5 clearance
STANDOFF_BOSS_D = 6.0;    // boss OD
STANDOFF_H      = 4.0;    // rubber standoff compressed height

// ---- Mounting flanges (M4 to plywood panel) ----
FLANGE_W      = 12;
FLANGE_THICK  = 3.0;      // stepped above FLOOR — leaves 1.5mm under counterbore
BOLT_D        = 4.5;      // M4 clearance
BOLT_HEAD_D   = 8.5;      // M4 washer/head counterbore
BOLT_HEAD_H   = 1.5;      // counterbore depth

// ---- Lid ----
LID_THICK     = 1.6;
LID_SCREW_D   = 2.7;      // M2.5 clearance
LID_BOSS_D    = 6;
LID_BOSS_HOLE = 2.1;      // pilot for M2.5 self-tap

// ---- Cable exit slots (right-angle adapters, per Research pitfall 3) ----
// Sized with 1-2mm margin on the nominal connector dimension — adapter
// bodies and cable strain-reliefs vary more than datasheet dims suggest.
// NOTE: HDMI0 and HDMI1 centres are 13.5mm apart on Pi 5. Any slot width
// over that merges the two cutouts into one opening — acceptable and only
// one HDMI is in use at a time (screen only). Bridge across the top of the
// merged slot is ~29mm, which PETG handles at reasonable print speeds.
HDMI_SLOT  = [15, 10];    // right-angle micro-HDMI adapter body (nom 14x8)
USB_SLOT   = [15, 18];    // stacked USB-A ports (nom 13.5x16.5)
PWR_SLOT   = [12, 8];     // USB-C cable shroud (nom ~11x7)
QWIIC_SLOT = [7, 5];      // Qwiic/STEMMA QT cable + strain relief
ONEWIRE_SLOT = [6, 4];    // DS18B20 1-Wire cable + heatshrink

// ---- Exhaust vents (original, kept for reference) ----
VENT_SLOT_W   = 20;
VENT_SLOT_H   = 1.5;
VENT_COUNT    = 6;
VENT_SPACING  = 4;


// =====================================================
//   Castle decorative parameters
// =====================================================
MORTAR_W       = 0.4;     // mortar groove width
MORTAR_D       = 0.5;     // mortar groove depth (leaves 2.0mm structural wall)
STONE_ROW_H    = 7.0;     // stone block row height
STONE_COL_W    = 11.0;    // stone block column width (running bond)

MERLON_W       = 5.0;     // battlement merlon width
MERLON_H       = 5.0;     // merlon height above lid surface
CRENEL_W       = 4.0;     // gap between merlons

PORTCULLIS_W   = 20;      // portcullis opening width
PORTCULLIS_H   = 26;      // portcullis opening height
PORT_BAR_W     = 1.2;     // portcullis bar width
PORT_BAR_N     = 4;       // number of vertical bars

SWORD_BLADE_L  = 20;      // sword blade length
SWORD_BLADE_W  = 2.5;     // blade width at guard
SWORD_TIP_W    = 0.6;     // blade tip width
SWORD_GUARD_W  = 6.0;     // crossguard width
SWORD_GUARD_H  = 1.2;     // crossguard height
SWORD_GRIP_L   = 6.0;     // grip length
SWORD_GRIP_W   = 1.5;     // grip width
SWORD_POMMEL_D = 2.5;     // pommel diameter
SWORD_RELIEF   = 0.3;     // relief depth carved into wall

SHIELD_W       = 28;      // sigil shield width on lid
SHIELD_H       = 35;      // sigil shield height on lid
SHIELD_RAISE   = 0.8;     // raised height above lid surface

FAN_FRAME_OD   = FAN_APERTURE + 6;  // fan arch frame outer diameter
FAN_FRAME_T    = 0.8;     // fan arch frame depth (protrusion from wall)


// =====================================================
//   Derived dimensions
// =====================================================
INNER_W = PI5_W + PCB_TOL;
INNER_D = PI5_D + PCB_TOL;
INNER_H = STACK_H + 5;    // 5mm clearance above stack top
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;
TOTAL_D = OUTER_D;

// Pi PCB origin relative to outer shell
PI_X0 = FLANGE_W + OUTER_WALL + PCB_TOL / 2;
PI_Y0 = OUTER_WALL + PCB_TOL / 2;
PI_Z0 = FLOOR + HAT_H;   // Pi PCB sits on top of NVMe HAT

// Fan centre on left wall, aligned with cooler
FAN_CZ = PI_Z0 + 1.6 + 15;
FAN_CY = OUTER_D / 2;

// Lid boss positions
BOSS_INSET_X = 5;
BOSS_INSET_Y = 5;
BOSS_X_L = FLANGE_W + OUTER_WALL + BOSS_INSET_X;
BOSS_X_R = FLANGE_W + OUTER_WALL + INNER_W - BOSS_INSET_X;
BOSS_Y_F = OUTER_WALL + BOSS_INSET_Y;
BOSS_Y_B = OUTER_WALL + INNER_D - BOSS_INSET_Y;


// =====================================================
//   Main — render tray and lid side by side
// =====================================================
pi_case_tray();
translate([0, OUTER_D + FLANGE_W + 10, 0]) pi_case_lid();


// =====================================================
//   Tray — functional geometry + castle decoration
// =====================================================
module pi_case_tray() {
    difference() {
        union() {
            pi_case_base_plate();
            pi_case_outer_walls();
            pi_case_standoff_bosses();
            pi_case_lid_bosses();
            castle_fan_arch();
        }
        pi_case_standoff_holes();
        pi_case_fan_cutout();
        castle_portcullis_vents();
        pi_case_gx12_cutout();
        pi_case_sma_cutout();
        pi_case_cable_slots();
        pi_case_flange_holes();
        pi_case_lid_boss_holes();
        castle_stone_mortar();
        castle_sword_relief();
    }
}


// =====================================================
//   Lid — functional geometry + castle decoration
// =====================================================
module pi_case_lid() {
    difference() {
        union() {
            // main plate
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            // inner lip drops into tray opening
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -0.8])
                cube([INNER_W, INNER_D, 0.8 + 0.01]);
            // castle decoration
            castle_lid_crenellations();
            castle_lid_shield();
        }
        // screw holes (extended through merlons for safety)
        for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_F, BOSS_Y_B])
            translate([x, y, -0.1])
                cylinder(d = LID_SCREW_D, h = LID_THICK + MERLON_H + 1);
        // arrow slit ventilation
        castle_arrow_slit_vents();
    }
}


// =====================================================
//   Tray solid components (functional, unchanged logic)
// =====================================================
module pi_case_base_plate() {
    union() {
        // main floor
        translate([FLANGE_W, 0, 0])
            cube([OUTER_W, OUTER_D, FLOOR]);
        // flanges along long edges (left and right of tray)
        for (side = [0, 1])
            translate([side == 0 ? 0 : FLANGE_W + OUTER_W, 0, 0])
                cube([FLANGE_W, OUTER_D, FLANGE_THICK]);
    }
}

module pi_case_outer_walls() {
    translate([FLANGE_W, 0, FLOOR])
        difference() {
            cube([OUTER_W, OUTER_D, INNER_H]);
            translate([OUTER_WALL, OUTER_WALL, -0.1])
                cube([INNER_W, INNER_D, INNER_H + 1]);
        }
}

module pi_case_standoff_bosses() {
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, FLOOR])
            cylinder(d = STANDOFF_BOSS_D, h = HAT_H - 1);
    }
}

module pi_case_lid_bosses() {
    boss_h = INNER_H;
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_F, BOSS_Y_B])
        translate([x, y, FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = boss_h);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = boss_h);
            }
}


// =====================================================
//   Tray cutouts (functional, unchanged logic)
// =====================================================
module pi_case_standoff_holes() {
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, -0.1])
            cylinder(d = STANDOFF_HOLE_D, h = FLOOR + HAT_H + 0.2);
    }
}

module pi_case_fan_cutout() {
    translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
        rotate([0, 90, 0]) {
            cylinder(d = FAN_APERTURE, h = OUTER_WALL + 0.2);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * FAN_MOUNT_SPG / 2, sy * FAN_MOUNT_SPG / 2, 0])
                    cylinder(d = FAN_SCREW_D, h = OUTER_WALL + 0.2);
        }
}

module pi_case_exhaust_vents() {
    // Original plain vents (retained for reference, replaced by portcullis)
    right_wall_x = FLANGE_W + OUTER_WALL + INNER_W;
    vent_block_h = VENT_COUNT * VENT_SPACING;
    start_z = FAN_CZ - vent_block_h / 2;
    for (i = [0 : VENT_COUNT - 1]) {
        z = start_z + i * VENT_SPACING;
        translate([right_wall_x - 0.1,
                   OUTER_D / 2 - VENT_SLOT_W / 2,
                   z - VENT_SLOT_H / 2])
            cube([OUTER_WALL + 0.2, VENT_SLOT_W, VENT_SLOT_H]);
    }
}

module pi_case_gx12_cutout() {
    translate([FLANGE_W + OUTER_W / 2,
               OUTER_D - 0.1,
               FLOOR + INNER_H / 2])
        rotate([270, 0, 0])
            cylinder(d = GX12_D, h = OUTER_WALL + 0.2, $fn = 32);
}

module pi_case_sma_cutout() {
    translate([FLANGE_W + OUTER_W / 2 + 20,
               OUTER_D - 0.1,
               FLOOR + INNER_H / 2])
        rotate([270, 0, 0])
            cylinder(d = SMA_HOLE_D, h = OUTER_WALL + 0.2, $fn = 32);
}

module pi_case_cable_slots() {
    // HDMI0, HDMI1, USB-C all live on the Pi's HDMI long edge, which faces
    // the case front wall (Y=0). Offsets are measured from the USB/Ethernet
    // short edge, which is the case RIGHT wall (X = PI_X0 + PI5_W).
    hdmi_z = PI_Z0 + HDMI_PORT_H;
    for (offset = [HDMI1_OFFSET, HDMI2_OFFSET]) {
        x = PI_X0 + PI5_W - offset - HDMI_SLOT[0] / 2;
        translate([x, -0.1, hdmi_z])
            cube([HDMI_SLOT[0], OUTER_WALL + 0.2, HDMI_SLOT[1]]);
    }

    // USB-C power: front wall, offset from the USB/Ethernet (right) short edge.
    pwr_x = PI_X0 + PI5_W - PWR_OFFSET - PWR_SLOT[0] / 2;
    pwr_z = PI_Z0 + PWR_PORT_H;
    translate([pwr_x, -0.1, pwr_z])
        cube([PWR_SLOT[0], OUTER_WALL + 0.2, PWR_SLOT[1]]);

    // USB-A stack: right short wall.
    usb_x = FLANGE_W + OUTER_WALL + INNER_W;
    usb_y = PI_Y0 + USB_OFFSET - USB_SLOT[0] / 2;
    usb_z = PI_Z0 + 1;
    translate([usb_x - 0.1, usb_y, usb_z])
        cube([OUTER_WALL + 0.2, USB_SLOT[0], USB_SLOT[1]]);

    // Qwiic + 1-Wire: back wall, near GPIO header long edge.
    translate([FLANGE_W + OUTER_W / 2 - 15 - QWIIC_SLOT[0] / 2,
               OUTER_D - 0.1,
               FLOOR + 2])
        cube([QWIIC_SLOT[0], OUTER_WALL + 0.2, QWIIC_SLOT[1]]);

    translate([FLANGE_W + OUTER_W / 2 - 25 - ONEWIRE_SLOT[0] / 2,
               OUTER_D - 0.1,
               FLOOR + 2])
        cube([ONEWIRE_SLOT[0], OUTER_WALL + 0.2, ONEWIRE_SLOT[1]]);
}

module pi_case_flange_holes() {
    margin = 6;
    for (x = [margin, TOTAL_W - margin],
         y = [margin, OUTER_D - margin])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = BOLT_HEAD_H + 0.1);
        }
}

module pi_case_lid_boss_holes() {
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_F, BOSS_Y_B])
        translate([x, y, FLOOR + INNER_H - 0.1])
            cylinder(d = LID_BOSS_HOLE, h = 1);
}

module pi_case_lid_vents() {
    // Original plain vents (retained for reference, replaced by arrow slits)
    lid_vent_count = 4;
    lid_vent_w = 25;
    lid_vent_spacing = 5;
    cx = FLANGE_W + OUTER_W / 2;
    for (i = [0 : lid_vent_count - 1]) {
        y = OUTER_D / 2 - (lid_vent_count - 1) * lid_vent_spacing / 2
            + i * lid_vent_spacing - VENT_SLOT_H / 2;
        translate([cx - lid_vent_w / 2, y, -0.1])
            cube([lid_vent_w, VENT_SLOT_H, LID_THICK + 0.2]);
    }
}


// =====================================================
//   Castle decorative modules — tray
// =====================================================

// --- Stone mortar grooves (running bond pattern on all 4 walls) ---

// Generates mortar for one wall face in local coords:
//   X = along wall width, Z = up wall height
//   Grooves extend MORTAR_D in +Y direction
module _mortar_face(w, h) {
    // horizontal mortar lines
    for (i = [1 : floor(h / STONE_ROW_H)]) {
        translate([0, 0, i * STONE_ROW_H - MORTAR_W / 2])
            cube([w, MORTAR_D + 0.01, MORTAR_W]);
    }
    // vertical mortar lines, staggered per row (running bond)
    for (row = [0 : floor(h / STONE_ROW_H)]) {
        voff = (row % 2 == 0) ? 0 : STONE_COL_W / 2;
        z0 = row * STONE_ROW_H;
        z1 = min((row + 1) * STONE_ROW_H, h);
        for (x = [voff + STONE_COL_W : STONE_COL_W : w]) {
            translate([x - MORTAR_W / 2, 0, z0])
                cube([MORTAR_W, MORTAR_D + 0.01, z1 - z0]);
        }
    }
}

// Same pattern but grooves extend in +X (for left/right walls)
module _mortar_face_xdir(w, h) {
    for (i = [1 : floor(h / STONE_ROW_H)]) {
        translate([0, 0, i * STONE_ROW_H - MORTAR_W / 2])
            cube([MORTAR_D + 0.01, w, MORTAR_W]);
    }
    for (row = [0 : floor(h / STONE_ROW_H)]) {
        voff = (row % 2 == 0) ? 0 : STONE_COL_W / 2;
        z0 = row * STONE_ROW_H;
        z1 = min((row + 1) * STONE_ROW_H, h);
        for (y = [voff + STONE_COL_W : STONE_COL_W : w]) {
            translate([0, y - MORTAR_W / 2, z0])
                cube([MORTAR_D + 0.01, MORTAR_W, z1 - z0]);
        }
    }
}

module castle_stone_mortar() {
    // Front wall (Y=0 face, grooves cut inward in +Y)
    translate([FLANGE_W, -0.01, FLOOR])
        _mortar_face(OUTER_W, INNER_H);

    // Back wall (Y=OUTER_D face, grooves cut inward in -Y)
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, FLOOR])
        mirror([1, 0, 0])
            mirror([0, 1, 0])
                _mortar_face(OUTER_W, INNER_H);

    // Left wall (X=FLANGE_W face, grooves cut inward in +X)
    translate([FLANGE_W - 0.01, 0, FLOOR])
        _mortar_face_xdir(OUTER_D, INNER_H);

    // Right wall (X=FLANGE_W+OUTER_W face, grooves cut inward in -X)
    translate([FLANGE_W + OUTER_W - MORTAR_D, 0, FLOOR])
        _mortar_face_xdir(OUTER_D, INNER_H);
}


// --- Portcullis exhaust vents (replaces plain horizontal slots) ---

module castle_gothic_arch_2d(w, h) {
    // Pointed ogival arch: rectangular base + two-arc pointed cap
    spring_h = h * 0.6;
    arch_r = w;  // equilateral ogive (radius = span)

    // rectangular base
    square([w, spring_h]);
    // pointed arch cap
    translate([0, spring_h])
        intersection() {
            circle(r = arch_r, $fn = 48);
            translate([w, 0]) circle(r = arch_r, $fn = 48);
            square([w, h - spring_h]);
        }
}

module castle_portcullis_2d(w, h) {
    // Gothic arch outline with vertical bars and crossbar
    difference() {
        castle_gothic_arch_2d(w, h);
        // vertical bars (material left standing in the opening)
        bar_spacing = w / (PORT_BAR_N + 1);
        for (i = [1 : PORT_BAR_N])
            translate([i * bar_spacing - PORT_BAR_W / 2, 0])
                square([PORT_BAR_W, h]);
        // horizontal crossbar
        translate([0, h * 0.4 - PORT_BAR_W / 2])
            square([w, PORT_BAR_W]);
    }
}

module castle_portcullis_vents() {
    right_wall_x = FLANGE_W + OUTER_WALL + INNER_W;

    // Transform: local X -> world Y, local Y -> world Z, local Z -> world X
    // so the 2D arch face maps to the YZ plane and extrudes through the wall
    translate([right_wall_x - 0.1,
               OUTER_D / 2 - PORTCULLIS_W / 2,
               FAN_CZ - PORTCULLIS_H / 2])
        multmatrix([[0, 0, 1, 0],
                    [1, 0, 0, 0],
                    [0, 1, 0, 0]])
            linear_extrude(OUTER_WALL + 0.2)
                castle_portcullis_2d(PORTCULLIS_W, PORTCULLIS_H);
}


// --- Fan intake arch frame ---

module castle_fan_arch() {
    // Raised ring frame around fan aperture on left wall exterior
    translate([FLANGE_W - FAN_FRAME_T, FAN_CY, FAN_CZ])
        rotate([0, 90, 0])
            difference() {
                cylinder(d = FAN_FRAME_OD, h = FAN_FRAME_T, $fn = 48);
                translate([0, 0, -0.1])
                    cylinder(d = FAN_APERTURE, h = FAN_FRAME_T + 0.2, $fn = 48);
            }
}


// --- Sword relief carvings ---

module castle_sword_2d() {
    // Sword silhouette, blade pointing up from origin at grip base
    // pommel
    translate([0, -SWORD_POMMEL_D / 2])
        circle(d = SWORD_POMMEL_D, $fn = 16);
    // grip
    translate([-SWORD_GRIP_W / 2, 0])
        square([SWORD_GRIP_W, SWORD_GRIP_L]);
    // crossguard
    translate([-SWORD_GUARD_W / 2, SWORD_GRIP_L])
        square([SWORD_GUARD_W, SWORD_GUARD_H]);
    // blade (tapered)
    translate([0, SWORD_GRIP_L + SWORD_GUARD_H])
        polygon([
            [-SWORD_BLADE_W / 2, 0],
            [SWORD_BLADE_W / 2, 0],
            [SWORD_TIP_W / 2, SWORD_BLADE_L],
            [-SWORD_TIP_W / 2, SWORD_BLADE_L]
        ]);
}

module castle_sword_relief() {
    // Sword crossing centre: middle of guard
    guard_cy = SWORD_GRIP_L + SWORD_GUARD_H / 2;

    // Front wall: crossed swords
    front_cx = FLANGE_W + OUTER_W / 2;
    front_cz = FLOOR + INNER_H * 0.68;

    for (angle = [25, -25])
        translate([front_cx, -0.01, front_cz])
            // local X -> world X, local Y -> world Z, local Z -> world Y
            multmatrix([[1, 0, 0, 0],
                        [0, 0, 1, 0],
                        [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    rotate([0, 0, angle])
                        translate([0, -guard_cy])
                            castle_sword_2d();

    // Back wall: two standing swords flanking cable cutouts
    for (x_off = [12, OUTER_W - 12])
        translate([FLANGE_W + x_off, OUTER_D + 0.01, FLOOR + INNER_H * 0.55])
            // local X -> world X, local Y -> world Z, local Z -> world -Y
            multmatrix([[1, 0, 0, 0],
                        [0, 0, -1, 0],
                        [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    translate([0, -guard_cy])
                        castle_sword_2d();
}


// =====================================================
//   Castle decorative modules — lid
// =====================================================

// --- Crenellated battlements around lid perimeter ---

module castle_lid_crenellations() {
    period = MERLON_W + CRENEL_W;

    // front edge (Y=0, along X)
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        translate([FLANGE_W + i * period, 0, LID_THICK])
            cube([MERLON_W, OUTER_WALL, MERLON_H]);
    }

    // back edge (Y=OUTER_D-OUTER_WALL, along X)
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        translate([FLANGE_W + i * period, OUTER_D - OUTER_WALL, LID_THICK])
            cube([MERLON_W, OUTER_WALL, MERLON_H]);
    }

    // left edge (X=FLANGE_W, along Y, skip corners)
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        translate([FLANGE_W, OUTER_WALL + i * period, LID_THICK])
            cube([OUTER_WALL, MERLON_W, MERLON_H]);
    }

    // right edge (X=FLANGE_W+OUTER_W-OUTER_WALL, along Y, skip corners)
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        translate([FLANGE_W + OUTER_W - OUTER_WALL,
                   OUTER_WALL + i * period, LID_THICK])
            cube([OUTER_WALL, MERLON_W, MERLON_H]);
    }
}


// --- Heater shield sigil (raised panel) ---

module castle_shield_2d(w, h) {
    // Medieval heater shield: flat top with rounded corners, point at bottom
    hull() {
        translate([-w / 2 + 3, h - 3]) circle(r = 3, $fn = 24);
        translate([w / 2 - 3, h - 3]) circle(r = 3, $fn = 24);
        translate([-w / 2 + 3, h * 0.55]) circle(r = 3, $fn = 24);
        translate([w / 2 - 3, h * 0.55]) circle(r = 3, $fn = 24);
        circle(r = 0.5, $fn = 12);
    }
}

module castle_lid_shield() {
    cx = FLANGE_W + OUTER_W / 2;
    cy = OUTER_D / 2;

    translate([cx, cy - SHIELD_H / 2, LID_THICK]) {
        // shield border (full height)
        linear_extrude(SHIELD_RAISE)
            difference() {
                castle_shield_2d(SHIELD_W, SHIELD_H);
                offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
            }
        // shield field (half height, the recessed interior)
        linear_extrude(SHIELD_RAISE * 0.5)
            offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
        // chevron device (full height, V-shape across the field)
        linear_extrude(SHIELD_RAISE)
            intersection() {
                offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
                castle_chevron_2d(SHIELD_W * 0.5, SHIELD_H * 0.15);
            }
    }
}

module castle_chevron_2d(w, h) {
    // V-shaped heraldic chevron, centred on origin
    chev_t = 2;  // chevron band thickness
    translate([0, SHIELD_H * 0.32])
        difference() {
            polygon([[-w / 2, 0], [0, h], [w / 2, 0],
                     [w / 2, -chev_t], [0, h - chev_t], [-w / 2, -chev_t]]);
        }
}


// --- Arrow slit ventilation (cross-shaped, replaces plain lid vents) ---

module castle_arrow_slit_2d(sw, sh, cw, ch) {
    // Cross-shaped arrow slit
    translate([-sw / 2, -sh / 2]) square([sw, sh]);
    translate([-cw / 2, -ch / 2]) square([cw, ch]);
}

module castle_arrow_slit_vents() {
    cx = FLANGE_W + OUTER_W / 2;
    slit_w = 1.5;
    slit_h = 10;
    cross_w = 5;
    cross_h = 1.5;
    spacing_y = 7;

    // Two columns flanking the shield, 4 slits per column
    for (side = [-1, 1]) {
        x = cx + side * (SHIELD_W / 2 + 8);
        for (j = [0 : 3]) {
            y = OUTER_D / 2 - 1.5 * spacing_y + j * spacing_y;
            translate([x, y, -0.1])
                linear_extrude(LID_THICK + MERLON_H + 0.2)
                    castle_arrow_slit_2d(slit_w, slit_h, cross_w, cross_h);
        }
    }
}
