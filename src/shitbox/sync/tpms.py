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

from shitbox.capture.speaker import speak_tpms_leak, speak_tpms_low, speak_tpms_restored
from shitbox.events.detector import Event, EventType
from shitbox.events.storage import EventStorage
from shitbox.hardware import probes as hw_probes
from shitbox.hardware import state as hw_state
from shitbox.health import alerts
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
        # Single-shot guard for events.json: alerts.fire_alert dedupes TTS but
        # save_event runs every frame the spike is in-window without this flag,
        # producing ~60 TPMS_LEAK rows per real leak. Flag resets in
        # _detect_leak when the spike rolls past the cutoff.
        self._leak_event_fired: Dict[str, bool] = {p: False for p in WHEEL_POSITIONS}

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
        """Drain stderr without blocking. Adapted from
        capture/ring_buffer.py:827-846 — same root cause as the March
        2026 ffmpeg pipe-buffer stall (28-RESEARCH.md Pitfall 1).

        On a non-blocking pipe, ``os.read`` raises ``BlockingIOError``
        once the buffer is empty rather than returning ``b""``. The
        ring_buffer.py original silently lost the accumulated bytes
        when this happened (the bare ``except Exception: pass`` swallowed
        it after dropping the partial data); the variant here catches
        the BlockingIOError as the loop-exit signal and returns whatever
        was already drained.
        """
        if self._process and self._process.stderr:
            data = b""
            try:
                fd = self._process.stderr.fileno()
                flags = os.get_blocking(fd)
                os.set_blocking(fd, False)
                try:
                    while True:
                        try:
                            chunk = os.read(fd, 4096)
                        except BlockingIOError:
                            # Pipe is empty for now — that's the signal to stop.
                            break
                        if not chunk:
                            # EOF (writer closed).
                            break
                        data += chunk
                finally:
                    os.set_blocking(fd, flags)
                return data.decode(errors="replace")[-500:]
            except Exception:
                # Last-ditch: keep whatever we already drained.
                return data.decode(errors="replace")[-500:] if data else ""
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

    # ── Frame handling ────────────────────────────────────────────

    def _handle_frame(self, line: str) -> None:
        """Parse one rtl_433 -F json line and dispatch state + alerts.

        Pipeline (per 28-RESEARCH.md Pattern 2 + Pattern 7):
            parse → lookup → correct → persist → state → alerts → leak.

        Frame rate is ~4 Hz across all four wheels combined (~1 Hz each)
        so a structlog INFO line per parsed frame is well below the
        noise threshold for the existing log channels.
        """
        parsed = parse_frame(line)
        if parsed is None:
            return  # malformed JSON or empty — drop silently
        if parsed.get("type") != "TPMS":
            return  # rtl_433 may emit non-TPMS frames if other decoders match
        sensor_id_raw = parsed.get("id", "")
        if not isinstance(sensor_id_raw, str) or not sensor_id_raw:
            return
        sensor_id = sensor_id_raw.lower()
        position = lookup_wheel(sensor_id, self.config.sensor_map)
        if position is None:
            log.info("tpms_unknown_sensor", sensor_id=sensor_id)
            return

        try:
            raw_kpa = float(parsed.get("pressure_kPa", 0.0))
            temperature_c = float(parsed.get("temperature_C", 0.0))
        except (TypeError, ValueError) as e:
            log.warning(
                "tpms_frame_field_error", error=str(e), wheel=position
            )
            return
        corrected_kpa = correct_pressure_kpa(
            raw_kpa, factor=self.config.pressure_correction_factor
        )
        psi = kpa_to_psi(corrected_kpa)
        status_raw = parsed.get("status")
        status: Optional[int] = status_raw if isinstance(status_raw, int) else None
        timestamp_utc_raw = parsed.get("time", "")
        timestamp_utc = timestamp_utc_raw if isinstance(timestamp_utc_raw, str) else ""

        log.info(
            "tpms_frame_received",
            wheel=position,
            sensor_id=sensor_id,
            pressure_psi=round(psi, 2),
            raw_kpa=round(raw_kpa, 2),
            corrected_kpa=round(corrected_kpa, 2),
            temperature_c=temperature_c,
        )

        # Persist (one row per parsed frame — SPEC-4).
        try:
            self.db.insert_tpms_reading(
                timestamp_utc=timestamp_utc,
                sensor_id=sensor_id,
                wheel=position,
                pressure_psi=psi,
                temperature_c=temperature_c,
                status=status,
                raw_pressure_kpa=raw_kpa,
            )
        except Exception as e:
            log.warning("tpms_db_insert_failed", error=str(e), wheel=position)

        # Update per-wheel state (single-writer: only this thread mutates _wheels).
        now_mono = time.monotonic()
        with self._state_lock:
            st = self._wheels[position]
            st.last_seen_monotonic = now_mono
            st.last_seen_wall = time.time()
            st.last_psi = psi
            st.last_temperature_c = temperature_c

        # Leak detection (deque per wheel — SPEC-8).
        leak_now = self._detect_leak(position, psi, now_mono)

        # Sustained-low alerts (SPEC-7) — only the red threshold fires TTS.
        self._wire_low_pressure_alert(position, psi)

        # Leak alert + event recording (SPEC-8).
        if leak_now:
            self._wire_leak_alert(position, psi)

    def _detect_leak(self, position: str, psi_now: float, now_mono: float) -> bool:
        """Append (now, psi) to the wheel's deque; return True if max-min in
        the window ≥ leak_drop_psi.

        Window is `leak_window_seconds` (default 60s). Returns True every
        frame the threshold is crossed — `alerts.fire_alert` collapses
        repeated active=True calls to a single fire (Phase 15 sustain
        semantics with `sustain_required=1`).
        """
        window = self._leak_windows[position]
        window.append((now_mono, psi_now))
        cutoff = now_mono - self.config.leak_window_seconds
        in_window = [psi for ts, psi in window if ts >= cutoff]
        if not in_window:
            self._leak_event_fired[position] = False
            return False
        spiked = (max(in_window) - psi_now) >= self.config.leak_drop_psi
        if not spiked:
            self._leak_event_fired[position] = False
        return spiked

    @staticmethod
    def _position_to_subtype(prefix: str, position: str) -> str:
        """``'LOW' + 'front-driver'`` → ``'TPMS_LOW_FRONT_DRIVER'``."""
        return f"TPMS_{prefix}_{position.upper().replace('-', '_')}"

    def _wire_low_pressure_alert(self, position: str, psi: float) -> None:
        """Fire/recover the sustained-low subtype for this wheel.

        Yellow band (25 < psi ≤ 28) is a Health-page row colour only —
        no fire_alert call. Red band (psi ≤ 25) fires after
        ``sustain_required`` consecutive frames; recovery requires
        psi > 28 for the same number of frames (recovery_subtype mirrors
        the Phase 15 ``_RESTORED`` suffix convention).
        """
        subtype = self._position_to_subtype("LOW", position)
        red_active = psi <= self.config.low_pressure_red_psi
        position_label = position.upper().replace("-", " ")

        # Inner functions close over `position` cleanly without the
        # `p=position` default-arg-lambda dance (which trips mypy's
        # type inference). Each call's `position` is the local scope's
        # value, so no late-binding hazard.
        def _say_low() -> None:
            speak_tpms_low(position)

        def _say_restored() -> None:
            speak_tpms_restored(position)

        # Mirrors thermal_monitor.py:326-340 — fire_alert and fire_recovery
        # are both passed the same `active` boolean; the helpers own the
        # edge logic. fire_recovery only emits once `active=False` has
        # sustained for `sustain_required` frames.
        alerts.fire_alert(
            subtype,
            red_active,
            f"{position_label} TYRE LOW PRESSURE",
            _say_low if red_active else None,
            sustain_required=self.config.sustain_required,
        )
        alerts.fire_recovery(
            subtype,
            red_active,
            f"{position_label} TYRE PRESSURE RESTORED",
            _say_restored,
            sustain_required=self.config.sustain_required,
            recovery_subtype=f"{subtype}_RESTORED",
        )

    def _wire_leak_alert(self, position: str, psi: float) -> None:
        """Fire the leak subtype + write a TPMS_LEAK Event to events.json.

        Leak is single-shot: ``sustain_required=1`` (the deque has
        already confirmed the drop). The Phase 15 ``fire_alert`` helper
        collapses repeated active=True calls to a single emit, so
        firing every frame the deque is over-threshold is safe.

        Recovery for leak subtypes is not wired here — by design.
        Once the deque rolls past the spike, ``_detect_leak`` returns
        False, so we simply stop calling fire_alert. The Phase 15
        helper holds ``fired=True`` until a fire_recovery sustains; for
        leaks we accept the alert stays "live" in the dashboard until
        the next reboot or an explicit clear. Acceptable per SPEC: a
        leak event is forensic, not a trip-state flag.
        """
        subtype = self._position_to_subtype("LEAK", position)
        position_label = position.upper().replace("-", " ")

        def _say_leak() -> None:
            speak_tpms_leak(position)

        alerts.fire_alert(
            subtype,
            True,
            f"TYRE LEAKING, {position_label}",
            _say_leak,
            sustain_required=1,
        )

        # Single-shot save_event: only the FIRST frame inside the spike
        # window writes events.json. _detect_leak clears the flag when
        # the spike rolls past the cutoff, allowing the next physical
        # leak to be recorded.
        if self._leak_event_fired.get(position, False):
            return
        self._leak_event_fired[position] = True

        # Write a TPMS_LEAK Event to events.json (no IMU samples, no
        # video buffer save — leak data alone tells the story per
        # SPEC REQ 8 / Plan 28-02 decision).
        try:
            now_wall = time.time()
            event = Event(
                event_type=EventType.TPMS_LEAK,
                start_time=now_wall,
                end_time=now_wall,
                peak_value=psi,
                peak_ax=0.0,
                peak_ay=0.0,
                peak_az=0.0,
                samples=[],
            )
            self.event_storage.save_event(event, video_path=None)
            log.info(
                "tpms_leak_event_recorded",
                wheel=position,
                pressure_psi=round(psi, 2),
            )
        except Exception as e:
            log.warning(
                "tpms_leak_event_save_failed", error=str(e), wheel=position
            )
