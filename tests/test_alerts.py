"""Unit tests for src/shitbox/health/alerts.py — Phase 15 helper.

Covers sustain + once-on-transition + recovery semantics + snapshot shape +
capture-path-sacred constraints (no threading.Lock on the alert path) +
TTS resilience + recovery_subtype rewrite.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_alerts_state():
    """Reset alerts module state before and after each test."""
    from shitbox.health import alerts

    alerts.clear_state()
    yield
    alerts.clear_state()


def test_fire_alert_once_on_transition() -> None:
    """sustain_required=2: first arms, second fires, third does not re-fire."""
    from shitbox.health import alerts

    tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", tts, sustain_required=2)
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", tts, sustain_required=2)
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", tts, sustain_required=2)

    assert mock_push.call_count == 1
    event = mock_push.call_args[0][0]
    assert event["type"] == "ALERT"
    assert event["subtype"] == "UNDERVOLTAGE"
    assert "UNDERVOLTAGE" in event["message"]
    assert isinstance(event["ts"], float)
    tts.assert_called_once()


def test_fire_recovery_once_on_transition() -> None:
    """After fire_alert has fired, two consecutive active=False → recovery fires once."""
    from shitbox.health import alerts

    alert_tts = MagicMock()
    recovery_tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_alert("UV", True, "UV", alert_tts, sustain_required=2)
        alerts.fire_alert("UV", True, "UV", alert_tts, sustain_required=2)
        alerts.fire_recovery("UV", False, "RESTORED", recovery_tts, sustain_required=2)
        alerts.fire_recovery("UV", False, "RESTORED", recovery_tts, sustain_required=2)
        # Extra call should NOT re-fire recovery.
        alerts.fire_recovery("UV", False, "RESTORED", recovery_tts, sustain_required=2)

    # 2 push events total: one alert, one recovery.
    assert mock_push.call_count == 2
    subtypes = [c[0][0]["subtype"] for c in mock_push.call_args_list]
    assert subtypes == ["UV", "UV"]  # no recovery_subtype passed → falls back to key
    recovery_tts.assert_called_once()


def test_fire_recovery_emits_with_recovery_subtype() -> None:
    """recovery_subtype rewrites the emitted event subtype; bookkeeping stays on the base key."""
    from shitbox.health import alerts

    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", sustain_required=2)
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", sustain_required=2)
        alerts.fire_recovery(
            "UNDERVOLTAGE",
            False,
            "POWER RESTORED",
            sustain_required=2,
            recovery_subtype="UNDERVOLTAGE_CLEARED",
        )
        alerts.fire_recovery(
            "UNDERVOLTAGE",
            False,
            "POWER RESTORED",
            sustain_required=2,
            recovery_subtype="UNDERVOLTAGE_CLEARED",
        )

    subtypes = [c[0][0]["subtype"] for c in mock_push.call_args_list]
    messages = [c[0][0]["message"] for c in mock_push.call_args_list]
    assert subtypes == ["UNDERVOLTAGE", "UNDERVOLTAGE_CLEARED"]
    assert messages == ["UNDERVOLTAGE DETECTED", "POWER RESTORED"]
    # Bookkeeping stays on the base key
    snap = alerts.snapshot()
    assert "UNDERVOLTAGE" in snap
    assert snap["UNDERVOLTAGE"].fired is False


def test_sustain_resets_on_break() -> None:
    """active=True, active=False, active=True with sustain_required=2 → no fire."""
    from shitbox.health import alerts

    tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_alert("UV", True, "UV", tts, sustain_required=2)
        alerts.fire_alert("UV", False, "UV", tts, sustain_required=2)  # break
        alerts.fire_alert("UV", True, "UV", tts, sustain_required=2)   # rearm from 1

    assert mock_push.call_count == 0
    tts.assert_not_called()


def test_snapshot_contains_all_tracked() -> None:
    """snapshot() returns state dict with subtype key after first observation."""
    from shitbox.health import alerts

    alerts.fire_alert("UNDERVOLTAGE", True, "UV", lambda: None, sustain_required=2)
    snap = alerts.snapshot()
    assert "UNDERVOLTAGE" in snap
    assert snap["UNDERVOLTAGE"].active_sustain_count == 1
    assert snap["UNDERVOLTAGE"].fired is False


def test_fire_recovery_before_fire_is_noop() -> None:
    """fire_recovery on a never-fired subtype must not emit anything."""
    from shitbox.health import alerts

    tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_recovery("UV", False, "RESTORED", tts, sustain_required=1)
        alerts.fire_recovery("UV", False, "RESTORED", tts, sustain_required=1)

    mock_push.assert_not_called()
    tts.assert_not_called()


def test_no_lock_on_alerts_module() -> None:
    """Capture-path-sacred: no threading.Lock on fire_alert/fire_recovery (Phase 10 D-02)."""
    from shitbox.health import alerts

    src_alert = inspect.getsource(alerts.fire_alert)
    src_recovery = inspect.getsource(alerts.fire_recovery)
    assert "Lock" not in src_alert, "fire_alert must not hold a threading.Lock"
    assert "Lock" not in src_recovery, "fire_recovery must not hold a threading.Lock"


def test_fire_alert_with_broken_tts_never_raises() -> None:
    """Phase 21 D-04: TTS raising must not propagate into the caller."""
    from shitbox.health import alerts

    def boom() -> None:
        raise RuntimeError("piper exploded")

    with patch("shitbox.health.alerts.dashboard_push_event"):
        alerts.fire_alert("UV", True, "UV", boom, sustain_required=1)
        # fired flag still set — the dashboard push succeeded
        assert alerts.snapshot()["UV"].fired is True


def test_fire_alert_with_tts_fn_none_never_raises() -> None:
    """Phase 21 D-04: Optional tts_fn — None is a valid no-op."""
    from shitbox.health import alerts

    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        # Default tts_fn=None path — must not raise
        alerts.fire_alert("UV", True, "UV", sustain_required=1)

    assert mock_push.call_count == 1
    assert alerts.snapshot()["UV"].fired is True


def test_fire_alert_with_sustain_required_1_fires_immediately() -> None:
    """sustain_required=1: single active=True call fires immediately."""
    from shitbox.health import alerts

    tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_alert("CAPTURE_FAILURE", True, "CAPTURE STALLED", tts, sustain_required=1)

    assert mock_push.call_count == 1
    tts.assert_called_once()
