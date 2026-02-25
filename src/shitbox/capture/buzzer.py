"""PiicoDev buzzer for audible capture feedback.

Thin wrapper around PiicoDev_Buzzer with graceful degradation
if the hardware is not available (same pattern as button.py).
"""

import threading
import time
from typing import Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

try:
    from PiicoDev_Buzzer import PiicoDev_Buzzer

    BUZZER_AVAILABLE = True
except ImportError:
    BUZZER_AVAILABLE = False

_buzzer: Optional["PiicoDev_Buzzer"] = None  # type: ignore[name-defined]

# Boot grace period — alerts are suppressed for this many seconds after startup
BOOT_GRACE_PERIOD_SECONDS = 30.0

_boot_start_time: float = 0.0


class BuzzerAlertState:
    """Tracks per-alert-type last-fired times to detect escalation.

    When the same failure recurs within ESCALATION_WINDOW_SECONDS the
    alert should be played twice (louder pattern via repetition) to draw
    the driver's attention to a repeating fault.
    """

    ESCALATION_WINDOW_SECONDS = 300  # 5 minutes

    def __init__(self) -> None:
        self._last_alerts: dict[str, float] = {}

    def should_escalate(self, alert_type: str) -> bool:
        """Return True if the same alert fired within the escalation window.

        Always updates the last-fired timestamp for alert_type.

        Args:
            alert_type: Stable string identifier for the alert (e.g. "buzzer-service-crash").

        Returns:
            True if this alert_type was seen within ESCALATION_WINDOW_SECONDS.
        """
        now = time.time()
        last = self._last_alerts.get(alert_type)
        self._last_alerts[alert_type] = now
        if last is None:
            return False
        return (now - last) < self.ESCALATION_WINDOW_SECONDS

    def reset(self, alert_type: str) -> None:
        """Remove the last-fired entry for alert_type.

        Call this when a recovery alert fires so the failure escalation
        counter is cleared.

        Args:
            alert_type: The alert identifier to clear.
        """
        self._last_alerts.pop(alert_type, None)


_alert_state = BuzzerAlertState()


def set_boot_start_time(t: float) -> None:
    """Record the engine boot timestamp so alerts can suppress during grace period.

    The engine calls this once at startup. Alert functions compare
    time.time() against this value and skip playback for
    BOOT_GRACE_PERIOD_SECONDS after boot.

    Args:
        t: Unix timestamp (time.time()) of engine start.
    """
    global _boot_start_time
    _boot_start_time = t


def _should_alert() -> bool:
    """Return False if we are still within the boot grace period."""
    return time.time() - _boot_start_time >= BOOT_GRACE_PERIOD_SECONDS


def init() -> bool:
    """Initialise the PiicoDev buzzer.

    Returns:
        True if buzzer was initialised successfully.
    """
    global _buzzer

    if not BUZZER_AVAILABLE:
        log.warning("piicodev_buzzer_not_available", hint="pip install piicodev")
        return False

    try:
        _buzzer = PiicoDev_Buzzer()
        log.info("buzzer_initialised")
        return True
    except Exception as e:
        log.warning("buzzer_init_failed", error=str(e))
        _buzzer = None
        return False


def cleanup() -> None:
    """Clean up buzzer resources (no-op for I2C)."""
    global _buzzer
    _buzzer = None


def _play(tones: list[tuple[int, int]]) -> None:
    """Play a sequence of (freq_hz, duration_ms) tones.

    Runs in the calling thread — callers should use _play_async.
    """
    if _buzzer is None:
        return

    for freq, duration_ms in tones:
        try:
            _buzzer.tone(freq, duration_ms)
            time.sleep(duration_ms / 1000.0)
        except Exception as e:
            log.warning("buzzer_tone_error", freq=freq, error=str(e))
            return


def _play_async(tones: list[tuple[int, int]], name: str = "buzzer") -> None:
    """Fire tones in a background thread so the caller is never blocked."""
    if _buzzer is None:
        return

    thread = threading.Thread(target=_play, args=(tones,), daemon=True, name=name)
    thread.start()


def beep_capture_start() -> None:
    """Short rising pair: 440 Hz 150 ms, 880 Hz 150 ms."""
    _play_async([(440, 150), (880, 150)], name="buzzer-capture-start")


def beep_capture_end() -> None:
    """Short descending pair: 880 Hz 150 ms, 440 Hz 150 ms."""
    _play_async([(880, 150), (440, 150)], name="buzzer-capture-end")


def beep_boot() -> None:
    """Three quick ascending tones: 440/100, 660/100, 880/200."""
    _play_async([(440, 100), (660, 100), (880, 200)], name="buzzer-boot")


def beep_alarm() -> None:
    """Four low 220 Hz tones (300 ms each) — distinct from higher-pitched beeps."""
    _play_async([(220, 300), (220, 300), (220, 300), (220, 300)], name="buzzer-alarm")


def beep_clean_boot() -> None:
    """Single short tone: clean boot confirmed."""
    _play_async([(880, 200)], name="buzzer-clean-boot")


def beep_crash_recovery() -> None:
    """Double beep: crash was detected, recovery ran."""
    _play_async([(880, 200), (880, 200)], name="buzzer-crash-recovery")


# ---------------------------------------------------------------------------
# Failure alert functions — 330 Hz low warning tone, distinct from boot/capture
# ---------------------------------------------------------------------------


def beep_service_crash() -> None:
    """One long low tone: service process crashed.

    Pattern: [(330, 800)]. Escalates (plays twice) if same fault fired
    within the last 5 minutes. Suppressed during boot grace period.
    """
    if not _should_alert():
        return
    name = "buzzer-service-crash"
    tones: list[tuple[int, int]] = [(330, 800)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_i2c_lockup() -> None:
    """Three short low tones: I2C bus has locked up.

    Pattern: [(330, 200), (330, 200), (330, 200)]. Escalates (plays twice)
    if same fault fired within the last 5 minutes. Suppressed during boot
    grace period.
    """
    if not _should_alert():
        return
    name = "buzzer-i2c-lockup"
    tones: list[tuple[int, int]] = [(330, 200), (330, 200), (330, 200)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_watchdog_miss() -> None:
    """Two long low tones: watchdog keepalive was missed.

    Pattern: [(330, 600), (330, 600)]. Escalates (plays twice) if same
    fault fired within the last 5 minutes. Suppressed during boot grace
    period.
    """
    if not _should_alert():
        return
    name = "buzzer-watchdog-miss"
    tones: list[tuple[int, int]] = [(330, 600), (330, 600)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_ffmpeg_stall() -> None:
    """Two short + one long low tones: ffmpeg recording has stalled.

    Pattern: [(330, 200), (330, 200), (330, 600)]. Escalates (plays twice)
    if same fault fired within the last 5 minutes. Suppressed during boot
    grace period.
    """
    if not _should_alert():
        return
    name = "buzzer-ffmpeg-stall"
    tones: list[tuple[int, int]] = [(330, 200), (330, 200), (330, 600)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_service_recovered(recovered_service: str = "unknown") -> None:
    """Single short high chirp: service has recovered.

    Pattern: [(880, 150)]. Clears the escalation counter for
    recovered_service so the next failure starts from scratch.
    Suppressed during boot grace period.

    Args:
        recovered_service: Name of the service that recovered (used to
            clear its escalation state).
    """
    if not _should_alert():
        return
    _alert_state.reset(recovered_service)
    _play_async([(880, 150)], name="buzzer-service-recovered")
