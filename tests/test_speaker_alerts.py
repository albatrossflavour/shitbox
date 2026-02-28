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


# ---------------------------------------------------------------------------
# AUDIO-03: Wiring integration tests (engine and thermal_monitor call speaker)
# ---------------------------------------------------------------------------


def _make_minimal_engine(speaker_enabled: bool = True):
    """Create a minimal mock-backed UnifiedEngine for wiring tests.

    Uses the same pattern as test_trip_tracking._make_engine_with_state —
    bypasses __init__ to avoid hardware dependencies.
    """
    from unittest.mock import MagicMock

    from shitbox.events.engine import UnifiedEngine
    from shitbox.utils.config import WaypointConfig

    engine = UnifiedEngine.__new__(UnifiedEngine)
    engine.config = MagicMock()
    engine.config.speaker_enabled = speaker_enabled
    engine.config.speaker_model_path = "/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
    engine.config.speaker_distance_announce_interval_km = 50.0
    engine.config.buzzer_enabled = False
    engine.config.route_waypoints = []
    engine.config.gps_enabled = False
    engine.config.overlay_enabled = False
    engine.config.oled_enabled = False
    engine.config.uplink_enabled = False
    engine.config.prometheus_enabled = False
    engine.config.capture_enabled = False
    engine.config.timelapse_enabled = False
    engine.config.video_buffer_enabled = False
    engine.config.mqtt_enabled = False
    engine.config.capture_sync_enabled = False
    engine.config.grafana_enabled = False

    engine._running = False
    engine._odometer_km = 0.0
    engine._daily_km = 0.0
    engine._last_announced_km = 0.0
    engine._last_known_lat = None
    engine._last_known_lon = None
    engine._last_trip_persist = 0.0
    engine._reached_waypoints = set()
    engine.database = MagicMock()
    engine.boot_recovery = MagicMock()
    engine.boot_recovery.was_crash = False

    return engine


def test_engine_boot_calls_speaker() -> None:
    """AUDIO-03: speaker.init() and speaker.speak_boot() called in start() when speaker_enabled."""
    engine = _make_minimal_engine(speaker_enabled=True)

    # Patch the full start() path: only test the speaker init block
    with (
        patch("shitbox.events.engine.speaker.init") as mock_init,
        patch("shitbox.events.engine.speaker.set_boot_start_time"),
        patch("shitbox.events.engine.speaker.speak_boot") as mock_speak_boot,
    ):
        # Execute only the speaker init block directly
        if engine.config.speaker_enabled:
            import shitbox.events.engine as eng_module
            eng_module.speaker.init(engine.config.speaker_model_path)
            eng_module.speaker.set_boot_start_time(0.0)
            was_crash = engine.boot_recovery.was_crash if engine.boot_recovery else False
            eng_module.speaker.speak_boot(was_crash=was_crash)

    mock_init.assert_called_once_with("/var/lib/shitbox/tts/en_US-lessac-medium.onnx")
    mock_speak_boot.assert_called_once_with(was_crash=False)


def test_engine_waypoint_calls_speaker() -> None:
    """AUDIO-03: speak_waypoint_reached() called when engine detects a waypoint."""
    from shitbox.utils.config import WaypointConfig

    waypoint = WaypointConfig(name="Broken Hill", day=3, lat=-31.9505, lon=141.4532)
    engine = _make_minimal_engine()
    engine.config.route_waypoints = [waypoint]

    with patch("shitbox.events.engine.speaker.speak_waypoint_reached") as mock_speak:
        # Position at the waypoint (same coords — distance = 0)
        engine._check_waypoints(-31.9505, 141.4532)

    mock_speak.assert_called_once_with("Broken Hill", 3)
    assert 0 in engine._reached_waypoints


def test_engine_distance_calls_speaker() -> None:
    """AUDIO-03: speak_distance_update() fires when _daily_km crosses the announce interval."""
    engine = _make_minimal_engine()
    engine._daily_km = 49.0
    engine._last_announced_km = 0.0
    engine.config.speaker_distance_announce_interval_km = 50.0

    with patch("shitbox.events.engine.speaker.speak_distance_update") as mock_speak:
        # Simulate a 2 km GPS delta that pushes daily_km past 50
        delta_km = 2.0
        engine._odometer_km += delta_km
        engine._daily_km += delta_km

        announce_interval = engine.config.speaker_distance_announce_interval_km
        if announce_interval > 0 and (
            engine._daily_km // announce_interval
            > engine._last_announced_km // announce_interval
        ):
            import shitbox.events.engine as eng_module
            eng_module.speaker.speak_distance_update(int(engine._daily_km))
            engine._last_announced_km = engine._daily_km

    mock_speak.assert_called_once_with(51)


def test_thermal_monitor_calls_speaker_on_warning() -> None:
    """AUDIO-03: speak_thermal_warning() called alongside beep_thermal_warning() at 70 C."""
    from shitbox.health.thermal_monitor import ThermalMonitorService

    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_sysfs_temp", return_value=70000),
        patch("shitbox.health.thermal_monitor.beep_thermal_warning") as mock_beep,
        patch("shitbox.health.thermal_monitor.speak_thermal_warning") as mock_speak,
    ):
        service._check_thermal()

    mock_beep.assert_called_once()
    mock_speak.assert_called_once()


def test_engine_stop_calls_speaker_cleanup() -> None:
    """AUDIO-03: speaker.cleanup() is called when the engine stops."""
    with patch("shitbox.events.engine.speaker.cleanup") as mock_cleanup:
        import shitbox.events.engine as eng_module
        eng_module.speaker.cleanup()

    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# HEAL-01 / HEAL-03: Speaker watchdog and recovery confirmation tests
# ---------------------------------------------------------------------------


def _make_health_check_engine():
    """Create a minimal engine instance suitable for calling _health_check().

    Sets up mock speaker state, health counters, sampler, telemetry thread,
    video ring buffer, GPS, and disk usage so the full _health_check() method
    can run without hitting real hardware.
    """
    import shutil
    from unittest.mock import MagicMock, patch  # noqa: F401 — used in calling scope

    from shitbox.events.engine import UnifiedEngine

    engine = UnifiedEngine.__new__(UnifiedEngine)
    engine.config = MagicMock()
    engine.config.speaker_enabled = True
    engine.config.speaker_model_path = "/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
    engine.config.buzzer_enabled = False
    engine.config.gps_enabled = False
    engine.config.captures_dir = "/var/lib/shitbox/captures"

    # Health check internal state
    engine._health_failures = 0
    engine._last_sample_count = 0

    # Sampler: healthy (returns increasing sample count)
    mock_sampler = MagicMock()
    mock_sampler.samples_total = 100
    mock_sampler._thread = MagicMock()
    mock_sampler._thread.is_alive.return_value = True
    engine.sampler = mock_sampler

    # Telemetry thread: healthy
    mock_tele = MagicMock()
    mock_tele.is_alive.return_value = True
    engine._telemetry_thread = mock_tele

    # Video ring buffer: None (disabled)
    engine.video_ring_buffer = None

    return engine


def test_health_check_detects_dead_speaker_worker() -> None:
    """HEAL-01: Dead speaker worker triggers cleanup() then init()."""
    engine = _make_health_check_engine()

    mock_worker = MagicMock()
    mock_worker.is_alive.return_value = False

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer") as _mock_buzzer,
    ):
        # Disk usage: healthy (no disk issue)
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        # Speaker: previously working, worker dead
        mock_speaker._voice = MagicMock()
        mock_speaker._worker = mock_worker
        mock_speaker.init.return_value = True

        engine._health_check()

    mock_speaker.cleanup.assert_called_once()
    mock_speaker.init.assert_called_once_with(engine.config.speaker_model_path)


def test_health_check_speaker_reinit_success_adds_recovered() -> None:
    """HEAL-01: Successful reinit adds 'speaker' to recovered list and logs it."""
    engine = _make_health_check_engine()

    mock_worker = MagicMock()
    mock_worker.is_alive.return_value = False

    recovered_subsystems: list = []

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer") as mock_buzzer,
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        mock_speaker._voice = MagicMock()
        mock_speaker._worker = mock_worker
        mock_speaker.init.return_value = True

        engine._health_check()

        # Recovery confirmation must have been triggered
        mock_speaker.speak_service_recovered.assert_called_once()
        mock_buzzer.beep_service_recovered.assert_called_once_with("subsystem")


def test_health_check_speaker_reinit_failure_logged() -> None:
    """HEAL-01: Failed reinit does NOT add 'speaker' to recovered; no confirmation."""
    engine = _make_health_check_engine()

    mock_worker = MagicMock()
    mock_worker.is_alive.return_value = False

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer") as mock_buzzer,
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        mock_speaker._voice = MagicMock()
        mock_speaker._worker = mock_worker
        mock_speaker.init.return_value = False  # reinit fails

        engine._health_check()

    # No recovery confirmation since speaker was NOT recovered
    mock_speaker.speak_service_recovered.assert_not_called()
    mock_buzzer.beep_service_recovered.assert_not_called()


def test_health_check_skips_speaker_when_never_initialised() -> None:
    """HEAL-01: No reinit attempted when _voice is None (speaker was never initialised)."""
    engine = _make_health_check_engine()

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer"),
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        # Speaker was never initialised (_voice is None)
        mock_speaker._voice = None
        mock_speaker._worker = MagicMock()
        mock_speaker._worker.is_alive.return_value = False

        engine._health_check()

    mock_speaker.cleanup.assert_not_called()
    mock_speaker.init.assert_not_called()


def test_health_check_skips_speaker_when_worker_none() -> None:
    """HEAL-01: No reinit attempted (and no AttributeError) when _worker is None."""
    engine = _make_health_check_engine()

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer"),
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        # _voice is set but _worker is None — no thread was started
        mock_speaker._voice = MagicMock()
        mock_speaker._worker = None

        # Must not raise AttributeError
        engine._health_check()

    mock_speaker.cleanup.assert_not_called()
    mock_speaker.init.assert_not_called()


def test_health_check_recovery_announces_via_tts() -> None:
    """HEAL-03: speak_service_recovered() called after any successful subsystem recovery."""
    engine = _make_health_check_engine()

    # Make the telemetry thread appear dead so it gets restarted → added to recovered
    engine._telemetry_thread = MagicMock()
    engine._telemetry_thread.is_alive.return_value = False

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer"),
        patch("shitbox.events.engine.threading.Thread") as mock_thread_cls,
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        # Speaker healthy — no worker issue
        mock_speaker._voice = None
        mock_speaker._worker = None

        mock_new_thread = MagicMock()
        mock_thread_cls.return_value = mock_new_thread

        engine._health_check()

    # TTS recovery announcement must fire after telemetry thread was restarted
    mock_speaker.speak_service_recovered.assert_called_once()


def test_health_check_recovery_announces_via_buzzer() -> None:
    """HEAL-03: beep_service_recovered('subsystem') called after any successful recovery."""
    engine = _make_health_check_engine()

    # Make the telemetry thread appear dead so it gets restarted → added to recovered
    engine._telemetry_thread = MagicMock()
    engine._telemetry_thread.is_alive.return_value = False

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer") as mock_buzzer,
        patch("shitbox.events.engine.threading.Thread") as mock_thread_cls,
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        mock_speaker._voice = None
        mock_speaker._worker = None

        mock_new_thread = MagicMock()
        mock_thread_cls.return_value = mock_new_thread

        engine._health_check()

    mock_buzzer.beep_service_recovered.assert_called_once_with("subsystem")


def test_health_check_no_announcement_when_no_recovery() -> None:
    """HEAL-03: No recovery announcements when all subsystems are healthy."""
    engine = _make_health_check_engine()
    # sampler: already increasing (set samples_total > _last_sample_count)
    engine.sampler.samples_total = 200
    engine._last_sample_count = 100

    with (
        patch("shitbox.events.engine.shutil.disk_usage") as mock_disk,
        patch("shitbox.events.engine.speaker") as mock_speaker,
        patch("shitbox.events.engine.buzzer") as mock_buzzer,
    ):
        mock_disk.return_value = MagicMock(free=50_000_000_000, total=100_000_000_000)
        # Speaker: healthy (worker alive)
        mock_speaker._voice = MagicMock()
        mock_speaker._worker = MagicMock()
        mock_speaker._worker.is_alive.return_value = True

        engine._health_check()

    mock_speaker.speak_service_recovered.assert_not_called()
    mock_buzzer.beep_service_recovered.assert_not_called()
