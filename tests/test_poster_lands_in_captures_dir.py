"""Phase 26 gap-closure (plan 26-08, G-07) — poster PNG must land in captures_dir.

On-device evidence (Pi, 2026-04-23):
  /var/lib/shitbox/events/2026-04-23/boot_092336_001_poster.png    [58KB]
  /var/lib/shitbox/captures/2026-04-23/                            [MP4s only]

The rsync in capture_sync.py only ships `captures_dir/` to the NAS (`events_dir/`
holds JSON + CSV which are Pi-local). When the engine renamed the slate PNG next
to the JSON (`events_dir/<date>/<base>_poster.png`) the PNG stayed on the Pi
forever. events.json's `poster_url` was still shaped `/captures/<date>/...`
(built from filename alone), so browsers got a 404 on every event.

The G-01 + G-06 tests passed because the harness reused a single tmp_path for
both events_dir and captures_dir; `day_dirs = [d for d in events_dir.iterdir()]`
happened to see the PNG because the two dirs overlapped. This file pins the
two dirs to separate paths so the bug is observable in-test.

Fix: both the EARLY save branch and the LATE update branch move the PNG into
the captures day dir (alongside the MP4) so rsync will pick it up.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from shitbox.capture.ring_buffer import VideoRingBuffer
from shitbox.events.detector import Event, EventType
from shitbox.events.storage import EventStorage


def _make_event(event_type: EventType = EventType.HARD_BRAKE) -> Event:
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
    """Key difference vs the G-01/G-06 test harnesses: captures_dir and events_dir
    are SEPARATE subtrees. Mirrors the real Pi layout (events/ holds JSON+CSV,
    captures/ is rsync'd to NAS with MP4 + poster PNG).
    """
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


def test_poster_lands_in_captures_dir_late_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LATE branch: _on_video_complete renames the PNG into captures_dir/<date>/,
    not events_dir/<date>/. Rsync only ships captures_dir to the NAS, so the
    events_dir-target of the pre-fix code stranded PNGs on the Pi.
    """
    from shitbox.dashboard import driver_state as ds

    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    vrb = _build_vrb_skeleton(tmp_path)
    engine, _storage, captures_dir, events_dir = _build_engine_skeleton(tmp_path, vrb)

    event = _make_event()
    eid = id(event)
    engine._pending_post_capture[eid] = {
        "event": event,
        "capture_until": time.monotonic() - 1.0,
        "video_path": None,
    }
    engine._check_post_captures()

    json_path = engine._event_json_paths[eid]

    vrb._save_counter = 1
    stable_png = vrb._pending_slates_dir / "1.png"
    stable_png.write_bytes(b"PNG-BYTES")
    mp4_path = tmp_path / "late_mp4.mp4"
    mp4_path.write_bytes(b"MP4-STUB")

    engine._on_video_complete(eid, mp4_path, stable_png)

    # PNG must be in captures_dir/<date>/ — the dir rsync ships to the NAS.
    captures_posters: list[Path] = []
    for d in captures_dir.iterdir():
        if d.is_dir():
            captures_posters.extend(d.glob("*_poster.png"))
    assert len(captures_posters) == 1, (
        f"Expected 1 poster under captures_dir, got {captures_posters}. "
        f"events_dir contents: {list(events_dir.rglob('*_poster.png'))}"
    )

    # Belt-and-braces: no poster stranded in events_dir where rsync won't find it.
    events_posters = list(events_dir.rglob("*_poster.png"))
    assert len(events_posters) == 0, (
        f"Poster stranded in events_dir (not rsync'd to NAS): {events_posters}"
    )

    # poster_path in the JSON must reflect the captures_dir location so
    # storage.generate_events_json() builds a URL that the NAS will serve.
    metadata = json.loads(json_path.read_text())
    poster_path_str = metadata["poster_path"]
    assert str(captures_dir) in poster_path_str, (
        f"Stored poster_path {poster_path_str!r} is not under captures_dir"
    )
    assert str(events_dir) not in poster_path_str, (
        f"Stored poster_path {poster_path_str!r} points into events_dir"
    )


def test_poster_lands_in_captures_dir_early_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EARLY branch: _check_post_captures renames the PNG into captures_dir/<date>/
    when the video stash has already been populated (fast path — _on_video_complete
    beat _check_post_captures to the mutex).
    """
    from shitbox.dashboard import driver_state as ds

    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    vrb = _build_vrb_skeleton(tmp_path)
    engine, _storage, captures_dir, events_dir = _build_engine_skeleton(tmp_path, vrb)

    event = _make_event()
    eid = id(event)

    vrb._save_counter = 1
    stable_png = vrb._pending_slates_dir / "1.png"
    stable_png.write_bytes(b"PNG-BYTES")

    real_mp4 = tmp_path / "real.mp4"
    real_mp4.write_bytes(b"MP4")
    with engine._event_paths_lock:
        engine._event_video_paths[eid] = real_mp4
        engine._event_poster_paths[eid] = stable_png

    engine._pending_post_capture[eid] = {
        "event": event,
        "capture_until": time.monotonic() - 1.0,
        "video_path": None,
    }
    engine._check_post_captures()

    captures_posters: list[Path] = []
    for d in captures_dir.iterdir():
        if d.is_dir():
            captures_posters.extend(d.glob("*_poster.png"))
    assert len(captures_posters) == 1, (
        f"Expected 1 poster under captures_dir, got {captures_posters}"
    )

    events_posters = list(events_dir.rglob("*_poster.png"))
    assert len(events_posters) == 0, (
        f"Poster stranded in events_dir: {events_posters}"
    )
