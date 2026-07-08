"""LogbookStorage — notes and fuel stop persistence for Phase 12."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import structlog

from shitbox.dashboard import gps_state
from shitbox.storage.database import Database

log = structlog.get_logger(__name__)


class LogbookStorage:
    """Persist and query notes and fuel stops in the shared telemetry database.

    ``snapshot_fn`` is injected for testability. In production the engine
    wires in ``read_snapshot`` from ``shitbox.dashboard.snapshot``. Tests pass
    a lambda that returns a controlled dict so hardware is never touched.
    """

    def __init__(
        self,
        db: Database,
        snapshot_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self.db = db
        self._snapshot_fn = snapshot_fn

    def _snapshot(self) -> Dict[str, Any]:
        if self._snapshot_fn is not None:
            return self._snapshot_fn()
        from shitbox.dashboard.snapshot import read_snapshot
        return read_snapshot()

    def _resolve_gps(self) -> tuple[Optional[float], Optional[float], bool, int]:
        """Return (lat, lng, gps_stale, stale_seconds).

        Uses the live snapshot when a GPS fix is active. Falls back to the
        last-known position (set by the GPS collector via gps_state) when the
        snapshot has no fix. When neither source has a position, lat/lng are
        None and gps_stale is True.
        """
        snap = self._snapshot()
        fix = snap.get("gps_fix_mode") or 0
        if fix > 0 and snap.get("lat") is not None and snap.get("lng") is not None:
            return float(snap["lat"]), float(snap["lng"]), False, 0
        last = gps_state.get_last_known_position()
        if last is None:
            return None, None, True, 0
        lat, lng, fixed_at = last
        return lat, lng, True, int(time.time() - fixed_at)

    def create_note(self, body: str, event_id: Optional[int] = None) -> Dict[str, Any]:
        """Insert a note row and return its dict representation."""
        lat, lng, stale, _ = self._resolve_gps()
        ts = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO notes (timestamp_utc, body, event_id, lat, lng, gps_stale) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, body, event_id, lat, lng, 1 if stale else 0),
            )
            note_id = cur.lastrowid
        log.info("note_saved", note_id=note_id, gps_stale=stale, event_id=event_id)
        return {
            "id": note_id,
            "timestamp_utc": ts,
            "body": body,
            "event_id": event_id,
            "lat": lat,
            "lng": lng,
            "gps_stale": stale,
        }

    def create_fuel_stop(
        self,
        volume_litres: float,
        cost_aud: Optional[float] = None,
        odometer_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Insert a fuel stop row and return its dict representation.

        ``cost_aud`` is persisted locally for the driver's own records but is
        never surfaced in sync payloads or JSON generators (D-10).
        """
        lat, lng, stale, _ = self._resolve_gps()
        ts = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO fuel_stops "
                "(timestamp_utc, volume_litres, cost_aud, lat, lng, gps_stale, odometer_km) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, volume_litres, cost_aud, lat, lng, 1 if stale else 0, odometer_km),
            )
            stop_id = cur.lastrowid
        log.info("fuel_stop_saved", id=stop_id, volume=volume_litres, gps_stale=stale)
        return {
            "id": stop_id,
            "timestamp_utc": ts,
            "volume_litres": volume_litres,
            "lat": lat,
            "lng": lng,
            "gps_stale": stale,
            "odometer_km": odometer_km,
        }

    def list_fuel_stops(self) -> Dict[str, Any]:
        """Return all fuel stops with per-stop and cumulative efficiency.

        Returns a dict with:
          - stops: list of stop dicts with km_per_litre computed at query time
          - cumulative_km_per_litre: overall efficiency across all stops with
            valid odometer data, or None if not calculable
        """
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, timestamp_utc, volume_litres, cost_aud, lat, lng, gps_stale, "
                "odometer_km FROM fuel_stops ORDER BY timestamp_utc ASC"
            ).fetchall()
        cols = ["id", "timestamp_utc", "volume_litres", "cost_aud", "lat", "lng",
                "gps_stale", "odometer_km"]
        stops = [dict(zip(cols, r)) for r in rows]

        total_dist = 0.0
        total_vol = 0.0
        for i, s in enumerate(stops):
            if i == 0 or s["odometer_km"] is None or stops[i - 1]["odometer_km"] is None:
                s["km_per_litre"] = None
                continue
            dist = s["odometer_km"] - stops[i - 1]["odometer_km"]
            if dist > 0 and s["volume_litres"] > 0:
                s["km_per_litre"] = round(dist / s["volume_litres"], 2)
                total_dist += dist
                total_vol += s["volume_litres"]
            else:
                s["km_per_litre"] = None

        cumulative = round(total_dist / total_vol, 2) if total_vol > 0 else None
        return {"stops": stops, "cumulative_km_per_litre": cumulative}

    def list_notes(self) -> List[Dict[str, Any]]:
        """Return all notes ordered by timestamp ascending."""
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, timestamp_utc, body, event_id, lat, lng, gps_stale "
                "FROM notes ORDER BY timestamp_utc ASC"
            ).fetchall()
        cols = ["id", "timestamp_utc", "body", "event_id", "lat", "lng", "gps_stale"]
        return [dict(zip(cols, r)) for r in rows]

    def generate_notes_json(self) -> List[Dict[str, Any]]:
        """Return notes as a list of dicts suitable for JSON serialisation."""
        return self.list_notes()

    def generate_fuel_json(self) -> List[Dict[str, Any]]:
        """Return fuel stops for JSON serialisation with cost_aud hard-excluded (D-10).

        The explicit SELECT column list below is the enforcement mechanism —
        cost_aud is never fetched, so it can never appear in output regardless
        of future schema changes.
        """
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, timestamp_utc, volume_litres, lat, lng, gps_stale, odometer_km "
                "FROM fuel_stops ORDER BY timestamp_utc ASC"
            ).fetchall()
        cols = ["id", "timestamp_utc", "volume_litres", "lat", "lng", "gps_stale", "odometer_km"]
        stops = [dict(zip(cols, r)) for r in rows]

        # Add per-stop efficiency for consistency with /api/fuel response
        for i, s in enumerate(stops):
            if i == 0 or s["odometer_km"] is None or stops[i - 1]["odometer_km"] is None:
                s["km_per_litre"] = None
                continue
            dist = s["odometer_km"] - stops[i - 1]["odometer_km"]
            if dist > 0 and s["volume_litres"] > 0:
                s["km_per_litre"] = round(dist / s["volume_litres"], 2)
            else:
                s["km_per_litre"] = None

        return stops

    def create_breakdown(self, reason: Optional[str] = None) -> Dict[str, Any]:
        """Insert a breakdown row (the car died here) and return its dict.

        ``reason`` is optional — a breakdown still counts even if the driver
        was too busy swearing to type why.
        """
        reason = (reason or "").strip() or None
        lat, lng, stale, _ = self._resolve_gps()
        ts = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO breakdowns (timestamp_utc, reason, lat, lng, gps_stale) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, reason, lat, lng, 1 if stale else 0),
            )
            breakdown_id = cur.lastrowid
        log.info("breakdown_saved", breakdown_id=breakdown_id, gps_stale=stale)
        return {
            "id": breakdown_id,
            "timestamp_utc": ts,
            "reason": reason,
            "lat": lat,
            "lng": lng,
            "gps_stale": stale,
        }

    def list_breakdowns(self) -> List[Dict[str, Any]]:
        """Return all breakdowns ordered by timestamp ascending."""
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT id, timestamp_utc, reason, lat, lng, gps_stale "
                "FROM breakdowns ORDER BY timestamp_utc ASC"
            ).fetchall()
        cols = ["id", "timestamp_utc", "reason", "lat", "lng", "gps_stale"]
        return [dict(zip(cols, r)) for r in rows]

    def generate_breakdown_json(self) -> List[Dict[str, Any]]:
        """Return breakdowns as a list of dicts suitable for JSON serialisation."""
        return self.list_breakdowns()
