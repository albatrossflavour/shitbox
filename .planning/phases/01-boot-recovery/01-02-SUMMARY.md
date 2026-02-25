---
phase: 01-boot-recovery
plan: "02"
subsystem: telemetry
tags: [boot-recovery, engine, buzzer, threading, prometheus, sqlite, wal]

# Dependency graph
requires:
  - phase: 01-01
    provides: "BootRecoveryService, detect_unclean_shutdown, EventStorage.close_orphaned_events()"
provides:
  - "BootRecoveryService wired into UnifiedEngine.start() with WAL detection before database.connect()"
  - "beep_clean_boot() and beep_crash_recovery() buzzer patterns"
  - "recovery_was_crash, recovery_complete, recovery_orphans_closed fields in get_status()"
  - "shitbox_boot_was_crash Prometheus gauge sent as best-effort one-shot on each boot"
  - "Integration tests for full engine boot recovery flow"
affects: [oled-display, health-monitor, phase-02, phase-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "WAL detection before database.connect() — crash detection must precede DB open"
    - "Best-effort background metric thread — daemon thread, failure logged and ignored"
    - "Recovery-specific buzzer: 3 ascending tones (boot) then 1 short (clean) or 2 short (crash)"

key-files:
  created:
    - tests/test_engine_boot.py
  modified:
    - src/shitbox/capture/buzzer.py
    - src/shitbox/events/engine.py

key-decisions:
  - "Buzzer plays distinct recovery tone AFTER the standard 3-tone beep_boot() sequence"
  - "boot_recovery attribute set to None in __init__ and populated in start() to match engine lifecycle"
  - "Prometheus metric uses best-effort fire-and-forget thread — failure is logged, not fatal"
  - "get_status() exposes recovery fields for future OLED display (Phase 2 renders them)"

patterns-established:
  - "Boot sequence ordering: WAL detect → DB connect → recovery start → services start → buzzer"
  - "One-shot daemon thread pattern for post-boot work that must not block data capture"

requirements-completed: [BOOT-01, BOOT-02, BOOT-03]

# Metrics
duration: 3min
completed: 2026-02-25
---

# Phase 01 Plan 02: Engine Boot Recovery Wiring Summary

**BootRecoveryService wired into UnifiedEngine.start() with WAL-based crash detection, recovery-specific buzzer tones, get_status() recovery fields, and a best-effort Prometheus boot metric**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-25T08:51:31Z
- **Completed:** 2026-02-25T08:54:04Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- WAL-based crash detection runs before `database.connect()` on every engine startup
- BootRecoveryService starts as a background daemon thread, orphan events repaired without blocking IMU/GPS
- Buzzer plays 3 ascending tones (boot) followed by 1 short beep (clean) or 2 short beeps (crash recovery)
- `get_status()` exposes `recovery_was_crash`, `recovery_complete`, and `recovery_orphans_closed` for OLED
- `shitbox_boot_was_crash` Prometheus gauge sent as a best-effort one-shot after recovery completes
- 6 integration tests verify the full recovery flow end-to-end without hardware dependencies

## Task Commits

Each task was committed atomically:

1. **Task 1: Add buzzer patterns and wire BootRecoveryService into engine** - `270ff7c` (feat)
2. **Task 2: Integration tests for engine boot recovery wiring** - `ca2869c` (test)

**Plan metadata:** *(docs commit follows)*

## Files Created/Modified

- `src/shitbox/capture/buzzer.py` - Added `beep_clean_boot()` and `beep_crash_recovery()` functions
- `src/shitbox/events/engine.py` - Imported `BootRecoveryService`/`detect_unclean_shutdown`, added `boot_recovery` attribute, wired WAL detection and recovery in `start()`, modified buzzer section, added recovery fields to `get_status()`
- `tests/test_engine_boot.py` - Integration tests: WAL detection, buzzer patterns, attribute defaults, full recovery flow

## Decisions Made

- Buzzer plays recovery-specific tone **after** `beep_boot()` so the 3-tone boot signal is always heard first, then the recovery indicator follows
- `self.boot_recovery` is set to `None` in `__init__` and only populated in `start()` — this matches the engine lifecycle where the database path isn't ready to check until startup
- The Prometheus metric uses a best-effort daemon thread with a 30-second timeout on `recovery_complete` — if Prometheus is unreachable, the failure is logged and ignored without impacting boot
- `get_status()` exposes raw recovery fields now; OLED rendering logic is deferred to Phase 2

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. All tests passed on first run.

## Next Phase Readiness

- Boot recovery is fully wired; the system now detects crashes, repairs orphaned events, and signals the driver via buzzer on every boot
- `get_status()` recovery fields are available for OLED display work in Phase 2
- Pre-existing ruff lint errors in `engine.py` (lines 370, 822-823, 851) and other files are out-of-scope and deferred

## Self-Check: PASSED

- FOUND: `src/shitbox/capture/buzzer.py`
- FOUND: `src/shitbox/events/engine.py`
- FOUND: `tests/test_engine_boot.py`
- FOUND: `.planning/phases/01-boot-recovery/01-02-SUMMARY.md`
- FOUND: commit `270ff7c` (feat: engine wiring)
- FOUND: commit `ca2869c` (test: integration tests)

---

*Phase: 01-boot-recovery*
*Completed: 2026-02-25*
