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

# File paths — one file per drawtext instance to avoid multiline newline
# rendering artifacts (ffmpeg drawtext shows \n as a visible null/box char)
SPEED_FILE = os.path.join(_DIR, "shitbox_speed.txt")
HEADING_FILE = os.path.join(_DIR, "shitbox_heading.txt")
GFORCE_FILE = os.path.join(_DIR, "shitbox_gforce.txt")
LOCATION_FILE = os.path.join(_DIR, "shitbox_location.txt")
GPS_TIME_FILE = os.path.join(_DIR, "shitbox_gps_time.txt")
GPS_COORDS_FILE = os.path.join(_DIR, "shitbox_gps_coords.txt")
DIST_START_FILE = os.path.join(_DIR, "shitbox_dist_start.txt")
DIST_DEST_FILE = os.path.join(_DIR, "shitbox_dist_dest.txt")

ALL_FILES = [
    SPEED_FILE, HEADING_FILE, GFORCE_FILE,
    LOCATION_FILE, GPS_TIME_FILE, GPS_COORDS_FILE,
    DIST_START_FILE, DIST_DEST_FILE,
]

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

    Eight drawtext instances reading from /dev/shm/ text files:
    - Speed (bottom-left, large)
    - Heading (bottom-left, smaller, below speed)
    - G-force with direction arrow (bottom-right)
    - Location name (top-right, bold white)
    - GPS time (top-right, below location)
    - GPS coords (top-right, below time, faded)
    - Distance from start (top-right, below coords)
    - Distance to destination (top-right, below start distance)
    Plus a static URL (bottom-centre).

    Each line is a separate file to avoid ffmpeg drawtext rendering
    newline bytes as visible null/box characters.
    """
    font = "font=DejaVu Sans"
    mono = "font=DejaVu Sans Mono"
    box = "box=1:boxcolor=black@0.6:boxborderw=8"

    parts = [
        # Speed — bottom-left
        (
            f"drawtext=textfile='{SPEED_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white"
            f":{box}:x=20:y=h-76"
        ),
        # Heading — bottom-left, below speed
        (
            f"drawtext=textfile='{HEADING_FILE}':reload=1"
            f":{mono}:fontsize=18:fontcolor=white@0.5"
            f":{box}:x=20:y=h-40"
        ),
        # G-force — bottom-right
        (
            f"drawtext=textfile='{GFORCE_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white"
            f":{box}:x=w-tw-20:y=h-76"
        ),
        # Location name — top-right, prominent
        (
            f"drawtext=textfile='{LOCATION_FILE}':reload=1"
            f":{font}:fontsize=28:fontcolor=white"
            f":{box}:x=w-tw-20:y=16"
        ),
        # GPS time — top-right, below location
        (
            f"drawtext=textfile='{GPS_TIME_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white@0.8"
            f":{box}:x=w-tw-20:y=56"
        ),
        # GPS coords — top-right, below time, faded
        (
            f"drawtext=textfile='{GPS_COORDS_FILE}':reload=1"
            f":{mono}:fontsize=18:fontcolor=white@0.5"
            f":{box}:x=w-tw-20:y=94"
        ),
        # Distance from start — top-right, below coords
        (
            f"drawtext=textfile='{DIST_START_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white@0.8"
            f":{box}:x=w-tw-20:y=130"
        ),
        # Distance to destination — top-right, below start distance
        (
            f"drawtext=textfile='{DIST_DEST_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white@0.8"
            f":{box}:x=w-tw-20:y=168"
        ),
        # URL — bottom-centre, static
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
    timestamp: Optional[datetime] = None,
    location_name: Optional[str] = None,
    distance_from_start_km: Optional[float] = None,
    distance_to_destination_km: Optional[float] = None,
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

    # Location name
    _atomic_write(LOCATION_FILE, location_name if location_name else "")

    # GPS time
    if timestamp is None:
        timestamp = datetime.now()
    time_str = timestamp.strftime("%H:%M:%S")
    _atomic_write(GPS_TIME_FILE, time_str)

    # GPS coords (faded, bottom line)
    if lat is not None and lon is not None:
        coord = f"{lat:.4f}, {lon:.4f}"
    else:
        coord = "--, --"
    _atomic_write(GPS_COORDS_FILE, coord)

    # Distance from start
    if distance_from_start_km is not None:
        _atomic_write(DIST_START_FILE, f"Start: {distance_from_start_km:,.0f} km")
    else:
        _atomic_write(DIST_START_FILE, "Start: -- km")

    # Distance to destination
    if distance_to_destination_km is not None:
        _atomic_write(DIST_DEST_FILE, f"Dest: {distance_to_destination_km:,.0f} km")
    else:
        _atomic_write(DIST_DEST_FILE, "Dest: -- km")


def init() -> None:
    """Write initial placeholder text files before ffmpeg starts."""
    update(
        speed=None, g_lat=0.0, g_lon=0.0, heading=None,
        lat=None, lon=None,
    )


def cleanup() -> None:
    """Remove all overlay text files."""
    for path in ALL_FILES:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
