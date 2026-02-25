"""Tests for SQLite Database class."""

from shitbox.storage.database import Database


def test_synchronous_full(tmp_path):
    """BOOT-03: PRAGMA synchronous=FULL is set on every new connection."""
    db_path = tmp_path / "test_sync.db"
    db = Database(db_path)
    db.connect()
    try:
        conn = db._get_connection()
        cursor = conn.execute("PRAGMA synchronous")
        row = cursor.fetchone()
        # 2 = FULL
        assert row[0] == 2, f"Expected synchronous=2 (FULL), got {row[0]}"
    finally:
        db.close()
