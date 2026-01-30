"""Video recorder using ffmpeg for webcam capture."""

import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class VideoRecorder:
    """Record video from USB webcam using ffmpeg.

    Runs ffmpeg as a subprocess for reliable capture.
    Non-blocking - recording runs in background.
    """

    def __init__(
        self,
        output_dir: str = "/var/lib/shitbox/captures",
        device: str = "/dev/video0",
        resolution: str = "1280x720",
        fps: int = 30,
    ):
        """Initialise video recorder.

        Args:
            output_dir: Directory to save video files.
            device: Video device path (e.g., /dev/video0).
            resolution: Video resolution (e.g., 1280x720).
            fps: Frames per second.
        """
        self.output_dir = Path(output_dir)
        self.device = device
        self.resolution = resolution
        self.fps = fps

        self._current_process: Optional[subprocess.Popen] = None
        self._current_output: Optional[Path] = None
        self._recording_start: Optional[float] = None

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        if self._current_process is None:
            return False
        return self._current_process.poll() is None

    def start_recording(
        self,
        duration_seconds: int = 60,
        filename_prefix: str = "manual_capture",
    ) -> Optional[Path]:
        """Start recording video.

        Args:
            duration_seconds: How long to record.
            filename_prefix: Prefix for output filename.

        Returns:
            Path to output file, or None if failed to start.
        """
        if self.is_recording:
            log.warning("video_already_recording")
            return self._current_output

        # Create output directory with date subdirectory
        today = datetime.now().strftime("%Y-%m-%d")
        output_subdir = self.output_dir / today
        output_subdir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%H%M%S")
        counter = 1
        while True:
            filename = f"{filename_prefix}_{timestamp}_{counter:03d}.mp4"
            output_path = output_subdir / filename
            if not output_path.exists():
                break
            counter += 1

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", self.resolution,
            "-framerate", str(self.fps),
            "-i", self.device,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-t", str(duration_seconds),
            str(output_path),
        ]

        log.info(
            "video_recording_starting",
            output=str(output_path),
            duration=duration_seconds,
            device=self.device,
        )

        try:
            self._current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._current_output = output_path
            self._recording_start = time.time()

            # Start thread to monitor completion
            threading.Thread(
                target=self._monitor_recording,
                daemon=True,
            ).start()

            return output_path

        except FileNotFoundError:
            log.error("ffmpeg_not_found", hint="Install with: sudo apt install ffmpeg")
            return None
        except Exception as e:
            log.error("video_recording_start_failed", error=str(e))
            return None

    def stop_recording(self) -> None:
        """Stop current recording early."""
        if not self.is_recording:
            return

        log.info("video_recording_stopping")

        try:
            self._current_process.terminate()
            self._current_process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._current_process.kill()
        except Exception as e:
            log.error("video_stop_error", error=str(e))

        self._current_process = None

    def _monitor_recording(self) -> None:
        """Monitor ffmpeg process and log completion."""
        if self._current_process is None:
            return

        # Wait for process to complete
        returncode = self._current_process.wait()
        duration = time.time() - self._recording_start if self._recording_start else 0

        if returncode == 0:
            # Check file size
            if self._current_output and self._current_output.exists():
                size_mb = self._current_output.stat().st_size / (1024 * 1024)
                log.info(
                    "video_recording_complete",
                    output=str(self._current_output),
                    duration_seconds=round(duration, 1),
                    size_mb=round(size_mb, 2),
                )
            else:
                log.warning("video_file_missing", output=str(self._current_output))
        else:
            # Get stderr for debugging
            stderr = ""
            if self._current_process.stderr:
                try:
                    stderr = self._current_process.stderr.read().decode()[-500:]
                except Exception:
                    pass
            log.error(
                "video_recording_failed",
                returncode=returncode,
                stderr=stderr,
            )

        self._current_process = None

    def cleanup_old_captures(self, max_age_days: int = 14) -> int:
        """Remove captures older than max_age_days.

        Args:
            max_age_days: Maximum age of files to keep.

        Returns:
            Number of files deleted.
        """
        if not self.output_dir.exists():
            return 0

        deleted = 0
        cutoff = time.time() - (max_age_days * 86400)

        for video_file in self.output_dir.rglob("*.mp4"):
            try:
                if video_file.stat().st_mtime < cutoff:
                    video_file.unlink()
                    deleted += 1
            except Exception as e:
                log.warning("cleanup_file_error", file=str(video_file), error=str(e))

        # Remove empty date directories
        for subdir in self.output_dir.iterdir():
            if subdir.is_dir():
                try:
                    subdir.rmdir()  # Only removes if empty
                except OSError:
                    pass  # Directory not empty

        if deleted > 0:
            log.info("video_cleanup_complete", deleted=deleted)

        return deleted

    def get_storage_size_mb(self) -> float:
        """Get total size of captures directory in MB."""
        if not self.output_dir.exists():
            return 0.0

        total = sum(
            f.stat().st_size
            for f in self.output_dir.rglob("*.mp4")
            if f.is_file()
        )
        return total / (1024 * 1024)
