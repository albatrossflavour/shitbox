"""Persistent gpsd JSON-stream client.

Replaces gpsd-py3's ``get_current()`` (which bails with ``UserWarning("GPS not
active")`` whenever the next line off the socket isn't a TPV — a single SKY
frame at the wrong moment kills a whole poll cycle) and the per-second
reconnect in the old ``_get_satellite_count`` helper.

One socket, one background thread. The reader parses every JSON object gpsd
emits and caches the latest TPV (position/fix/speed) and SKY (satellite
counts). Callers read the cache; the socket churn is gone. Broken pipes are
handled by the reader via exponential backoff reconnect.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any, Dict, Optional, Tuple

import structlog

log = structlog.get_logger(__name__)

_RECONNECT_MAX_SECONDS: float = 30.0
_CONNECT_TIMEOUT_SECONDS: float = 5.0
_RECV_CHUNK: int = 4096
_WATCH_CMD: bytes = b'?WATCH={"enable":true,"json":true}\n'


class GpsdClient:
    """Background gpsd client that caches the latest TPV and SKY frames."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2947,
        role: str = "gps",
    ) -> None:
        self.host = host
        self.port = port
        self.role = role
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()
        self._latest_tpv: Optional[Dict[str, Any]] = None
        self._latest_sky: Optional[Dict[str, Any]] = None
        self._last_tpv_mono: float = 0.0
        self._connected: bool = False

    def start(self) -> None:
        """Start the background reader thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="gpsd-reader"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the reader and close the socket."""
        self._running = False
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    @property
    def connected(self) -> bool:
        """Whether the socket is currently up."""
        return self._connected

    def get_latest(
        self,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], float]:
        """Return (latest_tpv, latest_sky, monotonic_ts_of_latest_tpv)."""
        with self._lock:
            return self._latest_tpv, self._latest_sky, self._last_tpv_mono

    def _reader_loop(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(_CONNECT_TIMEOUT_SECONDS)
                sock.connect((self.host, self.port))
                sock.sendall(_WATCH_CMD)
                sock.settimeout(None)
                self._sock = sock
                self._connected = True
                backoff = 1.0
                log.info("gpsd_connected", host=self.host, port=self.port)
                self._drain(sock)
            except Exception as e:
                log.warning("gpsd_connection_error", error=str(e))
            finally:
                self._connected = False
                sock = self._sock
                self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if not self._running:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2.0, _RECONNECT_MAX_SECONDS)

    def _drain(self, sock: socket.socket) -> None:
        buf = b""
        while self._running:
            try:
                chunk = sock.recv(_RECV_CHUNK)
            except OSError as e:
                raise OSError(f"gpsd recv failed: {e}") from e
            if not chunk:
                raise OSError("gpsd connection closed")
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line)

    def _handle_line(self, raw: bytes) -> None:
        line = raw.strip()
        if not line:
            return
        try:
            obj = json.loads(line.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return
        cls = obj.get("class")
        if cls == "TPV":
            with self._lock:
                self._latest_tpv = obj
                self._last_tpv_mono = time.monotonic()
            if self.role:
                # Local import -- avoids import cycle and keeps gpsd_client
                # usable without the hardware module.
                from shitbox.hardware import state as hw_state
                hw_state.report_present(self.role)
        elif cls == "SKY":
            with self._lock:
                self._latest_sky = obj
