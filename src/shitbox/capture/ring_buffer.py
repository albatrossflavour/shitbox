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
from typing import TYPE_CHECKING, Any, Callable, Optional

from shitbox.capture import buzzer
from shitbox.capture.speaker import (
    speak_capture_failed,
    speak_ffmpeg_stall,
    speak_service_recovered,
)
from shitbox.hardware import state as hw_state
from shitbox.utils.logging import get_logger

# Graceful-degradation import per Phase 21 D-04 ("never refuse boot").
# The ring buffer must keep running and beeping on a stall even if the
# health/alerts module is absent for any reason.
try:
    from shitbox.health import alerts
except ImportError:  # pragma: no cover — defensive fallback
    class _NoopAlerts:
        @staticmethod
        def fire_alert(*_a: Any, **_k: Any) -> None:
            pass

        @staticmethod
        def fire_recovery(*_a: Any, **_k: Any) -> None:
            pass

    alerts = _NoopAlerts()  # type: ignore[assignment]

if TYPE_CHECKING:
    from shitbox.capture.title_card import TitleCardRenderer
    from shitbox.events.detector import Event

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
    STALL_TIMEOUT_SECONDS = 30.0  # Declare stall if newest segment unchanged for this long

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
        role: str = "camera_front",
        audio_hw_role: str = "",
    ):
        self.buffer_dir = Path(buffer_dir)
        self.role = role
        self.audio_hw_role = audio_hw_role
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
        self._active_saves = 0
        self._lock = threading.Lock()
        self._intro_ts: Optional[Path] = None
        self._intro_duration_seconds: float = 0.0
        self._last_timelapse_segment: Optional[Path] = None
        self._ffmpeg_started_at: float = 0.0

        # Stall detection state (used by _check_stall / _reset_stall_state).
        # Wall-clock fields (mtime, size) compare against filesystem state.
        # The age timer uses time.monotonic() so a GPS clock-step does not
        # trigger a false-positive stall (REVIEW WR-03).
        self._stall_check_armed: bool = False
        self._last_segment_mtime: float = 0.0
        self._last_segment_size: int = 0
        self._last_segment_seen_monotonic: float = 0.0

        # Phase 15 MON-03: consecutive ffmpeg restart counter. Reset only on
        # recovery (a clean segment observed after a prior failure), not on
        # every restart. Escalates to CAPTURE_DOWN at >= 3.
        self._consecutive_restart_count: int = 0

        # Phase 26: title-card slate. All three set by the engine (plan 26-04
        # Task 3); left as default sentinels so the ring buffer runs unchanged
        # when title cards are disabled or the engine has not wired them up.
        self._title_card_renderer: Optional["TitleCardRenderer"] = None
        self._geocoder_fn: Optional[Callable[[float, float], Optional[str]]] = None
        self._active_driver_fn: Optional[Callable[[], Optional[str]]] = None
        # Per-save slate state. Reset at the top of each save pass and again
        # by the engine after the poster move.
        self._pending_slate_ts: Optional[Path] = None
        self._pending_slate_png: Optional[Path] = None
        self._pending_slate_duration: float = 0.0

        # Phase 26 gap-closure (plan 26-05): stable holding dir for slate PNGs.
        # The per-save tmp_dir is rmtree'd in _do_save_event's finally; the PNG
        # is relocated here BEFORE that runs so the engine can consume it later.
        self._pending_slates_dir: Path = self.buffer_dir / "pending_slates"
        self._process_start_time: float = 0.0  # set in start() for the sweep

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
    def is_monitoring(self) -> bool:
        """True if the internal health-monitor thread is alive.

        When this is True the ring buffer can self-recover from an ffmpeg
        crash — the engine-level health check should leave it alone.
        Stepping in concurrently was the source of the recurring
        ``'NoneType' object has no attribute 'poll'`` race in
        ``_start_ffmpeg``.
        """
        return self._health_thread is not None and self._health_thread.is_alive()

    @property
    def is_saving(self) -> bool:
        """True while any save-event thread is active (copying segments or concatenating)."""
        with self._lock:
            return self._active_saves > 0

    def start(self) -> None:
        """Start the continuous segment recording and health monitor."""
        if self._running:
            return

        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self._pending_slates_dir.mkdir(parents=True, exist_ok=True)
        self._process_start_time = time.time()
        self._cleanup_pending_slates()
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
        pre_seconds: Optional[int] = None,
        callback: Optional[Callable[[Optional[Path], float, Optional[Path]], None]] = None,
        event: Optional["Event"] = None,
    ) -> None:
        """Save pre-event buffer + post-event recording to a single MP4.

        Runs in a background thread so it doesn't block the caller.

        Args:
            prefix: Filename prefix for the saved video.
            post_seconds: Seconds of post-event footage to capture.
                          Defaults to self.post_event_seconds.
            pre_seconds: Seconds of pre-event footage to keep.
                         None means keep entire buffer.
            callback: Called with (output Path or None, clip_start_mtime,
                poster PNG Path or None). The poster path is the stable
                holding-dir location the save worker has moved the rendered
                slate PNG to before the per-save tmp dir is rmtree'd. None when
                no slate was rendered or the move to holding failed.
                clip_start_mtime is the filesystem mtime of the oldest
                pre-event segment — a GPS-clock wall-clock timestamp usable
                for cross-camera sync alignment.
            event: Optional source Event (phase 26). When provided and a
                   title-card renderer is wired, a slate is rendered into the
                   save tmp dir and inserted between intro.ts and the live
                   segments on concat. Required for a slate to appear; omitted
                   callers get the legacy intro→buffer sequence.
        """
        if post_seconds is None:
            post_seconds = self.post_event_seconds

        thread = threading.Thread(
            target=self._do_save_event,
            args=(prefix, post_seconds, pre_seconds, callback, event),
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

        # -skip_frame nokey forces the decoder to drop P/B frames and emit
        # only keyframes. With H264 passthrough the camera controls GOP, so
        # segment boundaries don't align to I-frames — decoding from packet 0
        # produces garbage until the next keyframe arrives.
        cmd = ["ffmpeg", "-y", "-skip_frame", "nokey", "-i", str(segment)]

        # H264 passthrough keeps segments raw, so the HUD is applied here
        # (live /dev/shm values — current at the moment of extraction).
        # MJPG segments already have the HUD baked in.
        if self.input_format == "h264" and self.overlay_path:
            from shitbox.capture.overlay import LOGO_PATH, build_filter_complex

            if Path(LOGO_PATH).exists():
                cmd += ["-i", LOGO_PATH]
                cmd += ["-filter_complex", build_filter_complex(logo_input_idx=1)]
                cmd += ["-map", "[out]"]
            else:
                from shitbox.capture.overlay import build_drawtext_filter
                cmd += ["-vf", build_drawtext_filter() + ",format=yuv420p"]

        cmd += ["-frames:v", "1", "-q:v", "5", str(output_path)]

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

    @staticmethod
    def _probe_duration(path: Path) -> float:
        """Return the duration of a media file in seconds, or 0.0 on failure."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.decode().strip())
        except (subprocess.TimeoutExpired, ValueError, OSError) as e:
            log.warning("probe_duration_failed", path=str(path), error=str(e))
        return 0.0

    @staticmethod
    def _probe_start_pts(path: Path) -> float:
        """Return the PTS of the first video packet in seconds, or 0.0 on failure.

        Uses packet-level pts_time rather than stream start_time because
        MPEG-TS segment files often report start_time=0 in the stream header
        even when actual packet PTS values are much larger (e.g. after
        segment_wrap cycling).
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "packet=pts_time",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    "-read_intervals", "%+#1",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if result.returncode == 0:
                raw = result.stdout.decode().strip()
                if raw and raw != "N/A":
                    return float(raw)
        except (subprocess.TimeoutExpired, ValueError, OSError) as e:
            log.warning("probe_start_pts_failed", path=str(path), error=str(e))
        return 0.0

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
                self._intro_duration_seconds = self._probe_duration(self._intro_ts)
                log.info(
                    "intro_video_cached",
                    size_mb=size_mb,
                    duration_s=round(self._intro_duration_seconds, 2),
                )
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
                self._intro_duration_seconds = self._probe_duration(self._intro_ts)
                log.info(
                    "intro_video_prepared",
                    size_mb=size_mb,
                    duration_s=round(self._intro_duration_seconds, 2),
                )
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
        """Build the ffmpeg segment muxer command.

        For cameras delivering native H264, the stream is copied verbatim
        (-c:v copy) — no filters, no re-encode. HUD and logo are burned in
        later: at save-time for event clips, at capture-time for timelapse
        frames. For MJPG (and any non-H264 source), the primary stream is
        re-encoded in real time with drawtext/logo and optional PiP.
        """
        segment_pattern = str(self.buffer_dir / "seg_%03d.ts")

        if self.input_format == "h264":
            has_cabin = bool(self.pip_device) and os.path.exists(self.pip_device)
            if self.pip_device and not has_cabin:
                log.warning(
                    "pip_camera_absent_single_camera_mode",
                    device=self.pip_device,
                )

            cmd = [
                "ffmpeg", "-y",
                "-thread_queue_size", "512",
                "-rtbufsize", "200M",
                "-f", "v4l2",
                "-input_format", "h264",
                "-video_size", self.resolution,
                "-framerate", str(self.fps),
                "-i", self.device,
            ]
            if has_cabin:
                # Cabin camera (Brio 100) — MJPG only, re-encoded below.
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

            # Output A: front camera (H264 passthrough, video-only).
            cmd += [
                "-map", "0:v", "-c:v", "copy",
                "-f", "segment",
                "-segment_time", str(self.segment_seconds),
                "-segment_wrap", str(self.buffer_segments),
                "-segment_format", "mpegts",
                segment_pattern,
            ]

            # Output B: cabin camera (libx264 ultrafast) + Brio mic audio.
            # Audio lives here — cabin mic belongs with the cabin stream, and
            # the front segments stay pure H264 passthrough with no intro-audio
            # mismatch at save time.
            if has_cabin:
                cabin_pattern = str(self.buffer_dir / "cabin_%03d.ts")
                cabin_gop = max(1, self.pip_fps * self.segment_seconds)
                cmd += [
                    "-map", "1:v",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-g", str(cabin_gop),
                    "-pix_fmt", "yuv420p",
                ]
                if with_audio:
                    audio_idx = 2 if has_cabin else 1
                    cmd += ["-map", f"{audio_idx}:a", "-c:a", "aac", "-b:a", "128k"]
                cmd += [
                    "-f", "segment",
                    "-segment_time", str(self.segment_seconds),
                    "-segment_wrap", str(self.buffer_segments),
                    "-segment_format", "mpegts",
                    cabin_pattern,
                ]
            return cmd

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

        if self.pip_device and not os.path.exists(self.pip_device):
            log.warning("pip_camera_absent_single_camera_mode", device=self.pip_device)
        if self.pip_device and os.path.exists(self.pip_device):
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

        if self.pip_device and os.path.exists(self.pip_device):
            # Real-time PiP composite — [0:v] primary, [1:v] cabin
            # Input indices: 0=front, 1=cabin, then optionally audio,
            # then optionally logo PNG.
            from shitbox.capture.overlay import LOGO_PATH

            x, y = _PIP_POSITION_MAP.get(
                self.pip_position, ("W-w-10", "H-h-10"),
            )
            audio_idx = 2  # always after primary + pip
            logo_exists = self.overlay_path and Path(LOGO_PATH).exists()
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
                f"[1:v]eq=brightness=0.06:saturation=1.2,"
                f"scale=iw*{self.pip_scale}:-2,"
                "pad=iw+6:ih+28:3:24:color=black@0.7,"
                "drawtext=text='Cabin':"
                "fontsize=22:fontcolor=white@0.9:x=8:y=4[pip]"
            )
            parts = [p for p in [logo_prep, pip_chain, composite] if p]
            filter_complex = ";".join(parts)

            cmd += ["-filter_complex", filter_complex, "-map", "[out]"]
            if with_audio:
                cmd += ["-map", f"{audio_idx}:a"]
        elif self.overlay_path:
            # Single-camera drawtext overlay
            from shitbox.capture.overlay import (
                LOGO_PATH,
                build_drawtext_filter,
                build_filter_complex,
            )

            logo_exists = Path(LOGO_PATH).exists()
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
        # ``include_saves=False`` because a save worker may be actively
        # populating a save_N/ directory between pre- and post-event copies;
        # nuking it here was breaking concats with the cabin_pre_*.ts
        # ``Impossible to open`` cascade. Stale save dirs from crashed prior
        # runs are cleaned at full process start() instead.
        self._cleanup_buffer(include_saves=False)
        self._ffmpeg_started_at = time.time()

        if not os.path.exists(self.device):
            log.warning("video_device_missing_at_start", device=self.device)
            return

        # Release devices before spawning — ensures any zombie holding them is gone.
        subprocess.run(["fuser", "-k", self.device], stderr=subprocess.DEVNULL)
        if self.pip_device and os.path.exists(self.pip_device):
            subprocess.run(["fuser", "-k", self.pip_device], stderr=subprocess.DEVNULL)
        time.sleep(0.5)

        if self.input_format == "h264":
            cabin_present = bool(self.pip_device) and os.path.exists(self.pip_device)
            mode = "h264_dual" if cabin_present else "h264_single"
        elif self.pip_device and os.path.exists(self.pip_device):
            mode = "mjpg_inline_pip"
        else:
            mode = "mjpg_single"

        log.info(
            "video_ring_buffer_ffmpeg_starting",
            device=self.device,
            audio_device=self.audio_device,
            mode=mode,
            pip_device=self.pip_device or None,
            pip_device_exists=bool(self.pip_device) and os.path.exists(self.pip_device),
        )

        try:
            _nice = lambda: os.nice(5)  # noqa: E731 — yield to Python engine

            if self.audio_device:
                # Try with audio
                cmd = self._build_ffmpeg_cmd(with_audio=True)
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    preexec_fn=_nice,
                )
                self._process = proc
                self._audio_available = True

                # Check for early crash (audio device not ready). Use a
                # LOCAL reference (`proc`) for the poll — `self._process`
                # may be nulled by another thread (notably ``stop()``)
                # during the 3 s sleep, which used to crash here with
                # ``'NoneType' object has no attribute 'poll'``. Bail out
                # quietly if we've been stopped or replaced.
                time.sleep(3.0)
                if not self._running or self._process is not proc:
                    return
                if proc.poll() is not None:
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

            hw_state.report_present(self.role)

        except FileNotFoundError:
            log.error("ffmpeg_not_found", hint="Install with: sudo apt install ffmpeg")
            self._running = False
        except Exception as e:
            log.error("video_ring_buffer_ffmpeg_start_failed", error=str(e))
            self._running = False

    def _read_stderr(self) -> str:
        """Read available stderr from the current process without blocking.

        On a non-blocking pipe ``os.read`` raises ``BlockingIOError`` once
        the buffer is empty rather than returning ``b""``. The earlier
        version of this method swallowed the error inside the bare
        ``except Exception: pass`` and lost any bytes already drained.
        Catch BlockingIOError as the loop-exit signal and return what
        we already have. Same fix shape as
        ``shitbox.sync.tpms._read_stderr_nonblocking``.
        """
        if self._process and self._process.stderr:
            data = b""
            try:
                fd = self._process.stderr.fileno()
                flags = os.get_blocking(fd)
                os.set_blocking(fd, False)
                try:
                    while True:
                        try:
                            chunk = os.read(fd, 4096)
                        except BlockingIOError:
                            break
                        if not chunk:
                            break
                        data += chunk
                finally:
                    os.set_blocking(fd, flags)
                return data.decode(errors="replace")[-500:]
            except Exception:
                return data.decode(errors="replace")[-500:] if data else ""
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

    def _check_stall(self) -> bool:
        """Stateful stall detector: arms on first segment, returns True after timeout.

        On the first call that observes a segment, arms the detector and records
        the segment's mtime and size. On subsequent calls:
          - If mtime or size changed: reset baseline, return False (active).
          - If neither changed and STALL_TIMEOUT_SECONDS elapsed: return True (stalled).
          - Otherwise: return False (still within timeout window).

        Returns:
            True if a stall is confirmed; False otherwise.
        """
        segments = self._get_buffer_segments()
        if not segments:
            return False  # buffer empty — starting up or no input

        newest = segments[-1]
        try:
            stat = newest.stat()
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            return False

        if not self._stall_check_armed:
            # First observation — arm the detector
            self._stall_check_armed = True
            self._last_segment_mtime = mtime
            self._last_segment_size = size
            self._last_segment_seen_monotonic = time.monotonic()
            return False

        if mtime != self._last_segment_mtime or size != self._last_segment_size:
            # Segment is growing or a new one appeared — reset baseline
            self._last_segment_mtime = mtime
            self._last_segment_size = size
            self._last_segment_seen_monotonic = time.monotonic()
            return False

        # Segment is frozen — measure age against monotonic clock so a GPS
        # wall-clock step does not register as a stall.
        age = time.monotonic() - self._last_segment_seen_monotonic
        return age > self.STALL_TIMEOUT_SECONDS

    def _reset_stall_state(self) -> None:
        """Reset all stall detection fields to their initial state.

        Called after ffmpeg is restarted to avoid triggering a false stall
        on the next health monitor cycle.
        """
        self._stall_check_armed = False
        self._last_segment_mtime = 0.0
        self._last_segment_size = 0
        self._last_segment_seen_monotonic = 0.0

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

            try:
                # Drain ffmpeg's stderr pipe every cycle to prevent the 64KB pipe
                # buffer from filling up. A full pipe causes ffmpeg to block on its
                # next stats write, stalling the entire process (~150s at 1Hz output).
                if self._process is not None and self._process.poll() is None:
                    self._read_stderr()

                # Phase 15 MON-03: recovery check. If a prior iteration
                # incremented the restart counter and the stall detector is
                # now armed (segments flowing again), announce recovery and
                # reset the counter. _check_stall is called at most once per
                # cycle so timers do not double-advance.
                stall_now: Optional[bool] = None
                if (
                    self._consecutive_restart_count > 0
                    and self._stall_check_armed
                    and self._process is not None
                    and self._process.poll() is None
                ):
                    stall_now = self._check_stall()
                    if not stall_now:
                        alerts.fire_recovery(
                            "CAPTURE_FAILURE",
                            active=False,
                            message="RECORDING RESUMED",
                            tts_fn=speak_service_recovered,
                            sustain_required=1,
                            recovery_subtype="CAPTURE_RESTORED",
                        )
                        # Clear CAPTURE_DOWN too so a second escalation can
                        # re-fire on a later episode (REVIEW WR-02). No TTS:
                        # CAPTURE_RESTORED above already announced recovery.
                        alerts.fire_recovery(
                            "CAPTURE_DOWN",
                            active=False,
                            message="RECORDING RESUMED",
                            sustain_required=1,
                        )
                        self._consecutive_restart_count = 0

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
                        hw_state.report_missing(self.role)
                        backoff_end = time.time() + self.DEVICE_MISSING_BACKOFF_SECONDS
                        while time.time() < backoff_end and self._running:
                            time.sleep(1.0)
                        continue
                    self._start_ffmpeg()
                    self._consecutive_restart_count += 1
                    if self._consecutive_restart_count >= 3:
                        alerts.fire_alert(
                            "CAPTURE_DOWN",
                            active=True,
                            message="CAPTURE DOWN",
                            tts_fn=speak_capture_failed,
                            sustain_required=1,
                        )
                    last_audio_retry = time.time()
                    continue

                # Restart if ffmpeg is alive but has stopped writing segments.
                # Reuse the cached stall_now value if the recovery branch
                # already called _check_stall this cycle; otherwise evaluate now.
                if self._process is not None and self._process.poll() is None:
                    if stall_now is None:
                        stall_now = self._check_stall()
                    if stall_now:
                        stderr = self._read_stderr()
                        log.warning(
                            "video_ring_buffer_ffmpeg_stalled",
                            device=self.device,
                            stall_timeout_seconds=self.STALL_TIMEOUT_SECONDS,
                            stderr=stderr,
                        )
                        hw_state.report_degraded(self.role)
                        buzzer.beep_ffmpeg_stall()
                        alerts.fire_alert(
                            "CAPTURE_FAILURE",
                            active=True,
                            message="CAPTURE STALLED",
                            tts_fn=speak_ffmpeg_stall,
                            sustain_required=1,
                        )
                        # Kill before replacing _process reference to avoid zombies
                        self._kill_current()
                        self._reset_stall_state()
                        self._start_ffmpeg()
                        self._consecutive_restart_count += 1
                        if self._consecutive_restart_count >= 3:
                            alerts.fire_alert(
                                "CAPTURE_DOWN",
                                active=True,
                                message="CAPTURE DOWN",
                                tts_fn=speak_capture_failed,
                                sustain_required=1,
                            )
                        last_audio_retry = time.time()
                        continue

                # If running without audio, periodically restart to retry —
                # but only when the hardware supervisor hasn't confirmed the
                # device absent. If audio_hw_role is set and hw_state shows
                # MISSING after at least one probe (last_seen > 0), the device
                # genuinely isn't fitted and we stop retrying.
                if self.audio_device and not self._audio_available:
                    if self.audio_hw_role:
                        status = hw_state.get_state(self.audio_hw_role)
                        if status is not None and status.last_seen == 0.0 and status.consecutive_misses > 0:
                            # Supervisor has probed at least once and never seen it.
                            pass  # skip retry — device not present
                        else:
                            now = time.time()
                            if (now - last_audio_retry) >= self.AUDIO_RETRY_SECONDS:
                                log.info("video_ring_buffer_retrying_audio")
                                self._audio_available = True
                                self._kill_current()
                                self._start_ffmpeg()
                                last_audio_retry = time.time()
                    else:
                        now = time.time()
                        if (now - last_audio_retry) >= self.AUDIO_RETRY_SECONDS:
                            log.info("video_ring_buffer_retrying_audio")
                            self._audio_available = True
                            self._kill_current()
                            self._start_ffmpeg()
                            last_audio_retry = time.time()

            except Exception as e:
                log.error("health_monitor_cycle_error", error=str(e))

    def _get_buffer_segments(self) -> list[Path]:
        """Return primary (front) buffer segment files sorted by mtime."""
        if not self.buffer_dir.exists():
            return []
        segments = sorted(
            self.buffer_dir.glob("seg_*.ts"),
            key=lambda p: p.stat().st_mtime,
        )
        return segments

    def _get_buffer_segments_cabin(self) -> list[Path]:
        """Return cabin buffer segment files sorted by mtime.

        Populated only when dual-output ffmpeg is running (H264 front +
        re-encoded cabin). Empty when the cabin camera is absent or when
        the MJPG single-camera composite path is active.
        """
        if not self.buffer_dir.exists():
            return []
        return sorted(
            self.buffer_dir.glob("cabin_*.ts"),
            key=lambda p: p.stat().st_mtime,
        )

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
        pre_seconds: Optional[int],
        callback: Optional[Callable[[Optional[Path], float, Optional[Path]], None]],
        event: Optional["Event"] = None,
    ) -> None:
        """Worker that copies buffer segments, waits for post-event, then concatenates."""
        with self._lock:
            self._save_counter += 1
            save_id = self._save_counter
            self._active_saves += 1

        tmp_dir = self.buffer_dir / f"save_{save_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Phase 26: reset per-save slate state at the top of every pass so a
        # previous event's leftovers (or a failed render) never leak across.
        self._pending_slate_ts = None
        self._pending_slate_png = None
        self._pending_slate_duration = 0.0

        # Phase 26 gap-closure (plan 26-05): stable_png_path holds the
        # holding-dir location of the slate PNG after it has been relocated
        # from tmp_dir. Initialised to None; set after the relocation move.
        stable_png_path: Optional[Path] = None

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
            # Filter to segments within pre_seconds of now if specified
            pre_min_mtime = (now - pre_seconds) if pre_seconds else None
            pre_segments = self._copy_complete_segments(
                tmp_dir, "pre", min_mtime=pre_min_mtime,
            )
            cabin_pre_segments = self._copy_complete_segments(
                tmp_dir, "pre", min_mtime=pre_min_mtime, stream="cabin",
            )
            # mtime of oldest segment = GPS-clock time when that segment closed;
            # used by downstream sync tooling to align independently-rolling buffers.
            clip_start_mtime = pre_segments[0].stat().st_mtime if pre_segments else pre_cutoff
            pre_bytes = sum(s.stat().st_size for s in pre_segments)
            cabin_pre_bytes = sum(s.stat().st_size for s in cabin_pre_segments)
            log.info(
                "video_save_pre_segments_copied",
                save_id=save_id,
                count=len(pre_segments),
                size_mb=round(pre_bytes / (1024 * 1024), 2),
                cabin_count=len(cabin_pre_segments),
                cabin_size_mb=round(cabin_pre_bytes / (1024 * 1024), 2),
            )

            # 2. Wait for post-event footage
            time.sleep(post_seconds)

            # 3. Copy segments written AFTER the pre-copy (avoids duplicates)
            post_segments = self._copy_complete_segments(
                tmp_dir, "post", min_mtime=pre_cutoff,
            )
            cabin_post_segments = self._copy_complete_segments(
                tmp_dir, "post", min_mtime=pre_cutoff, stream="cabin",
            )
            post_bytes = sum(s.stat().st_size for s in post_segments)
            cabin_post_bytes = sum(s.stat().st_size for s in cabin_post_segments)
            log.info(
                "video_save_post_segments_copied",
                save_id=save_id,
                count=len(post_segments),
                size_mb=round(post_bytes / (1024 * 1024), 2),
                cabin_count=len(cabin_post_segments),
                cabin_size_mb=round(cabin_post_bytes / (1024 * 1024), 2),
            )

            if not post_segments:
                log.warning(
                    "video_save_post_event_empty",
                    save_id=save_id,
                    hint="ffmpeg may have been restarting during post-event window",
                )

            all_segments = pre_segments + post_segments
            cabin_segments = cabin_pre_segments + cabin_post_segments
            if not all_segments:
                log.warning("video_save_no_segments", save_id=save_id)
                if callback:
                    callback(None, 0.0, None)
                return

            # Phase 26: render the title-card slate into the save tmp dir so
            # it can be inserted between intro and live footage by the
            # concat builder. Silent no-op when the renderer is absent or
            # the event arg wasn't passed by the engine.
            if event is not None and self._title_card_renderer is not None:
                slate_tmp_dir = all_segments[0].parent
                driver = self._active_driver_fn() if self._active_driver_fn else None
                png_path, ts_path, dur = self._render_slate(
                    event,
                    slate_tmp_dir,
                    geocoder=self._geocoder_fn,
                    driver_name=driver,
                )
                self._pending_slate_png = png_path
                self._pending_slate_ts = ts_path
                self._pending_slate_duration = dur

            # 4. Concatenate into a single MP4 (PiP composited if cabin present)
            output_path = self._concatenate_segments(
                all_segments, prefix, cabin_segments=cabin_segments,
            )
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

            # Phase 26 gap-closure: relocate the slate PNG out of tmp_dir to the
            # stable holding dir BEFORE the finally runs rmtree. stable_png_path
            # (passed to the callback below) survives the rmtree; the caller owns
            # the final rename into the per-day dir.
            if self._pending_slate_png is not None:
                src = self._pending_slate_png
                if src.exists():
                    dst = self._pending_slates_dir / f"{save_id}.png"
                    try:
                        self._pending_slates_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src), str(dst))
                        stable_png_path = dst
                        log.info(
                            "slate_png_relocated",
                            save_id=save_id,
                            src=str(src),
                            dst=str(dst),
                        )
                    except OSError as move_err:
                        log.warning(
                            "slate_move_to_holding_failed",
                            save_id=save_id,
                            src=str(src),
                            dst=str(dst),
                            error=str(move_err),
                        )
                        stable_png_path = None

            if callback:
                callback(output_path, clip_start_mtime, stable_png_path)

        except Exception as e:
            log.error("video_save_error", save_id=save_id, error=str(e))
            if callback:
                callback(None, 0.0, None)
        finally:
            with self._lock:
                self._active_saves -= 1
            # 5. Clean up temp copies
            shutil.rmtree(tmp_dir, ignore_errors=True)

    MIN_SEGMENT_BYTES = 10_000  # skip incomplete/corrupt segments

    def _copy_complete_segments(
        self,
        dest_dir: Path,
        phase: str,
        min_mtime: Optional[float] = None,
        stream: str = "front",
    ) -> list[Path]:
        """Copy completed buffer segments to dest_dir.

        Skips the newest segment (currently being written to by ffmpeg),
        segments smaller than MIN_SEGMENT_BYTES, and optionally segments
        older than min_mtime (to avoid duplicating pre-event footage in
        the post-event copy).

        ``stream="cabin"`` reads the cabin_*.ts output (dual-output mode)
        and prefixes copied filenames with ``cabin_`` to keep them distinct
        from the front segments sharing the tmp dir.
        """
        # Re-create dest_dir in case _cleanup_buffer() deleted it during a
        # stall-triggered restart while this save was sleeping between pre/post.
        dest_dir.mkdir(parents=True, exist_ok=True)

        if stream == "cabin":
            segments = self._get_buffer_segments_cabin()
            out_prefix = f"cabin_{phase}"
        else:
            segments = self._get_buffer_segments()
            out_prefix = phase

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

            dest = dest_dir / f"{out_prefix}_{idx:03d}.ts"
            try:
                shutil.copy2(str(seg), str(dest))
                copied.append(dest)
                idx += 1
            except Exception as e:
                log.warning("segment_copy_error", src=str(seg), error=str(e))

        return copied

    def _build_concat_reencode_cmd(
        self,
        segments: list[Path],
        concat_list: Path,
        tmp_mp4: Path,
    ) -> tuple[list[str], int]:
        """Build ffmpeg command that burns HUD + logo onto passthrough segments.

        Generates an ASS subtitle file from the telemetry history covering
        the clip's wall-clock window, then re-encodes through libx264
        (ultrafast) with the ASS filter and optional logo overlay. Returns
        (cmd, timeout_seconds).
        """
        from shitbox.capture import overlay as ol

        # mtime == moment a segment finished writing; its start is one
        # segment_seconds earlier. Intro is excluded — it is not live footage.
        seg_mtimes = [s.stat().st_mtime for s in segments if s.exists()]
        if seg_mtimes:
            clip_start_wall = min(seg_mtimes) - self.segment_seconds
            clip_end_wall = max(seg_mtimes)
        else:
            clip_start_wall = time.time()
            clip_end_wall = clip_start_wall

        intro_duration = getattr(self, "_intro_duration_seconds", 0.0) or 0.0
        slate_duration = self._pending_slate_duration
        head_offset_s = intro_duration + slate_duration

        history = ol.get_history(clip_start_wall, clip_end_wall)
        ass_path = concat_list.parent / "overlay.ass"
        ol.generate_ass_overlay(
            entries=history,
            clip_start_wall=clip_start_wall,
            clip_end_wall=clip_end_wall,
            intro_duration=head_offset_s,  # D-15: shift HUD past intro+slate
            output_path=ass_path,
        )
        log.info(
            "concat_overlay_generated",
            entries=len(history),
            intro_s=round(intro_duration, 2),
            slate_s=round(slate_duration, 2),
            head_offset_s=round(head_offset_s, 2),
            clip_s=round(clip_end_wall - clip_start_wall, 2),
        )

        logo_exists = Path(ol.LOGO_PATH).exists()
        if logo_exists:
            filter_complex = (
                f"[1:v]format=rgba,colorchannelmixer=aa=0.4[logo];"
                f"[0:v]ass={ass_path}[text];"
                "[text][logo]overlay=10:10,format=yuv420p[out]"
            )
        else:
            filter_complex = f"[0:v]ass={ass_path},format=yuv420p[out]"

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-analyzeduration", "20000000",
            "-probesize", "20000000",
            "-i", str(concat_list),
        ]
        if logo_exists:
            cmd += ["-i", ol.LOGO_PATH]
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "copy",
            "-r", str(self.fps),
            "-movflags", "+faststart",
            str(tmp_mp4),
        ]
        return ["nice", "-n", "10"] + cmd, 900

    def _build_dual_concat_reencode_cmd(
        self,
        segments: list[Path],
        concat_front: Path,
        concat_cabin: Path,
        tmp_mp4: Path,
        cabin_pts_offset: float = 0.0,
    ) -> tuple[list[str], int]:
        """Build ffmpeg command for dual-stream concat + PiP composite + HUD.

        Input 0 is the front concat (intro + live segments), input 1 is the
        cabin concat (live segments only). Cabin is scaled, framed, labelled,
        and shifted by intro_duration so it rides on top of the live footage
        without bleeding into the intro. ASS overlay and logo follow the same
        pattern as the single-stream path.
        """
        from shitbox.capture import overlay as ol

        seg_mtimes = [s.stat().st_mtime for s in segments if s.exists()]
        if seg_mtimes:
            clip_start_wall = min(seg_mtimes) - self.segment_seconds
            clip_end_wall = max(seg_mtimes)
        else:
            clip_start_wall = time.time()
            clip_end_wall = clip_start_wall

        intro_duration = getattr(self, "_intro_duration_seconds", 0.0) or 0.0
        slate_duration = self._pending_slate_duration
        head_offset_s = intro_duration + slate_duration

        # cabin_pts_offset accounts for the PTS difference between the first
        # selected front segment and the first selected cabin segment. When
        # the pre-event window straddles a segment boundary differently for
        # each stream (e.g. front gets 2 segments, cabin only 1), their
        # PTS origins diverge. Without correction the cabin PiP appears ahead
        # of the front footage by the difference.
        cabin_shift = head_offset_s + cabin_pts_offset

        history = ol.get_history(clip_start_wall, clip_end_wall)
        ass_path = concat_front.parent / "overlay.ass"
        ol.generate_ass_overlay(
            entries=history,
            clip_start_wall=clip_start_wall,
            clip_end_wall=clip_end_wall,
            intro_duration=head_offset_s,  # D-15: shift HUD past intro+slate
            output_path=ass_path,
        )
        log.info(
            "concat_overlay_generated",
            entries=len(history),
            intro_s=round(intro_duration, 2),
            slate_s=round(slate_duration, 2),
            head_offset_s=round(head_offset_s, 2),
            cabin_pts_offset=round(cabin_pts_offset, 3),
            cabin_shift=round(cabin_shift, 3),
            clip_s=round(clip_end_wall - clip_start_wall, 2),
            mode="dual",
        )

        x, y = _PIP_POSITION_MAP.get(
            self.pip_position, ("W-w-10", "H-h-10"),
        )
        logo_exists = Path(ol.LOGO_PATH).exists()

        # PTS-STARTPTS zero-resets the cabin stream's timeline (it can start
        # well above zero when segment_wrap has cycled), then +cabin_shift
        # positions it on the output timeline. cabin_shift = head_offset_s
        # (intro+slate) + cabin_pts_offset (PTS gap between first front and
        # first cabin segment). This keeps cabin aligned with front regardless
        # of how many pre-event segments each stream contributed.
        pip_chain = (
            f"[1:v]eq=brightness=0.06:saturation=1.2,"
            f"scale=iw*{self.pip_scale}:-2,"
            "pad=iw+6:ih+28:3:24:color=black@0.7,"
            "drawtext=text='Cabin':fontsize=22:fontcolor=white@0.9:x=8:y=4,"
            f"setpts=PTS-STARTPTS+{cabin_shift}/TB[pip]"
        )
        overlay_chain = (
            f"[0:v][pip]overlay={x}:{y}:enable='gte(t,{cabin_shift})'[base]"
        )

        audio_delay_ms = int(cabin_shift * 1000)
        audio_chain = f"[1:a]adelay={audio_delay_ms}:all=1,highpass=f=200[a]"

        if logo_exists:
            logo_input_idx = 2  # 0 = front concat, 1 = cabin concat, 2 = logo
            filter_complex = (
                f"{pip_chain};"
                f"{overlay_chain};"
                f"[{logo_input_idx}:v]format=rgba,colorchannelmixer=aa=0.4[logo];"
                f"[base]ass={ass_path}[text];"
                "[text][logo]overlay=10:10:shortest=1,format=yuv420p[out];"
                f"{audio_chain}"
            )
        else:
            filter_complex = (
                f"{pip_chain};"
                f"{overlay_chain};"
                f"[base]ass={ass_path},format=yuv420p[out];"
                f"{audio_chain}"
            )

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-analyzeduration", "20000000",
            "-probesize", "20000000",
            "-i", str(concat_front),
            "-f", "concat", "-safe", "0",
            "-analyzeduration", "20000000",
            "-probesize", "20000000",
            "-i", str(concat_cabin),
        ]
        if logo_exists:
            cmd += ["-loop", "1", "-i", ol.LOGO_PATH]
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "128k",
            "-r", str(self.fps),
            "-movflags", "+faststart",
            str(tmp_mp4),
        ]
        return ["nice", "-n", "10"] + cmd, 900

    def _render_slate(
        self,
        event: "Event",
        tmp_dir: Path,
        *,
        geocoder: Optional[Any] = None,
        driver_name: Optional[str] = None,
    ) -> tuple[Optional[Path], Optional[Path], float]:
        """Render the phase 26 title-card slate into tmp_dir.

        Returns ``(png_path, ts_path, duration)`` on success, or
        ``(None, None, 0.0)`` when:

          - no renderer is wired on this ring buffer (engine disabled it)
          - the renderer raises any exception (Pillow missing, ffmpeg missing,
            timeout, disk error, …)
          - the renderer returns 0.0 or fails to materialise the ts file

        Failure is silent at the ring-buffer level — ``_concatenate_segments``
        simply falls through to the existing ``intro → buffer`` sequence
        (matches the "always render if possible" best-effort intent of D-03).
        """
        if self._title_card_renderer is None:
            return None, None, 0.0

        png_path = tmp_dir / "slate.png"
        ts_path = tmp_dir / "slate.ts"
        try:
            duration = self._title_card_renderer.render(
                event,
                png_path,
                ts_path,
                geocoder=geocoder,
                driver_name=driver_name,
            )
        except Exception as exc:
            log.error(
                "slate_render_exception",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None, None, 0.0

        if duration <= 0.0 or not ts_path.exists():
            return None, None, 0.0
        return png_path, ts_path, duration

    def _concatenate_segments(
        self,
        segments: list[Path],
        prefix: str,
        cabin_segments: Optional[list[Path]] = None,
    ) -> Optional[Path]:
        """Concatenate MPEG-TS segments into a single MP4.

        Uses the ffmpeg concat demuxer (not byte-concatenation) so that PTS is
        adjusted at each file boundary. Byte-joining TS files with different PTS
        origins (intro vs live segments, or segments from different ffmpeg runs)
        causes timestamp discontinuities that players show as freezes/stutters.

        When ``cabin_segments`` is populated (dual-output mode), a second concat
        list is produced for the cabin stream and both feed a single ffmpeg pass
        that composites the cabin PiP onto the front frames. Front and cabin
        share a PTS origin from the source ffmpeg, so no offset math is needed
        beyond skipping the intro window via ``setpts``/``enable``.
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

        # Build file list for the front concat demuxer (intro + slate + live
        # segments). Phase 26: slate.ts inserts between intro and live footage
        # when the renderer produced one; otherwise falls through to the
        # original intro→buffer sequence.
        files: list[Path] = []
        if self._intro_ts and self._intro_ts.exists():
            files.append(self._intro_ts)

        # Phase 26: slate.ts lives in segments[0].parent (same tmp dir as
        # concat.txt) so it's cleaned up at the end of the save pass.
        # Skipped cleanly when the renderer is missing or returned 0.0:
        # _pending_slate_duration is 0.0 in that case and downstream offsets
        # fall through to intro_duration alone.
        slate_ts = self._pending_slate_ts
        slate_duration = self._pending_slate_duration
        if slate_ts is not None and slate_ts.exists() and slate_duration > 0.0:
            files.append(slate_ts)
            log.info(
                "slate_inserted",
                ts=str(slate_ts),
                slate_s=round(slate_duration, 2),
            )

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

        # Cabin concat list — no intro, cabin stream is shifted past intro in
        # the filter graph via setpts.
        cabin_concat: Optional[Path] = None
        cabin_bytes = 0
        use_cabin = bool(cabin_segments) and self.input_format == "h264"
        if use_cabin:
            cabin_concat = segments[0].parent / "concat_cabin.txt"
            try:
                with open(cabin_concat, "w") as f:
                    for p in cabin_segments or []:
                        f.write(f"file '{p}'\n")
                cabin_bytes = sum(
                    p.stat().st_size for p in (cabin_segments or []) if p.exists()
                )
            except Exception as e:
                log.warning("concat_cabin_list_write_error", error=str(e))
                cabin_concat = None
                use_cabin = False

        log.info(
            "concat_segments",
            segment_count=len(segments),
            total_mb=round(total_input_bytes / (1024 * 1024), 2),
            cabin_segment_count=len(cabin_segments or []),
            cabin_mb=round(cabin_bytes / (1024 * 1024), 2),
        )

        # Remux via concat demuxer → MP4 into buffer dir first, then move to
        # captures so rsync never sees a partial file in the output directory.
        # Large probesize ensures ffmpeg finds SPS/PPS NAL units even if the
        # h264_v4l2m2m encoder didn't emit them until a few seconds after startup.
        tmp_mp4 = segments[0].parent / f".tmp_{output_path.name}"

        if use_cabin and cabin_concat is not None and self.overlay_path:
            cabin_pts_offset = 0.0
            if segments and cabin_segments:
                front_start = self._probe_start_pts(segments[0])
                cabin_start = self._probe_start_pts(cabin_segments[0])
                cabin_pts_offset = cabin_start - front_start
                log.info(
                    "cabin_pts_sync",
                    front_seg=segments[0].name,
                    cabin_seg=cabin_segments[0].name,
                    front_start=round(front_start, 3),
                    cabin_start=round(cabin_start, 3),
                    cabin_pts_offset=round(cabin_pts_offset, 3),
                )
            cmd, timeout = self._build_dual_concat_reencode_cmd(
                segments, concat_list, cabin_concat, tmp_mp4,
                cabin_pts_offset=cabin_pts_offset,
            )
        elif self.input_format == "h264" and self.overlay_path:
            # H264 passthrough stored raw segments; burn in HUD + logo now.
            cmd, timeout = self._build_concat_reencode_cmd(
                segments, concat_list, tmp_mp4,
            )
        else:
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
            timeout = 60

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            concat_list.unlink(missing_ok=True)
            if cabin_concat is not None:
                cabin_concat.unlink(missing_ok=True)

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
            if cabin_concat is not None:
                cabin_concat.unlink(missing_ok=True)
            tmp_mp4.unlink(missing_ok=True)
            return None
        except Exception as e:
            log.error("concat_error", error=str(e))
            concat_list.unlink(missing_ok=True)
            if cabin_concat is not None:
                cabin_concat.unlink(missing_ok=True)
            tmp_mp4.unlink(missing_ok=True)
            return None

    def _cleanup_buffer(self, include_saves: bool = True) -> None:
        """Remove segment files (and optionally save dirs) from the buffer.

        Preserves intro.ts so it doesn't need to be re-converted on every
        restart.

        ``include_saves``: when True (process start), wipe stale ``save_*``
        directories left behind by a crashed prior run. When False (mid-run
        ffmpeg restart), leave them alone — a save worker thread may be
        actively using one. Deleting them mid-flight strands the concat
        list pointing at vanished pre-event segment copies, which is the
        cause of the recurring ``concat_failed`` /
        ``cabin_pre_000.ts: Impossible to open`` cascade.
        """
        if not self.buffer_dir.exists():
            return
        for pattern in ("seg_*.ts", "cabin_*.ts"):
            for f in self.buffer_dir.glob(pattern):
                f.unlink(missing_ok=True)
        combined = self.buffer_dir / "combined.ts"
        combined.unlink(missing_ok=True)
        if include_saves:
            for d in self.buffer_dir.glob("save_*"):
                shutil.rmtree(str(d), ignore_errors=True)

    def _cleanup_pending_slates(self) -> None:
        """Sweep pending_slates/ of orphan files from crashed prior runs.

        G-04 fix: any file whose mtime predates this process's start is an
        orphan by definition. save_event cannot fire until start() returns,
        so an in-run writer will always produce mtime > _process_start_time.
        The save_id guard the original implementation had was broken at
        startup (_save_counter == 0 means numeric orphans could never satisfy
        `save_id < _save_counter`) and is not needed for correctness — see
        26-REVIEW.md WR-01.
        """
        try:
            entries = list(self._pending_slates_dir.iterdir())
        except FileNotFoundError:
            return
        removed = 0
        for entry in entries:
            try:
                if not entry.is_file():
                    continue
                if entry.stat().st_mtime < self._process_start_time:
                    entry.unlink()
                    removed += 1
            except OSError:
                continue
        if removed > 0:
            log.info("pending_slates_swept", removed=removed)
        else:
            log.debug("pending_slates_swept", removed=0)
