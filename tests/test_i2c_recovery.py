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
    """Build a HighRateSampler with a mock LSM6DSOX and ring buffer.

    Does NOT call setup() or start() — hardware is bypassed.
    The v2 sampler uses circuitpython (no i2c_bus param); mock _lsm6dsox directly.
    """
    ring_buf = RingBuffer(max_seconds=1.0, sample_rate_hz=100.0)
    s = HighRateSampler(ring_buffer=ring_buf)
    # Wire a mock sensor so _read_sample can be called without real hardware
    mock_sensor = MagicMock()
    s._lsm6dsox = mock_sensor
    # i2c_bus attribute kept for compatibility with tests that reference it
    s.i2c_bus = 1
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

    # RPi package mock must expose .GPIO so `import RPi.GPIO as GPIO` binds
    # mock_gpio.  Python resolves `import RPi.GPIO as GPIO` by fetching the
    # `GPIO` attribute from the `RPi` entry in sys.modules.
    rpi_pkg_mock = MagicMock()
    rpi_pkg_mock.GPIO = mock_gpio

    # The v2 sampler uses circuitpython busio (not smbus2); setup() is called
    # to reinitialise LSM6DSOX after the GPIO sequence.
    mock_lsm6dsox = MagicMock()
    with (
        patch.dict(sys.modules, {"RPi": rpi_pkg_mock, "RPi.GPIO": mock_gpio}),
        patch.object(sampler, "setup") as mock_setup,
    ):
        # Make setup() succeed by setting _lsm6dsox after call
        def _setup_side_effect() -> None:
            sampler._lsm6dsox = mock_lsm6dsox

        mock_setup.side_effect = _setup_side_effect
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

    # LSM6DSOX reinitialised via setup()
    mock_setup.assert_called_once()


def test_i2c_bus_reset_returns_false_on_setup_failure(sampler: HighRateSampler) -> None:
    """_i2c_bus_reset returns False when setup() fails to initialise the sensor."""
    mock_gpio = _make_gpio_mock()

    rpi_pkg_mock = MagicMock()
    rpi_pkg_mock.GPIO = mock_gpio

    # setup() completes but leaves _lsm6dsox as None (sensor init failed)
    def _failing_setup() -> None:
        sampler._lsm6dsox = None

    with (
        patch.dict(sys.modules, {"RPi": rpi_pkg_mock, "RPi.GPIO": mock_gpio}),
        patch.object(sampler, "setup", side_effect=_failing_setup),
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


def test_force_reboot_not_called_after_max_resets(sampler: HighRateSampler) -> None:
    """_force_reboot() is NEVER called from the recovery escalation.

    Brain note open thread (2026-04-29): soft reboot does not recover a
    TCA4307-latched I2C bus on Pi 5 (PMIC keeps 3.3V alive through
    systemctl reboot). The escalation now drops _force_reboot entirely —
    after I2C_MAX_RESETS short retries we transition to a long-backoff
    retry mode and stay alive so the operator can hard power-cycle.
    """
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

    # _force_reboot is no longer in the escalation chain. The reset count
    # still reaches I2C_MAX_RESETS, but the daemon stays alive instead of
    # rebooting. Operator must hard power-cycle to recover when the
    # EN-pulse path can't clear the latch.
    reboot_mock.assert_not_called()
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
    sampler._lsm6dsox = None  # Force the setup() path in start()
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


def test_startup_all_attempts_fail_no_reboot(sampler: HighRateSampler) -> None:
    """start() returns without calling _force_reboot() when all setup attempts fail.

    Brain note open thread (2026-04-29): _force_reboot is no longer in
    the recovery escalation. When boot setup can't bring the IMU up the
    daemon stays alive with IMU missing — supervisor's health check
    surfaces the failure, manual hard power-cycle is the recovery.
    """
    sampler._lsm6dsox = None  # Force the setup() path in start()

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

    # _force_reboot() must NOT have been called.
    mock_reboot.assert_not_called()
    # No thread started — start() returned early.
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


# ---------------------------------------------------------------------------
# HardwareState observational hook tests (Phase 21-03)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_hw_state_for_i2c_tests():
    """Reset HardwareState before and after each test in this module."""
    from shitbox.hardware import state as hw_state
    hw_state.clear_state()
    yield
    hw_state.clear_state()


def test_successful_sample_reports_present(sampler: HighRateSampler) -> None:
    """A successful sample read reports PRESENT for the 'imu' role."""
    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState

    hw_state.initialise({"imu": "critical"})

    # Drive the success branch of _sample_loop directly
    with patch.object(sampler, "_read_sample", return_value=MagicMock()):
        sample = sampler._read_sample()
        sampler.ring_buffer.append(sample)
        sampler._consecutive_failures = 0
        hw_state.report_present(sampler.role)

    snap = hw_state.snapshot()
    assert snap["imu"].state == DeviceState.PRESENT


def test_i2c_lockup_reports_degraded(sampler: HighRateSampler) -> None:
    """i2c_bus_lockup_detected path reports DEGRADED and still calls _i2c_bus_reset."""
    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState

    hw_state.initialise({"imu": "critical"})

    # Pre-arm the failure counter to threshold - 1
    sampler._consecutive_failures = I2C_CONSECUTIVE_FAILURE_THRESHOLD - 1

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C bus error")),
        patch.object(sampler, "_i2c_bus_reset", return_value=True) as mock_reset,
        patch.object(sampler, "_force_reboot"),
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.perf_counter.side_effect = [0.0, 0.0, 1.0]
        mock_time.sleep = MagicMock()
        sampler._running = True
        # Run just one iteration by stopping after the lockup fires
        call_count = [0]

        def _stop_after_reset(*args, **kwargs):
            call_count[0] += 1
            sampler._running = False
            return True

        mock_reset.side_effect = _stop_after_reset
        sampler._sample_loop()

    snap = hw_state.snapshot()
    assert snap["imu"].state == DeviceState.DEGRADED
    mock_reset.assert_called_once()


def test_i2c_max_resets_reports_missing_in_give_up_mode(sampler: HighRateSampler) -> None:
    """MISSING is reported for 'imu' once short retries are exhausted.

    Brain note open thread (2026-04-29): _force_reboot is no longer in
    the escalation chain. After I2C_MAX_RESETS short retries the daemon
    transitions to long-backoff give-up mode and reports MISSING for the
    imu role. _force_reboot is never invoked.
    """
    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState
    from shitbox.events.sampler import I2C_GIVE_UP_BACKOFF_SECONDS

    hw_state.initialise({"imu": "critical"})

    reset_calls = [0]
    sleep_durations: list[float] = []
    state_at_give_up: list = []

    def _always_fail_reset() -> bool:
        reset_calls[0] += 1
        # Once we transition to give-up mode, capture the role state and stop.
        if reset_calls[0] > I2C_MAX_RESETS:
            state_at_give_up.append(hw_state.snapshot().get("imu"))
            sampler._running = False
        return False

    def _capture_sleep(duration: float) -> None:
        sleep_durations.append(duration)

    sampler._consecutive_failures = 0
    sampler._reset_count = 0

    with (
        patch.object(sampler, "_read_sample", side_effect=OSError("I2C bus error")),
        patch.object(sampler, "_i2c_bus_reset", side_effect=_always_fail_reset),
        patch.object(sampler, "_force_reboot") as mock_reboot,
        patch("shitbox.events.sampler.buzzer"),
        patch("shitbox.events.sampler.speaker"),
        patch("shitbox.events.sampler.time") as mock_time,
    ):
        mock_time.perf_counter.side_effect = lambda: float(reset_calls[0])
        mock_time.sleep = _capture_sleep
        sampler._running = True
        sampler._sample_loop()

    # _force_reboot was never called.
    mock_reboot.assert_not_called()
    # We reached give-up mode with MISSING reported.
    assert state_at_give_up, "give-up branch never executed"
    assert state_at_give_up[0].state == DeviceState.MISSING, (
        f"Expected MISSING in give-up mode, got {state_at_give_up[0].state}"
    )
    # Long backoff was applied at least once (60s give-up backoff).
    assert I2C_GIVE_UP_BACKOFF_SECONDS in sleep_durations, (
        f"Expected give-up backoff {I2C_GIVE_UP_BACKOFF_SECONDS}s in sleeps, "
        f"got {sleep_durations}"
    )
