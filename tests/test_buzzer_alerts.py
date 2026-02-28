"""Unit tests for buzzer alert patterns and escalation state.

Tests cover:
- Distinct tone patterns for each failure alert function
- BuzzerAlertState escalation within / outside the window
- Boot grace period suppression
- Thermal alert tone patterns (THRM-02)
"""

import time
from unittest.mock import MagicMock, call, patch

import pytest

import shitbox.capture.buzzer as buzzer_module
from shitbox.capture.buzzer import (
    BuzzerAlertState,
    beep_ffmpeg_stall,
    beep_i2c_lockup,
    beep_service_crash,
    beep_service_recovered,
    beep_thermal_critical,
    beep_thermal_recovered,
    beep_thermal_warning,
    beep_under_voltage,
    beep_watchdog_miss,
    set_boot_start_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_active_buzzer():
    """Return a mock that stands in for the PiicoDev_Buzzer instance."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Pattern tests
# ---------------------------------------------------------------------------


def test_beep_service_crash_pattern() -> None:
    """beep_service_crash plays a single 330 Hz 800 ms tone."""
    mock_buzzer = _make_active_buzzer()
    # Set boot time far enough in the past to skip grace period
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", mock_buzzer),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_service_crash()
    mock_play.assert_called_once_with([(330, 800)], name="buzzer-service-crash")


def test_beep_i2c_lockup_pattern() -> None:
    """beep_i2c_lockup plays three short 330 Hz 200 ms tones."""
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_i2c_lockup()
    mock_play.assert_called_once_with(
        [(330, 200), (330, 200), (330, 200)], name="buzzer-i2c-lockup"
    )


def test_beep_ffmpeg_stall_pattern() -> None:
    """beep_ffmpeg_stall plays two short + one long 330 Hz tones."""
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_ffmpeg_stall()
    mock_play.assert_called_once_with(
        [(330, 200), (330, 200), (330, 600)], name="buzzer-ffmpeg-stall"
    )


def test_beep_service_recovered() -> None:
    """beep_service_recovered plays a single short 880 Hz chirp."""
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_service_recovered()
    mock_play.assert_called_once_with([(880, 150)], name="buzzer-service-recovered")


# ---------------------------------------------------------------------------
# Escalation tests
# ---------------------------------------------------------------------------


def test_escalation_within_window() -> None:
    """First call returns False; second call within window returns True."""
    state = BuzzerAlertState()
    first = state.should_escalate("test-alert")
    second = state.should_escalate("test-alert")
    assert first is False
    assert second is True


def test_no_escalation_after_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second call after the escalation window expires returns False."""
    state = BuzzerAlertState()
    state.should_escalate("test-alert")  # records first timestamp

    # Advance time past the window
    real_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + 301)

    result = state.should_escalate("test-alert")
    assert result is False


def test_escalation_plays_pattern_twice() -> None:
    """When escalation is triggered the tones list is concatenated with itself."""
    set_boot_start_time(0.0)
    # Pre-seed the escalation state so should_escalate returns True immediately
    state = BuzzerAlertState()
    state.should_escalate("buzzer-service-crash")  # first call → False, records time

    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", state),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_service_crash()  # should_escalate returns True → doubled pattern

    expected = [(330, 800), (330, 800)]
    mock_play.assert_called_once_with(expected, name="buzzer-service-crash")


# ---------------------------------------------------------------------------
# Boot grace period tests
# ---------------------------------------------------------------------------


def test_alerts_suppressed_during_grace() -> None:
    """Alerts play nothing while within the 30-second boot grace period."""
    set_boot_start_time(time.monotonic())  # just booted
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_service_crash()
    mock_play.assert_not_called()


def test_alerts_active_after_grace() -> None:
    """Alerts play normally once past the 30-second boot grace period."""
    set_boot_start_time(time.monotonic() - 31)  # booted 31 seconds ago
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_service_crash()
    mock_play.assert_called_once()


# ---------------------------------------------------------------------------
# Thermal alert pattern tests (THRM-02)
# ---------------------------------------------------------------------------


def test_beep_thermal_warning_pattern() -> None:
    """beep_thermal_warning plays two 500 Hz 400 ms tones."""
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_thermal_warning()
    mock_play.assert_called_once_with(
        [(500, 400), (500, 400)], name="buzzer-thermal-warning"
    )


def test_beep_thermal_critical_pattern() -> None:
    """beep_thermal_critical plays three 500 Hz 600 ms tones."""
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_thermal_critical()
    mock_play.assert_called_once_with(
        [(500, 600), (500, 600), (500, 600)], name="buzzer-thermal-critical"
    )


def test_beep_under_voltage_pattern() -> None:
    """beep_under_voltage plays four rapid 500 Hz 150 ms tones."""
    set_boot_start_time(0.0)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", BuzzerAlertState()),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_under_voltage()
    mock_play.assert_called_once_with(
        [(500, 150), (500, 150), (500, 150), (500, 150)], name="buzzer-under-voltage"
    )


def test_beep_thermal_recovered_pattern() -> None:
    """beep_thermal_recovered plays a descending pair and resets warning state."""
    set_boot_start_time(0.0)
    mock_state = MagicMock(spec=BuzzerAlertState)
    with (
        patch.object(buzzer_module, "_buzzer", _make_active_buzzer()),
        patch.object(buzzer_module, "_alert_state", mock_state),
        patch.object(buzzer_module, "_play_async") as mock_play,
    ):
        beep_thermal_recovered()
    mock_play.assert_called_once_with(
        [(880, 150), (500, 150)], name="buzzer-thermal-recovered"
    )
    mock_state.reset.assert_called_once_with("buzzer-thermal-warning")
