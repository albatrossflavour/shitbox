"""RED-phase failing test stubs for Phase 10 dashboard surface.

These tests import from `shitbox.dashboard.*` modules that do not yet exist.
ImportError / NotImplementedError is the expected failure mode until later
waves implement the dashboard. Do NOT use pytest.importorskip here — we want
hard failures so each implementation task can flip its test from red to green.
"""

from __future__ import annotations

import re

import pytest


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


def test_sse_events_payload_has_lat_lng(mbtiles_fixture):
    """D-21: event payloads pushed via push_event must carry lat and lng fields.

    The frontend openEvents() uses ev.lat and ev.lng to place map markers.
    If the engine drops these fields the markers silently never appear.

    Tests the push_event fan-out directly: register a listener queue, push,
    assert the dequeued payload contains lat/lng.
    """
    import queue as _queue

    from shitbox.dashboard.sse import _event_listeners, _event_listeners_lock, push_event

    my_q: _queue.Queue = _queue.Queue()
    with _event_listeners_lock:
        _event_listeners.append(my_q)
    try:
        push_event({
            "type": "HIGH_G",
            "timestamp": "2026-04-09T12:00:00+00:00",
            "peak_g": 2.5,
            "duration_ms": 300,
            "speed_kmh": 80.0,
            "lat": -33.8688,
            "lng": 151.2093,
        })
        payload = my_q.get_nowait()
    finally:
        with _event_listeners_lock:
            _event_listeners.remove(my_q)

    assert "lat" in payload, "lat missing from event payload"
    assert "lng" in payload, "lng missing from event payload"
    assert payload["lat"] == pytest.approx(-33.8688)
    assert payload["lng"] == pytest.approx(151.2093)


# ---------------------------------------------------------------------------
# DISP-02 / D-07: Event ticker cap at 5 (Wave 0 RED — passes after Plan 17-02)
# ---------------------------------------------------------------------------


def test_event_ticker_max_five():
    """DISP-02/D-07: the kiosk event ticker must cap the events array at 5 items, not 10.

    This test is RED until Plan 17-02 changes `events.length > 10` to
    `events.length > 5` in src/shitbox/dashboard/static/index.html.

    Why: the 7" touchscreen has limited vertical space; 5 events fills the
    ticker without scrolling.  The current value of 10 causes overflow.
    """
    from pathlib import Path

    html_path = Path(__file__).parent.parent / "src" / "shitbox" / "dashboard" / "static" / "index.html"
    assert html_path.exists(), f"index.html not found at {html_path}"
    html = html_path.read_text(encoding="utf-8")

    assert re.search(r"events\.length\s*>\s*5", html), (
        "Expected `events.length > 5` in index.html — update the ticker cap from 10 to 5 (Plan 17-02, DISP-02/D-07)"
    )
    assert "events.length > 10" not in html, (
        "Found `events.length > 10` in index.html — this should have been updated to > 5 (Plan 17-02, DISP-02/D-07)"
    )


# ---------------------------------------------------------------------------
# DISP-03: active_driver key present in /sse/slow payload
# ---------------------------------------------------------------------------


def test_sse_slow_has_active_driver_key(mbtiles_fixture):
    """DISP-03: /sse/slow payload must include 'active_driver' key.

    The kiosk top bar binds to this key via Alpine x-text to show who is
    currently driving.  A missing key causes the top bar to show nothing.

    This test extends the existing test_sse_slow_schema coverage.
    """
    import json as _json

    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/slow")
    finally:
        srv.stop()
    data_line = next((line for line in lines if line.startswith("data:")), None)
    assert data_line is not None, "no data lines received from /sse/slow"
    payload = _json.loads(data_line[len("data:"):].strip())
    assert "active_driver" in payload, (
        f"'active_driver' key missing from /sse/slow payload. Got keys: {list(payload.keys())}"
    )


# ---------------------------------------------------------------------------
# Phase 15-05 — system_conditions payload regression coverage
#
# UI-SPEC contract (lines 170-209): exactly 5 scalar fields per row, always
# three rows in order undervoltage → thermal → capture. State is derived from
# alerts.snapshot() fired/active/last_change_ts — no other fields.
# ---------------------------------------------------------------------------


def _make_alert_status(
    subtype: str, *, fired: bool, active: bool, last_change_ts: float,
):
    """Build an AlertStatus with the real dataclass shape from 15-01."""
    from shitbox.health.alerts import AlertStatus

    return AlertStatus(
        subtype=subtype,
        active=active,
        fired=fired,
        active_sustain_count=2 if active else 0,
        clear_sustain_count=0 if active else 2,
        last_change_ts=last_change_ts,
    )


def test_system_conditions_payload_shape_is_five_scalars(monkeypatch):
    """UI-SPEC lines 170-209: each row emits EXACTLY role, label, tier, state, since_ms."""
    from shitbox.dashboard.sse import _system_conditions_payload

    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: {})
    rows = _system_conditions_payload()
    assert len(rows) == 3
    for row in rows:
        assert set(row.keys()) == {"role", "label", "tier", "state", "since_ms"}
        assert row["tier"] == "critical"


def test_system_conditions_payload_always_three_rows_in_order(monkeypatch):
    """UI-SPEC lines 126-148: always undervoltage → thermal → capture, even when empty."""
    from shitbox.dashboard.sse import _system_conditions_payload

    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: {})
    rows = _system_conditions_payload()
    assert [r["role"] for r in rows] == ["undervoltage", "thermal", "capture"]
    assert [r["label"] for r in rows] == ["UNDERVOLTAGE", "THERMAL", "CAPTURE"]
    assert all(r["state"] == "clear" for r in rows)
    assert all(r["since_ms"] is None for r in rows)


def test_system_conditions_payload_active_undervoltage(monkeypatch):
    import time as _time

    from shitbox.dashboard.sse import _system_conditions_payload

    now = _time.time()
    fake_snap = {
        "UNDERVOLTAGE": _make_alert_status(
            "UNDERVOLTAGE", fired=True, active=True, last_change_ts=now - 1.0,
        ),
    }
    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: fake_snap)
    rows = {r["role"]: r for r in _system_conditions_payload()}
    assert rows["undervoltage"]["state"] == "active"
    assert 900 <= rows["undervoltage"]["since_ms"] <= 1500
    assert rows["thermal"]["state"] == "clear"
    assert rows["capture"]["state"] == "clear"


def test_system_conditions_payload_restored_undervoltage(monkeypatch):
    """fired=True + active=False is the transient mid-recovery state."""
    import time as _time

    from shitbox.dashboard.sse import _system_conditions_payload

    now = _time.time()
    fake_snap = {
        "UNDERVOLTAGE": _make_alert_status(
            "UNDERVOLTAGE", fired=True, active=False, last_change_ts=now - 2.0,
        ),
    }
    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: fake_snap)
    rows = {r["role"]: r for r in _system_conditions_payload()}
    assert rows["undervoltage"]["state"] == "restored"


def test_system_conditions_payload_cleared_after_recovery_is_clear(monkeypatch):
    """Post-recovery (helper has flipped fired=False) → row returns to clear."""
    import time as _time

    from shitbox.dashboard.sse import _system_conditions_payload

    now = _time.time()
    fake_snap = {
        "UNDERVOLTAGE": _make_alert_status(
            "UNDERVOLTAGE", fired=False, active=False, last_change_ts=now - 2.0,
        ),
    }
    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: fake_snap)
    rows = {r["role"]: r for r in _system_conditions_payload()}
    assert rows["undervoltage"]["state"] == "clear"
    assert rows["undervoltage"]["since_ms"] is None


def test_system_conditions_payload_capture_down_rolls_up_same_role(monkeypatch):
    """CAPTURE_FAILURE and CAPTURE_DOWN both roll up into the capture row.

    Active wins over restored; the row reports state=active.
    """
    import time as _time

    from shitbox.dashboard.sse import _system_conditions_payload

    now = _time.time()
    fake_snap = {
        "CAPTURE_FAILURE": _make_alert_status(
            "CAPTURE_FAILURE", fired=True, active=True, last_change_ts=now - 1.0,
        ),
        "CAPTURE_DOWN": _make_alert_status(
            "CAPTURE_DOWN", fired=True, active=True, last_change_ts=now - 0.5,
        ),
    }
    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: fake_snap)
    rows = {r["role"]: r for r in _system_conditions_payload()}
    assert rows["capture"]["state"] == "active"
    assert rows["capture"]["label"] == "CAPTURE"
    assert rows["capture"]["tier"] == "critical"


def test_system_conditions_payload_no_forbidden_fields(monkeypatch):
    """UI-SPEC lock: no `key`, `subtype`, `message`, or `last_seen` fields."""
    import time as _time

    from shitbox.dashboard.sse import _system_conditions_payload

    now = _time.time()
    fake_snap = {
        "UNDERVOLTAGE": _make_alert_status(
            "UNDERVOLTAGE", fired=True, active=True, last_change_ts=now,
        ),
    }
    monkeypatch.setattr("shitbox.dashboard.sse.alerts.snapshot", lambda: fake_snap)
    rows = _system_conditions_payload()
    for row in rows:
        assert "key" not in row
        assert "subtype" not in row
        assert "message" not in row
        assert "last_seen" not in row


# ─── Phase 28: TPMS payload tests (SPEC-6) ─────────────────────────────

def test_tpms_payload_four_wheels(monkeypatch):
    """SPEC-6: _tpms_payload always emits four rows in deterministic FD/FP/RD/RP order."""
    try:
        from shitbox.dashboard.sse import _tpms_payload
    except ImportError:
        pytest.skip("Plan 28-05 — _tpms_payload not yet wired into sse.py")
    monkeypatch.setattr("shitbox.dashboard.sse.tpms_service", None)
    rows = _tpms_payload()
    assert len(rows) == 4
    assert [r["position"] for r in rows] == [
        "front-driver",
        "front-passenger",
        "rear-driver",
        "rear-passenger",
    ]


def test_tpms_payload_no_data(monkeypatch):
    """SPEC-6: pre-first-frame state is 'no_data' for every wheel."""
    try:
        from shitbox.dashboard.sse import _tpms_payload
    except ImportError:
        pytest.skip("Plan 28-05 — _tpms_payload not yet wired into sse.py")
    monkeypatch.setattr("shitbox.dashboard.sse.tpms_service", None)
    rows = _tpms_payload()
    assert all(r["state"] == "no_data" for r in rows)
    assert all(r["psi"] is None for r in rows)
