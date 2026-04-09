"""RED tests for INA226Collector (I2C power monitor).

These tests will FAIL until plan 02 creates shitbox/collectors/power.INA226Collector.
ImportError on 'from shitbox.collectors.power import INA226Collector' is the RED signal.

INA226 replaces INA219. Uses smbus2 directly (not adafruit circuitpython).
Reads bus voltage (V) and current (A) via I2C at address 0x40.
The sensor is DISABLED BY DEFAULT — must not touch I2C unless explicitly enabled.
"""

from unittest.mock import MagicMock, patch

import pytest

from shitbox.collectors.power import INA226Collector  # type: ignore[import]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(enabled: bool = False) -> MagicMock:
    config = MagicMock()
    config.sample_rate_hz = 1.0
    config.enabled = enabled
    config.address = 0x40
    config.i2c_bus = 1
    config.shunt_ohms = 0.1
    return config


# ---------------------------------------------------------------------------
# test_disabled_by_default_does_not_touch_i2c
# ---------------------------------------------------------------------------


def test_disabled_by_default_does_not_touch_i2c() -> None:
    """When config.enabled=False the collector must never open the I2C bus."""
    config = _make_config(enabled=False)

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        collector = INA226Collector(config=config)
        collector.setup()
        collector.collect()

    mock_smbus.SMBus.assert_not_called(), "smbus2 must not be opened when collector is disabled"


# ---------------------------------------------------------------------------
# test_reads_bus_voltage_and_current_when_enabled
# ---------------------------------------------------------------------------


def test_reads_bus_voltage_and_current_when_enabled() -> None:
    """When enabled, collector reads voltage_v and current_a from INA226 registers."""
    config = _make_config(enabled=True)

    # INA226 register values that encode 12.3 V bus voltage and 1.5 A current
    # (exact encoding depends on implementation; test asserts the Reading fields exist)
    mock_bus = MagicMock()
    # INA226 bus voltage register (0x02): 12.3V = 12300 / 1.25mV per LSB = 9840 = 0x2670
    # INA226 current register (0x04): 1.5A at 0.1 ohm shunt = depends on calibration
    # We mock the read to return predictable values and verify the collector unpacks them.
    mock_bus.read_word_data.side_effect = [
        0x2670,  # bus voltage register raw → 12.3V
        0x0258,  # current register raw → 1.5A (at appropriate calibration)
    ]

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        mock_smbus.SMBus.return_value = mock_bus
        collector = INA226Collector(config=config)
        collector.setup()
        reading = collector.collect()

    assert reading is not None, "Expected a Reading from INA226, got None"
    assert hasattr(reading, "voltage_v"), "Reading must have voltage_v field"
    assert hasattr(reading, "current_a"), "Reading must have current_a field"
    assert reading.voltage_v > 0, f"Expected voltage_v > 0, got {reading.voltage_v}"


# ---------------------------------------------------------------------------
# test_graceful_when_sensor_absent
# ---------------------------------------------------------------------------


def test_graceful_when_sensor_absent() -> None:
    """enabled=True but I2C raises → logs sensor_init_failed, collect() returns None, no exception."""
    config = _make_config(enabled=True)

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        mock_smbus.SMBus.side_effect = OSError("no device at address 0x40")
        collector = INA226Collector(config=config)
        collector.setup()  # must not raise
        result = collector.collect()

    assert result is None, f"Expected None when INA226 absent, got {result}"
