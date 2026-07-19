"""Tests for Phase 13 driver tracking — Wave 0 test stubs.

All 8 test functions cover DRVR-01/02/03. Imports from shitbox.storage.driver
and shitbox.dashboard.driver are guarded inside fixtures so test collection
does not crash before plan 02 builds those modules.

This file intentionally runs red (or skipped) on plan 01. Green state is
achieved in plan 02/03 when the implementation is added.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import pytest

from shitbox.storage.database import Database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Database:
    """Provide a fresh, connected Database in a temp directory."""
    db = Database(tmp_path / "test.db")
    db.connect()
    return db


@pytest.fixture()
def driver_storage(tmp_db: Database):
    """Construct DriverStorage(tmp_db) — skips if plan 02 not yet built."""
    try:
        from shitbox.storage.driver import DriverStorage  # type: ignore[import]
    except ImportError:
        pytest.skip("pending plan 02 — shitbox.storage.driver not yet built")
    return DriverStorage(tmp_db)


@pytest.fixture()
def client(driver_storage, tmp_db: Database):
    """Build a test FastAPI app with driver storage wired in, roster injected."""
    try:
        from shitbox.dashboard.server import build_app  # noqa: PLC0415
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("pending plan 02 — dashboard driver router not yet wired")

    roster = ["Tony", "Smithy", "Nav"]

    try:
        from shitbox.storage.driver import DriverStorage  # type: ignore[import]
        app = build_app(
            mbtiles_path=Path("/dev/null"),
            driver_storage=driver_storage,
            drivers=roster,
        )
    except TypeError:
        pytest.skip("pending plan 02 — build_app does not yet accept driver_storage kwarg")

    return TestClient(app)


@pytest.fixture()
def event_storage(tmp_path: Path):
    """Construct EventStorage for event attribution tests."""
    from shitbox.events.storage import EventStorage

    return EventStorage(
        base_dir=str(tmp_path / "events"),
        captures_dir=str(tmp_path / "captures"),
    )


# ---------------------------------------------------------------------------
# DRVR-01: Driver selection via POST /api/driver
# ---------------------------------------------------------------------------


def test_set_driver(client):
    """POST /api/driver with a valid name returns 200 and driver_name in body."""
    response = client.post("/api/driver", json={"name": "Tony"})
    assert response.status_code == 200
    assert response.json()["driver_name"] == "Tony"


def test_set_driver_unknown_name(client):
    """POST /api/driver with a name not in the roster returns 422."""
    response = client.post("/api/driver", json={"name": "Mallory"})
    assert response.status_code == 422


def test_sse_slow_includes_active_driver(client):
    """SSE /sse/slow payload generator includes an 'active_driver' key.

    The Starlette TestClient cannot stream infinite SSE generators (it blocks
    waiting for the response to complete). Instead we drive the async generator
    directly via asyncio.run(), which proves the payload field is present
    without going through the HTTP transport.
    """
    import asyncio
    from unittest.mock import MagicMock
    from shitbox.dashboard import snapshot, sse

    snapshot.update_snapshot({**snapshot.read_snapshot(), "active_driver": "Tony"})

    async def _get_first_payload() -> dict:
        request = MagicMock()
        response = await sse.sse_slow(request)
        gen = response.body_iterator
        item = await gen.__anext__()
        await gen.aclose()
        # item is {"event": "slow", "data": "<json>"}
        return json.loads(item["data"] if isinstance(item, dict) else item.split("data: ", 1)[-1])

    payload = asyncio.run(_get_first_payload())
    assert "active_driver" in payload, (
        f"Expected 'active_driver' key in SSE slow payload, got: {list(payload.keys())}"
    )


# ---------------------------------------------------------------------------
# DRVR-02: Driver stint tracking and statistics
# ---------------------------------------------------------------------------


def _add_stint(db: Database, name: str, started_at: str, ended_at: Optional[str]) -> None:
    """Insert a driver stint directly, using the space-separated datetime('now')
    format the app writes (deliberately different from the ISO reading format)."""
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO driver_stints (driver_name, started_at, ended_at, created_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (name, started_at, ended_at),
        )


def _add_gps(db: Database, ts_iso: str, speed_kmh: float, n: int = 1) -> None:
    """Insert ``n`` GPS readings at an ISO-8601 (T + tz) timestamp and speed."""
    with db.transaction() as conn:
        conn.executemany(
            "INSERT INTO readings (timestamp_utc, sensor_type, speed_kmh) VALUES (?, 'gps', ?)",
            [(ts_iso, speed_kmh)] * n,
        )


def test_driver_stats(driver_storage, tmp_db: Database):
    """get_stats() attributes MOVING GPS samples to the active driver's stint.

    Both stints fall on the same date and use the space-separated format, while
    readings use ISO-8601 with a 'T'. A naive string compare would misattribute
    (or zero) these; this asserts the julianday comparison gets it right and that
    stationary samples (speed below threshold) are excluded.
    """
    _add_stint(tmp_db, "Tony", "2026-07-11 10:00:00", "2026-07-11 12:00:00")
    _add_stint(tmp_db, "Steve", "2026-07-11 12:00:00", "2026-07-11 14:00:00")

    _add_gps(tmp_db, "2026-07-11T10:30:00+00:00", 50.0, n=100)  # Tony, moving
    _add_gps(tmp_db, "2026-07-11T10:40:00+00:00", 0.0, n=30)    # Tony, parked -> excluded
    _add_gps(tmp_db, "2026-07-11T12:30:00+00:00", 60.0, n=40)   # Steve, moving
    _add_gps(tmp_db, "2026-07-11T09:00:00+00:00", 80.0, n=99)   # before any stint -> unattributed

    stats = driver_storage.get_stats()

    assert all(
        "driver_name" in r and "total_seconds" in r and "pct" in r for r in stats
    ), f"Stats rows missing required keys: {stats}"
    by_name = {r["driver_name"]: r for r in stats}
    assert by_name["Tony"]["total_seconds"] == 100
    assert by_name["Steve"]["total_seconds"] == 40
    assert by_name["Tony"]["pct"] == pytest.approx(71.4, abs=0.2)
    assert sum(r["pct"] for r in stats) == pytest.approx(100.0, abs=0.5)


def test_driver_stats_rally_window(tmp_db: Database):
    """A configured rally window bounds hours to Sydney (UTC+10) dates in [start, end]."""
    from shitbox.storage.driver import DriverStorage

    _add_stint(tmp_db, "Tony", "2026-07-11 00:00:00", None)  # open, spans everything
    _add_gps(tmp_db, "2026-07-12T03:00:00+00:00", 50.0, n=60)  # 07-12 Sydney -> in window
    _add_gps(tmp_db, "2026-07-18T03:00:00+00:00", 50.0, n=99)  # 07-18 Sydney -> out
    _add_gps(tmp_db, "2026-07-17T14:30:00+00:00", 50.0, n=7)   # 00:30 07-18 Sydney -> out (tz boundary)

    ds = DriverStorage(tmp_db, rally_start_date="2026-07-11", rally_end_date="2026-07-17")
    tony = next(r for r in ds.get_stats() if r["driver_name"] == "Tony")
    assert tony["total_seconds"] == 60, (
        f"Expected only the 60 in-window samples, got {tony['total_seconds']}"
    )


def test_driver_stats_open_stint(driver_storage, tmp_db: Database):
    """An open stint (ended_at=NULL) counts its moving samples, bounded to now().

    Unlike the old wall-clock behaviour, an open stint cannot bleed time — it
    only accrues seconds where moving GPS samples actually exist within it.
    """
    _add_stint(tmp_db, "Tony", "2026-07-11 10:00:00", None)  # open, never closed
    _add_gps(tmp_db, "2026-07-11T10:30:00+00:00", 45.0, n=25)

    stats = driver_storage.get_stats()

    tony = next((r for r in stats if r["driver_name"] == "Tony"), None)
    assert tony is not None, "Expected Tony in stats for open stint with moving samples"
    assert tony["total_seconds"] == 25


def test_stint_switch_closes_previous(driver_storage, tmp_db: Database):
    """Calling set_driver twice leaves exactly one open stint (ended_at IS NULL)."""
    driver_storage.set_driver("Tony")
    driver_storage.set_driver("Smithy")

    with tmp_db.transaction() as conn:
        open_count = conn.execute(
            "SELECT COUNT(*) AS c FROM driver_stints WHERE ended_at IS NULL"
        ).fetchone()["c"]

    assert open_count == 1, (
        f"Expected exactly 1 open stint after switch, got {open_count}"
    )


# ---------------------------------------------------------------------------
# DRVR-03: Event attribution
# ---------------------------------------------------------------------------


def test_event_attribution(event_storage, tmp_path: Path):
    """EventStorage.save_event(..., driver_name='Tony') writes driver_name to JSON."""
    from shitbox.events.detector import Event, EventType

    now = time.time()
    event = Event(
        event_type=EventType.HIGH_G,
        start_time=now,
        end_time=now + 1.0,
        peak_value=2.5,
        peak_ax=2.5,
        peak_ay=0.1,
        peak_az=0.0,
    )

    try:
        json_path, _ = event_storage.save_event(event, driver_name="Tony")
    except TypeError:
        pytest.skip("pending plan 03 — save_event does not yet accept driver_name kwarg")

    with open(json_path) as f:
        metadata = json.load(f)

    assert metadata.get("driver_name") == "Tony", (
        f"Expected driver_name='Tony' in event metadata, got: {metadata.get('driver_name')}"
    )


def test_event_attribution_no_driver(event_storage, tmp_path: Path):
    """save_event() with no driver_name omits driver_name from JSON (or sets to None)."""
    from shitbox.events.detector import Event, EventType

    now = time.time()
    event = Event(
        event_type=EventType.HARD_BRAKE,
        start_time=now,
        end_time=now + 0.5,
        peak_value=1.8,
        peak_ax=1.8,
        peak_ay=0.0,
        peak_az=0.0,
    )

    # Call save_event without driver_name — current signature doesn't have it yet,
    # so this should work already (no TypeError expected here)
    json_path, _ = event_storage.save_event(event)

    with open(json_path) as f:
        metadata = json.load(f)

    # driver_name should be absent or None when not provided
    assert metadata.get("driver_name") is None, (
        f"Expected driver_name absent/None in event metadata, got: {metadata.get('driver_name')}"
    )
