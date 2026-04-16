"""Tests for CaptureSyncService JSON generator registry (plan 12-03)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shitbox.sync.capture_sync import CaptureSyncService


def _make_service(tmp_path: Path) -> CaptureSyncService:
    """Construct a CaptureSyncService with minimal mocked dependencies."""
    config = MagicMock()
    config.remote_dest = "user@host:/remote/path"
    config.rsync_path = "rsync"
    config.interval_seconds = 300

    connection = MagicMock()
    connection.is_connected = False  # prevent any real rsync attempts

    return CaptureSyncService(
        config=config,
        connection_monitor=connection,
        captures_dir=str(tmp_path),
        event_storage=None,
        timelapse_compiler=None,
    )


def test_register_json_generator_adds_entry(tmp_path: Path) -> None:
    """register_json_generator stores the callable under the given name."""
    svc = _make_service(tmp_path)
    svc.register_json_generator("notes", lambda: [{"a": 1}])
    assert "notes" in svc._json_generators


def test_generators_run_before_rsync(tmp_path: Path) -> None:
    """_run_json_generators writes each generator's output to {captures_dir}/{name}.json."""
    svc = _make_service(tmp_path)
    svc.register_json_generator("notes", lambda: [{"x": 1}])
    svc.register_json_generator("fuel", lambda: [{"y": 2}])

    svc._run_json_generators()

    notes_file = tmp_path / "notes.json"
    fuel_file = tmp_path / "fuel.json"

    assert notes_file.exists(), "notes.json should be written"
    assert fuel_file.exists(), "fuel.json should be written"
    assert json.loads(notes_file.read_text()) == [{"x": 1}]
    assert json.loads(fuel_file.read_text()) == [{"y": 2}]


def test_generator_failure_does_not_abort_sync(tmp_path: Path) -> None:
    """A failing generator is logged and skipped; other generators still run and no exception is raised."""
    svc = _make_service(tmp_path)

    def _bad() -> None:
        raise ValueError("boom")

    svc.register_json_generator("bad", _bad)
    svc.register_json_generator("good", lambda: [{"ok": True}])

    # Must not raise
    svc._run_json_generators()

    good_file = tmp_path / "good.json"
    bad_file = tmp_path / "bad.json"

    assert good_file.exists(), "good.json should be written"
    assert json.loads(good_file.read_text()) == [{"ok": True}]
    assert not bad_file.exists(), "bad.json must not be written when generator fails"


def test_route_generator_registers_and_writes(tmp_path: Path) -> None:
    """route generator writes route.json with expected top-level shape."""
    svc = _make_service(tmp_path)
    payload = {
        "generated_at": "2026-05-01T10:00:00+00:00",
        "tolerance_m": 10.0,
        "days": {"2026-05-01": {"point_count": 2, "points": [[-16.0, 145.0], [-16.01, 145.01]]}},
    }
    svc.register_json_generator("route", lambda: payload)
    svc._run_json_generators()
    route_file = tmp_path / "route.json"
    assert route_file.exists()
    parsed = json.loads(route_file.read_text())
    assert "generated_at" in parsed
    assert "days" in parsed
    assert "2026-05-01" in parsed["days"]
