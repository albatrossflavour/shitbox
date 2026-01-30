"""SQLite database management with WAL mode for crash resistance."""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from shitbox.storage.models import Reading, SensorType, SyncCursor
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Database schema version for migrations
SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Main telemetry readings table
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    sensor_type TEXT NOT NULL,

    -- GPS fields
    latitude REAL,
    longitude REAL,
    altitude_m REAL,
    speed_kmh REAL,
    heading_deg REAL,
    satellites INTEGER,
    fix_quality INTEGER,

    -- IMU fields
    accel_x REAL,
    accel_y REAL,
    accel_z REAL,
    gyro_x REAL,
    gyro_y REAL,
    gyro_z REAL,

    -- Temperature fields
    temp_celsius REAL,

    -- System fields (Pi health)
    cpu_temp_celsius REAL,

    -- Metadata
    created_at TEXT DEFAULT (datetime('now'))
);

-- Sync cursor tracking
CREATE TABLE IF NOT EXISTS sync_cursors (
    cursor_name TEXT PRIMARY KEY,
    last_synced_id INTEGER DEFAULT 0,
    last_synced_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_readings_sensor_type ON readings(sensor_type);
CREATE INDEX IF NOT EXISTS idx_readings_id_sensor ON readings(id, sensor_type);
"""


class Database:
    """SQLite database manager with WAL mode for crash resistance.

    Thread-safe: uses thread-local connections so each thread gets its own.
    """

    def __init__(self, db_path: str | Path):
        """Initialise database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._initialized = False

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,  # Wait up to 30s for locks
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row

            # Configure for crash resistance and performance
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA wal_autocheckpoint=1000")
            self._local.conn.execute("PRAGMA busy_timeout=30000")

        return self._local.conn

    def connect(self) -> None:
        """Initialise database schema."""
        log.info("connecting_to_database", path=str(self.db_path))

        conn = self._get_connection()

        # Initialise schema
        conn.executescript(SCHEMA_SQL)

        # Check/set schema version
        cursor = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        row = cursor.fetchone()
        current_version = row["version"] if row else 0

        if current_version < SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
            conn.commit()
            log.info("schema_initialised", version=SCHEMA_VERSION)

        self._initialized = True
        log.info("database_connected", wal_mode=True)

    def close(self) -> None:
        """Close database connection for current thread."""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._local.conn.close()
            self._local.conn = None
            log.info("database_closed")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for explicit transactions.

        Usage:
            with db.transaction() as conn:
                conn.execute(...)
        """
        conn = self._get_connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def insert_reading(self, reading: Reading) -> int:
        """Insert a single reading into the database.

        Args:
            reading: Reading to insert.

        Returns:
            ID of inserted row.
        """
        conn = self._get_connection()
        with self._write_lock:
            cursor = conn.execute(
                """
                INSERT INTO readings (
                    timestamp_utc, sensor_type,
                    latitude, longitude, altitude_m, speed_kmh, heading_deg,
                    satellites, fix_quality,
                    accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z,
                    temp_celsius, cpu_temp_celsius
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reading.timestamp_utc.isoformat(),
                    reading.sensor_type.value,
                    reading.latitude,
                    reading.longitude,
                    reading.altitude_m,
                    reading.speed_kmh,
                    reading.heading_deg,
                    reading.satellites,
                    reading.fix_quality,
                    reading.accel_x,
                    reading.accel_y,
                    reading.accel_z,
                    reading.gyro_x,
                    reading.gyro_y,
                    reading.gyro_z,
                    reading.temp_celsius,
                    reading.cpu_temp_celsius,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def insert_readings_batch(self, readings: list[Reading]) -> int:
        """Insert multiple readings in a single transaction.

        Args:
            readings: List of readings to insert.

        Returns:
            Number of rows inserted.
        """
        if not readings:
            return 0

        conn = self._get_connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for reading in readings:
                    conn.execute(
                        """
                        INSERT INTO readings (
                            timestamp_utc, sensor_type,
                            latitude, longitude, altitude_m, speed_kmh, heading_deg,
                            satellites, fix_quality,
                            accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z,
                            temp_celsius, cpu_temp_celsius
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            reading.timestamp_utc.isoformat(),
                            reading.sensor_type.value,
                            reading.latitude,
                            reading.longitude,
                            reading.altitude_m,
                            reading.speed_kmh,
                            reading.heading_deg,
                            reading.satellites,
                            reading.fix_quality,
                            reading.accel_x,
                            reading.accel_y,
                            reading.accel_z,
                            reading.gyro_x,
                            reading.gyro_y,
                            reading.gyro_z,
                            reading.temp_celsius,
                            reading.cpu_temp_celsius,
                        ),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return len(readings)

    def get_unsynced_readings(
        self,
        cursor_name: str,
        batch_size: int = 1000,
        sensor_type: Optional[SensorType] = None,
    ) -> list[Reading]:
        """Get readings that haven't been synced yet.

        Args:
            cursor_name: Name of sync cursor (e.g., 'mqtt', 'prometheus').
            batch_size: Maximum number of readings to return.
            sensor_type: Optional filter by sensor type.

        Returns:
            List of unsynced readings.
        """
        conn = self._get_connection()

        # Get current cursor position
        cursor = conn.execute(
            "SELECT last_synced_id FROM sync_cursors WHERE cursor_name = ?",
            (cursor_name,),
        )
        row = cursor.fetchone()
        last_id = row["last_synced_id"] if row else 0

        # Build query
        query = "SELECT * FROM readings WHERE id > ?"
        params: list = [last_id]

        if sensor_type:
            query += " AND sensor_type = ?"
            params.append(sensor_type.value)

        query += " ORDER BY id LIMIT ?"
        params.append(batch_size)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        return [self._row_to_reading(row) for row in rows]

    def update_sync_cursor(self, cursor_name: str, last_id: int) -> None:
        """Update sync cursor after successful sync.

        Args:
            cursor_name: Name of sync cursor.
            last_id: ID of last successfully synced reading.
        """
        conn = self._get_connection()
        with self._write_lock:
            conn.execute(
                """
                INSERT INTO sync_cursors (cursor_name, last_synced_id, last_synced_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(cursor_name) DO UPDATE SET
                    last_synced_id = excluded.last_synced_id,
                    last_synced_at = datetime('now'),
                    updated_at = datetime('now')
                """,
                (cursor_name, last_id),
            )
            conn.commit()
        log.debug("sync_cursor_updated", cursor=cursor_name, last_id=last_id)

    def get_sync_cursor(self, cursor_name: str) -> SyncCursor:
        """Get current sync cursor position.

        Args:
            cursor_name: Name of sync cursor.

        Returns:
            SyncCursor with current position.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM sync_cursors WHERE cursor_name = ?", (cursor_name,)
        )
        row = cursor.fetchone()

        if row:
            return SyncCursor(
                cursor_name=row["cursor_name"],
                last_synced_id=row["last_synced_id"],
                last_synced_at=(
                    datetime.fromisoformat(row["last_synced_at"])
                    if row["last_synced_at"]
                    else None
                ),
            )
        return SyncCursor(cursor_name=cursor_name)

    def get_sync_backlog_count(self, cursor_name: str) -> int:
        """Get count of unsynced readings for a cursor.

        Args:
            cursor_name: Name of sync cursor.

        Returns:
            Number of unsynced readings.
        """
        cursor_obj = self.get_sync_cursor(cursor_name)
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM readings WHERE id > ?",
            (cursor_obj.last_synced_id,),
        )
        row = cursor.fetchone()
        return row["count"] if row else 0

    def get_reading_count(self, sensor_type: Optional[SensorType] = None) -> int:
        """Get total count of readings.

        Args:
            sensor_type: Optional filter by sensor type.

        Returns:
            Total count of readings.
        """
        conn = self._get_connection()
        if sensor_type:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM readings WHERE sensor_type = ?",
                (sensor_type.value,),
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) as count FROM readings")

        row = cursor.fetchone()
        return row["count"] if row else 0

    def get_latest_reading(self, sensor_type: SensorType) -> Optional[Reading]:
        """Get the most recent reading for a sensor type.

        Args:
            sensor_type: Type of sensor.

        Returns:
            Latest reading or None.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM readings
            WHERE sensor_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (sensor_type.value,),
        )
        row = cursor.fetchone()
        return self._row_to_reading(row) if row else None

    def _row_to_reading(self, row: sqlite3.Row) -> Reading:
        """Convert a database row to a Reading object."""
        return Reading(
            id=row["id"],
            timestamp_utc=datetime.fromisoformat(row["timestamp_utc"]).replace(
                tzinfo=timezone.utc
            ),
            sensor_type=SensorType(row["sensor_type"]),
            latitude=row["latitude"],
            longitude=row["longitude"],
            altitude_m=row["altitude_m"],
            speed_kmh=row["speed_kmh"],
            heading_deg=row["heading_deg"],
            satellites=row["satellites"],
            fix_quality=row["fix_quality"],
            accel_x=row["accel_x"],
            accel_y=row["accel_y"],
            accel_z=row["accel_z"],
            gyro_x=row["gyro_x"],
            gyro_y=row["gyro_y"],
            gyro_z=row["gyro_z"],
            temp_celsius=row["temp_celsius"],
            cpu_temp_celsius=row["cpu_temp_celsius"] if "cpu_temp_celsius" in row.keys() else None,
        )

    def vacuum(self) -> None:
        """Reclaim disk space by vacuuming the database."""
        log.info("vacuuming_database")
        conn = self._get_connection()
        with self._write_lock:
            conn.execute("VACUUM")

    def checkpoint(self) -> None:
        """Force a WAL checkpoint."""
        conn = self._get_connection()
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
