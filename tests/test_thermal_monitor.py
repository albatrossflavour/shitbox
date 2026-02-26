"""Test scaffold for ThermalMonitorService.

These tests cover THRM-01, THRM-02, and THRM-03 requirements.
They will fail with ImportError until Plan 02 creates
shitbox.health.thermal_monitor — this is expected and correct.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from shitbox.health.thermal_monitor import ThermalMonitorService  # type: ignore[import]


# ---------------------------------------------------------------------------
# THRM-01: Temperature published to shared state
# ---------------------------------------------------------------------------


def test_temp_published_to_shared_state() -> None:
    """THRM-01: Mock sysfs 55000 raw value → current_temp_celsius == 55.0."""
    service = ThermalMonitorService()
    with patch.object(service, "_read_sysfs_temp", return_value=55000):
        service._check_thermal()
    assert service.current_temp_celsius == 55.0


def test_temp_thread_safe() -> None:
    """THRM-01: Concurrent reads/writes to current_temp_celsius raise no exceptions."""
    service = ThermalMonitorService()
    errors: list[Exception] = []

    def writer() -> None:
        for i in range(100):
            try:
                with patch.object(service, "_read_sysfs_temp", return_value=55000 + i * 1000):
                    service._check_thermal()
            except Exception as exc:
                errors.append(exc)

    def reader() -> None:
        for _ in range(100):
            try:
                _ = service.current_temp_celsius
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# THRM-02: Warning / critical / recovery thresholds
# ---------------------------------------------------------------------------


def test_warning_fires_at_threshold() -> None:
    """THRM-02: 70C triggers beep_thermal_warning."""
    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_sysfs_temp", return_value=70000),
        patch("shitbox.health.thermal_monitor.beep_thermal_warning") as mock_warn,
    ):
        service._check_thermal()
    mock_warn.assert_called_once()


def test_hysteresis_suppresses_below_rearm() -> None:
    """THRM-02: Warning fires at 70C, suppressed at 69C, re-arms at 66C, fires again at 70C."""
    service = ThermalMonitorService()
    with patch("shitbox.health.thermal_monitor.beep_thermal_warning") as mock_warn:
        # First trigger at 70C
        with patch.object(service, "_read_sysfs_temp", return_value=70000):
            service._check_thermal()

        # 69C — warning disarmed, still above re-arm threshold (65C)
        with patch.object(service, "_read_sysfs_temp", return_value=69000):
            service._check_thermal()

        # 66C — still suppressed, just above re-arm threshold
        with patch.object(service, "_read_sysfs_temp", return_value=66000):
            service._check_thermal()

        # 65C — at or below re-arm threshold, re-arms
        with patch.object(service, "_read_sysfs_temp", return_value=65000):
            service._check_thermal()

        # 70C again — fires a second time
        with patch.object(service, "_read_sysfs_temp", return_value=70000):
            service._check_thermal()

    assert mock_warn.call_count == 2


def test_critical_fires_independently() -> None:
    """THRM-02: 80C triggers beep_thermal_critical; warning not re-fired if disarmed."""
    service = ThermalMonitorService()
    with (
        patch("shitbox.health.thermal_monitor.beep_thermal_warning") as mock_warn,
        patch("shitbox.health.thermal_monitor.beep_thermal_critical") as mock_crit,
    ):
        # Fire warning at 70C
        with patch.object(service, "_read_sysfs_temp", return_value=70000):
            service._check_thermal()

        # Jump straight to 80C — critical should fire, warning should not re-fire
        with patch.object(service, "_read_sysfs_temp", return_value=80000):
            service._check_thermal()

    mock_crit.assert_called_once()
    mock_warn.assert_called_once()


def test_recovery_beep_on_cooldown() -> None:
    """THRM-02: beep_thermal_recovered fires when temp drops below re-arm threshold."""
    service = ThermalMonitorService()
    with (
        patch("shitbox.health.thermal_monitor.beep_thermal_warning"),
        patch("shitbox.health.thermal_monitor.beep_thermal_recovered") as mock_rec,
    ):
        # Fire warning
        with patch.object(service, "_read_sysfs_temp", return_value=70000):
            service._check_thermal()

        # Cool to 65C — should trigger recovery beep
        with patch.object(service, "_read_sysfs_temp", return_value=65000):
            service._check_thermal()

    mock_rec.assert_called_once()


# ---------------------------------------------------------------------------
# THRM-03: Throttle / under-voltage detection
# ---------------------------------------------------------------------------


def test_throttle_logs_only_on_change() -> None:
    """THRM-03: Same throttle bitmask emits log only once."""
    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x50005),
        patch("shitbox.health.thermal_monitor.log") as mock_log,
    ):
        service._check_throttled()
        service._check_throttled()

    # log.warning (or log.info) should have been called exactly once for the bitmask
    assert mock_log.warning.call_count + mock_log.info.call_count == 1


def test_under_voltage_triggers_buzzer() -> None:
    """THRM-03: Bitmask with bit 0 set triggers beep_under_voltage."""
    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage") as mock_uv,
    ):
        service._check_throttled()

    mock_uv.assert_called_once()


def test_vcgencmd_not_found_graceful() -> None:
    """THRM-03: FileNotFoundError from vcgencmd → _read_throttled returns None, no exception."""
    service = ThermalMonitorService()
    import subprocess

    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = service._read_throttled()

    assert result is None
