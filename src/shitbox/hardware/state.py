"""Central hardware presence state. Module-level, GIL-atomic rebind.

Safe to call from any thread — the module-level rebind is GIL-atomic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class DeviceState(str, Enum):
    PRESENT = "present"
    DEGRADED = "degraded"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)  # type: ignore[call-overload]
class DeviceStatus:
    """Immutable snapshot of a single device's current presence state."""

    role: str
    tier: str                  # "critical" | "important" | "best_effort"
    state: DeviceState
    last_seen: float           # time.time() of last successful read; 0.0 if never
    since_monotonic: float     # time.monotonic() when current state began
    next_retry_at: float       # time.monotonic(); 0.0 = not scheduled
    consecutive_misses: int


# Single source of truth. Rebinding is GIL-atomic.
_state: Dict[str, DeviceStatus] = {}

# Backoff ladder: indexed by consecutive_misses (1-based, clamped to len).
_BACKOFF_LADDER_SECONDS: list[float] = [5.0, 15.0, 60.0, 300.0]


def initialise(devices: Dict[str, str]) -> None:
    """Seed the state table. devices: {role: tier}. Called once at boot
    from HardwareSupervisor before any probes run.

    Safe to call from any thread — the module-level rebind is GIL-atomic.
    """
    global _state
    now = time.monotonic()
    _state = {
        role: DeviceStatus(
            role=role,
            tier=tier,
            state=DeviceState.MISSING,
            last_seen=0.0,
            since_monotonic=now,
            next_retry_at=0.0,
            consecutive_misses=0,
        )
        for role, tier in devices.items()
    }
    log.info("hw_state_initialised", devices=len(devices))


def report_present(role: str) -> Optional[DeviceState]:
    """Mark device PRESENT. Returns previous state for transition detection.

    Safe to call from any thread — the module-level rebind is GIL-atomic.
    """
    global _state
    prev = _state.get(role)
    if prev is None:
        return None
    now_wall = time.time()
    now_mono = time.monotonic()
    new_map = dict(_state)
    new_map[role] = DeviceStatus(
        role=role,
        tier=prev.tier,
        state=DeviceState.PRESENT,
        last_seen=now_wall,
        since_monotonic=now_mono if prev.state != DeviceState.PRESENT else prev.since_monotonic,
        next_retry_at=0.0,
        consecutive_misses=0,
    )
    _state = new_map
    if prev.state != DeviceState.PRESENT:
        log.info("hw_state_transition", role=role, prev=prev.state.value, new="present")
    return prev.state


def report_missing(role: str) -> Optional[DeviceState]:
    """Mark device MISSING and schedule next retry via backoff ladder.

    Safe to call from any thread — the module-level rebind is GIL-atomic.
    """
    global _state
    prev = _state.get(role)
    if prev is None:
        return None
    consecutive = min(prev.consecutive_misses + 1, len(_BACKOFF_LADDER_SECONDS))
    wait = _BACKOFF_LADDER_SECONDS[consecutive - 1]
    now_mono = time.monotonic()
    new_map = dict(_state)
    new_map[role] = DeviceStatus(
        role=role,
        tier=prev.tier,
        state=DeviceState.MISSING,
        last_seen=prev.last_seen,
        since_monotonic=now_mono if prev.state != DeviceState.MISSING else prev.since_monotonic,
        next_retry_at=now_mono + wait,
        consecutive_misses=consecutive,
    )
    _state = new_map
    if prev.state != DeviceState.MISSING:
        log.info("hw_state_transition", role=role, prev=prev.state.value, new="missing")
    log.debug("hw_state_missing_rescheduled", role=role, misses=consecutive, wait_s=wait)
    return prev.state


def report_degraded(role: str) -> Optional[DeviceState]:
    """Mark device DEGRADED (in-recovery). Does not change next_retry_at or
    consecutive_misses.

    Safe to call from any thread — the module-level rebind is GIL-atomic.
    """
    global _state
    prev = _state.get(role)
    if prev is None:
        return None
    new_map = dict(_state)
    new_map[role] = DeviceStatus(
        role=role,
        tier=prev.tier,
        state=DeviceState.DEGRADED,
        last_seen=prev.last_seen,
        since_monotonic=(
            time.monotonic() if prev.state != DeviceState.DEGRADED else prev.since_monotonic
        ),
        next_retry_at=prev.next_retry_at,
        consecutive_misses=prev.consecutive_misses,
    )
    _state = new_map
    if prev.state != DeviceState.DEGRADED:
        log.info("hw_state_transition", role=role, prev=prev.state.value, new="degraded")
    return prev.state


def get_state(role: str) -> Optional[DeviceStatus]:
    """Return the current DeviceStatus for a role, or None if unknown."""
    return _state.get(role)


def snapshot() -> Dict[str, DeviceStatus]:
    """Return current state dict. Do not mutate — DeviceStatus is frozen."""
    return _state


def clear_state() -> None:
    """Reset module state. TEST-ONLY helper — do not call in production code."""
    global _state
    _state = {}
