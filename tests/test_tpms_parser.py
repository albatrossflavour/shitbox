"""Unit tests for shitbox.sync.tpms parser / correction / wheel-mapping helpers.

SPEC-1 (frame ingestion), SPEC-2 (× 2.45 correction), SPEC-3 (wheel mapping).
Wave 0 stubs — bodies activate when Plan 28-04 lands the production module.

Per-test guards (not module-level importorskip) so `pytest --collect-only`
lists every behavioural test name. The first thing each test does is import
shitbox.sync.tpms; if it does not exist the test skips with an explicit
Plan-28-NN reference. The moment Plan 28-04 lands the module these flip
to real pass/fail.
"""
from __future__ import annotations

import json

import pytest


def _import_tpms():
    """Import shitbox.sync.tpms or skip with an explicit Plan 28-04 marker."""
    try:
        import shitbox.sync.tpms as tpms
    except ImportError:
        pytest.skip("Plan 28-04 — shitbox.sync.tpms not yet implemented")
    return tpms


def test_valid_abarth_frame(fake_rtl433_frames):
    """SPEC-1: a well-formed Abarth-124 frame parses cleanly."""
    tpms = _import_tpms()
    raw = fake_rtl433_frames[0]  # front-driver
    parsed = tpms.parse_frame(raw)
    assert parsed is not None
    assert parsed["id"] == "550b57d9"
    assert parsed["pressure_kPa"] == pytest.approx(87.6, abs=0.1)


def test_unknown_sensor_drop(fake_rtl433_frames):
    """SPEC-3: sensor IDs not in the wheel map return None."""
    tpms = _import_tpms()
    sensor_map = {"550b57d9": "front-driver"}  # only one wheel mapped
    other = fake_rtl433_frames[1]  # 54d96e8f — not in this map
    sid = json.loads(other)["id"]
    assert tpms.lookup_wheel(sid, sensor_map) is None


def test_malformed_json_skipped():
    """SPEC-1: malformed JSON returns None instead of raising."""
    tpms = _import_tpms()
    assert tpms.parse_frame("not valid json {{{") is None
    assert tpms.parse_frame("") is None


def test_pressure_correction():
    """SPEC-2: × 2.45 correction applied to decoder kPa."""
    tpms = _import_tpms()
    # 87.6 kPa raw × 2.45 = 214.62 corrected kPa
    corrected = tpms.correct_pressure_kpa(87.6, factor=2.45)
    assert corrected == pytest.approx(214.62, abs=0.01)


def test_kpa_to_psi():
    """SPEC-2: kPa → PSI via 0.145038 multiplier."""
    tpms = _import_tpms()
    # 214.62 kPa × 0.145038 = 31.13 PSI
    psi = tpms.kpa_to_psi(214.62)
    assert psi == pytest.approx(31.13, abs=0.05)


def test_wheel_mapping():
    """SPEC-3: known sensor IDs resolve to canonical wheel positions."""
    tpms = _import_tpms()
    sensor_map = {
        "550b57d9": "front-driver",
        "54d96e8f": "front-passenger",
        "550d14ed": "rear-driver",
        "550b5d8a": "rear-passenger",
    }
    assert tpms.lookup_wheel("550b57d9", sensor_map) == "front-driver"
    assert tpms.lookup_wheel("54D96E8F", sensor_map) == "front-passenger"  # case-insensitive
    assert tpms.lookup_wheel("deadbeef", sensor_map) is None
