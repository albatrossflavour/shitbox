---
phase: 11-v2-hardware-migration
verified: 2026-04-09T00:00:00Z
status: passed
score: 12/12 must-haves verified
gaps: []
human_verification:
  - test: "Brio 100 cabin camera udev rule"
    expected: "lsusb on Pi shows VID:PID 046d:085c for the Brio 100"
    why_human: "Assumed VID:PID from HARDWARE_IDS.md, not confirmed with physical device connected"
  - test: "Physical Pi 5 smoke test"
    expected: "All 6 smoke-test checks pass (confirmed by user prior to this verification)"
    why_human: "Requires hardware; user has confirmed all 6 passed"
---

# Phase 11: v2 Hardware Migration Verification Report

**Phase Goal:** Rewrite the sensor layer to match the v2 Pi 5 hat build — delete dead v1
collectors, add new v2 sensor collectors (LSM6DSOX+LIS3MDL IMU, DS18B20 1-Wire temps,
VEML7700 light, SEN0460 PM2.5, INA226 power), replace the UGREEN front camera with the
ELP 4K, bundle dead-code cleanup, and update pyproject/config so the stack runs cleanly
on the new Pi 5.

**Verified:** 2026-04-09
**Status:** PASSED
**Re-verification:** No (initial verification)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LSM6DSOX replaces MPU6050 in events/sampler.py | VERIFIED | `sampler.py` line 1 docstring "High-rate LSM6DSOX sampler"; no MPU6050 symbol anywhere in live `src/` |
| 2 | IMUHeadingCollector exists with complementary filter and LIS3MDL support | VERIFIED | `collectors/imu_heading.py` — full `ComplementaryFilter` class, `tilt_compensated_heading`, `IMUHeadingCollector` all present and substantive |
| 3 | DS18B20Collector replaces MCP9808 in temperature.py | VERIFIED | `collectors/temperature.py` — `DS18B20Collector` with dual-probe roles; MCP9808 absent from all live code |
| 4 | VEML7700Collector exists in collectors/light.py | VERIFIED | `collectors/light.py` — substantive `VEML7700Collector` with graceful degradation |
| 5 | SEN0460Collector exists in collectors/particulate.py, disabled by default | VERIFIED | `collectors/particulate.py` — `SEN0460Collector`, `enabled=False` default, I2C gated behind flag |
| 6 | INA226Collector exists in collectors/power.py, disabled by default | VERIFIED | `collectors/power.py` — `INA226Collector`, `enabled=False` default, smbus2 gated behind flag |
| 7 | All new collectors wired into UnifiedEngine (import, init, start, stop) | VERIFIED | `engine.py` imports all five; instantiated at lines 406-437; started/stopped in loop at lines 1829-1841 and 1946-1950 |
| 8 | pip_compositor.py deleted (D-15) | VERIFIED | File does not exist in `src/`; no references found in live code |
| 9 | pyproject.toml has all four new library deps | VERIFIED | `adafruit-circuitpython-lsm6ds>=4.6.2`, `adafruit-circuitpython-lis3mdl>=1.2.7`, `adafruit-circuitpython-veml7700>=2.2.1`, `w1thermsensor>=2.3.0` all present |
| 10 | config/config.yaml has real DS18B20 probe IDs (28- prefix) | VERIFIED | Lines 88-91: `28-00000024263a` (exterior), `28-0000002405b1` (engine_bay) |
| 11 | deploy/udev/99-shitbox-cameras.rules exists with ELP 32e4:0298 | VERIFIED | File exists; ELP rule `ATTRS{idVendor}=="32e4", ATTRS{idProduct}=="0298"` on line 9 |
| 12 | 168 tests passing, ruff check clean | VERIFIED | `pytest`: 168 passed, 1 warning; `ruff check src/`: All checks passed |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Role | Status | Notes |
|----------|------|--------|-------|
| `src/shitbox/events/sampler.py` | LSM6DSOX high-rate sampler | VERIFIED | Full implementation, no MPU6050 refs |
| `src/shitbox/collectors/imu_heading.py` | Complementary filter + LIS3MDL heading | VERIFIED | 290 lines, substantive |
| `src/shitbox/collectors/temperature.py` | DS18B20 dual-probe collector | VERIFIED | Replaces MCP9808 |
| `src/shitbox/collectors/light.py` | VEML7700 ambient light | VERIFIED | Graceful degradation per D-24 |
| `src/shitbox/collectors/particulate.py` | SEN0460 PM2.5 (default disabled) | VERIFIED | I2C gated; cable pinout documented in module docstring |
| `src/shitbox/collectors/power.py` | INA226 power monitor (default disabled) | VERIFIED | smbus2 gated; D-06 requirement met |
| `src/shitbox/collectors/_vendor/ina226.py` | Thin smbus2 INA226 driver | VERIFIED | Present, substantive |
| `src/shitbox/collectors/_vendor/dfrobot_airquality.py` | Thin smbus2 SEN0460 driver | VERIFIED | Present |
| `src/shitbox/events/engine.py` | UnifiedEngine wiring for all v2 collectors | VERIFIED | All five collectors imported, instantiated, started, stopped |
| `pyproject.toml` | New sensor library deps | VERIFIED | Four new deps declared |
| `config/config.yaml` | DS18B20 real probe IDs | VERIFIED | Both probes with `28-` prefix IDs |
| `deploy/udev/99-shitbox-cameras.rules` | ELP 4K + Brio 100 udev rules | VERIFIED (partial) | ELP confirmed; Brio VID:PID assumed, pending physical confirmation |

---

### Key Link Verification

| From | To | Via | Status | Notes |
|------|----|-----|--------|-------|
| `engine.py` | `imu_heading.py` | import + start loop | WIRED | Line 25 import; lines 434-437 init; lines 1834, 1950 start/stop |
| `engine.py` | `temperature.py` | import + start loop | WIRED | Line 29 import; lines 406-411 init; lines 1830, 1946 start/stop |
| `engine.py` | `light.py` | import + start loop | WIRED | Line 26 import; lines 413-418 init; lines 1831, 1947 start/stop |
| `engine.py` | `particulate.py` | import + start loop | WIRED | Line 27 import; lines 420-425 init; lines 1832, 1948 start/stop |
| `engine.py` | `power.py` | import + start loop | WIRED | Line 28 import; lines 427-431 init; lines 1833, 1949 start/stop |
| `sampler.py` | `adafruit_lsm6ds` | conditional import + LSM6DSOX() | WIRED | Lines 12-17; graceful absent if lib missing |
| `imu_heading.py` | `adafruit_lis3mdl` | conditional import + LIS3MDL() | WIRED | Lines 13-20; graceful absent if lib missing |
| `temperature.py` | `w1thermsensor` | conditional import + W1ThermSensor() | WIRED | Lines 23-30 |
| `power.py` | `_vendor/ina226.py` | conditional import | WIRED | Lines 20-21 |
| `particulate.py` | `_vendor/dfrobot_airquality.py` | conditional import | WIRED | Lines 25-26 |
| `config.yaml` | DS18B20 probe IDs | `sensor_ids` mapping | WIRED | Two real `28-` prefix IDs present |

---

### Anti-Patterns Found

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `collectors/light.py:89` | `to_reading` returns `Reading(sensor_type="light")` with no lux value stored | Info | Lux data is not persisted to SQLite in this phase; docstring acknowledges "no consumers wired in this phase" — consistent with phased approach |
| `collectors/particulate.py:95` | `to_reading` similarly returns bare `Reading(sensor_type="pm25")` | Info | Same pattern, same rationale |
| `.egg-info/PKG-INFO` | References MPU6050 and `adafruit-circuitpython-mcp9808` | Info | Stale build artefact, not live code. Does not affect runtime. `pyproject.toml` is correct. |

None of the above are blockers. The VEML7700 and SEN0460 `to_reading` stubs are intentional (logged in phase docs as deferred to a future dashboard integration phase). The sensors are collected and the data is available; storage schema extension is out of scope for phase 11.

---

### Human Verification Required

**1. Brio 100 cabin camera udev rule VID:PID**

**Test:** On the Pi 5, connect the Brio 100 and run `lsusb | grep -i brio` or `lsusb | grep 046d:085c`.
**Expected:** Device appears as `046d:085c`.
**Why human:** The `046d:085c` VID:PID in `99-shitbox-cameras.rules` is from HARDWARE_IDS.md (documented assumption) but cannot be confirmed from the dev laptop without the physical device.

**2. Physical Pi 5 smoke test (user-confirmed prior to verification)**

**Test:** Boot shitbox-telemetry.service on Pi 5 with v2 hardware attached.
**Expected:** All six checks pass (LSM6DSOX init, DS18B20 probes, VEML7700, SEN0460 disabled gracefully, INA226 disabled gracefully, heading collector running).
**Why human:** Requires hardware. User confirmed all 6 checks passed during the wave 0 validation session documented in `11-VALIDATION.md`.

---

### Summary

Phase 11 goal is fully achieved. The sensor layer has been rewritten for the v2 Pi 5 hat:

- MPU6050 is gone. LSM6DSOX is the high-rate sampler.
- Five new collectors are implemented, substantive, and wired into the engine with proper start/stop lifecycle.
- The two sensors not yet physically wired in v2 (SEN0460, INA226) correctly default to disabled and guard their I2C access.
- Dead code (pip_compositor.py) is deleted.
- pyproject.toml and config.yaml reflect the new hardware.
- ELP 4K udev rule is in place. Brio 100 rule uses a documented assumption pending physical confirmation.
- 168 tests pass. Ruff is clean.

The only open item is the Brio 100 VID:PID confirmation, which requires physical hardware and is flagged for human verification. It does not block the phase goal.

---

_Verified: 2026-04-09_
_Verifier: Claude (gsd-verifier)_
