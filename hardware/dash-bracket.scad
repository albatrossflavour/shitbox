// Shitbox Rally — passenger-side dash bracket for 7-inch screen
//
// Fixed-angle bracket bolting Waveshare 7" bezel to passenger-side dash
// (left side, right-hand-drive car). No articulating joints (per D-10).
// Two side walls connect base plate to angled screen face with integral
// gusset bracing.
//
// Bracket base flat on bed, angled face prints upward with support.
// Slicer note: 40% infill minimum for vibration resistance.
//
// Bolt pattern matches screen-bezel.scad bracket boss spacing.
//
// Units: mm.

$fn = 64;

// ---- Screen attachment (must match screen-bezel.scad) ----
BRACKET_SPREAD_W = 140;   // horizontal bolt spacing (matches bezel)
BRACKET_SPREAD_H = 75;    // vertical bolt spacing (matches bezel)
SCREEN_HOLE_D    = 4.5;   // M4 clearance

// ---- Bracket geometry ----
BRACKET_ANGLE = 18;        // degrees back from vertical (per discretion: 15-20)
BRACKET_W     = 160;       // overall width
BRACKET_THICK = 4.0;       // plate/wall thickness
SIDE_WALL_H   = 80;        // side wall height (determines screen centre height)

// ---- Dash mount ----
DASH_BOLT_D      = 4.5;    // M4 clearance
DASH_BOLT_HEAD   = 8.5;    // M4 counterbore
DASH_BOLT_SPREAD = 120;    // bolt spacing across dash
BASE_D           = 55;     // base plate depth (front to back)
BASE_THICK       = BRACKET_THICK;

// ---- Gussets (per Research pitfall 5 — anti-resonance) ----
GUSSET_THICK = 3.0;

// ---- Screen face plate ----
FACE_W  = BRACKET_SPREAD_W + 20;
FACE_H  = BRACKET_SPREAD_H + 20;


// =====================================================
//   Main
// =====================================================
dash_bracket();


// =====================================================
module dash_bracket() {
    difference() {
        union() {
            bracket_base();
            bracket_side_walls();
            bracket_screen_face();
        }
        bracket_dash_holes();
        bracket_screen_holes();
        bracket_weight_relief();
    }
}


// =====================================================
//   Solid components
// =====================================================
module bracket_base() {
    translate([-BRACKET_W / 2, 0, 0])
        cube([BRACKET_W, BASE_D, BASE_THICK]);
}

module bracket_side_walls() {
    // Two side walls with integral gusset shape (triangular profile)
    // Each wall is a hull from the base edge up to the screen face position
    for (sx = [-1, 1]) {
        x = sx * (BRACKET_W / 2 - BRACKET_THICK);
        hull() {
            // Bottom edge along base plate
            translate([x, 0, BASE_THICK])
                cube([BRACKET_THICK, BASE_D, 0.1]);
            // Top edge at screen face (angled back)
            translate([x,
                       BASE_D - BRACKET_THICK + sin(BRACKET_ANGLE) * SIDE_WALL_H,
                       BASE_THICK + cos(BRACKET_ANGLE) * SIDE_WALL_H])
                cube([BRACKET_THICK, BRACKET_THICK, 0.1]);
        }
    }
}

module bracket_screen_face() {
    // Angled plate at top where screen bezel bolts on
    face_cx = 0;
    face_cy = BASE_D - BRACKET_THICK / 2 + sin(BRACKET_ANGLE) * SIDE_WALL_H;
    face_cz = BASE_THICK + cos(BRACKET_ANGLE) * SIDE_WALL_H;

    translate([face_cx, face_cy, face_cz])
        rotate([BRACKET_ANGLE, 0, 0])
            translate([-FACE_W / 2, -FACE_H / 2, -BRACKET_THICK])
                cube([FACE_W, FACE_H, BRACKET_THICK]);
}


// =====================================================
//   Cutouts
// =====================================================
module bracket_dash_holes() {
    margin_y = 10;
    for (sx = [-1, 1])
        translate([sx * DASH_BOLT_SPREAD / 2,
                   BASE_D / 2,
                   -0.1]) {
            cylinder(d = DASH_BOLT_D, h = BASE_THICK + 0.2);
            cylinder(d = DASH_BOLT_HEAD, h = 1.5);
        }
}

module bracket_screen_holes() {
    face_cy = BASE_D - BRACKET_THICK / 2 + sin(BRACKET_ANGLE) * SIDE_WALL_H;
    face_cz = BASE_THICK + cos(BRACKET_ANGLE) * SIDE_WALL_H;

    translate([0, face_cy, face_cz])
        rotate([BRACKET_ANGLE, 0, 0])
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * BRACKET_SPREAD_W / 2,
                           sy * BRACKET_SPREAD_H / 2,
                           -BRACKET_THICK - 0.1])
                    cylinder(d = SCREEN_HOLE_D, h = BRACKET_THICK + 0.2);
}

module bracket_weight_relief() {
    face_cy = BASE_D - BRACKET_THICK / 2 + sin(BRACKET_ANGLE) * SIDE_WALL_H;
    face_cz = BASE_THICK + cos(BRACKET_ANGLE) * SIDE_WALL_H;

    translate([0, face_cy, face_cz])
        rotate([BRACKET_ANGLE, 0, 0])
            translate([-BRACKET_SPREAD_W / 2 + 15,
                       -BRACKET_SPREAD_H / 2 + 15,
                       -BRACKET_THICK - 0.1])
                cube([BRACKET_SPREAD_W - 30,
                      BRACKET_SPREAD_H - 30,
                      BRACKET_THICK + 0.2]);
}
