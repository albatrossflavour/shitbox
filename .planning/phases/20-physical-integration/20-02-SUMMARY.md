---
phase: 20-physical-integration
plan: 02
status: complete
started: 2026-04-17
completed: 2026-04-17
commits:
  - cca8efb
---

# Plan 20-02 Summary: Screen Bezel + Dash Bracket

## What was built

Two OpenSCAD files for the Waveshare 7" screen mounting system:

- `hardware/screen-bezel.scad` — slide-in bezel with retention lips and backplate
- `hardware/dash-bracket.scad` — fixed-angle dash bracket with gusset bracing

## Key design decisions

- **No VESA**: The Waveshare 7" HDMI LCD (H) has no VESA mount holes. Bezel uses a custom
  140x75mm bolt pattern through the backplate instead.
- **Slide-in**: Screen slides in from the left (connector side). Left edge stays open for
  HDMI, USB, and 3.5mm audio access. Retention lips on the other three sides.
- **Custom bolt pattern**: Both files share `BRACKET_SPREAD_W = 140` and `BRACKET_SPREAD_H = 75`
  constants. Change in one, change in both.
- **Integral gussets**: Bracket side walls are hull'd triangles from base to screen face,
  providing gusset bracing without separate gusset parts.
- **18 degree angle**: Screen tilted back from vertical for co-driver touch interaction and
  glare reduction.

## Measurements used

- Screen case: 190 x 115 x 15mm (measured 2026-04-17)
- Case bezel: 20mm sides, 15mm top/bottom (measured 2026-04-17)
- Glass area: 150 x 85mm (derived)

## Deviations

- Replaced VESA 75mm design with custom bolt pattern (screen has no VESA holes)
- Bezel is a slide-in U-channel rather than a full wrap-around (simpler, better connector access)
- `AUDIO_EXIT_D` constant defined but audio exit cutout not modelled in bezel — the open left
  side provides full connector access without a specific cutout
- Dash bracket has two side walls instead of a central riser + separate gussets — structurally
  better for vibration resistance
