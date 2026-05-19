"""DS18B20 1-Wire temperature collector.

Reads DS18B20 probes by sensor ID, mapped to semantic roles
(exterior, engine_bay) per config. IDs are discovered on the Pi 5
during phase 11 wave 0 and recorded in HARDWARE_IDS.md.

Reads directly from the kernel sysfs temperature file
(/sys/bus/w1/devices/28-{id}/temperature) rather than via w1thermsensor.
The w1_slave interface (which w1thermsensor uses) returns empty on the Pi 5
kernel, causing persistent SensorNotReadyError. The temperature file returns
millidegrees cleanly with no CRC overhead.

Graceful degradation: missing or unready probes log and skip the sample
without taking the engine down (D-24).
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading
from shitbox.utils.logging import get_logger

_W1_BASE = Path("/sys/bus/w1/devices")

log = get_logger(__name__)


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
        # Maps role -> sysfs temperature Path (None if not found at setup)
        self._paths: Dict[str, Optional[Path]] = {}

    def setup(self) -> None:
        """Resolve sysfs paths for each configured sensor ID."""
        for role, sensor_id in self._roles.items():
            path = _W1_BASE / f"28-{sensor_id}" / "temperature"
            if path.exists():
                self._paths[role] = path
                log.info("ds18b20_sensor_init", role=role, sensor_id=sensor_id)
            else:
                self._paths[role] = None
                log.warning("ds18b20_sensor_not_found", role=role, sensor_id=sensor_id)

    def collect(self) -> Optional[List["DS18B20Reading"]]:
        """Read temperature from each configured probe."""
        readings: List[DS18B20Reading] = []
        for role, path in self._paths.items():
            if path is None:
                continue
            try:
                raw = path.read_text().strip()
                if not raw:
                    time.sleep(0.2)
                    raw = path.read_text().strip()
                temp_c = int(raw) / 1000.0
                readings.append(DS18B20Reading(temp_celsius=temp_c, role=role))
            except Exception as e:
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
