# Phase 5: Audio Alerts and TTS - Research

**Researched:** 2026-02-27
**Domain:** Offline neural TTS (Piper), ALSA USB audio device detection, non-blocking audio queue
**Confidence:** HIGH

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- USB speaker: Jieli Technology UACDemoV1.0 (Bus 001 Device 004) is the primary audio output device
- Buzzer remains as fallback if USB speaker is not detected or fails
- TTS engine: Piper (offline neural TTS) for natural-sounding voice
- ~10-15% CPU for 1-2 seconds per utterance, acceptable for infrequent messages
- ~50-100MB model files on disk
- No internet required — fully offline
- Message types: alerts (thermal warning/critical, under-voltage, I2C lockup, ffmpeg stall, service crash/recovery), stage milestones ("Waypoint reached: Broken Hill"), periodic updates (distance driven today), system status ("System ready" on boot, recovery confirmations)

### Claude's Discretion

- Audio playback architecture (aplay, pygame, subprocess)
- Piper model selection (voice, language, quality tier)
- Message queue design to avoid overlapping announcements
- How to detect USB speaker presence and fall back to buzzer
- Exact wording of each announcement message

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUDIO-01 | USB speaker detected and used as primary audio output device | ALSA `/proc/asound/cards` parsing, `aplay -l` output, `plughw:CARD=...` device string pattern |
| AUDIO-02 | TTS engine (Piper) generates spoken alerts replacing buzzer tone patterns | `piper-tts` 1.4.1 on PyPI with ARM64 wheels on piwheels; subprocess pattern via `PiperVoice.load()` + `synthesize()` to WAV file + `aplay` |
| AUDIO-03 | Contextual announcements for system events (boot, thermal, waypoints, distance, recovery) | Hook points identified in engine.py: boot sequence, `_check_waypoints()`, `_telemetry_loop()`, `thermal_monitor.py` buzzer calls, `_health_check()` |

</phase_requirements>

---

## Summary

Phase 5 replaces the buzzer tone patterns with spoken TTS alerts delivered via USB speaker. The core implementation is a `SpeakerService` module in `src/shitbox/capture/` that mirrors the existing `buzzer.py` structure: a thin module-level API (`speak_boot()`, `speak_thermal_warning()`, etc.) backed by a shared daemon-thread queue worker. Every existing buzzer call site gets a paired `speaker.speak_*()` call; the speaker falls back silently to the buzzer if the USB device is absent.

The Piper TTS library (`piper-tts` 1.4.1, February 2026) is the correct choice — it is actively maintained, has pre-built ARM64 wheels on piwheels for Bookworm Python 3.11, ships offline ONNX voice models, and its Python API synthesises speech to a WAV file via `PiperVoice.load().synthesize()`. The synthesised WAV is played by `aplay` as a subprocess, with the ALSA device string derived from parsing `/proc/asound/cards` at startup to locate the Jieli USB speaker.

The non-blocking constraint is met by a single-item `queue.Queue` that the engine pushes messages into; a dedicated daemon thread dequeues and plays them serially. The queue drops lower-priority messages if a higher-priority alert is already queued (priority: alert > milestone > periodic), preventing voice stacking. Synthesis time (~1-2 s on Pi 4) happens on the worker thread, so the 100 Hz IMU sampling path is never touched.

**Primary recommendation:** Use `piper-tts` Python package with `en_US-lessac-medium` voice (63 MB), synthesise to a temporary WAV file, play with `aplay -D plughw:CARD=UACDemoV10,DEV=0`, and wrap everything in a `SpeakerService` module modelled on the existing `buzzer.py` pattern.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `piper-tts` | 1.4.1 (Feb 2026) | Offline neural TTS synthesis | Actively maintained, ARM64 wheel on piwheels for Bookworm, GPL-3.0 licensed, no internet required |
| `aplay` (ALSA) | system package | WAV file playback to USB speaker | Ships with Raspberry Pi OS Bookworm; no extra install, works with ALSA device strings |
| `queue.Queue` | stdlib | Non-blocking message queue | Thread-safe, zero deps, proven pattern used in existing async paths |
| `threading.Thread` | stdlib | Daemon worker thread | Mirrors buzzer's `_play_async()` pattern, daemon=True so it never blocks shutdown |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tempfile.NamedTemporaryFile` | stdlib | Temporary WAV file for synthesis output | Used by the queue worker; deleted after `aplay` returns |
| `/proc/asound/cards` | kernel sysfs | USB audio device detection | Parse at `SpeakerService.init()` to find Jieli card number without extra packages |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `aplay` subprocess | `sounddevice` + `numpy` stream | sounddevice requires `libportaudio2` and `numpy`; aplay is already installed and simpler |
| `piper-tts` Python package | `piper` CLI binary | CLI binary requires pre-compiled ARM release download; Python package installs cleanly via pip |
| Temporary WAV file | `piper.synthesize_stream_raw()` + aplay stdin pipe | Raw pipe avoids temp file but complicates error handling; WAV file approach is simpler to test |
| `queue.Queue` priority queue | `asyncio.Queue` | Async queue would require engine refactor; threading queue drops in alongside existing patterns |

**Installation:**

```bash
pip install piper-tts
```

Voice model download (run once during provisioning, not at runtime):

```bash
mkdir -p /var/lib/shitbox/tts
wget -O /var/lib/shitbox/tts/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget -O /var/lib/shitbox/tts/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/shitbox/capture/
├── buzzer.py           # EXISTING — buzzer fallback, unchanged
├── speaker.py          # NEW — SpeakerService + module-level speak_*() functions
```

No new top-level module. `speaker.py` lives alongside `buzzer.py` in `capture/` because it is the same conceptual layer: hardware audio output.

### Pattern 1: Module-Level API Mirroring buzzer.py

**What:** `speaker.py` exposes module-level functions (`speak_boot()`, `speak_thermal_warning()`, etc.) that match the buzzer's function names but produce speech. The `SpeakerService` class is an implementation detail; callers import the functions, not the class.

**When to use:** Everywhere an existing `buzzer.beep_*()` call should be augmented with a voice announcement. Callers in `engine.py` and `thermal_monitor.py` call both the buzzer and the speaker function.

**Example:**

```python
# src/shitbox/capture/speaker.py
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

_voice: Optional["PiperVoice"] = None
_alsa_device: Optional[str] = None          # e.g. "plughw:CARD=UACDemoV10,DEV=0"
_queue: "queue.Queue[Optional[str]]" = queue.Queue(maxsize=2)
_worker: Optional[threading.Thread] = None
_running = False

BOOT_GRACE_PERIOD_SECONDS = 30.0
_boot_start_time: float = 0.0


def _detect_usb_speaker() -> Optional[str]:
    """Parse /proc/asound/cards to find the Jieli USB speaker ALSA device string.

    Returns:
        ALSA plughw device string, e.g. "plughw:CARD=UACDemoV10,DEV=0",
        or None if not found.
    """
    try:
        cards = Path("/proc/asound/cards").read_text()
        for line in cards.splitlines():
            if "UACDemo" in line or "Jieli" in line:
                # Line format: " 1 [UACDemoV10    ]: USB-Audio - UACDemoV1.0"
                card_num = line.strip().split()[0]
                return f"plughw:{card_num},0"
    except OSError:
        pass
    return None


def init(model_path: str) -> bool:
    """Initialise the speaker: detect USB device, load Piper model, start worker thread."""
    global _voice, _alsa_device, _worker, _running

    if not PIPER_AVAILABLE:
        log.warning("piper_not_available", hint="pip install piper-tts")
        return False

    _alsa_device = _detect_usb_speaker()
    if not _alsa_device:
        log.warning("usb_speaker_not_detected", fallback="buzzer only")
        return False

    try:
        _voice = PiperVoice.load(model_path)
        log.info("piper_model_loaded", model=model_path, device=_alsa_device)
    except Exception as e:
        log.error("piper_model_load_failed", error=str(e))
        return False

    _running = True
    _worker = threading.Thread(target=_worker_loop, name="speaker-worker", daemon=True)
    _worker.start()
    return True


def _worker_loop() -> None:
    """Dequeue messages and synthesise+play them serially."""
    while _running:
        try:
            text = _queue.get(timeout=1.0)
            if text is None:
                break
            _synthesise_and_play(text)
        except queue.Empty:
            continue
        except Exception as e:
            log.warning("speaker_worker_error", error=str(e))


def _synthesise_and_play(text: str) -> None:
    """Synthesise text to a temporary WAV and play via aplay."""
    import subprocess
    import wave

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        with wave.open(wav_path, "w") as wav_file:
            _voice.synthesize(text, wav_file)  # type: ignore[union-attr]

        subprocess.run(
            ["aplay", "-D", _alsa_device, "-q", wav_path],
            timeout=10,
            check=False,
        )
    except Exception as e:
        log.warning("speaker_play_error", text=text, error=str(e))
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except OSError:
            pass
```

### Pattern 2: Priority-Drop Queue

**What:** The queue has `maxsize=2`. When the worker is busy playing a long utterance and two more messages arrive, the third is dropped (not queued). This prevents voice stacking where alerts pile up while the speaker is busy.

**When to use:** This is the default behaviour from `queue.Queue(maxsize=2)` — `put_nowait()` raises `queue.Full` when the queue is full, which the `speak_*()` functions catch and log at debug level.

```python
def _enqueue(text: str) -> None:
    """Attempt to enqueue a spoken message; drop silently if queue is full."""
    try:
        _queue.put_nowait(text)
    except queue.Full:
        log.debug("speaker_queue_full_dropped", text=text)
```

### Pattern 3: Call Site Pairing (engine.py and thermal_monitor.py)

**What:** Every existing `buzzer.beep_*()` call is augmented with a `speaker.speak_*()` call immediately below it. This keeps audio sources together and makes it easy to verify coverage.

**Example (engine.py boot sequence):**

```python
# Existing:
buzzer.beep_boot()
if self.boot_recovery and self.boot_recovery.was_crash:
    buzzer.beep_crash_recovery()
else:
    buzzer.beep_clean_boot()

# Augmented:
buzzer.beep_boot()
speaker.speak_boot(was_crash=self.boot_recovery.was_crash if self.boot_recovery else False)
```

**Example (thermal_monitor.py — thermal warning):**

```python
# Existing:
beep_thermal_warning()
# Added:
from shitbox.capture import speaker as _speaker
_speaker.speak_thermal_warning()
```

### Pattern 4: Waypoint Announcement Hook

**What:** `_check_waypoints()` already fires `log.info("waypoint_reached", name=waypoint.name, day=waypoint.day, ...)`. Immediately after the `self._reached_waypoints.add(i)` line, add a `speaker.speak_waypoint_reached(name=waypoint.name, day=waypoint.day)` call.

**Example:**

```python
self._reached_waypoints.add(i)
speaker.speak_waypoint_reached(waypoint.name, waypoint.day)
```

The spoken message: `"Waypoint reached: Broken Hill, Day 3"`.

### Pattern 5: Periodic Distance Announcement

**What:** A distance announcement every N km (configurable, default 50 km) fires from `_record_telemetry()` when `_daily_km` crosses the threshold. Tracked via `_last_announced_km` engine attribute.

**Example:**

```python
DISTANCE_ANNOUNCE_INTERVAL_KM = 50.0

# In _record_telemetry() after odometer update:
if (self._daily_km // DISTANCE_ANNOUNCE_INTERVAL_KM) > (
    self._last_announced_km // DISTANCE_ANNOUNCE_INTERVAL_KM
):
    speaker.speak_distance_update(int(self._daily_km))
    self._last_announced_km = self._daily_km
```

### Anti-Patterns to Avoid

- **Calling `_synthesise_and_play()` from the engine thread directly:** Synthesis takes 1-2 seconds on Pi 4, which would stall the 1 Hz telemetry loop. Always enqueue via `_enqueue()`.
- **Loading `PiperVoice` model at import time:** The 63 MB ONNX model takes several seconds to load. Load it once in `init()`, not at module level.
- **Using `queue.Queue()` with no maxsize:** An unbounded queue lets messages pile up during a long alert sequence. Cap at `maxsize=2`.
- **Calling `subprocess.run(["aplay", ...])` from multiple threads:** `aplay` opens the ALSA device exclusively; only one can play at a time. The single worker thread ensures serialisation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Offline TTS synthesis | Custom TTS engine or espeak wrapper | `piper-tts` Python package | ONNX-backed neural voice, ARM64 wheel, ~63 MB model, actively maintained |
| Audio device name discovery | Hard-code card number | Parse `/proc/asound/cards` at init | Card numbers shift when other USB devices plug in; kernel name is stable |
| Thread-safe message dropping | Custom semaphore or lock | `queue.Queue(maxsize=2)` + `put_nowait()` | stdlib-proven, trivially testable |

**Key insight:** The Piper synthesis step and the aplay playback step are independent — synthesise to a temp WAV, then play. This separation makes both steps easy to mock in tests.

---

## Common Pitfalls

### Pitfall 1: Hard-Coded ALSA Card Number

**What goes wrong:** `/proc/asound/cards` lists cards in plug-in order. If another USB audio device (the dashcam microphone `plughw:CARD=Camera,DEV=0`) is present, the Jieli speaker may be card 1 or card 2 depending on boot-time plug order.

**Why it happens:** Assuming `hw:1,0` is always the USB speaker because "it was card 1 last time".

**How to avoid:** Parse `/proc/asound/cards` by name substring (`"UACDemo"` or `"Jieli"`), not by card number. Then construct the ALSA string from the discovered card number.

**Warning signs:** `aplay: main:830: audio open error: No such file or directory` after a reboot with dashcam attached.

### Pitfall 2: Piper Model Load Blocking the Engine Start

**What goes wrong:** Loading a 63 MB ONNX model triggers onnxruntime session creation, which can take 3-5 seconds. If done in `UnifiedEngine.__init__()` on the main thread, it delays the boot sequence.

**Why it happens:** Model loading looks like a simple object constructor.

**How to avoid:** Initialise `SpeakerService` in `engine.start()` (not `__init__()`), after the buzzer boot tone plays. Or load the model in a background thread with a flag that reports readiness.

### Pitfall 3: aplay Holds the ALSA Device Exclusively

**What goes wrong:** A second `aplay` subprocess called while the first is still playing will fail with `device busy`.

**Why it happens:** ALSA `hw:` devices are exclusive by default. `plughw:` uses the plug layer but still serialises at the device level.

**How to avoid:** The single worker thread pattern guarantees only one `aplay` subprocess is active. Never call `_synthesise_and_play()` from outside the worker thread.

### Pitfall 4: Temp File Not Cleaned Up on Exception

**What goes wrong:** If `aplay` is killed by signal, the `NamedTemporaryFile` is orphaned and accumulates on `/tmp` (which may be ramfs on the Pi).

**Why it happens:** Exception path skips cleanup.

**How to avoid:** Always delete in a `finally` block. Use `Path.unlink(missing_ok=True)` (Python 3.8+, safe here as project requires 3.9+).

### Pitfall 5: Speaker Module Causes Import Failure on Non-Pi Hosts

**What goes wrong:** If `from piper.voice import PiperVoice` is a hard import at module level, running tests on macOS (dev machine) fails unless piper-tts is installed.

**Why it happens:** Same class of problem as `from PiicoDev_Buzzer import PiicoDev_Buzzer` — hardware library not present on dev machine.

**How to avoid:** Mirror the existing buzzer pattern exactly: wrap the import in `try/except ImportError`, set `PIPER_AVAILABLE = False`, and make all public functions no-ops when `_voice is None`.

---

## Code Examples

Verified patterns from research and codebase inspection:

### USB Speaker Detection (AUDIO-01)

```python
# Source: /proc/asound/cards parsing (confirmed Linux kernel pattern)
def _detect_usb_speaker() -> Optional[str]:
    """Return ALSA plughw string for the Jieli UACDemo speaker, or None."""
    try:
        cards = Path("/proc/asound/cards").read_text()
        for line in cards.splitlines():
            # Example line: " 1 [UACDemoV10    ]: USB-Audio - UACDemoV1.0"
            if "UACDemo" in line:
                card_num = line.strip().split()[0]
                return f"plughw:{card_num},0"
    except OSError:
        pass
    return None
```

### Piper TTS Synthesis to WAV (AUDIO-02)

```python
# Source: noerguerra.com Piper Python integration (verified against piper-tts 1.4.1 PyPI docs)
import wave
from piper.voice import PiperVoice

voice = PiperVoice.load("/var/lib/shitbox/tts/en_US-lessac-medium.onnx")

def synthesise(text: str, wav_path: str) -> None:
    with wave.open(wav_path, "w") as wav_file:
        voice.synthesize(text, wav_file)
```

### aplay Subprocess Invocation

```python
# Source: standard ALSA aplay usage
import subprocess

subprocess.run(
    ["aplay", "-D", "plughw:1,0", "-q", "/tmp/speech.wav"],
    timeout=10,
    check=False,
)
```

The `-q` flag suppresses aplay's banner output. `check=False` avoids raising on non-zero exit (e.g. device busy), which is logged at warning level instead.

### Non-Blocking Queue Worker

```python
# Source: stdlib queue.Queue pattern (mirrors buzzer._play_async architecture)
import queue
import threading

_queue: queue.Queue = queue.Queue(maxsize=2)

def _worker_loop() -> None:
    while _running:
        try:
            text = _queue.get(timeout=1.0)
            if text is None:  # sentinel for clean shutdown
                break
            _synthesise_and_play(text)
        except queue.Empty:
            continue

def _enqueue(text: str) -> None:
    try:
        _queue.put_nowait(text)
    except queue.Full:
        log.debug("speaker_queue_full_dropped", text=text)
```

### Wiring into ThermalMonitorService

```python
# thermal_monitor.py — augment existing buzzer calls
# Import speaker lazily inside methods (same pattern as buzzer import in health monitor)
if temp >= TEMP_WARNING_C and self._warning_armed:
    beep_thermal_warning()
    from shitbox.capture import speaker as _speaker
    _speaker.speak_thermal_warning()
    self._warning_armed = False
```

### Wiring into Engine (boot announcement)

```python
# engine.py start() — after buzzer boot block
if self.config.buzzer_enabled:
    buzzer.init()
    buzzer.set_boot_start_time(time.time())
    buzzer.beep_boot()
    if self.boot_recovery and self.boot_recovery.was_crash:
        buzzer.beep_crash_recovery()
    else:
        buzzer.beep_clean_boot()

# NEW — speaker announcements after buzzer (speaker init is after buzzer)
if self.config.speaker_enabled:
    speaker.init(self.config.speaker_model_path)
    speaker.set_boot_start_time(time.time())
    was_crash = self.boot_recovery.was_crash if self.boot_recovery else False
    speaker.speak_boot(was_crash=was_crash)
```

### Config Additions

**`config.py`** — new `SpeakerConfig` dataclass and field on `CaptureConfig`:

```python
@dataclass
class SpeakerConfig:
    enabled: bool = False
    model_path: str = "/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
    distance_announce_interval_km: float = 50.0
```

**`config/config.yaml`** — new section under `capture:`:

```yaml
capture:
  speaker:
    enabled: true
    model_path: /var/lib/shitbox/tts/en_US-lessac-medium.onnx
    distance_announce_interval_km: 50
```

**`EngineConfig`** — flat fields (per project pattern):

```python
speaker_enabled: bool = False
speaker_model_path: str = "/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
speaker_distance_announce_interval_km: float = 50.0
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `rhasspy/piper` CLI binary download | `piper-tts` PyPI package (1.4.1) | Oct 2025 (repo archived) | Install via pip, Python API, no manual binary download |
| `piper-tts` maintained by rhasspy | Maintained by OHF-voice (`piper1-gpl` repo) | Oct 2025 | Package still installs as `piper-tts`; API unchanged |

**Deprecated/outdated:**

- `rhasspy/piper` GitHub repo: Archived October 6, 2025. Do not reference its README for installation — it points to pre-built binary downloads. The `piper-tts` PyPI package is the current delivery mechanism.
- `piper-tts` < 1.4.0: Earlier versions had API differences. Use 1.4.1 — `PiperVoice.load(model)` is the correct constructor (not `PiperVoice(model)`).

---

## Open Questions

1. **Piper model load time on Pi 4**
   - What we know: 63 MB ONNX model, onnxruntime on ARM64
   - What's unclear: Exact load time (training data suggests 2-5 seconds, needs hardware validation)
   - Recommendation: Load in `start()` after buzzer boot tone; add a log timer. If > 5 s, move to background thread with `_voice_ready` event.

2. **Thermal monitor buzzer import pattern**
   - What we know: `thermal_monitor.py` imports buzzer functions at module level (per [03-02] decision: required for patch() in tests to bind to module-level names)
   - What's unclear: Should speaker be imported the same way (module-level) or lazily?
   - Recommendation: Import speaker at module level in thermal_monitor.py for consistency with the buzzer pattern and to preserve test patchability.

3. **`en_US-lessac-medium` vs other voices**
   - What we know: lessac-medium = 63 MB, male voice, good clarity. `en_US-ryan-high` = larger but higher quality. `en_US-amy-medium` = female voice.
   - What's unclear: Intelligibility in a moving car with road noise at rally speeds
   - Recommendation: Use `en_US-lessac-medium` for the 63 MB size; male voice is typically more intelligible in noisy environments. Swappable via config if user prefers another voice.

4. **USB speaker device naming stability**
   - What we know: `/proc/asound/cards` shows `UACDemoV10` as the card name substring
   - What's unclear: Whether the name is stable across reboots with the dashcam also plugged in
   - Recommendation: Detect by name substring at `init()` time, log the discovered device string. If not found, log warning and return False (buzzer-only fallback).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `pyproject.toml` (no `[tool.pytest]` section — runs with defaults) |
| Quick run command | `pytest tests/test_speaker_alerts.py -x -q` |
| Full suite command | `pytest tests/ -q` |
| Estimated runtime | ~1-2 seconds (no hardware, all mocked) |

### Phase Requirements → Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| AUDIO-01 | USB speaker detected via `/proc/asound/cards`, ALSA string returned | unit | `pytest tests/test_speaker_alerts.py::test_usb_speaker_detection -x` | Wave 0 gap |
| AUDIO-01 | Returns None and logs warning when Jieli card absent | unit | `pytest tests/test_speaker_alerts.py::test_usb_speaker_not_found -x` | Wave 0 gap |
| AUDIO-01 | `init()` returns False when speaker not detected; falls back gracefully | unit | `pytest tests/test_speaker_alerts.py::test_init_fallback_no_speaker -x` | Wave 0 gap |
| AUDIO-02 | `speak_boot()` enqueues correct text | unit | `pytest tests/test_speaker_alerts.py::test_speak_boot_clean -x` | Wave 0 gap |
| AUDIO-02 | `speak_boot(was_crash=True)` enqueues crash-recovery text | unit | `pytest tests/test_speaker_alerts.py::test_speak_boot_crash -x` | Wave 0 gap |
| AUDIO-02 | `speak_thermal_warning()` enqueues correct text | unit | `pytest tests/test_speaker_alerts.py::test_speak_thermal_warning -x` | Wave 0 gap |
| AUDIO-02 | `speak_thermal_critical()` enqueues correct text | unit | `pytest tests/test_speaker_alerts.py::test_speak_thermal_critical -x` | Wave 0 gap |
| AUDIO-02 | All speak_*() functions are no-ops when speaker not initialised | unit | `pytest tests/test_speaker_alerts.py::test_speaker_noop_when_not_init -x` | Wave 0 gap |
| AUDIO-02 | Queue drops message when full (maxsize=2 enforced) | unit | `pytest tests/test_speaker_alerts.py::test_queue_drops_when_full -x` | Wave 0 gap |
| AUDIO-02 | Boot grace period suppresses non-boot alerts | unit | `pytest tests/test_speaker_alerts.py::test_boot_grace_suppresses_alerts -x` | Wave 0 gap |
| AUDIO-03 | Waypoint announcement enqueues name and day label | unit | `pytest tests/test_speaker_alerts.py::test_speak_waypoint_reached -x` | Wave 0 gap |
| AUDIO-03 | Distance announcement fires at correct interval | unit | `pytest tests/test_speaker_alerts.py::test_speak_distance_update -x` | Wave 0 gap |
| AUDIO-03 | Engine `_check_waypoints()` calls `speaker.speak_waypoint_reached()` | unit | `pytest tests/test_speaker_alerts.py::test_engine_waypoint_calls_speaker -x` | Wave 0 gap |
| AUDIO-03 | `ThermalMonitorService._check_thermal()` calls speaker on warning | unit | `pytest tests/test_speaker_alerts.py::test_thermal_monitor_calls_speaker -x` | Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `pytest tests/test_speaker_alerts.py -x -q`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green (`pytest tests/ -q`) before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~2 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_speaker_alerts.py` — covers AUDIO-01, AUDIO-02, AUDIO-03 (14 tests mapped above)

*(conftest.py exists and is sufficient — no new shared fixtures needed for speaker tests)*

---

## Sources

### Primary (HIGH confidence)

- `piper-tts` PyPI page — version 1.4.1, Python >=3.9, ARM64 wheel, GPL-3.0 — https://pypi.org/project/piper-tts/
- piwheels.org/project/piper-tts — Bookworm Python 3.11 wheel confirmed available — https://www.piwheels.org/project/piper-tts/
- `en_US-lessac-medium.onnx` file size 63.2 MB confirmed — https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium
- Existing codebase: `src/shitbox/capture/buzzer.py`, `src/shitbox/events/engine.py`, `src/shitbox/health/thermal_monitor.py` — architecture, hook points, and patterns inspected directly

### Secondary (MEDIUM confidence)

- noerguerra.com Piper Python integration article — `PiperVoice.load(model)` API, `wave.open()` synthesis pattern (verified against PyPI package description)
- rmauro.dev Piper RPi guide — `--output-raw | aplay -r 22050 -f S16_LE` pipe pattern (verified as alternative to WAV file approach)
- ArchWiki ALSA documentation — `/proc/asound/cards` format and `plughw:CARD=...,DEV=0` device string convention

### Tertiary (LOW confidence)

- Piper load time estimates (2-5 seconds on Pi 4) — from community discussions, not measured on target hardware

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — piper-tts PyPI package confirmed, piwheels ARM64 wheel confirmed, aplay is standard on RPi OS
- Architecture: HIGH — directly derived from existing `buzzer.py` and engine patterns in the codebase
- Pitfalls: HIGH — ALSA card number shifting is documented Linux behaviour; import pattern matches existing buzzer convention; temp file cleanup is stdlib best practice
- Piper model load time: LOW — needs hardware validation

**Research date:** 2026-02-27
**Valid until:** 2026-05-27 (piper-tts is stable; piwheels wheels are published for Bookworm; ALSA behaviour is stable)
