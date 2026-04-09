---
phase: 10-live-dashboard-with-offline-map
plan: 04
subsystem: dashboard/wiring+frontend
tags: [dashboard, frontend, alpine, tailwind, leaflet, engine, sse, wave3]
requires:
  - shitbox.dashboard.server.DashboardServer (10-03)
  - shitbox.dashboard.sse.push_event (10-03)
  - shitbox.dashboard.snapshot.update_snapshot (10-01)
  - SHA256SUMS scaffold (10-02)
provides:
  - src/shitbox/dashboard/static/index.html — single-file Alpine+Tailwind+Leaflet dashboard
  - Vendored frontend assets (alpine 3.14.1, leaflet 1.9.4, tailwind 2.2.19) with real SHA256SUMS
  - UnifiedEngine.dashboard lifecycle (__init__ guard, start/stop)
  - 10 Hz snapshot decimation from engine._on_imu_sample
  - Event push into SSE queue from _check_post_captures
affects:
  - src/shitbox/events/engine.py
  - src/shitbox/dashboard/static/vendor/{alpine.min.js,leaflet.js,leaflet.css,tailwind.min.css,SHA256SUMS}
  - src/shitbox/dashboard/static/index.html (new)
  - config/config.yaml (dashboard.enabled -> true)
  - tests/__init__.py (new, Rule 3 fix)
tech-stack:
  added:
    - Alpine.js 3.14.1
    - Leaflet 1.9.4
    - Tailwind 2.2.19 (precompiled CDN; tailwind 3 dropped CDN build)
  patterns:
    - "Engine-side 100->10 Hz decimation via modulo counter (sampler stays untouched)"
    - "Atomic dict rebind snapshot (update_snapshot) as the sync/async handoff"
    - "Non-blocking push_event — drops on full, never waits on the dashboard"
    - "Dashboard stopped before other services so its port releases early"
key-files:
  created:
    - src/shitbox/dashboard/static/index.html
    - src/shitbox/dashboard/static/vendor/alpine.min.js
    - src/shitbox/dashboard/static/vendor/leaflet.js
    - src/shitbox/dashboard/static/vendor/leaflet.css
    - src/shitbox/dashboard/static/vendor/tailwind.min.css
    - tests/__init__.py
  modified:
    - src/shitbox/dashboard/static/vendor/SHA256SUMS
    - src/shitbox/events/engine.py
    - config/config.yaml
decisions:
  - "Tailwind 2.2.19 from unpkg: Tailwind 3 dropped the precompiled CDN build and npx tailwindcss wasn't available in this sandbox. Tailwind 2 covers every utility the locked layout uses (grid, flex, spacing, text, colors)."
  - "Engine uses IMUSample.ax/ay/az (not accel_x) — the plan's code sketch had the wrong field names; corrected against ring_buffer.py."
  - "Snapshot hdop/temps wired via getattr(...) with None fallbacks because EngineState does not yet track hdop separately and ThermalMonitorService exposes temps as attributes that may be absent on macOS dev."
  - "Dashboard stopped FIRST in UnifiedEngine.stop() (before sampler/sync/etc) so the uvicorn port releases immediately — prevents test retries and rapid restart races."
  - "Added tests/__init__.py. The 10-03 test suite claimed green but test_dashboard.py does `from tests.conftest import _KNOWN_PNG`, which fails without tests being a package. Rule 3 blocking fix — no functional change."
metrics:
  duration: ~12 min
  tasks: 3
  files_changed: 9
  completed: 2026-04-09
requirements-completed: [D-02, D-04, D-10, D-11, D-13, D-14, D-15, D-20, D-21, D-22]
---

# Phase 10 Plan 04: Frontend + Engine Wiring Summary

Wave 3 of Phase 10. The dashboard is now end-to-end: vendored frontend on disk, the locked layout from UI-SPEC rendering, and UnifiedEngine constructing/starting/stopping a real `DashboardServer` with snapshot and event hooks feeding it from the live capture path. All graceful-degradation discipline is in place — dashboard trouble (port bind, JSON build, queue full) never touches the 100 Hz sampler or the event save path.

## What shipped

### Task 1 — vendored assets

Downloaded to `src/shitbox/dashboard/static/vendor/`:

- `alpine.min.js` (44 KB) — Alpine.js 3.14.1 from jsdelivr
- `leaflet.js` (144 KB) + `leaflet.css` (14 KB) — Leaflet 1.9.4 from unpkg
- `tailwind.min.css` (2.8 MB) — Tailwind 2.2.19 from unpkg (see decision)

`SHA256SUMS` rewritten with real `sha256sum` output, all four `PENDING-WAVE3` markers gone, `sha256sum -c` verifies clean.

### Task 2 — `src/shitbox/dashboard/static/index.html`

Single self-contained HTML implementing the UI-SPEC contract:

- **Top bar** (80 px): GPS badge (NO FIX / 2D / 3D), speed (km/h, tabular-nums), SYNC badge
- **Main grid**: canvas G-gauge with `±peakG` auto-range decay (45s toward 1.0 g, D-14); IMU + SoC temperature cards; Leaflet map with offline `/tiles/{z}/{x}/{y}.png` layer, blue position marker, 300-point breadcrumb polyline, auto-recentre 10 s after last map interaction (D-20)
- **Bottom event strip** (88 px): horizontally scrolling badges for the last 10 events, coloured per `ev-*` class for HIGH_G / HARD_BRAKE / BIG_CORNER / ROUGH_ROAD / MANUAL / BOOT
- Three `EventSource` clients (`/sse/fast`, `/sse/slow`, `/sse/events`), all handling `event:`-typed frames
- Mobile reflow via the `md:grid-cols-2` breakpoint

### Task 3 — engine wiring

- **Imports** — `DashboardServer`, `build_dashboard_server`, `update_snapshot`, `push_event as dashboard_push_event`
- **EngineConfig** — four new flat fields (`dashboard_enabled`, `dashboard_host`, `dashboard_port`, `dashboard_mbtiles_path`) plus mapping in `from_yaml_config`
- **`__init__`** — `self._snapshot_counter = 0`; `self._dashboard = build_dashboard_server(...)` behind `config.dashboard_enabled`, wrapped in try/except → `dashboard_init_failed` log on failure, `self._dashboard = None` on failure
- **`start()`** — dashboard started after `thermal_monitor.start()` and before the sampler so the snapshot starts getting populated as soon as IMU samples arrive. Exceptions logged as `dashboard_start_failed`
- **`stop()`** — dashboard stopped **first** so its port is released immediately, before any other service shuts down. Exceptions logged as `dashboard_stop_failed`
- **`_on_imu_sample`** — after `detector.process_sample(sample)`:
  - increments `_snapshot_counter`
  - every 10th sample builds a fresh 16-key dict and calls `update_snapshot(...)`
  - wrapped in try/except → `dashboard_snapshot_update_failed` warning; sampler path never raises
  - fields sourced from existing engine state (`_current_speed_kmh`, `_current_lat`, `_current_lon`, `_current_heading`, `_gps_has_fix`, `_current_satellites`, `events_captured`, `batch_sync.pending_count`, `connection.is_connected`, `thermal_monitor.{imu,soc}_temp_c`)
- **`_check_post_captures`** — after successful `event_storage.save_event()`, pushes `{type, timestamp, peak_g, duration_ms, speed_kmh, lat, lng}` into the SSE queue via `dashboard_push_event`. Wrapped in try/except → `dashboard_event_push_failed` warning
- **`config/config.yaml`** — `dashboard.enabled` flipped from `false` to `true`

The `HighRateSampler` file is **completely untouched** — `git diff --stat src/shitbox/events/sampler.py` is empty. This was the explicit requirement from RESEARCH Open Question 1.

## Verification

- `python -c "from shitbox.events.engine import UnifiedEngine, EngineConfig; from shitbox.dashboard.server import DashboardServer; from shitbox.dashboard.snapshot import update_snapshot, read_snapshot"` — ok
- `cd src/shitbox/dashboard/static/vendor && sha256sum -c SHA256SUMS` — `alpine.min.js: OK / leaflet.js: OK / leaflet.css: OK / tailwind.min.css: OK`
- `git diff --stat src/shitbox/events/sampler.py` — empty (sampler untouched)
- `pytest tests/test_dashboard.py tests/test_download_tiles.py` — 18 passed
- `pytest tests/` — 133 passed, 14 pre-existing failures (`test_capture_integrity.py`, `test_ffmpeg_stall.py`, `test_speaker_alerts.py`) flagged as out-of-scope in the 10-03 summary
- Frontend contract grep: `EventSource(.*sse/fast|slow|events)`, `/tiles/{z}/{x}/{y}.png`, `/static/vendor/{leaflet.js,alpine.min.js,tailwind.min.css}`, `md:grid-cols-2`, `lastInteract`, all event badge classes — all match

## Deviations from Plan

### Rule 3 — Blocking: `tests/__init__.py` missing

`tests/test_dashboard.py::test_tiles_y_flip` does `from tests.conftest import _KNOWN_PNG`. Without a `tests/__init__.py` file pytest discovers the tests fine but the `tests` package import fails at runtime (`ModuleNotFoundError: No module named 'tests'`). The 10-03 summary claimed this test was green, but running it from a clean checkout today fails. Added an empty `tests/__init__.py`. No functional change to any test or source file.

### Rule 1 — Bug: plan code sketch used wrong IMUSample field names

The plan's snapshot hook sketch used `sample.accel_x / accel_y / accel_z`. `IMUSample` is a slotted dataclass with fields `ax, ay, az`. Corrected the engine wiring to use the real field names.

### Rule 3 — Blocking: Tailwind 3 has no precompiled CDN

The plan's first-choice URL (`cdn.jsdelivr.net/npm/tailwindcss@3.4.13/dist/tailwind.min.css`) 404s because Tailwind 3 dropped the precompiled build. The plan explicitly allowed the Tailwind 2.2.19 fallback, so that's what landed. Every utility class the locked layout uses (`grid`, `grid-cols-1`, `md:grid-cols-2`, `gap-*`, `p-*`, `flex`, `items-center`, `justify-between`, `text-*`, `overflow-hidden`, `overflow-x-auto`, etc.) is present in Tailwind 2. The handful of custom colour classes (`bg-red-700` etc.) are also defined as plain CSS in the `<style>` block for safety.

## Known Stubs

None introduced by this plan. The `gps_hdop` field is always `None` in the snapshot because the engine doesn't track HDOP separately today — the slow SSE stream surfaces `null` and the frontend prints the fix mode without it. This is a cosmetic gap rather than a stub: a future plan wanting HDOP on the badge will need to plumb it through from `_read_gps` into `_current_hdop` and then into the snapshot dict.

## Deferred Issues

- Pre-existing ruff E501/F401 warnings in unrelated engine code (lines 463, 553, 1037-8, 1066, 2058). Out of scope — those lines were not touched by this plan.
- 14 pre-existing pytest failures (capture integrity, ffmpeg stall, speaker alerts) already flagged as out of scope in the 10-03 summary. No regressions introduced.
- The `PytestUnhandledThreadExceptionWarning` from 10-03's retried uvicorn startup is still cosmetic and still present. Same note as before.

## Commits

- `624059d` chore(10-04): vendor frontend assets with real SHA256SUMS
- `5ed400e` feat(10-04): add single-file Alpine/Tailwind/Leaflet dashboard UI
- `c332851` feat(10-04): wire DashboardServer into UnifiedEngine lifecycle

## Self-Check: PASSED

- All vendored files, index.html, tests/__init__.py present
- Commits 624059d, 5ed400e, c332851 all present in git log
- `sha256sum -c SHA256SUMS` clean
- `git diff --stat src/shitbox/events/sampler.py` empty (sampler untouched)
- `pytest tests/test_dashboard.py tests/test_download_tiles.py` 18/18 green
