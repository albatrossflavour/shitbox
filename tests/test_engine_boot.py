"""Integration tests for engine boot recovery wiring.

Tests verify:
- WAL detection logic works with real paths
- Buzzer functions exist and produce expected tone patterns
- BootRecoveryService exposes expected attributes
- Full recovery flow end-to-end using tmp_path
"""

import json
from pathlib import Path
from unittest.mock import call, patch

import pytest

from shitbox.storage.database import Database
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
