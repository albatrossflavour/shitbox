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
import sqlite3
import subprocess
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class TimelapseCompiler:
    """Compile per-day timelapse frames into MP4 videos.

    Gracefully skips days with no frames and days where the MP4 already exists.
    """

    OUTPUT_FPS = 24
    MAX_SECONDS = 120
    TITLE_CARD_SECONDS = 2.5

    def __init__(
        self,
        captures_dir: str,
        fps: int = 24,
        intro_video: str = "",
        db_path: str = "",
    ) -> None:
        self._captures_dir = Path(captures_dir)
        self._fps = fps  # kept for compatibility; dynamic fps overrides per compile
        self._intro_video = intro_video
        self._db_path = db_path
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._geocoder: Any = None
        self._geocoder_tried = False

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

    def _first_gps_fix(self, day: str) -> Optional[tuple[float, float, str]]:
        """Return (lat, lon, timestamp_utc) of the first GPS fix on ``day``, or None."""
        if not self._db_path:
            return None
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT timestamp_utc, latitude, longitude FROM readings "
                    "WHERE sensor_type='gps' AND latitude IS NOT NULL "
                    "AND longitude IS NOT NULL AND substr(timestamp_utc,1,10)=? "
                    "ORDER BY timestamp_utc ASC LIMIT 1",
                    (day,),
                ).fetchone()
            finally:
                conn.close()
            if row is None:
                return None
            return float(row["latitude"]), float(row["longitude"]), row["timestamp_utc"]
        except Exception as exc:
            log.debug("timelapse_first_gps_query_failed", date=day, error=str(exc))
            return None

    def _resolve_place_name(self, lat: float, lon: float) -> Optional[str]:
        """Reverse-geocode (lat, lon) to a place name. Lazy-inits the library."""
        if not self._geocoder_tried:
            self._geocoder_tried = True
            try:
                import reverse_geocoder as rg  # type: ignore[import-untyped]
                self._geocoder = rg
            except Exception as exc:
                log.debug("timelapse_geocoder_unavailable", error=str(exc))
                self._geocoder = None
        if self._geocoder is None:
            return None
        try:
            results = self._geocoder.search((lat, lon))
            if not results:
                return None
            r = results[0]
            name = r.get("name", "") or ""
            admin1 = r.get("admin1", "") or ""
            if name and admin1:
                return f"{name}, {admin1}"
            return name or None
        except Exception as exc:
            log.debug("timelapse_geocode_failed", error=str(exc))
            return None

    @staticmethod
    def _escape_drawtext(s: str) -> str:
        """Escape characters that are special to ffmpeg drawtext ``text=`` values."""
        return s.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")

    def _generate_title_card(
        self, day: str, output_dir: Path, start_mtime: Optional[float]
    ) -> Optional[Path]:
        """Render a title card MP4 announcing the day's start. Returns path or None."""
        card_path = output_dir / "timelapse.card.mp4"

        try:
            dt = datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return None
        date_line = dt.strftime("%A, %-d %B %Y")

        location: Optional[str] = None
        time_line: Optional[str] = None
        gps = self._first_gps_fix(day)
        if gps is not None:
            lat, lon, ts = gps
            location = self._resolve_place_name(lat, lon)
            try:
                fix_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                time_line = fix_dt.astimezone().strftime("%H:%M")
            except Exception:
                pass

        if time_line is None and start_mtime is not None:
            time_line = datetime.fromtimestamp(start_mtime).strftime("%H:%M")

        filters = [
            "drawtext=font=DejaVu Sans:text='" + self._escape_drawtext(date_line) + "'"
            ":fontsize=44:fontcolor=0xf0dbb8:x=(w-text_w)/2:y=h/2-120",
        ]
        if location:
            filters.append(
                "drawtext=font=DejaVu Sans:text='" + self._escape_drawtext(location) + "'"
                ":fontsize=72:fontcolor=white:x=(w-text_w)/2:y=h/2-40"
            )
        if time_line:
            filters.append(
                "drawtext=font=DejaVu Sans:text='"
                + self._escape_drawtext("Started " + time_line)
                + "':fontsize=36:fontcolor=0xc9d1d9:x=(w-text_w)/2:y=h/2+60"
            )
        filters.append(
            "drawtext=font=DejaVu Sans:text='shit-of-theseus.com'"
            ":fontsize=22:fontcolor=0x8b949e:x=(w-text_w)/2:y=h-60"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=0x0d1117:size=1280x720:rate=24:duration={self.TITLE_CARD_SECONDS}",
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-an",
            str(card_path),
        ]
        try:
            r = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60
            )
            if r.returncode == 0 and card_path.exists() and card_path.stat().st_size > 0:
                log.info(
                    "timelapse_title_card_generated",
                    date=day,
                    location=location,
                    time=time_line,
                )
                return card_path
            stderr = r.stderr.decode()[-400:] if r.stderr else ""
            log.warning("timelapse_title_card_failed", date=day, stderr=stderr)
        except Exception as exc:
            log.error("timelapse_title_card_error", date=day, error=str(exc))
        card_path.unlink(missing_ok=True)
        return None

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
        frames = sorted(day_dir.glob("timelapse_*.jpg"), key=lambda p: p.stat().st_mtime)
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
            log.info(
                "timelapse_compiling",
                date=day,
                frame_count=len(frames),
                fps=self.OUTPUT_FPS,
                duration_s=round(duration_s, 1),
            )

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
                result = subprocess.run(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300
                )
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
                    r = subprocess.run(
                        intro_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120
                    )
                    intro_ok = (
                        r.returncode == 0 and tmp_intro.exists() and tmp_intro.stat().st_size > 0
                    )
                    if not intro_ok:
                        stderr = r.stderr.decode()[-300:] if r.stderr else ""
                        log.warning("timelapse_intro_transcode_failed", date=day, stderr=stderr)
                        tmp_intro.unlink(missing_ok=True)
                except Exception as exc:
                    log.error("timelapse_intro_transcode_error", date=day, error=str(exc))
                    tmp_intro.unlink(missing_ok=True)

                if intro_ok:
                    # Title card — sits between the static intro and the live footage
                    # so the viewer lands gently with a date/location/time marker.
                    first_frame_mtime = frames[0].stat().st_mtime if frames else None
                    tmp_card = self._generate_title_card(day, output_dir, first_frame_mtime)

                    clips = [tmp_intro]
                    if tmp_card is not None:
                        clips.append(tmp_card)
                    clips.append(tmp_frames)
                    n = len(clips)
                    concat_filter = (
                        "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1[out]"
                    )

                    cmd = ["ffmpeg", "-y"]
                    for clip in clips:
                        cmd.extend(["-i", str(clip)])
                    cmd.extend([
                        "-filter_complex", concat_filter,
                        "-map", "[out]",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                        str(tmp_path),
                    ])
                    try:
                        result = subprocess.run(
                            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300
                        )
                        tmp_intro.unlink(missing_ok=True)
                        if tmp_card is not None:
                            tmp_card.unlink(missing_ok=True)
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
                        if tmp_card is not None:
                            tmp_card.unlink(missing_ok=True)
                        tmp_path.unlink(missing_ok=True)
                        tmp_frames.rename(tmp_path)
                else:
                    tmp_frames.rename(tmp_path)
            else:
                tmp_frames.rename(tmp_path)

            os.replace(str(tmp_path), str(output_path))
            log.info(
                "timelapse_compiled",
                date=day,
                frame_count=len(frames),
                fps=self.OUTPUT_FPS,
                duration_s=round(duration_s, 1),
                output=str(output_path),
            )
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
