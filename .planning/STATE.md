# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Milestone v1.1 — Phase 7: Self-Healing and Crash-Loop Prevention

## Current Position

Phase: 7 of 9 (Self-Healing and Crash-Loop Prevention)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-02-28 — v1.1 roadmap created (Phases 7-9)

Progress: [##########░░░░░░░░░░] v1.0 complete, v1.1 0%

## Performance Metrics

**Velocity (v1.0):**

- Total plans completed: 9 (v1.0) + 2 (v1.0 wiring) = 11
- Average duration: ~2-3 min
- Total execution time: ~41 min

## Accumulated Context

### Decisions

- [v1.1]: batch_sync.py already updated with retry logic for "too old" rejections (MAX_TOO_OLD_RETRIES=20)
- [v1.1]: Prometheus outOfOrderTimeWindow=168h IS in config YAML but may not apply to remote-write-receiver path
- [v1.1]: Labels in batch_sync.py use `job: shitbox-mqtt-exporter` — potential conflict with scrape job of same name
- [v1.1]: USB speaker volume capped at 75% to prevent USB power contention causing xHCI errors
- [v1.1]: Event suppression is by design — consecutive auto events extend capture window, not separate videos
- [v1.1]: Crash-looping is the root cause — fix I2C escalation first (Phase 7), then capture/sync

### Pending Todos

- Deploy batch_sync.py retry logic to Pi
- Investigate Prometheus scrape job label conflict
- Get full logs from test drive for video/timelapse diagnosis

### Field Test Findings (2026-02-28)

- **Crash-looping is root cause** — Jan 28 had ~8 PIDs in 12 min, Feb 28 had ~7 PIDs in 3 min
- **Videos save fine when stable** — PID 1099 session: 5/5 saves completed (37-39MB each)
- **Timelapse extraction fails on corrupt segments** after crash-loop
- **Boot event fires before ffmpeg ready** — video_save_pre_segments count=0
- **Prometheus**: samples 49 min old rejected despite outOfOrderTimeWindow=168h
- **TTS**: Intermittent silence — USB power, queue overflow, or worker thread crash

### Blockers/Concerns

- **Priority #1**: I2C crash-loop escalation (Phase 7 addresses this)
- **Prometheus**: Scrape job label conflict may cause "too old" rejection (Phase 9)
- **TTS**: Need targeted logging to diagnose intermittent failures (Phase 7)

## Session Continuity

Last session: 2026-02-28
Stopped at: v1.1 roadmap created, ready to plan Phase 7
Resume file: None
