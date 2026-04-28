"""TPMS service: rtl_433 subprocess wrapper + per-wheel state + alerts.

Phase 28 (SPEC-1 through SPEC-10). Subprocess lifecycle lifted from
`src/shitbox/capture/ring_buffer.py` (the ffmpeg pattern shipped in
March 2026 — non-blocking stderr drain to avoid the 64 KB pipe stall).
Alert wiring uses the Phase 15 `health/alerts.py` helper. State and
leak detection are in-process (deque per wheel; GIL-atomic appends).

Structlog keyword logging everywhere. UK/Aus "tyre" spelling in user-
facing strings. Line length ≤ 100. mypy + ruff (E/F/I/W) clean.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, Tuple

from shitbox.events.storage import EventStorage
from shitbox.hardware import probes as hw_probes
from shitbox.hardware import state as hw_state
from shitbox.storage.database import Database
from shitbox.utils.config import TpmsConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Module-level pure helpers (importable without a TPMSService instance)
# ──────────────────────────────────────────────────────────────────────

_KPA_TO_PSI = 0.145037737797  # IEEE 1.0 kPa → PSI conversion factor


def parse_frame(line: str) -> Optional[dict]:
    """Parse one rtl_433 -F json line. Returns None on bad JSON or empty input.

    Wraps json.loads in a try/except so the reader thread never crashes on
    a malformed line. rtl_433 22.11 has been observed to interleave the
    occasional non-JSON banner line on stdout (28-RESEARCH.md Pattern 3).
    """
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def correct_pressure_kpa(raw_kpa: float, *, factor: float) -> float:
    """Apply the empirical correction factor to rtl_433 decoder output.

    The Abarth-124 / VDO-TG1C decoder uses raw_byte × 1.38 internally;
    this aftermarket kit's actual LSB needs an additional × `factor`
    (default 2.45 from the 2026-04-28 bench calibration).
    """
    return raw_kpa * factor


def kpa_to_psi(kpa: float) -> float:
    """Convert kPa to PSI using the IEEE conversion factor (0.145038)."""
    return kpa * _KPA_TO_PSI


def lookup_wheel(sensor_id: str, sensor_map: Dict[str, str]) -> Optional[str]:
    """Return the wheel position for a sensor ID, or None if unmapped.

    Case-insensitive on the input — rtl_433 emits lowercase but the YAML
    sensor map could be authored either way.
    """
    return sensor_map.get(sensor_id.lower())


# ──────────────────────────────────────────────────────────────────────
# Per-wheel state
# ──────────────────────────────────────────────────────────────────────

# Canonical wheel positions in deterministic order — used everywhere
# the dashboard or the snapshot output cares about row order.
WHEEL_POSITIONS: Tuple[str, ...] = (
    "front-driver",
    "front-passenger",
    "rear-driver",
    "rear-passenger",
)


@dataclass
class WheelState:
    """Per-wheel state tracked by TPMSService.

    `last_seen_monotonic` uses time.monotonic() so wall-clock skew
    doesn't affect stale detection. `last_seen_wall` is the wall time
    for log + SSE rendering.
    """

    last_seen_monotonic: Optional[float] = None
    last_seen_wall: Optional[float] = None
    last_psi: Optional[float] = None
    last_temperature_c: Optional[float] = None


# ──────────────────────────────────────────────────────────────────────
# TPMSService
# ──────────────────────────────────────────────────────────────────────

class TPMSService:
    """rtl_433 subprocess wrapper + TPMS frame dispatcher.

    Two daemon threads:
      - reader: blocks on subprocess.stdout.readline(), parses JSON,
                dispatches to _handle_frame.
      - monitor: every RESTART_BACKOFF_S seconds, drains stderr and
                 restarts the subprocess if it has exited. If the SDR
                 has been unplugged (probe_usb_vid_pid False), reports
                 MISSING and backs off DEVICE_MISSING_BACKOFF_S before
                 re-checking.

    The Phase 15 alerts helper is single-writer-per-subtype; all
    fire_alert / fire_recovery calls happen from the reader thread only
    (28-RESEARCH.md Pitfall 7).
    """

    DRAIN_INTERVAL_S: float = 2.0
    RESTART_BACKOFF_S: float = 5.0
    DEVICE_MISSING_BACKOFF_S: float = 30.0

    def __init__(
        self,
        config: TpmsConfig,
        database: Database,
        event_storage: EventStorage,
    ) -> None:
        self.config = config
        self.db = database
        self.event_storage = event_storage

        # Per-wheel state — deterministic order, all wheels initialised.
        self._wheels: Dict[str, WheelState] = {p: WheelState() for p in WHEEL_POSITIONS}
        # Per-wheel leak deque (60-second sliding window of (monotonic_ts, psi)).
        # maxlen=120 = 2 frames/sec × 60s headroom (steady-state is ~1 Hz/wheel).
        self._leak_windows: Dict[str, Deque[Tuple[float, float]]] = {
            p: deque(maxlen=120) for p in WHEEL_POSITIONS
        }

        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running: bool = False
        # Guards _wheels reads from snapshot() while reader updates them.
        self._state_lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn rtl_433 + reader + monitor threads. Idempotent."""
        if self._running:
            return
        if not self.config.enabled:
            log.info("tpms_service_disabled", reason="config.tpms.enabled=false")
            return
        log.info(
            "tpms_starting",
            protocol=self.config.rtl433_protocol_id,
            frequency_hz=self.config.rf_frequency_hz,
            gain_db=self.config.rf_gain_db,
            sensor_count=len(self.config.sensor_map),
        )
        self._running = True
        self._start_subprocess()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="tpms-reader", daemon=True
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="tpms-monitor", daemon=True
        )
        self._reader_thread.start()
        self._monitor_thread.start()

    def stop(self) -> None:
        """Terminate rtl_433 and join both threads. Idempotent."""
        if not self._running:
            return
        log.info("tpms_stopping")
        self._running = False
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
        for t in (self._reader_thread, self._monitor_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)
        log.info("tpms_stopped")

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return a per-wheel state dict for the dashboard SSE payload.

        State machine: no_data → ok | low | critical | stale.
        Stale is computed lazily here (not in _handle_frame) because it's
        time-since-last-seen, not a frame-driven event.
        """
        now = time.monotonic()
        out: Dict[str, Dict[str, Any]] = {}
        with self._state_lock:
            for position in WHEEL_POSITIONS:
                st = self._wheels[position]
                if st.last_seen_monotonic is None:
                    out[position] = {"state": "no_data", "psi": None, "since_ms": None}
                    continue
                age = now - st.last_seen_monotonic
                if age > self.config.stale_timeout_seconds:
                    state = "stale"
                elif (
                    st.last_psi is not None
                    and st.last_psi <= self.config.low_pressure_red_psi
                ):
                    state = "critical"
                elif (
                    st.last_psi is not None
                    and st.last_psi <= self.config.low_pressure_yellow_psi
                ):
                    state = "low"
                else:
                    state = "ok"
                out[position] = {
                    "state": state,
                    "psi": round(st.last_psi, 1) if st.last_psi is not None else None,
                    "since_ms": int(age * 1000),
                }
        return out

    # ── Subprocess lifecycle ──────────────────────────────────────

    def _build_cmd(self) -> list:
        """rtl_433 command line.

        - ``-R 156``  — Abarth-124 / VDO-TG1C decoder only
        - ``-F json`` — newline-delimited JSON on stdout
        - ``-M time:utc`` — ISO timestamps in each frame
        - ``-g``      — explicit R820T2 gain in dB
        - ``-f``      — centre frequency in Hz
        """
        return [
            "rtl_433",
            "-R", str(self.config.rtl433_protocol_id),
            "-F", "json",
            "-M", "time:utc",
            "-g", str(self.config.rf_gain_db),
            "-f", str(self.config.rf_frequency_hz),
        ]

    def _start_subprocess(self) -> None:
        cmd = self._build_cmd()
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered stdout
            )
        except FileNotFoundError:
            log.warning(
                "tpms_rtl433_binary_missing",
                hint="apt install rtl-433 librtlsdr-dev",
            )
            self._process = None
            return
        log.info("tpms_rtl433_started", pid=self._process.pid, cmd=" ".join(cmd))

    def _read_stderr_nonblocking(self) -> str:
        """Drain stderr without blocking. Lifted from
        capture/ring_buffer.py:827-846 — same root cause as the March
        2026 ffmpeg pipe-buffer stall (28-RESEARCH.md Pitfall 1)."""
        if self._process and self._process.stderr:
            try:
                fd = self._process.stderr.fileno()
                flags = os.get_blocking(fd)
                os.set_blocking(fd, False)
                try:
                    data = b""
                    while True:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            break
                        data += chunk
                finally:
                    os.set_blocking(fd, flags)
                return data.decode(errors="replace")[-500:]
            except Exception:
                pass
        return ""

    def _reader_loop(self) -> None:
        """Read JSON lines from rtl_433 stdout, dispatch to _handle_frame."""
        while self._running:
            if self._process is None or self._process.stdout is None:
                time.sleep(0.5)
                continue
            try:
                line = self._process.stdout.readline()
            except Exception as e:  # pragma: no cover — defensive
                log.warning("tpms_stdout_read_error", error=str(e))
                time.sleep(0.5)
                continue
            if not line:
                # EOF — process died. Monitor will restart it.
                time.sleep(0.5)
                continue
            try:
                self._handle_frame(line.strip())
            except Exception as e:
                log.warning(
                    "tpms_frame_handle_error", error=str(e), line=line[:200]
                )

    def _monitor_loop(self) -> None:
        """Drain stderr periodically; restart rtl_433 on exit; back off
        when the SDR is missing. Mirrors ring_buffer._health_monitor."""
        while self._running:
            time.sleep(self.RESTART_BACKOFF_S)
            if not self._running:
                break
            try:
                if self._process is not None and self._process.poll() is None:
                    # Alive — drain stderr to prevent pipe buffer fill.
                    self._read_stderr_nonblocking()
                    continue

                # Process is dead (or never spawned).
                if self._process is not None:
                    rc = self._process.returncode
                    stderr_tail = self._read_stderr_nonblocking()
                    log.warning(
                        "tpms_rtl433_exited", returncode=rc, stderr=stderr_tail
                    )

                # Check the USB device. If missing, mark MISSING and back off.
                if not hw_probes.probe_usb_vid_pid(self.config.usb_vid_pid):
                    hw_state.report_missing("tpms_radio")
                    log.warning(
                        "tpms_sdr_missing",
                        vid_pid=self.config.usb_vid_pid,
                        backoff_seconds=self.DEVICE_MISSING_BACKOFF_S,
                    )
                    backoff_end = time.time() + self.DEVICE_MISSING_BACKOFF_S
                    while time.time() < backoff_end and self._running:
                        time.sleep(1.0)
                    continue

                # SDR present — respawn.
                hw_state.report_present("tpms_radio")
                self._start_subprocess()
            except Exception as e:
                log.error("tpms_monitor_error", error=str(e))

    # ── Frame handling (PLACEHOLDER — Task 2 fills this in) ───────

    def _handle_frame(self, line: str) -> None:
        """Parse, correct, persist, dispatch alerts. Implemented in Task 2."""
        raise NotImplementedError("Task 2 fills in _handle_frame")
