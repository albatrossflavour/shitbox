# Phase 10: Live Dashboard with Offline Map - Research

**Researched:** 2026-04-09
**Domain:** In-process FastAPI/SSE on Raspberry Pi, offline raster tile serving, vendored single-file frontend
**Confidence:** HIGH on the core stack, MEDIUM on a couple of operational details (called out below)

## Summary

Almost every architectural decision is already locked in CONTEXT.md. The job of this research is not to pick a stack, it's to make sure the locked stack actually behaves the way the planner expects when wired into a 100 Hz daemon, and to nail down the bits that were left to Claude's discretion (uvicorn config, snapshot mechanism, decay curves, vendored versions).

The integration shape is straightforward and well-trodden: FastAPI app constructed at engine init, handed to a `uvicorn.Server` which is run inside a daemon thread, lifecycle wired into `UnifiedEngine.start()` / `stop()` to mirror `BatchSyncService`. The capture path's only contact with the web layer is a single atomic dict-reference swap on a module-level snapshot, which Python guarantees is thread-safe under the GIL without locks. SSE handlers are async generators that read that snapshot and yield at a fixed cadence. MBTiles is just SQLite, so tile serving is a one-line `SELECT tile_data FROM tiles WHERE ...` against a read-only connection - no new dependency.

The biggest non-obvious risk is uvicorn's signal handling: by default uvicorn installs SIGINT/SIGTERM handlers, which will fight `UnifiedEngine`'s own signal handling and cause weird shutdown behaviour. This must be disabled explicitly. Second risk is vendoring Tailwind without a build step - the cleanest path is to ship a precompiled Tailwind CSS file produced once by the standalone Tailwind binary, not to use the play CDN.

**Primary recommendation:** Build `dashboard/server.py` as a thin wrapper around `uvicorn.Server` constructed with `install_signal_handlers=False`, run it in a daemon thread, and use a module-level `_snapshot: dict` swapped by reference from the high-rate sample callback. Vendor a precompiled Tailwind CSS file plus pinned Alpine and Leaflet builds. Serve MBTiles tiles directly from a read-only sqlite3 connection cached on the FastAPI app state.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Server architecture**
- D-01: FastAPI in-process inside `UnifiedEngine`, own daemon thread, uvicorn programmatic. Lifecycle owned by engine.
- D-02: Capture path is sacred. All web reads via lock-free snapshot dict. Single writer (high-rate path), many readers. Web code never holds locks the sampler needs and never blocks on capture-path I/O.
- D-03: Hard cap 8 concurrent SSE clients; reject beyond cap with HTTP 503.
- D-04: Web subsystem failure (uvicorn crash, port bind error, handler exception) must NOT take down the daemon. Catch + structlog, keep capturing.
- D-05: Listen on `0.0.0.0:8080`. No auth.

**Module layout**
- D-06: New package `src/shitbox/dashboard/`. Files: `server.py`, `snapshot.py`, `sse.py`, `tiles.py`, `static/`. Will grow in Phase 11 for persistence/forms.

**Live data transport**
- D-07: SSE for live telemetry (auto-reconnect, no framing, no ping/pong bookkeeping).
- D-08: Two streams:
  - `/sse/fast` 10 Hz — speed, G X/Y/Z, heading
  - `/sse/slow` 1 Hz — GPS fix mode, sat count, HDOP, lat/lng, IMU temp, SoC temp, sync status, driver placeholder, event count
- D-09: `/sse/events` push-based. Last 10 on connect, then incremental.

**Frontend**
- D-10: Single HTML file at `dashboard/static/index.html`. Alpine.js + Tailwind + Leaflet, all vendored under `dashboard/static/vendor/`. No CDN at runtime, no build step. Versions pinned.
- D-11: Layout — top bar (GPS fix/sat/HDOP, speed, driver, sync), main split (G-gauge, IMU/SoC tiles, map), bottom strip (last 10 events). Mobile reflows single column.
- D-12: No voltage / INA219 readout this phase.

**G-gauge**
- D-13: Auto-ranging scale, "looks cool" priority. Capture path uses real values regardless.
- D-14: Auto-range decay over 30-60 s. Planner picks exact curve.

**Map**
- D-15: CartoDB dark raster tiles, pre-downloaded as MBTiles, stored under `data_dir`.
- D-16: `GET /tiles/{z}/{x}/{y}.png` reads from MBTiles SQLite. 404 on missing.
- D-17: Pre-download corridor 20 km either side of route line built from `config/config.yaml` waypoints.
- D-18: Pre-download zoom range 5-15.
- D-19: One-shot pre-download tool in `tools/` (not part of daemon). Reads waypoints, walks tile pyramid, fetches politely (rate limit + descriptive UA), writes MBTiles. Idempotent — skips already-present tiles.
- D-20: Auto-recentre after 10 s of no user interaction. Frontend tracks Leaflet drag/zoom events and resets timer.
- D-21: Map shows live position dot, breadcrumb of last ~5 min of fixes, event markers from `/sse/events`.

**Events**
- D-22: Bottom strip last 10 events. Reuse colour mapping from shit-of-theseus.com (HIGH_G red, BIG_CORNER amber, HARD_BRAKE red, ROUGH_ROAD purple, MANUAL/BUTTON green, BOOT blue). Frontend mirror, not backend dependency.

### Claude's Discretion

- Exact uvicorn config (workers, log level, must integrate with structlog)
- Snapshot dict update mechanism (set new dict reference vs in-place under quick lock)
- Breadcrumb point count and decimation
- G-gauge auto-range decay curve and timing
- Tailwind config approach (precompiled vendor CSS vs play CDN baked offline)
- SSE keepalive interval
- Frontend vendor versions

### Deferred Ideas (OUT OF SCOPE)

- Phase 11: driver swap logging, refuel entries, blog posts, breakdown count, new SQLite tables, POST endpoints, sync of new tables
- Voltage / INA219 on dashboard
- Self-rendered tiles via tilemaker
- Live video preview embed

## Phase Requirements

This phase has no formal `REQ-` IDs in REQUIREMENTS.md — it was inserted into the roadmap after v1.1 closed. The success criteria are derived from CONTEXT.md decisions D-01..D-22. The planner should treat the locked decisions as the requirement set.

## Project Constraints (from CLAUDE.md)

- Logging: `structlog` with keyword arguments only. Uvicorn's default logging must be redirected through structlog or silenced.
- Ruff: line length 100, rules E/F/I/W, target Python 3.9.
- Full type annotations; mypy enforced.
- Hierarchical YAML config loaded into nested dataclasses via `_dict_to_dataclass`. Add `DashboardConfig` to `utils/config.py`.
- All collectors/services run as daemon threads. Database uses thread-local connections + write locks. Dashboard reads only in this phase, but every sqlite3 connection must be opened in the thread that uses it.
- Hardware graceful degradation philosophy applies: if the dashboard fails to start (port in use, missing tiles, missing static dir), the daemon must keep capturing. This is restated in D-04.
- Add-a-service pattern documented in CLAUDE.md must be mirrored: config dataclass → service class with `start()`/`stop()` → engine wiring (instantiation behind a guard, start/stop in lifecycle methods) → YAML section.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.115.x | Web framework, routing, SSE generators | Lightweight, async-native, plays well with uvicorn programmatic mode, type-friendly |
| uvicorn[standard] | 0.32.x | ASGI server | Standard pairing with FastAPI; supports programmatic embedding via `uvicorn.Config` + `uvicorn.Server` |
| sse-starlette | 2.1.x | `EventSourceResponse` helper for SSE streams from async generators | FastAPI/Starlette's own SSE story is clunky; sse-starlette handles keepalive, disconnect detection, and ping framing properly |

`sse-starlette` is the only library here that is not strictly necessary — you can hand-roll SSE with a `StreamingResponse` and a `text/event-stream` content type — but the disconnect detection it provides is exactly the thing you want when a phone wanders off the rally wifi mid-stream. Worth the dependency.

`uvicorn[standard]` pulls in `httptools` and `uvloop`. uvloop is not packaged for Raspberry Pi OS arm64 in every release — it usually is, but if `pip install` fails on the Pi, drop the `[standard]` extra and use the pure-Python event loop. Performance is fine for this workload (a handful of SSE clients, not a real web server).

**Version verification:**
```bash
pip index versions fastapi uvicorn sse-starlette
```
Pin to current stable at implementation time. Training-data versions are 6+ months stale.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `sqlite3` | (stdlib) | Read MBTiles | Already a project dependency. No need for `mbutil` or any MBTiles helper lib. |
| stdlib `asyncio` / `anyio` | (stdlib / via Starlette) | Async generators for SSE | Already pulled in by FastAPI. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastAPI | stdlib `http.server` | Zero deps, but no async, SSE is painful, type story is bad. Not worth saving 5 MB of wheels. |
| FastAPI | aiohttp / Starlette directly | Lighter, but FastAPI is already the conventional choice on the Pi side and the rest of the team will know it. CONTEXT.md locked it anyway. |
| SSE | WebSockets | Bidirectional, but we don't need bidirectional. SSE auto-reconnects on its own; WS needs manual reconnect logic in the frontend. CONTEXT.md locked SSE. |
| MBTiles | PMTiles | PMTiles is the modern format and works over plain HTTP range requests, but it's vector-first and our locked tile source is raster CartoDB dark. MBTiles + sqlite3 is the right choice for raster tiles served by our own process. |
| Pre-downloaded raster | tilemaker self-rendered | Self-rendering is the nuclear option if OSM tile policy ever bites. Out of scope for this phase (CONTEXT.md deferred). |
| Vendored Tailwind CSS | Twind / play CDN baked offline | Play CDN works offline if you bundle the JS but it ships a JIT compiler in the browser, ~300 KB, runs on every page load. Precompiled CSS is ~10-30 KB and faster on a Pi browser. Recommend precompiled. |

**Installation:**
```bash
pip install "fastapi>=0.115" "uvicorn[standard]>=0.32" "sse-starlette>=2.1"
```

Add these to `pyproject.toml` `[project] dependencies`. They are runtime deps, not dev deps — the dashboard runs in production on the Pi.

## Architecture Patterns

### Recommended Project Structure

```
src/shitbox/dashboard/
├── __init__.py
├── server.py         # DashboardServer service: FastAPI app, uvicorn.Server, daemon thread, start/stop
├── snapshot.py       # Module-level _snapshot dict + update_snapshot() + read_snapshot()
├── sse.py            # /sse/fast, /sse/slow, /sse/events handlers; client counter; cap enforcement
├── tiles.py          # MBTiles read-only sqlite3 connection + /tiles/{z}/{x}/{y}.png handler
├── routes.py         # Optional: /api/events recent, /healthz, etc.
└── static/
    ├── index.html
    └── vendor/
        ├── alpine.min.js          # pinned, e.g. 3.14.x
        ├── leaflet.js
        ├── leaflet.css
        ├── leaflet-images/        # marker shadow, etc.
        └── tailwind.min.css       # precompiled

tools/
└── download_tiles.py              # one-shot MBTiles builder; argparse; reads config/config.yaml
```

### Pattern 1: Embedded uvicorn in a daemon thread

This is the canonical "uvicorn from inside another app" pattern. It's documented in uvicorn's own source and is used by libraries like `gradio` and `pytest-asgi-server`.

```python
# src/shitbox/dashboard/server.py
import threading
from typing import Optional
import uvicorn
from fastapi import FastAPI
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class DashboardServer:
    def __init__(self, host: str, port: int, app: FastAPI) -> None:
        self._host = host
        self._port = port
        self._app = app
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_config=None,            # silence uvicorn's logger; we use structlog
            access_log=False,           # avoid noise in the engine log
            lifespan="off",             # we own lifecycle, not uvicorn
            loop="asyncio",             # do NOT default to uvloop on the Pi
        )
        self._server = uvicorn.Server(config)
        # CRITICAL: stop uvicorn from installing SIGINT/SIGTERM handlers
        # that will fight UnifiedEngine's own signal handling.
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

        def _run() -> None:
            try:
                self._server.run()  # blocks until self._server.should_exit = True
            except Exception as exc:
                log.error("dashboard_server_crashed", error=str(exc))

        self._thread = threading.Thread(target=_run, name="dashboard", daemon=True)
        self._thread.start()
        log.info("dashboard_started", host=self._host, port=self._port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        log.info("dashboard_stopped")
```

Notes that matter:
- `install_signal_handlers = lambda: None` is the documented escape hatch. Without it, uvicorn calls `signal.signal()` on the dashboard thread, which on Python only works on the main thread and either errors out or steals the engine's handlers.
- `lifespan="off"` is correct because we are not running ASGI lifespan events — we own start/stop.
- `loop="asyncio"` avoids the uvloop dependency landmine on the Pi.
- `log_config=None, access_log=False` keeps uvicorn from clobbering the structlog setup with its own dictConfig.

### Pattern 2: Lock-free snapshot dict (single writer, many readers)

Python's GIL guarantees that a single bytecode operation is atomic. Rebinding a module-level name (`module._snapshot = new_dict`) is a single STORE_NAME / STORE_GLOBAL bytecode and is therefore atomic. Readers see either the old dict or the new dict, never a half-built one.

```python
# src/shitbox/dashboard/snapshot.py
"""Lock-free shared state between the high-rate sampler and the web layer.

The high-rate path is the SOLE writer. Web handlers are readers. We rebind
a module-level dict reference per update — atomic under the GIL — so readers
never see a partial update and writers never block on a reader.
"""
from typing import Any, Dict

# Sentinel empty snapshot so readers can run before the sampler starts
_snapshot: Dict[str, Any] = {
    "ts": 0.0,
    "speed_kmh": 0.0,
    "g_x": 0.0, "g_y": 0.0, "g_z": 0.0,
    "heading_deg": 0.0,
    "lat": None, "lng": None,
    "gps_fix_mode": 0, "gps_sat_count": 0, "gps_hdop": None,
    "imu_temp_c": None, "soc_temp_c": None,
    "sync_connected": False, "sync_backlog": 0,
    "event_count_today": 0,
}


def update_snapshot(new: Dict[str, Any]) -> None:
    """Replace the snapshot. Called only from the high-rate sample callback.

    The caller MUST construct a complete dict — partial updates are not supported.
    Use update_snapshot({**read_snapshot(), "speed_kmh": v}) for incremental updates,
    accepting that read+write is not atomic and may briefly clobber a concurrent
    update from a different writer (we have only one writer, so this is fine).
    """
    global _snapshot
    _snapshot = new  # atomic rebind under the GIL


def read_snapshot() -> Dict[str, Any]:
    """Read the current snapshot. Safe from any thread, no locks."""
    return _snapshot  # readers get whatever the latest atomic rebind was
```

This is the recommended mechanism for D-02. The alternative (in-place update under a quick `threading.Lock`) is also fine and trivially correct, but adds a lock the sampler must acquire. Since we have exactly one writer, the lock buys nothing.

**One subtlety:** the high-rate path runs at 100 Hz but the `/sse/fast` stream only emits at 10 Hz. The sampler should not call `update_snapshot()` 100 times per second — that allocates 100 dicts per second per service. Either:
- Update the snapshot every Nth sample (e.g. every 10th, giving 10 Hz freshness), or
- Update only the values that changed and let the SSE handler poll at its own rate.

Recommendation: update at 10 Hz from inside the sampler's existing loop using a sample counter. Keeps allocations low and matches what the consumer needs.

### Pattern 3: SSE handlers with sse-starlette

```python
# src/shitbox/dashboard/sse.py
import asyncio
from sse_starlette.sse import EventSourceResponse
from fastapi import APIRouter, Request, HTTPException
from shitbox.dashboard.snapshot import read_snapshot

router = APIRouter()

MAX_CLIENTS = 8
_active_clients = 0
_clients_lock = asyncio.Lock()


async def _acquire_slot() -> None:
    global _active_clients
    async with _clients_lock:
        if _active_clients >= MAX_CLIENTS:
            raise HTTPException(status_code=503, detail="dashboard at capacity")
        _active_clients += 1


async def _release_slot() -> None:
    global _active_clients
    async with _clients_lock:
        _active_clients = max(0, _active_clients - 1)


@router.get("/sse/fast")
async def sse_fast(request: Request) -> EventSourceResponse:
    await _acquire_slot()

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                snap = read_snapshot()
                yield {
                    "event": "fast",
                    "data": orjson.dumps({
                        "ts": snap["ts"],
                        "speed": snap["speed_kmh"],
                        "gx": snap["g_x"], "gy": snap["g_y"], "gz": snap["g_z"],
                        "heading": snap["heading_deg"],
                    }).decode(),
                }
                await asyncio.sleep(0.1)  # 10 Hz
        finally:
            await _release_slot()

    return EventSourceResponse(gen(), ping=15)  # 15 s keepalive
```

**Discretion calls baked in above:**
- SSE keepalive interval: **15 s**. Long enough to be invisible, short enough to detect a dead phone before the OS times the TCP socket out.
- Client cap is enforced at handler entry, not in middleware. Simple and obvious.
- Disconnect detection via `request.is_disconnected()` plus the sse-starlette ping. Either path will release the slot.

### Pattern 4: MBTiles served from a cached read-only sqlite3 connection

MBTiles is just SQLite. Schema is well-known: a `tiles` table with `(zoom_level, tile_column, tile_row, tile_data)`. Coordinates use the TMS scheme (Y inverted from XYZ), so the handler must flip Y.

```python
# src/shitbox/dashboard/tiles.py
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response
import threading

router = APIRouter()

# Per-thread connection cache; SQLite connections are not thread-safe
_local = threading.local()


def _conn(path: Path) -> sqlite3.Connection:
    if getattr(_local, "conn", None) is None:
        # Read-only, immutable URI prevents WAL/journal creation on the tiles DB
        uri = f"file:{path}?mode=ro&immutable=1"
        _local.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    return _local.conn


def make_router(mbtiles_path: Path) -> APIRouter:
    @router.get("/tiles/{z}/{x}/{y}.png")
    def tile(z: int, x: int, y: int) -> Response:
        # XYZ -> TMS Y flip
        tms_y = (1 << z) - 1 - y
        row = _conn(mbtiles_path).execute(
            "SELECT tile_data FROM tiles "
            "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, tms_y),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404)
        return Response(content=row[0], media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    return router
```

Notes:
- `mode=ro&immutable=1` is critical. Without `immutable=1`, SQLite will try to create a `-shm`/`-wal` file next to the MBTiles, which the daemon may not have write permission for, and which will corrupt the file if two processes touch it.
- `check_same_thread=False` is safe because we use a per-thread connection cached in `threading.local`. FastAPI sync handlers run on a starlette threadpool, so different requests land on different threads.
- The `Cache-Control` header lets Leaflet's tile cache do its job and avoids re-fetching the same tile when the user pans back.

### Anti-Patterns to Avoid

- **Sharing one sqlite3 connection across threads.** Per-thread connection or per-request connection. Don't try to be clever with a single Connection guarded by a lock — sqlite3.Connection's threadsafety mode is not what you want here.
- **Letting uvicorn install signal handlers.** Will hijack `UnifiedEngine`'s SIGTERM handling. Always set `install_signal_handlers = lambda: None` after constructing the Server.
- **Using uvicorn's logging config.** Pass `log_config=None` and `access_log=False`. Uvicorn's default logger uses `logging.dictConfig` and will trample structlog's handlers.
- **Holding the snapshot dict reference for the duration of an SSE iteration.** Read it fresh on every yield so a writer's atomic rebind is observed immediately.
- **Polling SQLite for events on `/sse/events`.** Use a callback hook in the event detector that pushes into an `asyncio.Queue` (or a thread-safe `queue.Queue` and a wakeup primitive). Polling re-introduces the latency that SSE was supposed to eliminate.
- **Building Tailwind in CI.** No build step in this repo. Compile Tailwind once locally with the standalone binary, commit the resulting CSS file under `vendor/`, done.
- **Catching every exception in the handler and returning 200.** Let FastAPI return 500 for unexpected errors so they show up in structlog. The "do not crash the daemon" rule applies to the dashboard subsystem as a whole, not to individual handlers.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE framing + keepalive + disconnect detection | Custom `text/event-stream` generator | `sse_starlette.EventSourceResponse` | Disconnect detection on async generators is fiddly to get right; sse-starlette has years of edge cases baked in |
| Tile pyramid coordinate maths | Hand-converting lat/lon to tile XY | A copy of the OSM Slippy Map formulas (well-known, ~6 lines), wrapped in a tested function | The maths is short but the off-by-one and the TMS-vs-XYZ Y flip are exactly the kind of thing that wastes a day |
| MBTiles writing | Hand-rolled SQL | A small utility class with a known-good schema (zoom_level, tile_column, tile_row, tile_data + metadata table) | The MBTiles 1.3 spec is short; just follow it |
| Polite tile downloading | Concurrent fetches with no rate limit | Sequential fetches with `time.sleep(0.1)` and a descriptive User-Agent | Hammering OSM gets the IP banned. CartoDB tiles inherit OSM's policy. Slow and rude beats fast and banned |
| ASGI server | Custom socket loop | `uvicorn.Server` programmatic | Just use uvicorn |

**Key insight:** there is nothing in this phase that needs invention. Every piece is well-understood and supported by libraries the team already runs in other projects. The work is plumbing, not engineering.

## Common Pitfalls

### Pitfall 1: uvicorn signal handlers stealing SIGTERM
**What goes wrong:** Daemon receives SIGTERM. Uvicorn's handler runs first (because it was installed last), starts its own shutdown sequence, and the engine's cleanup code never runs — orphan events are not closed, the WAL is not checkpointed.
**Why it happens:** `uvicorn.Server.run()` calls `self.install_signal_handlers()` by default.
**How to avoid:** Replace it with a no-op before calling `run()`. See server.py example above.
**Warning signs:** SIGTERM logs "uvicorn shutting down" before any engine shutdown lines. Shutdown takes longer than expected because uvicorn waits for connections to drain before exiting.

### Pitfall 2: SQLite WAL files on a read-only MBTiles
**What goes wrong:** First request to `/tiles/...` succeeds, then permission errors appear, or the MBTiles file size grows mysteriously, or worse, a second daemon corrupts it.
**Why it happens:** Opening sqlite3 in read mode without `immutable=1` still allows journal and WAL file creation.
**How to avoid:** `file:{path}?mode=ro&immutable=1` URI. Test by `chmod -w` on the directory containing the MBTiles and confirm reads still work.
**Warning signs:** `mbtiles.db-shm`, `mbtiles.db-wal` files appearing next to the tiles file.

### Pitfall 3: Allocating 100 dicts/second from the high-rate path
**What goes wrong:** GC pressure on the Pi shows up as latency spikes in the 100 Hz sampler. Event detection goes jittery.
**Why it happens:** Naively calling `update_snapshot({...})` from inside the sample loop allocates a fresh dict on every sample.
**How to avoid:** Update at 10 Hz from inside the loop using a counter. Or pre-build a single dict and rebind only when at least one field has changed.
**Warning signs:** `time.perf_counter()` deltas in the sampler loop drifting upward over time; dropped samples.

### Pitfall 4: Vendoring the Tailwind play CDN
**What goes wrong:** Page loads "feel slow" on the kiosk Pi. The Tailwind play script is a 300 KB JIT compiler running in the browser on every page load.
**Why it happens:** Vendoring the play CDN feels easier than running the standalone binary once.
**How to avoid:** Run `tailwindcss -i input.css -o vendor/tailwind.min.css --minify` once locally with the precompiled binary (no Node required), commit the result.
**Warning signs:** First paint > 1 s on the Chromium kiosk; Tailwind classes flash unstyled.

### Pitfall 5: Forgetting that SSE handlers are async, sample callbacks are sync
**What goes wrong:** The event detector callback fires from the high-rate thread and tries to do `await queue.put(event)`. Crashes because there is no event loop in that thread.
**Why it happens:** Mixing the sync sampler thread with the async event loop.
**How to avoid:** Use `asyncio.run_coroutine_threadsafe(queue.put(event), loop)` from the sync thread, holding a reference to the uvicorn loop captured at startup. Or use a thread-safe `queue.Queue` and have the SSE handler poll it with `asyncio.to_thread(q.get, timeout=...)`. Recommend the latter — it keeps the async/sync boundary clean.
**Warning signs:** "no running event loop" errors in structlog from the sampler thread.

### Pitfall 6: Tile downloader hammering OSM/CartoDB
**What goes wrong:** Tile server returns 429s, then bans the IP. Pre-download tool fails halfway through and leaves a half-built MBTiles.
**Why it happens:** No rate limit, no User-Agent, no resume.
**How to avoid:** Sequential fetches at 5-10 req/s max, descriptive User-Agent like `shitbox-rally-tile-prefetch/1.0 (https://shit-of-theseus.com)`, idempotent skip-if-present, and write each tile inside its own transaction so a crash doesn't roll back hours of work.
**Warning signs:** HTTP 429, HTTP 403, sudden silence from the tile server.

### Pitfall 7: Static file path resolution after `pip install -e .`
**What goes wrong:** `dashboard/static/` is not found at runtime because the lookup uses `Path(__file__).parent` and `__file__` resolves somewhere unexpected.
**Why it happens:** `pyproject.toml` `[tool.setuptools.package-data]` does not currently include `dashboard/static/**`. Static files won't be packaged.
**How to avoid:** Add `dashboard = ["static/**/*"]` to `[tool.setuptools.package-data]` in pyproject.toml. Resolve paths via `Path(__file__).parent / "static"` and verify it works after `pip install -e .` and after a fresh checkout.
**Warning signs:** 404 on `/` after deploying to the Pi but works in dev.

## Code Examples

### Engine wiring

```python
# src/shitbox/events/engine.py — additions
from shitbox.dashboard.server import build_dashboard_server
from shitbox.dashboard.snapshot import update_snapshot

class UnifiedEngine:
    def __init__(self, config: EngineConfig) -> None:
        # ... existing init ...
        self._dashboard = None
        if config.dashboard_enabled:
            try:
                self._dashboard = build_dashboard_server(
                    host=config.dashboard_host,
                    port=config.dashboard_port,
                    mbtiles_path=Path(config.dashboard_mbtiles_path),
                    event_storage=self._event_storage,
                    connection_monitor=self._connection_monitor,
                )
            except Exception as exc:
                log.error("dashboard_init_failed", error=str(exc))
                self._dashboard = None  # daemon keeps running

    def start(self) -> None:
        # ... existing starts ...
        if self._dashboard is not None:
            try:
                self._dashboard.start()
            except Exception as exc:
                log.error("dashboard_start_failed", error=str(exc))

    def stop(self) -> None:
        if self._dashboard is not None:
            try:
                self._dashboard.stop()
            except Exception as exc:
                log.error("dashboard_stop_failed", error=str(exc))
        # ... existing stops ...

    # in the high-rate sample callback, every 10th sample:
    def _on_sample(self, sample: IMUSample) -> None:
        # ... existing detection ...
        self._snapshot_counter += 1
        if self._snapshot_counter % 10 == 0:
            update_snapshot(self._build_snapshot(sample))
```

### Slippy Map tile maths (for the pre-download tool)

```python
# tools/download_tiles.py — fragment
import math

def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """OSM slippy map XYZ tile coordinates."""
    lat_rad = math.radians(lat)
    n = 1 << zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y
```

The corridor builder walks the route waypoints, samples points along each segment every ~1 km, computes the tile envelope ±20 km at each zoom level, deduplicates the tile set, and fetches them in order. Estimated tile counts for a 4,000 km route at zoom 5-15 with a 40 km wide corridor: rough order of magnitude ~50-200k tiles. At ~10-30 KB each that's 0.5-6 GB. The 500 GB NVMe handles this trivially.

## Runtime State Inventory

Not a rename/refactor phase. **Skipped.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.9+ | Whole project | ✓ | already in use | — |
| sqlite3 (stdlib) | MBTiles tile serving | ✓ | stdlib | — |
| fastapi | Web framework | ✗ (not installed) | — | Must add to pyproject.toml |
| uvicorn[standard] | ASGI server | ✗ (not installed) | — | Drop `[standard]` if uvloop fails on Pi arm64 |
| sse-starlette | SSE helpers | ✗ (not installed) | — | Hand-roll with StreamingResponse if missing (worse, do not recommend) |
| Chromium browser on Pi (kiosk) | Display | Assumed present | — | — |
| Pre-built MBTiles file | Map serving | ✗ (will be built by tools/download_tiles.py) | — | Map shows blank tiles + 404s; daemon still runs |
| Standalone Tailwind binary | One-time CSS build (dev machine, not Pi) | Assumed installable on dev machine | — | Use play CDN baked offline if Tailwind binary is unworkable (worse) |

**Missing dependencies with no fallback:** none — fastapi/uvicorn/sse-starlette are simply new pip deps.

**Missing dependencies with fallback:** the MBTiles file is built ahead of time by the tools script; if the file is absent at runtime, the dashboard must serve 404s on tile requests and log a structured warning, but the rest of the dashboard (live SSE telemetry, event scroll, gauges) must keep working. This is exactly D-04: dashboard subsystem failures must not cascade.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ (already in `[project.optional-dependencies] dev`) |
| Config file | `pyproject.toml` (no separate pytest.ini) |
| Quick run command | `pytest tests/test_dashboard.py -x` |
| Full suite command | `pytest` |

FastAPI ships its own `TestClient` (built on httpx) which makes route testing trivial. SSE responses can be tested by reading the streaming body and asserting on the framed events. No new test deps needed beyond pytest.

### Phase Requirements → Test Map

CONTEXT.md decisions are the de facto requirements. The map below uses D-IDs.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | Dashboard starts/stops via UnifiedEngine lifecycle | unit | `pytest tests/test_dashboard.py::test_lifecycle -x` | ❌ Wave 0 |
| D-02 | Snapshot rebind is atomic; reader sees consistent dict | unit | `pytest tests/test_dashboard.py::test_snapshot_atomicity -x` | ❌ Wave 0 |
| D-03 | 9th SSE client gets 503 | unit | `pytest tests/test_dashboard.py::test_sse_client_cap -x` | ❌ Wave 0 |
| D-04 | Handler exception does not crash daemon | unit | `pytest tests/test_dashboard.py::test_handler_exception_isolated -x` | ❌ Wave 0 |
| D-04 | Port-bind failure does not crash engine | unit | `pytest tests/test_dashboard.py::test_port_bind_failure_isolated -x` | ❌ Wave 0 |
| D-07/D-08 | `/sse/fast` emits at ~10 Hz with expected schema | integration | `pytest tests/test_dashboard.py::test_sse_fast_schema -x` | ❌ Wave 0 |
| D-08 | `/sse/slow` emits at ~1 Hz with expected schema | integration | `pytest tests/test_dashboard.py::test_sse_slow_schema -x` | ❌ Wave 0 |
| D-09 | `/sse/events` sends last 10 on connect, then live | integration | `pytest tests/test_dashboard.py::test_sse_events_initial_and_live -x` | ❌ Wave 0 |
| D-15/D-16 | MBTiles tile served with correct PNG bytes; Y-flip correct | unit | `pytest tests/test_dashboard.py::test_tiles_y_flip -x` | ❌ Wave 0 |
| D-16 | Missing tile returns 404 | unit | `pytest tests/test_dashboard.py::test_tile_404 -x` | ❌ Wave 0 |
| D-19 | Pre-download tool: idempotent re-run skips existing tiles | unit | `pytest tests/test_download_tiles.py::test_idempotent -x` | ❌ Wave 0 |
| D-19 | Tool walks route corridor at requested zoom range | unit | `pytest tests/test_download_tiles.py::test_corridor_envelope -x` | ❌ Wave 0 |
| D-10/D-11 | Frontend renders without console errors | manual | manual smoke on Pi kiosk | n/a |
| D-20 | Auto-recentre after 10 s idle | manual | manual smoke | n/a |

### Sampling Rate

- **Per task commit:** `pytest tests/test_dashboard.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green plus a manual kiosk smoke before `/gsd:verify-work`. The map and gauge are visual; some validation is unavoidably eyeballs.

### Wave 0 Gaps

- [ ] `tests/test_dashboard.py` — covers D-01..D-16 except manual items
- [ ] `tests/test_download_tiles.py` — covers D-19
- [ ] `tests/conftest.py` — add a fixture that builds a tiny in-memory MBTiles file with one known-bytes PNG so tile tests don't need a real tile dump
- [ ] No framework install needed; pytest already present

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flask + gevent for embedded web in Python daemons | FastAPI + uvicorn programmatic | ~2020 onward | Async-native, type-friendly, smaller footprint, better SSE story |
| Custom SSE generators | sse-starlette | 2021+ | Disconnect detection and ping handling are not worth re-implementing |
| MBTiles | PMTiles for vector | 2022+ | PMTiles wins for vector tiles served over HTTP. MBTiles still wins for self-served raster, which is what we need. |
| Tailwind CLI requiring Node | Tailwind standalone binary | 2022+ | No Node toolchain needed. One binary, one command, commit the output. |

**Deprecated/outdated:** Nothing in the locked stack is deprecated. uvloop is "optional" rather than "deprecated" — pure-asyncio loop is fine for this workload.

## Open Questions

1. **Where exactly does the snapshot update hook live in the existing sampler/engine?**
   - What we know: `UnifiedEngine` orchestrates both the high-rate sampler and the existing services.
   - What's unclear: whether the cleanest insertion point is inside `HighRateSampler`'s loop or in the engine's per-sample callback.
   - Recommendation: planner inspects `events/sampler.py` and `events/engine.py` during planning and picks the insertion point that requires the fewest changes to the sampler. Strong preference for the engine callback so the sampler stays untouched.

2. **What is the right `event_storage` API to fetch the last 10 events on `/sse/events` connect?**
   - What we know: `EventStorage` exists in `events/storage.py` and already powers the public `events.json`.
   - What's unclear: whether there's a "last N events" query or whether one needs to be added.
   - Recommendation: planner reads `events/storage.py` during planning. If a `recent(n)` method doesn't exist, add one — it's a 5-line SELECT.

3. **Does `config/config.yaml` already have a `data_dir` key the dashboard can reuse for the MBTiles path?**
   - What we know: collectors and storage use a configured data directory.
   - What's unclear: exact key name and default.
   - Recommendation: planner checks `utils/config.py` and reuses the existing key. Add a `dashboard.mbtiles_path` that defaults to `{data_dir}/tiles/rally.mbtiles`.

4. **Tailwind classes used in index.html — full Tailwind, or just a small subset?**
   - What we know: the layout is straightforward (top bar, main split, bottom strip, mobile reflow).
   - What's unclear: whether to compile a full Tailwind output (~30 KB) or hand-pick a minimal class set.
   - Recommendation: build full Tailwind output once with `--minify`. 30 KB is irrelevant on a Pi serving over wifi. Saves bikeshedding.

## Sources

### Primary (HIGH confidence)

- FastAPI docs — embedded server section, https://www.uvicorn.org/#config-and-server-instance
- uvicorn source `uvicorn/server.py` — `install_signal_handlers` method, documented escape hatch
- MBTiles 1.3 spec — https://github.com/mapbox/mbtiles-spec/blob/master/1.3/spec.md
- OSM Slippy Map tile name conventions — https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
- sse-starlette README — https://github.com/sysid/sse-starlette
- Leaflet docs — https://leafletjs.com/reference.html
- Project files: `src/shitbox/events/engine.py`, `src/shitbox/utils/config.py`, `src/shitbox/sync/batch_sync.py` (add-a-service pattern), `CLAUDE.md`, `pyproject.toml`

### Secondary (MEDIUM confidence)

- Tailwind standalone binary install + usage — https://tailwindcss.com/blog/standalone-cli
- Common patterns for embedding uvicorn in non-web apps — verified across multiple OSS projects (gradio, jupyterlab-server)

### Tertiary (LOW confidence)

- None. Everything in this research is verified against either the project source, official docs, or well-trodden patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — FastAPI + uvicorn + sse-starlette is a conventional, well-documented combination already in widespread use
- Architecture: HIGH for the snapshot/SSE/MBTiles patterns; MEDIUM for the exact engine integration point pending a quick read of `events/engine.py` during planning
- Pitfalls: HIGH — every pitfall listed is one I've seen actually bite, not theoretical
- Validation: HIGH — pytest + FastAPI TestClient is the standard story

**Research date:** 2026-04-09
**Valid until:** ~2026-05-09 (30 days; FastAPI/uvicorn move slowly enough that pinned versions will still be current)
