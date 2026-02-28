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
    STALL_TIMEOUT_SECONDS = 30

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
        intro_video: str = "",
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
        self.intro_video = intro_video

        self._process: Optional[subprocess.Popen] = None
        self._health_thread: Optional[threading.Thread] = None
        self._running = False
        self._audio_available = True
        self._video_encoder = self._detect_encoder()
        self._save_counter = 0
        self._lock = threading.Lock()
        self._intro_ts: Optional[Path] = None

        # Stall detection state — reset on every ffmpeg restart
        self._last_segment_mtime: float = 0.0
        self._last_segment_size: int = 0
        self._stall_check_armed: bool = False

    @staticmethod
    def _detect_encoder() -> list[str]:
        """Probe ffmpeg for the best available H.264 encoder.

        Prefers hardware (h264_v4l2m2m) over software (libx264).
        GOP size of 30 frames (1 keyframe/sec at 30fps) ensures each
        segment starts with a keyframe for clean concatenation.
        """
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            output = result.stdout.decode()
            if "h264_v4l2m2m" in output:
                log.info("video_encoder_selected", encoder="h264_v4l2m2m")
                return ["-c:v", "h264_v4l2m2m", "-b:v", "4M", "-g", "30"]
        except Exception as e:
            log.warning("video_encoder_detection_failed", error=str(e))

        log.info("video_encoder_selected", encoder="libx264")
        return ["-c:v", "libx264", "-preset", "ultrafast", "-g", "30"]

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
        self._prepare_intro()
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

    def _prepare_intro(self) -> None:
        """Pre-convert intro video to MPEG-TS matching capture settings.

        Transcodes once and caches in buffer_dir. Re-converts only when
        the source file changes. Runs before ffmpeg starts so the hardware
        encoder is free.
        """
        if not self.intro_video:
            return

        intro_path = Path(self.intro_video)
        if not intro_path.exists():
            log.warning("intro_video_not_found", path=self.intro_video)
            return

        self._intro_ts = self.buffer_dir / "intro.ts"

        # Skip if already converted and source hasn't changed
        if self._intro_ts.exists():
            if self._intro_ts.stat().st_mtime > intro_path.stat().st_mtime:
                size_mb = round(self._intro_ts.stat().st_size / (1024 * 1024), 2)
                log.info("intro_video_cached", size_mb=size_mb)
                return

        w, h = self.resolution.split("x")
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={self.fps},format=yuv420p"
        )

        cmd = ["ffmpeg", "-y", "-i", str(intro_path), "-vf", vf]
        cmd += self._video_encoder
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000"]
        cmd += ["-f", "mpegts", str(self._intro_ts)]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=120,
            )
            if result.returncode == 0 and self._intro_ts.exists():
                size_mb = round(self._intro_ts.stat().st_size / (1024 * 1024), 2)
                log.info("intro_video_prepared", size_mb=size_mb)
            else:
                stderr = result.stderr.decode()[-500:] if result.stderr else ""
                log.error("intro_video_conversion_failed", stderr=stderr)
                self._intro_ts = None
        except subprocess.TimeoutExpired:
            log.error("intro_video_conversion_timeout")
            self._intro_ts = None
        except Exception as e:
            log.error("intro_video_conversion_error", error=str(e))
            self._intro_ts = None

    def _build_ffmpeg_cmd(self, with_audio: bool) -> list[str]:
        """Build the ffmpeg segment muxer command."""
        segment_pattern = str(self.buffer_dir / "seg_%03d.ts")

        cmd = [
            "ffmpeg", "-y",
            # Video input (thread queue prevents drops during CPU pressure)
            "-thread_queue_size", "64",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", self.resolution,
            "-framerate", str(self.fps),
            "-i", self.device,
        ]

        if with_audio:
            cmd += ["-f", "alsa", "-i", self.audio_device]

        # Video filter — drawtext overlay reads text files with reload=1
        if self.overlay_path:
            from pathlib import Path as P

            from shitbox.capture.overlay import (
                LOGO_PATH,
                build_drawtext_filter,
                build_filter_complex,
            )

            logo_exists = P(LOGO_PATH).exists()
            if logo_exists:
                # Static logo image as second (or third) input
                cmd += ["-i", LOGO_PATH]
                logo_idx = 2 if with_audio else 1
                cmd += [
                    "-filter_complex",
                    build_filter_complex(logo_idx),
                ]
                cmd += ["-map", "[out]"]
                if with_audio:
                    cmd += ["-map", "1:a"]
            else:
                cmd += ["-vf", build_drawtext_filter() + ",format=yuv420p"]
        else:
            cmd += ["-pix_fmt", "yuv420p"]

        cmd += self._video_encoder

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
        self._reset_stall_state()
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
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._audio_available = True

            # Check for early crash (audio device not ready)
            time.sleep(3.0)
            if self._process.poll() is not None:
                stderr = self._read_stderr()
                log.warning(
                    "video_ring_buffer_audio_unavailable",
                    stderr=stderr,
                )
                # Fall back to video-only
                self._audio_available = False
                cmd = self._build_ffmpeg_cmd(with_audio=False)
                self._process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

        except FileNotFoundError:
            log.error("ffmpeg_not_found", hint="Install with: sudo apt install ffmpeg")
            self._running = False
        except Exception as e:
            log.error("video_ring_buffer_ffmpeg_start_failed", error=str(e))
            self._running = False

    def _read_stderr(self) -> str:
        """Read tail of stderr from the current process."""
        if self._process and self._process.stderr:
            try:
                return self._process.stderr.read().decode()[-500:]
            except Exception:
                pass
        return ""

    def _kill_current(self) -> None:
        """Terminate the current ffmpeg process."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _reset_stall_state(self) -> None:
        """Reset stall detection state. Called at the start of every ffmpeg launch."""
        self._last_segment_mtime = 0.0
        self._last_segment_size = 0
        self._stall_check_armed = False

    def _check_stall(self) -> Optional[dict[str, object]]:
        """Check whether the ffmpeg segment output has stalled.

        Uses the newest segment's mtime and size to detect frozen output.
        Returns diagnostic info when a stall is detected, or None otherwise.
        Returns None during the startup grace period (no segments yet) and
        on the first observation (baselining).

        Returns:
            Dict with diagnostic info if stalled, None otherwise.
        """
        segments = self._get_buffer_segments()
        if not segments:
            # ffmpeg still starting up — no segments yet
            return None

        newest = segments[-1]
        try:
            st = newest.stat()
        except OSError:
            return None

        if not self._stall_check_armed:
            # First observation — arm the detector and record baseline
            self._stall_check_armed = True
            self._last_segment_mtime = st.st_mtime
            self._last_segment_size = st.st_size
            return None

        if st.st_mtime != self._last_segment_mtime or st.st_size != self._last_segment_size:
            # File activity detected — update baseline and reset timer
            self._last_segment_mtime = st.st_mtime
            self._last_segment_size = st.st_size
            return None

        # No activity — check whether the stall timeout has elapsed
        now = time.time()
        if (now - self._last_segment_mtime) > self.STALL_TIMEOUT_SECONDS:
            return {
                "segment": newest.name,
                "size_kb": round(st.st_size / 1024, 1),
                "mtime_age_s": round(now - st.st_mtime, 1),
                "segment_count": len(segments),
            }
        return None

    def _health_monitor(self) -> None:
        """Background thread that restarts ffmpeg if it crashes or stalls.

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
                stderr = self._read_stderr()
                log.warning(
                    "video_ring_buffer_ffmpeg_crashed",
                    returncode=rc,
                    stderr=stderr,
                )
                self._start_ffmpeg()
                last_audio_retry = time.time()
                continue

            # Restart if ffmpeg is alive but producing no output
            stall_info = self._check_stall()
            if stall_info:
                log.warning(
                    "ffmpeg_stall_detected",
                    timeout_seconds=self.STALL_TIMEOUT_SECONDS,
                    newest_segment=stall_info.get("segment"),
                    segment_size_kb=stall_info.get("size_kb"),
                    segment_mtime_age_s=stall_info.get("mtime_age_s"),
                    segment_count=stall_info.get("segment_count"),
                    ffmpeg_pid=self._process.pid if self._process else None,
                    ffmpeg_alive=self._process.poll() is None if self._process else False,
                    stderr_tail=self._read_stderr(),
                )
                from shitbox.capture import buzzer, speaker

                buzzer.beep_ffmpeg_stall()
                speaker.speak_ffmpeg_stall()
                self._kill_current()
                self._start_ffmpeg()
                continue

            # If running without audio, periodically restart to retry
            if not self._audio_available:
                now = time.time()
                if (now - last_audio_retry) >= self.AUDIO_RETRY_SECONDS:
                    log.info("video_ring_buffer_retrying_audio")
                    self._audio_available = True
                    self._kill_current()
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
            pre_cutoff = time.time()
            pre_segments = self._copy_complete_segments(tmp_dir, "pre")
            pre_bytes = sum(s.stat().st_size for s in pre_segments)
            log.info(
                "video_save_pre_segments_copied",
                save_id=save_id,
                count=len(pre_segments),
                size_mb=round(pre_bytes / (1024 * 1024), 2),
            )

            # 2. Wait for post-event footage
            time.sleep(post_seconds)

            # 3. Copy segments written AFTER the pre-copy (avoids duplicates)
            post_segments = self._copy_complete_segments(
                tmp_dir, "post", min_mtime=pre_cutoff,
            )
            post_bytes = sum(s.stat().st_size for s in post_segments)
            log.info(
                "video_save_post_segments_copied",
                save_id=save_id,
                count=len(post_segments),
                size_mb=round(post_bytes / (1024 * 1024), 2),
            )

            if not post_segments:
                log.warning(
                    "video_save_post_event_empty",
                    save_id=save_id,
                    hint="ffmpeg may have been restarting during post-event window",
                )

            all_segments = pre_segments + post_segments
            if not all_segments:
                log.warning("video_save_no_segments", save_id=save_id)
                if callback:
                    callback(None)
                return

            # 4. Concatenate into a single MP4
            output_path = self._concatenate_segments(all_segments, prefix)
            if output_path and output_path.exists() and output_path.stat().st_size > 0:
                log.info(
                    "video_save_complete",
                    save_id=save_id,
                    output=str(output_path),
                    size_mb=round(output_path.stat().st_size / (1024 * 1024), 2),
                )
            else:
                log.error(
                    "video_save_verification_failed",
                    save_id=save_id,
                    output=str(output_path) if output_path else "None",
                    exists=output_path.exists() if output_path else False,
                    size=output_path.stat().st_size
                    if output_path and output_path.exists()
                    else 0,
                )
                try:
                    from shitbox.capture import buzzer, speaker

                    buzzer.beep_capture_failed()
                    speaker.speak_capture_failed()
                except Exception:
                    pass  # Alert is best-effort; save callback must still fire
                output_path = None

            if callback:
                callback(output_path)

        except Exception as e:
            log.error("video_save_error", save_id=save_id, error=str(e))
            if callback:
                callback(None)
        finally:
            # 5. Clean up temp copies
            shutil.rmtree(tmp_dir, ignore_errors=True)

    MIN_SEGMENT_BYTES = 10_000  # skip incomplete/corrupt segments

    def _copy_complete_segments(
        self,
        dest_dir: Path,
        phase: str,
        min_mtime: Optional[float] = None,
    ) -> list[Path]:
        """Copy completed buffer segments to dest_dir.

        Skips the newest segment (currently being written to by ffmpeg),
        segments smaller than MIN_SEGMENT_BYTES, and optionally segments
        older than min_mtime (to avoid duplicating pre-event footage in
        the post-event copy).
        """
        segments = self._get_buffer_segments()
        if len(segments) < 2:
            return []

        # Skip the newest segment (being written)
        complete = segments[:-1]
        copied = []
        idx = 0

        for seg in complete:
            try:
                st = seg.stat()
            except OSError:
                continue
            if st.st_size < self.MIN_SEGMENT_BYTES:
                continue
            if min_mtime is not None and st.st_mtime < min_mtime:
                continue

            dest = dest_dir / f"{phase}_{idx:03d}.ts"
            try:
                shutil.copy2(str(seg), str(dest))
                copied.append(dest)
                idx += 1
            except Exception as e:
                log.warning("segment_copy_error", src=str(seg), error=str(e))

        return copied

    def _concatenate_segments(self, segments: list[Path], prefix: str) -> Optional[Path]:
        """Concatenate MPEG-TS segments into a single MP4.

        MPEG-TS is byte-concatenatable by design, so we join the .ts files
        directly and then remux to MP4 with stream copy.  This is simpler
        and more robust than the ffmpeg concat demuxer.
        """
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

        # Byte-concatenate TS segments (MPEG-TS is designed for this)
        combined_ts = segments[0].parent / "combined.ts"
        total_input_bytes = 0
        try:
            with open(combined_ts, "wb") as out:
                # Prepend intro if available
                if self._intro_ts and self._intro_ts.exists():
                    intro_size = self._intro_ts.stat().st_size
                    total_input_bytes += intro_size
                    with open(self._intro_ts, "rb") as intro:
                        shutil.copyfileobj(intro, out)

                for seg in segments:
                    seg_size = seg.stat().st_size
                    total_input_bytes += seg_size
                    with open(seg, "rb") as inp:
                        shutil.copyfileobj(inp, out)
        except Exception as e:
            log.error("concat_ts_join_error", error=str(e))
            return None

        if total_input_bytes == 0:
            log.warning("concat_no_data", segment_count=len(segments))
            combined_ts.unlink(missing_ok=True)
            return None

        log.info(
            "concat_ts_joined",
            segment_count=len(segments),
            total_mb=round(total_input_bytes / (1024 * 1024), 2),
        )

        # Remux combined TS → MP4
        # Increase probesize so ffmpeg scans past the first segment to find
        # SPS/PPS NAL units — the h264_v4l2m2m encoder may not emit them
        # until a few seconds after startup, so the first segment's headers
        # can lack video dimensions.
        cmd = [
            "ffmpeg", "-y",
            "-analyzeduration", "20000000",
            "-probesize", "20000000",
            "-i", str(combined_ts),
            "-c", "copy",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            combined_ts.unlink(missing_ok=True)

            if result.returncode == 0 and output_path.exists():
                size = output_path.stat().st_size
                if size > 0:
                    return output_path
                # ffmpeg succeeded but produced empty file
                input_mb = round(total_input_bytes / (1024 * 1024), 2)
                log.error("concat_empty_output", input_mb=input_mb)
                output_path.unlink(missing_ok=True)
                return None
            else:
                stderr = result.stderr.decode()[-500:] if result.stderr else ""
                log.error("concat_failed", returncode=result.returncode, stderr=stderr)
                # Clean up 0-byte output
                if output_path.exists():
                    output_path.unlink(missing_ok=True)
                return None
        except subprocess.TimeoutExpired:
            log.error("concat_timeout")
            combined_ts.unlink(missing_ok=True)
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            return None
        except Exception as e:
            log.error("concat_error", error=str(e))
            combined_ts.unlink(missing_ok=True)
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            return None

    def _cleanup_buffer(self) -> None:
        """Remove all files from the buffer directory."""
        if self.buffer_dir.exists():
            shutil.rmtree(str(self.buffer_dir), ignore_errors=True)
