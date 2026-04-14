---
phase: 17-driver-display
plan: 01
subsystem: telemetry, dashboard, testing
tags: [sse, ds18b20, temperature, thermal-monitor, alerts, wave0-tests]

requires:
  - phase: 13-driver-tracking
    provides: active_driver in SSE slow stream and driver_state module
  - phase: 15-hardware-hardening
    provides: ThermalMonitorService with _check_thermal/_check_throttled structure

provides:
  - DS18B20 cabin temp fallback in engine._on_reading (elif SensorType.TEMPERATURE branch)
  - dashboard_push_event wired into thermal_monitor warning, critical, and undervoltage branches
  - Wave 0 test stubs for DS18B20 fallback, ALERT bridge, event ticker cap, and active_driver SSE key

affects: [17-02-kiosk-frontend, testing]

tech-stack:
  added: []
  patterns:
    - "try/except import of dashboard module in hardware service (graceful degradation)"
    - "elif sensor type branch in _on_reading for DS18B20 fallback (last-write wins)"

key-files:
  created:
    - tests/test_engine_boot.py (new test: test_on_reading_temperature_updates_cabin_temp)
    - tests/test_thermal_monitor.py (new tests: test_thermal_warning_pushes_dashboard_alert, test_undervoltage_pushes_dashboard_alert)
    - tests/test_dashboard.py (new tests: test_event_ticker_max_five, test_sse_slow_has_active_driver_key)
  modified:
    - src/shitbox/events/engine.py
    - src/shitbox/health/thermal_monitor.py

key-decisions:
  - "dashboard_push_event imported via try/except in thermal_monitor — mirrors existing buzzer/speaker pattern, module loads without dashboard present"
  - "elif branch in _on_reading rather than separate method — minimal change, keeps hot path unchanged"
  - "test_sse_slow_has_active_driver_key is GREEN at plan end — active_driver already in SSE from Phase 13, test confirms it remains there"
  - "test_event_ticker_max_five intentionally stays RED — Plan 17-02 owns the index.html change"

requirements-completed: [DISP-01, DISP-02, DISP-04]

duration: 4min
completed: 2026-04-10
---

# Phase 17 Plan 01: Backend Fixes and Wave 0 Test Scaffolds Summary

**DS18B20 cabin temp fallback wired into _on_reading, thermal/undervoltage alerts bridged to SSE push_event, and four Wave 0 test stubs landed for Plan 17-02 verification.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-10T01:46:28Z
- **Completed:** 2026-04-10T01:50:09Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `engine._on_reading` now handles `SensorType.TEMPERATURE` readings from DS18B20 — kiosk cabin temp tile will populate when BME680 is absent or still initialising (DISP-01, D-09)
- `thermal_monitor.py` pushes `ALERT` events into the SSE queue on thermal warning, thermal critical, and undervoltage — alert bridge complete (DISP-04, D-05)
- Four Wave 0 tests in three files provide the RED/GREEN scaffolding Plan 17-02 depends on; three are GREEN now, one stays RED until Plan 17-02 changes the ticker cap

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 — write failing tests** - `f45a345` (test)
2. **Task 2: Fix DS18B20 cabin temp fallback** - `ab875ee` (feat)
3. **Task 3: Bridge thermal and undervoltage alerts into SSE** - `b014dce` (feat)

## Files Created/Modified

- `tests/test_engine_boot.py` - Added `test_on_reading_temperature_updates_cabin_temp` (was RED, now GREEN after Task 2)
- `tests/test_thermal_monitor.py` - Added `test_thermal_warning_pushes_dashboard_alert` and `test_undervoltage_pushes_dashboard_alert` (were RED, now GREEN after Task 3)
- `tests/test_dashboard.py` - Added `test_event_ticker_max_five` (intentionally RED, Plan 17-02) and `test_sse_slow_has_active_driver_key` (GREEN — already present from Phase 13)
- `src/shitbox/events/engine.py` - Added `elif SensorType.TEMPERATURE` branch in `_on_reading`
- `src/shitbox/health/thermal_monitor.py` - Added `dashboard_push_event` import (try/except) and three call sites in warning, critical, and undervoltage branches

## Decisions Made

- `dashboard_push_event` imported via `try/except ImportError` in `thermal_monitor.py`, matching the existing pattern for buzzer/speaker imports. The fallback is a no-op so the thermal monitor loads on hardware without a dashboard running.
- The `elif` branch in `_on_reading` uses last-write wins semantics. If both BME680 and DS18B20 fire in the same second, whichever arrives second sets `_cabin_temp_c`. This is acceptable per the research notes (Pitfall 3).
- `test_sse_slow_has_active_driver_key` came up GREEN immediately because Phase 13 already wired `active_driver` into the slow SSE payload. The test is useful as a regression guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Split overly long elif line to stay within ruff E501 limit**

- **Found during:** Task 2 (DS18B20 fallback)
- **Issue:** The initial single-line `elif reading.sensor_type == SensorType.TEMPERATURE and reading.temp_celsius is not None:` was 101 chars (limit is 100). The preceding `if` line on the same logic was already 102 chars and pre-existing, but introducing a new violation was unnecessary.
- **Fix:** Wrapped the elif condition in parentheses across three lines.
- **Files modified:** `src/shitbox/events/engine.py`
- **Committed in:** `ab875ee` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 code style/bug)
**Impact on plan:** Minimal. No scope change, one cosmetic fix to keep ruff clean on the new lines.

## Issues Encountered

None — all tasks executed as specified.

## Known Stubs

None. The Wave 0 tests are deliberately RED (not stubs); they fail against real assertions and will go GREEN when the corresponding implementation lands.

`test_event_ticker_max_five` is intentionally RED pending Plan 17-02. It is a real failing assertion, not a placeholder.

## Next Phase Readiness

- Plan 17-02 (kiosk frontend) can proceed. Three of four Wave 0 tests are GREEN.
- `test_event_ticker_max_five` provides Plan 17-02 with its first acceptance check: change `events.length > 10` to `events.length > 5` in `index.html`.
- `_cabin_temp_c` will now be populated from DS18B20 when BME680 is absent — kiosk cabin temp tile should show values on next deploy.
- ALERT events from thermal and undervoltage conditions will appear in the `/sse/events` stream immediately once deployed.

---
*Phase: 17-driver-display*
*Completed: 2026-04-10*
