"""Tests for shitbox.capture.title_card — event video title card renderer."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest import mock

import pytest
from PIL import Image

from shitbox.events.detector import EventType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(
    *,
    event_type: EventType = EventType.HIGH_G,
    lat: Optional[float] = -17.0048,
    lng: Optional[float] = 145.4246,
    start_time: float = 1_714_000_000.0,
) -> SimpleNamespace:
    """Build a minimal event-like object carrying the fields the renderer reads.

    Uses SimpleNamespace instead of the real Event dataclass so tests don't have
    to construct the full Phase-22 peak_* and samples fields just to drive the
    renderer. The renderer only reads event_type, start_time, lat, lng.
    """
    return SimpleNamespace(
        event_type=event_type,
        start_time=start_time,
        lat=lat,
        lng=lng,
    )


@pytest.fixture
def png_and_ts(tmp_path):
    """Return (png_path, ts_path) in a clean tmp dir."""
    return tmp_path / "slate.png", tmp_path / "slate.ts"


# ---------------------------------------------------------------------------
# Task 1: PNG composition, fallback matrix, graceful failure
# ---------------------------------------------------------------------------


def _stub_encode_ts(renderer, ts_path: Path) -> None:
    """Monkeypatch _encode_ts to succeed without spawning ffmpeg."""
    def _fake(_self, _png_path, out_ts_path):
        Path(out_ts_path).write_bytes(b"TS-STUB")
        return True
    renderer._encode_ts = _fake.__get__(renderer, type(renderer))


def test_render_with_place_and_driver(png_and_ts, tmp_path):
    """Place name + driver credit render a non-empty 1280x720 PNG."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    event = _make_event()
    duration = r.render(
        event,
        png_path,
        ts_path,
        geocoder=lambda lat, lon: "Mareeba, Queensland",
        driver_name="Tony",
    )

    assert duration > 0
    assert png_path.exists()
    with Image.open(png_path) as img:
        assert img.size == (1280, 720)
        # Confirm something was drawn — a blank-black canvas would have
        # extrema == (0, 0) for every band.
        extrema = img.convert("RGB").getextrema()
        assert any(hi > 0 for _lo, hi in extrema)


def test_render_whimsy_when_no_gps(png_and_ts):
    """No lat/lng and no geocoder → whimsy branch (D-09) still renders."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    event = _make_event(lat=None, lng=None)
    duration = r.render(event, png_path, ts_path, geocoder=None, driver_name=None)

    assert duration > 0
    assert png_path.exists()
    with Image.open(png_path) as img:
        assert img.size == (1280, 720)


def test_render_coord_only_when_geocoder_returns_none(png_and_ts):
    """Event has lat/lng but geocoder returns None → coord-only (D-10)."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    captured: dict = {}

    def fake_compose(self, *args, **kwargs):
        captured.update(kwargs)
        # Still produce a real PNG so the outer contract holds.
        Image.new("RGB", (1280, 720), "#0d1117").save(args[0])

    with mock.patch.object(
        TitleCardRenderer, "_compose_png", autospec=True, side_effect=fake_compose
    ):
        event = _make_event(lat=-17.0048, lng=145.4246)
        duration = r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: None,
            driver_name="Tony",
        )

    assert duration > 0
    assert captured["hero_text"] is None
    assert captured["coord_text"] == "-17.0048, 145.4246"


def test_manual_capture_no_badge(png_and_ts):
    """MANUAL_CAPTURE events skip the badge (D-11)."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    captured: dict = {}

    def fake_compose(self, *args, **kwargs):
        captured.update(kwargs)
        Image.new("RGB", (1280, 720), "#0d1117").save(args[0])

    with mock.patch.object(
        TitleCardRenderer, "_compose_png", autospec=True, side_effect=fake_compose
    ):
        event = _make_event(event_type=EventType.MANUAL_CAPTURE)
        r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: "Somewhere",
            driver_name="Tony",
        )

    assert captured["show_badge"] is False


def test_rollover_hazard_stripes(png_and_ts):
    """ROLLOVER events flag is_rollover=True for stripe overlay (D-07)."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    captured: dict = {}

    def fake_compose(self, *args, **kwargs):
        captured.update(kwargs)
        Image.new("RGB", (1280, 720), "#0d1117").save(args[0])

    with mock.patch.object(
        TitleCardRenderer, "_compose_png", autospec=True, side_effect=fake_compose
    ):
        event = _make_event(event_type=EventType.ROLLOVER)
        r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: "Somewhere",
            driver_name="Tony",
        )

    assert captured["is_rollover"] is True
    assert captured["show_badge"] is True


def test_show_driver_false(png_and_ts):
    """show_driver=False suppresses the driver credit even if name is set."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer(show_driver=False)
    _stub_encode_ts(r, ts_path)

    captured: dict = {}

    def fake_compose(self, *args, **kwargs):
        captured.update(kwargs)
        Image.new("RGB", (1280, 720), "#0d1117").save(args[0])

    with mock.patch.object(
        TitleCardRenderer, "_compose_png", autospec=True, side_effect=fake_compose
    ):
        event = _make_event()
        r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: "Somewhere",
            driver_name="Tony",
        )

    # driver_name should be passed as None to _compose_png when show_driver False.
    assert captured["driver_name"] is None


def test_driver_name_none(png_and_ts):
    """driver_name=None never draws a driver line."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    captured: dict = {}

    def fake_compose(self, *args, **kwargs):
        captured.update(kwargs)
        Image.new("RGB", (1280, 720), "#0d1117").save(args[0])

    with mock.patch.object(
        TitleCardRenderer, "_compose_png", autospec=True, side_effect=fake_compose
    ):
        event = _make_event()
        r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: "Somewhere",
            driver_name=None,
        )

    assert captured["driver_name"] is None


def test_pillow_missing_fails_gracefully(png_and_ts, caplog):
    """Simulate PIL ImportError inside _compose_png; render() must not raise."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()
    _stub_encode_ts(r, ts_path)

    def raise_import_error(self, *args, **kwargs):
        raise ImportError("PIL not available")

    event = _make_event()

    with mock.patch.object(
        TitleCardRenderer, "_compose_png", autospec=True, side_effect=raise_import_error
    ):
        duration = r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: "Mareeba",
            driver_name="Tony",
        )

    assert duration == 0.0


def test_ts_encode_failure_returns_zero(png_and_ts):
    """If _encode_ts returns False, render() returns 0.0 even if PNG succeeded."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer()

    def fake(self, _png, _ts):
        return False

    with mock.patch.object(TitleCardRenderer, "_encode_ts", autospec=True, side_effect=fake):
        event = _make_event()
        duration = r.render(
            event,
            png_path,
            ts_path,
            geocoder=lambda lat, lon: "Mareeba",
            driver_name="Tony",
        )

    assert duration == 0.0


# ---------------------------------------------------------------------------
# Task 2: PNG → MPEG-TS encoder (ffmpeg subprocess)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_encode_ts_produces_valid_stream(png_and_ts):
    """End-to-end encode: ffprobe the resulting TS for concat-demuxer parity."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    # Create a tiny real PNG to feed ffmpeg.
    Image.new("RGB", (1280, 720), "#0d1117").save(png_path)

    r = TitleCardRenderer(duration_seconds=1.0, fps=10)
    assert r._encode_ts(png_path, ts_path) is True
    assert ts_path.exists() and ts_path.stat().st_size > 0

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "default=noprint_wrappers=0",
            str(ts_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert probe.returncode == 0, probe.stderr
    output = probe.stdout
    # Video checks.
    assert "codec_name=h264" in output
    assert "width=1280" in output
    assert "height=720" in output
    assert "pix_fmt=yuv420p" in output
    # Audio checks.
    assert "codec_name=aac" in output
    assert "sample_rate=48000" in output
    assert "channels=2" in output


def test_encode_ts_ffmpeg_missing_returns_false(png_and_ts):
    """FileNotFoundError from subprocess.run → False (not a raise)."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    png_path.write_bytes(b"not-a-real-png")
    r = TitleCardRenderer()

    with mock.patch("shitbox.capture.title_card.subprocess.run", side_effect=FileNotFoundError):
        assert r._encode_ts(png_path, ts_path) is False


def test_encode_ts_timeout_returns_false(png_and_ts):
    """subprocess.run raising TimeoutExpired → False."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    png_path.write_bytes(b"not-a-real-png")
    r = TitleCardRenderer()

    with mock.patch(
        "shitbox.capture.title_card.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=60),
    ):
        assert r._encode_ts(png_path, ts_path) is False


def test_encode_ts_nonzero_exit_returns_false(png_and_ts):
    """ffmpeg returncode != 0 → False, logs stderr tail."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    png_path.write_bytes(b"not-a-real-png")
    r = TitleCardRenderer()

    fake_result = SimpleNamespace(returncode=1, stderr=b"ffmpeg error text" * 40)

    with mock.patch(
        "shitbox.capture.title_card.subprocess.run", return_value=fake_result
    ):
        assert r._encode_ts(png_path, ts_path) is False


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_end_to_end_integration(png_and_ts):
    """Full render() call with real ffmpeg produces both PNG and TS."""
    from shitbox.capture.title_card import TitleCardRenderer

    png_path, ts_path = png_and_ts
    r = TitleCardRenderer(duration_seconds=1.0, fps=10)

    event = _make_event()
    duration = r.render(
        event,
        png_path,
        ts_path,
        geocoder=lambda lat, lon: "Mareeba, Queensland",
        driver_name="Tony",
    )

    assert duration == 1.0
    assert png_path.exists() and png_path.stat().st_size > 0
    assert ts_path.exists() and ts_path.stat().st_size > 0


# Phase 27 (SC-3, D-10, D-11): Wave 0 packaging-sanity — bundled Cinzel
# TTFs must load via Pillow from the in-tree asset path. If this test
# fails, pyproject.toml's package-data glob is wrong OR the vendored
# files are missing, and every slate on the Pi would fall through to
# ImageFont.load_default() (10pt bitmap typewriter text).
def test_cinzel_fonts_load():
    pytest.importorskip("PIL")
    from pathlib import Path

    from PIL import ImageFont

    assets_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "shitbox"
        / "capture"
        / "assets"
        / "cinzel"
    )
    bold_path = assets_dir / "Cinzel-Bold.ttf"
    regular_path = assets_dir / "Cinzel-Regular.ttf"
    ofl_path = assets_dir / "OFL.txt"

    assert bold_path.is_file(), f"missing {bold_path}"
    assert regular_path.is_file(), f"missing {regular_path}"
    assert ofl_path.is_file(), f"missing {ofl_path}"

    # Pillow must load both TTFs without raising; a fallback to
    # ImageFont.load_default() would return an ImageFont of a different
    # type, so we assert the concrete truetype load succeeds.
    bold_font = ImageFont.truetype(str(bold_path), 140)
    regular_font = ImageFont.truetype(str(regular_path), 40)

    assert bold_font is not None
    assert regular_font is not None


# --- Phase 27 Plan 02 Task 1: font constants point at bundled Cinzel --------

def test_font_display_constants_point_at_bundled_cinzel():
    """Task 1 (SC-1, D-10, D-11): FONT_DISPLAY_BOLD / FONT_DISPLAY_REGULAR

    resolve to the bundled Cinzel TTFs, FONT_DISPLAY is a back-compat alias
    for the Bold path (so the badge call site stays zero-touch, D-09), and
    FONT_MONO still points at the Pi-image DejaVu mono (D-12).
    """
    pytest.importorskip("PIL")
    from pathlib import Path

    from shitbox.capture import title_card

    assert title_card.FONT_DISPLAY_BOLD.endswith("Cinzel-Bold.ttf")
    assert title_card.FONT_DISPLAY_REGULAR.endswith("Cinzel-Regular.ttf")
    assert title_card.FONT_DISPLAY == title_card.FONT_DISPLAY_BOLD
    assert title_card.FONT_MONO.endswith("DejaVuSansMono.ttf")

    assert Path(title_card.FONT_DISPLAY_BOLD).is_file()
    assert Path(title_card.FONT_DISPLAY_REGULAR).is_file()
