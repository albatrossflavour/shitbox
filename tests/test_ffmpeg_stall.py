"""Unit tests for VideoRingBuffer ffmpeg stall detection logic.

Tests cover:
- Activity detection prevents false positives
- Stall detection after timeout elapses
- Startup grace period (no segments yet)
- Arming on first segment observation
- State reset on ffmpeg restart
- Health monitor integration: kills and restarts on stall
"""

import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from shitbox.capture.ring_buffer import VideoRingBuffer


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def _make_vrb(tmp_path: Path) -> VideoRingBuffer:
    """Build a VideoRingBuffer without starting ffmpeg or any threads.

    Sets buffer_dir to tmp_path/buffer and creates the directory.
    Skips _detect_encoder() which would invoke a subprocess.
    """
    buf_dir = tmp_path / "buffer"
    buf_dir.mkdir(parents=True, exist_ok=True)

    vrb: VideoRingBuffer = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = buf_dir
    vrb.output_dir = tmp_path / "output"
    vrb.device = "/dev/video0"
    vrb.resolution = "1280x720"
    vrb.fps = 30
    vrb.audio_device = "default"
    vrb.segment_seconds = 10
    vrb.buffer_segments = 5
    vrb.post_event_seconds = 30
    vrb.overlay_path = None
    vrb.intro_video = ""

    vrb._process = None
    vrb._health_thread = None
    vrb._running = False
    vrb._audio_available = True
    vrb._video_encoder = ["-c:v", "libx264", "-preset", "ultrafast", "-g", "30"]
    vrb._save_counter = 0
    import threading
    vrb._lock = threading.Lock()
    vrb._intro_ts: Optional[Path] = None

    # Stall detection state
    vrb._last_segment_mtime = 0.0
    vrb._last_segment_size = 0
    vrb._stall_check_armed = False

    return vrb


def _write_segment(directory: Path, name: str, content: bytes = b"x" * 1024) -> Path:
    """Write a segment file and return its path."""
    seg = directory / name
    seg.write_bytes(content)
    return seg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stall_not_detected_on_activity(tmp_path: Path) -> None:
    """_check_stall returns False when the newest segment is growing."""
    vrb = _make_vrb(tmp_path)
    buf_dir = vrb.buffer_dir

    _write_segment(buf_dir, "seg_000.ts")
    newest = _write_segment(buf_dir, "seg_001.ts", b"a" * 2048)

    # First call arms the detector — returns False
    result_first = vrb._check_stall()
    assert result_first is False
    assert vrb._stall_check_armed is True

    # Modify newest segment to simulate continued activity
    time.sleep(0.01)
    newest.write_bytes(newest.read_bytes() + b"more")

    # Second call detects activity — returns False
    result_second = vrb._check_stall()
    assert result_second is False


def test_stall_detected_after_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_check_stall returns True when mtime/size is unchanged past the timeout."""
    vrb = _make_vrb(tmp_path)
    buf_dir = vrb.buffer_dir

    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")

    # First call arms the detector
    assert vrb._check_stall() is False
    assert vrb._stall_check_armed is True

    # Second call with unchanged file and recent mtime — still False
    assert vrb._check_stall() is False

    # Advance time past the stall timeout
    segment_mtime = vrb._last_segment_mtime
    monkeypatch.setattr(
        time,
        "time",
        lambda: segment_mtime + VideoRingBuffer.STALL_TIMEOUT_SECONDS + 1,
    )

    # Third call — timeout elapsed with no activity
    assert vrb._check_stall() is True


def test_stall_not_triggered_before_first_segment(tmp_path: Path) -> None:
    """_check_stall returns False when no segment files exist yet."""
    vrb = _make_vrb(tmp_path)

    result = vrb._check_stall()

    assert result is False
    assert vrb._stall_check_armed is False


def test_stall_arms_on_first_segment(tmp_path: Path) -> None:
    """_check_stall arms when the first segment appears, then returns False."""
    vrb = _make_vrb(tmp_path)
    buf_dir = vrb.buffer_dir

    # No segments — should not arm
    assert vrb._check_stall() is False
    assert vrb._stall_check_armed is False

    # Create a segment
    _write_segment(buf_dir, "seg_000.ts")

    # First observation with a segment — arms and returns False
    result = vrb._check_stall()
    assert result is False
    assert vrb._stall_check_armed is True


def test_stall_state_resets(tmp_path: Path) -> None:
    """_reset_stall_state clears all stall detection fields."""
    vrb = _make_vrb(tmp_path)
    buf_dir = vrb.buffer_dir

    _write_segment(buf_dir, "seg_000.ts")

    # Arm the detector
    vrb._check_stall()
    assert vrb._stall_check_armed is True

    # Reset
    vrb._reset_stall_state()

    assert vrb._stall_check_armed is False
    assert vrb._last_segment_mtime == 0.0
    assert vrb._last_segment_size == 0


def test_health_monitor_restarts_on_stall(tmp_path: Path) -> None:
    """Health monitor kills and restarts ffmpeg when a stall is detected.

    Uses side_effect on _check_stall to return True once (triggering restart),
    then StopIteration to break out of the monitor loop cleanly via the sleep
    side_effect raising an exception after one iteration.
    """
    vrb = _make_vrb(tmp_path)

    # Make _process look alive (poll returns None)
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    vrb._process = mock_process
    vrb._running = True

    # sleep side_effect: first call does nothing (the loop body runs), second
    # call raises SystemExit to break out of the while loop cleanly.
    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=True),
        patch.object(vrb, "_kill_current") as mock_kill,
        patch.object(vrb, "_start_ffmpeg") as mock_start,
        patch("shitbox.capture.buzzer.beep_ffmpeg_stall") as mock_beep,
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass  # expected — used to break the monitor loop

    mock_beep.assert_called_once()
    mock_kill.assert_called_once()
    mock_start.assert_called_once()
