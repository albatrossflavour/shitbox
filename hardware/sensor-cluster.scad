// Shitbox Rally — ceiling-mounted Qwiic sensor cluster
//
// 4x2 grid, driver-facing front (floor of this tray = driver-facing down
// when mounted to the car roof).
//
// Sensors:
//   Row 1 (back, from driver's left): INA226 | BME690 | VEML7700 | TCA4307
//   Row 2 (front, from driver's left): Buzzer | SSD1306 | empty   | LIS3MDL
//
// Daisy-chain order:
//   Pi -> INA226 -> BME690 -> VEML7700 -> TCA4307 -> LIS3MDL -> SSD1306 -> Buzzer
//
// Units: mm.

$fn = 64;

// ---- PCB sizes ----
PCB_SMALL  = [25, 20];   // INA226, BME690, VEML7700, Buzzer, LIS3MDL
PCB_LARGE  = [25, 25];   // TCA4307, SSD1306
PCB_TOL    = 0.6;        // total clearance (0.3mm per side)

// ---- Cell geometry ----
CELL_W     = 38;         // cable-direction pitch (fits 25mm PCB + connectors + bend)
CELL_D     = 30;         // perpendicular to cable (fits 25mm PCB + tolerance + slack)
CELL_H     = 10;         // interior height (post 4mm + PCB 1.6mm + cable clearance)

WALL       = 1.5;        // between rows
OUTER_WALL = 2.0;
FLOOR      = 2.0;

// End zones house the 4 lid-screw bosses; keeps them out of the PCB cells.
// Left end zone also doubles as cable-entry from the Pi.
END_ZONE   = 9;

// ---- PCB mounting posts (M2.5 self-tap, 4 corners of each PCB) ----
POST_H         = 4.0;    // standoff height (PCB off floor = Qwiic connector clearance)
POST_OD        = 4.5;    // outer diameter
POST_PILOT     = 2.1;    // self-tap pilot for M2.5
HOLE_INSET     = 2.5;    // distance from PCB edge to hole centre

// ---- Mounting flanges (M4 to roof frame) ----
FLANGE_W      = 12;
FLANGE_THICK  = FLOOR;
BOLT_D        = 4.5;     // M4 clearance
BOLT_HEAD_D   = 8.5;     // M4 washer / head clearance (counterbore)

// ---- Lid ----
LID_THICK     = 1.6;
LID_SCREW_D   = 2.7;     // M2.5 clearance
LID_BOSS_D    = 6;       // boss OD for self-tap M2.5
LID_BOSS_HOLE = 2.1;     // pilot hole for M2.5 self-tap

// ---- Feature sizes ----
DISP_WINDOW   = [22, 12];  // SSD1306 active area
LIGHT_HOLE    = 4;         // VEML7700 window dia
VENT_SLOT     = [6, 1.5];  // BME690 vent
VENT_COUNT    = 4;
GRILLE_DIA    = 3;         // buzzer grille hole
WIRE_SLOT     = [8, 3];    // INA226 shunt-wire exit in side wall
JUMPER_NOTCH  = [6, 3];    // cable notch through row divider

// ---- Derived overall dims ----
GRID_COLS = 4;
GRID_ROWS = 2;
GRID_W  = GRID_COLS * CELL_W;
INNER_W = 2 * END_ZONE + GRID_W;       // end zone | cells | end zone
INNER_D = GRID_ROWS * CELL_D + (GRID_ROWS - 1) * WALL;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;
// x offset from flange origin to the start of the first cell
GRID_X0 = FLANGE_W + OUTER_WALL + END_ZONE;
// boss centres: inside each end zone, top and bottom rows
BOSS_X_L = FLANGE_W + OUTER_WALL + END_ZONE / 2;
BOSS_X_R = FLANGE_W + OUTER_WALL + END_ZONE + GRID_W + END_ZONE / 2;
BOSS_Y_T = OUTER_WALL + CELL_D / 2;
BOSS_Y_B = OUTER_WALL + CELL_D + WALL + CELL_D / 2;

// ---- Cell table: [col, row, name, pcb_size, feature] ----
// col 0..3 left->right, row 0 = back, row 1 = front
CELLS = [
    [0, 0, "INA226",   PCB_SMALL, "wire_slot"],
    [1, 0, "BME690",   PCB_SMALL, "vents"],
    [2, 0, "VEML7700", PCB_SMALL, "light_window"],
    [3, 0, "TCA4307",  PCB_LARGE, "none"],
    [0, 1, "Buzzer",   PCB_SMALL, "grille"],
    [1, 1, "SSD1306",  PCB_LARGE, "display"],
    // (2,1) intentionally empty
    [3, 1, "LIS3MDL",  PCB_SMALL, "none"]
];


// =====================================================
//   Main — render tray and lid side by side for preview
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
            lid_bosses();
            pcb_posts();
        }
        cell_floor_cutouts();
        side_wall_cutouts();
        flange_holes();
        pcb_post_holes();
    }
}

module lid() {
    // Lid sits above the tray; draw in tray coordinates then translate.
    difference() {
        union() {
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, LID_THICK]);
            translate([FLANGE_W + OUTER_WALL, OUTER_WALL, -0.8])
                cube([INNER_W, INNER_D, 0.8 + 0.01]);
        }
        // screw holes aligned to boss centres
        for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_T, BOSS_Y_B])
            translate([x, y, -0.1])
                cylinder(d = LID_SCREW_D, h = LID_THICK + 1);
    }
}


// =====================================================
//   Tray components
// =====================================================
module base_plate() {
    // main floor + flanges along the long edges
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

module outer_walls() {
    translate([FLANGE_W, 0, FLOOR])
        difference() {
            cube([OUTER_W, OUTER_D, CELL_H]);
            translate([OUTER_WALL, OUTER_WALL, -0.1])
                cube([INNER_W, INNER_D, CELL_H + 1]);
        }
}

module row_divider() {
    // horizontal wall between row 0 and row 1, spans the full inner width
    // notch for vertical jumper cable at rightmost column
    y = OUTER_WALL + CELL_D;
    translate([FLANGE_W + OUTER_WALL, y, FLOOR])
        difference() {
            cube([INNER_W, WALL, CELL_H]);
            // notch above col 3 (rightmost cell) — accounting for left end zone offset
            notch_x = END_ZONE + GRID_W - CELL_W / 2 - JUMPER_NOTCH[0] / 2;
            translate([notch_x, -0.1, CELL_H - JUMPER_NOTCH[1]])
                cube([JUMPER_NOTCH[0], WALL + 0.2, JUMPER_NOTCH[1] + 0.1]);
        }
}

module lid_bosses() {
    // 4 posts in the end zones, clear of the PCB cells
    boss_h = CELL_H;
    for (x = [BOSS_X_L, BOSS_X_R], y = [BOSS_Y_T, BOSS_Y_B])
        translate([x, y, FLOOR])
            difference() {
                cylinder(d = LID_BOSS_D, h = boss_h);
                translate([0, 0, 2])
                    cylinder(d = LID_BOSS_HOLE, h = boss_h);
            }
}

module cell_floor_cutouts() {
    // Apply cell-specific cutouts through the floor (driver-facing features)
    for (c = CELLS) {
        col  = c[0];
        row  = c[1];
        feat = c[4];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        translate([cx, cy, -0.1]) cell_feature(feat);
    }
}

module cell_feature(feat) {
    if (feat == "display") {
        // rectangular cutout for OLED active area
        translate([-DISP_WINDOW[0]/2, -DISP_WINDOW[1]/2, 0])
            cube([DISP_WINDOW[0], DISP_WINDOW[1], FLOOR + 0.2]);
    } else if (feat == "light_window") {
        cylinder(d = LIGHT_HOLE, h = FLOOR + 0.2);
    } else if (feat == "grille") {
        // centre hole + 4 around for piezo buzzer
        cylinder(d = GRILLE_DIA, h = FLOOR + 0.2);
        for (a = [0:90:359])
            rotate([0,0,a])
                translate([6, 0, 0])
                    cylinder(d = GRILLE_DIA, h = FLOOR + 0.2);
    } else if (feat == "vents") {
        // 4 horizontal slots for BME690 airflow
        spacing = 3;
        for (i = [0:VENT_COUNT-1])
            translate([-VENT_SLOT[0]/2,
                       (i - (VENT_COUNT-1)/2) * spacing - VENT_SLOT[1]/2,
                       0])
                cube([VENT_SLOT[0], VENT_SLOT[1], FLOOR + 0.2]);
    }
    // wire_slot handled in side_wall_cutouts (it's through the outer wall)
    // "none" = no floor cutout
}

module side_wall_cutouts() {
    // INA226 shunt wires exit through the BACK outer wall (y=0) above its cell
    ina = CELLS[0];
    col = ina[0];
    cx = GRID_X0 + col * CELL_W + CELL_W / 2;
    translate([cx - WIRE_SLOT[0]/2, -0.1, FLOOR + 2])
        cube([WIRE_SLOT[0], OUTER_WALL + 0.2, WIRE_SLOT[1]]);

    // Pi Qwiic cable entry: slot in LEFT outer wall into the left end zone
    entry_y = OUTER_WALL + CELL_D / 2;
    translate([FLANGE_W - 0.1, entry_y - 4, FLOOR + 2])
        cube([OUTER_WALL + 0.2, 8, 3]);
}

module flange_holes() {
    // 4 M4 bolt holes with counterbore, one per flange corner
    margin = 6;
    for (x = [margin, TOTAL_W - margin],
         y = [margin, OUTER_D - margin])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            // counterbore from bottom so head sits flush on roof bracket
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = 1.5);
        }
}

module pcb_posts() {
    // 4 M2.5 self-tap posts at each PCB's corner holes.
    // PCB rests on top of posts; screws come down from the lid side.
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
    // Pilot holes drilled into each post
    for (c = CELLS) {
        col = c[0]; row = c[1]; pcb = c[3];
        cx = GRID_X0 + col * CELL_W + CELL_W / 2;
        cy = OUTER_WALL + row * (CELL_D + WALL) + CELL_D / 2;
        dx = pcb[0]/2 - HOLE_INSET;
        dy = pcb[1]/2 - HOLE_INSET;
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx * dx, cy + sy * dy, FLOOR + 0.5])
                cylinder(d = POST_PILOT, h = POST_H + 0.5);
    }
}
