---
phase: 12-schema-foundation-and-logbook-api
plan: "01"
subsystem: database
tags: [sqlite, schema-migration, logbook, notes, fuel-stops, pytest, tdd]

requires: []
provides:
  - SCHEMA_VERSION=6 in database.py
  - notes table (id, timestamp_utc, body, event_id, lat, lng, gps_stale, created_at)
  - fuel_stops table (id, timestamp_utc, volume_litres, cost_aud, lat, lng, gps_stale, odometer_km, created_at)
  - _migrate_to_v6() migration method
  - Wave 0 test scaffolds (test_logbook.py, test_capture_sync_generators.py, test_v6_* in test_database.py)
affects:
  - 12-02 (logbook API — targets notes and fuel_stops tables)
  - 12-03 (capture sync generators — stubs in test_capture_sync_generators.py)
  - Any plan that instantiates Database and calls connect()

tech-stack:
  added: []
  patterns:
    - "Migration pattern: sequential if current_version < N branches (no elif), each calling _migrate_to_vN"
    - "Wave 0 stubs: pytest.skip with reason string, replaced by real assertions in the task that implements the feature"

key-files:
  created:
    - tests/test_logbook.py
    - tests/test_capture_sync_generators.py
  modified:
    - src/shitbox/storage/database.py
    - tests/test_database.py

key-decisions:
  - "notes and fuel_stops go into telemetry.db via _migrate_to_v6 — no separate database"
  - "cost_aud column is nullable — never appears in sync payloads or website (enforced at API layer in plan 12-02)"
  - "No indexes added on new tables in this plan — can follow in a later phase if query patterns demand it"

patterns-established:
  - "Migration pattern: sequential if current_version < N branches in connect(), each calling a dedicated method"
  - "Wave 0 test scaffold: stub files with pytest.skip created before implementation, replaced with real assertions in the same plan that adds the feature"

requirements-completed: [NOTE-01, NOTE-02, FUEL-01, FUEL-02]

duration: 2min
completed: 2026-04-09
---

# Phase 12 Plan 01: Schema v6 Foundation and Wave 0 Test Scaffolds Summary

**SQLite schema bumped to v6 with notes and fuel_stops tables via sequential migration, plus three Wave 0 test files seeded as skippable stubs for all subsequent plans in Phase 12.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-09T12:16:57Z
- **Completed:** 2026-04-09T12:18:41Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Schema migrated from v5 to v6 with `notes` and `fuel_stops` tables, both idempotently created via `CREATE TABLE IF NOT EXISTS`
- Migration runs on fresh databases and on any existing v5 database without data loss
- Wave 0 stubs created: `test_logbook.py` (7 stubs), `test_capture_sync_generators.py` (3 stubs), plus `test_v6_fresh_schema` and `test_v6_migration` in `test_database.py` (now real passing tests)
- All 15 tests pass or skip cleanly (`pytest` exits 0 with 5 passed, 10 skipped)

## Task Commits

1. **Task 1: Create Wave 0 test stubs** - `a167035` (test)
2. **Task 2: Schema v6 migration — notes and fuel_stops tables** - `c57d895` (feat)

## Files Created/Modified

- `src/shitbox/storage/database.py` - SCHEMA_VERSION=6, two new tables in SCHEMA_SQL, `_migrate_to_v6()` method, migration branch in `connect()`
- `tests/test_database.py` - appended `test_v6_fresh_schema` and `test_v6_migration` (both passing)
- `tests/test_logbook.py` - created with 7 skippable stubs for plan 12-02
- `tests/test_capture_sync_generators.py` - created with 3 skippable stubs for plan 12-03

## Decisions Made

- `cost_aud` stored in `fuel_stops` but kept nullable and excluded from sync payloads at the API layer (plan 12-02). The column is there for local record-keeping only.
- No indexes on the new tables in this plan. The write path for notes/fuel is low-frequency; indexes can be added if query patterns in later plans warrant it.
- Wave 0 stubs use `pytest.skip` with explicit reason strings so any future agent can grep for "pending plan 12-0X" to find what still needs wiring.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `database.py` is at v6; plan 12-02 can immediately target `notes` and `fuel_stops` without any schema work
- Wave 0 stub files are in place; plan 12-02 replaces the logbook stubs, plan 12-03 replaces the generator stubs
- All existing tests continue to pass — no regressions

---
*Phase: 12-schema-foundation-and-logbook-api*
*Completed: 2026-04-09*

## Self-Check: PASSED

- tests/test_logbook.py: FOUND
- tests/test_capture_sync_generators.py: FOUND
- src/shitbox/storage/database.py: FOUND
- .planning/phases/12-schema-foundation-and-logbook-api/12-01-SUMMARY.md: FOUND
- Commit a167035 (Wave 0 stubs): FOUND
- Commit c57d895 (schema v6): FOUND
