---
phase: 03-thermal-resilience-and-storage-management
plan: "02"
subsystem: health
tags: [thermal, cpu-temperature, sysfs, vcgencmd, buzzer, wal, sqlite, daemon-thread]

requires:
  - phase: 03-01
    provides: beep_thermal_warning/critical/recovered/under_voltage buzzer functions, checkpoint_wal() on Database

provides:
  - ThermalMonitorService daemon thread reading sysfs CPU temp every 5 seconds
  - Hysteresis-based buzzer alerts at 70C warning and 80C critical with 5C re-arm threshold
  - Recovery beep when temperature drops to 65C after a warning
  - vcgencmd throttle bitmask decoded and logged on state change only
  - beep_under_voltage() fires when bit 0 of throttle bitmask is set
  - WAL TRUNCATE checkpoint running every 5 minutes from engine telemetry loop
  - get_status() reads cpu_temp from thermal_monitor.current_temp_celsius

affects:
  - 04-remote-health-metrics
  - engine lifecycle management

tech-stack:
  added: []
  patterns:
    - "Daemon thread service with start()/stop() lifecycle following BatchSyncService pattern"
    - "Hysteresis state machine using armed/disarmed booleans and re-arm threshold"
    - "Module-level buzzer function imports (not lazy) for test mockability via patch()"
    - "Instance methods _read_sysfs_temp/_read_throttled for test mockability via patch.object()"
    - "WAL checkpoint timer co-located in existing telemetry loop (no new thread)"

key-files:
  created:
    - src/shitbox/health/thermal_monitor.py
  modified:
    - src/shitbox/events/engine.py

key-decisions:
  - "HYSTERESIS_C=5.0 (not 3.0 as stated in plan) — tests explicitly require 65C re-arm threshold: 66C suppressed, 65C re-arms"
  - "Buzzer functions imported at module level (not lazily) — no circular import exists; module-level import required for patch() to work in tests"
  - "_read_sysfs_temp and _read_throttled are instance methods (not module-level functions) — tests use patch.object() which requires instance methods"
  - "_read_sysfs_temp returns raw millidegrees (int), division by 1000 in _check_thermal — tests mock returning 70000 and expect 70.0C temp"
  - "WAL checkpoint _last_wal_checkpoint initialised to 0.0 so first checkpoint fires immediately at engine start"
  - "get_status() replaced _read_pi_temp() call with thermal_monitor.current_temp_celsius for single source of truth"

patterns-established:
  - "Pattern 1: Hysteresis state machine — armed flag + <= comparison for re-arm threshold"
  - "Pattern 2: Pre-existing lint errors in engine.py are out of scope; only new-code errors fixed"

requirements-completed: [THRM-01, THRM-02, THRM-03, STOR-01]

duration: 3min
completed: "2026-02-26"
---

# Phase 3 Plan 02: ThermalMonitorService Implementation Summary

**ThermalMonitorService daemon thread with 5C hysteresis alerts at 70/80C, throttle decode on bitmask change, and 5-minute WAL TRUNCATE checkpoint wired into engine lifecycle**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T19:36:26Z
- **Completed:** 2026-02-26T19:39:18Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `ThermalMonitorService` implemented with 5-second polling, hysteresis state machine, throttle decode, and thread-safe `current_temp_celsius` property
- All 9 pre-written thermal monitor tests pass on first implementation pass (after correcting hysteresis constant from plan)
- Engine wired with `thermal_monitor.start()/stop()` lifecycle, 5-minute WAL checkpoint timer, and `get_status()` updated to read from thermal monitor
- Full 52-test suite passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement ThermalMonitorService** - `73f22fd` (feat)
2. **Task 2: Wire ThermalMonitorService and WAL checkpoint into engine** - `8650d47` (feat)

**Plan metadata:** see final commit below

## Files Created/Modified

- `src/shitbox/health/thermal_monitor.py` — ThermalMonitorService with hysteresis state machine, sysfs reader, vcgencmd throttle decode, and module-level buzzer imports
- `src/shitbox/events/engine.py` — Import, init, start, stop wiring for thermal monitor; WAL checkpoint timer in telemetry loop; get_status() updated

## Decisions Made

- `HYSTERESIS_C = 5.0` (not 3.0 as stated in plan) — the test scaffold is the authoritative spec: 66C is suppressed, 65C re-arms, so threshold is `TEMP_WARNING_C - 5.0 = 65.0`
- Buzzer functions imported at module level (not lazily inside methods) — tests use `patch("shitbox.health.thermal_monitor.beep_thermal_warning")` which requires module-level binding; no circular import exists
- `_read_sysfs_temp` and `_read_throttled` are instance methods — tests mock them via `patch.object(service, ...)` which requires bound methods
- `_read_sysfs_temp` returns raw millidegrees (int), division by 1000 happens in `_check_thermal` — test mocks return 70000, test asserts 70.0C

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected HYSTERESIS_C from 3.0 to 5.0 to match test scaffold**

- **Found during:** Task 1 (ThermalMonitorService implementation)
- **Issue:** Plan specified `HYSTERESIS_C = 3.0` (re-arm at 67C), but the pre-written test `test_hysteresis_suppresses_below_rearm` explicitly shows 66C is suppressed and 65C re-arms, requiring re-arm at `70 - 5 = 65C`
- **Fix:** Set `HYSTERESIS_C = 5.0` and used `<= _WARN_REARM_C` comparison for re-arm
- **Files modified:** `src/shitbox/health/thermal_monitor.py`
- **Verification:** All 9 thermal monitor tests pass with `HYSTERESIS_C = 5.0`
- **Committed in:** `73f22fd` (Task 1 commit)

**2. [Rule 1 - Bug] Changed buzzer imports to module level (not lazy in methods)**

- **Found during:** Task 1 (ThermalMonitorService implementation)
- **Issue:** Plan suggested lazy imports inside methods; but tests patch via `patch("shitbox.health.thermal_monitor.beep_thermal_warning")` which requires the name to be bound at module level
- **Fix:** Imported `beep_thermal_warning`, `beep_thermal_critical`, `beep_thermal_recovered`, `beep_under_voltage` at module level in the standard import block
- **Files modified:** `src/shitbox/health/thermal_monitor.py`
- **Verification:** All 9 thermal monitor tests pass; ruff/mypy pass
- **Committed in:** `73f22fd` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs in plan spec vs test expectations)
**Impact on plan:** Both fixes necessary for tests to pass. No scope creep. The test scaffold is the authoritative specification.

## Issues Encountered

None beyond the hysteresis and import deviations documented above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 3 requirements THRM-01, THRM-02, THRM-03, STOR-01 are now fully satisfied
- `ThermalMonitorService.current_temp_celsius` is ready for Phase 4 remote health metrics reporting
- WAL checkpoint runs every 5 minutes, preventing unbounded WAL growth on the SD card
- All 52 existing tests pass — no regressions

---

*Phase: 03-thermal-resilience-and-storage-management*
*Completed: 2026-02-26*
