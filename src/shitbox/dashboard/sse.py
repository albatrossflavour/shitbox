"""Server-Sent Event routers for the live dashboard.

Three streams:

- ``/sse/fast`` — 10 Hz telemetry (speed, IMU, heading)
- ``/sse/slow`` — 1 Hz context (GPS fix, temps, sync state, event count)
- ``/sse/events`` — seeded with the last 10 events, then live pushes

All three share an 8-client cap (``MAX_CLIENTS``) per requirement D-03. A 9th
connection is rejected with HTTP 503. Event pushes from the engine's sync
detector callback use :func:`push_event`, which is non-blocking and drops on
full so the 100 Hz capture path (D-02/D-04) is never made to wait.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse  # noqa: F401  # kept for API symmetry
from sse_starlette.sse import EventSourceResponse

from shitbox.dashboard.snapshot import read_snapshot
from shitbox.hardware import state as hw_state

# Graceful-degradation import per D-04 / RESEARCH Pattern 2.
# The dashboard must still serve /sse/slow even if the alerts helper is
# absent (e.g. during unit tests that mock the dashboard subsystem). The
# no-op stub keeps `_system_conditions_payload` emitting three clear rows.
try:
    from shitbox.health import alerts
except ImportError:  # pragma: no cover — only triggered when alerts is unavailable
    class _NoopAlertsSnapshot:
        @staticmethod
        def snapshot() -> Dict[str, Any]:  # type: ignore[override]
            return {}

    alerts = _NoopAlertsSnapshot()  # type: ignore[assignment]

# Phase 28 — graceful degradation: dashboard works without TPMSService
# (e.g. unit tests, daemon started with tpms.enabled=false). WHEEL_POSITIONS
# is the canonical FD/FP/RD/RP order; mirror the tpms.py constant so the
# dashboard renders four deterministic rows even when the TPMS module is
# unavailable.
try:
    from shitbox.sync.tpms import WHEEL_POSITIONS
except ImportError:  # pragma: no cover
    WHEEL_POSITIONS = (
        "front-driver",
        "front-passenger",
        "rear-driver",
        "rear-passenger",
    )

log = structlog.get_logger(__name__)

_HARDWARE_LABELS: Dict[str, str] = {
    "imu": "IMU",
    "camera_front": "Front Cam",
    "power": "Power",
    "gps": "GPS",
    "environment": "Environment",
    "magnetometer": "Magnetometer",
    "light": "Ambient Light",
    "oled": "OLED",
    "temp_exterior": "Exterior Probe",
    "temp_engine_bay": "Engine Bay Probe",
    "camera_cabin": "Cabin Cam",
    "audio_mic": "USB Mic",
    "button": "Button",
    "display_hdmi": "HDMI",
    "tpms_radio": "TPMS Radio",
    "power_battery": "Battery",
    "audio_cabin_mic": "Cabin Mic",
}


def _hardware_label(role: str) -> str:
    return _HARDWARE_LABELS.get(role, role.replace("_", " ").title())


def _hardware_payload() -> List[Dict[str, Any]]:
    now = time.time()
    out = []
    for st in hw_state.snapshot().values():
        last_seen = st.last_seen if st.last_seen > 0 else None
        since_ms = int((now - st.last_seen) * 1000) if st.last_seen > 0 else None
        out.append({
            "role": st.role,
            "label": _hardware_label(st.role),
            "tier": st.tier,
            "state": st.state.value,
            "last_seen": last_seen,
            "since_ms": since_ms,
        })
    return out


# Phase 15-05 (D-13) — system-condition payload for the Health modal.
#
# UI-SPEC contract (lines 170-209): exactly five scalar fields per row,
# always three rows in order undervoltage → thermal → capture. No history
# arrays, no bitmasks, no message text — log detail lives in structlog.
_SYSTEM_CONDITION_LABELS: Dict[str, str] = {
    "undervoltage": "UNDERVOLTAGE",
    "thermal": "THERMAL",
    "capture": "CAPTURE",
}

# Maps alerts subtype → role. Recovery subtypes (*_CLEARED / *_RESTORED) do
# NOT appear here: the helper bookkeeps on the base subtype and the `fired`
# and `active` fields on that entry drive the row state.
_SUBTYPE_TO_ROLE: Dict[str, str] = {
    "UNDERVOLTAGE": "undervoltage",
    "THERMAL_WARNING": "thermal",
    "THERMAL_CRITICAL": "thermal",
    "CAPTURE_FAILURE": "capture",
    "CAPTURE_DOWN": "capture",
}


def _system_conditions_payload() -> List[Dict[str, Any]]:
    """Render the three system conditions for /sse/slow.

    Always emits all three rows so the frontend always has a complete set.
    State is derived from alerts.snapshot():
      - fired and active         → "active"
      - fired and not active     → "restored"
      - neither                  → "clear"
    ``since_ms`` is int millis since ``last_change_ts`` when available, else None.
    """
    now = time.time()
    snap = alerts.snapshot()

    role_state: Dict[str, Dict[str, Any]] = {
        "undervoltage": {"state": "clear", "since_ms": None},
        "thermal": {"state": "clear", "since_ms": None},
        "capture": {"state": "clear", "since_ms": None},
    }
    for subtype, status in snap.items():
        role = _SUBTYPE_TO_ROLE.get(subtype)
        if role is None:
            continue
        if status.fired and status.active:
            role_state[role]["state"] = "active"
            role_state[role]["since_ms"] = int((now - status.last_change_ts) * 1000)
        elif status.fired and not status.active:
            # Do not overwrite an active roll-up from another subtype under the same role
            if role_state[role]["state"] != "active":
                role_state[role]["state"] = "restored"
                role_state[role]["since_ms"] = int((now - status.last_change_ts) * 1000)

    out: List[Dict[str, Any]] = []
    for role, label in _SYSTEM_CONDITION_LABELS.items():
        rs = role_state[role]
        out.append({
            "role": role,
            "label": label,
            "tier": "critical",
            "state": rs["state"],
            "since_ms": rs["since_ms"],
        })
    return out


MAX_CLIENTS: int = 8
KEEPALIVE_SECONDS: int = 15
FAST_HZ: float = 10.0
SLOW_HZ: float = 1.0

router = APIRouter()

_active_clients: int = 0
_clients_lock = threading.Lock()

# Fan-out: each connected /sse/events client registers its own queue.
# push_event() broadcasts to all of them so every client sees every event,
# regardless of how many connections are active. A single shared queue would
# let stale generators (from reconnects) consume events before the live
# connection sees them.
_event_listeners: "List[queue.Queue[Dict[str, Any]]]" = []
_event_listeners_lock = threading.Lock()

_recent_provider: Optional[Callable[[int], List[Dict[str, Any]]]] = None


def set_recent_events_provider(
    fn: Optional[Callable[[int], List[Dict[str, Any]]]],
) -> None:
    """Register a callable returning the last N events (newest first).

    The engine wires this to ``EventStorage.recent`` at dashboard build time.
    """
    global _recent_provider
    _recent_provider = fn


# Phase 28 — TPMSService snapshot provider, set by the engine at startup.
# Optional[Any] avoids the import-cycle dance (sse.py is imported by the
# dashboard server before TPMSService is constructed). Tests
# `monkeypatch.setattr` it to None or a stub.
tpms_service: Optional[Any] = None


def set_tpms_service(svc: Optional[Any]) -> None:
    """Register the running TPMSService so _tpms_payload can pull state.

    The engine calls this at start() with self.tpms (or None when the
    service is disabled, missing the rtl_433 binary, or not yet built).
    """
    global tpms_service
    tpms_service = svc


# Phase 28 (SPEC-6) — TPMS section payload for /sse/slow.
#
# Always emits four rows in deterministic FD/FP/RD/RP order so Alpine's
# x-for never sees rearrangements (28-RESEARCH.md Pitfall 4 — :key on
# row.position prevents flicker).
_TPMS_LABELS: Dict[str, str] = {
    "front-driver": "FD",
    "front-passenger": "FP",
    "rear-driver": "RD",
    "rear-passenger": "RP",
}


def _tpms_payload() -> List[Dict[str, Any]]:
    """Render four TPMS wheel slots for /sse/slow.

    State machine (matches TPMSService.snapshot() output):
      no_data  → never seen a frame
      ok       → PSI > yellow threshold (default 28)
      low      → yellow threshold ≥ PSI > red threshold (default 25)
      critical → PSI ≤ red threshold OR active leak alert
      stale    → no frame for stale_timeout (default 5 min)

    `since_ms` is millis since the wheel's last_seen_monotonic for any
    state other than no_data, where it is None. The frontend renders
    this as "3s ago" using sinceText().

    When `tpms_service` is unset (engine never registered or
    config.tpms.enabled=false), four no_data rows are emitted so the
    frontend always has a complete grid.
    """
    snap: Dict[str, Dict[str, Any]] = (
        tpms_service.snapshot() if tpms_service is not None else {}
    )
    out: List[Dict[str, Any]] = []
    for position in WHEEL_POSITIONS:
        st = snap.get(position) or {}
        out.append({
            "label": _TPMS_LABELS[position],
            "position": position,
            "psi": st.get("psi"),
            "state": st.get("state", "no_data"),
            "since_ms": st.get("since_ms"),
        })
    return out


def push_event(event: Dict[str, Any]) -> None:
    """Broadcast a freshly-detected event to all connected /sse/events clients.

    Each client has its own queue; we put_nowait on all of them so a stale
    generator from a prior reconnect cannot consume the event before the live
    connection sees it. Drop on full per client — never block the capture path.
    """
    with _event_listeners_lock:
        for q in _event_listeners:
            try:
                q.put_nowait(event)
            except queue.Full:
                log.warning("dashboard_event_queue_full", dropped=event.get("type"))


def _check_capacity() -> None:
    """Raise HTTP 503 if already at MAX_CLIENTS, otherwise increment counter."""
    global _active_clients
    with _clients_lock:
        if _active_clients >= MAX_CLIENTS:
            raise HTTPException(status_code=503, detail="dashboard at capacity")
        _active_clients += 1


def _release_slot() -> None:
    """Decrement the active client counter."""
    global _active_clients
    with _clients_lock:
        _active_clients = max(0, _active_clients - 1)


@router.get("/sse/fast")
async def sse_fast(request: Request) -> Response:
    _check_capacity()

    async def gen() -> AsyncIterator[Dict[str, Any]]:
        try:
            while True:
                snap = read_snapshot()
                yield {
                    "event": "fast",
                    "data": json.dumps(
                        {
                            "ts": snap["ts"],
                            "speed": snap["speed_kmh"],
                            "gx": snap["g_x"],
                            "gy": snap["g_y"],
                            "gz": snap["g_z"],
                            "heading": snap["heading_deg"],
                        },
                        default=str,
                    ),
                }
                await asyncio.sleep(1.0 / FAST_HZ)
        finally:
            _release_slot()

    return EventSourceResponse(gen())


@router.get("/sse/slow")
async def sse_slow(request: Request) -> Response:
    _check_capacity()

    async def gen() -> AsyncIterator[Dict[str, Any]]:
        try:
            while True:
                snap = read_snapshot()
                yield {
                    "event": "slow",
                    "data": json.dumps(
                        {
                            "ts": snap["ts"],
                            "lat": snap["lat"],
                            "lng": snap["lng"],
                            "fix_mode": snap["gps_fix_mode"],
                            "sats": snap["gps_sat_count"],
                            "hdop": snap["gps_hdop"],
                            "imu_temp": snap["imu_temp_c"],
                            "soc_temp": snap["soc_temp_c"],
                            "sync_connected": snap["sync_connected"],
                            "sync_backlog": snap["sync_backlog"],
                            "event_count": snap["event_count_today"],
                            "active_driver": snap.get("active_driver"),
                            "recording_active": snap.get("recording_active", False),
                            "hardware": _hardware_payload(),
                            "system_conditions": _system_conditions_payload(),
                            "tpms": _tpms_payload(),
                        },
                        default=str,
                    ),
                }
                await asyncio.sleep(1.0 / SLOW_HZ)
        finally:
            _release_slot()

    return EventSourceResponse(gen())


@router.get("/sse/events")
async def sse_events(request: Request) -> Response:
    _check_capacity()

    async def gen() -> AsyncIterator[Dict[str, Any]]:
        my_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=256)
        with _event_listeners_lock:
            _event_listeners.append(my_queue)
        try:
            # Seed: last 10 events from the provider (wired by the engine)
            if _recent_provider is not None:
                try:
                    seed: List[Dict[str, Any]] = list(_recent_provider(10))
                except Exception as exc:
                    log.warning("dashboard_recent_provider_failed", error=str(exc))
                    seed = []
                # Yield oldest-first so the frontend's unshift() leaves
                # newest at the top of the list after the cap-and-pop cycle.
                for ev in reversed(seed):
                    yield {"event": "event", "data": json.dumps(ev, default=str)}
            # Live: drain this client's queue
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.to_thread(my_queue.get, True, 1.0)
                except queue.Empty:
                    continue
                yield {"event": "event", "data": json.dumps(ev, default=str)}
        finally:
            with _event_listeners_lock:
                _event_listeners.remove(my_queue)
            _release_slot()

    return EventSourceResponse(gen())
