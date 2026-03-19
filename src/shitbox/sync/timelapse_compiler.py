"""Timelapse video compiler service.

Compiles per-day JPEG frames captured by the ring buffer into MP4 videos.
Runs pending compilations at startup in a background thread, then watches
for day rollover to compile the just-completed day.

Frame layout:  <captures_dir>/timelapse/<date>/timelapse_*.jpg
Output layout: <captures_dir>/<date>/timelapse.mp4
Index:         <captures_dir>/timelapse.json
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class TimelapseCompiler:
    """Compile per-day timelapse frames into MP4 videos.

    Gracefully skips days with no frames and days where the MP4 already exists.
    """

    TARGET_MIN_SECONDS = 30
    TARGET_MAX_SECONDS = 90
    BASE_FPS = 24

    def __init__(self, captures_dir: str, fps: int = 24, intro_video: str = "") -> None:
        self._captures_dir = Path(captures_dir)
        self._fps = fps  # kept for compatibility; dynamic fps overrides per compile
        self._intro_video = intro_video
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        """Kick off background compilation and day-rollover watcher."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="timelapse-compiler"
        )
        self._thread.start()
        log.info("timelapse_compiler_started", captures_dir=str(self._captures_dir), fps=self._fps)

    def stop(self) -> None:
        """Stop the day-rollover watcher."""
        self._running = False

    def _run(self) -> None:
        """Compile pending days at startup, then watch for day rollover."""
        self._compile_pending()

        last_date = date.today()
        while self._running:
            time.sleep(60)
            today = date.today()
            if today != last_date:
                self._compile_day(last_date.isoformat())
                self.generate_timelapse_json()
                last_date = today

    def _compile_pending(self) -> None:
        """Compile all past days that have frames but no compiled MP4."""
        frames_root = self._captures_dir / "timelapse"
        if not frames_root.exists():
            log.debug("timelapse_no_frames_dir", path=str(frames_root))
            return

        today = date.today().isoformat()
        compiled_any = False

        for day_dir in sorted(frames_root.iterdir()):
            if not day_dir.is_dir():
                continue
            day = day_dir.name
            if day >= today:
                continue  # Still being written
            output = self._captures_dir / day / "timelapse.mp4"
            if output.exists():
                continue  # Already done
            frames = list(day_dir.glob("timelapse_*.jpg"))
            if not frames:
                continue
            self._compile_day(day)
            compiled_any = True

        if compiled_any:
            self.generate_timelapse_json()

    def _target_fps(self, frame_count: int) -> float:
        """Calculate fps so output duration falls between TARGET_MIN and TARGET_MAX seconds."""
        ideal = frame_count / self.BASE_FPS
        target_duration = max(self.TARGET_MIN_SECONDS, min(self.TARGET_MAX_SECONDS, ideal))
        return frame_count / target_duration

    def _compile_day(self, day: str) -> None:
        """Compile all frames for a single day into an MP4."""
        day_dir = self._captures_dir / "timelapse" / day
        frames = sorted(day_dir.glob("timelapse_*.jpg"))
        if not frames:
            log.info("timelapse_no_frames", date=day)
            return

        output_dir = self._captures_dir / day
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "timelapse.mp4"
        tmp_frames = output_dir / "timelapse.frames.mp4"
        tmp_path = output_dir / "timelapse.tmp.mp4"

        fps = self._target_fps(len(frames))
        duration_s = round(len(frames) / fps)
        log.info("timelapse_compiling", date=day, frame_count=len(frames), fps=round(fps, 2), duration_s=duration_s)

        # Pass 1: compile frames → temp MP4
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-pattern_type", "glob",
            "-i", str(day_dir / "timelapse_*.jpg"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            str(tmp_frames),
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
            if result.returncode != 0 or not tmp_frames.exists():
                stderr = result.stderr.decode()[-500:] if result.stderr else ""
                log.error("timelapse_compile_failed", date=day, stderr=stderr)
                tmp_frames.unlink(missing_ok=True)
                return
        except subprocess.TimeoutExpired:
            log.error("timelapse_compile_timeout", date=day)
            tmp_frames.unlink(missing_ok=True)
            return
        except Exception as exc:
            log.error("timelapse_compile_error", date=day, error=str(exc))
            tmp_frames.unlink(missing_ok=True)
            return

        # Pass 2: prepend intro if available
        intro = Path(self._intro_video) if self._intro_video else None
        if intro and intro.exists():
            cmd = [
                "ffmpeg", "-y",
                "-i", str(intro),
                "-i", str(tmp_frames),
                "-filter_complex", "[0:v][1:v]concat=n=2:v=1[out]",
                "-map", "[out]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
                str(tmp_path),
            ]
            try:
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
                tmp_frames.unlink(missing_ok=True)
                if result.returncode != 0 or not tmp_path.exists():
                    stderr = result.stderr.decode()[-500:] if result.stderr else ""
                    log.error("timelapse_intro_concat_failed", date=day, stderr=stderr)
                    tmp_path.unlink(missing_ok=True)
                    return
            except Exception as exc:
                log.error("timelapse_intro_concat_error", date=day, error=str(exc))
                tmp_frames.unlink(missing_ok=True)
                tmp_path.unlink(missing_ok=True)
                return
        else:
            tmp_frames.rename(tmp_path)

        os.replace(str(tmp_path), str(output_path))
        log.info("timelapse_compiled", date=day, frame_count=len(frames), fps=round(fps, 2), duration_s=duration_s, output=str(output_path))

    def generate_timelapse_json(self, video_base_url: str = "/captures") -> Optional[Path]:
        """Write captures/timelapse.json listing all compiled timelapse videos."""
        self._captures_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._captures_dir / "timelapse.json"

        entries = []
        for mp4 in sorted(self._captures_dir.glob("*/timelapse.mp4")):
            day = mp4.parent.name
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                continue

            frame_dir = self._captures_dir / "timelapse" / day
            frame_count = len(list(frame_dir.glob("timelapse_*.jpg"))) if frame_dir.exists() else 0

            entries.append({
                "date": day,
                "video_url": f"{video_base_url}/{day}/timelapse.mp4",
                "frame_count": frame_count,
            })

        entries.sort(key=lambda e: e["date"], reverse=True)

        tmp_path = out_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(entries, f, indent=2)
        os.replace(str(tmp_path), str(out_path))

        log.info("timelapse_json_generated", path=str(out_path), count=len(entries))
        return out_path
