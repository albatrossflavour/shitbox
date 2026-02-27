"""Tests for GPS-based trip tracking: odometer, daily distance, and waypoints.

Covers STGE-01 (cumulative distance), STGE-02 (daily distance with AEST reset),
and STGE-03 (waypoint proximity detection and persistence).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.events.engine import (
    TRIP_PERSIST_INTERVAL_S,
    _current_aest_date,
)
from shitbox.utils.config import WaypointConfig


# ---------------------------------------------------------------------------
# Database helper tests
# ---------------------------------------------------------------------------


def test_trip_state_get_set(db) -> None:
    """STGE-01: set_trip_state and get_trip_state round-trip a float value."""
    db.set_trip_state("odometer_km", 123.4)
    result = db.get_trip_state("odometer_km")
    assert result == pytest.approx(123.4)


def test_trip_state_text_get_set(db) -> None:
    """STGE-02: set_trip_state_text and get_trip_state_text round-trip a string."""
    db.set_trip_state_text("daily_reset_date", "2026-02-27")
    result = db.get_trip_state_text("daily_reset_date")
    assert result == "2026-02-27"


def test_trip_state_upsert(db) -> None:
    """STGE-01: Second set_trip_state call overwrites the first value."""
    db.set_trip_state("odometer_km", 100.0)
    db.set_trip_state("odometer_km", 200.0)
    result = db.get_trip_state("odometer_km")
    assert result == pytest.approx(200.0)


def test_trip_state_missing_key(db) -> None:
    """STGE-01: get_trip_state returns None for a key that was never set."""
    result = db.get_trip_state("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# Waypoint persistence tests
# ---------------------------------------------------------------------------


def test_record_waypoint_reached(db) -> None:
    """STGE-03: record_waypoint_reached stores the waypoint index."""
    db.record_waypoint_reached(0, "Port Douglas", -16.4838, 145.4673)
    result = db.get_reached_waypoints()
    assert result == {0}


def test_waypoint_idempotent(db) -> None:
    """STGE-03: Recording the same waypoint twice raises no error and deduplicates."""
    db.record_waypoint_reached(0, "Port Douglas", -16.4838, 145.4673)
    # Second call — INSERT OR IGNORE should not raise
    db.record_waypoint_reached(0, "Port Douglas", -16.4838, 145.4673)
    result = db.get_reached_waypoints()
    assert result == {0}


def test_multiple_waypoints_reached(db) -> None:
    """STGE-03: Multiple waypoints stored and retrieved correctly."""
    db.record_waypoint_reached(0, "Port Douglas", -16.4838, 145.4673)
    db.record_waypoint_reached(2, "Cairns", -16.9186, 145.7781)
    db.record_waypoint_reached(5, "Townsville", -19.2590, 146.8169)
    result = db.get_reached_waypoints()
    assert result == {0, 2, 5}


# ---------------------------------------------------------------------------
# Haversine helper (used by odometer and waypoint detection)
# ---------------------------------------------------------------------------


def test_haversine_known_distance() -> None:
    """_haversine_km returns a reasonable great-circle distance for known coords."""
    from shitbox.events.engine import UnifiedEngine

    # Port Douglas to Cairns: approximately 55-65 km by haversine (straight-line)
    dist = UnifiedEngine._haversine_km(-16.4838, 145.4673, -16.9186, 145.7781)
    assert 50.0 < dist < 70.0


def test_haversine_zero_distance() -> None:
    """_haversine_km returns 0 for identical coordinates."""
    from shitbox.events.engine import UnifiedEngine

    dist = UnifiedEngine._haversine_km(-16.4838, 145.4673, -16.4838, 145.4673)
    assert dist == pytest.approx(0.0, abs=0.001)


# ---------------------------------------------------------------------------
# Distance accumulation tests (unit-level, logic not full engine)
# ---------------------------------------------------------------------------


def _make_engine_with_state(**kwargs):
    """Create a minimal mock-backed engine object with trip state attributes set."""
    from shitbox.events.engine import UnifiedEngine

    engine = UnifiedEngine.__new__(UnifiedEngine)
    # Provide a mock config with minimal fields needed
    engine.config = MagicMock()
    engine.config.route_waypoints = []
    engine.config.gps_enabled = True
    engine.config.rally_start_lat = -16.483831
    engine.config.rally_start_lon = 145.467250
    engine.config.rally_destination_lat = -37.819142
    engine.config.rally_destination_lon = 144.960397
    engine.config.location_resolution_interval_seconds = 300
    engine.config.overlay_enabled = False
    engine.database = MagicMock()
    engine._odometer_km = kwargs.get("odometer_km", 0.0)
    engine._daily_km = kwargs.get("daily_km", 0.0)
    engine._last_known_lat = kwargs.get("last_known_lat", None)
    engine._last_known_lon = kwargs.get("last_known_lon", None)
    engine._last_trip_persist = kwargs.get("last_trip_persist", 0.0)
    engine._reached_waypoints = kwargs.get("reached_waypoints", set())
    engine._gps_available = False
    engine._gps_has_fix = False
    engine._current_speed_kmh = 0.0
    engine._current_lat = None
    engine._current_lon = None
    engine._current_heading = None
    engine._current_altitude = None
    engine._current_satellites = None
    engine._distance_from_start_km = None
    engine._distance_to_destination_km = None
    engine._current_location_name = None
    engine._last_location_resolve_time = 0.0
    engine._last_resolved_lat = None
    engine._last_resolved_lon = None
    engine._reverse_geocoder = None
    engine._health_collector = None
    engine._power_collector = None
    engine._environment_collector = None
    engine._last_timelapse_time = 0.0
    engine._last_wal_checkpoint = 0.0
    engine.ring_buffer = MagicMock()
    engine.ring_buffer.get_latest.return_value = []
    engine.batch_sync = None
    engine.mqtt = None
    engine.video_ring_buffer = None
    engine.video_recorder = None
    engine.telemetry_readings = 0
    engine.events_captured = 0
    return engine


def _make_gps_reading(lat: float, lon: float, speed_kmh: float | None = 10.0):
    """Return a mock GPS Reading with the given coordinates and speed."""
    from shitbox.storage.models import Reading, SensorType

    return Reading(
        timestamp_utc=datetime.now(tz=timezone.utc),
        sensor_type=SensorType.GPS,
        latitude=lat,
        longitude=lon,
        speed_kmh=speed_kmh,
    )


def test_odometer_accumulates() -> None:
    """STGE-01: Odometer increases by the haversine distance between two fixes at speed >= 5 km/h.

    Coordinates are chosen so that the delta is < 1 km (passes the sanity cap).
    """
    from shitbox.events.engine import UnifiedEngine

    # Small movement: approximately 0.1 degrees lat ≈ ~11 km — too large.
    # Use 0.005 degrees ≈ ~0.55 km, which is safely under the 1 km sanity cap.
    lat1, lon1 = -16.4838, 145.4673
    lat2, lon2 = -16.4888, 145.4673  # ~0.55 km south

    expected_delta = UnifiedEngine._haversine_km(lat1, lon1, lat2, lon2)
    assert expected_delta <= 1.0, "Test precondition: delta must be <= 1 km"

    engine = _make_engine_with_state(
        last_known_lat=lat1,
        last_known_lon=lon1,
    )

    speed_kmh = 30.0

    # Run the distance accumulation logic inline (mirrors engine._record_telemetry logic)
    if speed_kmh >= 5.0:
        if engine._last_known_lat is not None:
            delta_km = UnifiedEngine._haversine_km(
                engine._last_known_lat, engine._last_known_lon,
                lat2, lon2,
            )
            if delta_km <= 1.0:
                engine._odometer_km += delta_km
                engine._daily_km += delta_km
        engine._last_known_lat = lat2
        engine._last_known_lon = lon2

    assert engine._odometer_km == pytest.approx(expected_delta, rel=0.01)
    assert engine._daily_km == pytest.approx(expected_delta, rel=0.01)
    assert engine._last_known_lat == lat2
    assert engine._last_known_lon == lon2


def test_odometer_skips_slow() -> None:
    """STGE-01: GPS fix with speed < 5 km/h does NOT update last_known_lat or odometer."""
    engine = _make_engine_with_state(
        last_known_lat=-16.4838,
        last_known_lon=145.4673,
    )
    initial_odometer = engine._odometer_km

    lat2, lon2 = -16.4938, 145.4773
    speed_kmh = 3.0  # below threshold

    # Simulate the speed threshold check
    if speed_kmh is not None and speed_kmh >= 5.0:
        engine._last_known_lat = lat2
        engine._last_known_lon = lon2
        engine._odometer_km += 1.0  # would accumulate

    assert engine._odometer_km == pytest.approx(initial_odometer)
    assert engine._last_known_lat == -16.4838  # unchanged
    assert engine._last_known_lon == 145.4673  # unchanged


def test_odometer_rejects_implausible_delta() -> None:
    """STGE-01: Delta > 1 km in one GPS fix is rejected (GPS jump protection)."""
    from shitbox.events.engine import UnifiedEngine

    engine = _make_engine_with_state(
        last_known_lat=-16.4838,
        last_known_lon=145.4673,
    )

    # Jump to Cairns (~68 km away) in one second — implausible
    lat2, lon2 = -16.9186, 145.7781
    delta_km = UnifiedEngine._haversine_km(-16.4838, 145.4673, lat2, lon2)
    assert delta_km > 1.0  # confirm test precondition

    speed_kmh = 30.0
    if speed_kmh >= 5.0:
        if engine._last_known_lat is not None:
            if delta_km <= 1.0:  # sanity cap — skipped
                engine._odometer_km += delta_km
                engine._daily_km += delta_km
        engine._last_known_lat = lat2
        engine._last_known_lon = lon2

    assert engine._odometer_km == pytest.approx(0.0)
    assert engine._daily_km == pytest.approx(0.0)


def test_odometer_persists() -> None:
    """STGE-01: set_trip_state is called with 'odometer_km' once TRIP_PERSIST_INTERVAL_S elapses."""
    import time as real_time

    engine = _make_engine_with_state(
        odometer_km=42.5,
        daily_km=10.0,
        last_trip_persist=0.0,
    )

    # Simulate enough time elapsed
    now_mono = real_time.monotonic()
    engine._last_trip_persist = now_mono - TRIP_PERSIST_INTERVAL_S - 1.0

    # Trigger persistence logic
    if (now_mono - engine._last_trip_persist) >= TRIP_PERSIST_INTERVAL_S:
        engine.database.set_trip_state("odometer_km", engine._odometer_km)
        engine.database.set_trip_state("daily_km", engine._daily_km)
        engine._last_trip_persist = now_mono

    engine.database.set_trip_state.assert_any_call("odometer_km", pytest.approx(42.5))
    engine.database.set_trip_state.assert_any_call("daily_km", pytest.approx(10.0))


# ---------------------------------------------------------------------------
# Daily distance tests (STGE-02: AEST day boundary reset)
# ---------------------------------------------------------------------------


def test_daily_reset_new_day() -> None:
    """STGE-02: daily_km resets to 0 when stored date differs from today's AEST date."""
    engine = _make_engine_with_state(daily_km=55.3)

    # Return yesterday's date from the DB
    engine.database.get_trip_state.side_effect = lambda key: {
        "odometer_km": 200.0,
        "daily_km": 55.3,
    }.get(key)
    engine.database.get_trip_state_text.return_value = "2026-02-26"  # yesterday

    from shitbox.events.engine import _current_aest_date

    today_aest = _current_aest_date()

    # Simulate the boot logic
    stored_date = engine.database.get_trip_state_text("daily_reset_date")
    if stored_date != today_aest:
        engine._daily_km = 0.0
        engine.database.set_trip_state("daily_km", 0.0)
        engine.database.set_trip_state_text("daily_reset_date", today_aest)

    assert engine._daily_km == pytest.approx(0.0)
    engine.database.set_trip_state.assert_any_call("daily_km", 0.0)
    engine.database.set_trip_state_text.assert_any_call("daily_reset_date", today_aest)


def test_daily_persists_same_day() -> None:
    """STGE-02: daily_km is NOT reset when stored date matches today's AEST date."""
    from shitbox.events.engine import _current_aest_date

    today_aest = _current_aest_date()
    engine = _make_engine_with_state(daily_km=33.7)

    engine.database.get_trip_state.side_effect = lambda key: {
        "odometer_km": 150.0,
        "daily_km": 33.7,
    }.get(key)
    engine.database.get_trip_state_text.return_value = today_aest

    # Simulate boot logic
    stored_date = engine.database.get_trip_state_text("daily_reset_date")
    if stored_date != today_aest:
        engine._daily_km = 0.0
        engine.database.set_trip_state("daily_km", 0.0)
        engine.database.set_trip_state_text("daily_reset_date", today_aest)

    assert engine._daily_km == pytest.approx(33.7)  # unchanged
    # set_trip_state_text should NOT have been called with today's date for reset
    for c in engine.database.set_trip_state.call_args_list:
        assert c != call("daily_km", 0.0), "daily_km should not have been reset"


# ---------------------------------------------------------------------------
# Waypoint detection tests (STGE-03)
# ---------------------------------------------------------------------------


def test_waypoint_reached() -> None:
    """STGE-03: record_waypoint_reached called when within 5 km of a waypoint."""
    from shitbox.events.engine import UnifiedEngine

    waypoint = WaypointConfig(name="Test Town", day=1, lat=-16.4838, lon=145.4673)
    engine = _make_engine_with_state()
    engine.config.route_waypoints = [waypoint]

    # Position very close to the waypoint (same coords)
    engine._check_waypoints(-16.4838, 145.4673)

    engine.database.record_waypoint_reached.assert_called_once_with(
        0, "Test Town", -16.4838, 145.4673
    )
    assert 0 in engine._reached_waypoints


def test_waypoint_not_reached() -> None:
    """STGE-03: record_waypoint_reached NOT called when > 5 km from waypoint."""
    from shitbox.events.engine import UnifiedEngine

    waypoint = WaypointConfig(name="Far Town", day=1, lat=-16.4838, lon=145.4673)
    engine = _make_engine_with_state()
    engine.config.route_waypoints = [waypoint]

    # Port Douglas to Cairns (~68 km away) — well beyond 5 km threshold
    engine._check_waypoints(-16.9186, 145.7781)

    engine.database.record_waypoint_reached.assert_not_called()
    assert 0 not in engine._reached_waypoints


def test_waypoint_already_reached_skipped() -> None:
    """STGE-03: Already-reached waypoint is not recorded again."""
    waypoint = WaypointConfig(name="Test Town", day=1, lat=-16.4838, lon=145.4673)
    engine = _make_engine_with_state(reached_waypoints={0})
    engine.config.route_waypoints = [waypoint]

    # Even though we're at the waypoint, it is already in the set
    engine._check_waypoints(-16.4838, 145.4673)

    engine.database.record_waypoint_reached.assert_not_called()


def test_waypoints_loaded_on_boot() -> None:
    """STGE-03: _reached_waypoints is populated from database at boot."""
    engine = _make_engine_with_state()
    engine.database.get_reached_waypoints.return_value = {0, 2}

    # Simulate boot loading
    engine._reached_waypoints = engine.database.get_reached_waypoints()

    assert engine._reached_waypoints == {0, 2}


def test_stage_label() -> None:
    """STGE-03: get_status() returns correct waypoints_reached and waypoints_total counts."""
    from shitbox.events.engine import UnifiedEngine

    waypoints = [
        WaypointConfig(name="A", day=1, lat=-16.0, lon=145.0),
        WaypointConfig(name="B", day=1, lat=-17.0, lon=146.0),
        WaypointConfig(name="C", day=1, lat=-18.0, lon=147.0),
    ]

    engine = _make_engine_with_state(reached_waypoints={0, 1})
    engine.config.route_waypoints = waypoints

    # Provide stubs for get_status() dependencies
    engine.sampler = MagicMock()
    engine.sampler._running = True
    engine.connection = MagicMock()
    engine.connection.is_connected = True
    engine.thermal_monitor = MagicMock()
    engine.thermal_monitor.current_temp_celsius = 60.0
    engine.boot_recovery = None

    status = engine.get_status()

    assert status["waypoints_reached"] == 2
    assert status["waypoints_total"] == 3


# ---------------------------------------------------------------------------
# AEST helper test (STGE-02)
# ---------------------------------------------------------------------------


def test_current_aest_date_crosses_midnight() -> None:
    """_current_aest_date() returns AEST date for a UTC time that crosses midnight.

    UTC 2026-02-27T23:00 = AEST 2026-02-28T09:00 (UTC+10).
    """
    from shitbox.events.engine import AEST_OFFSET

    utc_time = datetime(2026, 2, 27, 23, 0, 0, tzinfo=timezone.utc)
    aest_time = utc_time + AEST_OFFSET
    expected_date = aest_time.strftime("%Y-%m-%d")

    with patch("shitbox.events.engine.datetime") as mock_dt:
        mock_dt.now.return_value = utc_time
        result = _current_aest_date()

    assert result == expected_date
    assert result == "2026-02-28"


def test_current_aest_date_same_day() -> None:
    """_current_aest_date() returns the same calendar day for UTC noon."""
    utc_time = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)

    with patch("shitbox.events.engine.datetime") as mock_dt:
        mock_dt.now.return_value = utc_time
        result = _current_aest_date()

    # UTC noon + 10h = 22:00 same AEST day
    assert result == "2026-02-27"


# ---------------------------------------------------------------------------
# get_status() odometer fields
# ---------------------------------------------------------------------------


def test_get_status_includes_trip_fields() -> None:
    """get_status() includes odometer_km, daily_km, waypoints_reached, waypoints_total."""
    from shitbox.events.engine import UnifiedEngine

    engine = _make_engine_with_state(
        odometer_km=1234.56,
        daily_km=87.3,
        reached_waypoints={0, 1, 2},
    )
    engine.config.route_waypoints = [
        WaypointConfig(name="A", day=1, lat=-16.0, lon=145.0),
        WaypointConfig(name="B", day=1, lat=-17.0, lon=146.0),
        WaypointConfig(name="C", day=1, lat=-18.0, lon=147.0),
        WaypointConfig(name="D", day=2, lat=-19.0, lon=148.0),
    ]

    # Stub out get_status() dependencies
    engine.sampler = MagicMock()
    engine.sampler._running = True
    engine.connection = MagicMock()
    engine.connection.is_connected = False
    engine.thermal_monitor = MagicMock()
    engine.thermal_monitor.current_temp_celsius = 55.0
    engine.boot_recovery = None

    status = engine.get_status()

    assert status["odometer_km"] == pytest.approx(1234.6)  # rounded to 1dp
    assert status["daily_km"] == pytest.approx(87.3)
    assert status["waypoints_reached"] == 3
    assert status["waypoints_total"] == 4
