"""Last-known GPS position helper. Module-level state, GIL-atomic rebind."""
from __future__ import annotations

import time
from typing import Optional, Tuple

_last: Optional[Tuple[float, float, float]] = None  # (lat, lng, fixed_at_epoch)


def update_last_known_position(lat: float, lng: float, fixed_at: Optional[float] = None) -> None:
    """Store the most recent valid GPS fix position.

    Safe to call from any thread — the module-level rebind is GIL-atomic.
    Silently ignores None lat/lng so callers can pass raw snapshot values
    without pre-checking.
    """
    global _last
    if lat is None or lng is None:
        return
    _last = (float(lat), float(lng), float(fixed_at if fixed_at is not None else time.time()))


def get_last_known_position() -> Optional[Tuple[float, float, float]]:
    """Return (lat, lng, fixed_at_epoch) or None if no position has ever been stored."""
    return _last


def clear_last_known_position() -> None:
    """Reset module state. Test helper only — do not call in production code."""
    global _last
    _last = None
