"""Event storage - saves events as JSON metadata + CSV bursts."""

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from shitbox.events.detector import Event, EventType
from shitbox.events.ring_buffer import IMUSample
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class EventStorage:
    """Stores detected events to disk.

    Each event is saved as:
    - JSON file with metadata
    - CSV file with raw IMU samples

    Directory structure:
    events/
      2026-01-28/
        hard_brake_143052_001.json
        hard_brake_143052_001.csv
        big_corner_144523_002.json
        big_corner_144523_002.csv
    """

    def __init__(
        self,
        base_dir: str = "/var/lib/shitbox/events",
        max_age_days: int = 14,
        max_size_mb: int = 500,
        captures_dir: Optional[str] = None,
    ):
        """Initialise event storage.

        Args:
            base_dir: Base directory for event files.
            max_age_days: Delete events older than this.
            max_size_mb: Maximum total storage size.
            captures_dir: Directory where captures/videos live (for events.json).
        """
        self.base_dir = Path(base_dir)
        self.max_age_days = max_age_days
        self.max_size_mb = max_size_mb
        self.captures_dir = Path(captures_dir) if captures_dir else None

        self._event_counter = 0
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create base directory if needed."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_day_dir(self, timestamp: float) -> Path:
        """Get directory for a specific day."""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        day_str = dt.strftime("%Y-%m-%d")
        day_dir = self.base_dir / day_str
        day_dir.mkdir(exist_ok=True)
        return day_dir

    def _generate_filename(self, event: Event) -> str:
        """Generate base filename for an event."""
        dt = datetime.fromtimestamp(event.start_time, tz=timezone.utc)
        time_str = dt.strftime("%H%M%S")
        self._event_counter += 1
        return f"{event.event_type.value}_{time_str}_{self._event_counter:03d}"

    def save_event(
        self, event: Event, video_path: Optional[Path] = None
    ) -> tuple[Path, Path]:
        """Save an event to disk.

        Args:
            event: The event to save.
            video_path: Path to the associated video capture, if any.

        Returns:
            Tuple of (json_path, csv_path).
        """
        day_dir = self._get_day_dir(event.start_time)
        base_name = self._generate_filename(event)

        json_path = day_dir / f"{base_name}.json"
        csv_path = day_dir / f"{base_name}.csv"

        # Save metadata as JSON
        metadata = event.to_dict()
        metadata["csv_file"] = csv_path.name
        metadata["saved_at"] = datetime.now(timezone.utc).isoformat()
        if video_path:
            metadata["video_path"] = str(video_path)

        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Save samples as CSV
        self._write_csv(csv_path, event.samples)

        log.info(
            "event_saved",
            type=event.event_type.value,
            json=str(json_path),
            samples=len(event.samples),
        )

        return json_path, csv_path

    def update_event_video(
        self, json_path: Path, video_path: Path
    ) -> None:
        """Update a saved event's JSON with a video path.

        Args:
            json_path: Path to the event's JSON metadata file.
            video_path: Path to the video file.
        """
        try:
            with open(json_path) as f:
                metadata = json.load(f)
            metadata["video_path"] = str(video_path)
            with open(json_path, "w") as f:
                json.dump(metadata, f, indent=2)
            log.info(
                "event_video_updated",
                json=str(json_path),
                video=str(video_path),
            )
        except (json.JSONDecodeError, IOError) as e:
            log.error("event_video_update_error", error=str(e))

    def _write_csv(self, path: Path, samples: List[IMUSample]) -> None:
        """Write samples to CSV file."""
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "ax", "ay", "az", "gx", "gy", "gz"])
            for s in samples:
                writer.writerow(
                    [
                        f"{s.timestamp:.6f}",
                        f"{s.ax:.6f}",
                        f"{s.ay:.6f}",
                        f"{s.az:.6f}",
                        f"{s.gx:.6f}",
                        f"{s.gy:.6f}",
                        f"{s.gz:.6f}",
                    ]
                )

    def cleanup_old_events(self) -> int:
        """Delete events older than max_age_days.

        Returns:
            Number of files deleted.
        """
        if not self.base_dir.exists():
            return 0

        cutoff = time.time() - (self.max_age_days * 86400)
        deleted = 0

        for day_dir in self.base_dir.iterdir():
            if not day_dir.is_dir():
                continue

            # Check if directory is old enough to consider
            try:
                dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d")
                dir_timestamp = dir_date.timestamp()
                if dir_timestamp < cutoff:
                    # Delete entire directory
                    for f in day_dir.iterdir():
                        f.unlink()
                        deleted += 1
                    day_dir.rmdir()
                    log.info("deleted_old_event_dir", dir=day_dir.name)
            except ValueError:
                continue  # Not a date-formatted directory

        return deleted

    def get_total_size_mb(self) -> float:
        """Get total size of event storage in MB."""
        if not self.base_dir.exists():
            return 0.0

        total = 0
        for f in self.base_dir.rglob("*"):
            if f.is_file():
                total += f.stat().st_size

        return total / (1024 * 1024)

    def cleanup_by_size(self) -> int:
        """Delete oldest events if over size limit.

        Returns:
            Number of files deleted.
        """
        current_size = self.get_total_size_mb()
        if current_size <= self.max_size_mb:
            return 0

        deleted = 0

        # Get all event files sorted by modification time
        all_files = []
        for f in self.base_dir.rglob("*"):
            if f.is_file():
                all_files.append((f.stat().st_mtime, f))

        all_files.sort()  # Oldest first

        # Delete until under limit
        for mtime, filepath in all_files:
            if self.get_total_size_mb() <= self.max_size_mb * 0.9:
                break
            filepath.unlink()
            deleted += 1

        if deleted:
            log.info("deleted_events_by_size", count=deleted)

        return deleted

    def close_orphaned_events(self) -> int:
        """Close event JSON files that were left open by a prior crash.

        Iterates all ``.json`` files under ``base_dir``.  Any file that is
        missing ``end_time`` or has ``status == "open"`` is considered
        orphaned: it receives ``status = "interrupted"`` and an ``end_time``
        derived from the file's modification time.

        The consolidated ``events.json`` file (if present) is skipped.

        Returns:
            Number of orphaned events that were closed.
        """
        closed = 0

        for json_file in self.base_dir.rglob("*.json"):
            if json_file.name == "events.json":
                continue

            try:
                with open(json_file) as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, IOError) as exc:
                log.warning("orphan_scan_skip", file=str(json_file), error=str(exc))
                continue

            is_orphan = ("end_time" not in meta) or (meta.get("status") == "open")
            if not is_orphan:
                continue

            meta["end_time"] = json_file.stat().st_mtime
            meta["status"] = "interrupted"

            try:
                with open(json_file, "w") as f:
                    json.dump(meta, f, indent=2)
            except IOError as exc:
                log.warning("orphan_close_error", file=str(json_file), error=str(exc))
                continue

            log.info(
                "orphaned_event_closed",
                file=str(json_file),
                event_type=meta.get("type", "unknown"),
            )
            closed += 1

        return closed

    def list_events(
        self, event_type: Optional[EventType] = None, days: int = 7
    ) -> List[dict]:
        """List recent events.

        Args:
            event_type: Filter by type (None for all).
            days: Number of days to look back.

        Returns:
            List of event metadata dicts.
        """
        events = []
        cutoff = time.time() - (days * 86400)

        for json_file in self.base_dir.rglob("*.json"):
            try:
                with open(json_file) as f:
                    metadata = json.load(f)

                if metadata.get("start_time", 0) < cutoff:
                    continue

                if event_type and metadata.get("type") != event_type.value:
                    continue

                metadata["file"] = str(json_file)
                events.append(metadata)
            except (json.JSONDecodeError, IOError):
                continue

        events.sort(key=lambda e: e.get("start_time", 0), reverse=True)
        return events

    def generate_events_json(self, video_base_url: str = "/captures") -> Optional[Path]:
        """Generate events.json index in captures_dir for the website.

        Scans all stored event JSON files and writes a consolidated index
        with fields the website expects: type, timestamp, peak_g, duration_ms,
        speed_kmh, lat, lng, video_url.

        Args:
            video_base_url: URL prefix for video links.

        Returns:
            Path to the generated events.json, or None if no captures_dir.
        """
        if not self.captures_dir:
            return None

        self.captures_dir.mkdir(parents=True, exist_ok=True)
        events_json_path = self.captures_dir / "events.json"

        entries = []
        for json_file in self.base_dir.rglob("*.json"):
            try:
                with open(json_file) as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            start_time = meta.get("start_time")
            if not start_time:
                continue

            dt = datetime.fromtimestamp(start_time, tz=timezone.utc)

            # Build video URL from stored path
            video_url = None
            stored_video = meta.get("video_path")
            if stored_video:
                vp = Path(stored_video)
                if vp.exists():
                    # Use date_dir/filename as relative path
                    video_url = (
                        f"{video_base_url}/{vp.parent.name}/{vp.name}"
                    )

            entry: dict = {
                "type": meta.get("type", "unknown").upper(),
                "timestamp": dt.isoformat(),
                "peak_g": meta.get("peak_value"),
                "duration_ms": meta.get("duration_ms"),
            }
            if meta.get("speed_kmh") is not None:
                entry["speed_kmh"] = meta["speed_kmh"]
            if meta.get("lat") is not None:
                entry["lat"] = meta["lat"]
            if meta.get("lng") is not None:
                entry["lng"] = meta["lng"]
            if meta.get("location_name") is not None:
                entry["location_name"] = meta["location_name"]
            if meta.get("distance_from_start_km") is not None:
                entry["distance_from_start_km"] = meta["distance_from_start_km"]
            if meta.get("distance_to_destination_km") is not None:
                entry["distance_to_destination_km"] = meta["distance_to_destination_km"]
            if video_url:
                entry["video_url"] = video_url

            entries.append(entry)

        entries.sort(key=lambda e: e["timestamp"], reverse=True)

        tmp_path = events_json_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp_path, events_json_path)

        log.info(
            "events_json_generated",
            path=str(events_json_path),
            count=len(entries),
        )
        return events_json_path
