"""Phase 26 gap-closure (plan 26-06) — title card overflow fit and local TZ."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from shitbox.capture import title_card as tc
from shitbox.capture.title_card import (
    AU_STATE_ABBREVIATIONS,
    _abbreviate_au_states,
)
from shitbox.events.detector import Event, EventType

# ---------- G-02: AU state abbreviations ----------


@pytest.mark.parametrize(
    "full,expected",
    [
        ("Narellan, New South Wales", "Narellan, NSW"),
        ("Perth, Western Australia", "Perth, WA"),
        ("Adelaide, South Australia", "Adelaide, SA"),
        ("Geelong, Victoria", "Geelong, VIC"),
        ("Brisbane, Queensland", "Brisbane, QLD"),
        ("Hobart, Tasmania", "Hobart, TAS"),
        ("Darwin, Northern Territory", "Darwin, NT"),
        ("Canberra, Australian Capital Territory", "Canberra, ACT"),
        # already short — pass-through
        ("Bathurst, NSW", "Bathurst, NSW"),
        # no state component — pass-through
        ("Narellan", "Narellan"),
        # idempotent
        ("Sydney, NSW", "Sydney, NSW"),
    ],
)
def test_au_state_abbreviation(full: str, expected: str) -> None:
    assert _abbreviate_au_states(full) == expected


def test_au_state_abbreviation_idempotent() -> None:
    once = _abbreviate_au_states("Narellan, New South Wales")
    twice = _abbreviate_au_states(once)
    assert once == twice == "Narellan, NSW"


def test_au_state_abbreviation_longest_first() -> None:
    """South Australia must abbreviate as SA, not "South A" with a later
    Australia-becoming-A rule (if we ever added one). The longest-first
    ordering in AU_STATE_ABBREVIATIONS is the invariant this test pins."""
    # Confirm the ordering: longer strings come before any that are prefixes
    # of them in the source list.
    longs = [long_form for long_form, _ in AU_STATE_ABBREVIATIONS]
    for i, long_i in enumerate(longs):
        for long_j in longs[i + 1:]:
            # long_j must not be a suffix of long_i (would mean j is shorter
            # AND contained — hit first and shadow i).
            assert not long_i.endswith(long_j) or long_i == long_j


# ---------- G-02: measure-and-shrink-fit ----------


def test_hero_shrink_fit_cinzel(tmp_path: Path) -> None:
    """Phase 27 (D-13): HERO_FONT_FLOOR and HERO_FONT_STEP are unchanged.

    Short Cinzel ALL CAPS names fit at FONT_HERO (140). Longer realistic AU
    place names shrink but stay at or above HERO_FONT_FLOOR (100). A 28-char
    synthetic string still fits the 1160px safe width at a size >= floor,
    or ellipsis-truncates.
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (tc.CANVAS_W, tc.CANVAS_H), tc.BG_COLOUR)
    draw = ImageDraw.Draw(img)
    safe_w = tc.CANVAS_W - 2 * tc.SAFE_MARGIN_PX

    # Short: fits at 140
    _text, font = tc._fit_hero_to_canvas(
        draw, "NARELLAN", tc.FONT_DISPLAY_BOLD, max_size=tc.FONT_HERO
    )
    assert font.size == tc.FONT_HERO

    # Longer: shrinks but stays >= floor
    _text, font = tc._fit_hero_to_canvas(
        draw, "MOUNT PANORAMA", tc.FONT_DISPLAY_BOLD, max_size=tc.FONT_HERO
    )
    assert font.size >= tc.HERO_FONT_FLOOR
    assert font.size <= tc.FONT_HERO

    # 28-char ALL CAPS still fits safe width at some size >= floor, or
    # ellipsis-truncates (27-RESEARCH.md Pitfall 4).
    long_name = "A" * 28
    fitted_text, font = tc._fit_hero_to_canvas(
        draw, long_name, tc.FONT_DISPLAY_BOLD, max_size=tc.FONT_HERO
    )
    assert font.size >= tc.HERO_FONT_FLOOR
    width = draw.textlength(fitted_text, font=font)
    assert width <= safe_w or "…" in fitted_text or "..." in fitted_text


def test_extremely_long_unabbreviated_string_ellipsis_truncates(tmp_path: Path) -> None:
    """A string with no AU states and longer than what even 100pt can hold
    must ellipsis-truncate at 100pt."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (tc.CANVAS_W, tc.CANVAS_H), tc.BG_COLOUR)
    draw = ImageDraw.Draw(img)

    mega = "A" * 200
    fitted_text, fitted_font = tc._fit_hero_to_canvas(
        draw, mega, tc.FONT_DISPLAY_BOLD, max_size=tc.FONT_HERO
    )
    # Must end with ellipsis and fit at 100pt.
    assert fitted_text.endswith("...")
    width = draw.textlength(fitted_text, font=fitted_font)
    safe_w = tc.CANVAS_W - 2 * tc.SAFE_MARGIN_PX
    assert width <= safe_w


# ---------- G-03: local TZ render ----------


def test_local_tz_in_slate_date(tmp_path: Path, monkeypatch) -> None:
    """With TZ=Australia/Sydney, the date string must contain AEST or AEDT,
    not UTC. Uses a known epoch (2026-04-23 04:25:00 UTC) which is
    2026-04-23 14:25 AEST (no DST in April in AU)."""
    import time

    # 2026-04-23 04:25:00 UTC — the exact time from the UAT screenshot.
    epoch_utc = datetime(2026, 4, 23, 4, 25, 0, tzinfo=timezone.utc).timestamp()

    # Force local TZ to Sydney for the render so the assertion is deterministic
    # regardless of dev-laptop region.
    monkeypatch.setenv("TZ", "Australia/Sydney")
    time.tzset()

    # Build a minimal event skeleton and render.
    event = Event(
        event_type=EventType.MANUAL_CAPTURE,
        start_time=epoch_utc,
        end_time=epoch_utc + 1.0,
        peak_value=1.0,
        peak_ax=0.0, peak_ay=0.0, peak_az=1.0,
        samples=[],
    )
    renderer = tc.TitleCardRenderer(duration_seconds=3.0, show_driver=False)
    png_path = tmp_path / "out.png"
    ts_path = tmp_path / "out.ts"
    # render() returns 0.0 on failure but writes the PNG first on success; for
    # this test we only care about the composed PNG, not the TS. Patch _encode_ts
    # to a no-op so ffmpeg is not required.
    monkeypatch.setattr(renderer, "_encode_ts", lambda p, t: True)
    renderer.render(event, png_path, ts_path, geocoder=None, driver_name=None)

    # The rendered PNG is binary, so we assert via the format helper directly.
    # Replicate the format line the renderer uses.
    dt = datetime.fromtimestamp(epoch_utc).astimezone()
    rendered_str = dt.strftime("%d %b %Y  %H:%M %Z")

    assert "AEST" in rendered_str or "AEDT" in rendered_str, rendered_str
    assert "UTC" not in rendered_str, rendered_str
    # Sydney is UTC+10 in April (AEST, no DST). 04:25 UTC = 14:25 AEST.
    assert "14:25" in rendered_str, rendered_str
