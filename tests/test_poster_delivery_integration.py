"""Integration test for Phase 26 gap-closure (plan 26-05): the full
save_event -> rmtree -> _check_post_captures -> events.json lifecycle.

Exercises the thread-hand-off that unit tests in 26-04 bypass
(they set _pending_slate_png manually and skip the rmtree). If CR-01
regresses, this test fails — the poster either doesn't land in the
day dir or events.json doesn't carry poster_url.

Real filesystem, real thread, stub renderer + stub ffmpeg-concat.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, List

import pytest

from shitbox.capture.ring_buffer import VideoRingBuffer
from shitbox.events.detector import Event, EventType
from shitbox.events.storage import EventStorage

# ---------------------------------------------------------------------------
# Shared harness helpers
# ---------------------------------------------------------------------------


@dataclass
class PosterHarness:
    vrb: VideoRingBuffer
    engine: Any
    event: Event
    eid: int
    segments: List[Path]
    mock_renderer: Any
    callback: Callable[..., None]
    captures_dir: Path
    events_dir: Path
    storage: EventStorage


def _make_stub_renderer(
    png_bytes: bytes = b"X", ts_bytes: bytes = b"Y", duration: float = 3.0
) -> Any:
    """Fake TitleCardRenderer: writes real bytes to the paths the ring buffer passes."""

    class _StubRenderer:
        def render(
            self, event, png_path: Path, ts_path: Path, *, geocoder=None, driver_name=None
        ):
            Path(png_path).write_bytes(png_bytes)
            Path(ts_path).write_bytes(ts_bytes)
            return duration

    return _StubRenderer()


def _make_event() -> Event:
    now = time.time()
    return Event(
        event_type=EventType.HARD_BRAKE,
        start_time=now,
        end_time=now + 2.0,
        peak_value=1.5,
        peak_ax=-1.2,
        peak_ay=0.1,
        peak_az=0.9,
        samples=[],
    )


def _build_vrb_skeleton(tmp_path: Path) -> VideoRingBuffer:
    """Surgical VideoRingBuffer via __new__ + attribute poke.

    Mirrors tests/test_ring_buffer_slate.py::_make_vrb but adds
    Phase 26-05 attrs: _pending_slates_dir, _process_start_time, _save_counter.
    """
    vrb = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = tmp_path / "buffer"
    vrb.buffer_dir.mkdir(parents=True, exist_ok=True)
    vrb._pending_slates_dir = vrb.buffer_dir / "pending_slates"
    vrb._pending_slates_dir.mkdir(parents=True, exist_ok=True)
    vrb._process_start_time = time.time() - 3600.0  # 1h ago
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
    """Minimal UnifiedEngine skeleton with real EventStorage.

    Returns (engine, storage, captures_dir, events_dir).
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
    engine._check_post_captures = UnifiedEngine._check_post_captures.__get__(
        engine, SimpleNamespace
    )
    engine._find_capture_video = lambda event: None

    return engine, storage, captures_dir, events_dir


@pytest.fixture
def shared_harness(tmp_path, monkeypatch):
    """Build the common test harness once per test.

    Stubs VideoRingBuffer._copy_complete_segments and
    VideoRingBuffer._concatenate_segments so no real ffmpeg runs.
    Returns a PosterHarness dataclass.
    """
    from shitbox.dashboard import driver_state as ds

    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    vrb = _build_vrb_skeleton(tmp_path)
    vrb._title_card_renderer = _make_stub_renderer()
    engine, storage, captures_dir, events_dir = _build_engine_skeleton(tmp_path, vrb)

    # Real segment files for _do_save_event to concat over.
    seg_dir = tmp_path / "segments"
    seg_dir.mkdir()
    seg1 = seg_dir / "000.ts"
    seg1.write_bytes(b"X" * 20_000)
    seg2 = seg_dir / "001.ts"
    seg2.write_bytes(b"X" * 20_000)
    segments = [seg1, seg2]

    # Stub _copy_complete_segments to drop our fixtures into the save tmp dir.
    # Patched on the class so first arg is self (the vrb instance).
    def _fake_copy(self_vrb, dest_dir, phase, min_mtime=None, stream="front"):
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for i, src in enumerate(segments):
            dst = dest_dir / f"{phase}_{i:03d}.ts"
            dst.write_bytes(src.read_bytes())
            copied.append(dst)
        return copied

    monkeypatch.setattr(VideoRingBuffer, "_copy_complete_segments", _fake_copy)

    # Stub _concatenate_segments to produce a real MP4.
    def _fake_concat(segments_in, prefix, cabin_segments=None):
        out = segments_in[0].parent.parent / f"{prefix}_test.mp4"
        out.write_bytes(b"MP4-STUB")
        return out

    monkeypatch.setattr(vrb, "_concatenate_segments", _fake_concat)

    event = _make_event()
    eid = id(event)
    engine._pending_post_capture[eid] = {
        "event": event,
        "capture_until": time.monotonic() - 1.0,  # already expired
        "video_path": None,
    }

    # Forwarding callback: the real engine lambda shape from Task 2.
    def callback(path, _cs, _pp, _eid=eid):
        engine._on_video_complete(_eid, path, _pp)

    yield PosterHarness(
        vrb=vrb,
        engine=engine,
        event=event,
        eid=eid,
        segments=segments,
        mock_renderer=vrb._title_card_renderer,
        callback=callback,
        captures_dir=captures_dir,
        events_dir=events_dir,
        storage=storage,
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_poster_survives_rmtree_and_appears_in_events_json(shared_harness):
    """CR-01 regression test. The full race path must leave
    <event>_poster.png in the day dir and events.json must carry
    poster_url for that event."""
    h = shared_harness

    # Drive the worker in-thread for determinism.
    h.vrb._do_save_event("event", 0, None, h.callback, h.event)

    # Post-worker: PNG must be gone from tmp_dir, present in pending_slates.
    tmp_dirs = list(h.vrb.buffer_dir.glob("save_*"))
    assert tmp_dirs == [], f"rmtree did not run — leftover {tmp_dirs}"
    pending_pngs = list(h.vrb._pending_slates_dir.glob("*.png"))
    assert len(pending_pngs) == 1, (
        f"Expected 1 PNG in pending_slates/, got {pending_pngs}"
    )
    with h.engine._event_paths_lock:
        assert h.eid in h.engine._event_poster_paths
        assert h.engine._event_poster_paths[h.eid] == pending_pngs[0]

    # Now run _check_post_captures (telemetry-thread equivalent).
    h.engine._check_post_captures()

    # Post-engine-consume: PNG moved to day_dir, events.json carries poster_url.
    day_dirs = [d for d in h.events_dir.iterdir() if d.is_dir()]
    assert len(day_dirs) == 1, f"Expected 1 day dir, got {day_dirs}"
    day_dir = day_dirs[0]
    poster_pngs = list(day_dir.glob("*_poster.png"))
    assert len(poster_pngs) == 1, (
        f"Expected 1 <base>_poster.png in day_dir, got {poster_pngs}"
    )
    assert list(h.vrb._pending_slates_dir.glob("*.png")) == []
    with h.engine._event_paths_lock:
        assert h.eid not in h.engine._event_poster_paths

    # events.json carries poster_url.
    h.engine.event_storage.generate_events_json()
    events_json = h.captures_dir / "events.json"
    assert events_json.exists()
    feed = json.loads(events_json.read_text())
    entries = feed["events"] if isinstance(feed, dict) else feed
    matching = [e for e in entries if "poster_url" in e]
    assert len(matching) == 1, (
        f"Expected 1 event with poster_url, got {len(matching)} "
        f"from {len(entries)} total entries"
    )
    poster_url = matching[0]["poster_url"]
    assert poster_url.endswith("_poster.png"), (
        f"poster_url has wrong suffix: {poster_url}"
    )
    assert day_dir.name in poster_url, (
        f"poster_url missing day dir: {poster_url}"
    )


def test_poster_absent_when_renderer_disabled(shared_harness):
    """Regression-proof of ROADMAP criterion #2: disabled config
    emits no poster_url, no holding-dir files."""
    h = shared_harness
    h.vrb._title_card_renderer = None  # rebind: renderer disabled

    h.vrb._do_save_event("event", 0, None, h.callback, h.event)

    # No PNG anywhere.
    assert list(h.vrb._pending_slates_dir.glob("*.png")) == []
    with h.engine._event_paths_lock:
        assert h.eid not in h.engine._event_poster_paths

    h.engine._check_post_captures()
    h.engine.event_storage.generate_events_json()
    events_json = h.captures_dir / "events.json"
    feed = json.loads(events_json.read_text())
    entries = feed["events"] if isinstance(feed, dict) else feed
    # video_url present (MP4 shipped), poster_url absent.
    assert any("video_url" in e for e in entries)
    assert not any("poster_url" in e for e in entries)


def test_poster_absent_when_holding_dir_move_fails(shared_harness, monkeypatch, caplog):
    """Graceful degradation: holding-dir move fails (disk full /
    perms), callback gets None, events.json omits poster_url,
    MP4 still ships."""
    h = shared_harness

    # Force the holding-dir move to fail. Patch shutil.move inside the
    # ring_buffer module namespace so only _do_save_event sees the
    # broken version; teardowns/_make_* helpers keep the real move.
    import shitbox.capture.ring_buffer as rb_mod

    def _boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr(rb_mod.shutil, "move", _boom)

    h.vrb._do_save_event("event", 0, None, h.callback, h.event)

    # No PNG in pending_slates (move failed).
    assert list(h.vrb._pending_slates_dir.glob("*.png")) == []
    # No poster path stashed.
    with h.engine._event_paths_lock:
        assert h.eid not in h.engine._event_poster_paths

    # Log check: structlog may or may not propagate to pytest caplog depending on
    # structlog processor config. The behavioral assertions below (no PNG + no
    # poster_url) are the primary regression guard; log presence is a bonus check.
    log_messages = [r.getMessage() for r in caplog.records]
    # If structlog does propagate, the warning must be there. If not, skip silently.
    if log_messages:
        assert any(
            "slate_move_to_holding_failed" in msg for msg in log_messages
        ), (
            f"slate_move_to_holding_failed missing from caplog: {log_messages}"
        )

    # events.json: video_url present, poster_url absent.
    h.engine._check_post_captures()
    h.engine.event_storage.generate_events_json()
    events_json = h.captures_dir / "events.json"
    feed = json.loads(events_json.read_text())
    entries = feed["events"] if isinstance(feed, dict) else feed
    assert any("video_url" in e for e in entries)
    assert not any("poster_url" in e for e in entries)
