---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: TBD
status: planning
stopped_at: v1.0 Operational Hardening milestone complete — clean slate for v2
last_updated: "2026-04-09"
last_activity: 2026-04-09
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-09)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Planning v2.0 milestone

## Current Position

Phase: None (between milestones)
Status: Ready to plan v2.0
Last activity: 2026-04-09

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

### Known Issues to Consider for v2

- HLTH-01: CPU temp/disk/sync metrics to Prometheus — implemented but not confirmed working end-to-end in production
- Prometheus scrape job label conflict (`job: shitbox-mqtt-exporter`) may cause metric collisions
- Pre-existing mypy errors in sampler.py (`_bus` typed as None vs Optional[SMBus]) — deferred

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-09
Stopped at: v1.0 milestone complete. Run /gsd:new-milestone to start v2 planning.
Resume file: None
