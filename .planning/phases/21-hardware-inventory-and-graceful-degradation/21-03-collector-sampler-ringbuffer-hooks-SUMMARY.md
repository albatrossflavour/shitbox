---
phase: 21
plan: 03
subsystem: hardware
tags: [hardware-inventory, graceful-degradation, collectors, sampler, ring-buffer, tdd]
dependency_graph:
  requires:
    - src/shitbox/hardware/state.py (Plan 21-01)
  provides:
    - src/shitbox/collectors/base.py (role hook + _report_present/_report_missing)
    - src/shitbox/collectors/environment.py (single-attempt setup, role propagated)
    - src/shitbox/events/sampler.py (3 observational hw_state calls)
    - src/shitbox/capture/ring_buffer.py (role kwarg + 3 observational hw_state calls)
  affects:
    - Plan 21-02 (supervisor reads state written by these hooks)
    - Plan 21-05 (engine passes role= kwargs to collectors/sampler/ring_buffer)
tech_stack:
  added: []
  patterns:
    - Local import inside helper to avoid circular dependency (hw_state in base.py)
    - Observational hook pattern (pure additions at existing log sites, zero logic change)
    - TDD RED/GREEN cycle per task
key_files:
  modified:
    - src/shitbox/collectors/base.py
    - src/shitbox/collectors/environment.py
    - src/shitbox/events/sampler.py
    - src/shitbox/capture/ring_buffer.py
    - tests/test_i2c_recovery.py
    - tests/test_ffmpeg_stall.py
  created:
    - tests/collectors/conftest.py
    - tests/collectors/test_base_hardware_hook.py
    - tests/collectors/test_environment_simplified_retry.py
decisions:
  - "Local import of hw_state inside _report_present/_report_missing avoids circular import at collector import time (base.py imports hw_state; hw_state imports nothing from collectors)"
  - "_make_vrb factory in test_ffmpeg_stall.py updated to set role='camera_front' so existing health monitor tests don't break when hw_state.report_degraded(self.role) is called"
  - "test_max_errors_safety_valve_unchanged patches shitbox.collectors.base.time rather than time.sleep globally, then joins the thread — avoids the poll-loop/sleep interaction problem"
metrics:
  duration: "7m"
  completed_date: "2026-04-21"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 6
---

# Phase 21 Plan 03: Collector, Sampler, Ring Buffer Hooks Summary

**One-liner:** Observational hw_state reporting wired into BaseCollector (template method), EnvironmentCollector (single-attempt setup replacing 5x1s retry loop), HighRateSampler (3 hook calls at existing log sites), and VideoRingBuffer (role kwarg + 3 hook calls).

## What Was Built

### BaseCollector (`src/shitbox/collectors/base.py`)

- `role: Optional[str] = None` kwarg added to `__init__` after `callback`. Stored as `self.role`.
- Two private helpers added above `_run_loop`:
  - `_report_present()` — no-op if `self.role is None`; calls `hw_state.report_present(self.role)` via local import (avoids circular import at module load time).
  - `_report_missing()` — same pattern for `hw_state.report_missing`.
- `_run_loop` success branch: `self._report_present()` called after `self._error_count = 0` (line 149).
- `_run_loop` except branch: `self._report_missing()` called as first statement, before `self._error_count += 1` (line 156).
- `start()` setup-failure branch: `self._report_missing()` called before `raise` (line 103).
- `_max_errors = 10` safety valve unchanged.

### EnvironmentCollector (`src/shitbox/collectors/environment.py`)

- `super().__init__` now receives `role="environment"`.
- `setup()` simplified to a single attempt — the 5-iteration `for attempt in range(...)` loop removed, along with the `time.sleep(_BME680_INIT_RETRY_DELAY_S)` call.
- Module constants `_BME680_INIT_RETRIES` and `_BME680_INIT_RETRY_DELAY_S` deleted.
- On setup failure: logs `environment_setup_error` and raises immediately. Supervisor's exponential backoff ladder (Plan 21-02) owns the retry cadence.
- `import time` removed from module imports (no longer needed).

### HighRateSampler (`src/shitbox/events/sampler.py`)

- `from shitbox.hardware import state as hw_state` added at module top.
- `self.role = "imu"` added in `__init__`.
- Hook locations (file:line):
  - `sampler.py:183` — `hw_state.report_present(self.role)` after `self._consecutive_failures = 0` (successful read branch — Pitfall 2 respected, only from real sample, not from `_i2c_bus_reset` success).
  - `sampler.py:199` — `hw_state.report_degraded(self.role)` after `log.warning("i2c_bus_lockup_detected", ...)`.
  - `sampler.py:220` — `hw_state.report_missing(self.role)` after `log.critical("i2c_max_resets_exceeded", ...)`, BEFORE `self._force_reboot()`.
- `buzzer.beep_i2c_lockup()`, `speaker.speak_i2c_lockup()`, the reset ladder, and `_force_reboot` all untouched (Pitfall 6 respected).

### VideoRingBuffer (`src/shitbox/capture/ring_buffer.py`)

- `from shitbox.hardware import state as hw_state` added at module top.
- `role: str = "camera_front"` kwarg added at end of `__init__` signature. Stored as `self.role` (set before all other instance attributes).
- Hook locations (file:line):
  - `ring_buffer.py:892` — `hw_state.report_missing(self.role)` after `log.warning("video_device_missing", ...)` in `_health_monitor`.
  - `ring_buffer.py:911` — `hw_state.report_degraded(self.role)` after `log.warning("video_ring_buffer_ffmpeg_stalled", ...)` in `_health_monitor`.
  - `ring_buffer.py:752` — `hw_state.report_present(self.role)` at the end of the try block in `_start_ffmpeg`, after process is confirmed launched.
- ffmpeg argv, `_check_stall`, `_kill_current`, `_cleanup_buffer`, stall timeout constant all untouched.

## Test Counts

| Module | Tests Before | Tests After | New |
|--------|-------------|-------------|-----|
| tests/collectors/test_base_hardware_hook.py | 0 (new) | 6 | +6 |
| tests/collectors/test_environment_simplified_retry.py | 0 (new) | 4 | +4 |
| tests/test_i2c_recovery.py | 13 | 16 | +3 |
| tests/test_ffmpeg_stall.py | 6 | 9 | +3 |
| **Total new** | | | **+16** |

Full suite: 281 passed, 1 skipped, 1 warning (pre-existing uvicorn warning in dashboard tests — unchanged from Plan 01).

## Verification Checks Passed

- `pytest tests/collectors/ tests/test_i2c_recovery.py tests/test_ffmpeg_stall.py -x -q` — 52 passed
- `pytest -x -q` — 281 passed, 1 skipped
- `grep -r "hw_state.report_" src/shitbox/` — 8 calls: 3 sampler + 3 ring_buffer + 2 base helpers
- `ruff check src/shitbox/collectors/base.py src/shitbox/collectors/environment.py src/shitbox/events/sampler.py src/shitbox/capture/ring_buffer.py` — all checks passed
- `! grep -q "_BME680_INIT_RETRIES" src/shitbox/collectors/environment.py` — confirmed removed
- `! grep -q "time.sleep" src/shitbox/collectors/environment.py` — confirmed no retry sleep

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] _make_vrb factory missing role attribute broke existing test**

- **Found during:** Task 2 GREEN phase
- **Issue:** `_make_vrb` in `test_ffmpeg_stall.py` uses `__new__` to bypass `__init__`, so `self.role` was never set. After adding `hw_state.report_degraded(self.role)` in `_health_monitor`, the existing `test_health_monitor_restarts_on_stall` test hit `AttributeError: 'VideoRingBuffer' object has no attribute 'role'`. The health monitor's `except Exception` caught this, suppressing the buzzer call, causing the test to fail.
- **Fix:** Added `vrb.role = "camera_front"` to the `_make_vrb` factory helper.
- **Files modified:** `tests/test_ffmpeg_stall.py`
- **Commit:** `6dbbd86` (same task commit)

**2. [Rule 1 - Bug] test_max_errors_safety_valve_unchanged timing issue**

- **Issue:** `patch("time.sleep")` intercepted the sleep inside the test's polling loop, so the background thread ran to completion but the polling loop never actually waited. The test saw `_running=True` because the patch eliminated all wait time in the test thread before the daemon thread finished.
- **Fix:** Replaced polling loop with `patch("shitbox.collectors.base.time")` (module-scoped, only affects the run loop) plus `c._thread.join(timeout=5.0)` to wait deterministically.
- **Files modified:** `tests/collectors/test_base_hardware_hook.py`
- **Commit:** `442841c` (same task commit)

**3. [Rule 3 - Blocking] environment.py test patches needed sys.modules not module attrs**

- **Issue:** Original test patches targeted `shitbox.collectors.environment.busio` etc. After moving imports inside `setup()`, those module attributes no longer exist and `patch()` raised `AttributeError`.
- **Fix:** Switched to `patch.dict(sys.modules, {"board": ..., "busio": ..., "adafruit_bme680": ...})` pattern, which intercepts the `import` statements inside `setup()`.
- **Files modified:** `tests/collectors/test_environment_simplified_retry.py`
- **Commit:** `442841c` (same task commit)

**4. [Rule 3 - Blocking] test_successful_ffmpeg_start_reports_present missing input_format**

- **Issue:** `_make_vrb_with_role` inherits from `_make_vrb` which uses `__new__`, so `input_format` was not set. `_start_ffmpeg` accesses `self.input_format` to choose the ffmpeg mode.
- **Fix:** Added `vrb.input_format = "mjpeg"` and `vrb._ffmpeg_started_at = 0.0` to the test setup.
- **Files modified:** `tests/test_ffmpeg_stall.py`
- **Commit:** `6dbbd86` (same task commit)

## Success Criteria Check

- [x] HW-02 reporting pathway: every collector tier (1Hz base + IMU + cameras) now writes into HardwareState.
- [x] HW-04 observational path: sampler reports DEGRADED mid-recovery, MISSING before reboot; ring_buffer reports MISSING on device missing, DEGRADED on stall.
- [x] BME680 cold-boot delay fixed (Pitfall 7): `setup()` is a single attempt.
- [x] Pitfall 2 respected: PRESENT only from a successful sample read, not from `_i2c_bus_reset`.
- [x] Pitfall 6 respected: `speak_i2c_lockup` remains in sampler; terminal TTS lives in supervisor.
- [x] `_max_errors=10` safety valve unchanged.

## Known Stubs

None. All hooks call real `hw_state` functions.

## Threat Flags

None. All hook calls are in-process GIL-atomic dict rebinds. No new network endpoints, auth paths, or trust boundary crossings.

## Self-Check: PASSED

- `src/shitbox/collectors/base.py` — FOUND, contains `_report_present`, `_report_missing`, `self.role`
- `src/shitbox/collectors/environment.py` — FOUND, no `_BME680_INIT_RETRIES`, no `time.sleep`, `role="environment"`
- `src/shitbox/events/sampler.py` — FOUND, contains `self.role = "imu"`, 3 `hw_state.report_*` calls
- `src/shitbox/capture/ring_buffer.py` — FOUND, contains `role: str = "camera_front"`, 3 `hw_state.report_*` calls
- `tests/collectors/test_base_hardware_hook.py` — FOUND
- `tests/collectors/test_environment_simplified_retry.py` — FOUND
- Commits: 5d79d63, 442841c, 5adc66f, 6dbbd86 — all present in git log
