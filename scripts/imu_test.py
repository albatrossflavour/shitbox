#!/usr/bin/env python3
"""Interactive IMU alignment test tool.

Use this to determine the axis orientation of your MPU6050.
Hold the board flat, then tilt different edges to see which axis responds.

Expected when flat and level:
  ax ~= 0g (forward/back)
  ay ~= 0g (left/right)
  az ~= 1g (up/down - gravity)
"""

import argparse
import sys
import time

from shitbox.events.ring_buffer import RingBuffer
from shitbox.events.sampler import HighRateSampler


def main():
    parser = argparse.ArgumentParser(description="Test IMU alignment")
    parser.add_argument(
        "--rate", "-r",
        type=float,
        default=10.0,
        help="Display update rate in Hz (default: 10)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw values without labels",
    )
    args = parser.parse_args()

    rb = RingBuffer(1, 100)
    sampler = HighRateSampler(rb)

    try:
        sampler.setup()
    except Exception as e:
        print(f"Failed to initialise IMU: {e}", file=sys.stderr)
        sys.exit(1)

    interval = 1.0 / args.rate

    print("IMU Alignment Test - Ctrl+C to stop")
    print()
    print("Hold flat and level: az should read ~1.0g")
    print("Tilt front down: positive axis = forward (X)")
    print("Tilt left down: positive axis = left (Y)")
    print()

    if not args.raw:
        print("    ax (fwd)    ay (left)   az (up)     gx          gy          gz")
        print("-" * 70)

    try:
        while True:
            sample = sampler.read_once()

            if args.raw:
                print(
                    f"{sample.ax:.4f},{sample.ay:.4f},{sample.az:.4f},"
                    f"{sample.gx:.2f},{sample.gy:.2f},{sample.gz:.2f}"
                )
            else:
                print(
                    f"\r  {sample.ax:+.3f}g     {sample.ay:+.3f}g     {sample.az:+.3f}g   "
                    f"  {sample.gx:+7.1f}      {sample.gy:+7.1f}      {sample.gz:+7.1f}   ",
                    end="",
                    flush=True,
                )

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nStopped.")


if __name__ == "__main__":
    main()
