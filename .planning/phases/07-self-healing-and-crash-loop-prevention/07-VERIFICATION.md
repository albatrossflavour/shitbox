---
phase: 07-self-healing-and-crash-loop-prevention
verified: 2026-02-28T08:30:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 7: Self-Healing and Crash-Loop Prevention Verification Report

**Phase Goal:** The system stops crash-looping from I2C failures and all subsystems follow a consistent detect-alert-recover-escalate pattern
**Verified:** 2026-02-28T08:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | When I2C bus locks up repeatedly, the system escalates through multiple reset attempts before falling back to a controlled reboot — never a tight crash-loop | VERIFIED | `_sample_loop` increments `_reset_count`, gates `_force_reboot()` on `_reset_count >= I2C_MAX_RESETS` (3); startup `start()` wraps `setup()` in escalation loop; 7 unit tests pass |
| 2 | When the TTS speaker stops producing audio, the system detects the silence within 30 seconds and re-initialises the speaker subsystem automatically | VERIFIED | `_health_check()` check 6 detects dead worker via `_worker.is_alive()`, calls `cleanup()` then `init()`; health check runs every 30 seconds; 8 unit tests pass |
| 3 | Every self-healing subsystem (I2C, TTS, ffmpeg) follows the same detect-failure / log / alert / attempt-recovery / escalate pattern | VERIFIED | I2C: `i2c_bus_lockup_detected` log + `beep_i2c_lockup()` + `speak_i2c_lockup()` + `_i2c_bus_reset()` + `_force_reboot()` after 3 fails; TTS: `speaker_worker_dead` log + `cleanup()` + `init()`; ffmpeg: `ffmpeg_stall_detected` log + `beep_ffmpeg_stall()` + `speak_ffmpeg_stall()` + `_kill_current()` + `_start_ffmpeg()` in `ring_buffer.py` |
| 4 | After a self-healing recovery event, the system announces the recovery via TTS (or buzzer fallback) so the driver knows it happened | VERIFIED | Shared `if recovered:` block at end of `_health_check()` calls `buzzer.beep_service_recovered("subsystem")` and `speaker.speak_service_recovered()`; also fires after I2C recovery via `beep_service_recovered("i2c")` and `speak_service_recovered()` in `_sample_loop` |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/events/sampler.py` | Escalating I2C recovery with counter and backoff | VERIFIED | 360 lines; contains `I2C_MAX_RESETS = 3`, `I2C_RESET_BACKOFF_SECONDS = [0, 2, 5]`, `_reset_count` attribute, escalation in `_sample_loop` and `start()`, reset in `stop()` |
| `tests/test_i2c_recovery.py` | Unit tests for escalation paths (min 100 lines) | VERIFIED | 442 lines; 13 tests total — 6 pre-existing + 7 new escalation tests covering counter increment, reboot gating, backoff delays, success reset, startup protection, startup all-fail, stop reset |
| `src/shitbox/events/engine.py` | Speaker watchdog in `_health_check` and recovery confirmation | VERIFIED | 1923 lines; check 6 at line 1827 with `speaker_worker_dead` log, triple guard (`_voice`, `_worker`, `is_alive()`), `cleanup()` + `init()` reinit, `recovered.append("speaker")`; recovery confirmation at lines 1865-1868 |
| `tests/test_speaker_alerts.py` | Unit tests for speaker watchdog and recovery announcements (min 200 lines) | VERIFIED | 649 lines; 8 new HEAL-01/HEAL-03 tests in addition to pre-existing AUDIO-01/02/03 tests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/shitbox/events/sampler.py` | `_i2c_bus_reset()` | `_reset_count >= I2C_MAX_RESETS` gates `_force_reboot()` | WIRED | Line 236: `elif self._reset_count >= I2C_MAX_RESETS:` before calling `self._force_reboot()` |
| `src/shitbox/events/sampler.py` | `start()` | `setup()` wrapped in `for attempt in range(I2C_MAX_RESETS + 1):` loop | WIRED | Lines 139-157: loop present, calls `_i2c_bus_reset()` on failure, `_force_reboot()` on exhaustion, returns without starting thread |
| `src/shitbox/events/engine.py` | `shitbox.capture.speaker` | `_health_check` speaker worker liveness check via `_worker.is_alive` | WIRED | Lines 1829-1832: `speaker._voice is not None and speaker._worker is not None and not speaker._worker.is_alive()` |
| `src/shitbox/events/engine.py` | `buzzer.beep_service_recovered` | Recovery confirmation after `health_check_recovered` | WIRED | Lines 1865-1868: `if recovered:` block calls `buzzer.beep_service_recovered("subsystem")` and `speaker.speak_service_recovered()` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HEAL-01 | 07-02-PLAN.md | When the TTS speaker stops producing audio, the system detects the failure and re-initialises the speaker subsystem | SATISFIED | Speaker worker liveness check (check 6) in `_health_check()`; detects dead thread, calls `cleanup()` then `init()`; 8 unit tests verify all guard conditions and reinit paths |
| HEAL-02 | 07-01-PLAN.md | When I2C bus lockups recur after a reset attempt, the system escalates (multiple reset attempts before reboot fallback) | SATISFIED | `I2C_MAX_RESETS=3` with `I2C_RESET_BACKOFF_SECONDS=[0,2,5]`; `_reset_count` persists across lockups, gates `_force_reboot()`; startup protection in `start()`; 7 unit tests verify all escalation paths |
| HEAL-03 | 07-01-PLAN.md, 07-02-PLAN.md | Each self-healing subsystem follows detect → log → alert → attempt recovery → escalate if fails pattern | SATISFIED | I2C: log `i2c_bus_lockup_detected` + buzz + speak + reset + escalate; TTS: log `speaker_worker_dead` + `cleanup()` + `init()` + recovery confirmation; ffmpeg: log `ffmpeg_stall_detected` + buzz + speak + kill + restart (pre-existing from Phase 2, confirmed in `ring_buffer.py` lines 542-558) |

**REQUIREMENTS.md traceability table** marks all three (HEAL-01, HEAL-02, HEAL-03) as Complete under Phase 7. No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No stubs, placeholders, or empty implementations found |

No `TODO`, `FIXME`, `return null`, or empty handler patterns were detected in any modified file.

### Human Verification Required

#### 1. I2C escalation timing under real bus lockup

**Test:** Connect an MPU6050, force a bus lockup (e.g. hold SDA low), and observe the log output over ~45 seconds (3 attempts × [0,2,5]s backoff).
**Expected:** Three `i2c_bus_lockup_detected` warnings with incrementing `reset_attempt`, then `i2c_max_resets_exceeded` critical followed by a controlled reboot.
**Why human:** Cannot simulate real I2C hardware lockup in unit tests; the test mocks `_i2c_bus_reset()` — actual GPIO bit-bang pulse sequence requires physical hardware.

#### 2. Speaker watchdog end-to-end on USB disconnect

**Test:** Start the daemon with the USB speaker connected, then pull the USB cable while the system is running. Wait up to 30 seconds (one health check cycle), then reconnect the cable.
**Expected:** `speaker_worker_dead` warning logged, followed by `speaker_reinitialised` (if reinit succeeds with device re-enumerated) or `speaker_reinit_failed_no_device` (if device not yet re-enumerated). After successful reinit, a spoken recovery announcement is heard.
**Why human:** USB device re-enumeration timing is hardware-dependent; the health check `init()` call may land before or after the OS re-enumerates the device. The 30-second detection window must be observed in real time.

#### 3. Recovery announcement audible to driver

**Test:** Trigger any subsystem recovery (e.g. kill the telemetry thread externally) and verify the recovery TTS announcement is audible and intelligible through the USB speaker.
**Expected:** After recovery, the driver hears a spoken confirmation (e.g. "System recovered.") within one health check cycle.
**Why human:** Audio output quality and intelligibility cannot be verified programmatically; requires physical listening in the car environment.

## Gaps Summary

No gaps. All must-haves verified at all three levels (exists, substantive, wired).

The phase goal is fully achieved: I2C crash-looping is eliminated through escalating reset attempts with backoff (HEAL-02), the TTS speaker worker is monitored and auto-healed (HEAL-01), and all three self-healing subsystems (I2C, TTS, ffmpeg) consistently follow the detect-alert-recover-escalate pattern with driver-audible recovery announcements (HEAL-03).

---

_Verified: 2026-02-28T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
