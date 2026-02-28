"""Unit test scaffolds for capture integrity behaviours (CAPT-01, CAPT-02, CAPT-03).

These are RED-phase tests — they will fail until Plan 02 implements the
corresponding behaviour in ring_buffer.py and engine.py.

Tests cover:
  CAPT-01 (post-save verification):
    - Missing output file detected and callback receives None
    - Zero-byte output file detected and callback receives None
    - Successful save passes callback the valid path
    - Failure triggers both buzzer and speaker alerts
  CAPT-02 (timelapse gap watchdog):
    - Gap fires after 3x interval with no successful capture
    - No false positive at boot (sentinel _last_timelapse_time == 0.0)
    - Recovery restarts ffmpeg via _kill_current() + _start_ffmpeg()
  CAPT-03 (boot guard and partial saves):
    - BOOT event with < 2 segments skips save_event() entirely
    - Empty post-event copy emits video_save_post_event_empty warning
    - Partial save (pre-only) still produces a valid callback path
"""

import threading
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from shitbox.capture.ring_buffer import VideoRingBuffer

# ---------------------------------------------------------------------------
# Factory helpers (mirror test_ffmpeg_stall.py _make_vrb pattern)
# ---------------------------------------------------------------------------


def _make_vrb(tmp_path: Path) -> VideoRingBuffer:
    """Build a VideoRingBuffer without starting ffmpeg or any threads.

    Sets buffer_dir to tmp_path/buffer and output_dir to tmp_path/output.
    Skips _detect_encoder() which would invoke a subprocess.
    """
    buf_dir = tmp_path / "buffer"
    buf_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    vrb: VideoRingBuffer = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = buf_dir
    vrb.output_dir = out_dir
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
    vrb._lock = threading.Lock()
    vrb._intro_ts = None

    vrb._last_segment_mtime = 0.0
    vrb._last_segment_size = 0
    vrb._stall_check_armed = False

    return vrb


def _write_segment(directory: Path, name: str, content: bytes = b"x" * 20_000) -> Path:
    """Write a segment file of sufficient size to pass MIN_SEGMENT_BYTES check."""
    seg = directory / name
    seg.write_bytes(content)
    return seg


def _make_minimal_engine(tmp_path: Path) -> MagicMock:
    """Build a minimal mock engine with the state attributes _check_timelapse needs.

    The mock uses spec=False intentionally so we can assign arbitrary attributes
    that the real engine would have, mirroring only what _check_timelapse reads.
    """
    from shitbox.events.engine import UnifiedEngine

    engine = MagicMock(spec=UnifiedEngine)
    engine._last_timelapse_time = 0.0
    engine._current_speed_kmh = 0.0
    engine.timelapse_images = 0
    engine.video_ring_buffer = None
    engine.video_recorder = None

    # EngineConfig-like config object
    config = MagicMock()
    config.timelapse_enabled = True
    config.timelapse_interval_seconds = 30
    config.timelapse_min_speed_kmh = 5.0
    engine.config = config

    return engine


# ---------------------------------------------------------------------------
# CAPT-01: Post-save verification
# ---------------------------------------------------------------------------


def test_save_verification_missing_file(tmp_path: Path) -> None:
    """_do_save_event detects when the output path does not exist.

    Mocks _concatenate_segments to return a Path that was never written.
    Asserts the callback receives None and beep_capture_failed is called.

    FAILS until Plan 02 adds post-save verification to _do_save_event().
    """
    vrb = _make_vrb(tmp_path)

    # Provide enough segments so the save proceeds past early guards
    buf_dir = vrb.buffer_dir
    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")
    _write_segment(buf_dir, "seg_002.ts")

    missing_path = tmp_path / "output" / "ghost_file.mp4"
    # Deliberately do NOT write this file — it should not exist

    callback_result: list[Optional[Path]] = []

    def _callback(path: Optional[Path]) -> None:
        callback_result.append(path)

    with (
        patch.object(vrb, "_copy_complete_segments", return_value=[buf_dir / "seg_000.ts"]),
        patch.object(vrb, "_concatenate_segments", return_value=missing_path),
        patch("time.sleep"),
        patch("shitbox.capture.buzzer.beep_capture_failed") as mock_beep,
        patch("shitbox.capture.speaker.speak_capture_failed"),
    ):
        vrb._do_save_event("test", 5, _callback)

    assert callback_result == [None], (
        "Callback should receive None when output file does not exist"
    )
    mock_beep.assert_called_once()


def test_save_verification_zero_byte(tmp_path: Path) -> None:
    """_do_save_event detects when the output file exists but is 0 bytes.

    Mocks _concatenate_segments to return a Path pointing to an empty file.
    Asserts the callback receives None.

    FAILS until Plan 02 adds post-save verification to _do_save_event().
    """
    vrb = _make_vrb(tmp_path)

    buf_dir = vrb.buffer_dir
    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")
    _write_segment(buf_dir, "seg_002.ts")

    zero_byte_path = tmp_path / "output" / "zero.mp4"
    zero_byte_path.parent.mkdir(parents=True, exist_ok=True)
    zero_byte_path.write_bytes(b"")  # 0 bytes

    callback_result: list[Optional[Path]] = []

    def _callback(path: Optional[Path]) -> None:
        callback_result.append(path)

    with (
        patch.object(vrb, "_copy_complete_segments", return_value=[buf_dir / "seg_000.ts"]),
        patch.object(vrb, "_concatenate_segments", return_value=zero_byte_path),
        patch("time.sleep"),
        patch("shitbox.capture.buzzer.beep_capture_failed"),
        patch("shitbox.capture.speaker.speak_capture_failed"),
    ):
        vrb._do_save_event("test", 5, _callback)

    assert callback_result == [None], (
        "Callback should receive None when output file is 0 bytes"
    )


def test_save_verification_success(tmp_path: Path) -> None:
    """_do_save_event passes the valid path to the callback on success.

    Mocks _concatenate_segments to return a Path with non-zero content.
    Asserts the callback receives the exact path.

    This test passes even before Plan 02 — success path is unchanged.
    """
    vrb = _make_vrb(tmp_path)

    buf_dir = vrb.buffer_dir
    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")
    _write_segment(buf_dir, "seg_002.ts")

    valid_path = tmp_path / "output" / "valid.mp4"
    valid_path.parent.mkdir(parents=True, exist_ok=True)
    valid_path.write_bytes(b"x" * 1024)  # non-zero content

    callback_result: list[Optional[Path]] = []

    def _callback(path: Optional[Path]) -> None:
        callback_result.append(path)

    with (
        patch.object(vrb, "_copy_complete_segments", return_value=[buf_dir / "seg_000.ts"]),
        patch.object(vrb, "_concatenate_segments", return_value=valid_path),
        patch("time.sleep"),
    ):
        vrb._do_save_event("test", 5, _callback)

    assert callback_result == [valid_path], (
        "Callback should receive the valid path on success"
    )


def test_save_verification_failure_alerts(tmp_path: Path) -> None:
    """_do_save_event calls both beep_capture_failed and speak_capture_failed on failure.

    Mocks _concatenate_segments to return None (concatenation failed entirely).
    Asserts both alert functions are called.

    FAILS until Plan 02 adds alert calls to the failure path in _do_save_event().
    """
    vrb = _make_vrb(tmp_path)

    buf_dir = vrb.buffer_dir
    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")
    _write_segment(buf_dir, "seg_002.ts")

    callback_result: list[Optional[Path]] = []

    def _callback(path: Optional[Path]) -> None:
        callback_result.append(path)

    with (
        patch.object(vrb, "_copy_complete_segments", return_value=[buf_dir / "seg_000.ts"]),
        patch.object(vrb, "_concatenate_segments", return_value=None),
        patch("time.sleep"),
        patch("shitbox.capture.buzzer.beep_capture_failed") as mock_beep,
        patch("shitbox.capture.speaker.speak_capture_failed") as mock_speak,
    ):
        vrb._do_save_event("test", 5, _callback)

    mock_beep.assert_called_once()
    mock_speak.assert_called_once()
    assert callback_result == [None]


# ---------------------------------------------------------------------------
# CAPT-02: Timelapse gap watchdog
# ---------------------------------------------------------------------------


def test_timelapse_gap_detected(tmp_path: Path) -> None:
    """_check_timelapse logs timelapse_gap_detected after 3x interval with no capture.

    Sets _last_timelapse_time to a value older than 3 * interval,
    speed above threshold, and capture_frame() returning None.
    Asserts the warning log key is emitted.

    FAILS until Plan 02 adds the gap watchdog to _check_timelapse().
    """
    from shitbox.events.engine import UnifiedEngine

    engine = _make_minimal_engine(tmp_path)
    interval = 30
    engine.config.timelapse_interval_seconds = interval
    engine.config.timelapse_min_speed_kmh = 5.0
    engine._current_speed_kmh = 60.0

    # Set last capture time to > 3x interval ago
    now = time.time()
    engine._last_timelapse_time = now - (interval * 3 + 10)

    # video_ring_buffer returns None from capture_frame (simulating stuck segment)
    mock_vrb = MagicMock()
    mock_vrb.is_running = True
    mock_vrb.capture_frame.return_value = None
    engine.video_ring_buffer = mock_vrb

    import structlog.testing

    with structlog.testing.capture_logs() as captured:
        UnifiedEngine._check_timelapse(engine, now)

    log_events = [e["event"] for e in captured]
    assert "timelapse_gap_detected" in log_events, (
        "Expected timelapse_gap_detected warning when gap exceeds 3x interval"
    )


def test_timelapse_gap_no_false_positive_at_boot(tmp_path: Path) -> None:
    """_check_timelapse does not fire the gap watchdog before the first capture.

    Sets _last_timelapse_time = 0.0 (sentinel meaning 'never captured').
    Speed is above threshold. Asserts timelapse_gap_detected is NOT emitted.

    FAILS until Plan 02 guards the watchdog with _last_timelapse_time > 0.0.
    """
    from shitbox.events.engine import UnifiedEngine

    engine = _make_minimal_engine(tmp_path)
    engine.config.timelapse_interval_seconds = 30
    engine.config.timelapse_min_speed_kmh = 5.0
    engine._current_speed_kmh = 60.0
    engine._last_timelapse_time = 0.0  # sentinel — never captured

    mock_vrb = MagicMock()
    mock_vrb.is_running = True
    mock_vrb.capture_frame.return_value = None
    engine.video_ring_buffer = mock_vrb

    # 'now' is large so elapsed = now - 0.0 would be enormous without the guard
    now = time.time()

    import structlog.testing

    with structlog.testing.capture_logs() as captured:
        UnifiedEngine._check_timelapse(engine, now)

    log_events = [e["event"] for e in captured]
    assert "timelapse_gap_detected" not in log_events, (
        "timelapse_gap_detected must not fire when _last_timelapse_time is the 0.0 sentinel"
    )


def test_timelapse_gap_recovery(tmp_path: Path) -> None:
    """_check_timelapse calls _kill_current() and _start_ffmpeg() on gap detection.

    Same setup as test_timelapse_gap_detected but asserts recovery actions.

    FAILS until Plan 02 adds recovery calls to the gap watchdog.
    """
    from shitbox.events.engine import UnifiedEngine

    engine = _make_minimal_engine(tmp_path)
    interval = 30
    engine.config.timelapse_interval_seconds = interval
    engine.config.timelapse_min_speed_kmh = 5.0
    engine._current_speed_kmh = 60.0

    now = time.time()
    engine._last_timelapse_time = now - (interval * 3 + 10)

    mock_vrb = MagicMock()
    mock_vrb.is_running = True
    mock_vrb.capture_frame.return_value = None
    engine.video_ring_buffer = mock_vrb

    import structlog.testing

    with structlog.testing.capture_logs() as _:
        UnifiedEngine._check_timelapse(engine, now)

    mock_vrb._kill_current.assert_called_once()
    mock_vrb._start_ffmpeg.assert_called_once()


# ---------------------------------------------------------------------------
# CAPT-03: Boot guard and partial saves
# ---------------------------------------------------------------------------


def test_boot_save_skipped_no_segments(tmp_path: Path) -> None:
    """_on_event skips save_event() for BOOT events when fewer than 2 segments exist.

    Creates a mock engine with a video_ring_buffer that reports < 2 segments.
    Fires a BOOT event via _on_event(). Asserts save_event() is NOT called.

    FAILS until Plan 02 adds the boot guard to _on_event().
    """
    from shitbox.events.engine import UnifiedEngine
    from shitbox.events.storage import Event, EventType

    engine = MagicMock(spec=UnifiedEngine)

    # Minimal config
    config = MagicMock()
    config.detector = MagicMock()
    config.detector.post_event_seconds = 30
    config.capture_post_seconds = 30
    engine.config = config

    # Engine state
    engine._pending_post_capture = {}
    engine._event_json_paths = {}
    engine._event_video_paths = {}
    engine._current_lat = None
    engine._current_lon = None
    engine._current_speed_kmh = 0.0
    engine._current_location_name = None
    engine._distance_from_start_km = None
    engine._distance_to_destination_km = None
    engine.mqtt = None

    # video_ring_buffer reports only 1 segment (not enough)
    mock_vrb = MagicMock()
    mock_vrb.is_running = True
    mock_vrb._get_buffer_segments.return_value = [Path(tmp_path / "seg_000.ts")]
    engine.video_ring_buffer = mock_vrb
    engine.video_recorder = None

    boot_event = Event(
        event_type=EventType.BOOT,
        start_time=time.time(),
        end_time=time.time(),
        peak_value=0.0,
        peak_ax=0.0,
        peak_ay=0.0,
        peak_az=0.0,
    )

    UnifiedEngine._on_event(engine, boot_event)

    mock_vrb.save_event.assert_not_called()


def test_post_event_empty_segments_logged(tmp_path: Path) -> None:
    """_do_save_event logs video_save_post_event_empty when post-event copy returns [].

    Pre-event copy returns 1 segment; post-event copy returns [].
    Asserts a warning with key video_save_post_event_empty is logged.

    FAILS until Plan 02 adds the empty-post-event log to _do_save_event().
    """
    vrb = _make_vrb(tmp_path)

    buf_dir = vrb.buffer_dir
    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")
    _write_segment(buf_dir, "seg_002.ts")

    pre_segment_copy = tmp_path / "pre_000.ts"
    pre_segment_copy.write_bytes(b"x" * 20_000)

    # Pre-event copy returns 1 segment; post-event copy returns nothing
    def _copy_side_effect(dest_dir: Path, phase: str, min_mtime: Optional[float] = None):
        if phase == "pre":
            return [pre_segment_copy]
        return []

    valid_path = tmp_path / "output" / "partial.mp4"
    valid_path.parent.mkdir(parents=True, exist_ok=True)
    valid_path.write_bytes(b"x" * 1024)

    import structlog.testing

    with (
        patch.object(vrb, "_copy_complete_segments", side_effect=_copy_side_effect),
        patch.object(vrb, "_concatenate_segments", return_value=valid_path),
        patch("time.sleep"),
        structlog.testing.capture_logs() as captured,
    ):
        vrb._do_save_event("test", 5, None)

    log_events = [e["event"] for e in captured]
    assert "video_save_post_event_empty" in log_events, (
        "Expected video_save_post_event_empty warning when post-event segments are empty"
    )


def test_partial_save_pre_only(tmp_path: Path) -> None:
    """_do_save_event passes the output path to callback even with pre-only segments.

    Post-event copy returns []; pre-event copy returns 1 segment.
    _concatenate_segments returns a valid path.
    Asserts callback receives the valid path (partial save is still valid).

    FAILS only if Plan 02 incorrectly rejects saves with no post-event segments.
    """
    vrb = _make_vrb(tmp_path)

    buf_dir = vrb.buffer_dir
    pre_segment_copy = tmp_path / "pre_000.ts"
    pre_segment_copy.write_bytes(b"x" * 20_000)

    _write_segment(buf_dir, "seg_000.ts")
    _write_segment(buf_dir, "seg_001.ts")

    def _copy_side_effect(dest_dir: Path, phase: str, min_mtime: Optional[float] = None):
        if phase == "pre":
            return [pre_segment_copy]
        return []

    valid_path = tmp_path / "output" / "partial.mp4"
    valid_path.parent.mkdir(parents=True, exist_ok=True)
    valid_path.write_bytes(b"x" * 1024)

    callback_result: list[Optional[Path]] = []

    def _callback(path: Optional[Path]) -> None:
        callback_result.append(path)

    with (
        patch.object(vrb, "_copy_complete_segments", side_effect=_copy_side_effect),
        patch.object(vrb, "_concatenate_segments", return_value=valid_path),
        patch("time.sleep"),
        patch("shitbox.capture.buzzer.beep_capture_failed", return_value=None),
        patch("shitbox.capture.speaker.speak_capture_failed", return_value=None),
    ):
        vrb._do_save_event("test", 5, _callback)

    assert callback_result == [valid_path], (
        "Partial save (pre-event segments only) should still deliver valid path to callback"
    )
