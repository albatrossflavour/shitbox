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
- [x] **Phase 13: Driver Tracking** - Active driver interface, stint tracking, event attribution (completed 2026-04-09)
- [ ] **Phase 14: Sensor Calibration** - All sensors validated and calibrated; event thresholds re-confirmed
- [ ] **Phase 15: Undervoltage and Monitoring** - Undervoltage fix confirmed, monitoring gaps closed, critical events visible
- [ ] **Phase 16: Video Capture Tuning** - Camera modes empirically listed; optimal settings confirmed
- [x] **Phase 17: Driver Display** - Fullscreen 7" kiosk productionised with live data, alerts, and active driver (completed 2026-04-10)
- [x] **Phase 18: Website Revamp** - Notes, fuel, and driver data integrated; Grafana improved (completed 2026-04-11)
- [ ] **Phase 19: Website Narrative Rebuild** - Day-centric IA with before/live/archive modes, timeline spine, progress-bar day nav
- [ ] **Phase 20: Physical Integration** - Mount the build; 3D-printed enclosures, cable looms, dash fitting

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

- [x] 13-01-PLAN.md — Wave 0 test scaffolds + schema v7 migration (driver_stints)
- [x] 13-02-PLAN.md — DriverStorage, driver_state, FastAPI router, config roster
- [x] 13-03-PLAN.md — Engine wiring: event attribution, SSE broadcast, sync generator
- [x] 13-04-PLAN.md — Dashboard UI: top-bar dropdown and stats modal

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

**Plans**: 2 plans

- [x] 17-01-PLAN.md — Backend fixes: DS18B20 cabin temp fallback + thermal/undervoltage SSE alert bridge + Wave 0 tests
- [ ] 17-02-PLAN.md — Kiosk 800x480 index.html rework: layout, overlays, 5-event ticker, waypoint haversine

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

**Plans**: 5 plans

Plans:

- [x] 18-01-PLAN.md — batch_sync metric fixes: shitbox_lux + DS18B20 probe labels + schema v9
- [x] 18-02-PLAN.md — Website: notes feed, current driver card, drivers tab, note badges
- [x] 18-03-PLAN.md — Website: fuel map pins, Grafana iframe fix, nginx cache headers
- [x] 18-04-PLAN.md — Grafana dashboard API update: Ambient Light panel + DS18B20 series
- [x] 18-05-PLAN.md — Rally summary metrics in Prometheus + RALLY SUMMARY dashboard row

**UI hint**: yes

---

### Phase 19: Website Narrative Rebuild

**Goal**: Transform the public website from a collection of disjointed tabs into a day-centric
rally scrapbook with before/live/archive modes. Day becomes the primary UX pivot; events,
notes, and fuel stops interleave onto a per-day timeline spine. Progress-bar day navigator
anchors the site through all three modes.

**Depends on**: Phase 18 (notes, fuel, driver data in sync payload)

**Requirements**: NARR-01, NARR-02, NARR-03, NARR-04, NARR-05, NARR-06, NARR-07, NARR-08, NARR-08b, NARR-09, NARR-10

**Success Criteria** (what must be TRUE):

  1. Homepage detects and renders three modes: before (countdown + agenda preview), live
     (today as homepage, auto-refresh), archive (rally overview + day grid)
  2. Day pages exist at /day/YYYY-MM-DD with a timeline spine that interleaves events, notes,
     and fuel stops in chronological order
  3. Day pages pre-load agenda context (camping, meals, route description) before telemetry
  4. A single progress-bar day navigator appears site-wide in all three modes
  5. Videos, Timelapse, and standalone Map tabs are removed; their content lives inside
     day pages
  6. Drivers tab and cross-rally totals fold into /about
  7. Grafana remains one click from the homepage

**Plans**: 12 plans

Plans:
- [x] 19-01-PLAN.md — Pi-side RouteStorage + Douglas-Peucker + engine wiring (TDD)
- [x] 19-02-PLAN.md — agenda.json authoring + nginx no-cache + SPA fetch plumbing
- [x] 19-03-PLAN.md — SPA router + detectMode() mode detection
- [x] 19-04-PLAN.md — Site-wide day-nav progress bar component
- [x] 19-05-PLAN.md — Day-page scaffold + agenda context + day stats
- [x] 19-06-PLAN.md — Timeline spine merge algorithm + per-kind cards
- [x] 19-07-PLAN.md — Day-page map with full-rally backdrop + day slice
- [x] 19-08-PLAN.md — Before-mode homepage (countdown + itinerary)
- [x] 19-09-PLAN.md — Live-mode homepage (today-as-homepage + refresh loop)
- [x] 19-10-PLAN.md — Archive-mode homepage (overview + linear day grid)
- [ ] 19-11-PLAN.md — Nav shrink + tab purge + /about consolidation
- [ ] 19-12-PLAN.md — REQUIREMENTS.md traceability + Brain update + rollback drill

**UI hint**: yes

**Source**: .planning/notes/2026-04-16-website-v2-ia-redesign.md

---

### Phase 20: Physical Integration

**Goal**: Move v2 hardware from bench pile to install-ready. Mount the Pi 5 + hat stack in
the car, design and 3D-print enclosures for the main board and sensors, route a proper cable
loom, and fit the 7" driver display on VESA mount. Target: nothing flapping, nothing dupont,
everything servicable.

**Depends on**: v2 hardware phases complete (Phase 11 done; Phases 14, 15, 16 can inform
sensor placement but are not hard blockers)

**Requirements**: TBD (to be defined in discuss-phase)

**Success Criteria** (what must be TRUE):

  1. Main Pi + hat stack housed in a 3D-printed enclosure with airflow
  2. All sensors mounted in their intended locations (cabin, engine bay, exterior)
  3. Cable loom routed cleanly — no loose dupont jumpers, no floating breadboards
  4. 7" driver display mounted on VESA arm in driver sightline
  5. PM2.5 sensor housed with air intake
  6. Power distribution from car battery via fused circuit, not breadboard power
  7. Full system boots and runs in-car for a multi-hour shake-down drive without failure

**Plans**: TBD

**UI hint**: no

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
| 13. Driver Tracking | v2.0 | 4/4 | Complete    | 2026-04-09 |
| 14. Sensor Calibration | v2.0 | TBD | Not started | — |
| 15. Undervoltage and Monitoring | v2.0 | TBD | Not started | — |
| 16. Video Capture Tuning | v2.0 | TBD | Not started | — |
| 17. Driver Display | v2.0 | 1/2 | Complete    | 2026-04-10 |
| 18. Website Revamp | v2.0 | 5/5 | Complete    | 2026-04-11 |
| 19. Website Narrative Rebuild | v2.0 | 10/12 | In Progress|  |
| 20. Physical Integration | v2.0 | TBD | Not started | — |
