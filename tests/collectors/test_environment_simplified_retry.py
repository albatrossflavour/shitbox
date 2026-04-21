"""Tests for EnvironmentCollector simplified single-attempt setup.

Verifies that:
- setup() makes a single attempt and returns immediately on success
- setup() raises immediately on failure without sleeping
- The old retry constants no longer exist on the module
- role="environment" is passed to BaseCollector
"""
from __future__ import annotations

import sys
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


def _make_hw_mocks():
    """Return (mock_board, mock_busio, mock_sensor_cls, mock_sensor_instance)."""
    mock_board = MagicMock()
    mock_board.SCL = MagicMock()
    mock_board.SDA = MagicMock()

    mock_i2c_instance = MagicMock()
    mock_busio = MagicMock()
    mock_busio.I2C.return_value = mock_i2c_instance

    mock_sensor_instance = MagicMock()
    mock_sensor_cls = MagicMock(return_value=mock_sensor_instance)

    return mock_board, mock_busio, mock_sensor_cls, mock_sensor_instance


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

    mock_board, mock_busio, mock_sensor_cls, mock_sensor_instance = _make_hw_mocks()

    # Patch hardware libs that are imported inside setup()
    with (
        patch.dict(
            sys.modules,
            {
                "board": mock_board,
                "busio": mock_busio,
                "adafruit_bme680": MagicMock(Adafruit_BME680_I2C=mock_sensor_cls),
            },
        ),
        patch("time.sleep") as mock_sleep,
    ):
        collector.setup()

    # time.sleep must NOT be called during a successful setup
    mock_sleep.assert_not_called()
    assert collector._sensor is mock_sensor_instance


def test_setup_raises_immediately_on_failure() -> None:
    """setup() raises immediately on failure without sleeping (no retry loop)."""
    config = _make_config()
    collector = EnvironmentCollector(config)

    mock_board, mock_busio, _, _ = _make_hw_mocks()
    # Make sensor class raise on instantiation
    failing_sensor_cls = MagicMock(side_effect=OSError("I2C bus error"))

    with (
        patch.dict(
            sys.modules,
            {
                "board": mock_board,
                "busio": mock_busio,
                "adafruit_bme680": MagicMock(Adafruit_BME680_I2C=failing_sensor_cls),
            },
        ),
        patch("time.sleep") as mock_sleep,
    ):
        with pytest.raises(OSError):
            collector.setup()

    # time.sleep must NOT be called during a failed setup
    mock_sleep.assert_not_called()
