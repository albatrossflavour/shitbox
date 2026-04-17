// Shitbox Rally — Pi 5 stack enclosure
//
// Stack (bottom to top): NVMe HAT → Pi 5 → active cooler → GPIO ext → perma-proto
// Installed orientation: NVMe HAT on floor, HDMI ports face LONG EDGE (front),
//                        USB/Ethernet face SHORT EDGE (right)
//
// All key dimensions measured with calipers 2026-04-17 ±0.5mm:
//   Total stack height  = 65.0  (NVMe HAT bottom to perma-proto top)
//   NVMe HAT height     = 20.0  (floor to Pi 5 PCB bottom)
//   Pi 5 board          = 85.0 × 56.0  (verified RPi mechanical drawing)
//   Mounting holes       = 58.0 × 49.0 spacing, 3.5mm inset (verified RPi mechanical drawing)
//
// Fan: 40mm Noctua NF-A4x10 5V (to be purchased). Parametric — change FAN_W if different.
//
// Units: mm.

$fn = 64;

// ---- Print / material ----
OUTER_WALL = 2.0;
FLOOR      = 2.0;
PCB_TOL    = 0.6;        // total clearance (0.3mm per side)

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
// HDMI micro ports on long edge (front wall, Y=0 side)
HDMI1_OFFSET  = 26.0;    // centre of HDMI0 from left board edge
HDMI2_OFFSET  = 39.5;    // centre of HDMI1 from left board edge
HDMI_PORT_H   = 3.5;     // port height above Pi PCB

// USB-A stack on short edge (right wall, X=PI5_W side)
USB_OFFSET    = 29.0;    // centre of USB stack from front board edge
USB_PORT_H    = 15.5;    // stacked USB-A height above PCB

// USB-C power on short edge
PWR_OFFSET    = 11.5;    // centre of USB-C from front board edge
PWR_PORT_H    = 3.5;     // USB-C height above PCB

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
FLANGE_THICK  = FLOOR;
BOLT_D        = 4.5;      // M4 clearance
BOLT_HEAD_D   = 8.5;      // M4 washer/head counterbore

// ---- Lid ----
LID_THICK     = 1.6;
LID_SCREW_D   = 2.7;      // M2.5 clearance
LID_BOSS_D    = 6;
LID_BOSS_HOLE = 2.1;      // pilot for M2.5 self-tap

// ---- Cable exit slots (right-angle adapters, per Research pitfall 3) ----
HDMI_SLOT  = [14, 8];     // right-angle HDMI adapter body
USB_SLOT   = [14, 17];    // stacked USB-A ports
PWR_SLOT   = [10, 6];     // USB-C power cable
QWIIC_SLOT = [6, 4];      // Qwiic/STEMMA QT cable
ONEWIRE_SLOT = [5, 3];    // DS18B20 1-Wire cable

// ---- Exhaust vents ----
VENT_SLOT_W   = 20;
VENT_SLOT_H   = 1.5;
VENT_COUNT    = 6;
VENT_SPACING  = 4;

// ---- Derived dimensions ----
INNER_W = PI5_W + PCB_TOL;
INNER_D = PI5_D + PCB_TOL;
INNER_H = STACK_H + 5;    // 5mm clearance above stack top
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;
TOTAL_D = OUTER_D;

// Pi PCB origin relative to inner cavity
PI_X0 = FLANGE_W + OUTER_WALL + PCB_TOL / 2;
PI_Y0 = OUTER_WALL + PCB_TOL / 2;
PI_Z0 = FLOOR + HAT_H;   // Pi PCB sits on top of NVMe HAT

// Fan centre: on the left wall (X=FLANGE_W side), centred on cooler height
// Cooler sits on Pi SoC, roughly centre of board, starts at PI_Z0 + 1.6 (PCB thickness)
FAN_CZ = PI_Z0 + 1.6 + 15;  // centre fan on cooler mid-height
FAN_CY = OUTER_D / 2;        // centred along depth

// Lid boss positions: four corners of the interior
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
module pi_case_tray() {
    difference() {
        union() {
            pi_case_base_plate();
            pi_case_outer_walls();
            pi_case_standoff_bosses();
            pi_case_lid_bosses();
        }
        pi_case_standoff_holes();
        pi_case_fan_cutout();
        pi_case_exhaust_vents();
        pi_case_gx12_cutout();
        pi_case_sma_cutout();
        pi_case_cable_slots();
        pi_case_flange_holes();
        pi_case_lid_boss_holes();
    }
}

module pi_case_lid() {
    difference() {
        union() {
            // main plate
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            // inner lip drops into tray opening
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -0.8])
                cube([INNER_W, INNER_D, 0.8 + 0.01]);
        }
        // screw holes
        for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_F, BOSS_Y_B])
            translate([x, y, -0.1])
                cylinder(d = LID_SCREW_D, h = LID_THICK + 1);
        // ventilation slots above cooler area
        pi_case_lid_vents();
    }
}


// =====================================================
//   Tray solid components
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
    // 4 bosses at Pi mounting hole positions, rising from floor
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
//   Tray cutouts
// =====================================================
module pi_case_standoff_holes() {
    // M2.5 clearance through bosses AND floor (through-hole for rubber standoff bolt)
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, -0.1])
            cylinder(d = STANDOFF_HOLE_D, h = FLOOR + HAT_H + 0.2);
    }
}

module pi_case_fan_cutout() {
    // Fan on left wall (X = FLANGE_W), centred on cooler height
    translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
        rotate([0, 90, 0]) {
            // airflow aperture
            cylinder(d = FAN_APERTURE, h = OUTER_WALL + 0.2);
            // M3 mounting holes
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * FAN_MOUNT_SPG / 2, sy * FAN_MOUNT_SPG / 2, 0])
                    cylinder(d = FAN_SCREW_D, h = OUTER_WALL + 0.2);
        }
}

module pi_case_exhaust_vents() {
    // Horizontal slots on right wall (opposite fan intake)
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
    // GX12 on rear wall (Y = OUTER_D side), centred horizontally
    translate([FLANGE_W + OUTER_W / 2,
               OUTER_D - 0.1,
               FLOOR + INNER_H / 2])
        rotate([270, 0, 0])
            cylinder(d = GX12_D, h = OUTER_WALL + 0.2, $fn = 32);
}

module pi_case_sma_cutout() {
    // SMA on rear wall, offset from GX12
    translate([FLANGE_W + OUTER_W / 2 + 20,
               OUTER_D - 0.1,
               FLOOR + INNER_H / 2])
        rotate([270, 0, 0])
            cylinder(d = SMA_HOLE_D, h = OUTER_WALL + 0.2, $fn = 32);
}

module pi_case_cable_slots() {
    // HDMI slots on front wall (Y = 0 side), aligned with Pi HDMI ports
    hdmi_z = PI_Z0 + HDMI_PORT_H;
    for (offset = [HDMI1_OFFSET, HDMI2_OFFSET]) {
        x = PI_X0 + offset - HDMI_SLOT[0] / 2;
        translate([x, -0.1, hdmi_z])
            cube([HDMI_SLOT[0], OUTER_WALL + 0.2, HDMI_SLOT[1]]);
    }

    // USB slot on right short-edge wall (X = FLANGE_W + OUTER_W side)
    usb_x = FLANGE_W + OUTER_WALL + INNER_W;
    usb_y = PI_Y0 + USB_OFFSET - USB_SLOT[0] / 2;
    usb_z = PI_Z0 + 1;  // just above Pi PCB
    translate([usb_x - 0.1, usb_y, usb_z])
        cube([OUTER_WALL + 0.2, USB_SLOT[0], USB_SLOT[1]]);

    // USB-C power slot on right short-edge wall
    pwr_y = PI_Y0 + PWR_OFFSET - PWR_SLOT[0] / 2;
    pwr_z = PI_Z0 + PWR_PORT_H;
    translate([usb_x - 0.1, pwr_y, pwr_z])
        cube([OUTER_WALL + 0.2, PWR_SLOT[0], PWR_SLOT[1]]);

    // Qwiic cable exit on rear wall
    translate([FLANGE_W + OUTER_W / 2 - 15 - QWIIC_SLOT[0] / 2,
               OUTER_D - 0.1,
               FLOOR + 2])
        cube([QWIIC_SLOT[0], OUTER_WALL + 0.2, QWIIC_SLOT[1]]);

    // 1-Wire cable exit on rear wall
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
                cylinder(d = BOLT_HEAD_D, h = 1.5);
        }
}

module pi_case_lid_boss_holes() {
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_F, BOSS_Y_B])
        translate([x, y, FLOOR + INNER_H - 0.1])
            cylinder(d = LID_BOSS_HOLE, h = 1);
}

module pi_case_lid_vents() {
    // Ventilation slots in lid above cooler area
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
