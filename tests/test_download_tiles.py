"""Tests for tools.download_tiles — corridor MBTiles builder.

Phase 10 plan 10-00 was supposed to land these as RED stubs; plan 10-02 creates
them alongside the implementation because 10-00's Task 3 had not executed yet.
"""

from __future__ import annotations

import sqlite3


def test_lonlat_to_tile_known_values():
    """OSM slippy map tile maths sanity. Sydney at zoom 10 should land in a known cell."""
    from tools.download_tiles import lonlat_to_tile

    # Sydney: 151.2093, -33.8688 at zoom 10. Standard OSM slippy map formula:
    # (lon+180)/360 * 2^z = 942.106, asinh(tan(lat))/pi-based Y = 614.
    # Plan 10-00/10-02 drafted (939, 614) but the maths disagrees; 942 is
    # the correct value for the formula the plan itself specifies.
    x, y = lonlat_to_tile(151.2093, -33.8688, 10)
    assert (x, y) == (942, 614)


def test_corridor_envelope():
    """D-17: corridor builder includes tiles +/-20km of the route line."""
    from tools.download_tiles import build_corridor_tile_set

    waypoints = [(151.2093, -33.8688), (144.9631, -37.8136)]  # Sydney -> Melbourne
    tiles = build_corridor_tile_set(waypoints, zoom_min=5, zoom_max=6, corridor_km=20.0)
    assert len(tiles) > 0
    for t in tiles:
        assert len(t) == 3
        assert 5 <= t[0] <= 6


def test_idempotent(tmp_path):
    """D-19: re-running over an existing MBTiles must skip tiles already present."""
    from tools.download_tiles import already_present

    mb = tmp_path / "test.mbtiles"
    conn = sqlite3.connect(mb)
    conn.executescript(
        """
        CREATE TABLE tiles (
            zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB
        );
        CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);
        INSERT INTO tiles VALUES (5, 15, 20, x'89');
        """
    )
    conn.commit()
    conn.close()
    assert already_present(mb, 5, 15, 20) is True
    assert already_present(mb, 5, 15, 21) is False


def test_user_agent_set():
    """RESEARCH Pitfall 6: tile downloader must set a descriptive User-Agent."""
    import inspect

    import tools.download_tiles as dl

    src = inspect.getsource(dl)
    assert "shitbox-rally" in src.lower(), "User-Agent must identify the project"
    assert "User-Agent" in src or "user-agent" in src.lower()


def test_rate_limit_present():
    """RESEARCH Pitfall 6: must rate-limit fetches (sleep or token bucket)."""
    import inspect

    import tools.download_tiles as dl

    src = inspect.getsource(dl)
    assert "time.sleep" in src or "sleep(" in src, "Tile fetcher must rate-limit"
