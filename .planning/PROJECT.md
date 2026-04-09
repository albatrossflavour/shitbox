# Shitbox Rally Telemetry

## What This Is

An offline-first rally car telemetry system for a 2001 Ford Laser competing in the Shitbox Rally (Port Douglas to Melbourne). It captures high-rate IMU data (LSM6DSOX, 100 Hz), GPS position, environment sensors (DS18B20 temps, VEML7700 lux, INA226 power), and video on a Raspberry Pi 5, stores everything locally in SQLite, and batch-syncs to Prometheus and a public website when mobile connectivity is available. A live in-process dashboard (FastAPI + SSE + MBTiles) serves telemetry to the Pi's Chromium kiosk and phones on rally wifi. The rally is a fundraising event (Cancer Council), so reliable data capture and public engagement both matter.

## Core Value

Never lose telemetry data or video — the system must survive thousands of kilometres of rough roads, power cycles, heat, and vibration without human intervention.

## Requirements

### Validated — v1.0

- ✓ Bulletproof boot recovery — WAL crash detection, orphan event closure, `synchronous=FULL` — v1.0
- ✓ Hardware watchdog active, all services auto-restart, ffmpeg stall detection — v1.0
- ✓ Thermal monitor (70/80°C alerts, throttle decode, WAL TRUNCATE checkpoint) — v1.0
- ✓ Stage tracking (GPS odometer, daily distance, waypoint detection) — v1.0
- ✓ USB speaker with Piper TTS replacing buzzer tones — contextual spoken alerts — v1.0
- ✓ Escalating I2C crash-loop prevention (3-attempt backoff before reboot) — v1.0
- ✓ Speaker worker watchdog with auto-reinit — v1.0
- ✓ Capture integrity: post-save MP4 verification, timelapse gap watchdog, boot save guard — v1.0
- ✓ Live dashboard: FastAPI + three SSE streams + MBTiles offline map + Alpine/Tailwind/Leaflet — v1.0
- ✓ V2 sensor stack: LSM6DSOX+LIS3MDL IMU, DS18B20 dual-probe, VEML7700, INA226 — v1.0
- ✓ High-rate IMU at 100 Hz with event detection (hard brake, big corner, high G, rough road) — existing
- ✓ GPS position, speed, and heading at 1 Hz — existing
- ✓ Offline-first SQLite with WAL mode — existing
- ✓ Cursor-based batch sync to Prometheus over WireGuard — existing
- ✓ Event-triggered and manual video capture with pre-event ring buffer — existing
- ✓ Capture sync to NAS via rsync — existing
- ✓ Public website (shit-of-theseus.com) with events, map, video, Grafana dashboard — existing

### Known Gaps from v1.0

- HLTH-01: System publishes CPU temp, disk %, sync backlog to Prometheus — implemented in HealthCollector but not confirmed working end-to-end in production
- SYNC-01/02/03: Prometheus sync reliability (dropped from v1.0; field test confirmed sync is working, cursor-safe rejection was already implemented)

### Active — v2.0

- DISP-01: Driver display productionised on 7" touchscreen (speed, G-force, map, temps, event ticker, alerts)
- NOTE-01: Field notes entry from Pi (freeform or pinned to event, auto DTS + GPS, syncs to website)
- FUEL-01: Refueling log (volume, location per stop, efficiency tracking, location + efficiency on website)
- ✓ DRVR-01: Driver tracking — who's driving interface, time/percentage per driver, event attribution — Validated in Phase 13: driver-tracking
- ✓ DRVR-02: Dashboard driver switcher, stats modal, SSE live-update, event attribution — Validated in Phase 13: driver-tracking
- WEB-01: Website revamp — improved Grafana graphs, integrate blog/refuel/driver data streams
- VID-01: ELP 4K video capture tuning — calibrate settings for actual mounted camera
- CAL-01: Sensor calibration — validate all sensors stationary + in-motion
- PWR-01: Undervoltage resolution — confirm hardware fix, software detection + alerting
- MON-01: Monitoring completeness — close HLTH-01, fix Prometheus scrape label conflict, critical events on UI

### Out of Scope

- OBD / ECU data — 2001 Ford Laser is OBD-I only, no practical interface
- Mobile app — web UI on Pi dashboard and website are sufficient
- Real-time video streaming — connectivity too sparse; batch sync is the right model
- Read-only OS filesystem (overlayfs) — incompatible with SQLite WAL data writes
- AI/ML event classification — unnecessary complexity for rally use case
- Automatic OTA updates — too risky for a multi-day rally in remote areas
- MQTT — Prometheus path is sufficient; MQTT adds duplicate metrics

## Context

- The rally runs from Port Douglas (Far North Queensland) to Melbourne — roughly 4,000+ km through remote and regional Australia
- Mobile connectivity will be intermittent at best; long stretches with no signal
- The car is a 2001 Ford Laser — no modern electronics, OBD-I only
- This is a fundraising event (Shitbox Rally / Cancer Council) — public engagement drives donations
- **Hardware**: Pi 5 with v2 sensor hat (LSM6DSOX+LIS3MDL, DS18B20 x2, VEML7700, INA226, ELP 4K camera). Pi 5 IP: 10.10.20.107
- Core telemetry stack tested on the car and confirmed working
- Website is a separate repo (`~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/`) deployed via Flux

## Constraints

- **Platform**: Raspberry Pi 5, Raspbian, Python 3.9+
- **Power**: 12V car power with ignition-linked supply — must handle unclean shutdowns
- **Connectivity**: WireGuard VPN over mobile data — intermittent, sometimes days without signal
- **Storage**: SD card (limited capacity) plus potential USB storage
- **Heat**: Australian summer, no air conditioning in a 2001 Ford Laser — cabin temps could exceed 50°C
- **Timeline**: Rally date approaching — must prioritise ruthlessly
- **Display**: 7" Raspberry Pi touchscreen attached to Pi

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Offline-first architecture | Connectivity too unreliable for real-time | ✓ Good |
| SQLite with WAL mode | Crash-resistant, no external dependencies | ✓ Good |
| Batch sync over WireGuard | Simple, secure, works with intermittent connectivity | ✓ Good |
| Priority: bulletproof capture over features | Data loss is unrecoverable | ✓ Good — v1.0 vindicated this |
| Escalating recovery (backoff before reboot) | Crash-loops destroy in-progress captures | ✓ Good — eliminated field-test crash loop |
| Piper TTS over buzzer tones | Spoken alerts are more informative in a car | ✓ Good |
| In-process FastAPI dashboard | Avoids separate process coordination; SSE keeps capture path clean | ✓ Good |
| LSM6DSOX replacing MPU6050 | V2 hat hardware; better precision and integrated with LIS3MDL heading | ✓ Good |
| No driver display yet | Display process deferred — not on the car yet | — Pending for v2 |

## Current Milestone: v2.0 Rally Ready

**Goal:** Turn the telemetry system into a full rally companion — driver display, field logging, public engagement features, and confirmed hardware reliability before race day.

**Target features:**
- Driver display productionised on the 7" touchscreen
- Field notes / blog with keyboard entry, GPS + DTS, syncs to website
- Refueling log with efficiency tracking, location on website map
- Driver tracking — who's driving, percentages, event attribution, website widgets
- Website revamp — Grafana improvements, new data streams integrated
- ELP 4K video capture tuning
- Sensor calibration (stationary + in-motion)
- Undervoltage resolution and confirmation
- Monitoring completeness — HLTH-01 closed, critical events on UI

## Shipped

### v1.0 — Operational Hardening (2026-04-09)

9 phases, 27 plans. Full details: `.planning/milestones/v1.0-ROADMAP.md`

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-09 — v2.0 Rally Ready milestone started.*
