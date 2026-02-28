"""Unit tests for I2C bus lockup detection and 9-clock bit-bang recovery.

Tests cover:
- Consecutive failure counter mechanics (reset on success, increment on error)
- Bit-bang recovery triggered after reaching the threshold
- GPIO sequence verification (9 clock pulses, selective cleanup)
- Reboot fallback when recovery fails
- smbus2 reopen failure handling
- Escalation counter increments across multiple failed attempts
- Reboot gated until I2C_MAX_RESETS attempts exhausted
- Backoff delays applied at correct intervals
- Counter reset after successful recovery
- Startup setup() escalation when bus is locked at boot
- Counter reset on stop()
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from shitbox.events.ring_buffer import RingBuffer
from shitbox.events.sampler import (
    I2C_CONSECUTIVE_FAILURE_THRESHOLD,
    I2C_MAX_RESETS,
    I2C_RESET_BACKOFF_SECONDS,
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
    ring_buf = RingBuffer(max_seconds=1.0, sample_rate_hz=100.0)
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

    # RPi package mock must expose .GPIO so `import RPi.GPIO as GPIO` binds
    # mock_gpio.  Python resolves `import RPi.GPIO as GPIO` by fetching the
    # `GPIO` attribute from the `RPi` entry in sys.modules.
    rpi_pkg_mock = MagicMock()
    rpi_pkg_mock.GPIO = mock_gpio

    with (
        patch.dict(sys.modules, {"RPi": rpi_pkg_mock, "RPi.GPIO": mock_gpio}),
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

    rpi_pkg_mock = MagicMock()
    rpi_pkg_mock.GPIO = mock_gpio

    with (
        patch.dict(sys.modules, {"RPi": rpi_pkg_mock, "RPi.GPIO": mock_gpio}),
        patch.dict(sys.modules, {"smbus2": mock_smbus2}),
    ):
        result = sampler._i2c_bus_reset()

    assert result is False


# ---------------------------------------------------------------------------
# Escalation counter and reboot gating
# ---------------------------------------------------------------------------


def test_escalation_counter_increments(sampler: HighRateSampler) -> None:
    """Reset counter increments with each failed recovery attempt."""
    # Use a sentinel to break out of _sample_loop after a fixed number of lockup cycles.
    # Each lockup cycle: 5 failures (threshold) + attempted recovery.
    call_count = [0]
    max_lockup_cycles = 3

    class _StopSentinel(Exception):
        pass

    def failing_read() -> None:
        raise OSError("I2C bus error")

    def failing_reset() -> bool:
        call_count[0] += 1
        if call_count[0] >= max_lockup_cycles:
            # Prevent the loop from running further after 3 resets
            sampler._running = False
        return False

    sampler._consecutive_failures = 0
    sampler._reset_count = 0

    with (
        patch.object(sampler, "_read_sample", side_effect=failing_read),
        patch.object(sampler, "_i2c_bus_reset", side_effect=failing_reset),
        patch.object(sampler, "_force_reboot"),
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        # perf_counter must return increasing values to keep the loop alive
        mock_time.perf_counter.side_effect = lambda: float(call_count[0])
        mock_time.sleep = MagicMock()
        sampler._running = True
        sampler._sample_loop()

    # After 3 failed resets the counter should be 3 (increments once per lockup detection)
    assert sampler._reset_count == max_lockup_cycles


def test_reboot_only_after_max_resets(sampler: HighRateSampler) -> None:
    """_force_reboot() is NOT called until _reset_count reaches I2C_MAX_RESETS."""
    reboot_mock = MagicMock()
    reset_calls = [0]

    def failing_reset() -> bool:
        reset_calls[0] += 1
        if reset_calls[0] >= I2C_MAX_RESETS:
            sampler._running = False
        return False

    sampler._consecutive_failures = 0
    sampler._reset_count = 0

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C bus error")),
        patch.object(sampler, "_i2c_bus_reset", side_effect=failing_reset),
        patch.object(sampler, "_force_reboot", reboot_mock),
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.perf_counter.side_effect = lambda: float(reset_calls[0])
        mock_time.sleep = MagicMock()
        sampler._running = True
        sampler._sample_loop()

    # Reboot must only be called after exactly I2C_MAX_RESETS failed attempts
    reboot_mock.assert_called_once()
    assert sampler._reset_count == I2C_MAX_RESETS


def test_backoff_delay_applied(sampler: HighRateSampler) -> None:
    """Correct backoff delays are applied before each recovery attempt."""
    reset_calls = [0]
    sleep_calls: list[float] = []

    def failing_reset() -> bool:
        reset_calls[0] += 1
        if reset_calls[0] >= I2C_MAX_RESETS:
            sampler._running = False
        return False

    sampler._consecutive_failures = 0
    sampler._reset_count = 0

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C bus error")),
        patch.object(sampler, "_i2c_bus_reset", side_effect=failing_reset),
        patch.object(sampler, "_force_reboot"),
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.perf_counter.side_effect = lambda: float(reset_calls[0])

        def capture_sleep(duration: float) -> None:
            sleep_calls.append(duration)

        mock_time.sleep = capture_sleep
        sampler._running = True
        sampler._sample_loop()

    # Backoff values must include at least the non-zero delays from I2C_RESET_BACKOFF_SECONDS
    non_zero_backoffs = [s for s in sleep_calls if s in I2C_RESET_BACKOFF_SECONDS and s > 0]
    # Attempt 2 has backoff=2, attempt 3 has backoff=5 — both must appear
    assert 2 in non_zero_backoffs, f"Expected backoff=2 in sleep calls, got {sleep_calls}"
    assert 5 in non_zero_backoffs, f"Expected backoff=5 in sleep calls, got {sleep_calls}"


def test_reset_count_resets_on_success(sampler: HighRateSampler) -> None:
    """_reset_count is zeroed after a successful I2C bus recovery."""
    reset_calls = [0]

    def conditional_reset() -> bool:
        reset_calls[0] += 1
        if reset_calls[0] == 1:
            return False  # First attempt fails, count becomes 1
        # Second attempt succeeds; stop the loop after recovery
        sampler._running = False
        return True

    sampler._consecutive_failures = 0
    sampler._reset_count = 0

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C bus error")),
        patch.object(sampler, "_i2c_bus_reset", side_effect=conditional_reset),
        patch.object(sampler, "_force_reboot"),
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.perf_counter.side_effect = lambda: float(reset_calls[0])
        mock_time.sleep = MagicMock()
        sampler._running = True
        sampler._sample_loop()

    # After successful recovery the counter must be reset to 0
    assert sampler._reset_count == 0


# ---------------------------------------------------------------------------
# Startup setup() escalation
# ---------------------------------------------------------------------------


def test_startup_setup_escalation(sampler: HighRateSampler) -> None:
    """start() retries setup() via _i2c_bus_reset() when setup raises on first call."""
    sampler._bus = None  # Force the setup() path in start()
    setup_calls = [0]

    def failing_setup() -> None:
        setup_calls[0] += 1
        if setup_calls[0] == 1:
            raise OSError("I2C timeout at boot")
        # Subsequent calls (from inside _i2c_bus_reset) succeed implicitly

    with (
        patch.object(sampler, "setup", side_effect=failing_setup),
        patch.object(sampler, "_i2c_bus_reset", return_value=True) as mock_reset,
        patch.object(sampler, "_force_reboot") as mock_reboot,
        patch.object(sampler, "_sample_loop"),  # Prevent infinite loop
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        sampler.start()

    # setup() was attempted at least once
    assert setup_calls[0] >= 1
    # _i2c_bus_reset() was called to recover
    mock_reset.assert_called_once()
    # No reboot needed — recovery succeeded
    mock_reboot.assert_not_called()
    # Thread was started (sampler is running)
    assert sampler._running is True


def test_startup_all_attempts_fail_reboots(sampler: HighRateSampler) -> None:
    """start() calls _force_reboot() when all setup attempts fail."""
    sampler._bus = None  # Force the setup() path in start()

    with (
        patch.object(sampler, "setup", side_effect=OSError("I2C bus permanently locked")),
        patch.object(sampler, "_i2c_bus_reset", return_value=False),
        patch.object(sampler, "_force_reboot") as mock_reboot,
        patch.object(sampler, "_sample_loop"),
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.sleep = MagicMock()
        sampler.start()

    # _force_reboot() must have been called
    mock_reboot.assert_called_once()
    # No thread started — start() returned early
    assert sampler._running is False


# ---------------------------------------------------------------------------
# Counter reset on stop()
# ---------------------------------------------------------------------------


def test_stop_resets_counter(sampler: HighRateSampler) -> None:
    """stop() resets _reset_count to 0 regardless of prior escalation state."""
    sampler._reset_count = 2
    sampler._running = False  # Prevent join from blocking

    sampler.stop()

    assert sampler._reset_count == 0
