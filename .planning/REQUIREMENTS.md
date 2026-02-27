# Requirements: Shitbox Rally Telemetry

**Defined:** 2026-02-25
**Core Value:** Never lose telemetry data or video — the system must survive thousands of kilometres of rough roads, power cycles, heat, and vibration without human intervention.

## v1 Requirements

Requirements for rally-ready hardening. Each maps to roadmap phases.

### Boot Recovery

- [x] **BOOT-01**: System runs SQLite `PRAGMA integrity_check` after detecting unclean shutdown
- [x] **BOOT-02**: System closes orphaned events from prior crash and marks them as interrupted on boot
- [x] **BOOT-03**: SQLite configured with `synchronous=FULL` for WAL durability across hard power cuts

### Watchdog and Self-Healing

- [x] **WDOG-01**: BCM2835 hardware watchdog enabled (`dtparam=watchdog=on`, `RuntimeWatchdogSec=14`)
- [x] **WDOG-02**: All systemd services audited and configured with `Restart=always`
- [x] **WDOG-03**: ffmpeg `is_running` bug fixed to use `poll()` with mtime-based health check and auto-restart
- [x] **WDOG-04**: I2C bus lockup detected and recovered via 9-clock bit-bang reset

### Remote Health Monitoring

- [ ] **HLTH-01**: System publishes CPU temp, disk %, sync backlog, and throttle state to Prometheus via existing remote_write
- [x] **HLTH-02**: In-car buzzer alerts on thermal warnings, storage critical, and service failures

### Thermal Resilience

- [x] **THRM-01**: Thermal monitor reads CPU temperature every 5 seconds and publishes to shared state
- [x] **THRM-02**: System alerts (buzzer + log) at 70°C warning and 80°C throttle thresholds
- [x] **THRM-03**: `vcgencmd get_throttled` bitmask decoded and logged at every health check

### Storage Management

- [x] **STOR-01**: WAL checkpoint runs periodic `TRUNCATE` to prevent unbounded WAL growth

### Stage Tracking

- [x] **STGE-01**: System tracks cumulative distance from GPS (odometer-style total km)
- [x] **STGE-02**: System tracks daily distance (resets on new driving day)
- [x] **STGE-03**: System loads waypoint-based rally route and tracks stage progress (waypoints reached, day label)

### Audio Alerts

- [x] **AUDIO-01**: USB speaker detected and used as primary audio output device
- [x] **AUDIO-02**: TTS engine (Piper) generates spoken alerts replacing buzzer tone patterns
- [ ] **AUDIO-03**: Contextual announcements for system events (boot, thermal, waypoints, distance, recovery)

## v2 Requirements

Deferred to post-rally or if time permits before departure.

### Driver Display

- **DISP-01**: Separate display process on 7" Pi screen showing speed and heading
- **DISP-02**: Display shows trip stats (distance today, total distance, driving time)
- **DISP-03**: Display shows system health badges (storage %, GPS lock, sync status, thermal)

### Storage Enhancements

- **STOR-02**: Proactive disk eviction starting at 70% (oldest synced videos first)
- **STOR-03**: Sync-status tracking per file so cleanup never deletes unsynced video
- **STOR-04**: log2ram installation to reduce SD card write pressure

### Resilience Enhancements

- **RSLN-01**: Configuration hot-reload via SIGHUP without restarting services
- **RSLN-02**: Persistent event queue for failed uploads (no events lost if sync fails)
- **RSLN-03**: Async GPS acquisition (non-blocking startup)

## Out of Scope

| Feature | Reason |
|---------|--------|
| OBD / ECU data | 2001 Ford Laser is OBD-I only, no easy interface |
| Real-time video streaming | Connectivity too sparse; batch sync is the right model |
| Mobile app | Web UI on website and Pi display are sufficient |
| Graceful shutdown on power loss | Requires new hardware wiring; WAL mode mitigates adequately |
| Read-only OS filesystem (overlayfs) | Incompatible with SQLite WAL data writes; high implementation risk |
| AI/ML event classification | Unnecessary complexity for rally use case |
| MQTT re-enable | Prometheus path is sufficient; MQTT adds duplicate metrics |
| Per-session lap timing | Not a timed rally; fundraising event |
| Automatic OTA updates | Too risky for a multi-day rally in remote areas |
| WireGuard PersistentKeepalive | Config change only, not a software requirement — do it manually |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BOOT-01 | Phase 1 | Complete |
| BOOT-02 | Phase 1 | Complete |
| BOOT-03 | Phase 1 | Complete |
| WDOG-01 | Phase 2 | Complete |
| WDOG-02 | Phase 2 | Complete |
| WDOG-03 | Phase 2 | Complete |
| WDOG-04 | Phase 2 | Complete |
| HLTH-02 | Phase 2 | Complete |
| THRM-01 | Phase 3 | Complete |
| THRM-02 | Phase 3 | Complete |
| THRM-03 | Phase 3 | Complete |
| STOR-01 | Phase 3 | Complete |
| HLTH-01 | Phase 4 | Pending |
| STGE-01 | Phase 4 | Complete |
| STGE-02 | Phase 4 | Complete |
| STGE-03 | Phase 4 | Complete |
| AUDIO-01 | Phase 5 | Complete |
| AUDIO-02 | Phase 5 | Complete |
| AUDIO-03 | Phase 5 | Pending |

**Coverage:**

- v1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---

*Requirements defined: 2026-02-25*
*Last updated: 2026-02-27 — added AUDIO-01/02/03 for Phase 5, updated STGE-03 to waypoint-based*
