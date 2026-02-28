---
phase: 08-capture-integrity
plan: "01"
subsystem: capture
tags: [video, ffmpeg, buzzer, speaker, tts, tdd, testing]

requires:
  - phase: 07-self-healing
    provides: beep_ffmpeg_stall pattern, speak_ffmpeg_stall pattern, escalation guard pattern

provides:
  - beep_capture_failed() in buzzer.py — double-descending tone alert for save verification failure
  - speak_capture_failed() in speaker.py — TTS announcement of video save failure
  - tests/test_capture_integrity.py — 10 RED-phase test functions covering CAPT-01/02/03

affects:
  - 08-02 (implements ring_buffer.py and engine.py behaviour these tests assert)

tech-stack:
  added: []
  patterns:
    - "beep_capture_failed follows beep_ffmpeg_stall escalation guard pattern (boot-grace + should_escalate)"
    - "speak_capture_failed guards on _voice is None before _should_alert(), matching other speak_* functions"
    - "_make_vrb() factory pattern from test_ffmpeg_stall.py reused for VRB unit tests"
    - "Engine-level tests use MagicMock(spec=UnifiedEngine) with manual attribute injection"

key-files:
  created:
    - tests/test_capture_integrity.py
  modified:
    - src/shitbox/capture/buzzer.py
    - src/shitbox/capture/speaker.py

key-decisions:
  - "beep_capture_failed uses 440→330 Hz descending pair (150ms each) — distinct from stall alert (330 Hz only) and capture-end (880→440)"
  - "speak_capture_failed guards _voice is None first then _should_alert() — matches pattern of all other speak_* functions"
  - "capture_failed message pre-rendered in _CACHED_MESSAGES to avoid on-demand synthesis latency"
  - "RED-phase tests test _do_save_event, _check_timelapse, and _on_event directly to match Plan 02 implementation targets"

patterns-established:
  - "Failure alert functions: _should_alert guard → name string → tones list → escalation check → _play_async"

requirements-completed:
  - CAPT-01
  - CAPT-02
  - CAPT-03

duration: 3min
completed: 2026-02-28
---

# Phase 8 Plan 01: Capture Integrity Test Scaffolds Summary

**beep_capture_failed() + speak_capture_failed() alert functions added, and 10 RED-phase TDD tests created covering post-save verification (CAPT-01), timelapse gap watchdog (CAPT-02), and boot guard with partial saves (CAPT-03)**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T07:55:31Z
- **Completed:** 2026-02-28T07:58:26Z
- **Tasks:** 2
- **Files modified:** 3 (buzzer.py, speaker.py, test_capture_integrity.py)

## Accomplishments

- Added `beep_capture_failed()` to buzzer.py with double-descending tone pattern (440→330 Hz), boot-grace suppression, and escalation guard
- Added `speak_capture_failed()` to speaker.py with TTS message "Video save failed.", voice guard, and grace period suppression
- Added `"capture_failed"` to `_CACHED_MESSAGES` in speaker.py for pre-rendering at init time
- Created `tests/test_capture_integrity.py` with 10 test functions, all importable and syntactically valid

## Task Commits

Each task was committed atomically:

1. **Task 1: Add capture-failed alert functions to buzzer and speaker** - `b167359` (feat)
2. **Task 2: Create test scaffolds for capture integrity** - `1d09e64` (test)

**Plan metadata:** (in final docs commit)

## Files Created/Modified

- `src/shitbox/capture/buzzer.py` — Added `beep_capture_failed()` function after `beep_ffmpeg_stall()`
- `src/shitbox/capture/speaker.py` — Added `speak_capture_failed()` function and cached message entry
- `tests/test_capture_integrity.py` — 10 RED-phase test functions covering all three CAPT requirements

## Decisions Made

- `beep_capture_failed` uses 440→330 Hz descending pair rather than pure 330 Hz (like stall) so the driver can distinguish "capture failed" from "recording stalled" by ear in a noisy car
- `speak_capture_failed` guards on `_voice is None` first (like `_enqueue` does) and then `_should_alert()` — consistent with the guard ordering pattern in all other `speak_*` alert functions
- The "capture_failed" pre-cached message avoids synthesis latency on the failure hot path

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- Ruff found 4 lint errors in the initial test file draft (unused imports `call` and `pytest`, import ordering, unused variable `pre_seg`) — auto-fixed before commit.

## Next Phase Readiness

- Plan 02 can now implement post-save verification in `ring_buffer._do_save_event()` — `beep_capture_failed` and `speak_capture_failed` are available at module level
- Plan 02 can implement the timelapse gap watchdog in `engine._check_timelapse()` — test assertions are written and waiting
- Plan 02 can implement the boot guard in `engine._on_event()` — test for zero-segment skip is written
- All 10 tests will turn green once Plan 02 is complete (the success path test `test_save_verification_success` may already pass depending on implementation)

---

*Phase: 08-capture-integrity*
*Completed: 2026-02-28*
