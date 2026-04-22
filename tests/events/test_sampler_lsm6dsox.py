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

try:
    from adafruit_lsm6ds import AccelRange, GyroRange
except ImportError:
    # Dev-laptop fallback: the library pins these as plain integer class
    # attributes (see adafruit_lsm6ds/__init__.py). Stand-in namespaces let
    # the cache-alignment tests run without the real library present.
    import types

    AccelRange = types.SimpleNamespace(  # type: ignore[assignment,misc]
        RANGE_2G=0,
        RANGE_16G=1,
        RANGE_4G=2,
        RANGE_8G=3,
    )
    GyroRange = types.SimpleNamespace(  # type: ignore[assignment,misc]
        RANGE_250_DPS=0,
        RANGE_500_DPS=1,
        RANGE_1000_DPS=2,
        RANGE_2000_DPS=3,
        RANGE_125_DPS=4,
    )


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


class _FakeLSM6DSOX(MagicMock):
    """MagicMock subclass that simulates the Adafruit driver's range-setter
    side effect: assigning ``accelerometer_range`` also updates
    ``_cached_accel_range`` (same for gyro). The real library does this in
    the property setter — without it the cache-alignment tests can't
    distinguish "setter called" from "cache aligned".
    """

    @property
    def accelerometer_range(self):  # type: ignore[override]
        return self._cached_accel_range

    @accelerometer_range.setter
    def accelerometer_range(self, value):
        # Real driver does: self._accel_range = value (RWBits masked RMW);
        # self._cached_accel_range = value; sleep(0.2). The cache update is
        # the only behaviour the tests care about.
        self._cached_accel_range = value

    @property
    def gyro_range(self):  # type: ignore[override]
        return self._cached_gyro_range

    @gyro_range.setter
    def gyro_range(self, value):
        self._cached_gyro_range = value


def _make_fake_lsm6dsox(
    accel: tuple = (9.81, 0.0, 0.0),
    gyro: tuple = (0.0, 0.0, 0.0),
) -> MagicMock:
    """Build a mock that looks like adafruit_lsm6ds.lsm6dsox.LSM6DSOX."""
    sensor = _FakeLSM6DSOX()
    sensor.acceleration = accel  # m/s²
    sensor.gyro = gyro           # rad/s
    # Seed the Adafruit driver's range cache to the constructor defaults — the
    # state real hardware presents BEFORE any property setter runs. Without
    # these explicit assignments, MagicMock auto-creates Mock sentinels and
    # the cache-alignment tests (22-04) would fail for the wrong reason.
    sensor._cached_accel_range = AccelRange.RANGE_4G
    sensor._cached_gyro_range = GyroRange.RANGE_250_DPS
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


# ---------------------------------------------------------------------------
# Phase 22 / plan 22-04: driver cache alignment after direct register writes
#
# Closes UAT gaps 1 and 3. The Adafruit LSM6DS driver caches
# `_cached_accel_range` / `_cached_gyro_range` at constructor defaults
# (±4g / ±250 dps). Our direct CTRL1_XL=0x52 / CTRL2_G=0x54 writes put the
# hardware at ±2g / ±500 dps but leave the driver caches stale, so
# .acceleration applies a 2x scale factor and .gyro halves the real rate.
# The fix (plan 22-04 Task 2) calls the property setters AFTER the direct
# writes to sync the caches.
# ---------------------------------------------------------------------------


def test_setup_syncs_accel_range_cache_to_2g() -> None:
    """After setup(), sensor._cached_accel_range == AccelRange.RANGE_2G.

    Before Task 2: driver cache stays at the constructor default RANGE_4G
    set by _make_fake_lsm6dsox, so .acceleration would return 2x the real g
    (the stationary mean_z=1.9997 symptom in UAT gap 1).
    """
    sampler = _make_sampler()
    fake_sensor, _ = _fake_sensor_with_i2c_spy()
    # Helper seeds RANGE_4G by default — assert that starting state explicitly.
    assert fake_sensor._cached_accel_range == AccelRange.RANGE_4G
    assert fake_sensor._cached_accel_range == 2  # integer double-guard

    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"):
        sampler.setup()

    assert fake_sensor._cached_accel_range == AccelRange.RANGE_2G, (
        "setup() did not sync the Adafruit driver's accel range cache. "
        f"Expected RANGE_2G, got {fake_sensor._cached_accel_range}. "
        "Fix: set sensor.accelerometer_range = AccelRange.RANGE_2G after "
        "the direct CTRL1_XL=0x52 write."
    )
    assert fake_sensor._cached_accel_range == 0  # integer double-guard


def test_setup_syncs_gyro_range_cache_to_500dps() -> None:
    """After setup(), sensor._cached_gyro_range == GyroRange.RANGE_500_DPS.

    Before Task 2: driver cache stays at the constructor default
    RANGE_250_DPS, so .gyro halves every rotation rate (UAT gap 3).
    """
    sampler = _make_sampler()
    fake_sensor, _ = _fake_sensor_with_i2c_spy()
    assert fake_sensor._cached_gyro_range == GyroRange.RANGE_250_DPS
    assert fake_sensor._cached_gyro_range == 0  # integer double-guard

    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"):
        sampler.setup()

    assert fake_sensor._cached_gyro_range == GyroRange.RANGE_500_DPS, (
        "setup() did not sync the Adafruit driver's gyro range cache. "
        f"Expected RANGE_500_DPS, got {fake_sensor._cached_gyro_range}. "
        "Fix: set sensor.gyro_range = GyroRange.RANGE_500_DPS after "
        "the direct CTRL2_G=0x54 write."
    )
    assert fake_sensor._cached_gyro_range == 1  # integer double-guard


def test_acceleration_returns_correct_g_after_setup() -> None:
    """End-to-end scaling regression: 9.80665 m/s² on Z returns ~1.0 g after setup().

    This is the real regression guard for UAT gap 1. The existing
    test_acceleration_converted_from_m_s2_to_g bypasses setup() and never
    touches the driver-cache path. This test runs setup() end-to-end, so
    the 2x scale bug would fail it in a way no existing test catches.

    We simulate the Adafruit driver's actual behaviour: .acceleration returns
    raw counts scaled by the range indicated by _cached_accel_range. If the
    cache is still at RANGE_4G while hardware is at RANGE_2G, the driver
    multiplies by the ±4g scale factor on ±2g raw data, returning 2x the
    real value — the UAT mean_z=1.9997 symptom exactly.
    """
    sampler = _make_sampler()
    # Hardware is at RANGE_2G (CTRL1_XL=0x52). A stationary IMU reads ~1.0 g
    # along Z — i.e. ~9.80665 m/s² of ACTUAL acceleration. We simulate the
    # driver's scaling: if cache is stale at RANGE_4G, it applies the ±4g
    # scale factor to the same raw register value and returns 2x.
    fake_sensor, _ = _fake_sensor_with_i2c_spy()

    # Adafruit scale table (m/s²/LSB, roughly):
    #   RANGE_2G  -> 0.061 mg/LSB  ->  0.000598325 m/s² per count
    #   RANGE_4G  -> 0.122 mg/LSB  ->  0.00119665  m/s² per count  (2x)
    # Simulate using simple multipliers rather than hunting exact LSB values:
    _SCALE = {
        AccelRange.RANGE_2G: 1.0,
        AccelRange.RANGE_4G: 2.0,  # this is the 2x bug
        AccelRange.RANGE_8G: 4.0,
        AccelRange.RANGE_16G: 8.0,
    }
    # "Actual" stationary reading at RANGE_2G (one g along Z).
    _actual_accel = (0.0, 0.0, 9.80665)

    def _scaled_accel() -> tuple:
        factor = _SCALE.get(fake_sensor._cached_accel_range, 1.0)
        return tuple(v * factor for v in _actual_accel)

    # Replace the static tuple with a PropertyMock bound to the cache state.
    type(fake_sensor).acceleration = property(lambda _self: _scaled_accel())
    fake_sensor.gyro = (0.0, 0.0, 0.0)

    with patch("shitbox.events.sampler.busio.I2C"), \
         patch("shitbox.events.sampler.LSM6DSOX", return_value=fake_sensor), \
         patch("shitbox.events.sampler._HAS_LSM6DS", True), \
         patch("shitbox.events.sampler.time.sleep"):
        sampler.setup()

    sample = sampler._read_sample()

    # On a stationary IMU the scaled reading is 1.0 g along gravity, not 2.0.
    assert sample.az == pytest.approx(1.0, abs=0.01), (
        f"Expected az=1.0 g from 9.80665 m/s² input after setup(), got {sample.az}. "
        "If this reads ~2.0 the Adafruit driver cache is stuck at RANGE_4G "
        "while hardware is at RANGE_2G — plan 22-04 fix missing."
    )
    assert sample.ax == pytest.approx(0.0, abs=0.01)
    assert sample.ay == pytest.approx(0.0, abs=0.01)
