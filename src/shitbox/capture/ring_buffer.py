"""Video ring buffer using ffmpeg segment muxer for dashcam-style pre-event capture.

Continuously records rotating MPEG-TS segments to a tmpfs buffer directory.
When an event fires, copies buffer segments + waits for post-event footage,
then concatenates into a single MP4.
"""

import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class VideoRingBuffer:
    """Continuous video ring buffer with event-triggered save.

    Uses ffmpeg's segment muxer to continuously write rotating MPEG-TS segments.
    On event, copies existing segments + captures post-event footage, then
    concatenates into a single MP4 file.

    MPEG-TS is used because segments are playable even when partially written
    (MP4 requires a finalized moov atom). Concatenation uses stream copy
    (no re-encode) so it completes in <1 second.
    """

    RESTART_BACKOFF_SECONDS = 2.0
    AUDIO_RETRY_SECONDS = 30.0

    def __init__(
        self,
        buffer_dir: str = "/var/lib/shitbox/video_buffer",
        output_dir: str = "/var/lib/shitbox/captures",
        device: str = "/dev/video0",
        resolution: str = "1280x720",
        fps: int = 30,
        audio_device: str = "default",
        segment_seconds: int = 10,
        buffer_segments: int = 5,
        post_event_seconds: int = 30,
        overlay_path: Optional[str] = None,
    ):
        self.buffer_dir = Path(buffer_dir)
        self.output_dir = Path(output_dir)
        self.device = device
        self.resolution = resolution
        self.fps = fps
        self.audio_device = audio_device
        self.segment_seconds = segment_seconds
        self.buffer_segments = buffer_segments
        self.post_event_seconds = post_event_seconds
        self.overlay_path = overlay_path

        self._process: Optional[subprocess.Popen] = None
        self._health_thread: Optional[threading.Thread] = None
        self._running = False
        self._audio_available = True
        self._save_counter = 0
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Check if the ffmpeg segment process is alive."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def start(self) -> None:
        """Start the continuous segment recording and health monitor."""
        if self._running:
            return

        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._start_ffmpeg()

        self._health_thread = threading.Thread(
            target=self._health_monitor, daemon=True, name="video-ring-health"
        )
        self._health_thread.start()
        log.info(
            "video_ring_buffer_started",
            buffer_dir=str(self.buffer_dir),
            segment_seconds=self.segment_seconds,
            buffer_segments=self.buffer_segments,
        )

    def stop(self) -> None:
        """Stop recording and clean up buffer directory."""
        self._running = False

        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2.0)
            except Exception as e:
                log.error("video_ring_buffer_stop_error", error=str(e))

        self._process = None

        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=3.0)

        # Clean up buffer segments
        self._cleanup_buffer()
        log.info("video_ring_buffer_stopped")

    def save_event(
        self,
        prefix: str = "event",
        post_seconds: Optional[int] = None,
        callback: Optional[Callable[[Optional[Path]], None]] = None,
    ) -> None:
        """Save pre-event buffer + post-event recording to a single MP4.

        Runs in a background thread so it doesn't block the caller.

        Args:
            prefix: Filename prefix for the saved video.
            post_seconds: Seconds of post-event footage to capture.
                          Defaults to self.post_event_seconds.
            callback: Called with the output Path on success, or None on failure.
        """
        if post_seconds is None:
            post_seconds = self.post_event_seconds

        thread = threading.Thread(
            target=self._do_save_event,
            args=(prefix, post_seconds, callback),
            daemon=True,
            name=f"video-save-{prefix}",
        )
        thread.start()

    def capture_frame(self, filename_prefix: str = "timelapse") -> Optional[Path]:
        """Extract a JPEG frame from the latest completed segment.

        This avoids opening the camera device directly (which would conflict
        with the running ffmpeg process).

        Args:
            filename_prefix: Prefix for the output filename.

        Returns:
            Path to the JPEG file, or None if extraction failed.
        """
        segment = self._latest_complete_segment()
        if segment is None:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        output_subdir = self.output_dir / "timelapse" / today
        output_subdir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%H%M%S")
        output_path = output_subdir / f"{filename_prefix}_{timestamp}.jpg"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(segment),
            "-frames:v", "1",
            "-q:v", "2",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if result.returncode == 0 and output_path.exists():
                log.debug("timelapse_frame_extracted", output=str(output_path))
                return output_path
            else:
                stderr = result.stderr.decode()[-200:] if result.stderr else ""
                log.warning("timelapse_frame_extraction_failed", stderr=stderr)
                return None
        except subprocess.TimeoutExpired:
            log.warning("timelapse_frame_extraction_timeout")
            return None
        except Exception as e:
            log.error("timelapse_frame_extraction_error", error=str(e))
            return None

    def cleanup_old_saves(self, max_age_days: int = 14) -> int:
        """Remove saved event videos older than max_age_days.

        Args:
            max_age_days: Maximum age of files to keep.

        Returns:
            Number of files deleted.
        """
        if not self.output_dir.exists():
            return 0

        deleted = 0
        cutoff = time.time() - (max_age_days * 86400)

        for pattern in ("*.mp4", "*.jpg"):
            for media_file in self.output_dir.rglob(pattern):
                try:
                    if media_file.stat().st_mtime < cutoff:
                        media_file.unlink()
                        deleted += 1
                except Exception as e:
                    log.warning("cleanup_file_error", file=str(media_file), error=str(e))

        # Remove empty date directories
        for subdir in self.output_dir.iterdir():
            if subdir.is_dir():
                try:
                    subdir.rmdir()
                except OSError:
                    pass

        if deleted > 0:
            log.info("video_cleanup_complete", deleted=deleted)

        return deleted

    # --- Internal methods ---

    def _build_ffmpeg_cmd(self, with_audio: bool) -> list[str]:
        """Build the ffmpeg segment muxer command."""
        segment_pattern = str(self.buffer_dir / "seg_%03d.ts")

        cmd = [
            "ffmpeg", "-y",
            # Video input
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", self.resolution,
            "-framerate", str(self.fps),
            "-i", self.device,
        ]

        if with_audio:
            cmd += ["-f", "alsa", "-i", self.audio_device]

        # Video filter (overlay)
        if self.overlay_path and Path(self.overlay_path).exists():
            drawtext = (
                f"drawtext=textfile='{self.overlay_path}'"
                ":reload=1"
                ":fontcolor=white:fontsize=20:font=monospace"
                ":x=10:y=h-th-10"
                ":box=1:boxcolor=black@0.5:boxborderw=5"
            )
            cmd += ["-vf", drawtext]

        cmd += [
            # Video encoding
            "-c:v", "libx264",
            "-preset", "ultrafast",
        ]

        if with_audio:
            cmd += ["-c:a", "aac", "-b:a", "128k"]

        cmd += [
            # Segment muxer
            "-f", "segment",
            "-segment_time", str(self.segment_seconds),
            "-segment_wrap", str(self.buffer_segments),
            "-segment_format", "mpegts",
            "-reset_timestamps", "1",
            segment_pattern,
        ]

        return cmd

    def _start_ffmpeg(self) -> None:
        """Launch ffmpeg with the segment muxer.

        Tries with audio first. If ffmpeg exits within 5 seconds
        (e.g. audio device not yet enumerated), retries without audio
        so recording starts immediately. The next health-monitor restart
        will try audio again.
        """
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

        log.info(
            "video_ring_buffer_ffmpeg_starting",
            device=self.device,
            audio_device=self.audio_device,
        )

        try:
            # Try with audio
            cmd = self._build_ffmpeg_cmd(with_audio=True)
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._audio_available = True

            # Check for early crash (audio device not ready)
            time.sleep(3.0)
            if self._process.poll() is not None:
                stderr = ""
                if self._process.stderr:
                    try:
                        stderr = self._process.stderr.read().decode()[-500:]
                    except Exception:
                        pass
                log.warning(
                    "video_ring_buffer_audio_unavailable",
                    stderr=stderr,
                )
                # Fall back to video-only for now
                self._audio_available = False
                cmd = self._build_ffmpeg_cmd(with_audio=False)
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

        except FileNotFoundError:
            log.error("ffmpeg_not_found", hint="Install with: sudo apt install ffmpeg")
            self._running = False
        except Exception as e:
            log.error("video_ring_buffer_ffmpeg_start_failed", error=str(e))
            self._running = False

    def _health_monitor(self) -> None:
        """Background thread that restarts ffmpeg if it crashes.

        Also retries with audio periodically if running in video-only mode,
        since the USB audio device may not be available at boot.
        """
        last_audio_retry = time.time()

        while self._running:
            time.sleep(self.RESTART_BACKOFF_SECONDS)
            if not self._running:
                break

            # Restart if ffmpeg crashed
            if self._process is not None and self._process.poll() is not None:
                rc = self._process.returncode
                stderr = ""
                if self._process.stderr:
                    try:
                        stderr = self._process.stderr.read().decode()[-500:]
                    except Exception:
                        pass
                log.warning(
                    "video_ring_buffer_ffmpeg_crashed",
                    returncode=rc,
                    stderr=stderr,
                )
                self._start_ffmpeg()
                last_audio_retry = time.time()
                continue

            # If running without audio, periodically restart to retry audio
            if not self._audio_available:
                now = time.time()
                if (now - last_audio_retry) >= self.AUDIO_RETRY_SECONDS:
                    log.info("video_ring_buffer_retrying_audio")
                    if self._process and self._process.poll() is None:
                        self._process.terminate()
                        try:
                            self._process.wait(timeout=5.0)
                        except subprocess.TimeoutExpired:
                            self._process.kill()
                    self._start_ffmpeg()
                    last_audio_retry = time.time()

    def _get_buffer_segments(self) -> list[Path]:
        """Return buffer segment files sorted by modification time (oldest first)."""
        if not self.buffer_dir.exists():
            return []
        segments = sorted(
            self.buffer_dir.glob("seg_*.ts"),
            key=lambda p: p.stat().st_mtime,
        )
        return segments

    def _latest_complete_segment(self) -> Optional[Path]:
        """Return the most recently completed (not currently being written) segment.

        The newest segment by mtime is the one currently being written to,
        so we return the second-newest.
        """
        segments = self._get_buffer_segments()
        if len(segments) < 2:
            return None
        return segments[-2]

    def _do_save_event(
        self,
        prefix: str,
        post_seconds: int,
        callback: Optional[Callable[[Optional[Path]], None]],
    ) -> None:
        """Worker that copies buffer segments, waits for post-event, then concatenates."""
        with self._lock:
            self._save_counter += 1
            save_id = self._save_counter

        tmp_dir = self.buffer_dir / f"save_{save_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Copy completed buffer segments (pre-event footage)
            pre_segments = self._copy_complete_segments(tmp_dir, "pre")
            log.info(
                "video_save_pre_segments_copied",
                save_id=save_id,
                count=len(pre_segments),
            )

            # 2. Wait for post-event footage
            time.sleep(post_seconds)

            # 3. Copy segments created during the wait (post-event footage)
            post_segments = self._copy_complete_segments(tmp_dir, "post")
            log.info(
                "video_save_post_segments_copied",
                save_id=save_id,
                count=len(post_segments),
            )

            all_segments = pre_segments + post_segments
            if not all_segments:
                log.warning("video_save_no_segments", save_id=save_id)
                if callback:
                    callback(None)
                return

            # 4. Concatenate into a single MP4
            output_path = self._concatenate_segments(all_segments, prefix)
            if output_path:
                log.info(
                    "video_save_complete",
                    save_id=save_id,
                    output=str(output_path),
                    size_mb=round(output_path.stat().st_size / (1024 * 1024), 2),
                )
            else:
                log.error("video_save_concatenation_failed", save_id=save_id)

            if callback:
                callback(output_path)

        except Exception as e:
            log.error("video_save_error", save_id=save_id, error=str(e))
            if callback:
                callback(None)
        finally:
            # 5. Clean up temp copies
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _copy_complete_segments(self, dest_dir: Path, phase: str) -> list[Path]:
        """Copy all completed buffer segments to dest_dir.

        Skips the newest segment (currently being written to by ffmpeg).
        Files are named with phase prefix to preserve ordering across pre/post.
        """
        segments = self._get_buffer_segments()
        if len(segments) < 2:
            return []

        # Skip the newest segment (being written)
        complete = segments[:-1]
        copied = []

        for i, seg in enumerate(complete):
            dest = dest_dir / f"{phase}_{i:03d}.ts"
            try:
                shutil.copy2(str(seg), str(dest))
                copied.append(dest)
            except Exception as e:
                log.warning("segment_copy_error", src=str(seg), error=str(e))

        return copied

    def _concatenate_segments(self, segments: list[Path], prefix: str) -> Optional[Path]:
        """Concatenate MPEG-TS segments into a single MP4 using ffmpeg concat demuxer."""
        if not segments:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        output_subdir = self.output_dir / today
        output_subdir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%H%M%S")
        counter = 1
        while True:
            filename = f"{prefix}_{timestamp}_{counter:03d}.mp4"
            output_path = output_subdir / filename
            if not output_path.exists():
                break
            counter += 1

        # Build concat file list
        concat_file = segments[0].parent / "concat.txt"
        with open(concat_file, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            if result.returncode == 0 and output_path.exists():
                return output_path
            else:
                stderr = result.stderr.decode()[-300:] if result.stderr else ""
                log.error("concat_failed", returncode=result.returncode, stderr=stderr)
                return None
        except subprocess.TimeoutExpired:
            log.error("concat_timeout")
            return None
        except Exception as e:
            log.error("concat_error", error=str(e))
            return None

    def _cleanup_buffer(self) -> None:
        """Remove all files from the buffer directory."""
        if self.buffer_dir.exists():
            shutil.rmtree(str(self.buffer_dir), ignore_errors=True)
