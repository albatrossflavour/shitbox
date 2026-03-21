"""Picture-in-picture compositor for dual-camera event clips.

Merges a primary (full-frame) clip and a secondary (cabin) clip into a single
MP4 with the secondary inset in the chosen corner.
"""

import subprocess
import tempfile
from pathlib import Path

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

MIN_CLIP_SECONDS = 5


_POSITION_OVERLAY = {
    "bottom_right": ("W-w-10", "H-h-10"),
    "bottom_left": ("10", "H-h-10"),
    "top_right": ("W-w-10", "10"),
    "top_left": ("10", "10"),
}


class PipCompositor:
    """Composite two video clips into a single PIP output.

    The primary clip occupies the full frame; the secondary is scaled and
    overlaid in a corner. Uses hardware encoding (h264_v4l2m2m) with a
    libx264 fallback. Deletes both input clips on success.
    """

    def __init__(self, position: str = "bottom_right", scale: float = 0.25):
        self.position = position
        self.scale = scale
        self._encoder = self._detect_encoder()

    @staticmethod
    def _detect_encoder() -> list[str]:
        """Return encoder args, preferring h264_v4l2m2m."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            if "h264_v4l2m2m" in result.stdout.decode():
                return ["-c:v", "h264_v4l2m2m", "-b:v", "6M"]
        except Exception:
            pass
        return ["-c:v", "libx264", "-preset", "ultrafast"]

    def composite(
        self,
        primary_path: Path,
        secondary_path: Path,
        output_path: Path,
        sync_offset_seconds: float = 0.0,
        pip_offset_seconds: float = 0.0,
    ) -> bool:
        """Merge primary and secondary clips into a PIP composite.

        If the secondary clip is missing or shorter than MIN_CLIP_SECONDS,
        copies the primary to output_path unchanged.

        Deletes both input clips on success.

        Args:
            primary_path: Full-frame clip (front cam).
            secondary_path: Cabin clip to overlay as PIP.
            output_path: Destination for the composited clip.

        Returns:
            True on success, False on failure. Input clips are only deleted
            on success.
        """
        if not primary_path.exists():
            log.warning("pip_composite_primary_missing", path=str(primary_path))
            return False

        if not secondary_path.exists() or not self._clip_long_enough(secondary_path):
            log.info(
                "pip_composite_secondary_missing_or_short",
                secondary=str(secondary_path),
                reason="using primary only",
            )
            secondary_path.unlink(missing_ok=True)
            return self._copy_primary(primary_path, output_path)

        # sync_offset_seconds = pip_clip_start_mtime - primary_clip_start_mtime
        # Derived from GPS-clock filesystem mtimes of the oldest pre-event segments.
        # > 0: pip started later → delay pip with -itsoffset
        # < 0: pip started earlier → trim pip start with -ss
        excess = sync_offset_seconds
        log.info("pip_sync", excess_s=round(excess, 3))

        # PiP enable gate: after intro (if any) and after pip content starts
        effective_pip_offset = max(pip_offset_seconds, max(0.0, excess))

        x, y = _POSITION_OVERLAY.get(self.position, ("W-w-10", "H-h-10"))
        enable = f":enable='gte(t,{effective_pip_offset:.3f})'" if effective_pip_offset > 0 else ""
        filter_complex = (
            f"[1:v]scale=iw*{self.scale}:-2,"
            f"pad=iw+4:ih+20:2:18:color=black@0.7,"
            f"drawtext=text='Cabin':fontsize=13:fontcolor=white@0.9"
            f":x=6:y=3[pip];"
            f"[0:v][pip]overlay={x}:{y}{enable}"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temp file in same dir, then rename, so we never leave a
        # partial file at output_path if ffmpeg fails mid-way.
        tmp = output_path.parent / f".tmp_{output_path.name}"
        try:
            cmd = ["ffmpeg", "-y", "-i", str(primary_path)]
            if excess > 0.5:
                # Front has more pre-event: delay secondary so events align
                cmd += ["-itsoffset", f"{excess:.3f}"]
            elif excess < -0.5:
                # Cabin has more pre-event: trim secondary start
                cmd += ["-ss", f"{-excess:.3f}"]
            cmd += ["-i", str(secondary_path), "-filter_complex", filter_complex]
            cmd += self._encoder
            cmd += ["-c:a", "copy", str(tmp)]

            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=120,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode()[-500:] if result.stderr else ""
                log.error(
                    "pip_composite_failed",
                    returncode=result.returncode,
                    stderr=stderr,
                )
                tmp.unlink(missing_ok=True)
                return False

            if not tmp.exists() or tmp.stat().st_size == 0:
                log.error("pip_composite_empty_output")
                tmp.unlink(missing_ok=True)
                return False

            tmp.rename(output_path)
            size_mb = round(output_path.stat().st_size / (1024 * 1024), 2)
            log.info(
                "pip_composite_complete",
                output=str(output_path),
                size_mb=size_mb,
                position=self.position,
            )

            # Clean up inputs after a confirmed successful composite
            primary_path.unlink(missing_ok=True)
            secondary_path.unlink(missing_ok=True)
            return True

        except subprocess.TimeoutExpired:
            log.error("pip_composite_timeout")
            tmp.unlink(missing_ok=True)
            return False
        except Exception as e:
            log.error("pip_composite_error", error=str(e))
            tmp.unlink(missing_ok=True)
            return False

    def _copy_primary(self, primary_path: Path, output_path: Path) -> bool:
        """Copy primary to output when secondary is unavailable."""
        try:
            import shutil
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(primary_path), str(output_path))
            primary_path.unlink(missing_ok=True)
            log.info("pip_composite_primary_only", output=str(output_path))
            return True
        except Exception as e:
            log.error("pip_composite_copy_error", error=str(e))
            return False

    @staticmethod
    def _get_start_time(path: Path) -> float:
        """Return clip start time in seconds (from shared monotonic clock), or 0.0 on error."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=start_time",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return float(result.stdout.decode().strip())
        except Exception:
            return 0.0

    @staticmethod
    def _get_duration(path: Path) -> float:
        """Return clip duration in seconds, or 0.0 on error."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return float(result.stdout.decode().strip())
        except Exception:
            return 0.0

    @staticmethod
    def _clip_long_enough(path: Path) -> bool:
        """Return True if the clip is at least MIN_CLIP_SECONDS long."""
        return PipCompositor._get_duration(path) >= MIN_CLIP_SECONDS
