"""RED tests for LSM6DSOX high-rate sampler.

These tests will FAIL until plan 01 rewrites the sampler to use LSM6DSOX.

# LSM6DSOX lib returns accel in m/s² and gyro in rad/s.
# Sampler MUST convert: ax_g = ax_ms2 / 9.81 ; gx_dps = gx_rads * (180.0 / math.pi)
# Getting this wrong silently breaks event detection thresholds.
"""

import math
import threading
import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.events.sampler import HighRateSampler


def _make_sampler(
    ax_offset: float = 0.0,
    ay_offset: float = 0.0,
    az_offset: float = 0.0,
) -> HighRateSampler:
    """Create a sampler with a fresh ring buffer."""
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=104.0)
    return HighRateSampler(
        ring_buffer=buf,
        accel_offset_x=ax_offset,
        accel_offset_y=ay_offset,
        accel_offset_z=az_offset,
    )


def _make_fake_lsm6dsox(
    accel: tuple = (9.81, 0.0, 0.0),
    gyro: tuple = (0.0, 0.0, 0.0),
) -> MagicMock:
    """Build a mock that looks like adafruit_lsm6ds.lsm6dsox.LSM6DSOX."""
    sensor = MagicMock()
    sensor.acceleration = accel  # m/s²
    sensor.gyro = gyro           # rad/s
    return sensor


# ---------------------------------------------------------------------------
# test_acceleration_converted_from_m_s2_to_g
# ---------------------------------------------------------------------------


def test_acceleration_converted_from_m_s2_to_g() -> None:
    """Sampler converts m/s² → g correctly: 9.81 m/s² == 1.0 g."""
    sampler = _make_sampler()
    fake_sensor = _make_fake_lsm6dsox(accel=(9.81, 0.0, 0.0), gyro=(0.0, 0.0, 0.0))

    # After plan 01 the sampler will hold a _lsm6dsox attribute
    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    sample = sampler._read_sample()  # type: ignore[attr-defined]

    assert sample.ax == pytest.approx(1.0, abs=0.001), (
        f"Expected ax=1.0 g from 9.81 m/s², got {sample.ax}. "
        "Check: ax_g = ax_ms2 / 9.81"
    )


# ---------------------------------------------------------------------------
# test_gyro_converted_from_rad_s_to_deg_s
# ---------------------------------------------------------------------------


def test_gyro_converted_from_rad_s_to_deg_s() -> None:
    """Sampler converts rad/s → deg/s correctly: π rad/s == 180 deg/s."""
    sampler = _make_sampler()
    fake_sensor = _make_fake_lsm6dsox(accel=(0.0, 0.0, 0.0), gyro=(math.pi, 0.0, 0.0))

    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    sample = sampler._read_sample()  # type: ignore[attr-defined]

    assert sample.gx == pytest.approx(180.0, abs=0.01), (
        f"Expected gx=180 deg/s from π rad/s, got {sample.gx}. "
        "Check: gx_dps = gx_rads * (180.0 / math.pi)"
    )


# ---------------------------------------------------------------------------
# test_sampler_graceful_when_lsm6dsox_absent
# ---------------------------------------------------------------------------


def test_sampler_graceful_when_lsm6dsox_absent() -> None:
    """Sampler.start() must not raise when I2C init fails; sensor stays None."""
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=104.0)
    sampler = HighRateSampler(ring_buffer=buf)

    # Simulate I2C not available (e.g. dev laptop)
    with patch("busio.I2C", side_effect=RuntimeError("no I2C bus")):
        with patch("shitbox.events.sampler.buzzer") as mock_buzzer:
            with patch("shitbox.events.sampler.speaker") as mock_speaker:
                sampler.start()
                # Give thread a moment to attempt init
                time.sleep(0.05)
                sampler.stop()

    # After graceful failure the sensor attribute must be None, not unset
    assert sampler._lsm6dsox is None, (  # type: ignore[attr-defined]
        "Expected _lsm6dsox=None after failed init, indicating graceful absent handling"
    )
    # And the sampler should log sensor_init_failed — we can't assert structlog output
    # directly here but the absence of an exception is the primary contract.


# ---------------------------------------------------------------------------
# test_sampler_produces_104_hz_rate
# ---------------------------------------------------------------------------


def test_sampler_produces_104_hz_rate() -> None:
    """Sampler fills the ring buffer at roughly 104 Hz over 0.5 s."""
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=104.0)
    sampler = HighRateSampler(ring_buffer=buf, sample_rate_hz=104.0)

    fake_sensor = _make_fake_lsm6dsox(accel=(0.0, 0.0, 9.81), gyro=(0.0, 0.0, 0.0))
    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    # Inject a fake setup that doesn't touch hardware
    def _fake_setup() -> None:
        pass

    sampler.setup = _fake_setup  # type: ignore[method-assign]

    sampler.start()
    time.sleep(0.5)
    sampler.stop()

    count = len(buf)
    # 104 Hz * 0.5 s = 52 expected; allow ±15 for scheduling jitter
    assert 37 <= count <= 67, (
        f"Expected 37-67 samples in 0.5 s at 104 Hz, got {count}"
    )


# ---------------------------------------------------------------------------
# test_calibration_offsets_applied
# ---------------------------------------------------------------------------


def test_calibration_offsets_applied() -> None:
    """Calibration offset is subtracted from raw reading: raw 1.0 g - offset 0.1 → stored 0.9 g."""
    sampler = _make_sampler(ax_offset=0.1)

    # Raw accel: 9.81 m/s² = 1.0 g; after offset 0.1 → stored as 0.9 g
    fake_sensor = _make_fake_lsm6dsox(accel=(9.81, 0.0, 0.0), gyro=(0.0, 0.0, 0.0))
    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    sample = sampler._read_sample()  # type: ignore[attr-defined]

    # The plan specifies: ax_offset=0.1, raw 1.0 g -> stored 0.9 g
    assert sample.ax == pytest.approx(0.9, abs=0.001), (
        f"Expected ax=0.9 g after offset correction (raw 1.0 g - offset 0.1), got {sample.ax}"
    )
