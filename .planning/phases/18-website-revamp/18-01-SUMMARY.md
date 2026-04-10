---
phase: 18
plan: "01"
subsystem: sync
tags: [prometheus, metrics, ds18b20, veml7700, tdd, schema-migration]
dependency_graph:
  requires: []
  provides: [shitbox_lux metric, shitbox_temp probe label]
  affects: [batch_sync, database, temperature collector]
tech_stack:
  added: []
  patterns: [TDD red/green, cursor-based Prometheus sync, SQLite ALTER TABLE migration]
key_files:
  created:
    - tests/test_batch_sync_metrics.py
  modified:
    - src/shitbox/sync/batch_sync.py
    - src/shitbox/storage/models.py
    - src/shitbox/storage/database.py
    - src/shitbox/collectors/temperature.py
    - tests/test_database.py
decisions:
  - probe label added only when sensor_id is set, preserving backward compat for unlabelled readings
  - sensor_id mapped to role string (exterior/engine_bay) at collector layer, not sensor hardware ID
metrics:
  duration_minutes: 17
  completed_date: "2026-04-11"
  tasks_completed: 3
  files_changed: 6
---

# Phase 18 Plan 01: Prometheus Metrics for Lux and DS18B20 Probes Summary

Added `shitbox_lux` metric and `shitbox_temp{probe=...}` label support to the batch sync pipeline, with a schema v9 migration to carry probe identity through the storage layer.

## What Was Done

The VEML7700 ambient light sensor was already writing `lux` values to SQLite, but `_readings_to_metrics()` had no `"light"` branch so those readings were silently dropped on every sync cycle. Similarly, the DS18B20 temperature probes (exterior and engine_bay) were both syncing as `shitbox_temp` with no way to distinguish them in Prometheus.

The fix touches three layers:

**Storage layer (schema v9):** `sensor_id TEXT` column added to `readings` via `_migrate_to_v9`. The migration uses `ALTER TABLE ... ADD COLUMN` with a try/except for idempotency, matching the existing v2-v8 pattern. `SCHEMA_VERSION` bumped to 9, and both `insert_reading` and `insert_readings_batch` updated to write `sensor_id`. `_row_to_reading` maps it back out.

**Model layer:** `sensor_id: Optional[str] = None` added to the `Reading` dataclass after `temp_celsius`. `to_mqtt_payload()` for TEMPERATURE type now includes it.

**Collector layer:** `DS18B20Collector.to_reading()` passes `sensor_id=data.role`, so the probe's semantic name ("exterior", "engine_bay") flows from collection through to sync.

**Sync layer:** `_readings_to_metrics()` got a `"light"` branch emitting `shitbox_lux` when `lux is not None`, and the `"temp"` branch was extended to emit `shitbox_temp{probe=...}` when `sensor_id` is set, with a fallback to the existing unlabelled metric for backward compatibility.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_lux_none_produces_no_metric was XPASS(strict) immediately**
- **Found during:** Task 1
- **Issue:** The test asserted `"shitbox_lux" not in names` for a LIGHT reading with `lux=None`. This trivially passes because there was no `"light"` branch at all, so no shitbox_lux metric could ever be emitted. xfail(strict=True) requires the test to fail, so it was actually a test structure error.
- **Fix:** Removed the xfail decorator from `test_lux_none_produces_no_metric` -- it's a valid passing test at all times.
- **Files modified:** tests/test_batch_sync_metrics.py

**2. [Rule 1 - Bug] test_temp_no_sensor_id_backward_compat was XPASS(strict) after Task 2a**
- **Found during:** Task 2a verification
- **Issue:** Once `sensor_id` was added to the `Reading` dataclass, the `Reading(sensor_type=..., sensor_id=None, ...)` constructor call stopped raising TypeError. The test's assertion (no probe label in output) was trivially true since `_readings_to_metrics` hadn't been updated yet. xfail(strict=True) failed because the test passed.
- **Fix:** Removed the xfail decorator from `test_temp_no_sensor_id_backward_compat`.
- **Files modified:** tests/test_batch_sync_metrics.py

**3. [Rule 1 - Bug] Pre-existing E402 in temperature.py**
- **Found during:** Task 2a ruff verification
- **Issue:** `_SENSOR_NOT_READY_RETRY_SECONDS` constant was defined between stdlib and project imports, causing E402 on the three project imports below it.
- **Fix:** Moved the constant below all imports.
- **Files modified:** src/shitbox/collectors/temperature.py

**4. [Rule 1 - Bug] Missing cpu_percent in insert_readings_batch INSERT**
- **Found during:** Task 2a while updating the batch INSERT to add sensor_id
- **Issue:** `insert_readings_batch` column list had `cpu_temp_celsius, disk_percent, sync_backlog, throttle_flags` but was missing `cpu_percent`. The single-row `insert_reading` had it. The values tuple was also missing it, so the mismatch was self-consistent but data loss was occurring for cpu_percent in batch inserts.
- **Fix:** Added `cpu_percent` to both the column list and values tuple in `insert_readings_batch`.
- **Files modified:** src/shitbox/storage/database.py

**5. [Rule 1 - Bug] test_migration_v8 asserted exact version == 8**
- **Found during:** Task 2a test run
- **Issue:** The test asserted `version == 8` which fails once schema version advances to 9.
- **Fix:** Changed assertion to `>= 8` and added `test_migration_v9_adds_sensor_id_column`.
- **Files modified:** tests/test_database.py

## Known Stubs

None. All metric paths are fully wired.

## Self-Check: PASSED
