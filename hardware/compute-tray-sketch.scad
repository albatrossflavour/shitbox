// Compute tray layout sketch — hybrid L-shape design
//
// =============================================================================
// DESIGN SUMMARY
// =============================================================================
//
// Existing 2x4 cross-member (bolted to rear seat anchor points) is kept.
// Existing vertical plywood panel (between front seats, carries flux capacitor
// + power-gear panel-mount kit on cabin face) is kept.
//
// New build adds:
//   - Wood horizontal shelf (12mm plywood) bolted to front face of vertical
//     panel, sitting at top-of-2x4 height. Has a rectangular cutout where the
//     metal sensor sub-tray drops in.
//   - Two metal L-brackets (50x50x4 aluminium angle) bolted to the front face
//     of the 2x4. Vertical flange clamps to 2x4, horizontal flange extends
//     forward and carries the sensor sub-tray. Doubles as L-junction stiffener
//     for the shelf-wall corner.
//   - Metal sensor sub-tray (3mm aluminium plate) bolted to L-bracket horizontal
//     flanges. Carries the sensor PCB with IMU. CHASSIS-COUPLED via 2x4, no wood
//     in the rigid path so the IMU sees clean chassis dynamics.
//   - Two diagonal braces (25x25 aluminium angle) from top of vertical wall
//     down to front edge of shelf, hugging the lateral edges. Triangulates the
//     L-section so neither plate is a free cantilever.
//
// Removable mounting (planned, not drawn): studs + locating dowels protruding
// from top of 2x4, brackets on the wood shelf drop over them, nuts clamp.
// 2 dowels for alignment + 3-4 studs for clamping. Whole assembly lifts off
// in under a minute for service.
//
// Mounting tilt compensation (planned, not drawn): a wedge shim between the
// L-bracket vertical flange and the 2x4 face, cut to whatever angle the 2x4
// front face is off vertical. Measured at install time, not pre-fabricated.
//
// =============================================================================
// INVENTORY (full list of what mounts on the assembly)
// =============================================================================
//
// On the vertical wall, cabin face:
//   - Flux capacitor (decorative, ~360x320, top of wall)
//   - Kill switch (50mm dia knob, mid-upper)
//   - Smart VSR / battery isolator (Powertech 140A, ~70mm dia can, mid-upper)
//   - Plutonium / digital readout (~80x60, mid)
//   - Fuse block (~120x60, lower)
//   - Anderson plug (~50x50x50, bottom)
//
// On the wood shelf, in a single row across the width (network-ordered):
//   - UGREEN 12V→USB-C PD adapter (80x80x30, passenger end)
//     12V input from fuse block, USB-C PD outputs to Pi + screen + router
//   - Pi castle (130x130x60)
//     USB-C PD power, ethernet to BE3600, USB to RTL-SDR, qwiic to sensor PCB,
//     GPIO to button, USB to cameras, HDMI to co-driver screen, SMA to GPS
//   - GL.iNet GL-BE3600 (Slate 7, 144x69x32)
//     USB-C PD power, ethernet to Pi + M1, SMA WiFi antennae external
//   - Netgear Nighthawk M1 (MR1100, 105x72x20, LCD up)
//     USB-C power, ethernet to BE3600, TS-9 LTE antennae external
//
// Zip-tied to baseplate via short USB extension:
//   - RTL-SDR (TPMS reception)
//
// On the metal sensor sub-tray (chassis-coupled):
//   - Sensor PCB carrying IMU (LSM6DSOX+LIS3MDL), magnetometer, BME680,
//     VEML7700, INA226. Qwiic chain back to Pi.
//
// Off the assembly (mentioned for context):
//   - LiFePO4 batteries in passenger footwells (12V power feed runs back to
//     wall-mounted kill switch)
//   - Co-driver screen on passenger dashboard (HDMI from Pi)
//   - Front + cabin cameras (USB to Pi)
//   - GPS antenna roof-mounted (SMA to Pi)
//   - All network antennae (TS-9 + SMA) external, routed up to roof
//   - Engine bay 1-wire DS18B20 probes (GX12 to Pi)
//   - Capture button under the handbrake (GX12 to Pi)
//
// =============================================================================
// COLOUR LEGEND (what each colour represents in the rendered output)
// =============================================================================
//
// STRUCTURE:
//   tan/burlywood          existing 2x4 cross-member
//   light tan              existing vertical plywood wall
//   medium brown           new wood horizontal shelf
//   orange                 new metal L-brackets (chassis-coupled)
//   bright orange          new diagonal braces
//   silver/grey            new metal sensor sub-tray
//   faint cream            existing boot cover (drawn faintly for context)
//   dark grey, transparent floor pan reference
//
// PANEL-MOUNT KIT (on vertical wall, cabin face):
//   black rectangle        flux capacitor backing plate
//   off-white cylinders    flux capacitor Y-arm tubes
//   red knob               kill switch
//   dark grey can          VSR / smart isolator
//   yellow square          plutonium / digital readout
//   dark grey rectangle    fuse block
//   medium grey block      Anderson plug
//
// SHELF DEVICES:
//   yellow block           UGREEN 12V→USB-C PD adapter
//   dark blue              Pi castle
//   medium blue            GL.iNet GL-BE3600 (Slate 7)
//   near-black             Netgear Nighthawk M1 (LCD up)
//   dark red               RTL-SDR (zip-tied)
//
// SENSOR:
//   mid-green              sensor PCB (IMU + mag + BME680 + VEML7700 + INA226)
//   darker green           IMU chip itself (the part that needs rigid mount)
//
// =============================================================================
// COORDINATE SYSTEM
// =============================================================================
//   +X = passenger side (lateral)
//   +Y = forward (toward front of car)
//   +Z = up
//   Origin: floor pan, on the centreline of the 2x4 rear face
//
// All dimensions are rough estimates. Replace with measured values before fab.

$fn = 24;

// === measured-then-update dimensions ===
beam_x        = 1100;   // 2x4 length across the car
beam_y        = 90;     // 2x4 dressed thickness front-to-back
beam_z        = 45;     // 2x4 dressed height
beam_z_off    = 100;    // 2x4 sits this high above the rear floor pan

// Vertical panel (existing, kept)
wall_x        = 500;    // wall width across the car (between the front seats)
wall_t        = 12;     // 12 mm plywood (or could be 3 mm aluminium)
wall_z        = 600;    // wall height above the 2x4 top
                        // (flux capacitor up high, switch/isolator/Anderson lower)

// Horizontal shelf (new, bolted to front face of vertical panel)
shelf_x       = 500;    // shelf width (matches wall width)
shelf_y       = 300;    // shelf depth forward of wall front face
shelf_t       = 3;      // aluminium plate thickness
shelf_z       = beam_z_off + beam_z;  // shelf top surface level with 2x4 top

// IMU bracket pass-through in the shelf
imu_hole_x    = 80;
imu_hole_y    = 60;
imu_y         = 150;    // forward of wall front face

// Components (rough placements, real sizes)
pi_x = 130; pi_y = 130; pi_z = 60;          // Pi castle (printed case, est.)
m1_x = 105; m1_y = 72;  m1_z = 20;          // Netgear Nighthawk M1
be_x = 144; be_y = 69;  be_z = 32;          // GL.iNet GL-BE3600
ug_x = 80;  ug_y = 80;  ug_z = 30;          // UGREEN 12V→USB-C PD adapter
fuse_x = 120; fuse_y = 60; fuse_z = 30;     // Fuse block

// === floor pan reference (low transparent slab) ===
front_pan_drop = 60;
color([0.25, 0.25, 0.30, 0.4])
  translate([-beam_x/2 - 50, -beam_y - 100, -2])
    cube([beam_x + 100, beam_y + 100 + 20, 2]);

color([0.25, 0.25, 0.30, 0.4])
  translate([-shelf_x/2 - 100, 0, -front_pan_drop - 2])
    cube([shelf_x + 200, shelf_y + 200, 2]);

// === 2x4 cross-member (existing) ===
color("burlywood")
  translate([-beam_x/2, -beam_y, beam_z_off])
    cube([beam_x, beam_y, beam_z]);

// === boot cover (existing, hinged on TOP of 2x4) — drawn faintly ===
color([0.70, 0.55, 0.35, 0.10])
  translate([-beam_x/2, -beam_y - 500, beam_z_off + beam_z])
    cube([beam_x, 500, 12]);

// === vertical panel (existing) ===
// Bolts to front face of 2x4, rises from floor pan to wall top
color([0.85, 0.65, 0.40, 0.85])
  translate([-wall_x/2, 0, 0])
    cube([wall_x, wall_t, beam_z_off + beam_z + wall_z]);

// === flux capacitor (the important bit) on cabin face of wall ===
// Mounted high, facing forward (toward cabin)
color([0.10, 0.10, 0.12])
  translate([-180, wall_t, beam_z_off + beam_z + 250])
    cube([360, 8, 320]);
// three Y-shaped tubes, simplified as cylinders, sticking forward
for (a = [-30, 90, 210])
  color([0.85, 0.85, 0.90])
    translate([0, wall_t + 8, beam_z_off + beam_z + 410])
      rotate([0, 0, a])
        rotate([-90, 0, 0])
          cylinder(h = 8, r = 18);

// === panel-mount controls on cabin face of wall ===
// All Z values relative to top of 2x4 (= shelf surface = shelf_z).

// Kill switch (red knob), z+250, slightly off-centre passenger side
color([0.85, 0.15, 0.15])
  translate([-100, wall_t, shelf_z + 250])
    rotate([-90, 0, 0])
      cylinder(h = 25, r = 22);

// VSR / isolator (round can), z+250, driver side
color([0.20, 0.20, 0.22])
  translate([60, wall_t, shelf_z + 250])
    rotate([-90, 0, 0])
      cylinder(h = 30, r = 26);

// Plutonium / digital readout, z+150
color([0.95, 0.85, 0.20])
  translate([-40, wall_t, shelf_z + 150])
    cube([80, 6, 60]);

// Fuse block, z+80, driver side
color([0.30, 0.30, 0.30])
  translate([60, wall_t, shelf_z + 80])
    cube([fuse_x, 6, fuse_y]);

// Anderson plug, z+30, just above shelf surface, passenger side
color([0.40, 0.40, 0.45])
  translate([-180, wall_t, shelf_z + 30])
    cube([60, 25, 35]);

// === metal L-brackets (new) — primary structural element ===
// Aluminium angle, vertical flange bolted to 2x4 front face, horizontal flange
// extends forward to carry the sensor sub-tray. Doubles as L-junction stiffener
// for the shelf-wall corner.
lbk_h         = 50;     // horizontal flange depth
lbk_v         = 80;     // vertical flange height (tall enough to reach 2x4 face)
lbk_t         = 4;      // angle thickness
lbk_x         = 60;     // bracket width across car
lbk_inset     = 80;     // distance from centreline to inner edge of bracket
lbk_top_z     = shelf_z;  // horizontal flange top surface = shelf top level
color([0.85, 0.55, 0.20])
  for (sx = [-lbk_inset - lbk_x, lbk_inset]) {
    // horizontal flange (extends forward from 2x4 face)
    translate([sx, 0, lbk_top_z - lbk_t])
      cube([lbk_x, lbk_h, lbk_t]);
    // vertical flange (bolts to 2x4 front face, drops down into the 2x4)
    translate([sx, -lbk_t, lbk_top_z - lbk_v])
      cube([lbk_x, lbk_t, lbk_v]);
  }

// === horizontal shelf (wood) — non-load-bearing surface for kit ===
// Sits at top-of-2x4 height. Has a cutout in the centre where the sensor sub-tray lives.
sub_tray_x   = 200;   // sensor sub-tray width
sub_tray_y   = 100;   // sensor sub-tray depth
sub_tray_t   = 3;     // sensor sub-tray thickness (aluminium)
sub_tray_y0  = 8;     // sensor sub-tray rear edge offset from 2x4 face
color([0.78, 0.62, 0.35, 0.85])
  difference() {
    translate([-shelf_x/2, 0, shelf_z - shelf_t])
      cube([shelf_x, shelf_y, shelf_t]);
    // cutout for sensor sub-tray
    translate([-sub_tray_x/2 - 5, sub_tray_y0 - 5, shelf_z - shelf_t - 1])
      cube([sub_tray_x + 10, sub_tray_y + 10, shelf_t + 2]);
  }

// === sensor sub-tray (aluminium, mounted on metal L-brackets) ===
// Carries the sensor cluster including the IMU. Chassis-coupled via L-brackets → 2x4.
color([0.75, 0.75, 0.78])
  translate([-sub_tray_x/2, sub_tray_y0, shelf_z - sub_tray_t])
    cube([sub_tray_x, sub_tray_y, sub_tray_t]);

// === diagonal braces (new) — top of wall to front edge of shelf ===
// One brace each side, hugging the lateral edges, leaving the shelf middle clear.
// Triangulates the L-section so the wall stops being a free cantilever and the
// shelf stops being a free cantilever — they brace each other.
brace_top_z    = beam_z_off + beam_z + wall_z - 30;   // anchor near top of wall
brace_top_y    = wall_t;                              // on wall front face
brace_bot_z    = shelf_z - shelf_t;                   // anchor at shelf underside
brace_bot_y    = wall_t + shelf_y - 20;               // near front edge of shelf
brace_section  = 25;                                   // rough section size for sketch
color([0.95, 0.55, 0.15])
  for (sx = [-shelf_x/2 + 5, shelf_x/2 - 5 - brace_section]) {
    hull() {
      // top anchor block
      translate([sx, brace_top_y, brace_top_z])
        cube([brace_section, brace_section, brace_section]);
      // bottom anchor block
      translate([sx, brace_bot_y, brace_bot_z])
        cube([brace_section, brace_section, brace_section]);
    }
  }

// === sensor cluster (on the metal sub-tray) ===
// Sensor PCB carries IMU, magnetometer, light, BME680, INA226. Sat on sub-tray.
color([0.20, 0.55, 0.30])
  translate([-90, sub_tray_y0 + 15, shelf_z])
    cube([180, 60, 8]);
// IMU chip (the bit that actually cares about rigid mounting)
color("darkgreen")
  translate([-15, sub_tray_y0 + 35, shelf_z + 8])
    cube([30, 25, 4]);

// === components on the wood shelf ===
// Single-row layout across the width, ordered for short cable runs:
//
//   Y=300 (front edge of shelf, cabin side)
//   +--------------------------------------------+
//   |  [UG]  [Pi]    [BE3600]    [M1]            |
//   |  80    130     144         105             |
//   |  USB-C USB-C   eth+USB-C   eth+USB-C       |
//   |   ──── power ────►                         |
//   |        ◄─── eth ──►◄─── eth ──►            |
//   |                                            |
//   |   [RTL-SDR]                                |
//   |                                            |
//   |          [sensor sub-tray cutout]          |
//   +--------------------------------------------+
//   Y=0 (rear, against wall)
//   X=-250 (passenger)               X=+250 (driver)

// UGREEN 12V→USB-C PD adapter — passenger end of row
color([0.85, 0.85, 0.30, 0.85])
  translate([-240, sub_tray_y0 + sub_tray_y + 20, shelf_z])
    cube([ug_x, ug_y, ug_z]);

// Pi castle — next to UGREEN
color([0.20, 0.30, 0.75, 0.85])
  translate([-150, sub_tray_y0 + sub_tray_y + 20, shelf_z])
    cube([pi_x, pi_y, pi_z]);

// GL.iNet GL-BE3600 — middle (between Pi and M1 for ethernet flow)
color([0.30, 0.50, 0.70, 0.90])
  translate([-10, sub_tray_y0 + sub_tray_y + 20, shelf_z])
    cube([be_x, be_y, be_z]);

// Netgear Nighthawk M1 — driver end of row (LCD up)
color([0.10, 0.10, 0.10, 0.90])
  translate([144, sub_tray_y0 + sub_tray_y + 20, shelf_z])
    cube([m1_x, m1_y, m1_z]);

// RTL-SDR (zip-tied to baseplate via short USB extension)
color([0.55, 0.10, 0.10, 0.90])
  translate([-240, sub_tray_y0 + sub_tray_y + ug_y + 40, shelf_z])
    cube([90, 30, 12]);
