---
phase: 07-self-healing-and-crash-loop-prevention
plan: 01
subsystem: events
tags: [i2c, mpu6050, recovery, escalation, smbus2, gpio, raspberry-pi]

# Dependency graph
requires:
  - phase: 02-watchdog-and-recovery
    provides: "_i2c_bus_reset() bit-bang recovery and I2C_CONSECUTIVE_FAILURE_THRESHOLD"
provides:
  - "I2C_MAX_RESETS=3 and I2C_RESET_BACKOFF_SECONDS=[0,2,5] escalation constants"
  - "Escalating recovery in _sample_loop: backoff + counter before _force_reboot()"
  - "Startup setup() wrapped in escalation loop in start()"
  - "_reset_count reset in stop() for clean restart state"
  - "7 unit tests covering all escalation paths"
affects:
  - phase 07 plans 02 onwards
  - field testing and crash-loop analysis

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Escalating recovery with counter and backoff list — I2C_MAX_RESETS attempts before reboot"
    - "_reset_count persists across lockup cycles, resets to 0 on success or stop()"

key-files:
  created: []
  modified:
    - src/shitbox/events/sampler.py
    - tests/test_i2c_recovery.py

key-decisions:
  - "_reset_count resets in stop() so a service restart gets a fresh escalation counter"
  - "start() escalation calls _i2c_bus_reset() (not setup()) to avoid double setup — _i2c_bus_reset already calls setup() internally"
  - "Pre-existing mypy errors in sampler.py (_bus typed as None rather than Optional[SMBus]) left out of scope — 8 identical errors existed before this plan"

patterns-established:
  - "Pattern: Escalating recovery — I2C_MAX_RESETS attempts with I2C_RESET_BACKOFF_SECONDS[attempt] before _force_reboot()"
  - "Pattern: Startup protection — wrap setup() in same escalation loop as runtime recovery"

requirements-completed:
  - HEAL-02
  - HEAL-03

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 7 Plan 01: Escalating I2C Recovery Summary

**Escalating I2C bus reset with 3-attempt backoff ([0,2,5]s) before forced reboot, eliminating the crash-loop that produced ~7 PIDs in 3 minutes during field testing**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T07:14:46Z
- **Completed:** 2026-02-28T07:17:46Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `I2C_MAX_RESETS=3` and `I2C_RESET_BACKOFF_SECONDS=[0,2,5]` module-level constants
- Modified `_sample_loop` recovery path: applies backoff, increments `_reset_count`, only calls `_force_reboot()` after counter reaches `I2C_MAX_RESETS`
- Wrapped `start()/setup()` in same escalation loop, protecting against startup I2C lockups that were the root cause of the crash-loop field failure
- Reset `_reset_count=0` in `stop()` so restart via engine health check gets fresh escalation state
- Added 7 unit tests (446 total lines): counter increment, reboot gating, backoff delays, success reset, startup protection, startup total failure, stop reset

## Task Commits

Each task was committed atomically:

1. **Task 1: Add escalating I2C recovery to HighRateSampler** - `942f60c` (feat)
2. **Task 2: Add unit tests for I2C escalation paths** - `50fc87e` (test)

## Files Created/Modified

- `src/shitbox/events/sampler.py` - Escalation constants, `_reset_count` attribute, modified `_sample_loop` and `start()`, reset in `stop()`
- `tests/test_i2c_recovery.py` - 7 new escalation tests added; 13 total tests pass

## Decisions Made

- `_reset_count` resets in `stop()` so the engine health check's stop()/start() cycle gives the restarted sampler a clean slate, not inherited failure state from the prior run
- In the `start()` escalation loop, `_i2c_bus_reset()` is called (not `setup()`) because `_i2c_bus_reset()` already calls `setup()` internally — calling `setup()` again would be a double-call on success
- Pre-existing mypy errors (`_bus: None` vs `Optional[SMBus]`) left unchanged — 8 identical errors were present before this plan; fixing them is out of scope

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed line too long (101 chars) in sampler.py constant comment**

- **Found during:** Task 1 (ruff check after initial implementation)
- **Issue:** `I2C_RESET_BACKOFF_SECONDS` comment was 101 characters, exceeding ruff line limit of 100
- **Fix:** Shortened comment from "index = attempt number" to "index = attempt"
- **Files modified:** `src/shitbox/events/sampler.py`
- **Verification:** `ruff check src/shitbox/events/sampler.py` — All checks passed
- **Committed in:** `942f60c` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed unused imports and import sort in test file**

- **Found during:** Task 2 (ruff check after initial test implementation)
- **Issue:** Added `threading`, `time`, `ModuleType`, `call` imports not needed in new tests; import sort violated isort order
- **Fix:** Removed unused imports, ran `ruff --fix` to correct import ordering
- **Files modified:** `tests/test_i2c_recovery.py`
- **Verification:** `ruff check tests/test_i2c_recovery.py` — All checks passed
- **Committed in:** `50fc87e` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — lint correctness issues)
**Impact on plan:** Minor lint fixes only. No functional changes, no scope creep.

## Issues Encountered

None beyond the lint deviations documented above.

## Next Phase Readiness

- I2C escalation is complete and tested; crash-loop root cause addressed
- Phase 7 Plan 02 (speaker watchdog) is already committed on this branch (`e5dbe08`)
- Ready to proceed to Phase 7 Plan 03 or phase verification

## Self-Check: PASSED

- FOUND: `src/shitbox/events/sampler.py`
- FOUND: `tests/test_i2c_recovery.py`
- FOUND: `.planning/phases/07-self-healing-and-crash-loop-prevention/07-01-SUMMARY.md`
- FOUND commit: `942f60c` (feat: escalating I2C recovery)
- FOUND commit: `50fc87e` (test: escalation tests)
- Constants verified: `I2C_MAX_RESETS == 3`, `I2C_RESET_BACKOFF_SECONDS == [0, 2, 5]`
- Tests: 13 passed, 0 failed

---

*Phase: 07-self-healing-and-crash-loop-prevention*
*Completed: 2026-02-28*
