// Shitbox Rally — Waveshare 7-inch screen bezel (split two-part variant)
//
// Alternative to screen-bezel.scad that splits the enclosure into a
// separately-printed front bezel and back shell. Purpose: each half prints
// with its show face on the bed and no enclosed cavities, so no supports
// are needed at all (big win for PETG).
//
// Assembly:
//   1. Drop screen into back shell pocket (open top).
//   2. Place front bezel over the front; lip covers the screen edge.
//   3. 4× M3 screws from the back shell thread into heat-set inserts
//      in the front bezel corner bosses.
//
// Print orientation:
//   Front bezel   — front face down on bed. Bosses project upward.
//   Back shell    — back face (dash-bracket side) down on bed. Pocket up.
//
// Both orientations have no overhangs worth supporting.
//
// Set PART to render one half at a time for printing.
//
// Units: mm.

$fn = 64;

PART = "front";               // "front" | "back" | "both" (preview only)

// =====================================================
//   Screen (from screen-bezel.scad, measured 2026-04-17)
// =====================================================
SCREEN_W     = 190;
SCREEN_H     = 115;
SCREEN_DEPTH = 17.3;
GLASS_W      = 150;
GLASS_H      = 85;
BEZEL_L = 20; BEZEL_R = 20; BEZEL_T = 15; BEZEL_B = 15;

// =====================================================
//   Enclosure construction
// =====================================================
FRONT_LIP_T    = 1.5;         // front face plate thickness
FRONT_LIP_IN   = 1.5;         // lip overhang onto glass (retention + cosmetic edge)
BEZEL_TOL      = 0.5;         // clearance around screen in pocket
BACKPLATE_T    = 4.0;         // back shell floor thickness (>M3_HEAD_H so head has a bearing floor)
SHELL_WALL     = 3.0;         // back shell side wall thickness

// Rim carries the corner bosses. 14mm gives clearance between the screen
// pocket (inner edge at X=RIM) and a 10mm boss with 2mm gap.
RIM            = 14;

OUTER_W        = SCREEN_W + 2 * RIM;   // 218
OUTER_H        = SCREEN_H + 2 * RIM;   // 143

// =====================================================
//   Fasteners (M3 heat-set insert in front bezel, screw from back)
// =====================================================
INSERT_D       = 4.2;         // heat-set insert OD (M3xL4xD4.2 stock)
INSERT_DEPTH   = 4.2;         // insert length + 0.2mm headroom
INSERT_BOSS_D  = 10.0;        // outer diameter of boss around insert
BOSS_INSET     = 7.0;         // boss centre inset from outer corner
M3_CLEARANCE_D = 3.4;         // M3 clearance bore through boss shank
M3_HEAD_D      = 6.0;         // M3 socket head clearance
M3_HEAD_H      = 3.0;         // M3 socket head counterbore depth

// =====================================================
//   Dash bracket (same pattern as screen-bezel.scad)
// =====================================================
BRACKET_HOLE_D   = 4.5;
BRACKET_CB_D     = 8.0;
BRACKET_CB_DEPTH = 2.0;
BRACKET_SPREAD_W = 140;
BRACKET_SPREAD_H = 75;

// =====================================================
//   Derived
// =====================================================
POCKET_D        = SCREEN_DEPTH;
BOSS_LEN        = POCKET_D;           // boss spans the pocket depth
TOTAL_D         = BACKPLATE_T + POCKET_D;   // assembled shell height
FRONT_TOTAL_D   = FRONT_LIP_T + BOSS_LEN;   // assembled front-part height


// =====================================================
//   Dispatch
// =====================================================
if (PART == "front") {
    front_bezel();
} else if (PART == "back") {
    back_shell();
} else {
    // Exploded preview
    back_shell();
    translate([0, 0, TOTAL_D + 20])
        rotate([180, 0, 0])
            translate([0, 0, -FRONT_TOTAL_D])
                front_bezel();
}


// =====================================================
//   Front bezel
// =====================================================
module front_bezel() {
    difference() {
        union() {
            // Front face lip plate — sits on the bed
            cube([OUTER_W, OUTER_H, FRONT_LIP_T]);
            // Four corner bosses project back from the lip
            boss_positions()
                translate([0, 0, FRONT_LIP_T])
                    cylinder(d = INSERT_BOSS_D, h = BOSS_LEN);
        }
        // Glass window through the front lip
        glass_window();
        // M3 clearance bore through each boss
        boss_positions()
            translate([0, 0, FRONT_LIP_T - 0.1])
                cylinder(d = M3_CLEARANCE_D, h = BOSS_LEN + 0.2);
        // Insert pocket at the rear (back) end of each boss — the open
        // end faces the back shell so the insert is pressed in from there.
        boss_positions()
            translate([0, 0, FRONT_LIP_T + BOSS_LEN - INSERT_DEPTH])
                cylinder(d = INSERT_D, h = INSERT_DEPTH + 0.1);
    }
}


// =====================================================
//   Back shell
// =====================================================
module back_shell() {
    difference() {
        union() {
            // Backplate — sits on the bed
            cube([OUTER_W, OUTER_H, BACKPLATE_T]);
            // Right, top, bottom walls (left short edge left open for
            // HDMI / USB / audio connectors on the Waveshare case).
            translate([OUTER_W - SHELL_WALL, 0, 0])
                cube([SHELL_WALL, OUTER_H, TOTAL_D]);
            translate([0, OUTER_H - SHELL_WALL, 0])
                cube([OUTER_W, SHELL_WALL, TOTAL_D]);
            cube([OUTER_W, SHELL_WALL, TOTAL_D]);
        }

        // Screen pocket
        translate([RIM - BEZEL_TOL / 2,
                   RIM - BEZEL_TOL / 2,
                   BACKPLATE_T])
            cube([SCREEN_W + BEZEL_TOL,
                  SCREEN_H + BEZEL_TOL,
                  POCKET_D + 0.1]);

        // M3 pass-through with socket head counterbore on the back face
        boss_positions() {
            translate([0, 0, -0.1])
                cylinder(d = M3_CLEARANCE_D, h = TOTAL_D + 0.2);
            translate([0, 0, -0.1])
                cylinder(d = M3_HEAD_D, h = M3_HEAD_H + 0.1);
        }

        // Dash bracket holes through backplate (matches screen-bezel.scad)
        bracket_holes();
    }
}


// =====================================================
//   Shared geometry
// =====================================================
module boss_positions() {
    for (sx = [0, 1], sy = [0, 1]) {
        translate([sx ? OUTER_W - BOSS_INSET : BOSS_INSET,
                   sy ? OUTER_H - BOSS_INSET : BOSS_INSET,
                   0])
            children();
    }
}

module glass_window() {
    win_x = RIM + BEZEL_L - FRONT_LIP_IN + BEZEL_TOL / 2;
    win_y = RIM + BEZEL_B - FRONT_LIP_IN + BEZEL_TOL / 2;
    translate([win_x, win_y, -0.1])
        cube([GLASS_W + 2 * FRONT_LIP_IN,
              GLASS_H + 2 * FRONT_LIP_IN,
              FRONT_LIP_T + 0.2]);
}

module bracket_holes() {
    cx = OUTER_W / 2;
    cy = OUTER_H / 2;
    for (sx = [-1, 1], sy = [-1, 1]) {
        translate([cx + sx * BRACKET_SPREAD_W / 2,
                   cy + sy * BRACKET_SPREAD_H / 2,
                   -0.1])
            cylinder(d = BRACKET_HOLE_D, h = BACKPLATE_T + 0.2);
        translate([cx + sx * BRACKET_SPREAD_W / 2,
                   cy + sy * BRACKET_SPREAD_H / 2,
                   -0.1])
            cylinder(d = BRACKET_CB_D, h = BRACKET_CB_DEPTH + 0.1);
    }
}
