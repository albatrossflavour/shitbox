"""RED tests for SEN0460Collector (I2C PM2.5 particulate sensor).

These tests will FAIL until plan 02 creates shitbox/collectors/particulate.SEN0460Collector.
ImportError on 'from shitbox.collectors.particulate import SEN0460Collector' is the RED signal.

IMPORTANT — cable pinout (D-05). Do not rewire blind. The SEN0460 I2C cable colours:
- cyan = SDA
- blue = SCL

The sensor is DISABLED BY DEFAULT. It must never touch I2C unless explicitly enabled in config.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.collectors.particulate import SEN0460Collector  # type: ignore[import]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(enabled: bool = False) -> MagicMock:
    config = MagicMock()
    config.sample_rate_hz = 1.0
    config.enabled = enabled
    return config


# ---------------------------------------------------------------------------
# test_disabled_by_default_does_not_touch_i2c
# ---------------------------------------------------------------------------


def test_disabled_by_default_does_not_touch_i2c() -> None:
    """When config.enabled=False the collector must never open the I2C bus."""
    config = _make_config(enabled=False)

    with patch("shitbox.collectors.particulate.busio") as mock_busio:
        collector = SEN0460Collector(config=config)
        collector.setup()
        collector.collect()

    mock_busio.I2C.assert_not_called(), "I2C must not be opened when collector is disabled"


# ---------------------------------------------------------------------------
# test_cable_pinout_docstring
# ---------------------------------------------------------------------------


def test_cable_pinout_docstring() -> None:
    """Particulate collector module docstring must contain cable colour pinout.

    This is a guardrail (D-05): if a future developer looks at the file they
    get the pinout before they touch a wire.
    """
    import shitbox.collectors.particulate as module  # type: ignore[import]

    doc = module.__doc__ or ""
    assert "cyan=SDA" in doc, (
        "Module docstring must contain 'cyan=SDA' — SEN0460 cable pinout guardrail (D-05)"
    )
    assert "blue=SCL" in doc, (
        "Module docstring must contain 'blue=SCL' — SEN0460 cable pinout guardrail (D-05)"
    )


# ---------------------------------------------------------------------------
# test_graceful_when_sensor_absent
# ---------------------------------------------------------------------------


def test_graceful_when_sensor_absent() -> None:
    """enabled=True but I2C raises → logs sensor_init_failed, collect() returns None, no exception."""
    config = _make_config(enabled=True)

    with patch("shitbox.collectors.particulate.busio") as mock_busio:
        mock_busio.I2C.side_effect = OSError("no device at address 0x19")
        collector = SEN0460Collector(config=config)
        collector.setup()  # must not raise
        result = collector.collect()

    assert result is None, f"Expected None when sensor absent, got {result}"
