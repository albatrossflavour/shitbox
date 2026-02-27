"""Health metrics collector for CPU, disk, sync backlog, and throttle state.

Assembles a system Reading from the current state of the thermal monitor,
batch sync service, and local disk usage.  Designed to be called once per
telemetry cycle from the UnifiedEngine.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Optional

from shitbox.health.thermal_monitor import ThermalMonitorService
from shitbox.storage.models import Reading, SensorType
from shitbox.sync.batch_sync import BatchSyncService
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class HealthCollector:
    """Assemble a system health Reading from current subsystem state.

    Gracefully degrades: if any individual metric cannot be read (e.g. sensor
    unavailable, path does not exist), that field is left as None and
    collection continues.
    """

    def __init__(
        self,
        thermal_monitor: ThermalMonitorService,
        batch_sync: Optional[BatchSyncService],
        data_dir: str,
    ) -> None:
        """Initialise the health collector.

        Args:
            thermal_monitor: Running ThermalMonitorService instance.
            batch_sync: Optional BatchSyncService; if None backlog is reported as 0.
            data_dir: Path to the data directory to measure disk usage against.
        """
        self._thermal = thermal_monitor
        self._batch_sync = batch_sync
        self._data_dir = data_dir

    def collect(self) -> Optional[Reading]:
        """Assemble a system health Reading from current subsystem state.

        Returns:
            A Reading with sensor_type=SYSTEM and health fields populated,
            or None if the data directory does not exist.
        """
        # CPU temperature from thermal monitor (already sampled in background)
        cpu_temp: Optional[float] = None
        try:
            cpu_temp = self._thermal.current_temp_celsius
        except Exception as exc:
            log.warning("health_collector_cpu_temp_error", error=str(exc))

        # Disk usage
        disk_pct: Optional[float] = None
        try:
            usage = shutil.disk_usage(self._data_dir)
            disk_pct = (usage.used / usage.total) * 100.0
        except FileNotFoundError:
            log.warning("health_collector_disk_path_missing", path=self._data_dir)
            return None
        except OSError as exc:
            log.warning("health_collector_disk_error", error=str(exc))

        # Sync backlog (count of unsynced readings in database)
        backlog: int = 0
        try:
            if self._batch_sync is not None:
                backlog = self._batch_sync.get_backlog_count()
        except Exception as exc:
            log.warning("health_collector_backlog_error", error=str(exc))

        # Throttle bitmask from thermal monitor's last vcgencmd read
        throttle: Optional[int] = None
        try:
            throttle = self._thermal.last_throttled_raw
        except Exception as exc:
            log.warning("health_collector_throttle_error", error=str(exc))

        return Reading(
            timestamp_utc=datetime.now(timezone.utc),
            sensor_type=SensorType.SYSTEM,
            cpu_temp_celsius=cpu_temp,
            disk_percent=disk_pct,
            sync_backlog=backlog,
            throttle_flags=throttle,
        )
