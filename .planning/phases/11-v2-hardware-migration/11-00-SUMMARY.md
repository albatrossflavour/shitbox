---
phase: 11-v2-hardware-migration
plan: "00"
subsystem: testing
tags: [lsm6dsox, lis3mdl, ds18b20, veml7700, sen0460, ina226, tdd, red-phase, imu, sensors]

requires: []
provides:
  - "RED test stubs for LSM6DSOX sampler (5 tests)"
  - "RED test stubs for IMUHeadingCollector with complementary filter (4 tests)"
  - "RED test stubs for DS18B20 dual-probe temperature collector (4 tests)"
  - "RED test stubs for VEML7700 ambient light collector (2 tests)"
  - "RED test stubs for SEN0460 PM2.5 particulate collector (3 tests)"
  - "RED test stubs for INA226 power monitor (3 tests)"
  - "Unit conversion comment guardrail: m/s2->g, rad/s->deg/s in sampler tests"
  - "Cable pinout docstring guardrail: cyan=SDA, blue=SCL in SEN0460 tests"
affects:
  - "11-01 (LSM6DSOX sampler rewrite — turns sampler RED tests GREEN)"
  - "11-02 (new collectors — turns heading/DS18B20/VEML7700/SEN0460/INA226 RED tests GREEN)"
  - "11-03 (hardware IDs from HARDWARE_IDS.md go into config)"

tech-stack:
  added: []
  patterns:
    - "RED-first TDD: test files reference non-existent modules, fail at import time"
    - "MagicMock-only test files: no real hardware libs imported at module top"
    - "Graceful-absent pattern: _disabled flag, _sensor=None, log+return-None, never raise"

key-files:
  created:
    - tests/events/__init__.py
    - tests/collectors/__init__.py
    - tests/events/test_sampler_lsm6dsox.py
    - tests/collectors/test_imu_heading.py
    - tests/collectors/test_temperature_ds18b20.py
    - tests/collectors/test_light_veml7700.py
    - tests/collectors/test_pm25_sen0460.py
    - tests/collectors/test_power_ina226.py
  modified: []

key-decisions:
  - "offset convention: ax_offset subtracted from converted value (raw 1.0g - 0.1 = 0.9g stored)"
  - "SEN0460 and INA226 default disabled: must not touch I2C unless config.enabled=True"
  - "All test files use MagicMock; no real adafruit/smbus2 libs required on dev laptop"

patterns-established:
  - "RED tests: import non-existent modules with type: ignore[import] — ImportError IS the red signal"
  - "Graceful-absent tests: collector.setup() must not raise; collect() returns None; _sensor=None"

requirements-completed:
  - D-01
  - D-03
  - D-04
  - D-05
  - D-06
  - D-09
  - D-10
  - D-11
  - D-13

duration: ~25min
completed: "2026-04-09"
---

# Phase 11 Plan 00: v2 Hardware Migration RED Phase Summary

**Six failing test stubs covering LSM6DSOX sampler, IMU heading filter, DS18B20 dual-probe, VEML7700, SEN0460, and INA226 — wave 0 RED phase complete, concrete DS18B20 IDs and ELP VID:PID recorded from Pi 5**

## Performance

- **Duration:** ~25 min (including human-action hardware discovery)
- **Started:** 2026-04-09T03:02:31Z
- **Completed:** 2026-04-09T03:15:00Z
- **Tasks:** 3 of 3 complete
- **Files modified:** 9

## Accomplishments

- Created `tests/events/` and `tests/collectors/` subdirectories with `__init__.py` files
- 5 failing RED tests for LSM6DSOX sampler: unit conversion (m/s2->g, rad/s->deg/s), graceful absent, 104 Hz rate, calibration offset
- 4 failing RED tests for IMUHeadingCollector: complementary filter alpha=0.98, tilt-compensated heading, heading at zero GPS speed (D-12 coverage), LIS3MDL graceful absent
- 12 failing RED tests across four new collectors: DS18B20 dual-probe, VEML7700 lux, SEN0460 PM2.5, INA226 power
- DS18B20 IDs discovered on Pi 5 via temperature differential: exterior=`28-00000024263a`, engine_bay=`28-0000002405b1`
- ELP 4K camera: VID:PID `32e4:0298`, `/dev/video0`

## Hardware IDs Discovered

DS18B20 probes identified by holding one probe (warmer = engine_bay):

- `exterior: 28-00000024263a` (22.6°C at time of recording)
- `engine_bay: 28-0000002405b1` (28.4°C at time of recording)

ELP 4K front camera:

- USB VID:PID: `32e4:0298` (device reports as "16MP USB Camera")
- Enumerated as `/dev/video0`

Brio 100 cabin camera: not captured (not connected during discovery). Confirm before writing udev rule in plan 03.

## Task Commits

1. **Task 1: RED stubs for LSM6DSOX sampler + complementary filter** - `1b170ab` (test)
2. **Task 2: RED stubs for DS18B20, VEML7700, SEN0460, INA226 collectors** - `a86f0d7` (test)
3. **Task 3: Hardware discovery on Pi 5** - `1d613dd` (docs)

## Files Created/Modified

- `tests/events/__init__.py` - New test subdirectory package
- `tests/collectors/__init__.py` - New test subdirectory package
- `tests/events/test_sampler_lsm6dsox.py` - 5 RED tests for LSM6DSOX sampler with unit conversion guardrails
- `tests/collectors/test_imu_heading.py` - 4 RED tests for IMUHeadingCollector (complementary filter + LIS3MDL)
- `tests/collectors/test_temperature_ds18b20.py` - 4 RED tests for DS18B20 dual-probe collector
- `tests/collectors/test_light_veml7700.py` - 2 RED tests for VEML7700 lux collector
- `tests/collectors/test_pm25_sen0460.py` - 3 RED tests for SEN0460 (includes cable pinout docstring guardrail)
- `tests/collectors/test_power_ina226.py` - 3 RED tests for INA226 power monitor
- `.planning/phases/11-v2-hardware-migration/HARDWARE_IDS.md` - Real DS18B20 IDs and ELP VID:PID from Pi 5

## Decisions Made

- `accel_offset_x` is applied after unit conversion (raw - offset in g units), matching the plan spec of "raw 1.0 g - offset 0.1 → stored 0.9 g"
- SEN0460 and INA226 tests verify disabled-by-default behaviour explicitly — I2C must never be touched when `config.enabled=False`
- All test files use `MagicMock` only at the top; real hardware libs patched inside test bodies so tests run on the dev laptop without Pi hardware
- Brio 100 VID:PID deferred — camera was not connected during discovery; must confirm in plan 03 before writing udev rule

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. Tests failed cleanly at import time or attribute access, as expected for the RED phase. Hardware discovery via temperature differential worked as described.

## Known Stubs

None in the test files themselves. The test files reference future implementations that don't exist yet:

- `shitbox.collectors.imu_heading.IMUHeadingCollector` — created in plan 02
- `shitbox.collectors.light.VEML7700Collector` — created in plan 02
- `shitbox.collectors.particulate.SEN0460Collector` — created in plan 02
- `shitbox.collectors.temperature.DS18B20Collector` — created in plan 02
- `shitbox.collectors.power.INA226Collector` — created in plan 02
- `shitbox.events.sampler.HighRateSampler._lsm6dsox` — added in plan 01

These are intentional stubs — this is the RED phase. Plans 01 and 02 turn them green.

## Next Phase Readiness

- All 21 RED tests are committed and failing cleanly
- HARDWARE_IDS.md committed with real sensor IDs — plans 03 and 04 are unblocked
- Plan 01 (LSM6DSOX sampler rewrite) ready to start
- Plan 02 (new collector implementations) ready to start
- Brio 100 VID:PID must be confirmed before plan 03 writes the udev rule — only remaining open item

---
*Phase: 11-v2-hardware-migration*
*Completed: 2026-04-09*
