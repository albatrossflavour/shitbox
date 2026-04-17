// Shitbox Rally — Waveshare 7-inch screen bezel
//
// Slide-in bezel for Waveshare 7" HDMI LCD (H). Screen slides in from the
// left (connector side). Retention lips on right, top, and bottom edges.
// Left edge open for HDMI, USB, and 3.5mm audio connectors.
// Backplate has bolt holes for dash bracket attachment.
//
// Print face-down on bed for best surface finish on visible front face.
//
// Measured with calipers 2026-04-17 ±0.5mm:
//   Screen case:  190 × 115 × 15mm
//   Case bezel:   20mm sides, 15mm top and bottom
//   Glass area:   150 × 85mm (derived)
//   Connectors:   all on left short edge
//   VESA:         none
//
// Units: mm.

$fn = 64;

// ---- Screen dimensions (measured 2026-04-17) ----
SCREEN_W     = 190;       // case width (landscape, long edge)
SCREEN_H     = 115;       // case height (short edge)
SCREEN_DEPTH = 15;        // case thickness (front glass to back)

// ---- Glass visible area (derived) ----
GLASS_W      = 150;       // 190 - 2 * 20
GLASS_H      = 85;        // 115 - 2 * 15

// ---- Case bezel insets (measured 2026-04-17) ----
BEZEL_L = 20;             // left (connector side — open)
BEZEL_R = 20;             // right
BEZEL_T = 15;             // top
BEZEL_B = 15;             // bottom

// ---- Bezel construction ----
BEZEL_WALL   = 2.0;       // side wall thickness
BEZEL_LIP    = 1.5;       // front lip overlapping glass face (retention)
BEZEL_TOL    = 0.5;       // clearance around screen case
BACKPLATE_T  = 3.0;       // backplate thickness (structural)

// ---- Bracket attachment (custom spacing, no VESA) ----
BRACKET_HOLE_D  = 4.5;    // M4 clearance
BRACKET_BOSS_D  = 10;     // boss around each hole
BRACKET_BOSS_H  = 4;      // boss standoff from backplate
BRACKET_SPREAD_W = 140;   // horizontal bolt spacing
BRACKET_SPREAD_H = 75;    // vertical bolt spacing

// ---- Audio access ----
AUDIO_EXIT_D = 8;         // 3.5mm jack + plug clearance

// ---- Derived dimensions ----
// Cavity fits the screen case with tolerance
CAVITY_W = SCREEN_W + BEZEL_TOL;
CAVITY_H = SCREEN_H + BEZEL_TOL;
CAVITY_D = SCREEN_DEPTH;

// Outer bezel dimensions
OUTER_W = CAVITY_W + BEZEL_WALL;          // only right wall (left open)
OUTER_H = CAVITY_H + 2 * BEZEL_WALL;
TOTAL_D = CAVITY_D + BACKPLATE_T;


// =====================================================
//   Main
// =====================================================
screen_bezel();


// =====================================================
module screen_bezel() {
    difference() {
        union() {
            bezel_frame();
            bezel_backplate();
            bezel_bracket_bosses();
        }
        bezel_glass_window();
        bezel_screen_cavity();
        bezel_bracket_holes();
    }
}


// =====================================================
//   Solid components
// =====================================================
module bezel_frame() {
    // U-shaped frame: right wall, top wall, bottom wall
    // Left side open for slide-in and connector access
    // Front face has retention lips overlapping the glass

    // Front lip plate (covers full front except glass window)
    cube([OUTER_W, OUTER_H, BEZEL_LIP]);

    // Right wall
    translate([CAVITY_W, 0, 0])
        cube([BEZEL_WALL, OUTER_H, TOTAL_D]);

    // Top wall
    translate([0, CAVITY_H + BEZEL_WALL, 0])
        cube([OUTER_W, BEZEL_WALL, TOTAL_D]);

    // Bottom wall
    cube([OUTER_W, BEZEL_WALL, TOTAL_D]);
}

module bezel_backplate() {
    // Solid plate behind the screen
    translate([0, 0, CAVITY_D])
        cube([OUTER_W, OUTER_H, BACKPLATE_T]);
}

module bezel_bracket_bosses() {
    // 4 bosses on backplate for bracket bolt attachment
    cx = OUTER_W / 2;
    cy = OUTER_H / 2;
    for (sx = [-1, 1], sy = [-1, 1])
        translate([cx + sx * BRACKET_SPREAD_W / 2,
                   cy + sy * BRACKET_SPREAD_H / 2,
                   TOTAL_D])
            cylinder(d = BRACKET_BOSS_D, h = BRACKET_BOSS_H);
}


// =====================================================
//   Cutouts
// =====================================================
module bezel_glass_window() {
    // Opening through front lip to expose glass
    // Centred on the glass area position
    win_x = BEZEL_L - BEZEL_LIP + BEZEL_TOL / 2;
    win_y = BEZEL_WALL + BEZEL_B - BEZEL_LIP + BEZEL_TOL / 2;
    translate([win_x, win_y, -0.1])
        cube([GLASS_W + 2 * BEZEL_LIP, GLASS_H + 2 * BEZEL_LIP, BEZEL_LIP + 0.2]);
}

module bezel_screen_cavity() {
    // Pocket for the screen case body (slides in from left)
    // Extends through the left wall (open side)
    translate([-0.1, BEZEL_WALL, BEZEL_LIP])
        cube([CAVITY_W + 0.2, CAVITY_H, CAVITY_D]);
}

module bezel_bracket_holes() {
    // M4 clearance holes through backplate + bosses
    cx = OUTER_W / 2;
    cy = OUTER_H / 2;
    for (sx = [-1, 1], sy = [-1, 1])
        translate([cx + sx * BRACKET_SPREAD_W / 2,
                   cy + sy * BRACKET_SPREAD_H / 2,
                   CAVITY_D - 0.1])
            cylinder(d = BRACKET_HOLE_D, h = BACKPLATE_T + BRACKET_BOSS_H + 0.2);
}
