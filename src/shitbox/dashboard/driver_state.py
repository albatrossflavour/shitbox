"""Module-level active driver state.

Same pattern as gps_state.py: module-level Optional[str] with setter/getter.
CPython GIL makes string rebind atomic, so no lock is needed for reads in the
SSE stream, snapshot writer, or event recorder. Writes happen from the
FastAPI driver router thread after a successful DB write.
"""
from __future__ import annotations

from typing import Optional

_active_driver: Optional[str] = None


def set_active_driver(name: Optional[str]) -> None:
    global _active_driver
    _active_driver = name


def get_active_driver() -> Optional[str]:
    return _active_driver


def clear_active_driver() -> None:
    """Test helper only — resets module state between tests."""
    global _active_driver
    _active_driver = None
