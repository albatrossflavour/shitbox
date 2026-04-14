"""Environment data collector for BME680 sensor."""

import time
from typing import Callable, Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import EnvironmentReading, Reading
from shitbox.utils.config import EnvironmentConfig
from shitbox.utils.logging import get_logger

_BME680_INIT_RETRIES = 5
_BME680_INIT_RETRY_DELAY_S = 1.0

log = get_logger(__name__)


class EnvironmentCollector(BaseCollector[EnvironmentReading]):
    """Collector for BME680 I2C environment sensor.

    Reads barometric pressure (hPa), relative humidity (%), temperature (C),
    and gas resistance (ohms) for VOC/air quality measurement.
    """

    def __init__(
        self,
        config: EnvironmentConfig,
        callback: Optional[Callable[[Reading], None]] = None,
    ):
        super().__init__(
            name="environment",
            sample_rate_hz=config.sample_rate_hz,
            callback=callback,
        )
        self.config = config
        self._sensor = None
        self._i2c = None

    def setup(self) -> None:
        """Initialise BME680 hardware.

        Retries up to _BME680_INIT_RETRIES times to handle the sensor not being
        ready milliseconds after daemon start (I2C bus busy, sensor power-on delay).
        """
        try:
            import board
            import busio
            from adafruit_bme680 import Adafruit_BME680_I2C
        except ImportError as e:
            log.error("environment_import_error", error=str(e))
            raise RuntimeError(
                "BME680 library not installed. "
                "Run: pip install adafruit-circuitpython-bme680"
            ) from e

        log.info(
            "initialising_environment_sensor",
            bus=self.config.i2c_bus,
            address=hex(self.config.address),
        )

        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(1, _BME680_INIT_RETRIES + 1):
            try:
                self._i2c = busio.I2C(board.SCL, board.SDA)
                self._sensor = Adafruit_BME680_I2C(self._i2c, address=self.config.address)
                log.info("environment_sensor_initialised", attempt=attempt)
                return
            except Exception as e:
                last_exc = e
                log.warning(
                    "environment_sensor_init_retry",
                    attempt=attempt,
                    max_attempts=_BME680_INIT_RETRIES,
                    error=str(e),
                )
                if attempt < _BME680_INIT_RETRIES:
                    time.sleep(_BME680_INIT_RETRY_DELAY_S)

        log.error("environment_setup_error", error=str(last_exc))
        raise last_exc

    def read(self) -> Optional[EnvironmentReading]:
        """Read current environment metrics."""
        if not self._sensor:
            return None

        try:
            pressure = self._sensor.pressure
            humidity = self._sensor.relative_humidity
            temperature = self._sensor.temperature
            gas = self._sensor.gas

            reading = EnvironmentReading(
                timestamp=self.now_utc(),
                pressure_hpa=pressure,
                humidity_pct=humidity,
                env_temp_celsius=temperature,
                gas_resistance_ohms=gas,
            )

            log.debug(
                "environment_reading",
                pressure_hpa=f"{pressure:.1f}",
                humidity_pct=f"{humidity:.1f}",
                temp_c=f"{temperature:.1f}",
                gas_ohms=gas,
            )

            return reading

        except Exception as e:
            log.error("environment_read_error", error=str(e))
            raise

    def to_reading(self, data: EnvironmentReading) -> Reading:
        """Convert EnvironmentReading to generic Reading."""
        return Reading.from_environment(data)

    def cleanup(self) -> None:
        """Release I2C resources."""
        if self._i2c:
            self._i2c.deinit()
            self._i2c = None
            self._sensor = None
            log.info("environment_cleanup_complete")
