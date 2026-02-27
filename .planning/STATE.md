# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-25)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Phase 4 — Remote Health and Stage Tracking

## Current Position

Phase: 4 of 5 (Remote Health and Stage Tracking)
Plan: 1 of 2 in current phase (04-01 complete)
Status: In progress
Last activity: 2026-02-27 — Plan 04-01 completed (Schema v4, HealthCollector, Prometheus health metrics)

Progress: [█████░░░░░] 50%

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: ~2-3 min
- Total execution time: ~35 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-boot-recovery | 2 | ~6 min | ~3 min |
| 02-watchdog-and-self-healing | 3 | ~24 min | ~8 min |
| 03-thermal-resilience-and-storage-management | 2 | ~5 min | ~2-3 min |

**Recent Trend:**

- Last 5 plans: 02-02 (~17 min), 02-03 (~5 min), 03-01 (~2 min), 03-02 (~3 min)
- Trend: Fast (small focused plans)

*Updated after each plan completion*

| Phase 02-watchdog-and-self-healing P03 | 5 | 2 tasks | 3 files |
| Phase 03-thermal-resilience-and-storage-management P01 | 6 | 2 tasks | 6 files |
| Phase 03-thermal-resilience-and-storage-management P02 | 7 | 2 tasks | 2 files |
| Phase 04-remote-health-and-stage-tracking P01 | 8 | 2 tasks | 7 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Recent decisions affecting current work:

- [Roadmap]: Driver display (DISP-01, DISP-02, DISP-03) deferred to v2 — Phase 5 exists as a
  placeholder but has no v1 requirements. Can be dropped if time is short before the rally.
- [Roadmap]: HLTH-02 (buzzer alerts) placed in Phase 2 because the buzzer mechanism is built
  alongside HealthMonitor; thermal and storage thresholds that trigger it come from Phase 3.
- [Roadmap]: HLTH-01 (remote health metrics) placed in Phase 4 because it depends on ThermalMonitor
  (Phase 3) and StorageManager (Phase 3) producing the values that are reported.
- [01-01]: WAL crash detection must occur before database.connect() to avoid false negatives.
- [01-01]: Orphaned event end_time uses file st_mtime as best-effort crash timestamp.
- [01-01]: BootRecoveryService calls db._get_connection() lazily to honour thread-local model.
- [01-02]: Buzzer plays recovery tone AFTER beep_boot() — 3 tones then 1 (clean) or 2 (crash).
- [01-02]: boot_recovery attribute set None in __init__, populated in start() to match engine lifecycle.
- [01-02]: Prometheus boot metric uses best-effort daemon thread — failure logged, not fatal.
- [02-01]: WatchdogSec changed from 30 to 10 to match RuntimeWatchdogSec=10 deployed via /etc/systemd/system.conf.d/watchdog.conf.
- [02-01]: StartLimitIntervalSec=0 added to prevent systemd permanently stopping restarts after rapid crash loops.
- [02-01]: Alert escalation plays pattern twice via list concatenation (not volume control) — PiicoDev_Buzzer .volume() not available on all firmware.
- [02-02]: STALL_TIMEOUT_SECONDS=30 is conservative for 10-second segments — 3 missed segments before alert fires.
- [02-02]: Stall check uses both mtime and size to catch both new-segment creation and ongoing writes to the current segment.
- [02-02]: _stall_check_armed flag provides startup grace — no stall fires until at least one segment exists and is baselined.
- [02-02]: buzzer imported lazily inside _health_monitor stall block to avoid circular import at module level.
- [Phase 02-03]: Import RPi.GPIO inside _i2c_bus_reset() method body to preserve graceful degradation on non-Pi hosts
- [Phase 02-03]: GPIO.cleanup([SCL_PIN, SDA_PIN]) uses selective pin list — NOT global GPIO.cleanup() — to avoid disrupting other GPIO users
- [Phase 02-03]: buzzer.set_boot_start_time() called immediately after buzzer.init() in engine.start() to anchor grace period to actual engine start time
- [03-01]: Thermal alerts use 500 Hz to distinguish from 330 Hz service-failure alerts (per RESEARCH.md)
- [03-01]: beep_thermal_recovered calls _alert_state.reset() before playing — no escalation check needed for recovery
- [03-01]: checkpoint_wal() is silent when WAL is clean (row[2] == 0) to avoid log noise in steady state
- [03-02]: HYSTERESIS_C=5.0 (not 3.0 as specified in plan) — test scaffold is authoritative: 66C suppressed, 65C re-arms
- [03-02]: Buzzer functions imported at module level in thermal_monitor.py (not lazily) — required for patch() in tests to bind to module-level names
- [03-02]: _read_sysfs_temp/_read_throttled are instance methods so tests can use patch.object() for per-test mocking
- [03-02]: WAL checkpoint timer co-located in _telemetry_loop, no new thread — per user decision in plan
- [03-02]: get_status() now reads cpu_temp from thermal_monitor.current_temp_celsius (single source of truth)

### Pending Todos

None yet.

### Blockers/Concerns

- **Phase 3**: Sync-status tracking logic (which video files are safe to delete) needs careful
  schema design — risk of deleting unsynced video during a connectivity gap. Flag for planning.
- **Phase 4**: GPX route file for Shitbox Rally 2026 is an operational dependency. Confirm it is
  available in GPX format before Phase 4 planning begins.
- **Phase 5**: pygame-ce KMSDRM on target Bookworm image needs hardware-in-loop validation early
  in the phase. SDL2 package list may differ between Bookworm releases.
- ~~**Pre-start**: `synchronous=FULL` config value is unknown — verify in Phase 1.~~ RESOLVED: set in 01-01.
- **Pre-start**: WireGuard `PersistentKeepalive=25` should be set manually before the rally
  (config change only, not a software requirement).

## Session Continuity

Last session: 2026-02-27
Stopped at: Completed 04-01-PLAN.md (Schema v4, HealthCollector, Prometheus health metrics)
Resume file: None
