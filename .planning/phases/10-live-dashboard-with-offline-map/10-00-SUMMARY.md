---
phase: 10-live-dashboard-with-offline-map
plan: 00
subsystem: testing
tags: [pytest, mbtiles, sse, fastapi, red-phase, tdd]

requires:
  - phase: 10-live-dashboard-with-offline-map
    provides: CONTEXT.md, RESEARCH.md, VALIDATION.md (test contracts)
provides:
  - mbtiles_fixture pytest fixture building a real on-disk MBTiles file
  - _KNOWN_PNG constant (1x1 transparent PNG) for tile body assertions
  - 13 failing test stubs for the dashboard surface (snapshot, server, SSE, tiles)
  - 5 failing test stubs for tools.download_tiles (Wave 1 tile downloader)
affects: [10-01, 10-02, 10-03, 10-04, 10-05]

tech-stack:
  added: []
  patterns:
    - "RED-phase-first: every Wave 1+ implementation has a pre-existing automated check"
    - "MBTiles fixture uses real tmp path so immutable=1 URIs work"

key-files:
  created:
    - tests/test_dashboard.py
  modified:
    - tests/conftest.py
    - tests/test_download_tiles.py

key-decisions:
  - "mbtiles_fixture uses tmp_path_factory.mktemp so the file is real on disk (immutable URI needs a real path)"
  - "No pytest.importorskip — we want hard ImportError so RED is unambiguous"
  - "_KNOWN_PNG kept at module level so tests can import it directly"

patterns-established:
  - "Pattern: Wave 0 seeds failing tests for every later wave so TDD cycle is enforced"

requirements-completed: [D-01, D-02, D-03, D-04, D-07, D-08, D-09, D-15, D-16, D-19]

duration: ~8min
completed: 2026-04-09
---

# Phase 10 Plan 00: Wave 0 RED Tests Summary

**Failing test scaffolds for the dashboard surface and tile downloader, covering snapshot, SSE streams, MBTiles y-flip, and corridor maths — every Wave 1+ implementation task now has a pre-existing automated check.**

## Performance

- **Duration:** ~8 min
- **Tasks:** 3
- **Files modified:** 3 (conftest.py, test_dashboard.py, test_download_tiles.py)

## Accomplishments

- MBTiles fixture builds a real on-disk 1-tile MBTiles SQLite file with a known PNG, ready for immutable=1 URI connections
- 13 failing dashboard tests (ImportError / NotImplementedError) wired to `shitbox.dashboard.*`
- 5 failing tile-downloader tests wired to `tools.download_tiles`
- Every Phase 10 requirement from D-01..D-19 covered by at least one RED test

## Task Commits

1. **Task 1: mbtiles_fixture + _KNOWN_PNG** — `f354a47` (test)
2. **Task 2: tests/test_dashboard.py RED stubs** — `f4aaccc` (test)
3. **Task 3: tests/test_download_tiles.py RED stubs** — `273ee0f` (test — committed ahead of 10-00 during 10-02 scaffolding; file content matches this plan's contract)

## Files Created/Modified

- `tests/conftest.py` — Added `_KNOWN_PNG` constant and `mbtiles_fixture`
- `tests/test_dashboard.py` — 13 RED stubs covering snapshot, server lifecycle, SSE fast/slow/events, tiles Y-flip, 404, immutable URI, uvicorn signal handler override
- `tests/test_download_tiles.py` — 5 RED stubs covering lon/lat→tile, corridor envelope, idempotency, User-Agent, rate-limit

## Decisions Made

- Followed plan as specified. The `test_lonlat_to_tile_known_values` assertion for Sydney at z=10 was corrected to (942, 614) when `tools.download_tiles` was drafted in 10-02; the plan's (939, 614) disagreed with the standard slippy map formula. Recorded in-file as a comment.

## Deviations from Plan

None of substance. Task 3's test file was already on disk from an earlier out-of-order 10-02 scaffolding commit (`273ee0f`), with content equivalent to this plan's contract. No duplicate commit created.

## Issues Encountered

- Pre-existing unrelated test failures in `tests/test_ffmpeg_stall.py` and `tests/test_speaker_alerts.py` (Phase 7/8 leftovers). Out of scope for this plan — not touched.
- `test_snapshot_atomicity` and `test_snapshot_default_keys` actually pass because Plan 10-01 already committed `shitbox.dashboard.snapshot` ahead of Wave 0 (commits `913f647`, `5cb9e59`). The remaining 16 tests are RED as required.

## Self-Check: PASSED

- tests/conftest.py: FOUND (mbtiles_fixture, _KNOWN_PNG present)
- tests/test_dashboard.py: FOUND (13 test functions)
- tests/test_download_tiles.py: FOUND (5 test functions)
- Commit f354a47: FOUND
- Commit f4aaccc: FOUND
- Commit 273ee0f: FOUND

## Next Phase Readiness

- Wave 1 implementation plans (10-01, 10-02, 10-03) now have failing tests to drive TDD
- Ruff clean on all touched test files
- No blockers

---
*Phase: 10-live-dashboard-with-offline-map*
*Completed: 2026-04-09*
