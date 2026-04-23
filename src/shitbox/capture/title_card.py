"""Event video title-card (slate) renderer.

Builds a 1280x720 PNG poster for a detected event — place-name hero, date,
coord strip, driver credit, event-type badge, logo — and encodes it to a
self-contained MPEG-TS segment so it concatenates cleanly with intro.ts
and the buffer segments on the concat demuxer path.

Public contract (plan 26-03):

    renderer = TitleCardRenderer(duration_seconds=3.0, show_driver=True)
    duration_s = renderer.render(
        event, png_path, ts_path,
        geocoder=engine._reverse_geocoder,
        driver_name=driver_state.get_active_driver(),
    )

`render()` never raises. It returns `self.duration_seconds` on success or
`0.0` on any failure (PNG composition, font miss, ffmpeg blow-up), so the
caller can degrade to the intro→buffer path without a slate.

Fallback matrix (D-09 / D-10 / D-11 / D-12):
  - place truthy        → hero=place, coords if lat/lng
  - geocoder None OR no lat/lng → hero=whimsy (D-09), no coord row
  - geocoder called, None → hero=None, coord-only (D-10)
  - event_type MANUAL_CAPTURE → no badge (D-11), driver credit fills the slot
  - event_type ROLLOVER → badge with 45° hazard stripes over red (D-07)
  - show_driver True AND driver_name truthy → 'Driver: ...' line (D-12)
"""

from __future__ import annotations

import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from shitbox.events.detector import EventType
from shitbox.events.labels import (
    ROLLOVER_STRIPE_COLOUR,
    colour_for,
    label_for,
)
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Matches overlay.py font choices (D-04). DejaVu ships on the Pi image.
FONT_DISPLAY = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
LOGO_PATH = str(Path(__file__).parent / "assets" / "shitbox_rally_logo.png")

# Default whimsy pool (D-09). Empty config list means "use these".
DEFAULT_WHIMSY = [
    "Here be dragons",
    "GPS off having a lie down",
    "Somewhere between A and B",
    "The map ends here",
    "Lost, but enthusiastic",
]

# Type of the geocoder resolver passed in by the engine at render time.
GeocoderFn = Callable[[float, float], Optional[str]]

# Canvas defaults (D-06).
CANVAS_W = 1280
CANVAS_H = 720

# Font sizes (D-05).
FONT_HERO = 140
FONT_DATE = 40
FONT_COORD = 28
FONT_DRIVER = FONT_DATE
FONT_BADGE = 36

# Palette — dark documentary look, matches the website (GitHub-ish).
BG_COLOUR = "#0d1117"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#c9d1d9"
TEXT_MONO = "#8b949e"

# Truncation caps (T-26-03-01 mitigation). All unbounded string inputs are
# clamped before being handed to Pillow so a 10 MB whimsy line can't blow the
# render timeout or burn an arbitrary amount of RAM.
MAX_PLACE_CHARS = 28
MAX_DRIVER_CHARS = 40
MAX_WHIMSY_CHARS = 40

# G-02: AU state abbreviations. Applied BEFORE width measurement so
# "Narellan, New South Wales" becomes "Narellan, NSW" before we decide
# whether to shrink the font. Longest-first iteration prevents prefix
# collisions if a future state entry shares a word-start with another.
AU_STATE_ABBREVIATIONS: List[Tuple[str, str]] = [
    ("Australian Capital Territory", "ACT"),
    ("Northern Territory", "NT"),
    ("Western Australia", "WA"),
    ("South Australia", "SA"),
    ("New South Wales", "NSW"),
    ("Queensland", "QLD"),
    ("Tasmania", "TAS"),
    ("Victoria", "VIC"),
]


def _abbreviate_au_states(place: str) -> str:
    """Abbreviate AU state names in a place string.

    Word-boundary replacement so "South Australian wine" does NOT become
    "SAn wine". Case-sensitive match (geocoder output is canonical-cased).
    Idempotent: short forms pass through unchanged.
    """
    result = place
    for long_form, short_form in AU_STATE_ABBREVIATIONS:
        # \b on both sides: \bNew South Wales\b
        pattern = r"\b" + re.escape(long_form) + r"\b"
        result = re.sub(pattern, short_form, result)
    return result


# G-02: measure-and-shrink-fit. Applied AFTER abbreviation. Shrink step
# is 10pt, floor is 100pt (FONT_HERO = 140pt default). If the abbreviated
# string is still too wide at 100pt, ellipsis-truncate char-by-char until
# it fits at 100pt.
HERO_FONT_FLOOR = 100
HERO_FONT_STEP = 10
SAFE_MARGIN_PX = 60  # each side; total safe width = 1280 - 2*60 = 1160


class TitleCardRenderer:
    """Renders an event slate as a PNG and a concat-ready MPEG-TS segment.

    Instances are cheap; hold one on `UnifiedEngine` and reuse it per event.
    Pillow is imported lazily inside `_compose_png()` so merely constructing
    a renderer on a host without Pillow does not raise.
    """

    def __init__(
        self,
        *,
        duration_seconds: float = 3.0,
        show_driver: bool = True,
        whimsy_lines: Optional[List[str]] = None,
        resolution: str = "1280x720",
        fps: int = 30,
    ) -> None:
        self.duration_seconds = float(duration_seconds)
        self.show_driver = bool(show_driver)
        # Empty / None config list falls back to the hardcoded defaults (D-16).
        self.whimsy_lines = list(whimsy_lines) if whimsy_lines else list(DEFAULT_WHIMSY)
        self.resolution = resolution
        self.fps = int(fps)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def render(
        self,
        event,  # Event-shaped: has event_type, start_time, optional lat/lng
        png_path: Path,
        ts_path: Path,
        *,
        geocoder: Optional[GeocoderFn] = None,
        driver_name: Optional[str] = None,
    ) -> float:
        """Render slate PNG + MPEG-TS. Returns duration on success, 0.0 on failure.

        Never raises — a caller that receives 0.0 should skip the slate and
        proceed with the intro→buffer concat path. All failure modes are
        logged as ``slate_render_failed`` with a ``stage`` kwarg.
        """
        png_path = Path(png_path)
        ts_path = Path(ts_path)

        # 1. Decide what gets drawn.
        hero_text, coord_text, show_badge, badge_label, badge_colour, is_rollover = (
            self._resolve_strings(event, geocoder)
        )

        # 2. Resolve driver-credit visibility.
        effective_driver = None
        if self.show_driver and driver_name:
            effective_driver = _truncate(driver_name, MAX_DRIVER_CHARS)

        # 3. Compose the PNG. Any exception (PIL missing, font missing, disk
        #    full, whatever) is caught and reported as a failed render.
        try:
            self._compose_png(
                png_path,
                hero_text=hero_text,
                coord_text=coord_text,
                show_badge=show_badge,
                badge_label=badge_label,
                badge_colour=badge_colour,
                is_rollover=is_rollover,
                start_time=event.start_time,
                driver_name=effective_driver,
            )
        except Exception as exc:
            log.error(
                "slate_render_failed",
                stage="png",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return 0.0

        # 4. Encode the PNG to a concat-compatible TS segment.
        try:
            ok = self._encode_ts(png_path, ts_path)
        except Exception as exc:  # defensive — _encode_ts swallows most errors
            log.error(
                "slate_render_failed",
                stage="ts",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return 0.0

        if not ok:
            log.error("slate_render_failed", stage="ts")
            return 0.0

        log.info(
            "slate_rendered",
            event_type=event.event_type.value,
            place=hero_text or "(whimsy)",
            coords=coord_text,
            png=str(png_path),
            ts=str(ts_path),
            duration_s=self.duration_seconds,
        )
        return self.duration_seconds

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_strings(self, event, geocoder: Optional[GeocoderFn]):
        """Return (hero_text, coord_text, show_badge, badge_label, badge_colour, is_rollover)."""
        lat = getattr(event, "lat", None)
        lng = getattr(event, "lng", None)

        # Geocoder is only consulted when we have both coords AND a resolver.
        # This is the D-09 vs D-10 fork:
        #   - geocoder present + lat/lng present → call it; truthy string = place,
        #     falsy = D-10 coord-only.
        #   - geocoder missing OR no lat/lng → D-09 whimsy, no coord row.
        place: Optional[str] = None
        geocoder_called = False
        if geocoder is not None and lat is not None and lng is not None:
            try:
                place = geocoder(lat, lng)
                geocoder_called = True
            except Exception as exc:
                log.debug("slate_geocoder_error", error=str(exc))
                place = None
                geocoder_called = True

        hero_text: Optional[str]
        coord_text: Optional[str]
        if place:
            # G-02: abbreviate AU state names before char-truncation so
            # "Narellan, New South Wales" (clips at 140pt) becomes "Narellan, NSW".
            abbreviated = _abbreviate_au_states(place)
            hero_text = _truncate(abbreviated, MAX_PLACE_CHARS)
            coord_text = f"{lat:.4f}, {lng:.4f}" if (lat is not None and lng is not None) else None
        elif geocoder_called:
            # D-10: we asked, got nothing; show coords only, no hero.
            hero_text = None
            coord_text = f"{lat:.4f}, {lng:.4f}"
        else:
            # D-09: no GPS or no geocoder → whimsy line, no coords.
            hero_text = _truncate(
                random.choice(self.whimsy_lines), MAX_WHIMSY_CHARS
            )
            coord_text = None

        # Badge (D-11): manual captures drop the badge so the driver credit
        # can take visual centre-stage on the bottom row.
        show_badge = event.event_type != EventType.MANUAL_CAPTURE
        badge_label = label_for(event.event_type)
        badge_colour = colour_for(event.event_type)
        is_rollover = event.event_type == EventType.ROLLOVER

        return hero_text, coord_text, show_badge, badge_label, badge_colour, is_rollover

    def _compose_png(
        self,
        png_path: Path,
        *,
        hero_text: Optional[str],
        coord_text: Optional[str],
        show_badge: bool,
        badge_label: str,
        badge_colour: str,
        is_rollover: bool,
        start_time: float,
        driver_name: Optional[str],
    ) -> None:
        """Draw the slate PNG at png_path. Raises on unrecoverable failure.

        Pillow is imported here (not at module scope) so the renderer module
        stays import-safe on a dev box without PIL — the failure only fires
        when a render is actually attempted, and is caught by `render()`.
        """
        from PIL import Image, ImageDraw, ImageFont

        # Font loaders with graceful fallback for dev laptops without DejaVu.
        def _font(path: str, size: int):
            try:
                return ImageFont.truetype(path, size)
            except Exception as exc:
                log.debug("slate_font_fallback", path=path, size=size, error=str(exc))
                return ImageFont.load_default()

        # f_hero is no longer allocated here — _fit_hero_to_canvas picks the
        # correct size per-render (G-02).
        f_date = _font(FONT_DISPLAY, FONT_DATE)
        f_driver = _font(FONT_DISPLAY, FONT_DRIVER)
        f_coord = _font(FONT_MONO, FONT_COORD)
        f_badge = _font(FONT_DISPLAY, FONT_BADGE)

        img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOUR)
        draw = ImageDraw.Draw(img)

        # Hero row (D-05 — place name, ~140pt). D-10 (coord-only) skips this.
        if hero_text:
            # G-02: measure-and-shrink-fit. Abbreviation already applied in
            # _resolve_strings; here we pick the largest size that fits within
            # 1160px safe width, falling through to ellipsis truncation at 100pt.
            fitted_text, fitted_font = _fit_hero_to_canvas(
                draw, hero_text, FONT_DISPLAY, max_size=FONT_HERO
            )
            _draw_centered(draw, fitted_text, fitted_font, y=220, fill=TEXT_PRIMARY)

        # Date/time row.
        # G-03: render in local time with the local TZ abbreviation (AEST/AEDT
        # on the Pi). astimezone() with no arg uses the system local TZ; %Z
        # emits the TZ name that strftime gets from the tzinfo object.
        dt = datetime.fromtimestamp(start_time).astimezone()
        date_str = dt.strftime("%d %b %Y  %H:%M %Z")
        _draw_centered(draw, date_str, f_date, y=400, fill=TEXT_SECONDARY)

        # Driver credit (D-12). Only rendered if caller passed a value through.
        if driver_name:
            _draw_centered(
                draw, f"Driver: {driver_name}", f_driver, y=455, fill=TEXT_SECONDARY
            )

        # Coord row (D-10 anchor when no hero; decorative otherwise).
        if coord_text:
            _draw_centered(draw, coord_text, f_coord, y=520, fill=TEXT_MONO)

        # Badge bottom-left (D-05).
        if show_badge:
            _draw_badge(
                img,
                draw,
                label=badge_label,
                colour=badge_colour,
                font=f_badge,
                is_rollover=is_rollover,
                anchor_x=60,
                anchor_y=600,
            )

        # Logo bottom-right (D-05). Skip silently if the asset is missing.
        try:
            with Image.open(LOGO_PATH) as logo:
                logo = logo.convert("RGBA")
                max_h = 120
                if logo.height > max_h:
                    scale = max_h / logo.height
                    new_size = (int(logo.width * scale), int(logo.height * scale))
                    logo = logo.resize(new_size, Image.Resampling.LANCZOS)
                pos = (
                    CANVAS_W - logo.width - 40,
                    CANVAS_H - logo.height - 40,
                )
                img.paste(logo, pos, logo)
        except FileNotFoundError:
            log.warning("slate_logo_missing", path=LOGO_PATH)
        except Exception as exc:  # unreadable / corrupt logo — don't fail the render
            log.debug("slate_logo_skip", path=LOGO_PATH, error=str(exc))

        img.save(png_path, format="PNG")

    def _encode_ts(self, png_path: Path, ts_path: Path) -> bool:
        """Convert the slate PNG to an MPEG-TS segment with silent AAC.

        The silent AAC input is NOT optional — intro.ts carries AAC stereo
        48 kHz, and the concat demuxer errors out on mismatched track layouts
        between concatenated entries. See 26-PATTERNS.md gotcha.
        """
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(png_path),
            "-f", "lavfi", "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t", str(self.duration_seconds),
            "-vf", f"fps={self.fps},format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-f", "mpegts", str(ts_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except FileNotFoundError:
            log.error("slate_ts_failed", stage="ffmpeg_missing")
            return False
        except subprocess.TimeoutExpired:
            log.error("slate_ts_timeout", duration_s=self.duration_seconds)
            return False

        if (
            result.returncode == 0
            and Path(ts_path).exists()
            and Path(ts_path).stat().st_size > 0
        ):
            size_mb = round(Path(ts_path).stat().st_size / (1024 * 1024), 3)
            log.info(
                "slate_ts_rendered",
                ts=str(ts_path),
                size_mb=size_mb,
                duration_s=self.duration_seconds,
            )
            return True

        stderr = result.stderr.decode(errors="replace")[-500:] if result.stderr else ""
        log.error(
            "slate_ts_failed",
            returncode=result.returncode,
            stderr=stderr,
        )
        return False


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_chars: int) -> str:
    """Clamp ``text`` to ``max_chars``, appending an ellipsis when we cut.

    Mitigates T-26-03-01: a very long place name or driver string would
    otherwise blow the Pillow render bounds (and indirectly the ffmpeg
    timeout if rendering spirals).
    """
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _fit_hero_to_canvas(draw, text: str, font_path: str, max_size: int = FONT_HERO):
    """Return (fitted_text, font) such that font renders fitted_text <= SAFE_WIDTH.

    Pipeline: abbreviation is done BEFORE this call by the caller. Here:
    1. Try max_size. If fits, return.
    2. Shrink in HERO_FONT_STEP decrements down to HERO_FONT_FLOOR.
    3. If still too wide at floor, char-truncate with '...' suffix.

    `draw` is a Pillow ImageDraw; `font_path` is the TTF path.
    """
    from PIL import ImageFont

    safe_w = CANVAS_W - 2 * SAFE_MARGIN_PX  # 1160 for 1280 canvas

    def _measure(s: str, size: int):
        f: object
        try:
            f = ImageFont.truetype(font_path, size)
        except Exception:
            f = ImageFont.load_default()
        # Pillow >= 9.2: textlength returns a float width in px.
        w = draw.textlength(s, font=f)
        return w, f

    # Step 1+2: abbreviate-already-done, try sizes max_size -> floor.
    for size in range(max_size, HERO_FONT_FLOOR - 1, -HERO_FONT_STEP):
        w, f = _measure(text, size)
        if w <= safe_w:
            return text, f

    # Step 3: char-truncate at floor size.
    floor_size = HERO_FONT_FLOOR
    trimmed = text
    while len(trimmed) > 1:
        trimmed = trimmed[:-1]
        candidate = trimmed.rstrip() + "..."
        w, f = _measure(candidate, floor_size)
        if w <= safe_w:
            return candidate, f
    # Unreachable in practice (a single-char string at 100pt fits 1160px).
    _, f = _measure(text, floor_size)
    return text, f


def _text_width(draw, text: str, font) -> int:
    """Width of `text` in `font`, using ImageDraw's textbbox (Pillow 10+)."""
    try:
        left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
        return int(right - left)
    except AttributeError:
        # Very old Pillow fallback.
        return int(draw.textsize(text, font=font)[0])  # type: ignore[attr-defined]


def _draw_centered(draw, text: str, font, *, y: int, fill: str) -> None:
    w = _text_width(draw, text, font)
    x = (CANVAS_W - w) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _draw_badge(
    img,
    draw,
    *,
    label: str,
    colour: str,
    font,
    is_rollover: bool,
    anchor_x: int,
    anchor_y: int,
) -> None:
    """Draw a filled rectangle badge with centred label text.

    Layout: rect height ~60px, width fits the label with 20px padding each
    side. ROLLOVER additionally composites a 45° hazard-stripe overlay at
    ~30% alpha to unambiguously distinguish it from HIGH_G red.
    """
    from PIL import Image, ImageDraw

    padding_x = 20
    padding_y = 12
    text_w = _text_width(draw, label, font)
    badge_w = text_w + padding_x * 2
    badge_h = max(60, FONT_BADGE + padding_y * 2)

    # Solid fill first.
    draw.rectangle(
        (anchor_x, anchor_y, anchor_x + badge_w, anchor_y + badge_h),
        fill=colour,
    )

    # Hazard stripes for rollover (D-07). Drawn on a transparent RGBA overlay
    # sized exactly like the badge, then composited so stripes sit on top of
    # the red fill but under the label.
    if is_rollover:
        overlay = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        stripe_rgba = (*_hex_to_rgb(ROLLOVER_STRIPE_COLOUR), 76)  # ~30% alpha
        step = 24
        # Diagonal lines every `step` pixels across a band wide enough to
        # cover the full rectangle at 45° (h + w from top-left anchor).
        for offset in range(-badge_h, badge_w + badge_h, step):
            odraw.line(
                (offset, badge_h, offset + badge_h, 0),
                fill=stripe_rgba,
                width=12,
            )
        img.paste(overlay, (anchor_x, anchor_y), overlay)

    # Label text centered within the badge.
    text_x = anchor_x + (badge_w - text_w) // 2
    text_y = anchor_y + (badge_h - FONT_BADGE) // 2 - 2  # slight optical nudge
    draw.text((text_x, text_y), label, font=font, fill="#ffffff")


def _hex_to_rgb(hex_colour: str):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
