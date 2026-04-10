"""DS18B20 1-Wire temperature collector.

Reads two DS18B20 probes by sensor ID, mapped to semantic roles
(exterior, engine_bay) per config. IDs are discovered on the Pi 5
during phase 11 wave 0 and recorded in HARDWARE_IDS.md.

Graceful degradation: missing or unready probes log and skip the sample
without taking the engine down (D-24).
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading
from shitbox.utils.logging import get_logger

_SENSOR_NOT_READY_RETRY_SECONDS = 0.15  # DS18B20 needs up to 750ms to convert; retry after 150ms

log = get_logger(__name__)

# Module-level names — patched in tests via:
#   patch("shitbox.collectors.temperature.W1ThermSensor")
#   patch("shitbox.collectors.temperature.NoSensorFoundError", ...)
try:
    from w1thermsensor import NoSensorFoundError, SensorNotReadyError, W1ThermSensor
    _HAS_W1 = True
except ImportError:
    W1ThermSensor = None  # type: ignore[assignment, misc]
    NoSensorFoundError = Exception  # type: ignore[assignment, misc]
    SensorNotReadyError = Exception  # type: ignore[assignment, misc]
    _HAS_W1 = False


@dataclass
class DS18B20Reading:
    """Temperature reading from a single DS18B20 probe."""

    temp_celsius: float
    role: str  # "exterior" or "engine_bay"

    @property
    def value(self) -> float:
        """Value accessor for generic collector plumbing."""
        return self.temp_celsius


class DS18B20Collector(BaseCollector["DS18B20Reading"]):
    """Dual DS18B20 probes: exterior + engine_bay roles."""

    def __init__(
        self,
        config: object,
        callback: Optional[object] = None,
    ) -> None:
        super().__init__(
            name="ds18b20",
            sample_rate_hz=getattr(config, "sample_rate_hz", 1.0),
            callback=callback,
        )
        self._roles: Dict[str, str] = dict(getattr(config, "sensor_ids", {}))
        self._sensors: Dict[str, object] = {}
        self._disabled: bool = False

    def setup(self) -> None:
        """Initialise DS18B20 sensors by sensor ID.

        Sets self._disabled=True if the w1thermsensor library is unavailable
        (covers both real import failure and test-time sys.modules patching).
        """
        if W1ThermSensor is None:
            log.warning("ds18b20_lib_missing")
            self._disabled = True
            return

        for role, sensor_id in self._roles.items():
            try:
                self._sensors[role] = W1ThermSensor(sensor_id=sensor_id)
                log.info("ds18b20_sensor_init", role=role, sensor_id=sensor_id)
            except NoSensorFoundError:
                log.warning("ds18b20_sensor_not_found", role=role, sensor_id=sensor_id)
                self._sensors[role] = None

    def collect(self) -> Optional[List["DS18B20Reading"]]:
        """Read temperature from each configured probe."""
        if self._disabled:
            return None

        readings: List[DS18B20Reading] = []
        for role, sensor in self._sensors.items():
            if sensor is None:
                continue
            try:
                temp_c = sensor.get_temperature()
                readings.append(DS18B20Reading(temp_celsius=temp_c, role=role))
            except SensorNotReadyError:
                time.sleep(_SENSOR_NOT_READY_RETRY_SECONDS)
                try:
                    temp_c = sensor.get_temperature()
                    readings.append(DS18B20Reading(temp_celsius=temp_c, role=role))
                except SensorNotReadyError as e:
                    log.warning("ds18b20_read_error", role=role, error=str(e))
            except (OSError, Exception) as e:
                log.warning("ds18b20_read_error", role=role, error=str(e))
        return readings if readings else None

    def read(self) -> Optional["DS18B20Reading"]:
        """Read probes and dispatch each via callback directly.

        BaseCollector expects a single item from read(). DS18B20 has multiple
        probes, so we fire the callback for each probe here and return None
        so the base loop does not attempt to call to_reading on the list.
        """
        readings = self.collect()
        if readings and self.callback:
            for item in readings:
                self.callback(self.to_reading(item))
        return None

    def to_reading(self, data: "DS18B20Reading") -> Reading:
        """Convert a DS18B20Reading to a generic Reading for storage."""
        from shitbox.storage.models import SensorType
        return Reading(
            sensor_type=SensorType.TEMPERATURE,
            temp_celsius=data.temp_celsius,
            sensor_id=data.role,
        )
