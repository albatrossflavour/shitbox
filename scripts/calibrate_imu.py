#!/usr/bin/env python3
"""IMU accelerometer calibration tool.

Park the car on flat, level ground. Run this script with the engine off and
the car stationary. It will sample for a few seconds and compute the bias
offsets needed to zero ax/ay and correct the az gravity baseline.

Usage:
    python scripts/calibrate_imu.py

Output is a YAML snippet to paste into config/config.yaml under
sensors.imu.
"""

import math
import sys
import time

from shitbox.events.ring_buffer import RingBuffer
from shitbox.events.sampler import HighRateSampler

SAMPLE_COUNT = 300   # 3 seconds at ~100 Hz
SAMPLE_RATE = 100.0


def main() -> None:
    print("IMU Calibration")
    print("=" * 50)
    print()
    print("Park on flat, level ground.")
    print("Engine off. Car stationary.")
    print()
    input("Press Enter when ready...")
    print()

    rb = RingBuffer(max_seconds=10, sample_rate_hz=SAMPLE_RATE)
    sampler = HighRateSampler(rb, sample_rate_hz=SAMPLE_RATE)

    try:
        sampler.setup()
    except Exception as e:
        print(f"Failed to initialise IMU: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Collecting {SAMPLE_COUNT} samples (~{SAMPLE_COUNT / SAMPLE_RATE:.0f}s)...")

    samples_ax = []
    samples_ay = []
    samples_az = []
    interval = 1.0 / SAMPLE_RATE

    for i in range(SAMPLE_COUNT):
        try:
            s = sampler.read_once()
            samples_ax.append(s.ax)
            samples_ay.append(s.ay)
            samples_az.append(s.az)
        except Exception as e:
            print(f"Read error at sample {i}: {e}", file=sys.stderr)
        time.sleep(interval)

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{SAMPLE_COUNT}")

    if len(samples_ax) < 50:
        print("Not enough samples collected — aborting.", file=sys.stderr)
        sys.exit(1)

    mean_ax = sum(samples_ax) / len(samples_ax)
    mean_ay = sum(samples_ay) / len(samples_ay)
    mean_az = sum(samples_az) / len(samples_az)

    # stddev for sanity check — if the car was moving, values will be noisy
    def stddev(vals: list, mean: float) -> float:
        return math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))

    std_ax = stddev(samples_ax, mean_ax)
    std_ay = stddev(samples_ay, mean_ay)
    std_az = stddev(samples_az, mean_az)

    # ax and ay should be 0 when stationary on flat ground
    offset_x = -mean_ax
    offset_y = -mean_ay

    # az should be ±1g (gravity). Auto-detect orientation.
    expected_az = 1.0 if mean_az > 0 else -1.0
    offset_z = expected_az - mean_az

    print()
    print("Results")
    print("-" * 50)
    print(f"  ax  mean={mean_ax:+.4f}g  stddev={std_ax:.4f}g")
    print(f"  ay  mean={mean_ay:+.4f}g  stddev={std_ay:.4f}g")
    print(f"  az  mean={mean_az:+.4f}g  stddev={std_az:.4f}g  (gravity axis: {expected_az:+.0f}g)")
    print()

    if std_ax > 0.05 or std_ay > 0.05 or std_az > 0.1:
        print("WARNING: High noise — was the car moving? Re-run with car stationary.")
        print()

    print("Calibration offsets (add these to config/config.yaml under sensors.imu):")
    print()
    print("    accel_offset_x: {:+.4f}".format(offset_x))
    print("    accel_offset_y: {:+.4f}".format(offset_y))
    print("    accel_offset_z: {:+.4f}".format(offset_z))
    print()
    print("After adding offsets, verify with: python scripts/imu_test.py")
    print("  ax/ay should read near 0g, az near ±1g when stationary.")


if __name__ == "__main__":
    main()
