"""RED tests for DS18B20Collector (dual-probe 1-Wire temperature).

These tests will FAIL until plan 02 creates shitbox/collectors/temperature.DS18B20Collector.
ImportError on 'from shitbox.collectors.temperature import DS18B20Collector' is the RED signal.

The DS18B20 collector replaces MCP9808 (single I2C probe) with two 1-Wire probes:
exterior (bonnet) and engine_bay, identified by 28-xxxxxxxxxxxx sensor IDs.
"""

from unittest.mock import MagicMock, patch

import pytest

from shitbox.collectors.temperature import DS18B20Collector  # type: ignore[import]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(exterior_id: str = "28-aabbccddeeff", engine_bay_id: str = "28-112233445566") -> MagicMock:
    config = MagicMock()
    config.sample_rate_hz = 0.1
    config.sensor_ids = {"exterior": exterior_id, "engine_bay": engine_bay_id}
    return config


# ---------------------------------------------------------------------------
# test_reads_both_probes_by_id
# ---------------------------------------------------------------------------


def test_reads_both_probes_by_id() -> None:
    """Collector produces two Reading objects, one per probe ID."""
    exterior_id = "28-aabbccddeeff"
    engine_bay_id = "28-112233445566"
    config = _make_config(exterior_id=exterior_id, engine_bay_id=engine_bay_id)

    mock_exterior = MagicMock()
    mock_exterior.id = exterior_id
    mock_exterior.get_temperature.return_value = 22.5

    mock_engine_bay = MagicMock()
    mock_engine_bay.id = engine_bay_id
    mock_engine_bay.get_temperature.return_value = 68.0

    with patch("shitbox.collectors.temperature.W1ThermSensor") as MockSensor:
        MockSensor.return_value = mock_exterior

        def get_sensor(sensor_id: str) -> MagicMock:
            return mock_exterior if sensor_id == exterior_id else mock_engine_bay

        MockSensor.side_effect = get_sensor

        collector = DS18B20Collector(config=config)
        collector.setup()
        readings = collector.collect()

    assert readings is not None, "Expected readings, got None"
    assert len(readings) == 2, f"Expected 2 readings (exterior + engine_bay), got {len(readings)}"


# ---------------------------------------------------------------------------
# test_role_mapping_from_config
# ---------------------------------------------------------------------------


def test_role_mapping_from_config() -> None:
    """Config dict {exterior: id, engine_bay: id} maps correctly to Reading.role."""
    exterior_id = "28-aaaabbbbcccc"
    engine_bay_id = "28-ddddeeeeffffgg"  # noqa: E501 — intentional long ID for realism
    config = _make_config(exterior_id=exterior_id, engine_bay_id=engine_bay_id)

    mock_sensor = MagicMock()
    mock_sensor.get_temperature.return_value = 25.0

    with patch("shitbox.collectors.temperature.W1ThermSensor", return_value=mock_sensor):
        collector = DS18B20Collector(config=config)
        collector.setup()
        readings = collector.collect()

    assert readings is not None
    roles = {r.role for r in readings}  # type: ignore[attr-defined]
    assert "exterior" in roles, f"Expected 'exterior' role, got {roles}"
    assert "engine_bay" in roles, f"Expected 'engine_bay' role, got {roles}"


# ---------------------------------------------------------------------------
# test_missing_probe_logged_not_raised
# ---------------------------------------------------------------------------


def test_missing_probe_logged_not_raised() -> None:
    """W1ThermSensor raises NoSensorFoundError → collector logs and returns None, no exception."""
    config = _make_config()

    # Simulate sensor not found (W1ThermSensor raises its own exception type)
    class NoSensorFoundError(Exception):
        pass

    with patch("shitbox.collectors.temperature.W1ThermSensor") as MockSensor:
        MockSensor.side_effect = NoSensorFoundError("sensor not found")
        with patch("shitbox.collectors.temperature.NoSensorFoundError", NoSensorFoundError):
            collector = DS18B20Collector(config=config)
            collector.setup()
            result = collector.collect()

    assert result is None, f"Expected None when probe missing, got {result}"
    # No exception must propagate — the test passing is the assertion.


# ---------------------------------------------------------------------------
# test_graceful_when_w1thermsensor_import_fails
# ---------------------------------------------------------------------------


def test_graceful_when_w1thermsensor_import_fails() -> None:
    """ImportError for w1thermsensor library → collector logs and sets _disabled=True."""
    config = _make_config()

    with patch.dict("sys.modules", {"w1thermsensor": None}):
        collector = DS18B20Collector(config=config)
        collector.setup()

    assert collector._disabled is True, (  # type: ignore[attr-defined]
        "Expected collector._disabled=True when w1thermsensor import fails"
    )
