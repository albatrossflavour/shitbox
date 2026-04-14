"""RED tests for VEML7700Collector (I2C ambient light sensor).

These tests will FAIL until plan 02 creates shitbox/collectors/light.VEML7700Collector.
ImportError on 'from shitbox.collectors.light import VEML7700Collector' is the RED signal.

VEML7700 reads lux via Adafruit CircuitPython library over I2C.
Graceful-absent pattern: catch I2C NACK / import errors, log, return None.
"""

from unittest.mock import MagicMock, patch

import pytest

from shitbox.collectors.light import VEML7700Collector  # type: ignore[import]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> MagicMock:
    config = MagicMock()
    config.sample_rate_hz = 1.0
    config.i2c_bus = 1
    return config


# ---------------------------------------------------------------------------
# test_reads_lux
# ---------------------------------------------------------------------------


def test_reads_lux() -> None:
    """Collector reads lux value from VEML7700 and returns it in the Reading."""
    config = _make_config()

    mock_sensor = MagicMock()
    mock_sensor.lux = 12345.6

    with patch("shitbox.collectors.light.adafruit_veml7700") as mock_lib:
        mock_lib.VEML7700.return_value = mock_sensor
        with patch("shitbox.collectors.light.busio") as mock_busio:
            mock_busio.I2C.return_value = MagicMock()
            with patch("shitbox.collectors.light.board") as mock_board:
                mock_board.SCL = MagicMock()
                mock_board.SDA = MagicMock()
                collector = VEML7700Collector(config=config)
                collector.setup()
                reading = collector.collect()

    assert reading is not None, "Expected a Reading, got None"
    assert reading.value == pytest.approx(12345.6, rel=1e-4), (  # type: ignore[attr-defined]
        f"Expected lux=12345.6, got {reading.value}"
    )


# ---------------------------------------------------------------------------
# test_graceful_when_sensor_absent
# ---------------------------------------------------------------------------


def test_graceful_when_sensor_absent() -> None:
    """I2C NACK during init → logs sensor_init_failed, collect() returns None, no exception raised."""
    config = _make_config()

    with patch("shitbox.collectors.light.busio") as mock_busio:
        mock_busio.I2C.side_effect = OSError("I2C NACK — device not found")
        collector = VEML7700Collector(config=config)
        collector.setup()  # must not raise
        result = collector.collect()

    assert result is None, f"Expected None when sensor absent, got {result}"
    # _sensor should be None after failed init
    assert collector._sensor is None, (  # type: ignore[attr-defined]
        "Expected _sensor=None after failed I2C init"
    )
