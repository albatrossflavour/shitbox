"""Embedded uvicorn dashboard server.

Runs FastAPI on a daemon thread owned by :class:`UnifiedEngine`, following the
``BatchSyncService`` / ``CaptureSyncService`` start/stop pattern documented in
``CLAUDE.md``. Two things this module exists to prevent:

1. **uvicorn hijacking signals.** By default ``uvicorn.Server.run()`` installs
   its own SIGINT/SIGTERM handlers, which would fight the engine's existing
   signal handling and make Ctrl-C misbehave on the Pi. We override
   ``install_signal_handlers`` with a no-op. See RESEARCH Pitfall 1.

2. **Port-bind failures crashing the engine.** A stray port conflict must
   never take down the capture path (D-04). ``start()`` catches and logs
   exceptions; the server simply stays down.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from shitbox.dashboard import logbook as logbook_mod
from shitbox.dashboard import sse as sse_mod
from shitbox.dashboard.tiles import make_router as make_tiles_router

log = structlog.get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def build_app(
    mbtiles_path: Path,
    recent_events_provider: Optional[Callable[[int], List[dict]]] = None,
    logbook_storage: Optional[object] = None,
    driver_storage: Optional[object] = None,
    drivers: Optional[List[str]] = None,
    captures_path: Optional[Path] = None,
) -> FastAPI:
    """Construct the dashboard FastAPI app.

    Pure factory: no I/O, no thread, no port bind. Safe to call from tests via
    ``TestClient`` without ever touching the network stack.
    """
    app = FastAPI(title="shitbox dashboard", docs_url=None, redoc_url=None)
    app.include_router(sse_mod.router)
    app.include_router(make_tiles_router(Path(mbtiles_path)))

    if recent_events_provider is not None:
        sse_mod.set_recent_events_provider(recent_events_provider)

    if logbook_storage is not None:
        logbook_mod.set_storage(logbook_storage)  # type: ignore[arg-type]
        app.include_router(logbook_mod.router)

    if driver_storage is not None:
        from shitbox.dashboard import driver as driver_mod
        driver_mod.set_storage(driver_storage)  # type: ignore[arg-type]
        if drivers:
            driver_mod.set_drivers_roster(drivers)
        app.include_router(driver_mod.router)

    if captures_path is not None and captures_path.is_dir():
        app.mount("/captures", StaticFiles(directory=str(captures_path)), name="captures")

        timelapse_dir = captures_path / "timelapse"

        @app.get("/api/timelapse/latest")
        def timelapse_latest() -> JSONResponse:
            """Return the URL of the most recent timelapse JPEG, or null if none."""
            if not timelapse_dir.is_dir():
                return JSONResponse({"url": None})
            # Scan date subdirs newest-first, return first JPEG found
            for date_dir in sorted(timelapse_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                jpegs = sorted(date_dir.glob("timelapse_*.jpg"), reverse=True)
                if jpegs:
                    rel = jpegs[0].relative_to(captures_path)
                    return JSONResponse({"url": f"/captures/{rel}"})
            return JSONResponse({"url": None})

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        index = STATIC_DIR / "index.html"
        if index.is_file():
            @app.get("/")
            def root() -> FileResponse:
                return FileResponse(str(index))
    else:
        log.warning("dashboard_static_dir_missing", path=str(STATIC_DIR))

    return app


class DashboardServer:
    """Embedded uvicorn server running on a daemon thread.

    Lifecycle mirrors BatchSyncService: ``start()`` spawns a daemon thread and
    returns immediately; ``stop()`` signals uvicorn to shut down and joins.
    Both methods swallow exceptions so the engine's capture path is never
    harmed by dashboard trouble.
    """

    def __init__(self, host: str, port: int, app: FastAPI) -> None:
        self._host = host
        self._port = port
        self._app = app
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        try:
            config = uvicorn.Config(
                self._app,
                host=self._host,
                port=self._port,
                log_config=None,
                access_log=False,
                lifespan="off",
                loop="asyncio",
            )
            self._server = uvicorn.Server(config)
            # CRITICAL (RESEARCH Pitfall 1): stop uvicorn from installing
            # SIGINT/SIGTERM handlers that would fight UnifiedEngine's own
            # signal handling.
            self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

            def _run() -> None:
                try:
                    assert self._server is not None
                    self._server.run()
                except Exception as exc:
                    log.error("dashboard_server_crashed", error=str(exc))

            self._thread = threading.Thread(target=_run, name="dashboard", daemon=True)
            self._thread.start()
            log.info("dashboard_started", host=self._host, port=self._port)
        except Exception as exc:
            log.error("dashboard_start_failed", error=str(exc))
            self._server = None
            self._thread = None

    def stop(self) -> None:
        try:
            if self._server is not None:
                self._server.should_exit = True
            if self._thread is not None:
                self._thread.join(timeout=5.0)
            log.info("dashboard_stopped")
        except Exception as exc:
            log.error("dashboard_stop_failed", error=str(exc))


def build_dashboard_server(
    host: str,
    port: int,
    mbtiles_path: Path,
    recent_events_provider: Optional[Callable[[int], List[dict]]] = None,
    logbook_storage: Optional[object] = None,
    driver_storage: Optional[object] = None,
    drivers: Optional[List[str]] = None,
    captures_path: Optional[Path] = None,
) -> DashboardServer:
    """Convenience factory used by UnifiedEngine wiring."""
    app = build_app(
        mbtiles_path=mbtiles_path,
        recent_events_provider=recent_events_provider,
        logbook_storage=logbook_storage,
        driver_storage=driver_storage,
        drivers=drivers,
        captures_path=captures_path,
    )
    return DashboardServer(host=host, port=port, app=app)
