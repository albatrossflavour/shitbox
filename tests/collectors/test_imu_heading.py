"""RED tests for IMUHeadingCollector (complementary filter + LIS3MDL tilt-compensated heading).

These tests will FAIL until plan 02 creates shitbox/collectors/imu_heading.py.
ImportError on 'from shitbox.collectors.imu_heading import IMUHeadingCollector' is the RED signal.
"""

import math
from unittest.mock import MagicMock, patch

import pytest

from shitbox.collectors.imu_heading import IMUHeadingCollector  # type: ignore[import]  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collector(alpha: float = 0.98) -> "IMUHeadingCollector":
    """Create a collector instance with a mock config."""
    config = MagicMock()
    config.alpha = alpha
    config.sample_rate_hz = 100.0
    return IMUHeadingCollector(config=config)


# ---------------------------------------------------------------------------
# test_complementary_filter_alpha_098
# ---------------------------------------------------------------------------


def test_complementary_filter_alpha_098() -> None:
    """Complementary filter blends gyro and accel with alpha=0.98.

    Given initial pitch=0 and gyro_x=10 deg/s for dt=0.01 s:
    - Gyro integration: 10 * 0.01 = 0.1 deg
    - Filter output: 0.98 * (0 + 0.1) + 0.02 * 0 = 0.098 deg
    """
    collector = _make_collector(alpha=0.98)

    # Feed one step: pitch=0, gyro_x=10 deg/s, dt=0.01 s, accel-derived pitch=0
    pitch = collector.update_pitch(
        current_pitch=0.0,
        gyro_x_dps=10.0,
        accel_pitch_deg=0.0,
        dt=0.01,
    )

    assert pitch == pytest.approx(0.098, abs=0.001), (
        f"Expected filter pitch ~0.098°, got {pitch}. "
        "Check: alpha=0.98, gyro_int=0.1, accel=0 → 0.98*0.1 + 0.02*0 = 0.098"
    )


# ---------------------------------------------------------------------------
# test_tilt_compensated_heading_at_standstill
# ---------------------------------------------------------------------------


def test_tilt_compensated_heading_at_standstill() -> None:
    """Tilt-compensated heading from LIS3MDL at level orientation.

    mag (20, 0, 0) µT, pitch=0 roll=0 → heading ≈ 0°
    mag (0, 20, 0) µT, pitch=0 roll=0 → heading ≈ 90°
    """
    collector = _make_collector()

    heading_north = collector.compute_heading(
        mag_x=20.0, mag_y=0.0, mag_z=0.0,
        pitch_deg=0.0, roll_deg=0.0,
    )
    assert abs(heading_north) < 1.0 or abs(heading_north - 360.0) < 1.0, (
        f"Expected heading ≈ 0° for mag pointing north, got {heading_north}"
    )

    heading_east = collector.compute_heading(
        mag_x=0.0, mag_y=20.0, mag_z=0.0,
        pitch_deg=0.0, roll_deg=0.0,
    )
    assert abs(heading_east - 90.0) < 1.0, (
        f"Expected heading ≈ 90° for mag pointing east, got {heading_east}"
    )


# ---------------------------------------------------------------------------
# test_heading_available_at_zero_gps_speed
# ---------------------------------------------------------------------------


def test_heading_available_at_zero_gps_speed() -> None:
    """Heading is computed from IMU+mag regardless of GPS speed (covers D-12).

    GPS heading is unavailable at standstill; IMU-derived heading must still update.
    """
    collector = _make_collector()

    # Simulate a collector update with velocity == 0
    heading = collector.get_heading(
        mag_x=20.0, mag_y=0.0, mag_z=0.0,
        pitch_deg=0.0, roll_deg=0.0,
        gps_speed_ms=0.0,  # standstill
    )

    # Heading should be a real float (not None, not NaN)
    assert heading is not None, "Heading must not be None at standstill"
    assert not math.isnan(heading), "Heading must not be NaN at standstill"
    assert 0.0 <= heading < 360.0, f"Heading {heading} out of range [0, 360)"


# ---------------------------------------------------------------------------
# test_lis3mdl_collector_graceful_absent
# ---------------------------------------------------------------------------


def test_lis3mdl_collector_graceful_absent() -> None:
    """Collector must log and continue when LIS3MDL fails to init — never raise."""
    config = MagicMock()
    config.alpha = 0.98
    config.sample_rate_hz = 100.0

    with patch(
        "shitbox.collectors.imu_heading.adafruit_lis3mdl",
        side_effect=ImportError("no lis3mdl"),
    ):
        # Should not raise
        collector = IMUHeadingCollector(config=config)
        collector.setup()

    # Sensor attribute must be None, not missing
    assert collector._lis3mdl is None, (  # type: ignore[attr-defined]
        "Expected _lis3mdl=None after failed LIS3MDL init"
    )
