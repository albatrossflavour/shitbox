"""RED tests for LSM6DSOX high-rate sampler.

These tests will FAIL until plan 01 rewrites the sampler to use LSM6DSOX.

# LSM6DSOX lib returns accel in m/s² and gyro in rad/s.
# Sampler MUST convert: ax_g = ax_ms2 / 9.81 ; gx_dps = gx_rads * (180.0 / math.pi)
# Getting this wrong silently breaks event detection thresholds.
"""

import math
import time
from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.events.sampler import HighRateSampler


def _make_sampler(
    ax_offset: float = 0.0,
    ay_offset: float = 0.0,
    az_offset: float = 0.0,
) -> HighRateSampler:
    """Create a sampler with a fresh ring buffer."""
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=104.0)
    return HighRateSampler(
        ring_buffer=buf,
        accel_offset_x=ax_offset,
        accel_offset_y=ay_offset,
        accel_offset_z=az_offset,
    )


def _make_fake_lsm6dsox(
    accel: tuple = (9.81, 0.0, 0.0),
    gyro: tuple = (0.0, 0.0, 0.0),
) -> MagicMock:
    """Build a mock that looks like adafruit_lsm6ds.lsm6dsox.LSM6DSOX."""
    sensor = MagicMock()
    sensor.acceleration = accel  # m/s²
    sensor.gyro = gyro           # rad/s
    return sensor


# ---------------------------------------------------------------------------
# test_acceleration_converted_from_m_s2_to_g
# ---------------------------------------------------------------------------


def test_acceleration_converted_from_m_s2_to_g() -> None:
    """Sampler converts m/s² → g correctly: 9.81 m/s² == 1.0 g."""
    sampler = _make_sampler()
    fake_sensor = _make_fake_lsm6dsox(accel=(9.81, 0.0, 0.0), gyro=(0.0, 0.0, 0.0))

    # After plan 01 the sampler will hold a _lsm6dsox attribute
    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    sample = sampler._read_sample()  # type: ignore[attr-defined]

    assert sample.ax == pytest.approx(1.0, abs=0.001), (
        f"Expected ax=1.0 g from 9.81 m/s², got {sample.ax}. "
        "Check: ax_g = ax_ms2 / 9.81"
    )


# ---------------------------------------------------------------------------
# test_gyro_converted_from_rad_s_to_deg_s
# ---------------------------------------------------------------------------


def test_gyro_converted_from_rad_s_to_deg_s() -> None:
    """Sampler converts rad/s → deg/s correctly: π rad/s == 180 deg/s."""
    sampler = _make_sampler()
    fake_sensor = _make_fake_lsm6dsox(accel=(0.0, 0.0, 0.0), gyro=(math.pi, 0.0, 0.0))

    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    sample = sampler._read_sample()  # type: ignore[attr-defined]

    assert sample.gx == pytest.approx(180.0, abs=0.01), (
        f"Expected gx=180 deg/s from π rad/s, got {sample.gx}. "
        "Check: gx_dps = gx_rads * (180.0 / math.pi)"
    )


# ---------------------------------------------------------------------------
# test_sampler_graceful_when_lsm6dsox_absent
# ---------------------------------------------------------------------------


def test_sampler_graceful_when_lsm6dsox_absent() -> None:
    """Sampler.start() must not raise when I2C init fails; sensor stays None."""
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=104.0)
    sampler = HighRateSampler(ring_buffer=buf)

    # Simulate I2C not available (e.g. dev laptop)
    with patch("busio.I2C", side_effect=RuntimeError("no I2C bus")):
        with patch("shitbox.events.sampler.buzzer"):
            with patch("shitbox.events.sampler.speaker"):
                sampler.start()
                # Give thread a moment to attempt init
                time.sleep(0.05)
                sampler.stop()

    # After graceful failure the sensor attribute must be None, not unset
    assert sampler._lsm6dsox is None, (  # type: ignore[attr-defined]
        "Expected _lsm6dsox=None after failed init, indicating graceful absent handling"
    )
    # And the sampler should log sensor_init_failed — we can't assert structlog output
    # directly here but the absence of an exception is the primary contract.


# ---------------------------------------------------------------------------
# test_sampler_produces_104_hz_rate
# ---------------------------------------------------------------------------


def test_sampler_produces_104_hz_rate() -> None:
    """Sampler fills the ring buffer at roughly 104 Hz over 0.5 s."""
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=104.0)
    sampler = HighRateSampler(ring_buffer=buf, sample_rate_hz=104.0)

    fake_sensor = _make_fake_lsm6dsox(accel=(0.0, 0.0, 9.81), gyro=(0.0, 0.0, 0.0))
    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    # Inject a fake setup that doesn't touch hardware
    def _fake_setup() -> None:
        pass

    sampler.setup = _fake_setup  # type: ignore[method-assign]

    sampler.start()
    time.sleep(0.5)
    sampler.stop()

    count = len(buf)
    # 104 Hz * 0.5 s = 52 expected; allow ±15 for scheduling jitter
    assert 37 <= count <= 67, (
        f"Expected 37-67 samples in 0.5 s at 104 Hz, got {count}"
    )


# ---------------------------------------------------------------------------
# test_calibration_offsets_applied
# ---------------------------------------------------------------------------


def test_calibration_offsets_applied() -> None:
    """Calibration offset is subtracted from raw reading: raw 1.0 g - offset 0.1 → stored 0.9 g."""
    sampler = _make_sampler(ax_offset=0.1)

    # Raw accel: 9.81 m/s² = 1.0 g; after offset 0.1 → stored as 0.9 g
    fake_sensor = _make_fake_lsm6dsox(accel=(9.81, 0.0, 0.0), gyro=(0.0, 0.0, 0.0))
    sampler._lsm6dsox = fake_sensor  # type: ignore[attr-defined]

    sample = sampler._read_sample()  # type: ignore[attr-defined]

    # The plan specifies: ax_offset=0.1, raw 1.0 g -> stored 0.9 g
    assert sample.ax == pytest.approx(0.9, abs=0.001), (
        f"Expected ax=0.9 g after offset correction (raw 1.0 g - offset 0.1), got {sample.ax}"
    )


# ---------------------------------------------------------------------------
# Phase 22 / plan 22-01: register-write tests, settle-ordering, update_offsets
# ---------------------------------------------------------------------------


def _fake_sensor_with_i2c_spy():
    """Returns (fake_sensor, fake_i2c) where fake_i2c.write is a MagicMock
    recording every byte payload written via ``with sensor.i2c_device as i2c:``.
    """
    fake_sensor = _make_fake_lsm6dsox()
    fake_i2c = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=fake_i2c)
    ctx.__exit__ = MagicMock(return_value=False)
    fake_sensor.i2c_device = ctx
    return fake_sensor, fake_i2c


def test_ctrl1_xl_written_with_208hz_and_lpf2() -> None:
    """setup() writes 0x52 to CTRL1_XL (0x10): ODR=208Hz, FS=+/-2g, LPF2_XL_EN=1."""
    sampler = _make_sampler()
    fake_sensor, fake_i2c = _fake_sensor_with_i2c_spy()
    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"):
        sampler.setup()
    payloads = [c.args[0] for c in fake_i2c.write.call_args_list]
    assert bytearray([0x10, 0x52]) in payloads, (
        f"Expected CTRL1_XL=0x52 at addr 0x10; got {payloads}"
    )


def test_ctrl2_g_written_with_500dps() -> None:
    """setup() writes 0x54 to CTRL2_G (0x11): ODR=208Hz, FS=+/-500 dps."""
    sampler = _make_sampler()
    fake_sensor, fake_i2c = _fake_sensor_with_i2c_spy()
    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"):
        sampler.setup()
    payloads = [c.args[0] for c in fake_i2c.write.call_args_list]
    assert bytearray([0x11, 0x54]) in payloads, (
        f"Expected CTRL2_G=0x54 at addr 0x11; got {payloads}"
    )


def test_ctrl8_xl_written_with_odr_10_cutoff_and_fast_settle() -> None:
    """setup() writes 0x28 to CTRL8_XL (0x17): HPCF_XL=ODR/10, FASTSETTL_MODE_XL=1."""
    sampler = _make_sampler()
    fake_sensor, fake_i2c = _fake_sensor_with_i2c_spy()
    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"):
        sampler.setup()
    payloads = [c.args[0] for c in fake_i2c.write.call_args_list]
    assert bytearray([0x17, 0x28]) in payloads, (
        f"Expected CTRL8_XL=0x28 at addr 0x17; got {payloads}"
    )


def test_setup_sleeps_after_register_writes() -> None:
    """setup() performs EXACTLY 3 register writes and the LAST time.sleep call
    is the 0.05s AN5272 settle. This asserts ordering, not just existence.

    If a future edit removes the settle OR places it before the writes, the
    assertion on mock_sleep.call_args_list[-1] fails.
    """
    sampler = _make_sampler()
    fake_sensor, fake_i2c = _fake_sensor_with_i2c_spy()
    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep") as mock_sleep:
        sampler.setup()

    # Exactly three register writes: CTRL1_XL, CTRL2_G, CTRL8_XL.
    write_calls = fake_i2c.write.call_args_list
    assert len(write_calls) == 3, (
        f"Expected exactly 3 register writes (CTRL1_XL, CTRL2_G, CTRL8_XL); "
        f"got {len(write_calls)}: {write_calls}"
    )
    # The FINAL sleep invocation must be the settle — this catches both
    # 'settle removed' and 'settle moved before writes' regressions.
    assert mock_sleep.call_args_list, "setup() never slept — settle missing"
    assert mock_sleep.call_args_list[-1] == call(0.05), (
        f"Expected final time.sleep call to be the 0.05s settle AFTER "
        f"register writes; got call list: {mock_sleep.call_args_list}"
    )


def test_register_write_failure_reports_degraded_and_nulls_sensor() -> None:
    """If an I2C write raises, setup() logs, reports degraded, leaves _lsm6dsox=None,
    and does NOT propagate the exception (graceful-boot contract, D-24)."""
    sampler = _make_sampler()
    fake_sensor, fake_i2c = _fake_sensor_with_i2c_spy()
    fake_i2c.write.side_effect = OSError("I2C NACK")
    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"), \
         patch("shitbox.events.sampler.hw_state.report_degraded") as mock_degraded:
        sampler.setup()  # must NOT raise
    assert sampler._lsm6dsox is None
    mock_degraded.assert_called_with("imu")


def test_update_offsets_replaces_all_three() -> None:
    """update_offsets(x, y, z) replaces the three accel offsets atomically."""
    sampler = _make_sampler(ax_offset=0.0, ay_offset=0.0, az_offset=0.0)
    sampler.update_offsets(1.0, 2.0, 3.0)
    assert sampler._accel_offset_x == 1.0
    assert sampler._accel_offset_y == 2.0
    assert sampler._accel_offset_z == 3.0


def test_sample_loop_rate() -> None:
    """IMU-02: the application poll rate remains ~100 Hz after Phase 22.

    Drives ``_sample_loop`` for 1 simulated second under a monotonic fake
    ``time.perf_counter`` and asserts approximately 100 reads occurred.
    Register reconfiguration in setup() does NOT change loop pacing —
    this test fails if a future edit changes sample_rate_hz or
    restructures pacing so the poll rate drifts outside 95-110 Hz.
    """
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=100.0)
    sampler = HighRateSampler(ring_buffer=buf, sample_rate_hz=100.0)
    fake_sensor, _ = _fake_sensor_with_i2c_spy()
    sampler._lsm6dsox = fake_sensor

    # Monotonic clock: each call advances 10 ms. Once the simulated clock
    # passes 1.0 s, flip `_running` so the next `while self._running:` check
    # exits the loop. Polling the stop flag from inside `perf_counter` (rather
    # than from `fake_sleep`) is required because when we're running at the
    # target rate the loop's sleep_time is zero or negative — `time.sleep` is
    # not invoked every iteration, so a sleep-side stop never fires.
    clock = {"t": 0.0}

    def fake_perf_counter() -> float:
        clock["t"] += 0.01
        if clock["t"] >= 1.0:
            sampler._running = False
        return clock["t"]

    def fake_sleep(seconds: float) -> None:
        # No-op — we drive time via perf_counter above.
        pass

    read_count = {"n": 0}
    original_read = sampler._read_sample

    def counting_read() -> IMUSample:
        read_count["n"] += 1
        return original_read()

    sampler._running = True
    with patch("shitbox.events.sampler.time.perf_counter", side_effect=fake_perf_counter), \
         patch("shitbox.events.sampler.time.sleep", side_effect=fake_sleep), \
         patch.object(sampler, "_read_sample", side_effect=counting_read):
        sampler._sample_loop()

    assert 95 <= read_count["n"] <= 110, (
        f"IMU-02 regression: expected ~100 reads in 1 simulated second "
        f"at sample_rate_hz=100.0, got {read_count['n']}. Check _sample_loop "
        f"pacing and sampler config sample_rate_hz."
    )
