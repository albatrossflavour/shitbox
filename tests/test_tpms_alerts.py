"""Unit tests for TPMS sustain/transition/recovery + stale-sensor detection.

SPEC-7 (low-pressure 28/25 PSI alerts), SPEC-9 (5-minute stale timeout).
Bodies activated by Plan 28-04 when TPMSService._handle_frame landed.

Per-test guards (not module-level importorskip) so `pytest --collect-only`
lists every behavioural test name in the must_haves artifact contract.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

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


def _make_service(tpms_module, sustain_required: int = 2):
    """Build a TPMSService with mocked DB + EventStorage and the four
    bench-validated wheel mappings."""
    from shitbox.utils.config import TpmsConfig, TpmsSensorMapEntry

    cfg = TpmsConfig(
        enabled=True,
        sustain_required=sustain_required,
        sensors=[
            TpmsSensorMapEntry(id="550b57d9", position="front-driver"),
            TpmsSensorMapEntry(id="54d96e8f", position="front-passenger"),
            TpmsSensorMapEntry(id="550d14ed", position="rear-driver"),
            TpmsSensorMapEntry(id="550b5d8a", position="rear-passenger"),
        ],
    )
    db = MagicMock()
    db.insert_tpms_reading.return_value = 1
    event_storage = MagicMock()
    event_storage.save_event.return_value = ("/tmp/x.json", "/tmp/x.csv")
    return tpms_module.TPMSService(cfg, db, event_storage)


def _frame(sensor_id: str, kpa_raw: float, *, secs: int = 10) -> str:
    """Build an rtl_433 -F json frame string with the specified raw kPa."""
    return json.dumps(
        {
            "time": f"2026-04-28T12:34:{secs:02d}Z",
            "model": "Abarth-124Spider",
            "type": "TPMS",
            "id": sensor_id,
            "flags": "9300",
            "pressure_kPa": kpa_raw,
            "temperature_C": 22.5,
            "status": 19,
            "mic": "CHECKSUM",
        }
    )


# Pre-correction kPa values that produce specific PSI readings after
# the standard × 2.45 correction:
#   PSI = kPa_raw × 2.45 × 0.145038
#   kPa_raw = PSI / (2.45 × 0.145038) = PSI / 0.355343
KPA_FOR_31_PSI = 87.24  # 31.00 PSI corrected
KPA_FOR_24_PSI = 67.54  # 24.00 PSI corrected (red, ≤25)
KPA_FOR_27_PSI = 75.98  # 27.00 PSI corrected (yellow, 25 < PSI ≤ 28)
KPA_FOR_32_PSI = 90.05  # 32.00 PSI corrected (recovered, > 28)


def test_low_pressure_red_fires(monkeypatch):
    """SPEC-7: PSI ≤ 25 sustained for sustain_required frames fires red TTS once."""
    tpms = _import_tpms()
    spoken = []
    monkeypatch.setattr(
        tpms, "speak_tpms_low", lambda position: spoken.append(("low", position))
    )
    service = _make_service(tpms, sustain_required=2)

    # Two consecutive frames at red (24 PSI) should fire exactly once.
    service._handle_frame(_frame("550b57d9", KPA_FOR_24_PSI, secs=10))
    service._handle_frame(_frame("550b57d9", KPA_FOR_24_PSI, secs=11))
    # Third frame at red — no second fire (alerts helper holds fired=True).
    service._handle_frame(_frame("550b57d9", KPA_FOR_24_PSI, secs=12))

    assert spoken == [("low", "front-driver")]
    snap = alerts.snapshot()
    assert "TPMS_LOW_FRONT_DRIVER" in snap
    assert snap["TPMS_LOW_FRONT_DRIVER"].fired is True


def test_yellow_no_tts(monkeypatch):
    """SPEC-7: 25 < PSI ≤ 28 fires Health-page banner only, no TTS call."""
    tpms = _import_tpms()
    spoken = []
    monkeypatch.setattr(
        tpms, "speak_tpms_low", lambda position: spoken.append(("low", position))
    )
    service = _make_service(tpms, sustain_required=2)

    # Five frames at yellow (27 PSI) — must never fire low TTS.
    for i in range(5):
        service._handle_frame(_frame("550b57d9", KPA_FOR_27_PSI, secs=10 + i))

    assert spoken == []
    snap = alerts.snapshot()
    # Subtype either absent or never fired.
    if "TPMS_LOW_FRONT_DRIVER" in snap:
        assert snap["TPMS_LOW_FRONT_DRIVER"].fired is False


def test_low_pressure_restored(monkeypatch):
    """SPEC-7: re-inflation above 28 PSI emits the _RESTORED suffix once."""
    tpms = _import_tpms()
    spoken = []
    monkeypatch.setattr(
        tpms, "speak_tpms_low", lambda position: spoken.append(("low", position))
    )
    monkeypatch.setattr(
        tpms,
        "speak_tpms_restored",
        lambda position: spoken.append(("restored", position)),
    )
    service = _make_service(tpms, sustain_required=2)

    # Fire low.
    service._handle_frame(_frame("550b57d9", KPA_FOR_24_PSI, secs=10))
    service._handle_frame(_frame("550b57d9", KPA_FOR_24_PSI, secs=11))
    assert ("low", "front-driver") in spoken

    # Re-inflate; recovery requires sustain_required=2 frames at not-red.
    service._handle_frame(_frame("550b57d9", KPA_FOR_32_PSI, secs=20))
    service._handle_frame(_frame("550b57d9", KPA_FOR_32_PSI, secs=21))

    assert ("restored", "front-driver") in spoken
    # The recovery_subtype the helper emits to the dashboard should be _RESTORED.
    # The subtype-key bookkeeping is on TPMS_LOW_FRONT_DRIVER; after recovery
    # it goes back to fired=False, active=False.
    snap = alerts.snapshot()
    assert snap["TPMS_LOW_FRONT_DRIVER"].fired is False
    assert snap["TPMS_LOW_FRONT_DRIVER"].active is False


def test_stale_after_5min(monkeypatch):
    """SPEC-9: time.monotonic advanced past stale_timeout flips wheel state to STALE."""
    tpms = _import_tpms()
    service = _make_service(tpms)

    # Land one frame at a known monotonic.
    monkeypatch.setattr(tpms.time, "monotonic", lambda: 1000.0)
    service._handle_frame(_frame("550b57d9", KPA_FOR_31_PSI, secs=10))

    # Advance monotonic past stale_timeout_seconds (default 300).
    monkeypatch.setattr(tpms.time, "monotonic", lambda: 1000.0 + 360.0)
    snap = service.snapshot()
    assert snap["front-driver"]["state"] == "stale"
    # Other (never-seen) wheels remain no_data.
    assert snap["rear-driver"]["state"] == "no_data"


def test_stale_clears(monkeypatch):
    """SPEC-9: a fresh frame after STALE flips state back to ok/low/critical."""
    tpms = _import_tpms()
    service = _make_service(tpms)

    monkeypatch.setattr(tpms.time, "monotonic", lambda: 1000.0)
    service._handle_frame(_frame("550b57d9", KPA_FOR_31_PSI, secs=10))

    # Advance past stale → confirm stale.
    monkeypatch.setattr(tpms.time, "monotonic", lambda: 1000.0 + 360.0)
    assert service.snapshot()["front-driver"]["state"] == "stale"

    # Fresh frame at the new monotonic — must clear stale (back to ok).
    service._handle_frame(_frame("550b57d9", KPA_FOR_31_PSI, secs=400))
    assert service.snapshot()["front-driver"]["state"] == "ok"
