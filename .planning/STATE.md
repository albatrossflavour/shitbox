# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-25)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Phase 1 — Boot Recovery

## Current Position

Phase: 1 of 5 (Boot Recovery)
Plan: 1 of TBD in current phase
Status: In progress
Last activity: 2026-02-25 — Plan 01-01 completed (BOOT-01, BOOT-02, BOOT-03)

Progress: [█░░░░░░░░░] 10%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

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

Last session: 2026-02-25
Stopped at: Completed 01-01-PLAN.md (BootRecoveryService, synchronous=FULL, close_orphaned_events)
Resume file: None
