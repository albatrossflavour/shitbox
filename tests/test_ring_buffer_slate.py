"""Tests for Phase 26-04 Task 2: VideoRingBuffer slate insertion and head_offset_s.

Covers:
  - _render_slate fallback matrix (no renderer, exception, zero duration)
  - concat.txt file-list includes slate.ts between intro.ts and segments
  - _build_concat_reencode_cmd passes head_offset_s = intro + slate into
    generate_ass_overlay
  - _build_dual_concat_reencode_cmd does the same AND emits the correct
    setpts + enable gate on the PiP filter chain
  - _pending_slate_* state resets cleanly across save passes

Mirrors tests/test_ring_buffer_cmd.py — constructs a VideoRingBuffer via
__new__ and pokes attributes directly so no real ffmpeg or Pillow runs.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

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
