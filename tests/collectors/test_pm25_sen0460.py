"""Tests for SEN0460Collector (I2C PM2.5 particulate sensor).

IMPORTANT — cable pinout (D-05). Do not rewire blind. The SEN0460 I2C cable colours:
- cyan = SDA
- blue = SCL

The sensor is DISABLED BY DEFAULT. It must never touch I2C unless explicitly enabled in config.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from shitbox.collectors.particulate import SEN0460Collector
from shitbox.storage.models import SensorType


def _make_config(enabled: bool = False) -> MagicMock:
    config = MagicMock()
    config.sample_rate_hz = 1.0
    config.i2c_bus = 1
    config.address = 0x19
    config.enabled = enabled
    return config


def test_disabled_by_default_does_not_touch_i2c() -> None:
    """When config.enabled=False the collector must never open the I2C bus."""
    config = _make_config(enabled=False)

    with patch("shitbox.collectors.particulate.smbus2") as mock_smbus:
        collector = SEN0460Collector(config=config)
        collector.setup()
        collector.collect()

    mock_smbus.SMBus.assert_not_called(), "I2C must not be opened when collector is disabled"


def test_cable_pinout_docstring() -> None:
    """Particulate collector module docstring must contain cable colour pinout (D-05)."""
    import shitbox.collectors.particulate as module

    doc = module.__doc__ or ""
    assert "cyan=SDA" in doc, (
        "Module docstring must contain 'cyan=SDA' — SEN0460 cable pinout guardrail (D-05)"
    )
    assert "blue=SCL" in doc, (
        "Module docstring must contain 'blue=SCL' — SEN0460 cable pinout guardrail (D-05)"
    )


def test_graceful_when_sensor_absent() -> None:
    """enabled=True but I2C raises → logs sensor_init_failed, collect() returns None, no exception."""
    config = _make_config(enabled=True)

    with patch("shitbox.collectors.particulate.smbus2") as mock_smbus:
        mock_smbus.SMBus.side_effect = OSError("no device at address 0x19")
        collector = SEN0460Collector(config=config)
        collector.setup()  # must not raise
        result = collector.collect()

    assert result is None, f"Expected None when sensor absent, got {result}"
    assert collector._sensor is None, "Expected _sensor=None after failed init"


def test_reads_pm25_and_maps_to_reading() -> None:
    """Collector reads PM2.5 and produces a Reading with sensor_type=PM25."""
    config = _make_config(enabled=True)

    mock_sensor = MagicMock()
    mock_sensor.read_particle_concentration.return_value = 17.0

    with patch("shitbox.collectors.particulate.smbus2") as mock_smbus, patch(
        "shitbox.collectors.particulate.dfrobot_airquality"
    ) as mock_lib:
        mock_smbus.SMBus.return_value = MagicMock()
        mock_lib.DFRobot_AirQualitySensor.return_value = mock_sensor
        collector = SEN0460Collector(config=config)
        collector.setup()
        data = collector.collect()

    assert data is not None
    assert data.pm25_ug_m3 == pytest.approx(17.0)
    mock_sensor.read_particle_concentration.assert_called_once_with("PM2.5")

    reading = collector.to_reading(data)
    assert reading.sensor_type is SensorType.PM25
    assert reading.pm25_ug_m3 == pytest.approx(17.0)
    assert isinstance(reading.timestamp_utc, datetime)
