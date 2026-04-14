"""DriverStorage — wraps driver_stints table for Phase 13."""
from __future__ import annotations

from typing import Any, Dict, List

import structlog

from shitbox.storage.database import Database

log = structlog.get_logger(__name__)


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
        """Return per-driver time + percentage, sorted by time descending.

        Uses COALESCE so open stints count live time against now().
        """
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    driver_name,
                    SUM(CAST(
                        (julianday(COALESCE(ended_at, datetime('now'))) -
                         julianday(started_at)) * 86400
                    AS INTEGER)) AS total_seconds
                FROM driver_stints
                GROUP BY driver_name
                ORDER BY total_seconds DESC
                """
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
