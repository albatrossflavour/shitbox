---
phase: 19-website-narrative-rebuild
verified: 2026-04-22T00:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 10/11
  previous_verified: 2026-04-16T05:30:00Z
  gaps_closed:
    - "NARR-08b: home-address proximity filter confirmed implemented at src/shitbox/storage/route.py:22-28 (_haversine_m), :121 (_exclude_home flag), :153-157 (drop points within home_exclusion_radius_m); wired in engine.py:627-632. The 2026-04-16 verification pre-dated the implementation; this correction reflects actual code state per the 2026-04-22 v2.0 milestone audit."
  gaps_remaining: []
  regressions: []
gaps: []
human_verification:
  - test: "Before-mode homepage countdown renders and ticks"
    expected: "Visiting https://shit-of-theseus.com shows a countdown with days/hours/minutes/seconds ticking down to 2026-05-27. Day-nav shows 10 future segments (all grey). 10 day rows in the itinerary are clickable. Planned route image renders or hides gracefully."
    why_human: "Cannot test live browser rendering or JavaScript execution programmatically. Countdown behaviour, Leaflet tile loading, and SPA navigation require a real browser."
  - test: "SPA routing — /day/YYYY-MM-DD loads correct day content"
    expected: "Navigating to /day/2026-05-27 renders 'Day 1 — Port Douglas → Cairns' with agenda context, stats row, map section, and timeline spine. Back button returns to /. URL changes via pushState without full page reload."
    why_human: "SPA navigation, pushState/popstate behaviour, and day-page scaffold rendering require a browser environment."
  - test: "Live-mode homepage renders correctly"
    expected: "When agenda.rally.start_date is set to today in DevTools: homepage shows today's day page with pulsing LIVE badge, current-driver widget (or silent if no driver data), and network tab shows /captures/*.json fetches every 2 minutes. Navigating to a day page stops the refresh timer."
    why_human: "Requires simulating live mode by overriding agenda dates in browser DevTools, and observing timer behaviour in Network tab."
  - test: "Archive-mode homepage renders correctly"
    expected: "When rally.end_date is set to yesterday in DevTools: homepage shows overview stats + linear day grid sorted newest-first. Clicking any day card navigates via pushState. Missing hero.jpg/timelapse-poster.jpg fall through to text 'Day N' placeholder without broken image icons."
    why_human: "Requires simulating archive mode and observing thumbnail fallback chain — both require a real browser."
  - test: "/about page content renders correctly"
    expected: "Visiting /about shows: hero (logo.png or hidden), drivers section (or 'No driver data yet.' placeholder), The Car section with car-front.jpg/car-side.jpg gallery, Ship of Theseus explanation, The Telemetry section with GitHub link. Back to Home returns via pushState."
    why_human: "Content rendering and image fallbacks require browser observation."
  - test: "route.json is produced on Pi daemon restart"
    expected: "After daemon restart: /var/lib/shitbox/captures/route.json exists, is under 1 MB, and contains generated_at + tolerance_m + days keys. journalctl shows 'route_json_generated' log entries."
    why_human: "Requires access to the Pi hardware (hostname: laser) which cannot be tested from the laptop."
---

# Phase 19: Website Narrative Rebuild — Verification Report

**Phase Goal:** Rebuild the Shit of Theseus website from tab-based SPA to day-centric narrative structure with before/live/archive mode detection, day pages with timeline spine, and cleaned-up navigation.

**Verified:** 2026-04-16T05:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Homepage adapts to before/live/archive mode via detectMode() | VERIFIED | detectMode() function present with 6-branch self-test IIFE; renderHomepage dispatches to renderHomepageBefore/renderHomepageLive/renderHomepageArchive on correct mode strings |
| 2 | /day/YYYY-MM-DD routes to renderDayPage via pushState SPA | VERIFIED | DAY_URL_RE regex, route() dispatcher, navigateToDay() with history.pushState all present; popstate handler wired |
| 3 | Day page has timeline spine merging events/notes/fuel/driver changes/agenda markers | VERIFIED | buildSpine(), renderSpine(), and 7 per-kind card renderers all present; wired into renderDayPage after showRoute() |
| 4 | Day page renders agenda context BEFORE telemetry (D-12 order) | VERIFIED | Section order in renderDayPage: header(1827) → agenda(1828) → stats(1829) → map(1863) → spine(1864) → videos(1865) → timelapse(1866) |
| 5 | Site-wide day-nav progress bar visible on all routes | VERIFIED | renderDayNav() called first in renderDayPage (line 1827), renderHomepage (line 1948), renderAbout (line 1975) |
| 6 | Top nav shrunk to 4 entries: Home / Grafana / About / Donate | VERIFIED | Nav block contains exactly 4 anchors; Grafana and Donate both have target="_blank" rel="noopener" |
| 7 | /about consolidates drivers + car + telemetry content | VERIFIED | renderAbout() and _renderDriversForAbout() both present; Ship of Theseus and github.com/albatrossflavour/shitbox content confirmed in file |
| 8 | Pi-side route.json generator emits DP-simplified per-day polylines | VERIFIED | RouteStorage class, douglas_peucker() (iterative), generate_route_json() all present in route.py; 11 tests pass; engine wires route as 4th register_json_generator call |
| 9 | Home-address exclusion enforced in route.json | VERIFIED | `src/shitbox/storage/route.py:22-28` `_haversine_m`, `:121` `_exclude_home` flag, `:153-157` drops points where distance < `home_exclusion_radius_m`; `src/shitbox/events/engine.py:627-632` instantiates `RouteStorage` with `home_lat`/`home_lng`/`home_exclusion_radius_m` from config. Confirmed by v2.0 milestone audit 2026-04-22. |
| 10 | Day-page map shows full-rally backdrop + day slice highlight | VERIFIED | initDayMap() present with backdrop grey polylines, orange day-slice, event pins via BADGE_COLORS, _teardownDayMap() lifecycle management |
| 11 | agenda.json serves as single source of rally-shape truth | VERIFIED | agenda.json exists with D-10 schema (10 days, sequential dates, correct field structure); nginx no-cache rule present; SPA fetches on load via Promise.allSettled |

**Score: 11/11 truths verified**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/storage/route.py` | RouteStorage + douglas_peucker + generate_route_json | VERIFIED | 158 lines, all three components present, iterative DP chosen over recursive |
| `tests/test_route_storage.py` | 11+ tests including test_size_budget | VERIFIED | 171 lines, 11 tests, all pass |
| `tests/test_capture_sync_generators.py` | test_route_generator_registers_and_writes | VERIFIED | Test present and passing |
| `src/shitbox/events/engine.py` | RouteStorage import + 4 register_json_generator calls | VERIFIED | Import at line 47, route_storage at line 570-574, 4 total registrations confirmed |
| `webroot/agenda.json` | D-10 schema, 10 days sequential | VERIFIED | start_date: 2026-05-27, end_date: 2026-06-05, 10 days, sequential day_numbers |
| `nginx-config/default.conf` | location = /agenda.json + route in captures regex | VERIFIED | Both changes present, try_files preserved |
| `webroot/index.html` | All SPA, day-page, mode, and nav functions | VERIFIED | 2107 lines; all required functions confirmed present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| engine.py UnifiedEngine.__init__ | RouteStorage.generate_route_json | register_json_generator("route") | VERIFIED | Line 572-574 in engine.py |
| generate_route_json | readings table (sensor_type='gps') | SQL SELECT with WHERE sensor_type='gps' | VERIFIED | Explicit column-list SELECT in generate_route_json() |
| index.html fetch('/agenda.json') | agendaData module variable | Promise.allSettled then route() | VERIFIED | Lines 2093-2105 |
| nginx location = /agenda.json | no-cache headers | add_header Cache-Control | VERIFIED | Block present in default.conf |
| renderHomepage() dispatcher | renderHomepageBefore/Live/Archive | detectMode() result | VERIFIED | All three branches at lines 1958, 1962, 1965 |
| renderDayPage #day-spine | renderSpine(buildSpine()) | getElementById after showRoute() | VERIFIED | Lines 1882-1884 |
| renderDayPage #day-map | initDayMap(dayISO, routeData, eventsData) | after spine wiring | VERIFIED | Confirmed present after showRoute() |
| route() dispatcher | renderDayPage(dayISO) | DAY_URL_RE pathname match | VERIFIED | Lines 1089, 1110-1113 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| route.py generate_route_json | rows (GPS readings) | SQL SELECT from readings WHERE sensor_type='gps' | Yes — DB query, not static | FLOWING |
| index.html renderDayPage | eventsData, fuelData, routeData | Fetched from /captures/*.json on load | Yes — real JSON sources, no hardcoded values | FLOWING |
| index.html renderDayNav | agendaData.days | Fetched from /agenda.json via Promise.allSettled | Yes — real agenda.json content | FLOWING |
| index.html buildSpine | events/notes/fuel/agendaDay | Module-level globals populated by fetch chains | Yes — upstream fetch sources | FLOWING |
| index.html initDayMap | routeData.days[dayISO].points | routeData populated from /captures/route.json fetch | Yes — real polyline data (when available) | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED for Pi daemon (no runnable entry point on laptop). Python test suite run instead.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| RouteStorage tests pass | pytest tests/test_route_storage.py -x -q | 11 passed in 30.99s | PASS |
| Capture sync integration test passes | pytest tests/test_capture_sync_generators.py -x -q | 4 passed | PASS |
| agenda.json validates | python3 validation script | start_date, end_date, 10 days, sequential day_numbers all confirmed | PASS |
| nginx config has required blocks | grep location=agenda.json, grep route in captures regex | Both present | PASS |
| index.html has all required functions | grep counts for all key functions | All confirm count=1 or expected count | PASS |
| Legacy sections removed | grep id="status-section" etc | All return 0 | PASS |
| PII exclusion — no cost_aud in JS rendering | grep cost_aud excluding guard comment | 0 field accesses | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| NARR-01 | 19-03, 19-08, 19-09, 19-10 | Homepage mode detection + 3 mode renderers | SATISFIED | detectMode() + renderHomepageBefore/Live/Archive all wired |
| NARR-02 | 19-03 | /day/YYYY-MM-DD URL routing | SATISFIED | DAY_URL_RE, route(), navigateToDay(), popstate handler |
| NARR-03 | 19-06 | Timeline spine merging all sources | SATISFIED | buildSpine() + renderSpine() + 7 per-kind cards |
| NARR-04 | 19-05 | Agenda context before telemetry (D-12) | SATISFIED | Section order verified by line numbers |
| NARR-05 | 19-04 | Day-nav progress bar on all routes | SATISFIED | renderDayNav() called first in all 3 render functions |
| NARR-06 | 19-11 | Nav shrunk to 4 entries | SATISFIED | 4 nav anchors confirmed |
| NARR-07 | 19-11 | /about consolidates content | SATISFIED | renderAbout() with 5 sections |
| NARR-08 | 19-01 | Pi-side route.json generator | SATISFIED | RouteStorage, DP, tests all present and passing |
| NARR-08b | 19-01 | Home-address exclusion in route.json | SATISFIED | Implemented in `src/shitbox/storage/route.py:22-28, 121, 153-157`; wired in `engine.py:627-632`. Confirmed by v2.0 milestone audit 2026-04-22. |
| NARR-09 | 19-07 | Day-page map with full-rally backdrop | SATISFIED | initDayMap() with backdrop + day slice + event pins |
| NARR-10 | 19-02 | agenda.json as rally-shape truth | SATISFIED | agenda.json, nginx rule, SPA fetch all confirmed |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| webroot/index.html | ~1865 | `id="day-videos" class="day-section-placeholder"` — video highlights section is a dashed placeholder | Warning | Plans 19-11 SUMMARY explicitly notes this as a known stub deferred to future phase. Day pages lack video section. Not a blocker — plan documented this as out of scope for Phase 19. |
| webroot/index.html | ~1866 | `id="day-timelapse" class="day-section-placeholder"` — timelapse section is a dashed placeholder | Warning | Same as above — explicitly documented stub. |
| agenda.json | — | Rally dates 2026-05-27 to 2026-06-05 are placeholder — confirmed rally date is 2026-07-10 per Brain doc | Warning | Plan 19-12 flagged this as Phase 19.1 candidate. Before-mode countdown will show wrong remaining days. Not a code defect but a content accuracy issue. |

### Human Verification Required

### 1. Before-Mode Homepage Countdown

**Test:** Open https://shit-of-theseus.com in a browser (today is 2026-04-16, rally placeholder date is 2026-05-27).
**Expected:** Countdown shows ~41 days / hours / minutes / seconds ticking once per second. Day-nav shows 10 future segments (grey). 10 itinerary rows are visible and clickable. Planned route image (/route.jpg) renders or hides gracefully via onerror.
**Why human:** JavaScript execution, DOM rendering, and timer behaviour require a browser environment.

### 2. SPA Routing — /day/YYYY-MM-DD Navigation

**Test:** Navigate to https://shit-of-theseus.com/day/2026-05-27 directly (deep link) and via clicking Day 1 in the itinerary.
**Expected:** Page renders "Day 1 — Port Douglas → Cairns" header, agenda context (route prose, camping, meals), stats row (all zeros pre-rally), map section showing "No route recorded" message, timeline spine showing "Nothing logged yet.", and the back-to-home link works via pushState.
**Why human:** SPA routing, pushState/popstate, and rendered output require browser verification.

### 3. Live-Mode Homepage

**Test:** Temporarily set agenda.rally.start_date to today's date (2026-04-16) in the agenda.json, deploy via Flux, reload the site.
**Expected:** Homepage renders today as a day page with pulsing "LIVE" badge in the h1. Current-driver widget shows active driver or is absent (silent). Network tab shows /captures/events.json fetching every 2 minutes. Navigating to /day/2026-05-28 stops the refresh timer (visible in Network tab).
**Why human:** Requires agenda.json edit + deploy, and timer behaviour observation in browser DevTools.

### 4. Archive-Mode Homepage

**Test:** Temporarily set agenda.rally.end_date to yesterday in agenda.json, deploy, reload.
**Expected:** Homepage shows overview stats card (Distance, Days, Events, Fuel, Drivers), then linear day grid sorted newest-first (Day 10 first). Clicking any day card navigates to /day/YYYY-MM-DD via pushState. Missing hero.jpg and timelapse-poster.jpg fall through to amber "Day N" text — no broken image icons.
**Why human:** Requires agenda.json edit + deploy, and thumbnail fallback chain requires browser observation.

### 5. /about Page Content

**Test:** Click About in the top nav.
**Expected:** /about renders: logo.png (or hidden), Drivers section (or "No driver data yet." pre-rally), The Car section with car-front.jpg/car-side.jpg (or hidden), Ship of Theseus explanation, The Telemetry section with clickable GitHub link opening in new tab. Back-to-home link works via pushState.
**Why human:** Image fallbacks, external link target behaviour, and rendered content require browser verification.

### 6. Pi Daemon — route.json Production

**Test:** SSH to laser, restart shitbox-telemetry, wait 5 minutes, check captures directory.
**Expected:** /var/lib/shitbox/captures/route.json exists, is under 1 MB, and contains keys generated_at + tolerance_m + days. journalctl shows "route_json_generated" structlog entries. If GPS data exists: route.json has per-day point arrays.
**Why human:** Requires Pi hardware access (hostname: laser) which is not available from the laptop. On-device verification deferred per the plan's own verification section.

### Gaps Summary

Zero blockers. NARR-08b was previously reported as a blocker in the 2026-04-16 verification but the v2.0 milestone audit (2026-04-22) confirmed the home-address proximity filter is implemented in `src/shitbox/storage/route.py:22-28`, `route.py:121`, `route.py:153-157` and wired via `engine.py:627-632`. The original 2026-04-16 verifier ran before the filter was merged; this report corrects the record.

Two non-blocking warnings remain, documented in the Anti-Patterns Found table:

- `#day-videos` and `#day-timelapse` placeholder stubs in `webroot/index.html`, explicitly deferred in Plan 19-11 SUMMARY.
- Rally date placeholders in `agenda.json` (2026-05-27 to 2026-06-05 vs Brain-doc confirmed 2026-07-10), content-accuracy issue flagged in Plan 19-12 as Phase 19.1 candidate.

Neither warning blocks milestone v2.0 closure.

---

_Verified: 2026-04-16T05:30:00Z (initial)_
_Re-verified: 2026-04-22T00:00:00Z (Phase 23 closure, NARR-08b correction)_
_Verifier: Claude (gsd-verifier)_
