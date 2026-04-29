"""VEML7700 ambient light collector (lux).

No consumers wired in this phase — stored raw for later night-mode /
dashboard integration. Graceful degradation per D-24.
"""

from typing import Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Module-level imports — patched in tests via:
#   patch("shitbox.collectors.light.adafruit_veml7700")
#   patch("shitbox.collectors.light.busio")
try:
    import adafruit_veml7700
    import board
    import busio
    _HAS_VEML = True
except ImportError:
    board = None  # type: ignore[assignment]
    adafruit_veml7700 = None  # type: ignore[assignment]
    busio = None  # type: ignore[assignment]
    _HAS_VEML = False


class VEML7700Reading:
    """Ambient light reading from VEML7700."""

    def __init__(self, lux: float) -> None:
        self.value: float = lux
        self.lux: float = lux


class VEML7700Collector(BaseCollector["VEML7700Reading"]):
    """VEML7700 ambient light sensor, 1 Hz."""

    def __init__(
        self,
        config: object,
        callback: Optional[object] = None,
        role: Optional[str] = None,
    ) -> None:
        super().__init__(
            name="veml7700",
            sample_rate_hz=getattr(config, "sample_rate_hz", 1.0),
            callback=callback,
            role=role,
        )
        self._sensor: Optional[object] = None

    def setup(self) -> None:
        """Initialise VEML7700 over I2C.

        Logs veml7700_sensor_init_failed and leaves _sensor=None if the device
        is absent or the library unavailable (D-24 graceful degradation).
        """
        if adafruit_veml7700 is None or busio is None:
            log.warning("veml7700_lib_missing")
            return
        try:
            # busio.I2C is patched in tests; on the Pi, board.SCL/board.SDA
            # are the standard args but we call through busio to keep the
            # patch surface simple.
            i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = adafruit_veml7700.VEML7700(i2c)
            log.info("veml7700_sensor_init")
        except (OSError, ValueError, Exception) as e:
            log.warning("veml7700_sensor_init_failed", error=str(e))
            self._sensor = None

    def collect(self) -> Optional["VEML7700Reading"]:
        """Read ambient lux from the VEML7700."""
        if self._sensor is None:
            return None
        try:
            lux = self._sensor.lux
            return VEML7700Reading(lux=float(lux))
        except Exception as e:
            log.warning("veml7700_read_error", error=str(e))
            return None

    def read(self) -> Optional["VEML7700Reading"]:
        """Alias for collect — satisfies BaseCollector ABC."""
        return self.collect()

    def to_reading(self, data: "VEML7700Reading") -> Reading:
        """Convert VEML7700Reading to a generic Reading for storage."""
        return Reading.from_light(lux=data.lux, timestamp=self.now_utc())
