---
phase: 02-watchdog-and-self-healing
plan: "02"
subsystem: capture
tags: [ffmpeg, stall-detection, mtime, ring-buffer, buzzer, health-monitor]

# Dependency graph
requires:
  - phase: 02-01
    provides: beep_ffmpeg_stall() buzzer alert and buzzer module pattern

provides:
  - Mtime-based stall detection in VideoRingBuffer._check_stall()
  - _reset_stall_state() called on every ffmpeg restart
  - Health monitor wired to kill/restart ffmpeg on detected stall
  - 6 unit tests covering all stall detection paths

affects:
  - 02-03 (I2C recovery — same health-monitor extension pattern)
  - 03-thermal-and-storage (may query is_running state)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mtime+size baseline pattern: arm on first file observation, compare on subsequent checks"
    - "Stall state reset on restart: _reset_stall_state() called at top of _start_ffmpeg()"
    - "Health monitor extension: add detection block before audio-retry block, use continue"

key-files:
  created:
    - tests/test_ffmpeg_stall.py
  modified:
    - src/shitbox/capture/ring_buffer.py

key-decisions:
  - "STALL_TIMEOUT_SECONDS=30 chosen as conservative threshold for 10-second segments — 3 missed segments before alert"
  - "Stall check uses both mtime and size so detection works even when filesystem mtime resolution is low"
  - "_stall_check_armed flag provides startup grace: no stall fires until at least one segment exists and is baselined"
  - "buzzer imported inside _health_monitor stall block to avoid circular import at module level"

patterns-established:
  - "Stall detection pattern: arm-on-first-observation, compare-on-subsequent, timeout-on-unchanged"
  - "Integration test pattern: use sleep side_effect list with sentinel exception to run exactly one health-monitor iteration"

requirements-completed:
  - WDOG-03

# Metrics
duration: 17min
completed: 2026-02-25
---

# Phase 2 Plan 02: ffmpeg Stall Detection Summary

**Mtime+size-based ffmpeg stall detection in VideoRingBuffer health monitor with 30-second timeout, startup grace, and buzzer alert on frozen output**

## Performance

- **Duration:** 17 min
- **Started:** 2026-02-25T09:42:26Z
- **Completed:** 2026-02-25T10:00:41Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `_check_stall()` to `VideoRingBuffer` — detects frozen ffmpeg output via segment mtime+size monitoring with 30-second timeout
- Wired stall detection into `_health_monitor()` — calls `buzzer.beep_ffmpeg_stall()`, kills, and restarts ffmpeg on detection
- Added `_reset_stall_state()` called at top of `_start_ffmpeg()` so the stall timer resets cleanly on every restart
- Created 6 unit tests covering all code paths: activity detection, timeout, startup grace, arming, state reset, and health monitor integration

## Task Commits

Each task was committed atomically:

1. **Task 1: Add mtime-based stall detection to VideoRingBuffer health monitor** - `98b940a` (feat)
2. **Task 2: Tests for ffmpeg stall detection** - `53ceea1` (test)

## Files Created/Modified

- `src/shitbox/capture/ring_buffer.py` — Added `STALL_TIMEOUT_SECONDS`, `_last_segment_mtime`, `_last_segment_size`, `_stall_check_armed`, `_reset_stall_state()`, `_check_stall()`, and stall detection block in `_health_monitor()`
- `tests/test_ffmpeg_stall.py` — 6 unit tests for stall detection logic

## Decisions Made

- `STALL_TIMEOUT_SECONDS=30` chosen as conservative threshold — 3 missed 10-second segments before alerting, avoids false positives on slow hardware
- Stall check uses both `st_mtime` and `st_size` so it detects both new-segment creation (mtime changes) and ongoing writes to the current segment (size changes), improving detection on filesystems with coarse mtime resolution
- `_stall_check_armed` flag provides startup grace: no stall fires until at least one segment has appeared and a baseline has been recorded
- `buzzer` imported inside the stall detection block of `_health_monitor` (lazy import) to avoid a potential circular import at module level

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed integration test tight-loop issue**

- **Found during:** Task 2 (test_health_monitor_restarts_on_stall)
- **Issue:** Patching `time.sleep` with a no-op and using a background stopper thread caused the health monitor loop to spin thousands of iterations before the stopper thread could run, calling the mock beep thousands of times instead of once
- **Fix:** Replaced stopper thread with a `sleep_calls` list `side_effect` that raises `SystemExit` on the second call, cleanly terminating the loop after exactly one iteration
- **Files modified:** tests/test_ffmpeg_stall.py
- **Verification:** `pytest tests/test_ffmpeg_stall.py -x -q` — 6 passed
- **Committed in:** `53ceea1` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test design)
**Impact on plan:** Fix required for test correctness. No scope creep.

## Issues Encountered

None beyond the auto-fixed test design issue above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `VideoRingBuffer` now fully self-healing: process crashes (existing) and frozen output (new) both trigger automatic restart
- `buzzer.beep_ffmpeg_stall()` integrates with the escalation system from 02-01 — repeated stalls within 5 minutes play the pattern twice
- Ready for Phase 2 Plan 03 (I2C bus lockup detection and recovery in `HighRateSampler`)

---
*Phase: 02-watchdog-and-self-healing*
*Completed: 2026-02-25*
