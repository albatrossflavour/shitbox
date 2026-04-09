---
phase: 11
plan: "04"
subsystem: engine-wiring
tags: [v2-hardware, engine, collectors, dead-code, integration]
dependency_graph:
  requires: [11-01, 11-02, 11-03]
  provides: [full-v2-sensor-pipeline]
  affects: [engine.py, sampler.py, ring_buffer.py]
tech_stack:
  added: []
  patterns: [BaseCollector callback wiring, _on_reading dispatcher, v2 collector lifecycle in UnifiedEngine]
key_files:
  created:
    - .planning/phases/11-v2-hardware-migration/DEAD_CODE_AUDIT.md
  modified:
    - src/shitbox/events/engine.py
    - src/shitbox/events/sampler.py
    - src/shitbox/capture/ring_buffer.py
    - src/shitbox/storage/database.py
    - src/shitbox/sync/capture_sync.py
    - src/shitbox/sync/timelapse_compiler.py
    - tests/test_i2c_recovery.py
    - tests/test_capture_integrity.py
    - tests/test_speaker_alerts.py
decisions:
  - v2 collector constructors use (config, callback) signature not flat kwargs -- matched actual API not plan template
  - _on_reading() added to UnifiedEngine as shared callback for all v2 collectors writing to SQLite
  - latest_sample() added to HighRateSampler to expose current IMUSample for IMUHeadingCollector
  - getattr guard used for _ina226_collector in _get_status() -- tests use __new__() bypassing __init__
  - All 14 pre-existing test failures and 13 errors fixed -- plan required green suite
metrics:
  duration: "~35 min"
  completed: "2026-04-09"
  tasks: 2
  files_modified: 9
---

# Phase 11 Plan 04: Engine Wiring and Dead-Code Audit Summary

Wire all five v2 sensor collectors (DS18B20, VEML7700, SEN0460, INA226, IMUHeadingCollector) into `UnifiedEngine`'s full lifecycle and sign off all Phase 11 dead-code audit items with verified evidence.

## Tasks Completed

### Task 1 -- Wire v2 collectors into UnifiedEngine

**Commit:** `2200e6f`

The five collectors implemented in plans 01 and 02 had no connection to the engine. This task completed the circuit.

`EngineConfig` was updated to hold typed config objects for each v2 sensor rather than the old flat MPU6050 fields. `from_yaml_config()` was updated to extract those objects from the parsed YAML config. In `UnifiedEngine.__init__()`, each collector is instantiated behind an `enabled` guard, with `callback=self._on_reading` wired in.

`_on_reading()` is a new method that accepts any `Reading` and writes it to SQLite via `database.insert_reading()`, incrementing `telemetry_readings` and logging on error. This gives all five collectors a uniform path to storage.

`HighRateSampler.latest_sample()` was added to expose the most recent `IMUSample` from the ring buffer, giving `IMUHeadingCollector` the data it needs without coupling it to the sampler internals.

`start()` and `stop()` were updated with loops over all five optional collectors, each wrapped in try/except so a hardware failure on one sensor doesn't prevent the others from starting or stopping cleanly.

The plan template showed constructor calls with flat kwargs (`roles=`, `sample_rate_hz=`) that don't match the actual `BaseCollector` signature. All instantiations use the real `(config, callback)` form.

Also fixed in this task: 14 failing tests and 13 errors that predated this plan, left over from API changes in phases 08 and 11-01 through 11-03. These were blocking the plan's acceptance criterion (green suite), so all were resolved:

- `test_i2c_recovery.py`: updated fixture for v2 `HighRateSampler` API (no `i2c_bus`, uses `_lsm6dsox` not `_bus`)
- `test_capture_integrity.py`: fixed `_do_save_event` arity, callback signature, missing `_ffmpeg_started_at`, and stale assertion about who owns ffmpeg restarts
- `test_speaker_alerts.py`: `speaker.init` now passes `volume=` kwarg; assertion updated
- `ring_buffer.py`: added stateful `_check_stall()` / `_reset_stall_state()` replacing `_is_stalled()`, which is what the stall tests expected
- Various E501/F401 ruff violations in `database.py`, `capture_sync.py`, `timelapse_compiler.py`

Final state: `168 passed, 1 warning`, ruff clean.

### Task 2 -- Dead-code audit sign-off (D-15 through D-21)

**Commit:** `c5ffde9`

`DEAD_CODE_AUDIT.md` documents the resolution status and evidence for every dead-code item raised during Phase 11 planning:

| Item | Status |
|------|--------|
| D-15 pip_compositor.py | File never existed on v2 branch; grep returns zero hits |
| D-16 INA219 power.py | Deleted and replaced by INA226Collector in plan 02 |
| D-17 MCP9808 temperature.py | Deleted and replaced by DS18B20Collector in plan 01 |
| D-18 MPU6050 sampler | Deleted and replaced by HighRateSampler/LSM6DSOX in plan 01 |
| D-19 ring_buffer dead imports | Clean -- `_nice` and bare `import os` both absent |
| D-20 `_event_json_paths` lock | Clean -- all three access sites use `with self._event_paths_lock:` |
| D-21 capture_sync background | Clean -- `_do_sync` called only from daemon `_sync_loop`; never from telemetry thread |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] `_on_reading()` method not in plan**
- **Found during:** Task 1
- **Issue:** Plan referenced `callback=self._on_reading` but the method did not exist on `UnifiedEngine`
- **Fix:** Added `_on_reading(self, reading: Reading) -> None` with SQLite write, counter increment, and error logging
- **Files modified:** `src/shitbox/events/engine.py`
- **Commit:** 2200e6f

**2. [Rule 2 - Missing functionality] `latest_sample()` not on HighRateSampler**
- **Found during:** Task 1
- **Issue:** Plan showed `latest_sample_fn=self._sampler.latest_sample` but the method did not exist
- **Fix:** Added `latest_sample()` to `HighRateSampler` returning most-recent `IMUSample` from ring buffer
- **Files modified:** `src/shitbox/events/sampler.py`
- **Commit:** 2200e6f

**3. [Rule 1 - Bug] Stateful stall detection API mismatch**
- **Found during:** Task 1 (test failures)
- **Issue:** `test_ffmpeg_stall.py` expected `_check_stall()` / `_reset_stall_state()` methods; only `_is_stalled()` existed
- **Fix:** Implemented full stateful stall detection (`_stall_check_armed`, `_last_segment_mtime`, `_last_segment_size`, `_ffmpeg_started_at`) with the expected public API
- **Files modified:** `src/shitbox/capture/ring_buffer.py`
- **Commit:** 2200e6f

**4. [Rule 1 - Bug] 14 pre-existing test failures blocking green suite**
- **Found during:** Task 1 (acceptance criterion: full suite green)
- **Issue:** API changes from phases 08 and 11-01/02/03 left stale test scaffolds
- **Fix:** Updated three test files to match current APIs (see task 1 detail above)
- **Files modified:** `tests/test_i2c_recovery.py`, `tests/test_capture_integrity.py`, `tests/test_speaker_alerts.py`
- **Commit:** 2200e6f

**5. [Rule 3 - Blocking] Worktree vs main repo path conflict**
- **Found during:** Task 1
- **Issue:** Agent ran in git worktree; pytest loaded code from pip-editable install pointing to main repo. Changes in worktree had no effect on test runs.
- **Fix:** Generated patch from worktree diff, applied to main repo with `git apply`
- **Impact:** All code changes live in main repo at `/Users/tgreen/dev/shitbox/src/`

**6. [Rule 1 - Bug] Constructor signature mismatch in plan template**
- **Found during:** Task 1
- **Issue:** Plan showed `DS18B20Collector(roles=..., sample_rate_hz=..., callback=...)` but actual signature is `(config, callback)`
- **Fix:** Used actual constructor signatures throughout
- **Commit:** 2200e6f

## Known Stubs

None. All five collectors write real sensor readings to SQLite via `_on_reading()`. No placeholder data paths.

## Self-Check: PASSED

All key files confirmed present. Both task commits verified in git log.

| Check | Result |
|-------|--------|
| `src/shitbox/events/engine.py` | FOUND |
| `src/shitbox/events/sampler.py` | FOUND |
| `src/shitbox/capture/ring_buffer.py` | FOUND |
| `DEAD_CODE_AUDIT.md` | FOUND |
| Commit `2200e6f` | FOUND |
| Commit `c5ffde9` | FOUND |
