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
