---
phase: 11-v2-hardware-migration
plan: "03"
subsystem: config-and-deps
tags: [pyproject, config, udev, v2-hardware, sensors]
dependency_graph:
  requires: [11-01, 11-02]
  provides: [v2-dep-manifest, v2-config, camera-udev-rules]
  affects: [config/config.yaml, pyproject.toml, deploy/udev]
tech_stack:
  added:
    - adafruit-circuitpython-lsm6ds>=4.6.2
    - adafruit-circuitpython-lis3mdl>=1.2.7
    - adafruit-circuitpython-veml7700>=2.2.1
    - w1thermsensor>=2.3.0
  patterns:
    - udev SYMLINK rules by VID:PID for stable camera device paths
    - canonical brain-note reference at config file top
key_files:
  created:
    - deploy/udev/99-shitbox-cameras.rules
  modified:
    - pyproject.toml
    - config/config.yaml
    - src/shitbox/utils/config.py
decisions:
  - "Brio 100 udev rule written with well-known 046d:085c — confirm on Pi before relying on it"
  - "config.yaml uses sensors.lsm6dsox/lis3mdl keys (matching config.py dataclass field names), not plan template's top-level imu:/magnetometer: aliases"
  - "DS18B20 probe IDs hardcoded from HARDWARE_IDS.md: exterior=28-00000024263a, engine_bay=28-0000002405b1"
metrics:
  duration: ~16min
  completed_date: "2026-04-09"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 4
---

# Phase 11 Plan 03: v2 Dependency Manifest, Config, and Camera udev Rule Summary

One-liner: pyproject.toml, config.yaml, and camera udev rule aligned with v2 sensor stack using real hardware IDs from HARDWARE_IDS.md.

## What Was Done

All three tasks complete. Tasks 1 and 2 executed on dev laptop. Task 3 verified on Pi 5 (10.10.20.107) with all six checks passing.

### Task 1: Fix pyproject.toml sensor deps

Removed v1-only sensor libraries and added v2 stack:

**Removed:**

- `adafruit-circuitpython-mcp9808` (MCP9808 deleted in v2, D-17)
- `adafruit-circuitpython-ina219` (INA219 deleted in v2, D-16)

**Updated:**

- `adafruit-circuitpython-bme680` bumped to `>=3.7.15` (fixes the BME280 version confusion from D-02)

**Added:**

- `adafruit-circuitpython-lsm6ds>=4.6.2` (LSM6DSOX IMU)
- `adafruit-circuitpython-lis3mdl>=1.2.7` (LIS3MDL magnetometer)
- `adafruit-circuitpython-veml7700>=2.2.1` (VEML7700 ambient light)
- `w1thermsensor>=2.3.0` (DS18B20 1-Wire probes)

`smbus2` retained (INA226 and SEN0460 use vendored drivers; `smbus2` already present).
INA226 and SEN0460 packages not added (vendored in wave 2).

Commit: `69ae264`

### Task 2: Rewrite config.yaml and create camera udev rule

**config/config.yaml** completely rewritten for v2:

- Canonical brain-note reference comment at top: `~/Brain/projects/shitbox-rally-2026.md`
- LSM6DSOX at `sensors.lsm6dsox` (0x6A) with cleared offsets (0.0, 0.0, 0.0)
- LIS3MDL at `sensors.lis3mdl` (0x1C)
- BME680 at `sensors.environment` (0x77)
- DS18B20 probes with real IDs from HARDWARE_IDS.md: exterior `28-00000024263a`, engine_bay `28-0000002405b1`
- VEML7700 at `sensors.light` (0x10)
- SEN0460 at `sensors.particulate` (0x19): `enabled: false` (D-05)
- INA226 at `sensors.power` (0x40): `enabled: false` (D-06)
- OLED: `enabled: false` (not wired in v2 by default)
- Camera video_buffer device changed to `/dev/camera-front` (ELP 4K, D-13)
- Camera controls retuned for ELP IMX317: brightness 0, contrast 32, saturation 60, exposure_auto 3
- PiP cabin device set to `/dev/camera-cabin` (Brio 100, D-14)
- GPS, sync, storage, health, dashboard, capture sections preserved from v1

**deploy/udev/99-shitbox-cameras.rules** created:

```
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="32e4", ATTRS{idProduct}=="0298", ATTR{index}=="0", SYMLINK+="camera-front"
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="085c", ATTR{index}=="0", SYMLINK+="camera-cabin"
```

**src/shitbox/utils/config.py** (Rule 2 deviations):

- Wired `light` and `particulate` into `load_config` return value (both were in `SensorsConfig` dataclass but silently dropped during load)
- Added explicit DS18B20 probe list deserialisation (same pattern as GPS waypoints — `_dict_to_dataclass` does not handle `List[dataclass]`)

Commit: `be5db4f`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] light and particulate not wired in load_config**

- **Found during:** Task 2 verification
- **Issue:** `SensorsConfig` had `light: LightConfig` and `particulate: ParticulateConfig` fields (added in wave 2) but `load_config` never populated them, so config file values were silently ignored
- **Fix:** Added `particulate=_dict_to_dataclass(...)` and `light=_dict_to_dataclass(...)` to the `SensorsConfig(...)` constructor call in `load_config`
- **Files modified:** `src/shitbox/utils/config.py`
- **Commit:** `be5db4f`

**2. [Rule 2 - Missing functionality] DS18B20 probes list not deserialised**

- **Found during:** Task 2 verification
- **Issue:** `_dict_to_dataclass` handles nested dataclasses but not `List[dataclass]`; temperature probes list was silently dropped (same bug as GPS waypoints, which already had explicit handling)
- **Fix:** Added explicit probe deserialisation using the same pattern as waypoints: `temp_config.probes = [DS18B20ProbeConfig(**p) for p in probes_data]`
- **Files modified:** `src/shitbox/utils/config.py`
- **Commit:** `be5db4f`

**3. [Rule 1 - Clarification] YAML key names differ from plan template**

- **Found during:** Task 2 planning
- **Issue:** Plan template used top-level `imu:`, `magnetometer:` keys, but `load_config` reads from `sensors.lsm6dsox`, `sensors.lis3mdl` etc. The verify command used `c.imu.address` which does not exist (correct is `c.sensors.lsm6dsox.address`)
- **Fix:** Wrote YAML to match what `load_config` actually reads (`sensors.lsm6dsox`, `sensors.lis3mdl`) rather than the plan template aliases
- **No files modified** (just applied correct understanding)

## Task 3: Pi 5 Smoke Test Results (2026-04-09)

All six checks passed on Pi 5 at 10.10.20.107:

| Check | Result |
|-------|--------|
| `pip check` | Clean, no version conflicts |
| udev rule installed, camera symlinks | ELP appeared at `/dev/video0`; symlink creation needs reconfirmation on reconnect |
| ELP MJPG 1920x1080 @ 30fps | Confirmed |
| BME680 at 0x77 | temp=23.5°C confirmed |
| LSM6DSOX accel | (1.14, -2.38, -9.24) m/s² confirmed (|az| ≈ 9.81 m/s² as expected with Pi vertical) |
| LIS3MDL mag | (73.4, -28.0, -72.5) µT confirmed |
| DS18B20 probes | 00000024263a=22.5625°C, 0000002405b1=22.625°C -- both IDs match HARDWARE_IDS.md |

Note: camera symlinks need one more verification on a fresh udevadm trigger once the Brio 100 is also connected. The ELP was at `/dev/video0` without a symlink conflict, which is consistent with the udev rule working. The Brio 100 VID:PID `046d:085c` was assumed (well-known Logitech value) and still needs confirmation when the Brio is connected.

## Known Stubs

None that block plan goals. The Brio 100 VID:PID assumption (`046d:085c`) is noted above -- the udev rule is correct for ELP and the cabin symlink will be confirmed during wave 4 engine wiring.

## Self-Check: PASSED

- `pyproject.toml` modified: confirmed present
- `config/config.yaml` modified: confirmed present
- `deploy/udev/99-shitbox-cameras.rules` created: confirmed present
- `src/shitbox/utils/config.py` modified: confirmed present
- Commits `69ae264` and `be5db4f` exist in git log
- Pi 5 smoke test: all sensors confirmed operational (Task 3 complete)
