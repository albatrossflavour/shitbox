"""SEN0460 PM2.5 collector (DFRobot air quality sensor).

Cable pinout gotcha — our Gravity 4-pin cable has SDA/SCL swapped from
the DFRobot standard colour code:
    red=VCC(5V), black=GND, cyan=SDA, blue=SCL
Document this in the module docstring so future-Tony does not rewire blind.

Ships with enabled=false by default — the 5V PM2.5 rail is not wired in v2
until the hardware build is finalised. See D-05 in phase 11 CONTEXT.md.
"""

from typing import Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Module-level imports — patched in tests via:
#   patch("shitbox.collectors.particulate.busio")
try:
    import busio

    from shitbox.collectors._vendor import dfrobot_airquality
    _HAS_SEN0460 = True
except ImportError:
    busio = None  # type: ignore[assignment]
    dfrobot_airquality = None  # type: ignore[assignment]
    _HAS_SEN0460 = False


class SEN0460Reading:
    """PM2.5 concentration reading from SEN0460."""

    def __init__(self, pm25_ug_m3: float) -> None:
        self.value: float = pm25_ug_m3
        self.pm25_ug_m3: float = pm25_ug_m3


class SEN0460Collector(BaseCollector["SEN0460Reading"]):
    """DFRobot SEN0460 PM2.5 sensor. Ships disabled by default (D-05)."""

    def __init__(
        self,
        config: object,
        callback: Optional[object] = None,
    ) -> None:
        super().__init__(
            name="sen0460",
            sample_rate_hz=getattr(config, "sample_rate_hz", 0.2),
            callback=callback,
        )
        self._enabled: bool = bool(getattr(config, "enabled", False))
        self._i2c_bus: int = int(getattr(config, "i2c_bus", 1))
        self._address: int = int(getattr(config, "address", 0x19))
        self._sensor: Optional[object] = None

    def setup(self) -> None:
        """Initialise SEN0460 over I2C.

        When disabled, I2C is never opened (D-05 requirement).
        Logs sen0460_sensor_init_failed and leaves _sensor=None on any error.
        """
        if not self._enabled:
            log.info("sen0460_disabled")
            return
        if busio is None or dfrobot_airquality is None:
            log.warning("sen0460_lib_missing")
            return
        try:
            i2c = busio.I2C(1, 2)
            self._sensor = dfrobot_airquality.DFRobot_AirQualitySensor(i2c, self._address)
            log.info("sen0460_sensor_init")
        except (OSError, Exception) as e:
            log.warning("sen0460_sensor_init_failed", error=str(e))
            self._sensor = None

    def collect(self) -> Optional["SEN0460Reading"]:
        """Read PM2.5 concentration from the SEN0460."""
        if not self._enabled or self._sensor is None:
            return None
        try:
            pm25 = self._sensor.read_particle_concentration("PM2.5")
            return SEN0460Reading(pm25_ug_m3=float(pm25))
        except (OSError, Exception) as e:
            log.warning("sen0460_read_error", error=str(e))
            return None

    def read(self) -> Optional["SEN0460Reading"]:
        """Alias for collect — satisfies BaseCollector ABC."""
        return self.collect()

    def to_reading(self, data: "SEN0460Reading") -> Reading:
        """Convert SEN0460Reading to a generic Reading for storage."""
        return Reading(
            sensor_type="pm25",  # type: ignore[arg-type]
        )
