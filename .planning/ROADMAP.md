# Roadmap: Shitbox Rally Telemetry

## Milestones

- ✅ **v1.0 — Operational Hardening** — Phases 1-11 (shipped 2026-04-09)
- 🚧 **v2.0 — Rally Ready** — Phases 12-18 (in progress)

## Phases

<details>
<summary>✅ v1.0 — Operational Hardening (Phases 1-11) — SHIPPED 2026-04-09</summary>

- [x] Phase 1: Boot Recovery — 2/2 plans (completed 2026-02-25)
- [x] Phase 2: Watchdog and Self-Healing — 3/3 plans (completed 2026-02-25)
- [x] Phase 3: Thermal Resilience and Storage Management — 2/2 plans (completed 2026-02-26)
- [x] Phase 4: Remote Health and Stage Tracking — 2/2 plans (completed 2026-02-27)
- [x] Phase 5: Audio Alerts and TTS — 2/2 plans (completed 2026-02-27)
- [ ] Phase 6: Driver Display — Deferred to v2
- [x] Phase 7: Self-Healing and Crash-Loop Prevention — 2/2 plans (completed 2026-02-28)
- [x] Phase 8: Capture Integrity — 2/2 plans (completed 2026-02-28)
- [x] Phase 9: Sync Reliability — Dropped (criteria met by prior work)
- [x] Phase 10: Live Dashboard with Offline Map — 7/7 plans (completed 2026-04-09)
- [x] Phase 11: V2 Hardware Migration — 5/5 plans (completed 2026-04-09)

Full archive: `.planning/milestones/v1.0-ROADMAP.md`

</details>

### 🚧 v2.0 — Rally Ready (In Progress)

**Milestone Goal:** Turn the telemetry system into a full rally companion — driver display,
field logging, public engagement features, and confirmed hardware reliability before race day.

- [x] **Phase 12: Schema Foundation and Logbook API** - New DB tables, notes and fuel endpoints, sync pipeline extension (completed 2026-04-09)
- [ ] **Phase 13: Driver Tracking** - Active driver interface, stint tracking, event attribution
- [ ] **Phase 14: Sensor Calibration** - All sensors validated and calibrated; event thresholds re-confirmed
- [ ] **Phase 15: Undervoltage and Monitoring** - Undervoltage fix confirmed, monitoring gaps closed, critical events visible
- [ ] **Phase 16: Video Capture Tuning** - Camera modes empirically listed; optimal settings confirmed
- [ ] **Phase 17: Driver Display** - Fullscreen 7" kiosk productionised with live data, alerts, and active driver
- [ ] **Phase 18: Website Revamp** - Notes, fuel, and driver data integrated; Grafana improved

## Phase Details

### Phase 12: Schema Foundation and Logbook API

**Goal**: The Pi can record field notes and fuel stops via REST endpoints, with all new data
landing in telemetry.db and the sync pipeline updated to export notes and fuel data (without
cost fields) alongside events.

**Depends on**: Phase 11 (V2 Hardware Migration complete)

**Requirements**: NOTE-01, NOTE-02, FUEL-01, FUEL-02

**Success Criteria** (what must be TRUE):

  1. User can POST a field note from the Pi UI (or curl) and it appears in the database with DTS and GPS location auto-captured
  2. User can optionally pin a field note to an existing event ID and the association is stored
  3. User can POST a fuel stop with volume and location and it appears in the database
  4. System calculates and returns fuel efficiency (km/L) per stop and a running cumulative average in the fuel API response
  5. The events.json sync payload includes notes and fuel stop data; the fuel cost field is absent from the payload

**Plans**: 4 plans

- [x] 12-01-PLAN.md — Schema v6 migration + Wave 0 test scaffolds
- [x] 12-02-PLAN.md — LogbookStorage, gps_state helper, FastAPI logbook router
- [x] 12-03-PLAN.md — CaptureSyncService JSON generator registry
- [x] 12-04-PLAN.md — Engine wiring + dashboard modals (UI)

**UI hint**: yes

---

### Phase 13: Driver Tracking

**Goal**: The crew can set who is currently driving from the Pi UI, the system records driving
time per driver and attributes events to the driver on duty, and the active driver is broadcast
on the SSE stream for other consumers (display, dashboard).

**Depends on**: Phase 12

**Requirements**: DRVR-01, DRVR-02, DRVR-03

**Success Criteria** (what must be TRUE):

  1. User can select the active driver from the Pi UI and the change takes effect immediately
  2. The SSE stream includes an `active_driver` field that updates when the driver changes
  3. System records start/end timestamps for each driver stint in the database
  4. Each event in the database records the driver who was active at the time of the event
  5. The Pi UI shows current driver, total time per driver, and percentage breakdown for the rally so far

**Plans**: 4 plans

- [ ] 13-01-PLAN.md — Wave 0 test scaffolds + schema v7 migration (driver_stints)
- [ ] 13-02-PLAN.md — DriverStorage, driver_state, FastAPI router, config roster
- [ ] 13-03-PLAN.md — Engine wiring: event attribution, SSE broadcast, sync generator
- [ ] 13-04-PLAN.md — Dashboard UI: top-bar dropdown and stats modal

**UI hint**: yes

---

### Phase 14: Sensor Calibration

**Goal**: All sensors are validated against known references with offsets applied, and event
detection thresholds are re-confirmed accurate under calibrated readings.

**Depends on**: Phase 11 (V2 hardware must be running)

**Requirements**: CAL-01, CAL-02

**Success Criteria** (what must be TRUE):

  1. Each sensor (LSM6DSOX accel/gyro, LIS3MDL, DS18B20 x2, VEML7700, INA226) has a documented calibration result: offset applied or confirmed-zero, with reference comparison
  2. Calibration offsets are applied in code and the system runs with corrected sensor values in production
  3. Event detection thresholds (hard brake, big corner, high G, rough road) are validated against calibrated IMU output and adjusted if readings shifted post-calibration

**Plans**: TBD

---

### Phase 15: Undervoltage and Monitoring

**Goal**: Undervoltage is detectable and visible; the health monitoring gaps from v1.0 are
closed; critical system events surface on the live dashboard.

**Depends on**: Phase 11

**Requirements**: PWR-01, PWR-02, MON-01, MON-02, MON-03

**Success Criteria** (what must be TRUE):

  1. The undervoltage hardware fix is confirmed working; software reads the throttled bitmask and correctly identifies current undervoltage from bits 0-3 only, ignoring sticky historical bits 16-19
  2. An undervoltage event triggers a visible alert overlay on the live dashboard and a spoken TTS announcement
  3. CPU temperature, disk percentage, and sync backlog metrics are confirmed reaching Prometheus end-to-end; the `insert_readings_batch` cpu_percent bug is fixed and verified
  4. The Prometheus scrape job label conflict (shitbox-mqtt-exporter) is resolved with no duplicate or missing metric series
  5. Thermal alerts, undervoltage events, and capture failures are all visible in the live dashboard UI

**Plans**: TBD

**UI hint**: yes

---

### Phase 16: Video Capture Tuning

**Goal**: The ELP 4K camera is empirically characterised on the mounted hardware and running
with optimal settings confirmed to produce clean event recording output.

**Depends on**: Phase 11

**Requirements**: VID-01, VID-02

**Success Criteria** (what must be TRUE):

  1. A complete list of supported camera modes (resolution, framerate, format) is obtained from the mounted ELP 4K hardware and documented in config
  2. The selected resolution and framerate for event recording is justified based on the empirical mode list
  3. v4l2 controls and ffmpeg settings are applied in configuration and a recorded event clip is visually confirmed to be clean (no dropped frames, no corruption artefacts)

**Plans**: TBD

---

### Phase 17: Driver Display

**Goal**: The 7" touchscreen shows a fullscreen kiosk layout with live telemetry data, the
active driver, a scrolling event ticker, and visible alert overlays for critical system events.

**Depends on**: Phase 13 (active driver in SSE), Phase 15 (undervoltage alerts)

**Requirements**: DISP-01, DISP-02, DISP-03, DISP-04

**Success Criteria** (what must be TRUE):

  1. The 7" touchscreen shows a fullscreen kiosk with speed, G-force circle, temperatures, GPS status, and sync status updating live
  2. A scrolling event ticker shows recent events (type + peak G) in real time
  3. The display shows the currently active driver, updated live from the SSE stream when the driver changes
  4. A high-G event, thermal alert, or undervoltage event triggers a visible full-screen alert overlay on the display

**Plans**: TBD

**UI hint**: yes

---

### Phase 18: Website Revamp

**Goal**: The public website integrates field notes, fuel stops, and driver data from the sync
pipeline, with improved Grafana dashboards; the changes are deployed via the home-ops repo.

**Depends on**: Phase 12 (notes and fuel in sync payload), Phase 13 (driver data available)

**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, DRVR-04, DRVR-05, NOTE-03, FUEL-03

**Success Criteria** (what must be TRUE):

  1. The website shows a notes/blog section listing field notes with timestamp and GPS location
  2. The Leaflet map shows fuel stop pins as a distinct layer with efficiency data in the popup; no cost data is present anywhere on the site
  3. The website homepage shows a "who's in charge" widget with current driver and running time percentages
  4. A driver stats page shows per-driver driving time, percentage, and event attribution
  5. Grafana graph layouts are improved and the iframe kiosk display issues are resolved

**Plans**: TBD

**UI hint**: yes

---

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Boot Recovery | v1.0 | 2/2 | Complete | 2026-02-25 |
| 2. Watchdog and Self-Healing | v1.0 | 3/3 | Complete | 2026-02-25 |
| 3. Thermal Resilience and Storage Management | v1.0 | 2/2 | Complete | 2026-02-26 |
| 4. Remote Health and Stage Tracking | v1.0 | 2/2 | Complete | 2026-02-27 |
| 5. Audio Alerts and TTS | v1.0 | 2/2 | Complete | 2026-02-27 |
| 6. Driver Display | v2 | TBD | Deferred | — |
| 7. Self-Healing and Crash-Loop Prevention | v1.0 | 2/2 | Complete | 2026-02-28 |
| 8. Capture Integrity | v1.0 | 2/2 | Complete | 2026-02-28 |
| 9. Sync Reliability | v1.0 | — | Dropped | 2026-02-28 |
| 10. Live Dashboard with Offline Map | v1.0 | 7/7 | Complete | 2026-04-09 |
| 11. V2 Hardware Migration | v1.0 | 5/5 | Complete | 2026-04-09 |
| 12. Schema Foundation and Logbook API | v2.0 | 4/4 | Complete    | 2026-04-09 |
| 13. Driver Tracking | v2.0 | 0/4 | Not started | — |
| 14. Sensor Calibration | v2.0 | TBD | Not started | — |
| 15. Undervoltage and Monitoring | v2.0 | TBD | Not started | — |
| 16. Video Capture Tuning | v2.0 | TBD | Not started | — |
| 17. Driver Display | v2.0 | TBD | Not started | — |
| 18. Website Revamp | v2.0 | TBD | Not started | — |
