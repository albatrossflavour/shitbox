// Shitbox Rally — Pi 5 enclosure: HINGE v2 — longitudinal split
//
// The case splits down its LENGTH (plane Y = OUTER_D/2).
// Two halves hinge outward from the long base edges like a clamshell.
// No pin. Snap-fit: base carries shaft cylinders; halves carry C-clips.
// Press half straight down to snap on; pull up to release.
//
// BASE  — floor + flanges only. Snap shaft arms at Y=0 and Y=OUTER_D.
//         No walls — walls live entirely in each half. Stays bolted to car.
//
// FRONT — wall at Y=0 (HDMI, USB-C cutouts), seam face at Y=SEAM_Y,
//         front portion of left wall (fan upper arc, SD front portion),
//         front gate post stubs, front corner towers, front lid half.
//         Snap clips at Y=0 base edge. Opens forward.
//
// BACK  — wall at Y=OUTER_D (GX12, SMA), seam face at Y=SEAM_Y,
//         back left wall (fan lower arc, SD back portion), back gate post
//         stubs, back corner towers, back lid half, portcullis vent.
//         Snap clips at Y=OUTER_D base edge. Opens backward.
//
// Seam — flat faces at Y=SEAM_Y. Snap clips (4 pairs) hold halves closed.
//
// Fan  — FAN_CY = OUTER_D/2 = SEAM_Y. Each half carries a D-shaped half
//        of the aperture. Fan body bridges the seam; a thin flange ring
//        (separate print) can cap the joint if needed.
//
// Hinge — SNAP_N shaft/clip pairs per long edge. Shaft on base, C-clip on half.
//   Slot faces -Z so half drops straight down to engage. PETG flex, no tool.

$fn = 64;


// =====================================================
//   Parameters — kept in sync with pi-case.scad
// =====================================================

OUTER_WALL = 2.5;
FLOOR      = 2.5;
PCB_TOL    = 1.0;

PI5_W              = 85.0;
PI5_D              = 56.0;
PI5_PCB_T          = 1.4;
PI5_INSET          = 3.5;
PI5_HOLE_W         = 58.0;
PI5_HOLE_D_SPACING = 49.0;

HAT_D   = 55.6;
HAT_H   = 18;

HDMI1_OFFSET = 26.0;
HDMI2_OFFSET = 39.5;
PWR_OFFSET   = 11.5;
PORT_TOL     = 1.0;

FAN_APERTURE  = 37;
FAN_BODY_DEPTH = 10;
FAN_PI_GAP    = 5;
FAN_MOUNT_SPG = 32;
FAN_SCREW_D   = 3.4;
FAN_FRAME_OD  = FAN_APERTURE + 6;
FAN_FRAME_T   = 0.8;

GX12_D          = 12.5;
SMA_HOLE_D      = 6.7;
SMA_X_OFF       = 40;
CONN_TOP_MARGIN = 10;

PI_SCREW_CLEAR_D = 3.2;
PI_SCREW_HEAD_D  = 5.0;
PI_SCREW_HEAD_H  = 1.6;

FLANGE_W         = 12;
FLANGE_THICK     = 3.0;
BOLT_D           = 4.5;
FLANGE_MARGIN    = 6;
BOLT_TOWER_INSET = 4;

MAGNET_POCKET_D = 4.4;
MAGNET_POCKET_H = 2.2;

HDMI_SLOT = [15, 6];
PWR_SLOT  = [12, 6];
SD_SLOT   = [16, 4];

LID_THICK = 1.6;

GATE_POST_L      = 11.0;
TOWER_OD         = 12.0;

SEAM_COURSE_H  = 2.5;
SEAM_STEP_PROJ = 0.5;

PORTCULLIS_W = 20;
PORTCULLIS_H = 22;
PORT_BAR_W   = 1.2;
PORT_BAR_N   = 4;

MORTAR_W    = 0.4;
MORTAR_D    = 0.5;
STONE_ROW_H = 7.0;
STONE_COL_W = 11.0;

SWORD_BLADE_L  = 20; SWORD_BLADE_W = 2.5; SWORD_TIP_W  = 0.6;
SWORD_GUARD_W  = 6.0; SWORD_GUARD_H = 1.2;
SWORD_GRIP_L   = 6.0; SWORD_GRIP_W  = 1.5;
SWORD_POMMEL_D = 2.5; SWORD_RELIEF  = 0.3;

TOWER_SLIT_W     = 1.2;
TOWER_SLIT_H     = 7.0;
TOWER_SLIT_COUNT = 3;


// =====================================================
//   Hinge parameters
// =====================================================

INNER_H = 93;

// Snap-fit hinge — no pin, no rod.
// Base carries solid shaft cylinders.  Each half carries matching C-clips at
// the SAME X positions.  Press half straight down onto base: shaft enters
// slot, walls flex (PETG), snap closed.  Half pivots freely.  To remove,
// pull half upward with firm even pressure.
SNAP_R     = 4.0;   // shaft radius
SNAP_CLEAR = 0.3;   // rotation clearance (C inner = SNAP_R + SNAP_CLEAR)
SNAP_WALL  = 2.0;   // C-clip wall thickness
SNAP_PINCH = 0.8;   // slot narrower than shaft ⌀ by this much — snap stiffness
SNAP_W     = 12.0;  // shaft / clip width in X
SNAP_N     = 4;     // clips per long edge
SNAP_ARM_T   = 6.3;  // floor shelf depth — reaches shaft centre for column support
U_WALL_T     = 2.0;  // U-shape wall thickness in X
U_CLIP_CLEAR = 0.3;  // axial clearance between clip face and U wall inner face

CLIP_W = 6.0;
CLIP_H = 4.0;
CLIP_D = 1.5;


// =====================================================
//   Derived
// =====================================================

INNER_W = 110;
INNER_D = max(PI5_D, HAT_D) + PCB_TOL + 3;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;

PI_X0 = FLANGE_W + OUTER_WALL + FAN_BODY_DEPTH + FAN_PI_GAP + PCB_TOL / 2;
PI_Y0 = OUTER_WALL + PCB_TOL / 2;
PI_Z0 = FLOOR + HAT_H;

FAN_CZ = 30;
FAN_CY = OUTER_D / 2;   // fan centre lands exactly at the seam

UPPER_TOP_Z = FLOOR + INNER_H;
HALF_WALL_H = UPPER_TOP_Z - FLOOR;

TOWER_X_L = FLANGE_W;
TOWER_X_R = FLANGE_W + OUTER_W;
TOWER_Y_F = 0;
TOWER_Y_B = OUTER_D;

SEAM_Y = OUTER_D / 2;

// Snap-fit pivot: raise pivot so clip bottom lands exactly at FLOOR — no sub-floor material.
SNAP_CLIP_R_OUT = SNAP_R + SNAP_CLEAR + SNAP_WALL;
SNAP_PIVOT_Z    = FLOOR + SNAP_CLIP_R_OUT;
SNAP_X_STEP     = OUTER_W / (SNAP_N + 1);

function snap_xc(i) = FLANGE_W + (i + 1) * SNAP_X_STEP;


// =====================================================
//   Main — side-by-side preview
// =====================================================

// Side-by-side preview (default):
// render() hinge_base();
// translate([0, OUTER_D + 20, 0]) render() front_half();
// translate([0, 2 * (OUTER_D + 20), 0]) render() back_half();

// Assembled preview (uncomment):
// render() hinge_base();
// translate([0, 0, 0.01]) render() front_half();
// translate([0, 0, 0.01]) render() back_half();

// All three pieces on one plate: base at origin, halves (roof-down) beside it.
//hinge_base();
//translate([0, OUTER_D + 30, 0]) print_layout();
hinge_base();
translate([0, OUTER_D + 30, 0]) print_layout();

// =====================================================
//   BASE — floor + flanges + hinge knuckle arms
// =====================================================

module hinge_base() {
    difference() {
        union() {
            translate([FLANGE_W, 0, 0])
                cube([OUTER_W, OUTER_D, FLOOR]);
            // shelf lips: extend floor outward at both hinge edges so shaft arms
            // sit on a floor rather than cantilevering from the floor edge
            translate([FLANGE_W, -SNAP_ARM_T, 0])
                cube([OUTER_W, SNAP_ARM_T, FLOOR]);
            translate([FLANGE_W, OUTER_D, 0])
                cube([OUTER_W, SNAP_ARM_T, FLOOR]);
            for (side = [0, 1])
                translate([side == 0 ? 0 : FLANGE_W + OUTER_W, 0, 0])
                    cube([FLANGE_W, OUTER_D, FLANGE_THICK]);
            _base_snap_shafts(y_edge = 0);
            _base_snap_shafts(y_edge = OUTER_D);
        }
        _base_standoff_holes();
        _base_flange_holes();
    }
}

module _base_standoff_holes() {
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, -0.1])
            cylinder(d = PI_SCREW_CLEAR_D, h = FLOOR + 0.2);
        translate([x, y, -0.05])
            cylinder(d1 = PI_SCREW_HEAD_D, d2 = PI_SCREW_CLEAR_D,
                     h = PI_SCREW_HEAD_H + 0.05);
    }
}

module _base_flange_holes() {
    bolt_y_f = TOWER_OD / 2 + BOLT_TOWER_INSET;
    bolt_y_b = OUTER_D - TOWER_OD / 2 - BOLT_TOWER_INSET;
    for (x = [FLANGE_MARGIN, TOTAL_W - FLANGE_MARGIN], y = [bolt_y_f, bolt_y_b])
        translate([x, y, -0.1])
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
}


// =====================================================
//   Snap-fit hinge geometry — shaft on base, C-clip on halves
//
// Each long edge carries SNAP_N shaft/clip pairs spaced evenly in X.
// BASE: solid shaft cylinder at y_edge, arm fin from build plate to shaft top.
// HALF: C-clip ring (inner r = SNAP_R+SNAP_CLEAR, outer r = SNAP_CLIP_R_OUT),
//       slot opens at -Z so the half presses straight down to snap on.
// SNAP_PIVOT_Z = FLOOR + SNAP_CLIP_R_OUT: clip bottom lands exactly at FLOOR,
// so no sub-floor material exists in either part's print orientation.
// =====================================================

module _snap_c_clip_2d() {
    clip_r_in = SNAP_R + SNAP_CLEAR;
    slot_half = (2 * SNAP_R - SNAP_PINCH) / 2;
    difference() {
        circle(r = SNAP_CLIP_R_OUT);
        circle(r = clip_r_in);
        // rotate([0,90,0]) maps local +X → world -Z (downward in assembled space),
        // so slot at +X here becomes the downward opening the half presses into.
        translate([0, -slot_half])
            square([SNAP_CLIP_R_OUT + 0.1, slot_half * 2]);
    }
}

module _base_snap_shafts(y_edge) {
    outward   = (y_edge < OUTER_D / 2) ? -1 : 1;
    shaft_y   = y_edge + outward * SNAP_CLIP_R_OUT;
    slot_half = (2 * SNAP_R - SNAP_PINCH) / 2;

    // U-shape: two thin side walls + shaft cylinder that bridges them. No fin.
    //
    // Walls at Y = shaft_y ± slot_half — radius 3.6 mm from shaft centre.
    // Bore inner r = SNAP_R + SNAP_CLEAR = 4.3 mm > 3.6 mm, so the walls live
    // entirely inside the bore void; the C-ring sweeps freely at any rotation.
    //
    // Axial stop: wall inner faces at xc ± (SNAP_W/2 + U_CLIP_CLEAR).
    // Clip drops between them, butts against inner faces with 0.3 mm play in X.
    //
    // Shaft spans the full U width to bridge both walls. The bore region between
    // the walls is hollow; the shaft cylinder is the only material there.
    shaft_span = SNAP_W + 2 * (U_CLIP_CLEAR + U_WALL_T);

    for (i = [0 : SNAP_N - 1]) {
        xc = snap_xc(i);
        // Left wall (X-axis stop)
        translate([xc - SNAP_W / 2 - U_CLIP_CLEAR - U_WALL_T, shaft_y - slot_half, 0])
            cube([U_WALL_T, 2 * slot_half, SNAP_PIVOT_Z]);
        // Right wall (X-axis stop)
        translate([xc + SNAP_W / 2 + U_CLIP_CLEAR, shaft_y - slot_half, 0])
            cube([U_WALL_T, 2 * slot_half, SNAP_PIVOT_Z]);
        // Shaft cylinder — spans full U width, connects both walls at pivot height
        translate([xc, shaft_y, SNAP_PIVOT_Z])
            rotate([0, 90, 0])
                cylinder(r = SNAP_R, h = shaft_span, center = true);
    }
}

module _half_snap_clips(y_edge) {
    outward = (y_edge < OUTER_D / 2) ? -1 : 1;
    ring_y    = y_edge + outward * SNAP_CLIP_R_OUT;
    arm_y0    = (outward < 0) ? ring_y : y_edge;
    arm_y1    = (outward < 0) ? y_edge : ring_y;
    clip_r_in = SNAP_R + SNAP_CLEAR;
    for (i = [0 : SNAP_N - 1]) {
        xc = snap_xc(i);
        // Arm cube + C-ring as a union, then re-subtract the bore so the arm
        // doesn't fill the shaft clearance hole above SNAP_PIVOT_Z.
        difference() {
            union() {
                translate([xc - SNAP_W / 2, arm_y0, SNAP_PIVOT_Z])
                    cube([SNAP_W, arm_y1 - arm_y0, SNAP_CLIP_R_OUT]);
                translate([xc, ring_y, SNAP_PIVOT_Z])
                    rotate([0, 90, 0])
                        linear_extrude(SNAP_W, center = true)
                            _snap_c_clip_2d();
            }
            translate([xc, ring_y, SNAP_PIVOT_Z])
                rotate([0, 90, 0])
                    cylinder(r = clip_r_in, h = SNAP_W + 0.2, center = true);
        }
    }
}


// =====================================================
//   FRONT HALF — Y = 0 .. SEAM_Y
// =====================================================

module front_half() {
    difference() {
        render() union() {
            // Front wall (full X, Y=0..OUTER_WALL, full height)
            translate([FLANGE_W, 0, FLOOR])
                cube([OUTER_W, OUTER_WALL, HALF_WALL_H]);
            // Left wall front portion (X=FLANGE_W..+OUTER_WALL, Y=0..SEAM_Y)
            translate([FLANGE_W, 0, FLOOR])
                cube([OUTER_WALL, SEAM_Y, HALF_WALL_H]);
            // Front gate post stubs (right wall, front region only)
            translate([FLANGE_W + OUTER_W - OUTER_WALL, 0, FLOOR])
                cube([OUTER_WALL, GATE_POST_L, HALF_WALL_H]);
            // Front corner towers (full height)
            for (cx = [TOWER_X_L, TOWER_X_R])
                translate([cx, TOWER_Y_F, FLOOR])
                    cylinder(d = TOWER_OD, h = HALF_WALL_H);
            // Lid front half
            translate([FLANGE_W, 0, UPPER_TOP_Z])
                cube([OUTER_W, SEAM_Y, LID_THICK]);
            for (cx = [TOWER_X_L, TOWER_X_R])
                translate([cx, TOWER_Y_F, UPPER_TOP_Z])
                    cylinder(d = TOWER_OD, h = LID_THICK);
            // Snap clips at Y=0 edge
            _half_snap_clips(y_edge = 0);
            // Seam step at Y=SEAM_Y
            _seam_step_front();
            // Snap clips projecting toward back half
            _seam_clips_project();
        }
        _left_wall_sd_front();
        _left_wall_fan_front();
        _left_wall_fan_screws_front();
        _front_tower_slits();
        _front_sword_relief();
        _front_mortar();
        // Magnet pockets in front tower tops
        for (cx = [TOWER_X_L, TOWER_X_R])
            translate([cx, TOWER_Y_F, UPPER_TOP_Z + LID_THICK - MAGNET_POCKET_H])
                cylinder(d = MAGNET_POCKET_D, h = MAGNET_POCKET_H + 0.01);
    }
}

module _seam_step_front() {
    // Small outward step at the seam face so the halves interlock.
    translate([FLANGE_W, SEAM_Y - SEAM_STEP_PROJ, FLOOR])
        difference() {
            cube([OUTER_W, SEAM_STEP_PROJ + OUTER_WALL, SEAM_COURSE_H / 2]);
            translate([OUTER_WALL, SEAM_STEP_PROJ, -0.1])
                cube([OUTER_W - 2 * OUTER_WALL, OUTER_WALL,
                      SEAM_COURSE_H]);
        }
}

module _seam_clips_project() {
    // Two clip tabs projecting from front half seam face at Y=SEAM_Y.
    // Back half has matching recesses (subtracted in back_half).
    for (xc = [FLANGE_W + OUTER_W * 0.3, FLANGE_W + OUTER_W * 0.7],
         zc = [FLOOR + HALF_WALL_H * 0.35, FLOOR + HALF_WALL_H * 0.65])
        translate([xc - CLIP_W / 2, SEAM_Y, zc - CLIP_H / 2])
            cube([CLIP_W, CLIP_D, CLIP_H]);
}

module _seam_clip_recesses() {
    // Matching recesses subtracted from the back half seam face.
    for (xc = [FLANGE_W + OUTER_W * 0.3, FLANGE_W + OUTER_W * 0.7],
         zc = [FLOOR + HALF_WALL_H * 0.35, FLOOR + HALF_WALL_H * 0.65])
        translate([xc - CLIP_W / 2 - 0.2, SEAM_Y - CLIP_D - 0.1, zc - CLIP_H / 2 - 0.2])
            cube([CLIP_W + 0.4, CLIP_D + 0.2, CLIP_H + 0.4]);
}

module _back_wall_hdmi_slots() {
    cutout_z = PI_Z0 + PI5_PCB_T - PORT_TOL;
    for (offset = [HDMI1_OFFSET, HDMI2_OFFSET]) {
        x = PI_X0 + offset - HDMI_SLOT[0] / 2;
        translate([x, OUTER_D - OUTER_WALL - 0.1, cutout_z])
            cube([HDMI_SLOT[0], OUTER_WALL + 0.2, HDMI_SLOT[1]]);
    }
    pwr_x = PI_X0 + PWR_OFFSET - PWR_SLOT[0] / 2;
    translate([pwr_x, OUTER_D - OUTER_WALL - 0.1, cutout_z])
        cube([PWR_SLOT[0], OUTER_WALL + 0.2, PWR_SLOT[1]]);
}

module _left_wall_sd_front() {
    sd_y0 = PI_Y0 + PI5_D / 2 - SD_SLOT[0] / 2;
    sd_y1 = sd_y0 + SD_SLOT[0];
    sd_z  = PI_Z0 - SD_SLOT[1] / 2;
    y1 = min(sd_y1, SEAM_Y);
    if (y1 > sd_y0)
        translate([FLANGE_W - 0.1, sd_y0, sd_z])
            cube([OUTER_WALL + 0.2, y1 - sd_y0, SD_SLOT[1]]);
}

module _left_wall_fan_front() {
    // D-shaped half of the fan aperture: keep Y <= SEAM_Y
    r = FAN_APERTURE / 2;
    intersection() {
        translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
            rotate([0, 90, 0])
                cylinder(d = FAN_APERTURE, h = OUTER_WALL + 0.2);
        translate([FLANGE_W - 0.2, SEAM_Y - r - 0.1, FAN_CZ - r - 0.1])
            cube([OUTER_WALL + 0.4, r + 0.2, FAN_APERTURE + 0.2]);
    }
    // Fan intake ring arc — front half
    intersection() {
        translate([FLANGE_W - FAN_FRAME_T, FAN_CY, FAN_CZ])
            rotate([0, 90, 0])
                difference() {
                    cylinder(d = FAN_FRAME_OD, h = FAN_FRAME_T);
                    translate([0, 0, -0.1])
                        cylinder(d = FAN_APERTURE, h = FAN_FRAME_T + 0.2);
                }
        translate([FLANGE_W - FAN_FRAME_T - 0.1, -FAN_FRAME_OD,
                   FAN_CZ - FAN_FRAME_OD])
            cube([FAN_FRAME_T + 0.2, FAN_FRAME_OD + SEAM_Y,
                  FAN_FRAME_OD * 2]);
    }
}

module _left_wall_fan_screws_front() {
    // Fan mount screw holes that fall in the front half (sy = -1 → Y = SEAM_Y - 16)
    cut_x_depth = OUTER_WALL + 0.2;
    translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
        rotate([0, 90, 0])
            for (sx = [-1, 1])
                translate([sx * FAN_MOUNT_SPG / 2, -FAN_MOUNT_SPG / 2, 0])
                    cylinder(d = FAN_SCREW_D, h = cut_x_depth);
}

module _front_tower_slits() {
    corners = [[TOWER_X_L, TOWER_Y_F, 225], [TOWER_X_R, TOWER_Y_F, 315]];
    _tower_slits_at(corners);
}

module _front_sword_relief() {
    guard_cy = SWORD_GRIP_L + SWORD_GUARD_H / 2;
    fcx      = FLANGE_W + OUTER_W / 2;
    fcz      = FLOOR + 8.5;
    for (angle = [25, -25])
        translate([fcx, -0.01, fcz])
            multmatrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    rotate([0, 0, angle])
                        translate([0, -guard_cy])
                            _castle_sword_2d();
}

module _front_mortar() {
    h = HALF_WALL_H;
    // Front wall (Y=0 face, runs in X)
    translate([FLANGE_W, -0.01, FLOOR]) _mortar_face_y(OUTER_W, h);
    // Left wall front portion (X=FLANGE_W face, runs in Y up to SEAM_Y)
    translate([FLANGE_W - 0.01, 0, FLOOR]) _mortar_face_x(SEAM_Y, h);
}


// =====================================================
//   BACK HALF — Y = SEAM_Y .. OUTER_D
// =====================================================

module back_half() {
    difference() {
        render() union() {
            // Back wall (full X, Y=OUTER_D-OUTER_WALL..OUTER_D, full height)
            translate([FLANGE_W, OUTER_D - OUTER_WALL, FLOOR])
                cube([OUTER_W, OUTER_WALL, HALF_WALL_H]);
            // Left wall back portion (X=FLANGE_W..+OUTER_WALL, Y=SEAM_Y..OUTER_D)
            translate([FLANGE_W, SEAM_Y, FLOOR])
                cube([OUTER_WALL, OUTER_D - SEAM_Y, HALF_WALL_H]);
            // Back gate post stubs
            translate([FLANGE_W + OUTER_W - OUTER_WALL, OUTER_D - GATE_POST_L, FLOOR])
                cube([OUTER_WALL, GATE_POST_L, HALF_WALL_H]);
            // Back corner towers
            for (cx = [TOWER_X_L, TOWER_X_R])
                translate([cx, TOWER_Y_B, FLOOR])
                    cylinder(d = TOWER_OD, h = HALF_WALL_H);
            // Lid back half
            translate([FLANGE_W, SEAM_Y, UPPER_TOP_Z])
                cube([OUTER_W, OUTER_D - SEAM_Y, LID_THICK]);
            for (cx = [TOWER_X_L, TOWER_X_R])
                translate([cx, TOWER_Y_B, UPPER_TOP_Z])
                    cylinder(d = TOWER_OD, h = LID_THICK);
            // Snap clips at Y=OUTER_D edge
            _half_snap_clips(y_edge = OUTER_D);
            // Seam step at Y=SEAM_Y (back side)
            _seam_step_back();
        }
        _back_wall_connectors();
        _back_wall_hdmi_slots();
        _left_wall_sd_back();
        _left_wall_fan_back();
        _left_wall_fan_screws_back();
        _back_portcullis();
        _back_tower_slits();
        _back_sword_relief();
        _back_mortar();
        // Seam clip recesses (front half tabs engage here)
        _seam_clip_recesses();
        // Magnet pockets in back tower tops
        for (cx = [TOWER_X_L, TOWER_X_R])
            translate([cx, TOWER_Y_B, UPPER_TOP_Z + LID_THICK - MAGNET_POCKET_H])
                cylinder(d = MAGNET_POCKET_D, h = MAGNET_POCKET_H + 0.01);
    }
}

module _seam_step_back() {
    translate([FLANGE_W, SEAM_Y, FLOOR + SEAM_COURSE_H / 2])
        difference() {
            cube([OUTER_W, SEAM_STEP_PROJ + OUTER_WALL, SEAM_COURSE_H / 2]);
            translate([OUTER_WALL, SEAM_STEP_PROJ, -0.1])
                cube([OUTER_W - 2 * OUTER_WALL, OUTER_WALL, SEAM_COURSE_H]);
        }
}

module _back_wall_connectors() {
    conn_z = UPPER_TOP_Z - CONN_TOP_MARGIN;
    for (x_off = [15, OUTER_W - 15])
        translate([FLANGE_W + x_off, OUTER_D + 0.1, conn_z])
            rotate([90, 0, 0])
                cylinder(d = GX12_D, h = OUTER_WALL + 0.2, $fn = 48);
    translate([FLANGE_W + SMA_X_OFF, OUTER_D + 0.1, conn_z])
        rotate([90, 0, 0])
            cylinder(d = SMA_HOLE_D, h = OUTER_WALL + 0.2, $fn = 32);
}

module _left_wall_sd_back() {
    sd_y0 = PI_Y0 + PI5_D / 2 - SD_SLOT[0] / 2;
    sd_y1 = sd_y0 + SD_SLOT[0];
    sd_z  = PI_Z0 - SD_SLOT[1] / 2;
    y0 = max(sd_y0, SEAM_Y);
    if (sd_y1 > y0)
        translate([FLANGE_W - 0.1, y0, sd_z])
            cube([OUTER_WALL + 0.2, sd_y1 - y0, SD_SLOT[1]]);
}

module _left_wall_fan_back() {
    // D-shaped half of the fan aperture: keep Y >= SEAM_Y
    r = FAN_APERTURE / 2;
    intersection() {
        translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
            rotate([0, 90, 0])
                cylinder(d = FAN_APERTURE, h = OUTER_WALL + 0.2);
        translate([FLANGE_W - 0.2, SEAM_Y - 0.1, FAN_CZ - r - 0.1])
            cube([OUTER_WALL + 0.4, r + 0.2, FAN_APERTURE + 0.2]);
    }
    // Fan intake ring arc — back half
    intersection() {
        translate([FLANGE_W - FAN_FRAME_T, FAN_CY, FAN_CZ])
            rotate([0, 90, 0])
                difference() {
                    cylinder(d = FAN_FRAME_OD, h = FAN_FRAME_T);
                    translate([0, 0, -0.1])
                        cylinder(d = FAN_APERTURE, h = FAN_FRAME_T + 0.2);
                }
        translate([FLANGE_W - FAN_FRAME_T - 0.1, SEAM_Y - 0.1,
                   FAN_CZ - FAN_FRAME_OD])
            cube([FAN_FRAME_T + 0.2, FAN_FRAME_OD,
                  FAN_FRAME_OD * 2]);
    }
}

module _left_wall_fan_screws_back() {
    // Fan mount screw holes that fall in the back half (sy = +1 → Y = SEAM_Y + 16)
    translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
        rotate([0, 90, 0])
            for (sx = [-1, 1])
                translate([sx * FAN_MOUNT_SPG / 2, FAN_MOUNT_SPG / 2, 0])
                    cylinder(d = FAN_SCREW_D, h = OUTER_WALL + 0.2);
}

module _back_portcullis() {
    cx = FLANGE_W + OUTER_W / 2 - PORTCULLIS_W / 2;
    cz = FLOOR + HALF_WALL_H / 2 - PORTCULLIS_H / 2;
    translate([cx, OUTER_D + 0.1, cz])
        rotate([90, 0, 0])
            linear_extrude(height = OUTER_WALL + 0.2)
                _portcullis_2d(PORTCULLIS_W, PORTCULLIS_H);
}

module _back_tower_slits() {
    corners = [[TOWER_X_L, TOWER_Y_B, 135], [TOWER_X_R, TOWER_Y_B, 45]];
    _tower_slits_at(corners);
}

module _back_sword_relief() {
    guard_cy = SWORD_GRIP_L + SWORD_GUARD_H / 2;
    bcz = FLOOR + HALF_WALL_H * 0.3;
    for (x_off = [27, OUTER_W - 27])
        translate([FLANGE_W + x_off, OUTER_D + 0.01, bcz])
            multmatrix([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    translate([0, -guard_cy])
                        _castle_sword_2d();
}

module _back_mortar() {
    h = HALF_WALL_H;
    // Back wall (Y=OUTER_D face, runs in X)
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, FLOOR])
        mirror([1, 0, 0]) mirror([0, 1, 0])
            _mortar_face_y(OUTER_W, h);
    // Left wall back portion (runs in Y from SEAM_Y to OUTER_D)
    translate([FLANGE_W - 0.01, SEAM_Y, FLOOR])
        _mortar_face_x(OUTER_D - SEAM_Y, h);
}


// =====================================================
//   Shared castle sub-modules
// =====================================================

module _tower_slits_at(corners) {
    slit_span_z = TOWER_SLIT_H * TOWER_SLIT_COUNT + (TOWER_SLIT_COUNT - 1) * 3;
    z_start = (UPPER_TOP_Z + FLOOR) / 2 - slit_span_z / 2;
    for (corner = corners) {
        cx = corner[0]; cy = corner[1]; face_angle = corner[2];
        for (i = [0 : TOWER_SLIT_COUNT - 1]) {
            zc = z_start + i * (TOWER_SLIT_H + 3) + TOWER_SLIT_H / 2;
            translate([cx, cy, zc])
                rotate([0, 0, face_angle])
                    translate([TOWER_OD / 2 - 0.4, 0, 0])
                        rotate([90, 0, 0])
                            linear_extrude(height = TOWER_OD, center = true)
                                _arrow_slit_2d(TOWER_SLIT_W, TOWER_SLIT_H);
        }
    }
}

module _arrow_slit_2d(w, h) {
    translate([-w / 2, -h / 2]) square([w, h]);
    translate([-w * 1.5, -w / 2]) square([w * 3.0, w]);
}

module _castle_sword_2d() {
    translate([0, -SWORD_POMMEL_D / 2]) circle(d = SWORD_POMMEL_D, $fn = 16);
    translate([-SWORD_GRIP_W / 2, 0]) square([SWORD_GRIP_W, SWORD_GRIP_L]);
    translate([-SWORD_GUARD_W / 2, SWORD_GRIP_L]) square([SWORD_GUARD_W, SWORD_GUARD_H]);
    translate([0, SWORD_GRIP_L + SWORD_GUARD_H])
        polygon([[-SWORD_BLADE_W / 2, 0], [SWORD_BLADE_W / 2, 0],
                 [SWORD_TIP_W / 2, SWORD_BLADE_L], [-SWORD_TIP_W / 2, SWORD_BLADE_L]]);
}

module _portcullis_2d(w, h) {
    difference() {
        _pointed_arch_2d(w, h);
        bar_spacing = w / (PORT_BAR_N + 1);
        for (i = [1 : PORT_BAR_N])
            translate([i * bar_spacing - PORT_BAR_W / 2, 0]) square([PORT_BAR_W, h]);
        translate([0, h * 0.4 - PORT_BAR_W / 2]) square([w, PORT_BAR_W]);
    }
}

module _pointed_arch_2d(w, h) {
    spring_h = h * 0.45; arch_r = w;
    square([w, spring_h]);
    translate([0, spring_h])
        intersection() {
            circle(r = arch_r, $fn = 48);
            translate([w, 0]) circle(r = arch_r, $fn = 48);
            square([w, h - spring_h]);
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


// =====================================================
//   Print layout — roof down, mutual seam support
// =====================================================

// Lid face (Z = UPPER_TOP_Z + LID_THICK) to build plate; open end up.
// Both halves sit side-by-side at the seam plane:
// front half at Y 0..SEAM_Y, back half at Y SEAM_Y..OUTER_D.
module _layout_flip() {
    translate([0, 0, UPPER_TOP_Z + LID_THICK])
        mirror([0, 0, 1])
            children();
}

// Roof-down layout: both halves in one print, seam faces touching.
module print_layout() {
    // SNAP_PIVOT_Z = FLOOR + SNAP_CLIP_R_OUT ensures clip bottom lands at FLOOR.
    // In print orientation (Z-flipped, lid face down), the clip bottom maps to
    // exactly FLOOR_Z_PRINT — no sub-floor material, no clipping needed for clips.
    FLOOR_Z_PRINT = UPPER_TOP_Z + LID_THICK - FLOOR + 0.01;

    // Gap between the two halves — without this they share the seam face exactly
    // and the slicer/printer treats them as a single body.
    PRINT_GAP = 2.0;

    render() difference() {
        _layout_flip() front_half();
        // Clip snap-clip projections from seam face so halves sit flush
        translate([0, SEAM_Y - 0.01, -0.1])
            cube([TOTAL_W + 20, CLIP_D + 0.6, UPPER_TOP_Z + LID_THICK + 0.2]);
        // Clip the front seam-step protrusion at the seam/floor junction
        translate([-10, SEAM_Y - SEAM_STEP_PROJ - 0.1,
                   FLOOR_Z_PRINT - SEAM_COURSE_H / 2 - 0.1])
            cube([TOTAL_W + 20, SEAM_STEP_PROJ + 0.2,
                  SEAM_COURSE_H / 2 + 0.2]);
    }
    // Back half shifted by PRINT_GAP so there's a visible gap at the seam face.
    // The outer translate applies to both the geometry and the clip cube inside,
    // so the clip stays correctly aligned with the shifted seam face.
    translate([0, PRINT_GAP, 0])
    render() difference() {
        _layout_flip() back_half();
        // Clip the back seam-step protrusion
        translate([-10, SEAM_Y - 0.1,
                   FLOOR_Z_PRINT - SEAM_COURSE_H - 0.1])
            cube([TOTAL_W + 20, OUTER_WALL + 0.2,
                  SEAM_COURSE_H / 2 + 0.2]);
    }
}
