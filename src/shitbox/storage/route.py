"""RouteStorage -- GPS polyline generator for Phase 19 day-page maps."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import structlog

from shitbox.storage.database import Database

log = structlog.get_logger(__name__)

# Sydney is UTC+10 year-round (QLD has no DST; NSW aligns for this use case).
_SYDNEY_OFFSET_HOURS = 10
_DEFAULT_TOLERANCE_M = 10.0
_LAT_METRES_PER_DEGREE = 111_000.0
_COORD_DECIMALS = 5  # ~1.1 m precision at the equator; saves ~15% JSON bytes


def _perpendicular_distance(
    pt: Tuple[float, float],
    line_start: Tuple[float, float],
    line_end: Tuple[float, float],
) -> float:
    """Planar perpendicular distance (metres) from pt to segment line_start to line_end.

    Uses rough lat/lng to metres conversion keyed to line_start latitude. Good
    enough at 10 m scale on unprojected WGS-84.
    """
    lng_m = _LAT_METRES_PER_DEGREE * math.cos(math.radians(line_start[0]))
    px = (pt[1] - line_start[1]) * lng_m
    py = (pt[0] - line_start[0]) * _LAT_METRES_PER_DEGREE
    sx = (line_end[1] - line_start[1]) * lng_m
    sy = (line_end[0] - line_start[0]) * _LAT_METRES_PER_DEGREE
    seg_len_sq = sx * sx + sy * sy
    if seg_len_sq == 0:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * sx + py * sy) / seg_len_sq))
    proj_x = t * sx
    proj_y = t * sy
    return math.hypot(px - proj_x, py - proj_y)


def douglas_peucker(
    points: List[Tuple[float, float]],
    tolerance_m: float = _DEFAULT_TOLERANCE_M,
) -> List[Tuple[float, float]]:
    """Ramer-Douglas-Peucker polyline simplification. Tolerance in metres.

    Iterative implementation using an explicit stack -- safe for large per-day
    input sizes without hitting Python's recursion limit.
    """
    if len(points) < 3:
        return list(points)

    # keep[i] = True means point i survives simplification
    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True

    # Stack holds (start_index, end_index) segments to examine
    stack: List[Tuple[int, int]] = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        dmax = 0.0
        index = start
        for i in range(start + 1, end):
            d = _perpendicular_distance(points[i], points[start], points[end])
            if d > dmax:
                dmax = d
                index = i
        if dmax > tolerance_m:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))

    return [pt for pt, k in zip(points, keep) if k]


def _sydney_date(ts_iso: str) -> str:
    """Return YYYY-MM-DD in Australia/Sydney (UTC+10) for an ISO-8601 timestamp string."""
    dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt + timedelta(hours=_SYDNEY_OFFSET_HOURS)
    return local.strftime("%Y-%m-%d")


class RouteStorage:
    """Generate simplified per-day polylines from GPS readings.

    Mirrors LogbookStorage: Database injected, generator methods return a
    JSON-serialisable value (the registry writes it).
    """

    def __init__(self, db: Database, tolerance_m: float = _DEFAULT_TOLERANCE_M) -> None:
        self.db = db
        self.tolerance_m = tolerance_m

    def generate_route_json(self) -> Dict[str, Any]:
        """Return route payload suitable for route.json.

        Shape::

            {
              "generated_at": "2026-05-03T14:23:17+00:00",
              "tolerance_m": 10.0,
              "days": {
                "2026-05-01": {"point_count": 412, "points": [[lat, lng], ...]},
                ...
              }
            }

        Column list is explicit -- never SELECT * -- to guarantee no future schema
        columns (cost_*, user_id, device_id) can leak into the payload.
        """
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT timestamp_utc, latitude, longitude FROM readings "
                "WHERE sensor_type = 'gps' "
                "AND latitude IS NOT NULL AND longitude IS NOT NULL "
                "ORDER BY timestamp_utc ASC"
            ).fetchall()

        by_day: Dict[str, List[Tuple[float, float]]] = {}
        for row in rows:
            ts, lat, lng = row[0], row[1], row[2]
            day = _sydney_date(ts)
            by_day.setdefault(day, []).append((float(lat), float(lng)))

        days_out: Dict[str, Dict[str, Any]] = {}
        total_before = 0
        total_after = 0
        for day, pts in by_day.items():
            total_before += len(pts)
            simp = douglas_peucker(pts, self.tolerance_m)
            total_after += len(simp)
            points_rounded = [
                [round(p[0], _COORD_DECIMALS), round(p[1], _COORD_DECIMALS)]
                for p in simp
            ]
            days_out[day] = {"point_count": len(points_rounded), "points": points_rounded}

        payload: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tolerance_m": self.tolerance_m,
            "days": days_out,
        }
        log.info(
            "route_json_generated",
            day_count=len(days_out),
            points_before=total_before,
            points_after=total_after,
            tolerance_m=self.tolerance_m,
        )
        return payload
