---
phase: 12-schema-foundation-and-logbook-api
plan: "03"
subsystem: sync
tags: [capture-sync, json-generator, registry, tdd, pytest, rsync]

requires:
  - 12-01 (Wave 0 test stubs — test_capture_sync_generators.py)
provides:
  - register_json_generator(name, fn) on CaptureSyncService
  - _run_json_generators() private method
  - _json_generators dict registry
  - Pass 1 rsync excludes *.json (covers all current and future generators)
affects:
  - 12-04 (engine wiring — registers notes/fuel generators here)
  - Any module that imports CaptureSyncService

tech-stack:
  added: []
  patterns:
    - "Registry pattern: dict[str, Callable[[], Any]] with per-entry try/except isolation"
    - "TDD: RED commit then GREEN commit, each tested against worktree PYTHONPATH"

key-files:
  created: []
  modified:
    - src/shitbox/sync/capture_sync.py
    - tests/test_capture_sync_generators.py

key-decisions:
  - "Pass 1 rsync uses --exclude=*.json rather than per-file excludes — covers all registered generators automatically"
  - "_run_json_generators() called as first line of _do_sync_inner() — generators always run before media and index rsyncs"
  - "Generator failures are caught per-entry; bad generator does not affect good generators or the rsync"

duration: ~4min
completed: 2026-04-09
---

# Phase 12 Plan 03: JSON Generator Registry on CaptureSyncService Summary

**CaptureSyncService extended with a register_json_generator registry that writes pre-rsync JSON artefacts with per-generator failure isolation, plus Pass 1 rsync updated to exclude all *.json files.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-09T12:19:30Z
- **Completed:** 2026-04-09T12:23:43Z
- **Tasks:** 1 (TDD: RED then GREEN)
- **Files modified:** 2

## Accomplishments

- `CaptureSyncService.__init__` gains `self._json_generators: dict[str, Callable[[], Any]] = {}`
- `register_json_generator(name, fn)` adds a callable to the registry; replaces on name collision
- `_run_json_generators()` iterates the registry, writes each to `{captures_dir}/{name}.json`, wraps each in `try/except` — a failing generator is logged and skipped, does not abort others or the rsync
- `_do_sync_inner()` calls `_run_json_generators()` as its first line, before the events.json/timelapse.json refresh block
- Pass 1 rsync `--exclude=events.json --exclude=timelapse.json` replaced with a single `--exclude=*.json` — covers all present and future generator outputs
- All 3 generator tests pass (0 skipped): register, run, and failure isolation

## Task Commits

1. **RED — failing tests** — `a8fa7dd` (test)
2. **GREEN — implementation** — `5ef3bec` (feat)

## Files Created/Modified

- `src/shitbox/sync/capture_sync.py` — imports extended (`json`, `Path`, `Any`, `Callable`), `_json_generators` dict, `register_json_generator`, `_run_json_generators`, `_do_sync_inner` call, Pass 1 `--exclude=*.json`
- `tests/test_capture_sync_generators.py` — stubs replaced with real assertions for register, run, and failure isolation

## Decisions Made

- Pass 1 rsync uses `--exclude=*.json` rather than per-file exclusions. This is strictly better: it covers the existing `events.json` and `timelapse.json` plus any generator the engine registers (notes, fuel, or future additions), with no maintenance cost.
- Generators run as the very first thing in `_do_sync_inner()`. This is the safest order: JSON files are on disk before either the media rsync or the index rsync touches the remote.

## Deviations from Plan

**[Rule 3 - Blocking] Cherry-picked plan 01 commits into worktree**

- **Found during:** Task setup
- **Issue:** This worktree was created from `main`, which does not contain the plan 01 commits (`a167035`, `c57d895`) that created the Wave 0 test stubs and schema v6 migration. The test file and updated `capture_sync.py` were not present.
- **Fix:** Cherry-picked `a167035` (Wave 0 stubs) and `c57d895` (schema v6) from `gsd/phase-12-schema-foundation-and-logbook-api` into the worktree branch. Then proceeded with plan 03 implementation.
- **Files modified:** `tests/test_capture_sync_generators.py`, `tests/test_logbook.py`, `src/shitbox/storage/database.py`, `tests/test_database.py`
- **Commits:** Cherry-pick of `a167035` → `a705e4b`, cherry-pick of `c57d895` → `8ecbf6e`

**[Rule 3 - Blocking] PYTHONPATH override required for worktree tests**

- **Found during:** GREEN verification
- **Issue:** The `shitbox` package is installed in development mode pointing to `/Users/tgreen/dev/shitbox/src/` (main repo). Tests run without PYTHONPATH override load the unmodified main-repo source, not the worktree source, causing `AttributeError: 'CaptureSyncService' object has no attribute 'register_json_generator'`.
- **Fix:** Ran all test verification with `PYTHONPATH=/Users/tgreen/dev/shitbox/.claude/worktrees/agent-aec3b5dc/src`.
- **No file changes required** — this is a worktree runtime concern, not a code issue.

## Known Stubs

None — plan 03 replaces all three Wave 0 stubs with real assertions.

---
*Phase: 12-schema-foundation-and-logbook-api*
*Completed: 2026-04-09*

## Self-Check: PASSED

- src/shitbox/sync/capture_sync.py: FOUND
- tests/test_capture_sync_generators.py: FOUND
- .planning/phases/12-schema-foundation-and-logbook-api/12-03-SUMMARY.md: FOUND
- Commit a8fa7dd (RED — failing tests): FOUND
- Commit 5ef3bec (GREEN — implementation): FOUND
