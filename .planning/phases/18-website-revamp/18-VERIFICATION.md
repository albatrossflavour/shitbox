---
phase: 18-website-revamp
verified: 2026-04-22T00:00:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: missing
  previous_score: n/a
  gaps_closed:
    - "Phase 18 had no VERIFICATION.md at all prior to this run, v2.0 milestone audit (2026-04-22) confirmed all code wired end-to-end; this document provides the missing formal artefact."
  gaps_remaining: []
  regressions: []
deferred: []
---

# Phase 18: Website Revamp, Verification Report

**Phase Goal (ROADMAP):** The public website integrates field notes, fuel stops, and driver data from the sync pipeline, with improved Grafana dashboards; the changes are deployed via the home-ops repo.

**Verified:** 2026-04-22
**Status:** passed
**Re-verification:** Yes, initial formal verification after v2.0 milestone audit identified Phase 18 VERIFICATION.md as missing.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Website shows a notes/blog section listing field notes with timestamp and GPS location | VERIFIED | `engine.py:613-616` registers `notes` generator; `webroot/index.html:1737-1738` fetches and renders `notes.json`; 18-02 SUMMARY confirms Field Notes card + badge injection |
| 2 | Leaflet map shows fuel stop pins as a distinct layer with efficiency data in popup; no cost data on site | VERIFIED | `engine.py:613-616` registers `fuel` generator; `webroot/index.html:2741` fuel fetch; 18-03 SUMMARY confirms Leaflet pins with km/L popup and PII exclusion at SQL SELECT level |
| 3 | Website homepage shows a "who's in charge" widget with current driver and running percentages | VERIFIED | `engine.py:619-624` registers `driver-stats` generator; `webroot/index.html:2414` current-driver card; 18-02 SUMMARY confirms `active_driver` read from `driver-stats.json` with em-dash fallback |
| 4 | Driver stats page shows per-driver driving time, percentage, and event attribution | VERIFIED | `webroot/index.html:1615-1624` drivers-table rendering; `webroot/index.html:2751` driver-stats fetch; event-attribution references at `:1410, 1414, 1419, 1661` |
| 5 | Grafana graph layouts improved and iframe kiosk display issues resolved | VERIFIED | 18-03 SUMMARY confirms Grafana iframe fix + nginx cache headers; 18-04 SUMMARY confirms Ambient Light panel + DS18B20 series API update; 18-05 SUMMARY confirms RALLY SUMMARY dashboard row |
| 6 | Notes feed wired from Pi SQLite to capture_sync to website without cost/PII leakage | VERIFIED | `engine.py:613-616` registers generator; LogbookStorage excludes cost at SQL SELECT (12-02, 18-02); 18-02 SUMMARY confirms no `cost` field in JS rendering |
| 7 | Fuel stop data syncs to website map without cost_aud appearing anywhere on the site | VERIFIED | 18-02/18-03 SUMMARY confirm zero `cost_aud` grep matches in webroot/index.html rendering code; SQL SELECT in LogbookStorage enforces exclusion |
| 8 | Batch-sync Prometheus metric coverage extended with v2.0 sensors (shitbox_lux, DS18B20 probe labels, rally summary gauges) | VERIFIED | 18-01 SUMMARY: batch_sync adds `shitbox_lux` + DS18B20 probe labels + schema v9; 18-05 SUMMARY: rally summary gauges pushed to Prometheus |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/events/engine.py` | `capture_sync.register_json_generator` calls for notes, fuel, driver-stats (and route) | VERIFIED | Lines 613-616 register notes and fuel generators; lines 619-624 register driver-stats; route generator also registered at line 634 in the same init block |
| `webroot/index.html` (home-ops repo) | Notes, fuel, drivers fetch chains + current-driver card + drivers table | VERIFIED | Lines 1737-1738 notes fetch; 2741 fuel fetch; 2746 route fetch; 2751 driver-stats fetch; 1615-1624 drivers-table rendering; 2414 current-driver card |
| `nginx-config/default.conf` (home-ops repo) | Cache headers for JSON feeds so the browser does not stale-serve `events.json`/`notes.json`/`fuel.json` | VERIFIED | 18-03 SUMMARY confirms nginx cache-control headers added for JSON paths |
| Grafana dashboard JSON (Grafana API-updated) | Ambient Light panel, DS18B20 per-probe series, RALLY SUMMARY row | VERIFIED | 18-04 SUMMARY confirms Ambient Light + DS18B20 panels updated via API; 18-05 SUMMARY confirms RALLY SUMMARY row added to `shitbox-rally-command` dashboard |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| engine.py `UnifiedEngine.__init__` | `LogbookStorage.generate_notes_json` | `capture_sync.register_json_generator("notes", ...)` | VERIFIED | Line 613-616 |
| engine.py `UnifiedEngine.__init__` | `LogbookStorage.generate_fuel_json` | `capture_sync.register_json_generator("fuel", ...)` | VERIFIED | Line 613-616 |
| engine.py `UnifiedEngine.__init__` | `DriverStorage.generate_driver_stats_json` | `capture_sync.register_json_generator("driver-stats", ...)` | VERIFIED | Line 619-624 |
| `notes.json` | `#notes-container` | fetch chain in index.html | VERIFIED | Line 1737-1738 |
| `fuel.json` | Leaflet fuel pins layer | fetch chain in index.html | VERIFIED | Line 2741 |
| `driver-stats.json` | `#drivers-table` + current-driver card | fetch chain in index.html | VERIFIED | Lines 1615-1624, 2414, 2751 |
| Events JSON `active_driver` field | per-event attribution display | `webroot/index.html:1410, 1414, 1419, 1661` | VERIFIED | Confirmed by v2.0 integration checker |

## Requirements Coverage

| Requirement | Status | Evidence Ref |
|-------------|--------|--------------|
| NOTE-03: Field notes sync to shit-of-theseus.com and display in a blog/notes section | satisfied | Truth #1, Key Link row 1, 4 |
| FUEL-03: Fuel stop locations and efficiency data sync to the website map; cost data never syncs | satisfied | Truth #2, #7, Key Link row 2, 5 |
| DRVR-04: Website shows a "who's in charge" widget on the homepage with current driver and running percentages | satisfied | Truth #3, Key Link row 3, 6 |
| DRVR-05: Website shows per-driver stats including driving time, percentage, and event attribution | satisfied | Truth #4, Key Link row 3, 6, 7 |
| WEB-01: Website integrates field notes as a blog/notes section with timestamp and location | satisfied | Truth #1, Key Link row 1, 4 |
| WEB-02: Website shows fuel stop pins as a Leaflet map layer with efficiency data | satisfied | Truth #2, Key Link row 2, 5 |
| WEB-03: Website shows driver stats page with time percentages and event attribution | satisfied | Truth #4, Key Link row 3, 6, 7 |
| WEB-04: Grafana graph layouts improved; iframe kiosk issues resolved; metric coverage improved with v2.0 sensors | satisfied | Truth #5, #8, Artifacts row 3, 4 |

## Anti-Patterns Found

None, all eight requirements wired end-to-end per the v2.0 milestone audit (2026-04-22). One cosmetic follow-up noted in the audit (peak_gx/peak_gy/peak_gz reach events.json but are not rendered on the site) is out of scope for Phase 18 and tracked in the home-ops repo.

## Human Verification Required

These are non-blocking, cosmetic/UX spot-checks. The code wiring is already proven by the integration checker; these confirm the deployed site renders correctly on real hardware.

- Test: Open deployed site Notes tab; verify at least one note renders with timestamp and GPS map link. Expected: Notes card visible; GPS link opens correct map coord; no cost field. Why human: Static HTML/JS, no automated browser framework.
- Test: Open Events tab on deployed site; verify fuel pins visible as distinct colour; click one and confirm popup shows km/L, no cost field. Expected: Fuel pin popup lists volume + km/L only. Why human: Leaflet DOM interaction.
- Test: Open Drivers tab; verify current-driver widget + drivers table both visible. Expected: Current driver amber + middle-dot; table lists all drivers with hours and percentages. Why human: DOM rendering.
- Test: Open Dashboard tab; confirm iframe loads shitbox-rally-command dashboard (not shitbox-telemetry). Expected: RALLY SUMMARY row visible; Ambient Light panel visible; DS18B20 series labelled per-probe. Why human: External Grafana service.

_Verified: 2026-04-22T00:00:00Z_
_Verifier: Claude (gsd-verifier via Phase 23 closure)_
