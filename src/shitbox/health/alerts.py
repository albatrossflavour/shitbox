"""Alert sustain + transition helper. Module-level, single-writer-per-subtype.

Owned subtypes per Phase 15: UNDERVOLTAGE, UNDERVOLTAGE_CLEARED,
CAPTURE_FAILURE, CAPTURE_RESTORED, CAPTURE_DOWN. Callers provide the
subtype, active boolean, overlay message, and an optional TTS callable;
the helper owns sustain counting and once-on-transition + once-on-recovery
emission semantics.

Concurrency contract: each subtype must have a single writer thread. The
read-modify-write sequence inside fire_alert / fire_recovery is NOT atomic
under the GIL — only the final dict rebind is. Two threads writing the same
subtype concurrently can lose updates. Today the wiring is single-writer:
thermal_monitor owns UNDERVOLTAGE; ring_buffer owns CAPTURE_*. Add a lock if
that ever changes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Graceful-degradation import per D-11 / RESEARCH Pattern 2.
# Keeps the helper importable from unit tests without the dashboard subsystem
# booted and honours Phase 21 D-04 "never refuse boot".
try:
    from shitbox.dashboard.sse import push_event as dashboard_push_event
except ImportError:
    def dashboard_push_event(event: Dict[str, Any]) -> None:  # type: ignore[misc]
        pass


@dataclass(frozen=True, slots=True)  # type: ignore[call-overload]
class AlertStatus:
    """Immutable snapshot of a single alert subtype's sustain + transition state."""

    subtype: str
    active: bool              # True once alert has sustained; False once recovery has sustained
    fired: bool               # has fire_alert emitted for this active run?
    active_sustain_count: int  # consecutive active=True observations since last reset
    clear_sustain_count: int  # consecutive active=False observations since last reset
    last_change_ts: float     # time.time() of last state transition (0.0 if never)


_NEW = AlertStatus(
    subtype="",
    active=False,
    fired=False,
    active_sustain_count=0,
    clear_sustain_count=0,
    last_change_ts=0.0,
)


# Single source of truth. Final rebind is GIL-atomic; the read-modify-write
# in fire_alert / fire_recovery is not — see module docstring.
_state: Dict[str, AlertStatus] = {}


def _rebind(subtype: str, new_status: AlertStatus) -> None:
    """Rebind module-level dict. Final assignment is GIL-atomic; callers
    must hold the single-writer-per-subtype invariant (see module docstring)."""
    global _state
    new_map = dict(_state)
    new_map[subtype] = new_status
    _state = new_map


def _get_or_init(subtype: str) -> AlertStatus:
    existing = _state.get(subtype)
    if existing is None:
        return replace(_NEW, subtype=subtype)
    return existing


def fire_alert(
    subtype: str,
    active: bool,
    message: str,
    tts_fn: Optional[Callable[[], None]] = None,
    sustain_required: int = 2,
) -> None:
    """Observe the current active state for ``subtype``. Emit ALERT exactly once
    on transition from "not sustained" to "sustained active", gated by
    ``sustain_required`` consecutive observations of ``active=True``.

    Callers call this every cycle with the current active boolean; the helper
    owns the state machine. ``tts_fn=None`` is a no-op (Phase 21 D-04 — alerts
    never refuse to fire when TTS is absent). Never raises.
    """
    try:
        prev = _get_or_init(subtype)
        now = time.time()
        if active:
            new_active_count = prev.active_sustain_count + 1
            should_fire = (not prev.fired) and new_active_count >= sustain_required
            if should_fire:
                new_status = AlertStatus(
                    subtype=subtype,
                    active=True,
                    fired=True,
                    active_sustain_count=new_active_count,
                    clear_sustain_count=0,
                    last_change_ts=now,
                )
                _rebind(subtype, new_status)
                _emit_alert(subtype, message, now)
                _safe_tts(tts_fn)
                log.info(
                    "alert_fired",
                    subtype=subtype,
                    sustain_reads=new_active_count,
                )
            else:
                _rebind(
                    subtype,
                    replace(
                        prev,
                        active_sustain_count=new_active_count,
                        clear_sustain_count=0,
                    ),
                )
        else:
            # active=False observed; reset the active-sustain counter.
            # Do NOT emit recovery here — fire_recovery owns that edge.
            if prev.active_sustain_count != 0:
                _rebind(
                    subtype,
                    replace(prev, active_sustain_count=0),
                )
    except Exception:  # noqa: BLE001 — never let alerts crash the caller
        log.exception("fire_alert_failed", subtype=subtype)


def fire_recovery(
    subtype: str,
    active: bool,
    message: str,
    tts_fn: Optional[Callable[[], None]] = None,
    sustain_required: int = 2,
    recovery_subtype: Optional[str] = None,
) -> None:
    """Observe the current active state for ``subtype``. Emit a recovery ALERT
    exactly once when ``fired=True`` and ``active=False`` has sustained for
    ``sustain_required`` consecutive observations.

    Bookkeeping is keyed on ``subtype`` (matching the fire_alert key). The
    emitted ALERT payload carries ``recovery_subtype`` if provided (e.g.
    ``"UNDERVOLTAGE_CLEARED"``), else falls back to ``subtype``. The frontend
    branches on the ``_CLEARED``/``_RESTORED`` suffix so the right subtype
    string must reach the event payload for the green branch.

    ``tts_fn=None`` is a no-op. Never raises.
    """
    try:
        prev = _get_or_init(subtype)
        if not prev.fired:
            # Nothing to recover from.
            return
        now = time.time()
        if not active:
            new_clear_count = prev.clear_sustain_count + 1
            if new_clear_count >= sustain_required:
                cleared = AlertStatus(
                    subtype=subtype,
                    active=False,
                    fired=False,
                    active_sustain_count=0,
                    clear_sustain_count=0,
                    last_change_ts=now,
                )
                _rebind(subtype, cleared)
                _emit_alert(recovery_subtype or subtype, message, now)
                _safe_tts(tts_fn)
                log.info(
                    "alert_recovered",
                    subtype=subtype,
                    emitted_subtype=recovery_subtype or subtype,
                    held_ms=(
                        int((now - prev.last_change_ts) * 1000)
                        if prev.last_change_ts
                        else 0
                    ),
                )
            else:
                _rebind(
                    subtype,
                    replace(prev, clear_sustain_count=new_clear_count),
                )
        else:
            # Still active; reset clear-sustain counter.
            if prev.clear_sustain_count != 0:
                _rebind(
                    subtype,
                    replace(prev, clear_sustain_count=0),
                )
    except Exception:  # noqa: BLE001
        log.exception("fire_recovery_failed", subtype=subtype)


def _emit_alert(subtype: str, message: str, ts: float) -> None:
    """Shape-locked dashboard push. Mirrors thermal_monitor.py:311-316."""
    dashboard_push_event(
        {
            "type": "ALERT",
            "subtype": subtype,
            "message": message,
            "ts": ts,
        }
    )


def _safe_tts(tts_fn: Optional[Callable[[], None]]) -> None:
    """Never let a broken or absent TTS path raise into the caller (Phase 21 D-04)."""
    if tts_fn is None:
        return
    try:
        tts_fn()
    except Exception:  # noqa: BLE001
        log.exception("alert_tts_failed")


def snapshot() -> Dict[str, AlertStatus]:
    """Return current state dict. Do not mutate — AlertStatus is frozen."""
    return _state


def clear_state() -> None:
    """Reset module state. TEST-ONLY helper — do not call in production code."""
    global _state
    _state = {}
