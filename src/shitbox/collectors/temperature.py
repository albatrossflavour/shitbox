"""Temperature data collector for MCP9808 sensor."""

from typing import Callable, Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading, TemperatureReading
from shitbox.utils.config import TemperatureConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class TemperatureCollector(BaseCollector[TemperatureReading]):
    """Collector for MCP9808 I2C temperature sensor.

    High-accuracy (+/- 0.25C) digital temperature sensor.
    Reads at low sample rates (0.1Hz default) to conserve resources.
    """

    def __init__(
        self,
        config: TemperatureConfig,
        callback: Optional[Callable[[Reading], None]] = None,
    ):
        """Initialise temperature collector.

        Args:
            config: Temperature sensor configuration.
            callback: Function to call with each reading.
        """
        super().__init__(
            name="temperature",
            sample_rate_hz=config.sample_rate_hz,
            callback=callback,
        )
        self.config = config
        self._sensor = None
        self._i2c = None

    def setup(self) -> None:
        """Initialise MCP9808 hardware."""
        try:
            import board
            import busio
            import adafruit_mcp9808

            log.info(
                "initialising_temperature_sensor",
                bus=self.config.i2c_bus,
                address=hex(self.config.address),
            )

            # Create I2C bus
            self._i2c = busio.I2C(board.SCL, board.SDA)

            # Create sensor object
            self._sensor = adafruit_mcp9808.MCP9808(
                self._i2c, address=self.config.address
            )

            log.info("temperature_sensor_initialised")

        except ImportError as e:
            log.error("temperature_import_error", error=str(e))
            raise RuntimeError(
                "MCP9808 library not installed. Run: pip install adafruit-circuitpython-mcp9808"
            ) from e
        except Exception as e:
            log.error("temperature_setup_error", error=str(e))
            raise

    def read(self) -> Optional[TemperatureReading]:
        """Read current temperature.

        Returns:
            TemperatureReading with temperature in Celsius.
        """
        if not self._sensor:
            return None

        try:
            temp_celsius = self._sensor.temperature

            reading = TemperatureReading(
                timestamp=self.now_utc(),
                temp_celsius=temp_celsius,
            )

            log.debug("temperature_reading", temp_c=f"{temp_celsius:.2f}")

            return reading

        except Exception as e:
            log.error("temperature_read_error", error=str(e))
            raise

    def to_reading(self, data: TemperatureReading) -> Reading:
        """Convert TemperatureReading to generic Reading."""
        return Reading.from_temperature(data)

    def cleanup(self) -> None:
        """Release I2C resources."""
        if self._i2c:
            self._i2c.deinit()
            self._i2c = None
            self._sensor = None
            log.info("temperature_cleanup_complete")
