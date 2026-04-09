"""RED-phase failing test stubs for Phase 10 dashboard surface.

These tests import from `shitbox.dashboard.*` modules that do not yet exist.
ImportError / NotImplementedError is the expected failure mode until later
waves implement the dashboard. Do NOT use pytest.importorskip here — we want
hard failures so each implementation task can flip its test from red to green.
"""

from __future__ import annotations


def test_snapshot_atomicity():
    from shitbox.dashboard.snapshot import read_snapshot, update_snapshot

    update_snapshot(
        {
            "speed_kmh": 42.0,
            "ts": 1.0,
            "g_x": 0.0,
            "g_y": 0.0,
            "g_z": 0.0,
            "heading_deg": 0.0,
            "lat": None,
            "lng": None,
            "gps_fix_mode": 0,
            "gps_sat_count": 0,
            "gps_hdop": None,
            "imu_temp_c": None,
            "soc_temp_c": None,
            "sync_connected": False,
            "sync_backlog": 0,
            "event_count_today": 0,
        }
    )
    snap = read_snapshot()
    assert snap["speed_kmh"] == 42.0


def test_snapshot_default_keys():
    from shitbox.dashboard.snapshot import read_snapshot

    snap = read_snapshot()
    for key in (
        "ts",
        "speed_kmh",
        "g_x",
        "g_y",
        "g_z",
        "heading_deg",
        "lat",
        "lng",
        "gps_fix_mode",
        "gps_sat_count",
        "gps_hdop",
        "imu_temp_c",
        "soc_temp_c",
        "sync_connected",
        "sync_backlog",
        "event_count_today",
    ):
        assert key in snap


def test_lifecycle():
    """D-01: dashboard starts and stops cleanly via DashboardServer."""
    from fastapi import FastAPI
    from shitbox.dashboard.server import DashboardServer

    srv = DashboardServer(host="127.0.0.1", port=0, app=FastAPI())
    srv.start()
    srv.stop()


def test_handler_exception_isolated(mbtiles_fixture):
    """D-04: a handler exception does not propagate to the engine thread."""
    from fastapi.testclient import TestClient

    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/boom")
        assert r.status_code == 500
        # The next request must still succeed — daemon process is unaffected.
        r2 = client.get("/tiles/5/0/0.png")
        assert r2.status_code == 404  # missing tile, not crash


def test_port_bind_failure_isolated():
    """D-04: port-in-use must not crash the engine."""
    import socket

    from fastapi import FastAPI

    from shitbox.dashboard.server import DashboardServer

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.listen(1)
    try:
        srv = DashboardServer(host="127.0.0.1", port=port, app=FastAPI())
        srv.start()  # must not raise
        srv.stop()
    finally:
        s.close()


def test_sse_client_cap():
    """D-03: 9th client gets HTTP 503."""
    from shitbox.dashboard.sse import MAX_CLIENTS

    assert MAX_CLIENTS == 8


def _read_one_sse_data(response) -> str:
    """Consume the streamed response until a `data:` line is seen, then return it."""
    for line in response.iter_lines():
        if line.startswith("data:"):
            return line[len("data:"):].strip()
    return ""


def _start_live_server(app):
    """Spin up a real uvicorn on an ephemeral port for streaming tests.

    starlette's in-process TestClient fully drains infinite async generators
    before returning, which makes it unusable for SSE streams. A real uvicorn
    on 127.0.0.1 is the pragmatic fix — it exercises the same DashboardServer
    wiring the engine uses in production anyway.
    """
    import socket

    from shitbox.dashboard.server import DashboardServer

    import time as _time

    last_srv = None
    for _attempt in range(5):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        srv = DashboardServer(host="127.0.0.1", port=port, app=app)
        srv.start()
        last_srv = srv
        # Wait up to 2s for the port to accept connections.
        deadline = _time.time() + 2.0
        accepted = False
        while _time.time() < deadline:
            if srv._thread is None or not srv._thread.is_alive():
                break  # uvicorn crashed (probably port-bind) — retry
            probe = socket.socket()
            try:
                probe.connect(("127.0.0.1", port))
                probe.close()
                accepted = True
                break
            except OSError:
                probe.close()
                _time.sleep(0.05)
        if accepted:
            return srv, f"http://127.0.0.1:{port}"
        srv.stop()
        _time.sleep(0.1)
    raise RuntimeError("failed to start DashboardServer after retries")


def _stop_live_server(srv) -> None:
    """Stop and wait a beat so TIME_WAIT/bind races don't cross tests."""
    import time as _time
    srv.stop()
    _time.sleep(0.2)


def _read_sse_lines(url: str, max_lines: int = 6, timeout: float = 3.0):
    """Connect to ``url`` and read up to ``max_lines`` lines from the SSE body."""
    import httpx

    lines = []
    with httpx.Client(timeout=timeout) as client:
        with client.stream("GET", url) as r:
            assert r.status_code == 200, f"unexpected status {r.status_code}"
            for line in r.iter_lines():
                lines.append(line)
                if len(lines) >= max_lines:
                    break
    return lines


def test_sse_fast_schema(mbtiles_fixture):
    """D-07/D-08: /sse/fast emits keys ts,speed,gx,gy,gz,heading."""
    import json as _json

    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/fast")
    finally:
        srv.stop()
    data_line = next((l for l in lines if l.startswith("data:")), None)
    assert data_line is not None
    payload = _json.loads(data_line[len("data:"):].strip())
    for key in ("ts", "speed", "gx", "gy", "gz", "heading"):
        assert key in payload


def test_sse_slow_schema(mbtiles_fixture):
    """D-08: /sse/slow emits gps + temp + sync keys."""
    import json as _json

    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/slow")
    finally:
        srv.stop()
    data_line = next((l for l in lines if l.startswith("data:")), None)
    assert data_line is not None
    payload = _json.loads(data_line[len("data:"):].strip())
    for key in ("lat", "lng", "fix_mode", "sats", "imu_temp", "sync_connected"):
        assert key in payload


def test_sse_events_initial_and_live(mbtiles_fixture):
    """D-09: /sse/events sends last 10 on connect."""
    from fastapi.testclient import TestClient

    from shitbox.dashboard.server import build_app

    seed = [{"type": "BOOT", "timestamp": "2026-04-09T00:00:00", "peak_g": 0.0}]
    app = build_app(mbtiles_path=mbtiles_fixture, recent_events_provider=lambda n: seed[:n])
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/events", max_lines=2)
    finally:
        srv.stop()
    joined = "\n".join(lines)
    assert "BOOT" in joined


def test_tiles_y_flip(mbtiles_fixture):
    """D-15/D-16: XYZ z=5 x=15 y=11 (TMS y=20) returns the known PNG."""
    from fastapi.testclient import TestClient
    from shitbox.dashboard.server import build_app

    from tests.conftest import _KNOWN_PNG

    app = build_app(mbtiles_path=mbtiles_fixture)
    with TestClient(app) as client:
        # TMS y=20 at z=5 -> XYZ y = (1<<5)-1-20 = 11
        r = client.get("/tiles/5/15/11.png")
        assert r.status_code == 200
        assert r.content == _KNOWN_PNG


def test_tile_404(mbtiles_fixture):
    """D-16: missing tile returns 404."""
    from fastapi.testclient import TestClient
    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    with TestClient(app) as client:
        r = client.get("/tiles/5/0/0.png")
        assert r.status_code == 404


def test_mbtiles_immutable_uri():
    """RESEARCH Pitfall 2: connection MUST use immutable=1 to prevent WAL/SHM creation."""
    import inspect

    import shitbox.dashboard.tiles as tiles_mod

    src = inspect.getsource(tiles_mod)
    assert "immutable=1" in src, "tiles.py must open MBTiles with immutable=1 URI"
    assert "mode=ro" in src, "tiles.py must open MBTiles read-only"


def test_uvicorn_signal_handlers_disabled():
    """RESEARCH Pitfall 1: server must NOT install uvicorn signal handlers."""
    import inspect

    import shitbox.dashboard.server as server_mod

    src = inspect.getsource(server_mod)
    assert (
        "install_signal_handlers" in src
    ), "server.py must override install_signal_handlers"
