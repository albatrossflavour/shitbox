"""MBTiles tile server router for the live dashboard.

Serves XYZ-oriented tile requests from a read-only MBTiles SQLite file. Two
critical details you cannot skip:

1. Connection URI uses ``file:...?mode=ro&immutable=1``. Without ``immutable=1``
   SQLite will try to create WAL/SHM files next to the MBTiles file, which
   fails on a read-only filesystem and (worse) mutates the file mtime on a
   read-only mount, breaking reproducibility. See RESEARCH Pitfall 2.

2. MBTiles stores tiles in TMS Y orientation. Browsers/Leaflet speak XYZ.
   Flip with ``tms_y = (1 << z) - 1 - y``.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Response

log = structlog.get_logger(__name__)

_local = threading.local()


def _conn(path: Path) -> sqlite3.Connection:
    """Per-thread cached read-only connection.

    CRITICAL: ``immutable=1`` prevents WAL/SHM creation. ``mode=ro`` makes the
    read-only intent explicit to SQLite.
    """
    cached: Optional[sqlite3.Connection] = getattr(_local, "conn", None)
    if cached is None:
        uri = f"file:{path}?mode=ro&immutable=1"
        _local.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        cached = _local.conn
    return cached


def make_router(mbtiles_path: Path) -> APIRouter:
    """Return a FastAPI router serving ``/tiles/{z}/{x}/{y}.png`` from MBTiles."""
    router = APIRouter()

    @router.get("/tiles/{z}/{x}/{y}.png")
    def tile(z: int, x: int, y: int) -> Response:
        # XYZ -> TMS Y flip
        tms_y = (1 << z) - 1 - y
        try:
            row = _conn(mbtiles_path).execute(
                "SELECT tile_data FROM tiles "
                "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, tms_y),
            ).fetchone()
        except sqlite3.Error as exc:
            log.warning("tile_query_failed", z=z, x=x, y=y, error=str(exc))
            raise HTTPException(status_code=404) from exc
        if row is None:
            raise HTTPException(status_code=404)
        return Response(
            content=row[0],
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return router
