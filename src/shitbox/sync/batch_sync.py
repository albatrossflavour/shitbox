"""Batch sync service for historical data to Prometheus."""

import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from shitbox.storage.database import Database
from shitbox.storage.models import Reading
from shitbox.sync.connection import ConnectionMonitor
from shitbox.sync.prometheus_write import encode_remote_write
from shitbox.utils.config import PrometheusConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class DuplicateDataError(Exception):
    """Raised when Prometheus rejects data as duplicate."""
    pass


class TooOldSampleError(Exception):
    """Raised when Prometheus rejects data as too old."""
    pass


class BatchSyncService:
    """Sync historical data to Prometheus in batches.

    Uses cursor-based tracking to ensure no data is lost or duplicated.
    Only syncs when network is available.
    """

    def __init__(
        self,
        config: PrometheusConfig,
        database: Database,
        connection_monitor: ConnectionMonitor,
    ):
        """Initialise batch sync service.

        Args:
            config: Prometheus configuration.
            database: Database instance for reading data.
            connection_monitor: Connection monitor for checking connectivity.
        """
        self.config = config
        self.db = database
        self.connection = connection_monitor

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cursor_name = "prometheus"

    def start(self) -> None:
        """Start batch sync service."""
        if self._running:
            return

        log.info(
            "starting_batch_sync",
            endpoint=self.config.remote_write_url,
            batch_size=self.config.batch_size,
        )

        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop batch sync service."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _sync_loop(self) -> None:
        """Main sync loop."""
        while self._running:
            # Wait for interval
            time.sleep(self.config.batch_interval_seconds)

            if not self._running:
                break

            # Only sync if connected
            if not self.connection.is_connected:
                log.debug("batch_sync_skipped_no_connection")
                continue

            try:
                self._sync_batch()
            except Exception as e:
                log.error("batch_sync_error", error=str(e))

    def _sync_batch(self) -> None:
        """Sync a single batch of readings."""
        # Get unsynced readings
        readings = self.db.get_unsynced_readings(
            cursor_name=self._cursor_name,
            batch_size=self.config.batch_size,
        )

        if not readings:
            log.debug("batch_sync_no_data")
            return

        log.info("batch_sync_starting", count=len(readings))
        last_id = readings[-1].id

        # Convert to Prometheus format and send
        try:
            self._send_to_prometheus(readings)

            # Update cursor on success
            self.db.update_sync_cursor(self._cursor_name, last_id)
            log.info("batch_sync_complete", count=len(readings), last_id=last_id)

        except DuplicateDataError:
            # Data already exists in Prometheus - skip this batch and continue
            log.warning(
                "batch_sync_duplicate_skipped",
                count=len(readings),
                last_id=last_id,
                hint="Data already synced via another path",
            )
            self.db.update_sync_cursor(self._cursor_name, last_id)

        except TooOldSampleError:
            # Data is too old for Prometheus to accept - skip and advance
            log.warning(
                "batch_sync_too_old_skipped",
                count=len(readings),
                last_id=last_id,
                oldest_reading=readings[0].timestamp_utc.isoformat(),
            )
            self.db.update_sync_cursor(self._cursor_name, last_id)

        except Exception as e:
            log.error("batch_sync_send_failed", error=str(e))
            raise

    def _readings_to_metrics(
        self, readings: List[Reading]
    ) -> List[Tuple[str, dict, float, int]]:
        """Convert readings to Prometheus metrics format.

        Returns list of (metric_name, labels, value, timestamp_ms).
        """
        metrics = []
        labels = {"car": "shitbox", "job": "shitbox-mqtt-exporter"}

        for reading in readings:
            timestamp_ms = int(reading.timestamp_utc.timestamp() * 1000)

            # Debug: log first reading's timestamp
            if len(metrics) == 0:
                log.info(
                    "batch_sync_debug",
                    reading_time=reading.timestamp_utc.isoformat(),
                    timestamp_ms=timestamp_ms,
                    now_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                )

            if reading.sensor_type.value == "gps":
                if reading.latitude is not None:
                    metrics.append(
                        ("shitbox_lat", labels, reading.latitude, timestamp_ms)
                    )
                if reading.longitude is not None:
                    metrics.append(
                        ("shitbox_lon", labels, reading.longitude, timestamp_ms)
                    )
                if reading.speed_kmh is not None:
                    metrics.append(
                        ("shitbox_spd", labels, reading.speed_kmh, timestamp_ms)
                    )
                if reading.altitude_m is not None:
                    metrics.append(
                        ("shitbox_alt", labels, reading.altitude_m, timestamp_ms)
                    )
                if reading.satellites is not None:
                    metrics.append(
                        ("shitbox_sat", labels, float(reading.satellites), timestamp_ms)
                    )
                if reading.fix_quality is not None:
                    metrics.append(
                        ("shitbox_fix", labels, float(reading.fix_quality), timestamp_ms)
                    )

            elif reading.sensor_type.value == "imu":
                if reading.accel_x is not None:
                    metrics.append(
                        ("shitbox_ax", labels, reading.accel_x, timestamp_ms)
                    )
                if reading.accel_y is not None:
                    metrics.append(
                        ("shitbox_ay", labels, reading.accel_y, timestamp_ms)
                    )
                if reading.accel_z is not None:
                    metrics.append(
                        ("shitbox_az", labels, reading.accel_z, timestamp_ms)
                    )
                if reading.gyro_x is not None:
                    metrics.append(
                        ("shitbox_gx", labels, reading.gyro_x, timestamp_ms)
                    )
                if reading.gyro_y is not None:
                    metrics.append(
                        ("shitbox_gy", labels, reading.gyro_y, timestamp_ms)
                    )
                if reading.gyro_z is not None:
                    metrics.append(
                        ("shitbox_gz", labels, reading.gyro_z, timestamp_ms)
                    )

            elif reading.sensor_type.value == "temp":
                if reading.temp_celsius is not None:
                    metrics.append(
                        ("shitbox_temp", labels, reading.temp_celsius, timestamp_ms)
                    )

            elif reading.sensor_type.value == "power":
                if reading.bus_voltage_v is not None:
                    metrics.append(
                        ("shitbox_bus_voltage", labels, reading.bus_voltage_v, timestamp_ms)
                    )
                if reading.current_ma is not None:
                    metrics.append(
                        ("shitbox_current", labels, reading.current_ma, timestamp_ms)
                    )
                if reading.power_mw is not None:
                    metrics.append(
                        ("shitbox_power", labels, reading.power_mw, timestamp_ms)
                    )

            elif reading.sensor_type.value == "environment":
                if reading.pressure_hpa is not None:
                    metrics.append(
                        ("shitbox_pressure", labels, reading.pressure_hpa, timestamp_ms)
                    )
                if reading.humidity_pct is not None:
                    metrics.append(
                        ("shitbox_humidity", labels, reading.humidity_pct, timestamp_ms)
                    )
                if reading.env_temp_celsius is not None:
                    metrics.append(
                        ("shitbox_env_temp", labels, reading.env_temp_celsius, timestamp_ms)
                    )
                if reading.gas_resistance_ohms is not None:
                    metrics.append((
                        "shitbox_gas_resistance",
                        labels,
                        reading.gas_resistance_ohms,
                        timestamp_ms,
                    ))

            elif reading.sensor_type.value == "system":
                if reading.cpu_temp_celsius is not None:
                    metrics.append(
                        ("shitbox_cpu_temp", labels, reading.cpu_temp_celsius, timestamp_ms)
                    )

        return metrics

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
        retry=lambda retry_state: (
            retry_state.outcome is not None
            and retry_state.outcome.exception() is not None
            and not isinstance(
                retry_state.outcome.exception(), (DuplicateDataError, TooOldSampleError)
            )
        ),
    )
    def _send_to_prometheus(self, readings: List[Reading]) -> None:
        """Send readings to Prometheus via remote_write API.

        Args:
            readings: List of readings to send.

        Raises:
            DuplicateDataError: If Prometheus rejects as duplicate (don't retry).
            RuntimeError: For other errors (will retry).
        """
        metrics = self._readings_to_metrics(readings)

        if not metrics:
            return

        # Encode as protobuf + snappy
        data = encode_remote_write(metrics)

        log.info(
            "prometheus_write_attempt",
            readings_count=len(readings),
            metrics_count=len(metrics),
            payload_bytes=len(data),
        )

        try:
            response = requests.post(
                self.config.remote_write_url,
                data=data,
                headers={
                    "Content-Type": "application/x-protobuf",
                    "Content-Encoding": "snappy",
                    "X-Prometheus-Remote-Write-Version": "0.1.0",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            log.error("prometheus_write_request_error", error=str(e))
            raise RuntimeError(f"Prometheus request failed: {e}")

        if response.status_code not in (200, 204):
            response_text = response.text[:500] if response.text else ""

            # Check for duplicate sample error - don't retry, just skip
            if response.status_code == 400 and "duplicate sample" in response_text.lower():
                log.warning(
                    "prometheus_duplicate_detected",
                    response_text=response_text,
                )
                raise DuplicateDataError(response_text)

            # Check for too old sample error - don't retry, just skip
            if response.status_code == 400 and "too old sample" in response_text.lower():
                log.warning(
                    "prometheus_too_old_detected",
                    response_text=response_text,
                )
                raise TooOldSampleError(response_text)

            log.error(
                "prometheus_write_http_error",
                status_code=response.status_code,
                response_text=response_text,
            )
            raise RuntimeError(
                f"Prometheus write failed: {response.status_code} {response_text}"
            )

        log.info("prometheus_write_success", metrics_count=len(metrics))

    def get_backlog_count(self) -> int:
        """Get number of unsynced readings."""
        return self.db.get_sync_backlog_count(self._cursor_name)

    def sync_now(self) -> bool:
        """Trigger immediate sync (non-blocking).

        Returns:
            True if sync was triggered, False if not connected.
        """
        if not self.connection.is_connected:
            return False

        threading.Thread(target=self._sync_batch, daemon=True).start()
        return True
