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

    OUTPUT_FPS = 24
    MAX_SECONDS = 120

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
        lock_path = output_dir / "timelapse.lock"
        tmp_frames = output_dir / "timelapse.frames.mp4"
        tmp_path = output_dir / "timelapse.tmp.mp4"

        # Guard against multiple processes compiling the same day simultaneously
        try:
            lock_path.touch(exist_ok=False)
        except FileExistsError:
            log.debug("timelapse_compile_skipped_locked", date=day)
            return

        try:
            # Duration scales with frame count at OUTPUT_FPS; cap at MAX_SECONDS
            duration_s = min(len(frames) / self.OUTPUT_FPS, self.MAX_SECONDS)
            per_frame = duration_s / len(frames)
            log.info("timelapse_compiling", date=day, frame_count=len(frames), fps=self.OUTPUT_FPS, duration_s=round(duration_s, 1))

            # Write concat demuxer list — explicit per-frame duration avoids fps rounding issues
            frames_txt = output_dir / "timelapse.frames.txt"
            with frames_txt.open("w") as f:
                for img in frames:
                    f.write(f"file '{img.as_posix()}'\n")
                    f.write(f"duration {per_frame:.6f}\n")
                # Repeat last frame so its duration is honoured by the demuxer
                f.write(f"file '{frames[-1].as_posix()}'\n")

            # Pass 1: compile frames → temp MP4
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(frames_txt),
                "-r", "24",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "18", "-preset", "ultrafast",
                str(tmp_frames),
            ]
            try:
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
                frames_txt.unlink(missing_ok=True)
                if result.returncode != 0 or not tmp_frames.exists():
                    stderr = result.stderr.decode()[-500:] if result.stderr else ""
                    log.error("timelapse_compile_failed", date=day, stderr=stderr)
                    tmp_frames.unlink(missing_ok=True)
                    return
            except subprocess.TimeoutExpired:
                log.error("timelapse_compile_timeout", date=day)
                frames_txt.unlink(missing_ok=True)
                tmp_frames.unlink(missing_ok=True)
                return
            except Exception as exc:
                log.error("timelapse_compile_error", date=day, error=str(exc))
                frames_txt.unlink(missing_ok=True)
                tmp_frames.unlink(missing_ok=True)
                return

            # Pass 2: prepend intro if available.
            # Pre-transcode intro to match timelapse specs (1280x720, 24fps, yuv420p)
            # before concatenating — avoids resolution/fps mismatch in the concat filter.
            intro = Path(self._intro_video) if self._intro_video else None
            if intro and intro.exists() and intro.stat().st_size > 0:
                tmp_intro = output_dir / "timelapse.intro.mp4"
                intro_cmd = [
                    "ffmpeg", "-y", "-i", str(intro),
                    "-vf", "scale=1280:720,fps=24,format=yuv420p",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-an",
                    str(tmp_intro),
                ]
                intro_ok = False
                try:
                    r = subprocess.run(intro_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
                    intro_ok = r.returncode == 0 and tmp_intro.exists() and tmp_intro.stat().st_size > 0
                    if not intro_ok:
                        stderr = r.stderr.decode()[-300:] if r.stderr else ""
                        log.warning("timelapse_intro_transcode_failed", date=day, stderr=stderr)
                        tmp_intro.unlink(missing_ok=True)
                except Exception as exc:
                    log.error("timelapse_intro_transcode_error", date=day, error=str(exc))
                    tmp_intro.unlink(missing_ok=True)

                if intro_ok:
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(tmp_intro),
                        "-i", str(tmp_frames),
                        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[out]",
                        "-map", "[out]",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                        str(tmp_path),
                    ]
                    try:
                        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
                        tmp_intro.unlink(missing_ok=True)
                        if result.returncode != 0 or not tmp_path.exists():
                            stderr = result.stderr.decode()[-500:] if result.stderr else ""
                            log.warning("timelapse_intro_concat_failed", date=day, stderr=stderr,
                                        hint="falling back to frames-only")
                            tmp_path.unlink(missing_ok=True)
                            tmp_frames.rename(tmp_path)
                        else:
                            tmp_frames.unlink(missing_ok=True)
                    except Exception as exc:
                        log.error("timelapse_intro_concat_error", date=day, error=str(exc))
                        tmp_intro.unlink(missing_ok=True)
                        tmp_path.unlink(missing_ok=True)
                        tmp_frames.rename(tmp_path)
                else:
                    tmp_frames.rename(tmp_path)
            else:
                tmp_frames.rename(tmp_path)

            os.replace(str(tmp_path), str(output_path))
            log.info("timelapse_compiled", date=day, frame_count=len(frames), fps=self.OUTPUT_FPS, duration_s=round(duration_s, 1), output=str(output_path))
        finally:
            lock_path.unlink(missing_ok=True)

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
