"""Artificial horizon and tilt-compensated heading via complementary filter.

Fuses LSM6DSOX accel+gyro (from events.sampler.HighRateSampler) with
LIS3MDL magnetometer (read here at 10 Hz) into pitch, roll, and
tilt-compensated heading. Stored in SQLite for later consumers (driver
display, dashboard). Heading is available at standstill -- see D-12.
"""

import math
from typing import Callable, Optional

try:
    import adafruit_lis3mdl
    import board
    import busio

    _HAS_LIS3MDL = True
except ImportError:
    adafruit_lis3mdl = None  # type: ignore[assignment]
    _HAS_LIS3MDL = False

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading, SensorType
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

COMPLEMENTARY_ALPHA = 0.98  # trust gyro short-term, accel long-term


class ComplementaryFilter:
    """Simple complementary filter for pitch and roll estimation.

    Fuses gyro integration (short-term accurate, drifts over time) with
    accelerometer-derived tilt angles (long-term accurate, noisy short-term).
    """

    def __init__(self, alpha: float = COMPLEMENTARY_ALPHA) -> None:
        self.alpha = alpha
        self.pitch: float = 0.0
        self.roll: float = 0.0
        self._last_ts: Optional[float] = None

    def update(
        self,
        ax: float,
        ay: float,
        az: float,
        gx: float,
        gy: float,
        gz: float,
        ts: float,
    ) -> None:
        """Update pitch and roll estimates.

        Args:
            ax, ay, az: Acceleration in g.
            gx, gy, gz: Angular velocity in deg/s.
            ts: Current timestamp (epoch seconds).
        """
        dt = (ts - self._last_ts) if self._last_ts is not None else 0.01
        self._last_ts = ts

        accel_pitch = math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az)))
        accel_roll = math.degrees(math.atan2(-ax, az))

        self.pitch = (
            self.alpha * (self.pitch + gx * dt)
            + (1 - self.alpha) * accel_pitch
        )
        self.roll = (
            self.alpha * (self.roll + gy * dt)
            + (1 - self.alpha) * accel_roll
        )


def tilt_compensated_heading(
    mx: float,
    my: float,
    mz: float,
    pitch_deg: float,
    roll_deg: float,
) -> float:
    """Compute tilt-compensated magnetic heading.

    Compensates for sensor tilt using pitch and roll angles so heading is
    accurate even when the sensor is not level.

    Args:
        mx, my, mz: Magnetometer readings in microteslas.
        pitch_deg: Current pitch angle in degrees.
        roll_deg: Current roll angle in degrees.

    Returns:
        Heading in degrees [0, 360).
    """
    p = math.radians(pitch_deg)
    r = math.radians(roll_deg)

    xh = mx * math.cos(p) + mz * math.sin(p)
    yh = (
        mx * math.sin(r) * math.sin(p)
        + my * math.cos(r)
        - mz * math.sin(r) * math.cos(p)
    )

    heading = math.degrees(math.atan2(yh, xh))
    return (heading + 360.0) % 360.0


class IMUHeadingCollector(BaseCollector):
    """Collector that fuses LSM6DSOX and LIS3MDL into pitch, roll, and heading.

    Reads LIS3MDL magnetometer at sample_rate_hz (default 10 Hz) and combines
    it with the latest IMU sample from the high-rate sampler via complementary
    filter to produce a tilt-compensated heading.

    D-12: heading must be available at standstill. Filter runs unconditionally,
    independent of GPS speed. This is the whole point of adding the magnetometer.
    """

    def __init__(
        self,
        config: object,
        latest_sample_fn: Optional[Callable] = None,
        callback: Optional[Callable[[Reading], None]] = None,
    ) -> None:
        """Initialise IMU heading collector.

        Args:
            config: Config object with alpha and sample_rate_hz attributes.
            latest_sample_fn: Callable returning the most recent IMUSample (or None).
            callback: Called with each Reading produced.
        """
        alpha = getattr(config, "alpha", COMPLEMENTARY_ALPHA)
        sample_rate_hz = getattr(config, "sample_rate_hz", 10.0)

        super().__init__(
            name="imu_heading",
            sample_rate_hz=sample_rate_hz,
            callback=callback,
        )

        self.config = config
        self._latest_sample_fn = latest_sample_fn
        self._filter = ComplementaryFilter(alpha=alpha)
        self._lis3mdl: Optional[object] = None
        self._i2c: Optional[object] = None

    def setup(self) -> None:
        """Initialise LIS3MDL hardware.

        On failure (hardware absent, I2C error, ImportError), logs
        sensor_init_failed and sets _lis3mdl = None. Does NOT raise --
        graceful degradation mirrors the LSM6DSOX sampler pattern.
        """
        try:
            if adafruit_lis3mdl is None:
                raise ImportError("adafruit-circuitpython-lis3mdl not installed")
            self._i2c = busio.I2C(board.SCL, board.SDA)  # type: ignore[name-defined]
            self._lis3mdl = adafruit_lis3mdl.LIS3MDL(self._i2c)
            log.info("lis3mdl_initialised")
        except (OSError, ValueError, ImportError, RuntimeError, Exception) as e:
            log.error("sensor_init_failed", sensor="LIS3MDL", error=str(e))
            self._lis3mdl = None

    def read(self) -> Optional[Reading]:
        """Read mag + IMU, compute heading, return a Reading or None."""
        if self._lis3mdl is None:
            return None

        try:
            mx, my, mz = self._lis3mdl.magnetic  # type: ignore[union-attr]

            # Grab latest IMU sample if available for filter update
            if self._latest_sample_fn is not None:
                sample = self._latest_sample_fn()
                if sample is not None:
                    self._filter.update(
                        ax=sample.ax,
                        ay=sample.ay,
                        az=sample.az,
                        gx=sample.gx,
                        gy=sample.gy,
                        gz=sample.gz,
                        ts=sample.timestamp,
                    )

            pitch = self._filter.pitch
            roll = self._filter.roll
            heading = tilt_compensated_heading(mx, my, mz, pitch, roll)

            return Reading(
                sensor_type=SensorType.IMU_HEADING,
                heading_deg=heading,
                accel_x=pitch,  # pitch stored here under imu_heading sensor type
                accel_y=roll,   # roll stored here under imu_heading sensor type
            )

        except (OSError, ValueError) as e:
            log.error("sensor_read_error", sensor="LIS3MDL", error=str(e))
            return None

    def to_reading(self, data: Reading) -> Reading:
        """Pass through (read() already returns a Reading)."""
        return data

    def cleanup(self) -> None:
        """Release I2C resources."""
        if self._i2c is not None:
            try:
                self._i2c.deinit()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._i2c = None
        self._lis3mdl = None

    # ------------------------------------------------------------------
    # Public calculation methods (used directly in tests and by callers
    # that need stateless computation without running the full collector)
    # ------------------------------------------------------------------

    def update_pitch(
        self,
        current_pitch: float,
        gyro_x_dps: float,
        accel_pitch_deg: float,
        dt: float,
    ) -> float:
        """Apply one complementary filter step and return updated pitch.

        Args:
            current_pitch: Current pitch estimate in degrees.
            gyro_x_dps: Gyro x reading in deg/s.
            accel_pitch_deg: Accel-derived pitch in degrees.
            dt: Time step in seconds.

        Returns:
            Updated pitch in degrees.
        """
        alpha = self._filter.alpha
        return alpha * (current_pitch + gyro_x_dps * dt) + (1 - alpha) * accel_pitch_deg

    def compute_heading(
        self,
        mag_x: float,
        mag_y: float,
        mag_z: float,
        pitch_deg: float,
        roll_deg: float,
    ) -> float:
        """Compute tilt-compensated heading from magnetometer and tilt angles.

        Args:
            mag_x, mag_y, mag_z: Magnetometer readings in microteslas.
            pitch_deg: Pitch angle in degrees.
            roll_deg: Roll angle in degrees.

        Returns:
            Heading in degrees [0, 360).
        """
        return tilt_compensated_heading(mag_x, mag_y, mag_z, pitch_deg, roll_deg)

    def get_heading(
        self,
        mag_x: float,
        mag_y: float,
        mag_z: float,
        pitch_deg: float,
        roll_deg: float,
        gps_speed_ms: float = 0.0,
    ) -> float:
        """Return tilt-compensated heading regardless of GPS speed.

        D-12: heading must be available at standstill. Filter runs
        unconditionally, independent of GPS speed. This is the whole point
        of adding the magnetometer.

        Args:
            mag_x, mag_y, mag_z: Magnetometer readings in microteslas.
            pitch_deg: Pitch angle in degrees.
            roll_deg: Roll angle in degrees.
            gps_speed_ms: Current GPS speed in m/s (ignored -- D-12).

        Returns:
            Heading in degrees [0, 360).
        """
        # gps_speed_ms is intentionally unused -- heading is computed regardless
        return tilt_compensated_heading(mag_x, mag_y, mag_z, pitch_deg, roll_deg)
