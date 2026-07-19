"""DriverStorage — wraps driver_stints table for Phase 13."""
from __future__ import annotations

from typing import Any, Dict, List

import structlog

from shitbox.storage.database import Database

log = structlog.get_logger(__name__)

# Speed above which a GPS sample counts as "driving" (km/h). Filters out idling
# at lights and stationary GPS jitter so hours reflect real time at the wheel.
_MOVING_SPEED_KMH = 5.0


class DriverStorage:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set_driver(self, name: str) -> Dict[str, Any]:
        """Close any open stint and open a new one for ``name``.

        Returns {driver_name, started_at}.
        """
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE driver_stints SET ended_at = datetime('now') "
                "WHERE ended_at IS NULL"
            )
            cursor = conn.execute(
                "INSERT INTO driver_stints (driver_name, started_at, created_at) "
                "VALUES (?, datetime('now'), datetime('now'))",
                (name,),
            )
            row = conn.execute(
                "SELECT driver_name, started_at FROM driver_stints WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        # Update module-level state after successful commit
        from shitbox.dashboard import driver_state
        driver_state.set_active_driver(name)
        log.info("driver_set", driver_name=name)
        return {"driver_name": row["driver_name"], "started_at": row["started_at"]}

    def clear_driver(self) -> None:
        """Close current open stint without opening a new one (crew break)."""
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE driver_stints SET ended_at = datetime('now') "
                "WHERE ended_at IS NULL"
            )
        from shitbox.dashboard import driver_state
        driver_state.set_active_driver(None)
        log.info("driver_cleared")

    def get_stats(self) -> List[Dict[str, Any]]:
        """Return per-driver driving time + percentage, sorted by time descending.

        ``total_seconds`` is real time at the wheel: GPS samples moving faster
        than ``_MOVING_SPEED_KMH`` attributed to whichever driver's stint was
        active at the sample's timestamp. GPS logs at ~1 Hz, so one moving
        sample counts as one second.

        This deliberately does NOT use stint wall-clock. A stint runs from one
        driver change to the next, so wall-clock counted overnight camps and
        parked time — inflating a 7-day rally to ~240 h against ~56 h actually
        driven. Bounding by moving GPS samples also makes an unclosed (open)
        stint harmless: it can only accrue time while samples exist, not bleed
        to now().

        Stint windows are half-open ``[started_at, ended_at)`` so a sample on a
        driver-change boundary is counted once, against the incoming driver.

        Comparison is via ``julianday`` because the two columns store different
        formats: stint bounds are ``YYYY-MM-DD HH:MM:SS`` (from datetime('now'))
        while readings are ISO-8601 ``YYYY-MM-DDTHH:MM:SS+00:00``. A raw string
        compare breaks at the 'T'-vs-space at index 10 and misattributes samples;
        julianday parses both to real instants.
        """
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.driver_name,
                    COUNT(*) AS total_seconds
                FROM readings r
                JOIN driver_stints s
                  ON julianday(r.timestamp_utc) >= julianday(s.started_at)
                 AND julianday(r.timestamp_utc) <  julianday(
                         COALESCE(s.ended_at, datetime('now')))
                WHERE r.sensor_type = 'gps'
                  AND r.speed_kmh > ?
                GROUP BY s.driver_name
                ORDER BY total_seconds DESC
                """,
                (_MOVING_SPEED_KMH,),
            ).fetchall()
        total = sum((r["total_seconds"] or 0) for r in rows)
        n = len(rows)
        return [
            {
                "driver_name": r["driver_name"],
                "total_seconds": r["total_seconds"] or 0,
                "pct": round((r["total_seconds"] or 0) / total * 100, 1)
                if total > 0
                else (round(100.0 / n, 1) if n > 0 else 0.0),
            }
            for r in rows
        ]

    def get_driver_stats_payload(self) -> Dict[str, Any]:
        """Return sync export dict: {active_driver, drivers: [...]}.

        Used by the driver-stats JSON generator registered in plan 03.
        """
        from shitbox.dashboard import driver_state
        return {
            "active_driver": driver_state.get_active_driver(),
            "drivers": self.get_stats(),
        }
