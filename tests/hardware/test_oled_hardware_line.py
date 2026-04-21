"""Tests for OLED line 3 hardware rollup rendering (Phase 21, HW-02).

Drives OLEDDisplayService._render() directly without starting the hardware
thread. The display hardware, PIL, and engine references are all mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.hardware import state as hw_state

# ---------------------------------------------------------------------------
# Fixture: minimal OLEDDisplayService with mocked hardware context
# ---------------------------------------------------------------------------


@pytest.fixture()
def oled_service():
    """Return an OLEDDisplayService whose display + draw context are mocks.

    Bypasses start() entirely — that is the approach endorsed by the plan for
    unit testing without PIL or Adafruit hardware available.
    """
    # Mock all hardware-library imports used by oled.py before importing the class.
    with (
        patch.dict(
            "sys.modules",
            {
                "adafruit_ssd1306": MagicMock(),
                "board": MagicMock(),
                "busio": MagicMock(),
                "PIL": MagicMock(),
                "PIL.Image": MagicMock(),
                "PIL.ImageDraw": MagicMock(),
                "PIL.ImageFont": MagicMock(),
            },
        )
    ):
        from shitbox.display.oled import OLEDDisplayService
        from shitbox.utils.config import OLEDConfig

        config = OLEDConfig(address=0x3C, update_interval_seconds=1.0)

        # Build a mock engine with get_status() returning minimal required fields.
        engine = MagicMock()
        engine.get_status.return_value = {
            "gps_available": False,
            "gps_has_fix": False,
            "satellites": 0,
            "speed_kmh": None,
            "peak_g": 0.0,
            "events_captured": 0,
            "recording": False,
            "net_connected": False,
            "sync_backlog": 0,
            "cpu_temp": None,
        }

        svc = OLEDDisplayService(config, engine)

        # Wire a mock draw context and font so _draw_text works without PIL.
        mock_draw = MagicMock()
        mock_font = MagicMock()
        # font.getbbox must return a 4-tuple for the inverted branch.
        mock_font.getbbox.return_value = (0, 0, 24, 8)
        svc._draw = mock_draw
        svc._font = mock_font
        svc._display = MagicMock()
        svc._image = MagicMock()

        # Spy on _draw_text by wrapping the real method.
        svc._draw_text = MagicMock(wraps=svc._draw_text)

    return svc


# ---------------------------------------------------------------------------
# Helper: extract line-3 _draw_text calls (y == 32)
# ---------------------------------------------------------------------------


def _line3_calls(svc) -> list[call]:
    """Return all _draw_text calls that targeted y=32 (OLED line 3)."""
    return [c for c in svc._draw_text.call_args_list if c.args[1] == 32]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_oled_line_3_all_present(oled_service):
    """All six devices present: no inversions, ENV:3/3."""
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
        "power": "important",
        "environment": "best_effort",
        "magnetometer": "best_effort",
        "light": "best_effort",
    })
    for role in ("imu", "camera_front", "power", "environment", "magnetometer", "light"):
        hw_state.report_present(role)

    oled_service._render()
    calls = _line3_calls(oled_service)

    # Assert specific call args: (x, 32, text, inverted=False/True)
    assert call(0, 32, "IMU", inverted=False) in calls, f"IMU call missing from {calls}"
    assert call(32, 32, "CAM", inverted=False) in calls, f"CAM call missing from {calls}"
    assert call(64, 32, "PWR", inverted=False) in calls, f"PWR call missing from {calls}"
    assert call(96, 32, "ENV:3/3") in calls, f"ENV rollup missing from {calls}"


def test_oled_line_3_imu_missing_inverts(oled_service):
    """IMU MISSING → rendered with inverted=True."""
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
        "power": "important",
        "environment": "best_effort",
        "magnetometer": "best_effort",
        "light": "best_effort",
    })
    # Report all present except imu
    for role in ("camera_front", "power", "environment", "magnetometer", "light"):
        hw_state.report_present(role)
    # imu stays MISSING (initialise seeds all as MISSING)

    oled_service._render()
    calls = _line3_calls(oled_service)

    assert call(0, 32, "IMU", inverted=True) in calls, (
        f"Expected IMU inverted=True; calls: {calls}"
    )
    assert call(32, 32, "CAM", inverted=False) in calls
    assert call(64, 32, "PWR", inverted=False) in calls


def test_oled_line_3_camera_front_missing_inverts(oled_service):
    """camera_front MISSING → CAM rendered with inverted=True."""
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
        "power": "important",
        "environment": "best_effort",
        "magnetometer": "best_effort",
        "light": "best_effort",
    })
    for role in ("imu", "power", "environment", "magnetometer", "light"):
        hw_state.report_present(role)
    # camera_front stays MISSING

    oled_service._render()
    calls = _line3_calls(oled_service)

    assert call(0, 32, "IMU", inverted=False) in calls
    assert call(32, 32, "CAM", inverted=True) in calls, (
        f"Expected CAM inverted=True; calls: {calls}"
    )


def test_oled_line_3_power_missing_does_not_invert(oled_service):
    """Power is important tier — MISSING must NOT invert per UI-SPEC."""
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
        "power": "important",
        "environment": "best_effort",
        "magnetometer": "best_effort",
        "light": "best_effort",
    })
    for role in ("imu", "camera_front", "environment", "magnetometer", "light"):
        hw_state.report_present(role)
    # power stays MISSING

    oled_service._render()
    calls = _line3_calls(oled_service)

    assert call(64, 32, "PWR", inverted=False) in calls, (
        f"Expected PWR inverted=False even when missing; calls: {calls}"
    )


def test_oled_line_3_env_rollup_partial(oled_service):
    """environment present, magnetometer + light missing → ENV:1/3."""
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
        "power": "important",
        "environment": "best_effort",
        "magnetometer": "best_effort",
        "light": "best_effort",
    })
    for role in ("imu", "camera_front", "power", "environment"):
        hw_state.report_present(role)
    # magnetometer and light stay MISSING

    oled_service._render()
    calls = _line3_calls(oled_service)

    assert call(96, 32, "ENV:1/3") in calls, f"Expected ENV:1/3; calls: {calls}"


def test_oled_line_3_empty_snapshot(oled_service):
    """No initialise() called — empty snapshot.

    All critical tokens must render inverted (MISSING), rollup ENV:0/3.
    This is HW-02 safety gate: snapshot empty = still renders safely.
    """
    # _clear_hw_state autouse fixture ensures snapshot is empty here.
    oled_service._render()
    calls = _line3_calls(oled_service)

    assert call(0, 32, "IMU", inverted=True) in calls, (
        f"Expected IMU inverted=True on empty snapshot; calls: {calls}"
    )
    assert call(32, 32, "CAM", inverted=True) in calls, (
        f"Expected CAM inverted=True on empty snapshot; calls: {calls}"
    )
    assert call(64, 32, "PWR", inverted=False) in calls, (
        f"Expected PWR inverted=False on empty snapshot; calls: {calls}"
    )
    assert call(96, 32, "ENV:0/3") in calls, (
        f"Expected ENV:0/3 on empty snapshot; calls: {calls}"
    )
