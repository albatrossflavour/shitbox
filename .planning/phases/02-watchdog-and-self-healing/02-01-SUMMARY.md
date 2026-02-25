---
phase: 02-watchdog-and-self-healing
plan: "01"
subsystem: infra
tags: [systemd, watchdog, buzzer, piicodev, alerts, escalation]

# Dependency graph
requires:
  - phase: 01-boot-recovery
    provides: buzzer.py module with beep_boot/beep_clean_boot/beep_crash_recovery functions

provides:
  - Hardened systemd unit with WatchdogSec=10 and StartLimitIntervalSec=0
  - BuzzerAlertState class with 5-minute escalation window tracking
  - Five failure alert functions at 330 Hz (service_crash, i2c_lockup, watchdog_miss, ffmpeg_stall, service_recovered)
  - Boot grace period suppression (30 seconds) via set_boot_start_time()
  - Unit tests for systemd unit file and buzzer alert patterns

affects:
  - 02-watchdog-and-self-healing (HealthMonitor integration will call these alert functions)
  - 03-thermal-and-storage (thermal/storage alerts may use buzzer patterns)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alert escalation: BuzzerAlertState tracks last-fired time per alert type; same failure within 5 min plays pattern twice"
    - "Boot grace period: set_boot_start_time() at engine start; _should_alert() returns False for first 30 seconds"
    - "330 Hz low warning tone for failures, distinct from 440/660/880 Hz used by boot/capture tones"

key-files:
  created:
    - tests/test_watchdog.py
    - tests/test_buzzer_alerts.py
  modified:
    - systemd/shitbox-telemetry.service
    - src/shitbox/capture/buzzer.py

key-decisions:
  - "WatchdogSec changed from 30 to 10 to match RuntimeWatchdogSec=10 deployed via /etc/systemd/system.conf.d/watchdog.conf"
  - "StartLimitIntervalSec=0 added to prevent systemd permanently stopping restarts after rapid crash loops"
  - "Escalation plays pattern twice by list concatenation (not volume control) — PiicoDev_Buzzer .volume() not available on all firmware"
  - "Boot grace period is module-level state set via set_boot_start_time() to allow engine to control suppression window"

patterns-established:
  - "Alert functions: check _should_alert() first, then _alert_state.should_escalate(), double tones if escalating"

requirements-completed: [WDOG-01, WDOG-02, HLTH-02]

# Metrics
duration: ~2min
completed: 2026-02-25
---

# Phase 2 Plan 01: Watchdog Hardening and Buzzer Alerts Summary

**Systemd unit hardened with WatchdogSec=10 and unlimited restarts via StartLimitIntervalSec=0; five 330 Hz failure alert functions added to buzzer.py with 5-minute escalation tracking and 30-second boot grace period suppression**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-25T09:38:00Z
- **Completed:** 2026-02-25T09:40:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Changed `WatchdogSec=30` to `WatchdogSec=10` and added `StartLimitIntervalSec=0` to the systemd unit so the service restarts indefinitely without hitting systemd's burst restart limit
- Added `BuzzerAlertState` class with a 5-minute escalation window that doubles the pattern when the same failure recurs
- Added five distinct failure alert functions at 330 Hz (`beep_service_crash`, `beep_i2c_lockup`, `beep_watchdog_miss`, `beep_ffmpeg_stall`, `beep_service_recovered`) with boot grace period suppression
- Wrote 12 passing tests covering tone patterns, escalation logic, and grace period behaviour

## Task Commits

Each task was committed atomically:

1. **Task 1: Harden systemd unit and add buzzer alert patterns** — `d72f4be` (feat)
2. **Task 2: Tests for systemd unit file and buzzer alert patterns** — `191e63f` (test)

**Plan metadata:** (final docs commit — see below)

## Files Created/Modified

- `systemd/shitbox-telemetry.service` — WatchdogSec=10, StartLimitIntervalSec=0 added
- `src/shitbox/capture/buzzer.py` — BuzzerAlertState, set_boot_start_time(), _should_alert(), five beep_* alert functions
- `tests/test_watchdog.py` — configparser-based assertions on systemd unit file values
- `tests/test_buzzer_alerts.py` — tone pattern, escalation, and grace period tests

## Decisions Made

- **WatchdogSec=10**: Matches the `RuntimeWatchdogSec=10` to be deployed to the Pi via `/etc/systemd/system.conf.d/watchdog.conf`. The existing engine `_notify_systemd(WATCHDOG=1)` loop already pets at a compatible interval.
- **StartLimitIntervalSec=0**: Prevents systemd from permanently blocking restarts after rapid crash loops (the default 5-in-10s limit). This is the correct setting for an always-on embedded system.
- **Escalation via list concatenation**: The plan explicitly prohibits using `PiicoDev_Buzzer.volume()` as it may not be available on all firmware versions. Playing the pattern twice is a firmware-safe equivalent.
- **Module-level boot start time**: `set_boot_start_time()` stores a `float` at module level so alert functions can check elapsed time without needing to pass engine context.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `BuzzerAlertState` and all five alert functions are ready for the `HealthMonitor` to call in Phase 2 Plan 02
- The engine needs to call `set_boot_start_time(time.time())` early in `UnifiedEngine.start()` — this wiring should be added in Phase 2 Plan 02 when HealthMonitor is integrated
- Systemd unit changes take effect on next `systemctl daemon-reload && systemctl restart shitbox-telemetry` on the Pi

---

*Phase: 02-watchdog-and-self-healing*
*Completed: 2026-02-25*

## Self-Check: PASSED

- systemd/shitbox-telemetry.service: FOUND
- src/shitbox/capture/buzzer.py: FOUND
- tests/test_watchdog.py: FOUND
- tests/test_buzzer_alerts.py: FOUND
- Commit d72f4be: FOUND
- Commit 191e63f: FOUND
