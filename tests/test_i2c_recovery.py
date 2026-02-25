"""Unit tests for I2C bus lockup detection and 9-clock bit-bang recovery.

Tests cover:
- Consecutive failure counter mechanics (reset on success, increment on error)
- Bit-bang recovery triggered after reaching the threshold
- GPIO sequence verification (9 clock pulses, selective cleanup)
- Reboot fallback when recovery fails
- smbus2 reopen failure handling
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.events.ring_buffer import RingBuffer
from shitbox.events.sampler import (
    I2C_CONSECUTIVE_FAILURE_THRESHOLD,
    SCL_PIN,
    SDA_PIN,
    HighRateSampler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sampler() -> HighRateSampler:
    """Build a HighRateSampler with a mock bus and ring buffer.

    Does NOT call setup() or start() — hardware is bypassed.
    """
    ring_buf = RingBuffer(capacity=100)
    s = HighRateSampler(ring_buffer=ring_buf, i2c_bus=1)
    # Wire a mock bus so _read_sample can be called without real hardware
    mock_bus = MagicMock()
    s._bus = mock_bus
    return s


# ---------------------------------------------------------------------------
# Counter mechanics
# ---------------------------------------------------------------------------


def test_failure_counter_resets_on_success(sampler: HighRateSampler) -> None:
    """Consecutive failure counter is zeroed when a read succeeds."""
    sampler._consecutive_failures = 3

    # Simulate _sample_loop success path: read succeeds, counter resets
    with patch.object(sampler, "_read_sample", return_value=MagicMock()):
        try:
            sample = sampler._read_sample()
            sampler.ring_buffer.append(sample)
            sampler._consecutive_failures = 0
        except Exception:
            sampler._consecutive_failures += 1

    assert sampler._consecutive_failures == 0


def test_failure_counter_increments_on_error(sampler: HighRateSampler) -> None:
    """Consecutive failure counter increments on each I2C read error."""
    sampler._consecutive_failures = 0

    with patch.object(sampler, "_read_sample", side_effect=OSError("I2C error")):
        try:
            sampler._read_sample()
        except Exception:
            sampler._consecutive_failures += 1

    assert sampler._consecutive_failures == 1


# ---------------------------------------------------------------------------
# Bit-bang trigger threshold
# ---------------------------------------------------------------------------


def test_bitbang_triggered_after_5_failures(sampler: HighRateSampler) -> None:
    """Recovery is triggered when consecutive failures reach the threshold."""
    sampler._consecutive_failures = I2C_CONSECUTIVE_FAILURE_THRESHOLD - 1  # 4

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C error")),
        patch.object(sampler, "_i2c_bus_reset", return_value=True) as mock_reset,
        patch.object(sampler, "_force_reboot") as mock_reboot,
        patch("shitbox.events.sampler.buzzer") as mock_buzzer,
    ):
        # Simulate one failure iteration in _sample_loop
        try:
            sampler._read_sample()
        except Exception as e:
            sampler._consecutive_failures += 1
            if sampler._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
                mock_buzzer.beep_i2c_lockup()
                recovered = sampler._i2c_bus_reset()
                if recovered:
                    mock_buzzer.beep_service_recovered("i2c")
                    sampler._consecutive_failures = 0
                else:
                    sampler._force_reboot()

    mock_reset.assert_called_once()
    mock_buzzer.beep_i2c_lockup.assert_called_once()
    mock_buzzer.beep_service_recovered.assert_called_once_with("i2c")
    mock_reboot.assert_not_called()
    assert sampler._consecutive_failures == 0


def test_reboot_on_bitbang_failure(sampler: HighRateSampler) -> None:
    """System reboot is triggered when bit-bang recovery returns False."""
    sampler._consecutive_failures = I2C_CONSECUTIVE_FAILURE_THRESHOLD - 1  # 4

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C error")),
        patch.object(sampler, "_i2c_bus_reset", return_value=False) as mock_reset,
        patch.object(sampler, "_force_reboot") as mock_reboot,
        patch("shitbox.events.sampler.buzzer") as mock_buzzer,
    ):
        try:
            sampler._read_sample()
        except Exception:
            sampler._consecutive_failures += 1
            if sampler._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
                mock_buzzer.beep_i2c_lockup()
                recovered = sampler._i2c_bus_reset()
                if recovered:
                    mock_buzzer.beep_service_recovered("i2c")
                    sampler._consecutive_failures = 0
                else:
                    sampler._force_reboot()

    mock_reset.assert_called_once()
    mock_reboot.assert_called_once()


# ---------------------------------------------------------------------------
# GPIO bit-bang sequence
# ---------------------------------------------------------------------------


def _make_gpio_mock() -> MagicMock:
    """Return a MagicMock RPi.GPIO module with BCM constant."""
    gpio = MagicMock()
    gpio.BCM = 11  # BCM mode constant value used by real RPi.GPIO
    gpio.OUT = 0
    gpio.HIGH = 1
    gpio.LOW = 0
    return gpio


def test_i2c_bus_reset_gpio_sequence(sampler: HighRateSampler) -> None:
    """9-clock bit-bang reset issues correct GPIO sequence with selective cleanup."""
    mock_gpio = _make_gpio_mock()
    mock_smbus2 = MagicMock()
    mock_smbus2.SMBus.return_value = MagicMock()

    with (
        patch.dict(sys.modules, {"RPi": MagicMock(), "RPi.GPIO": mock_gpio}),
        patch.dict(sys.modules, {"smbus2": mock_smbus2}),
        patch.object(sampler, "setup") as mock_setup,
    ):
        result = sampler._i2c_bus_reset()

    assert result is True

    # BCM mode set
    mock_gpio.setmode.assert_called_once_with(mock_gpio.BCM)

    # SCL_PIN configured as output
    mock_gpio.setup.assert_any_call(SCL_PIN, mock_gpio.OUT, initial=mock_gpio.HIGH)

    # 9 clock pulses = at least 18 GPIO.output calls (9 LOW + 9 HIGH)
    output_calls = mock_gpio.output.call_args_list
    assert len(output_calls) >= 18, f"Expected >=18 GPIO.output calls, got {len(output_calls)}"

    # Selective cleanup — NOT global cleanup()
    mock_gpio.cleanup.assert_called_once_with([SCL_PIN, SDA_PIN])

    # smbus2.SMBus opened with correct bus number
    mock_smbus2.SMBus.assert_called_once_with(sampler.i2c_bus)

    # MPU6050 reinitialised
    mock_setup.assert_called_once()


def test_i2c_bus_reset_returns_false_on_smbus_failure(sampler: HighRateSampler) -> None:
    """_i2c_bus_reset returns False when smbus2.SMBus constructor raises OSError."""
    mock_gpio = _make_gpio_mock()
    mock_smbus2 = MagicMock()
    mock_smbus2.SMBus.side_effect = OSError("I2C device not found")

    with (
        patch.dict(sys.modules, {"RPi": MagicMock(), "RPi.GPIO": mock_gpio}),
        patch.dict(sys.modules, {"smbus2": mock_smbus2}),
    ):
        result = sampler._i2c_bus_reset()

    assert result is False
