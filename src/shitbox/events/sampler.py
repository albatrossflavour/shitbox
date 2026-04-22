"""High-rate LSM6DSOX sampler for event detection."""

import math
import subprocess
import threading
import time
from typing import Callable, Optional

try:
    import board
    import busio
    from adafruit_lsm6ds import AccelRange, GyroRange
    from adafruit_lsm6ds.lsm6dsox import LSM6DSOX

    _HAS_LSM6DS = True
except ImportError:
    # Dev-laptop fallback: bind stand-in namespaces so tests can patch
    # ``shitbox.events.sampler.busio.I2C`` and ``shitbox.events.sampler.LSM6DSOX``
    # without a ``create=True`` on every patch. Production code guards on
    # ``_HAS_LSM6DS`` before using any of these. AccelRange / GyroRange use
    # the same integer constants the real library pins (see
    # adafruit_lsm6ds/__init__.py) so tests can assert against them directly.
    import types

    board = types.SimpleNamespace(SCL=None, SDA=None)  # type: ignore[assignment]
    busio = types.SimpleNamespace(I2C=None)  # type: ignore[assignment]
    AccelRange = types.SimpleNamespace(  # type: ignore[assignment,misc]
        RANGE_2G=0, RANGE_16G=1, RANGE_4G=2, RANGE_8G=3,
    )
    GyroRange = types.SimpleNamespace(  # type: ignore[assignment,misc]
        RANGE_250_DPS=0, RANGE_500_DPS=1, RANGE_1000_DPS=2,
        RANGE_2000_DPS=3, RANGE_125_DPS=4,
    )

    def LSM6DSOX(*args, **kwargs):  # type: ignore[no-redef]
        raise ImportError("adafruit-circuitpython-lsm6ds not installed")

    _HAS_LSM6DS = False

from shitbox.capture import buzzer, speaker
from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.hardware import state as hw_state
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Unit conversion constants
MS2_PER_G = 9.80665             # convert m/s² -> g  (LSM6DSOX returns m/s²)
DEG_PER_RAD = 180.0 / math.pi  # convert rad/s -> deg/s (LSM6DSOX returns rad/s)

# I2C bus lockup recovery constants
I2C_CONSECUTIVE_FAILURE_THRESHOLD = 5  # Triggers recovery after 5 failures (~50ms at 100 Hz)
I2C_RECOVERY_DELAY_SECONDS = 0.1       # 100ms delay after GPIO cleanup before reinit
SCL_PIN = 3                            # GPIO3 = physical pin 5
SDA_PIN = 2                            # GPIO2 = physical pin 3
I2C_MAX_RESETS = 3                     # Maximum recovery attempts before forced reboot
I2C_RESET_BACKOFF_SECONDS = [0, 2, 5]  # Seconds to wait before each attempt (index = attempt)

# LSM6DSOX control register addresses (ref: STMicroelectronics lsm6dsox_reg.h;
# Adafruit _LSM6DS_CTRL1_XL / CTRL2_G / CTRL8_XL constants — see 22-RESEARCH.md)
REG_CTRL1_XL = 0x10  # Accel: ODR + FS + LPF2_XL_EN
REG_CTRL2_G = 0x11   # Gyro:  ODR + FS
REG_CTRL8_XL = 0x17  # Accel: LPF2 cutoff (HPCF_XL), fast-settle

# Values derived in 22-RESEARCH.md "Register-Level Changes":
# CTRL1_XL = ODR_XL=0b0101 (208 Hz) << 4 | FS_XL=0b00 (+/-2g) << 2 | LPF2_XL_EN=1 << 1 = 0x52
CTRL1_XL_VALUE = 0x52
# CTRL2_G  = ODR_G=0b0101 (208 Hz) << 4 | FS_G=0b01 (+/-500 dps) << 2 = 0x54
CTRL2_G_VALUE = 0x54
# CTRL8_XL = HPCF_XL=0b001 (ODR/10 ~= 20.8 Hz) << 5 | FASTSETTL_MODE_XL=1 << 3 = 0x28
CTRL8_XL_VALUE = 0x28
# AN5272: LPF2 filter settling is worst-case 8/ODR = ~38.5 ms at 208 Hz.
# 50 ms is the comfortable pad; fast-settle halves it anyway. See setup().
FILTER_SETTLE_SECONDS = 0.05

# Plan 22-05: poll-rate diagnostics. We observe ~60-80 Hz app poll rate on real
# hardware where the target is 100 Hz (UAT gap 2). Root cause is unknown —
# could be I2C contention, Adafruit getter overhead, ring buffer append lock,
# or on_sample callback cost. These two constants drive the two structlog
# diagnostic lines `_sample_loop` emits:
#
#   sampler_read_rate        — once per _RATE_LOG_INTERVAL_SECONDS window,
#                              observed samples_per_second + dropped delta.
#   sampler_timing_snapshot  — once every _TIMING_SNAPSHOT_EVERY_N_SAMPLES
#                              successful reads, per-stage latency breakdown.
#
# The timing snapshot is guarded by a modulo check so the four extra
# time.perf_counter() calls only fire on every 100th iteration — important
# because the IMU-02 `test_sample_loop_rate` pins the per-iteration perf_counter
# count (see tests/events/test_sampler_lsm6dsox.py::test_sample_loop_rate).
_TIMING_SNAPSHOT_EVERY_N_SAMPLES = 100  # ~1 Hz at 100 Hz target rate
_RATE_LOG_INTERVAL_SECONDS = 10.0


def _write_register(sensor: object, reg_addr: int, value: int) -> None:
    """Write a single byte to an LSM6DSOX control register.

    Uses the same ``with sensor.i2c_device as i2c:`` pattern the Adafruit
    driver uses internally for MLC upload (ref:
    adafruit_lsm6ds/__init__.py load_mlc). OSError/ValueError from this
    call must be caught by the surrounding try/except in setup() so the
    sampler falls through to the I2C recovery ladder and reports
    degraded via hw_state (D-24 — graceful boot contract).
    """
    buf = bytearray([reg_addr, value & 0xFF])
    with sensor.i2c_device as i2c:  # type: ignore[attr-defined]
        i2c.write(buf)


class HighRateSampler:
    """High-rate IMU sampler using LSM6DSOX.

    Samples at ~104 Hz (application poll rate; sensor ODR is 208 Hz internally
    after phase 22 and the intermediate sample is silently dropped) and feeds
    data into a ring buffer. Designed to run in its own thread with minimal
    latency.
    """

    def __init__(
        self,
        ring_buffer: RingBuffer,
        sample_rate_hz: float = 104.0,
        accel_offset_x: float = 0.0,
        accel_offset_y: float = 0.0,
        accel_offset_z: float = 0.0,
        on_sample: Optional[Callable[[IMUSample], None]] = None,
    ):
        """Initialise high-rate sampler.

        Args:
            ring_buffer: Buffer to store samples.
            sample_rate_hz: Target application poll rate in Hz (sensor ODR
                is configured to 208 Hz; the poll-loop decimates to this rate).
            accel_offset_x: Bias correction for ax (g), subtracted after unit conversion.
            accel_offset_y: Bias correction for ay (g), subtracted after unit conversion.
            accel_offset_z: Bias correction for az (g), subtracted after unit conversion.
            on_sample: Optional callback for each sample.
        """
        self.ring_buffer = ring_buffer
        self.sample_rate_hz = sample_rate_hz
        self.sample_interval = 1.0 / sample_rate_hz
        self.on_sample = on_sample
        self._accel_offset_x = accel_offset_x
        self._accel_offset_y = accel_offset_y
        self._accel_offset_z = accel_offset_z

        self._lsm6dsox: Optional[object] = None
        self._i2c: Optional[object] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stats
        self.samples_total = 0
        self.samples_dropped = 0
        self._last_sample_time = 0.0

        # Hardware state role for observational reporting
        self.role = "imu"

        # I2C lockup recovery
        self._consecutive_failures: int = 0
        self._reset_count: int = 0

    def setup(self) -> None:
        """Initialise LSM6DSOX for high-rate sampling.

        On failure (hardware absent, I2C error), logs sensor_init_failed and
        sets _lsm6dsox = None. Does NOT raise -- graceful degradation (D-24).
        """
        try:
            if not _HAS_LSM6DS:
                raise ImportError("adafruit-circuitpython-lsm6ds not installed")
            self._i2c = busio.I2C(board.SCL, board.SDA)  # type: ignore[name-defined]
            sensor = LSM6DSOX(self._i2c)  # type: ignore[name-defined]
            # Phase 22: direct register writes. Bypasses the Adafruit
            # property getters to avoid read-modify-write clobbering
            # LPF2_XL_EN (see 22-RESEARCH Pitfall 2).
            _write_register(sensor, REG_CTRL1_XL, CTRL1_XL_VALUE)  # ODR=208 Hz, LPF2_XL_EN=1
            _write_register(sensor, REG_CTRL2_G,  CTRL2_G_VALUE)   # ODR=208 Hz, FS=+/-500 dps
            _write_register(sensor, REG_CTRL8_XL, CTRL8_XL_VALUE)  # HPCF_XL=ODR/10, fast-settle
            # Phase 22 plan 22-04: sync the Adafruit driver's range cache to match
            # the hardware state produced by the direct writes above.
            # _cached_accel_range / _cached_gyro_range are used by the .acceleration
            # and .gyro property getters to scale raw counts. Without this sync, the
            # cache stays at constructor defaults (+/-4g / +/-250 dps) and readings
            # are off by a 2x scale factor — the root cause of the UAT gap-1
            # stationary mean_z=1.9997 symptom and the gap-3 halved-gyro consequence.
            #
            # These setters use RWBits(2, REG, 2), which masks off only the FS bits
            # [3:2]. Our direct CTRL1_XL=0x52 write already set FS_XL = 0b00
            # (RANGE_2G), so the underlying register write is a no-op; LPF2_XL_EN
            # (bit 1) and ODR_XL (bits [7:4]) are preserved through the RMW. Same
            # logic for CTRL2_G: FS_G = 0b01 already matches RANGE_500_DPS, ODR_G
            # preserved.
            #
            # ORDERING NOTE (load-bearing): each setter calls sleep(0.2) internally.
            # Our AN5272 50 ms settle MUST remain the LAST time.sleep in setup() — it
            # guards the filter chain, not the range cache. Both setter calls go
            # BEFORE the existing 50 ms sleep.
            sensor.accelerometer_range = AccelRange.RANGE_2G
            sensor.gyro_range = GyroRange.RANGE_500_DPS
            log.debug(
                "lsm6dsox_driver_cache_synced",
                accel_range="RANGE_2G",
                gyro_range="RANGE_500_DPS",
            )
            # AN5272 (STMicroelectronics LSM6DSOX app note): worst-case LPF2 settling
            # is 8/ODR seconds after filter reconfiguration. At 208 Hz that is ~38.5 ms.
            # Fast-settle mode (CTRL8_XL bit 3) converges in 2 samples (~9.6 ms) but the
            # conservative pad keeps the detector from seeing transients. DO NOT REMOVE
            # this sleep or reorder it before the register writes — without it running
            # AFTER all three writes (AND the property setters that follow), the first
            # ~8 samples can falsely trigger HARD_BRAKE/HIGH_G at boot. The Task 2 /
            # plan 22-04 Task 3 unit tests pin this ordering as the LAST time.sleep.
            time.sleep(FILTER_SETTLE_SECONDS)
            self._lsm6dsox = sensor
            log.info("lsm6dsox_initialised", sample_rate_hz=self.sample_rate_hz)
        except (OSError, ValueError, ImportError, RuntimeError, Exception) as e:
            # Phase 22: differentiate register-config failure from sensor-detection
            # failure in the log message. Both paths null _lsm6dsox so start()
            # triggers the I2C recovery ladder identically.
            log.error("sensor_init_failed", sensor="LSM6DSOX", error=str(e))
            hw_state.report_degraded(self.role)
            self._lsm6dsox = None

    def update_offsets(self, x: float, y: float, z: float) -> None:
        """Replace the three accel offsets live, without restarting the sampler.

        Called by the engine telemetry loop when auto-zero accepts a new
        stationary-window mean (plan 22-03). Assignment to three independent
        float attributes is not atomic as a sequence in CPython; a worst-case
        interleaved read from the sampler thread would see x updated but y/z
        not yet. The sub-0.05 g delta per assignment is below detector noise
        and is accepted as negligible (see 22-RESEARCH Assumption A4).
        """
        self._accel_offset_x = x
        self._accel_offset_y = y
        self._accel_offset_z = z
        log.info(
            "sampler_offsets_updated",
            offset_x=round(x, 4),
            offset_y=round(y, 4),
            offset_z=round(z, 4),
        )

    def start(self) -> None:
        """Start sampling in background thread."""
        if self._running:
            return

        if self._lsm6dsox is None:
            for attempt in range(I2C_MAX_RESETS + 1):
                try:
                    self.setup()
                except Exception as e:
                    log.error("sampler_setup_exception", attempt=attempt + 1, error=str(e))
                if self._lsm6dsox is not None:
                    break
                if attempt < I2C_MAX_RESETS:
                    log.error("sampler_setup_failed", attempt=attempt + 1)
                    buzzer.beep_i2c_lockup()
                    speaker.speak_i2c_lockup()
                    backoff = I2C_RESET_BACKOFF_SECONDS[attempt]
                    if backoff > 0:
                        time.sleep(backoff)
                    recovered = self._i2c_bus_reset()
                    if recovered:
                        break
                else:
                    log.critical("sampler_setup_unrecoverable")
                    self._force_reboot()
                    return

        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        log.info("high_rate_sampler_started", rate_hz=self.sample_rate_hz)

    def stop(self) -> None:
        """Stop sampling."""
        self._running = False
        self._reset_count = 0
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        log.info(
            "high_rate_sampler_stopped",
            samples_total=self.samples_total,
            samples_dropped=self.samples_dropped,
        )

    def _sample_loop(self) -> None:
        """Main sampling loop - runs at target rate."""
        if self._lsm6dsox is None:
            log.warning("high_rate_sampler_no_sensor_exiting")
            return

        next_sample_time = time.perf_counter()
        # Plan 22-05: fixed-cadence rate instrumentation. `rate_window_samples`
        # counts successful reads in the current 10 s window; baseline of
        # `samples_dropped` at window start lets us emit the per-window drop
        # delta rather than the lifetime counter.
        last_rate_log = next_sample_time
        rate_window_samples = 0
        rate_window_dropped_baseline = self.samples_dropped

        while self._running:
            now = time.perf_counter()

            # Check if we're behind schedule
            if now > next_sample_time + self.sample_interval:
                self.samples_dropped += 1
                next_sample_time = now

            # Wait until next sample time
            sleep_time = next_sample_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Read sample
            try:
                if self._lsm6dsox is None:
                    raise OSError("sensor is None — I2C reinit failed")
                # Plan 22-05: only time every Nth read. The unconditional
                # `perf_counter` calls in the simpler target shape would break
                # the IMU-02 `test_sample_loop_rate` pin, so we gate the four
                # timestamps behind the same modulo check that decides whether
                # to emit `sampler_timing_snapshot`. Non-snapshot iterations do
                # exactly one perf_counter call, matching pre-22-05 behaviour.
                do_timing = (
                    (self.samples_total + 1) % _TIMING_SNAPSHOT_EVERY_N_SAMPLES == 0
                )

                t_read_start = time.perf_counter() if do_timing else 0.0
                sample = self._read_sample()
                t_read_done = time.perf_counter() if do_timing else 0.0

                self.ring_buffer.append(sample)
                t_append_done = time.perf_counter() if do_timing else 0.0

                self.samples_total += 1
                rate_window_samples += 1
                self._consecutive_failures = 0
                hw_state.report_present(self.role)

                if self.on_sample:
                    self.on_sample(sample)
                t_callback_done = time.perf_counter() if do_timing else 0.0

                if do_timing:
                    log.info(
                        "sampler_timing_snapshot",
                        i2c_read_ms=round((t_read_done - t_read_start) * 1000.0, 3),
                        ring_buffer_append_ms=round(
                            (t_append_done - t_read_done) * 1000.0, 3
                        ),
                        on_sample_callback_ms=round(
                            (t_callback_done - t_append_done) * 1000.0, 3
                        ),
                        total_cycle_ms=round(
                            (t_callback_done - t_read_start) * 1000.0, 3
                        ),
                        samples_total=self.samples_total,
                    )

            except OSError as e:
                log.error("sample_read_error", error=str(e))
                self._consecutive_failures += 1

                if self._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
                    log.warning(
                        "i2c_bus_lockup_detected",
                        consecutive_failures=self._consecutive_failures,
                        reset_attempt=self._reset_count + 1,
                        max_resets=I2C_MAX_RESETS,
                    )
                    hw_state.report_degraded(self.role)
                    buzzer.beep_i2c_lockup()
                    speaker.speak_i2c_lockup()

                    backoff = I2C_RESET_BACKOFF_SECONDS[
                        min(self._reset_count, len(I2C_RESET_BACKOFF_SECONDS) - 1)
                    ]
                    if backoff > 0:
                        time.sleep(backoff)

                    self._reset_count += 1
                    recovered = self._i2c_bus_reset()

                    if recovered:
                        log.info("i2c_bus_recovery_successful", attempt=self._reset_count)
                        buzzer.beep_service_recovered("i2c")
                        speaker.speak_service_recovered()
                        self._consecutive_failures = 0
                        self._reset_count = 0
                    elif self._reset_count >= I2C_MAX_RESETS:
                        log.critical("i2c_max_resets_exceeded", reset_count=self._reset_count)
                        hw_state.report_missing(self.role)
                        self._force_reboot()

            except Exception as e:
                log.error("sample_read_error", error=str(e))
                self._consecutive_failures += 1

            # Plan 22-05: periodic rate log at fixed 10 s cadence. Uses `now`
            # captured at loop top — no extra perf_counter call. Window is
            # windowed: `rate_window_samples` counts successful reads in this
            # window; `samples_dropped_delta` is dropped count change since
            # the window began.
            if now - last_rate_log >= _RATE_LOG_INTERVAL_SECONDS:
                elapsed = now - last_rate_log
                dropped_delta = self.samples_dropped - rate_window_dropped_baseline
                log.info(
                    "sampler_read_rate",
                    samples_per_second=round(rate_window_samples / elapsed, 2),
                    target_hz=self.sample_rate_hz,
                    window_seconds=round(elapsed, 2),
                    samples_dropped_delta=dropped_delta,
                )
                rate_window_samples = 0
                rate_window_dropped_baseline = self.samples_dropped
                last_rate_log = now

            next_sample_time += self.sample_interval

    def _i2c_bus_reset(self) -> bool:
        """Attempt 9-clock bit-bang recovery to release a stuck I2C slave.

        Pulses SCL 9 times to allow a slave device holding SDA low to complete
        its transaction and release the bus. Then generates a STOP condition,
        performs selective GPIO cleanup, waits for the I2C driver to reclaim
        the pins, and reinitialises the LSM6DSOX.

        Returns:
            True if the bus was successfully recovered and the sensor
            reinitialised; False on any failure.
        """
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]
        except ImportError:
            log.error("rpi_gpio_not_available", hint="Cannot perform I2C bit-bang recovery")
            return False

        # Close the existing I2C connection
        try:
            if self._i2c is not None:
                self._i2c.deinit()  # type: ignore[attr-defined]
        except Exception:
            pass

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(SCL_PIN, GPIO.OUT, initial=GPIO.HIGH)

            # Pulse SCL 9 times to release stuck slave
            for _ in range(9):
                GPIO.output(SCL_PIN, GPIO.LOW)
                time.sleep(0.000005)  # 5 microsecond half-cycle
                GPIO.output(SCL_PIN, GPIO.HIGH)
                time.sleep(0.000005)  # 5 microsecond half-cycle

            # Generate STOP condition: SDA goes HIGH while SCL is HIGH
            GPIO.setup(SDA_PIN, GPIO.OUT, initial=GPIO.LOW)
            time.sleep(0.000005)
            GPIO.output(SDA_PIN, GPIO.HIGH)

            # Selective cleanup — do NOT call global GPIO.cleanup()
            GPIO.cleanup([SCL_PIN, SDA_PIN])

        except Exception as e:
            log.error("i2c_bitbang_gpio_error", error=str(e))
            return False

        # Wait for the I2C driver to reclaim the pins
        time.sleep(I2C_RECOVERY_DELAY_SECONDS)

        self.setup()
        return self._lsm6dsox is not None

    def _force_reboot(self) -> None:
        """Force a system reboot after unrecoverable I2C failure."""
        log.critical("i2c_recovery_failed_forcing_reboot")
        subprocess.run(["sudo", "systemctl", "reboot"], check=False)

    def _read_sample(self) -> IMUSample:
        """Read accelerometer and gyroscope data from LSM6DSOX."""
        ax_ms2, ay_ms2, az_ms2 = self._lsm6dsox.acceleration  # type: ignore[union-attr]
        gx_rads, gy_rads, gz_rads = self._lsm6dsox.gyro  # type: ignore[union-attr]

        # UNIT CONVERSION -- m/s² -> g, rad/s -> deg/s.
        # The event detector thresholds are in g and deg/s; getting this wrong
        # silently breaks HARD_BRAKE / HIGH_G / BIG_CORNER / ROUGH_ROAD.
        ax = ax_ms2 / MS2_PER_G - self._accel_offset_x
        ay = ay_ms2 / MS2_PER_G - self._accel_offset_y
        az = az_ms2 / MS2_PER_G - self._accel_offset_z
        gx = gx_rads * DEG_PER_RAD
        gy = gy_rads * DEG_PER_RAD
        gz = gz_rads * DEG_PER_RAD

        return IMUSample(timestamp=time.time(), ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz)

    def latest_sample(self) -> Optional[IMUSample]:
        """Return the most recent IMUSample from the ring buffer, or None if empty.

        Thread-safe: delegates to RingBuffer.get_latest() which holds its own lock.
        Used by IMUHeadingCollector at 10 Hz to fuse mag + accel/gyro.
        """
        samples = self.ring_buffer.get_latest(1)
        return samples[0] if samples else None

    def read_once(self) -> IMUSample:
        """Read a single sample (for testing/calibration)."""
        if self._lsm6dsox is None:
            self.setup()
        return self._read_sample()

    @property
    def actual_rate(self) -> float:
        """Calculate actual sample rate from recent samples."""
        samples = self.ring_buffer.get_latest(100)
        if len(samples) < 2:
            return 0.0
        duration = samples[-1].timestamp - samples[0].timestamp
        if duration <= 0:
            return 0.0
        return (len(samples) - 1) / duration
