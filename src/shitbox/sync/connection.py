"""Network connectivity detection."""

import socket
import threading
import time
from typing import Callable, Optional

from shitbox.utils.config import ConnectivityConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class ConnectionMonitor:
    """Monitor network connectivity status.

    Periodically checks if the network is available and notifies
    callbacks when connectivity changes.
    """

    def __init__(
        self,
        config: ConnectivityConfig,
        on_connected: Optional[Callable[[], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
    ):
        """Initialise connection monitor.

        Args:
            config: Connectivity configuration.
            on_connected: Callback when connection is established.
            on_disconnected: Callback when connection is lost.
        """
        self.config = config
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected

        self._is_connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def check_connectivity(self) -> bool:
        """Check if network is available.

        Returns:
            True if connected, False otherwise.
        """
        try:
            socket.setdefaulttimeout(self.config.timeout_seconds)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(
                (self.config.check_host, self.config.check_port)
            )
            sock.close()
            return result == 0
        except (socket.timeout, socket.error, OSError):
            return False

    def check_host_reachable(self, host: str, port: int) -> bool:
        """Check if a specific host is reachable.

        Args:
            host: Hostname or IP address.
            port: Port number.

        Returns:
            True if reachable, False otherwise.
        """
        try:
            socket.setdefaulttimeout(self.config.timeout_seconds)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except (socket.timeout, socket.error, OSError):
            return False

    def start(self) -> None:
        """Start monitoring connectivity in background."""
        if self._running:
            return

        log.info(
            "starting_connection_monitor",
            check_host=self.config.check_host,
            interval_s=self.config.check_interval_seconds,
        )

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring connectivity."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            was_connected = self._is_connected
            is_now_connected = self.check_connectivity()

            with self._lock:
                self._is_connected = is_now_connected

            # Detect state change
            if is_now_connected and not was_connected:
                log.info("network_connected")
                if self.on_connected:
                    try:
                        self.on_connected()
                    except Exception as e:
                        log.error("on_connected_callback_error", error=str(e))

            elif not is_now_connected and was_connected:
                log.warning("network_disconnected")
                if self.on_disconnected:
                    try:
                        self.on_disconnected()
                    except Exception as e:
                        log.error("on_disconnected_callback_error", error=str(e))

            time.sleep(self.config.check_interval_seconds)

    @property
    def is_connected(self) -> bool:
        """Check current connectivity status."""
        with self._lock:
            return self._is_connected

    def wait_for_connection(self, timeout: Optional[float] = None) -> bool:
        """Block until connection is available.

        Args:
            timeout: Maximum seconds to wait. None for indefinite.

        Returns:
            True if connected, False if timed out.
        """
        start = time.monotonic()
        while True:
            if self.is_connected:
                return True

            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False

            time.sleep(1.0)
