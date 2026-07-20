"""Tests for timelapse rebuild helpers: Day-N derivation and corrupt-frame filtering."""

import os

import pytest

from shitbox.sync.rebuild_timelapses import _clear_outputs, _discover_days
from shitbox.sync.timelapse_compiler import TimelapseCompiler


def _compiler(rally_start=""):
    return TimelapseCompiler(captures_dir="/tmp", rally_start_date=rally_start)


class TestDayNumber:
    def test_rally_start_is_day_one(self):
        assert _compiler("2026-07-11")._day_number("2026-07-11") == 1

    def test_last_rally_day(self):
        assert _compiler("2026-07-11")._day_number("2026-07-17") == 7

    def test_return_leg_keeps_counting(self):
        assert _compiler("2026-07-11")._day_number("2026-07-19") == 9

    def test_pre_rally_is_none(self):
        # 09/10 July are shakedown footage before Day 1 — no day number.
        assert _compiler("2026-07-11")._day_number("2026-07-10") is None

    def test_no_start_date_is_none(self):
        assert _compiler("")._day_number("2026-07-11") is None

    def test_unparseable_is_none(self):
        assert _compiler("2026-07-11")._day_number("not-a-date") is None


def _write(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


class TestValidFrames:
    def test_drops_empty_and_truncated_keeps_order(self, tmp_path):
        good1 = tmp_path / "timelapse_00001.jpg"
        empty = tmp_path / "timelapse_00002.jpg"
        truncated = tmp_path / "timelapse_00003.jpg"
        good2 = tmp_path / "timelapse_00004.jpg"

        _write(good1, b"\xff\xd8\xff\xd9")  # minimal JPEG (SOI + EOI)
        _write(empty, b"")  # zero-byte
        _write(truncated, b"\xff\xd8\xff\x00")  # no EOI marker
        _write(good2, b"\xff\xd8\xff\xd9")

        # Force ascending mtimes so order is deterministic.
        for i, p in enumerate([good1, empty, truncated, good2]):
            os.utime(p, (1000 + i, 1000 + i))

        result = TimelapseCompiler._valid_frames(tmp_path)
        assert result == [good1, good2]

    def test_empty_dir_returns_empty(self, tmp_path):
        assert TimelapseCompiler._valid_frames(tmp_path) == []


class TestRebuildHelpers:
    def test_discover_days_only_dated_frame_dirs(self, tmp_path):
        (tmp_path / "timelapse" / "2026-07-11").mkdir(parents=True)
        (tmp_path / "timelapse" / "2026-07-09").mkdir(parents=True)
        (tmp_path / "timelapse" / "not-a-day").mkdir(parents=True)
        assert _discover_days(tmp_path) == ["2026-07-09", "2026-07-11"]

    def test_discover_days_no_frames_root(self, tmp_path):
        assert _discover_days(tmp_path) == []

    def test_clear_outputs_removes_stale_and_reports(self, tmp_path):
        day_dir = tmp_path / "2026-07-11"
        day_dir.mkdir()
        (day_dir / "timelapse.mp4").write_bytes(b"x")
        (day_dir / "timelapse.frames.mp4").write_bytes(b"x")
        (day_dir / "timelapse.lock").write_bytes(b"")
        (day_dir / "keep.txt").write_bytes(b"x")  # unrelated file survives

        removed = _clear_outputs(tmp_path, "2026-07-11")

        assert set(removed) == {"timelapse.mp4", "timelapse.frames.mp4", "timelapse.lock"}
        assert not (day_dir / "timelapse.mp4").exists()
        assert (day_dir / "keep.txt").exists()

    def test_clear_outputs_noop_when_clean(self, tmp_path):
        (tmp_path / "2026-07-11").mkdir()
        assert _clear_outputs(tmp_path, "2026-07-11") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
