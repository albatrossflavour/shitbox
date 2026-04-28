"""Unit + integration tests for ≥5 PSI / 60s leak detection.

SPEC-8 (rapid deflation → TPMS_LEAK event in events.json).
Bodies activated by Plan 28-04 once TPMSService landed.

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
    alerts.clear_state()
    yield
    alerts.clear_state()


def _import_tpms():
    """Import shitbox.sync.tpms or skip with an explicit Plan 28-04 marker."""
    try:
        import shitbox.sync.tpms as tpms
    except ImportError:
        pytest.skip("Plan 28-04 — leak detector lives in TPMSService")
    return tpms


def _make_service(tpms_module, *, event_storage=None):
    from shitbox.utils.config import TpmsConfig, TpmsSensorMapEntry

    cfg = TpmsConfig(
        enabled=True,
        sensors=[
            TpmsSensorMapEntry(id="550b57d9", position="front-driver"),
            TpmsSensorMapEntry(id="54d96e8f", position="front-passenger"),
            TpmsSensorMapEntry(id="550d14ed", position="rear-driver"),
            TpmsSensorMapEntry(id="550b5d8a", position="rear-passenger"),
        ],
    )
    db = MagicMock()
    db.insert_tpms_reading.return_value = 1
    if event_storage is None:
        event_storage = MagicMock()
        event_storage.save_event.return_value = ("/tmp/x.json", "/tmp/x.csv")
    return tpms_module.TPMSService(cfg, db, event_storage)


def test_leak_detected():
    """SPEC-8: PSI dropping ≥5 within 60s window returns True from _detect_leak."""
    tpms = _import_tpms()
    service = _make_service(tpms)

    # First: a 31 PSI baseline at t=0.
    assert service._detect_leak("front-driver", 31.0, now_mono=0.0) is False
    # Second: a 25 PSI reading at t=10s — drop of 6 PSI within window.
    assert service._detect_leak("front-driver", 25.0, now_mono=10.0) is True


def test_slow_deflation_no_leak():
    """SPEC-8: 1 PSI/min over 60s does NOT trigger leak detection (drop < 5)."""
    tpms = _import_tpms()
    service = _make_service(tpms)

    # Drop 1 PSI per 10s over 60s → max-min = 6, but most points are within
    # the window and the spread builds gradually. We simulate the case where
    # every step the *recent* spread stays just under the 5 PSI threshold.
    # Actually the deque sees ALL points in the window; with steady decline
    # max - latest = 5 PSI on the sixth frame, which IS ≥ 5 — so the spec
    # treats slow deflation that exceeds 5 PSI in a 60s window as a leak.
    # This test must therefore use a smaller drop: 0.5 PSI per 10s over 60s
    # (total drop within window = 3 PSI, well under threshold).
    psi = 31.0
    triggered = False
    for i in range(7):
        t = i * 10.0
        if service._detect_leak("front-driver", psi, now_mono=t):
            triggered = True
            break
        psi -= 0.5
    assert triggered is False


def test_leak_writes_event_json(tmp_path):
    """SPEC-8: a leak fire writes a TPMS_LEAK Event via EventStorage.save_event.

    Uses a real EventStorage with tmp dir to verify the JSON file actually
    lands on disk with the right type.
    """
    try:
        from shitbox.events.detector import EventType
    except ImportError:
        pytest.skip("Plan 28-02 — EventType.TPMS_LEAK not yet defined")
    if not hasattr(EventType, "TPMS_LEAK"):
        pytest.skip("Plan 28-02 — EventType.TPMS_LEAK enum value missing")

    tpms = _import_tpms()
    from shitbox.events.storage import EventStorage

    storage = EventStorage(base_dir=str(tmp_path / "events"))
    service = _make_service(tpms, event_storage=storage)

    # Drive a leak: baseline then large drop.
    service._handle_frame(_frame("550b57d9", 87.24, secs=10))  # ~31 PSI
    service._handle_frame(_frame("550b57d9", 67.54, secs=11))  # ~24 PSI (>5 PSI drop)

    # Find the JSON file written.
    json_files = list((tmp_path / "events").rglob("tpms_leak_*.json"))
    assert len(json_files) >= 1, f"no tpms_leak json under {tmp_path}"
    payload = json.loads(json_files[0].read_text())
    assert payload["type"] == "tpms_leak"


def _frame(sensor_id: str, kpa_raw: float, *, secs: int = 10) -> str:
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
