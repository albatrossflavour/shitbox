---
phase: 08-capture-integrity
plan: "02"
subsystem: capture
tags: [video, ffmpeg, ring-buffer, boot-guard, timelapse-watchdog, verification]

requires:
  - phase: 08-01
    provides: beep_capture_failed(), speak_capture_failed(), 10 RED-phase TDD tests

provides:
  - post-save verification in ring_buffer._do_save_event() with driver alert
  - boot save guard in engine._on_event() skipping saves with < 2 segments
  - timelapse gap watchdog in engine._check_timelapse() with ffmpeg recovery

affects:
  - tests/test_capture_integrity.py (all 10 tests now green)

tech-stack:
  added: []
  patterns:
    - "Post-save verification: check output_path exists AND size > 0 after concatenation"
    - "Alert in try/except to ensure callback always fires even if buzzer/speaker unavailable"
    - "Class constant referenced via ClassName.CONST (not self.) so MagicMock(spec=) resolves real value"
    - "Boot guard: < 2 segment threshold (newest segment still being written)"

key-files:
  created: []
  modified:
    - src/shitbox/capture/ring_buffer.py
    - src/shitbox/events/engine.py
    - tests/test_capture_integrity.py

key-decisions:
  - "TIMELAPSE_GAP_FACTOR referenced as UnifiedEngine.TIMELAPSE_GAP_FACTOR (not self.) — MagicMock(spec=UnifiedEngine) does not expose class constants as real values; class reference always resolves correctly"
  - "Alert import inside try/except in _do_save_event — matches Phase 7 pattern, ensures buzzer/speaker failure never prevents callback"
  - "Boot guard returns after event_storage.save_event() — metadata saved even when video skipped"
  - "Gap watchdog uses _last_timelapse_time > 0.0 sentinel to prevent false alarms at boot"

metrics:
  duration: ~3min
  completed: 2026-02-28
  tasks: 3
  files_modified: 3
---

# Phase 8 Plan 02: Capture Integrity Implementation Summary

**Post-save verification, timelapse gap watchdog, and boot save guard implemented in ring_buffer.py and engine.py — all 10 capture integrity tests pass**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T08:04:44Z
- **Completed:** 2026-02-28T08:07:22Z
- **Tasks:** 3
- **Files modified:** 3 (ring_buffer.py, engine.py, test_capture_integrity.py)

## Accomplishments

- Added post-save verification to `_do_save_event()`: checks output path exists with
  non-zero size after `_concatenate_segments()`; on failure logs `video_save_verification_failed`,
  calls `beep_capture_failed()` and `speak_capture_failed()`, passes `None` to callback
- Added `video_save_post_event_empty` warning when post-event segment copy returns empty
  list (diagnostic only, does not affect save flow)
- Added `TIMELAPSE_GAP_FACTOR = 3` class constant to `UnifiedEngine`
- Added boot save guard in `_on_event()`: BOOT events with fewer than 2 buffer segments
  skip `save_event()` and record event metadata only via `event_storage.save_event()`
- Added timelapse gap watchdog in `_check_timelapse()`: fires `timelapse_gap_detected`
  warning after `3 * interval` seconds pass while moving, recovers by restarting ffmpeg
  via `_kill_current()` + `_start_ffmpeg()`, guarded by `_last_timelapse_time > 0.0` sentinel

## Task Commits

Each task was committed atomically:

1. **Task 1: Post-save verification and post-event empty warning** — `3d2f56d` (feat)
2. **Task 2: Boot save guard and timelapse gap watchdog** — `be38a6d` (feat)
3. **Task 3: Full test suite and lint validation** — (no code changes, validation only)

**Plan metadata:** (in final docs commit)

## Files Created/Modified

- `src/shitbox/capture/ring_buffer.py` — Replaced concatenation success/failure block with
  verification that checks `output_path.exists()` and `output_path.stat().st_size > 0`;
  added `video_save_post_event_empty` warning after post-event segment copy
- `src/shitbox/events/engine.py` — Added `TIMELAPSE_GAP_FACTOR = 3`, boot save guard in
  `_on_event()`, and gap watchdog in `_check_timelapse()`
- `tests/test_capture_integrity.py` — Fixed `Event()` constructor call to include required
  `peak_ax`, `peak_ay`, `peak_az` fields (auto-fix for Rule 1 bug)

## Decisions Made

- `TIMELAPSE_GAP_FACTOR` referenced as `UnifiedEngine.TIMELAPSE_GAP_FACTOR` inside the
  method body — `MagicMock(spec=UnifiedEngine)` does not expose class-level constants as
  real numeric values, so `self.TIMELAPSE_GAP_FACTOR` would return a MagicMock and break
  the `>` comparison. Direct class reference always resolves the real integer.
- Alert calls wrapped in `try/except Exception: pass` — ensures buzzer or speaker
  failures (e.g. hardware unavailable) never prevent the callback from firing
- Boot guard calls `self.event_storage.save_event(event)` before returning — boot event
  metadata is always persisted even when video is skipped due to no segments

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed stale Event constructor in test_capture_integrity.py**

- **Found during:** Task 2 — running all 10 tests after engine changes
- **Issue:** `test_boot_save_skipped_no_segments` used `Event(event_type=..., start_time=..., end_time=..., peak_value=0.0)` — missing required positional arguments `peak_ax`, `peak_ay`, `peak_az` added to `Event` dataclass in a previous phase
- **Fix:** Added `peak_ax=0.0, peak_ay=0.0, peak_az=0.0` to the `Event()` constructor call
- **Files modified:** `tests/test_capture_integrity.py`
- **Commit:** `be38a6d`

**2. [Rule 1 - Bug] Used class reference for TIMELAPSE_GAP_FACTOR**

- **Found during:** Task 2 — first test run of timelapse gap tests
- **Issue:** `self.TIMELAPSE_GAP_FACTOR` returns a `MagicMock` in tests using `MagicMock(spec=UnifiedEngine)`, causing `TypeError: '>' not supported between instances of 'float' and 'MagicMock'`
- **Fix:** Changed `self.TIMELAPSE_GAP_FACTOR` to `UnifiedEngine.TIMELAPSE_GAP_FACTOR` in `_check_timelapse()`
- **Files modified:** `src/shitbox/events/engine.py`
- **Commit:** `be38a6d`

## Pre-existing Issues (Out of Scope)

- `tests/test_ffmpeg_stall.py` has 1 pre-existing failure (`test_stall_not_detected_on_activity` asserts `is False` but `_check_stall()` returns `None` on first arm) — not caused by this plan
- `ruff check engine.py` reports 4 pre-existing errors (E501 line-too-long at lines 397/915, F401 unused imports at lines 886/887) — not in sections modified by this plan
- `mypy` reports 10 pre-existing errors in ring_buffer.py and engine.py — none in sections modified by this plan

These are logged to `.planning/phases/08-capture-integrity/deferred-items.md` implicitly via this record.

## Next Phase Readiness

- Phase 8 is complete — all CAPT-01, CAPT-02, CAPT-03 requirements implemented and tested
- Phase 9 (Prometheus label conflict investigation) can proceed

## Self-Check: PASSED

- `08-02-SUMMARY.md` — found
- `src/shitbox/capture/ring_buffer.py` — found
- `src/shitbox/events/engine.py` — found
- Commit `3d2f56d` — found
- Commit `be38a6d` — found
- All 10 capture integrity tests pass

---

*Phase: 08-capture-integrity*
*Completed: 2026-02-28*
