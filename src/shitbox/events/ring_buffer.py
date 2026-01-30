"""Thread-safe ring buffer for high-rate IMU samples."""

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Iterator, List, Optional


@dataclass(slots=True)
class IMUSample:
    """Single IMU sample at high rate."""

    timestamp: float  # Unix seconds
    ax: float  # Acceleration X (g)
    ay: float  # Acceleration Y (g)
    az: float  # Acceleration Z (g)
    gx: float  # Gyro X (deg/s) - optional, can be 0
    gy: float  # Gyro Y (deg/s)
    gz: float  # Gyro Z (deg/s)


class RingBuffer:
    """Thread-safe ring buffer for IMU samples.

    Maintains a fixed-duration window of samples in RAM.
    Designed for ~100 Hz sampling with 20-30 second retention.
    """

    def __init__(self, max_seconds: float = 30.0, sample_rate_hz: float = 100.0):
        """Initialise ring buffer.

        Args:
            max_seconds: Maximum duration to retain.
            sample_rate_hz: Expected sample rate for sizing.
        """
        self.max_samples = int(max_seconds * sample_rate_hz)
        self._buffer: deque[IMUSample] = deque(maxlen=self.max_samples)
        self._lock = threading.Lock()

    def append(self, sample: IMUSample) -> None:
        """Add a sample to the buffer (thread-safe)."""
        with self._lock:
            self._buffer.append(sample)

    def get_window(self, seconds: float) -> List[IMUSample]:
        """Get the last N seconds of samples.

        Args:
            seconds: Duration to retrieve.

        Returns:
            List of samples (oldest first).
        """
        with self._lock:
            if not self._buffer:
                return []

            now = self._buffer[-1].timestamp
            cutoff = now - seconds
            return [s for s in self._buffer if s.timestamp >= cutoff]

    def get_all(self) -> List[IMUSample]:
        """Get all samples in buffer."""
        with self._lock:
            return list(self._buffer)

    def get_latest(self, n: int = 1) -> List[IMUSample]:
        """Get the N most recent samples."""
        with self._lock:
            if n >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-n:]

    def __len__(self) -> int:
        """Number of samples currently in buffer."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clear all samples."""
        with self._lock:
            self._buffer.clear()

    @property
    def duration(self) -> float:
        """Current duration of data in buffer (seconds)."""
        with self._lock:
            if len(self._buffer) < 2:
                return 0.0
            return self._buffer[-1].timestamp - self._buffer[0].timestamp

    @property
    def is_full(self) -> bool:
        """Whether buffer has reached max capacity."""
        with self._lock:
            return len(self._buffer) >= self.max_samples
