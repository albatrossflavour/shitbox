---
phase: 10-live-dashboard-with-offline-map
plan: 02
subsystem: dashboard/offline-map
tags: [tiles, mbtiles, cartodb, vendoring, tdd]
requires: []
provides:
  - tools.download_tiles module (lonlat_to_tile, build_corridor_tile_set, already_present, fetch_and_store)
  - python -m tools.download_tiles CLI
  - src/shitbox/dashboard/static/vendor/SHA256SUMS manifest contract for plan 10-04
affects:
  - tests/test_download_tiles.py (backfilled from plan 10-00)
tech-stack:
  added: []
  patterns:
    - "MBTiles SQLite schema (metadata, tiles, UNIQUE tile_index)"
    - "Idempotent tile fetch via already_present check + INSERT OR REPLACE"
    - "Polite CDN client: descriptive User-Agent + 150 ms rate limit"
key-files:
  created:
    - tools/__init__.py
    - tools/download_tiles.py
    - tests/test_download_tiles.py
    - src/shitbox/dashboard/static/vendor/.gitkeep
    - src/shitbox/dashboard/static/vendor/SHA256SUMS
  modified: []
decisions:
  - "Sydney z=10 assertion uses (942, 614) not (939, 614): the standard OSM slippy formula the plan specifies produces 942; the plan's cited value was arithmetically wrong."
  - "Plan 10-00 Task 3 (test stubs) had not landed yet, so 10-02 backfills tests/test_download_tiles.py directly — treated as Rule 3 blocking fix."
metrics:
  duration: ~6 min
  completed: 2026-04-09
---

# Phase 10 Plan 02: Offline Tile Downloader + Vendor Manifest Summary

One-liner: Corridor MBTiles builder for CartoDB dark tiles plus a SHA256 manifest contract for the frontend vendor assets.

## What Landed

- `tools/download_tiles.py`: pure-stdlib + `requests` + `pyyaml` tile pre-fetcher. Samples the configured rally waypoints every ~1 km, expands a ±20 km envelope, computes the XYZ tile set across `--zoom-min..--zoom-max`, and writes each fetched tile into an MBTiles SQLite file in TMS y orientation. Rate-limited at 150 ms per request, descriptive User-Agent, idempotent on re-run via `already_present()`.
- `tools/__init__.py`: makes `tools` an importable package so the tests can `import tools.download_tiles`.
- `tests/test_download_tiles.py`: 5 tests — lonlat maths, corridor envelope, idempotency, User-Agent, rate limit. All GREEN.
- `src/shitbox/dashboard/static/vendor/SHA256SUMS`: 4 PENDING-WAVE3 placeholder entries (alpine.min.js, leaflet.js, leaflet.css, tailwind.min.css). Plan 10-04's executor is contractually obliged to replace each placeholder with the real `sha256sum` output of the vendored binary it ships.

## Commits

- `273ee0f` test(10-02): add failing tests for tools.download_tiles (RED)
- `6ee457f` feat(10-02): implement tools.download_tiles corridor MBTiles builder (GREEN)
- `f1c04e2` chore(10-02): scaffold vendor SHA256SUMS manifest

## Deviations from Plan

### Rule 3 — Blocking

**Backfilled tests/test_download_tiles.py**. Plan 10-02 listed the test file under `@-context` as if it already existed, but plan 10-00 Task 3 had not run — only the `mbtiles_fixture` had landed (commit `f354a47`). Without the test file there was no RED phase to drive this TDD task, so 10-02 created it using the exact stubs plan 10-00 specified, with one correction (below).

### Rule 1 — Bug

**Test assertion for Sydney z=10 tile coordinates**. Both plans 10-00 and 10-02 assert `lonlat_to_tile(151.2093, -33.8688, 10) == (939, 614)`, and plan 10-02 even flags this as "double-check your formula if you get a different number". Running the standard OSM slippy formula the plan itself specifies:

```
(151.2093 + 180) / 360 * 2^10 = 942.106 -> int() -> 942
```

The formula is correct (matches OSM wiki) and 942 is the right tile. The plan's cited `939` is arithmetically wrong. Adjusted the test to assert `(942, 614)`. Implementation uses the plan-specified formula unchanged. Future plans referencing this coordinate should use 942.

## Verification

- `pytest tests/test_download_tiles.py` — 5 passed
- `ruff check tools/download_tiles.py` — clean
- `python -m tools.download_tiles --help` — runs, prints argparse help
- `grep -c PENDING-WAVE3 src/shitbox/dashboard/static/vendor/SHA256SUMS` — 4

## Self-Check: PASSED

- Files exist: tools/__init__.py, tools/download_tiles.py, tests/test_download_tiles.py, vendor/.gitkeep, vendor/SHA256SUMS
- Commits exist: 273ee0f, 6ee457f, f1c04e2
