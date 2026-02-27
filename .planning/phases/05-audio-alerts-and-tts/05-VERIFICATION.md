---
phase: 05-audio-alerts-and-tts
verified: 2026-02-27T04:00:00Z
status: passed
score: 15/15 must-haves verified
re_verification: false
---

# Phase 5: Audio Alerts and TTS Verification Report

**Phase Goal:** USB speaker provides spoken alerts and contextual announcements, replacing buzzer
tone patterns as the primary audio output

**Verified:** 2026-02-27T04:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All must-haves are drawn from PLAN frontmatter across plans 05-01 and 05-02.

#### Plan 05-01 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | USB speaker detected by parsing `/proc/asound/cards` for `UACDemo` substring | VERIFIED | `_detect_usb_speaker()` in `speaker.py` L41-59 parses `/proc/asound/cards`, iterates lines, checks `"UACDemo" in line` |
| 2 | `init()` returns False and logs warning when USB speaker is absent | VERIFIED | `speaker.py` L96-99 calls `_detect_usb_speaker()`, returns False with `log.warning("usb_speaker_not_detected", ...)` on None result |
| 3 | Piper model loads once during `init()`, not at import time or per-utterance | VERIFIED | `speaker.py` L101-107 calls `PiperVoice.load(model_path)` inside `init()` only; import is guarded by `try/except ImportError` at module level |
| 4 | `speak_*()` functions enqueue text without blocking the caller | VERIFIED | `_enqueue()` at L178-192 uses `_queue.put_nowait()` which returns immediately; actual synthesis runs in background `_worker_loop()` thread |
| 5 | Queue drops messages when full (`maxsize=2`) instead of blocking | VERIFIED | `_enqueue()` L189-192 catches `queue.Full` and calls `log.debug()`; `queue.Queue(maxsize=2)` at L32; `test_queue_drops_when_full` passes |
| 6 | All `speak_*()` functions are silent no-ops when speaker is not initialised | VERIFIED | `_enqueue()` L187-188: `if _voice is None: return`; `test_speaker_noop_when_not_init` passes with all 11 functions called on `_voice=None` |
| 7 | Boot grace period suppresses non-boot alerts for 30 seconds after startup | VERIFIED | `BOOT_GRACE_PERIOD_SECONDS = 30.0` at L37; `_should_alert()` L76-78; all 8 non-boot `speak_*()` functions call `if not _should_alert(): return`; `test_boot_grace_suppresses_alerts` passes |
| 8 | `piper-tts` import failure does not crash the module | VERIFIED | L23-28: `try: from piper.voice import PiperVoice; PIPER_AVAILABLE = True` / `except ImportError: PIPER_AVAILABLE = False`; `test_init_piper_not_available` passes |

#### Plan 05-02 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 9 | Boot sequence announces via speaker after buzzer tones | VERIFIED | `engine.py` L1624-1629: speaker init block is placed after the buzzer init block; `speaker.speak_boot(was_crash=was_crash)` called; `test_engine_boot_calls_speaker` passes |
| 10 | Thermal warning and critical thresholds trigger spoken announcements alongside buzzer tones | VERIFIED | `thermal_monitor.py` L241-242: `beep_thermal_warning()` then `speak_thermal_warning()`; L248-249: `beep_thermal_recovered()` then `speak_thermal_recovered()`; L259-260: `beep_thermal_critical()` then `speak_thermal_critical()`; L288-289: `beep_under_voltage()` then `speak_under_voltage()`; `test_thermal_monitor_calls_speaker_on_warning` passes |
| 11 | Waypoint reached triggers spoken announcement with waypoint name and day label | VERIFIED | `engine.py` L1358: `speaker.speak_waypoint_reached(waypoint.name, waypoint.day)` in `_check_waypoints()`; `test_engine_waypoint_calls_speaker` passes with name "Broken Hill" and day 3 |
| 12 | Distance update announces at configurable interval (default 50 km) | VERIFIED | `engine.py` L1254-1261: interval check uses `_daily_km // announce_interval > _last_announced_km // announce_interval`; default 50.0 km from `EngineConfig`; `_last_announced_km` reset at L1479 on day boundary; `test_engine_distance_calls_speaker` passes |
| 13 | Speaker initialises in `engine.start()` after buzzer, controlled by `speaker_enabled` config | VERIFIED | `engine.py` L1624-1629: `if self.config.speaker_enabled:` guard; `speaker.init()` and `speaker.set_boot_start_time()` called; comment "after buzzer" at L1624 |
| 14 | Speaker cleanup runs in `engine.stop()` alongside buzzer cleanup | VERIFIED | `engine.py` L1677-1679: comment "Clean up buzzer and speaker" followed by `speaker.cleanup()`; `test_engine_stop_calls_speaker_cleanup` passes |
| 15 | Audio playback never blocks the engine thread or 100 Hz IMU sampling | VERIFIED | Worker runs in `threading.Thread(daemon=True)` at L110; `_enqueue()` uses `put_nowait()` (non-blocking); synthesis and `aplay` subprocess happen only inside `_worker_loop()` |

**Score:** 15/15 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/capture/speaker.py` | SpeakerService module with `speak_*()` functions mirroring `buzzer.py` | VERIFIED | 316 lines; 11 `speak_*()` functions present; `_detect_usb_speaker()` present; queue worker; graceful degradation |
| `src/shitbox/utils/config.py` | `SpeakerConfig` dataclass | VERIFIED | L220-225: `SpeakerConfig` with `enabled`, `model_path`, `distance_announce_interval_km`; L243: field on `CaptureConfig`; L353: wired into `load_config()` |
| `config/config.yaml` | Speaker YAML configuration section | VERIFIED | L149-152: `speaker:` under `capture:` with `enabled: true`, `model_path`, `distance_announce_interval_km: 50` |
| `tests/test_speaker_alerts.py` | Unit and integration tests; min 100 lines | VERIFIED | 407 lines; 20 tests; all 20 pass in 0.11s |
| `src/shitbox/events/engine.py` | Speaker wiring in `start()`, `stop()`, boot sequence, waypoints, distance | VERIFIED | `speaker.init` at L1626; `speaker.cleanup` at L1679; `speak_waypoint_reached` at L1358; `speak_distance_update` at L1260 |
| `src/shitbox/health/thermal_monitor.py` | Speaker calls alongside buzzer calls for thermal events | VERIFIED | Module-level import with `ImportError` fallback at L24-42; `speak_thermal_warning/critical/recovered` and `speak_under_voltage` paired with every buzzer call |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `speaker.py` | `piper.voice.PiperVoice` | `try/except ImportError` with `PIPER_AVAILABLE` flag | VERIFIED | L23-28: `PIPER_AVAILABLE` set to True/False; `init()` checks `if not PIPER_AVAILABLE` at L92 |
| `speaker.py` | `/proc/asound/cards` | `Path.read_text()` parsing for `UACDemo` substring | VERIFIED | L41-59: `_detect_usb_speaker()` reads `/proc/asound/cards`, searches for `"UACDemo" in line` |
| `engine.py` | `speaker.py` | import and `init`/`speak_*`/`cleanup` calls | VERIFIED | L21: `from shitbox.capture import buzzer, overlay, speaker`; `speaker.init`, `speaker.speak_boot`, `speaker.speak_waypoint_reached`, `speaker.speak_distance_update`, `speaker.cleanup` all present |
| `thermal_monitor.py` | `speaker.py` | module-level import and `speak_thermal_*` calls | VERIFIED | L24-29: module-level `from shitbox.capture.speaker import speak_thermal_critical, speak_thermal_recovered, speak_thermal_warning, speak_under_voltage`; called at L242, L249, L260, L289 |
| `engine.py` | `speaker.py` via `_check_waypoints` | `speak_waypoint_reached` | VERIFIED | L1358: `speaker.speak_waypoint_reached(waypoint.name, waypoint.day)` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AUDIO-01 | 05-01 | USB speaker detected and used as primary audio output device | SATISFIED | `_detect_usb_speaker()` parses `/proc/asound/cards` for `UACDemo`; returns `plughw:N,0`; `init()` returns False (fallback) when not found; 5 detection tests pass |
| AUDIO-02 | 05-01 | TTS engine (Piper) generates spoken alerts replacing buzzer tone patterns | SATISFIED | `PiperVoice.load()` in `init()`; `_synthesise_and_play()` writes WAV via `wave.open()` then plays via `aplay`; non-blocking queue; graceful degradation when piper absent; 10 enqueue/behaviour tests pass |
| AUDIO-03 | 05-02 | Contextual announcements for system events (boot, thermal, waypoints, distance, recovery) | SATISFIED | `speak_boot()` wired in `engine.start()`; `speak_thermal_*` and `speak_under_voltage()` paired in `thermal_monitor.py`; `speak_waypoint_reached()` in `_check_waypoints()`; `speak_distance_update()` in telemetry loop; 5 integration tests pass |

No orphaned requirements found. All three AUDIO requirements mapped to plans and confirmed implemented.

---

### Anti-Patterns Found

None detected. Scanned `speaker.py`, `engine.py` (speaker sections), and `thermal_monitor.py` for:

- TODO/FIXME/PLACEHOLDER comments — none found
- Empty return stubs (`return null`, `return {}`, `return []`) — none in speaker module
- Handler-only stubs (no API call) — not applicable; `speak_*()` functions actively enqueue

---

### Human Verification Required

The following items cannot be verified programmatically and require hardware testing on the Pi:

#### 1. USB Speaker Detection on Hardware

**Test:** Connect the Jieli UACDemoV1.0 USB speaker to the Pi and start the daemon with
`speaker_enabled: true` in `config.yaml`.

**Expected:** Log entry `speaker_initialised` with the correct `plughw:N,0` device string appears.
No `usb_speaker_not_detected` warning.

**Why human:** `/proc/asound/cards` parsing logic is tested with mocked content; real hardware
card numbering must be confirmed on the target device.

#### 2. Spoken Boot Announcement Audibility

**Test:** Boot the Pi with USB speaker connected. Listen for spoken output after buzzer boot tones.

**Expected:** Clear spoken phrase "System ready." follows the buzzer boot sequence within ~2 seconds.

**Why human:** Audio synthesis quality, volume, and timing relative to buzzer tones cannot be
asserted programmatically.

#### 3. Thermal Warning Spoken Announcement

**Test:** Drive CPU temperature above 70 C (e.g. via stress test) and listen for spoken output.

**Expected:** "Warning. CPU temperature high." spoken clearly. Buzzer beep should precede it.

**Why human:** Real thermal threshold crossing requires hardware; audio playback quality requires ears.

#### 4. Waypoint Announcement on Route

**Test:** Configure a waypoint near a known GPS location and drive through it.

**Expected:** "Waypoint reached. [name]. Day [N]." spoken within 2-3 seconds of crossing threshold.

**Why human:** GPS triggering and audio synchronisation cannot be simulated without hardware.

#### 5. Distance Announcement at 50 km Interval

**Test:** Drive 50+ km with USB speaker connected.

**Expected:** Spoken "[N] kilometres driven today." when crossing each 50 km threshold.

**Why human:** Requires real GPS data accumulation over distance.

---

### Test Results Summary

| Suite | Tests | Passed | Failed |
|-------|-------|--------|--------|
| `tests/test_speaker_alerts.py` (unit + integration) | 20 | 20 | 0 |
| Full test suite (`tests/`) | 104 | 104 | 0 |

No regressions introduced. 20 phase tests pass in 0.11s. Full 104-test suite passes in 0.65s.

---

### Commit Verification

All four phase commits confirmed present in repository history:

| Commit | Description |
|--------|-------------|
| `bf3895e` | feat(05-01): add speaker.py module with Piper TTS and SpeakerConfig |
| `10963db` | test(05-01): add 15 unit tests for speaker module covering AUDIO-01 and AUDIO-02 |
| `18c599e` | feat(05-02): wire speaker into engine.py and thermal_monitor.py |
| `febd5fd` | feat(05-02): add integration tests for speaker wiring (AUDIO-03) |

---

_Verified: 2026-02-27T04:00:00Z_
_Verifier: Claude (gsd-verifier)_
