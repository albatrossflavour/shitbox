"""Phase 26 gap-closure (plan 26-07, G-06) — EARLY save branch symmetry with G-05.

Before G-06, `_check_post_captures` (EARLY save) fell back to
`_find_capture_video` type-scan when the video stash was empty. On this Pi the
video save takes longer than `post_event_seconds`, so the stash is empty when
save_event fires — type-scan then returned the PRIOR event's MP4 (most recent
of the same type). That stale path got stamped into the event JSON AND into
events.json (published to NAS/browsers) before `_on_video_complete` patched
it via event_id strict lookup ~90s later.

G-06 applies the symmetric G-05 treatment to the EARLY branch:
  (1) no type-scan fallback in EARLY — save with `video_path=None` and rely
      on the LATE branch to pair by event_id.
  (3) skip `generate_events_json` when `video_path is None` — defer the
      publish until the LATE branch has paired the real MP4. Prevents a
      race-window events.json from being served to browsers or cached at
      the NAS rsync level.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from shitbox.capture.ring_buffer import VideoRingBuffer
from shitbox.events.detector import Event, EventType
from shitbox.events.storage import EventStorage


def _make_event(event_type: EventType = EventType.MANUAL_CAPTURE) -> Event:
    now = time.time()
    return Event(
        event_type=event_type,
        start_time=now,
        end_time=now + 2.0,
        peak_value=1.0,
        peak_ax=0.0,
        peak_ay=0.0,
        peak_az=1.0,
        samples=[],
    )


def _build_vrb_skeleton(tmp_path: Path) -> VideoRingBuffer:
    vrb = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = tmp_path / "buffer"
    vrb.buffer_dir.mkdir(parents=True, exist_ok=True)
    vrb._pending_slates_dir = vrb.buffer_dir / "pending_slates"
    vrb._pending_slates_dir.mkdir(parents=True, exist_ok=True)
    vrb._process_start_time = time.time() - 3600.0
    vrb._save_counter = 0
    vrb._pending_slate_png = None
    vrb._pending_slate_ts = None
    vrb._pending_slate_duration = 0.0
    vrb._title_card_renderer = None
    vrb.post_event_seconds = 0
    vrb.segment_seconds = 5
    vrb.buffer_segments = 5
    vrb.overlay_path = None
    vrb.intro_video = ""
    vrb._intro_ts = None
    vrb._intro_duration_seconds = 0.0
    vrb._geocoder_fn = None
    vrb._active_driver_fn = None
    vrb._active_saves = 0
    vrb._lock = threading.Lock()
    vrb.fps = 10
    vrb.audio_device = ""
    vrb._audio_available = False
    vrb._ffmpeg_started_at = 0.0
    return vrb


def _build_engine_skeleton(
    tmp_path: Path, vrb: VideoRingBuffer
) -> tuple[Any, EventStorage, Path, Path]:
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    storage = EventStorage(
        base_dir=str(events_dir),
        captures_dir=str(captures_dir),
    )

    engine = SimpleNamespace()
    engine.event_storage = storage
    engine.video_ring_buffer = vrb
    engine._event_video_paths = {}
    engine._event_poster_paths = {}
    engine._event_json_paths = {}
    engine._event_paths_lock = threading.Lock()
    engine._pending_post_capture = {}
    engine._pending_lock = threading.Lock()
    engine.capture_sync = None
    engine.grafana = None
    engine.events_captured = 0
    engine.config = SimpleNamespace(
        uplink_enabled=False,
        events_dir=str(events_dir),
        captures_dir=str(captures_dir),
        detector=SimpleNamespace(post_event_seconds=0),
        capture_pre_seconds=0,
        capture_post_seconds=0,
    )
    engine.ring_buffer = SimpleNamespace(get_window=lambda s: [])

    from shitbox.events.engine import UnifiedEngine

    engine._on_video_complete = UnifiedEngine._on_video_complete.__get__(
        engine, SimpleNamespace
    )
    engine._post_grafana_annotation = UnifiedEngine._post_grafana_annotation.__get__(
        engine, SimpleNamespace
    )
    engine._annotated_event_ids = set()
    engine._check_post_captures = UnifiedEngine._check_post_captures.__get__(
        engine, SimpleNamespace
    )
    engine._find_capture_video = lambda event: None

    return engine, storage, captures_dir, events_dir


def test_early_save_refuses_type_scan_and_defers_events_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G-06 RED test.

    EARLY save must:
      (1) NOT consult `_find_capture_video` when the video stash is empty;
          otherwise it stamps the prior event's MP4 into the JSON.
      (3) NOT regenerate `events.json` when `video_path` is None; otherwise
          the race-window events.json is published to NAS/browsers and can
          be cached past the LATE branch's corrective regen.

    LATE branch (`_on_video_complete`) subsequently pairs the real MP4 via
    event_id strict lookup and does regenerate events.json.
    """
    from shitbox.dashboard import driver_state as ds

    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    vrb = _build_vrb_skeleton(tmp_path)
    engine, storage, captures_dir, _events_dir = _build_engine_skeleton(tmp_path, vrb)

    # If EARLY branch still calls type-scan, it would return this stale path.
    prior_mp4 = tmp_path / "prior_event.mp4"
    prior_mp4.write_bytes(b"STALE")
    type_scan_spy = MagicMock(return_value=prior_mp4)
    engine._find_capture_video = type_scan_spy

    gen_spy = MagicMock(wraps=storage.generate_events_json)
    storage.generate_events_json = gen_spy

    event = _make_event(EventType.MANUAL_CAPTURE)
    eid = id(event)
    engine._pending_post_capture[eid] = {
        "event": event,
        "capture_until": time.monotonic() - 1.0,
        "video_path": None,
    }

    engine._check_post_captures()

    # (1) Type-scan refused.
    type_scan_spy.assert_not_called()

    # Event JSON still saved to disk (persistence path unaffected).
    assert engine.events_captured == 1
    assert eid in engine._event_json_paths
    json_path = engine._event_json_paths[eid]
    assert json_path.exists()

    # No stale video_path in the JSON.
    metadata = json.loads(json_path.read_text())
    assert not metadata.get("video_path"), (
        f"Stale video_path leaked into JSON: {metadata.get('video_path')!r}"
    )

    # (3) events.json NOT regenerated during the race window.
    gen_spy.assert_not_called()
    events_json = captures_dir / "events.json"
    assert not events_json.exists(), (
        "events.json was published during the save→video-complete race "
        "window; browsers/NAS may cache a stale or no-video entry."
    )

    # LATE branch fires with the real MP4 — events.json is regenerated now,
    # and JSON carries the correct video_path.
    real_mp4 = tmp_path / "real_event.mp4"
    real_mp4.write_bytes(b"REAL")
    engine._on_video_complete(eid, real_mp4, None)

    assert gen_spy.call_count == 1
    assert events_json.exists()

    metadata = json.loads(json_path.read_text())
    assert metadata["video_path"] == str(real_mp4)


def test_early_save_with_stash_populated_still_publishes_events_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G-06 guard: when video IS available at save time (fast Pi / small clip),
    the EARLY branch saves with the real video_path AND regenerates events.json
    — i.e. the deferred-publish path is gated on `video_path is None`, not on
    "always skip". Prevents a regression where fast paths would also defer.
    """
    from shitbox.dashboard import driver_state as ds

    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    vrb = _build_vrb_skeleton(tmp_path)
    engine, storage, captures_dir, _events_dir = _build_engine_skeleton(tmp_path, vrb)

    gen_spy = MagicMock(wraps=storage.generate_events_json)
    storage.generate_events_json = gen_spy

    event = _make_event(EventType.MANUAL_CAPTURE)
    eid = id(event)

    # Simulate: _on_video_complete fired BEFORE _check_post_captures,
    # stashing the real MP4 keyed by event_id.
    real_mp4 = tmp_path / "real_event.mp4"
    real_mp4.write_bytes(b"REAL")
    with engine._event_paths_lock:
        engine._event_video_paths[eid] = real_mp4

    engine._pending_post_capture[eid] = {
        "event": event,
        "capture_until": time.monotonic() - 1.0,
        "video_path": None,
    }

    engine._check_post_captures()

    # Stash was consumed, JSON has the real video_path.
    json_path = engine._event_json_paths[eid]
    metadata = json.loads(json_path.read_text())
    assert metadata["video_path"] == str(real_mp4)

    # events.json regenerated on the EARLY save (video_path was non-None).
    gen_spy.assert_called_once()
    events_json = captures_dir / "events.json"
    assert events_json.exists()
