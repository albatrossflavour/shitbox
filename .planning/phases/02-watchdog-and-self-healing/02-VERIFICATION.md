---
phase: 02-watchdog-and-self-healing
verified: 2026-02-26T00:00:00Z
status: human_needed
score: 14/14 must-haves verified
re_verification: false
human_verification:
  - test: "Confirm Pi has dtparam=watchdog=on in /boot/firmware/config.txt and RuntimeWatchdogSec=10 in /etc/systemd/system.conf.d/watchdog.conf"
    expected: "BCM2835 hardware watchdog is armed; cat /sys/class/watchdog/watchdog0/status shows 'active'"
    why_human: "WDOG-01 requires the hardware watchdog to be enabled via Pi firmware config — this is an out-of-repo Pi deployment step that cannot be verified from the codebase. REQUIREMENTS.md states RuntimeWatchdogSec=14 but context doc locked timeout to 10 seconds; the deployed value on the Pi must be confirmed."
  - test: "Confirm buzzer audible alert patterns are distinguishable by a driver who cannot look at a screen"
    expected: "service_crash (1 long), i2c_lockup (3 short), watchdog_miss (2 long), ffmpeg_stall (2 short + 1 long), and service_recovered (1 short high chirp) are each aurally distinct"
    why_human: "Tone patterns are verified in code and tests, but learnable distinction requires human ears on hardware."
  - test: "Trigger a test I2C lockup on the Pi and confirm the bit-bang recovery path fires without disrupting the GPIO button handler"
    expected: "I2C bus recovers within ~200ms, buzzer plays 3-short lockup pattern, sampler resumes reads, button handler on GPIO17 continues to function"
    why_human: "GPIO selective cleanup (GPIO.cleanup([2, 3])) cannot be verified without real Raspberry Pi hardware."
---

# Phase 2: Watchdog and Self-Healing Verification Report

**Phase Goal:** Hardware watchdog is active, all services restart on crash, and known data-loss bugs are fixed
**Verified:** 2026-02-26
**Status:** human_needed — all automated checks pass; 3 items require Pi hardware or live deployment confirmation
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Systemd service unit has WatchdogSec=10 and StartLimitIntervalSec=0 | VERIFIED | `systemd/shitbox-telemetry.service` line 16: `StartLimitIntervalSec=0`; line 19: `WatchdogSec=10` |
| 2 | Service unit has Restart=always and will never permanently stop restarting | VERIFIED | `systemd/shitbox-telemetry.service` line 13: `Restart=always`; `StartLimitIntervalSec=0` disables the burst limit |
| 3 | Distinct buzzer patterns exist for service crash, I2C lockup, watchdog miss, ffmpeg stall, and service recovered | VERIFIED | All five functions present in `src/shitbox/capture/buzzer.py` lines 184–261 with distinct 330 Hz and 880 Hz tone sequences |
| 4 | Escalating repeat alerts trigger doubled patterns when same failure recurs within 5 minutes | VERIFIED | `BuzzerAlertState.should_escalate()` (line 43) updates timestamp and returns True within `ESCALATION_WINDOW_SECONDS=300`; all alert functions double tones on True |
| 5 | Buzzer alerts suppressed during 30-second boot grace period | VERIFIED | `_should_alert()` (line 90) checks `time.time() - _boot_start_time >= BOOT_GRACE_PERIOD_SECONDS`; all 5 alert functions call it first |
| 6 | ffmpeg stall detected when output file mtime stops changing for 30 seconds | VERIFIED | `_check_stall()` in `src/shitbox/capture/ring_buffer.py` lines 467–503; `STALL_TIMEOUT_SECONDS=30` class constant |
| 7 | Stall detector does not false-positive when no segments exist yet (startup grace) | VERIFIED | `_check_stall()` returns False immediately when `segments` is empty (line 479–481) |
| 8 | On stall detection, `buzzer.beep_ffmpeg_stall()` called, then ffmpeg killed and restarted | VERIFIED | `_health_monitor()` lines 532–542: calls `buzzer.beep_ffmpeg_stall()`, `_kill_current()`, `_start_ffmpeg()` |
| 9 | Stall timer resets on every ffmpeg restart | VERIFIED | `_reset_stall_state()` called at top of `_start_ffmpeg()` (line 398) |
| 10 | After 5 consecutive I2C read failures, 9-clock bit-bang recovery attempted | VERIFIED | `_sample_loop()` lines 186–198: increments `_consecutive_failures`; triggers at `I2C_CONSECUTIVE_FAILURE_THRESHOLD=5` |
| 11 | Consecutive failure counter resets to 0 on any successful read | VERIFIED | `sampler.py` line 177: `self._consecutive_failures = 0` on successful read |
| 12 | After successful bit-bang recovery, MPU6050 reinitialised before resuming reads | VERIFIED | `_i2c_bus_reset()` lines 256–258: calls `self.setup()` after `smbus2.SMBus()` reopen |
| 13 | If bit-bang recovery fails, system forces reboot | VERIFIED | `_i2c_bus_reset()` returns False on exception; `_sample_loop()` line 198 calls `self._force_reboot()` which runs `sudo systemctl reboot` |
| 14 | Engine wires boot start time to buzzer for grace period suppression | VERIFIED | `engine.py` line 1455: `buzzer.set_boot_start_time(time.time())` called immediately after `buzzer.init()` |

**Score:** 14/14 truths verified

---

## Required Artifacts

| Artifact | Expected | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| `systemd/shitbox-telemetry.service` | Hardened unit with WatchdogSec=10 and StartLimitIntervalSec=0 | Yes | Yes (45 lines, both directives present) | N/A (deployment file) | VERIFIED |
| `src/shitbox/capture/buzzer.py` | Alert patterns and BuzzerAlertState escalation tracker | Yes | Yes (262 lines, all 5 alert functions + BuzzerAlertState class) | Yes — imported in `sampler.py` and `engine.py` | VERIFIED |
| `src/shitbox/capture/ring_buffer.py` | Mtime-based stall detection in `_check_stall` | Yes | Yes (`_check_stall`, `_reset_stall_state`, `STALL_TIMEOUT_SECONDS` all present) | Yes — `_check_stall` called in `_health_monitor` at line 532 | VERIFIED |
| `src/shitbox/events/sampler.py` | I2C bus lockup detection and 9-clock bit-bang recovery | Yes | Yes (`_i2c_bus_reset`, `_force_reboot`, `I2C_CONSECUTIVE_FAILURE_THRESHOLD=5` constants) | Yes — triggered from `_sample_loop` exception handler | VERIFIED |
| `src/shitbox/events/engine.py` | Boot start time wired to buzzer | Yes | Yes — `buzzer.set_boot_start_time(time.time())` at line 1455 | Yes — called in `start()` immediately after `buzzer.init()` | VERIFIED |
| `tests/test_watchdog.py` | Unit tests for systemd unit file parsing | Yes | Yes (3 tests covering WatchdogSec, Restart, StartLimitIntervalSec, Type=notify) | Yes — runs as part of test suite | VERIFIED |
| `tests/test_buzzer_alerts.py` | Unit tests for buzzer alert patterns and escalation | Yes | Yes (8 tests: 4 pattern, 3 escalation, 1 grace period) | Yes — runs as part of test suite | VERIFIED |
| `tests/test_ffmpeg_stall.py` | Unit tests for stall detection logic | Yes | Yes (6 tests covering all stall detection paths) | Yes — runs as part of test suite | VERIFIED |
| `tests/test_i2c_recovery.py` | Unit tests for I2C recovery with mocked GPIO and smbus2 | Yes | Yes (6 tests covering counter mechanics, GPIO sequence, reboot fallback) | Yes — runs as part of test suite | VERIFIED |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `systemd/shitbox-telemetry.service` | `src/shitbox/events/engine.py` | `WatchdogSec=10` matches existing `_notify_systemd("WATCHDOG=1")` petting in main loop | VERIFIED | `engine.py` `_notify_systemd("WATCHDOG=1")` petting confirmed present; runs each loop iteration; `WatchdogSec=10` verified in unit file |
| `src/shitbox/capture/buzzer.py` | `BuzzerAlertState` | `should_escalate()` method | VERIFIED | `BuzzerAlertState.should_escalate()` exists at line 43; used in all 5 alert functions |
| `src/shitbox/capture/ring_buffer.py` | `_health_monitor` | `_check_stall()` called in health monitor loop | VERIFIED | `_health_monitor()` line 532: `if self._check_stall():` |
| `src/shitbox/capture/ring_buffer.py` | `src/shitbox/capture/buzzer.py` | `beep_ffmpeg_stall()` called on stall detection | VERIFIED | Lines 537–539: lazy `from shitbox.capture import buzzer; buzzer.beep_ffmpeg_stall()` |
| `src/shitbox/events/sampler.py` | `src/shitbox/capture/buzzer.py` | `beep_i2c_lockup()` called on recovery attempt | VERIFIED | `sampler.py` line 9: `from shitbox.capture import buzzer`; line 191: `buzzer.beep_i2c_lockup()` |
| `src/shitbox/events/sampler.py` | `RPi.GPIO` | GPIO.output for 9-clock bit-bang on GPIO2/GPIO3 | VERIFIED | `_i2c_bus_reset()` lines 233–236: 9-iteration loop calling `GPIO.output(SCL_PIN, GPIO.LOW)` and `GPIO.output(SCL_PIN, GPIO.HIGH)` |
| `src/shitbox/events/engine.py` | `src/shitbox/capture/buzzer.py` | `set_boot_start_time` called during engine start | VERIFIED | `engine.py` line 1455: `buzzer.set_boot_start_time(time.time())` |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WDOG-01 | 02-01 | BCM2835 hardware watchdog enabled (`dtparam=watchdog=on`, `RuntimeWatchdogSec=14`) | PARTIAL — in-repo portion VERIFIED; Pi deployment requires human | `WatchdogSec=10` in service unit verified. `RuntimeWatchdogSec` is a system.conf Pi deployment step outside the repo. Context locked timeout to 10s (not 14s as in REQUIREMENTS.md). Pi hardware must be checked. |
| WDOG-02 | 02-01 | All systemd services audited and configured with `Restart=always` | VERIFIED | `systemd/shitbox-telemetry.service`: `Restart=always` + `StartLimitIntervalSec=0` confirmed |
| WDOG-03 | 02-02 | ffmpeg `is_running` bug fixed to use `poll()` with mtime-based health check and auto-restart | VERIFIED | `is_running` property uses `poll()` (line 107); `_check_stall()` adds mtime monitoring; `_health_monitor()` kills and restarts on stall |
| WDOG-04 | 02-03 | I2C bus lockup detected and recovered via 9-clock bit-bang reset | VERIFIED | `_i2c_bus_reset()` fully implemented with 9-clock SCL pulses, selective GPIO cleanup, smbus2 reopen, MPU6050 reinit, and reboot fallback |
| HLTH-02 | 02-01 | In-car buzzer alerts on thermal warnings, storage critical, and service failures | PARTIALLY VERIFIED — service failures covered; thermal and storage alerts are Phase 3 scope | Five failure alert functions implemented and tested. Thermal/storage buzzer alerts are Phase 3 (THRM-01/02). HLTH-02 description in REQUIREMENTS.md is broader than Phase 2's implementation scope. |

**Notes:**

- WDOG-01 discrepancy: REQUIREMENTS.md states `RuntimeWatchdogSec=14` but the CONTEXT.md locked the timeout to 10 seconds. The PLAN instructs `WatchdogSec=10` in the service unit (codebase artifact, verified). The `RuntimeWatchdogSec` Pi system.conf deployment is outside the repo and requires physical confirmation.
- HLTH-02 partial scope: The requirement description mentions thermal and storage alerts, which belong to Phase 3. The Phase 2 portion (service failures, I2C lockup, watchdog miss, ffmpeg stall) is fully implemented.

---

## Anti-Patterns Found

None detected. Scanned `systemd/shitbox-telemetry.service`, `src/shitbox/capture/buzzer.py`, `src/shitbox/capture/ring_buffer.py`, `src/shitbox/events/sampler.py`, and all four test files for TODO/FIXME/placeholder/stub patterns. Clean.

---

## Test Suite Results

```
pytest tests/test_watchdog.py tests/test_buzzer_alerts.py tests/test_ffmpeg_stall.py tests/test_i2c_recovery.py -x -q
24 passed in 0.27s

pytest tests/ -x -q
37 passed in 0.31s
```

All 24 phase-specific tests pass. Full suite (37 tests) passes with no regressions.

---

## Human Verification Required

### 1. BCM2835 Hardware Watchdog Armed on Pi

**Test:** SSH to Pi; run `cat /sys/class/watchdog/watchdog0/status` and `cat /etc/systemd/system.conf.d/watchdog.conf`
**Expected:** Status shows `active`; conf file contains `RuntimeWatchdogSec=10` (or 14 if REQUIREMENTS.md value was intended — confirm which is correct)
**Why human:** The hardware watchdog requires `dtparam=watchdog=on` in `/boot/firmware/config.txt` and `RuntimeWatchdogSec` in system.conf. These are Pi deployment steps — no file in this repo enables the hardware watchdog. Without this, `WatchdogSec=10` in the service unit still provides service-level restart behaviour, but the BCM2835 chip that can recover from a full OS hang is not armed.

### 2. Buzzer Alert Patterns Are Aurally Distinguishable

**Test:** On Pi with PiicoDev buzzer attached, trigger each alert function via a Python REPL: `python -c "from shitbox.capture import buzzer; buzzer.init(); buzzer.set_boot_start_time(0.0); buzzer.beep_service_crash()"` and repeat for each alert type
**Expected:** Each pattern sounds distinct and recognisable without reference material; escalation (call same function twice within 5 minutes) plays the pattern twice
**Why human:** Tone frequencies (330 Hz vs 880 Hz) and durations are correct in code, but human hearing verification is required to confirm the patterns are learnable under rally driving conditions.

### 3. GPIO Selective Cleanup Does Not Disrupt Button Handler During I2C Recovery

**Test:** On Pi, deliberately trigger an I2C lockup simulation (or set `_consecutive_failures = 4` and force one more failure in a test harness), then immediately test the GPIO button on pin 17
**Expected:** Button handler continues functioning after `GPIO.cleanup([2, 3])` — only SCL and SDA pins are reset, GPIO17 button state is unchanged
**Why human:** GPIO selective cleanup behaviour requires real Raspberry Pi GPIO hardware; cannot be verified by mocking.

---

## Commit Verification

All commits referenced in SUMMARY files are present in the git log:

| Commit | Plan | Description |
|--------|------|-------------|
| `d72f4be` | 02-01 | feat: harden systemd unit and add buzzer alert patterns |
| `191e63f` | 02-01 | test: add unit tests for systemd unit and buzzer alerts |
| `98b940a` | 02-02 | feat: add mtime-based stall detection to VideoRingBuffer |
| `53ceea1` | 02-02 | test: ffmpeg stall + I2C recovery tests |
| `d86f89f` | 02-03 | feat: add I2C bus lockup detection and 9-clock bit-bang recovery |
| `2efe972` | 02-03 | test: I2C recovery unit tests with mocked GPIO and smbus2 |

---

_Verified: 2026-02-26_
_Verifier: Claude (gsd-verifier)_
