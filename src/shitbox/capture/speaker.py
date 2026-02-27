"""USB speaker with Piper TTS for spoken audio alerts.

Mirrors the buzzer.py architecture: module-level state, graceful degradation
when hardware or piper-tts is absent, and a background daemon thread that
dequeues and plays messages without blocking the caller.

The Jieli Technology UACDemoV1.0 USB speaker is detected by parsing
/proc/asound/cards at init time. If absent, all speak_*() functions are
silent no-ops and the caller falls back to buzzer.py tones.
"""

import queue
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

try:
    from piper.voice import PiperVoice

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

_voice: Optional["PiperVoice"] = None  # type: ignore[name-defined]
_alsa_device: Optional[str] = None
_queue: "queue.Queue[Optional[str]]" = queue.Queue(maxsize=2)
_worker: Optional[threading.Thread] = None
_running = False

# Boot grace period — non-boot alerts are suppressed for this many seconds after startup
BOOT_GRACE_PERIOD_SECONDS = 30.0
_boot_start_time: float = 0.0


def _detect_usb_speaker() -> Optional[str]:
    """Parse /proc/asound/cards to find the Jieli UACDemo USB speaker.

    Searches for a line containing the "UACDemo" substring and extracts
    the ALSA card number to build the plughw device string.

    Returns:
        ALSA plughw device string (e.g. "plughw:1,0") or None if not found.
    """
    try:
        cards = Path("/proc/asound/cards").read_text()
        for line in cards.splitlines():
            if "UACDemo" in line:
                # Line format: " 1 [UACDemoV10    ]: USB-Audio - UACDemoV1.0"
                card_num = line.strip().split()[0]
                return f"plughw:{card_num},0"
    except OSError:
        pass
    return None


def set_boot_start_time(t: float) -> None:
    """Record the engine boot timestamp to anchor the grace period.

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


def init(model_path: str) -> bool:
    """Initialise the speaker: detect USB device, load Piper model, start worker thread.

    Args:
        model_path: Path to the Piper ONNX voice model file.

    Returns:
        True if the speaker was successfully initialised.
    """
    global _voice, _alsa_device, _worker, _running

    if not PIPER_AVAILABLE:
        log.warning("piper_not_available", hint="pip install piper-tts")
        return False

    _alsa_device = _detect_usb_speaker()
    if not _alsa_device:
        log.warning("usb_speaker_not_detected", fallback="buzzer only")
        return False

    try:
        _voice = PiperVoice.load(model_path)  # type: ignore[name-defined]
        log.info("piper_model_loaded", model=model_path, device=_alsa_device)
    except Exception as e:
        log.warning("piper_model_load_failed", error=str(e))
        _voice = None
        return False

    _running = True
    _worker = threading.Thread(target=_worker_loop, name="speaker-worker", daemon=True)
    _worker.start()
    log.info("speaker_initialised", device=_alsa_device)
    return True


def cleanup() -> None:
    """Stop the worker thread and release resources."""
    global _running, _worker, _voice
    _running = False
    # Send None sentinel to unblock the worker's queue.get()
    try:
        _queue.put_nowait(None)
    except queue.Full:
        pass
    if _worker is not None and _worker.is_alive():
        _worker.join(timeout=5.0)
    _worker = None
    _voice = None


def _worker_loop() -> None:
    """Dequeue messages and synthesise+play them serially on the worker thread."""
    while _running:
        try:
            text = _queue.get(timeout=1.0)
            if text is None:
                # Sentinel — clean shutdown requested
                break
            _synthesise_and_play(text)
        except queue.Empty:
            continue
        except Exception as e:
            log.warning("speaker_worker_error", error=str(e))


def _synthesise_and_play(text: str) -> None:
    """Synthesise text to a temporary WAV file and play it via aplay.

    The temp file is always deleted in the finally block, even if aplay fails.

    Args:
        text: The spoken text to synthesise.
    """
    import subprocess
    import wave

    wav_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        with wave.open(wav_path, "w") as wav_file:
            _voice.synthesize(text, wav_file)  # type: ignore[union-attr]

        # _alsa_device and wav_path are always set when the worker is running
        subprocess.run(
            ["aplay", "-D", str(_alsa_device), "-q", str(wav_path)],
            timeout=10,
            check=False,
        )
    except Exception as e:
        log.warning("speaker_play_error", text=text, error=str(e))
    finally:
        if wav_path is not None:
            Path(wav_path).unlink(missing_ok=True)


def _enqueue(text: str) -> None:
    """Attempt to enqueue a spoken message; drop silently if queue is full.

    Returns immediately if the speaker is not initialised (_voice is None),
    making all speak_*() callers safe no-ops before init() succeeds.

    Args:
        text: The spoken text to enqueue.
    """
    if _voice is None:
        return
    try:
        _queue.put_nowait(text)
    except queue.Full:
        log.debug("speaker_queue_full_dropped", text=text)


# ---------------------------------------------------------------------------
# speak_*() functions — public API mirroring buzzer.beep_*() names
# ---------------------------------------------------------------------------


def speak_boot(was_crash: bool = False) -> None:
    """Announce system readiness after boot.

    Boot messages bypass the grace period check — they are always delivered.

    Args:
        was_crash: True if the previous shutdown was an unclean crash.
    """
    if was_crash:
        _enqueue("System recovered after crash.")
    else:
        _enqueue("System ready.")


def speak_thermal_warning() -> None:
    """Announce CPU temperature at warning threshold (70 C).

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Warning. CPU temperature high.")


def speak_thermal_critical() -> None:
    """Announce CPU temperature at critical threshold (80 C).

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Critical. CPU temperature critical.")


def speak_thermal_recovered() -> None:
    """Announce CPU temperature has recovered below warning threshold.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("CPU temperature recovered.")


def speak_under_voltage() -> None:
    """Announce an under-voltage condition detected by the kernel.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Warning. Under voltage detected.")


def speak_service_crash() -> None:
    """Announce that a monitored service process has crashed.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Warning. Service failure detected.")


def speak_service_recovered() -> None:
    """Announce that a monitored service has recovered.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Service recovered.")


def speak_i2c_lockup() -> None:
    """Announce that the I2C sensor bus has locked up.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Warning. Sensor bus lockup.")


def speak_ffmpeg_stall() -> None:
    """Announce that video recording has stalled.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Warning. Video recording stalled.")


def speak_waypoint_reached(name: str, day: int) -> None:
    """Announce that a rally waypoint has been reached.

    Not suppressed by the grace period — waypoint announcements are
    informational and are never triggered at boot time.

    Args:
        name: Human-readable waypoint name (e.g. "Broken Hill").
        day: Rally day number (e.g. 3).
    """
    _enqueue(f"Waypoint reached. {name}. Day {day}.")


def speak_distance_update(km: int) -> None:
    """Announce the distance driven today.

    Not suppressed by the grace period — distance announcements are
    informational and are never triggered at boot time.

    Args:
        km: Kilometres driven today (integer).
    """
    _enqueue(f"{km} kilometres driven today.")
