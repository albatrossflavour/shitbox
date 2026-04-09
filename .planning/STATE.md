---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Rally Ready
status: ready_to_plan
stopped_at: Roadmap created — 7 phases defined (12-18), 28 requirements mapped
last_updated: "2026-04-09"
last_activity: 2026-04-09
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-09)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** v2.0 Rally Ready — Phase 12 ready to plan

## Current Position

Phase: 12 of 18 (Schema Foundation and Logbook API)
Plan: — (not yet planned)
Status: Ready to plan
Last activity: 2026-04-09 — v2.0 roadmap created, 28 requirements mapped across phases 12-18

Progress: [░░░░░░░░░░] 0% (v2.0)

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

### Known Constraints for v2.0

- Phase 17 (Driver Display) depends on Phase 13 (active driver in SSE) and Phase 15 (undervoltage alerts)
- Phase 18 (Website) depends on Phase 12 (notes/fuel in sync payload) and Phase 13 (driver data)
- Phase 18 is in a separate repo (home-ops) and deploys via Flux — not the shitbox repo
- PWR-01 bitmask fix: read bits 0-3 only for current undervoltage, never bits 16-19 (sticky historical)
- CAL-01/CAL-02 can run in parallel with Phases 12-13 but must complete before Phase 17 is relied on for accuracy

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-09
Stopped at: v2.0 roadmap created. Run /gsd:plan-phase 12 to start.
Resume file: None
