---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: — Operational Hardening
status: executing
stopped_at: Completed 10-04-PLAN.md
last_updated: "2026-04-08T23:46:28.907Z"
last_activity: 2026-04-08
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 21
  completed_plans: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Phase 10 — live-dashboard-with-offline-map

## Current Position

Phase: 10 (live-dashboard-with-offline-map) — EXECUTING
Plan: 4 of 6
Status: Ready to execute
Last activity: 2026-04-08

Progress: [###############░░░░░] v1.0 complete, v1.1 Phase 7 complete, Phase 8 complete

## Performance Metrics

**Velocity (v1.0):**

- Total plans completed: 9 (v1.0) + 2 (v1.0 wiring) = 11
- Average duration: ~2-3 min
- Total execution time: ~41 min

**v1.1 Phase 8:**

| Phase | Plan | Duration | Tasks | Files |
| ----- | ---- | -------- | ----- | ----- |
| 08    | 01   | ~3 min   | 2     | 3     |
| 08    | 02   | ~3 min   | 3     | 3     |
| Phase 10 P01 | ~2 min | 3 tasks | 5 files |
| Phase 10 P00 | 8min | 3 tasks | 3 files |
| Phase 10-live-dashboard-with-offline-map P03 | 25min | 3 tasks | 5 files |
| Phase 10-live-dashboard-with-offline-map P04 | ~12 min | 3 tasks | 9 files |

## Accumulated Context

### Decisions

- [v1.1]: batch_sync.py already updated with retry logic for "too old" rejections (MAX_TOO_OLD_RETRIES=20)
- [v1.1]: Prometheus outOfOrderTimeWindow=168h IS in config YAML but may not apply to remote-write-receiver path
- [v1.1]: Labels in batch_sync.py use `job: shitbox-mqtt-exporter` — potential conflict with scrape job of same name
- [v1.1]: USB speaker volume capped at 75% to prevent USB power contention causing xHCI errors
- [v1.1]: Event suppression is by design — consecutive auto events extend capture window, not separate videos
- [v1.1]: Crash-looping is the root cause — fix I2C escalation first (Phase 7), then capture/sync
- [07-01]: _reset_count resets in stop() so engine health check's stop()/start() cycle gives restarted sampler fresh escalation state
- [07-01]: start() escalation calls _i2c_bus_reset() (not setup()) — _i2c_bus_reset already calls setup() internally; double-call avoided
- [07-02]: Speaker reinit guarded by _voice is not None AND _worker is not None — avoids spurious
  reinit when speaker was never initialised, and AttributeError after cleanup() zeroed worker ref

- [07-02]: Recovery confirmation (TTS + buzzer) fires at shared if recovered: block — DRY and covers
  all subsystems (IMU, telemetry, video, GPS, speaker)

- [08-01]: beep_capture_failed uses 440→330 Hz descending pair to distinguish from beep_ffmpeg_stall (330 Hz only)
- [08-01]: speak_capture_failed guards _voice is None first then _should_alert() — consistent with speak_* pattern
- [08-01]: RED-phase tests written for _do_save_event, _check_timelapse, and _on_event; all 10 will fail until Plan 02
- [Phase 08-02]: TIMELAPSE_GAP_FACTOR referenced as UnifiedEngine.TIMELAPSE_GAP_FACTOR — MagicMock(spec=) does not expose class constants as real values
- [Phase 08-02]: Alert calls wrapped in try/except in _do_save_event — buzzer/speaker failures never prevent callback from firing
- [Phase 08-02]: Boot guard calls event_storage.save_event() before early return — boot event metadata always persisted even when video skipped

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

### Roadmap Evolution

- Phase 10 added: Live Dashboard with offline map (in-process FastAPI in UnifiedEngine, SSE telemetry stream, single-file Alpine+Tailwind+Leaflet frontend, offline CartoDB MBTiles for the rally route corridor, no auth, listens on localhost + Pi LAN IPs, served to Chromium kiosk on the Pi)

### Blockers/Concerns

- **Prometheus**: Scrape job label conflict may cause "too old" rejection (Phase 9)
- Pre-existing mypy errors in sampler.py (_bus typed as None vs Optional[SMBus]) — deferred

## Session Continuity

Last session: 2026-04-08T23:46:28.904Z
Stopped at: Completed 10-04-PLAN.md
Resume file: None
