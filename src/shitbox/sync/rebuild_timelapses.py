"""Rebuild per-day timelapse videos from their source frames.

The live :class:`~shitbox.sync.timelapse_compiler.TimelapseCompiler` compiles a
day exactly once and then skips it forever (the presence of ``timelapse.mp4`` is
its "done" marker). This entry point forces a rebuild: it clears a day's output
and any orphaned temp files, then re-runs the *same* compile path — intro +
rally-branded title card + frames — so a rebuild is byte-for-byte what production
would have produced, not a stitch onto the finished video.

Frames are the source of truth; empty/truncated JPEGs are dropped by the
compiler. Dry-run by default: prints the plan and writes nothing.

Usage (on the Pi, in the venv)::

    python -m shitbox.sync.rebuild_timelapses                 # dry run, all days
    python -m shitbox.sync.rebuild_timelapses --yes           # rebuild all days
    python -m shitbox.sync.rebuild_timelapses --day 2026-07-11 --yes
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from shitbox.events.engine import EngineConfig
from shitbox.sync.timelapse_compiler import TimelapseCompiler
from shitbox.utils.config import load_config

# Temp/leftover artefacts a rebuild must clear so the compile starts clean.
_STALE_NAMES = (
    "timelapse.mp4",
    "timelapse.frames.mp4",
    "timelapse.tmp.mp4",
    "timelapse.intro.mp4",
    "timelapse.card.mp4",
    "timelapse.card.png",
    "timelapse.lock",
)


def _is_day(name: str) -> bool:
    try:
        datetime.strptime(name, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _discover_days(captures_dir: Path) -> List[str]:
    """All dates that have a frame directory, oldest first."""
    frames_root = captures_dir / "timelapse"
    if not frames_root.exists():
        return []
    return sorted(d.name for d in frames_root.iterdir() if d.is_dir() and _is_day(d.name))


def _clear_outputs(captures_dir: Path, day: str) -> List[str]:
    """Remove the compiled output and orphan temps for ``day``. Returns names removed."""
    out_dir = captures_dir / day
    removed: List[str] = []
    for name in _STALE_NAMES:
        p = out_dir / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild timelapse videos from source frames.")
    parser.add_argument("--config", "-c", default="config/config.yaml", help="Path to config file")
    parser.add_argument(
        "--day",
        action="append",
        metavar="YYYY-MM-DD",
        help="Rebuild only this day (repeatable). Default: every day with frames.",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Actually rebuild. Without this, dry run."
    )
    args = parser.parse_args()

    yaml_config = load_config(args.config)
    config = EngineConfig.from_yaml_config(yaml_config)
    captures_dir = Path(config.captures_dir)

    compiler = TimelapseCompiler(
        captures_dir=config.captures_dir,
        fps=config.timelapse_compile_fps,
        max_seconds=config.timelapse_max_seconds,
        intro_video=config.video_buffer_intro_video,
        db_path=config.database_path,
        rally_title=config.timelapse_rally_title,
        rally_start_date=config.rally_start_date,
        day_routes=config.timelapse_day_routes,
    )

    days = args.day if args.day else _discover_days(captures_dir)
    if not days:
        print(f"no frame directories under {captures_dir / 'timelapse'}", file=sys.stderr)
        return 1

    mode = "WRITE (--yes)" if args.yes else "dry run"
    print("=== rebuild timelapses ===")
    print(f"captures : {captures_dir}")
    print(f"fps={config.timelapse_compile_fps}  max_seconds={config.timelapse_max_seconds}  "
          f"rally_start={config.rally_start_date or '<unset>'}")
    print(f"mode     : {mode}\n")

    rebuilt = 0
    for day in days:
        frames = TimelapseCompiler._valid_frames(captures_dir / "timelapse" / day)
        if not frames:
            print(f"{day}  skip — no usable frames")
            continue

        day_num = compiler._day_number(day)
        label = f"Day {day_num}" if day_num is not None else "pre-rally"
        print(f"{day}  {label} · {len(frames)} frames")
        if not args.yes:
            continue

        removed = _clear_outputs(captures_dir, day)
        if removed:
            print(f"   cleared: {', '.join(removed)}")
        compiler._compile_day(day)
        output = captures_dir / day / "timelapse.mp4"
        if output.exists() and output.stat().st_size > 0:
            print(f"   wrote {output} ({output.stat().st_size // (1024 * 1024)} MB)")
            rebuilt += 1
        else:
            print(f"   FAILED — {output} not produced", file=sys.stderr)

    if args.yes:
        compiler.generate_timelapse_json()
        print(f"\n{rebuilt}/{len(days)} day(s) rebuilt. timelapse.json regenerated.")
    else:
        print(f"\n{len(days)} day(s) would be rebuilt. Re-run with --yes to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
