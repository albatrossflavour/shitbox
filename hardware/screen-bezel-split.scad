// Shitbox Rally — Waveshare 7-inch screen bezel (split two-part variant)
//
// Picture-frame construction: the back-shell walls are thick enough to
// wrap the screen directly (0.2 mm clearance, not 0.5), and M3 heat-set
// inserts live in the top face of each wall. The front bezel is a flat
// picture-frame ring — four M3 countersunk screws from the front face
// thread down into the wall-top inserts.
//
// Retention comes from the walls gripping the screen, not from the
// front lip clamping. Under rally vibration the screen has nowhere to
// walk. Previous stub-based design relied on a 1.5 mm lip overhang
// with 0.5 mm pocket slop, which was not enough.
//
// RAM Mount attachment:
//   Xiuganpo / RAM-compatible 1" B-size AMPS square plate bolts to the
//   back of the shell. M4 flat-head screws go in from INSIDE the case
//   (heads countersunk flush with the interior backplate face), shafts
//   exit through the 7 mm backplate, AMPS plate slides onto the shafts,
//   M4 washer + nyloc nut clamps it tight from outside.
//   AMPS hole pattern: 38.1 mm × 19.05 mm CTC (standard B-size).
//   Verify against your plate before printing — measure CTC, not plate edge.
//
// Assembly:
//   1. Press 4× M3 heat-set inserts into the top face of the back-shell
//      walls (top-left, top-right, bottom-left, bottom-right).
//   2. Drop screen into pocket. Left side is open for HDMI/USB/audio.
//   3. Thread 4× M4 flat-head screws from inside the case through the
//      backplate. Heads sit flush with the interior floor.
//   4. Slide AMPS plate onto the four protruding shafts. Add washers,
//      run M4 nyloc nuts finger-tight, then torque evenly.
//   5. Place front bezel over the screen; lip overhangs the screen's
//      black bezel (not the glass).
//   6. 4× M3 countersunk screws from the front face thread down into
//      the wall-top inserts. Heads are visible on the front face — fine
//      for a rally car.
//
// Print orientation:
//   Front bezel   — front face down on bed. Flat print, no overhangs.
//   Back shell    — backplate down on bed. Walls project upward.
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
FRONT_LIP_T    = 3.0;         // front face plate thickness (houses countersink + screw head)
FRONT_LIP_IN   = 1.5;         // lip overhang onto black bezel
BEZEL_TOL      = 0.2;         // snug pocket — walls grip the screen
BACKPLATE_T    = 7.0;         // back shell floor — thick for M4 CSK + 4 mm solid beyond
SHELL_WALL     = 10.0;        // wall thickness: 4.2 insert OD + 2.9 mm wall each side
FRONT_Y_PAD    = 1.0;         // extra Y padding on front bezel only (top + bottom)

OUTER_W        = SCREEN_W + 2 * SHELL_WALL + BEZEL_TOL;   // 210.2
OUTER_H        = SCREEN_H + 2 * SHELL_WALL + BEZEL_TOL;   // 135.2

// =====================================================
//   Fasteners — front bezel (M3 heat-set insert in wall, screw from front)
// =====================================================
INSERT_D       = 4.2;         // heat-set insert OD (M3xL4xD4.2 stock)
INSERT_DEPTH   = 4.2;         // insert length + headroom
M3_CLEARANCE_D = 3.4;         // M3 clearance bore through front bezel
M3_CSK_D       = 6.0;         // M3 countersink head diameter (90°)
M3_CSK_DEPTH   = 1.7;         // M3 countersink depth

// Screw layout: 4 screws on the top and bottom walls, inset from corners
SCREW_X_SPREAD = 150;         // horizontal distance between left/right screws

// =====================================================
//   Fasteners — RAM Mount AMPS plate (M4 flat-head from inside)
// =====================================================
// Standard B-size AMPS hole pattern. Verify CTC against your plate before printing.
AMPS_SPREAD_W  = 38.1;        // horizontal hole CTC (mm)
AMPS_SPREAD_H  = 19.05;       // vertical hole CTC (mm)
M4_CLEAR_D     = 4.5;         // M4 clearance bore
M4_CSK_D       = 8.5;         // M4 flat-head CSK diameter (head ~8 mm + tolerance)
M4_CSK_DEPTH   = 3.2;         // M4 flat-head CSK depth (leaves ~3.8 mm solid beyond)

// =====================================================
//   Derived
// =====================================================
POCKET_D        = SCREEN_DEPTH;
TOTAL_D         = BACKPLATE_T + POCKET_D;   // assembled back-shell height


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
            translate([0, 0, -FRONT_LIP_T])
                front_bezel();
}


// =====================================================
//   Front bezel (picture frame)
// =====================================================
module front_bezel() {
    // Front bezel is 2 * FRONT_Y_PAD taller than the back in Y so the
    // countersinks aren't bursting through the outer edge. Inner features
    // (glass window + screw holes) shift up by FRONT_Y_PAD so they stay
    // aligned with the back's heat-set insert positions. Front overhangs
    // the back by FRONT_Y_PAD mm top and bottom — accepted, no reprint.
    difference() {
        // Solid frame plate, front face on the bed
        cube([OUTER_W, OUTER_H + 2 * FRONT_Y_PAD, FRONT_LIP_T]);
        translate([0, FRONT_Y_PAD, 0]) {
            // Glass window through the frame
            glass_window();
            // Four M3 clearance bores with countersinks on the front face
            screw_positions() {
                // Clearance bore through the frame
                translate([0, 0, -0.1])
                    cylinder(d = M3_CLEARANCE_D, h = FRONT_LIP_T + 0.2);
                // Countersink opens on the Z=0 face (front, bed side)
                translate([0, 0, -0.1])
                    cylinder(d = M3_CSK_D, h = M3_CSK_DEPTH + 0.1);
            }
        }
    }
}


// =====================================================
//   Back shell (U-shape with wall-top inserts)
// =====================================================
module back_shell() {
    difference() {
        union() {
            // Backplate on the bed
            cube([OUTER_W, OUTER_H, BACKPLATE_T]);
            // Right wall (cable egress is on the left — HDMI/USB/audio)
            translate([OUTER_W - SHELL_WALL, 0, 0])
                cube([SHELL_WALL, OUTER_H, TOTAL_D]);
            // Top wall
            translate([0, OUTER_H - SHELL_WALL, 0])
                cube([OUTER_W, SHELL_WALL, TOTAL_D]);
            // Bottom wall
            cube([OUTER_W, SHELL_WALL, TOTAL_D]);
        }

        // Insert pockets in the top face of each wall
        screw_positions()
            translate([0, 0, TOTAL_D - INSERT_DEPTH])
                cylinder(d = INSERT_D, h = INSERT_DEPTH + 0.1);

        // RAM Mount AMPS plate holes through backplate
        amps_holes();
    }
}


// =====================================================
//   Shared geometry
// =====================================================
module screw_positions() {
    // Four positions: top rim (X-left, X-right) and bottom rim (same X).
    // Y sits on the wall centreline so the insert is surrounded by
    // SHELL_WALL/2 of material on both sides (3 mm each side at SHELL_WALL=6).
    for (sx = [-1, 1], sy = [-1, 1]) {
        translate([OUTER_W / 2 + sx * SCREW_X_SPREAD / 2,
                   sy < 0 ? SHELL_WALL / 2 : OUTER_H - SHELL_WALL / 2,
                   0])
            children();
    }
}

module glass_window() {
    win_x = (OUTER_W - GLASS_W - 2 * FRONT_LIP_IN) / 2;
    win_y = (OUTER_H - GLASS_H - 2 * FRONT_LIP_IN) / 2;
    translate([win_x, win_y, -0.1])
        cube([GLASS_W + 2 * FRONT_LIP_IN,
              GLASS_H + 2 * FRONT_LIP_IN,
              FRONT_LIP_T + 0.2]);
}

module amps_holes() {
    // 4× M4 flat-head screws from inside the case — heads countersunk
    // flush with the interior backplate face (z = BACKPLATE_T), shafts
    // exit at z = 0 where the AMPS plate sits. Nut + washer on outside.
    cx = OUTER_W / 2;
    cy = OUTER_H / 2;
    for (sx = [-1, 1], sy = [-1, 1]) {
        x = cx + sx * AMPS_SPREAD_W / 2;
        y = cy + sy * AMPS_SPREAD_H / 2;
        // Clearance bore through backplate (exits at z = 0)
        translate([x, y, -0.1])
            cylinder(d = M4_CLEAR_D, h = BACKPLATE_T - M4_CSK_DEPTH + 0.2);
        // Countersink opens on inside face (z = BACKPLATE_T), tapers to bore
        translate([x, y, BACKPLATE_T - M4_CSK_DEPTH])
            cylinder(d1 = M4_CLEAR_D, d2 = M4_CSK_D,
                     h = M4_CSK_DEPTH + 0.1);
    }
}
