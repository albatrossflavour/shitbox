"""Boot recovery service — detects unclean shutdowns and repairs orphaned state."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from shitbox.utils.logging import get_logger

if TYPE_CHECKING:
    from shitbox.events.storage import EventStorage
    from shitbox.storage.database import Database

log = get_logger(__name__)


def detect_unclean_shutdown(db_path: Path) -> bool:
    """Check whether the previous shutdown was unclean by looking for a WAL file.

    IMPORTANT: Call this BEFORE database.connect(), which creates the WAL file.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        True if a WAL file is present (unclean shutdown), False otherwise.
    """
    wal_path = Path(str(db_path) + "-wal")
    return wal_path.exists()


class BootRecoveryService:
    """Detects crash conditions on boot and repairs orphaned event state.

    Usage::

        was_crash = detect_unclean_shutdown(db_path)
        db.connect()
        service = BootRecoveryService(db=db, event_storage=event_storage)
        service.was_crash = was_crash
        service.start()
        # service.recovery_complete.wait() if you need to block
    """

    def __init__(self, db: "Database", event_storage: "EventStorage") -> None:
        """Initialise the recovery service.

        Args:
            db: Connected Database instance.
            event_storage: EventStorage instance for closing orphaned events.
        """
        self.db = db
        self.event_storage = event_storage

        self.was_crash: bool = False
        self.orphans_closed: int = 0
        self.integrity_ok: bool = True
        self.recovery_complete: threading.Event = threading.Event()

    def start(self) -> None:
        """Start the recovery process in a background daemon thread."""
        thread = threading.Thread(target=self._run, name="boot-recovery", daemon=True)
        thread.start()

    def _run(self) -> None:
        """Run recovery, always signalling completion even on error."""
        try:
            self._detect_and_recover()
        except Exception as exc:
            log.error("boot_recovery_error", error=str(exc))
        finally:
            self.recovery_complete.set()

    def _detect_and_recover(self) -> None:
        """Perform crash detection and recovery steps."""
        if self.was_crash:
            self._run_integrity_check()
            self.orphans_closed = self.event_storage.close_orphaned_events()
            log.info(
                "crash_recovery_complete",
                integrity_ok=self.integrity_ok,
                orphans_closed=self.orphans_closed,
            )
        else:
            log.info("clean_boot_detected")

    def _run_integrity_check(self) -> bool:
        """Run PRAGMA quick_check and update integrity_ok.

        Returns:
            True if the database passed the integrity check.
        """
        conn = self.db._get_connection()
        cursor = conn.execute("PRAGMA quick_check")
        rows = [row[0] for row in cursor.fetchall()]

        if rows == ["ok"]:
            log.info("integrity_check_passed")
            self.integrity_ok = True
        else:
            log.error("integrity_check_failed", errors=rows)
            self.integrity_ok = False

        return self.integrity_ok
