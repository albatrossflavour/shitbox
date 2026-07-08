"""SQLite database management with WAL mode for crash resistance."""

import os
import socket
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from shitbox.storage.models import Reading, SensorType, SyncCursor
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


def _send_systemd_notify(state: str) -> None:
    """Best-effort sd_notify message. No-op outside systemd or on error.

    Lives here (rather than imported from engine) so the database module
    can pet the watchdog during long migrations without taking a
    dependency on the engine package.
    """
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.connect(notify_socket)
            s.sendall(state.encode())
        finally:
            s.close()
    except Exception:
        # Notification failures are non-fatal — the migration must continue.
        pass


def _notify_systemd_long_operation(extend_seconds: int) -> None:
    """Tell systemd to extend the watchdog/startup timeout by extend_seconds.

    EXTEND_TIMEOUT_USEC is the protocol-supported way to ask for extra
    runway during a long step (per sd_notify(3)). Combined with a parallel
    keepalive pinger, this stops a slow CREATE INDEX from tripping the
    runtime watchdog.
    """
    _send_systemd_notify(f"EXTEND_TIMEOUT_USEC={extend_seconds * 1_000_000}")
    log.info("systemd_extend_timeout_requested", seconds=extend_seconds)


def _systemd_watchdog_keepalive(stop: threading.Event, interval_seconds: float) -> None:
    """Background pinger that sends WATCHDOG=1 until stop is set.

    Runs alongside any blocking operation (e.g. a multi-minute index build)
    so the runtime watchdog stays satisfied. The interval should be well
    below WatchdogSec to leave margin.
    """
    while not stop.wait(interval_seconds):
        _send_systemd_notify("WATCHDOG=1")

# Database schema version for migrations
SCHEMA_VERSION = 14

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

    -- Power fields (INA219)
    bus_voltage_v REAL,
    current_ma REAL,
    power_mw REAL,

    -- Environment fields (BME680)
    pressure_hpa REAL,
    humidity_pct REAL,
    env_temp_celsius REAL,
    gas_resistance_ohms REAL,
    air_quality_score REAL,

    -- Light fields (VEML7700)
    lux REAL,

    -- Particulate fields (SEN0460)
    pm25_ug_m3 REAL,

    -- System fields (Pi health)
    cpu_temp_celsius REAL,
    cpu_percent REAL,
    disk_percent REAL,
    sync_backlog INTEGER,
    throttle_flags INTEGER,

    -- Metadata
    created_at TEXT DEFAULT (datetime('now'))
);

-- Trip state key-value store (for stage tracking)
CREATE TABLE IF NOT EXISTS trip_state (
    key TEXT PRIMARY KEY,
    value_real REAL,
    value_text TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Waypoints reached during a stage
CREATE TABLE IF NOT EXISTS waypoints_reached (
    waypoint_index INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    reached_at TEXT NOT NULL,
    lat_at_reach REAL,
    lon_at_reach REAL
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

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    body TEXT NOT NULL,
    event_id INTEGER,
    lat REAL,
    lng REAL,
    gps_stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fuel_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    volume_litres REAL NOT NULL,
    cost_aud REAL,
    lat REAL,
    lng REAL,
    gps_stale BOOLEAN NOT NULL DEFAULT 0,
    odometer_km REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS breakdowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    reason TEXT,
    lat REAL,
    lng REAL,
    gps_stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_readings_sensor_type ON readings(sensor_type);
CREATE INDEX IF NOT EXISTS idx_readings_id_sensor ON readings(id, sensor_type);
-- Covering index for "latest per sensor" queries (sensor freshness, dashboards).
-- (sensor_type, id) order lets SQLite seek by sensor_type then walk the index
-- in id-desc order to find the most recent row for a sensor in O(log n).
-- The pre-existing (id, sensor_type) index can't seek by sensor_type so it
-- degenerates into a full scan when a sensor stops emitting.
CREATE INDEX IF NOT EXISTS idx_readings_sensor_type_id ON readings(sensor_type, id);
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
            self._local.conn.execute("PRAGMA synchronous=FULL")
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

        if current_version < 2:
            self._migrate_to_v2(conn)

        if current_version < 3:
            self._migrate_to_v3(conn)

        if current_version < 4:
            self._migrate_to_v4(conn)

        if current_version < 5:
            self._migrate_to_v5(conn)

        if current_version < 6:
            self._migrate_to_v6(conn)

        if current_version < 7:
            self._migrate_to_v7(conn)

        if current_version < 8:
            self._migrate_to_v8(conn)

        if current_version < 9:
            self._migrate_to_v9(conn)

        if current_version < 10:
            self._migrate_to_v10(conn)

        if current_version < 11:
            self._migrate_to_v11(conn)

        if current_version < 12:
            self._migrate_to_v12(conn)

        if current_version < 13:
            self._migrate_to_v13(conn)

        if current_version < 14:
            self._migrate_to_v14(conn)

        if current_version < SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
            conn.commit()
            log.info("schema_updated", version=SCHEMA_VERSION)

        self._initialized = True
        log.info("database_connected", wal_mode=True)

    def _migrate_to_v2(self, conn: sqlite3.Connection) -> None:
        """Add power and environment sensor columns."""
        new_columns = [
            ("bus_voltage_v", "REAL"),
            ("current_ma", "REAL"),
            ("power_mw", "REAL"),
            ("pressure_hpa", "REAL"),
            ("humidity_pct", "REAL"),
            ("env_temp_celsius", "REAL"),
        ]
        for col_name, col_type in new_columns:
            try:
                conn.execute(f"ALTER TABLE readings ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v2", columns=[c[0] for c in new_columns])

    def _migrate_to_v3(self, conn: sqlite3.Connection) -> None:
        """Add gas resistance column for BME680 sensor."""
        try:
            conn.execute("ALTER TABLE readings ADD COLUMN gas_resistance_ohms REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v3", columns=["gas_resistance_ohms"])

    def _migrate_to_v4(self, conn: sqlite3.Connection) -> None:
        """Add health metric columns and trip/waypoint tables for Phase 4."""
        new_columns = [
            ("disk_percent", "REAL"),
            ("sync_backlog", "INTEGER"),
            ("throttle_flags", "INTEGER"),
        ]
        for col_name, col_type in new_columns:
            try:
                conn.execute(f"ALTER TABLE readings ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trip_state (
                key TEXT PRIMARY KEY,
                value_real REAL,
                value_text TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS waypoints_reached (
                waypoint_index INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                reached_at TEXT NOT NULL,
                lat_at_reach REAL,
                lon_at_reach REAL
            )
            """
        )
        conn.commit()
        log.info("migrated_to_v4", columns=[c[0] for c in new_columns])

    def _migrate_to_v5(self, conn: sqlite3.Connection) -> None:
        """Add cpu_percent column to system readings."""
        try:
            conn.execute("ALTER TABLE readings ADD COLUMN cpu_percent REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v5", columns=["cpu_percent"])

    def _migrate_to_v6(self, conn: sqlite3.Connection) -> None:
        """Add notes and fuel_stops tables for Phase 12 logbook feature."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                body TEXT NOT NULL,
                event_id INTEGER,
                lat REAL,
                lng REAL,
                gps_stale BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fuel_stops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                volume_litres REAL NOT NULL,
                cost_aud REAL,
                lat REAL,
                lng REAL,
                gps_stale BOOLEAN NOT NULL DEFAULT 0,
                odometer_km REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        log.info("migrated_to_v6", tables=["notes", "fuel_stops"])

    def _migrate_to_v7(self, conn: sqlite3.Connection) -> None:
        """Add driver_stints table for Phase 13 driver tracking.

        Note: there is no SQL events table in this project — events are stored
        as JSON files by EventStorage.save_event(). Driver attribution for
        events is handled via a driver_name kwarg on save_event() (see plan 03),
        not a column on any SQL table. Per D-04 interpretation confirmed in
        13-RESEARCH.md "Critical Note: Events Table Interpretation".
        """
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_stints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        log.info("migrated_to_v7", tables=["driver_stints"])

    def _migrate_to_v8(self, conn: sqlite3.Connection) -> None:
        """Add lux column for VEML7700 ambient light sensor."""
        try:
            conn.execute("ALTER TABLE readings ADD COLUMN lux REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v8", columns=["lux"])

    def _migrate_to_v9(self, conn: sqlite3.Connection) -> None:
        """Add sensor_id column for DS18B20 probe identification."""
        try:
            conn.execute("ALTER TABLE readings ADD COLUMN sensor_id TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v9", columns=["sensor_id"])

    def _migrate_to_v10(self, conn: sqlite3.Connection) -> None:
        """Add pm25_ug_m3 column for SEN0460 particulate sensor."""
        try:
            conn.execute("ALTER TABLE readings ADD COLUMN pm25_ug_m3 REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v10", columns=["pm25_ug_m3"])

    def _migrate_to_v13(self, conn: sqlite3.Connection) -> None:
        """Add air_quality_score column for the BME680 0-100 IAQ score.

        A plain nullable ADD COLUMN — metadata-only in SQLite, effectively
        instant regardless of table size (unlike the v12 index build, which
        scanned every row). Existing rows read back NULL for this column.
        """
        try:
            conn.execute("ALTER TABLE readings ADD COLUMN air_quality_score REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
        log.info("migrated_to_v13", columns=["air_quality_score"])

    def _migrate_to_v14(self, conn: sqlite3.Connection) -> None:
        """Add breakdowns table — logbook of times the car died on us."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS breakdowns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                reason TEXT,
                lat REAL,
                lng REAL,
                gps_stale BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        log.info("migrated_to_v14", tables=["breakdowns"])

    def _migrate_to_v11(self, conn: sqlite3.Connection) -> None:
        """Add tpms_readings table for Phase 28 TPMS integration.

        A dedicated table parallel to notes / fuel_stops / driver_stints —
        the readings table is already 30+ columns wide and TPMS frames have
        six TPMS-specific fields nobody else queries. See Phase 28
        RESEARCH.md Pattern 4 for the rationale.
        """
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tpms_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                wheel TEXT NOT NULL,
                pressure_psi REAL NOT NULL,
                temperature_c REAL NOT NULL,
                status INTEGER,
                raw_pressure_kpa REAL NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tpms_timestamp "
            "ON tpms_readings(timestamp_utc)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tpms_wheel ON tpms_readings(wheel)"
        )
        conn.commit()
        log.info("migrated_to_v11", tables=["tpms_readings"])

    def _migrate_to_v12(self, conn: sqlite3.Connection) -> None:
        """Add (sensor_type, id) covering index for 'latest per sensor' queries.

        The pre-existing (id, sensor_type) index sorts by id first, so SQLite
        cannot seek to a given sensor_type — it degenerates into a full scan
        when a sensor stops emitting (the query has to walk back through
        millions of rows hunting for the dead sensor's most recent entry).
        The new index makes that lookup O(log n) regardless of sensor liveness.

        First-time build on a 20M-row table is slow (multiple minutes on a Pi
        with SD-card storage) but happens once at daemon startup after the
        upgrade. Sends EXTEND_TIMEOUT_USEC=300s to systemd up-front so the
        watchdog doesn't kill us mid-build (and a parallel pinger thread
        keeps WATCHDOG=1 flowing in case the long-startup window converts to
        a runtime watchdog after sd_notify(READY=1) fires).
        """
        log.info(
            "migrate_v12_starting",
            note="building covering index, may take several minutes on large DBs",
        )
        _notify_systemd_long_operation(extend_seconds=300)
        stop_pinger = threading.Event()
        pinger = threading.Thread(
            target=_systemd_watchdog_keepalive,
            args=(stop_pinger, 5.0),
            daemon=True,
            name="migrate-v12-watchdog",
        )
        pinger.start()
        try:
            t0 = time.monotonic()
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_sensor_type_id "
                "ON readings(sensor_type, id)"
            )
            conn.commit()
            elapsed = time.monotonic() - t0
        finally:
            stop_pinger.set()
            pinger.join(timeout=2.0)
        log.info(
            "migrated_to_v12",
            index="idx_readings_sensor_type_id",
            elapsed_seconds=round(elapsed, 1),
        )

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
                    temp_celsius, sensor_id,
                    bus_voltage_v, current_ma, power_mw,
                    pressure_hpa, humidity_pct, env_temp_celsius,
                    gas_resistance_ohms,
                    air_quality_score,
                    lux,
                    pm25_ug_m3,
                    cpu_temp_celsius, cpu_percent, disk_percent, sync_backlog, throttle_flags
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
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
                    reading.sensor_id,
                    reading.bus_voltage_v,
                    reading.current_ma,
                    reading.power_mw,
                    reading.pressure_hpa,
                    reading.humidity_pct,
                    reading.env_temp_celsius,
                    reading.gas_resistance_ohms,
                    reading.air_quality_score,
                    reading.lux,
                    reading.pm25_ug_m3,
                    reading.cpu_temp_celsius,
                    reading.cpu_percent,
                    reading.disk_percent,
                    reading.sync_backlog,
                    reading.throttle_flags,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def insert_tpms_reading(
        self,
        *,
        timestamp_utc: str,
        sensor_id: str,
        wheel: str,
        pressure_psi: float,
        temperature_c: float,
        status: Optional[int],
        raw_pressure_kpa: float,
    ) -> int:
        """Insert a single TPMS frame into tpms_readings; return lastrowid.

        Keyword-only args mirror the rtl_433 frame shape (id -> sensor_id,
        pressure_kPa -> raw_pressure_kpa). Wheel is the canonical position
        string (e.g. 'front-driver') resolved by TPMSService before insert.
        """
        conn = self._get_connection()
        with self._write_lock:
            cursor = conn.execute(
                """
                INSERT INTO tpms_readings (
                    timestamp_utc, sensor_id, wheel,
                    pressure_psi, temperature_c, status, raw_pressure_kpa
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_utc,
                    sensor_id,
                    wheel,
                    pressure_psi,
                    temperature_c,
                    status,
                    raw_pressure_kpa,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_unsynced_tpms_readings(self, batch_size: int = 1000) -> list[dict]:
        """Return tpms_readings rows past the 'prometheus_tpms' cursor.

        Mirrors get_unsynced_readings but selects from tpms_readings and
        returns raw dicts (no Reading model — TPMS rows have a different
        shape and live alongside notes/fuel_stops as plain dicts).
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT last_synced_id FROM sync_cursors WHERE cursor_name = ?",
            ("prometheus_tpms",),
        )
        row = cursor.fetchone()
        last_id = row["last_synced_id"] if row else 0
        rows = conn.execute(
            "SELECT * FROM tpms_readings WHERE id > ? ORDER BY id LIMIT ?",
            (last_id, batch_size),
        ).fetchall()
        return [dict(r) for r in rows]

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
                            temp_celsius, sensor_id,
                            bus_voltage_v, current_ma, power_mw,
                            pressure_hpa, humidity_pct, env_temp_celsius,
                            gas_resistance_ohms,
                            air_quality_score,
                            lux,
                            pm25_ug_m3,
                            cpu_temp_celsius, cpu_percent, disk_percent,
                            sync_backlog, throttle_flags
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
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
                            reading.sensor_id,
                            reading.bus_voltage_v,
                            reading.current_ma,
                            reading.power_mw,
                            reading.pressure_hpa,
                            reading.humidity_pct,
                            reading.env_temp_celsius,
                            reading.gas_resistance_ohms,
                            reading.air_quality_score,
                            reading.lux,
                            reading.pm25_ug_m3,
                            reading.cpu_temp_celsius,
                            reading.cpu_percent,
                            reading.disk_percent,
                            reading.sync_backlog,
                            reading.throttle_flags,
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

    def get_sync_backlog_time_range(
        self, cursor_name: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Get oldest and newest timestamps of unsynced readings.

        Args:
            cursor_name: Name of sync cursor.

        Returns:
            Tuple of (oldest_timestamp, newest_timestamp) as ISO strings,
            or (None, None) if no backlog.
        """
        cursor_obj = self.get_sync_cursor(cursor_name)
        conn = self._get_connection()
        cursor = conn.execute(
            """SELECT MIN(timestamp_utc) as oldest,
                      MAX(timestamp_utc) as newest
               FROM readings WHERE id > ?""",
            (cursor_obj.last_synced_id,),
        )
        row = cursor.fetchone()
        if row and row["oldest"]:
            return row["oldest"], row["newest"]
        return None, None

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

    def get_fuel_summary(self) -> dict:
        """Return aggregate fuel stats: count, total_litres, efficiency_kml."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(volume_litres), 0) as total_litres "
            "FROM fuel_stops"
        ).fetchone()
        count = row["cnt"]
        total_litres = row["total_litres"]

        odo_row = conn.execute(
            "SELECT MAX(odometer_km) as hi, MIN(odometer_km) as lo "
            "FROM fuel_stops WHERE odometer_km IS NOT NULL"
        ).fetchone()
        efficiency = 0.0
        if (
            odo_row
            and odo_row["hi"] is not None
            and odo_row["lo"] is not None
            and total_litres > 0
        ):
            efficiency = round((odo_row["hi"] - odo_row["lo"]) / total_litres, 3)

        return {"count": count, "total_litres": total_litres, "efficiency_kml": efficiency}

    def get_notes_count(self) -> int:
        """Return total number of field notes."""
        row = self._get_connection().execute(
            "SELECT COUNT(*) as cnt FROM notes"
        ).fetchone()
        return row["cnt"]

    def get_active_driver_name(self) -> Optional[str]:
        """Return the name of the currently active driver, or None."""
        row = self._get_connection().execute(
            "SELECT driver_name FROM driver_stints WHERE ended_at IS NULL LIMIT 1"
        ).fetchone()
        return row["driver_name"] if row else None

    def get_driver_time_seconds(self) -> dict:
        """Return total drive time in seconds per driver, keyed by driver name."""
        rows = self._get_connection().execute(
            """
            SELECT driver_name,
                   SUM(CAST(
                       (julianday(COALESCE(ended_at, datetime('now'))) -
                        julianday(started_at)) * 86400
                   AS INTEGER)) AS total_seconds
            FROM driver_stints
            GROUP BY driver_name
            """
        ).fetchall()
        return {r["driver_name"]: float(r["total_seconds"] or 0) for r in rows}

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
        keys = row.keys()
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
            sensor_id=row["sensor_id"] if "sensor_id" in keys else None,
            bus_voltage_v=row["bus_voltage_v"] if "bus_voltage_v" in keys else None,
            current_ma=row["current_ma"] if "current_ma" in keys else None,
            power_mw=row["power_mw"] if "power_mw" in keys else None,
            pressure_hpa=row["pressure_hpa"] if "pressure_hpa" in keys else None,
            humidity_pct=row["humidity_pct"] if "humidity_pct" in keys else None,
            env_temp_celsius=row["env_temp_celsius"] if "env_temp_celsius" in keys else None,
            gas_resistance_ohms=(
                row["gas_resistance_ohms"] if "gas_resistance_ohms" in keys else None
            ),
            air_quality_score=(
                row["air_quality_score"] if "air_quality_score" in keys else None
            ),
            cpu_temp_celsius=row["cpu_temp_celsius"] if "cpu_temp_celsius" in keys else None,
            cpu_percent=row["cpu_percent"] if "cpu_percent" in keys else None,
            disk_percent=row["disk_percent"] if "disk_percent" in keys else None,
            sync_backlog=row["sync_backlog"] if "sync_backlog" in keys else None,
            throttle_flags=row["throttle_flags"] if "throttle_flags" in keys else None,
            lux=row["lux"] if "lux" in keys else None,
            pm25_ug_m3=row["pm25_ug_m3"] if "pm25_ug_m3" in keys else None,
        )

    def get_trip_state(self, key: str) -> Optional[float]:
        """Get a numeric trip state value.

        Args:
            key: State key name.

        Returns:
            Stored float value, or None if key does not exist.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT value_real FROM trip_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value_real"] if row else None

    def get_trip_state_text(self, key: str) -> Optional[str]:
        """Get a text trip state value.

        Args:
            key: State key name.

        Returns:
            Stored text value, or None if key does not exist.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT value_text FROM trip_state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value_text"] if row else None

    def set_trip_state(self, key: str, value: float) -> None:
        """Upsert a numeric trip state value.

        Args:
            key: State key name.
            value: Float value to store.
        """
        conn = self._get_connection()
        with self._write_lock:
            conn.execute(
                """
                INSERT INTO trip_state (key, value_real, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value_real = excluded.value_real,
                    updated_at = datetime('now')
                """,
                (key, value),
            )
            conn.commit()

    def set_trip_state_text(self, key: str, value: str) -> None:
        """Upsert a text trip state value.

        Args:
            key: State key name.
            value: Text value to store.
        """
        conn = self._get_connection()
        with self._write_lock:
            conn.execute(
                """
                INSERT INTO trip_state (key, value_text, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value_text = excluded.value_text,
                    updated_at = datetime('now')
                """,
                (key, value),
            )
            conn.commit()

    def record_waypoint_reached(
        self, waypoint_index: int, name: str, lat: float, lon: float
    ) -> None:
        """Record that a waypoint was reached during the current stage.

        Uses INSERT OR IGNORE so re-crossing a waypoint boundary is idempotent.

        Args:
            waypoint_index: Zero-based index into the waypoints list.
            name: Human-readable waypoint name.
            lat: Latitude at the moment of crossing.
            lon: Longitude at the moment of crossing.
        """
        conn = self._get_connection()
        with self._write_lock:
            conn.execute(
                """
                INSERT OR IGNORE INTO waypoints_reached
                    (waypoint_index, name, reached_at, lat_at_reach, lon_at_reach)
                VALUES (?, ?, datetime('now'), ?, ?)
                """,
                (waypoint_index, name, lat, lon),
            )
            conn.commit()

    def get_reached_waypoints(self) -> set[int]:
        """Get the set of waypoint indices already reached.

        Returns:
            Set of zero-based waypoint indices.
        """
        conn = self._get_connection()
        cursor = conn.execute("SELECT waypoint_index FROM waypoints_reached")
        return {row["waypoint_index"] for row in cursor.fetchall()}

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

    def checkpoint_wal(self) -> None:
        """Run a TRUNCATE WAL checkpoint and log only when pages were checkpointed.

        Uses TRUNCATE mode so the WAL file is zeroed after a successful
        full checkpoint. Silent when the WAL was already clean (no pages to
        checkpoint). Logs at INFO level only when work was actually done.
        """
        conn = self._get_connection()
        with self._write_lock:
            cursor = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            row = cursor.fetchone()
        if row is not None and row[2] > 0:
            log.info("wal_checkpoint_completed", pages_checkpointed=row[2], pages_in_wal=row[1])
