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

    # MON-03 consecutive restart counter (plan 15-03)
    vrb._consecutive_restart_count = 0

    # Hardware state role (Plan 21-03)
    vrb.role = "camera_front"

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

    # Advance monotonic clock past the stall timeout. Stall age is measured
    # against time.monotonic() (REVIEW WR-03) so a GPS wall-clock step does
    # not register as a stall.
    seen_at = vrb._last_segment_seen_monotonic
    monkeypatch.setattr(
        "shitbox.capture.ring_buffer.time.monotonic",
        lambda: seen_at + VideoRingBuffer.STALL_TIMEOUT_SECONDS + 1,
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


# ---------------------------------------------------------------------------
# HardwareState observational hook tests (Phase 21-03)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_hw_state_ffmpeg():
    """Reset HardwareState before and after each test in this module."""
    from shitbox.hardware import state as hw_state
    hw_state.clear_state()
    yield
    hw_state.clear_state()


def _make_vrb_with_role(tmp_path: Path, role: str = "camera_front") -> VideoRingBuffer:
    """Build a VideoRingBuffer with a role attribute for hardware state tests."""
    vrb = _make_vrb(tmp_path)
    vrb.role = role
    return vrb


def test_video_device_missing_reports_missing(tmp_path: Path) -> None:
    """video_device_missing log site reports MISSING for the camera role."""
    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState

    hw_state.initialise({"camera_front": "critical"})

    vrb = _make_vrb_with_role(tmp_path, role="camera_front")

    # Simulate ffmpeg process that has exited (poll returns non-None)
    mock_process = MagicMock()
    mock_process.poll.return_value = 1  # exited
    mock_process.returncode = 1
    mock_process.stderr = MagicMock()
    mock_process.stderr.fileno.return_value = -1
    vrb._process = mock_process
    vrb._running = True

    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0) if sleep_calls else SystemExit("stop")
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch("os.path.exists", return_value=False),  # device node missing
        patch.object(vrb, "_read_stderr", return_value=""),
        patch.object(vrb, "_start_ffmpeg"),
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass

    snap = hw_state.snapshot()
    assert snap["camera_front"].state == DeviceState.MISSING


def test_stall_reports_degraded(tmp_path: Path) -> None:
    """ffmpeg stall detection path reports DEGRADED for the camera role."""
    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState

    hw_state.initialise({"camera_front": "critical"})

    vrb = _make_vrb_with_role(tmp_path, role="camera_front")

    mock_process = MagicMock()
    mock_process.poll.return_value = None  # alive
    vrb._process = mock_process
    vrb._running = True

    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0) if sleep_calls else SystemExit("stop")
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=True),
        patch.object(vrb, "_kill_current"),
        patch.object(vrb, "_start_ffmpeg"),
        patch.object(vrb, "_read_stderr", return_value=""),
        patch("shitbox.capture.buzzer.beep_ffmpeg_stall"),
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass

    snap = hw_state.snapshot()
    assert snap["camera_front"].state == DeviceState.DEGRADED


def test_successful_ffmpeg_start_reports_present(tmp_path: Path) -> None:
    """_start_ffmpeg reports PRESENT after process launches successfully."""
    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState

    hw_state.initialise({"camera_front": "critical"})

    vrb = _make_vrb_with_role(tmp_path, role="camera_front")
    vrb._running = True
    vrb.audio_device = ""  # video-only path (no audio retry delay)
    vrb.pip_device = ""
    vrb.input_format = "mjpeg"
    vrb._ffmpeg_started_at = 0.0

    mock_process = MagicMock()
    mock_process.poll.return_value = None  # process alive

    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.run"),
        patch("subprocess.Popen", return_value=mock_process),
        patch.object(vrb, "_build_ffmpeg_cmd", return_value=["ffmpeg"]),
        patch.object(vrb, "_cleanup_buffer"),
    ):
        vrb._start_ffmpeg()

    snap = hw_state.snapshot()
    assert snap["camera_front"].state == DeviceState.PRESENT


# ---------------------------------------------------------------------------
# MON-03: capture-failure alerts (Phase 15-03)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_alerts_state():
    """Reset alerts module state before and after each test in this module."""
    from shitbox.health import alerts
    alerts.clear_state()
    yield
    alerts.clear_state()


def test_mon03_capture_failure_fires(tmp_path: Path) -> None:
    """Stall detection fires alerts.fire_alert with CAPTURE_FAILURE subtype."""
    vrb = _make_vrb(tmp_path)

    mock_process = MagicMock()
    mock_process.poll.return_value = None
    vrb._process = mock_process
    vrb._running = True
    vrb._consecutive_restart_count = 0

    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=True),
        patch.object(vrb, "_read_stderr", return_value=""),
        patch.object(vrb, "_kill_current"),
        patch.object(vrb, "_start_ffmpeg"),
        patch("shitbox.capture.buzzer.beep_ffmpeg_stall") as mock_beep,
        patch("shitbox.capture.ring_buffer.alerts.fire_alert") as mock_fire,
        patch("shitbox.capture.ring_buffer.hw_state.report_degraded") as mock_degraded,
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass

    mock_beep.assert_called_once()
    mock_degraded.assert_called_once_with("camera_front")
    # First call must be CAPTURE_FAILURE; CAPTURE_DOWN only fires at >= 3 restarts
    capture_failure_calls = [
        c for c in mock_fire.call_args_list if c.args[0] == "CAPTURE_FAILURE"
    ]
    assert len(capture_failure_calls) == 1
    call = capture_failure_calls[0]
    assert call.kwargs.get("active") is True or call.args[1] is True
    assert (
        call.kwargs.get("message") == "CAPTURE STALLED"
        or call.args[2] == "CAPTURE STALLED"
    )
    assert call.kwargs.get("sustain_required") == 1


def test_mon03_capture_down_after_threshold(tmp_path: Path) -> None:
    """Three consecutive stall iterations escalate to CAPTURE_DOWN."""
    vrb = _make_vrb(tmp_path)

    mock_process = MagicMock()
    mock_process.poll.return_value = None
    vrb._process = mock_process
    vrb._running = True
    vrb._consecutive_restart_count = 0

    # Four sleep ticks: 3 stall iterations then stop
    sleep_calls = [None, None, None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=True),
        patch.object(vrb, "_read_stderr", return_value=""),
        patch.object(vrb, "_kill_current"),
        patch.object(vrb, "_start_ffmpeg"),
        patch("shitbox.capture.buzzer.beep_ffmpeg_stall"),
        patch("shitbox.capture.ring_buffer.alerts.fire_alert") as mock_fire,
        patch("shitbox.capture.ring_buffer.hw_state.report_degraded"),
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass

    subtypes = [c.args[0] for c in mock_fire.call_args_list]
    assert subtypes.count("CAPTURE_FAILURE") == 3, subtypes
    assert subtypes.count("CAPTURE_DOWN") == 1, subtypes
    # CAPTURE_DOWN must appear after the third CAPTURE_FAILURE, not before
    first_down = subtypes.index("CAPTURE_DOWN")
    failures_before_down = subtypes[:first_down].count("CAPTURE_FAILURE")
    assert failures_before_down == 3


def test_mon03_capture_restored_fires(tmp_path: Path) -> None:
    """Clean segment after prior failure fires CAPTURE_RESTORED recovery."""
    vrb = _make_vrb(tmp_path)

    mock_process = MagicMock()
    mock_process.poll.return_value = None
    vrb._process = mock_process
    vrb._running = True
    vrb._consecutive_restart_count = 2  # prior failures
    vrb._stall_check_armed = True        # detector has seen a segment

    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=False),
        patch.object(vrb, "_read_stderr", return_value=""),
        patch.object(vrb, "_kill_current"),
        patch.object(vrb, "_start_ffmpeg"),
        patch("shitbox.capture.ring_buffer.alerts.fire_recovery") as mock_recovery,
        patch("shitbox.capture.ring_buffer.alerts.fire_alert"),
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass

    # Recovery branch fires CAPTURE_FAILURE → CAPTURE_RESTORED for UI/TTS,
    # plus CAPTURE_DOWN to clear the escalation latch (REVIEW WR-02) so a
    # second escalation episode can re-fire CAPTURE_DOWN.
    assert mock_recovery.call_count == 2
    failure_call, down_call = mock_recovery.call_args_list
    assert failure_call.args[0] == "CAPTURE_FAILURE"
    assert failure_call.kwargs.get("recovery_subtype") == "CAPTURE_RESTORED"
    assert failure_call.kwargs.get("message") == "RECORDING RESUMED"
    assert down_call.args[0] == "CAPTURE_DOWN"
    assert down_call.kwargs.get("message") == "RECORDING RESUMED"
    assert vrb._consecutive_restart_count == 0
