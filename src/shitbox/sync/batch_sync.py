"""Batch sync service for historical data to Prometheus."""

import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

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

    Rejection handling:
    - Duplicate samples: safe to skip (already in Prometheus).
    - Too-old samples: retried for MAX_TOO_OLD_RETRIES cycles before
      skipping. Data remains in SQLite and can be recovered manually.
    """

    # Number of consecutive sync cycles to retry before skipping a
    # batch that Prometheus rejects as "too old".  At 15 s intervals
    # this gives ~5 minutes for transient issues to clear.
    MAX_TOO_OLD_RETRIES = 20

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
        self._too_old_failures: int = 0
        self._too_old_cursor: int = -1

        # Cumulative stats for sync state logging
        self._total_synced: int = 0
        self._total_failed: int = 0
        self._total_skipped: int = 0
        self._consecutive_errors: int = 0
        self._last_success_time: Optional[str] = None
        self._last_error: Optional[str] = None

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

            # Log sync state every cycle
            self._log_sync_state()

            # Only sync if connected
            if not self.connection.is_connected:
                log.info("batch_sync_skipped_no_connection")
                continue

            try:
                self._sync_batch()
            except Exception as e:
                self._consecutive_errors += 1
                self._total_failed += 1
                self._last_error = str(e)
                log.error("batch_sync_error", error=str(e))

    def _log_sync_state(self) -> None:
        """Log full sync state for debugging."""
        try:
            now_utc = datetime.now(timezone.utc)
            cursor = self.db.get_sync_cursor(self._cursor_name)
            backlog = self.db.get_sync_backlog_count(self._cursor_name)
            oldest, newest = self.db.get_sync_backlog_time_range(
                self._cursor_name,
            )

            # Calculate sync lag in seconds
            sync_lag_seconds: Optional[float] = None
            if oldest:
                try:
                    oldest_dt = datetime.fromisoformat(oldest)
                    if oldest_dt.tzinfo is None:
                        oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
                    sync_lag_seconds = round(
                        (now_utc - oldest_dt).total_seconds(), 1,
                    )
                except (ValueError, TypeError):
                    pass

            log.info(
                "sync_state",
                now_utc=now_utc.isoformat(),
                connected=self.connection.is_connected,
                cursor_position=cursor.last_synced_id,
                cursor_updated=(
                    cursor.last_synced_at.isoformat()
                    if cursor.last_synced_at
                    else None
                ),
                backlog=backlog,
                backlog_oldest=oldest,
                backlog_newest=newest,
                sync_lag_seconds=sync_lag_seconds,
                total_synced=self._total_synced,
                total_failed=self._total_failed,
                total_skipped=self._total_skipped,
                consecutive_errors=self._consecutive_errors,
                too_old_failures=self._too_old_failures,
                last_success=self._last_success_time,
                last_error=self._last_error,
                endpoint=self.config.remote_write_url,
                batch_size=self.config.batch_size,
            )
        except Exception as e:
            log.warning("sync_state_log_error", error=str(e))

    def _sync_batch(self) -> None:
        """Sync a single batch of readings.

        On "too old" rejection the cursor is NOT advanced immediately.
        The batch is retried for MAX_TOO_OLD_RETRIES cycles.  If it
        still fails, the batch is skipped with an ERROR-level log so
        the pipeline does not stall permanently.  Data remains in
        SQLite for manual recovery.
        """
        # Get unsynced readings
        readings = self.db.get_unsynced_readings(
            cursor_name=self._cursor_name,
            batch_size=self.config.batch_size,
        )

        if not readings:
            log.debug("batch_sync_no_data")
            return

        first_id = readings[0].id
        last_id = readings[-1].id
        oldest = readings[0].timestamp_utc.isoformat()
        newest = readings[-1].timestamp_utc.isoformat()

        # Sensor type breakdown
        sensor_counts: Dict[str, int] = dict(
            Counter(r.sensor_type.value for r in readings)
        )

        log.info(
            "batch_sync_starting",
            count=len(readings),
            first_id=first_id,
            last_id=last_id,
            oldest=oldest,
            newest=newest,
            sensor_types=sensor_counts,
        )

        # Convert to Prometheus format and send
        try:
            self._send_to_prometheus(readings)

            # Success — reset failure tracking and advance cursor
            self._too_old_failures = 0
            self._too_old_cursor = -1
            self._total_synced += len(readings)
            self._consecutive_errors = 0
            self._last_success_time = datetime.now(timezone.utc).isoformat()
            self.db.update_sync_cursor(self._cursor_name, last_id)
            log.info("batch_sync_complete", count=len(readings), last_id=last_id)

        except DuplicateDataError:
            # Data already exists in Prometheus — safe to skip
            log.warning(
                "batch_sync_duplicate_skipped",
                count=len(readings),
                first_id=first_id,
                last_id=last_id,
                hint="Data already synced via another path",
            )
            self._too_old_failures = 0
            self._too_old_cursor = -1
            self._total_skipped += len(readings)
            self._consecutive_errors = 0
            self.db.update_sync_cursor(self._cursor_name, last_id)

        except TooOldSampleError:
            # Track consecutive failures at the same cursor position
            if self._too_old_cursor != first_id:
                self._too_old_cursor = first_id
                self._too_old_failures = 1
            else:
                self._too_old_failures += 1

            if self._too_old_failures < self.MAX_TOO_OLD_RETRIES:
                log.warning(
                    "batch_sync_too_old_retrying",
                    count=len(readings),
                    first_id=first_id,
                    last_id=last_id,
                    oldest=oldest,
                    newest=newest,
                    attempt=self._too_old_failures,
                    max_retries=self.MAX_TOO_OLD_RETRIES,
                )
                # Do NOT advance cursor — will retry next cycle
            else:
                log.error(
                    "batch_sync_too_old_abandoned",
                    count=len(readings),
                    first_id=first_id,
                    last_id=last_id,
                    oldest=oldest,
                    newest=newest,
                    attempts=self._too_old_failures,
                    hint="Data remains in SQLite for manual recovery",
                )
                self._too_old_failures = 0
                self._too_old_cursor = -1
                self._total_skipped += len(readings)
                self.db.update_sync_cursor(self._cursor_name, last_id)

        except Exception as e:
            self._consecutive_errors += 1
            self._total_failed += 1
            self._last_error = str(e)
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
                if reading.disk_percent is not None:
                    metrics.append(
                        ("shitbox_disk_pct", labels, reading.disk_percent, timestamp_ms)
                    )
                if reading.sync_backlog is not None:
                    metrics.append(
                        ("shitbox_sync_backlog", labels, float(reading.sync_backlog), timestamp_ms)
                    )
                if reading.throttle_flags is not None:
                    metrics.append(
                        (
                            "shitbox_throttle_flags",
                            labels,
                            float(reading.throttle_flags),
                            timestamp_ms,
                        )
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
                retry_state.outcome.exception(),
                (DuplicateDataError, TooOldSampleError),
            )
        ),
    )
    def _send_to_prometheus(self, readings: List[Reading]) -> None:
        """Send readings to Prometheus via remote_write API.

        Args:
            readings: List of readings to send.

        Raises:
            DuplicateDataError: If Prometheus rejects as duplicate.
            TooOldSampleError: If Prometheus rejects as too old.
            RuntimeError: For other errors (will retry).
        """
        metrics = self._readings_to_metrics(readings)

        if not metrics:
            return

        # Encode as protobuf + snappy
        data = encode_remote_write(metrics)

        # Determine tenacity attempt number
        attempt = 1
        if hasattr(self._send_to_prometheus, "statistics"):
            stats = self._send_to_prometheus.statistics
            attempt = stats.get("attempt_number", 1)

        log.info(
            "prometheus_write_attempt",
            attempt=attempt,
            readings_count=len(readings),
            metrics_count=len(metrics),
            payload_bytes=len(data),
            url=self.config.remote_write_url,
        )

        t0 = time.monotonic()
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
            duration_ms = round(
                (time.monotonic() - t0) * 1000, 1,
            )
            log.error(
                "prometheus_write_request_error",
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                attempt=attempt,
            )
            raise RuntimeError(f"Prometheus request failed: {e}")

        duration_ms = round((time.monotonic() - t0) * 1000, 1)

        # Extract useful response headers for debugging
        resp_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower().startswith("x-") or k.lower() == "retry-after"
        }

        if response.status_code not in (200, 204):
            response_text = response.text[:500] if response.text else ""

            if (
                response.status_code == 400
                and "duplicate sample" in response_text.lower()
            ):
                log.warning(
                    "prometheus_duplicate_detected",
                    response_text=response_text,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    response_headers=resp_headers,
                )
                raise DuplicateDataError(response_text)

            if (
                response.status_code == 400
                and "too old sample" in response_text.lower()
            ):
                oldest_ms = metrics[0][3] if metrics else 0
                newest_ms = metrics[-1][3] if metrics else 0
                now_ms = int(
                    datetime.now(timezone.utc).timestamp() * 1000,
                )
                log.warning(
                    "prometheus_too_old_detected",
                    response_text=response_text.strip(),
                    oldest_sample_ms=oldest_ms,
                    newest_sample_ms=newest_ms,
                    now_ms=now_ms,
                    age_seconds=(
                        (now_ms - oldest_ms) // 1000
                        if oldest_ms
                        else 0
                    ),
                    readings_count=len(readings),
                    duration_ms=duration_ms,
                    attempt=attempt,
                    response_headers=resp_headers,
                )
                raise TooOldSampleError(response_text)

            log.error(
                "prometheus_write_http_error",
                status_code=response.status_code,
                response_text=response_text,
                duration_ms=duration_ms,
                attempt=attempt,
                response_headers=resp_headers,
            )
            raise RuntimeError(
                f"Prometheus write failed: "
                f"{response.status_code} {response_text}"
            )

        log.info(
            "prometheus_write_success",
            metrics_count=len(metrics),
            duration_ms=duration_ms,
            attempt=attempt,
            response_headers=resp_headers,
        )

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
