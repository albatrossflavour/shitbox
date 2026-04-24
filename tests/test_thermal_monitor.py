"""Test scaffold for ThermalMonitorService.

These tests cover THRM-01, THRM-02, and THRM-03 requirements.
They will fail with ImportError until Plan 02 creates
shitbox.health.thermal_monitor — this is expected and correct.
"""

import threading
from unittest.mock import patch

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
    """THRM-03: Sustained bitmask with bit 0 set triggers beep_under_voltage.

    Phase 15 PWR-01/D-02: sustain_required=2 — a single read no longer fires
    immediately. Two consecutive low-nibble-non-zero reads are required.
    """
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage") as mock_uv,
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.alerts.dashboard_push_event"),
    ):
        service._check_throttled()
        service._check_throttled()

    mock_uv.assert_called_once()
    alerts_mod.clear_state()


def test_vcgencmd_not_found_graceful() -> None:
    """THRM-03: FileNotFoundError from vcgencmd → _read_throttled returns None, no exception."""
    service = ThermalMonitorService()

    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = service._read_throttled()

    assert result is None


# ---------------------------------------------------------------------------
# DISP-04 / D-05: Alert bridge — thermal and undervoltage push to SSE
# (Wave 0 RED — passes after Task 3 wires dashboard_push_event call sites)
# ---------------------------------------------------------------------------


def test_thermal_warning_pushes_dashboard_alert() -> None:
    """DISP-04/D-05: _check_thermal() at warning threshold must call dashboard_push_event.

    This test is RED until Task 3 adds the dashboard_push_event import and call
    site in the warning branch of thermal_monitor._check_thermal.
    """
    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_sysfs_temp", return_value=72000),  # 72.0 °C — above 70 threshold
        patch("shitbox.health.thermal_monitor.beep_thermal_warning"),
        patch("shitbox.health.thermal_monitor.speak_thermal_warning"),
        patch("shitbox.health.thermal_monitor.dashboard_push_event") as mock_push,
    ):
        service._check_thermal()

    mock_push.assert_called_once()
    event = mock_push.call_args[0][0]
    assert event.get("type") == "ALERT", f"expected type='ALERT', got {event.get('type')!r}"
    assert event.get("subtype") == "THERMAL_WARNING", (
        f"expected subtype='THERMAL_WARNING', got {event.get('subtype')!r}"
    )
    assert "message" in event, "event payload missing 'message' key"
    assert "72" in str(event["message"]), (
        f"expected temperature value '72' in message, got {event['message']!r}"
    )


def test_undervoltage_pushes_dashboard_alert() -> None:
    """DISP-04/D-05: sustained _check_throttled() with bit 0 set pushes ALERT.

    Phase 15 PWR-01/D-02: emission is now owned by the alerts helper and
    gated by sustain_required=2 — two consecutive low-nibble-non-zero reads
    fire exactly one UNDERVOLTAGE push_event. Mock target is the helper's
    bound name (``shitbox.health.alerts.dashboard_push_event``) since the
    helper now owns the emission, not the thermal_monitor module.
    """
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x1),  # bit 0 = under_voltage
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.alerts.dashboard_push_event") as mock_push,
    ):
        service._check_throttled()
        service._check_throttled()

    mock_push.assert_called_once()
    event = mock_push.call_args[0][0]
    assert event.get("type") == "ALERT", f"expected type='ALERT', got {event.get('type')!r}"
    assert event.get("subtype") == "UNDERVOLTAGE", (
        f"expected subtype='UNDERVOLTAGE', got {event.get('subtype')!r}"
    )
    assert "message" in event, "event payload missing 'message' key"
    assert "UNDERVOLTAGE" in str(event["message"]), (
        f"expected 'UNDERVOLTAGE' in message, got {event['message']!r}"
    )
    alerts_mod.clear_state()


# --- Phase 15 PWR-01 / PWR-02 regressions ---


def test_pwr01_sticky_bits_ignored() -> None:
    """PWR-01/D-01: bitmask with only sticky bits 16-19 set must NOT fire."""
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    # 0x50000: bit 16 + bit 18 set — sticky throttling-occurred + sticky soft-temp-occurred.
    # Low nibble == 0 — no current undervoltage.
    with (
        patch.object(service, "_read_throttled", return_value=0x50000),
        patch("shitbox.health.thermal_monitor.beep_under_voltage") as mock_beep,
        patch("shitbox.health.thermal_monitor.speak_under_voltage") as mock_tts,
        patch("shitbox.health.alerts.dashboard_push_event") as mock_push,
    ):
        for _ in range(5):
            service._check_throttled()

    mock_push.assert_not_called()
    mock_beep.assert_not_called()
    mock_tts.assert_not_called()
    alerts_mod.clear_state()


def test_pwr01_sustain_required() -> None:
    """PWR-01/D-02: low nibble set for only 1 cycle must NOT fire (sustain_required=2)."""
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    raws = [0x1, 0x0]
    with (
        patch.object(service, "_read_throttled", side_effect=raws),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.alerts.dashboard_push_event") as mock_push,
    ):
        service._check_throttled()
        service._check_throttled()

    mock_push.assert_not_called()
    alerts_mod.clear_state()


def test_pwr01_single_read_no_fire() -> None:
    """PWR-01/D-02: a single raw=0x1 read with no follow-up must NOT fire."""
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.alerts.dashboard_push_event") as mock_push,
    ):
        service._check_throttled()

    mock_push.assert_not_called()
    alerts_mod.clear_state()


def test_pwr02_undervoltage_fires_then_recovers() -> None:
    """PWR-02/D-03: sustained active fires UNDERVOLTAGE; sustained clear fires _CLEARED."""
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    # Two cycles active (arms + fires), then two cycles clear (arms + fires recovery)
    raws = [0x1, 0x1, 0x0, 0x0]
    with (
        patch.object(service, "_read_throttled", side_effect=raws),
        patch("shitbox.health.thermal_monitor.beep_under_voltage") as mock_beep,
        patch("shitbox.health.thermal_monitor.speak_under_voltage") as mock_failure_tts,
        patch("shitbox.health.thermal_monitor.speak_power_restored") as mock_recovery_tts,
        patch("shitbox.health.alerts.dashboard_push_event") as mock_push,
    ):
        for _ in range(4):
            service._check_throttled()

    assert mock_push.call_count == 2, f"expected 2 ALERT events, got {mock_push.call_count}"
    subtypes = [call[0][0]["subtype"] for call in mock_push.call_args_list]
    messages = [call[0][0]["message"] for call in mock_push.call_args_list]
    assert subtypes == ["UNDERVOLTAGE", "UNDERVOLTAGE_CLEARED"]
    assert messages[0] == "UNDERVOLTAGE DETECTED"
    assert messages[1] == "POWER RESTORED"
    mock_failure_tts.assert_called_once()
    mock_recovery_tts.assert_called_once()
    mock_beep.assert_called_once()  # beep fires once on the failure transition
    alerts_mod.clear_state()


def test_pwr02_tts_once_on_transition() -> None:
    """PWR-02/D-12: five cycles of sustained active fire TTS exactly once."""
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage") as mock_tts,
        patch("shitbox.health.alerts.dashboard_push_event"),
    ):
        for _ in range(5):
            service._check_throttled()

    mock_tts.assert_called_once()
    alerts_mod.clear_state()


def test_pwr01_low_nibble_change_clears_sticky_gate() -> None:
    """PWR-01: the fix must not re-introduce a full-word change gate.

    Two reads of 0x50001 (sticky + current-undervoltage set) followed by
    two reads of 0x50000 (sticky stays, current clears) MUST fire exactly
    one UNDERVOLTAGE then one UNDERVOLTAGE_CLEARED — the sticky bits are
    stable across all four reads, so a full-word gate would never change
    and never fire anything.
    """
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    raws = [0x50001, 0x50001, 0x50000, 0x50000]
    with (
        patch.object(service, "_read_throttled", side_effect=raws),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_power_restored"),
        patch("shitbox.health.alerts.dashboard_push_event") as mock_push,
    ):
        for _ in range(4):
            service._check_throttled()

    assert mock_push.call_count == 2
    subtypes = [call[0][0]["subtype"] for call in mock_push.call_args_list]
    assert subtypes == ["UNDERVOLTAGE", "UNDERVOLTAGE_CLEARED"]
    alerts_mod.clear_state()
