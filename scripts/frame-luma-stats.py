#!/usr/bin/env python3
"""Measure front-camera exposure from captured frames.

Answers one question fast: is the *road* exposed, or is the auto-exposure
metering the bright sky and crushing the drivable surface into black? Point it
at a batch of timelapse/event JPEGs and it reports per-region luma plus a
per-frame verdict, so a camera change (e.g. backlight_compensation) can be
judged on numbers instead of vibes.

The metric that matters is the ROAD SURFACE, not the whole lower frame. The
bonnet is a fixed near-black lump at the bottom of every frame and the verge is
often deep shade; including them just makes every frame look "crushed". We
measure the drivable tarmac box in the lower centre instead.

Crushed vs balanced-dark. A dark road is only a *fault* when the sky is
simultaneously bright — that's the meter protecting the highlights at the
road's expense. A genuinely shaded scene (tree tunnel) has a dark road AND a
tame sky, and is a correct exposure. So the fault flag needs both conditions,
learned from the 2026-07-09 shakedown:
    CRUSHED  = road mean < 40  AND  sky bright (>=6% of sky pixels near-white)
    balanced = anything else (including faithfully-dark shade shots)

Reference frames (2026-07-09, all judged good by eye):
    timelapse_00119  open-ish, well lit   road ~well above 40
    timelapse_00145  tree tunnel, dim     road ~55, sky 109  -> balanced dark
The same drive averaged a crushed road under bright open sky. Success after a
camera fix = open-sky frames stop tripping CRUSHED and their road luma climbs,
while shade frames like 00145 stay untouched.

Usage:
    scripts/frame-luma-stats.py '~/Downloads/2026-07-10/timelapse_*.jpg'
    scripts/frame-luma-stats.py '*.jpg' --ref timelapse_00119.jpg
    scripts/frame-luma-stats.py '*.jpg' --list-crushed
"""
import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

# ROIs as (y0, y1, x0, x1) fractions. Tuned to the fixed front-camera mount.
ROI = {
    "road": (0.74, 0.90, 0.40, 0.62),   # drivable tarmac, lower centre — THE metric
    "subject": (0.68, 0.76, 0.46, 0.55),  # car ahead / horizon of the lane
    "sky": (0.00, 0.35, 0.35, 0.65),      # canopy gap / open sky, centre top
}
ROAD_DARK = 40.0   # road mean below this is "dark"
SKY_BRIGHT_PCT = 6.0  # >= this %% of sky pixels near-white means the meter has a bright target


def _box(a, roi):
    h, w = a.shape
    y0, y1, x0, x1 = roi
    return a[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def _measure(path):
    a = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
    m = {k: _box(a, roi) for k, roi in ROI.items()}
    road = float(m["road"].mean())
    sky_wht = 100.0 * (m["sky"] >= 250).mean()
    crushed = road < ROAD_DARK and sky_wht >= SKY_BRIGHT_PCT
    return {
        "road": road,
        "subject": float(m["subject"].mean()),
        "sky": float(m["sky"].mean()),
        "sky_wht": sky_wht,
        "crushed": crushed,
    }


def frame_report(path):
    r = _measure(path)
    verdict = "CRUSHED (AE fooled by sky)" if r["crushed"] else "ok / balanced"
    print(f"\n{os.path.basename(path)}: {verdict}")
    print(f"  road {r['road']:5.1f}   subject {r['subject']:5.1f}   "
          f"sky {r['sky']:5.1f} (near-white {r['sky_wht']:.1f}%)")


def batch_report(paths, list_crushed=False):
    res = [(p, _measure(p)) for p in paths]
    road = np.array([r["road"] for _, r in res])
    crushed = [p for p, r in res if r["crushed"]]
    print(f"\n{len(paths)} frames")
    print(f"  road luma  mean {road.mean():5.1f}  min {road.min():5.1f}  max {road.max():5.1f}")
    print(f"  CRUSHED frames (road<{ROAD_DARK:.0f} & bright sky): {len(crushed)}/{len(res)}  "
          f"({100*len(crushed)/len(res):.0f}%)")
    print("  reference: 00145 road ~55 = balanced dark; "
          "success = fewer crushed, higher road on open-sky frames")
    if list_crushed and crushed:
        print("\n  crushed frames:")
        for p in crushed:
            print(f"    {os.path.basename(p)}")


def main():
    ap = argparse.ArgumentParser(description="Front-camera road-exposure luma stats.")
    ap.add_argument("pattern", nargs="?", default="timelapse_*.jpg",
                    help="glob of frames (quote it so the shell doesn't expand)")
    ap.add_argument("--ref", help="single frame to break down (the target)")
    ap.add_argument("--list-crushed", action="store_true", help="name every crushed frame")
    args = ap.parse_args()

    if args.ref:
        frame_report(os.path.expanduser(args.ref))

    paths = sorted(glob.glob(os.path.expanduser(args.pattern)))
    if not paths:
        print(f"no frames matched: {args.pattern}", file=sys.stderr)
        sys.exit(1)
    batch_report(paths, list_crushed=args.list_crushed)


if __name__ == "__main__":
    main()
