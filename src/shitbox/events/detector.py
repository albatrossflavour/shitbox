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
    ROLLOVER = "rollover"  # Phase 22 (IMU-03)
    TPMS_LEAK = "tpms_leak"  # Phase 28 (SPEC-8) — fired by TPMSService, no video buffer save


@dataclass
class Event:
    """Structured detection event produced by the EventDetector state machine.

    Peak-field semantics (locked by plan 22-02 / IMU-03):
        peak_ax/ay/az and peak_gx/gy/gz are the accelerometer and gyro readings
        TAKEN AT THE SAMPLE where `peak_value` (the tracked axis) was observed.
        They are a point-in-time snapshot of the full 6-DoF state at the peak,
        NOT per-axis maxima computed independently over the event window.

        This means: if |gx| is tracked and peaks at sample N, `peak_gy` is the
        gy value at sample N — not the maximum |gy| seen anywhere between
        start_time and end_time. If you need per-axis maxima, compute them
        from `samples` (the retained pre/in-event IMU buffer).
    """

    event_type: EventType
    start_time: float  # Unix timestamp
    end_time: float
    peak_value: float  # Peak g-force or stddev
    peak_ax: float
    peak_ay: float
    peak_az: float
    peak_gx: float = 0.0
    peak_gy: float = 0.0
    peak_gz: float = 0.0
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
            "peak_gx": round(self.peak_gx, 3),
            "peak_gy": round(self.peak_gy, 3),
            "peak_gz": round(self.peak_gz, 3),
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
    hard_brake_threshold_g: float = -0.35
    hard_brake_min_duration_ms: int = 200

    # Big corner: |ay| > threshold for duration
    big_corner_threshold_g: float = 0.45
    big_corner_yaw_dps: float = 60.0  # OR-trigger: sustained yaw rate (Phase 22 / IMU-04)
    big_corner_min_duration_ms: int = 300

    # Rough road: stddev of az over window > threshold
    rough_road_threshold_stddev: float = 0.3
    rough_road_window_ms: int = 1000

    # High G: sqrt(ax² + ay²) > threshold
    high_g_threshold: float = 0.8
    high_g_min_duration_ms: int = 300
    high_g_min_speed_kmh: float = 10.0

    # Rollover: sustained |gx| or |gy| above threshold (Phase 22 / IMU-03)
    rollover_threshold_dps: float = 250.0
    rollover_min_duration_ms: int = 150

    # Cooldown: minimum time between events of same type
    cooldown_seconds: float = 10.0

    # Pre/post event capture
    pre_event_seconds: float = 5.0
    post_event_seconds: float = 10.0

    # Application poll rate (Hz). Mirrored from LSM6DSOXConfig.sample_rate_hz by
    # engine wiring so the detector's rolling-window sizes match the ring buffer's
    # fill rate. Default aligns with LSM6DSOXConfig default (25 Hz per 22-07).
    # Placed at end of dataclass for positional-arg call-site safety.
    sample_rate_hz: float = 25.0


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
        get_speed: Optional[Callable[[], float]] = None,
    ):
        """Initialise event detector.

        Args:
            ring_buffer: Source of IMU samples.
            config: Detection thresholds.
            on_event: Callback when event is detected.
            get_speed: Callback returning current speed in km/h (from GPS).
        """
        self.ring_buffer = ring_buffer
        self.config = config or DetectorConfig()
        self.on_event = on_event
        self._get_speed = get_speed or (lambda: 0.0)

        # Active event tracking
        self._active_events: Dict[EventType, dict] = {}

        # Cooldown tracking (last event time per type)
        self._last_event_time: Dict[EventType, float] = {}

        # Stats
        self.events_detected: Dict[EventType, int] = {t: 0 for t in EventType}

        # Rolling window for rough road detection. Sized from ms window * Hz / 1000
        # so it scales with the application poll rate (22-07). Pre-22-07 this hardcoded
        # a /10 divisor assuming 100 Hz, which silently broke at any other rate.
        # max(1, ...) prevents a zero-size window if someone configures a pathological
        # <1 Hz rate with a <1 s window.
        self._az_window: List[float] = []
        self._az_window_size = max(
            1,
            int(self.config.rough_road_window_ms * self.config.sample_rate_hz / 1000.0),
        )

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
        completed_event = self._check_rollover(sample) or completed_event  # Phase 22

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
            "peak_gx": sample.gx,
            "peak_gy": sample.gy,
            "peak_gz": sample.gz,
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
            # peak_gx/gy/gz are snapshot-at-peak, NOT per-axis maxima — they
            # record the full gyro triple at the same sample where peak_value
            # (the tracked axis) was observed. Matches peak_ax/ay/az semantics.
            # See Event dataclass docstring for the contract.
            event["peak_gx"] = sample.gx
            event["peak_gy"] = sample.gy
            event["peak_gz"] = sample.gz

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
            EventType.ROLLOVER: self.config.rollover_min_duration_ms,
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
            peak_gx=event_data["peak_gx"],
            peak_gy=event_data["peak_gy"],
            peak_gz=event_data["peak_gz"],
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
        """Check for hard braking (strong positive ay; Y+ is rearward so braking = +ay)."""
        event_type = EventType.HARD_BRAKE
        threshold = self.config.hard_brake_threshold_g

        if -sample.ay < threshold:
            if event_type not in self._active_events:
                self._start_event(event_type, sample, -sample.ay)
            else:
                self._update_event(event_type, sample, -sample.ay)
            return None
        else:
            return self._end_event(event_type, sample)

    def _check_big_corner(self, sample: IMUSample) -> Optional[Event]:
        """Check for big corner (strong lateral ax OR sustained yaw rate gz).

        Phase 22 / IMU-04. Lateral-g alone misses slow tight turns (lateral g
        is speed^2 / radius). Adding gz captures yaw as a cleaner signature of
        cornering; either exceeding its threshold triggers. The trigger value
        fed to _start_event/_update_event is whichever axis is more strongly
        past its threshold (ratio-based), so the peak-tracking stays coherent.
        """
        event_type = EventType.BIG_CORNER
        g_threshold = self.config.big_corner_threshold_g
        yaw_threshold = self.config.big_corner_yaw_dps
        ax_ratio = abs(sample.ax) / g_threshold if g_threshold > 0 else 0.0
        gz_ratio = abs(sample.gz) / yaw_threshold if yaw_threshold > 0 else 0.0
        triggered = ax_ratio > 1.0 or gz_ratio > 1.0
        if triggered:
            trigger_value = sample.ax if ax_ratio >= gz_ratio else sample.gz
            if event_type not in self._active_events:
                self._start_event(event_type, sample, trigger_value)
            else:
                self._update_event(event_type, sample, trigger_value)
            return None
        else:
            return self._end_event(event_type, sample)

    def _check_high_g(self, sample: IMUSample) -> Optional[Event]:
        """Check for high combined lateral/longitudinal g."""
        event_type = EventType.HIGH_G
        threshold = self.config.high_g_threshold

        combined_g = math.sqrt(sample.ax ** 2 + sample.ay ** 2)

        # Ignore high-G when stationary/crawling (e.g. pulling away from stop)
        if combined_g > threshold and self._get_speed() < self.config.high_g_min_speed_kmh:
            return self._end_event(event_type, sample)

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

    def _check_rollover(self, sample: IMUSample) -> Optional[Event]:
        """Check for rollover (sustained roll or pitch rate).

        Phase 22 / IMU-03. Triggers on |gx| OR |gy| above rollover_threshold_dps
        (default 250 dps — below NHTSA 300 dps clipping reference, above normal
        aggressive cornering ~100 dps). Duration gate in _end_event rejects
        spikes shorter than rollover_min_duration_ms (default 150 ms).
        """
        event_type = EventType.ROLLOVER
        threshold = self.config.rollover_threshold_dps
        abs_gx = abs(sample.gx)
        abs_gy = abs(sample.gy)
        if abs_gx > threshold or abs_gy > threshold:
            trigger_value = sample.gx if abs_gx >= abs_gy else sample.gy
            if event_type not in self._active_events:
                self._start_event(event_type, sample, trigger_value)
            else:
                self._update_event(event_type, sample, trigger_value)
            return None
        else:
            return self._end_event(event_type, sample)
