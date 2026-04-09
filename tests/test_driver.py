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
    """GET /sse/slow payload contains an 'active_driver' key."""
    from shitbox.dashboard import snapshot

    snapshot.update_snapshot({**snapshot.read_snapshot(), "active_driver": "Tony"})

    # Stream the SSE endpoint and read the first event payload
    with client.stream("GET", "/sse/slow") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("data:"):
                payload_str = line[len("data:"):].strip()
                try:
                    payload = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                assert "active_driver" in payload, (
                    f"Expected 'active_driver' key in SSE slow payload, got: {list(payload.keys())}"
                )
                break


# ---------------------------------------------------------------------------
# DRVR-02: Driver stint tracking and statistics
# ---------------------------------------------------------------------------


def test_driver_stats(driver_storage, tmp_db: Database):
    """DriverStorage.get_stats() returns list of {driver_name, total_seconds, pct}."""
    driver_storage.set_driver("Tony")
    time.sleep(0.01)
    driver_storage.set_driver("Smithy")

    stats = driver_storage.get_stats()

    assert isinstance(stats, list)
    assert all(
        "driver_name" in r and "total_seconds" in r and "pct" in r for r in stats
    ), f"Stats rows missing required keys: {stats}"
    total_pct = sum(r["pct"] for r in stats)
    assert total_pct == pytest.approx(100.0, abs=0.5) or stats == []


def test_driver_stats_open_stint(driver_storage, tmp_db: Database):
    """A stint with ended_at=NULL still counts live time via COALESCE."""
    driver_storage.set_driver("Tony")  # open stint, never explicitly closed

    stats = driver_storage.get_stats()

    tony = next((r for r in stats if r["driver_name"] == "Tony"), None)
    assert tony is not None, "Expected Tony in stats after set_driver"
    assert tony["total_seconds"] >= 0, (
        f"Expected non-negative total_seconds for open stint, got {tony['total_seconds']}"
    )


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
