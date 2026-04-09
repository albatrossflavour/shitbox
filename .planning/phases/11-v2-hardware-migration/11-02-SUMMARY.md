---
phase: 11-v2-hardware-migration
plan: "02"
subsystem: sensors
tags: [ds18b20, w1thermsensor, veml7700, adafruit, sen0460, ina226, smbus2, dfrobot, i2c, 1-wire]

requires:
  - phase: 11-01
    provides: LSM6DSOX + LIS3MDL + IMUHeading collectors (RED tests) that this wave turns green

provides:
  - DS18B20Collector: dual 1-Wire probe reading with exterior/engine_bay role mapping
  - VEML7700Collector: ambient lux at 1 Hz with graceful-absent handling
  - SEN0460Collector: PM2.5 particulate, disabled by default, cable pinout documented
  - INA226Collector: bus voltage + current via smbus2, disabled by default
  - _vendor/ina226.py: thin ~60-line smbus2 INA226 register driver
  - _vendor/dfrobot_airquality.py: minimal DFRobot SEN0460 stub (full driver TODO before Pi 5 enable)

affects: [engine-wiring, config-yaml, phase-12]

tech-stack:
  added: [w1thermsensor (1-Wire DS18B20), adafruit-veml7700 (light), smbus2 (INA226)]
  patterns:
    - graceful-absent via module-level try/except + _disabled flag
    - sensor disabled check at setup() entry prevents I2C bus opens
    - vendored drivers in src/shitbox/collectors/_vendor/ for unmaintained/PyPI-absent libs

key-files:
  created:
    - src/shitbox/collectors/light.py
    - src/shitbox/collectors/particulate.py
    - src/shitbox/collectors/_vendor/__init__.py
    - src/shitbox/collectors/_vendor/ina226.py
    - src/shitbox/collectors/_vendor/dfrobot_airquality.py
  modified:
    - src/shitbox/collectors/temperature.py
    - src/shitbox/collectors/power.py
    - src/shitbox/utils/config.py

key-decisions:
  - "SEN0460 uses busio.I2C (not smbus2) — test contracts from wave 0 set this boundary"
  - "INA226 vendor driver uses read_word_data + byte-swap, not read_i2c_block_data"
  - "DFRobot SEN0460 vendored as stub — full driver TODO before enabling on Pi 5"
  - "DS18B20Reading dataclass carries role attribute directly, not via metadata dict"
  - "busio patched at module level in tests — import busio must be top-level, not inside setup()"

patterns-established:
  - "Disabled-by-default pattern: check self._enabled first in setup(), never open I2C if false"
  - "Module-level import guard: try/except ImportError → None sentinels → patched in tests"
  - "Reading subclasses carry domain-specific attributes (role, voltage_v, current_a) rather than generic metadata dict"

requirements-completed: [D-03, D-04, D-05, D-06, D-16, D-17, D-24]

duration: 12min
completed: 2026-04-09
---

# Phase 11 Plan 02: Sensor Collector Wave 2 Summary

**DS18B20 dual-probe 1-Wire collector, VEML7700 lux collector, SEN0460 PM2.5 stub (disabled), and INA226 power monitor (disabled) — four wave-0 RED tests turned green, MCP9808 and INA219 deleted**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-09T13:27:00Z
- **Completed:** 2026-04-09T13:31:30Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Rewrote temperature.py: MCP9808 deleted, DS18B20Collector reads two 1-Wire probes by ID with exterior/engine_bay role mapping
- Added light.py: VEML7700Collector reads ambient lux at 1 Hz with graceful I2C-NACK handling
- Added particulate.py: SEN0460Collector with cable pinout docstring guardrail (cyan=SDA, blue=SCL), ships disabled
- Rewrote power.py: INA226Collector via in-tree smbus2 wrapper, ships disabled per D-06
- Added `_vendor/ina226.py`: ~60-line smbus2 register driver using read_word_data with big/little-endian byte swap
- Added `_vendor/dfrobot_airquality.py`: minimal stub matching DFRobot API; full driver to be dropped in before enabling
- All 12 wave-0 collector tests pass; full collector suite (16 tests) green

## Task Commits

1. **Task 1: DS18B20 + VEML7700 collectors** - `4facf0f` (feat)
2. **Task 2: SEN0460 + INA226 collectors + vendored drivers** - `cae880d` (feat)

## Files Created/Modified

- `src/shitbox/collectors/temperature.py` - DS18B20Collector replacing MCP9808; dual-probe with role mapping
- `src/shitbox/collectors/light.py` - VEML7700Collector, 1 Hz lux, graceful absent
- `src/shitbox/collectors/particulate.py` - SEN0460Collector, disabled by default, cable pinout docstring
- `src/shitbox/collectors/power.py` - INA226Collector, disabled by default, uses _vendor.ina226
- `src/shitbox/collectors/_vendor/__init__.py` - Package marker for vendored drivers
- `src/shitbox/collectors/_vendor/ina226.py` - Thin smbus2 INA226 driver (~60 lines)
- `src/shitbox/collectors/_vendor/dfrobot_airquality.py` - DFRobot SEN0460 stub with TODO
- `src/shitbox/utils/config.py` - Added DS18B20ProbeConfig, updated TemperatureConfig, LightConfig, updated PowerConfig, ParticulateConfig

## Decisions Made

- SEN0460 uses `busio.I2C` rather than `smbus2.SMBus` — the wave-0 test contract patches `busio`, so the import boundary was non-negotiable
- INA226 vendor driver uses `read_word_data` with explicit byte-swap — test mocks `read_word_data`, not `read_i2c_block_data`
- `DS18B20Reading` carries `role` as a direct dataclass attribute — tests access `r.role` directly, not via a metadata dict
- Module-level `try/except ImportError` pattern for all optional hardware libs — enables patch-at-module-level in tests without import machinery fighting the collector

## Deviations from Plan

None — plan executed exactly as written, with the test contracts resolving ambiguities in the implementation spec (busio vs smbus2 for SEN0460, read_word_data for INA226).

## Issues Encountered

One minor ruff I001 (import sort) auto-fixed with `ruff --fix` on particulate.py and power.py. Tests still passed after fix.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All four new collectors are wired up and test-green. Engine wiring (plan 03) can now import DS18B20Collector, VEML7700Collector, SEN0460Collector, INA226Collector.
- SEN0460 and INA226 remain disabled until hardware is wired — set `enabled: true` in config.yaml to activate.
- DFRobot stub in `_vendor/dfrobot_airquality.py` must be replaced with full upstream driver before enabling SEN0460 on the Pi.

---

*Phase: 11-v2-hardware-migration*
*Completed: 2026-04-09*
