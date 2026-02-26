"""CPU thermal monitoring with hysteresis-based buzzer alerts.

Runs as a daemon thread polling sysfs temperature and vcgencmd every 5 seconds.
Fires audible alerts at configurable warning and critical thresholds, and decodes
the Pi firmware throttle bitmask to detect under-voltage and frequency capping.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from shitbox.capture.buzzer import (
    beep_thermal_critical,
    beep_thermal_recovered,
    beep_thermal_warning,
    beep_under_voltage,
)
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

TEMP_WARNING_C = 70.0
TEMP_CRITICAL_C = 80.0
HYSTERESIS_C = 5.0
POLL_INTERVAL_S = 5.0

# Re-arm thresholds (temperature must drop below these before alert fires again)
_WARN_REARM_C = TEMP_WARNING_C - HYSTERESIS_C   # 65.0 °C
_CRIT_REARM_C = TEMP_CRITICAL_C - HYSTERESIS_C  # 75.0 °C

# ---------------------------------------------------------------------------
# Throttle bitmask flag definitions
# ---------------------------------------------------------------------------

THROTTLE_FLAGS: dict[int, str] = {
    0: "under_voltage",
    1: "freq_capped",
    2: "throttled",
    3: "soft_temp_limit",
}

BOOT_THROTTLE_FLAGS: dict[int, str] = {
    16: "under_voltage_since_boot",
    17: "freq_capped_since_boot",
    18: "throttled_since_boot",
    19: "soft_temp_limit_since_boot",
}

# ---------------------------------------------------------------------------
# Module-level helper functions (instance methods below for mockability)
# ---------------------------------------------------------------------------


def _decode_throttled(value: int) -> dict:
    """Decode a vcgencmd get_throttled bitmask into human-readable flags.

    Args:
        value: Raw integer value from vcgencmd get_throttled.

    Returns:
        Dict with ``"current"`` and ``"since_boot"`` sub-dicts, each mapping
        flag name → bool indicating whether the flag is set.
    """
    current = {name: bool(value & (1 << bit)) for bit, name in THROTTLE_FLAGS.items()}
    since_boot = {name: bool(value & (1 << bit)) for bit, name in BOOT_THROTTLE_FLAGS.items()}
    return {"current": current, "since_boot": since_boot}


# ---------------------------------------------------------------------------
# ThermalMonitorService
# ---------------------------------------------------------------------------


class ThermalMonitorService:
    """Daemon thread that monitors CPU temperature and Pi firmware throttle state.

    - Samples every 5 seconds via sysfs and vcgencmd.
    - Fires buzzer alerts at 70 °C (warning) and 80 °C (critical) with
      5 °C hysteresis before the alert can re-arm.
    - Fires a recovery beep when temperature drops back below the re-arm
      threshold after a warning.
    - Logs throttle state changes (bitmask differs from previous read).
    - Fires beep_under_voltage() when bit 0 of the throttle bitmask is set.
    - Exposes current temperature via thread-safe ``current_temp_celsius`` property.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._current_temp: Optional[float] = None
        # Armed = alert has not yet fired; disarmed = waiting for re-arm threshold
        self._warning_armed = True
        self._critical_armed = True
        self._last_throttled_raw: Optional[int] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def current_temp_celsius(self) -> Optional[float]:
        """Return the most recently sampled CPU temperature, thread-safe."""
        with self._lock:
            return self._current_temp

    def start(self) -> None:
        """Start the thermal monitor daemon thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="thermal-monitor",
            daemon=True,
        )
        self._thread.start()
        log.info("thermal_monitor_started")

    def stop(self) -> None:
        """Stop the thermal monitor daemon thread and wait for it to finish."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=POLL_INTERVAL_S + 1)
        log.info("thermal_monitor_stopped")

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Main polling loop — runs on the daemon thread."""
        while self._running:
            try:
                self._check_thermal()
            except Exception as exc:
                log.error("thermal_monitor_check_error", error=str(exc))
            time.sleep(POLL_INTERVAL_S)

    # ------------------------------------------------------------------
    # Sysfs / vcgencmd helpers (instance methods so tests can patch them)
    # ------------------------------------------------------------------

    def _read_sysfs_temp(self) -> Optional[int]:
        """Read raw millidegree value from sysfs thermal zone.

        Returns:
            Integer millidegrees (e.g. 55000 for 55 °C), or None on failure.
        """
        try:
            raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
            return int(raw)
        except (IOError, ValueError, OSError) as exc:
            log.warning("sysfs_temp_read_error", error=str(exc))
            return None

    def _read_throttled(self) -> Optional[int]:
        """Read throttle bitmask from vcgencmd get_throttled.

        Returns:
            Integer bitmask, or None if vcgencmd is unavailable or the
            output cannot be parsed.
        """
        try:
            result = subprocess.run(
                ["vcgencmd", "get_throttled"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            # Expected output: "throttled=0x0" or "throttled=0x50005"
            output = result.stdout.strip()
            _, _, hex_part = output.partition("=")
            return int(hex_part, 16)
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return None
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Thermal check logic
    # ------------------------------------------------------------------

    def _check_thermal(self) -> None:
        """Read temperature, update shared state, and fire alerts as needed."""
        raw = self._read_sysfs_temp()
        if raw is None:
            return

        temp = raw / 1000.0

        with self._lock:
            self._current_temp = temp

        # Warning threshold
        if temp >= TEMP_WARNING_C and self._warning_armed:
            log.warning(
                "cpu_temp_warning",
                temp_celsius=round(temp, 1),
                threshold=TEMP_WARNING_C,
            )
            beep_thermal_warning()
            self._warning_armed = False

        # Warning recovery (re-arm)
        if temp <= _WARN_REARM_C and not self._warning_armed:
            log.info("cpu_temp_recovered", temp_celsius=round(temp, 1))
            beep_thermal_recovered()
            self._warning_armed = True

        # Critical threshold
        if temp >= TEMP_CRITICAL_C and self._critical_armed:
            log.error(
                "cpu_temp_critical",
                temp_celsius=round(temp, 1),
                threshold=TEMP_CRITICAL_C,
            )
            beep_thermal_critical()
            self._critical_armed = False

        # Critical recovery (silent re-arm only)
        if temp <= _CRIT_REARM_C:
            self._critical_armed = True

        self._check_throttled()

    def _check_throttled(self) -> None:
        """Read and decode throttle bitmask; alert on under-voltage."""
        raw = self._read_throttled()
        if raw is None:
            return

        if raw == self._last_throttled_raw:
            return  # No change — stay silent

        self._last_throttled_raw = raw
        decoded = _decode_throttled(raw)
        log.warning(
            "throttle_state_changed",
            raw_hex=hex(raw),
            current=decoded["current"],
            since_boot=decoded["since_boot"],
        )

        if decoded["current"].get("under_voltage"):
            beep_under_voltage()
