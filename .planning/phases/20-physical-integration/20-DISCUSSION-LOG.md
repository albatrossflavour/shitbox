# Phase 20: Physical Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 20-physical-integration
**Areas discussed:** Pi enclosure, Screen mounting, ELP camera

---

## Pi Enclosure

### Pi location

| Option | Description | Selected |
|--------|-------------|----------|
| Under dash (passenger) | Protected from sun, close to screen HDMI run | |
| Behind dash centre | Central location, short runs to both cameras | |
| Under passenger seat | Good airflow, easy access, longer cable runs | |
| Other: Keep on plywood panel | Existing panel between seats with flux capacitor | ✓ |

**User's choice:** Keep on existing plywood electronics panel (photo provided showing current bench state)
**Notes:** Panel has flux capacitor prop, GL.iNet router, Brio cabin camera, voltmeter, battery isolator already mounted

### Enclosure approach

| Option | Description | Selected |
|--------|-------------|----------|
| 3D-printed case on panel | PETG enclosure screwed to plywood, cutouts for cables | ✓ |
| Open mount with cover | Pi stays exposed, shield/cover for dust protection | |
| You decide | Claude picks | |

**User's choice:** 3D-printed case on panel

### Panel mounting

| Option | Description | Selected |
|--------|-------------|----------|
| Bolted in | Screwed/bolted to car body permanently | ✓ |
| Removable | Strapped or slotted, can pull out for bench work | |
| Not decided yet | Still figuring out | |

**User's choice:** Bolted in

### CAD tool

| Option | Description | Selected |
|--------|-------------|----------|
| OpenSCAD (match existing) | Parametric, consistent with sensor-cluster.scad | ✓ |
| Edward designs it | Edward creates in Blender/Fusion | |

**User's choice:** OpenSCAD

### Vibration isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Rubber standoffs | M2.5 rubber grommets, standard motorsport approach | ✓ |
| Sorbothane pads | Viscoelastic pads, overkill for a shitbox | |
| Don't bother | Screw straight down, cable strain relief matters more | |

**User's choice:** Rubber standoffs

### Fan size

| Option | Description | Selected |
|--------|-------------|----------|
| 30mm (Noctua NF-A4) | Compact, enough for Pi 5, 5V off GPIO | ✓ |
| 40mm | More airflow, slightly larger case | |
| Whatever fits | Parametric, Claude sizes it | |

**User's choice:** 30mm Noctua NF-A4

### Connector cutouts

| Option | Description | Selected |
|--------|-------------|----------|
| One GX12 | Single panel mount for external sensor loom | ✓ |
| Two or more | Multiple GX12 for separate cable runs | |
| Not sure yet | Still figuring out | |

**User's choice:** One GX12, plus grommeted holes for remaining cables (GPS SMA, 1-Wire, I2C, HDMI, USB, power)
**Notes:** Photo provided showing current cable state — GX12 connector, SMA GPS antenna, loose 1-Wire and I2C wires

### Cable exits

| Option | Description | Selected |
|--------|-------------|----------|
| Individual holes | Sized rubber grommets per cable | |
| One large exit slot | Single open slot, all cables exit together | |
| You decide | Claude picks based on printability | ✓ |

**User's choice:** You decide

---

## Screen Mounting

### Screen availability

| Option | Description | Selected |
|--------|-------------|----------|
| Got it | Screen in hand, can measure and test fit | ✓ |
| Still waiting | Design from datasheet dimensions | |

**User's choice:** Got it — screen has arrived

### Dash position

| Option | Description | Selected |
|--------|-------------|----------|
| Centre dash (above stereo) | Both driver and passenger can see | |
| Driver side (left of wheel) | In driver's peripheral vision | |
| Top of dash (near windscreen) | High mount, sun glare risk | |
| Other: Passenger side | Left side of vehicle (RHD car) | ✓ |

**User's choice:** Passenger side (left-hand side of vehicle)
**Notes:** Co-driver/navigator can interact with touch, driver sees with quick glance left

### Mount type

| Option | Description | Selected |
|--------|-------------|----------|
| RAM Mount + VESA | Off-the-shelf, adjustable but articulating joint may loosen | |
| 3D-printed bracket | Custom PETG bolted to dash, no joints, more rigid | ✓ |
| Not decided yet | Waiting for screen to assess | |

**User's choice:** 3D-printed bracket

### Bezel design

| Option | Description | Selected |
|--------|-------------|----------|
| Integrated bezel + VESA | Single piece: edge protection + VESA 75mm holes | ✓ |
| Separate bezel and plate | Two pieces, easier to reprint individually | |
| You decide | Claude picks | |

**User's choice:** Integrated bezel + VESA

### Bracket angle

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed angle | Set once during install, no joints to loosen | |
| Adjustable tilt | Hinge or slot mechanism | |
| You decide | Claude picks | ✓ |

**User's choice:** You decide

### Touch input

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, touch active | Co-driver uses for notes, fuel, driver switching | ✓ |
| Display only | Dashboard kiosk, input via keyboard/button | |
| Both | Primarily display, touch as backup | |

**User's choice:** Yes, touch active

---

## ELP Camera

### Camera position

| Option | Description | Selected |
|--------|-------------|----------|
| Windscreen (suction/adhesive) | Classic dashcam position | |
| Top of plywood panel | Next to Brio on panel | |
| Custom bracket on dash | 3D-printed mount bolted to dash/A-pillar | ✓ |

**User's choice:** Custom bracket on dash

### Camera housing

| Option | Description | Selected |
|--------|-------------|----------|
| Enclosure | Full housing with lens window | |
| Bracket only | Simple cradle for bare camera module | ✓ |
| You decide | Claude picks | |

**User's choice:** Bracket only

---

## Claude's Discretion

- Cable exit approach for Pi case (individual grommeted holes vs single exit slot)
- Screen bracket angle (fixed, optimised for touch interaction)

## Deferred Ideas

- Cable loom design (routing, protection, connector choices) — not discussed, could be separate scope
- Power distribution (12V fused circuit, buck converter, ignition-linked shutdown) — not discussed
