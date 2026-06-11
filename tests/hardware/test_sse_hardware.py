"""Tests for the hardware field on the /sse/slow SSE payload (Phase 21, HW-02).

Drives the /sse/slow async generator via a live uvicorn instance, matching the
established pattern from tests/test_dashboard.py (STATE.md Plan 13-03 decision:
Starlette TestClient cannot consume infinite async generators, so a real server
on an ephemeral port is the pragmatic approach).
"""
from __future__ import annotations

import json
import time

import pytest

from shitbox.hardware import state as hw_state


# ---------------------------------------------------------------------------
# Helpers — borrowed from tests/test_dashboard.py
# ---------------------------------------------------------------------------


def _start_live_server(app):
    """Spin up a real uvicorn on an ephemeral port. Returns (srv, base_url)."""
    import socket

    from shitbox.dashboard.server import DashboardServer

    for _attempt in range(5):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()

        srv = DashboardServer(host="127.0.0.1", port=port, app=app)
        srv.start()
        deadline = time.time() + 2.0
        accepted = False
        while time.time() < deadline:
            if srv._thread is None or not srv._thread.is_alive():
                break
            probe = socket.socket()
            try:
                probe.connect(("127.0.0.1", port))
                probe.close()
                accepted = True
                break
            except OSError:
                probe.close()
                time.sleep(0.05)
        if accepted:
            return srv, f"http://127.0.0.1:{port}"
        srv.stop()
        time.sleep(0.1)
    raise RuntimeError("failed to start DashboardServer after retries")


def _read_sse_lines(url: str, max_lines: int = 6, timeout: float = 3.0):
    """Connect to url and read up to max_lines lines from the SSE body."""
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


def _first_slow_payload(mbtiles_fixture) -> dict:
    """Return the first parsed /sse/slow payload from a live server."""
    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/slow")
    finally:
        srv.stop()
        time.sleep(0.2)  # allow port TIME_WAIT to clear

    data_line = next((l for l in lines if l.startswith("data:")), None)
    assert data_line is not None, "no data line received from /sse/slow"
    return json.loads(data_line[len("data:"):].strip())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sse_slow_includes_hardware_field(mbtiles_fixture):
    """hardware field is a list; seeded devices appear with correct state."""
    hw_state.initialise({
        "imu": "critical",
        "power": "important",
        "environment": "best_effort",
    })
    hw_state.report_present("imu")
    hw_state.report_present("environment")
    # power stays MISSING

    payload = _first_slow_payload(mbtiles_fixture)
    assert "hardware" in payload, f"'hardware' key missing; keys: {list(payload.keys())}"
    hw = payload["hardware"]
    assert isinstance(hw, list), f"expected list, got {type(hw)}"
    assert len(hw) == 3, f"expected 3 entries, got {len(hw)}"

    imu_entry = next((e for e in hw if e["role"] == "imu"), None)
    assert imu_entry is not None, "imu entry missing from hardware list"
    assert imu_entry["state"] == "present", f"expected 'present', got {imu_entry['state']}"


def test_sse_slow_hardware_labels(mbtiles_fixture):
    """Label lookup matches UI-SPEC copy table verbatim (spot-check 5 roles)."""
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
        "temp_exterior": "best_effort",
        "audio_mic": "best_effort",
        "display_hdmi": "best_effort",
    })

    payload = _first_slow_payload(mbtiles_fixture)
    hw = payload["hardware"]
    by_role = {e["role"]: e for e in hw}

    assert by_role["imu"]["label"] == "IMU"
    assert by_role["camera_front"]["label"] == "Front Cam"
    assert by_role["temp_exterior"]["label"] == "Exterior Probe"
    assert by_role["audio_mic"]["label"] == "USB Mic"
    assert by_role["display_hdmi"]["label"] == "HDMI"


def test_sse_slow_hardware_last_seen_and_since_ms(mbtiles_fixture):
    """Never-seen device has last_seen=None and since_ms=None.

    Seen device has last_seen > 0 and since_ms >= 0.
    """
    hw_state.initialise({
        "imu": "critical",
        "camera_front": "critical",
    })
    hw_state.report_present("imu")  # sets last_seen to now
    # camera_front stays MISSING (last_seen=0.0)

    payload = _first_slow_payload(mbtiles_fixture)
    hw = payload["hardware"]
    by_role = {e["role"]: e for e in hw}

    imu = by_role["imu"]
    assert imu["last_seen"] is not None, "last_seen should be set for a seen device"
    assert imu["last_seen"] > 0, "last_seen should be > 0 for a seen device"
    assert imu["since_ms"] is not None, "since_ms should be set for a seen device"
    assert imu["since_ms"] >= 0, "since_ms should be >= 0"

    cam = by_role["camera_front"]
    assert cam["last_seen"] is None, f"last_seen should be None for never-seen; got {cam['last_seen']}"
    assert cam["since_ms"] is None, f"since_ms should be None for never-seen; got {cam['since_ms']}"


def test_sse_slow_hardware_empty_snapshot(mbtiles_fixture):
    """Empty snapshot (no initialise called) yields hardware == []."""
    # _clear_hw_state autouse fixture ensures snapshot is empty
    payload = _first_slow_payload(mbtiles_fixture)
    assert payload["hardware"] == [], (
        f"expected empty hardware list, got: {payload['hardware']}"
    )


def test_sse_slow_hardware_unknown_role_fallback_label(mbtiles_fixture):
    """Role not in label table → title-cased fallback label."""
    hw_state.initialise({"new_widget": "best_effort"})

    payload = _first_slow_payload(mbtiles_fixture)
    hw = payload["hardware"]
    by_role = {e["role"]: e for e in hw}

    assert "new_widget" in by_role, "new_widget role missing from payload"
    assert by_role["new_widget"]["label"] == "New Widget", (
        f"expected 'New Widget' fallback; got {by_role['new_widget']['label']}"
    )


def test_sse_slow_other_fields_unchanged(mbtiles_fixture):
    """Adding hardware field must not remove any existing /sse/slow fields."""
    payload = _first_slow_payload(mbtiles_fixture)

    required_fields = (
        "ts", "lat", "lng", "fix_mode", "sats", "hdop",
        "imu_temp", "soc_temp", "sync_connected", "sync_backlog",
        "event_count", "active_driver", "recording_active",
        "recording_ends_at",
    )
    missing = [f for f in required_fields if f not in payload]
    assert not missing, f"Fields missing from /sse/slow payload: {missing}"
