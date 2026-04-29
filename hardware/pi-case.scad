// Shitbox Rally — Pi 5 stack enclosure v3 — 3-PIECE CASTLE EDITION
//
// Horizontally-split shell with open right (USB-A / Ethernet) short wall.
// Three pieces:
//   1. BOTTOM — tray. Floor + walls. Sits on car mount (M4 flanges).
//   2. TOP    — sealed flat upper. Smooth structural box, no decoration.
//              Magnets in corner towers mate with bottom.
//   3. ROOF   — full-area decorated plate. Bonds permanently on top of TOP
//              via PETG solvent weld. Carries all castle decoration:
//              perimeter crenellations, corner tower caps, shield, vents.
//
// Why split into three? Castle decoration on a single lid forced
// support-heavy prints in PETG — overhang under crenellation gaps fused
// into the merlons and could not be removed cleanly (see brain note +
// IMG_2036). Splitting into a sealed flat TOP + decorated ROOF means
// both pieces print bed-down with no support material.
//
// Stack (bottom to top):
//   NVMe HAT (HAT_H = 20 mm) → Pi 5 PCB → active cooler →
//   GPIO extender → perma-proto HAT
//
// Pi 5 orientation:
//   HDMI / USB-C / fan header long edge → case FRONT (Y=0)
//   GPIO header long edge                → case BACK (Y=OUTER_D)
//   USB-A + Ethernet short edge          → case RIGHT (+X, open gatehouse)
//   Display + SD short edge              → case LEFT (-X)
//
// Fasteners:
//   Pi mount     — 4× M2.5 heat-set inserts in floor → brass standoffs
//                  carry the NVMe HAT, then Pi.
//   Plywood mnt  — 4× M4 through-hole flanges on left+right exteriors.
//                  Bolt holes sit between the corner towers, inset
//                  ~4 mm past each tower edge — clear of the towers
//                  on both sides without widening the flange tabs.
//   Top↔Bottom   — 4× N35 magnet pairs in corner buttress towers.
//   Top↔Roof     — permanent bond (PETG solvent weld, full-area).
//
// v3 changes from v2 (see ~/Brain/projects/shitbox-pi-case-redesign-spec.md):
//   - Three-piece split: bottom + top + roof.
//   - Top is fully smooth (no shield, no crenellations, no slits).
//   - All decoration moves to roof.
//   - Top has large central vent cutout matching roof vent footprint.
//   - Gate post stubs truncated to 4 mm at the OUTER end of each piece
//     (bottom-of-bottom, top-of-top) — USB-A / Ethernet plug clearance
//     through the gatehouse, structural reinforcement only at the
//     joining surfaces.
//   - Mounting flange bolt holes moved between the corner towers
//     (inset ~4 mm past each tower edge) instead of crammed into the
//     corner alongside the towers. No flange extension required.
//
// Castle features now living on the ROOF (printed standalone, bed-down):
//   - Perimeter crenellations w/ pyramidal merlon caps + arrow slits
//   - Machicolation gallery (corbelled overhang) w/ murder holes
//   - Corner tower caps: corbel ring + battlement merlons + conical roof
//   - Heater shield + chevron sigil at roof centre
//   - Functional cross-shaped ventilation cuts through the plate
//   - Mortar engraving on merlon faces
//   - Drawbridge relief on the gatehouse edge
//   - Flag finial on one corner tower
//
// Castle features still on the BOTTOM walls (zero overhang):
//   - Corner buttress towers (cylinders, full bottom-half height)
//   - Stepped battered course along clamshell seam
//   - Running-bond mortar grooves on three solid walls
//   - Sword relief carvings on front wall
//   - Tower arrow slits in tower bodies
//   - Fan intake aperture on left wall
//
// Castle features on the TOP walls:
//   - Corner buttress towers (cylinders, top-half height)
//   - Running-bond mortar grooves on three solid walls
//   - Sword relief on back wall (flanking the portcullis, inset to
//     clear the GX12 cutouts)
//   - Portcullis vent on back wall (decorative, also passes the GPS
//     antenna coax)
//   - Two GX12 panel-mount cutouts on the back wall, tucked alongside
//     the corner towers (button + 1-Wire)
//   - Tower arrow slits (continued from bottom)
//
// Units: mm. $fn = 64 for STL export; reduce for live preview.

$fn = 64;


// =====================================================
//   Parameters
// =====================================================

// ---- Print / material ----
OUTER_WALL = 2.5;    // 2 mm structural + 0.5 mm stone relief allowance
FLOOR      = 2.5;    // thick enough to support M2.5 heat-set insert torque
PCB_TOL    = 1.0;    // total clearance (0.5 mm per side — first-print margin)

// ---- Pi 5 board (RPi mechanical drawing) ----
PI5_W              = 85.0;
PI5_D              = 56.0;
PI5_PCB_T          = 1.4;       // PCB thickness (port body sits on top of PCB)
PI5_INSET          = 3.5;
PI5_HOLE_W         = 58.0;
PI5_HOLE_D_SPACING = 49.0;

// ---- NVMe HAT (Freenove V2, measured 2026-04-28) ----
HAT_W            = 88.0;
HAT_D            = 55.6;
HAT_OVERHANG_X   = HAT_W - PI5_W;
HAT_BASE_OFFSET  = 6;

// ---- Stack heights ----
STACK_H = 47;
HAT_H   = 18;

// ---- Pi 5 connector offsets ----
HDMI1_OFFSET = 26.0;
HDMI2_OFFSET = 39.5;
HDMI_PORT_H  = 3.5;
USB_OFFSET   = 29.0;
PWR_OFFSET   = 11.5;
PWR_PORT_H   = 3.5;
PORT_TOL     = 1.0;

// ---- Fan (Noctua NF-A4x10 5V) ----
FAN_W            = 40;
FAN_MOUNT_SPG    = 32;
FAN_SCREW_D      = 3.4;
FAN_APERTURE     = 37;
FAN_BODY_DEPTH   = 10;
FAN_PI_GAP       = 5;

// ---- Back-wall connector cutouts ----
GX12_D     = 12.5;
SMA_HOLE_D = 6.7;

// ---- Pi mounting: heat-set inserts in floor ----
INSERT_D_M25     = 4.0;
INSERT_H_M25     = 5.0;
BOSS_H_M25       = 3.0;
STANDOFF_BOSS_OD = 7.0;

// ---- Mounting flanges (M4 to plywood panel) ----
FLANGE_W      = 12;
FLANGE_THICK  = 3.0;
BOLT_D        = 4.5;       // M4 clearance
BOLT_HEAD_D   = 8.5;       // M4 cap-head clearance
BOLT_HEAD_H   = 1.5;
FLANGE_MARGIN = 6;
// v3 take 3: bolt holes sit BETWEEN the corner towers along each flange,
// inset BOLT_TOWER_INSET from the tower outer edge. No flange extension
// in Y — the original [0..OUTER_D] flange length is enough once the
// bolts move out of the corners.
FLANGE_Y_EXT     = 0;
BOLT_TOWER_INSET = 4;     // gap from tower outer edge to bolt centre

// ---- Clamshell closure (4× N35 magnet pairs, 4×2 mm) ----
MAGNET_D        = 4.0;
MAGNET_H        = 2.0;
MAGNET_POCKET_D = 4.1;
MAGNET_POCKET_H = MAGNET_H + 0.1;

// Parked: bolts replaced by magnets.
CLAM_BOLT_D       = 3.4;
CLAM_BOLT_HEAD_D  = 6.0;
CLAM_BOLT_HEAD_H  = 3.2;
INSERT_D_M3       = 4.6;
INSERT_H_M3       = 6.0;

// ---- Clamshell geometry ----
SPLIT_Z    = 30;
INNER_H    = 60;

// Shiplap seam
LIP_SLICE = OUTER_WALL / 2;
LIP_DROP  = 3.0;

// ---- Cable exit slots ----
HDMI_SLOT    = [15, 6];
USB_SLOT     = [15, 18];
PWR_SLOT     = [12, 6];
QWIIC_SLOT   = [7, 5];
ONEWIRE_SLOT = [6, 4];
SD_SLOT      = [16, 4];

// ---- Top lid + roof plate ----
LID_THICK     = 1.6;
ROOF_PLATE_T  = 2.0;

// v3: gate post stubs truncated to GATE_POST_STUB_H above each half's
// base. USB-A / Ethernet plug insertion clearance was blocked by full-
// height stubs at the front-right and back-right corners.
GATE_POST_STUB_H = 4.0;

// v3: large central vent cutout in the TOP lid plate. Matches the roof
// vent cluster footprint plus tolerance so air flows from interior →
// top cutout → roof vents → atmosphere. Loose fit; the roof's vent
// cluster can land anywhere within this rectangle.
TOP_VENT_W = 60;
TOP_VENT_D = 42;


// =====================================================
//   Castle decoration parameters
// =====================================================

// Running-bond stone mortar (walls)
MORTAR_W    = 0.4;
MORTAR_D    = 0.5;
STONE_ROW_H = 7.0;
STONE_COL_W = 11.0;

// Roof perimeter crenellations
MERLON_W      = 5.0;
MERLON_H      = 5.0;
CRENEL_W      = 4.0;
MERLON_CAP_H  = 2.0;       // pyramidal cap height on top of each merlon
MERLON_SLIT_W = 1.0;       // arrow slit through merlon face
MERLON_SLIT_H = 3.0;

// Corner buttress towers (case body — bottom + top halves)
TOWER_OD          = 12.0;
TOWER_CORBEL_H    = 2.0;
TOWER_CORBEL_PROJ = 0.8;
TOWER_SLIT_W      = 1.2;
TOWER_SLIT_H      = 7.0;
TOWER_SLIT_COUNT  = 3;
TOWER_MERLON_N    = 8;
TOWER_MERLON_W    = 2.8;
TOWER_MERLON_H    = 3.5;

// Roof corner tower caps (continue the towers above the roof plate)
TOWER_CAP_CORBEL_H    = 2.0;
TOWER_CAP_CORBEL_PROJ = 1.0;     // slightly more than the case-body corbel
TOWER_CAP_MERLON_H    = 3.5;
TOWER_CAP_MERLON_W    = 2.8;
TOWER_CAP_MERLON_N    = 8;
TOWER_CAP_CONE_H      = 9.0;
TOWER_CAP_CONE_TIP_D  = 1.0;

// Stepped battered course masking the clamshell seam
SEAM_COURSE_H    = 2.5;
SEAM_STEP_PROJ   = 0.5;

// Gatehouse pointed arch (frame only — parked, replaced by lid plate)
GATE_FRAME_T     = 2.5;
GATE_HEADER_H    = 8.0;

// Decorative portcullis vent on back wall (top half)
PORTCULLIS_W = 20;
PORTCULLIS_H = 22;
PORT_BAR_W   = 1.2;
PORT_BAR_N   = 4;

// Sword relief
SWORD_BLADE_L  = 20;
SWORD_BLADE_W  = 2.5;
SWORD_TIP_W    = 0.6;
SWORD_GUARD_W  = 6.0;
SWORD_GUARD_H  = 1.2;
SWORD_GRIP_L   = 6.0;
SWORD_GRIP_W   = 1.5;
SWORD_POMMEL_D = 2.5;
SWORD_RELIEF   = 0.3;

// Heater shield sigil on roof centre
SHIELD_W     = 28;
SHIELD_H     = 35;
SHIELD_RAISE = 0.8;

// Fan intake ring (on top half left wall)
FAN_FRAME_OD = FAN_APERTURE + 6;
FAN_FRAME_T  = 0.8;

// Machicolation gallery (corbelled overhang ring beneath roof crenellations)
MACHI_BAND_H    = 1.6;       // height of corbel band above roof plate
MACHI_PROJ      = 0.8;       // outward projection beyond roof plate edge
MACHI_HOLE_W    = 2.0;       // murder-hole slot width (along wall)
MACHI_HOLE_D    = 1.6;       // murder-hole slot depth (perpendicular to wall)
MACHI_HOLE_GAP  = 6.0;       // murder-hole period along wall

// Drawbridge relief (engraved on the +X edge of the roof, between corner caps)
BRIDGE_PLANK_W  = 3.0;       // visible plank width along Y
BRIDGE_PLANK_GAP= 0.8;       // groove width between planks
BRIDGE_RELIEF   = 0.5;       // depth of relief
BRIDGE_INSET    = 1.5;       // how far in from roof +X edge the bridge sits

// Flag finial (one tower)
FLAG_MAST_D     = 1.0;
FLAG_MAST_H     = 6.0;
FLAG_W          = 4.0;
FLAG_H          = 2.5;
FLAG_T          = 0.6;


// =====================================================
//   Derived dimensions
// =====================================================
INNER_W = 110;
INNER_D = max(PI5_D, HAT_D) + PCB_TOL + 3;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;

PI_X0 = FLANGE_W + OUTER_WALL + FAN_BODY_DEPTH + FAN_PI_GAP + PCB_TOL / 2;
PI_Y0 = OUTER_WALL + PCB_TOL / 2;
PI_Z0 = FLOOR + HAT_H;

RIGHT_EDGE_X = PI_X0 + PI5_W;

FAN_CZ = 30;
FAN_CY = OUTER_D / 2;

// Split geometry
TRAY_TOP_Z   = SPLIT_Z;
UPPER_TOP_Z  = FLOOR + INNER_H;
UPPER_WALL_H = UPPER_TOP_Z - SPLIT_Z;

// Corner tower centres
TOWER_X_L = FLANGE_W;
TOWER_X_R = FLANGE_W + OUTER_W;
TOWER_Y_F = 0;
TOWER_Y_B = OUTER_D;

// Right-side gatehouse
GATE_POST_L     = 11.0;
GATE_OPENING_Y0 = GATE_POST_L;
GATE_OPENING_Y1 = OUTER_D - GATE_POST_L;
GATE_OPENING_H  = INNER_H;


// =====================================================
//   Main — render bottom + top + roof side by side
// =====================================================
pi_case_bottom();
translate([0,     OUTER_D + TOWER_OD + 15, 0]) pi_case_top();
translate([0, 2 * (OUTER_D + TOWER_OD + 15), 0]) pi_case_roof();

// Assembled preview: uncomment to stack roof on top of top on top of bottom.
// pi_case_bottom();
// translate([0, 0, 0.01]) pi_case_top();
// translate([0, 0, UPPER_TOP_Z + LID_THICK + 0.02]) pi_case_roof();


// =====================================================
//   Bottom (lower clamshell half)
// =====================================================
module pi_case_bottom() {
    difference() {
        union() {
            pi_case_base_plate();
            pi_case_bottom_walls();
            pi_case_gate_posts(bottom = true);
            pi_case_corner_towers(bottom = true);
            pi_case_standoff_bosses();
            castle_fan_arch_bottom();
            castle_seam_course(top = false);
        }
        pi_case_standoff_insert_holes();
        pi_case_cable_slots_bottom();
        pi_case_fan_cutout();
        pi_case_flange_holes();
        pi_case_clamshell_holes(bottom = true);
        castle_tower_arrow_slits();
        castle_stone_mortar_bottom();
        castle_sword_relief_bottom();
    }
}


// =====================================================
//   Top (upper clamshell half — sealed flat, no decoration)
// =====================================================
module pi_case_top() {
    difference() {
        union() {
            pi_case_top_walls();
            pi_case_gate_posts(bottom = false);
            pi_case_corner_towers(bottom = false);
            pi_case_top_lid_plate();
            castle_seam_course(top = true);
        }
        pi_case_fan_cutout();
        pi_case_cable_slots_top();
        pi_case_clamshell_holes(bottom = false);
        castle_tower_arrow_slits();
        castle_stone_mortar_top();
        castle_portcullis_vents();
        castle_sword_relief_top();
        pi_case_top_lid_vent();          // large central air cutout
        pi_case_shiplap_slot_clearance();
    }
}


// =====================================================
//   Roof (decorated plate, bonds permanently to top)
// =====================================================
module pi_case_roof() {
    difference() {
        union() {
            roof_plate();
            roof_machicolation();
            roof_perimeter_crenellations();
            roof_corner_caps();
            roof_corner_gargoyles();
            roof_corner_flag();
            roof_shield();
            roof_drawbridge_relief_solid();
        }
        roof_vent_cuts();
        roof_merlon_arrow_slits();
        roof_crenel_gap_slits();
        roof_machicolation_holes();
        roof_drawbridge_grooves();
        // roof_perimeter_rope_grooves(): dropped — ~120 rotated cube
        // subtractions blew the CSG normalization tree past 100k
        // elements and the whole render came back empty. Module
        // definition retained below in case a future rev simplifies it.
    }
}


// =====================================================
//   Bottom solid geometry
// =====================================================
module pi_case_base_plate() {
    union() {
        // main floor
        translate([FLANGE_W, 0, 0])
            cube([OUTER_W, OUTER_D, FLOOR]);
        // M4 mounting flanges along the left + right exteriors. Run
        // the full case Y length; bolt holes sit between the corner
        // towers (see pi_case_flange_holes). FLANGE_Y_EXT left as a
        // tunable in case a future revision wants to widen the tabs.
        for (side = [0, 1])
            translate([side == 0 ? 0 : FLANGE_W + OUTER_W,
                       -FLANGE_Y_EXT,
                       0])
                cube([FLANGE_W,
                      OUTER_D + 2 * FLANGE_Y_EXT,
                      FLANGE_THICK]);
    }
}

module pi_case_bottom_walls() {
    wall_h = TRAY_TOP_Z - FLOOR;

    // Full-thickness walls, FLOOR .. SPLIT_Z
    translate([FLANGE_W, 0, FLOOR])
        cube([OUTER_W, OUTER_WALL, wall_h]);
    translate([FLANGE_W, OUTER_D - OUTER_WALL, FLOOR])
        cube([OUTER_W, OUTER_WALL, wall_h]);
    translate([FLANGE_W, 0, FLOOR])
        cube([OUTER_WALL, OUTER_D, wall_h]);

    // Shiplap outer-slice projection, SPLIT_Z .. SPLIT_Z + LIP_DROP
    difference() {
        union() {
            translate([FLANGE_W, 0, TRAY_TOP_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            translate([FLANGE_W, OUTER_D - LIP_SLICE, TRAY_TOP_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            translate([FLANGE_W, 0, TRAY_TOP_Z])
                cube([LIP_SLICE, OUTER_D, LIP_DROP]);
        }
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
            translate([cx, cy, TRAY_TOP_Z - 0.05])
                cylinder(d = TOWER_OD + 0.4, h = LIP_DROP + 0.1);
    }
}

module pi_case_top_walls() {
    wall_h_full = UPPER_TOP_Z - (SPLIT_Z + LIP_DROP);
    skirt_off   = OUTER_WALL - LIP_SLICE;

    // Full-thickness walls above the shiplap overlap
    translate([FLANGE_W, 0, SPLIT_Z + LIP_DROP])
        cube([OUTER_W, OUTER_WALL, wall_h_full]);
    translate([FLANGE_W, OUTER_D - OUTER_WALL, SPLIT_Z + LIP_DROP])
        cube([OUTER_W, OUTER_WALL, wall_h_full]);
    translate([FLANGE_W, 0, SPLIT_Z + LIP_DROP])
        cube([OUTER_WALL, OUTER_D, wall_h_full]);

    // Shiplap inner-slice skirt
    difference() {
        union() {
            translate([FLANGE_W, skirt_off, SPLIT_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            translate([FLANGE_W, OUTER_D - OUTER_WALL, SPLIT_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            translate([FLANGE_W + skirt_off, 0, SPLIT_Z])
                cube([LIP_SLICE, OUTER_D, LIP_DROP]);
        }
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
            translate([cx, cy, SPLIT_Z - 0.05])
                cylinder(d = TOWER_OD + 0.4, h = LIP_DROP + 0.1);
    }
}

module pi_case_shiplap_slot_clearance() {
    // Carve a slot through the upper's shiplap zone so the bottom's outer
    // slice has clean space to seat. Without this, several features (left
    // wall inner skirt, gate post stub, seam course outward bump) collide
    // with the bottom's outer slice and stop the lid closing.
    eps = 0.05;
    slot_h = LIP_DROP + 2 * eps;
    difference() {
        union() {
            translate([FLANGE_W - eps,
                       -SEAM_STEP_PROJ,
                       SPLIT_Z - eps])
                cube([OUTER_W + SEAM_STEP_PROJ + 2 * eps,
                      SEAM_STEP_PROJ + LIP_SLICE,
                      slot_h]);
            translate([FLANGE_W - eps,
                       OUTER_D - LIP_SLICE,
                       SPLIT_Z - eps])
                cube([OUTER_W + SEAM_STEP_PROJ + 2 * eps,
                      SEAM_STEP_PROJ + LIP_SLICE,
                      slot_h]);
            translate([FLANGE_W - SEAM_STEP_PROJ,
                       -eps,
                       SPLIT_Z - eps])
                cube([SEAM_STEP_PROJ + LIP_SLICE,
                      OUTER_D + 2 * eps,
                      slot_h]);
        }
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
            translate([cx, cy, SPLIT_Z - 0.1])
                cylinder(d = TOWER_OD, h = LIP_DROP + 0.2);
    }
}

module pi_case_top_lid_plate() {
    // Rectangular lid spanning the case footprint, plus circular caps
    // at each corner that cover the half of every tower projecting
    // outside the rectangle. Without the caps the lid edge cuts the
    // tower in half at z = UPPER_TOP_Z and the outer half of the
    // tower top stays exposed.
    translate([FLANGE_W, 0, UPPER_TOP_Z])
        cube([OUTER_W, OUTER_D, LID_THICK]);
    for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
        translate([cx, cy, UPPER_TOP_Z])
            cylinder(d = TOWER_OD, h = LID_THICK);
}

module pi_case_top_lid_vent() {
    // Large central cutout in the top's lid plate. Generous tolerance so
    // the roof's vent cluster can land within without precise alignment.
    cx = FLANGE_W + OUTER_W / 2;
    cy = OUTER_D / 2;
    translate([cx - TOP_VENT_W / 2,
               cy - TOP_VENT_D / 2,
               UPPER_TOP_Z - 0.1])
        cube([TOP_VENT_W,
              TOP_VENT_D,
              LID_THICK + 0.2]);
}

module pi_case_gate_posts(bottom = true) {
    // Short stubs at the front-right and back-right corners. Each piece
    // gets a 4 mm stub at its OUTER end (away from the seam):
    //   - Bottom piece: stub at Z = 0..4 (bottom of bottom — sits on
    //     the floor, reinforces flange-to-tower junction).
    //   - Top piece: stub at Z = UPPER_TOP_Z-4..UPPER_TOP_Z (top of top —
    //     reinforces the lid-to-tower junction where the roof bonds).
    // Middle of each tower is left clear so USB-A / Ethernet plugs have
    // unobstructed insertion clearance through the gatehouse mouth.
    h  = GATE_POST_STUB_H;
    z0 = bottom ? 0 : (UPPER_TOP_Z - h);

    // Front-right stub
    translate([FLANGE_W + OUTER_W - OUTER_WALL, 0, z0])
        cube([OUTER_WALL, GATE_POST_L, h]);

    // Back-right stub
    translate([FLANGE_W + OUTER_W - OUTER_WALL,
               OUTER_D - GATE_POST_L, z0])
        cube([OUTER_WALL, GATE_POST_L, h]);
}

module pi_case_standoff_bosses() {
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, FLOOR])
            cylinder(d = STANDOFF_BOSS_OD, h = BOSS_H_M25);
    }
}


// =====================================================
//   Bottom / top cutouts (functional)
// =====================================================
module pi_case_standoff_insert_holes() {
    boss_top_z = FLOOR + BOSS_H_M25;
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, boss_top_z - INSERT_H_M25])
            cylinder(d = INSERT_D_M25,
                     h = INSERT_H_M25 + 0.2);
    }
}

module pi_case_fan_cutout() {
    cut_x_start = FLANGE_W - SEAM_STEP_PROJ - 0.1;
    cut_x_depth = OUTER_WALL + SEAM_STEP_PROJ + 0.2;
    translate([cut_x_start, FAN_CY, FAN_CZ])
        rotate([0, 90, 0]) {
            cylinder(d = FAN_APERTURE, h = cut_x_depth);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * FAN_MOUNT_SPG / 2,
                           sy * FAN_MOUNT_SPG / 2, 0])
                    cylinder(d = FAN_SCREW_D, h = cut_x_depth);
        }
}

module pi_case_cable_slots_bottom() {
    cutout_z = PI_Z0 + PI5_PCB_T - PORT_TOL;
    for (offset = [HDMI1_OFFSET, HDMI2_OFFSET]) {
        x = PI_X0 + offset - HDMI_SLOT[0] / 2;
        translate([x, -0.1, cutout_z])
            cube([HDMI_SLOT[0], OUTER_WALL + 0.2, HDMI_SLOT[1]]);
    }

    pwr_x = PI_X0 + PWR_OFFSET - PWR_SLOT[0] / 2;
    translate([pwr_x, -0.1, cutout_z])
        cube([PWR_SLOT[0], OUTER_WALL + 0.2, PWR_SLOT[1]]);

    sd_y = PI_Y0 + PI5_D / 2 - SD_SLOT[0] / 2;
    sd_z = PI_Z0 - SD_SLOT[1] / 2;
    translate([FLANGE_W - 0.1, sd_y, sd_z])
        cube([OUTER_WALL + 0.2, SD_SLOT[0], SD_SLOT[1]]);
}

module pi_case_cable_slots_top() {
    // BACK WALL upper half — two GX12 panel mounts flanking the
    // portcullis vent, sat 15 mm in from each corner so they tuck
    // alongside the back-left and back-right corner towers:
    //   left  : button GX12 (GPIO 17 arcade button)
    //   right : 1-Wire GX12 (DS18B20 bus → engine bay + exterior)
    //
    // GPS antenna coax now exits through the existing portcullis vent
    // gaps on the back wall — no dedicated SMA hole. The earlier v3
    // layout put all three holes on the FRONT wall but the print test
    // showed they aligned directly with the top of the Pi stack
    // internally, leaving no clean cable-routing path. Moving them to
    // the back keeps the front wall (HDMI / USB-C cutouts on the
    // bottom half only) clean.
    conn_z = FLOOR + INNER_H * 0.75;

    for (x_off = [15, OUTER_W - 15])
        translate([FLANGE_W + x_off,
                   OUTER_D + 0.1,
                   conn_z])
            rotate([90, 0, 0])
                cylinder(d = GX12_D,
                         h = OUTER_WALL + 0.2,
                         $fn = 48);
}

module pi_case_flange_holes() {
    // Bolt holes sit on each side flange BETWEEN the corner towers,
    // inset BOLT_TOWER_INSET past the tower outer edge. With towers at
    // (TOWER_X_*, TOWER_Y_F=0) and (..., TOWER_Y_B=OUTER_D) and tower
    // radius TOWER_OD/2, that puts the front bolt at y = TOWER_OD/2 +
    // BOLT_TOWER_INSET and the back at OUTER_D - TOWER_OD/2 -
    // BOLT_TOWER_INSET. Plenty of flange material around the hole and
    // socket access stays clear of the tower bodies.
    bolt_y_front = TOWER_OD / 2 + BOLT_TOWER_INSET;
    bolt_y_back  = OUTER_D - TOWER_OD / 2 - BOLT_TOWER_INSET;
    for (x = [FLANGE_MARGIN, TOTAL_W - FLANGE_MARGIN],
         y = [bolt_y_front, bolt_y_back])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = BOLT_HEAD_H + 0.1);
        }
}

module pi_case_clamshell_holes(bottom = true) {
    if (bottom) {
        for (x = [TOWER_X_L, TOWER_X_R], y = [TOWER_Y_F, TOWER_Y_B])
            translate([x, y, TRAY_TOP_Z - MAGNET_POCKET_H])
                cylinder(d = MAGNET_POCKET_D,
                         h = MAGNET_POCKET_H + 0.01);
    } else {
        for (x = [TOWER_X_L, TOWER_X_R], y = [TOWER_Y_F, TOWER_Y_B])
            translate([x, y, SPLIT_Z - 0.01])
                cylinder(d = MAGNET_POCKET_D,
                         h = MAGNET_POCKET_H + 0.01);
    }
}


// =====================================================
//   Corner buttress towers (case body)
// =====================================================
module pi_case_corner_towers(bottom = true) {
    z0 = bottom ? 0 : SPLIT_Z;
    z1 = bottom ? TRAY_TOP_Z : UPPER_TOP_Z;
    h  = z1 - z0;

    for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
        translate([cx, cy, z0])
            cylinder(d = TOWER_OD, h = h);

    // Battlement caps moved to the ROOF — case-body towers terminate at
    // UPPER_TOP_Z. The roof's corner caps continue them visually.
}

module castle_tower_arrow_slits() {
    for (corner = [[TOWER_X_L, TOWER_Y_F, 225],
                   [TOWER_X_R, TOWER_Y_F, 315],
                   [TOWER_X_L, TOWER_Y_B, 135],
                   [TOWER_X_R, TOWER_Y_B,  45]])
    {
        cx = corner[0];
        cy = corner[1];
        face_angle = corner[2];

        slit_span_z = TOWER_SLIT_H * TOWER_SLIT_COUNT
                      + (TOWER_SLIT_COUNT - 1) * 3;
        z_start = (INNER_H + FLOOR) / 2 - slit_span_z / 2;

        for (i = [0 : TOWER_SLIT_COUNT - 1]) {
            zc = z_start + i * (TOWER_SLIT_H + 3) + TOWER_SLIT_H / 2;
            translate([cx, cy, zc])
                rotate([0, 0, face_angle])
                    translate([TOWER_OD / 2 - 0.4, 0, 0])
                        rotate([90, 0, 0])
                            linear_extrude(height = TOWER_OD,
                                           center = true)
                                _arrow_slit_2d(TOWER_SLIT_W,
                                               TOWER_SLIT_H);
        }
    }
}

module _arrow_slit_2d(w, h) {
    cw = w * 3.0;
    ch = w;
    translate([-w / 2, -h / 2]) square([w, h]);
    translate([-cw / 2, -ch / 2]) square([cw, ch]);
}


// =====================================================
//   Seam course (stepped band along the clamshell split)
// =====================================================
module castle_seam_course(top = false) {
    // Decorative step centred on SPLIT_Z. v3 dropped the right-side gate
    // post bands — the gate post stubs are now only 4 mm tall and don't
    // span the seam zone at all.
    band_h = SEAM_COURSE_H / 2;
    z0 = top ? SPLIT_Z : SPLIT_Z - band_h;

    // Front wall band
    translate([FLANGE_W,
               -SEAM_STEP_PROJ,
               z0])
        cube([OUTER_W, SEAM_STEP_PROJ + OUTER_WALL, band_h]);

    // Back wall band
    translate([FLANGE_W,
               OUTER_D - OUTER_WALL,
               z0])
        cube([OUTER_W, SEAM_STEP_PROJ + OUTER_WALL, band_h]);

    // Left wall band
    translate([FLANGE_W - SEAM_STEP_PROJ, 0, z0])
        cube([SEAM_STEP_PROJ + OUTER_WALL, OUTER_D, band_h]);
}


// =====================================================
//   Running-bond mortar grooves
// =====================================================
module _mortar_face_y(w, h) {
    for (i = [1 : floor(h / STONE_ROW_H)]) {
        translate([0, 0, i * STONE_ROW_H - MORTAR_W / 2])
            cube([w, MORTAR_D + 0.01, MORTAR_W]);
    }
    for (row = [0 : floor(h / STONE_ROW_H)]) {
        voff = (row % 2 == 0) ? 0 : STONE_COL_W / 2;
        z0 = row * STONE_ROW_H;
        z1 = min((row + 1) * STONE_ROW_H, h);
        for (x = [voff + STONE_COL_W : STONE_COL_W : w]) {
            translate([x - MORTAR_W / 2, 0, z0])
                cube([MORTAR_W, MORTAR_D + 0.01, z1 - z0]);
        }
    }
}

module _mortar_face_x(w, h) {
    for (i = [1 : floor(h / STONE_ROW_H)]) {
        translate([0, 0, i * STONE_ROW_H - MORTAR_W / 2])
            cube([MORTAR_D + 0.01, w, MORTAR_W]);
    }
    for (row = [0 : floor(h / STONE_ROW_H)]) {
        voff = (row % 2 == 0) ? 0 : STONE_COL_W / 2;
        z0 = row * STONE_ROW_H;
        z1 = min((row + 1) * STONE_ROW_H, h);
        for (y = [voff + STONE_COL_W : STONE_COL_W : w]) {
            translate([0, y - MORTAR_W / 2, z0])
                cube([MORTAR_D + 0.01, MORTAR_W, z1 - z0]);
        }
    }
}

module castle_stone_mortar_bottom() {
    h = TRAY_TOP_Z - FLOOR;
    translate([FLANGE_W, -0.01, FLOOR])
        _mortar_face_y(OUTER_W, h);
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, FLOOR])
        mirror([1, 0, 0])
            mirror([0, 1, 0])
                _mortar_face_y(OUTER_W, h);
    translate([FLANGE_W - 0.01, 0, FLOOR])
        _mortar_face_x(OUTER_D, h);
}

module castle_stone_mortar_top() {
    h = UPPER_TOP_Z - SPLIT_Z;
    translate([FLANGE_W, -0.01, SPLIT_Z])
        _mortar_face_y(OUTER_W, h);
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, SPLIT_Z])
        mirror([1, 0, 0])
            mirror([0, 1, 0])
                _mortar_face_y(OUTER_W, h);
    translate([FLANGE_W - 0.01, 0, SPLIT_Z])
        _mortar_face_x(OUTER_D, h);
}


// =====================================================
//   Back-wall portcullis vent (top half)
// =====================================================
module castle_portcullis_vents() {
    cy = OUTER_D + 0.1;
    cx = FLANGE_W + OUTER_W / 2 - PORTCULLIS_W / 2;
    cz = SPLIT_Z + (UPPER_TOP_Z - SPLIT_Z) / 2 - PORTCULLIS_H / 2;

    translate([cx, cy, cz])
        rotate([90, 0, 0])
            linear_extrude(height = OUTER_WALL + 0.2)
                _portcullis_2d(PORTCULLIS_W, PORTCULLIS_H);
}

module _portcullis_2d(w, h) {
    difference() {
        _pointed_arch_2d(w, h);
        bar_spacing = w / (PORT_BAR_N + 1);
        for (i = [1 : PORT_BAR_N])
            translate([i * bar_spacing - PORT_BAR_W / 2, 0])
                square([PORT_BAR_W, h]);
        translate([0, h * 0.4 - PORT_BAR_W / 2])
            square([w, PORT_BAR_W]);
    }
}

module _pointed_arch_2d(w, h) {
    spring_h = h * 0.45;
    arch_r   = w;
    square([w, spring_h]);
    translate([0, spring_h])
        intersection() {
            circle(r = arch_r, $fn = 48);
            translate([w, 0]) circle(r = arch_r, $fn = 48);
            square([w, h - spring_h]);
        }
}


// =====================================================
//   Sword reliefs
// =====================================================
module castle_sword_2d() {
    translate([0, -SWORD_POMMEL_D / 2])
        circle(d = SWORD_POMMEL_D, $fn = 16);
    translate([-SWORD_GRIP_W / 2, 0])
        square([SWORD_GRIP_W, SWORD_GRIP_L]);
    translate([-SWORD_GUARD_W / 2, SWORD_GRIP_L])
        square([SWORD_GUARD_W, SWORD_GUARD_H]);
    translate([0, SWORD_GRIP_L + SWORD_GUARD_H])
        polygon([
            [-SWORD_BLADE_W / 2, 0],
            [ SWORD_BLADE_W / 2, 0],
            [ SWORD_TIP_W   / 2, SWORD_BLADE_L],
            [-SWORD_TIP_W   / 2, SWORD_BLADE_L]
        ]);
}

module castle_sword_relief_bottom() {
    guard_cy = SWORD_GRIP_L + SWORD_GUARD_H / 2;
    fcx = FLANGE_W + OUTER_W / 2;
    fcz = FLOOR + 8.5;

    for (angle = [25, -25])
        translate([fcx, -0.01, fcz])
            multmatrix([[1, 0, 0, 0],
                        [0, 0, 1, 0],
                        [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    rotate([0, 0, angle])
                        translate([0, -guard_cy])
                            castle_sword_2d();
}

module castle_sword_relief_top() {
    // Two standing swords on the back wall, flanking the portcullis,
    // pushed inward (x_off 27 instead of 14) to leave clear space for
    // the back-wall GX12 cutouts at x_off 15 — pi_case_cable_slots_top.
    guard_cy = SWORD_GRIP_L + SWORD_GUARD_H / 2;
    bcz = SPLIT_Z + (UPPER_TOP_Z - SPLIT_Z) * 0.3;

    for (x_off = [27, OUTER_W - 27])
        translate([FLANGE_W + x_off, OUTER_D + 0.01, bcz])
            multmatrix([[1, 0, 0, 0],
                        [0, 0, -1, 0],
                        [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    translate([0, -guard_cy])
                        castle_sword_2d();
}


// =====================================================
//   Fan intake ring (left wall)
// =====================================================
module castle_fan_arch_bottom() {
    // Fan straddles the seam and the ring decoration is on the top half.
}

module castle_fan_arch_top() {
    translate([FLANGE_W - FAN_FRAME_T, FAN_CY, FAN_CZ])
        rotate([0, 90, 0])
            difference() {
                cylinder(d = FAN_FRAME_OD, h = FAN_FRAME_T, $fn = 48);
                translate([0, 0, -0.1])
                    cylinder(d = FAN_APERTURE,
                             h = FAN_FRAME_T + 0.2,
                             $fn = 48);
            }
}


// =====================================================
//   ROOF — solid geometry
// =====================================================
module roof_plate() {
    // Full-area plate matching the case OUTER_W × OUTER_D footprint, plus
    // circular corner caps that cover the half-tower projecting outside
    // the rectangle. Bond surface matches pi_case_top_lid_plate so the
    // solvent weld lands on flat-on-flat material everywhere — including
    // the tower-top crescents.
    // Roof prints with bottom (bond) face on the bed; decoration rises
    // upward from Z = ROOF_PLATE_T.
    translate([FLANGE_W, 0, 0])
        cube([OUTER_W, OUTER_D, ROOF_PLATE_T]);
    for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
        translate([cx, cy, 0])
            cylinder(d = TOWER_OD, h = ROOF_PLATE_T);
}

module roof_machicolation() {
    // Corbelled overhang ring just above the plate, four bands tracing
    // the perimeter only. Projects outward beyond the plate edge by
    // MACHI_PROJ; the perimeter crenellations land on its outer face.
    // Centre is left clear so the shield + vent cuts read cleanly.
    z0 = ROOF_PLATE_T;
    band_t = OUTER_WALL;

    // Front band
    translate([FLANGE_W - MACHI_PROJ,
               -MACHI_PROJ,
               z0])
        cube([OUTER_W + 2 * MACHI_PROJ,
              MACHI_PROJ + band_t,
              MACHI_BAND_H]);
    // Back band
    translate([FLANGE_W - MACHI_PROJ,
               OUTER_D - band_t,
               z0])
        cube([OUTER_W + 2 * MACHI_PROJ,
              MACHI_PROJ + band_t,
              MACHI_BAND_H]);
    // Left band
    translate([FLANGE_W - MACHI_PROJ,
               0,
               z0])
        cube([MACHI_PROJ + band_t,
              OUTER_D,
              MACHI_BAND_H]);
    // Right band (full edge — drawbridge relief sits on top of it)
    translate([FLANGE_W + OUTER_W - band_t,
               0,
               z0])
        cube([MACHI_PROJ + band_t,
              OUTER_D,
              MACHI_BAND_H]);
}

module roof_machicolation_holes() {
    // Murder-hole slots cut down through the corbel band, between the
    // perimeter merlons. Dropped into the band as small rectangular
    // slots at MACHI_HOLE_GAP intervals along each wall.
    z0 = ROOF_PLATE_T - 0.05;
    h  = MACHI_BAND_H + 0.1;
    eps = 0.05;

    // Front and back walls (along X)
    for (i = [3 : floor((OUTER_W - 6) / MACHI_HOLE_GAP)]) {
        x = FLANGE_W + i * MACHI_HOLE_GAP;
        // Front
        translate([x - MACHI_HOLE_W / 2,
                   -MACHI_PROJ - eps,
                   z0])
            cube([MACHI_HOLE_W,
                  MACHI_PROJ + MACHI_HOLE_D,
                  h]);
        // Back
        translate([x - MACHI_HOLE_W / 2,
                   OUTER_D + MACHI_PROJ + eps - (MACHI_PROJ + MACHI_HOLE_D),
                   z0])
            cube([MACHI_HOLE_W,
                  MACHI_PROJ + MACHI_HOLE_D,
                  h]);
    }

    // Left and right walls (along Y)
    for (i = [1 : floor((OUTER_D - 6) / MACHI_HOLE_GAP)]) {
        y = i * MACHI_HOLE_GAP;
        // Left
        translate([FLANGE_W - MACHI_PROJ - eps,
                   y - MACHI_HOLE_W / 2,
                   z0])
            cube([MACHI_PROJ + MACHI_HOLE_D,
                  MACHI_HOLE_W,
                  h]);
        // Right (between gate-post stub regions only — keep the
        // gatehouse-mouth panel solid for the drawbridge relief)
        if (y > GATE_POST_L + 1 && y < OUTER_D - GATE_POST_L - 1)
            translate([FLANGE_W + OUTER_W + MACHI_PROJ + eps - (MACHI_PROJ + MACHI_HOLE_D),
                       y - MACHI_HOLE_W / 2,
                       z0])
                cube([MACHI_PROJ + MACHI_HOLE_D,
                      MACHI_HOLE_W,
                      h]);
    }
}

module roof_perimeter_crenellations() {
    // Merlons sit on top of the machicolation band, at the perimeter of
    // the roof. Each merlon has a pyramidal cap rising above. Arrow slits
    // are subtracted in roof_merlon_arrow_slits().
    period = MERLON_W + CRENEL_W;
    z_base = ROOF_PLATE_T + MACHI_BAND_H;

    // Front (Y = 0) — merlons sit just inside the machicolation outer
    // edge (Y = -MACHI_PROJ), with the merlon body OUTER_WALL deep.
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        x = FLANGE_W + i * period;
        // skip merlons that overlap corner cap footprint
        if (x > TOWER_X_L + TOWER_OD / 2 - 1
            && x + MERLON_W < TOWER_X_R - TOWER_OD / 2 + 1)
            translate([x, -MACHI_PROJ, z_base])
                _merlon_with_cap(MERLON_W, OUTER_WALL);
    }

    // Back (Y = OUTER_D)
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        x = FLANGE_W + i * period;
        if (x > TOWER_X_L + TOWER_OD / 2 - 1
            && x + MERLON_W < TOWER_X_R - TOWER_OD / 2 + 1)
            translate([x,
                       OUTER_D + MACHI_PROJ - OUTER_WALL,
                       z_base])
                _merlon_with_cap(MERLON_W, OUTER_WALL);
    }

    // Left (X = FLANGE_W)
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        y = OUTER_WALL + i * period;
        if (y > TOWER_OD / 2 - 1
            && y + MERLON_W < OUTER_D - TOWER_OD / 2 + 1)
            translate([FLANGE_W - MACHI_PROJ, y, z_base])
                _merlon_with_cap_y(MERLON_W, OUTER_WALL);
    }

    // Right (X = FLANGE_W + OUTER_W) — only across gate post stubs to
    // keep the drawbridge panel uninterrupted.
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        y = OUTER_WALL + i * period;
        if (y + MERLON_W < GATE_POST_L + OUTER_WALL
            || y > OUTER_D - GATE_POST_L - OUTER_WALL)
            translate([FLANGE_W + OUTER_W + MACHI_PROJ - OUTER_WALL,
                       y,
                       z_base])
                _merlon_with_cap_y(MERLON_W, OUTER_WALL);
    }
}

module _merlon_with_cap(w, d) {
    // Merlon extruded along X with depth in Y. Pyramidal cap on top.
    cube([w, d, MERLON_H]);
    translate([0, 0, MERLON_H])
        linear_extrude(height = MERLON_CAP_H, scale = 0.05)
            square([w, d]);
}

module _merlon_with_cap_y(w, d) {
    // Merlon for left/right walls — extruded along Y, depth in X.
    cube([d, w, MERLON_H]);
    translate([0, 0, MERLON_H])
        linear_extrude(height = MERLON_CAP_H, scale = 0.05)
            square([d, w]);
}

module roof_merlon_arrow_slits() {
    // Subtract a vertical slit through each perimeter merlon, parallel
    // to the wall it sits on. The slit pierces the merlon body so light
    // / air pass through.
    period = MERLON_W + CRENEL_W;
    z_base = ROOF_PLATE_T + MACHI_BAND_H;
    slit_z = z_base + (MERLON_H - MERLON_SLIT_H) / 2;
    eps = 0.1;

    // Front & back — slit oriented along Y (depth), cut across full
    // OUTER_WALL of merlon.
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        x = FLANGE_W + i * period;
        if (x > TOWER_X_L + TOWER_OD / 2 - 1
            && x + MERLON_W < TOWER_X_R - TOWER_OD / 2 + 1) {
            // Front slit
            translate([x + MERLON_W / 2 - MERLON_SLIT_W / 2,
                       -MACHI_PROJ - eps,
                       slit_z])
                cube([MERLON_SLIT_W, OUTER_WALL + 2 * eps, MERLON_SLIT_H]);
            // Back slit
            translate([x + MERLON_W / 2 - MERLON_SLIT_W / 2,
                       OUTER_D + MACHI_PROJ - OUTER_WALL - eps,
                       slit_z])
                cube([MERLON_SLIT_W, OUTER_WALL + 2 * eps, MERLON_SLIT_H]);
        }
    }

    // Left & right — slit oriented along X
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        y = OUTER_WALL + i * period;
        // Left
        if (y > TOWER_OD / 2 - 1
            && y + MERLON_W < OUTER_D - TOWER_OD / 2 + 1)
            translate([FLANGE_W - MACHI_PROJ - eps,
                       y + MERLON_W / 2 - MERLON_SLIT_W / 2,
                       slit_z])
                cube([OUTER_WALL + 2 * eps, MERLON_SLIT_W, MERLON_SLIT_H]);
        // Right (only across gate post stubs)
        if (y + MERLON_W < GATE_POST_L + OUTER_WALL
            || y > OUTER_D - GATE_POST_L - OUTER_WALL)
            translate([FLANGE_W + OUTER_W + MACHI_PROJ - OUTER_WALL - eps,
                       y + MERLON_W / 2 - MERLON_SLIT_W / 2,
                       slit_z])
                cube([OUTER_WALL + 2 * eps, MERLON_SLIT_W, MERLON_SLIT_H]);
    }
}

module roof_corner_caps() {
    // Continue each case-body corner tower upward from the roof plate:
    //   corbel ring → ring of merlons → conical roof
    z0 = ROOF_PLATE_T;
    for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B]) {
        translate([cx, cy, z0]) {
            // Corbel ring (slight outward step from tower OD)
            cylinder(d = TOWER_OD + 2 * TOWER_CAP_CORBEL_PROJ,
                     h = TOWER_CAP_CORBEL_H);
            // Battlement merlons
            translate([0, 0, TOWER_CAP_CORBEL_H])
                _tower_cap_merlons();
            // Conical roof
            translate([0, 0, TOWER_CAP_CORBEL_H + TOWER_CAP_MERLON_H])
                cylinder(d1 = TOWER_OD,
                         d2 = TOWER_CAP_CONE_TIP_D,
                         h  = TOWER_CAP_CONE_H);
        }
    }
}

module _tower_cap_merlons() {
    r_out = TOWER_OD / 2 + TOWER_CAP_CORBEL_PROJ;
    r_in  = r_out - TOWER_CAP_MERLON_W;
    for (i = [0 : TOWER_CAP_MERLON_N - 1]) {
        a = i * (360 / TOWER_CAP_MERLON_N);
        rotate([0, 0, a])
            translate([r_in, -TOWER_CAP_MERLON_W / 2, 0])
                cube([TOWER_CAP_MERLON_W,
                      TOWER_CAP_MERLON_W,
                      TOWER_CAP_MERLON_H]);
    }
}

module roof_corner_flag() {
    // Pennant flag on the back-right tower's cone tip.
    cx = TOWER_X_R;
    cy = TOWER_Y_B;
    cone_top_z = ROOF_PLATE_T
                 + TOWER_CAP_CORBEL_H
                 + TOWER_CAP_MERLON_H
                 + TOWER_CAP_CONE_H;

    // Mast continues up from the cone tip
    translate([cx, cy, cone_top_z - 0.5])
        cylinder(d = FLAG_MAST_D, h = FLAG_MAST_H, $fn = 16);

    // Triangular pennant attached to mast, projecting in +X then tapering
    flag_z0 = cone_top_z + FLAG_MAST_H * 0.3;
    translate([cx, cy + FLAG_MAST_D / 2, flag_z0])
        rotate([90, 0, 0])
            linear_extrude(height = FLAG_T)
                polygon([[0, 0],
                         [FLAG_W, FLAG_H / 2],
                         [0, FLAG_H]]);
}

module roof_shield() {
    // Heater shield + chevron sigil at roof centre.
    cx = FLANGE_W + OUTER_W / 2;
    cy = OUTER_D / 2;
    z0 = ROOF_PLATE_T;

    translate([cx, cy - SHIELD_H / 2, z0]) {
        // Border
        linear_extrude(SHIELD_RAISE)
            difference() {
                castle_shield_2d(SHIELD_W, SHIELD_H);
                offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
            }
        // Field (recessed)
        linear_extrude(SHIELD_RAISE * 0.5)
            offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
        // Chevron device
        linear_extrude(SHIELD_RAISE)
            intersection() {
                offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
                castle_chevron_2d(SHIELD_W * 0.5, SHIELD_H * 0.15);
            }
    }
}

module castle_shield_2d(w, h) {
    hull() {
        translate([-w / 2 + 3, h - 3]) circle(r = 3, $fn = 24);
        translate([ w / 2 - 3, h - 3]) circle(r = 3, $fn = 24);
        translate([-w / 2 + 3, h * 0.55]) circle(r = 3, $fn = 24);
        translate([ w / 2 - 3, h * 0.55]) circle(r = 3, $fn = 24);
        circle(r = 0.5, $fn = 12);
    }
}

module castle_chevron_2d(w, h) {
    chev_t = 2;
    translate([0, SHIELD_H * 0.32])
        polygon([[-w / 2, 0], [0, h], [w / 2, 0],
                 [w / 2, -chev_t], [0, h - chev_t], [-w / 2, -chev_t]]);
}

module roof_vent_cuts() {
    // Cross-shaped ventilation cuts through the roof plate, flanking the
    // shield. These line up over the TOP's central lid cutout so air
    // flows interior → top cutout → roof crosses → atmosphere.
    cx = FLANGE_W + OUTER_W / 2;
    slit_w  = 1.5;
    slit_h  = 10;
    spacing_y = 7;
    cut_h   = ROOF_PLATE_T + MACHI_BAND_H + 0.4;

    for (side = [-1, 1]) {
        x = cx + side * (SHIELD_W / 2 + 8);
        for (j = [0 : 3]) {
            y = OUTER_D / 2 - 1.5 * spacing_y + j * spacing_y;
            translate([x, y, -0.1])
                linear_extrude(cut_h)
                    _arrow_slit_2d(slit_w, slit_h);
        }
    }
}

module roof_drawbridge_relief_solid() {
    // Solid panel band across the gatehouse edge, between the front- and
    // back-right corner caps. Raised slightly above the corbel band so
    // the engraved planks read as relief rather than holes.
    panel_x = FLANGE_W + OUTER_W + MACHI_PROJ - 0.1;
    panel_y0 = TOWER_OD / 2;
    panel_y1 = OUTER_D - TOWER_OD / 2;
    panel_z0 = ROOF_PLATE_T + MACHI_BAND_H;
    panel_h  = MERLON_H * 0.45;            // about half the merlon height

    translate([panel_x - BRIDGE_INSET,
               panel_y0,
               panel_z0])
        cube([BRIDGE_INSET + 0.1,
              panel_y1 - panel_y0,
              panel_h]);
}

module roof_drawbridge_grooves() {
    // Engraved horizontal plank lines across the drawbridge panel.
    panel_x = FLANGE_W + OUTER_W + MACHI_PROJ;
    panel_y0 = TOWER_OD / 2;
    panel_y1 = OUTER_D - TOWER_OD / 2;
    panel_h  = MERLON_H * 0.45;
    panel_z0 = ROOF_PLATE_T + MACHI_BAND_H;
    grooves = floor((panel_y1 - panel_y0) / (BRIDGE_PLANK_W + BRIDGE_PLANK_GAP));

    for (i = [1 : grooves - 1]) {
        y = panel_y0 + i * (BRIDGE_PLANK_W + BRIDGE_PLANK_GAP);
        translate([panel_x - BRIDGE_RELIEF,
                   y - BRIDGE_PLANK_GAP / 2,
                   panel_z0 - 0.1])
            cube([BRIDGE_RELIEF + 0.2,
                  BRIDGE_PLANK_GAP,
                  panel_h + 0.2]);
    }
}

module roof_corner_gargoyles() {
    // One outward-facing gargoyle per corner cap, projecting from the
    // corbel ring at 45° (away from case centre). Small rectangular
    // spout — visible on all four exterior corners. Below 45° overhang
    // (3 mm long × 1.5 mm wide × 1.5 mm tall), so PETG handles it
    // without support.
    z0 = ROOF_PLATE_T + TOWER_CAP_CORBEL_H * 0.4;
    spout_l = 3.5;
    spout_w = 1.6;
    spout_h = 1.6;

    for (corner = [[TOWER_X_L, TOWER_Y_F, 225],
                   [TOWER_X_R, TOWER_Y_F, 315],
                   [TOWER_X_L, TOWER_Y_B, 135],
                   [TOWER_X_R, TOWER_Y_B,  45]])
    {
        cx = corner[0];
        cy = corner[1];
        a  = corner[2];
        translate([cx, cy, z0])
            rotate([0, 0, a])
                translate([TOWER_OD / 2 + TOWER_CAP_CORBEL_PROJ - 0.4,
                           -spout_w / 2,
                           0])
                    cube([spout_l, spout_w, spout_h]);
    }
}

module roof_crenel_gap_slits() {
    // Optional vent slits dropping through the machicolation band in
    // each crenel gap (between perimeter merlons). Adds extra vent area
    // beyond the cross slits flanking the shield.
    period = MERLON_W + CRENEL_W;
    slit_w  = 1.0;
    slit_z0 = ROOF_PLATE_T - 0.05;
    slit_h  = MACHI_BAND_H + 0.1;
    eps = 0.05;

    // Front + back (slit oriented along Y, cuts through the band)
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        x_merlon_end = FLANGE_W + i * period + MERLON_W;
        x_crenel = x_merlon_end + CRENEL_W / 2 - slit_w / 2;
        if (x_crenel > TOWER_X_L + TOWER_OD / 2
            && x_crenel + slit_w < TOWER_X_R - TOWER_OD / 2) {
            // Front
            translate([x_crenel,
                       -MACHI_PROJ - eps,
                       slit_z0])
                cube([slit_w,
                      MACHI_PROJ + OUTER_WALL + 2 * eps,
                      slit_h]);
            // Back
            translate([x_crenel,
                       OUTER_D - OUTER_WALL - eps,
                       slit_z0])
                cube([slit_w,
                      MACHI_PROJ + OUTER_WALL + 2 * eps,
                      slit_h]);
        }
    }

    // Left + right (slit oriented along X)
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        y_merlon_end = OUTER_WALL + i * period + MERLON_W;
        y_crenel = y_merlon_end + CRENEL_W / 2 - slit_w / 2;
        // Left
        if (y_crenel > TOWER_OD / 2
            && y_crenel + slit_w < OUTER_D - TOWER_OD / 2)
            translate([FLANGE_W - MACHI_PROJ - eps,
                       y_crenel,
                       slit_z0])
                cube([MACHI_PROJ + OUTER_WALL + 2 * eps,
                      slit_w,
                      slit_h]);
        // Right — only across the gate post stubs (drawbridge panel
        // covers the middle span).
        if (y_crenel + slit_w < GATE_POST_L + OUTER_WALL
            || y_crenel > OUTER_D - GATE_POST_L - OUTER_WALL)
            translate([FLANGE_W + OUTER_W - OUTER_WALL - eps,
                       y_crenel,
                       slit_z0])
                cube([MACHI_PROJ + OUTER_WALL + 2 * eps,
                      slit_w,
                      slit_h]);
    }
}

module roof_perimeter_rope_grooves() {
    // Cord-twist relief engraved on the bottom-perimeter outer face of
    // the roof plate. When the roof is bonded to the top, this band
    // sits at the visible seam — a row of short angled grooves reading
    // as a twisted rope from a few feet away. Cuts only into the outer
    // face (depth 0.4 mm), so the bond surface and machicolation
    // overhang are untouched.
    rope_z = 0.3;          // band centre Z (well below ROOF_PLATE_T = 2)
    rope_h = 0.8;          // engraving height
    rope_d = 0.4;          // depth into the outer face
    rope_w = 1.0;          // groove width
    rope_pitch = 2.5;      // groove period along the wall
    eps = 0.1;

    // Front + back (grooves along X). Skip merlon-cap zones at the
    // corners — the merlon caps are at z = MACHI_BAND_H + MERLON_H + ...
    // which is well above rope_z, so no actual collision; just visual
    // alignment of pattern with corner cap circle.
    for (x = [FLANGE_W + 6 : rope_pitch : FLANGE_W + OUTER_W - 6]) {
        // Front
        translate([x - rope_w / 2,
                   -MACHI_PROJ - eps,
                   rope_z - rope_h / 2])
            rotate([0, 30, 0])
                cube([rope_w, rope_d + eps, rope_h]);
        // Back
        translate([x - rope_w / 2,
                   OUTER_D + MACHI_PROJ - rope_d,
                   rope_z - rope_h / 2])
            rotate([0, 30, 0])
                cube([rope_w, rope_d + eps, rope_h]);
    }

    // Left + right (grooves along Y)
    for (y = [6 : rope_pitch : OUTER_D - 6]) {
        // Left
        translate([FLANGE_W - MACHI_PROJ - eps,
                   y - rope_w / 2,
                   rope_z - rope_h / 2])
            rotate([0, 0, 30])
                cube([rope_d + eps, rope_w, rope_h]);
        // Right
        translate([FLANGE_W + OUTER_W + MACHI_PROJ - rope_d,
                   y - rope_w / 2,
                   rope_z - rope_h / 2])
            rotate([0, 0, 30])
                cube([rope_d + eps, rope_w, rope_h]);
    }
}
