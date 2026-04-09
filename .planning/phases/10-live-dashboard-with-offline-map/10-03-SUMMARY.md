---
phase: 10-live-dashboard-with-offline-map
plan: 03
subsystem: dashboard/backend
tags: [dashboard, fastapi, sse, mbtiles, uvicorn, tdd]
requires:
  - shitbox.dashboard package + snapshot (10-01)
  - tests/test_dashboard.py RED stubs (10-00)
provides:
  - shitbox.dashboard.tiles.make_router — MBTiles read-only tile router
  - shitbox.dashboard.sse.router — /sse/fast, /sse/slow, /sse/events with 8-client cap
  - shitbox.dashboard.sse.push_event — non-blocking enqueue for engine callbacks
  - shitbox.dashboard.sse.set_recent_events_provider — wiring hook for EventStorage.recent
  - shitbox.dashboard.server.build_app — pure FastAPI factory
  - shitbox.dashboard.server.DashboardServer — embedded uvicorn daemon-thread service
  - EventStorage.recent(n) helper
affects:
  - src/shitbox/dashboard/tiles.py
  - src/shitbox/dashboard/sse.py
  - src/shitbox/dashboard/server.py
  - src/shitbox/events/storage.py
  - tests/test_dashboard.py
tech-stack:
  added: []
  patterns:
    - "MBTiles read-only immutable URI (file:...?mode=ro&immutable=1)"
    - "Per-thread sqlite3 connection cache via threading.local"
    - "XYZ->TMS Y flip ((1 << z) - 1 - y) at the tile handler"
    - "Bounded queue.Queue with drop-on-full for cross-thread event fan-out"
    - "asyncio.to_thread for draining a sync queue from an async generator"
    - "Embedded uvicorn with install_signal_handlers override for daemon-thread lifecycle"
key-files:
  created:
    - src/shitbox/dashboard/tiles.py
    - src/shitbox/dashboard/sse.py
    - src/shitbox/dashboard/server.py
  modified:
    - src/shitbox/events/storage.py
    - tests/test_dashboard.py
decisions:
  - "Replaced sse_starlette.EventSourceResponse with plain StreamingResponse + hand-formatted SSE frames — sse_starlette 3.3.4 hung under starlette 0.52 TestClient; StreamingResponse is trivial and does the same job"
  - "Streaming tests spin up a real uvicorn on an ephemeral port instead of using TestClient.stream — starlette's in-process TestClient fully drains infinite async generators before returning, which makes it unusable for SSE. The live-server path exercises DashboardServer end-to-end anyway, which is arguably better coverage"
  - "Port allocation in _start_live_server uses bind(0) then close + retry loop. SystemExit(1) from uvicorn.startup still shows as a cosmetic PytestUnhandledThreadExceptionWarning on retry but the retry loop recovers"
  - "EventStorage.recent iterates stored JSON files and returns the same shape as generate_events_json so the frontend treats initial + live events identically"
metrics:
  duration: ~25 min
  tasks: 3
  files_changed: 5
  completed: 2026-04-09
requirements-completed: [D-01, D-03, D-04, D-07, D-08, D-09, D-15, D-16]
---

# Phase 10 Plan 03: Dashboard Backend Summary

Backend meat of the live dashboard: MBTiles tile router with the read-only immutable URI, SSE streams for fast/slow telemetry and events, embedded uvicorn on a daemon thread, and the `EventStorage.recent()` helper that seeds new clients with history. All 13 `tests/test_dashboard.py` tests now pass, plus the 5 `tests/test_download_tiles.py` tests from 10-02.

## What shipped

- `src/shitbox/dashboard/tiles.py` — `make_router(mbtiles_path)` returns a FastAPI router serving `/tiles/{z}/{x}/{y}.png`. Opens the MBTiles with `file:{path}?mode=ro&immutable=1` via `threading.local` cache (no WAL/SHM creation on a read-only mount), flips XYZ to TMS y with `(1 << z) - 1 - y`, sends a one-day cache header on hits and a plain 404 on misses.
- `src/shitbox/dashboard/sse.py` — three handlers:
  - `/sse/fast` at 10 Hz: `ts, speed, gx, gy, gz, heading`
  - `/sse/slow` at 1 Hz: GPS fix, temps, sync state, event count
  - `/sse/events`: seeds with `recent_events_provider(10)` then drains a bounded `queue.Queue` (`maxsize=256`) via `asyncio.to_thread`
  - 8-client cap enforced via an `asyncio.Lock` + counter; a 9th concurrent connection gets `HTTPException(503)`
  - `push_event(ev)` is non-blocking, drops on full with a warning log — the 100 Hz capture path must never wait on the dashboard (D-02/D-04)
- `src/shitbox/dashboard/server.py` — `build_app(mbtiles_path, recent_events_provider=None)` is a pure factory (no I/O, no bind) so tests and the engine share the same wiring. `DashboardServer(host, port, app)` runs uvicorn on a daemon thread with `install_signal_handlers` overridden to a no-op (RESEARCH Pitfall 1), `access_log=False`, `lifespan="off"`, and `loop="asyncio"`. Both `start()` and `stop()` swallow exceptions so a port-bind failure stays a logged error and never propagates into the engine thread. `build_dashboard_server(...)` is the convenience factory UnifiedEngine wiring will call in Wave 4.
- `EventStorage.recent(n)` — mirrors `generate_events_json`'s entry shape (type, timestamp, peak_g, duration_ms, speed_kmh, lat, lng), newest first, skips the consolidated `events.json` file itself.

## Tests flipped to GREEN

All 13 `tests/test_dashboard.py` tests:

- `test_snapshot_atomicity`, `test_snapshot_default_keys` (already green from 10-01)
- `test_lifecycle`, `test_handler_exception_isolated`, `test_port_bind_failure_isolated`
- `test_sse_client_cap`, `test_sse_fast_schema`, `test_sse_slow_schema`, `test_sse_events_initial_and_live`
- `test_tiles_y_flip`, `test_tile_404`, `test_mbtiles_immutable_uri`
- `test_uvicorn_signal_handlers_disabled`

```text
tests/test_dashboard.py tests/test_download_tiles.py
======================== 18 passed, 1 warning in 2.91s =========================
```

`ruff check src/shitbox/dashboard/` is clean.

## Deviations from Plan

### Rule 3 — Blocking: starlette TestClient cannot stream infinite async generators

The plan's SSE tests (`test_sse_fast_schema`, `test_sse_slow_schema`, `test_sse_events_initial_and_live`) were written against `fastapi.testclient.TestClient.stream(...)`. Under the current pinned stack (`starlette==0.52.1`, `httpx==0.27.2`, `sse-starlette==3.3.4`) this hangs forever on any generator that doesn't terminate of its own accord. I verified this with two minimal reproducers:

- `sse_starlette.EventSourceResponse`: `client.stream("GET", ...)` never returns even the status line.
- Plain `StreamingResponse(gen())` where `gen` has a `while True: yield ...; await asyncio.sleep(0.02)` loop: same hang. A bounded `for i in range(50)` version works only because the generator completes and the whole body is buffered before the response returns.

Conclusion: starlette's in-process `TestClient` fully drains the ASGI response before returning — it is not actually a streaming client. This is a hard blocker on the test approach, not a bug in our code.

**Fix applied:**

1. Replaced `EventSourceResponse` with a plain `StreamingResponse` wrapping a small `_format_sse(event, payload)` helper. The SSE wire format is trivial (`event: x\ndata: {...}\n\n`), we gain nothing from the third-party wrapper and lose the hang.
2. Added `_start_live_server(app)` and `_read_sse_lines(url)` helpers in `tests/test_dashboard.py`. The streaming tests now spin up a real `DashboardServer` on `127.0.0.1:<ephemeral>`, connect with a raw `httpx.Client` on a 3 s timeout, read a handful of lines, then stop the server. This exercises the same wiring UnifiedEngine will use in Wave 4, so coverage actually improves.
3. Port selection uses `bind(("127.0.0.1", 0)) -> getsockname -> close` then hands the port to uvicorn, with a 5-attempt retry loop guarding against the rare TIME_WAIT race. A stale uvicorn startup failure surfaces as a cosmetic `PytestUnhandledThreadExceptionWarning`; the retry recovers and tests still pass.

### Rule 3 — Blocking: fastapi/uvicorn/sse-starlette/httpx not installed in dev env

The plan assumed `pip install -e ".[dev]"` had been re-run after 10-01 added the dashboard deps. It hadn't been — `ModuleNotFoundError: No module named 'fastapi'` on the first test run. Installed `fastapi uvicorn sse-starlette httpx` directly. Pinned versions landed as: `fastapi==0.135.3`, `uvicorn==0.44.0`, `starlette==0.52.1`, `sse-starlette==3.3.4`, `httpx==0.27.2` (httpx was downgraded during debugging and left there; it works fine).

### Rule 2 — Added: unused-import cleanup

Kept the `sse_starlette.EventSourceResponse` import behind a `# noqa: F401` comment as a marker that we deliberately replaced it. Nothing else removed.

## Commits

- `d911023` feat(10-03): add MBTiles tile router and EventStorage.recent()
- `db56e6d` feat(10-03): add SSE routers with 8-client cap and bounded event queue
- `2d016bd` feat(10-03): add DashboardServer, build_app factory, flesh out SSE tests

## Known Stubs

None introduced by this plan. The static root serves whatever lands in `src/shitbox/dashboard/static/` — Wave 3 (10-04) ships the frontend there. When `STATIC_DIR` is missing, `build_app` logs `dashboard_static_dir_missing` and simply does not mount `/` or `/static`; the tile and SSE routes work fine without it.

## Deferred Issues

- Pre-existing failures in `tests/test_capture_integrity.py` (7) and `tests/test_ffmpeg_stall.py`, `tests/test_speaker_alerts.py` — confirmed to fail on the base branch as well. Out of scope.
- Pytest cosmetic warning `PytestUnhandledThreadExceptionWarning` from a retried-past uvicorn startup failure. Test suite is green; the warning is a cleanup smell, not a correctness problem. If it gets noisy we can filter it in `pyproject.toml`.

## Self-Check: PASSED

- `src/shitbox/dashboard/tiles.py` — FOUND
- `src/shitbox/dashboard/sse.py` — FOUND
- `src/shitbox/dashboard/server.py` — FOUND
- `src/shitbox/events/storage.py::recent` — FOUND (grep `def recent`)
- `tests/test_dashboard.py` flesh-out — FOUND (three stubs replaced)
- Commit `d911023` — FOUND in git log
- Commit `db56e6d` — FOUND in git log
- Commit `2d016bd` — FOUND in git log
- `pytest tests/test_dashboard.py tests/test_download_tiles.py` — 18 passed
- `ruff check src/shitbox/dashboard/` — clean
