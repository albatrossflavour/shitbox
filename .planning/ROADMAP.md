# Roadmap: Shitbox Rally Telemetry — Hardening Milestone

## Overview

This roadmap hardens the existing Shitbox telemetry system for the Shitbox Rally: 4,000 km from
Port Douglas to Melbourne across remote Australia in a 2001 Ford Laser. The existing architecture
(SQLite WAL, 100 Hz IMU, batch Prometheus sync, event-triggered video) is sound. What it lacks is
the operational hardening to survive twenty hard power cuts per day, 50°C cabin temperatures, zero
mobile coverage for 12-hour stretches, and ten consecutive driving days without human intervention.
Five sequential phases deliver that hardening. Each phase enables the next. Boot recovery comes
first because it protects data integrity before any new complexity is added. Driver display comes
last because it consumes all state produced by earlier phases and can be deferred without impacting
data capture if time runs short before departure.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Boot Recovery** - System survives hard power cuts and starts cleanly every time
- [ ] **Phase 2: Watchdog and Self-Healing** - Hardware watchdog active, all services auto-restart, known bugs fixed
- [ ] **Phase 3: Thermal Resilience and Storage Management** - Temperature alerts before throttle, disk never exhausts
- [ ] **Phase 4: Remote Health and Stage Tracking** - Crew can see system health; car knows where it is on the route
- [ ] **Phase 5: Driver Display** - Speed, heading, trip progress, and system health on 7" screen

## Phase Details

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

**Plans**: TBD

### Phase 3: Thermal Resilience and Storage Management

**Goal**: System alerts before thermal throttle degrades IMU sampling, and the SD card never fills silently
**Depends on**: Phase 2
**Requirements**: THRM-01, THRM-02, THRM-03, STOR-01
**Success Criteria** (what must be TRUE):

1. CPU temperature is sampled every 5 seconds and the current value is available to other subsystems (health monitor, display) without each subsystem polling sysfs independently
2. When CPU temperature reaches 70°C, a warning is logged and the buzzer alerts; when it reaches 80°C, throttle state is logged and the buzzer alerts again
3. The `vcgencmd get_throttled` bitmask is decoded and logged at every health check interval so thermal events are visible in structured logs
4. The SQLite WAL file does not grow unboundedly — a periodic `TRUNCATE` checkpoint runs and is logged when it executes

**Plans**: TBD

### Phase 4: Remote Health and Stage Tracking

**Goal**: Crew at home can see system health during connectivity windows; the car knows its position on the rally route
**Depends on**: Phase 3
**Requirements**: HLTH-01, STGE-01, STGE-02, STGE-03
**Success Criteria** (what must be TRUE):

1. When WireGuard connectivity is available, CPU temperature, disk usage percentage, Prometheus sync backlog, and throttle state appear as metrics in Grafana
2. The system accumulates GPS distance driven as a running total (odometer) that persists across reboots
3. The system tracks distance driven today, resetting correctly on a new driving day
4. Given a GPX file of the rally route, the system calculates percentage of route complete and kilometres remaining, and makes that data available to other subsystems

**Plans**: TBD

### Phase 5: Driver Display

**Goal**: Driver can see speed, heading, trip distance, stage progress, and system health on the 7" screen without touching anything
**Depends on**: Phase 4
**Requirements**: (v2 scope — DISP-01, DISP-02, DISP-03 deferred)
**Success Criteria** (what must be TRUE):

1. The 7" Pi screen shows current speed and heading in large readable type at 10 Hz without interfering with the 100 Hz IMU sampler
2. Trip stats (distance today, total distance) update on screen as the car moves
3. System health badges (storage %, GPS lock, sync status, thermal state) are visible on screen and update without driver interaction
4. If the display process crashes, the engine continues capturing data — the display failure is isolated and does not affect telemetry

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Boot Recovery | 2/2 | Complete | 2026-02-25 |
| 2. Watchdog and Self-Healing | 0/TBD | Not started | - |
| 3. Thermal Resilience and Storage Management | 0/TBD | Not started | - |
| 4. Remote Health and Stage Tracking | 0/TBD | Not started | - |
| 5. Driver Display | 0/TBD | Not started | - |
