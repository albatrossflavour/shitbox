"""Unit tests for USB speaker detection, TTS enqueue, and queue behaviour.

Tests cover AUDIO-01 (USB speaker detection and fallback) and AUDIO-02
(TTS enqueue, queue overflow, grace period, no-op when uninitialised).
All hardware dependencies (piper, /proc/asound/cards, aplay) are mocked —
no real hardware is required.
"""

import queue
import time
from unittest.mock import MagicMock, patch

import pytest

import shitbox.capture.speaker as speaker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_speaker_state():
    """Save and restore module-level state around each test.

    Ensures tests are isolated from each other regardless of run order.
    """
    # Save original state
    orig_voice = speaker._voice
    orig_alsa = speaker._alsa_device
    orig_running = speaker._running
    orig_boot_time = speaker._boot_start_time
    orig_worker = speaker._worker

    # Drain the queue so each test starts clean
    while not speaker._queue.empty():
        try:
            speaker._queue.get_nowait()
        except queue.Empty:
            break

    yield

    # Restore original state
    speaker._voice = orig_voice
    speaker._alsa_device = orig_alsa
    speaker._running = orig_running
    speaker._boot_start_time = orig_boot_time
    speaker._worker = orig_worker

    # Drain again after test
    while not speaker._queue.empty():
        try:
            speaker._queue.get_nowait()
        except queue.Empty:
            break


# ---------------------------------------------------------------------------
# AUDIO-01: USB speaker detection
# ---------------------------------------------------------------------------


def test_usb_speaker_detection() -> None:
    """_detect_usb_speaker returns correct plughw string when UACDemo card is present."""
    cards_content = (
        " 0 [ALSA           ]: bcm2835_alsa - bcm2835 ALSA\n"
        "                      bcm2835 ALSA\n"
        " 1 [UACDemoV10     ]: USB-Audio - UACDemoV1.0\n"
        "                      Jieli Technology UACDemoV1.0 at usb-3f980000.usb-1.3\n"
    )
    with patch("shitbox.capture.speaker.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_instance.read_text.return_value = cards_content
        mock_path_cls.return_value = mock_path_instance

        result = speaker._detect_usb_speaker()

    assert result == "plughw:1,0"


def test_usb_speaker_not_found() -> None:
    """_detect_usb_speaker returns None when no UACDemo card is present."""
    cards_content = (
        " 0 [ALSA           ]: bcm2835_alsa - bcm2835 ALSA\n"
        "                      bcm2835 ALSA\n"
        " 1 [Camera         ]: USB-Audio - USB Camera\n"
        "                      USB Camera at usb-3f980000.usb-1.2\n"
    )
    with patch("shitbox.capture.speaker.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_instance.read_text.return_value = cards_content
        mock_path_cls.return_value = mock_path_instance

        result = speaker._detect_usb_speaker()

    assert result is None


def test_usb_speaker_oserror() -> None:
    """_detect_usb_speaker returns None without crashing when /proc/asound/cards is unreadable."""
    with patch("shitbox.capture.speaker.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_instance.read_text.side_effect = OSError("No such file or directory")
        mock_path_cls.return_value = mock_path_instance

        result = speaker._detect_usb_speaker()

    assert result is None


def test_init_fallback_no_speaker() -> None:
    """init() returns False and speak_*() functions are no-ops when USB speaker is absent."""
    with (
        patch.object(speaker, "PIPER_AVAILABLE", True),
        patch.object(speaker, "_detect_usb_speaker", return_value=None),
    ):
        result = speaker.init("/some/model.onnx")

    assert result is False
    # _voice must remain None so speak_*() functions are no-ops
    assert speaker._voice is None


def test_init_piper_not_available() -> None:
    """init() returns False without error when piper-tts is not installed."""
    with patch.object(speaker, "PIPER_AVAILABLE", False):
        result = speaker.init("/some/model.onnx")

    assert result is False
    assert speaker._voice is None


# ---------------------------------------------------------------------------
# AUDIO-02: TTS enqueue behaviour
# ---------------------------------------------------------------------------


def test_speak_boot_clean() -> None:
    """speak_boot(was_crash=False) enqueues 'System ready.'"""
    with patch.object(speaker, "_enqueue") as mock_enqueue:
        # _voice must be set (non-None) for _enqueue to not short-circuit;
        # but we're patching _enqueue directly so it does not matter here.
        speaker.speak_boot(was_crash=False)

    mock_enqueue.assert_called_once_with("System ready.")


def test_speak_boot_crash() -> None:
    """speak_boot(was_crash=True) enqueues crash-recovery message."""
    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_boot(was_crash=True)

    mock_enqueue.assert_called_once_with("System recovered after crash.")


def test_speak_thermal_warning() -> None:
    """speak_thermal_warning() enqueues thermal warning text when past grace period."""
    speaker.set_boot_start_time(0.0)  # far in the past → grace period elapsed
    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_thermal_warning()

    mock_enqueue.assert_called_once()
    assert "temperature" in mock_enqueue.call_args[0][0].lower()


def test_speak_thermal_critical() -> None:
    """speak_thermal_critical() enqueues thermal critical text when past grace period."""
    speaker.set_boot_start_time(0.0)
    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_thermal_critical()

    mock_enqueue.assert_called_once()
    assert "critical" in mock_enqueue.call_args[0][0].lower()


def test_speaker_noop_when_not_init() -> None:
    """All speak_*() functions are silent no-ops when speaker is not initialised."""
    # Ensure _voice is None (uninitialised)
    speaker._voice = None

    # None of these should raise or enqueue anything
    speaker.speak_boot()
    speaker.speak_thermal_warning()
    speaker.speak_thermal_critical()
    speaker.speak_thermal_recovered()
    speaker.speak_under_voltage()
    speaker.speak_service_crash()
    speaker.speak_service_recovered()
    speaker.speak_i2c_lockup()
    speaker.speak_ffmpeg_stall()
    speaker.speak_waypoint_reached("Broken Hill", 3)
    speaker.speak_distance_update(150)

    # Queue must remain empty — no messages were enqueued
    assert speaker._queue.empty()


def test_queue_drops_when_full() -> None:
    """_enqueue() drops messages silently when the queue is full (maxsize=2)."""
    # Set _voice to a non-None mock so _enqueue does not short-circuit
    speaker._voice = MagicMock()

    # Fill the queue to capacity
    speaker._queue.put_nowait("message one")
    speaker._queue.put_nowait("message two")

    # This call must not raise even though the queue is at maxsize
    speaker._enqueue("overflow message")

    # The queue should still have exactly 2 items (the overflow was dropped)
    assert speaker._queue.qsize() == 2


def test_boot_grace_suppresses_alerts() -> None:
    """Boot grace period suppresses non-boot alerts within 30 seconds of startup."""
    # Set boot time to now — we are within the grace period
    speaker.set_boot_start_time(time.time())

    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_thermal_warning()
        speaker.speak_thermal_critical()
        speaker.speak_thermal_recovered()
        speaker.speak_under_voltage()
        speaker.speak_service_crash()
        speaker.speak_service_recovered()
        speaker.speak_i2c_lockup()
        speaker.speak_ffmpeg_stall()

    # No alert should have been enqueued during grace period
    mock_enqueue.assert_not_called()


def test_boot_not_suppressed_by_grace() -> None:
    """speak_boot() bypasses the grace period check and always enqueues."""
    speaker.set_boot_start_time(time.time())  # within grace period

    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_boot(was_crash=False)

    mock_enqueue.assert_called_once_with("System ready.")


# ---------------------------------------------------------------------------
# AUDIO-03: Contextual announcement message content
# ---------------------------------------------------------------------------


def test_speak_waypoint_reached() -> None:
    """speak_waypoint_reached() enqueues a message containing the name and day number."""
    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_waypoint_reached("Broken Hill", 3)

    mock_enqueue.assert_called_once()
    message = mock_enqueue.call_args[0][0]
    assert "Broken Hill" in message
    assert "3" in message


def test_speak_distance_update() -> None:
    """speak_distance_update() enqueues a message containing the km count and 'kilometres'."""
    with patch.object(speaker, "_enqueue") as mock_enqueue:
        speaker.speak_distance_update(150)

    mock_enqueue.assert_called_once()
    message = mock_enqueue.call_args[0][0]
    assert "150" in message
    assert "kilometres" in message
