"""High-rate LSM6DSOX sampler for event detection."""

import math
import subprocess
import threading
import time
from typing import Callable, Optional

try:
    import board
    import busio
    from adafruit_lsm6ds import Rate
    from adafruit_lsm6ds.lsm6dsox import LSM6DSOX

    _HAS_LSM6DS = True
except ImportError:
    _HAS_LSM6DS = False

from shitbox.capture import buzzer, speaker
from shitbox.events.ring_buffer import IMUSample, RingBuffer
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


class HighRateSampler:
    """High-rate IMU sampler using LSM6DSOX.

    Samples at ~104 Hz (LSM6DSOX Rate.RATE_104_HZ) and feeds data into a ring
    buffer. Designed to run in its own thread with minimal latency.
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
            sample_rate_hz: Target sample rate (104.0 matches Rate.RATE_104_HZ).
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
            sensor.accelerometer_data_rate = Rate.RATE_104_HZ  # type: ignore[name-defined]
            sensor.gyro_data_rate = Rate.RATE_104_HZ  # type: ignore[name-defined]
            self._lsm6dsox = sensor
            log.info("lsm6dsox_initialised", sample_rate_hz=self.sample_rate_hz)
        except (OSError, ValueError, ImportError, RuntimeError, Exception) as e:
            log.error("sensor_init_failed", sensor="LSM6DSOX", error=str(e))
            self._lsm6dsox = None

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
                sample = self._read_sample()
                self.ring_buffer.append(sample)
                self.samples_total += 1
                self._consecutive_failures = 0

                if self.on_sample:
                    self.on_sample(sample)

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
                        self._force_reboot()

            except Exception as e:
                log.error("sample_read_error", error=str(e))
                self._consecutive_failures += 1

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
