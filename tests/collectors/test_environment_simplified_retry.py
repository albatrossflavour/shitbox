"""Tests for EnvironmentCollector simplified single-attempt setup.

Verifies that:
- setup() makes a single attempt and returns immediately on success
- setup() raises immediately on failure without sleeping
- The old retry constants no longer exist on the module
- role="environment" is passed to BaseCollector
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import shitbox.collectors.environment as env_module
from shitbox.collectors.environment import EnvironmentCollector
from shitbox.utils.config import EnvironmentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> EnvironmentConfig:
    """Build a minimal EnvironmentConfig for testing."""
    return EnvironmentConfig(sample_rate_hz=1.0, i2c_bus=1, address=0x77)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bme680_constants_removed() -> None:
    """_BME680_INIT_RETRIES and _BME680_INIT_RETRY_DELAY_S must not exist on the module."""
    assert not hasattr(env_module, "_BME680_INIT_RETRIES"), (
        "_BME680_INIT_RETRIES should have been removed from environment.py"
    )
    assert not hasattr(env_module, "_BME680_INIT_RETRY_DELAY_S"), (
        "_BME680_INIT_RETRY_DELAY_S should have been removed from environment.py"
    )


def test_role_passed_to_base() -> None:
    """EnvironmentCollector passes role='environment' to BaseCollector.__init__."""
    config = _make_config()
    collector = EnvironmentCollector(config)
    assert collector.role == "environment"


def test_setup_single_attempt_on_success() -> None:
    """setup() completes on a single attempt without calling time.sleep."""
    config = _make_config()
    collector = EnvironmentCollector(config)

    mock_i2c = MagicMock()
    mock_sensor = MagicMock()

    with (
        patch("shitbox.collectors.environment.busio") as mock_busio,
        patch("shitbox.collectors.environment.board"),
        patch("shitbox.collectors.environment.Adafruit_BME680_I2C", return_value=mock_sensor),
        patch("time.sleep") as mock_sleep,
    ):
        mock_busio.I2C.return_value = mock_i2c
        collector.setup()

    # time.sleep must NOT be called during a successful setup
    mock_sleep.assert_not_called()
    assert collector._sensor is mock_sensor


def test_setup_raises_immediately_on_failure() -> None:
    """setup() raises immediately on failure without sleeping (no retry loop)."""
    config = _make_config()
    collector = EnvironmentCollector(config)

    with (
        patch("shitbox.collectors.environment.busio") as mock_busio,
        patch("shitbox.collectors.environment.board"),
        patch(
            "shitbox.collectors.environment.Adafruit_BME680_I2C",
            side_effect=OSError("I2C bus error"),
        ),
        patch("time.sleep") as mock_sleep,
    ):
        mock_busio.I2C.return_value = MagicMock()
        with pytest.raises(OSError):
            collector.setup()

    # time.sleep must NOT be called during a failed setup
    mock_sleep.assert_not_called()
