// Shitbox Rally — ELP 4K front camera dash cradle
//
// U-shaped cradle holding the ELP 4K camera module (42mm cube in metal case).
// Camera drops in from the top, lens faces forward. 1/4"-20 UNC heat-set
// insert boss on the bottom for tripod mount already on dash.
//
// Base flat on bed, no supports needed.
//
// Measured with calipers 2026-04-18 ±0.5mm:
//   Camera body: 42 × 42 × 42mm (metal case, cube)
//   No PCB mounting holes — friction fit in cradle
//   USB cable exits from rear face (top edge)
//   Lens protrudes from front face (centre)
//
// Units: mm.

$fn = 64;

// ---- Camera body (measured 2026-04-18) ----
CAM_W = 42;               // width (left-right)
CAM_D = 42;               // depth (front-back)
CAM_H = 42;               // height

// ---- Cradle construction ----
CRADLE_WALL  = 2.0;        // wall thickness (matches OUTER_WALL convention)
CRADLE_TOL   = 0.5;        // clearance around camera body
CRADLE_FLOOR = 3.0;        // base thickness (houses tripod insert)

// ---- Tripod mount (1/4"-20 UNC heat-set insert) ----
TRIPOD_HOLE_D  = 6.0;      // hole for heat-set insert (slightly under insert OD)
TRIPOD_BOSS_D  = 14.0;     // boss around insert for strength
TRIPOD_DEPTH   = 8.0;      // insert depth into boss

// ---- Lens aperture ----
LENS_D         = 20;        // generous aperture for lens + adjustment ring
LENS_CZ        = CAM_H / 2; // lens centre height on camera face

// ---- USB cable exit ----
USB_EXIT_W     = 10;        // width of cable exit slot
USB_EXIT_H     = 6;         // height of cable exit slot

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

    // Rear wall (USB cable side — shorter for cable exit)
    translate([0, CRADLE_WALL + INNER_D, 0])
        cube([OUTER_W, CRADLE_WALL, CRADLE_FLOOR + WALL_H]);
}

module cradle_tripod_boss() {
    // Reinforced boss on bottom centre for 1/4"-20 heat-set insert
    translate([OUTER_W / 2, OUTER_D / 2, 0])
        cylinder(d = TRIPOD_BOSS_D, h = CRADLE_FLOOR);
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
    // Circular cutout in front wall for lens
    translate([OUTER_W / 2, -0.1, CRADLE_FLOOR + LENS_CZ])
        rotate([270, 0, 0])
            cylinder(d = LENS_D, h = CRADLE_WALL + 0.2);
}

module cradle_usb_exit() {
    // Slot in rear wall for USB cable
    translate([OUTER_W / 2 - USB_EXIT_W / 2,
               CRADLE_WALL + INNER_D - 0.1,
               CRADLE_FLOOR + WALL_H - USB_EXIT_H])
        cube([USB_EXIT_W, CRADLE_WALL + 0.2, USB_EXIT_H + 1]);
}

module cradle_tripod_hole() {
    // Hole for 1/4"-20 heat-set insert from bottom
    translate([OUTER_W / 2, OUTER_D / 2, -0.1])
        cylinder(d = TRIPOD_HOLE_D, h = TRIPOD_DEPTH + 0.2);
}
