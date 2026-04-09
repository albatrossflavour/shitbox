"""FastAPI router for driver tracking (Phase 13)."""
from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shitbox.storage.driver import DriverStorage

log = structlog.get_logger(__name__)
router = APIRouter()

_storage: Optional[DriverStorage] = None
_drivers_roster: List[str] = []


def set_storage(storage: DriverStorage) -> None:
    global _storage
    _storage = storage


def set_drivers_roster(drivers: List[str]) -> None:
    global _drivers_roster
    _drivers_roster = list(drivers)


def _require_storage() -> DriverStorage:
    if _storage is None:
        raise HTTPException(status_code=503, detail="driver storage not available")
    return _storage


class DriverRequest(BaseModel):
    name: str = Field(..., min_length=0, max_length=64)


@router.post("/api/driver", status_code=200)
def set_driver(payload: DriverRequest) -> dict:
    storage = _require_storage()
    name = payload.name.strip()
    if name == "":
        # Empty name = clear driver (crew break)
        storage.clear_driver()
        return {"driver_name": None, "started_at": None}
    if _drivers_roster and name not in _drivers_roster:
        raise HTTPException(
            status_code=422,
            detail=f"driver '{name}' not in roster {_drivers_roster}",
        )
    return storage.set_driver(name)


@router.get("/api/driver/stats")
def get_driver_stats() -> dict:
    storage = _require_storage()
    from shitbox.dashboard import driver_state
    return {
        "active_driver": driver_state.get_active_driver(),
        "drivers": storage.get_stats(),
        "roster": _drivers_roster,
    }
