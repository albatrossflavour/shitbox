"""Tests for EventStorage.generate_events_json() peak-axis copy-through.

Covers UAT gap 4 (phase 22-06): the website-facing events.json must honour the
additive per-axis peak fields emitted by Event.to_dict (peak_ax/ay/az plus the
phase 22-02 additions peak_gx/gy/gz).

Direct JSON write is used (not save_event) so the tests model the scenario the
generator sees on disk: a mixed bag of old and new event files, where older
entries may lack peak_gx/gy/gz entirely.
"""

from __future__ import annotations

import json

from shitbox.events.storage import EventStorage


def _write_event_json(storage: EventStorage, start_time: float, meta: dict) -> None:
    """Write a single event JSON file under the storage base_dir's day folder."""
    day_dir = storage._get_day_dir(start_time)
    (day_dir / f"event_{int(start_time * 1000)}.json").write_text(json.dumps(meta))


def test_generate_events_json_surfaces_peak_axes_when_present(tmp_path):
    """When source event carries peak_ax/ay/az/gx/gy/gz, index entry surfaces all six."""
    storage = EventStorage(
        base_dir=str(tmp_path / "events"),
        captures_dir=str(tmp_path / "captures"),
    )

    start_time = 1776800000.0  # some fixed epoch second
    meta = {
        "type": "rollover",
        "start_time": start_time,
        "end_time": start_time + 0.5,
        "peak_value": 350.2,
        "duration_ms": 500,
        "peak_ax": 0.12,
        "peak_ay": -0.34,
        "peak_az": 1.01,
        "peak_gx": 280.5,
        "peak_gy": -45.2,
        "peak_gz": 12.3,
        "sample_count": 52,
    }
    _write_event_json(storage, start_time, meta)

    events_json_path = storage.generate_events_json()
    assert events_json_path is not None

    entries = json.loads(events_json_path.read_text())
    assert len(entries) == 1
    entry = entries[0]

    assert entry["peak_ax"] == 0.12
    assert entry["peak_ay"] == -0.34
    assert entry["peak_az"] == 1.01
    assert entry["peak_gx"] == 280.5
    assert entry["peak_gy"] == -45.2
    assert entry["peak_gz"] == 12.3

    # Existing base-projection keys still present and unchanged in shape
    assert entry["type"] == "ROLLOVER"
    assert entry["peak_g"] == 350.2
    assert entry["duration_ms"] == 500


def test_generate_events_json_omits_peak_axes_when_absent(tmp_path):
    """When source event lacks per-axis peaks, no placeholder nulls appear in output."""
    storage = EventStorage(
        base_dir=str(tmp_path / "events"),
        captures_dir=str(tmp_path / "captures"),
    )

    start_time = 1776800100.0
    meta = {
        "type": "hard_brake",
        "start_time": start_time,
        "end_time": start_time + 0.3,
        "peak_value": -0.42,
        "duration_ms": 300,
        # Deliberately no peak_ax/ay/az or peak_gx/gy/gz
    }
    _write_event_json(storage, start_time, meta)

    events_json_path = storage.generate_events_json()
    assert events_json_path is not None

    entries = json.loads(events_json_path.read_text())
    assert len(entries) == 1
    entry = entries[0]

    for absent_key in ("peak_ax", "peak_ay", "peak_az", "peak_gx", "peak_gy", "peak_gz"):
        assert absent_key not in entry, (
            f"{absent_key} should not be present when source event lacks it "
            "(avoid placeholder-null regression)"
        )


def test_generate_events_json_preserves_zero_axis_readings(tmp_path):
    """A legitimate 0.0 reading still surfaces (guards against truthy-check regression)."""
    storage = EventStorage(
        base_dir=str(tmp_path / "events"),
        captures_dir=str(tmp_path / "captures"),
    )

    start_time = 1776800200.0
    meta = {
        "type": "big_corner",
        "start_time": start_time,
        "end_time": start_time + 0.4,
        "peak_value": 0.55,
        "duration_ms": 400,
        "peak_ax": 0.0,
        "peak_ay": 0.55,
        "peak_az": 0.0,
        "peak_gx": 0.0,
        "peak_gy": 0.0,
        "peak_gz": 80.0,
    }
    _write_event_json(storage, start_time, meta)

    events_json_path = storage.generate_events_json()
    assert events_json_path is not None

    entries = json.loads(events_json_path.read_text())
    assert len(entries) == 1
    entry = entries[0]

    assert entry["peak_ax"] == 0.0
    assert entry["peak_az"] == 0.0
    assert entry["peak_gx"] == 0.0
    assert entry["peak_gy"] == 0.0
    assert entry["peak_gz"] == 80.0
