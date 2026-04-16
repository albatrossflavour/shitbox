"""Unit tests for VideoRingBuffer._build_ffmpeg_cmd().

Covers the dual-output shape used when the front camera runs H264
passthrough and the cabin camera is present. Also verifies the fallback
to single-camera passthrough when the cabin device is absent.
"""

from __future__ import annotations

import threading
from pathlib import Path

from shitbox.capture.ring_buffer import VideoRingBuffer


def _make_vrb(tmp_path: Path, pip_device: str, input_format: str = "h264") -> VideoRingBuffer:
    """Instantiate without running start() so we can poke _build_ffmpeg_cmd() directly."""
    buf_dir = tmp_path / "buffer"
    buf_dir.mkdir(parents=True, exist_ok=True)

    vrb: VideoRingBuffer = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = buf_dir
    vrb.output_dir = tmp_path / "output"
    vrb.device = "/dev/video0"
    vrb.input_format = input_format
    vrb.resolution = "1920x1080"
    vrb.fps = 30
    vrb.audio_device = ""  # video-only keeps the command terse
    vrb.segment_seconds = 10
    vrb.buffer_segments = 5
    vrb.post_event_seconds = 30
    vrb.overlay_path = None
    vrb.intro_video = ""

    vrb.pip_device = pip_device
    vrb.pip_input_format = "mjpeg"
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

    return vrb


def test_h264_dual_output_when_cabin_present(tmp_path: Path) -> None:
    """Cabin device present → front passthrough + cabin re-encode outputs."""
    fake_cabin = tmp_path / "camera-cabin"
    fake_cabin.touch()

    vrb = _make_vrb(tmp_path, pip_device=str(fake_cabin))
    cmd = vrb._build_ffmpeg_cmd(with_audio=False)

    # Front passthrough segment muxer
    front_pattern = str(tmp_path / "buffer" / "seg_%03d.ts")
    assert front_pattern in cmd

    # Cabin re-encode segment muxer
    cabin_pattern = str(tmp_path / "buffer" / "cabin_%03d.ts")
    assert cabin_pattern in cmd

    # Two v4l2 inputs (front + cabin)
    v4l2_count = sum(
        1 for a, b in zip(cmd, cmd[1:]) if a == "-f" and b == "v4l2"
    )
    assert v4l2_count == 2

    # Cabin is encoded with libx264 ultrafast; front is copy.
    assert "libx264" in cmd
    assert "copy" in cmd

    # Cabin input stream is mapped for the second output block
    map_args = [v for i, v in enumerate(cmd) if i > 0 and cmd[i - 1] == "-map"]
    assert "0:v" in map_args  # front
    assert "1:v" in map_args  # cabin


def test_h264_single_output_when_cabin_absent(tmp_path: Path) -> None:
    """No cabin device → original single-output passthrough shape."""
    missing_cabin = tmp_path / "not-here"  # deliberately not created

    vrb = _make_vrb(tmp_path, pip_device=str(missing_cabin))
    cmd = vrb._build_ffmpeg_cmd(with_audio=False)

    cabin_pattern = str(tmp_path / "buffer" / "cabin_%03d.ts")
    assert cabin_pattern not in cmd

    # Only one v4l2 input
    v4l2_count = sum(
        1 for a, b in zip(cmd, cmd[1:]) if a == "-f" and b == "v4l2"
    )
    assert v4l2_count == 1

    # libx264 is only added by the cabin output; not present when cabin absent
    assert "libx264" not in cmd
    assert "copy" in cmd


def test_h264_no_pip_device_configured(tmp_path: Path) -> None:
    """Empty pip_device config → single-output shape."""
    vrb = _make_vrb(tmp_path, pip_device="")
    cmd = vrb._build_ffmpeg_cmd(with_audio=False)

    cabin_pattern = str(tmp_path / "buffer" / "cabin_%03d.ts")
    assert cabin_pattern not in cmd
    assert "libx264" not in cmd
