"""Lock-free shared snapshot for the live dashboard.

Single writer, many readers. The writer is the engine's high-rate sample
callback (running at ~10 Hz for dashboard updates — NOT the 100 Hz capture
path, which is sacred per D-02). Readers are the SSE streams and any health
probes.

Concurrency model: we rely on CPython's GIL-atomic dict rebind. ``update_snapshot``
replaces the module-level ``_snapshot`` reference in a single bytecode op
(``STORE_GLOBAL``), so a reader calling ``read_snapshot`` either sees the old
dict or the new one — never a half-built one. No locks, no copies on the read
path.

Do NOT mutate the returned dict in-place. Build a fresh dict in the writer and
call ``update_snapshot`` with it. If you need to update a subset of keys, start
from ``read_snapshot()`` and splat: ``update_snapshot({**read_snapshot(), 'speed_kmh': v})``.
"""

from __future__ import annotations

from typing import Any, Dict

# 19-key default contract. Any field the UI may read MUST be present here so
# consumers never hit KeyError during boot before the first writer tick.
_snapshot: Dict[str, Any] = {
    "ts": 0.0,
    "speed_kmh": 0.0,
    "g_x": 0.0,
    "g_y": 0.0,
    "g_z": 0.0,
    "heading_deg": 0.0,
    "lat": None,
    "lng": None,
    "gps_fix_mode": 0,
    "gps_sat_count": 0,
    "gps_hdop": None,
    "imu_temp_c": None,
    "soc_temp_c": None,
    "sync_connected": False,
    "sync_backlog": 0,
    "event_count_today": 0,
    "active_driver": None,
    "recording_active": False,
    # Wall-clock epoch-ms when the current capture's post-event footage window
    # ends, or None when idle / already past it. The kiosk counts down to this;
    # once recording_active is still True but this is None/past, footage is done
    # and the clip is concatenating ("Saving…"). Reflects the fixed footage
    # window only — it does NOT track the concat tail (unknown duration).
    "recording_ends_at": None,
}


def update_snapshot(new: Dict[str, Any]) -> None:
    """Atomically replace the shared snapshot.

    Sole legitimate caller is the engine's dashboard sample callback. Rebinding
    the module global is a single GIL-protected op, so readers observe the
    swap atomically.
    """
    global _snapshot
    _snapshot = new


def read_snapshot() -> Dict[str, Any]:
    """Return the current snapshot dict.

    Returned by reference — do NOT mutate. Readers should consume values
    immediately or copy what they need.
    """
    return _snapshot
