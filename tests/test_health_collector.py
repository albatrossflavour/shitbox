"""Tests for HealthCollector and the new system Prometheus metrics.

Covers HLTH-01: CPU temp, disk %, sync backlog, throttle state appear
in Grafana when WireGuard is available.
"""

import shutil
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from shitbox.health.health_collector import HealthCollector
from shitbox.health.thermal_monitor import ThermalMonitorService
from shitbox.storage.models import Reading, SensorType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thermal(temp: float | None = 65.0, throttle: int | None = 0) -> MagicMock:
    """Create a MagicMock standing in for ThermalMonitorService with specified values."""
    svc = MagicMock(spec=ThermalMonitorService)
    type(svc).current_temp_celsius = property(lambda self: temp)
    type(svc).last_throttled_raw = property(lambda self: throttle)
    return svc


_FAKE_DISK = shutil.disk_usage.__class__  # namedtuple type


def _disk_usage(used: int, total: int) -> object:
    """Return a fake disk_usage namedtuple."""
    import collections
    DiskUsage = collections.namedtuple("DiskUsage", ["total", "used", "free"])
    return DiskUsage(total=total, used=used, free=total - used)


# ---------------------------------------------------------------------------
# HLTH-01: HealthCollector assembles all four fields
# ---------------------------------------------------------------------------


def test_health_collector_all_fields(tmp_path) -> None:
    """collect() returns a Reading with cpu_temp, disk_pct, sync_backlog, throttle_flags."""
    thermal = _make_thermal(temp=65.0, throttle=0)
    batch_sync = MagicMock()
    batch_sync.get_backlog_count.return_value = 42

    fake_disk = _disk_usage(used=5_000_000_000, total=20_000_000_000)

    collector = HealthCollector(
        thermal_monitor=thermal,
        batch_sync=batch_sync,
        data_dir=str(tmp_path),
    )

    with patch("shutil.disk_usage", return_value=fake_disk):
        reading = collector.collect()

    assert reading is not None
    assert reading.sensor_type == SensorType.SYSTEM
    assert reading.cpu_temp_celsius == 65.0
    assert reading.disk_percent == pytest.approx(25.0)
    assert reading.sync_backlog == 42
    assert reading.throttle_flags == 0


def test_health_collector_no_batch_sync(tmp_path) -> None:
    """batch_sync=None → sync_backlog is 0."""
    thermal = _make_thermal(temp=55.0, throttle=0)
    fake_disk = _disk_usage(used=1_000_000_000, total=10_000_000_000)

    collector = HealthCollector(
        thermal_monitor=thermal,
        batch_sync=None,
        data_dir=str(tmp_path),
    )

    with patch("shutil.disk_usage", return_value=fake_disk):
        reading = collector.collect()

    assert reading is not None
    assert reading.sync_backlog == 0


def test_health_collector_no_temp(tmp_path) -> None:
    """current_temp_celsius=None → cpu_temp_celsius is None, other fields still populated."""
    thermal = _make_thermal(temp=None, throttle=5)
    fake_disk = _disk_usage(used=2_000_000_000, total=10_000_000_000)

    collector = HealthCollector(
        thermal_monitor=thermal,
        batch_sync=None,
        data_dir=str(tmp_path),
    )

    with patch("shutil.disk_usage", return_value=fake_disk):
        reading = collector.collect()

    assert reading is not None
    assert reading.cpu_temp_celsius is None
    assert reading.disk_percent == pytest.approx(20.0)
    assert reading.throttle_flags == 5


def test_health_collector_graceful_disk_failure(tmp_path) -> None:
    """OSError from disk_usage → collect() returns None gracefully."""
    thermal = _make_thermal(temp=60.0, throttle=0)
    collector = HealthCollector(
        thermal_monitor=thermal,
        batch_sync=None,
        data_dir=str(tmp_path),
    )

    with patch("shutil.disk_usage", side_effect=OSError("no device")):
        reading = collector.collect()

    # OSError (not FileNotFoundError) → disk_percent is None, reading still returned
    assert reading is not None
    assert reading.disk_percent is None
    assert reading.cpu_temp_celsius == 60.0


def test_health_collector_missing_path_returns_none() -> None:
    """FileNotFoundError from disk_usage → collect() returns None (path never existed)."""
    thermal = _make_thermal(temp=60.0, throttle=0)
    collector = HealthCollector(
        thermal_monitor=thermal,
        batch_sync=None,
        data_dir="/nonexistent/path/for/test",
    )

    with patch("shutil.disk_usage", side_effect=FileNotFoundError("no path")):
        reading = collector.collect()

    assert reading is None


# ---------------------------------------------------------------------------
# HLTH-01: Prometheus metric emission for new system fields
# ---------------------------------------------------------------------------


def test_health_metrics_in_prometheus() -> None:
    """_readings_to_metrics() emits shitbox_disk_pct, shitbox_sync_backlog, shitbox_throttle_flags."""
    from unittest.mock import MagicMock

    from shitbox.sync.batch_sync import BatchSyncService

    # Construct a minimal BatchSyncService (no real network calls)
    svc = BatchSyncService.__new__(BatchSyncService)

    reading = Reading(
        timestamp_utc=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        sensor_type=SensorType.SYSTEM,
        cpu_temp_celsius=72.5,
        disk_percent=55.3,
        sync_backlog=100,
        throttle_flags=0x50005,
    )

    metrics = svc._readings_to_metrics([reading])
    metric_names = [m[0] for m in metrics]

    assert "shitbox_cpu_temp" in metric_names
    assert "shitbox_disk_pct" in metric_names
    assert "shitbox_sync_backlog" in metric_names
    assert "shitbox_throttle_flags" in metric_names

    # Verify values
    by_name = {m[0]: m[2] for m in metrics}
    assert by_name["shitbox_cpu_temp"] == pytest.approx(72.5)
    assert by_name["shitbox_disk_pct"] == pytest.approx(55.3)
    assert by_name["shitbox_sync_backlog"] == pytest.approx(100.0)
    assert by_name["shitbox_throttle_flags"] == pytest.approx(float(0x50005))


def test_health_metrics_none_fields_omitted() -> None:
    """Fields that are None are not emitted as Prometheus metrics."""
    from shitbox.sync.batch_sync import BatchSyncService

    svc = BatchSyncService.__new__(BatchSyncService)

    reading = Reading(
        timestamp_utc=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        sensor_type=SensorType.SYSTEM,
        cpu_temp_celsius=65.0,
        disk_percent=None,
        sync_backlog=None,
        throttle_flags=None,
    )

    metrics = svc._readings_to_metrics([reading])
    metric_names = [m[0] for m in metrics]

    assert "shitbox_cpu_temp" in metric_names
    assert "shitbox_disk_pct" not in metric_names
    assert "shitbox_sync_backlog" not in metric_names
    assert "shitbox_throttle_flags" not in metric_names


# ---------------------------------------------------------------------------
# ThermalMonitorService: last_throttled_raw property
# ---------------------------------------------------------------------------


def test_last_throttled_raw_property() -> None:
    """last_throttled_raw returns None before first read, then the last bitmask."""
    svc = ThermalMonitorService()

    # Before any throttle check
    assert svc.last_throttled_raw is None

    # Simulate _check_throttled updating the internal state
    with (
        patch.object(svc, "_read_throttled", return_value=0x50005),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.log"),
    ):
        svc._check_throttled()

    assert svc.last_throttled_raw == 0x50005


def test_last_throttled_raw_no_change_preserves_value() -> None:
    """Same bitmask returned twice — value preserved, no spurious reset."""
    svc = ThermalMonitorService()

    with (
        patch.object(svc, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.log"),
    ):
        svc._check_throttled()

    first = svc.last_throttled_raw

    with (
        patch.object(svc, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.log"),
    ):
        svc._check_throttled()

    assert svc.last_throttled_raw == first == 0x1
