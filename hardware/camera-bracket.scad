// Shitbox Rally — ELP 4K front camera dash cradle
//
// U-shaped cradle holding the ELP 4K camera module in metal case.
// Camera drops in from the top, lens faces forward. 1/4"-20 UNC heat-set
// insert boss on the bottom for tripod mount already on dash.
// USB-A cable exits from the bottom of the camera, routed out through
// a slot in the cradle floor.
//
// Print upside-down (cradle opening on bed) so tripod boss prints without support.
//
// Measured with calipers 2026-04-20 ±0.5mm:
//   Camera body: 45 × 25 × 43mm (W × D × H, metal case)
//   Lens: 18mm diameter, centred on front face
//   USB-A cable exits from bottom face (centre)
//   No PCB mounting holes — friction fit in cradle
//
// Units: mm.

$fn = 64;

// ---- Camera body (measured 2026-04-20) ----
CAM_W = 45;               // width (left-right)
CAM_D = 25;               // depth (front-back)
CAM_H = 43;               // height

// ---- Cradle construction ----
CRADLE_WALL  = 2.0;        // wall thickness (matches OUTER_WALL convention)
CRADLE_TOL   = 0.5;        // clearance around camera body
CRADLE_FLOOR = 3.0;        // base thickness above tripod boss

// ---- Tripod mount (1/4"-20 UNC heat-set insert) ----
TRIPOD_HOLE_D  = 6.0;      // hole for heat-set insert (slightly under insert OD)
TRIPOD_BOSS_D  = 14.0;     // boss around insert for strength
TRIPOD_DEPTH   = 8.0;      // insert depth into boss
TRIPOD_BOSS_H  = 10.0;     // total boss height below base (insert depth + 2mm solid base)

// ---- Lens aperture ----
LENS_D         = 20;        // generous aperture for 18mm lens + adjustment ring clearance
LENS_CZ        = CAM_H / 2; // lens centre height on camera face

// ---- USB cable exit (rear wall, bottom-right corner looking from back) ----
USB_EXIT_W     = 19;        // width of cable exit (plug 15.5mm + clearance)
USB_EXIT_H     = 13;        // height of cable exit (plug 9mm + clearance)

// ---- Derived dimensions ----
INNER_W = CAM_W + CRADLE_TOL;
INNER_D = CAM_D + CRADLE_TOL;
OUTER_W = INNER_W + 2 * CRADLE_WALL;
OUTER_D = INNER_D + 2 * CRADLE_WALL;
WALL_H  = CAM_H * 0.7;     // walls 70% of camera height (open top, camera held by friction)


// =====================================================
//   Main
// =====================================================
camera_bracket();


// =====================================================
module camera_bracket() {
    difference() {
        union() {
            cradle_base();
            cradle_walls();
            cradle_tripod_boss();
        }
        cradle_cavity();
        cradle_lens_aperture();
        cradle_usb_exit();
        cradle_tripod_hole();
    }
}


// =====================================================
//   Solid components
// =====================================================
module cradle_base() {
    cube([OUTER_W, OUTER_D, CRADLE_FLOOR]);
}

module cradle_walls() {
    // Left wall
    cube([CRADLE_WALL, OUTER_D, CRADLE_FLOOR + WALL_H]);

    // Right wall
    translate([CRADLE_WALL + INNER_W, 0, 0])
        cube([CRADLE_WALL, OUTER_D, CRADLE_FLOOR + WALL_H]);

    // Front wall (lens side)
    cube([OUTER_W, CRADLE_WALL, CRADLE_FLOOR + WALL_H]);

    // Rear wall
    translate([0, CRADLE_WALL + INNER_D, 0])
        cube([OUTER_W, CRADLE_WALL, CRADLE_FLOOR + WALL_H]);
}

module cradle_tripod_boss() {
    // Reinforced boss extending below base for 1/4"-20 heat-set insert.
    translate([OUTER_W / 2, OUTER_D / 2, -TRIPOD_BOSS_H])
        cylinder(d = TRIPOD_BOSS_D, h = TRIPOD_BOSS_H + CRADLE_FLOOR);
}


// =====================================================
//   Cutouts
// =====================================================
module cradle_cavity() {
    // Interior pocket for camera body
    translate([CRADLE_WALL, CRADLE_WALL, CRADLE_FLOOR])
        cube([INNER_W, INNER_D, WALL_H + 1]);
}

module cradle_lens_aperture() {
    // U-shaped cutout in front wall for lens, open at the top.
    // Semicircle at bottom, rectangular slot up to top of wall.
    translate([OUTER_W / 2, -0.1, CRADLE_FLOOR + LENS_CZ])
        rotate([270, 0, 0])
            cylinder(d = LENS_D, h = CRADLE_WALL + 0.2);
    translate([OUTER_W / 2 - LENS_D / 2, -0.1, CRADLE_FLOOR + LENS_CZ])
        cube([LENS_D, CRADLE_WALL + 0.2, WALL_H + CRADLE_FLOOR]);
}

module cradle_usb_exit() {
    // Rectangular cutout in rear wall, bottom-right corner (looking from back).
    // Right side of rear wall = left side in model coords (X=0 end).
    translate([-0.1,
               CRADLE_WALL + INNER_D - 0.1,
               0])
        cube([USB_EXIT_W + 0.1, CRADLE_WALL + 0.2, USB_EXIT_H]);
}

module cradle_tripod_hole() {
    // Hole for 1/4"-20 heat-set insert from bottom of boss (matches boss offset)
    translate([OUTER_W / 2, OUTER_D / 2, -TRIPOD_BOSS_H - 0.1])
        cylinder(d = TRIPOD_HOLE_D, h = TRIPOD_DEPTH + 0.2);
}
