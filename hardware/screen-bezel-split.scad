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
//      in the top and bottom edge stubs of the front bezel.
//
// Edge-stub layout (v2): the four retention screws live on the top and
// bottom rims of the bezel rather than the corners. Shrinking the corner
// bosses to edge stubs drops the rim from 14 mm to 10 mm per side,
// reclaiming 8 mm of dashboard real estate on each axis.
//
// Print orientation:
//   Front bezel   — front face down on bed. Stubs project upward.
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

// Edge-stub retention (v2): stubs live on the top and bottom rims instead
// of the corners, so the rim only needs to accommodate a slim stub and the
// M3 screw-head counterbore on the backplate.
RIM            = 10;

OUTER_W        = SCREEN_W + 2 * RIM;   // 210
OUTER_H        = SCREEN_H + 2 * RIM;   // 135

// =====================================================
//   Fasteners (M3 heat-set insert in front bezel, screw from back)
// =====================================================
INSERT_D       = 4.2;         // heat-set insert OD (M3xL4xD4.2 stock)
INSERT_DEPTH   = 4.2;         // insert length + 0.2mm headroom
STUB_D         = 6.0;         // outer diameter of stub around insert (0.9 mm wall)
STUB_Y_INSET   = 6.5;         // stub centre inset from top/bottom outer edge
STUB_X_SPREAD  = 140;         // horizontal distance between the two stub pairs
M3_CLEARANCE_D = 3.4;         // M3 clearance bore through backplate and stub
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
STUB_LEN        = POCKET_D;           // stub spans the pocket depth
TOTAL_D         = BACKPLATE_T + POCKET_D;   // assembled shell height
FRONT_TOTAL_D   = FRONT_LIP_T + STUB_LEN;   // assembled front-part height


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
            // Four edge stubs project back from the lip (top and bottom rims)
            stub_positions()
                translate([0, 0, FRONT_LIP_T])
                    cylinder(d = STUB_D, h = STUB_LEN);
        }
        // Glass window through the front lip
        glass_window();
        // M3 clearance bore through each stub
        stub_positions()
            translate([0, 0, FRONT_LIP_T - 0.1])
                cylinder(d = M3_CLEARANCE_D, h = STUB_LEN + 0.2);
        // Insert pocket at the rear (back) end of each stub — the open
        // end faces the back shell so the insert is pressed in from there.
        stub_positions()
            translate([0, 0, FRONT_LIP_T + STUB_LEN - INSERT_DEPTH])
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

        // M3 pass-through at each stub position: clearance bore through
        // the backplate, socket-head counterbore on the back face.
        stub_positions() {
            translate([0, 0, -0.1])
                cylinder(d = M3_CLEARANCE_D, h = BACKPLATE_T + 0.2);
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
module stub_positions() {
    // Four positions: top rim (x-left, x-right) and bottom rim (same X).
    // Y sits STUB_Y_INSET in from the outer edge so the stub fits between
    // the back-shell outer wall and the screen pocket.
    for (sx = [-1, 1], sy = [-1, 1]) {
        translate([OUTER_W / 2 + sx * STUB_X_SPREAD / 2,
                   sy < 0 ? STUB_Y_INSET : OUTER_H - STUB_Y_INSET,
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
