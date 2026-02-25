"""Tests for BootRecoveryService and EventStorage.close_orphaned_events()."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from shitbox.storage.database import Database


def _make_service(db, event_storage):
    """Import here so stubs can be created before implementation exists."""
    from shitbox.sync.boot_recovery import BootRecoveryService
    return BootRecoveryService(db=db, event_storage=event_storage)


def test_wal_crash_detection(tmp_path):
    """BOOT-01: WAL file presence before connect() signals unclean shutdown."""
    from shitbox.sync.boot_recovery import detect_unclean_shutdown

    db_path = tmp_path / "telemetry.db"
    wal_path = Path(str(db_path) + "-wal")

    # No WAL file — clean boot
    assert detect_unclean_shutdown(db_path) is False

    # Create a fake WAL file — unclean shutdown
    wal_path.touch()
    assert detect_unclean_shutdown(db_path) is True

    # Remove it — clean again
    wal_path.unlink()
    assert detect_unclean_shutdown(db_path) is False


def test_integrity_check_on_crash(db, event_storage):
    """BOOT-02: quick_check runs when was_crash=True."""
    service = _make_service(db, event_storage)
    service.was_crash = True
    service._detect_and_recover()
    assert service.integrity_ok is True


def test_no_integrity_check_clean_boot(db, event_storage):
    """BOOT-02: quick_check does NOT run on clean boot."""
    service = _make_service(db, event_storage)
    service.was_crash = False
    with patch.object(service, "_run_integrity_check") as mock_check:
        service._detect_and_recover()
        mock_check.assert_not_called()


def test_orphan_events_closed(event_storage, event_storage_dir):
    """BOOT-01: Orphaned events (missing end_time) are marked interrupted."""
    # File 1: complete event — should be left alone
    complete = {"type": "HIGH_G", "start_time": 1000.0, "end_time": 1005.0, "status": "complete"}
    complete_file = event_storage_dir / "complete.json"
    event_storage_dir.mkdir(parents=True, exist_ok=True)
    complete_file.write_text(json.dumps(complete))

    # File 2: orphan — missing end_time
    orphan = {"type": "HARD_BRAKE", "start_time": 2000.0}
    orphan_file = event_storage_dir / "orphan.json"
    orphan_file.write_text(json.dumps(orphan))

    closed = event_storage.close_orphaned_events()
    assert closed == 1

    # Orphan should now have status=interrupted and end_time set
    updated = json.loads(orphan_file.read_text())
    assert updated["status"] == "interrupted"
    assert "end_time" in updated

    # Complete file should be unchanged
    unchanged = json.loads(complete_file.read_text())
    assert unchanged["status"] == "complete"
    assert unchanged["end_time"] == 1005.0


def test_corrupt_json_handled(event_storage, event_storage_dir):
    """BOOT-01: Corrupt JSON files are skipped without crashing."""
    event_storage_dir.mkdir(parents=True, exist_ok=True)
    corrupt_file = event_storage_dir / "corrupt.json"
    corrupt_file.write_text("{ invalid json")

    result = event_storage.close_orphaned_events()
    assert result == 0  # No events closed, no exception raised


def test_recovery_complete_event_set(db, event_storage):
    """BOOT-02: recovery_complete threading.Event is set after _run() finishes."""
    service = _make_service(db, event_storage)
    service.was_crash = False
    service.start()
    completed = service.recovery_complete.wait(timeout=5.0)
    assert completed is True
