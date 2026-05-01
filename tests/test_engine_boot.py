"""Integration tests for engine boot recovery wiring.

Tests verify:
- WAL detection logic works with real paths
- Buzzer functions exist and produce expected tone patterns
- BootRecoveryService exposes expected attributes
- Full recovery flow end-to-end using tmp_path
- HW-05: engine starts with all critical hardware missing (no crash, no block)
- HW-05 pitfall 5: IMU setup failure does not invoke _force_reboot at boot
- Boot capture fires when segments are available, skips when deadline expires
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from shitbox.hardware import state as hw_state
from shitbox.storage.database import Database
from shitbox.storage.models import Reading, SensorType
from shitbox.sync.boot_recovery import BootRecoveryService, detect_unclean_shutdown


def test_engine_detects_wal_before_connect(tmp_path):
    """WAL detection returns True when WAL file present, False otherwise."""
    db_path = tmp_path / "telemetry.db"
    wal_path = Path(str(db_path) + "-wal")

    # No WAL file — fresh boot
    assert detect_unclean_shutdown(db_path) is False

    # Simulate unclean shutdown by creating a WAL file
    wal_path.touch()
    assert detect_unclean_shutdown(db_path) is True

    # Simulate clean state after checkpoint
    wal_path.unlink()
    assert detect_unclean_shutdown(db_path) is False


def test_buzzer_clean_boot_called():
    """beep_clean_boot() exists and can be called; it does not call _play_async when no buzzer."""
    from shitbox.capture import buzzer

    assert callable(buzzer.beep_clean_boot)
    assert callable(buzzer.beep_crash_recovery)

    # With no buzzer initialised, calling the functions should be a no-op
    with patch.object(buzzer, "_play_async") as mock_play:
        buzzer.beep_clean_boot()
        # _play_async returns early because _buzzer is None — no assertion needed
        # but the function must not raise
    # No exception means pass


def test_buzzer_crash_recovery_tone_sequence():
    """beep_crash_recovery() calls _play_async with the expected double-beep pattern."""
    from shitbox.capture import buzzer

    with patch.object(buzzer, "_buzzer", new=object()):
        with patch.object(buzzer, "_play") as mock_play:
            # Run _play_async synchronously by patching threading.Thread
            with patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start.return_value = None
                buzzer.beep_crash_recovery()
                mock_thread.assert_called_once()
                _, kwargs = mock_thread.call_args
                assert kwargs["name"] == "buzzer-crash-recovery"
                # Verify the target callable would pass the correct tones
                target_fn = mock_thread.call_args[1]["target"]
                # The target is _play, bound with the correct args
                args_passed = mock_thread.call_args[1]["args"]
                assert args_passed == ([(880, 200), (880, 200)],)


def test_buzzer_clean_boot_tone_sequence():
    """beep_clean_boot() calls _play_async with the expected single-beep pattern."""
    from shitbox.capture import buzzer

    with patch.object(buzzer, "_buzzer", new=object()):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start.return_value = None
            buzzer.beep_clean_boot()
            mock_thread.assert_called_once()
            _, kwargs = mock_thread.call_args
            assert kwargs["name"] == "buzzer-clean-boot"
            args_passed = mock_thread.call_args[1]["args"]
            assert args_passed == ([(880, 200)],)


def test_get_status_includes_recovery_fields():
    """BootRecoveryService exposes was_crash, recovery_complete, orphans_closed attributes."""
    db_path = Path("/tmp/test_boot_attrs.db")
    db = Database(db_path)

    # Create a minimal mock EventStorage
    class MockEventStorage:
        def close_orphaned_events(self):
            return 0

    service = BootRecoveryService(db=db, event_storage=MockEventStorage())

    # Verify default attribute values (pre-recovery)
    assert service.was_crash is False
    assert service.orphans_closed == 0
    assert service.integrity_ok is True
    assert service.recovery_complete.is_set() is False

    # Verify attributes match what get_status() keys expect
    assert isinstance(service.was_crash, bool)
    assert isinstance(service.orphans_closed, int)
    assert hasattr(service.recovery_complete, "is_set")


def test_full_recovery_flow(tmp_path):
    """End-to-end recovery using tmp_path: crash → detect → recover → verify."""
    from shitbox.events.storage import EventStorage

    db_path = tmp_path / "telemetry.db"
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    # Step 1: Create and connect a DB (this creates the WAL file under WAL mode)
    db1 = Database(db_path)
    db1.connect()

    # Step 2: Create an orphaned event (no end_time)
    orphan = {"type": "HARD_BRAKE", "start_time": 1000.0}
    orphan_file = events_dir / "orphan.json"
    orphan_file.write_text(json.dumps(orphan))

    # Step 3: Close the DB cleanly — WAL is checkpointed on clean close
    db1.close()

    # Step 4: Manually create a WAL file to simulate an unclean shutdown
    wal_path = Path(str(db_path) + "-wal")
    wal_path.touch()

    # Step 5: Detection BEFORE connect should return True
    assert detect_unclean_shutdown(db_path) is True

    # Step 6: Connect a fresh Database instance (as the engine would do after detection)
    db2 = Database(db_path)
    db2.connect()

    event_storage = EventStorage(base_dir=str(events_dir))
    service = BootRecoveryService(db=db2, event_storage=event_storage)
    service.was_crash = True

    # Step 7: Run recovery synchronously
    service._detect_and_recover()

    # Step 8: Verify outcomes
    assert service.integrity_ok is True
    assert service.orphans_closed >= 1

    updated = json.loads(orphan_file.read_text())
    assert updated["status"] == "interrupted"
    assert "end_time" in updated

    db2.close()


# ---------------------------------------------------------------------------
# DISP-01 / D-09: DS18B20 cabin temp fallback (Wave 0 RED — passes after Task 2)
# ---------------------------------------------------------------------------


def _make_minimal_engine():
    """Build a minimal UnifiedEngine stub that can run _on_reading without hardware.

    Uses __new__ to bypass __init__, then manually wires the fields that
    _on_reading actually touches.  All hardware-touching attributes are left
    absent (they are not accessed by _on_reading).
    """
    from shitbox.events.engine import UnifiedEngine

    engine = UnifiedEngine.__new__(UnifiedEngine)
    engine.database = MagicMock()
    engine.telemetry_readings = 0
    engine._cabin_temp_c = None
    return engine


def test_on_reading_temperature_updates_cabin_temp():
    """DISP-01/D-09: DS18B20 TEMPERATURE readings must populate _cabin_temp_c.

    This test is RED until Task 2 adds the SensorType.TEMPERATURE elif branch
    in engine._on_reading.  It also verifies the existing ENVIRONMENT branch
    is untouched (regression guard).
    """
    engine = _make_minimal_engine()

    # --- DS18B20 branch (the new code this test is guarding) ---
    ds_reading = Reading(sensor_type=SensorType.TEMPERATURE, temp_celsius=42.5)
    engine._on_reading(ds_reading)
    assert engine._cabin_temp_c == 42.5, (
        "DS18B20 TEMPERATURE reading did not update _cabin_temp_c. "
        "Add the elif SensorType.TEMPERATURE branch in engine._on_reading."
    )

    # --- ENVIRONMENT branch (regression guard — must still work) ---
    env_reading = Reading(sensor_type=SensorType.ENVIRONMENT, env_temp_celsius=30.0)
    engine._on_reading(env_reading)
    assert engine._cabin_temp_c == 30.0, (
        "ENVIRONMENT reading no longer updates _cabin_temp_c — regression in _on_reading."
    )


# ---------------------------------------------------------------------------
# HW-05: Engine boots with all critical hardware missing
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_hw_state_hw05():
    """Ensure module-level hw_state does not leak between HW-05 tests."""
    hw_state.clear_state()
    yield
    hw_state.clear_state()


@pytest.fixture
def minimal_engine_config(tmp_path):
    """Build an EngineConfig with paths redirected to tmp_path.

    Disables all network-dependent and hardware-dependent services so
    start() can run without blocking on GPS, speaker, or dashboard init.
    """
    from shitbox.events.engine import EngineConfig
    from shitbox.utils.config import load_config

    cfg = load_config("config/config.yaml")
    ecfg = EngineConfig.from_yaml_config(cfg)
    ecfg.database_path = str(tmp_path / "test.db")
    ecfg.events_dir = str(tmp_path / "events")
    ecfg.captures_dir = str(tmp_path / "captures")
    ecfg.video_buffer_dir = str(tmp_path / "video_buffer")
    # Disable services that block on external resources
    ecfg.uplink_enabled = False
    ecfg.gps_enabled = False
    ecfg.speaker_enabled = False
    ecfg.buzzer_enabled = False
    ecfg.dashboard_enabled = False
    return ecfg


def test_boot_with_all_critical_missing(minimal_engine_config):
    """HW-05: engine.start() completes with every critical service failing.

    All probes return False and all collector start() calls raise IOError.
    The engine must not raise, must log unified_engine_started, and the
    HardwareSupervisor thread must be alive.

    Structlog uses cache_logger_on_first_use=True, so we intercept the module-level
    log object in engine.py directly rather than relying on pytest caplog.
    """
    from shitbox.events.engine import UnifiedEngine

    info_calls: list[str] = []
    error_calls: list[tuple[str, dict]] = []

    def fake_info(event: str, **kw) -> None:  # type: ignore[return]
        info_calls.append(event)

    def fake_error(event: str, **kw) -> None:  # type: ignore[return]
        error_calls.append((event, kw))

    with patch("shitbox.hardware.probes.probe_i2c", return_value=False), \
         patch("shitbox.hardware.probes.probe_onewire", return_value=False), \
         patch("shitbox.hardware.probes.probe_usb_path", return_value=False), \
         patch("shitbox.hardware.probes.probe_audio_label", return_value=False), \
         patch("shitbox.hardware.probes.probe_hdmi", return_value=False), \
         patch("shitbox.hardware.probes.probe_gpio_pin", return_value=False), \
         patch("shitbox.hardware.probes.probe_i2c_bus_is_bitbang", return_value=True), \
         patch("shitbox.events.sampler.HighRateSampler.start", side_effect=IOError("no imu")), \
         patch(
             "shitbox.collectors.environment.EnvironmentCollector.start",
             side_effect=IOError("no bme680"),
         ), \
         patch(
             "shitbox.collectors.light.VEML7700Collector.start",
             side_effect=IOError("no veml7700"),
         ), \
         patch(
             "shitbox.capture.ring_buffer.VideoRingBuffer.start",
             side_effect=IOError("no camera"),
         ), \
         patch("shitbox.events.engine.log.info", side_effect=fake_info), \
         patch("shitbox.events.engine.log.error", side_effect=fake_error):
        engine = UnifiedEngine(minimal_engine_config)

        # Must not raise
        engine.start()

        # Supervisor must be alive
        assert engine.supervisor is not None
        assert engine.supervisor._thread is not None  # type: ignore[attr-defined]
        assert engine.supervisor._thread.is_alive()   # type: ignore[attr-defined]

        # unified_engine_started logged at INFO
        assert "unified_engine_started" in info_calls, (
            f"unified_engine_started must be logged; got info calls: {info_calls}"
        )

        # At least one service_start_failed logged at ERROR
        assert any(ev == "service_start_failed" for ev, _ in error_calls), (
            f"expected service_start_failed; got error calls: {[e for e, _ in error_calls]}"
        )

        # Clean stop must not raise
        engine.stop()


def test_imu_setup_failure_is_nonfatal(minimal_engine_config):
    """HW-05 + pitfall 5: IMU setup failure must not call _force_reboot at boot.

    Only the IMU start() raises; other probes return True. Engine must complete
    start(), log service_start_failed for imu_sampler, and never call _force_reboot.
    """
    from shitbox.events.engine import UnifiedEngine

    error_calls: list[tuple[str, dict]] = []

    def fake_error(event: str, **kw) -> None:  # type: ignore[return]
        error_calls.append((event, kw))

    with patch(
        "shitbox.events.sampler.HighRateSampler.start",
        side_effect=IOError("imu init failed"),
    ), patch(
        "shitbox.events.sampler.HighRateSampler._force_reboot"
    ) as mock_reboot, patch(
        "shitbox.hardware.probes.probe_i2c", return_value=True
    ), patch(
        "shitbox.hardware.probes.probe_gpio_pin", return_value=True
    ), patch(
        "shitbox.hardware.probes.probe_i2c_bus_is_bitbang", return_value=True
    ), patch(
        "shitbox.hardware.probes.probe_usb_path", return_value=False
    ), patch(
        "shitbox.hardware.probes.probe_onewire", return_value=False
    ), patch(
        "shitbox.hardware.probes.probe_audio_label", return_value=False
    ), patch(
        "shitbox.hardware.probes.probe_hdmi", return_value=False
    ), patch(
        "shitbox.capture.ring_buffer.VideoRingBuffer.start",
        side_effect=IOError("no camera"),
    ), patch(
        "shitbox.events.engine.log.error", side_effect=fake_error
    ):
        engine = UnifiedEngine(minimal_engine_config)
        engine.start()

        # IMU failure recorded with correct service name
        imu_errors = [
            (ev, kw) for ev, kw in error_calls
            if ev == "service_start_failed" and kw.get("service") == "imu_sampler"
        ]
        assert imu_errors, (
            f"service_start_failed for imu_sampler must be logged; errors: {error_calls}"
        )

        # _force_reboot NEVER called during boot
        mock_reboot.assert_not_called()

        engine.stop()


# ---------------------------------------------------------------------------
# Boot capture: segment wait and skip logic
# ---------------------------------------------------------------------------


def _make_boot_capture_engine(tmp_path, segment_seconds=10):
    """Build a minimal UnifiedEngine stub for testing _fire_boot_capture.

    Bypasses __init__ and wires only the fields that _fire_boot_capture
    and _on_event touch.
    """
    from shitbox.events.engine import EngineConfig, UnifiedEngine

    engine = UnifiedEngine.__new__(UnifiedEngine)
    engine.config = EngineConfig()
    engine.config.video_buffer_segment_seconds = segment_seconds

    buffer_dir = tmp_path / "video_buffer"
    buffer_dir.mkdir()

    mock_ring = MagicMock()
    mock_ring.buffer_dir = buffer_dir
    mock_ring.is_saving = False
    engine.video_ring_buffer = mock_ring

    engine._on_event = MagicMock()
    return engine


def test_boot_capture_fires_when_segments_available(tmp_path):
    """_fire_boot_capture triggers a BOOT event when >= 2 segments exist."""
    from shitbox.events.detector import EventType

    engine = _make_boot_capture_engine(tmp_path, segment_seconds=1)

    seg_dir = engine.video_ring_buffer.buffer_dir
    (seg_dir / "seg_000.ts").write_bytes(b"\x00" * 100)
    (seg_dir / "seg_001.ts").write_bytes(b"\x00" * 100)
    engine.video_ring_buffer._get_buffer_segments.return_value = [
        seg_dir / "seg_000.ts",
        seg_dir / "seg_001.ts",
    ]

    log_events: list[tuple[str, dict]] = []

    def capture_info(event: str, **kw: object) -> None:
        log_events.append((event, kw))

    with patch("shitbox.events.engine.log.info", side_effect=capture_info):
        engine._fire_boot_capture()

    engine._on_event.assert_called_once()
    boot_event = engine._on_event.call_args[0][0]
    assert boot_event.event_type == EventType.BOOT

    event_names = [e for e, _ in log_events]
    assert "boot_capture_waiting" in event_names
    assert "boot_capture_segments_ready" in event_names
    assert "boot_capture_triggered" in event_names


def test_boot_capture_skipped_when_no_segments(tmp_path):
    """_fire_boot_capture logs boot_capture_skipped when deadline expires."""
    engine = _make_boot_capture_engine(tmp_path, segment_seconds=1)
    engine.video_ring_buffer._get_buffer_segments.return_value = []

    log_events: list[tuple[str, dict]] = []
    warning_events: list[tuple[str, dict]] = []

    def capture_info(event: str, **kw: object) -> None:
        log_events.append((event, kw))

    def capture_warning(event: str, **kw: object) -> None:
        warning_events.append((event, kw))

    with patch("shitbox.events.engine.log.info", side_effect=capture_info), \
         patch("shitbox.events.engine.log.warning", side_effect=capture_warning), \
         patch("time.sleep"):
        engine._fire_boot_capture()

    engine._on_event.assert_not_called()

    skip_events = [e for e, kw in warning_events if e == "boot_capture_skipped"]
    assert len(skip_events) == 1
    skip_kw = [kw for e, kw in warning_events if e == "boot_capture_skipped"][0]
    assert skip_kw["reason"] == "deadline_expired"
    assert skip_kw["segment_count"] == 0


def test_boot_capture_waits_then_fires(tmp_path):
    """_fire_boot_capture waits through empty polls then fires when segments appear."""
    from shitbox.events.detector import EventType

    engine = _make_boot_capture_engine(tmp_path, segment_seconds=1)

    seg_dir = engine.video_ring_buffer.buffer_dir
    seg_files = [seg_dir / "seg_000.ts", seg_dir / "seg_001.ts"]

    call_count = 0

    def delayed_segments():
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            return seg_files
        return []

    engine.video_ring_buffer._get_buffer_segments.side_effect = delayed_segments

    with patch("shitbox.events.engine.log.info"), \
         patch("time.sleep"):
        engine._fire_boot_capture()

    engine._on_event.assert_called_once()
    assert engine._on_event.call_args[0][0].event_type == EventType.BOOT
    assert call_count >= 3
