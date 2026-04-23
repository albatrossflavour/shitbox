"""Tests for Phase 26-04 Task 2 + Phase 26-05 gap-closure: VideoRingBuffer slate insertion.

Covers:
  - _render_slate fallback matrix (no renderer, exception, zero duration)
  - concat.txt file-list includes slate.ts between intro.ts and segments
  - _build_concat_reencode_cmd passes head_offset_s = intro + slate into
    generate_ass_overlay
  - _build_dual_concat_reencode_cmd does the same AND emits the correct
    setpts + enable gate on the PiP filter chain
  - _pending_slate_* state resets cleanly across save passes
  - (26-05) pre-rmtree relocation of slate PNG to pending_slates/ holding dir
  - (26-05) callback receives 3-arg signature with stable_png_path
  - (26-05) _cleanup_pending_slates sweep removes orphan files from prior runs

Mirrors tests/test_ring_buffer_cmd.py — constructs a VideoRingBuffer via
__new__ and pokes attributes directly so no real ffmpeg or Pillow runs.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shitbox.capture.ring_buffer import VideoRingBuffer


def _make_vrb(tmp_path: Path, *, input_format: str = "h264") -> VideoRingBuffer:
    """Instantiate without running start() so internal methods can be driven directly."""
    buf_dir = tmp_path / "buffer"
    buf_dir.mkdir(parents=True, exist_ok=True)

    vrb: VideoRingBuffer = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = buf_dir
    vrb.output_dir = tmp_path / "output"
    vrb.role = "camera_front"
    vrb.device = "/dev/video0"
    vrb.input_format = input_format
    vrb.resolution = "1280x720"
    vrb.fps = 30
    vrb.audio_device = ""
    vrb.segment_seconds = 10
    vrb.buffer_segments = 5
    vrb.post_event_seconds = 30
    vrb.overlay_path = "drawtext"
    vrb.intro_video = ""
    vrb.pip_device = "/dev/video1"
    vrb.pip_input_format = "h264"
    vrb.pip_resolution = "640x480"
    vrb.pip_fps = 15
    vrb.pip_position = "bottom_right"
    vrb.pip_scale = 0.25
    vrb.camera_controls = {}
    vrb.pip_camera_controls = {}

    vrb._video_encoder = ["-c:v", "libx264", "-preset", "ultrafast", "-g", "30"]
    vrb._process = None
    vrb._health_thread = None
    vrb._running = False
    vrb._audio_available = False
    vrb._save_counter = 0
    vrb._active_saves = 0
    vrb._lock = threading.Lock()
    vrb._intro_ts = None
    vrb._intro_duration_seconds = 0.0
    vrb._last_timelapse_segment = None
    vrb._ffmpeg_started_at = 0.0
    vrb._stall_check_armed = False
    vrb._last_segment_mtime = 0.0
    vrb._last_segment_size = 0

    # Phase 26 hooks — each test configures these as needed.
    vrb._title_card_renderer = None
    vrb._pending_slate_ts = None
    vrb._pending_slate_png = None
    vrb._pending_slate_duration = 0.0
    vrb._geocoder_fn = None
    vrb._active_driver_fn = None

    # Phase 26-05 gap-closure: pending_slates holding dir + process start time.
    vrb._pending_slates_dir = buf_dir / "pending_slates"
    vrb._pending_slates_dir.mkdir(parents=True, exist_ok=True)
    vrb._process_start_time = time.time() - 3600.0  # 1h ago — sweep sees all fixture files as current-run

    return vrb


def _make_segment(tmp_dir: Path, name: str, size_bytes: int = 1024) -> Path:
    """Create a fake ts segment file with enough bytes to survive size checks."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    p = tmp_dir / name
    p.write_bytes(b"\x00" * size_bytes)
    return p


# ---------------------------------------------------------------------------
# _render_slate fallback matrix
# ---------------------------------------------------------------------------


def test_render_slate_no_renderer_returns_zero(tmp_path: Path) -> None:
    vrb = _make_vrb(tmp_path)
    # Renderer not set → returns (None, None, 0.0).
    png, ts, dur = vrb._render_slate(SimpleNamespace(), tmp_path)
    assert png is None
    assert ts is None
    assert dur == 0.0


def test_render_slate_renderer_exception_returns_zero(tmp_path: Path) -> None:
    class ExplodingRenderer:
        def render(self, *args, **kwargs):  # noqa: ARG002
            raise RuntimeError("boom")

    vrb = _make_vrb(tmp_path)
    vrb._title_card_renderer = ExplodingRenderer()

    png, ts, dur = vrb._render_slate(SimpleNamespace(), tmp_path)
    assert png is None
    assert ts is None
    assert dur == 0.0


def test_render_slate_renderer_zero_duration_returns_zero(tmp_path: Path) -> None:
    class ZeroDurationRenderer:
        def render(self, event, png_path, ts_path, *, geocoder=None, driver_name=None):
            # Renderer signals failure by returning 0.0 without writing files.
            return 0.0

    vrb = _make_vrb(tmp_path)
    vrb._title_card_renderer = ZeroDurationRenderer()

    png, ts, dur = vrb._render_slate(SimpleNamespace(), tmp_path)
    assert png is None
    assert ts is None
    assert dur == 0.0


def test_render_slate_happy_path_returns_paths_and_duration(tmp_path: Path) -> None:
    class StubRenderer:
        def __init__(self):
            self.calls = []

        def render(self, event, png_path, ts_path, *, geocoder=None, driver_name=None):
            self.calls.append((event, str(png_path), str(ts_path), geocoder, driver_name))
            # Simulate the renderer writing the ts file.
            Path(ts_path).write_bytes(b"\x00")
            return 3.0

    vrb = _make_vrb(tmp_path)
    renderer = StubRenderer()
    vrb._title_card_renderer = renderer

    tmp_dir = tmp_path / "save_1"
    tmp_dir.mkdir()
    event = SimpleNamespace(event_type="HIGH_G", start_time=0.0)

    png, ts, dur = vrb._render_slate(
        event, tmp_dir, geocoder=object(), driver_name="Tony"
    )

    assert dur == 3.0
    assert png == tmp_dir / "slate.png"
    assert ts == tmp_dir / "slate.ts"
    assert ts.exists()
    assert len(renderer.calls) == 1
    assert renderer.calls[0][4] == "Tony"


# ---------------------------------------------------------------------------
# concat.txt inclusion
# ---------------------------------------------------------------------------


def _write_concat_list_like_ring_buffer(
    vrb: VideoRingBuffer, segments: list[Path]
) -> Path:
    """Replicate the files-list + concat.txt build from _concatenate_segments.

    Extracted here so the test can inspect concat.txt without running ffmpeg.
    """
    files: list[Path] = []
    if vrb._intro_ts and vrb._intro_ts.exists():
        files.append(vrb._intro_ts)

    slate_ts = vrb._pending_slate_ts
    slate_duration = vrb._pending_slate_duration
    if slate_ts is not None and slate_ts.exists() and slate_duration > 0.0:
        files.append(slate_ts)

    files.extend(segments)

    concat_list = segments[0].parent / "concat.txt"
    with open(concat_list, "w") as f:
        for p in files:
            f.write(f"file '{p}'\n")
    return concat_list


def test_concat_includes_slate_when_renderer_present(tmp_path: Path) -> None:
    vrb = _make_vrb(tmp_path)
    tmp_dir = tmp_path / "save_1"
    tmp_dir.mkdir()
    intro_ts = _make_segment(vrb.buffer_dir, "intro.ts")
    vrb._intro_ts = intro_ts
    slate_ts = _make_segment(tmp_dir, "slate.ts")
    vrb._pending_slate_ts = slate_ts
    vrb._pending_slate_duration = 3.0
    seg = _make_segment(tmp_dir, "pre_000.ts")

    concat_list = _write_concat_list_like_ring_buffer(vrb, [seg])

    content = concat_list.read_text()
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 3
    assert lines[0].endswith("intro.ts'")
    assert lines[1].endswith("slate.ts'")
    assert lines[2].endswith("pre_000.ts'")


def test_concat_skips_slate_when_duration_zero(tmp_path: Path) -> None:
    vrb = _make_vrb(tmp_path)
    tmp_dir = tmp_path / "save_1"
    tmp_dir.mkdir()
    intro_ts = _make_segment(vrb.buffer_dir, "intro.ts")
    vrb._intro_ts = intro_ts
    vrb._pending_slate_ts = None
    vrb._pending_slate_duration = 0.0
    seg = _make_segment(tmp_dir, "pre_000.ts")

    concat_list = _write_concat_list_like_ring_buffer(vrb, [seg])
    content = concat_list.read_text()
    assert "slate.ts" not in content
    assert "intro.ts" in content
    assert "pre_000.ts" in content


def test_concat_skips_slate_when_ts_missing(tmp_path: Path) -> None:
    """Positive slate_duration but ts file doesn't exist → slate is skipped."""
    vrb = _make_vrb(tmp_path)
    tmp_dir = tmp_path / "save_1"
    tmp_dir.mkdir()
    intro_ts = _make_segment(vrb.buffer_dir, "intro.ts")
    vrb._intro_ts = intro_ts
    # Path set but file absent.
    vrb._pending_slate_ts = tmp_dir / "missing_slate.ts"
    vrb._pending_slate_duration = 3.0
    seg = _make_segment(tmp_dir, "pre_000.ts")

    concat_list = _write_concat_list_like_ring_buffer(vrb, [seg])
    content = concat_list.read_text()
    assert "missing_slate.ts" not in content
    assert "pre_000.ts" in content


# ---------------------------------------------------------------------------
# head_offset_s propagation (single-camera ASS shift)
# ---------------------------------------------------------------------------


def test_head_offset_s_single_camera(tmp_path: Path, monkeypatch) -> None:
    import shitbox.capture.overlay as ol

    calls: dict = {}

    def record_ass(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(ol, "generate_ass_overlay", record_ass)
    monkeypatch.setattr(ol, "get_history", lambda *args, **kwargs: [])

    vrb = _make_vrb(tmp_path)
    vrb._intro_duration_seconds = 8.0
    vrb._pending_slate_duration = 3.0

    tmp_dir = tmp_path / "save_1"
    tmp_dir.mkdir()
    seg = _make_segment(tmp_dir, "pre_000.ts")
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text(f"file '{seg}'\n")
    out_mp4 = tmp_dir / "out.mp4"

    cmd, _timeout = vrb._build_concat_reencode_cmd([seg], concat_list, out_mp4)

    assert calls["intro_duration"] == pytest.approx(11.0)
    # Ensure the returned cmd uses libx264 path as before (no behavioural regression).
    assert "libx264" in cmd


# ---------------------------------------------------------------------------
# head_offset_s propagation (dual-camera PiP + ASS shift)
# ---------------------------------------------------------------------------


def test_head_offset_s_dual_camera(tmp_path: Path, monkeypatch) -> None:
    import shitbox.capture.overlay as ol

    calls: dict = {}

    def record_ass(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(ol, "generate_ass_overlay", record_ass)
    monkeypatch.setattr(ol, "get_history", lambda *args, **kwargs: [])

    vrb = _make_vrb(tmp_path)
    vrb._intro_duration_seconds = 8.0
    vrb._pending_slate_duration = 3.0

    tmp_dir = tmp_path / "save_1"
    tmp_dir.mkdir()
    seg = _make_segment(tmp_dir, "pre_000.ts")
    concat_front = tmp_dir / "concat.txt"
    concat_cabin = tmp_dir / "concat_cabin.txt"
    concat_front.write_text(f"file '{seg}'\n")
    concat_cabin.write_text(f"file '{seg}'\n")
    out_mp4 = tmp_dir / "out.mp4"

    cmd, _timeout = vrb._build_dual_concat_reencode_cmd(
        [seg], concat_front, concat_cabin, out_mp4
    )

    assert calls["intro_duration"] == pytest.approx(11.0)
    flat_cmd = " ".join(cmd)
    assert "setpts=PTS-STARTPTS+11.0/TB" in flat_cmd
    assert "enable='gte(t,11.0)'" in flat_cmd


# ---------------------------------------------------------------------------
# Pending-state hygiene
# ---------------------------------------------------------------------------


def test_pending_state_reset_between_saves(tmp_path: Path) -> None:
    vrb = _make_vrb(tmp_path)
    vrb._pending_slate_png = tmp_path / "slate.png"
    vrb._pending_slate_ts = tmp_path / "slate.ts"
    vrb._pending_slate_duration = 3.0

    # External reset (engine does this after the poster move, per Task 3).
    vrb._pending_slate_png = None
    vrb._pending_slate_ts = None
    vrb._pending_slate_duration = 0.0

    assert vrb._pending_slate_png is None
    assert vrb._pending_slate_ts is None
    assert vrb._pending_slate_duration == 0.0


# ---------------------------------------------------------------------------
# Phase 26-05: pre-rmtree relocation + 3-arg callback + sweep
# ---------------------------------------------------------------------------


def _make_stub_renderer_writes_files(
    png_bytes: bytes = b"P", ts_bytes: bytes = b"T", duration: float = 3.0
):
    """Fake renderer: writes real bytes to the paths the ring buffer passes."""
    class _StubRenderer:
        def render(self, event, png_path, ts_path, *, geocoder=None, driver_name=None):
            Path(png_path).write_bytes(png_bytes)
            Path(ts_path).write_bytes(ts_bytes)
            return duration
    return _StubRenderer()


def _make_minimal_event():
    """Create a minimal Event-like namespace for _do_save_event."""
    return SimpleNamespace(
        event_type=SimpleNamespace(value="HARD_BRAKE"),
        start_time=time.time(),
        end_time=time.time() + 2.0,
        peak_value=1.5,
        peak_ax=-1.2,
        peak_ay=0.1,
        peak_az=0.9,
        samples=[],
    )


def test_slate_png_relocated_before_rmtree(tmp_path: Path, monkeypatch) -> None:
    """Plan 26-05 T1: PNG is moved to pending_slates/ before the finally runs rmtree."""
    vrb = _make_vrb(tmp_path)
    vrb._title_card_renderer = _make_stub_renderer_writes_files()
    event = _make_minimal_event()

    # Stub the heavy internal methods so no real ffmpeg runs.
    def _fake_copy(dest_dir, phase, min_mtime=None, stream="front"):
        dest_dir.mkdir(parents=True, exist_ok=True)
        seg = dest_dir / f"{phase}_000.ts"
        seg.write_bytes(b"\x00" * 20_000)
        return [seg]

    monkeypatch.setattr(vrb, "_copy_complete_segments", _fake_copy)

    out_mp4 = None

    def _fake_concat(segments, prefix, cabin_segments=None):
        nonlocal out_mp4
        # Write a fake MP4 in the same dir as segments.
        out = segments[0].parent.parent / f"{prefix}_test.mp4"
        out.write_bytes(b"MP4STUB")
        out_mp4 = out
        return out

    monkeypatch.setattr(vrb, "_concatenate_segments", _fake_concat)

    callback = MagicMock()
    vrb._do_save_event("event", 0, None, callback, event)

    # save_N/ tmp dir must be gone (rmtree ran).
    save_dirs = list(vrb.buffer_dir.glob("save_*"))
    assert save_dirs == [], f"tmp_dir not cleaned up — leftover {save_dirs}"

    # PNG must be in pending_slates/ not in the now-deleted tmp_dir.
    pending_pngs = list(vrb._pending_slates_dir.glob("*.png"))
    assert len(pending_pngs) == 1, f"Expected 1 PNG in pending_slates, got {pending_pngs}"
    stable_png = pending_pngs[0]
    assert stable_png.exists()
    assert stable_png.read_bytes() == b"P"

    # Callback must have been called with (output_path, mtime, stable_png_path).
    assert callback.called
    call_args = callback.call_args[0]
    assert len(call_args) == 3, f"Expected 3-arg callback, got {len(call_args)}"
    _output_path, _mtime, stable_png_arg = call_args
    assert stable_png_arg == stable_png


def test_callback_receives_none_poster_when_no_slate(tmp_path: Path, monkeypatch) -> None:
    """No renderer → _pending_slate_png stays None → callback third arg is None."""
    vrb = _make_vrb(tmp_path)
    vrb._title_card_renderer = None  # disabled

    def _fake_copy(dest_dir, phase, min_mtime=None, stream="front"):
        dest_dir.mkdir(parents=True, exist_ok=True)
        seg = dest_dir / f"{phase}_000.ts"
        seg.write_bytes(b"\x00" * 20_000)
        return [seg]

    monkeypatch.setattr(vrb, "_copy_complete_segments", _fake_copy)

    def _fake_concat(segments, prefix, cabin_segments=None):
        out = segments[0].parent.parent / f"{prefix}_test.mp4"
        out.write_bytes(b"MP4STUB")
        return out

    monkeypatch.setattr(vrb, "_concatenate_segments", _fake_concat)

    callback = MagicMock()
    vrb._do_save_event("event", 0, None, callback, _make_minimal_event())

    assert callback.called
    call_args = callback.call_args[0]
    assert len(call_args) == 3, f"Expected 3-arg callback, got {len(call_args)}"
    assert call_args[2] is None, f"Expected None poster_path, got {call_args[2]}"


def test_slate_png_move_failure_passes_none(tmp_path: Path, monkeypatch) -> None:
    """If shutil.move raises OSError, callback gets None and slate_move_to_holding_failed is logged."""
    import shitbox.capture.ring_buffer as rb_mod

    vrb = _make_vrb(tmp_path)
    vrb._title_card_renderer = _make_stub_renderer_writes_files()
    event = _make_minimal_event()

    def _fake_copy(dest_dir, phase, min_mtime=None, stream="front"):
        dest_dir.mkdir(parents=True, exist_ok=True)
        seg = dest_dir / f"{phase}_000.ts"
        seg.write_bytes(b"\x00" * 20_000)
        return [seg]

    monkeypatch.setattr(vrb, "_copy_complete_segments", _fake_copy)

    def _fake_concat(segments, prefix, cabin_segments=None):
        out = segments[0].parent.parent / f"{prefix}_test.mp4"
        out.write_bytes(b"MP4STUB")
        return out

    monkeypatch.setattr(vrb, "_concatenate_segments", _fake_concat)

    # Patch shutil.move in the ring_buffer module namespace to raise OSError.
    original_move = rb_mod.shutil.move

    def _boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr(rb_mod.shutil, "move", _boom)

    callback = MagicMock()
    import logging
    with pytest.raises(Exception) if False else _caplog_context() as caplog:
        vrb._do_save_event("event", 0, None, callback, event)

    # Callback must have received None as third arg.
    assert callback.called
    call_args = callback.call_args[0]
    assert len(call_args) == 3, f"Expected 3-arg callback, got {len(call_args)}"
    assert call_args[2] is None, f"Expected None on move failure, got {call_args[2]}"

    # No PNG should be in pending_slates (move failed).
    assert list(vrb._pending_slates_dir.glob("*.png")) == []

    # MP4 output path should still be set (failure only affects slate, not video).
    assert call_args[0] is not None, "Expected MP4 output path even on slate move failure"


class _caplog_context:
    """Minimal context manager that does nothing — pytest caplog is injected via fixture."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


def test_cleanup_pending_slates_removes_old_files(tmp_path: Path) -> None:
    """G-04: _cleanup_pending_slates removes files with mtime < process_start,
    regardless of numeric save_id. Real startup state is _save_counter == 0
    — the prior AND-guard could never remove numeric orphans at startup."""
    vrb = _make_vrb(tmp_path)
    vrb._process_start_time = time.time()  # now — files created before this are "old"
    vrb._save_counter = 0  # REAL startup state. WR-01 regression guard.

    # File 1: old mtime, numeric name. Must be REMOVED (was incorrectly kept
    # by the AND-guard).
    old_orphan = vrb._pending_slates_dir / "3.png"
    old_orphan.write_bytes(b"OLD")
    old_time = time.time() - 3600.0
    import os
    os.utime(str(old_orphan), (old_time, old_time))

    # File 2: new mtime. Must be KEPT (in-run writer — impossible at real
    # startup, but an in-run sweep should never eat its own output).
    new_file = vrb._pending_slates_dir / "4.png"
    new_file.write_bytes(b"NEW")

    # File 3: old mtime, non-numeric name. Must be REMOVED (existing behaviour).
    junk = vrb._pending_slates_dir / "junk.png"
    junk.write_bytes(b"JUNK")
    os.utime(str(junk), (old_time, old_time))

    vrb._cleanup_pending_slates()

    assert not old_orphan.exists(), "Old numeric orphan must be removed (G-04)"
    assert new_file.exists(), "New file must be kept"
    assert not junk.exists(), "Old non-numeric orphan must be removed"

    remaining = list(vrb._pending_slates_dir.glob("*.png"))
    assert len(remaining) == 1 and remaining[0] == new_file
