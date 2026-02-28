# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-28)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Milestone v1.1 — Field-Test Hardening

## Current Position

Phase: Not started (roadmap pending)
Plan: —
Status: Requirements defined, awaiting roadmap creation
Last activity: 2026-02-28 — Milestone v1.1 started (field-test hardening)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity (v1.0):**

- Total plans completed: 9
- Average duration: ~2-3 min
- Total execution time: ~41 min

## Accumulated Context

### Decisions

- [v1.1]: batch_sync.py already updated with retry logic for "too old" rejections (MAX_TOO_OLD_RETRIES=20)
- [v1.1]: Prometheus outOfOrderTimeWindow=168h IS in config YAML but may not apply to remote-write-receiver path
- [v1.1]: Labels in batch_sync.py use `job: shitbox-mqtt-exporter` — potential conflict with scrape job of same name
- [v1.1]: USB speaker volume capped at 75% to prevent USB power contention causing xHCI errors
- [v1.1]: Event suppression is by design — consecutive auto events extend capture window, not separate videos

### Pending Todos

- Deploy batch_sync.py retry logic to Pi
- Investigate Prometheus scrape job label conflict
- Get full logs from test drive for video/timelapse diagnosis

### Blockers/Concerns

- **Prometheus**: The "too old" rejection root cause is still unclear — config shows 168h window but
  samples 49 minutes old are rejected. Possible label conflict with a scrape job using the same
  `job` label as batch sync.
- **Video captures**: Need test drive logs to determine if events were suppressed, ffmpeg stalled,
  or save_event failed.
- **TTS**: Intermittent silence could be USB power, queue overflow, or worker thread crash.

## Session Continuity

Last session: 2026-02-28
Stopped at: Milestone v1.1 requirements defined, roadmap creation pending
Resume file: None
