"""USB speaker with Piper TTS for spoken audio alerts.

Mirrors the buzzer.py architecture: module-level state, graceful degradation
when hardware or piper-tts is absent, and a background daemon thread that
dequeues and plays messages without blocking the caller.

Fixed messages are pre-rendered to WAV at init time and cached in /tmp/shitbox-tts/.
Dynamic messages (waypoints, distances) are synthesised on demand.

The Jieli Technology UACDemoV1.0 USB speaker is detected by parsing
/proc/asound/cards at init time. If absent, all speak_*() functions are
silent no-ops and the caller falls back to buzzer.py tones.
"""

import queue
import threading
import time
from pathlib import Path
from typing import Optional, Union

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

try:
    from piper.voice import PiperVoice

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

_voice: Optional["PiperVoice"] = None  # type: ignore[name-defined]
_alsa_device: Optional[str] = None
_queue: "queue.Queue[Optional[Union[str, Path]]]" = queue.Queue(maxsize=2)
_worker: Optional[threading.Thread] = None
_running = False

# Boot grace period — non-boot alerts are suppressed for this many seconds after startup
BOOT_GRACE_PERIOD_SECONDS = 30.0
_boot_start_time: float = 0.0

# Pre-rendered WAV cache: message text -> Path to cached WAV file
_cache_dir: Optional[Path] = None
_cache: dict[str, Path] = {}

# All fixed messages that can be pre-rendered at init time
_CACHED_MESSAGES: dict[str, str] = {
    "system_ready": "System ready.",
    "crash_recovery": "System recovered after crash.",
    "thermal_warning": "Warning. CPU temperature high.",
    "thermal_critical": "Critical. CPU temperature critical.",
    "thermal_recovered": "CPU temperature recovered.",
    "under_voltage": "Warning. Under voltage detected.",
    "service_crash": "Warning. Service failure detected.",
    "service_recovered": "Service recovered.",
    "health_alarm": "Warning. Health check failing.",
    "i2c_lockup": "Warning. Sensor bus lockup.",
    "ffmpeg_stall": "Warning. Video recording stalled.",
    "capture_failed": "Video save failed.",
    "capture_hard_brake": "Hard braking detected.",
    "capture_big_corner": "Big corner detected.",
    "capture_high_g": "High G force detected.",
    "capture_rough_road": "Rough road detected.",
    "capture_manual": "Manual capture.",
    "capture_end": "Capture complete.",
}


def _set_volume(percent: int) -> None:
    """Set the ALSA playback volume for the USB speaker.

    Uses amixer to avoid the speaker resetting when driven at 100%.

    Args:
        percent: Volume level 0-100.
    """
    import subprocess

    if _alsa_device is None:
        return
    # Extract card number from "plughw:N,0"
    card = _alsa_device.split(":")[1].split(",")[0]
    try:
        subprocess.run(
            ["amixer", "-c", card, "sset", "PCM", f"{percent}%"],
            timeout=5,
            check=False,
            capture_output=True,
        )
        log.info("speaker_volume_set", card=card, percent=percent)
    except Exception as e:
        log.warning("speaker_volume_set_failed", error=str(e))


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


def _warm_cache() -> None:
    """Pre-render all fixed messages to WAV files in the cache directory."""
    import wave

    global _cache_dir
    _cache_dir = Path("/tmp/shitbox-tts")
    _cache_dir.mkdir(parents=True, exist_ok=True)

    rendered = 0
    for key, text in _CACHED_MESSAGES.items():
        wav_path = _cache_dir / f"{key}.wav"
        if wav_path.exists():
            _cache[text] = wav_path
            rendered += 1
            continue
        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                _voice.synthesize_wav(text, wav_file)  # type: ignore[union-attr]
            _cache[text] = wav_path
            rendered += 1
        except Exception as e:
            log.warning("cache_render_failed", key=key, error=str(e))

    log.info("speaker_cache_warmed", count=rendered, total=len(_CACHED_MESSAGES))


def set_boot_start_time(t: float) -> None:
    """Record the engine boot timestamp to anchor the grace period.

    The engine calls this once at startup. Alert functions compare
    time.monotonic() against this value and skip playback for
    BOOT_GRACE_PERIOD_SECONDS after boot.

    Args:
        t: Monotonic timestamp (time.monotonic()) of engine start.
    """
    global _boot_start_time
    _boot_start_time = t


def _should_alert() -> bool:
    """Return False if we are still within the boot grace period."""
    return time.monotonic() - _boot_start_time >= BOOT_GRACE_PERIOD_SECONDS


def init(model_path: str) -> bool:
    """Initialise the speaker: detect USB device, load Piper model, warm cache, start worker.

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

    _set_volume(75)

    try:
        _voice = PiperVoice.load(model_path)  # type: ignore[name-defined]
        log.info("piper_model_loaded", model=model_path, device=_alsa_device)
    except Exception as e:
        log.warning("piper_model_load_failed", error=str(e))
        _voice = None
        return False

    _warm_cache()

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
    """Dequeue messages and play them serially on the worker thread.

    Items are either a Path (cached WAV) or a str (synthesise on demand).
    """
    while _running:
        try:
            item = _queue.get(timeout=1.0)
            if item is None:
                # Sentinel — clean shutdown requested
                break
            if isinstance(item, Path):
                _play_cached(item)
            else:
                _synthesise_and_play(item)
        except queue.Empty:
            continue
        except Exception as e:
            log.warning("speaker_worker_error", error=str(e))


def _play_cached(wav_path: Path) -> None:
    """Play a pre-rendered WAV file via aplay.

    Args:
        wav_path: Path to the cached WAV file.
    """
    import subprocess

    try:
        subprocess.run(
            ["aplay", "-D", str(_alsa_device), "-q", str(wav_path)],
            timeout=10,
            check=False,
        )
    except Exception as e:
        log.warning("speaker_play_error", path=str(wav_path), error=str(e))


def _synthesise_and_play(text: str) -> None:
    """Synthesise text to a temporary WAV file and play it via aplay.

    Used for dynamic messages that can't be pre-cached (waypoints, distances).
    The temp file is always deleted in the finally block, even if aplay fails.

    Args:
        text: The spoken text to synthesise.
    """
    import subprocess
    import tempfile
    import wave

    wav_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        with wave.open(wav_path, "wb") as wav_file:
            _voice.synthesize_wav(text, wav_file)  # type: ignore[union-attr]

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

    If the message matches a pre-cached WAV, enqueues the Path instead
    of the raw text to skip synthesis. Returns immediately if the speaker
    is not initialised (_voice is None).

    Args:
        text: The spoken text to enqueue.
    """
    if _voice is None:
        return
    item: Union[str, Path] = _cache.get(text, text)
    try:
        _queue.put_nowait(item)
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


def speak_health_alarm() -> None:
    """Announce persistent health check failures.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    _enqueue("Warning. Health check failing.")


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


def speak_capture_failed() -> None:
    """Announce that video save verification failed.

    Suppressed during the boot grace period.
    """
    if _voice is None:
        return
    if not _should_alert():
        return
    _enqueue("Video save failed.")


_EVENT_TYPE_MESSAGES: dict[str, str] = {
    "hard_brake": "Hard braking detected.",
    "big_corner": "Big corner detected.",
    "high_g": "High G force detected.",
    "rough_road": "Rough road detected.",
    "manual_capture": "Manual capture.",
}


def speak_capture_start(event_type: str = "") -> None:
    """Announce the specific driving event that triggered video capture.

    Not suppressed by the grace period — captures don't happen at boot.

    Args:
        event_type: The EventType.value string (e.g. "hard_brake").
    """
    text = _EVENT_TYPE_MESSAGES.get(event_type, f"{event_type} detected.")
    _enqueue(text)


def speak_capture_end() -> None:
    """Announce that video capture has finished.

    Not suppressed by the grace period — captures don't happen at boot.
    """
    _enqueue("Capture complete.")


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
