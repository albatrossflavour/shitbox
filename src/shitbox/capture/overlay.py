"""Text-based HUD overlay for ffmpeg drawtext filters.

Writes small text files to /dev/shm/ at 1 Hz. ffmpeg's drawtext filter
with reload=1 picks up changes every frame — no second input, no pipe,
no synchronization issues.

Each update() call also snapshots the formatted HUD values into a
module-level history deque. generate_ass_overlay() consumes those
snapshots at save-time to produce an ASS subtitle file that ffmpeg can
burn into a passthrough-recorded clip.
"""

import math
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import NamedTuple, Optional

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
GFORCE_FILE = os.path.join(_DIR, "shitbox_gforce.txt")
LOCATION_FILE = os.path.join(_DIR, "shitbox_location.txt")
GPS_TIME_FILE = os.path.join(_DIR, "shitbox_gps_time.txt")
DIST_DEST_FILE = os.path.join(_DIR, "shitbox_dist_dest.txt")

ALL_FILES = [
    SPEED_FILE, GFORCE_FILE,
    LOCATION_FILE, GPS_TIME_FILE, DIST_DEST_FILE,
]

# Pre-processed 80x80 PNG with circular alpha mask
LOGO_PATH = str(Path(__file__).parent / "assets" / "shitbox_rally_logo.png")


class TelemetrySnapshot(NamedTuple):
    """One frame of formatted HUD state, captured by update()."""

    wall_time: float
    speed: str
    gforce: str
    location: str
    gps_time: str
    dist_dest: str


# 10 minutes at ~1 Hz — event clips are <=90 s, so ample headroom.
_HISTORY_MAXLEN = 600
_history: "deque[TelemetrySnapshot]" = deque(maxlen=_HISTORY_MAXLEN)
_history_lock = Lock()


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
    - G-force with direction arrow (right side, above PiP)
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
            f":{box}:x=20:y=h-50"
        ),
        # G-force — right side, above PiP inset
        (
            f"drawtext=textfile='{GFORCE_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white"
            f":{box}:x=w-tw-20:y=h-200"
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
        # Distance to destination — top-right, below time
        (
            f"drawtext=textfile='{DIST_DEST_FILE}':reload=1"
            f":{mono}:fontsize=22:fontcolor=white@0.8"
            f":{box}:x=w-tw-20:y=94"
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
    """Write all overlay text files and append a snapshot to history."""
    # Speed
    speed_str = f"{speed:.0f} km/h" if speed is not None else "-- km/h"
    _atomic_write(SPEED_FILE, speed_str)

    # G-force
    magnitude = math.sqrt(g_lat * g_lat + g_lon * g_lon)
    arrow = _g_arrow(g_lat, g_lon)
    gforce_str = f"{arrow} {magnitude:.1f}g"
    _atomic_write(GFORCE_FILE, gforce_str)

    # Location name
    location_str = location_name if location_name else ""
    _atomic_write(LOCATION_FILE, location_str)

    # GPS time
    if timestamp is None:
        timestamp = datetime.now()
    gps_time_str = timestamp.strftime("%H:%M:%S")
    _atomic_write(GPS_TIME_FILE, gps_time_str)

    # Distance to destination
    if distance_to_destination_km is not None:
        dist_dest_str = f"Dest: {distance_to_destination_km:,.0f} km"
    else:
        dist_dest_str = "Dest: -- km"
    _atomic_write(DIST_DEST_FILE, dist_dest_str)

    snapshot = TelemetrySnapshot(
        wall_time=time.time(),
        speed=speed_str,
        gforce=gforce_str,
        location=location_str,
        gps_time=gps_time_str,
        dist_dest=dist_dest_str,
    )
    with _history_lock:
        _history.append(snapshot)


def get_history(start_time: float, end_time: float) -> list[TelemetrySnapshot]:
    """Return snapshots whose wall_time falls in [start_time, end_time].

    If any snapshots precede the window, the most recent one is prepended
    so the clip opens with valid HUD values even if the first in-window
    update has not landed yet.
    """
    with _history_lock:
        entries = list(_history)

    result: list[TelemetrySnapshot] = []
    preceding: Optional[TelemetrySnapshot] = None
    for snap in entries:
        if snap.wall_time < start_time:
            preceding = snap
        elif snap.wall_time <= end_time:
            result.append(snap)
    if preceding is not None:
        result.insert(0, preceding)
    return result


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp H:MM:SS.cc (centiseconds)."""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds - hours * 3600 - minutes * 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


# ASS BackColour alpha 0x66 ≈ 60 % opaque, matches drawtext box black@0.6.
# Text alpha 0x33 ≈ 80 % opaque, matches faded white@0.8.
# URL alpha 0x66 ≈ 60 % opaque, matches white@0.6.
_ASS_HEADER = (
    "[Script Info]\n"
    "ScriptType: v4.00+\n"
    "PlayResX: 1920\n"
    "PlayResY: 1080\n"
    "WrapStyle: 0\n"
    "ScaledBorderAndShadow: yes\n"
    "\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Mono22,DejaVu Sans Mono,22,&H00FFFFFF,&H00FFFFFF,"
    "&H00000000,&H66000000,0,0,0,0,100,100,0,0,3,8,0,7,0,0,0,1\n"
    "Style: Mono22Faded,DejaVu Sans Mono,22,&H33FFFFFF,&H33FFFFFF,"
    "&H00000000,&H66000000,0,0,0,0,100,100,0,0,3,8,0,7,0,0,0,1\n"
    "Style: Sans28,DejaVu Sans,28,&H00FFFFFF,&H00FFFFFF,"
    "&H00000000,&H66000000,0,0,0,0,100,100,0,0,3,8,0,7,0,0,0,1\n"
    "Style: URL,DejaVu Sans,28,&H66FFFFFF,&H66FFFFFF,"
    "&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
    "\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
    "MarginV, Effect, Text\n"
)


def _escape_ass(s: str) -> str:
    # Curly braces delimit override tags; literal braces must be escaped.
    return s.replace("{", r"\{").replace("}", r"\}")


def _dialogue(start: float, end: float, style: str, override: str, text: str) -> str:
    return (
        f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},"
        f"{style},,0,0,0,,{{{override}}}{_escape_ass(text)}\n"
    )


def generate_ass_overlay(
    entries: list[TelemetrySnapshot],
    clip_start_wall: float,
    clip_end_wall: float,
    intro_duration: float,
    output_path: Path,
) -> Path:
    """Write an ASS subtitle file replicating the drawtext HUD layout.

    Each entry holds until the next entry's wall_time (hold-last-value
    for gaps). All HUD dialogue is offset by intro_duration so it begins
    after the intro finishes playing. A static URL line spans the
    non-intro portion of the clip.
    """
    clip_duration = max(0.0, clip_end_wall - clip_start_wall)
    total_duration = intro_duration + clip_duration

    lines = [_ASS_HEADER]

    if total_duration > intro_duration:
        lines.append(_dialogue(
            intro_duration, total_duration, "URL",
            r"\an2\pos(960,1040)",
            "shit-of-theseus.com",
        ))

    for i, entry in enumerate(entries):
        video_start = intro_duration + max(0.0, entry.wall_time - clip_start_wall)
        if i + 1 < len(entries):
            video_end = intro_duration + max(
                0.0, entries[i + 1].wall_time - clip_start_wall
            )
        else:
            video_end = total_duration

        video_start = max(intro_duration, video_start)
        video_end = min(total_duration, video_end)
        if video_end <= video_start:
            continue

        lines.append(_dialogue(
            video_start, video_end, "Mono22",
            r"\an7\pos(20,1030)", entry.speed,
        ))
        lines.append(_dialogue(
            video_start, video_end, "Mono22",
            r"\an9\pos(1900,880)", entry.gforce,
        ))
        if entry.location:
            lines.append(_dialogue(
                video_start, video_end, "Sans28",
                r"\an9\pos(1900,16)", entry.location,
            ))
        lines.append(_dialogue(
            video_start, video_end, "Mono22Faded",
            r"\an9\pos(1900,56)", entry.gps_time,
        ))
        lines.append(_dialogue(
            video_start, video_end, "Mono22Faded",
            r"\an9\pos(1900,94)", entry.dist_dest,
        ))

    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path


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
