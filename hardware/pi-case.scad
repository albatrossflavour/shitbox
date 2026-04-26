// Shitbox Rally — Pi 5 stack enclosure v2 — CASTLE CLAMSHELL EDITION
//
// Horizontally-split clamshell shell with open right (USB-A / Ethernet)
// short wall. Rally-side service wins over full seal: the upper half
// lifts clear of the tray on four M3 clamshell bolts, exposing the
// perma-proto HAT, GPIO extender and top of the Pi 5 stack without
// disturbing the NVMe HAT, brass standoffs or any cable routed through
// a fixed wall. USB ports stay permanently accessible through the
// skeletal right-side gatehouse.
//
// Stack (bottom to top):
//   NVMe HAT (HAT_H = 20 mm) → Pi 5 PCB → active cooler →
//   GPIO extender → perma-proto HAT
//
// Pi 5 orientation (same as v1):
//   HDMI / USB-C / fan header long edge → case FRONT (Y=0)
//   GPIO header long edge                → case BACK (Y=OUTER_D)
//   USB-A + Ethernet short edge          → case RIGHT (+X, open gatehouse)
//   Display + SD short edge              → case LEFT (-X)
//
// Fasteners:
//   Pi mount     — 4× M2.5 heat-set inserts in floor → brass standoffs
//                  carry the NVMe HAT, then Pi.
//   Plywood mnt  — 4× M4 through-hole flanges on left+right exteriors.
//   Clamshell    — 4× M3 cap screws down through the four corner
//                  buttress towers; M3 heat-set inserts in the tray
//                  tower tops, clearance hole + cap-head recess up
//                  through the upper tower, corbel and battlement ring.
//                  Interior bolt posts are deliberately absent so the
//                  four Pi mounts are clear and the Pi stack is fully
//                  4-point supported under rally vibration.
//
// v1 bugs fixed (see memory: project_pi_case_v2):
//   1. USB cutout count — right short wall is absent (open gatehouse).
//   2. USB-C X offset   — anchored to USB/Ethernet short edge regardless
//                         of which wall is present.
//   3. GX12/SMA cutouts — rotation fixed so cylinders pierce the back
//                         wall fully rather than leaving a 0.1 mm sliver.
//   4. GX12 labelled    — left port is the arcade BUTTON on GPIO 17.
//   5. Back-wall ports  — standardised on GX12 panel mounts: left port
//                         BUTTON, right port 1-WIRE bus, flanking the
//                         portcullis at upper-third Z. SMA (GPS) drops
//                         to centre-X low (FLOOR+8) so the castle face
//                         reads symmetric.
//   6. Pi mounting      — brass standoffs into heat-set inserts at all
//                         FOUR Pi mount positions. Clamshell bolts
//                         relocated into corner towers so they no
//                         longer collide with the display-side Pi
//                         mount pair.
//   7. Seam lip         — replaced free-standing 0.8×3 mm tab (snapped
//                         off on first print) with a 50/50 shiplap:
//                         tray walls extend LIP_DROP above SPLIT_Z as
//                         an outer slice, upper walls carry a matching
//                         inner-slice skirt. Full wall cross-section
//                         through the overlap, nothing cantilevered.
//
// Castle features (print-safe set — see repo notes for what was
// considered and dropped for PETG overhang margin):
//   - Corner buttress towers at all 4 exterior corners, full height,
//     crenellated battlements, arrow slits on each tower face.
//   - Stepped battered course along the clamshell seam (decorative
//     thickening that masks the split line; zero overhang).
//   - Gatehouse pointed arch (frame only — no hanging bars) across the
//     open right side, structural top beam.
//   - Running-bond mortar grooves on the three solid walls.
//   - Sword relief carvings on front and back walls.
//   - Portcullis vents (decorative ogival arch with bars) on back wall.
//   - Crenellated battlements around lid perimeter.
//   - Heater-shield sigil with chevron on lid.
//   - Cross-shaped arrow-slit ventilation through lid.
//   - Fan intake arch ring around the 40 mm Noctua on left wall.
//
// Units: mm. $fn = 64 for STL export; reduce for live preview.
//
// All key dimensions measured with calipers 2026-04-17 ±0.5 mm.

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
PI5_INSET          = 3.5;
PI5_HOLE_W         = 58.0;
PI5_HOLE_D_SPACING = 49.0;

// ---- Stack heights (measured 2026-04-17) ----
STACK_H = 65;        // full stack, NVMe HAT bottom to perma-proto top
HAT_H   = 20;        // NVMe HAT: floor to Pi 5 PCB bottom

// ---- Pi 5 connector offsets (from RPi mech drawing) ----
// All X offsets measure inward from the USB/Ethernet short edge plane.
// In v2 that wall is absent, but the offset reference plane is the
// same virtual line. HDMI0 is the cable we actually use (screen).
HDMI1_OFFSET = 26.0;
HDMI2_OFFSET = 39.5;
HDMI_PORT_H  = 3.5;
USB_OFFSET   = 29.0;
PWR_OFFSET   = 11.5;
PWR_PORT_H   = 3.5;

// ---- Fan (Noctua NF-A4x10 5V) ----
FAN_W         = 40;
FAN_MOUNT_SPG = 32;
FAN_SCREW_D   = 3.4;   // M3 clearance
FAN_APERTURE  = 37;

// ---- Back-wall connector cutouts ----
GX12_D     = 12.5;     // arcade button (GPIO 17) — 12 mm panel mount + 0.5 mm
SMA_HOLE_D = 6.7;      // GPS antenna SMA bulkhead — 6.35 mm + 0.35 mm

// ---- Pi mounting: heat-set inserts in floor ----
// RUTHEX M2.5 short inserts — 4.0 mm pocket D, 5 mm depth.
// Boss height chosen so the insert seats blind (pocket stays above
// the floor underside): FLOOR (2.5) + BOSS_H_M25 (3.0) = 5.5 mm,
// ≥ INSERT_H_M25 (5.0).
INSERT_D_M25     = 4.0;
INSERT_H_M25     = 5.0;
BOSS_H_M25       = 3.0;
STANDOFF_BOSS_OD = 7.0;   // boss wrapping the insert for lateral rigidity

// ---- Mounting flanges (M4 to plywood panel) ----
FLANGE_W     = 12;
FLANGE_THICK = 3.0;
BOLT_D       = 4.5;
BOLT_HEAD_D  = 8.5;
BOLT_HEAD_H  = 1.5;
FLANGE_MARGIN = 6;       // flange bolt hole inset from flange edge

// ---- Clamshell closure (4× N35 magnet pairs, 4×2 mm) ----
// Closure lives in the four corner buttress towers, opening toward the
// seam. Lid is ~120 g of PETG, alignment lip carries shear, magnets only
// resist gravity + vibration lift-off. 4 pairs × ~300 g pull each
// ≫ lid mass under 1–2 g rally loads (≥4× margin worst case).
MAGNET_D        = 4.0;     // N35 disc magnet diameter
MAGNET_H        = 2.0;     // N35 disc magnet height
MAGNET_POCKET_D = 4.1;     // press-fit clearance (0.05 mm radial)
MAGNET_POCKET_H = MAGNET_H + 0.1;  // 0.1 mm seat clearance

// Parked: bolts replaced by magnets. Constants left in place in case a
// future revision wants to revert. Not currently referenced.
CLAM_BOLT_D       = 3.4;   // M3 clearance
CLAM_BOLT_HEAD_D  = 6.0;   // M3 cap head
CLAM_BOLT_HEAD_H  = 3.2;   // counterbore depth in upper half
INSERT_D_M3       = 4.6;   // RUTHEX M3 pocket D
INSERT_H_M3       = 6.0;

// ---- Clamshell geometry ----
SPLIT_Z    = 33;           // seam Z, above Pi PCB + active cooler
INNER_H    = STACK_H + 5;  // 70 mm interior — 5 mm clearance above stack

// Shiplap seam (replaces earlier thin-tab alignment lip).
// Tray walls extend LIP_DROP above SPLIT_Z carrying only their OUTER
// slice (LIP_SLICE thick); upper walls start at SPLIT_Z with an
// INNER-slice skirt of matching width that nests alongside. Total
// wall cross-section through the overlap is full OUTER_WALL — no
// free-standing thin feature to shear at the layer line. 50/50 split
// keeps both slices at ≥3 perimeters on a 0.4 mm nozzle.
LIP_SLICE = OUTER_WALL / 2;  // 1.25 mm — outer slice on tray, inner slice on upper
LIP_DROP  = 3.0;             // vertical overlap depth (inside seam at SPLIT_Z,
                             // outside seam at SPLIT_Z + LIP_DROP)

// ---- Cable exit slots ----
HDMI_SLOT    = [15, 10];
USB_SLOT     = [15, 18];    // (unused — right wall absent)
PWR_SLOT     = [12, 8];
QWIIC_SLOT   = [7, 5];
ONEWIRE_SLOT = [6, 4];
SD_SLOT      = [16, 4];     // microSD extraction clearance on left wall

// ---- Lid ----
LID_THICK = 1.6;


// =====================================================
//   Castle decoration parameters
// =====================================================

// Running-bond stone mortar
MORTAR_W    = 0.4;
MORTAR_D    = 0.5;        // leaves 2.0 mm structural wall
STONE_ROW_H = 7.0;
STONE_COL_W = 11.0;

// Lid perimeter crenellations
MERLON_W = 5.0;
MERLON_H = 5.0;
CRENEL_W = 4.0;

// Corner buttress towers
TOWER_OD         = 12.0;   // tower outer diameter — sized so clamshell
                           // bolt at tower centre clears the Pi
                           // display-side standoff boss with room to
                           // spare (centre-to-centre 9.19 mm, insert r
                           // 2.3 + boss r 3.5 = 5.8 mm, margin 3.4 mm).
TOWER_CORBEL_H   = 2.0;    // stepped corbel table height under battlements
TOWER_CORBEL_PROJ= 0.8;    // corbel table outward projection
TOWER_SLIT_W     = 1.2;    // arrow slit width in tower face
TOWER_SLIT_H     = 7.0;    // arrow slit height
TOWER_SLIT_COUNT = 3;      // vertical slits stacked per tower face
TOWER_MERLON_N   = 8;      // battlement merlons ringing each tower top
TOWER_MERLON_W   = 2.8;
TOWER_MERLON_H   = 3.5;

// Stepped battered course masking the clamshell seam
SEAM_COURSE_H    = 2.5;    // total vertical height of the decorative band
SEAM_STEP_PROJ   = 0.5;    // outward projection of each step (×2 steps)

// Gatehouse pointed arch across the open right side (frame only)
GATE_FRAME_T     = 2.5;    // arch frame wall thickness
GATE_HEADER_H    = 8.0;    // depth of horizontal stone header under arch

// Decorative portcullis vent on back wall (ogival arch with bars)
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

// Heater shield sigil on lid
SHIELD_W     = 28;
SHIELD_H     = 35;
SHIELD_RAISE = 0.8;

// Fan intake ring
FAN_FRAME_OD = FAN_APERTURE + 6;
FAN_FRAME_T  = 0.8;


// =====================================================
//   Derived dimensions
// =====================================================
INNER_W = PI5_W + PCB_TOL;
INNER_D = PI5_D + PCB_TOL;
OUTER_W = INNER_W + 2 * OUTER_WALL;
OUTER_D = INNER_D + 2 * OUTER_WALL;
TOTAL_W = OUTER_W + 2 * FLANGE_W;

// Pi PCB origin relative to outer shell
PI_X0 = FLANGE_W + OUTER_WALL + PCB_TOL / 2;
PI_Y0 = OUTER_WALL + PCB_TOL / 2;
PI_Z0 = FLOOR + HAT_H;   // Pi PCB bottom

// Virtual USB/Ethernet reference plane (right short edge of Pi)
RIGHT_EDGE_X = PI_X0 + PI5_W;

// Fan centre on left wall — positioned so the aperture bottom sits
// exactly on the clamshell seam (FAN_CZ - FAN_APERTURE/2 = SPLIT_Z).
FAN_CZ = SPLIT_Z + FAN_APERTURE / 2;
FAN_CY = OUTER_D / 2;

// Split geometry
TRAY_TOP_Z  = SPLIT_Z;           // tray walls stop here
UPPER_TOP_Z = FLOOR + INNER_H;   // top of walls (below lid plate)
UPPER_WALL_H = UPPER_TOP_Z - SPLIT_Z;

// Corner tower centres (at case-shell outer corners)
TOWER_X_L = FLANGE_W;
TOWER_X_R = FLANGE_W + OUTER_W;
TOWER_Y_F = 0;
TOWER_Y_B = OUTER_D;

// Clamshell bolts live at the centres of the four corner buttress
// towers — NOT inside the case — so they do not collide with the Pi
// mount grid. See pi_case_clamshell_holes().

// Right-side gatehouse — width of the open bay
//   Front/back walls keep a short stub (GATE_POST_L) at their +X end
//   to carry the portcullis arch springings and the back-right tower
//   shoulder. Between those stubs is open air (the gate).
GATE_POST_L = 11.0;  // stub length along +X from wall inner face
                     // (tuned to hide tower-wall join and give the
                     // gatehouse arch a visible spring point)
GATE_OPENING_Y0 = GATE_POST_L;               // opening starts at this Y from Y=0
GATE_OPENING_Y1 = OUTER_D - GATE_POST_L;     // opening ends here
GATE_OPENING_H  = INNER_H;                   // full interior height


// =====================================================
//   Main — render tray and upper half side by side
// =====================================================
pi_case_tray();
translate([0, OUTER_D + TOWER_OD + 15, 0]) pi_case_upper();

// Assembled preview: uncomment to stack upper over tray.
// pi_case_tray();
// translate([0, 0, 0.01]) pi_case_upper();


// =====================================================
//   Tray (bottom clamshell half)
// =====================================================
module pi_case_tray() {
    difference() {
        union() {
            pi_case_base_plate();
            pi_case_tray_walls();
            pi_case_gate_posts(tray = true);
            pi_case_corner_towers(tray = true);
            pi_case_standoff_bosses();
            castle_fan_arch_tray();          // fan partially in tray if any overhang
            castle_seam_course(upper = false);
        }
        pi_case_standoff_insert_holes();
        pi_case_cable_slots_tray();
        pi_case_flange_holes();
        pi_case_clamshell_holes(tray = true);
        castle_tower_arrow_slits();
        castle_stone_mortar_tray();
        castle_sword_relief_tray();
    }
}


// =====================================================
//   Upper (top clamshell half)
// =====================================================
module pi_case_upper() {
    difference() {
        union() {
            pi_case_upper_walls();
            pi_case_gate_posts(tray = false);
            pi_case_corner_towers(tray = false);
            pi_case_upper_lid_plate();
            // castle_fan_arch_upper();  // dropped: 43 mm ring centred at
                                         // z=51.5 dips 3 mm below the seam,
                                         // forcing supports under the upper
                                         // print. Aperture + screw holes
                                         // remain in pi_case_fan_cutout().
            castle_seam_course(upper = true);
            // castle_gate_arch();  // dropped: pointed-arch crown is a
                                    // PETG overhang, lid plate is the
                                    // real top chord across the open
                                    // gatehouse end. Module left parked.
            castle_lid_crenellations();
            castle_lid_shield();
        }
        pi_case_fan_cutout();
        pi_case_cable_slots_upper();
        pi_case_clamshell_holes(tray = false);
        castle_tower_arrow_slits();
        castle_stone_mortar_upper();
        castle_portcullis_vents();
        castle_sword_relief_upper();
        castle_arrow_slit_vents();
        pi_case_shiplap_slot_clearance();
    }
}


// =====================================================
//   Tray solid geometry
// =====================================================
module pi_case_base_plate() {
    union() {
        // main floor
        translate([FLANGE_W, 0, 0])
            cube([OUTER_W, OUTER_D, FLOOR]);
        // M4 mounting flanges — only along left/right exteriors, not
        // under the corner towers (which already sit at Z=0 and fuse
        // cleanly with the flange top).
        for (side = [0, 1])
            translate([side == 0 ? 0 : FLANGE_W + OUTER_W, 0, 0])
                cube([FLANGE_W, OUTER_D, FLANGE_THICK]);
    }
}

module pi_case_tray_walls() {
    // Front + back + left walls, from Z=FLOOR up to SPLIT_Z, plus a
    // shiplap outer-slice projection continuing LIP_DROP above SPLIT_Z.
    // Projection is trimmed to clear corner tower footprints so the
    // upper's tower cylinders seat flush at Z=SPLIT_Z.
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
            // Front wall outer slice (Y=0 .. LIP_SLICE)
            translate([FLANGE_W, 0, TRAY_TOP_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            // Back wall outer slice (Y=OUTER_D - LIP_SLICE .. OUTER_D)
            translate([FLANGE_W, OUTER_D - LIP_SLICE, TRAY_TOP_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            // Left wall outer slice (X=FLANGE_W .. FLANGE_W + LIP_SLICE)
            translate([FLANGE_W, 0, TRAY_TOP_Z])
                cube([LIP_SLICE, OUTER_D, LIP_DROP]);
        }
        // Clear corner tower footprints (upper half's towers land here)
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
            translate([cx, cy, TRAY_TOP_Z - 0.05])
                cylinder(d = TOWER_OD + 0.4, h = LIP_DROP + 0.1);
    }
}

module pi_case_upper_walls() {
    // Shiplap counterpart to the tray: full-thickness walls above
    // SPLIT_Z + LIP_DROP, inner-slice skirt from SPLIT_Z down through
    // the overlap zone. Skirt is trimmed to clear tower footprints.
    wall_h_full = UPPER_TOP_Z - (SPLIT_Z + LIP_DROP);
    skirt_off   = OUTER_WALL - LIP_SLICE;   // inner-slice offset from outer face

    // Full-thickness walls above the shiplap overlap
    translate([FLANGE_W, 0, SPLIT_Z + LIP_DROP])
        cube([OUTER_W, OUTER_WALL, wall_h_full]);
    translate([FLANGE_W, OUTER_D - OUTER_WALL, SPLIT_Z + LIP_DROP])
        cube([OUTER_W, OUTER_WALL, wall_h_full]);
    translate([FLANGE_W, 0, SPLIT_Z + LIP_DROP])
        cube([OUTER_WALL, OUTER_D, wall_h_full]);

    // Shiplap inner-slice skirt, SPLIT_Z .. SPLIT_Z + LIP_DROP
    difference() {
        union() {
            // Front inner slice (Y = skirt_off .. OUTER_WALL)
            translate([FLANGE_W, skirt_off, SPLIT_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            // Back inner slice (Y = OUTER_D - OUTER_WALL .. OUTER_D - OUTER_WALL + LIP_SLICE)
            translate([FLANGE_W, OUTER_D - OUTER_WALL, SPLIT_Z])
                cube([OUTER_W, LIP_SLICE, LIP_DROP]);
            // Left inner slice (X = FLANGE_W + skirt_off .. FLANGE_W + OUTER_WALL)
            translate([FLANGE_W + skirt_off, 0, SPLIT_Z])
                cube([LIP_SLICE, OUTER_D, LIP_DROP]);
        }
        // Clear corner tower footprints
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
            translate([cx, cy, SPLIT_Z - 0.05])
                cylinder(d = TOWER_OD + 0.4, h = LIP_DROP + 0.1);
    }
}

module pi_case_shiplap_slot_clearance() {
    // Hollow out the outer-slice slot across the upper's shiplap zone so
    // the tray's outer slice has clean space to seat. Without this,
    // three separate features collide with the tray's projecting slice
    // and stop the lid closing:
    //   - left-wall inner skirt extends Y in [0, OUTER_D] across the
    //     front-left and back-left corner inner cubes, where the tray's
    //     front/back outer slices already sit
    //   - right gate posts run full thickness through the shiplap zone,
    //     blocking the tray's outer slice at Y in [0, LIP_SLICE] /
    //     Y in [OD-LIP_SLICE, OD]
    //   - the seam course on the upper covers the full wall cross-
    //     section plus a SEAM_STEP_PROJ outward bump, filling the slot
    //     and (for the bump) leaving a free-standing tab in print
    //
    // Slot footprint = tray's outer-slice footprint (front/back/left
    // strips), expanded outward by SEAM_STEP_PROJ to also strip the
    // seam-course outward bump in this zone. Corner tower bodies are
    // preserved so they stay solid through the seam.
    eps = 0.05;
    slot_h = LIP_DROP + 2 * eps;
    difference() {
        union() {
            // Front strip — extends past +X to clip the front-right
            // gate-post seam-course bump
            translate([FLANGE_W - eps,
                       -SEAM_STEP_PROJ,
                       SPLIT_Z - eps])
                cube([OUTER_W + SEAM_STEP_PROJ + 2 * eps,
                      SEAM_STEP_PROJ + LIP_SLICE,
                      slot_h]);
            // Back strip — same trick at the back-right
            translate([FLANGE_W - eps,
                       OUTER_D - LIP_SLICE,
                       SPLIT_Z - eps])
                cube([OUTER_W + SEAM_STEP_PROJ + 2 * eps,
                      SEAM_STEP_PROJ + LIP_SLICE,
                      slot_h]);
            // Left strip
            translate([FLANGE_W - SEAM_STEP_PROJ,
                       -eps,
                       SPLIT_Z - eps])
                cube([SEAM_STEP_PROJ + LIP_SLICE,
                      OUTER_D + 2 * eps,
                      slot_h]);
        }
        // Preserve corner towers — they stay solid through the seam.
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
            translate([cx, cy, SPLIT_Z - 0.1])
                cylinder(d = TOWER_OD, h = LIP_DROP + 0.2);
    }
}

module pi_case_upper_lid_plate() {
    // Lid top plate — spans the full case footprint.
    translate([FLANGE_W, 0, UPPER_TOP_Z])
        cube([OUTER_W, OUTER_D, LID_THICK]);
}

module pi_case_gate_posts(tray = true) {
    // Short wall stubs at the front-right and back-right corners that
    // frame the open gatehouse. Run full height of their half so they
    // carry the corner towers + clamshell posts on the open side.
    z0 = tray ? 0 : SPLIT_Z;
    z1 = tray ? TRAY_TOP_Z : UPPER_TOP_Z;

    // Front-right stub: extends +X from the front-right inner corner
    translate([FLANGE_W + OUTER_W - OUTER_WALL, 0, z0])
        cube([OUTER_WALL, GATE_POST_L, z1 - z0]);

    // Back-right stub
    translate([FLANGE_W + OUTER_W - OUTER_WALL,
               OUTER_D - GATE_POST_L, z0])
        cube([OUTER_WALL, GATE_POST_L, z1 - z0]);
}

module pi_case_standoff_bosses() {
    // Bosses around the M2.5 heat-set insert pockets in the floor.
    // Full 4-position grid (all four Pi mount holes). The display-side
    // pair (sx=0) is now clear: clamshell bolts were relocated from
    // interior posts at (POST_X_L, ...) into the corner towers, so the
    // (18.5, 6.5) and (18.5, 55.5) Pi mounts are no longer blocked.
    // Boss fuses cosmetically with the nearest corner tower (centre-
    // to-centre 9.19 mm vs boss-r 3.5 + tower-r 6.0 = 9.5) — the 0.31
    // mm overlap is welcome extra material around the Pi mount.
    for (sx = [0, 1], sy = [0, 1]) {
        x = PI_X0 + PI5_INSET + sx * PI5_HOLE_W;
        y = PI_Y0 + PI5_INSET + sy * PI5_HOLE_D_SPACING;
        translate([x, y, FLOOR])
            cylinder(d = STANDOFF_BOSS_OD, h = BOSS_H_M25);
    }
}

// =====================================================
//   Tray / upper cutouts (functional)
// =====================================================
module pi_case_standoff_insert_holes() {
    // Heat-set insert pockets for M2.5 brass standoffs — full 4-
    // position grid to match the Pi mount pattern.
    // Pocket anchored to boss top so the 5 mm insert seats blind above
    // the floor underside (FLOOR 2.5 + BOSS_H_M25 3.0 = 5.5 mm ≥ 5.0).
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
    // Fan entirely in the upper half (FAN_CZ = 51, aperture 37 ⇒
    // Z 32.5 .. 69.5, within [SPLIT_Z, UPPER_TOP_Z]).
    translate([FLANGE_W - 0.1, FAN_CY, FAN_CZ])
        rotate([0, 90, 0]) {
            cylinder(d = FAN_APERTURE, h = OUTER_WALL + 0.2);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx * FAN_MOUNT_SPG / 2,
                           sy * FAN_MOUNT_SPG / 2, 0])
                    cylinder(d = FAN_SCREW_D, h = OUTER_WALL + 0.2);
        }
}

module pi_case_cable_slots_tray() {
    // HDMI0, HDMI1, USB-C are on the Pi HDMI long edge (case front,
    // Y=0). All three sit at Pi PCB + 3.5 mm ⇒ below SPLIT_Z, so
    // they live in the tray half of the front wall.
    hdmi_z = PI_Z0 + HDMI_PORT_H;
    for (offset = [HDMI1_OFFSET, HDMI2_OFFSET]) {
        x = RIGHT_EDGE_X - offset - HDMI_SLOT[0] / 2;
        translate([x, -0.1, hdmi_z])
            cube([HDMI_SLOT[0], OUTER_WALL + 0.2, HDMI_SLOT[1]]);
    }

    pwr_x = RIGHT_EDGE_X - PWR_OFFSET - PWR_SLOT[0] / 2;
    pwr_z = PI_Z0 + PWR_PORT_H;
    translate([pwr_x, -0.1, pwr_z])
        cube([PWR_SLOT[0], OUTER_WALL + 0.2, PWR_SLOT[1]]);

    // Qwiic + 1-Wire: back wall, low (Z ≈ FLOOR + 2) — tray half.
    // (1-Wire is being migrated to a back-wall GX12 in the upper half,
    // but the legacy slot stays for cable pass-through during transition.)
    translate([FLANGE_W + OUTER_W / 2 - 15 - QWIIC_SLOT[0] / 2,
               OUTER_D - 0.1,
               FLOOR + 2])
        cube([QWIIC_SLOT[0], OUTER_WALL + 0.2, QWIIC_SLOT[1]]);

    translate([FLANGE_W + OUTER_W / 2 - 25 - ONEWIRE_SLOT[0] / 2,
               OUTER_D - 0.1,
               FLOOR + 2])
        cube([ONEWIRE_SLOT[0], OUTER_WALL + 0.2, ONEWIRE_SLOT[1]]);

    // SMA bulkhead (GPS antenna) — back wall, centre-X, Z clearing
    // the NVMe HAT top. Dropped from upper-third to keep the pair of
    // GX12 ports symmetric either side of the portcullis. Coax loops
    // back up to the GPS HAT internally (~25 mm bend, fine for RG178).
    translate([FLANGE_W + OUTER_W / 2,
               OUTER_D + 0.1,
               FLOOR + 8])
        rotate([90, 0, 0])
            cylinder(d = SMA_HOLE_D,
                     h = OUTER_WALL + 0.2,
                     $fn = 32);

    // microSD extraction slot — left wall, at Pi PCB level.
    sd_y = PI_Y0 + PI5_D / 2 - SD_SLOT[0] / 2;
    sd_z = PI_Z0 - SD_SLOT[1] / 2;
    translate([FLANGE_W - 0.1, sd_y, sd_z])
        cube([OUTER_WALL + 0.2, SD_SLOT[0], SD_SLOT[1]]);
}

module pi_case_cable_slots_upper() {
    // Two GX12 panel connectors on the back wall, upper-third Z,
    // flanking the portcullis vent symmetrically (reads as arrow
    // slits either side of the arch). Left port is the arcade
    // BUTTON (GPIO 17); right port is the 1-WIRE sensor bus.
    // Rotation trick: sit at Y = OUTER_D + small-overlap, extrude
    // back through the wall via rotate([90,0,0]).
    gx12_z = FLOOR + INNER_H * 0.75;

    for (x_off = [-15, 15])
        translate([FLANGE_W + OUTER_W / 2 + x_off,
                   OUTER_D + 0.1,
                   gx12_z])
            rotate([90, 0, 0])
                cylinder(d = GX12_D,
                         h = OUTER_WALL + 0.2,
                         $fn = 48);
}

module pi_case_flange_holes() {
    for (x = [FLANGE_MARGIN, TOTAL_W - FLANGE_MARGIN],
         y = [FLANGE_MARGIN, OUTER_D - FLANGE_MARGIN])
        translate([x, y, -0.1]) {
            cylinder(d = BOLT_D, h = FLANGE_THICK + 0.2);
            translate([0, 0, -0.1])
                cylinder(d = BOLT_HEAD_D, h = BOLT_HEAD_H + 0.1);
        }
}

module pi_case_clamshell_holes(tray = true) {
    // Magnet pockets at the four CORNER TOWER CENTRES, opening toward
    // the seam. Press-fit (5.1 mm pocket vs 5.0 mm magnet, 0.05 mm
    // radial slip). No glue channel on first try — slicer cold seat
    // should hold; revisit if any pocket spits its magnet.
    //
    // ASSEMBLY: install all four tray magnets with the SAME pole up,
    // and all four lid magnets with the OPPOSITE pole down, before
    // first mating. Get this wrong and the lid will jump off the tray.
    //   tray side: pocket top at TRAY_TOP_Z, depth MAGNET_POCKET_H downward
    //   upper side: pocket bottom at SPLIT_Z, depth MAGNET_POCKET_H upward
    if (tray) {
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
//   Corner buttress towers
// =====================================================
// Cylindrical towers at the four exterior case corners. Full height
// in their respective half; capped with a corbel table step and a
// ring of crenellated merlons on the upper half. Arrow slits carved
// through the tower face on whichever side points outward.
module pi_case_corner_towers(tray = true) {
    z0 = tray ? 0 : SPLIT_Z;
    z1 = tray ? TRAY_TOP_Z : UPPER_TOP_Z;
    h  = z1 - z0;

    for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B])
        translate([cx, cy, z0])
            cylinder(d = TOWER_OD, h = h);

    // Corbel table + battlements only on the upper half tops
    if (!tray) {
        for (cx = [TOWER_X_L, TOWER_X_R], cy = [TOWER_Y_F, TOWER_Y_B]) {
            translate([cx, cy, UPPER_TOP_Z]) {
                // Corbel table (stepped band, no overhang — it is a
                // thicker ring directly above the tower; battlements
                // grow from the top of this ring).
                cylinder(d = TOWER_OD + 2 * TOWER_CORBEL_PROJ,
                         h = TOWER_CORBEL_H);
                // Ring of merlons
                translate([0, 0, TOWER_CORBEL_H])
                    _tower_battlements();
            }
        }
    }
}

module _tower_battlements() {
    r_out = TOWER_OD / 2 + TOWER_CORBEL_PROJ;
    r_in  = r_out - TOWER_MERLON_W;
    for (i = [0 : TOWER_MERLON_N - 1]) {
        a = i * (360 / TOWER_MERLON_N);
        rotate([0, 0, a])
            translate([r_in, -TOWER_MERLON_W / 2, 0])
                cube([TOWER_MERLON_W,
                      TOWER_MERLON_W,
                      TOWER_MERLON_H]);
    }
}

module castle_tower_arrow_slits() {
    // Tall narrow slits on the outward face of each tower. Each
    // tower has TOWER_SLIT_COUNT slits stacked vertically, centred
    // on the case-height midpoint of its clamshell half.
    // The outward face direction per corner:
    //   front-left  (-X, -Y)
    //   front-right (+X, -Y)
    //   back-left   (-X, +Y)
    //   back-right  (+X, +Y)
    // We cut through both halves in one pass — the cutter is placed
    // at the tower centre and radiates outward on both tray + upper.
    for (corner = [[TOWER_X_L, TOWER_Y_F, 225],
                   [TOWER_X_R, TOWER_Y_F, 315],
                   [TOWER_X_L, TOWER_Y_B, 135],
                   [TOWER_X_R, TOWER_Y_B,  45]])
    {
        cx = corner[0];
        cy = corner[1];
        face_angle = corner[2];

        // Stack of slits along the tower height
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
    // Simple cross-shaped slit
    cw = w * 3.0;
    ch = w;
    translate([-w / 2, -h / 2]) square([w, h]);
    translate([-cw / 2, -ch / 2]) square([cw, ch]);
}


// =====================================================
//   Seam course (stepped battered band along the clamshell split)
// =====================================================
// Purely decorative — sits centred on SPLIT_Z, split between tray
// (lower half of the band) and upper (upper half). Each half has its
// own step of SEAM_STEP_PROJ outward projection; visually it reads as
// a thickened corbel table that hides the split line. Zero overhang.
module castle_seam_course(upper = false) {
    band_h = SEAM_COURSE_H / 2;
    z0 = upper ? SPLIT_Z : SPLIT_Z - band_h;
    // Only apply along the three solid walls (front / back / left)
    // and across the front-right / back-right gate post stubs.

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

    // Right gate post stubs band (just the short stubs, not across
    // the open gatehouse mouth)
    translate([FLANGE_W + OUTER_W - OUTER_WALL, 0, z0])
        cube([OUTER_WALL + SEAM_STEP_PROJ,
              GATE_POST_L, band_h]);
    translate([FLANGE_W + OUTER_W - OUTER_WALL,
               OUTER_D - GATE_POST_L, z0])
        cube([OUTER_WALL + SEAM_STEP_PROJ,
              GATE_POST_L, band_h]);
}


// =====================================================
//   Gatehouse arch — spans the open right side, upper half
// =====================================================
// Pointed (ogival) stone arch that sits across the top of the
// gatehouse opening. Structural: ties front-right tower to back-right
// tower, providing a top chord for the otherwise-open side. No bars:
// unsupported bars would print as failure overhangs in PETG.
module castle_gate_arch() {
    // Arch span (Y direction): from GATE_OPENING_Y0 to GATE_OPENING_Y1
    // Arch rise: from just above SPLIT_Z to just under the lid plate.
    // We build it as a horizontal header below the arch springline,
    // plus the arch frame above, extruded through the outer X plane.
    span_y0 = GATE_OPENING_Y0;
    span_y1 = GATE_OPENING_Y1;
    span_w  = span_y1 - span_y0;       // in Y

    header_z0 = SPLIT_Z;               // header base
    arch_z0   = header_z0 + GATE_HEADER_H;
    arch_z1   = UPPER_TOP_Z - 1;       // arch crown just under lid
    arch_h    = arch_z1 - arch_z0;

    // Horizontal stone header across the top of the opening
    translate([FLANGE_W + OUTER_W - OUTER_WALL,
               span_y0,
               header_z0])
        cube([OUTER_WALL + GATE_FRAME_T,
              span_w,
              GATE_HEADER_H]);

    // Pointed arch frame above
    translate([FLANGE_W + OUTER_W - OUTER_WALL,
               span_y0,
               arch_z0])
        rotate([0, -90, 0])
            rotate([0, 0, 90])
                linear_extrude(height = OUTER_WALL + GATE_FRAME_T)
                    _gate_arch_frame_2d(span_w, arch_h);
}

module _gate_arch_frame_2d(w, h) {
    // 2D: pointed arch outline at (0,0)..(w, h), frame thickness
    // GATE_FRAME_T inset inward from outer rectangle.
    difference() {
        _pointed_arch_2d(w, h);
        translate([GATE_FRAME_T, 0])
            _pointed_arch_2d(w - 2 * GATE_FRAME_T,
                             h - GATE_FRAME_T);
    }
}

module _pointed_arch_2d(w, h) {
    // Rectangular base + two-arc gothic ogive cap, origin at BL
    spring_h = h * 0.45;
    arch_r   = w;       // equilateral ogive
    square([w, spring_h]);
    translate([0, spring_h])
        intersection() {
            circle(r = arch_r, $fn = 48);
            translate([w, 0]) circle(r = arch_r, $fn = 48);
            square([w, h - spring_h]);
        }
}


// =====================================================
//   Running-bond mortar grooves
// =====================================================
// Reused across tray and upper halves. Each face has its own Z range.
module _mortar_face_y(w, h) {
    // Grooves projected in +Y (applied to front wall; mirror for back)
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
    // Grooves projected in +X (applied to left wall)
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

module castle_stone_mortar_tray() {
    h = TRAY_TOP_Z - FLOOR;
    // Front wall
    translate([FLANGE_W, -0.01, FLOOR])
        _mortar_face_y(OUTER_W, h);
    // Back wall (mirror grooves inward in -Y)
    translate([FLANGE_W + OUTER_W, OUTER_D + 0.01, FLOOR])
        mirror([1, 0, 0])
            mirror([0, 1, 0])
                _mortar_face_y(OUTER_W, h);
    // Left wall
    translate([FLANGE_W - 0.01, 0, FLOOR])
        _mortar_face_x(OUTER_D, h);
}

module castle_stone_mortar_upper() {
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
//   Back-wall portcullis vent (decorative, upper half only)
// =====================================================
module castle_portcullis_vents() {
    // Pointed gothic arch cut into back wall, flanked by sword reliefs.
    // Centre at X = case centre, Z = upper-half midline.
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
        // vertical bars
        bar_spacing = w / (PORT_BAR_N + 1);
        for (i = [1 : PORT_BAR_N])
            translate([i * bar_spacing - PORT_BAR_W / 2, 0])
                square([PORT_BAR_W, h]);
        // horizontal crossbar
        translate([0, h * 0.4 - PORT_BAR_W / 2])
            square([w, PORT_BAR_W]);
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

module castle_sword_relief_tray() {
    // Crossed swords on front wall, low in the tray half.
    // fcz set so the full sword cross (blade top at fcz + ~19 mm) stays
    // under TRAY_TOP_Z — otherwise the relief is clipped at the seam.
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

module castle_sword_relief_upper() {
    // Two standing swords on back wall of upper half, flanking the
    // portcullis vent. Blade pointing up.
    guard_cy = SWORD_GRIP_L + SWORD_GUARD_H / 2;
    bcz = SPLIT_Z + (UPPER_TOP_Z - SPLIT_Z) * 0.3;

    for (x_off = [14, OUTER_W - 14])
        translate([FLANGE_W + x_off, OUTER_D + 0.01, bcz])
            multmatrix([[1, 0, 0, 0],
                        [0, 0, -1, 0],
                        [0, 1, 0, 0]])
                linear_extrude(SWORD_RELIEF + 0.02)
                    translate([0, -guard_cy])
                        castle_sword_2d();
}


// =====================================================
//   Fan intake arch (ring around fan on left wall)
// =====================================================
module castle_fan_arch_tray() {
    // Fan is entirely in the upper half, so the tray does not carry
    // any arch geometry. Empty module kept for symmetry with upper.
}

module castle_fan_arch_upper() {
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
//   Lid decoration (top of upper half)
// =====================================================
module castle_lid_crenellations() {
    period = MERLON_W + CRENEL_W;
    lid_z  = UPPER_TOP_Z + LID_THICK;

    // front edge (Y=0, along X) — skip corner tower footprint
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        x = FLANGE_W + i * period;
        // keep merlons away from where corner towers cap the corners
        if (x > TOWER_X_L + TOWER_OD / 2 - 1
            && x + MERLON_W < TOWER_X_R - TOWER_OD / 2 + 1)
            translate([x, 0, lid_z])
                cube([MERLON_W, OUTER_WALL, MERLON_H]);
    }
    // back edge
    for (i = [0 : floor((OUTER_W - MERLON_W) / period)]) {
        x = FLANGE_W + i * period;
        if (x > TOWER_X_L + TOWER_OD / 2 - 1
            && x + MERLON_W < TOWER_X_R - TOWER_OD / 2 + 1)
            translate([x, OUTER_D - OUTER_WALL, lid_z])
                cube([MERLON_W, OUTER_WALL, MERLON_H]);
    }
    // left edge (skip corners)
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        y = OUTER_WALL + i * period;
        if (y > TOWER_OD / 2 - 1
            && y + MERLON_W < OUTER_D - TOWER_OD / 2 + 1)
            translate([FLANGE_W, y, lid_z])
                cube([OUTER_WALL, MERLON_W, MERLON_H]);
    }
    // right edge — but only across the two gate post stubs; the
    // open gatehouse mouth is crowned by castle_gate_arch, not
    // by crenellations.
    for (i = [0 : floor((OUTER_D - 2 * OUTER_WALL - MERLON_W) / period)]) {
        y = OUTER_WALL + i * period;
        if (y + MERLON_W < GATE_POST_L + OUTER_WALL
            || y > OUTER_D - GATE_POST_L - OUTER_WALL)
            translate([FLANGE_W + OUTER_W - OUTER_WALL, y, lid_z])
                cube([OUTER_WALL, MERLON_W, MERLON_H]);
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

module castle_lid_shield() {
    cx = FLANGE_W + OUTER_W / 2;
    cy = OUTER_D / 2;
    z0 = UPPER_TOP_Z + LID_THICK;

    translate([cx, cy - SHIELD_H / 2, z0]) {
        // border
        linear_extrude(SHIELD_RAISE)
            difference() {
                castle_shield_2d(SHIELD_W, SHIELD_H);
                offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
            }
        // field (half-height recessed inside the border)
        linear_extrude(SHIELD_RAISE * 0.5)
            offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
        // chevron device
        linear_extrude(SHIELD_RAISE)
            intersection() {
                offset(-2) castle_shield_2d(SHIELD_W, SHIELD_H);
                castle_chevron_2d(SHIELD_W * 0.5, SHIELD_H * 0.15);
            }
    }
}

module castle_arrow_slit_vents() {
    // Cross-shaped ventilation slits cut through the lid plate,
    // flanking the shield.
    cx = FLANGE_W + OUTER_W / 2;
    slit_w = 1.5;
    slit_h = 10;
    cross_w = 5;
    cross_h = 1.5;
    spacing_y = 7;

    for (side = [-1, 1]) {
        x = cx + side * (SHIELD_W / 2 + 8);
        for (j = [0 : 3]) {
            y = OUTER_D / 2 - 1.5 * spacing_y + j * spacing_y;
            translate([x, y, UPPER_TOP_Z - 0.1])
                linear_extrude(LID_THICK + MERLON_H + 0.2)
                    _arrow_slit_2d(slit_w, slit_h);
        }
    }
}
