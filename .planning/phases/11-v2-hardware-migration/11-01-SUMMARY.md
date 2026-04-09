---
phase: 11-v2-hardware-migration
plan: "01"
subsystem: imu
tags: [lsm6dsox, lis3mdl, complementary-filter, adafruit-circuitpython, i2c, unit-conversion]

requires:
  - phase: 11-00
    provides: wave-0 RED tests for LSM6DSOX sampler and IMUHeadingCollector

provides:
  - LSM6DSOX-backed HighRateSampler with m/s² to g and rad/s to deg/s conversion
  - ComplementaryFilter class with alpha=0.98 for pitch/roll estimation
  - IMUHeadingCollector fusing LSM6DSOX and LIS3MDL into pitch/roll/heading
  - Tilt-compensated heading available at standstill (D-12)
  - LSM6DSOXConfig, LIS3MDLConfig, IMUHeadingConfig dataclasses in config.py

affects: [engine-wiring, 11-02, 11-03, event-detector]

tech-stack:
  added: [adafruit-circuitpython-lsm6ds, adafruit-circuitpython-lis3mdl]
  patterns:
    - Adafruit CircuitPython try/except import pattern with module-level sentinel
    - Graceful absent: sensor_init_failed logged, _sensor=None, no raise
    - Unit conversion constants at module level (MS2_PER_G, DEG_PER_RAD)
    - Complementary filter (alpha=0.98) fusing gyro integration with accel tilt

key-files:
  created:
    - src/shitbox/collectors/imu_heading.py
  modified:
    - src/shitbox/events/sampler.py
    - src/shitbox/events/ring_buffer.py
    - src/shitbox/utils/config.py

key-decisions:
  - "MS2_PER_G = 9.80665 (not 9.81) for precision; accel offset subtracted after unit conversion, not before"
  - "adafruit_lis3mdl imported at module level as a name so tests can patch it via shitbox.collectors.imu_heading.adafruit_lis3mdl"
  - "IMUHeadingCollector exposes update_pitch/compute_heading/get_heading as public methods to satisfy test contract"
  - "ring_buffer.py unused imports removed (time, Iterator, Optional) as part of D-19 cleanup"

patterns-established:
  - "Sensor absent pattern: try import at module level, catch in setup(), set _sensor=None, log sensor_init_failed"
  - "Unit conversion: always divide m/s2 by MS2_PER_G, multiply rad/s by DEG_PER_RAD -- never reverse"

requirements-completed: [D-01, D-09, D-10, D-11, D-12, D-18, D-19]

duration: 8min
completed: 2026-04-09
---

# Phase 11 Plan 01: IMU Stack Rewrite Summary

**LSM6DSOX replaces MPU6050 with explicit m/s2-to-g and rad/s-to-deg/s conversion; new IMUHeadingCollector fuses LSM6DSOX and LIS3MDL via complementary filter for standstill heading (D-12)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-09T03:14:58Z
- **Completed:** 2026-04-09T03:22:29Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Rewrote `HighRateSampler` to use `adafruit-circuitpython-lsm6ds` at `Rate.RATE_104_HZ`; unit
  conversion proof: `ax_g = ax_ms2 / 9.80665`, `gx_dps = gx_rads * (180.0 / math.pi)`
- Created `IMUHeadingCollector` with `ComplementaryFilter(alpha=0.98)` blending gyro integration
  (short-term) with accel-derived tilt (long-term); tilt-compensated heading via LIS3MDL mag
- D-12 confirmed: `get_heading()` ignores `gps_speed_ms` parameter entirely -- heading updates at
  standstill without any GPS dependency
- Replaced `IMUConfig` (MPU6050, address 0x68) with `LSM6DSOXConfig`, `LIS3MDLConfig`, and
  `IMUHeadingConfig` dataclasses in config.py; all old MPU6050 references removed

## Unit Conversion Proof

The landmine in this migration is silent threshold breakage. The event detector compares in g and deg/s:

- `MS2_PER_G = 9.80665` -- LSM6DSOX `.acceleration` returns m/s², divide to get g
- `DEG_PER_RAD = 180.0 / math.pi` -- LSM6DSOX `.gyro` returns rad/s, multiply to get deg/s
- Calibration offsets (in g) subtracted after conversion, not before
- 9 passing tests confirm both conversions are correct (1g == 9.81 m/s2, 180 deg/s == pi rad/s)

## Complementary Filter Formula

```
accel_pitch = atan2(ay, sqrt(ax^2 + az^2))   # degrees
accel_roll  = atan2(-ax, az)                  # degrees
pitch = 0.98 * (pitch + gx * dt) + 0.02 * accel_pitch
roll  = 0.98 * (roll  + gy * dt) + 0.02 * accel_roll
```

Heading tilt compensation rotates the mag vector by pitch and roll before computing `atan2(yh, xh)`.

## D-12 Standstill Confirmation

`IMUHeadingCollector.get_heading()` accepts a `gps_speed_ms` parameter but ignores it. The comment
in the source reads: "gps_speed_ms is intentionally unused -- heading is computed regardless." The
filter runs unconditionally. Test `test_heading_available_at_zero_gps_speed` confirms heading is
a valid float in [0, 360) when `gps_speed_ms=0.0`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite HighRateSampler for LSM6DSOX** - `a0c8567` (feat)
2. **Task 2: IMUHeadingCollector with complementary filter** - `25e6988` (feat)

## Files Created/Modified

- `src/shitbox/events/sampler.py` - Rewritten for LSM6DSOX; MPU6050 register code deleted
- `src/shitbox/events/ring_buffer.py` - Unused imports removed (D-19 cleanup)
- `src/shitbox/utils/config.py` - IMUConfig replaced with LSM6DSOXConfig, LIS3MDLConfig, IMUHeadingConfig
- `src/shitbox/collectors/imu_heading.py` - New collector: ComplementaryFilter + tilt heading

## Decisions Made

- `MS2_PER_G = 9.80665` rather than the rounded `9.81` -- the standard gravity constant, matches
  what the adafruit library uses internally
- `adafruit_lis3mdl` imported as a bare module name at module level so tests can patch it via
  `shitbox.collectors.imu_heading.adafruit_lis3mdl`; the graceful-absent fallback works whether
  the library is missing entirely (ImportError on import) or hardware is absent (OSError in setup)
- `IMUHeadingCollector` exposes `update_pitch`, `compute_heading`, and `get_heading` as public
  methods; the wave-0 test contract calls these directly rather than going through the collector
  run loop, so they needed to be public stateless helpers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Removed pre-existing unused imports from ring_buffer.py**

- **Found during:** Task 1 (ruff check on modified files)
- **Issue:** `import time`, `Iterator`, `Optional` were unused in ring_buffer.py, causing ruff
  F401 failures that would block CI
- **Fix:** Removed the three unused imports; kept `threading`, `deque`, `dataclass`, `List`
- **Files modified:** `src/shitbox/events/ring_buffer.py`
- **Verification:** `ruff check src/shitbox/events/ring_buffer.py` exits zero
- **Committed in:** `a0c8567` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 -- missing correctness, blocking ruff)
**Impact on plan:** Necessary cleanup. The plan explicitly mentioned removing dead code from
ring_buffer.py; these were additional unused imports on top of the expected `_nice` lambda removal
(which wasn't present -- already clean).

## Issues Encountered

- `busio` and `board` are not available on macOS dev laptop; graceful-absent test patches
  `busio.I2C` to raise RuntimeError, confirming the fallback path works without hardware

## Next Phase Readiness

- LSM6DSOX sampler ready for engine wiring (plan 11-02/11-03)
- IMUHeadingCollector ready to be started alongside other collectors in UnifiedEngine
- Config dataclasses added to SensorsConfig; YAML config.yaml will need corresponding sections
  on the Pi for non-default values

## Self-Check: PASSED

- FOUND: src/shitbox/events/sampler.py
- FOUND: src/shitbox/events/ring_buffer.py
- FOUND: src/shitbox/utils/config.py
- FOUND: src/shitbox/collectors/imu_heading.py
- FOUND commit a0c8567 (Task 1)
- FOUND commit 25e6988 (Task 2)

---

*Phase: 11-v2-hardware-migration*
*Completed: 2026-04-09*
