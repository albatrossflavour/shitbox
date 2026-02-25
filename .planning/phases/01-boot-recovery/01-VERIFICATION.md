---
phase: 01-boot-recovery
verified: 2026-02-25T09:15:00Z
status: passed
score: 4/4 must-haves verified
gaps: []
human_verification:
  - test: "Start the engine on a Pi where a prior run was killed hard (via power cut or SIGKILL). Check structured logs for crash_recovery_complete, integrity_check_passed, and orphaned_event_closed entries."
    expected: "Exactly those log lines appear before GPS/IMU data lines. No manual intervention required."
    why_human: "Cannot simulate a real hard power cut in a unit test — the WAL file creation and journaling behaviour differs between macOS tmp_path and a live Raspberry Pi filesystem."
  - test: "Pull power mid-run, reboot, observe buzzer sequence."
    expected: "Three ascending boot tones followed immediately by two short 880 Hz beeps (crash recovery pattern), not one."
    why_human: "Buzzer is hardware-only; tests verify the function is called but cannot produce audible output."
---

# Phase 1: Boot Recovery Verification Report

**Phase Goal:** System survives hard power cuts and starts cleanly after every ignition cycle
**Verified:** 2026-02-25T09:15:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After pulling the power cable mid-run and restarting, the system starts without manual intervention and no events are left in an open/corrupted state | VERIFIED | `BootRecoveryService._detect_and_recover()` runs on every crash boot, calls `close_orphaned_events()`, and sets `recovery_complete`; `test_full_recovery_flow` confirms end-to-end with real tmp_path files |
| 2 | SQLite integrity check runs on every startup after an unclean shutdown and logs the result | VERIFIED | `_run_integrity_check()` runs `PRAGMA quick_check` and logs `integrity_check_passed` or `integrity_check_failed`; only called when `was_crash=True`; `test_integrity_check_on_crash` confirms |
| 3 | Events from a prior crash are closed and marked as interrupted — not silently dropped and not left open indefinitely | VERIFIED | `close_orphaned_events()` marks files missing `end_time` or with `status=open` as `"interrupted"` with `end_time` from file mtime; `test_orphan_events_closed` confirms; corrupt JSON handled without crash |
| 4 | SQLite is configured with synchronous=FULL so that WAL writes are durable across hard power cuts | VERIFIED | `database.py` line 116: `PRAGMA synchronous=FULL` set on every new thread-local connection; `test_synchronous_full` asserts `PRAGMA synchronous` returns `2` (FULL) |

**Score:** 4/4 truths verified

### Note on Success Criterion 2 Phrasing

The success criterion says integrity check should log "before any other service thread starts". The locked architectural decision (in `01-CONTEXT.md` and `01-RESEARCH.md`) is the opposite: recovery runs in a background daemon thread so it does NOT block data capture. This is intentional. The implementation honours the locked decision: `BootRecoveryService.start()` is called before GPS/IMU/sync threads start (line 1340 vs line 1387+), and the integrity check runs in that background thread concurrently with GPS init. The check always completes and logs its result; it is not silently skipped.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/storage/database.py` | `synchronous=FULL` PRAGMA on every connection | VERIFIED | Line 116: `self._local.conn.execute("PRAGMA synchronous=FULL")`; substantive implementation (532 lines); used by all DB operations throughout the engine |
| `src/shitbox/sync/boot_recovery.py` | `BootRecoveryService` with crash detection, integrity check, orphan closure | VERIFIED | 106 lines; exports `BootRecoveryService` and `detect_unclean_shutdown`; all four methods implemented with real logic; imported and used in `engine.py` |
| `src/shitbox/events/storage.py` | `close_orphaned_events()` method on `EventStorage` | VERIFIED | Lines 233–280; iterates `rglob("*.json")`, skips `events.json`, marks orphans as `interrupted`; corrupt JSON handled; used by `BootRecoveryService._detect_and_recover()` |
| `src/shitbox/events/engine.py` | `BootRecoveryService` wiring and `get_status()` recovery fields | VERIFIED | Import at line 33; `boot_recovery` attribute at line 301; WAL detection at line 1330 (before `database.connect()` at line 1335); `recovery_was_crash`, `recovery_complete`, `recovery_orphans_closed` in `get_status()` at lines 1097–1105 |
| `src/shitbox/capture/buzzer.py` | `beep_clean_boot()` and `beep_crash_recovery()` functions | VERIFIED | Lines 99–106; `beep_clean_boot` plays `[(880, 200)]`; `beep_crash_recovery` plays `[(880, 200), (880, 200)]`; called from engine at lines 1457–1460 |
| `tests/conftest.py` | Shared fixtures for boot recovery tests | VERIFIED | 34 lines; `tmp_db_path`, `db`, `event_storage_dir`, `event_storage` fixtures all present and used |
| `tests/test_database.py` | BOOT-03 PRAGMA verification test | VERIFIED | `test_synchronous_full` asserts `row[0] == 2`; passes |
| `tests/test_boot_recovery.py` | BOOT-01 and BOOT-02 tests | VERIFIED | 6 tests, all pass: WAL detection, integrity check on crash, no check on clean boot, orphan closure, corrupt JSON, recovery_complete event |
| `tests/test_engine_boot.py` | Integration tests for engine boot recovery wiring | VERIFIED | 6 tests, all pass: WAL detection with real paths, buzzer functions callable, tone sequences verified, attribute defaults, full end-to-end recovery flow |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py` | `boot_recovery.py` | `from shitbox.sync.boot_recovery import BootRecoveryService, detect_unclean_shutdown` | WIRED | Line 33 import; `detect_unclean_shutdown` called line 1330; `BootRecoveryService` instantiated line 1338; `was_crash` set line 1339; `start()` called line 1340 |
| `engine.py` | `database.py` | WAL detection BEFORE `database.connect()` | WIRED | `detect_unclean_shutdown(self.database.db_path)` at line 1330; `self.database.connect()` at line 1335 — correct ordering confirmed |
| `boot_recovery.py` | `database.py` | `Database._get_connection()` for `PRAGMA quick_check` | WIRED | `_run_integrity_check()` calls `conn = self.db._get_connection()` then `conn.execute("PRAGMA quick_check")`; result fetched and logged |
| `boot_recovery.py` | `storage.py` | `EventStorage.close_orphaned_events()` | WIRED | `_detect_and_recover()` calls `self.event_storage.close_orphaned_events()` and stores result in `self.orphans_closed` |
| `engine.py` | `buzzer.py` | `beep_crash_recovery` or `beep_clean_boot` after recovery | WIRED | Lines 1457–1460: `buzzer.beep_crash_recovery()` if `was_crash` else `buzzer.beep_clean_boot()` |
| `engine.py` | `get_status()` dict | `recovery_was_crash` and `recovery_complete` keys | WIRED | Lines 1097–1105 in `get_status()`: all three recovery fields present with safe fallbacks when `boot_recovery is None` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BOOT-01 | 01-01, 01-02 | System runs SQLite `PRAGMA integrity_check` after detecting unclean shutdown | SATISFIED | `_run_integrity_check()` in `boot_recovery.py` runs `PRAGMA quick_check` (intentional — see research doc §Pattern 4); only runs when `was_crash=True`; logs `integrity_check_passed` or `integrity_check_failed`; `test_integrity_check_on_crash` and `test_no_integrity_check_clean_boot` verify both paths |
| BOOT-02 | 01-01, 01-02 | System closes orphaned events from prior crash and marks them as interrupted on boot | SATISFIED | `close_orphaned_events()` marks events missing `end_time` or with `status=open` as `interrupted`; corrupt JSON skipped; count returned and logged; `test_orphan_events_closed`, `test_corrupt_json_handled`, `test_full_recovery_flow` all verify |
| BOOT-03 | 01-01, 01-02 | SQLite configured with `synchronous=FULL` for WAL durability across hard power cuts | SATISFIED | `database.py` line 116 confirmed; `test_synchronous_full` asserts `PRAGMA synchronous` returns `2`; applies to every thread-local connection including the recovery thread |

**Note on `quick_check` vs `integrity_check`:** The REQUIREMENTS.md uses `integrity_check` as the generic label. The research document (`01-RESEARCH.md` §Pattern 4) explicitly designates this as "Claude's Discretion" and recommends `quick_check` for correctness on embedded systems. The research context gives this authority; it is not a gap.

**No orphaned requirements:** All three Phase 1 requirements are claimed by plans 01-01 and 01-02 and are verified above.

### Anti-Patterns Found

None. No `TODO`, `FIXME`, `XXX`, `HACK`, or placeholder comments in any modified file. No empty return stubs. No `console.log`-only handlers. Ruff lint passes on all four modified production files.

### Human Verification Required

#### 1. Real hard power cut recovery

**Test:** Run the daemon on a Raspberry Pi. After it has been running for at least 30 seconds (ensuring WAL file is active), cut power by unplugging the Pi's USB supply. Restore power and let it boot. Examine the systemd journal (`journalctl -u shitbox-telemetry`).

**Expected:** Log lines include `unclean_shutdown_detected`, followed by `integrity_check_passed` (or `integrity_check_failed` with errors), followed by `crash_recovery_complete` with `orphans_closed` count, followed by `clean_boot_detected` on the subsequent clean reboot. No manual intervention required at any point.

**Why human:** A real hard power cut on Linux involves the kernel's page cache and `fsync` behaviour — this cannot be simulated on macOS with `tmp_path`. Unit tests use a fake WAL file (`wal_path.touch()`); a real test needs actual SQLite WAL writes and an abrupt kernel poweroff.

#### 2. Audible buzzer distinction

**Test:** Pull power mid-run on the Pi (with buzzer attached). Reboot. Listen to the startup sequence.

**Expected:** Three ascending tones (440/660/880 Hz, standard `beep_boot()`), then two identical 880 Hz short beeps (crash recovery pattern). On a subsequent clean reboot, three ascending tones then one single 880 Hz beep.

**Why human:** Buzzer is I2C hardware (`PiicoDev_Buzzer`) not available in the development environment. Tests verify `_play_async` is called with the correct tone arrays but cannot produce audible output.

### Gaps Summary

No gaps. All four observable truths are VERIFIED with substantive, wired implementations and passing tests.

---

_Verified: 2026-02-25T09:15:00Z_
_Verifier: Claude (gsd-verifier)_
