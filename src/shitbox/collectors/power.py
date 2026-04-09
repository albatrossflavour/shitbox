"""INA226 power monitor collector.

Replaces the v1 power collector. Ships with enabled=false by default —
INA226 shunt wiring is deferred per D-06. See phase 11 CONTEXT.md.
"""

from typing import Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Module-level imports — patched in tests via:
#   patch("shitbox.collectors.power.smbus2")
try:
    import smbus2

    from shitbox.collectors._vendor.ina226 import INA226
    _HAS_INA226 = True
except ImportError:
    smbus2 = None  # type: ignore[assignment]
    INA226 = None  # type: ignore[assignment]
    _HAS_INA226 = False


class INA226Reading:
    """Power reading from INA226: bus voltage and current."""

    def __init__(self, voltage_v: float, current_a: float) -> None:
        self.voltage_v: float = voltage_v
        self.current_a: float = current_a
        self.value: float = voltage_v


class INA226Collector(BaseCollector["INA226Reading"]):
    """INA226 power monitor. Ships disabled by default (D-06)."""

    def __init__(
        self,
        config: object,
        callback: Optional[object] = None,
    ) -> None:
        super().__init__(
            name="ina226",
            sample_rate_hz=getattr(config, "sample_rate_hz", 1.0),
            callback=callback,
        )
        self._enabled: bool = bool(getattr(config, "enabled", False))
        self._i2c_bus: int = int(getattr(config, "i2c_bus", 1))
        self._address: int = int(getattr(config, "address", 0x40))
        self._shunt_ohms: float = float(getattr(config, "shunt_ohms", 0.1))
        self._sensor: Optional[object] = None

    def setup(self) -> None:
        """Initialise INA226 over smbus2.

        When disabled, smbus2 is never opened (D-06 requirement).
        Logs ina226_sensor_init_failed and leaves _sensor=None on any error.
        """
        if not self._enabled:
            log.info("ina226_disabled")
            return
        if smbus2 is None or INA226 is None:
            log.warning("ina226_lib_missing")
            return
        try:
            bus = smbus2.SMBus(self._i2c_bus)
            self._sensor = INA226(bus, address=self._address, shunt_ohms=self._shunt_ohms)
            log.info("ina226_sensor_init")
        except (OSError, Exception) as e:
            log.warning("ina226_sensor_init_failed", error=str(e))
            self._sensor = None

    def collect(self) -> Optional["INA226Reading"]:
        """Read bus voltage and current from the INA226."""
        if not self._enabled or self._sensor is None:
            return None
        try:
            voltage_v, current_a = self._sensor.read()
            return INA226Reading(voltage_v=voltage_v, current_a=current_a)
        except (OSError, Exception) as e:
            log.warning("ina226_read_error", error=str(e))
            return None

    def read(self) -> Optional["INA226Reading"]:
        """Alias for collect — satisfies BaseCollector ABC."""
        return self.collect()

    def to_reading(self, data: "INA226Reading") -> Reading:
        """Convert INA226Reading to a generic Reading for storage."""
        return Reading(
            sensor_type="power",  # type: ignore[arg-type]
            bus_voltage_v=data.voltage_v,
            current_ma=data.current_a * 1000.0,
        )
