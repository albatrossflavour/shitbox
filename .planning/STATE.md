---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: — Rally Ready
status: executing
stopped_at: Completed 12-04-PLAN.md — engine wiring and dashboard modals
last_updated: "2026-04-09T12:38:33.707Z"
last_activity: 2026-04-09
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 4
  completed_plans: 4
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-09)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Phase 12 — schema-foundation-and-logbook-api

## Current Position

Phase: 12 (schema-foundation-and-logbook-api) — COMPLETE
Plan: 4 of 4
Status: Complete
Last activity: 2026-04-09

Progress: [██████████] 100% (v2.0, 4/4 plans in phase 12)

v1.0 shipped: 9 phases, 27 plans, 2026-04-09

## Accumulated Context

### Decisions (carry-forward from v1.0)

- Offline-first SQLite with WAL — confirmed correct, never changing
- Batch sync over WireGuard — confirmed working (1,288 readings synced in 281ms in field test)
- Piper TTS over buzzer — confirmed better in car
- Escalating I2C reset (backoff before reboot) — eliminated crash-loops
- In-process FastAPI dashboard — no process coordination overhead, SSE clean
- LSM6DSOX+LIS3MDL now the active IMU pair on Pi 5 v2 hat
- DS18B20 probe IDs: exterior=28-00000024263a, engine_bay=28-0000002405b1
- SEN0460 (PM2.5) and INA226 default disabled — enable via config when wired
- Pi 5 IP: 10.10.20.107
- All new v2.0 tables (notes, fuel_stops, driver_stints, calibration) go into telemetry.db — no separate databases
- Touchscreen OSK deferred — USB keyboard required (Wayland/Chromium OSK unreliable on Pi 5)
- Cost data hard exclusion: fuel cost must never appear in sync payloads or on the website
- Plan 12-01: cost_aud stored in fuel_stops (nullable) but excluded from sync payloads at API layer (plan 12-02)
- Plan 12-01: no indexes added on notes/fuel_stops — low-write tables, add later if query patterns demand
- Plan 12-02: snapshot_fn injected into LogbookStorage for testability without hardware dependency
- Plan 12-02: generate_fuel_json enforces cost_aud exclusion at SQL SELECT level, not post-processing (D-10)
- Plan 12-04: LogbookStorage registered unconditionally in UnifiedEngine.__init__ — cheap, REST-only, idempotent; generators guarded on capture_sync not None
- Plan 12-04: gps_state.update_last_known_position co-located with existing lat/lng not-None guard in _record_telemetry

### Known Constraints for v2.0

- Phase 17 (Driver Display) depends on Phase 13 (active driver in SSE) and Phase 15 (undervoltage alerts)
- Phase 18 (Website) depends on Phase 12 (notes/fuel in sync payload) and Phase 13 (driver data)
- Phase 18 is in a separate repo (home-ops) and deploys via Flux — not the shitbox repo
- PWR-01 bitmask fix: read bits 0-3 only for current undervoltage, never bits 16-19 (sticky historical)
- CAL-01/CAL-02 can run in parallel with Phases 12-13 but must complete before Phase 17 is relied on for accuracy

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-09T12:38:33.705Z
Stopped at: Completed 12-04-PLAN.md — engine wiring and dashboard modals
Resume file: None
