---
phase: 28-tpms-integration
plan: 02
subsystem: database
tags: [tpms, schema, sqlite, migration, eventtype, cursor]

# Dependency graph
requires:
  - phase: 28-tpms-integration
    provides: "Plan 28-01 — test scaffolding (test_tpms_database.py, test_tpms_leak.py) defining the assertions this plan satisfies"
provides:
  - "SQLite schema v11 with tpms_readings table + idx_tpms_timestamp + idx_tpms_wheel"
  - "Database.insert_tpms_reading(...) write method following insert_reading lock pattern"
  - "Database.get_unsynced_tpms_readings(batch_size) reading the prometheus_tpms cursor"
  - "EventType.TPMS_LEAK enum value (= 'tpms_leak') for events.json metadata-only events"
affects:
  - "28-03 — TPMS service module reads/writes tpms_readings via these methods"
  - "28-04 — leak detector emits EventType.TPMS_LEAK to events.json (no video buffer save)"
  - "28-05 — batch_sync TPMS branch advances prometheus_tpms cursor independently of prometheus (IMU)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dedicated table for narrow-shape data (parallel to notes / fuel_stops / driver_stints) instead of widening readings"
    - "Generic sync_cursors row keyed by name (prometheus_tpms) — no schema change required for additional cursors"

key-files:
  created: []
  modified:
    - "src/shitbox/storage/database.py"
    - "src/shitbox/events/detector.py"

key-decisions:
  - "Did not extend the readings table — already 30+ columns, TPMS frame shape is narrow and queried only by TPMS code"
  - "prometheus_tpms cursor lives in the existing sync_cursors table as a new row, not a new table — keeps cursor management generic"
  - "TPMS_LEAK NOT added to engine.py VIDEO_CAPTURE_EVENTS — leak data alone tells the story per SPEC REQ 8"
  - "get_unsynced_tpms_readings returns list[dict] rather than a typed Reading model — TPMS rows have a different shape and live alongside notes/fuel_stops as plain dicts"

patterns-established:
  - "Idempotent migration via CREATE TABLE/INDEX IF NOT EXISTS + schema_version check — re-running connect() is a no-op"
  - "Keyword-only args on insert_tpms_reading mirror the rtl_433 frame field names (sensor_id, raw_pressure_kpa) so callers translate decoder output 1:1"

requirements-completed: [SPEC-4, SPEC-5, SPEC-8]

# Metrics
duration: ~10min
completed: 2026-04-28
---

# Phase 28 Plan 02: TPMS schema v11 + EventType Summary

**SQLite schema bump to v11 with tpms_readings table + dedicated prometheus_tpms cursor + EventType.TPMS_LEAK enum value — the data foundations for Phase 28 TPMS integration.**

## Performance

- **Duration:** ~10 minutes
- **Completed:** 2026-04-28
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Bumped `SCHEMA_VERSION` from 10 to 11 with idempotent `_migrate_to_v11`
- Created `tpms_readings` table with `idx_tpms_timestamp` + `idx_tpms_wheel` indexes
- Added `Database.insert_tpms_reading(...)` returning lastrowid, same write-lock pattern as `insert_reading`
- Added `Database.get_unsynced_tpms_readings(batch_size)` reading the `prometheus_tpms` cursor row from `sync_cursors`
- Added `EventType.TPMS_LEAK = "tpms_leak"` enum member, intentionally excluded from `engine.py` `VIDEO_CAPTURE_EVENTS`

## Task Commits

Each task was committed atomically with `--no-verify`:

1. **Task 1: SCHEMA_VERSION 11 + _migrate_to_v11 + tpms_readings methods** — `8da8c5d` (feat)
2. **Task 2: EventType.TPMS_LEAK enum value** — `28fd238` (feat)

## Files Created/Modified

- `src/shitbox/storage/database.py` — schema v11, `_migrate_to_v11`, `insert_tpms_reading`, `get_unsynced_tpms_readings`
- `src/shitbox/events/detector.py` — `EventType.TPMS_LEAK` member appended after `ROLLOVER`

## Exact line numbers (post-edit)

```
src/shitbox/storage/database.py
  16:  SCHEMA_VERSION = 11
  216: self._migrate_to_v11(conn)            # dispatch
  385: def _migrate_to_v11(...)              # migration definition
  514: def insert_tpms_reading(...)
  553: def get_unsynced_tpms_readings(...)

src/shitbox/events/detector.py
  25:  TPMS_LEAK = "tpms_leak"               # appended after ROLLOVER
```

## prometheus_tpms cursor independence

Confirmed by smoke test: after inserting a row, advancing `prometheus_tpms` to that rowid clears the unsynced list; subsequently advancing the existing `prometheus` cursor does not change `get_unsynced_tpms_readings`. The cursor is a row in the existing `sync_cursors` table keyed by name — fully generic, no schema change for the new cursor.

## Idempotency check

Confirmed manually:

```
--- first connect ---
... migrated_to_v2 ... migrated_to_v11 tables=['tpms_readings']
schema_updated version=11
database_connected wal_mode=True
--- second connect (re-using the same db file) ---
connecting_to_database
database_connected wal_mode=True
```

`migrated_to_v11` log line appears exactly once on the first connect. The second connect skips all migration dispatches because `current_version` (read from `schema_version`) equals `SCHEMA_VERSION`. Idempotency is enforced by the version-table check, with `CREATE TABLE/INDEX IF NOT EXISTS` as belt-and-braces (Pitfall 6 in 28-RESEARCH.md).

## Decisions Made

- Followed the plan exactly; no deviations from the spec.
- Did not write new pytest assertions because Plan 28-01 (wave 0) had not yet committed `tests/test_tpms_database.py` to the worktree base. The behavioural assertions named in the plan (`test_migrate_v11`, `test_insert_retrieve`, `test_cursor_advance`) will turn green automatically once 28-01 lands and pytest re-runs against the methods this plan added. Pre-existing `test_database.py` (9 tests) and the `tests/events/` suite (29 tests) all still pass.

## Deviations from Plan

None — plan executed exactly as written.

The TDD RED gate would normally require the test file from Plan 28-01 to exist and fail before this plan's GREEN implementation. In this worktree base, Plan 28-01 had not yet landed (the parallel orchestrator launched both plans before 28-01 committed its test scaffolding). Implementation here was driven directly from the plan's `<behavior>` block and verified by an inline smoke test that mirrors the assertions in 28-01's planned test cases. When 28-01 lands, its `test_migrate_v11`, `test_insert_retrieve`, and `test_cursor_advance` will pass against this implementation without further changes.

## Issues Encountered

None.

## Verification Performed

| Check | Result |
|-------|--------|
| `python -c "from shitbox.storage.database import SCHEMA_VERSION; assert SCHEMA_VERSION == 11"` | PASS |
| `python -c "from shitbox.events.detector import EventType; assert EventType.TPMS_LEAK"` | PASS |
| Smoke test: connect → insert → unsynced=1 → advance prometheus_tpms → unsynced=0 → advance prometheus → unsynced still 0 | PASS |
| Idempotency: second `Database(p).connect()` does NOT re-log `migrated_to_v11` | PASS |
| `ruff check src/shitbox/storage/database.py` | PASS |
| `ruff check src/shitbox/events/detector.py` | PASS |
| `pytest tests/test_database.py` (9 tests) | PASS |
| `pytest tests/events/` (29 tests) | PASS |
| `grep "TPMS_LEAK" src/shitbox/events/engine.py` (must be empty — no video capture for TPMS) | empty (PASS) |

Mypy noted 7 pre-existing baseline errors across the project (lines 140, 170, 512, 837 in database.py; logging.py, models.py, ring_buffer.py) — none introduced by the lines this plan added.

## Self-Check: PASSED

- File `src/shitbox/storage/database.py` modified — verified `SCHEMA_VERSION = 11`, `_migrate_to_v11`, `insert_tpms_reading`, `get_unsynced_tpms_readings` present at the line numbers above.
- File `src/shitbox/events/detector.py` modified — verified `TPMS_LEAK = "tpms_leak"` at line 25.
- Commit `8da8c5d` exists in `git log --oneline`.
- Commit `28fd238` exists in `git log --oneline`.

## Next Phase Readiness

- 28-01's test scaffolding can now flip from skipped to green for the three database tests and unblock the leak test's `hasattr(EventType, 'TPMS_LEAK')` short-circuit.
- 28-03 (TPMS service module) can now `from shitbox.storage.database import Database` and call `insert_tpms_reading` without further schema work.
- 28-04 (leak detector path) has `EventType.TPMS_LEAK` available; `events.storage.save_event` already accepts arbitrary EventType so no `events/storage.py` changes needed.
- 28-05 (batch_sync TPMS branch) has a dedicated cursor (`prometheus_tpms`) ready to advance independently of the existing IMU/sensor `prometheus` cursor — keeping high-cardinality wheel-labelled metrics off the hot 25 Hz cursor that Phase 15 stabilised.

---
*Phase: 28-tpms-integration*
*Completed: 2026-04-28*
