"""Unit tests for BatchSyncService._readings_to_metrics().

Tests cover lux metric emission and DS18B20 probe label generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from shitbox.storage.models import Reading, SensorType
from shitbox.sync.batch_sync import BatchSyncService


def _make_service() -> BatchSyncService:
    """Build a minimal BatchSyncService without real config or DB."""
    config = MagicMock()
    config.remote_write_url = "http://localhost:9090/api/v1/write"
    config.batch_size = 100
    config.batch_interval_seconds = 15

    db = MagicMock()
    connection_monitor = MagicMock()

    return BatchSyncService(
        config=config,
        database=db,
        connection_monitor=connection_monitor,
    )


def _ts() -> datetime:
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_lux_metric_emitted() -> None:
    """LIGHT reading with lux value produces a shitbox_lux metric tuple."""
    svc = _make_service()
    reading = Reading(
        sensor_type=SensorType.LIGHT,
        lux=42.5,
        timestamp_utc=_ts(),
    )
    metrics = svc._readings_to_metrics([reading])
    names = [m[0] for m in metrics]
    assert "shitbox_lux" in names
    lux_metric = next(m for m in metrics if m[0] == "shitbox_lux")
    assert lux_metric[2] == 42.5


def test_lux_none_produces_no_metric() -> None:
    """LIGHT reading with lux=None must not emit a shitbox_lux metric."""
    svc = _make_service()
    reading = Reading(
        sensor_type=SensorType.LIGHT,
        lux=None,
        timestamp_utc=_ts(),
    )
    metrics = svc._readings_to_metrics([reading])
    names = [m[0] for m in metrics]
    assert "shitbox_lux" not in names


def test_temp_exterior_probe_label() -> None:
    """TEMPERATURE reading with sensor_id 'exterior' gets a probe label."""
    svc = _make_service()
    reading = Reading(
        sensor_type=SensorType.TEMPERATURE,
        temp_celsius=25.0,
        sensor_id="exterior",
        timestamp_utc=_ts(),
    )
    metrics = svc._readings_to_metrics([reading])
    temp_metrics = [m for m in metrics if m[0] == "shitbox_temp"]
    assert len(temp_metrics) == 1
    labels = temp_metrics[0][1]
    assert labels.get("probe") == "exterior"
    assert temp_metrics[0][2] == 25.0


def test_temp_engine_bay_probe_label() -> None:
    """TEMPERATURE reading with sensor_id 'engine_bay' gets a probe label."""
    svc = _make_service()
    reading = Reading(
        sensor_type=SensorType.TEMPERATURE,
        temp_celsius=80.0,
        sensor_id="engine_bay",
        timestamp_utc=_ts(),
    )
    metrics = svc._readings_to_metrics([reading])
    temp_metrics = [m for m in metrics if m[0] == "shitbox_temp"]
    assert len(temp_metrics) == 1
    labels = temp_metrics[0][1]
    assert labels.get("probe") == "engine_bay"
    assert temp_metrics[0][2] == 80.0


def test_temp_no_sensor_id_backward_compat() -> None:
    """TEMPERATURE reading with sensor_id=None emits metric without probe label."""
    svc = _make_service()
    reading = Reading(
        sensor_type=SensorType.TEMPERATURE,
        temp_celsius=22.0,
        sensor_id=None,
        timestamp_utc=_ts(),
    )
    metrics = svc._readings_to_metrics([reading])
    temp_metrics = [m for m in metrics if m[0] == "shitbox_temp"]
    assert len(temp_metrics) == 1
    labels = temp_metrics[0][1]
    assert "probe" not in labels
    assert temp_metrics[0][2] == 22.0


class TestSummaryMetrics:
    """Tests for BatchSyncService._build_summary_metrics()."""

    def _make_service(self, db, event_storage=None):
        config = MagicMock()
        config.remote_write_url = "http://localhost:9090/api/v1/write"
        config.batch_size = 100
        config.batch_interval_seconds = 15
        conn = MagicMock()
        conn.is_connected = True
        return BatchSyncService(config, db, conn, event_storage=event_storage)

    def test_summary_empty_db(self, tmp_path):
        """Empty database returns zero-value metrics without raising."""
        from shitbox.storage.database import Database
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        svc = self._make_service(db)
        metrics = svc._build_summary_metrics()
        names = [m[0] for m in metrics]
        assert "shitbox_fuel_stops_total" in names
        assert "shitbox_fuel_litres_total" in names
        assert "shitbox_notes_total" in names
        assert "shitbox_active_driver" not in names

    def test_summary_fuel_counts(self, tmp_path):
        """Fuel stop count and total litres are correct."""
        from shitbox.storage.database import Database
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        conn = db._get_connection()
        conn.execute(
            "INSERT INTO fuel_stops (timestamp_utc, volume_litres) VALUES (datetime('now'), 45.5)"
        )
        conn.execute(
            "INSERT INTO fuel_stops (timestamp_utc, volume_litres) VALUES (datetime('now'), 38.2)"
        )
        conn.commit()

        svc = self._make_service(db)
        metrics = svc._build_summary_metrics()
        by_name = {m[0]: m[2] for m in metrics}

        assert by_name["shitbox_fuel_stops_total"] == 2.0
        assert abs(by_name["shitbox_fuel_litres_total"] - 83.7) < 0.01

    def test_summary_notes_count(self, tmp_path):
        """Note count metric matches rows in notes table."""
        from shitbox.storage.database import Database
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        conn = db._get_connection()
        conn.execute(
            "INSERT INTO notes (timestamp_utc, body) VALUES (datetime('now'), 'test note')"
        )
        conn.commit()

        svc = self._make_service(db)
        metrics = svc._build_summary_metrics()
        by_name = {m[0]: m[2] for m in metrics}
        assert by_name["shitbox_notes_total"] == 1.0

    def test_summary_active_driver(self, tmp_path):
        """Active driver produces shitbox_active_driver metric with name label."""
        from shitbox.storage.database import Database
        db = Database(str(tmp_path / "test.db"))
        db.connect()
        conn = db._get_connection()
        conn.execute(
            "INSERT INTO driver_stints (driver_name, started_at, created_at) "
            "VALUES ('Tony', datetime('now'), datetime('now'))"
        )
        conn.commit()

        svc = self._make_service(db)
        metrics = svc._build_summary_metrics()
        driver_metrics = [m for m in metrics if m[0] == "shitbox_active_driver"]
        assert len(driver_metrics) == 1
        assert driver_metrics[0][1].get("name") == "Tony"
        assert driver_metrics[0][2] == 1.0

    def test_summary_event_counts(self, tmp_path):
        """Event type counts are emitted when EventStorage is provided."""
        import json
        from shitbox.storage.database import Database
        from shitbox.events.storage import EventStorage
        event_dir = tmp_path / "events" / "2026-05-01"
        event_dir.mkdir(parents=True)
        (event_dir / "high_g_120000_001.json").write_text(json.dumps({"type": "HIGH_G"}))
        (event_dir / "high_g_120100_002.json").write_text(json.dumps({"type": "HIGH_G"}))
        (event_dir / "hard_brake_120200_001.json").write_text(json.dumps({"type": "HARD_BRAKE"}))

        es = EventStorage(str(tmp_path / "events"))
        db = Database(str(tmp_path / "test.db"))
        db.connect()

        svc = self._make_service(db, event_storage=es)
        metrics = svc._build_summary_metrics()
        event_metrics = {m[1].get("type"): m[2] for m in metrics if m[0] == "shitbox_events_total"}
        assert event_metrics.get("HIGH_G") == 2.0
        assert event_metrics.get("HARD_BRAKE") == 1.0
