"""Tests for Phase 12 logbook — storage layer and REST API."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from shitbox.storage.database import Database
from shitbox.dashboard import gps_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path):
    """Provide a fresh, connected Database in a temp directory."""
    db = Database(tmp_path / "test.db")
    db.connect()
    return db


@pytest.fixture(autouse=True)
def reset_gps_state():
    """Clear module-level GPS state between tests."""
    gps_state.clear_last_known_position()
    yield
    gps_state.clear_last_known_position()


# ---------------------------------------------------------------------------
# Task 1: Storage layer tests
# ---------------------------------------------------------------------------


def test_create_note(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"lat": 1.0, "lng": 2.0, "gps_fix_mode": 3}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    result = storage.create_note("hello")

    assert result["body"] == "hello"
    assert result["lat"] == 1.0
    assert result["lng"] == 2.0
    assert result["gps_stale"] is False

    # Verify row is in the database
    with tmp_db.transaction() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (result["id"],)).fetchone()
    assert row["body"] == "hello"
    assert row["lat"] == pytest.approx(1.0)
    assert row["lng"] == pytest.approx(2.0)
    assert row["gps_stale"] == 0


def test_note_gps_stale(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"gps_fix_mode": 0, "lat": None, "lng": None}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)

    gps_state.update_last_known_position(5.0, 6.0, time.time() - 120)
    result = storage.create_note("x")

    assert result["gps_stale"] is True
    assert result["lat"] == pytest.approx(5.0)
    assert result["lng"] == pytest.approx(6.0)

    with tmp_db.transaction() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (result["id"],)).fetchone()
    assert row["gps_stale"] == 1
    assert row["lat"] == pytest.approx(5.0)
    assert row["lng"] == pytest.approx(6.0)


def test_note_event_pin(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"lat": 0.0, "lng": 0.0, "gps_fix_mode": 1}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    result = storage.create_note("n", event_id=42)

    assert result["event_id"] == 42
    with tmp_db.transaction() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (result["id"],)).fetchone()
    assert row["event_id"] == 42


def test_create_fuel_stop(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"lat": 1.0, "lng": 2.0, "gps_fix_mode": 1}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    result = storage.create_fuel_stop(30.0, cost_aud=60.0, odometer_km=1000.0)

    assert result["volume_litres"] == pytest.approx(30.0)

    with tmp_db.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM fuel_stops WHERE id = ?", (result["id"],)
        ).fetchone()
    assert row["volume_litres"] == pytest.approx(30.0)
    assert row["cost_aud"] == pytest.approx(60.0)
    assert row["odometer_km"] == pytest.approx(1000.0)


def test_fuel_efficiency(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"lat": 0.0, "lng": 0.0, "gps_fix_mode": 1}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    storage.create_fuel_stop(30.0, odometer_km=1000.0)
    storage.create_fuel_stop(30.0, odometer_km=1300.0)
    storage.create_fuel_stop(30.0, odometer_km=1600.0)

    result = storage.list_fuel_stops()
    stops = result["stops"]

    assert stops[0]["km_per_litre"] is None  # First stop — no prior odometer
    assert stops[1]["km_per_litre"] == pytest.approx(10.0)
    assert stops[2]["km_per_litre"] == pytest.approx(10.0)
    assert result["cumulative_km_per_litre"] == pytest.approx(10.0)


def test_fuel_efficiency_no_odo(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"lat": 0.0, "lng": 0.0, "gps_fix_mode": 1}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    storage.create_fuel_stop(30.0)
    storage.create_fuel_stop(25.0)

    result = storage.list_fuel_stops()
    for stop in result["stops"]:
        assert stop["km_per_litre"] is None
    assert result["cumulative_km_per_litre"] is None


def test_fuel_json_no_cost(tmp_db):
    from shitbox.storage.logbook import LogbookStorage

    snap_fn = lambda: {"lat": 1.0, "lng": 2.0, "gps_fix_mode": 1}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    storage.create_fuel_stop(30.0, cost_aud=99.99, odometer_km=1000.0)

    rows = storage.generate_fuel_json()
    assert len(rows) == 1
    assert "cost_aud" not in rows[0]
    assert "volume_litres" in rows[0]


# ---------------------------------------------------------------------------
# Task 2: REST API tests
# ---------------------------------------------------------------------------


def _make_test_app(tmp_db, snap_fn=None):
    """Build a test FastAPI app with logbook storage wired in."""
    from pathlib import Path
    from shitbox.storage.logbook import LogbookStorage
    from shitbox.dashboard.server import build_app

    if snap_fn is None:
        snap_fn = lambda: {"lat": 1.0, "lng": 2.0, "gps_fix_mode": 1}
    storage = LogbookStorage(tmp_db, snapshot_fn=snap_fn)
    # Use a dummy mbtiles path — tiles router gracefully handles missing file
    app = build_app(mbtiles_path=Path("/dev/null"), logbook_storage=storage)
    return app


def test_api_create_note_201(tmp_db):
    app = _make_test_app(tmp_db)
    with TestClient(app) as client:
        resp = client.post("/api/notes", json={"body": "hi"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "hi"
    assert isinstance(data["gps_stale"], bool)


def test_api_create_note_validation(tmp_db):
    app = _make_test_app(tmp_db)
    with TestClient(app) as client:
        resp = client.post("/api/notes", json={})
    assert resp.status_code == 422


def test_api_create_fuel_and_list(tmp_db):
    app = _make_test_app(tmp_db)
    with TestClient(app) as client:
        r1 = client.post("/api/fuel", json={"volume_litres": 30, "odometer_km": 1000})
        assert r1.status_code == 201
        r2 = client.post("/api/fuel", json={"volume_litres": 30, "odometer_km": 1300})
        assert r2.status_code == 201
        r3 = client.get("/api/fuel")
    assert r3.status_code == 200
    data = r3.json()
    assert data["cumulative_km_per_litre"] == pytest.approx(10.0)


def test_api_gps_status(tmp_db):
    gps_state.update_last_known_position(10.0, 20.0, time.time() - 60)
    snap_fn = lambda: {"gps_fix_mode": 0, "lat": None, "lng": None}
    app = _make_test_app(tmp_db, snap_fn=snap_fn)
    with TestClient(app) as client:
        resp = client.get("/api/logbook/gps")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_fix"] is False
    assert data["gps_stale"] is True
