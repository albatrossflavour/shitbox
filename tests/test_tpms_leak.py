"""Unit + integration tests for ≥5 PSI / 60s leak detection.

SPEC-8 (rapid deflation → TPMS_LEAK event in events.json).
Wave 0 stubs — bodies activate when Plan 28-02 lands EventType.TPMS_LEAK and
Plan 28-04 lands the deque-based detector + engine wiring.

Per-test guards (not module-level importorskip) so `pytest --collect-only`
lists every behavioural test name in the must_haves artifact contract.
"""
from __future__ import annotations

import pytest


def _import_tpms():
    """Import shitbox.sync.tpms or skip with an explicit Plan 28-04 marker."""
    try:
        import shitbox.sync.tpms as tpms
    except ImportError:
        pytest.skip("Plan 28-04 — leak detector lives in TPMSService")
    return tpms


def test_leak_detected():
    """SPEC-8: PSI dropping ≥5 within 60s window returns True from _detect_leak."""
    _import_tpms()
    pytest.skip("Plan 28-04 — _detect_leak deque API not yet implemented")


def test_slow_deflation_no_leak():
    """SPEC-8: 1 PSI/min over 60s does NOT trigger leak detection."""
    _import_tpms()
    pytest.skip("Plan 28-04 — _detect_leak deque API not yet implemented")


def test_leak_writes_event_json(event_storage):
    """SPEC-8: a leak fire writes a TPMS_LEAK Event via EventStorage.save_event."""
    try:
        from shitbox.events.detector import EventType
    except ImportError:
        pytest.skip("Plan 28-02 — EventType.TPMS_LEAK not yet defined")
    if not hasattr(EventType, "TPMS_LEAK"):
        pytest.skip("Plan 28-02 — EventType.TPMS_LEAK enum value missing")
    pytest.skip("Plan 28-04 — engine wiring writes the event; integration lands then")
