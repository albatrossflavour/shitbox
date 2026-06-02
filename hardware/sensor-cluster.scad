// Shitbox Rally — sensor cluster tray v3
//
// 3×3 grid, 38 mm square cells. LSM6DSOX at centre (1,1).
// Two WAGO 221-2 saddles on lid exterior: INA228 sense (V+/V-) and SEN0460 5 V.
// Lid retained by 4× M2.5 screws. Castle theme throughout.
//
// Grid layout (row 0 = back = car-front edge):
//   Row 0:  TCA4307  | INA228   | BME680
//   Row 1:  VEML7700 | LSM6DSOX | LIS3MDL
//   Row 2:  SSD1306  | Buzzer   | [empty]
//
// Print: tray floor-down. Lid outer-face-up (saddles protrude up; flip from v2).
// Units: mm.

$fn = 64;

// ── PCB footprints ──────────────────────────────────────────────
PCB_QWIIC   = [25, 17.85];
PCB_INA     = [25, 20.3];
PCB_BUZZER  = [25, 20];
PCB_DISPLAY = [25, 25];

// ── Cell geometry ───────────────────────────────────────────────
CELL_W = 38;
CELL_D = 38;
CELL_H = 18;

WALL       = 1.5;
OUTER_WALL = 2.0;
FLOOR      = 2.0;
END_ZONE   = 9;

// ── PCB posts (M2.5 self-tap) ───────────────────────────────────
// Height is thread-engagement only; connector clearance no longer needed.
POST_H     = 5.0;
POST_OD    = 6.0;
POST_PILOT = 2.1;
HOLE_INSET = 2.5;

// ── Mounting flanges (M4 to roof frame) ─────────────────────────
FLANGE_W     = 12;
FLANGE_THICK = FLOOR;
BOLT_D       = 4.5;
BOLT_HEAD_D  = 8.5;

// ── Lid ─────────────────────────────────────────────────────────
LID_THICK     = 1.6;
LID_LIP_DEPTH = 0.8;
LID_SCREW_D   = 2.7;
LID_BOSS_D    = 6.0;
LID_BOSS_HOLE = 2.1;

// ── Lid cell features ───────────────────────────────────────────
DISP_WINDOW = [22, 12];
LIGHT_HOLE  = 20;
VENT_SLOT   = [6, 1.5];
VENT_COUNT  = 4;
GRILLE_DIA  = 3;
NOTCH_W     = 10;
NOTCH_H     = 8;

// ── WAGO 221-2 saddle (measured from datasheet) ─────────────────
// 18.2 × 13.1 × 10.2 mm (depth × width × height, levers up).
// Saddle open at +Y end; WAGO slides in from front.
// Lid printed outer-face-up so saddles clear the bed.
WAGO_D      = 18.2;   // depth (Y in saddle frame)
WAGO_W      = 13.1;   // width (X)
WAGO_H      = 10.2;   // height (Z, levers at top)
WAGO_TOL    = 0.4;
WAGO_WALL   = 2.0;
WAGO_SLOT_W = 8;      // cable slot through lid
WAGO_SLOT_D = 4;

// ── Castle theme ─────────────────────────────────────────────────
MORTAR_W    = 0.4;
MORTAR_D    = 0.5;
STONE_ROW_H = 7.0;
STONE_COL_W = 11.0;
BATT_W      = 7.0;
BATT_H      = 5.0;
BATT_GAP    = 5.0;

// ── Derived ──────────────────────────────────────────────────────
GRID_COLS = 3;
GRID_ROWS = 3;
GRID_W    = GRID_COLS * CELL_W;
GRID_D    = GRID_ROWS * CELL_D + (GRID_ROWS - 1) * WALL;

INNER_W = 2 * END_ZONE + GRID_W;
INNER_D = GRID_D;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;

GRID_X0 = FLANGE_W + OUTER_WALL + END_ZONE;

// Boss centres at OUTER_D/3 and 2×OUTER_D/3 — clear of all row centres.
// Row centres (approx): 21 mm, 60.5 mm, 100 mm. Bosses at ~40 and ~81 mm.
BOSS_X_L = FLANGE_W + OUTER_WALL + END_ZONE / 2;
BOSS_X_R = FLANGE_W + OUTER_WALL + END_ZONE + GRID_W + END_ZONE / 2;
BOSS_Y_A = OUTER_D / 3;
BOSS_Y_B = 2 * OUTER_D / 3;

BOSS_XY = [
    [BOSS_X_L, BOSS_Y_A], [BOSS_X_L, BOSS_Y_B],
    [BOSS_X_R, BOSS_Y_A], [BOSS_X_R, BOSS_Y_B],
];

// WAGO saddle centres on lid outer face.
// INA pair: back edge, col 1 — directly above INA228.
// SEN0460: front edge, col 1 — adjacent to Buzzer; saddle opens toward tray interior (-Y).
// INA V+ and V- are adjacent; offset = half-saddle-width + 1 mm gap.
_wago_back_cy  = WAGO_D / 2 + WAGO_WALL + OUTER_WALL;
_wago_front_cy = OUTER_D - WAGO_D / 2 - WAGO_WALL - OUTER_WALL;
_col1_cx       = GRID_X0 + CELL_W + CELL_W / 2;            // col 1 X centre (INA228 / Buzzer)
_col2_cx       = GRID_X0 + 2 * CELL_W + CELL_W / 2;        // col 2 X centre (empty cell)
_ina_pair_off  = (WAGO_W + WAGO_TOL) / 2 + WAGO_WALL + 1; // half-saddle + 1 mm gap ≈ 9.75 mm
WAGO_POS = [
    [_col1_cx - _ina_pair_off,  _wago_back_cy],  // INA228 V+  (col 1, left  — back edge)
    [_col1_cx + _ina_pair_off,  _wago_back_cy],  // INA228 V-  (col 1, right — back edge)
];
WAGO_POS_FRONT = [
    [_col2_cx, _wago_front_cy],  // SEN0460 5V (col 2 — front edge, over empty cell)
];

// ── Cell descriptors: [col, row, pcb, lid_feature] ───────────────
CELLS = [
    [0, 0, PCB_QWIIC,   "none"        ],  // TCA4307
    [1, 0, PCB_INA,     "none"        ],  // INA228
    [2, 0, PCB_QWIIC,   "vents"       ],  // BME680
    [0, 1, PCB_QWIIC,   "light_window"],  // VEML7700
    [1, 1, PCB_QWIIC,   "none"        ],  // LSM6DSOX (centre)
    [2, 1, PCB_QWIIC,   "none"        ],  // LIS3MDL
    [0, 2, PCB_DISPLAY, "display"     ],  // SSD1306
    [1, 2, PCB_BUZZER,  "grille"      ],  // Buzzer
    // [2, 2] empty
];

// ── Top-level ────────────────────────────────────────────────────
tray();
translate([0, OUTER_D + 15, 0]) lid();


// ═════════════════════════════════════════════════════════════════
//   TRAY
// ═════════════════════════════════════════════════════════════════
module tray() {
    difference() {
        union() {
            _base_plate();
            _outer_walls();
            _row_dividers();
            _lid_bosses();
            _pcb_posts();
        }
        _cable_entries();
        _qwiic_exit();
        _flange_holes();
        _pcb_post_holes();
        _lid_boss_holes();
        _tray_mortar();
    }
}

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

// Two dividers for three rows; notch at each column centre for cable routing.
module _row_dividers() {
    for (r = [1, 2]) {
        y = OUTER_WALL + r * CELL_D + (r - 1) * WALL;
        translate([FLANGE_W + OUTER_WALL, y, FLOOR])
            difference() {
                cube([INNER_W, WALL, CELL_H]);
                for (col = [0, 1, 2]) {
                    nx = END_ZONE + col * CELL_W + CELL_W / 2 - NOTCH_W / 2;
                    translate([nx, -0.1, CELL_H - NOTCH_H])
                        cube([NOTCH_W, WALL + 0.2, NOTCH_H + 0.1]);
                }
            }
    }
}

module _lid_bosses() {
    for (bxy = BOSS_XY)
        translate([bxy[0], bxy[1], FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = CELL_H);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = CELL_H);
            }
}

module _lid_boss_holes() {
    for (bxy = BOSS_XY)
        translate([bxy[0], bxy[1], -0.1])
            cylinder(d = LID_BOSS_HOLE, h = FLOOR + 2.1);
}

module _pcb_posts() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; pcb = c[2];
        _posts_for_cell(col, row, pcb);
    }
}

module _pcb_post_holes() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; pcb = c[2];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        dx = pcb[0] / 2 - HOLE_INSET;
        dy = pcb[1] / 2 - HOLE_INSET;
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx * dx, cy + sy * dy, FLOOR + 0.5])
                cylinder(d = POST_PILOT, h = POST_H + 0.5);
    }
}

module _posts_for_cell(col, row, pcb) {
    cx = GRID_X0 + col * CELL_W + CELL_W / 2;
    cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
    dx = pcb[0] / 2 - HOLE_INSET;
    dy = pcb[1] / 2 - HOLE_INSET;
    for (sx = [-1, 1], sy = [-1, 1])
        translate([cx + sx * dx, cy + sy * dy, FLOOR])
            cylinder(d = POST_OD, h = POST_H);
}

// Pi Qwiic cable enters through left end wall at row 0 centre.
module _cable_entries() {
    row0_cy = OUTER_WALL + CELL_D / 2;
    translate([FLANGE_W - 0.1, row0_cy - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 4]);
}

// SEN0460 Qwiic cable exits through the front wall (Y = OUTER_D face) near Buzzer (col 1).
// Separate from the SEN0460 5V WAGO saddle on the lid — this is the data cable only.
module _qwiic_exit() {
    buzz_cx = GRID_X0 + CELL_W + CELL_W / 2;  // col 1 X centre
    translate([buzz_cx - 4, OUTER_D - OUTER_WALL - 0.1, FLOOR + 2])
        cube([8, OUTER_WALL + 0.2, 4]);
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


// ═════════════════════════════════════════════════════════════════
//   LID
// ═════════════════════════════════════════════════════════════════
module lid() {
    difference() {
        union() {
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            // Inner lip (faces into tray when closed)
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -LID_LIP_DEPTH])
                cube([INNER_W, INNER_D, LID_LIP_DEPTH + 0.01]);
            _battlements();
            _wago_saddles();
        }
        _lid_cell_cutouts();
        _lid_screw_holes();
        _wago_slots();
    }
}

module _lid_cell_cutouts() {
    for (c = CELLS) {
        col = c[0]; row = c[1]; feat = c[3];
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
    for (bxy = BOSS_XY)
        translate([bxy[0], bxy[1], -(LID_LIP_DEPTH + 0.1)])
            cylinder(d = LID_SCREW_D, h = LID_THICK + LID_LIP_DEPTH + 1);
}

// WAGO saddles: 3-wall clip on lid outer face (Z = LID_THICK).
// Open at +Y end — WAGO slides in from front. Levers face up (+Z).
module _wago_saddles() {
    for (wp = WAGO_POS)
        _wago_saddle(wp[0], wp[1]);
    for (wp = WAGO_POS_FRONT)
        _wago_saddle_front(wp[0], wp[1]);
}

module _wago_saddle(cx, cy) {
    pw = WAGO_D + WAGO_TOL;
    pd = WAGO_W + WAGO_TOL;
    ph = WAGO_H;
    ox = cx - pd / 2 - WAGO_WALL;
    oy = cy - pw / 2 - WAGO_WALL;
    translate([ox, oy, LID_THICK]) {
        // Left wall
        cube([WAGO_WALL, pw + 2 * WAGO_WALL, ph]);
        // Right wall
        translate([pd + WAGO_WALL, 0, 0])
            cube([WAGO_WALL, pw + 2 * WAGO_WALL, ph]);
        // Back wall (closed end)
        cube([pd + 2 * WAGO_WALL, WAGO_WALL, ph]);
        // Front open — WAGO slides in here
    }
}

// Front saddle: closed end at high-Y (against tray front wall), opens toward -Y (tray interior).
module _wago_saddle_front(cx, cy) {
    pw = WAGO_D + WAGO_TOL;
    pd = WAGO_W + WAGO_TOL;
    ph = WAGO_H;
    ox = cx - pd / 2 - WAGO_WALL;
    oy = cy - pw / 2 - WAGO_WALL;
    translate([ox, oy, LID_THICK]) {
        // Left wall
        cube([WAGO_WALL, pw + 2 * WAGO_WALL, ph]);
        // Right wall
        translate([pd + WAGO_WALL, 0, 0])
            cube([WAGO_WALL, pw + 2 * WAGO_WALL, ph]);
        // Closed end at high-Y — WAGO slides in from tray interior (-Y)
        translate([0, pw + WAGO_WALL, 0])
            cube([pd + 2 * WAGO_WALL, WAGO_WALL, ph]);
    }
}

// Cable slots through lid, centred under each WAGO body.
module _wago_slots() {
    for (wp = concat(WAGO_POS, WAGO_POS_FRONT))
        translate([wp[0] - WAGO_SLOT_W / 2, wp[1] - WAGO_SLOT_D / 2, -(LID_LIP_DEPTH + 0.1)])
            cube([WAGO_SLOT_W, WAGO_SLOT_D, LID_THICK + LID_LIP_DEPTH + 0.2]);
}


// ═════════════════════════════════════════════════════════════════
//   CASTLE THEME
// ═════════════════════════════════════════════════════════════════

// Skip battlement blocks that would land over a screw boss.
function _boss_overlap(px, py) =
    len([for (bxy = BOSS_XY)
         if (abs(px - bxy[0]) < BATT_W / 2 + LID_BOSS_D / 2 + 0.5 &&
             abs(py - bxy[1]) < BATT_W / 2 + LID_BOSS_D / 2 + 0.5) 1
    ]) > 0;

// Skip battlement blocks that would land over a WAGO saddle cavity.
function _wago_clear(px, py) =
    len([for (wp = concat(WAGO_POS, WAGO_POS_FRONT))
         if (abs(px - wp[0]) < BATT_W / 2 + (WAGO_W + WAGO_TOL) / 2 + WAGO_WALL &&
             abs(py - wp[1]) < BATT_W / 2 + (WAGO_D + WAGO_TOL) / 2 + WAGO_WALL) 1
    ]) > 0;

module _battlements() {
    top_z = LID_THICK;
    // Long walls (X direction), front and back edges
    for (x = [FLANGE_W : BATT_W + BATT_GAP : FLANGE_W + OUTER_W - BATT_W])
        for (y_pos = [0, OUTER_D - BATT_W]) {
            bx = x + BATT_W / 2;
            by = y_pos + BATT_W / 2;
            if (!_boss_overlap(bx, by) && !_wago_clear(bx, by))
                translate([x, y_pos, top_z])
                    cube([BATT_W, BATT_W, BATT_H]);
        }
    // Short walls (Y direction), left and right edges
    for (y = [0 : BATT_W + BATT_GAP : OUTER_D - BATT_W])
        for (x_pos = [FLANGE_W, FLANGE_W + OUTER_W - BATT_W]) {
            bx = x_pos + BATT_W / 2;
            by = y + BATT_W / 2;
            if (!_boss_overlap(bx, by) && !_wago_clear(bx, by))
                translate([x_pos, y, top_z])
                    cube([BATT_W, BATT_W, BATT_H]);
        }
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
    translate([FLANGE_W, -0.01, FLOOR])
        _mortar_face_y(OUTER_W, h);
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, FLOOR])
        mirror([1, 0, 0]) mirror([0, 1, 0])
            _mortar_face_y(OUTER_W, h);
    translate([FLANGE_W - 0.01, 0, FLOOR])
        _mortar_face_x(OUTER_D, h);
    translate([FLANGE_W + OUTER_W + 0.01, OUTER_D, FLOOR])
        mirror([0, 1, 0])
            _mortar_face_x(OUTER_D, h);
}
