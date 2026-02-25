---
phase: 02-watchdog-and-self-healing
plan: "03"
subsystem: telemetry
tags: [i2c, gpio, mpu6050, smbus2, rpi-gpio, bit-bang, recovery, buzzer, sampler]

# Dependency graph
requires:
  - phase: 02-01
    provides: buzzer alert patterns including beep_i2c_lockup and beep_service_recovered
  - phase: 01-01
    provides: HighRateSampler and ring buffer infrastructure

provides:
  - I2C bus lockup detection after 5 consecutive read failures in HighRateSampler
  - 9-clock SCL bit-bang recovery on GPIO3 with selective pin cleanup
  - MPU6050 reinitialisation after successful bus recovery
  - System reboot via systemctl when bit-bang recovery fails
  - Engine wires buzzer boot start time for grace period suppression
  - Unit tests for all recovery paths with mocked GPIO and smbus2

affects:
  - 02-04
  - any phase extending HighRateSampler or sampler error handling

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "I2C recovery: 9-clock SCL bit-bang → selective GPIO.cleanup([pins]) → 100ms delay → smbus2 reopen → MPU6050 reinit"
    - "Local import pattern: import RPi.GPIO inside method body for graceful degradation"
    - "GPIO mock pattern: sys.modules patch needs rpi_pkg_mock.GPIO = mock_gpio so import RPi.GPIO as GPIO resolves correctly"

key-files:
  created:
    - tests/test_i2c_recovery.py
  modified:
    - src/shitbox/events/sampler.py
    - src/shitbox/events/engine.py

key-decisions:
  - "Import RPi.GPIO inside _i2c_bus_reset() method body (not module level) to preserve graceful degradation on non-Pi hosts"
  - "GPIO.cleanup([SCL_PIN, SDA_PIN]) uses selective pin list — NOT global GPIO.cleanup() — to avoid disrupting other GPIO users (button handler)"
  - "I2C_RECOVERY_DELAY_SECONDS=0.1 gives the kernel I2C driver 100ms to reclaim SDA/SCL after GPIO releases them"
  - "buzzer.set_boot_start_time() called immediately after buzzer.init() in engine.start() so the grace period is anchored to actual engine start time"

patterns-established:
  - "sys.modules GPIO mock: set rpi_pkg_mock.GPIO = mock_gpio so both sys.modules keys are consistent with Python's import machinery"

requirements-completed: [WDOG-04]

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 2 Plan 03: I2C Bus Lockup Recovery Summary

**9-clock SCL bit-bang I2C recovery in HighRateSampler with GPIO3, selective cleanup, MPU6050 reinit, reboot fallback, and buzzer alerting**

## Performance

- **Duration:** ~5 min (execution interrupted by rate limit; actual coding time)
- **Started:** 2026-02-25T21:02:00Z
- **Completed:** 2026-02-25T22:10:16Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- HighRateSampler detects I2C bus lockup after 5 consecutive read failures (~50ms at 100 Hz) and triggers 9-clock bit-bang recovery via GPIO3/GPIO2
- Recovery performs selective `GPIO.cleanup([SCL_PIN, SDA_PIN])` (not global), waits 100ms for the kernel I2C driver to reclaim the pins, reopens smbus2, and calls `setup()` to reinitialise MPU6050 registers
- If recovery fails, `_force_reboot()` calls `sudo systemctl reboot` as last resort; on success buzzer chirps via `beep_service_recovered("i2c")`
- Engine wires `buzzer.set_boot_start_time(time.time())` immediately after `buzzer.init()` so the 30-second grace period is anchored to actual engine start
- 6 unit tests cover all paths: counter mechanics, threshold trigger, GPIO sequence (18+ output calls), selective cleanup, reboot fallback, smbus2 failure

## Task Commits

Each task was committed atomically:

1. **Task 1: Add I2C bus lockup recovery to HighRateSampler** - `d86f89f` (feat)
2. **Task 2: Tests for I2C bus lockup recovery** - `2efe972` (test)

**Plan metadata:** _(final docs commit below)_

## Files Created/Modified

- `src/shitbox/events/sampler.py` - I2C_CONSECUTIVE_FAILURE_THRESHOLD constant, _consecutive_failures counter, _i2c_bus_reset(), _force_reboot(), updated _sample_loop error path
- `src/shitbox/events/engine.py` - Added `buzzer.set_boot_start_time(time.time())` call after `buzzer.init()` in `start()`
- `tests/test_i2c_recovery.py` - 6 unit tests for all I2C recovery code paths, mocked GPIO and smbus2

## Decisions Made

- Import `RPi.GPIO` inside `_i2c_bus_reset()` method body (not module level) so the sampler continues to import cleanly on non-Pi development hosts
- Use `GPIO.cleanup([SCL_PIN, SDA_PIN])` with an explicit pin list instead of global `GPIO.cleanup()` to avoid disrupting the button handler and any other GPIO users in the process
- `I2C_RECOVERY_DELAY_SECONDS = 0.1` — 100ms gives the Linux I2C driver time to reclaim SDA/SCL pins after the bit-bang GPIO release
- `buzzer.set_boot_start_time()` called immediately after `buzzer.init()` (not at a later startup stage) so the grace period timer starts at the right moment

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed RingBuffer fixture using wrong constructor argument**

- **Found during:** Task 2 (Tests for I2C bus lockup recovery)
- **Issue:** Test fixture called `RingBuffer(capacity=100)` but the class signature is `RingBuffer(max_seconds, sample_rate_hz)` — caused `TypeError` on all tests
- **Fix:** Changed to `RingBuffer(max_seconds=1.0, sample_rate_hz=100.0)`
- **Files modified:** `tests/test_i2c_recovery.py`
- **Verification:** All 6 tests pass
- **Committed in:** `2efe972` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed GPIO mock not being bound by `import RPi.GPIO as GPIO`**

- **Found during:** Task 2 (GPIO sequence test)
- **Issue:** `patch.dict(sys.modules, {"RPi": MagicMock(), "RPi.GPIO": mock_gpio})` with an independent `MagicMock()` for `RPi` caused Python's import machinery to bind the `GPIO` attribute from the `RPi` package mock (a fresh `MagicMock`) rather than `mock_gpio` — leaving `mock_gpio.setmode` uncalled
- **Fix:** Created `rpi_pkg_mock = MagicMock(); rpi_pkg_mock.GPIO = mock_gpio` and passed that as the `RPi` entry so both `sys.modules` keys are consistent
- **Files modified:** `tests/test_i2c_recovery.py`
- **Verification:** `mock_gpio.setmode.assert_called_once_with(mock_gpio.BCM)` passes; all 6 tests green
- **Committed in:** `2efe972` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 × Rule 1 bugs)
**Impact on plan:** Both fixes were in the test file, not in production code. No scope creep.

## Issues Encountered

None in production code. Both issues were in the test harness (wrong RingBuffer args and GPIO mock binding), discovered and fixed during Task 2 verification.

## Next Phase Readiness

- I2C self-healing is complete; the sampler will now recover from bus lockups without requiring a manual restart or data loss gap beyond ~50ms
- The engine's `set_boot_start_time` wiring means all buzzer alert functions have a correct grace period anchor from plan 02-03 onwards
- Ready for 02-04 (health monitor integration or next planned phase)

---

*Phase: 02-watchdog-and-self-healing*
*Completed: 2026-02-25*
