// Shitbox Rally — ceiling-mounted Qwiic sensor cluster
//
// Grid section (4x2) + dedicated SEN0460 air quality bay.
// Tray floor bolts to ceiling (flanges face up). Lid faces cabin (down).
// Boards mounted component-side-up in the tray — sensors face the lid,
// which faces the cabin when ceiling-mounted. All feature cutouts (display
// window, sensor vents, light hole, buzzer grille) are in the lid.
//
// Grid sensors:
//   Row 0 (back, from driver's left): TCA4307 | INA219  | BME680  | VEML7700
//   Row 1 (front, from driver's left): empty  | Buzzer  | SSD1306 | LSM6DSOX
//
// SEN0460 bay: behind front row, centred in tray width.
//   Air intake faces lid (cabin-side). 5V power cable routes separately.
//
// Daisy-chain order (TCA4307 first as I2C bus protector):
//   Pi -> TCA4307 -> INA219 -> BME680 -> VEML7700 -> LSM6DSOX
//      -> SSD1306 -> Buzzer -> SEN0460
//
// Snake routing: row 0 left-to-right, jump at col 3, row 1 right-to-left.
// Every consecutive pair is in adjacent cells — all hops under 50mm.
//
// Print orientation:
//   Tray — flanges down on bed (open top faces up). No supports.
//   Lid  — cabin face DOWN on bed. The inner plug extrudes upward from
//          the centre of the top plate. Do NOT invert the lid and print
//          plug-down, or the top plate's overhanging perimeter will print
//          badly. Branding goes on a vinyl sticker, not engraved.
//
// Units: mm.

$fn = 64;

// ---- PCB sizes (measured with calipers) ----
PCB_QWIIC   = [25, 17.85];  // TCA4307, BME680, VEML7700, LSM6DSOX
PCB_INA     = [25, 20.3];   // INA219
PCB_BUZZER  = [25, 20];     // buzzer module
PCB_DISPLAY = [25, 25];     // SSD1306 OLED
PCB_TOL     = 0.6;          // total clearance (0.3mm per side)

// ---- Cell geometry ----
CELL_W     = 45;         // cable-direction pitch (25mm PCB + connectors + 50mm cable slack)
CELL_D     = 30;         // perpendicular to cable direction
CELL_H     = 18;         // interior height (accommodates SEN0460 + generous cable routing)

WALL       = 1.5;        // internal divider thickness (row divider, grid-SEN divider)
OUTER_WALL = 2.0;
FLOOR      = 2.0;

// End zones house lid-screw bosses, clear of PCB cells.
// Left end zone also serves as Pi cable entry.
END_ZONE   = 9;

// ---- PCB mounting posts (M2.5 self-tap) ----
// Post heights sized so components sit ~1mm below lid inner face.
// Formula: CELL_H - PCB_THICK - component_height - 1mm clearance
PCB_THICK      = 1.6;    // standard PCB thickness
POST_H_QWIIC  = 10.7;   // TCA4307, BME680, VEML7700, LSM6DSOX (4.7mm connector height)
POST_H_INA    = 8.4;     // INA219 (7mm component height)
POST_H_DISPLAY = 13.8;   // SSD1306 mounted inverted (1.6mm to screen face)
POST_H_BUZZER = 10.7;    // buzzer module (4.7mm component height)
POST_OD        = 6.0;    // increased from 4.5 — stops splitting on screw insertion
POST_PILOT     = 2.1;    // self-tap pilot for M2.5
HOLE_INSET     = 2.5;    // distance from PCB edge to hole centre

// ---- Mounting flanges (M4 to roof frame) ----
FLANGE_W      = 12;
FLANGE_THICK  = FLOOR;
BOLT_D        = 4.5;     // M4 clearance
BOLT_HEAD_D   = 8.5;     // M4 washer / head clearance (counterbore)

// ---- Lid ----
LID_THICK     = 1.6;
LID_LIP_DEPTH = 0.8;      // inner plug that drops into the tray rim (under LID_THICK)
LID_SCREW_D   = 2.7;     // M2.5 clearance
LID_BOSS_D    = 6;
LID_BOSS_HOLE = 2.1;     // pilot hole for M2.5 self-tap

// ---- Feature sizes ----
DISP_WINDOW   = [22, 12];  // SSD1306 active area
LIGHT_HOLE    = 4;          // VEML7700 window diameter
VENT_SLOT     = [6, 1.5];  // BME680 vent slot
VENT_COUNT    = 4;
GRILLE_DIA    = 3;          // buzzer grille hole
WIRE_SLOT     = [8, 3];    // INA219 shunt-wire exit in back wall
JUMPER_NOTCH  = [10, 5];   // cable notch through dividers (widened for Qwiic plugs)

// ---- SEN0460 air quality sensor ----
SEN_W        = 72.5;     // width
SEN_D        = 40;        // depth
SEN_H        = 13.85;     // height
SEN_CONN_W   = 12;        // connector width (on one end)
SEN_TOL      = 0.6;       // clearance
SEN_INSET    = 2.5;       // mounting hole inset from edge (standard)
SEN_POST_H   = 2;         // shorter posts (taller sensor, intake gap below lid vents)

SEN_INNER_W  = SEN_W + SEN_TOL;
SEN_INNER_D  = SEN_D + SEN_TOL;

// ---- SEN0460 lid ventilation ----
SEN_VENT_W     = 50;      // vent slot width (most of sensor width)
SEN_VENT_H     = 1.5;     // vent slot height
SEN_VENT_COUNT = 8;       // number of vent slots
SEN_VENT_SPACE = 4;       // spacing between vent slots


// =====================================================
//   Derived dimensions
// =====================================================
GRID_COLS = 4;
GRID_ROWS = 2;
GRID_W  = GRID_COLS * CELL_W;
GRID_D  = GRID_ROWS * CELL_D + (GRID_ROWS - 1) * WALL;

INNER_W = 2 * END_ZONE + GRID_W;
INNER_D = GRID_D + WALL + SEN_INNER_D;  // grid + divider + SEN bay
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;

// x offset from flange origin to first cell
GRID_X0 = FLANGE_W + OUTER_WALL + END_ZONE;

// SEN bay position (centred in tray width)
SEN_BAY_Y0 = OUTER_WALL + GRID_D + WALL;
SEN_BAY_X0 = FLANGE_W + OUTER_WALL + (INNER_W - SEN_INNER_W) / 2;

// SEN0460 centre
SEN_CX = SEN_BAY_X0 + SEN_INNER_W / 2;
SEN_CY = SEN_BAY_Y0 + SEN_INNER_D / 2;

// Lid boss centres: 4 in grid end zones + 2 in SEN bay
BOSS_X_L = FLANGE_W + OUTER_WALL + END_ZONE / 2;
BOSS_X_R = FLANGE_W + OUTER_WALL + END_ZONE + GRID_W + END_ZONE / 2;
BOSS_Y_R0 = OUTER_WALL + CELL_D / 2;                       // grid row 0
BOSS_Y_R1 = OUTER_WALL + CELL_D + WALL + CELL_D / 2;       // grid row 1
BOSS_Y_SEN = SEN_BAY_Y0 + SEN_INNER_D / 2;                 // SEN bay


// ---- Cell table: [col, row, name, pcb_size, feature, post_h] ----
// Snake path: row 0 L->R, jump at col 3, row 1 R->L
CELLS = [
    // Row 0 (back): chain L->R
    [0, 0, "TCA4307",  PCB_QWIIC,   "none",         POST_H_QWIIC],
    [1, 0, "INA219",   PCB_INA,     "wire_slot",    POST_H_INA],
    [2, 0, "BME680",   PCB_QWIIC,   "vents",        POST_H_QWIIC],
    [3, 0, "VEML7700", PCB_QWIIC,   "light_window", POST_H_QWIIC],
    // Row 1 (front): chain R->L
    [3, 1, "LSM6DSOX", PCB_QWIIC,   "none",         POST_H_QWIIC],
    [2, 1, "SSD1306",  PCB_DISPLAY, "display",      POST_H_DISPLAY],
    [1, 1, "Buzzer",   PCB_BUZZER,  "grille",       POST_H_BUZZER],
    // (0,1) empty — cable routing to SEN0460 bay
];


// =====================================================
//   Main — render tray and lid side by side
// =====================================================
tray();
translate([0, OUTER_D + FLANGE_W + 10, 0]) lid();


// =====================================================
module tray() {
    difference() {
        union() {
            base_plate();
            outer_walls();
            row_divider();
            grid_sen_divider();
            lid_bosses();
            pcb_posts();
            sen_posts();
        }
        side_wall_cutouts();
        flange_holes();
        pcb_post_holes();
        sen_post_holes();
    }
}

module lid() {
    difference() {
        union() {
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -LID_LIP_DEPTH])
                cube([INNER_W, INNER_D, LID_LIP_DEPTH + 0.01]);
        }
        // screw holes: grid bosses + SEN bay bosses (clear through plug + top plate)
        for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_R0, BOSS_Y_R1])
            translate([x, y, -(LID_LIP_DEPTH + 0.1)])
                cylinder(d = LID_SCREW_D, h = LID_THICK + LID_LIP_DEPTH + 1);
        for (x = [BOSS_X_L, BOSS_X_R])
            translate([x, BOSS_Y_SEN, -(LID_LIP_DEPTH + 0.1)])
                cylinder(d = LID_SCREW_D, h = LID_THICK + LID_LIP_DEPTH + 1);
        // sensor feature cutouts (cabin-facing)
        lid_cell_cutouts();
        lid_sen_vents();
    }
}


// =====================================================
//   Tray components
// =====================================================
module base_plate() {
    union() {
        translate([FLANGE_W, 0, 0])
            cube([OUTER_W, OUTER_D, FLOOR]);
        for (side = [0, 1])
            translate([side == 0 ? 0 : FLANGE_W + OUTER_W, 0, 0])
                cube([FLANGE_W, OUTER_D, FLANGE_THICK]);
    }
}

module outer_walls() {
    translate([FLANGE_W, 0, FLOOR])
        difference() {
            cube([OUTER_W, OUTER_D, CELL_H]);
            translate([OUTER_WALL, OUTER_WALL, -0.1])
                cube([INNER_W, INNER_D, CELL_H + 1]);
        }
}

module row_divider() {
    // Between grid row 0 and row 1
    y = OUTER_WALL + CELL_D;
    translate([FLANGE_W + OUTER_WALL, y, FLOOR])
        difference() {
            cube([INNER_W, WALL, CELL_H]);
            // cable notch at col 3 for VEML7700 -> LSM6DSOX jump
            notch_x = END_ZONE + 3 * CELL_W + CELL_W / 2 - JUMPER_NOTCH[0] / 2;
            translate([notch_x, -0.1, CELL_H - JUMPER_NOTCH[1]])
                cube([JUMPER_NOTCH[0], WALL + 0.2, JUMPER_NOTCH[1] + 0.1]);
        }
}

module grid_sen_divider() {
    // Between grid front row and SEN0460 bay
    y = OUTER_WALL + GRID_D;
    translate([FLANGE_W + OUTER_WALL, y, FLOOR])
        difference() {
            cube([INNER_W, WALL, CELL_H]);
            // Qwiic cable notch: buzzer(1,1) -> SEN0460 bay
            notch_x = END_ZONE + 1 * CELL_W + CELL_W / 2 - JUMPER_NOTCH[0] / 2;
            translate([notch_x, -0.1, CELL_H - JUMPER_NOTCH[1]])
                cube([JUMPER_NOTCH[0], WALL + 0.2, JUMPER_NOTCH[1] + 0.1]);
            // 5V power cable notch: routes through grid to Pi cable exit
            pwr_x = END_ZONE / 2 - 4;
            translate([pwr_x, -0.1, CELL_H - JUMPER_NOTCH[1]])
                cube([8, WALL + 0.2, JUMPER_NOTCH[1] + 0.1]);
        }
}

module lid_bosses() {
    boss_h = CELL_H;
    // Grid section: 4 bosses in end zones
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_R0, BOSS_Y_R1])
        translate([x, y, FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = boss_h);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = boss_h);
            }
    // SEN bay: 2 bosses flanking the sensor
    for (x = [BOSS_X_L, BOSS_X_R])
        translate([x, BOSS_Y_SEN, FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = boss_h);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = boss_h);
            }
}

module pcb_posts() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; pcb = c[3]; ph = c[5];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        dx = pcb[0] / 2 - HOLE_INSET;
        dy = pcb[1] / 2 - HOLE_INSET;
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx * dx, cy + sy * dy, FLOOR])
                cylinder(d = POST_OD, h = ph);
    }
}

module sen_posts() {
    // SEN0460 mounting posts (shorter — taller sensor needs intake gap)
    dx = SEN_W / 2 - SEN_INSET;
    dy = SEN_D / 2 - SEN_INSET;
    for (sx = [-1, 1], sy = [-1, 1])
        translate([SEN_CX + sx * dx, SEN_CY + sy * dy, FLOOR])
            cylinder(d = POST_OD, h = SEN_POST_H);
}


// =====================================================
//   Cutouts
// =====================================================
module lid_cell_cutouts() {
    // Feature cutouts through the lid (cabin-facing side)
    for (c = CELLS) {
        col  = c[0];
        row  = c[1];
        feat = c[4];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        translate([cx, cy, -(LID_LIP_DEPTH + 0.1)]) lid_feature(feat);
    }
}

module lid_feature(feat) {
    // Height spans the plug + top plate so every cutout passes clean through.
    h = LID_THICK + LID_LIP_DEPTH + 0.2;
    if (feat == "display") {
        translate([-DISP_WINDOW[0] / 2, -DISP_WINDOW[1] / 2, 0])
            cube([DISP_WINDOW[0], DISP_WINDOW[1], h]);
    } else if (feat == "light_window") {
        cylinder(d = LIGHT_HOLE, h = h);
    } else if (feat == "grille") {
        cylinder(d = GRILLE_DIA, h = h);
        for (a = [0:90:359])
            rotate([0, 0, a])
                translate([6, 0, 0])
                    cylinder(d = GRILLE_DIA, h = h);
    } else if (feat == "vents") {
        spacing = 3;
        for (i = [0 : VENT_COUNT - 1])
            translate([-VENT_SLOT[0] / 2,
                       (i - (VENT_COUNT - 1) / 2) * spacing - VENT_SLOT[1] / 2,
                       0])
                cube([VENT_SLOT[0], VENT_SLOT[1], h]);
    }
    // "wire_slot" handled in side_wall_cutouts (tray wall feature)
    // "none" = no cutout
}

module lid_sen_vents() {
    // Ventilation slots in lid above SEN0460 air intake
    // Cabin air flows through lid vents into the gap above the sensor intake
    for (i = [0 : SEN_VENT_COUNT - 1]) {
        y = SEN_CY - (SEN_VENT_COUNT - 1) * SEN_VENT_SPACE / 2
            + i * SEN_VENT_SPACE;
        translate([SEN_CX - SEN_VENT_W / 2, y - SEN_VENT_H / 2, -(LID_LIP_DEPTH + 0.1)])
            cube([SEN_VENT_W, SEN_VENT_H, LID_THICK + LID_LIP_DEPTH + 0.2]);
    }
}

module side_wall_cutouts() {
    // INA219 shunt wires exit through the BACK outer wall (Y=0)
    ina_col = 1;  // INA219 at column 1
    cx = GRID_X0 + ina_col * CELL_W + CELL_W / 2;
    translate([cx - WIRE_SLOT[0] / 2, -0.1, FLOOR + 2])
        cube([WIRE_SLOT[0], OUTER_WALL + 0.2, WIRE_SLOT[1]]);

    // Pi Qwiic cable entry: slot in LEFT outer wall into the left end zone
    // Aligned with row 0 (back row, where TCA4307 sits)
    entry_y = OUTER_WALL + CELL_D / 2;
    translate([FLANGE_W - 0.1, entry_y - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 4]);

    // SEN0460 5V power cable exit: slot in LEFT outer wall at SEN bay level
    translate([FLANGE_W - 0.1, SEN_CY - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 4]);

    // SEN0460 Qwiic cable alternative exit: slot in FRONT outer wall (new back)
    translate([SEN_CX - 5, OUTER_D - OUTER_WALL - 0.1, FLOOR + 2])
        cube([10, OUTER_WALL + 0.2, 4]);
}

module flange_holes() {
    margin = 6;
    for (x = [margin, TOTAL_W - margin],
         y = [margin, OUTER_D - margin])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = 1.5);
        }
}

module pcb_post_holes() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; pcb = c[3]; ph = c[5];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        dx = pcb[0] / 2 - HOLE_INSET;
        dy = pcb[1] / 2 - HOLE_INSET;
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx * dx, cy + sy * dy, FLOOR + 0.5])
                cylinder(d = POST_PILOT, h = ph + 0.5);
    }
}

module sen_post_holes() {
    dx = SEN_W / 2 - SEN_INSET;
    dy = SEN_D / 2 - SEN_INSET;
    for (sx = [-1, 1], sy = [-1, 1])
        translate([SEN_CX + sx * dx, SEN_CY + sy * dy, FLOOR + 0.5])
            cylinder(d = POST_PILOT, h = SEN_POST_H + 0.5);
}
