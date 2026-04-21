"""Unit tests for the HardwareState module (hw_state)."""
from __future__ import annotations

from unittest.mock import patch

from shitbox.hardware import state as hw_state
from shitbox.hardware.state import DeviceState


def test_initialise_seeds_all_devices_missing():
    hw_state.initialise({"imu": "critical", "power": "important"})
    snap = hw_state.snapshot()
    assert set(snap.keys()) == {"imu", "power"}
    assert snap["imu"].state == DeviceState.MISSING
    assert snap["power"].state == DeviceState.MISSING
    assert snap["imu"].consecutive_misses == 0
    assert snap["imu"].next_retry_at == 0.0
    assert snap["imu"].last_seen == 0.0
    assert snap["imu"].tier == "critical"
    assert snap["power"].tier == "important"


def test_report_present_unknown_role_returns_none():
    # No initialise — state dict is empty
    result = hw_state.report_present("nonexistent")
    assert result is None
    assert hw_state.snapshot() == {}


def test_report_present_returns_previous_state():
    hw_state.initialise({"imu": "critical"})
    prev = hw_state.report_present("imu")
    assert prev == DeviceState.MISSING


def test_report_present_resets_consecutive_misses():
    hw_state.initialise({"imu": "critical"})
    # Drive up some misses first
    hw_state.report_missing("imu")
    hw_state.report_missing("imu")
    snap = hw_state.snapshot()
    assert snap["imu"].consecutive_misses == 2

    hw_state.report_present("imu")
    snap = hw_state.snapshot()
    assert snap["imu"].state == DeviceState.PRESENT
    assert snap["imu"].consecutive_misses == 0
    assert snap["imu"].next_retry_at == 0.0
    assert snap["imu"].last_seen > 0.0


def test_backoff_schedule():
    """6 consecutive report_missing calls should yield [5, 15, 60, 300, 300, 300] waits."""
    hw_state.initialise({"imu": "critical"})

    # Use a controllable monotonic clock
    mono_clock = [1000.0]

    def fake_monotonic():
        return mono_clock[0]

    expected_waits = [5.0, 15.0, 60.0, 300.0, 300.0, 300.0]

    with patch("shitbox.hardware.state.time") as mock_time:
        mock_time.monotonic.side_effect = fake_monotonic
        mock_time.time.return_value = 0.0

        for i, expected_wait in enumerate(expected_waits):
            hw_state.report_missing("imu")
            snap = hw_state.snapshot()
            actual_wait = snap["imu"].next_retry_at - mono_clock[0]
            assert abs(actual_wait - expected_wait) < 0.01, (
                f"Call {i+1}: expected wait {expected_wait}s, got {actual_wait}s"
            )
            # Consecutive misses is clamped to len(ladder)
            assert snap["imu"].consecutive_misses == min(i + 1, 4)


def test_report_degraded_preserves_next_retry_at():
    hw_state.initialise({"imu": "critical"})
    hw_state.report_missing("imu")
    before = hw_state.snapshot()["imu"].next_retry_at

    hw_state.report_degraded("imu")
    after = hw_state.snapshot()["imu"]
    assert after.state == DeviceState.DEGRADED
    assert after.next_retry_at == before
    assert after.consecutive_misses == before_misses(before)


def before_misses(v):
    # helper: report_missing from MISSING sets consecutive_misses=1
    return 1


def test_report_degraded_preserves_next_retry_at_explicit():
    hw_state.initialise({"imu": "critical"})
    # set up a scheduled retry
    hw_state.report_missing("imu")
    snap_before = hw_state.snapshot()["imu"]
    next_retry = snap_before.next_retry_at
    misses = snap_before.consecutive_misses

    # degraded should not touch those fields
    hw_state.report_degraded("imu")
    snap_after = hw_state.snapshot()["imu"]
    assert snap_after.state == DeviceState.DEGRADED
    assert snap_after.next_retry_at == next_retry
    assert snap_after.consecutive_misses == misses


def test_snapshot_returns_current_state():
    hw_state.initialise({"imu": "critical", "gps": "important"})
    snap = hw_state.snapshot()
    assert len(snap) == 2
    assert "imu" in snap
    assert "gps" in snap


def test_clear_state_empties_dict():
    hw_state.initialise({"imu": "critical"})
    assert len(hw_state.snapshot()) == 1
    hw_state.clear_state()
    assert hw_state.snapshot() == {}
