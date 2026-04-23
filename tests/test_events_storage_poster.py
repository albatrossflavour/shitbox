"""Tests for Phase 26-04 Task 1: EventStorage poster_path / poster_url plumbing.

Covers:
  1. save_event persists poster_path to metadata JSON when provided
  2. save_event omits poster_path key when not provided
  3. generate_events_json emits poster_url when PNG exists on disk
  4. generate_events_json omits poster_url when PNG is missing (exists-guard)
  5. video_path and poster_path are independent — all four combinations work
  6. Task 3 add-on: base_name= override suppresses the internal counter bump

The tests mirror the shape of tests/test_driver.py::test_event_attribution —
real EventStorage against a tmp_path, round-trip the JSON, assert fields.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from shitbox.events.detector import Event, EventType
from shitbox.events.storage import EventStorage


def _make_event(event_type: EventType = EventType.HIGH_G) -> Event:
    now = time.time()
    return Event(
        event_type=event_type,
        start_time=now,
        end_time=now + 1.0,
        peak_value=2.5,
        peak_ax=2.5,
        peak_ay=0.1,
        peak_az=0.0,
    )


@pytest.fixture()
def storage(tmp_path: Path) -> EventStorage:
    return EventStorage(
        base_dir=str(tmp_path / "events"),
        captures_dir=str(tmp_path / "captures"),
    )


# ---------------------------------------------------------------------------
# save_event poster_path persistence
# ---------------------------------------------------------------------------


def test_save_event_with_poster_path_persists_field(
    storage: EventStorage, tmp_path: Path
) -> None:
    """save_event(..., poster_path=<Path>) writes 'poster_path' into metadata JSON."""
    event = _make_event()
    poster_png = tmp_path / "sample_poster.png"
    poster_png.write_bytes(b"\x89PNG\r\n\x1a\n")  # just enough to exist

    json_path, _ = storage.save_event(event, poster_path=poster_png)

    with open(json_path) as f:
        metadata = json.load(f)

    assert metadata.get("poster_path") == str(poster_png), (
        f"Expected poster_path={poster_png!s}, got {metadata.get('poster_path')!r}"
    )


def test_save_event_without_poster_path_omits_field(storage: EventStorage) -> None:
    """save_event() with no poster_path does not emit a 'poster_path' key."""
    event = _make_event()

    json_path, _ = storage.save_event(event)

    with open(json_path) as f:
        metadata = json.load(f)

    assert "poster_path" not in metadata, (
        f"Expected poster_path absent, got: {metadata.get('poster_path')!r}"
    )


# ---------------------------------------------------------------------------
# generate_events_json poster_url emission
# ---------------------------------------------------------------------------


def test_generate_events_json_emits_poster_url_when_exists(
    storage: EventStorage,
) -> None:
    """When poster_path exists on disk, feed entry gains poster_url of the video_url shape."""
    event = _make_event()
    # save_event writes into storage.base_dir/<YYYY-MM-DD>/... — put the poster
    # in that same day dir so generate_events_json's exists-check passes.
    day_dir = storage._get_day_dir(event.start_time)
    poster_png = day_dir / "high_g_000000_001_poster.png"
    day_dir.mkdir(parents=True, exist_ok=True)
    poster_png.write_bytes(b"\x89PNG\r\n\x1a\n")

    storage.save_event(event, poster_path=poster_png)
    feed_path = storage.generate_events_json()

    assert feed_path is not None
    with open(feed_path) as f:
        entries = json.load(f)

    assert len(entries) == 1
    entry = entries[0]
    assert "poster_url" in entry, f"Expected poster_url in entry, got keys: {list(entry)}"
    assert entry["poster_url"] == f"/captures/{day_dir.name}/{poster_png.name}"


def test_generate_events_json_omits_poster_url_when_missing(
    storage: EventStorage, tmp_path: Path
) -> None:
    """When poster_path points at a missing file, feed entry omits poster_url."""
    event = _make_event()
    # Path references a PNG that will not exist by the time generate_events_json fires.
    dangling_png = tmp_path / "never_created_poster.png"

    storage.save_event(event, poster_path=dangling_png)
    feed_path = storage.generate_events_json()

    assert feed_path is not None
    with open(feed_path) as f:
        entries = json.load(f)

    assert len(entries) == 1
    entry = entries[0]
    assert "poster_url" not in entry, (
        f"Expected poster_url absent when file missing, got: {entry.get('poster_url')!r}"
    )


# ---------------------------------------------------------------------------
# video_path + poster_path independence
# ---------------------------------------------------------------------------


def test_save_event_video_and_poster_independent(
    storage: EventStorage, tmp_path: Path
) -> None:
    """Every combination of (video_path, poster_path) persists correctly.

    Four sub-cases: neither, video only, poster only, both.
    """
    cases = [
        ("neither", None, None),
        ("video_only", tmp_path / "video_only.mp4", None),
        ("poster_only", None, tmp_path / "poster_only.png"),
        ("both", tmp_path / "both.mp4", tmp_path / "both.png"),
    ]

    for label, video_path, poster_path in cases:
        event = _make_event(EventType.HARD_BRAKE)
        # Bump start_time by a second per case so per-day filename counter differs.
        event.start_time += hash(label) % 1000
        event.end_time = event.start_time + 0.5

        json_path, _ = storage.save_event(
            event, video_path=video_path, poster_path=poster_path
        )
        with open(json_path) as f:
            metadata = json.load(f)

        if video_path is None:
            assert "video_path" not in metadata, f"[{label}] video_path should be absent"
        else:
            assert metadata.get("video_path") == str(video_path), f"[{label}] video_path mismatch"

        if poster_path is None:
            assert "poster_path" not in metadata, f"[{label}] poster_path should be absent"
        else:
            assert metadata.get("poster_path") == str(poster_path), (
                f"[{label}] poster_path mismatch"
            )


# ---------------------------------------------------------------------------
# base_name override (Task 3 add-on — counter stability)
# ---------------------------------------------------------------------------


def test_save_event_base_name_override(storage: EventStorage, tmp_path: Path) -> None:
    """Passing base_name= skips internal _generate_filename() and leaves the counter alone.

    This is the mitigation for T-26-04-06: engine pre-generates the base_name
    once (to construct the per-event poster PNG filename), then passes it into
    save_event so the counter is not bumped a second time.
    """
    event1 = _make_event()
    before = storage._event_counter

    # Pre-generate a base_name the way the engine will do it in Task 3.
    day_dir = storage._get_day_dir(event1.start_time)  # noqa: F841 — isolate fixture side-effects
    pre_generated = storage._generate_filename(event1)  # bumps counter by 1
    after_pre = storage._event_counter
    assert after_pre == before + 1

    # Now call save_event with that pre-generated base_name. The expected
    # behaviour is that save_event does NOT increment the counter a second
    # time (no double-bump) AND the returned json_path uses pre_generated.
    json_path, _ = storage.save_event(event1, base_name=pre_generated)
    after_save = storage._event_counter

    assert after_save == after_pre, (
        f"Counter should stay at {after_pre} when base_name= is passed, got {after_save}"
    )
    assert json_path.stem == pre_generated, (
        f"Expected json_path.stem={pre_generated!r}, got {json_path.stem!r}"
    )
