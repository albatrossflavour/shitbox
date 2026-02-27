"""High-rate MPU6050 sampler for event detection."""

import struct
import subprocess
import threading
import time
from typing import Callable, Optional

from shitbox.capture import buzzer, speaker
from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# MPU6050 registers
MPU6050_ADDR = 0x68
PWR_MGMT_1 = 0x6B
SMPLRT_DIV = 0x19
CONFIG = 0x1A
GYRO_CONFIG = 0x1B
ACCEL_CONFIG = 0x1C
FIFO_EN = 0x23
INT_ENABLE = 0x38
FIFO_COUNT_H = 0x72
FIFO_R_W = 0x74
USER_CTRL = 0x6A
ACCEL_XOUT_H = 0x3B

# Scale factors
ACCEL_SCALE_4G = 8192.0  # LSB/g for ±4g range
GYRO_SCALE_500 = 65.5    # LSB/(deg/s) for ±500 deg/s range

# I2C bus lockup recovery constants
I2C_CONSECUTIVE_FAILURE_THRESHOLD = 5  # Triggers recovery after 5 failures (~50ms at 100 Hz)
I2C_RECOVERY_DELAY_SECONDS = 0.1       # 100ms delay after GPIO cleanup before smbus2 reopen
SCL_PIN = 3                            # GPIO3 = physical pin 5
SDA_PIN = 2                            # GPIO2 = physical pin 3


class HighRateSampler:
    """High-rate IMU sampler using MPU6050.

    Samples at ~100 Hz and feeds data into a ring buffer.
    Designed to run in its own thread with minimal latency.
    """

    def __init__(
        self,
        ring_buffer: RingBuffer,
        i2c_bus: int = 1,
        address: int = MPU6050_ADDR,
        sample_rate_hz: float = 100.0,
        accel_range: int = 4,
        gyro_range: int = 500,
        on_sample: Optional[Callable[[IMUSample], None]] = None,
    ):
        """Initialise high-rate sampler.

        Args:
            ring_buffer: Buffer to store samples.
            i2c_bus: I2C bus number.
            address: MPU6050 I2C address.
            sample_rate_hz: Target sample rate.
            accel_range: Accelerometer range (2, 4, 8, 16 g).
            gyro_range: Gyroscope range (250, 500, 1000, 2000 deg/s).
            on_sample: Optional callback for each sample.
        """
        self.ring_buffer = ring_buffer
        self.i2c_bus = i2c_bus
        self.address = address
        self.sample_rate_hz = sample_rate_hz
        self.sample_interval = 1.0 / sample_rate_hz
        self.on_sample = on_sample

        # Scale factors based on range
        self.accel_scale = {2: 16384.0, 4: 8192.0, 8: 4096.0, 16: 2048.0}[accel_range]
        self.gyro_scale = {250: 131.0, 500: 65.5, 1000: 32.8, 2000: 16.4}[gyro_range]
        self.accel_range = accel_range
        self.gyro_range = gyro_range

        self._bus = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stats
        self.samples_total = 0
        self.samples_dropped = 0
        self._last_sample_time = 0.0

        # I2C lockup recovery
        self._consecutive_failures: int = 0

    def setup(self) -> None:
        """Initialise MPU6050 for high-rate sampling."""
        try:
            import smbus2
            self._bus = smbus2.SMBus(self.i2c_bus)
        except ImportError:
            raise RuntimeError("smbus2 not installed. Run: pip install smbus2")

        # Wake up MPU6050
        self._bus.write_byte_data(self.address, PWR_MGMT_1, 0x00)
        time.sleep(0.1)

        # Set sample rate divider for ~100 Hz
        # Sample Rate = Gyro Output Rate / (1 + SMPLRT_DIV)
        # Gyro output rate is 1kHz when DLPF is enabled
        # For 100 Hz: SMPLRT_DIV = 9 (1000 / (1 + 9) = 100)
        divider = int(1000 / self.sample_rate_hz) - 1
        self._bus.write_byte_data(self.address, SMPLRT_DIV, divider)

        # Set DLPF (Digital Low Pass Filter) - ~44 Hz bandwidth
        self._bus.write_byte_data(self.address, CONFIG, 0x03)

        # Set accelerometer range
        accel_config = {2: 0x00, 4: 0x08, 8: 0x10, 16: 0x18}[self.accel_range]
        self._bus.write_byte_data(self.address, ACCEL_CONFIG, accel_config)

        # Set gyroscope range
        gyro_config = {250: 0x00, 500: 0x08, 1000: 0x10, 2000: 0x18}[self.gyro_range]
        self._bus.write_byte_data(self.address, GYRO_CONFIG, gyro_config)

        log.info(
            "mpu6050_initialised",
            sample_rate_hz=self.sample_rate_hz,
            accel_range=self.accel_range,
            gyro_range=self.gyro_range,
        )

    def start(self) -> None:
        """Start sampling in background thread."""
        if self._running:
            return

        if self._bus is None:
            self.setup()

        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        log.info("high_rate_sampler_started", rate_hz=self.sample_rate_hz)

    def stop(self) -> None:
        """Stop sampling."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        log.info(
            "high_rate_sampler_stopped",
            samples_total=self.samples_total,
            samples_dropped=self.samples_dropped,
        )

    def _sample_loop(self) -> None:
        """Main sampling loop - runs at target rate."""
        next_sample_time = time.perf_counter()

        while self._running:
            now = time.perf_counter()

            # Check if we're behind schedule
            if now > next_sample_time + self.sample_interval:
                # We're more than one sample behind - log and catch up
                self.samples_dropped += 1
                next_sample_time = now

            # Wait until next sample time
            sleep_time = next_sample_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Read sample
            try:
                sample = self._read_sample()
                self.ring_buffer.append(sample)
                self.samples_total += 1
                self._consecutive_failures = 0

                if self.on_sample:
                    self.on_sample(sample)

            except Exception as e:
                log.error("sample_read_error", error=str(e))
                self._consecutive_failures += 1

                if self._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
                    log.warning(
                        "i2c_bus_lockup_detected",
                        consecutive_failures=self._consecutive_failures,
                    )
                    buzzer.beep_i2c_lockup()
                    speaker.speak_i2c_lockup()
                    recovered = self._i2c_bus_reset()
                    if recovered:
                        log.info("i2c_bus_recovery_successful")
                        buzzer.beep_service_recovered("i2c")
                        speaker.speak_service_recovered()
                        self._consecutive_failures = 0
                    else:
                        self._force_reboot()

            next_sample_time += self.sample_interval

    def _i2c_bus_reset(self) -> bool:
        """Attempt 9-clock bit-bang recovery to release a stuck I2C slave.

        Pulses SCL 9 times to allow a slave device holding SDA low to
        complete its transaction and release the bus. Then generates a STOP
        condition, performs selective GPIO cleanup, waits for the I2C driver
        to reclaim the pins, reopens smbus2, and reinitialises the MPU6050.

        Returns:
            True if the bus was successfully recovered and the sensor
            reinitialised; False on any failure.
        """
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]
        except ImportError:
            log.error("rpi_gpio_not_available", hint="Cannot perform I2C bit-bang recovery")
            return False

        # Close the existing bus connection
        try:
            if self._bus is not None:
                self._bus.close()
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

        try:
            import smbus2  # type: ignore[import]
            self._bus = smbus2.SMBus(self.i2c_bus)
            self.setup()
            return True
        except Exception as e:
            log.error("i2c_bus_reopen_failed", error=str(e))
            return False

    def _force_reboot(self) -> None:
        """Force a system reboot after unrecoverable I2C failure."""
        log.critical("i2c_recovery_failed_forcing_reboot")
        subprocess.run(["sudo", "systemctl", "reboot"], check=False)

    def _read_sample(self) -> IMUSample:
        """Read accelerometer and gyroscope data from MPU6050."""
        # Read 14 bytes starting from ACCEL_XOUT_H
        # Format: AccelX, AccelY, AccelZ, Temp, GyroX, GyroY, GyroZ (2 bytes each)
        data = self._bus.read_i2c_block_data(self.address, ACCEL_XOUT_H, 14)

        # Parse raw values (big-endian signed 16-bit)
        raw_ax = struct.unpack(">h", bytes(data[0:2]))[0]
        raw_ay = struct.unpack(">h", bytes(data[2:4]))[0]
        raw_az = struct.unpack(">h", bytes(data[4:6]))[0]
        # Skip temperature (bytes 6-7)
        raw_gx = struct.unpack(">h", bytes(data[8:10]))[0]
        raw_gy = struct.unpack(">h", bytes(data[10:12]))[0]
        raw_gz = struct.unpack(">h", bytes(data[12:14]))[0]

        # Convert to physical units
        ax = raw_ax / self.accel_scale
        ay = raw_ay / self.accel_scale
        az = raw_az / self.accel_scale
        gx = raw_gx / self.gyro_scale
        gy = raw_gy / self.gyro_scale
        gz = raw_gz / self.gyro_scale

        return IMUSample(
            timestamp=time.time(),
            ax=ax,
            ay=ay,
            az=az,
            gx=gx,
            gy=gy,
            gz=gz,
        )

    def read_once(self) -> IMUSample:
        """Read a single sample (for testing/calibration)."""
        if self._bus is None:
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
