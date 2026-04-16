"""Unit tests for shitbox.capture.overlay history + ASS generator."""

from __future__ import annotations

from pathlib import Path

from shitbox.capture import overlay
from shitbox.capture.overlay import TelemetrySnapshot


def _reset_history() -> None:
    with overlay._history_lock:
        overlay._history.clear()


def _mk(wall_time: float, speed: str = "40 km/h") -> TelemetrySnapshot:
    return TelemetrySnapshot(
        wall_time=wall_time,
        speed=speed,
        gforce="· 0.0g",
        location="Home",
        gps_time="09:00:00",
        dist_dest="Dest: 50 km",
    )


def test_get_history_inside_window():
    _reset_history()
    with overlay._history_lock:
        for t in (100.0, 101.0, 102.0):
            overlay._history.append(_mk(t))

    result = overlay.get_history(start_time=100.5, end_time=101.5)
    assert [s.wall_time for s in result] == [100.0, 101.0]


def test_get_history_preceding_entry_included():
    """When nothing lives inside the window, the most recent preceding
    entry is returned so the clip opens with valid data."""
    _reset_history()
    with overlay._history_lock:
        for t in (50.0, 60.0, 70.0):
            overlay._history.append(_mk(t))

    result = overlay.get_history(start_time=80.0, end_time=90.0)
    assert [s.wall_time for s in result] == [70.0]


def test_get_history_empty():
    _reset_history()
    assert overlay.get_history(0.0, 10.0) == []


def test_generate_ass_hold_last_and_url(tmp_path: Path):
    entries = [
        _mk(998.0, speed="40 km/h"),   # preceding
        _mk(1002.5, speed="60 km/h"),  # middle
        _mk(1007.0, speed="80 km/h"),  # last
    ]
    out = overlay.generate_ass_overlay(
        entries=entries,
        clip_start_wall=1000.0,
        clip_end_wall=1010.0,
        intro_duration=8.0,
        output_path=tmp_path / "o.ass",
    )
    text = out.read_text()
    assert "PlayResX: 1920" in text
    # URL active during non-intro portion (8.0 → 18.0).
    assert r"{\an2\pos(960,1040)}shit-of-theseus.com" in text
    # Preceding entry clamped to intro boundary → 0:00:08.00–0:00:10.50.
    assert "Dialogue: 0,0:00:08.00,0:00:10.50," in text
    # Last entry holds to clip end → 0:00:15.00–0:00:18.00.
    assert "Dialogue: 0,0:00:15.00,0:00:18.00," in text
    # Speed values render in their dialogue lines.
    assert "40 km/h" in text and "60 km/h" in text and "80 km/h" in text


def test_generate_ass_no_entries_still_emits_url(tmp_path: Path):
    out = overlay.generate_ass_overlay(
        entries=[],
        clip_start_wall=100.0,
        clip_end_wall=110.0,
        intro_duration=5.0,
        output_path=tmp_path / "empty.ass",
    )
    text = out.read_text()
    assert "shit-of-theseus.com" in text
    # No Mono22 / Sans28 dialogue rows when there are no entries.
    assert "Mono22" not in [line.split(",")[3] for line in text.splitlines()
                            if line.startswith("Dialogue:")]


def test_generate_ass_escapes_curly_braces(tmp_path: Path):
    entry = TelemetrySnapshot(
        wall_time=1001.0,
        speed="50 km/h",
        gforce="↑ 0.1g",
        location="Weird {place}",
        gps_time="09:00:01",
        dist_dest="Dest: 10 km",
    )
    out = overlay.generate_ass_overlay(
        entries=[entry],
        clip_start_wall=1000.0,
        clip_end_wall=1005.0,
        intro_duration=0.0,
        output_path=tmp_path / "brace.ass",
    )
    text = out.read_text()
    assert r"Weird \{place\}" in text


def test_format_ass_time():
    assert overlay._format_ass_time(0.0) == "0:00:00.00"
    assert overlay._format_ass_time(65.5) == "0:01:05.50"
    assert overlay._format_ass_time(3661.25) == "1:01:01.25"
    # Negatives clamp to zero.
    assert overlay._format_ass_time(-1.0) == "0:00:00.00"
