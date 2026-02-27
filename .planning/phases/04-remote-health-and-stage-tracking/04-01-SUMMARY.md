---
phase: 04-remote-health-and-stage-tracking
plan: "01"
subsystem: health
tags: [prometheus, shutil, thermal, schema-migration, sqlite]

requires:
  - phase: 03-thermal-resilience-and-storage-management
    provides: ThermalMonitorService with current_temp_celsius property
provides:
  - Schema v4 migration with health columns and trip/waypoint tables
  - HealthCollector value assembler for system metrics
  - Prometheus metrics for disk_pct, sync_backlog, throttle_flags
  - ThermalMonitorService.last_throttled_raw property
  - Database trip_state and waypoints_reached helpers (for plan 04-02)
affects: [04-02, batch-sync, grafana]

tech-stack:
  added: []
  patterns:
    - "Value assembler pattern (HealthCollector) — non-threaded collector called from telemetry loop"
    - "Schema migration v4 following v2/v3 ALTER TABLE + try/except pattern"

key-files:
  created:
    - src/shitbox/health/health_collector.py
    - tests/test_health_collector.py
  modified:
    - src/shitbox/storage/database.py
    - src/shitbox/storage/models.py
    - src/shitbox/health/thermal_monitor.py
    - src/shitbox/sync/batch_sync.py
    - src/shitbox/events/engine.py

key-decisions:
  - "HealthCollector is a value assembler called from _record_telemetry, not a BaseCollector subclass with its own thread"
  - "last_throttled_raw exposed as property to avoid duplicate vcgencmd subprocess calls"
  - "trip_state table uses key-value pattern with separate value_real and value_text columns"

patterns-established:
  - "Value assembler pattern: non-threaded collector wired into existing telemetry loop"

requirements-completed: [HLTH-01]

duration: ~5min
completed: 2026-02-27
---

# Plan 04-01: Health Metrics Summary

**Schema v4 migration with health columns, HealthCollector assembling CPU temp/disk/backlog/throttle into Prometheus metrics**

## Performance

- **Duration:** ~5 min
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Schema v4 migration adds disk_percent, sync_backlog, throttle_flags to readings plus trip_state and waypoints_reached tables
- HealthCollector assembles four system health metrics from ThermalMonitorService, shutil.disk_usage, and BatchSyncService
- BatchSync emits three new Prometheus metrics (shitbox_disk_pct, shitbox_sync_backlog, shitbox_throttle_flags)
- 9 tests covering all health collection paths including graceful degradation

## Task Commits

Each task was committed atomically:

1. **Task 1: Schema v4 migration, Reading model, database helpers** - `dfec28f` (feat)
2. **Task 2: HealthCollector, throttle property, batch_sync metrics, engine wiring, tests** - `3a734f3` (feat)

## Files Created/Modified

- `src/shitbox/health/health_collector.py` - Value assembler for system health metrics
- `tests/test_health_collector.py` - 9 tests for health collection and Prometheus emission
- `src/shitbox/storage/database.py` - Schema v4 migration, trip_state/waypoint helpers
- `src/shitbox/storage/models.py` - Three new optional fields on Reading
- `src/shitbox/health/thermal_monitor.py` - last_throttled_raw property
- `src/shitbox/sync/batch_sync.py` - Three new Prometheus metric emissions
- `src/shitbox/events/engine.py` - HealthCollector wiring in telemetry loop

## Decisions Made

- HealthCollector is a value assembler (not a BaseCollector subclass) — called directly from _record_telemetry
- Reused ThermalMonitorService.last_throttled_raw property instead of separate vcgencmd call

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Schema v4 tables (trip_state, waypoints_reached) ready for plan 04-02
- Database helpers (get/set_trip_state, record_waypoint_reached) available for distance tracking

---
*Phase: 04-remote-health-and-stage-tracking*
*Completed: 2026-02-27*
