"""Capture sync service - rsyncs captures to NAS when connected."""

import subprocess
import threading
import time
from typing import Optional

from shitbox.events.storage import EventStorage
from shitbox.sync.connection import ConnectionMonitor
from shitbox.utils.config import CaptureSyncConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

RSYNC_TIMEOUT_SECONDS = 600


class CaptureSyncService:
    """Rsync captures directory to NAS when VPN is available.

    Follows the BatchSyncService pattern: daemon thread with a
    sleep-check-work loop gated by ConnectionMonitor.is_connected.
    Before each rsync, regenerates events.json so the NAS always
    has a fresh index.
    """

    def __init__(
        self,
        config: CaptureSyncConfig,
        connection_monitor: ConnectionMonitor,
        captures_dir: str,
        event_storage: Optional[EventStorage] = None,
    ):
        self.config = config
        self.connection = connection_monitor
        self.captures_dir = captures_dir
        self.event_storage = event_storage

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the capture sync service."""
        if self._running:
            return

        log.info(
            "capture_sync_starting",
            remote_dest=self.config.remote_dest,
            interval_seconds=self.config.interval_seconds,
        )

        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the capture sync service."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _sync_loop(self) -> None:
        """Main sync loop."""
        while self._running:
            time.sleep(self.config.interval_seconds)

            if not self._running:
                break

            if not self.connection.is_connected:
                log.debug("capture_sync_skipped_no_connection")
                continue

            try:
                self._do_sync()
            except Exception as e:
                log.error("capture_sync_error", error=str(e))

    def _do_sync(self) -> None:
        """Regenerate events.json and rsync captures to NAS."""
        # Refresh events index before syncing
        if self.event_storage:
            try:
                self.event_storage.generate_events_json()
            except Exception as e:
                log.warning("capture_sync_events_json_error", error=str(e))

        # Ensure source path ends with / for rsync directory semantics
        source = self.captures_dir.rstrip("/") + "/"

        cmd = [
            "rsync",
            "-auv",
            f"--rsync-path={self.config.rsync_path}",
            "-e", "ssh",
            source,
            self.config.remote_dest,
        ]

        log.info("capture_sync_running", cmd=" ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=RSYNC_TIMEOUT_SECONDS,
        )

        if result.returncode == 0:
            log.info("capture_sync_complete", stdout=result.stdout[-500:] if result.stdout else "")
        else:
            log.error(
                "capture_sync_failed",
                returncode=result.returncode,
                stderr=result.stderr[-500:] if result.stderr else "",
            )
