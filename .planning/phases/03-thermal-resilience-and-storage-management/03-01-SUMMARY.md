---
phase: 03-thermal-resilience-and-storage-management
plan: "01"
subsystem: thermal-buzzer-wal-scaffold
tags: [thermal, buzzer, wal, database, test-scaffold, health-package]
dependency_graph:
  requires: []
  provides:
    - shitbox.health package (empty init for Plan 02)
    - beep_thermal_warning, beep_thermal_critical, beep_under_voltage, beep_thermal_recovered
    - Database.checkpoint_wal()
    - tests/test_thermal_monitor.py scaffold (THRM-01/02/03)
    - tests/test_buzzer_alerts.py thermal pattern tests
    - tests/test_database.py WAL checkpoint tests
  affects:
    - src/shitbox/capture/buzzer.py (4 new functions)
    - src/shitbox/storage/database.py (1 new method)
tech_stack:
  added: []
  patterns:
    - Thermal alerts at 500 Hz to distinguish from 330 Hz service-failure alerts
    - beep_thermal_recovered resets escalation state rather than escalating
    - checkpoint_wal logs conditionally (only when row[2] > 0)
key_files:
  created:
    - src/shitbox/health/__init__.py
    - tests/test_thermal_monitor.py
  modified:
    - src/shitbox/capture/buzzer.py
    - src/shitbox/storage/database.py
    - tests/test_buzzer_alerts.py
    - tests/test_database.py
decisions:
  - "Thermal alerts use 500 Hz to distinguish from 330 Hz service-failure alerts (per RESEARCH.md)"
  - "beep_thermal_recovered calls _alert_state.reset() before playing, no escalation check needed"
  - "checkpoint_wal is silent when WAL is clean (row[2] == 0) to avoid log noise in steady state"
  - "test_thermal_monitor.py scaffold fails with ImportError until Plan 02 — this is expected"
metrics:
  duration: "~2 min"
  completed: "2026-02-26"
  tasks_completed: 2
  files_changed: 6
---

# Phase 03 Plan 01: Test Scaffolds, Thermal Buzzer Functions, and WAL Checkpoint Summary

**One-liner:** Health package created, four 500 Hz thermal buzzer alert functions added to buzzer.py,
Database.checkpoint_wal() added with conditional logging, and test scaffolds written for all Phase 3
requirements.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add thermal buzzer functions, WAL checkpoint, and health package | 60e5ac9 | src/shitbox/health/__init__.py, src/shitbox/capture/buzzer.py, src/shitbox/storage/database.py |
| 2 | Create test scaffolds for all Phase 3 requirements | 5729907 | tests/test_thermal_monitor.py, tests/test_buzzer_alerts.py, tests/test_database.py |

## What Was Built

### Health Package

`src/shitbox/health/__init__.py` created as an empty package init with docstring
`"Health monitoring services."`. This makes `import shitbox.health` work and allows
Plan 02 to place `thermal_monitor.py` inside it.

### Thermal Buzzer Functions

Four new functions added to `src/shitbox/capture/buzzer.py` in a dedicated section
following the existing `# Failure alert functions` section:

- `beep_thermal_warning()`: `[(500, 400), (500, 400)]` — two medium tones at 70C warning
- `beep_thermal_critical()`: `[(500, 600), (500, 600), (500, 600)]` — three long tones at 80C critical
- `beep_under_voltage()`: `[(500, 150), (500, 150), (500, 150), (500, 150)]` — four rapid tones
- `beep_thermal_recovered()`: `[(880, 150), (500, 150)]` — descending pair, resets warning escalation state

All four use 500 Hz to be aurally distinct from the 330 Hz service-failure alerts.
The recovery function calls `_alert_state.reset("buzzer-thermal-warning")` instead of
checking escalation, so the next warning starts fresh.

### WAL Checkpoint Method

`Database.checkpoint_wal()` added after the existing `checkpoint()` method:

- Uses `self._get_connection()` for thread-local connection
- Acquires `self._write_lock` for the PRAGMA call
- Executes `PRAGMA wal_checkpoint(TRUNCATE)`
- Fetches `(busy, log, checkpointed)` from result row
- Logs `wal_checkpoint_completed` only when `row[2] > 0` (pages were actually checkpointed)
- Silent when WAL was already clean to avoid noise in telemetry logs

### Test Scaffolds

- `tests/test_thermal_monitor.py`: 9 tests for THRM-01/02/03 — fails with ImportError until
  Plan 02 creates `shitbox.health.thermal_monitor`. Expected and correct.
- `tests/test_buzzer_alerts.py`: 4 new thermal pattern tests added — all pass now.
- `tests/test_database.py`: 2 new WAL checkpoint tests added — both pass now.

## Verification Results

```
pytest tests/test_buzzer_alerts.py -x -q   → 13 passed
pytest tests/test_database.py -x -q        → 3 passed
python -c "from shitbox.capture.buzzer import beep_thermal_warning"  → OK
python -c "from shitbox.storage.database import Database; assert hasattr(Database, 'checkpoint_wal')"  → OK
python -c "import shitbox.health"  → OK
ruff check src/shitbox/capture/buzzer.py src/shitbox/storage/database.py src/shitbox/health/__init__.py  → All checks passed
```

## Decisions Made

1. **500 Hz thermal alerts**: Thermal alerts use 500 Hz per RESEARCH.md to distinguish them
   from 330 Hz service-failure alerts (beep_service_crash, beep_i2c_lockup, etc.) and
   from 880/440 Hz capture/boot tones.

2. **Recovery resets escalation state**: `beep_thermal_recovered` calls
   `_alert_state.reset("buzzer-thermal-warning")` rather than checking
   `should_escalate()`, so the first warning after recovery always plays as a
   fresh (non-escalated) alert.

3. **Conditional WAL checkpoint logging**: `checkpoint_wal()` only logs when `row[2] > 0`
   (pages were actually checkpointed). When the WAL is already clean the method is silent,
   avoiding noise in the telemetry logs during normal operation.

4. **Scaffold fail is correct**: `test_thermal_monitor.py` is expected to fail with
   ImportError until Plan 02 implements `ThermalMonitorService`. This is correct
   test-first behaviour — the scaffold defines the contract Plan 02 must satisfy.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/shitbox/health/__init__.py | FOUND |
| tests/test_thermal_monitor.py | FOUND |
| 03-01-SUMMARY.md | FOUND |
| Commit 60e5ac9 (task 1) | FOUND |
| Commit 5729907 (task 2) | FOUND |
