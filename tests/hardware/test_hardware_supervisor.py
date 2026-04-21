"""Unit tests for HardwareSupervisor daemon thread.

Tests cover HW-03 (per-tier alert cadence) and HW-04 (exponential backoff
re-adoption + restored TTS). No live threads — tests call _tick() directly
and monkeypatch time.monotonic for deterministic cadence assertions.
"""
from __future__ import annotations

from typing import Callable, Dict, List
from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.hardware import state as hw_state
from shitbox.hardware.supervisor import HardwareSupervisor
from shitbox.utils.config import HardwareDeviceConfig, HardwareManifestConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_manifest(*devices: HardwareDeviceConfig) -> HardwareManifestConfig:
    return HardwareManifestConfig(devices=list(devices))


def _imu_device() -> HardwareDeviceConfig:
    return HardwareDeviceConfig(
        role="imu", bus="i2c-1", criticality="critical", address=0x6A
    )


def _power_device() -> HardwareDeviceConfig:
    return HardwareDeviceConfig(
        role="power", bus="i2c-1", criticality="important", address=0x40
    )


def _env_device() -> HardwareDeviceConfig:
    return HardwareDeviceConfig(
        role="environment", bus="i2c-1", criticality="best_effort", address=0x77
    )


def _mag_device() -> HardwareDeviceConfig:
    return HardwareDeviceConfig(
        role="magnetometer", bus="i2c-1", criticality="best_effort", address=0x1C
    )


@pytest.fixture()
def supervisor_fixture(monkeypatch: pytest.MonkeyPatch) -> HardwareSupervisor:
    """Build a supervisor with 3 devices (imu critical, power important, environment best_effort).

    Does NOT start the thread. Probes are all patched to return True by default
    so the caller can override as needed.
    """
    manifest = _make_manifest(_imu_device(), _power_device(), _env_device())
    reprobe: Dict[str, Callable[[], bool]] = {
        "imu": MagicMock(return_value=True),
        "power": MagicMock(return_value=True),
        "environment": MagicMock(return_value=True),
    }
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks=reprobe)
    return sup


# ---------------------------------------------------------------------------
# Helper: seed hw_state MISSING for a role with a given consecutive_misses count
# ---------------------------------------------------------------------------


def _force_missing(role: str, tier: str, consecutive: int = 1, next_retry_at: float = 0.0) -> None:
    """Directly seed hw_state with a MISSING entry bypassing the backoff ladder."""
    import time
    from shitbox.hardware.state import DeviceState, DeviceStatus

    new_map = dict(hw_state.snapshot())
    new_map[role] = DeviceStatus(
        role=role,
        tier=tier,
        state=DeviceState.MISSING,
        last_seen=0.0,
        since_monotonic=time.monotonic(),
        next_retry_at=next_retry_at,
        consecutive_misses=consecutive,
    )
    hw_state._state = new_map  # type: ignore[attr-defined]


def _force_present(role: str, tier: str) -> None:
    """Directly seed hw_state with a PRESENT entry."""
    import time
    from shitbox.hardware.state import DeviceState, DeviceStatus

    new_map = dict(hw_state.snapshot())
    new_map[role] = DeviceStatus(
        role=role,
        tier=tier,
        state=DeviceState.PRESENT,
        last_seen=time.time(),
        since_monotonic=time.monotonic(),
        next_retry_at=0.0,
        consecutive_misses=0,
    )
    hw_state._state = new_map  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_start_seeds_state_from_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    """start() initialises hw_state with all manifest roles then stops cleanly."""
    manifest = _make_manifest(_imu_device(), _power_device(), _env_device())
    reprobe: Dict[str, Callable[[], bool]] = {}
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks=reprobe)

    # Patch probes so _probe_all doesn't touch real hardware
    monkeypatch.setattr("shitbox.hardware.supervisor.hw_probes.probe_i2c_bus_is_bitbang", lambda b: True)
    monkeypatch.setattr("shitbox.hardware.supervisor.hw_probes.probe_i2c", lambda b, a: True)

    sup.start()
    sup.stop()

    snap = hw_state.snapshot()
    assert "imu" in snap
    assert "power" in snap
    assert "environment" in snap
    assert snap["imu"].tier == "critical"
    assert snap["power"].tier == "important"
    assert snap["environment"].tier == "best_effort"


def test_probe_all_marks_missing_when_bus_not_bitbang(monkeypatch: pytest.MonkeyPatch) -> None:
    """All i2c-1 devices are marked MISSING without probing when the bus is not bit-bang."""
    manifest = _make_manifest(_imu_device(), _power_device(), _env_device())
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks={})

    mock_probe_i2c = MagicMock(return_value=True)
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.hw_probes.probe_i2c_bus_is_bitbang", lambda b: False
    )
    monkeypatch.setattr("shitbox.hardware.supervisor.hw_probes.probe_i2c", mock_probe_i2c)

    # Initialise state first (start() does this before _probe_all)
    hw_state.initialise({"imu": "critical", "power": "important", "environment": "best_effort"})
    sup._probe_all()

    snap = hw_state.snapshot()
    assert snap["imu"].state == hw_state.DeviceState.MISSING
    assert snap["power"].state == hw_state.DeviceState.MISSING
    assert snap["environment"].state == hw_state.DeviceState.MISSING
    mock_probe_i2c.assert_not_called()


def test_probe_all_reports_present_when_probe_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All devices marked PRESENT when probes return True."""
    manifest = _make_manifest(_imu_device(), _power_device(), _env_device())
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks={})

    monkeypatch.setattr(
        "shitbox.hardware.supervisor.hw_probes.probe_i2c_bus_is_bitbang", lambda b: True
    )
    monkeypatch.setattr("shitbox.hardware.supervisor.hw_probes.probe_i2c", lambda b, a: True)

    hw_state.initialise({"imu": "critical", "power": "important", "environment": "best_effort"})
    sup._probe_all()

    snap = hw_state.snapshot()
    assert snap["imu"].state == hw_state.DeviceState.PRESENT
    assert snap["power"].state == hw_state.DeviceState.PRESENT
    assert snap["environment"].state == hw_state.DeviceState.PRESENT


def test_critical_tier_renags_every_30s(monkeypatch: pytest.MonkeyPatch) -> None:
    """Critical MISSING devices re-speak every 30s; not between nag intervals (HW-03)."""
    manifest = _make_manifest(_imu_device())
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks={})

    hw_state.initialise({"imu": "critical"})
    _force_missing("imu", "critical", consecutive=1, next_retry_at=9999.0)  # no retry yet

    mock_missing = MagicMock()
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_missing", mock_missing)
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.speaker.speak_hardware_restored", MagicMock()
    )

    # First tick at t=0: _prev_state empty → first transition → speaks once, sets _last_nag=0
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=0.0):
        sup._tick()
    assert mock_missing.call_count == 1

    # t=29: still within 30s window → no re-nag
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=29.0):
        sup._tick()
    assert mock_missing.call_count == 1

    # t=31: beyond 30s → re-nag fires
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=31.0):
        sup._tick()
    assert mock_missing.call_count == 2


def test_important_tier_speaks_once_per_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Important MISSING speaks once on first detection; no re-nag at 31s (HW-03)."""
    manifest = _make_manifest(_power_device())
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks={})

    hw_state.initialise({"power": "important"})
    _force_missing("power", "important", consecutive=1, next_retry_at=9999.0)

    mock_missing = MagicMock()
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_missing", mock_missing)
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.speaker.speak_hardware_restored", MagicMock()
    )

    # First tick: new transition → speaks once
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=0.0):
        sup._tick()
    assert mock_missing.call_count == 1

    # 5s later: still MISSING, no new transition → silent
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=5.0):
        sup._tick()
    assert mock_missing.call_count == 1

    # 31s later: still MISSING, important tier → NO re-nag (important is once per transition)
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=31.0):
        sup._tick()
    assert mock_missing.call_count == 1


def test_best_effort_silent_except_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """best_effort devices are silent on MISSING; environment is the one exception (HW-03)."""
    manifest = _make_manifest(_mag_device(), _env_device())
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks={})

    hw_state.initialise({"magnetometer": "best_effort", "environment": "best_effort"})
    _force_missing("magnetometer", "best_effort", consecutive=1, next_retry_at=9999.0)
    _force_missing("environment", "best_effort", consecutive=1, next_retry_at=9999.0)

    mock_missing = MagicMock()
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_missing", mock_missing)
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.speaker.speak_hardware_restored", MagicMock()
    )

    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=0.0):
        sup._tick()

    # speak_hardware_missing called once — for environment only (magnetometer is silent)
    mock_missing.assert_called_once_with("environment", "best_effort")


def test_reprobe_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    """When reprobe callback returns True, state flips PRESENT + restored TTS (HW-04)."""
    manifest = _make_manifest(_imu_device())
    reprobe = {"imu": MagicMock(return_value=True)}
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks=reprobe)

    hw_state.initialise({"imu": "critical"})
    # next_retry_at=0 → retry is due immediately at t=0
    _force_missing("imu", "critical", consecutive=1, next_retry_at=0.0)

    mock_missing = MagicMock()
    mock_restored = MagicMock()
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_missing", mock_missing)
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_restored", mock_restored)

    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=0.0):
        sup._tick()

    assert hw_state.snapshot()["imu"].state == hw_state.DeviceState.PRESENT
    mock_restored.assert_called_once_with("imu", "critical")
    mock_missing.assert_not_called()


def test_reprobe_failure_reschedules(monkeypatch: pytest.MonkeyPatch) -> None:
    """When reprobe returns False, consecutive_misses bumps and next_retry_at advances (HW-04)."""
    manifest = _make_manifest(_imu_device())
    reprobe = {"imu": MagicMock(return_value=False)}
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks=reprobe)

    hw_state.initialise({"imu": "critical"})
    _force_missing("imu", "critical", consecutive=1, next_retry_at=0.0)

    monkeypatch.setattr(
        "shitbox.hardware.supervisor.speaker.speak_hardware_missing", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.speaker.speak_hardware_restored", MagicMock()
    )

    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=0.0):
        sup._tick()

    snap = hw_state.snapshot()
    assert snap["imu"].consecutive_misses == 2
    assert snap["imu"].next_retry_at > 0.0
    assert snap["imu"].state == hw_state.DeviceState.MISSING


def test_tick_swallows_exceptions(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """tick_loop swallows exceptions from _tick and logs hw_supervisor_tick_error."""
    import logging

    manifest = _make_manifest(_imu_device())
    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks={})

    # Make hw_state.snapshot raise to trigger the error path
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.hw_state.snapshot",
        MagicMock(side_effect=RuntimeError("boom")),
    )

    # Call _tick directly — must not raise
    with caplog.at_level(logging.ERROR):
        try:
            sup._tick()
        except Exception as e:
            pytest.fail(f"_tick raised unexpectedly: {e}")

    # The tick itself does the try/except — the error is logged in _tick_loop
    # Test that _tick_loop correctly catches and logs by running one iteration manually
    sup._running = True

    call_count = 0

    def boom_tick() -> None:
        nonlocal call_count
        call_count += 1
        sup._running = False  # stop after one iteration
        raise RuntimeError("tick_error")

    sup._tick = boom_tick  # type: ignore[method-assign]

    import threading

    t = threading.Thread(target=sup._tick_loop, daemon=True)
    t.start()
    t.join(timeout=3.0)

    # Thread must have exited cleanly (not timed out)
    assert not t.is_alive()
    assert call_count == 1


def test_bme680_canonical_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """CANONICAL HW-04: BME680 fails initial probe, retries at 5s, succeeds, speaks restored.

    Reproduces the documented boot-timing race (STATE.md out-of-band note 2026-04-10):
    - environment (best_effort, i2c-1, 0x77) fails first probe at boot
    - consecutive_misses=1, next_retry_at=5s
    - At t=5s, reprobe returns True → state PRESENT, speak_hardware_restored called once
    """
    env_dev = HardwareDeviceConfig(
        role="environment", bus="i2c-1", criticality="best_effort", address=0x77
    )
    manifest = _make_manifest(env_dev)

    # First call: False (boot timing race); second call: True (sensor settled)
    probe_attempts: List[bool] = [False, True]
    reprobe = {"environment": MagicMock(side_effect=probe_attempts)}

    sup = HardwareSupervisor(manifest=manifest, reprobe_callbacks=reprobe)

    # Patch so _probe_all's i2c check returns False (boot miss)
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.hw_probes.probe_i2c_bus_is_bitbang", lambda b: True
    )
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.hw_probes.probe_i2c", lambda b, a: False  # initial probe fails
    )

    mock_missing = MagicMock()
    mock_restored = MagicMock()
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_missing", mock_missing)
    monkeypatch.setattr("shitbox.hardware.supervisor.speaker.speak_hardware_restored", mock_restored)

    # Initialise state and run probe_all (simulates supervisor.start() without the thread)
    hw_state.initialise({"environment": "best_effort"})
    sup._probe_all()

    # After boot probe: environment must be MISSING with consecutive_misses=1
    snap = hw_state.snapshot()
    assert snap["environment"].state == hw_state.DeviceState.MISSING
    assert snap["environment"].consecutive_misses == 1
    assert snap["environment"].next_retry_at > 0.0

    # Force next_retry_at to 5.0 for deterministic test
    _force_missing("environment", "best_effort", consecutive=1, next_retry_at=5.0)

    # t=4.9: retry not yet due
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=4.9):
        sup._tick()
    assert hw_state.snapshot()["environment"].state == hw_state.DeviceState.MISSING

    # t=5.0: retry due → reprobe returns True → PRESENT + restored TTS
    with patch("shitbox.hardware.supervisor.time.monotonic", return_value=5.0):
        sup._tick()

    final = hw_state.snapshot()
    assert final["environment"].state == hw_state.DeviceState.PRESENT
    mock_restored.assert_called_once_with("environment", "best_effort")
