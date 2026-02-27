---
phase: 05-audio-alerts-and-tts
plan: 01
subsystem: audio
tags: [piper-tts, alsa, usb-speaker, tts, queue, threading, graceful-degradation]

requires:
  - phase: 03-thermal-resilience-and-storage-management
    provides: ThermalMonitorService that will be augmented with speaker calls in Plan 02
  - phase: 04-remote-health-and-stage-tracking
    provides: waypoint detection and distance tracking that speak_waypoint_reached/speak_distance_update announce

provides:
  - speaker.py module with 11 speak_*() functions mirroring buzzer.py API
  - SpeakerConfig dataclass in config.py
  - YAML speaker section under capture: in config/config.yaml
  - 15 unit tests covering AUDIO-01 and AUDIO-02 requirements

affects:
  - 05-02 (Plan 02 wires speak_*() calls into engine.py and thermal_monitor.py)

tech-stack:
  added:
    - piper-tts (piper.voice.PiperVoice) — offline neural TTS, graceful ImportError handling
    - aplay (ALSA, subprocess) — WAV playback to USB speaker device
    - tempfile.NamedTemporaryFile — temporary WAV synthesis output
    - queue.Queue(maxsize=2) — non-blocking drop queue for TTS messages
  patterns:
    - Module-level state with graceful degradation (PIPER_AVAILABLE flag, _voice None guard)
    - Daemon worker thread dequeuing and playing messages serially
    - put_nowait() + queue.Full catch for overflow dropping without blocking
    - /proc/asound/cards parsing by name substring (not hard-coded card number)
    - Boot grace period suppression via _boot_start_time + _should_alert()

key-files:
  created:
    - src/shitbox/capture/speaker.py
    - tests/test_speaker_alerts.py
  modified:
    - src/shitbox/utils/config.py
    - config/config.yaml

key-decisions:
  - "speaker.py mirrors buzzer.py module-level API exactly: module-level state, try/except ImportError,
     all functions are no-ops when _voice is None"
  - "_detect_usb_speaker() searches for UACDemo substring (not Jieli substring from research) —
     matches the PLAN.md must_haves specification and avoids false matches"
  - "Queue maxsize=2: one message playing + one queued, third dropped silently at debug log level"
  - "str(_alsa_device) and str(wav_path) used in subprocess args to satisfy mypy Optional[str] typing
     — both are guaranteed non-None when worker is executing"
  - "15 tests created (plan required 14+): extra test_boot_not_suppressed_by_grace verifies speak_boot()
     bypasses grace period check, covering an important correctness edge case"

patterns-established:
  - "Pattern: USB audio device detection via /proc/asound/cards name substring, returning plughw:N,0"
  - "Pattern: Piper TTS synthesise-to-temp-WAV, play via aplay subprocess, always delete in finally"
  - "Pattern: module-level _voice None guard makes speak_*() functions safe no-ops before init()"

requirements-completed:
  - AUDIO-01
  - AUDIO-02

duration: 3min
completed: 2026-02-27
---

# Phase 5 Plan 01: Speaker Module and TTS Foundation Summary

**Piper TTS speaker.py module with USB speaker detection, non-blocking queue worker, 11 speak_*()
functions mirroring buzzer.py, and 15 unit tests covering AUDIO-01 and AUDIO-02 requirements.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-27T03:35:44Z
- **Completed:** 2026-02-27T03:38:29Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created `speaker.py` with `_detect_usb_speaker()`, `init()`, `cleanup()`, worker thread, and 11
  `speak_*()` functions. Graceful degradation when piper-tts is absent or USB speaker not detected.
- Added `SpeakerConfig` dataclass to `config.py` and wired into `CaptureConfig`. Updated
  `config/config.yaml` with speaker section under `capture:`.
- 15 unit tests: 5 for AUDIO-01 (detection, not found, OSError, init fallback, piper unavailable),
  7 for AUDIO-02 (boot clean/crash, thermal warning/critical, noop, queue overflow, grace period),
  2 for boot grace bypass, 2 for AUDIO-03 (waypoint, distance message content). Full suite 99/99.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create speaker.py module and SpeakerConfig** - `bf3895e` (feat)
2. **Task 2: Write unit tests for speaker module** - `10963db` (test)

## Files Created/Modified

- `src/shitbox/capture/speaker.py` — USB TTS speaker module mirroring buzzer.py architecture
- `src/shitbox/utils/config.py` — SpeakerConfig dataclass added; field on CaptureConfig; load_config wired
- `config/config.yaml` — speaker: section added under capture:
- `tests/test_speaker_alerts.py` — 15 unit tests, all hardware mocked, no real hardware required

## Decisions Made

- `_detect_usb_speaker()` uses `"UACDemo"` substring (PLAN.md must_haves spec) — the research
  mentions "Jieli" as an alternative but the plan spec is authoritative.
- `str(_alsa_device)` and `str(wav_path)` casts in subprocess call to satisfy mypy typing on
  `Optional[str]` list items — both guaranteed non-None in worker context.
- 15 tests instead of 14 — added `test_boot_not_suppressed_by_grace` to explicitly verify
  `speak_boot()` bypasses the grace period check (the plan's must_haves requires this).

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- `mypy` reported `Optional[str]` incompatibility for `_alsa_device` in subprocess args list.
  Fixed with `str(_alsa_device)` cast. Pre-existing config.py mypy errors (yaml stubs, Python 3.10
  union syntax) are out of scope and unchanged.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `speaker.py` is complete and independently testable. All 11 `speak_*()` functions exist.
- Plan 02 can wire `speak_*()` calls into `engine.py` and `thermal_monitor.py` immediately.
- Piper model (`en_US-lessac-medium.onnx`) must be downloaded to the Pi before first run —
  operational dependency, not a code dependency.

---

*Phase: 05-audio-alerts-and-tts*
*Completed: 2026-02-27*
