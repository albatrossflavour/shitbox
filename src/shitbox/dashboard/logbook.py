"""REST router for Phase 12 logbook: notes and fuel stops."""
from __future__ import annotations

import time
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shitbox.dashboard import gps_state
from shitbox.dashboard.snapshot import read_snapshot
from shitbox.storage.logbook import LogbookStorage

router = APIRouter()
_storage: Optional[LogbookStorage] = None
_sync_trigger: Optional[Callable[[], None]] = None


def set_storage(storage: LogbookStorage) -> None:
    """Register the LogbookStorage instance for this router.

    Called once by ``build_app()`` when ``logbook_storage`` is provided. The
    module-level rebind is GIL-atomic so no lock is needed.
    """
    global _storage
    _storage = storage


def set_sync_trigger(trigger: Callable[[], None]) -> None:
    """Register a callable to request an immediate capture sync after mutations."""
    global _sync_trigger
    _sync_trigger = trigger


def _require_storage() -> LogbookStorage:
    if _storage is None:
        raise HTTPException(status_code=503, detail="logbook storage not configured")
    return _storage


class NoteRequest(BaseModel):
    body: str = Field(..., min_length=1)
    event_id: Optional[int] = None


class FuelRequest(BaseModel):
    volume_litres: float = Field(..., gt=0)
    cost_aud: Optional[float] = Field(None, ge=0)
    odometer_km: Optional[float] = Field(None, ge=0)


@router.post("/api/notes", status_code=201)
def create_note(payload: NoteRequest) -> dict:
    """Create a new field note with GPS position captured at call time."""
    result = _require_storage().create_note(payload.body, payload.event_id)
    if _sync_trigger is not None:
        _sync_trigger()
    return result


@router.post("/api/fuel", status_code=201)
def create_fuel(payload: FuelRequest) -> dict:
    """Log a refuelling stop with volume, optional cost, and optional odometer."""
    result = _require_storage().create_fuel_stop(
        payload.volume_litres, payload.cost_aud, payload.odometer_km
    )
    if _sync_trigger is not None:
        _sync_trigger()
    return result


@router.get("/api/fuel")
def list_fuel() -> dict:
    """Return all fuel stops with per-stop and cumulative efficiency."""
    return _require_storage().list_fuel_stops()


@router.get("/api/logbook/gps")
def gps_status() -> dict:
    """Return current GPS staleness state for the note entry modal pre-flight check."""
    snap = read_snapshot()
    fix = snap.get("gps_fix_mode") or 0
    if fix > 0 and snap.get("lat") is not None:
        return {
            "has_fix": True,
            "gps_stale": False,
            "stale_seconds": 0,
            "lat": snap.get("lat"),
            "lng": snap.get("lng"),
        }
    last = gps_state.get_last_known_position()
    if last is None:
        return {
            "has_fix": False,
            "gps_stale": True,
            "stale_seconds": None,
            "lat": None,
            "lng": None,
        }
    lat, lng, fixed_at = last
    return {
        "has_fix": False,
        "gps_stale": True,
        "stale_seconds": int(time.time() - fixed_at),
        "lat": lat,
        "lng": lng,
    }
