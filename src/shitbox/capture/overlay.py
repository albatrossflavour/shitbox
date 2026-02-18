"""Text-based HUD overlay for ffmpeg drawtext filters.

Writes small text files to /dev/shm/ at 1 Hz. ffmpeg's drawtext filter
with reload=1 picks up changes every frame — no second input, no pipe,
no synchronization issues.
"""

import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

_DIR = "/dev/shm"

# 8 cardinal + ordinal arrows indexed by 45° increments from N
_HEADING_ARROWS = ["\u2191", "\u2197", "\u2192", "\u2198", "\u2193", "\u2199", "\u2190", "\u2196"]

# 8 G-force direction arrows (same set, based on atan2 of G vector)
_G_ARROWS = ["\u2191", "\u2197", "\u2192", "\u2198", "\u2193", "\u2199", "\u2190", "\u2196"]

# File paths
SPEED_FILE = os.path.join(_DIR, "shitbox_speed.txt")
HEADING_FILE = os.path.join(_DIR, "shitbox_heading.txt")
GFORCE_FILE = os.path.join(_DIR, "shitbox_gforce.txt")
GPS_FILE = os.path.join(_DIR, "shitbox_gps.txt")

ALL_FILES = [SPEED_FILE, HEADING_FILE, GFORCE_FILE, GPS_FILE]

# Pre-processed 80x80 PNG with circular alpha mask
LOGO_PATH = str(Path(__file__).parent / "assets" / "shitbox_rally_logo.png")


def _atomic_write(path: str, text: str) -> None:
    """Write text to a file atomically via tmp + rename."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(text)
        os.rename(tmp, path)
    except Exception as e:
        log.debug("overlay_write_error", path=path, error=str(e))


def _heading_arrow(degrees: float) -> str:
    idx = round(degrees / 45) % 8
    return _HEADING_ARROWS[idx]


def _g_arrow(g_lat: float, g_lon: float) -> str:
    """Return a Unicode arrow for the G-force direction."""
    if abs(g_lat) < 0.05 and abs(g_lon) < 0.05:
        return "\u00b7"  # center dot for negligible G
    angle = math.atan2(g_lat, -g_lon)  # 0 = braking (up), +90 = right
    idx = round(angle / (math.pi / 4)) % 8
    return _G_ARROWS[idx]


def build_drawtext_filter() -> str:
    """Return the -vf drawtext filter chain for ffmpeg.

    Four drawtext instances reading from /dev/shm/ text files:
    - Speed (bottom-left, large)
    - Heading (bottom-left, smaller, below speed)
    - G-force with direction arrow (bottom-right)
    - GPS coords + sats + time (top-right)
    Plus a static SHITBOX logo (bottom-center).
    """
    font = "font=DejaVu Sans"
    mono = "font=DejaVu Sans Mono"
    box = "box=1:boxcolor=black@0.6:boxborderw=8"

    parts = [
        # Speed — bottom-left, large
        (
            f"drawtext=textfile='{SPEED_FILE}':reload=1"
            f":{font}:fontsize=64:fontcolor=white"
            f":{box}:x=20:y=h-140"
        ),
        # Heading — bottom-left, below speed
        (
            f"drawtext=textfile='{HEADING_FILE}':reload=1"
            f":{font}:fontsize=32:fontcolor=gray"
            f":{box}:x=20:y=h-65"
        ),
        # G-force — bottom-right
        (
            f"drawtext=textfile='{GFORCE_FILE}':reload=1"
            f":{font}:fontsize=48:fontcolor=white"
            f":{box}:x=w-tw-20:y=h-110"
        ),
        # GPS — top-right
        (
            f"drawtext=textfile='{GPS_FILE}':reload=1"
            f":{mono}:fontsize=24:fontcolor=white"
            f":{box}:x=w-tw-20:y=16"
        ),
        # URL — bottom-center, static
        (
            f"drawtext=text='shit-of-theseus.com'"
            f":{font}:fontsize=28:fontcolor=white@0.6"
            ":x=(w-tw)/2:y=h-40"
        ),
    ]
    return ",".join(parts)


def build_filter_complex(logo_input_idx: int) -> str:
    """Return a filter_complex string combining drawtext HUD + logo overlay.

    The logo is a pre-processed 80x80 PNG with circular alpha mask.
    At runtime ffmpeg just applies opacity and overlays — no per-pixel
    expression evaluation needed.

    Args:
        logo_input_idx: ffmpeg input index for the logo image
                        (1 without audio, 2 with audio).
    """
    drawtext_chain = build_drawtext_filter()

    # Scale (no-op at 80px) + apply 40% opacity
    logo_prep = (
        f"[{logo_input_idx}:v]"
        "format=rgba,colorchannelmixer=aa=0.4"
        "[logo]"
    )

    return (
        f"{logo_prep};"
        f"[0:v]{drawtext_chain}[text];"
        "[text][logo]overlay=10:10,format=yuv420p[out]"
    )


def update(
    speed: Optional[float],
    g_lat: float,
    g_lon: float,
    heading: Optional[float],
    lat: Optional[float],
    lon: Optional[float],
    satellites: Optional[int],
    timestamp: Optional[datetime] = None,
) -> None:
    """Write all overlay text files."""
    # Speed
    speed_str = f"{speed:.0f} km/h" if speed is not None else "-- km/h"
    _atomic_write(SPEED_FILE, speed_str)

    # Heading
    if heading is not None:
        heading_str = f"{heading:.0f}\u00b0 {_heading_arrow(heading)}"
    else:
        heading_str = "--\u00b0"
    _atomic_write(HEADING_FILE, heading_str)

    # G-force
    magnitude = math.sqrt(g_lat * g_lat + g_lon * g_lon)
    arrow = _g_arrow(g_lat, g_lon)
    _atomic_write(GFORCE_FILE, f"{arrow} {magnitude:.1f}g")

    # GPS
    if timestamp is None:
        timestamp = datetime.now()
    time_str = timestamp.strftime("%H:%M:%S")
    sats = f"sats {satellites}" if satellites is not None else "sats --"
    if lat is not None and lon is not None:
        coord = f"{lat:.4f}, {lon:.4f}"
    else:
        coord = "--, --"
    _atomic_write(GPS_FILE, f"{coord}\n{sats}  |  {time_str}")


def init() -> None:
    """Write initial placeholder text files before ffmpeg starts."""
    update(
        speed=None, g_lat=0.0, g_lon=0.0, heading=None,
        lat=None, lon=None, satellites=None,
    )


def cleanup() -> None:
    """Remove all overlay text files."""
    for path in ALL_FILES:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
