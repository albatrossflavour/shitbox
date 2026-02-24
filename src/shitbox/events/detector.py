"""Event detection from high-rate IMU data."""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class EventType(Enum):
    """Types of detectable events."""

    HARD_BRAKE = "hard_brake"
    BIG_CORNER = "big_corner"
    ROUGH_ROAD = "rough_road"
    HIGH_G = "high_g"
    MANUAL_CAPTURE = "manual_capture"
    BOOT = "boot"


@dataclass
class Event:
    """A detected driving event."""

    event_type: EventType
    start_time: float  # Unix timestamp
    end_time: float
    peak_value: float  # Peak g-force or stddev
    peak_ax: float
    peak_ay: float
    peak_az: float
    samples: List[IMUSample] = field(default_factory=list)
    lat: Optional[float] = None
    lng: Optional[float] = None
    speed_kmh: Optional[float] = None
    location_name: Optional[str] = None
    distance_from_start_km: Optional[float] = None
    distance_to_destination_km: Optional[float] = None

    @property
    def duration(self) -> float:
        """Event duration in seconds."""
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        """Convert to JSON-serialisable dict."""
        d: dict = {
            "type": self.event_type.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": int(self.duration * 1000),
            "peak_value": round(self.peak_value, 3),
            "peak_ax": round(self.peak_ax, 3),
            "peak_ay": round(self.peak_ay, 3),
            "peak_az": round(self.peak_az, 3),
            "sample_count": len(self.samples),
        }
        if self.lat is not None:
            d["lat"] = round(self.lat, 6)
        if self.lng is not None:
            d["lng"] = round(self.lng, 6)
        if self.speed_kmh is not None:
            d["speed_kmh"] = round(self.speed_kmh, 1)
        if self.location_name is not None:
            d["location_name"] = self.location_name
        if self.distance_from_start_km is not None:
            d["distance_from_start_km"] = round(self.distance_from_start_km, 1)
        if self.distance_to_destination_km is not None:
            d["distance_to_destination_km"] = round(self.distance_to_destination_km, 1)
        return d


@dataclass
class DetectorConfig:
    """Configuration for event detection thresholds."""

    # Hard braking: ax < threshold for duration
    hard_brake_threshold_g: float = -0.45
    hard_brake_min_duration_ms: int = 200

    # Big corner: |ay| > threshold for duration
    big_corner_threshold_g: float = 0.6
    big_corner_min_duration_ms: int = 300

    # Rough road: stddev of az over window > threshold
    rough_road_threshold_stddev: float = 0.3
    rough_road_window_ms: int = 1000

    # High G: sqrt(ax² + ay²) > threshold
    high_g_threshold: float = 0.85
    high_g_min_duration_ms: int = 150

    # Cooldown: minimum time between events of same type
    cooldown_seconds: float = 10.0

    # Pre/post event capture
    pre_event_seconds: float = 5.0
    post_event_seconds: float = 10.0


class EventDetector:
    """Detects driving events from high-rate IMU data.

    Runs detection algorithms on each new sample and fires
    callbacks when events are detected.
    """

    def __init__(
        self,
        ring_buffer: RingBuffer,
        config: Optional[DetectorConfig] = None,
        on_event: Optional[Callable[[Event], None]] = None,
    ):
        """Initialise event detector.

        Args:
            ring_buffer: Source of IMU samples.
            config: Detection thresholds.
            on_event: Callback when event is detected.
        """
        self.ring_buffer = ring_buffer
        self.config = config or DetectorConfig()
        self.on_event = on_event

        # Active event tracking
        self._active_events: Dict[EventType, dict] = {}

        # Cooldown tracking (last event time per type)
        self._last_event_time: Dict[EventType, float] = {}

        # Stats
        self.events_detected: Dict[EventType, int] = {t: 0 for t in EventType}

        # Rolling window for rough road detection
        self._az_window: List[float] = []
        self._az_window_size = int(
            self.config.rough_road_window_ms / 10
        )  # Assuming ~100 Hz

    def process_sample(self, sample: IMUSample) -> Optional[Event]:
        """Process a new sample and check for events.

        Args:
            sample: New IMU sample.

        Returns:
            Completed Event if one just ended, None otherwise.
        """
        completed_event = None

        # Check each event type
        completed_event = self._check_hard_brake(sample) or completed_event
        completed_event = self._check_big_corner(sample) or completed_event
        completed_event = self._check_high_g(sample) or completed_event
        completed_event = self._check_rough_road(sample) or completed_event

        return completed_event

    def _is_on_cooldown(self, event_type: EventType) -> bool:
        """Check if event type is in cooldown period."""
        last_time = self._last_event_time.get(event_type, 0)
        return (time.time() - last_time) < self.config.cooldown_seconds

    def _start_event(
        self, event_type: EventType, sample: IMUSample, trigger_value: float
    ) -> None:
        """Start tracking a potential event."""
        if event_type in self._active_events:
            return  # Already tracking

        if self._is_on_cooldown(event_type):
            return

        self._active_events[event_type] = {
            "start_time": sample.timestamp,
            "samples": [sample],
            "peak_value": abs(trigger_value),
            "peak_ax": sample.ax,
            "peak_ay": sample.ay,
            "peak_az": sample.az,
        }

    def _update_event(
        self, event_type: EventType, sample: IMUSample, current_value: float
    ) -> None:
        """Update an active event with new sample."""
        if event_type not in self._active_events:
            return

        event = self._active_events[event_type]
        event["samples"].append(sample)

        if abs(current_value) > event["peak_value"]:
            event["peak_value"] = abs(current_value)
            event["peak_ax"] = sample.ax
            event["peak_ay"] = sample.ay
            event["peak_az"] = sample.az

    def _end_event(self, event_type: EventType, sample: IMUSample) -> Optional[Event]:
        """End an active event and return it if valid."""
        if event_type not in self._active_events:
            return None

        event_data = self._active_events.pop(event_type)
        duration_ms = (sample.timestamp - event_data["start_time"]) * 1000

        # Check minimum duration
        min_duration = {
            EventType.HARD_BRAKE: self.config.hard_brake_min_duration_ms,
            EventType.BIG_CORNER: self.config.big_corner_min_duration_ms,
            EventType.HIGH_G: self.config.high_g_min_duration_ms,
            EventType.ROUGH_ROAD: self.config.rough_road_window_ms,
        }.get(event_type, 0)

        if duration_ms < min_duration:
            return None

        # Get pre-event samples from ring buffer
        pre_samples = self.ring_buffer.get_window(
            self.config.pre_event_seconds + duration_ms / 1000
        )

        # Create event
        event = Event(
            event_type=event_type,
            start_time=event_data["start_time"],
            end_time=sample.timestamp,
            peak_value=event_data["peak_value"],
            peak_ax=event_data["peak_ax"],
            peak_ay=event_data["peak_ay"],
            peak_az=event_data["peak_az"],
            samples=pre_samples,
        )

        # Update stats and cooldown
        self.events_detected[event_type] += 1
        self._last_event_time[event_type] = sample.timestamp

        log.info(
            "event_detected",
            type=event_type.value,
            duration_ms=int(duration_ms),
            peak_g=round(event.peak_value, 2),
        )

        if self.on_event:
            self.on_event(event)

        return event

    def _check_hard_brake(self, sample: IMUSample) -> Optional[Event]:
        """Check for hard braking (strong negative ax)."""
        event_type = EventType.HARD_BRAKE
        threshold = self.config.hard_brake_threshold_g

        if sample.ax < threshold:
            if event_type not in self._active_events:
                self._start_event(event_type, sample, sample.ax)
            else:
                self._update_event(event_type, sample, sample.ax)
            return None
        else:
            return self._end_event(event_type, sample)

    def _check_big_corner(self, sample: IMUSample) -> Optional[Event]:
        """Check for big corner (strong lateral ay)."""
        event_type = EventType.BIG_CORNER
        threshold = self.config.big_corner_threshold_g

        if abs(sample.ay) > threshold:
            if event_type not in self._active_events:
                self._start_event(event_type, sample, sample.ay)
            else:
                self._update_event(event_type, sample, sample.ay)
            return None
        else:
            return self._end_event(event_type, sample)

    def _check_high_g(self, sample: IMUSample) -> Optional[Event]:
        """Check for high combined lateral/longitudinal g."""
        event_type = EventType.HIGH_G
        threshold = self.config.high_g_threshold

        combined_g = math.sqrt(sample.ax ** 2 + sample.ay ** 2)

        if combined_g > threshold:
            if event_type not in self._active_events:
                self._start_event(event_type, sample, combined_g)
            else:
                self._update_event(event_type, sample, combined_g)
            return None
        else:
            return self._end_event(event_type, sample)

    def _check_rough_road(self, sample: IMUSample) -> Optional[Event]:
        """Check for rough road (high variance in az)."""
        event_type = EventType.ROUGH_ROAD
        threshold = self.config.rough_road_threshold_stddev

        # Maintain rolling window of az values
        self._az_window.append(sample.az)
        if len(self._az_window) > self._az_window_size:
            self._az_window.pop(0)

        if len(self._az_window) < self._az_window_size:
            return None  # Not enough data yet

        # Calculate standard deviation
        mean_az = sum(self._az_window) / len(self._az_window)
        variance = sum((z - mean_az) ** 2 for z in self._az_window) / len(
            self._az_window
        )
        stddev = math.sqrt(variance)

        if stddev > threshold:
            if event_type not in self._active_events:
                self._start_event(event_type, sample, stddev)
            else:
                self._update_event(event_type, sample, stddev)
            return None
        else:
            return self._end_event(event_type, sample)
