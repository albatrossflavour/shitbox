"""Video ring buffer using ffmpeg segment muxer for dashcam-style pre-event capture.

Continuously records rotating MPEG-TS segments to a tmpfs buffer directory.
When an event fires, copies buffer segments + waits for post-event footage,
then concatenates into a single MP4.
"""

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

_PIP_POSITION_MAP = {
    "bottom_right": ("W-w-10", "H-h-10"),
    "bottom_left": ("10", "H-h-10"),
    "top_right": ("W-w-10", "10"),
    "top_left": ("10", "10"),
}

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
    DEVICE_MISSING_BACKOFF_SECONDS = 30.0

    def __init__(
        self,
        buffer_dir: str = "/var/lib/shitbox/video_buffer",
        output_dir: str = "/var/lib/shitbox/captures",
        device: str = "/dev/video0",
        input_format: str = "mjpeg",
        resolution: str = "1280x720",
        fps: int = 30,
        audio_device: str = "default",
        segment_seconds: int = 10,
        buffer_segments: int = 5,
        post_event_seconds: int = 30,
        overlay_path: Optional[str] = None,
        intro_video: str = "",
        pip_device: str = "",
        pip_input_format: str = "mjpeg",
        pip_resolution: str = "640x480",
        pip_fps: int = 15,
        pip_position: str = "bottom_right",
        pip_scale: float = 0.25,
        camera_controls: Optional[dict[str, int]] = None,
        pip_camera_controls: Optional[dict[str, int]] = None,
    ):
        self.buffer_dir = Path(buffer_dir)
        self.output_dir = Path(output_dir)
        self.device = device
        self.input_format = input_format
        self.resolution = resolution
        self.fps = fps
        self.audio_device = audio_device
        self.segment_seconds = segment_seconds
        self.buffer_segments = buffer_segments
        self.post_event_seconds = post_event_seconds
        self.overlay_path = overlay_path
        self.intro_video = intro_video
        self.pip_device = pip_device
        self.pip_input_format = pip_input_format
        self.pip_resolution = pip_resolution
        self.pip_fps = pip_fps
        self.pip_position = pip_position
        self.pip_scale = pip_scale
        self.camera_controls = camera_controls or {}
        self.pip_camera_controls = pip_camera_controls or {}

        self._process: Optional[subprocess.Popen] = None
        self._health_thread: Optional[threading.Thread] = None
        self._running = False
        self._audio_available = bool(audio_device)  # False when no device configured
        self._video_encoder = ["-c:v", "libx264", "-preset", "ultrafast", "-g", "30"]
        self._save_counter = 0
        self._lock = threading.Lock()
        self._intro_ts: Optional[Path] = None
        self._last_timelapse_segment: Optional[Path] = None
        self._ffmpeg_started_at: float = 0.0

    def _configure_cameras(self) -> None:
        """Apply v4l2 controls to cameras before recording starts."""
        device_controls = [
            (self.device, self.camera_controls),
            (self.pip_device, self.pip_camera_controls),
        ]
        for device, controls in device_controls:
            if not device or not controls or not os.path.exists(device):
                continue
            for ctrl, value in controls.items():
                try:
                    subprocess.run(
                        [
                            "v4l2-ctl", "--device", device,
                            "--set-ctrl", f"{ctrl}={value}",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        timeout=5,
                    )
                    log.info(
                        "camera_ctrl_set",
                        device=device, ctrl=ctrl, value=value,
                    )
                except FileNotFoundError:
                    log.warning(
                        "v4l2ctl_not_found",
                        hint="Install: sudo apt install v4l-utils",
                    )
                    return
                except Exception as e:
                    log.warning(
                        "camera_ctrl_failed",
                        device=device, ctrl=ctrl, error=str(e),
                    )

    @property
    def is_running(self) -> bool:
        """Check if the ffmpeg segment process is alive."""
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def intro_duration_seconds(self) -> float:
        """Duration of the intro clip in seconds, or 0.0 if none."""
        if not self._intro_ts or not self._intro_ts.exists():
            return 0.0
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(self._intro_ts),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return float(result.stdout.decode().strip())
        except Exception:
            return 0.0

    def start(self) -> None:
        """Start the continuous segment recording and health monitor."""
        if self._running:
            return

        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_buffer()  # Clear stale segments from previous run
        self._prepare_intro()
        self._configure_cameras()
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
        callback: Optional[Callable[[Optional[Path], float], None]] = None,
    ) -> None:
        """Save pre-event buffer + post-event recording to a single MP4.

        Runs in a background thread so it doesn't block the caller.

        Args:
            prefix: Filename prefix for the saved video.
            post_seconds: Seconds of post-event footage to capture.
                          Defaults to self.post_event_seconds.
            callback: Called with (output Path or None, clip_start_mtime).
                      clip_start_mtime is the filesystem mtime of the oldest
                      pre-event segment — a GPS-clock wall-clock timestamp usable
                      for cross-camera sync alignment.
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

        # Skip if this segment was already used — guards against duplicate frames
        # during a ffmpeg stall where the same segment stays newest indefinitely.
        if segment == self._last_timelapse_segment:
            log.debug("timelapse_frame_skipped_stale_segment", segment=str(segment))
            return None
        self._last_timelapse_segment = segment

        today = datetime.now().strftime("%Y-%m-%d")
        output_subdir = self.output_dir / "timelapse" / today
        output_subdir.mkdir(parents=True, exist_ok=True)

        # Monotonic sequence number — survives service restarts without reordering
        existing = sorted(output_subdir.glob(f"{filename_prefix}_*.jpg"))
        seq = len(existing) + 1
        output_path = output_subdir / f"{filename_prefix}_{seq:05d}.jpg"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(segment),
            "-frames:v", "1",
            "-q:v", "5",
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
                poster_path = self.output_dir / "intro_poster.jpg"
                if not poster_path.exists():
                    self._extract_intro_poster(intro_path)
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
                self._extract_intro_poster(intro_path)
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

    def _extract_intro_poster(self, intro_path: Path) -> None:
        """Extract a single JPEG frame from the intro video for use as a video poster."""
        poster_path = self.output_dir / "intro_poster.jpg"
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", "0.5", "-i", str(intro_path),
                    "-frames:v", "1", "-q:v", "3",
                    str(poster_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            if result.returncode == 0 and poster_path.exists():
                log.info("intro_poster_extracted", path=str(poster_path))
        except Exception as e:
            log.warning("intro_poster_extraction_failed", error=str(e))

    def _build_ffmpeg_cmd(self, with_audio: bool) -> list[str]:
        """Build the ffmpeg segment muxer command."""
        segment_pattern = str(self.buffer_dir / "seg_%03d.ts")

        cmd = [
            "ffmpeg", "-y",
            # Primary camera — rtbufsize absorbs short bursts; thread_queue_size
            # prevents drops during CPU pressure.
            "-thread_queue_size", "512",
            "-rtbufsize", "200M",
            "-f", "v4l2",
            "-input_format", self.input_format,
            "-video_size", self.resolution,
            "-framerate", str(self.fps),
            "-i", self.device,
        ]

        if self.pip_device:
            # Secondary (cabin) camera
            cmd += [
                "-thread_queue_size", "512",
                "-rtbufsize", "200M",
                "-f", "v4l2",
                "-input_format", self.pip_input_format,
                "-video_size", self.pip_resolution,
                "-framerate", str(self.pip_fps),
                "-i", self.pip_device,
            ]

        if with_audio:
            cmd += ["-f", "alsa", "-i", self.audio_device]

        if self.pip_device:
            # Real-time PiP composite — [0:v] primary, [1:v] cabin
            # Input indices: 0=front, 1=cabin, then optionally audio,
            # then optionally logo PNG.
            from pathlib import Path as P

            from shitbox.capture.overlay import LOGO_PATH

            x, y = _PIP_POSITION_MAP.get(
                self.pip_position, ("W-w-10", "H-h-10"),
            )
            audio_idx = 2  # always after primary + pip
            logo_exists = self.overlay_path and P(LOGO_PATH).exists()
            if logo_exists:
                cmd += ["-i", LOGO_PATH]
                logo_idx = 3 if with_audio else 2

            if self.overlay_path:
                from shitbox.capture.overlay import build_drawtext_filter
                hud = build_drawtext_filter()
                if logo_exists:
                    # PiP + HUD drawtext + logo overlay
                    logo_prep = (
                        f"[{logo_idx}:v]"
                        "format=rgba,colorchannelmixer=aa=0.4"
                        "[logo]"
                    )
                    composite = (
                        f"[0:v][pip]overlay={x}:{y},"
                        f"{hud}[text];"
                        "[text][logo]overlay=10:10,"
                        "format=yuv420p[out]"
                    )
                else:
                    logo_prep = ""
                    composite = (
                        f"[0:v][pip]overlay={x}:{y},"
                        f"{hud},format=yuv420p[out]"
                    )
            else:
                logo_prep = ""
                composite = (
                    f"[0:v][pip]overlay={x}:{y},"
                    "format=yuv420p[out]"
                )

            pip_chain = (
                f"[1:v]scale=iw*{self.pip_scale}:-2,"
                "pad=iw+4:ih+20:2:18:color=black@0.7,"
                "drawtext=text='Cabin':"
                "fontsize=13:fontcolor=white@0.9:x=6:y=3[pip]"
            )
            parts = [p for p in [logo_prep, pip_chain, composite] if p]
            filter_complex = ";".join(parts)

            cmd += ["-filter_complex", filter_complex, "-map", "[out]"]
            if with_audio:
                cmd += ["-map", f"{audio_idx}:a"]
        elif self.overlay_path:
            # Single-camera drawtext overlay
            from pathlib import Path as P

            from shitbox.capture.overlay import (
                LOGO_PATH,
                build_drawtext_filter,
                build_filter_complex,
            )

            logo_exists = P(LOGO_PATH).exists()
            if logo_exists:
                cmd += ["-i", LOGO_PATH]
                logo_idx = 2 if with_audio else 1
                cmd += ["-filter_complex", build_filter_complex(logo_idx)]
                cmd += ["-map", "[out]"]
                if with_audio:
                    cmd += ["-map", "1:a"]
            else:
                cmd += ["-vf", build_drawtext_filter() + ",format=yuv420p"]
        else:
            cmd += ["-pix_fmt", "yuv420p"]

        cmd += self._video_encoder
        # Override GOP to align keyframes with segment boundaries — last -g wins
        cmd += ["-g", str(self.fps * self.segment_seconds)]

        if with_audio:
            cmd += ["-c:a", "aac", "-b:a", "128k"]

        cmd += [
            "-f", "segment",
            "-segment_time", str(self.segment_seconds),
            "-segment_wrap", str(self.buffer_segments),
            "-segment_format", "mpegts",
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
        # Clear stale segments before every spawn. Without this, segments from
        # a previous ffmpeg run remain on disk with old mtimes and corrupt the
        # cross-camera sync offset calculation after a crash+restart.
        self._cleanup_buffer()
        self._ffmpeg_started_at = time.time()

        if not os.path.exists(self.device):
            log.warning("video_device_missing_at_start", device=self.device)
            return

        # Release devices before spawning — ensures any zombie holding them is gone.
        subprocess.run(["fuser", "-k", self.device], stderr=subprocess.DEVNULL)
        if self.pip_device and os.path.exists(self.pip_device):
            subprocess.run(["fuser", "-k", self.pip_device], stderr=subprocess.DEVNULL)
        time.sleep(0.5)

        log.info(
            "video_ring_buffer_ffmpeg_starting",
            device=self.device,
            audio_device=self.audio_device,
        )

        try:
            _nice = lambda: os.nice(5)  # noqa: E731 — yield to Python engine

            if self.audio_device:
                # Try with audio
                cmd = self._build_ffmpeg_cmd(with_audio=True)
                self._process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    preexec_fn=_nice,
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
                        preexec_fn=_nice,
                    )
            else:
                # No audio device configured — start video-only immediately
                cmd = self._build_ffmpeg_cmd(with_audio=False)
                self._process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    preexec_fn=_nice,
                )

        except FileNotFoundError:
            log.error("ffmpeg_not_found", hint="Install with: sudo apt install ffmpeg")
            self._running = False
        except Exception as e:
            log.error("video_ring_buffer_ffmpeg_start_failed", error=str(e))
            self._running = False

    def _read_stderr(self) -> str:
        """Read available stderr from the current process without blocking."""
        if self._process and self._process.stderr:
            try:
                fd = self._process.stderr.fileno()
                flags = os.get_blocking(fd)
                os.set_blocking(fd, False)
                try:
                    data = b""
                    while True:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            break
                        data += chunk
                finally:
                    os.set_blocking(fd, flags)
                return data.decode(errors="replace")[-500:]
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

    def _is_stalled(self) -> bool:
        """Return True if ffmpeg is alive but has stopped writing segments.

        Checks whether the newest segment file has been updated within
        2 × segment_seconds. A stalled ffmpeg holds the device open but
        produces no new footage, so it must be killed and restarted.
        """
        segments = self._get_buffer_segments()
        if not segments:
            return False  # buffer empty — may still be starting up
        newest_mtime = segments[-1].stat().st_mtime
        age = time.time() - newest_mtime
        return age > 2 * self.segment_seconds

    def _health_monitor(self) -> None:
        """Background thread that restarts ffmpeg on crash or stall.

        Also retries with audio periodically if running in video-only mode,
        since the USB audio device may not be available at boot.
        """
        last_audio_retry = time.time()

        while self._running:
            time.sleep(self.RESTART_BACKOFF_SECONDS)
            if not self._running:
                break

            # Drain ffmpeg's stderr pipe every cycle to prevent the 64KB pipe
            # buffer from filling up. A full pipe causes ffmpeg to block on its
            # next stats write, stalling the entire process (~150s at 1Hz output).
            if self._process is not None and self._process.poll() is None:
                self._read_stderr()

            # Restart if ffmpeg crashed
            if self._process is not None and self._process.poll() is not None:
                rc = self._process.returncode
                stderr = self._read_stderr()
                log.warning(
                    "video_ring_buffer_ffmpeg_crashed",
                    returncode=rc,
                    stderr=stderr,
                )
                # If the device node is missing, back off instead of tight-looping
                if not os.path.exists(self.device):
                    log.warning(
                        "video_device_missing",
                        device=self.device,
                        backoff_seconds=self.DEVICE_MISSING_BACKOFF_SECONDS,
                    )
                    backoff_end = time.time() + self.DEVICE_MISSING_BACKOFF_SECONDS
                    while time.time() < backoff_end and self._running:
                        time.sleep(1.0)
                    continue
                self._start_ffmpeg()
                last_audio_retry = time.time()
                continue

            # Restart if ffmpeg is alive but has stopped writing segments
            if self._process is not None and self._process.poll() is None:
                if self._is_stalled():
                    stderr = self._read_stderr()
                    log.warning(
                        "video_ring_buffer_ffmpeg_stalled",
                        device=self.device,
                        stale_after_seconds=2 * self.segment_seconds,
                        stderr=stderr,
                    )
                    # Kill before replacing _process reference to avoid zombies
                    self._kill_current()
                    self._start_ffmpeg()
                    last_audio_retry = time.time()
                    continue

            # If running without audio, periodically restart to retry
            # (only when an audio device is configured but wasn't available at last start)
            if self.audio_device and not self._audio_available:
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
        """Return a completed segment suitable for timelapse frame extraction.

        Skips the two newest segments: the newest is currently being written,
        and the second-newest may be mid-transition as ffmpeg opens a new file.
        The third-newest is ~20s old and guaranteed stable.
        """
        segments = self._get_buffer_segments()
        if len(segments) < 3:
            return None
        return segments[-3]

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
            now = time.time()
            buffer_segments = self._get_buffer_segments()
            ages = [round(now - s.stat().st_mtime, 1) for s in buffer_segments]
            started = self._ffmpeg_started_at
            ffmpeg_uptime = round(now - started, 1) if started else 0.0
            log.info(
                "video_save_buffer_state",
                save_id=save_id,
                segment_count=len(buffer_segments),
                segment_ages_seconds=ages,
                ffmpeg_uptime_seconds=ffmpeg_uptime,
                buffer_capacity_seconds=self.buffer_segments * self.segment_seconds,
            )
            pre_cutoff = now
            pre_segments = self._copy_complete_segments(tmp_dir, "pre")
            # mtime of oldest segment = GPS-clock time when that segment closed;
            # used by the PiP compositor to align two independently-rolling buffers.
            clip_start_mtime = pre_segments[0].stat().st_mtime if pre_segments else pre_cutoff
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
                    callback(None, 0.0)
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
                callback(output_path, clip_start_mtime)

        except Exception as e:
            log.error("video_save_error", save_id=save_id, error=str(e))
            if callback:
                callback(None, 0.0)
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
        # Re-create dest_dir in case _cleanup_buffer() deleted it during a
        # stall-triggered restart while this save was sleeping between pre/post.
        dest_dir.mkdir(parents=True, exist_ok=True)

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

        Uses the ffmpeg concat demuxer (not byte-concatenation) so that PTS is
        adjusted at each file boundary. Byte-joining TS files with different PTS
        origins (intro vs live segments, or segments from different ffmpeg runs)
        causes timestamp discontinuities that players show as freezes/stutters.
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

        # Build file list for the concat demuxer
        files: list[Path] = []
        if self._intro_ts and self._intro_ts.exists():
            files.append(self._intro_ts)
        files.extend(segments)

        total_input_bytes = sum(f.stat().st_size for f in files if f.exists())
        if total_input_bytes == 0:
            log.warning("concat_no_data", segment_count=len(segments))
            return None

        # concat.txt lives in the save_N/ tmp dir and is cleaned up with it
        concat_list = segments[0].parent / "concat.txt"
        try:
            with open(concat_list, "w") as f:
                for p in files:
                    f.write(f"file '{p}'\n")
        except Exception as e:
            log.error("concat_list_write_error", error=str(e))
            return None

        log.info(
            "concat_segments",
            segment_count=len(segments),
            total_mb=round(total_input_bytes / (1024 * 1024), 2),
        )

        # Remux via concat demuxer → MP4 into buffer dir first, then move to
        # captures so rsync never sees a partial file in the output directory.
        # Large probesize ensures ffmpeg finds SPS/PPS NAL units even if the
        # h264_v4l2m2m encoder didn't emit them until a few seconds after startup.
        tmp_mp4 = segments[0].parent / f".tmp_{output_path.name}"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-analyzeduration", "20000000",
            "-probesize", "20000000",
            "-i", str(concat_list),
            "-c", "copy",
            "-r", str(self.fps),
            "-video_track_timescale", str(self.fps * 1000),
            "-movflags", "+faststart",
            str(tmp_mp4),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            concat_list.unlink(missing_ok=True)

            if result.returncode == 0 and tmp_mp4.exists():
                size = tmp_mp4.stat().st_size
                if size > 0:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_mp4.rename(output_path)
                    return output_path
                # ffmpeg succeeded but produced empty file
                input_mb = round(total_input_bytes / (1024 * 1024), 2)
                log.error("concat_empty_output", input_mb=input_mb)
                tmp_mp4.unlink(missing_ok=True)
                return None
            else:
                stderr = result.stderr.decode()[-500:] if result.stderr else ""
                log.error("concat_failed", returncode=result.returncode, stderr=stderr)
                tmp_mp4.unlink(missing_ok=True)
                return None
        except subprocess.TimeoutExpired:
            log.error("concat_timeout")
            concat_list.unlink(missing_ok=True)
            tmp_mp4.unlink(missing_ok=True)
            return None
        except Exception as e:
            log.error("concat_error", error=str(e))
            concat_list.unlink(missing_ok=True)
            tmp_mp4.unlink(missing_ok=True)
            return None

    def _cleanup_buffer(self) -> None:
        """Remove segment files and temporary save dirs from the buffer directory.

        Preserves intro.ts so it doesn't need to be re-converted on every restart.
        """
        if not self.buffer_dir.exists():
            return
        for f in self.buffer_dir.glob("seg_*.ts"):
            f.unlink(missing_ok=True)
        combined = self.buffer_dir / "combined.ts"
        combined.unlink(missing_ok=True)
        for d in self.buffer_dir.glob("save_*"):
            shutil.rmtree(str(d), ignore_errors=True)
