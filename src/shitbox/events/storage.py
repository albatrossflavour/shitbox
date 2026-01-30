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
    ):
        """Initialise event storage.

        Args:
            base_dir: Base directory for event files.
            max_age_days: Delete events older than this.
            max_size_mb: Maximum total storage size.
        """
        self.base_dir = Path(base_dir)
        self.max_age_days = max_age_days
        self.max_size_mb = max_size_mb

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

    def save_event(self, event: Event) -> tuple[Path, Path]:
        """Save an event to disk.

        Args:
            event: The event to save.

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
