---
phase: 05-audio-alerts-and-tts
plan: 02
subsystem: audio
tags: [tts, speaker, piper, thermal, engine, waypoints, distance]

# Dependency graph
requires:
  - phase: 05-01
    provides: speaker.py module with Piper TTS API (init, speak_*, cleanup)
  - phase: 03-thermal-resilience-and-storage-management
    provides: ThermalMonitorService with beep_* hooks
  - phase: 04-remote-health-and-stage-tracking
    provides: waypoint detection and distance tracking in engine.py
provides:
  - Speaker wired into UnifiedEngine start()/stop() lifecycle
  - Boot spoken announcement (clean boot or crash recovery) after buzzer tones
  - Waypoint spoken announcement with name and day label via speak_waypoint_reached()
  - Distance spoken announcement at configurable interval (default 50 km)
  - Thermal spoken announcements alongside buzzer tones in ThermalMonitorService
  - 5 integration tests verifying all wiring points
affects:
  - future phases using engine or thermal monitor hook points

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Speaker calls placed immediately after each corresponding buzzer call
    - Module-level speaker imports in thermal_monitor.py with ImportError fallback to no-ops
    - _last_announced_km float state for distance threshold tracking (no DB persistence)
    - Speaker config flat fields on EngineConfig wired from CaptureConfig.speaker

key-files:
  created: []
  modified:
    - src/shitbox/events/engine.py
    - src/shitbox/health/thermal_monitor.py
    - tests/test_speaker_alerts.py

key-decisions:
  - "Speaker import is module-level in engine.py (from shitbox.capture import buzzer, overlay, speaker)"
  - "Speaker init called after buzzer in start() so boot tones precede the spoken announcement"
  - "speak_under_voltage() called after beep_under_voltage() in _check_throttled()"
  - "_last_announced_km reset on AEST day boundary alongside _daily_km — no DB persistence needed"
  - "EngineConfig speaker fields wired directly from config.capture.speaker (SpeakerConfig already existed)"

patterns-established:
  - "Paired buzzer+speaker calls: beep_X() then speak_X() — speaker is graceful no-op when uninitialised"
  - "ImportError fallback no-ops in thermal_monitor.py preserve graceful degradation on non-Pi hosts"

requirements-completed:
  - AUDIO-03

# Metrics
duration: 3min
completed: 2026-02-27
---

# Phase 5 Plan 02: Speaker Wiring Summary

**Engine and thermal monitor wired with Piper TTS spoken announcements for boot, crash recovery, waypoints, distance milestones, and all thermal alert events alongside existing buzzer tones**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-27T03:41:32Z
- **Completed:** 2026-02-27T03:44:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Wired `speaker.init()`, `speaker.set_boot_start_time()`, and `speaker.speak_boot()` into `engine.start()` after the buzzer block; `speaker.cleanup()` into `engine.stop()`
- Added `speak_waypoint_reached(name, day)` call in `_check_waypoints()` and distance announcement logic with `_last_announced_km` state tracking
- Added `speak_thermal_warning/critical/recovered/under_voltage` calls alongside every corresponding `beep_*` call in `thermal_monitor.py` with module-level imports and ImportError fallback
- 20 total tests pass (15 unit from Plan 01 + 5 new integration tests covering all wiring points)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire speaker into engine.py and thermal_monitor.py** - `18c599e` (feat)
2. **Task 2: Add integration tests for speaker wiring** - `febd5fd` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified

- `src/shitbox/events/engine.py` - Added speaker import, EngineConfig fields, init/cleanup in start/stop, waypoint and distance announcements
- `src/shitbox/health/thermal_monitor.py` - Added module-level speaker imports with ImportError fallback; speak_* calls alongside beep_* calls
- `tests/test_speaker_alerts.py` - Added 5 integration wiring tests (AUDIO-03)

## Decisions Made

- Speaker import at module level in `engine.py` alongside `buzzer` and `overlay` (consistent with project pattern)
- Speaker init placed after buzzer in `start()` so the buzzer boot tones always precede the spoken announcement
- `_last_announced_km` is not persisted to the database — resetting on reboot is acceptable for distance announcement tracking (the announced threshold resets cleanly)
- `speak_under_voltage()` wired in `_check_throttled()` after `beep_under_voltage()` — same pattern as thermal alert wiring
- `EngineConfig` speaker fields wire directly from `config.capture.speaker` (SpeakerConfig dataclass was already created in Phase 05-01)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

Pre-existing ruff (E501) and mypy errors in `engine.py` lines 397, 667, 707, 869-870, 871, 898, 996, 1184, 1518 were noted and left out of scope per deviation rules. None were introduced by these changes.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- AUDIO-03 (contextual announcements) complete — Phase 5 is now done
- All hardware-level audio (buzzer + TTS speaker) wired at all alert hook points
- Full rally readiness: boot, crash recovery, waypoints, distance milestones, thermal events all produce spoken announcements when USB speaker is present

---

*Phase: 05-audio-alerts-and-tts*
*Completed: 2026-02-27*
