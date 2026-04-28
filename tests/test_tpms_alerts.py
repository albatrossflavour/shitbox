"""Unit tests for TPMS sustain/transition/recovery + stale-sensor detection.

SPEC-7 (low-pressure 28/25 PSI alerts), SPEC-9 (5-minute stale timeout).
Wave 0 stubs — bodies activate when Plan 28-04 lands the alert wiring.

Per-test guards (not module-level importorskip) so `pytest --collect-only`
lists every behavioural test name in the must_haves artifact contract.
"""
from __future__ import annotations

import pytest

from shitbox.health import alerts


@pytest.fixture(autouse=True)
def _clear_alerts_state():
    """Reset module-level alerts state between tests (mirrors test_alerts.py:15-22)."""
    alerts.clear_state()
    yield
    alerts.clear_state()


def _import_tpms():
    """Import shitbox.sync.tpms or skip with an explicit Plan 28-04 marker."""
    try:
        import shitbox.sync.tpms as tpms
    except ImportError:
        pytest.skip("Plan 28-04 — TPMSService not yet implemented")
    return tpms


def test_low_pressure_red_fires(monkeypatch):
    """SPEC-7: PSI ≤ 25 sustained for sustain_required frames fires red TTS once."""
    _import_tpms()
    pytest.skip("Plan 28-04 — alert wiring lands with TPMSService._handle_frame")


def test_yellow_no_tts(monkeypatch):
    """SPEC-7: 25 < PSI ≤ 28 fires Health-page banner only, no TTS call."""
    _import_tpms()
    pytest.skip("Plan 28-04 — yellow state is a row colour, not a TTS event")


def test_low_pressure_restored(monkeypatch):
    """SPEC-7: re-inflation above 28 PSI emits the _RESTORED suffix once."""
    _import_tpms()
    pytest.skip("Plan 28-04 — fire_recovery wiring lands with the alert path")


def test_stale_after_5min(monkeypatch):
    """SPEC-9: time.monotonic advanced past stale_timeout flips wheel state to STALE.

    Pattern (Plan 28-04 implementation):
        monkeypatch.setattr("shitbox.sync.tpms.time.monotonic",
                            lambda: last_seen + 360.0)
        snap = service.snapshot()
        assert snap["front-driver"]["state"] == "stale"
    """
    _import_tpms()
    pytest.skip("Plan 28-04 — TPMSService.snapshot() not yet implemented")


def test_stale_clears(monkeypatch):
    """SPEC-9: a fresh frame after STALE flips state back to ok/low/critical."""
    _import_tpms()
    pytest.skip("Plan 28-04 — TPMSService.snapshot() not yet implemented")
