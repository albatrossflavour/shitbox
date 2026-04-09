"""Shared pytest fixtures for shitbox tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shitbox.events.storage import EventStorage
from shitbox.storage.database import Database

# 1x1 transparent PNG — used by Phase 10 dashboard tests as a known tile body.
_KNOWN_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
    "ae426082"
)


@pytest.fixture
def tmp_db_path(tmp_path):
    """Return a Path to a temporary SQLite file."""
    return tmp_path / "test.db"


@pytest.fixture
def db(tmp_db_path):
    """Create a connected Database instance, yield it, then close."""
    database = Database(tmp_db_path)
    database.connect()
    yield database
    database.close()


@pytest.fixture
def event_storage_dir(tmp_path):
    """Return a Path for event JSON files."""
    return tmp_path / "events"


@pytest.fixture
def event_storage(event_storage_dir):
    """Create an EventStorage instance with a temporary base directory."""
    return EventStorage(base_dir=str(event_storage_dir))


@pytest.fixture
def mbtiles_fixture(tmp_path_factory) -> Path:
    """Build a tiny real-on-disk MBTiles file with one known PNG tile.

    The path is real on disk because `file:...?mode=ro&immutable=1` URIs
    (used by the dashboard tile server) require a real file.
    """
    path = tmp_path_factory.mktemp("mbtiles") / "rally.mbtiles"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE metadata (name TEXT, value TEXT);
            CREATE TABLE tiles (
                zoom_level INTEGER,
                tile_column INTEGER,
                tile_row INTEGER,
                tile_data BLOB
            );
            CREATE UNIQUE INDEX tile_index
                ON tiles (zoom_level, tile_column, tile_row);
            """
        )
        conn.executemany(
            "INSERT INTO metadata (name, value) VALUES (?, ?)",
            [
                ("name", "test"),
                ("format", "png"),
                ("minzoom", "5"),
                ("maxzoom", "15"),
            ],
        )
        # Single known tile at zoom=5, tile_column=15, tile_row=20 (TMS Y).
        conn.execute(
            "INSERT INTO tiles (zoom_level, tile_column, tile_row, tile_data) "
            "VALUES (?, ?, ?, ?)",
            (5, 15, 20, _KNOWN_PNG),
        )
        conn.commit()
    finally:
        conn.close()
    return path
