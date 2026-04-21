"""Canonical BME680 cold-boot -> recover scenario (Phase 21 integration).

This is the end-to-end truth test for the supervisor + module-level hw_state +
collector contract. If this passes, hardware graceful degradation is working.

Time is monkeypatched so the test completes quickly -- the real backoff ladder
is validated by on-Pi smoke checks, not by burning 7+ seconds in CI.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from shitbox.hardware import state as hw_state
from shitbox.hardware.state import DeviceState
from shitbox.hardware.supervisor import HardwareSupervisor
from shitbox.utils.config import HardwareDeviceConfig, HardwareManifestConfig


@pytest.fixture
def manifest_bme680_only():
    """Minimal manifest with only the BME680 environment device."""
    return HardwareManifestConfig(
        devices=[
            HardwareDeviceConfig(
                role="environment",
                bus="i2c-1",
                address=0x77,
                criticality="best_effort",
            ),
        ]
    )


def test_bme680_cold_boot_then_recovers_via_supervisor(
    manifest_bme680_only, monkeypatch
):
    """Cold boot BME680 absent -> supervisor retries at first backoff tier -> PRESENT + TTS.

    Timeline (virtual time -- time.monotonic monkeypatched):
      T=0.0   supervisor.start() -> probe False -> MISSING, speak_hardware_missing
      T=5.1   probe True -> supervisor retry callback runs -> calls report_present
      T=5.1   supervisor observes PRESENT -> speak_hardware_restored

    The background tick thread is stopped immediately after start() so we can
    drive the state machine manually without racing or sleeping.
    """
    clock = {"t": 0.0}
    monkeypatch.setattr(
        "shitbox.hardware.supervisor.time.monotonic", lambda: clock["t"]
    )
    monkeypatch.setattr(
        "shitbox.hardware.state.time.monotonic", lambda: clock["t"]
    )

    # reprobe callback returns True once the clock passes 5s
    def probe_fn() -> bool:
        return clock["t"] >= 5.0

    reprobe_callbacks = {"environment": probe_fn}

    # probe_i2c also follows the clock (used by _probe_all at start time)
    monkeypatch.setattr(
        "shitbox.hardware.probes.probe_i2c",
        lambda bus, address: clock["t"] >= 5.0,
    )
    monkeypatch.setattr(
        "shitbox.hardware.probes.probe_i2c_bus_is_bitbang",
        lambda bus: True,
    )

    with patch(
        "shitbox.hardware.supervisor.speaker.speak_hardware_missing"
    ) as mock_missing, patch(
        "shitbox.hardware.supervisor.speaker.speak_hardware_restored"
    ) as mock_restored:
        supervisor = HardwareSupervisor(manifest_bme680_only, reprobe_callbacks)
        supervisor.start()

        # Stop the background thread immediately -- we drive ticks manually
        supervisor._running = False  # type: ignore[attr-defined]

        # First manual tick: T=0, state is MISSING, prev=None -> speak_hardware_missing
        # (The retry branch won't fire because consecutive_misses=0 after _probe_all
        # calls report_missing once -- wait, _probe_all calls report_missing which sets
        # consecutive_misses=1 and next_retry_at=5.0. But T=0 < 5.0 so retry won't fire.)
        supervisor._tick()

        # After first tick: state MISSING, missing TTS fired once
        snap = hw_state.snapshot()
        assert snap["environment"].state == DeviceState.MISSING
        mock_missing.assert_called_once_with("environment", "best_effort")

        # Advance virtual time past the first backoff tier (5s)
        clock["t"] = 5.1

        # Second manual tick: retry fires, probe returns True -> PRESENT + restored TTS
        supervisor._tick()

        # State should now be PRESENT and restored TTS fired once
        snap = hw_state.snapshot()
        assert snap["environment"].state == DeviceState.PRESENT
        mock_restored.assert_called_once_with("environment", "best_effort")

        supervisor.stop()


def test_bme680_supervisor_does_not_invoke_internal_retry_loop(
    manifest_bme680_only,
):
    """Pitfall 7 guard: BME680 collector's legacy 5x1s retry must NOT run.

    If the supervisor is the single source of retry cadence, the collector's
    internal _BME680_INIT_RETRIES loop must be gone (deleted in Plan 03).
    """
    from shitbox.collectors import environment

    with open(environment.__file__) as f:
        source = f.read()
    assert "_BME680_INIT_RETRIES" not in source, (
        "pitfall 7: environment.py must not re-introduce internal retry loop"
    )
    assert "time.sleep" not in source, (
        "environment.py setup must be single-attempt; supervisor owns retry"
    )
