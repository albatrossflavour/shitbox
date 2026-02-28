# Roadmap: Shitbox Rally Telemetry — Hardening Milestone

## Overview

This roadmap hardens the existing Shitbox telemetry system for the Shitbox Rally: 4,000 km from
Port Douglas to Melbourne across remote Australia in a 2001 Ford Laser. The existing architecture
(SQLite WAL, 100 Hz IMU, batch Prometheus sync, event-triggered video) is sound.

**v1.0 (Phases 1-5)** delivered operational hardening: boot recovery, watchdog, thermal resilience,
remote health, stage tracking, and audio alerts. Phase 6 (Driver Display) is deferred to v2.

**v1.1 (Phases 7-9)** addresses field-test failures discovered during the first test drive. The
root cause of most failures is crash-looping from I2C bus lockups — each restart kills in-progress
video saves, resets timelapse state, and loses sync progress. Phase 7 fixes the crash-loop root
cause with escalating self-healing. Phase 8 hardens video capture against the remaining edge cases.
Phase 9 fixes Prometheus sync so offline data is never silently lost.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

### v1.0 — Operational Hardening (Complete)

- [x] **Phase 1: Boot Recovery** - System survives hard power cuts and starts cleanly every time
- [x] **Phase 2: Watchdog and Self-Healing** - Hardware watchdog active, all services auto-restart, known bugs fixed (completed 2026-02-25)
- [x] **Phase 3: Thermal Resilience and Storage Management** - Temperature alerts before throttle, disk never exhausts (completed 2026-02-26)
- [x] **Phase 4: Remote Health and Stage Tracking** - Crew can see system health; car knows where it is on the route (completed 2026-02-27)
- [x] **Phase 5: Audio Alerts and TTS** - USB speaker replaces buzzer with spoken alerts and contextual announcements (completed 2026-02-27)
- [ ] **Phase 6: Driver Display** - Deferred to v2

### v1.1 — Field-Test Hardening

- [ ] **Phase 7: Self-Healing and Crash-Loop Prevention** - I2C crash-loops eliminated, all subsystems follow detect-alert-recover-escalate pattern
- [ ] **Phase 8: Capture Integrity** - Video saves verified, timelapse monitored, ffmpeg crashes recovered with footage preserved
- [ ] **Phase 9: Sync Reliability** - Prometheus never loses data, cursor never advances past rejections, manual sync available

## Phase Details

<details>
<summary>v1.0 Phases 1-5 (Complete)</summary>

### Phase 1: Boot Recovery

**Goal**: System survives hard power cuts and starts cleanly after every ignition cycle
**Depends on**: Nothing (first phase)
**Requirements**: BOOT-01, BOOT-02, BOOT-03
**Success Criteria** (what must be TRUE):

1. After pulling the power cable mid-run and restarting, the system starts without manual intervention and no events are left in an open/corrupted state
2. SQLite integrity check runs on every startup after an unclean shutdown and logs the result before any other service thread starts
3. Events from a prior crash are closed and marked as interrupted — not silently dropped and not left open indefinitely
4. SQLite is configured with `synchronous=FULL` so that WAL writes are durable across hard power cuts

**Plans:** 2/2 plans executed

Plans:

- [x] 01-01-PLAN.md — Tests, synchronous=FULL, BootRecoveryService, orphan event closure
- [x] 01-02-PLAN.md — Engine wiring, buzzer patterns, OLED status, Prometheus metric

### Phase 2: Watchdog and Self-Healing

**Goal**: Hardware watchdog is active, all services restart on crash, and known data-loss bugs are fixed
**Depends on**: Phase 1
**Requirements**: WDOG-01, WDOG-02, WDOG-03, WDOG-04, HLTH-02
**Success Criteria** (what must be TRUE):

1. If a service crashes or hangs during driving, it restarts automatically within seconds without operator action
2. If the kernel hangs entirely, the BCM2835 hardware watchdog reboots the Pi within 15 seconds
3. If ffmpeg stops writing video (process alive but output stalled), the health monitor detects it and restarts ffmpeg automatically
4. If the I2C bus locks up (sensors stop responding), the system performs a 9-clock bit-bang reset and resumes sensor reads without a reboot
5. When a service failure, I2C lockup, or watchdog miss occurs, the in-car buzzer alerts the driver

**Plans:** 3/3 plans complete

Plans:

- [x] 02-01-PLAN.md — Systemd watchdog hardening (WatchdogSec=14, StartLimitIntervalSec=0) and buzzer alert patterns with escalation
- [x] 02-02-PLAN.md — ffmpeg mtime-based stall detection and auto-restart
- [x] 02-03-PLAN.md — I2C bus lockup recovery via 9-clock bit-bang reset with reboot fallback

### Phase 3: Thermal Resilience and Storage Management

**Goal**: System alerts before thermal throttle degrades IMU sampling, and the SD card never fills silently
**Depends on**: Phase 2
**Requirements**: THRM-01, THRM-02, THRM-03, STOR-01
**Success Criteria** (what must be TRUE):

1. CPU temperature is sampled every 5 seconds and the current value is available to other subsystems (health monitor, display) without each subsystem polling sysfs independently
2. When CPU temperature reaches 70C, a warning is logged and the buzzer alerts; when it reaches 80C, throttle state is logged and the buzzer alerts again
3. The `vcgencmd get_throttled` bitmask is decoded and logged at every health check interval so thermal events are visible in structured logs
4. The SQLite WAL file does not grow unboundedly — a periodic `TRUNCATE` checkpoint runs and is logged when it executes

**Plans:** 2/2 plans executed

Plans:

- [x] 03-01-PLAN.md — Test scaffolds, thermal buzzer alerts, WAL checkpoint method, health package
- [x] 03-02-PLAN.md — ThermalMonitorService implementation and engine wiring

### Phase 4: Remote Health and Stage Tracking

**Goal**: Crew at home can see system health during connectivity windows; the car knows its position on the rally route
**Depends on**: Phase 3
**Requirements**: HLTH-01, STGE-01, STGE-02, STGE-03
**Success Criteria** (what must be TRUE):

1. When WireGuard connectivity is available, CPU temperature, disk usage percentage, Prometheus sync backlog, and throttle state appear as metrics in Grafana
2. The system accumulates GPS distance driven as a running total (odometer) that persists across reboots
3. The system tracks distance driven today, resetting correctly on a new driving day
4. Given a waypoint-based rally route in YAML config, the system tracks stage progress (waypoints reached within 5 km, day labels) and makes that data available to other subsystems

**Plans:** 2/2 plans complete

Plans:

- [ ] 04-01-PLAN.md — Schema v4 migration, HealthCollector, batch_sync health metrics (HLTH-01)
- [ ] 04-02-PLAN.md — Config dataclasses, GPS distance tracking, waypoint detection (STGE-01/02/03)

### Phase 5: Audio Alerts and TTS

**Goal**: USB speaker provides spoken alerts and contextual announcements, replacing buzzer tone patterns as the primary audio output
**Depends on**: Phase 4
**Requirements**: AUDIO-01, AUDIO-02, AUDIO-03
**Success Criteria** (what must be TRUE):

1. The USB speaker is detected and configured as the audio output device, with buzzer as fallback if speaker is unavailable
2. Piper TTS generates natural-sounding spoken messages for all alert types previously handled by buzzer tones
3. Contextual announcements fire for system events: boot ready, thermal warnings, waypoint reached, periodic distance updates, and recovery confirmations
4. Audio playback does not block the main engine thread or interfere with 100 Hz IMU sampling

**Plans:** 2/2 plans complete

Plans:

- [ ] 05-01-PLAN.md — Speaker module, SpeakerConfig, USB detection, TTS enqueue, unit tests (AUDIO-01, AUDIO-02)
- [ ] 05-02-PLAN.md — Engine and thermal monitor wiring, waypoint and distance announcements (AUDIO-03)

</details>

### Phase 6: Driver Display (Deferred to v2)

**Goal**: Driver can see speed, heading, trip distance, stage progress, and system health on the 7" screen without touching anything
**Depends on**: Phase 5
**Requirements**: (v2 scope — DISP-01, DISP-02, DISP-03 deferred)
**Success Criteria** (what must be TRUE):

1. The 7" Pi screen shows current speed and heading in large readable type at 10 Hz without interfering with the 100 Hz IMU sampler
2. Trip stats (distance today, total distance) update on screen as the car moves
3. System health badges (storage %, GPS lock, sync status, thermal state) are visible on screen and update without driver interaction
4. If the display process crashes, the engine continues capturing data — the display failure is isolated and does not affect telemetry

**Plans**: TBD

### Phase 7: Self-Healing and Crash-Loop Prevention

**Goal**: The system stops crash-looping from I2C failures and all subsystems follow a consistent detect-alert-recover-escalate pattern
**Depends on**: Phase 5 (builds on existing watchdog and TTS infrastructure)
**Requirements**: HEAL-01, HEAL-02, HEAL-03
**Success Criteria** (what must be TRUE):

1. When the I2C bus locks up repeatedly, the system escalates through multiple reset attempts before falling back to a controlled reboot — it never enters a tight crash-loop that kills other subsystems
2. When the TTS speaker stops producing audio (USB disconnect, worker thread crash, or queue overflow), the system detects the silence within 30 seconds and re-initialises the speaker subsystem automatically
3. Every self-healing subsystem (I2C, TTS, ffmpeg) follows the same pattern: detect failure, log structured event, alert via available audio, attempt recovery, escalate if recovery fails
4. After a self-healing recovery event, the system announces the recovery via TTS (or buzzer fallback) so the driver knows it happened

**Plans:** 1/2 plans executed

Plans:

- [ ] 07-01-PLAN.md — Escalating I2C bus recovery with counter, backoff, and startup protection (HEAL-02, HEAL-03)
- [ ] 07-02-PLAN.md — Speaker worker watchdog in health check and recovery confirmation announcements (HEAL-01, HEAL-03)

### Phase 8: Capture Integrity

**Goal**: Video captures are verified after save, timelapse gaps are detected and recovered, and ffmpeg crashes during active events preserve whatever footage was captured
**Depends on**: Phase 7 (stable system reduces crash-induced capture failures)
**Requirements**: CAPT-01, CAPT-02, CAPT-03
**Success Criteria** (what must be TRUE):

1. After every video save completes, the system verifies the MP4 file exists and has non-zero size — if the file is missing or empty, an error is logged and the save is retried from available segments
2. If no timelapse frame has been captured within the expected interval, the system logs a warning and attempts to restart timelapse extraction without losing future frames
3. When ffmpeg crashes or stalls during an active event recording, the system recovers and produces a valid MP4 from whatever segments were captured before the crash — partial footage is preserved, not discarded
4. Boot events that fire before ffmpeg is ready do not attempt a video save with zero segments — the system waits for capture readiness or skips the video gracefully

**Plans**: TBD

### Phase 9: Sync Reliability

**Goal**: Prometheus sync never silently loses data, cursor management is safe, and the operator can force a sync when connectivity is available
**Depends on**: Phase 7 (stable system prevents sync interruption from crash-loops)
**Requirements**: SYNC-01, SYNC-02, SYNC-03
**Success Criteria** (what must be TRUE):

1. When Prometheus rejects a batch of samples (HTTP 400, "too old", or any non-success response), the cursor does not advance past those samples — they remain in SQLite for retry
2. After repeated rejections of the same batch (e.g. label conflict), the system eventually skips forward with a structured log entry recording exactly which samples were abandoned and why
3. Offline telemetry data collected hours or days ago is accepted by Prometheus — the "too old" rejection is resolved (whether by fixing label conflicts, adjusting Prometheus config, or both)
4. The operator can trigger a manual sync of all pending data via a script or signal (e.g. `systemctl kill -s SIGUSR1 shitbox-telemetry` or a helper script)

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 through 5 (complete), then 7, 8, 9. Phase 6 deferred to v2.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Boot Recovery | v1.0 | 2/2 | Complete | 2026-02-25 |
| 2. Watchdog and Self-Healing | v1.0 | 3/3 | Complete | 2026-02-25 |
| 3. Thermal Resilience and Storage Management | v1.0 | 2/2 | Complete | 2026-02-26 |
| 4. Remote Health and Stage Tracking | v1.0 | 2/2 | Complete | 2026-02-27 |
| 5. Audio Alerts and TTS | v1.0 | 2/2 | Complete | 2026-02-27 |
| 6. Driver Display | v2 | 0/TBD | Deferred | - |
| 7. Self-Healing and Crash-Loop Prevention | 1/2 | In Progress|  | - |
| 8. Capture Integrity | v1.1 | 0/TBD | Not started | - |
| 9. Sync Reliability | v1.1 | 0/TBD | Not started | - |
