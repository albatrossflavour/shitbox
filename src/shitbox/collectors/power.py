"""Power data collector for INA219 sensor."""

from typing import Callable, Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import PowerReading, Reading
from shitbox.utils.config import PowerConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class PowerCollector(BaseCollector[PowerReading]):
    """Collector for INA219 I2C power sensor.

    Reads battery voltage (V), current (mA), and power (mW).
    """

    def __init__(
        self,
        config: PowerConfig,
        callback: Optional[Callable[[Reading], None]] = None,
    ):
        super().__init__(
            name="power",
            sample_rate_hz=config.sample_rate_hz,
            callback=callback,
        )
        self.config = config
        self._sensor = None
        self._i2c = None

    def setup(self) -> None:
        """Initialise INA219 hardware."""
        try:
            import board
            import busio
            from adafruit_ina219 import INA219

            log.info(
                "initialising_power_sensor",
                bus=self.config.i2c_bus,
                address=hex(self.config.address),
            )

            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = INA219(self._i2c, addr=self.config.address)

            log.info("power_sensor_initialised")

        except ImportError as e:
            log.error("power_import_error", error=str(e))
            raise RuntimeError(
                "INA219 library not installed. "
                "Run: pip install adafruit-circuitpython-ina219"
            ) from e
        except Exception as e:
            log.error("power_setup_error", error=str(e))
            raise

    def read(self) -> Optional[PowerReading]:
        """Read current power metrics."""
        if not self._sensor:
            return None

        try:
            bus_voltage = self._sensor.bus_voltage
            current = self._sensor.current
            power = self._sensor.power

            reading = PowerReading(
                timestamp=self.now_utc(),
                bus_voltage_v=bus_voltage,
                current_ma=current,
                power_mw=power,
            )

            log.debug(
                "power_reading",
                voltage_v=f"{bus_voltage:.2f}",
                current_ma=f"{current:.1f}",
                power_mw=f"{power:.1f}",
            )

            return reading

        except Exception as e:
            log.error("power_read_error", error=str(e))
            raise

    def to_reading(self, data: PowerReading) -> Reading:
        """Convert PowerReading to generic Reading."""
        return Reading.from_power(data)

    def cleanup(self) -> None:
        """Release I2C resources."""
        if self._i2c:
            self._i2c.deinit()
            self._i2c = None
            self._sensor = None
            log.info("power_cleanup_complete")
