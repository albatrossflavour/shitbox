---
phase: 01-boot-recovery
plan: "01"
subsystem: storage/sync
tags: [boot-recovery, sqlite, crash-detection, orphan-closure, tdd]
dependency_graph:
  requires: []
  provides: [BootRecoveryService, detect_unclean_shutdown, close_orphaned_events, synchronous=FULL]
  affects: [src/shitbox/events/engine.py]
tech_stack:
  added: []
  patterns: [daemon-thread service, WAL crash detection, orphan file repair]
key_files:
  created:
    - src/shitbox/sync/boot_recovery.py
    - tests/conftest.py
    - tests/test_database.py
    - tests/test_boot_recovery.py
  modified:
    - src/shitbox/storage/database.py
    - src/shitbox/events/storage.py
key_decisions:
  - "WAL file detection must occur before database.connect() to avoid false negatives"
  - "orphan end_time uses file st_mtime as a best-effort crash timestamp"
  - "BootRecoveryService.start() returns immediately; callers block on recovery_complete if needed"
metrics:
  duration_minutes: 2
  tasks_completed: 2
  files_changed: 6
  completed_date: "2026-02-25"
requirements_covered: [BOOT-01, BOOT-02, BOOT-03]
---

# Phase 1 Plan 01: Boot Recovery Building Blocks Summary

**One-liner:** WAL-based crash detection, PRAGMA synchronous=FULL, and orphaned-event closure
implemented with 7 passing unit tests and no new dependencies.

## What Was Built

### Task 1 — Test scaffolding and synchronous=FULL (commit 0b9b1b4)

- `tests/conftest.py`: shared fixtures (`tmp_db_path`, `db`, `event_storage_dir`,
  `event_storage`) used by all boot-recovery tests.
- `tests/test_database.py`: `test_synchronous_full` confirms `PRAGMA synchronous` returns
  `2` (FULL) on every new connection.
- `tests/test_boot_recovery.py`: all six BOOT-01/BOOT-02 test stubs.
- `src/shitbox/storage/database.py` line 116: `synchronous=NORMAL` changed to
  `synchronous=FULL`. This is the single most critical durability change — every committed
  WAL write is now flushed to physical storage before SQLite acknowledges the commit.

### Task 2 — BootRecoveryService and close_orphaned_events() (commit b208a7d)

- `src/shitbox/sync/boot_recovery.py`:
  - `detect_unclean_shutdown(db_path)` — checks for `<db>-wal` before `connect()`.
  - `BootRecoveryService` — daemon thread with `start()` / `_run()` / `_detect_and_recover()` /
    `_run_integrity_check()`. Sets `recovery_complete` threading.Event on finish, even on error.
- `src/shitbox/events/storage.py` — `close_orphaned_events()` method: iterates all `.json`
  files, skips `events.json`, marks files missing `end_time` or with `status=open` as
  `interrupted` using `st_mtime` as best-effort end timestamp.

## Verification

```
pytest tests/ -x -q      → 7 passed in 0.02s
ruff check src/…          → All checks passed
grep synchronous=FULL     → line 116 confirmed
grep close_orphaned_events → line 233 confirmed
```

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

1. WAL detection must precede `database.connect()` — the plan calls this out explicitly and the
   implementation enforces it via docstring and module-level placement.
2. `end_time` uses `st_mtime` (float) matching the existing `start_time` float convention in
   the event metadata schema.
3. `BootRecoveryService` does not take a `Connection` at init — it calls `db._get_connection()`
   lazily so it works correctly with the thread-local connection model.

## Self-Check: PASSED

All files confirmed on disk. Both task commits (0b9b1b4, b208a7d) confirmed in git log.
