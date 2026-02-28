---
phase: 07-self-healing-and-crash-loop-prevention
plan: 02
subsystem: health
tags: [speaker, watchdog, tts, buzzer, health-check, thread-liveness, recovery]

# Dependency graph
requires:
  - phase: 05-audio-alerts-and-tts
    provides: speaker module with _voice, _worker, cleanup(), init() API
  - phase: 07-self-healing-and-crash-loop-prevention
    plan: 01
    provides: _health_check() skeleton with checks 1-5 and recovered[] list
provides:
  - Speaker worker thread liveness check (check 6) in _health_check()
  - TTS and buzzer recovery confirmation after any successful subsystem recovery
affects:
  - phase 07 future plans (health check pattern now covers all subsystems)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Health check pattern: detect dead thread via .is_alive(), cleanup() then init(),
      append to recovered[] on success"
    - "Recovery confirmation: if recovered: buzzer.beep_service_recovered() +
      speaker.speak_service_recovered() at end of _health_check()"
    - "Speaker guard pattern: check _voice is not None AND _worker is not None before
      liveness test to avoid AttributeError and spurious reinit"

key-files:
  created:
    - .planning/phases/07-self-healing-and-crash-loop-prevention/07-02-SUMMARY.md
  modified:
    - src/shitbox/events/engine.py
    - tests/test_speaker_alerts.py

key-decisions:
  - "Speaker reinit only when _voice is not None — avoids attempting reinit when
    speaker was never initialised (e.g. no USB device or Piper unavailable)"
  - "Speaker reinit only when _worker is not None — avoids AttributeError after
    cleanup() zeroed the worker reference"
  - "Always call cleanup() before init() — never call init() without cleanup() first
    (matches speaker.py contract and Pitfall 5 from research)"
  - "Recovery confirmation (TTS + buzzer) fires for ANY recovered subsystem, not just
    speaker, completing HEAL-03 across all subsystem types"

patterns-established:
  - "Speaker watchdog: _voice is not None and _worker is not None and not
    _worker.is_alive() — minimum viable guard set"
  - "Announce recovery: always append to recovered[], then let the shared if recovered:
    block fire the single confirmation"

requirements-completed: [HEAL-01, HEAL-03]

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 7 Plan 02: Speaker Watchdog and Recovery Confirmations Summary

**Speaker worker thread watchdog added to _health_check() with cleanup()+init() reinit, plus
TTS and buzzer recovery confirmation announcements after all subsystem recoveries (HEAL-01 and
HEAL-03).**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T07:15:01Z
- **Completed:** 2026-02-28T07:17:10Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added check 6 to `_health_check()`: detects dead speaker worker thread via `.is_alive()`,
  calls `cleanup()` then `init()` to reinitialise, appends "speaker" to `recovered[]`
  on success
- Added `buzzer.beep_service_recovered("subsystem")` and `speaker.speak_service_recovered()`
  to the shared `if recovered:` block — announces any subsystem recovery (IMU, telemetry,
  video, GPS, or speaker) to the driver
- Added 8 new unit tests covering all watchdog scenarios: dead worker detection, reinit
  success/failure, skip-when-never-initialised, skip-when-worker-none, and both
  announcement checks

## Task Commits

Each task was committed atomically:

1. **Task 1: Add speaker watchdog and recovery confirmations to health check** - `e5dbe08` (feat)
2. **Task 2: Add unit tests for speaker watchdog and recovery announcements** - `c056980` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/shitbox/events/engine.py` — Added speaker worker liveness check (check 6) and
  recovery confirmation calls in `_health_check()`
- `tests/test_speaker_alerts.py` — Added 8 tests for HEAL-01/HEAL-03 scenarios (649 total
  lines, was 407)

## Decisions Made

- Guard pattern uses three conditions: `_voice is not None` AND `_worker is not None` AND
  `not _worker.is_alive()` — all three are necessary to avoid spurious reinit and
  AttributeError edge cases
- Recovery confirmation fires at the shared `if recovered:` block rather than
  per-subsystem, keeping the announcement logic DRY and consistent

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. Pre-existing lint errors in engine.py (lines 397, 871, 872, 900 — E501 and F401)
are out of scope for this plan and logged to deferred items.

## Next Phase Readiness

- Speaker watchdog and recovery confirmations complete — all HEAL-01 and HEAL-03
  requirements satisfied
- Phase 7 health check now covers all six subsystems: IMU, telemetry thread, video ring
  buffer, GPS, disk space, and speaker
- Ready for any Phase 8 work (no blockers from this plan)

---

*Phase: 07-self-healing-and-crash-loop-prevention*
*Completed: 2026-02-28*
