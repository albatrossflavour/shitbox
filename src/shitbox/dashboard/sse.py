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
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse  # noqa: F401  # kept for API symmetry
from sse_starlette.sse import EventSourceResponse

from shitbox.dashboard.snapshot import read_snapshot

log = structlog.get_logger(__name__)

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
