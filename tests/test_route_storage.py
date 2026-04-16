"""Tests for RouteStorage (Phase 19 Plan 01)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shitbox.storage.database import Database
from shitbox.storage.route import RouteStorage, douglas_peucker


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "test.db"))
    db.connect()
    return db


def _insert_gps(db: Database, ts_iso: str, lat: float, lng: float) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO readings (timestamp_utc, sensor_type, latitude, longitude) "
            "VALUES (?, 'gps', ?, ?)",
            (ts_iso, lat, lng),
        )


def test_douglas_peucker_trivial_passthrough() -> None:
    assert douglas_peucker([(0.0, 0.0), (1.0, 1.0)], tolerance_m=10.0) == [(0.0, 0.0), (1.0, 1.0)]


def test_douglas_peucker_collinear_collapses() -> None:
    # Three roughly collinear points at ~10 m scale — middle point should collapse
    pts = [(0.0, 0.0), (0.00005, 0.00005), (0.0001, 0.0001)]
    out = douglas_peucker(pts, tolerance_m=10.0)
    assert out == [(0.0, 0.0), (0.0001, 0.0001)]


def test_douglas_peucker_sharp_turn_preserved() -> None:
    # 90-degree turn >> 10 m tolerance — all three corner points must stay
    pts = [(-16.0, 145.0), (-16.0, 145.01), (-16.01, 145.01)]
    out = douglas_peucker(pts, tolerance_m=10.0)
    assert len(out) == 3


def test_generate_route_json_shape(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_gps(db, "2026-05-01T01:00:00+00:00", -16.0, 145.0)
    _insert_gps(db, "2026-05-01T02:00:00+00:00", -16.01, 145.01)
    _insert_gps(db, "2026-05-02T01:00:00+00:00", -16.02, 145.02)

    payload = RouteStorage(db).generate_route_json()

    assert "generated_at" in payload
    assert "tolerance_m" in payload
    assert "days" in payload
    assert isinstance(payload["days"], dict)
    for key, val in payload["days"].items():
        # Keys must be YYYY-MM-DD
        assert len(key) == 10
        assert key[4] == "-" and key[7] == "-"
        assert "point_count" in val
        assert isinstance(val["point_count"], int)
        assert "points" in val
        assert isinstance(val["points"], list)
        for pt in val["points"]:
            assert len(pt) == 2
            assert isinstance(pt[0], float)
            assert isinstance(pt[1], float)


def test_generate_route_json_day_bucketing_uses_sydney_tz(tmp_path: Path) -> None:
    """A UTC row that is next-day in Sydney must bucket to the Sydney date."""
    db = _db(tmp_path)
    # 2026-05-01T15:30:00+00:00 = 2026-05-02 01:30 in Sydney (UTC+10)
    _insert_gps(db, "2026-05-01T15:30:00+00:00", -16.0, 145.0)

    payload = RouteStorage(db).generate_route_json()

    assert "2026-05-02" in payload["days"], (
        f"Expected Sydney-local date 2026-05-02, got keys: {list(payload['days'].keys())}"
    )


def test_generate_route_json_no_cost_field(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _insert_gps(db, "2026-05-01T01:00:00+00:00", -16.0, 145.0)

    payload = RouteStorage(db).generate_route_json()
    dumped = json.dumps(payload)

    assert "cost" not in dumped
    assert "cost_aud" not in dumped


def test_generate_route_json_empty_database(tmp_path: Path) -> None:
    db = _db(tmp_path)
    payload = RouteStorage(db).generate_route_json()

    assert "generated_at" in payload
    assert payload["days"] == {}


def test_generate_route_json_sparse_non_gps_rows_ignored(tmp_path: Path) -> None:
    db = _db(tmp_path)
    # Insert non-GPS rows — these must not appear in output
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO readings (timestamp_utc, sensor_type, accel_x) VALUES (?, 'imu', ?)",
            ("2026-05-01T01:00:00+00:00", 0.5),
        )
        conn.execute(
            "INSERT INTO readings (timestamp_utc, sensor_type, temp_celsius) VALUES (?, 'temperature', ?)",
            ("2026-05-01T01:01:00+00:00", 25.0),
        )
    # One real GPS row so days is not empty
    _insert_gps(db, "2026-05-01T01:02:00+00:00", -16.0, 145.0)

    payload = RouteStorage(db).generate_route_json()

    # Only one day, with exactly one point (the GPS row)
    assert len(payload["days"]) == 1
    day = next(iter(payload["days"].values()))
    assert day["point_count"] == 1


def test_size_budget(tmp_path: Path) -> None:
    """Synthetic 14-day rally at 1 pt/sec for 10 h/day must produce < 1 MB JSON."""
    db = _db(tmp_path)
    start = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    lat, lng = -16.0, 145.0
    step_deg = 0.00005  # ~5 m per step at -16 lat

    for day_num in range(14):
        day_start = start + timedelta(days=day_num)
        for second in range(10 * 3600):  # 36,000 points per day
            ts = (day_start + timedelta(seconds=second)).isoformat()
            lat += step_deg
            lng += step_deg
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO readings (timestamp_utc, sensor_type, latitude, longitude) "
                    "VALUES (?, 'gps', ?, ?)",
                    (ts, lat, lng),
                )

    payload = RouteStorage(db).generate_route_json()
    size = len(json.dumps(payload))
    assert size < 1_048_576, (
        f"route.json size budget exceeded ({size} bytes) — bump DP tolerance or drop per-point timestamps"
    )


def test_generated_at_is_recent_iso(tmp_path: Path) -> None:
    db = _db(tmp_path)
    payload = RouteStorage(db).generate_route_json()

    generated_at = datetime.fromisoformat(payload["generated_at"])
    now = datetime.now(timezone.utc)
    diff = abs((now - generated_at).total_seconds())
    assert diff < 5.0, f"generated_at is {diff:.1f}s away from now — expected < 5s"


def test_dp_recursion_safe_on_50k_points(tmp_path: Path) -> None:
    """50,000-point single-day input must not raise RecursionError and must reduce significantly."""
    pts = [(float(i) * 0.00001, float(i) * 0.00001) for i in range(50_000)]
    out = douglas_peucker(pts, tolerance_m=10.0)
    # Must not crash, and must reduce substantially
    assert len(out) < 5000, f"Expected < 5000 points after DP, got {len(out)}"
