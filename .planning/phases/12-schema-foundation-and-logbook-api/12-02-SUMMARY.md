---
phase: 12
plan: 02
subsystem: storage, dashboard-api
tags: [logbook, notes, fuel, gps-staleness, fastapi, sqlite]
requires: [12-01]
provides: [LogbookStorage, gps_state, logbook-router, build_app-logbook-wiring]
affects: [dashboard/server.py, storage/logbook.py, dashboard/logbook.py]
tech-stack:
  added: [pydantic-models-for-logbook, fastapi-logbook-router]
  patterns: [gil-atomic-module-state, snapshot-fn-injection-for-testability, explicit-select-for-cost-exclusion]
key-files:
  created:
    - src/shitbox/storage/logbook.py
    - src/shitbox/dashboard/gps_state.py
    - src/shitbox/dashboard/logbook.py
  modified:
    - src/shitbox/dashboard/server.py
    - tests/test_logbook.py
    - pyproject.toml
decisions:
  - "snapshot_fn injected into LogbookStorage for testability — avoids hardware dependency in tests"
  - "gps_state uses GIL-atomic module rebind (same pattern as snapshot.py) — no locks needed"
  - "generate_fuel_json enforces cost_aud exclusion via explicit SELECT column list, not post-processing"
  - "build_app logbook_storage kwarg defaults to None — zero impact on existing callers"
  - "pytest pythonpath=['src'] added to pyproject.toml to let worktree tests find local source"
metrics:
  duration_minutes: 3
  completed_date: "2026-04-09"
  tasks_completed: 2
  files_changed: 6
---

# Phase 12 Plan 02: Logbook Storage and API Summary

LogbookStorage class, gps_state helper, and FastAPI logbook router — all wired into build_app with
GPS staleness fallback and cost_aud strictly excluded from sync outputs.

## What Was Built

### LogbookStorage (`src/shitbox/storage/logbook.py`)

The core persistence class. Takes an injected `snapshot_fn` so tests can pass a lambda without
touching hardware. GPS resolution works in two tiers: live snapshot when `gps_fix_mode > 0`, then
last-known position from `gps_state`, then `(None, None, stale=True)` when no position is available
at all.

Key method decisions:

- `create_note` and `create_fuel_stop` both call `_resolve_gps()` at insert time, not before
- `list_fuel_stops` computes efficiency at query time — no stored derived values
- `generate_fuel_json` uses an explicit `SELECT` column list that omits `cost_aud` at the SQL
  level, making it structurally impossible for cost data to appear in output (D-10 enforcement)

### gps_state (`src/shitbox/dashboard/gps_state.py`)

Module-level tuple with a GIL-atomic rebind. Same pattern as `snapshot.py`. The GPS collector will
call `update_last_known_position` whenever it gets a valid fix; the logbook calls
`get_last_known_position` when the snapshot has no active fix. `clear_last_known_position` is a
test helper only.

### Logbook Router (`src/shitbox/dashboard/logbook.py`)

FastAPI router with four endpoints:

- `POST /api/notes` (201) — body required, event_id optional
- `POST /api/fuel` (201) — volume_litres required, cost_aud and odometer_km optional
- `GET /api/fuel` — returns stops list with per-stop and cumulative efficiency
- `GET /api/logbook/gps` — returns staleness state for the UI modal pre-flight check

Module-level `_storage` set by `set_storage()`. Returns 503 if storage is not configured, 422 on
invalid input (Pydantic default).

### Server wiring (`src/shitbox/dashboard/server.py`)

`build_app()` and `build_dashboard_server()` both accept `logbook_storage=None`. The router is only
included when storage is provided, so existing callers with no logbook argument see exactly the same
behaviour as before.

## Test Coverage

11 tests total, 0 skipped:

- 7 storage-layer tests: note creation, GPS staleness fallback, event pinning, fuel stop creation,
  efficiency calculation, no-odometer edge case, cost_aud exclusion from JSON
- 4 HTTP tests: 201 on valid note, 422 on missing body, fuel create + list with efficiency,
  GPS status endpoint with stale position

All 30 tests in the `test_logbook`, `test_dashboard`, and `test_database` suites pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] pytest pythonpath not configured for worktree**

- **Found during:** Task 1 GREEN phase
- **Issue:** pytest picked up the editable-installed shitbox from the main repo rather than the
  worktree's `src/` directory, causing import failures for newly created modules
- **Fix:** Added `[tool.pytest.ini_options] pythonpath = ["src"]` to the worktree's `pyproject.toml`
- **Files modified:** `pyproject.toml`
- **Commit:** 26a9013

## Known Stubs

None. All methods are fully implemented and all tests exercise real database operations.

## Self-Check: PASSED
