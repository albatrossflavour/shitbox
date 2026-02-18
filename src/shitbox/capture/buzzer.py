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
