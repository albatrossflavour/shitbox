"""One-shot offline tile downloader for the rally route corridor.

Builds an MBTiles SQLite file of CartoDB dark tiles covering a +/-20 km
corridor around the configured rally waypoints. Designed to run once on the
laptop before the rally (over fast home internet), then ship the resulting
.mbtiles file to the Pi so the dashboard can serve map tiles entirely
offline.

Run:

    python -m tools.download_tiles \\
        --config config/config.yaml \\
        --out /var/lib/shitbox/tiles/rally.mbtiles \\
        --zoom-min 5 --zoom-max 15

Re-running is idempotent: tiles already present in the MBTiles file are
skipped.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import time
from pathlib import Path
from typing import Iterable, List, Set, Tuple

import requests
import structlog

log = structlog.get_logger(__name__)

USER_AGENT = "shitbox-rally-tile-prefetch/1.0 (https://shit-of-theseus.com)"
# CartoDB dark — https://github.com/CartoDB/basemap-styles
TILE_URL_TEMPLATE = "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
RATE_LIMIT_SECONDS = 0.15  # ~6 req/s, polite for a public CDN


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[int, int]:
    """Return OSM slippy map XYZ tile coordinates for a lon/lat at a given zoom."""
    lat_rad = math.radians(lat)
    n = 1 << zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _interpolate_segment(
    a: Tuple[float, float],
    b: Tuple[float, float],
    step_km: float,
) -> Iterable[Tuple[float, float]]:
    """Yield (lon, lat) points along a segment roughly every ``step_km`` km."""
    lon1, lat1 = a
    lon2, lat2 = b
    # Crude equirectangular distance, plenty accurate at 1 km sampling.
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0)) * 111.32
    dy = (lat2 - lat1) * 110.57
    dist_km = math.hypot(dx, dy)
    n = max(1, int(dist_km / step_km))
    for i in range(n + 1):
        t = i / n
        yield (lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t)


def build_corridor_tile_set(
    waypoints: List[Tuple[float, float]],
    zoom_min: int,
    zoom_max: int,
    corridor_km: float = 20.0,
) -> Set[Tuple[int, int, int]]:
    """Walk waypoints, sample every ~1 km, expand +/-corridor_km, return XYZ tile set."""
    tiles: Set[Tuple[int, int, int]] = set()
    if len(waypoints) < 2:
        return tiles
    for i in range(len(waypoints) - 1):
        for lon, lat in _interpolate_segment(waypoints[i], waypoints[i + 1], step_km=1.0):
            dlat = corridor_km / 110.57
            dlon = corridor_km / (111.32 * max(0.01, math.cos(math.radians(lat))))
            for z in range(zoom_min, zoom_max + 1):
                x_a, y_a = lonlat_to_tile(lon - dlon, lat - dlat, z)
                x_b, y_b = lonlat_to_tile(lon + dlon, lat + dlat, z)
                for x in range(min(x_a, x_b), max(x_a, x_b) + 1):
                    for y in range(min(y_a, y_b), max(y_a, y_b) + 1):
                        tiles.add((z, x, y))
    return tiles


def already_present(mbtiles_path: Path, z: int, x: int, tms_y: int) -> bool:
    """Return True if the given TMS-y tile is already in the MBTiles file."""
    if not Path(mbtiles_path).exists():
        return False
    conn = sqlite3.connect(str(mbtiles_path))
    try:
        row = conn.execute(
            "SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=? LIMIT 1",
            (z, x, tms_y),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT);
        CREATE TABLE IF NOT EXISTS tiles (
            zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB
        );
        CREATE UNIQUE INDEX IF NOT EXISTS tile_index
            ON tiles (zoom_level, tile_column, tile_row);
        """
    )


def fetch_and_store(
    tiles: Iterable[Tuple[int, int, int]],
    mbtiles_path: Path,
) -> None:
    """Fetch each tile from the CartoDB CDN and INSERT it into the MBTiles file."""
    mbtiles_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(mbtiles_path))
    _ensure_schema(conn)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    fetched = skipped = errors = 0
    for z, x, y in tiles:
        tms_y = (1 << z) - 1 - y  # XYZ -> TMS
        if already_present(mbtiles_path, z, x, tms_y):
            skipped += 1
            continue
        url = TILE_URL_TEMPLATE.format(z=z, x=x, y=y)
        try:
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                errors += 1
                log.warning("tile_fetch_failed", z=z, x=x, y=y, status=r.status_code)
                time.sleep(RATE_LIMIT_SECONDS)
                continue
            conn.execute(
                "INSERT OR REPLACE INTO tiles "
                "(zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                (z, x, tms_y, r.content),
            )
            conn.commit()
            fetched += 1
        except Exception as exc:
            errors += 1
            log.warning("tile_fetch_exception", z=z, x=x, y=y, error=str(exc))
        time.sleep(RATE_LIMIT_SECONDS)
    conn.close()
    log.info("tile_download_done", fetched=fetched, skipped=skipped, errors=errors)


def _load_waypoints_from_config(config_path: Path) -> List[Tuple[float, float]]:
    import yaml

    with open(config_path) as fh:
        data = yaml.safe_load(fh)
    waypoints = (
        data.get("sensors", {}).get("gps", {}).get("route", {}).get("waypoints", [])
    )
    return [(float(w["lon"]), float(w["lat"])) for w in waypoints]


def main() -> None:
    p = argparse.ArgumentParser(
        description="Pre-download CartoDB dark MBTiles for the rally corridor",
    )
    p.add_argument("--config", default="config/config.yaml")
    p.add_argument("--out", required=True)
    p.add_argument("--zoom-min", type=int, default=5)
    p.add_argument("--zoom-max", type=int, default=15)
    p.add_argument("--corridor-km", type=float, default=20.0)
    args = p.parse_args()
    waypoints = _load_waypoints_from_config(Path(args.config))
    tiles = build_corridor_tile_set(
        waypoints, args.zoom_min, args.zoom_max, args.corridor_km
    )
    log.info(
        "tile_corridor_built",
        tile_count=len(tiles),
        zoom_min=args.zoom_min,
        zoom_max=args.zoom_max,
    )
    fetch_and_store(tiles, Path(args.out))


if __name__ == "__main__":
    main()
