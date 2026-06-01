// Shitbox Rally — sensor cluster tray v2
//
// 4x2 grid. SEN0460 relocated to ceiling mount — its bay is removed.
// Cell (0,1) re-purposed as WAGO 221-2 cradle for SEN0460 5V passthrough.
// Lid retained by M2.5 screws. Castle theme throughout.
//
// Qwiic chain:
//   Pi -> TCA4307 -> INA228 -> BME680 -> VEML7700 -> LIS3MDL -> SSD1306 -> Buzzer
//   Buzzer -> SEN0460 via modified Qwiic cable exiting left end wall.
//
// Grid layout:
//   Row 0 (back):  TCA4307 | INA228 | BME680  | VEML7700
//   Row 1 (front): WAGO    | Buzzer | SSD1306 | LIS3MDL
//
// WAGO cradle (col 0, row 1): holds WAGO 221-2. Pi 5V wire enters from
//   inside the tray; SEN0460 5V + Qwiic bundle exits through left end wall.
//   Levers face up -- accessible when lid is open.
//
// Print: tray floor-down (flanges on bed). Lid cabin-face-down.
// Units: mm.

$fn = 64;

// ---- PCB sizes (measured with calipers) ----
PCB_QWIIC   = [25, 17.85];
PCB_INA     = [25, 20.3];   // INA228 same footprint as INA219
PCB_BUZZER  = [25, 20];
PCB_DISPLAY = [25, 25];

// ---- Cell geometry ----
CELL_W = 45;
CELL_D = 30;
CELL_H = 18;

WALL       = 1.5;
OUTER_WALL = 2.0;
FLOOR      = 2.0;
END_ZONE   = 9;

// ---- PCB mounting posts (M2.5 self-tap) ----
POST_H_QWIIC   = 10.7;
POST_H_INA     = 8.4;
POST_H_DISPLAY = 13.8;
POST_H_BUZZER  = 10.7;
POST_OD        = 6.0;
POST_PILOT     = 2.1;
HOLE_INSET     = 2.5;

// ---- Mounting flanges (M4 to roof frame) ----
FLANGE_W     = 12;
FLANGE_THICK = FLOOR;
BOLT_D       = 4.5;
BOLT_HEAD_D  = 8.5;

// ---- Lid (M2.5 screw closure) ----
LID_THICK     = 1.6;
LID_LIP_DEPTH = 0.8;
LID_SCREW_D   = 2.7;
LID_BOSS_D    = 6.0;
LID_BOSS_HOLE = 2.1;

// ---- Feature sizes ----
DISP_WINDOW  = [22, 12];
LIGHT_HOLE   = 4;
VENT_SLOT    = [6, 1.5];
VENT_COUNT   = 4;
GRILLE_DIA   = 3;
WIRE_SLOT    = [8, 3];
JUMPER_NOTCH = [10, 5];

// ---- WAGO 221-2 cradle ----
WAGO_L    = 26.5;
WAGO_W    = 17.5;
WAGO_H    = 15.0;
WAGO_TOL  = 0.5;
WAGO_WALL = 2.0;

// ---- Castle theme ----
MORTAR_W    = 0.4;
MORTAR_D    = 0.5;
STONE_ROW_H = 7.0;
STONE_COL_W = 11.0;
BATT_W      = 7.0;
BATT_H      = 5.0;
BATT_GAP    = 5.0;


// =====================================================
//   Derived
// =====================================================
GRID_COLS = 4;
GRID_ROWS = 2;
GRID_W    = GRID_COLS * CELL_W;
GRID_D    = GRID_ROWS * CELL_D + (GRID_ROWS - 1) * WALL;

INNER_W = 2 * END_ZONE + GRID_W;
INNER_D = GRID_D;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;

GRID_X0 = FLANGE_W + OUTER_WALL + END_ZONE;

// Lid screw boss centres -- 4 in end zones, one per row
BOSS_X_L  = FLANGE_W + OUTER_WALL + END_ZONE / 2;
BOSS_X_R  = FLANGE_W + OUTER_WALL + END_ZONE + GRID_W + END_ZONE / 2;
BOSS_Y_R0 = OUTER_WALL + CELL_D / 2;
BOSS_Y_R1 = OUTER_WALL + CELL_D + WALL + CELL_D / 2;

// WAGO cradle centre -- cell (0, 1)
WAGO_CX = GRID_X0 + 0 * CELL_W + CELL_W / 2;
WAGO_CY = OUTER_WALL + 1 * (CELL_D + WALL) + CELL_D / 2;

CELLS = [
    // Row 0 (back): L -> R
    [0, 0, "TCA4307",  PCB_QWIIC,   "none",         POST_H_QWIIC],
    [1, 0, "INA228",   PCB_INA,     "wire_slot",    POST_H_INA],
    [2, 0, "BME680",   PCB_QWIIC,   "vents",        POST_H_QWIIC],
    [3, 0, "VEML7700", PCB_QWIIC,   "light_window", POST_H_QWIIC],
    // Row 1 (front): R -> L  (col 0 = WAGO cradle, no PCB posts)
    [3, 1, "LIS3MDL",  PCB_QWIIC,   "none",         POST_H_QWIIC],
    [2, 1, "SSD1306",  PCB_DISPLAY, "display",      POST_H_DISPLAY],
    [1, 1, "Buzzer",   PCB_BUZZER,  "grille",       POST_H_BUZZER],
];


// =====================================================
//   Main
// =====================================================
tray();
translate([0, OUTER_D + 10, 0]) lid();


// =====================================================
module tray() {
    difference() {
        union() {
            _base_plate();
            _outer_walls();
            _row_divider();
            _lid_bosses();
            _pcb_posts();
            _wago_cradle();
        }
        _side_wall_cutouts();
        _flange_holes();
        _pcb_post_holes();
        _lid_boss_holes();
        _tray_mortar();
    }
}

module lid() {
    difference() {
        union() {
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -LID_LIP_DEPTH])
                cube([INNER_W, INNER_D, LID_LIP_DEPTH + 0.01]);
            _battlements();
        }
        _lid_cell_cutouts();
        _lid_screw_holes();
    }
}


// =====================================================
//   Tray structure
// =====================================================
module _base_plate() {
    translate([FLANGE_W, 0, 0])
        cube([OUTER_W, OUTER_D, FLOOR]);
    for (side = [0, 1])
        translate([side == 0 ? 0 : FLANGE_W + OUTER_W, 0, 0])
            cube([FLANGE_W, OUTER_D, FLANGE_THICK]);
}

module _outer_walls() {
    translate([FLANGE_W, 0, FLOOR])
        difference() {
            cube([OUTER_W, OUTER_D, CELL_H]);
            translate([OUTER_WALL, OUTER_WALL, -0.1])
                cube([INNER_W, INNER_D, CELL_H + 1]);
        }
}

module _row_divider() {
    y = OUTER_WALL + CELL_D;
    translate([FLANGE_W + OUTER_WALL, y, FLOOR])
        difference() {
            cube([INNER_W, WALL, CELL_H]);
            // VEML7700 (col 3, row 0) -> LIS3MDL (col 3, row 1) jump
            notch_x = END_ZONE + 3 * CELL_W + CELL_W / 2 - JUMPER_NOTCH[0] / 2;
            translate([notch_x, -0.1, CELL_H - JUMPER_NOTCH[1]])
                cube([JUMPER_NOTCH[0], WALL + 0.2, JUMPER_NOTCH[1] + 0.1]);
        }
}

// Lid screw bosses in end zones
module _lid_bosses() {
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_R0, BOSS_Y_R1])
        translate([x, y, FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = CELL_H);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = CELL_H);
            }
}

module _lid_boss_holes() {
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_R0, BOSS_Y_R1])
        translate([x, y, -0.1])
            cylinder(d = LID_BOSS_HOLE, h = FLOOR + 2.1);
}

module _pcb_posts() {
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

module _pcb_post_holes() {
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

// WAGO cradle: four-walled pocket in cell (0,1), open at top.
// WAGO drops in from above; both wires enter from the top when lid is open.
module _wago_cradle() {
    pw = WAGO_L + WAGO_TOL;
    pd = WAGO_W + WAGO_TOL;
    ph = WAGO_H;
    translate([WAGO_CX - pw / 2 - WAGO_WALL, WAGO_CY - pd / 2 - WAGO_WALL, FLOOR])
        difference() {
            cube([pw + 2 * WAGO_WALL, pd + 2 * WAGO_WALL, ph + WAGO_WALL]);
            translate([WAGO_WALL, WAGO_WALL, WAGO_WALL])
                cube([pw, pd, ph + 0.1]);
        }
}


// =====================================================
//   Cutouts
// =====================================================
module _side_wall_cutouts() {
    // INA228 battery wires exit through back outer wall (Y=0)
    cx = GRID_X0 + 1 * CELL_W + CELL_W / 2;
    translate([cx - WIRE_SLOT[0] / 2, -0.1, FLOOR + 2])
        cube([WIRE_SLOT[0], OUTER_WALL + 0.2, WIRE_SLOT[1]]);

    // Pi Qwiic cable entry: left end wall, row 0 level
    translate([FLANGE_W - 0.1, OUTER_WALL + CELL_D / 2 - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 4]);

    // Pi 5V cable entry: left end wall, row 1 level (feeds WAGO cradle)
    translate([FLANGE_W - 0.1, WAGO_CY - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 4]);

    // SEN0460 exit bundle (5V + Qwiic): left end wall, upper slot at row 1
    translate([FLANGE_W - 0.1, WAGO_CY - 5, FLOOR + CELL_H - 7])
        cube([OUTER_WALL + 0.2, 10, 6]);
}

module _flange_holes() {
    margin = 6;
    for (x = [margin, TOTAL_W - margin], y = [margin, OUTER_D - margin])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = 1.5);
        }
}


// =====================================================
//   Lid
// =====================================================
module _lid_cell_cutouts() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; feat = c[4];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        translate([cx, cy, -(LID_LIP_DEPTH + 0.1)])
            _lid_feature(feat);
    }
}

module _lid_feature(feat) {
    h = LID_THICK + LID_LIP_DEPTH + 0.2;
    if (feat == "display")
        translate([-DISP_WINDOW[0] / 2, -DISP_WINDOW[1] / 2, 0])
            cube([DISP_WINDOW[0], DISP_WINDOW[1], h]);
    else if (feat == "light_window")
        cylinder(d = LIGHT_HOLE, h = h);
    else if (feat == "grille") {
        cylinder(d = GRILLE_DIA, h = h);
        for (a = [0:90:359])
            rotate([0, 0, a])
                translate([6, 0, 0])
                    cylinder(d = GRILLE_DIA, h = h);
    } else if (feat == "vents") {
        spacing = 3;
        for (i = [0 : VENT_COUNT - 1])
            translate([-VENT_SLOT[0] / 2,
                       (i - (VENT_COUNT - 1) / 2) * spacing - VENT_SLOT[1] / 2, 0])
                cube([VENT_SLOT[0], VENT_SLOT[1], h]);
    }
}

module _lid_screw_holes() {
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_R0, BOSS_Y_R1])
        translate([x, y, -(LID_LIP_DEPTH + 0.1)])
            cylinder(d = LID_SCREW_D, h = LID_THICK + LID_LIP_DEPTH + 1);
}


// =====================================================
//   Castle theme
// =====================================================
module _battlements() {
    top_z = LID_THICK;
    // Long walls (run in X)
    for (x = [FLANGE_W : BATT_W + BATT_GAP : FLANGE_W + OUTER_W - BATT_W])
        for (y_pos = [0, OUTER_D - BATT_W])
            translate([x, y_pos, top_z])
                cube([BATT_W, BATT_W, BATT_H]);
    // Short end walls (run in Y)
    for (y = [0 : BATT_W + BATT_GAP : OUTER_D - BATT_W])
        for (x_pos = [FLANGE_W, FLANGE_W + OUTER_W - BATT_W])
            translate([x_pos, y, top_z])
                cube([BATT_W, BATT_W, BATT_H]);
}

module _mortar_face_y(w, h) {
    for (i = [1 : floor(h / STONE_ROW_H)])
        translate([0, 0, i * STONE_ROW_H - MORTAR_W / 2])
            cube([w, MORTAR_D + 0.01, MORTAR_W]);
    for (row = [0 : floor(h / STONE_ROW_H)]) {
        voff = (row % 2 == 0) ? 0 : STONE_COL_W / 2;
        z0 = row * STONE_ROW_H;
        z1 = min((row + 1) * STONE_ROW_H, h);
        for (x = [voff + STONE_COL_W : STONE_COL_W : w])
            translate([x - MORTAR_W / 2, 0, z0])
                cube([MORTAR_W, MORTAR_D + 0.01, z1 - z0]);
    }
}

module _mortar_face_x(w, h) {
    for (i = [1 : floor(h / STONE_ROW_H)])
        translate([0, 0, i * STONE_ROW_H - MORTAR_W / 2])
            cube([MORTAR_D + 0.01, w, MORTAR_W]);
    for (row = [0 : floor(h / STONE_ROW_H)]) {
        voff = (row % 2 == 0) ? 0 : STONE_COL_W / 2;
        z0 = row * STONE_ROW_H;
        z1 = min((row + 1) * STONE_ROW_H, h);
        for (y = [voff + STONE_COL_W : STONE_COL_W : w])
            translate([0, y - MORTAR_W / 2, z0])
                cube([MORTAR_D + 0.01, MORTAR_W, z1 - z0]);
    }
}

module _tray_mortar() {
    h = CELL_H;
    // Back wall (Y=0 face)
    translate([FLANGE_W, -0.01, FLOOR])
        _mortar_face_y(OUTER_W, h);
    // Front wall (Y=OUTER_D face)
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, FLOOR])
        mirror([1, 0, 0]) mirror([0, 1, 0])
            _mortar_face_y(OUTER_W, h);
    // Left end wall (X=FLANGE_W face)
    translate([FLANGE_W - 0.01, 0, FLOOR])
        _mortar_face_x(OUTER_D, h);
    // Right end wall
    translate([FLANGE_W + OUTER_W + 0.01, OUTER_D, FLOOR])
        mirror([0, 1, 0])
            _mortar_face_x(OUTER_D, h);
}
