"""Base collector class for all sensors."""

import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Generic, Optional, TypeVar

from shitbox.storage.models import Reading
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Type variable for specific reading types
T = TypeVar("T")


class BaseCollector(ABC, Generic[T]):
    """Abstract base class for sensor data collectors.

    Collectors run in their own thread and call a callback with each reading.
    """

    def __init__(
        self,
        name: str,
        sample_rate_hz: float,
        callback: Optional[Callable[[Reading], None]] = None,
    ):
        """Initialise the collector.

        Args:
            name: Human-readable name for logging.
            sample_rate_hz: How many samples per second to collect.
            callback: Function to call with each reading.
        """
        self.name = name
        self.sample_rate_hz = sample_rate_hz
        self.sample_interval = 1.0 / sample_rate_hz
        self.callback = callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._error_count = 0
        self._max_errors = 10  # Stop after this many consecutive errors
        self._last_reading: Optional[T] = None

    @abstractmethod
    def setup(self) -> None:
        """Initialise the sensor hardware.

        Called once before collection starts. Should raise an exception
        if the sensor cannot be initialised.
        """
        pass

    @abstractmethod
    def read(self) -> Optional[T]:
        """Read a single sample from the sensor.

        Returns:
            Sensor-specific reading object, or None if read failed.
        """
        pass

    @abstractmethod
    def to_reading(self, data: T) -> Reading:
        """Convert sensor-specific data to a generic Reading.

        Args:
            data: Sensor-specific reading.

        Returns:
            Generic Reading object for storage.
        """
        pass

    def cleanup(self) -> None:
        """Clean up sensor resources.

        Called when collection stops. Override if cleanup is needed.
        """
        pass

    def start(self) -> None:
        """Start collecting data in a background thread."""
        if self._running:
            log.warning("collector_already_running", collector=self.name)
            return

        log.info("starting_collector", collector=self.name, rate_hz=self.sample_rate_hz)

        try:
            self.setup()
        except Exception as e:
            log.error("collector_setup_failed", collector=self.name, error=str(e))
            raise

        self._running = True
        self._error_count = 0
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop collecting data."""
        if not self._running:
            return

        log.info("stopping_collector", collector=self.name)
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        self.cleanup()

    def _run_loop(self) -> None:
        """Main collection loop running in background thread."""
        log.info("collector_loop_started", collector=self.name)

        while self._running:
            loop_start = time.monotonic()

            try:
                data = self.read()

                if data is not None:
                    self._last_reading = data
                    self._error_count = 0

                    if self.callback:
                        reading = self.to_reading(data)
                        self.callback(reading)

            except Exception as e:
                self._error_count += 1
                log.error(
                    "collector_read_error",
                    collector=self.name,
                    error=str(e),
                    error_count=self._error_count,
                )

                if self._error_count >= self._max_errors:
                    log.error(
                        "collector_max_errors_reached",
                        collector=self.name,
                        max_errors=self._max_errors,
                    )
                    self._running = False
                    break

            # Sleep for remaining time to maintain sample rate
            elapsed = time.monotonic() - loop_start
            sleep_time = self.sample_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        log.info("collector_loop_stopped", collector=self.name)

    @property
    def is_running(self) -> bool:
        """Check if collector is currently running."""
        return self._running

    @property
    def last_reading(self) -> Optional[T]:
        """Get the most recent reading."""
        return self._last_reading

    @staticmethod
    def now_utc() -> datetime:
        """Get current UTC timestamp."""
        return datetime.now(timezone.utc)
