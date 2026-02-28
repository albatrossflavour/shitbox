# Shitbox Rally Telemetry

## What This Is

An offline-first rally car telemetry system for a 2001 Ford Laser competing in the Shitbox Rally (Port Douglas to Melbourne). It captures high-rate IMU data, GPS position, temperature, and video on a Raspberry Pi, stores everything locally in SQLite, and batch-syncs to Prometheus and a public website when mobile connectivity is available. The rally is a fundraising event, so reliable data capture and public engagement matter.

## Core Value

Never lose telemetry data or video — the system must survive thousands of kilometres of rough roads, power cycles, heat, and vibration without human intervention.

## Requirements

### Validated

- ✓ High-rate IMU sampling at 100 Hz with event detection (hard brake, big corner, high G, rough road) — existing
- ✓ GPS position, speed, and heading tracking at 1 Hz — existing
- ✓ Temperature and environment monitoring (BME680, MCP9808) — existing
- ✓ Power monitoring (INA219) — existing
- ✓ Offline-first SQLite storage with WAL mode — existing
- ✓ Cursor-based batch sync to Prometheus over WireGuard — existing
- ✓ Event-triggered video capture with pre-event ring buffer — existing
- ✓ Manual video capture via GPIO button — existing
- ✓ Capture sync to NAS via rsync — existing
- ✓ GPS-based clock synchronisation — existing
- ✓ Structured logging via structlog — existing
- ✓ Graceful hardware degradation (runs with whatever sensors are available) — existing
- ✓ Public website at shit-of-theseus.com showing events, map, video, and Grafana dashboard — existing
- ✓ OLED display service (SSD1306) — existing

### Active

- [ ] Bulletproof boot recovery — clean startup after ignition cycles and unexpected power loss
- [ ] Watchdog and self-healing — detect stuck services and restart them automatically
- [ ] Remote health monitoring — visibility into system health when connectivity is available
- [ ] Driver display on 7" Pi screen — speed, heading, trip stats, system health at a glance
- [ ] Rally stage tracking — distance covered, progress along the route
- [ ] Thermal resilience — handle high cabin temperatures without data loss
- [ ] Storage management — prevent SD card filling up over multi-day rally
- [ ] Website engagement — reliable delivery of videos and metrics to followers during the rally

### Out of Scope

- OBD / ECU data — 2001 Ford Laser is OBD-I only, no easy interface
- Mobile app — web UI on Pi display and website are sufficient
- Real-time streaming — connectivity too sparse; batch sync is the right model
- G-force display on driver screen — driver doesn't need live accelerometer data

## Context

- The rally runs from Port Douglas (Far North Queensland) to Melbourne — roughly 4,000+ km through remote and regional Australia
- Mobile connectivity will be intermittent at best; long stretches with no signal
- The car is a 2001 Ford Laser — no modern electronics, OBD-I only
- This is a fundraising event (Shitbox Rally / Cancer Council) so public engagement through the website drives donations
- The Pi hardware setup (mounting, wiring, power) is still a work in progress
- Core telemetry stack (IMU, GPS, video, Prometheus sync) has been partially tested on the car and confirmed working
- Website is a separate repo (`~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/`) deployed via Flux
- The existing codebase already has a health watchdog loop (30-second interval), systemd notify support, and disk space checks

## Constraints

- **Platform**: Raspberry Pi with Raspbian, Python 3.9+
- **Power**: 12V car power with ignition-linked supply — must handle unclean shutdowns
- **Connectivity**: WireGuard VPN over mobile data — intermittent, sometimes days without signal
- **Storage**: SD card (limited capacity) plus potential USB storage
- **Heat**: Australian summer, no air conditioning in a 2001 Ford Laser — cabin temps could exceed 50°C
- **Timeline**: Rally is a few months away — must prioritise ruthlessly
- **Display**: 7" Raspberry Pi touchscreen attached to Pi

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Offline-first architecture | Connectivity too unreliable for real-time | ✓ Good |
| SQLite with WAL mode | Crash-resistant, no external dependencies | ✓ Good |
| Batch sync over WireGuard | Simple, secure, works with intermittent connectivity | ✓ Good |
| Priority: bulletproof capture over features | Data loss is unrecoverable; features can be added later | — Pending |
| 7" Pi screen for driver display | Already have the hardware, directly attached to Pi | — Pending |
| No OBD integration | OBD-I too complex for the value it adds | ✓ Good |

## Current Milestone: v1.1 Field-Test Hardening

**Goal:** Fix all issues discovered during the first test drive — sync reliability, capture integrity, and self-healing recovery across subsystems.

**Target fixes:**

- Prometheus sync "too old" rejections — data lost on every drive
- Missing video captures and timelapse gaps
- IMU I2C bus alarms recurring
- TTS speaker intermittently silent
- No way to manually trigger data upload
- Cursor advances past unsynced data

---
*Last updated: 2026-02-28 after v1.1 milestone start*
