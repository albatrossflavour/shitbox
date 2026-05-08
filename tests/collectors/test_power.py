"""Tests for INACollector (INA228 power monitor).

Replaces the v1 INA219 / v2 INA226 era — that chip is gone, replaced
by an INA228 on the 12 V battery rail at 0x40. Pi-side power telemetry
moved to the Pi 5 PMIC (`vcgencmd pmic_read_adc`) instead of an inline
shunt; tests for that live in test_pmic.py.
"""

from unittest.mock import MagicMock, patch

from shitbox.collectors.power import INACollector


def _make_config(
    enabled: bool = False,
    chip: str = "ina228",
    address: int = 0x40,
    disconnected_threshold_v: float = 1.0,
) -> MagicMock:
    config = MagicMock()
    config.sample_rate_hz = 1.0
    config.enabled = enabled
    config.chip = chip
    config.address = address
    config.i2c_bus = 1
    config.shunt_ohms = 0.015
    config.max_expected_amps = 10.0
    config.disconnected_threshold_v = disconnected_threshold_v
    return config


def test_disabled_by_default_does_not_touch_i2c() -> None:
    """When config.enabled=False the collector must never open the I2C bus."""
    config = _make_config(enabled=False)

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        collector = INACollector(config=config, role="battery")
        collector.setup()
        collector.collect()

    mock_smbus.SMBus.assert_not_called()


def test_reads_bus_voltage_and_current_when_enabled() -> None:
    """When enabled, INA228 collector reads voltage and current from registers."""
    config = _make_config(enabled=True, chip="ina228", address=0x40)

    mock_bus = MagicMock()
    # INA228 has 24-bit registers (20-bit data, 4 reserved low bits).
    # VBUS LSB = 195.3125 µV. 12.3 V → raw_data = 62976 → register =
    # 62976 << 4 = 1007616 = 0x0F6000.
    # CURRENT signed 20-bit. With max_amps=10 → CURRENT_LSB = 10/2^19
    # ≈ 19.07 µA. 1.5 A → raw_data ≈ 78643 → register = 78643 << 4 =
    # 1258288 = 0x133330.
    mock_bus.read_i2c_block_data.side_effect = [
        [0x0F, 0x60, 0x00],  # VBUS
        [0x13, 0x33, 0x30],  # CURRENT
    ]

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        mock_smbus.SMBus.return_value = mock_bus
        collector = INACollector(config=config, role="battery")
        collector.setup()
        reading = collector.collect()

    assert reading is not None
    assert reading.role == "battery"
    assert 12.0 < reading.voltage_v < 12.5
    assert 1.4 < reading.current_a < 1.6


def test_graceful_when_sensor_absent() -> None:
    """enabled=True but I2C raises → setup logs and returns; collect() returns None."""
    config = _make_config(enabled=True)

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        mock_smbus.SMBus.side_effect = OSError("no device at address 0x40")
        collector = INACollector(config=config, role="battery")
        collector.setup()  # must not raise
        result = collector.collect()

    assert result is None


def test_floating_chip_below_threshold_emits_nothing() -> None:
    """Voltage below disconnected_threshold_v drops the reading silently.

    Models the case where V+/V- aren't wired and the chip's just reading
    its own ADC noise floor. We don't want this in the DB or Prometheus.
    """
    config = _make_config(enabled=True, chip="ina228", address=0x40,
                          disconnected_threshold_v=1.0)

    mock_bus = MagicMock()
    # Tiny VBUS reading (well under 1 V) plus tiny current — chip alive
    # but inputs floating. INA228 24-bit registers, 20-bit data.
    # 0.0006 V → raw_data ≈ 3 → register ≈ 48 = 0x000030.
    mock_bus.read_i2c_block_data.side_effect = [
        [0x00, 0x00, 0x30],  # VBUS — noise level
        [0xFF, 0xFF, 0xC0],  # CURRENT — small negative noise
    ]

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        mock_smbus.SMBus.return_value = mock_bus
        collector = INACollector(config=config, role="battery")
        collector.setup()
        reading = collector.collect()

    assert reading is None


def test_unknown_chip_does_not_crash() -> None:
    """Unrecognised `chip` value logs a warning, leaves sensor unset, no I2C touched."""
    config = _make_config(enabled=True, chip="ina999")

    with patch("shitbox.collectors.power.smbus2") as mock_smbus:
        collector = INACollector(config=config, role="battery")
        collector.setup()

    mock_smbus.SMBus.assert_not_called()
    assert collector.collect() is None
