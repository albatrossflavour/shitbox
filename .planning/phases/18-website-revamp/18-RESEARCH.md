# Phase 18: Website Revamp — Research

**Researched:** 2026-04-10
**Domain:** Vanilla JS SPA (single-file), Leaflet 1.9.4, Grafana HTTP API, Prometheus remote write
**Confidence:** HIGH — all findings verified against actual source files

---

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Field notes embedded in the Status tab, not a new nav tab. Notes feed sits below the
  latest event stats section.
- **D-02:** Notes displayed blog-style: full note body visible in a card, with timestamp, GPS
  location link (if available), and a link to the associated event if pinned. Chronological,
  newest first.
- **D-03:** Event cards get a small note icon/badge in the card corner when a note is attached.
  Must not change card layout or height.
- **D-04:** Status tab gets a "Current Driver" card alongside the existing stats section. Name
  of currently active driver only. Simple, no percentages on the homepage.
- **D-05:** A new "Drivers" nav tab with a full per-driver breakdown table: Driver Name | Time
  Driven | % of total. Sorted by time descending.
- **D-06:** No event attribution counts in the Drivers tab for this phase -- time and percentage
  only.
- **D-07:** Fuel stops always-on on the existing Map tab. No toggle layer controls.
- **D-08:** Fuel stop popup shows: volume in litres, efficiency for that fill (km/L), and running
  average km/L across all stops to that point. Cost data never displayed (hard exclusion).
- **D-09:** Grafana section needs investigation before implementation. Planner should assess the
  iframe, layout/kiosk issues, and surrounding presentation improvements.
- **D-10:** All available v2 sensors to be graphed: DS18B20 dual-probe temps (exterior + engine
  bay), VEML7700 ambient light (lux), LIS3MDL heading/magnetometer. INA226 excluded.
- **D-11:** Dashboard tab should look good and show everything the car is measuring. No specific
  layout prescription -- Claude's discretion.

### Claude's Discretion

- Visual treatment of the notes feed on Status tab (card style, spacing)
- Fuel stop pin colour/icon to distinguish from event pins
- Exact HTML/CSS for the Drivers tab table
- How `driver-stats.json` active_driver field maps to the "Current Driver" status widget
- Grafana dashboard panel layout and arrangement

### Deferred Ideas (OUT OF SCOPE)

- Event attribution counts per driver (time/percentage only for now)
- Notes on the Map tab as pins
- INA226 power/voltage graphs in Grafana
- Toggle-able fuel stop layer

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WEB-01 | Website integrates field notes as a blog/notes section with timestamp and location | notes.json schema confirmed; fetch pattern and DOM insertion approach documented |
| WEB-02 | Website shows fuel stop pins as a Leaflet map layer with efficiency data | fuel.json schema confirmed; L.circleMarker pattern from existing initMap documented; cumulative avg gap identified |
| WEB-03 | Website shows driver stats page with time percentages | driver-stats.json schema confirmed; new Drivers tab pattern matches existing nav |
| WEB-04 | Grafana graph layouts improved; iframe kiosk issues resolved; v2 sensor coverage improved | iframe src fix confirmed; batch_sync gaps for lux/probe labels documented; Grafana API approach confirmed |
| DRVR-04 | Website shows "who's in charge" widget with current driver | driver-stats.json active_driver field confirmed; status-card insertion point confirmed |
| DRVR-05 | Website shows per-driver stats including driving time and percentage | driver-stats.json drivers[] array confirmed with total_seconds and pct fields |
| NOTE-03 | Field notes sync to website and display in a blog/notes section | generate_notes_json confirmed; nginx cache gap identified |
| FUEL-03 | Fuel stop locations and efficiency data sync to website map; cost data never syncs | generate_fuel_json confirms cost hard-exclusion at SQL level; cumulative avg field gap identified |

</phase_requirements>

---

## Summary

Phase 18 is a frontend-only phase (with two backend support changes) targeting the home-ops
repo. The public website is a single-file vanilla SPA -- no build step, no frameworks, `var`
declarations in an IIFE. All changes go into one file: `webroot/index.html`. Two supporting
changes are also required outside the website: an nginx config update (cache headers for new
JSON endpoints) and two batch_sync.py additions (VEML7700 lux metric, DS18B20 probe labels)
that the Grafana panel improvements depend on.

The data pipeline from Phases 12 and 13 is fully in place. `notes.json`, `fuel.json`, and
`driver-stats.json` are being generated and rsynced. Their schemas are confirmed from reading
the actual storage code. The website just needs to consume them. The patterns are clear: three
parallel fetches on page load, same fetch/render structure as the existing events.json fetch.

One non-obvious gap exists: the UI-SPEC requires a "running average km/L to that point" in the
fuel popup, but `generate_fuel_json()` only returns per-stop `km_per_litre`, not a cumulative
running average. This must be computed client-side from the stops array (it is trivially
calculable by accumulating distance and volume up to each stop). No backend change needed.

A second gap: the nginx config only has no-cache headers for `events.json` and `timelapse.json`.
The three new JSON files (`notes.json`, `fuel.json`, `driver-stats.json`) will fall through to
the `/captures/` location block and be served with `Cache-Control: public, max-age=86400`. This
means users would see stale data for up to 24 hours. The nginx config must be updated to add
these to the no-cache pattern.

**Primary recommendation:** Implement in waves: (1) nginx cache fix + notes/drivers/fuel
frontend changes, (2) batch_sync.py metric additions, (3) Grafana dashboard JSON update via API.
Each wave is independently deployable.

---

## Project Constraints (from CLAUDE.md)

- All markdown must pass markdownlint without overrides
- UK spelling throughout
- 1Password account: `my.1password.com` (Grafana API key lookup)
- Website stack: plain HTML/CSS/JS, no build step, no frameworks
- No `const`/`let` -- use `var` to match existing style
- All CSS inline in `<style>` block
- No external dependencies beyond Leaflet 1.9.4 (already loaded)
- Dev environment is macOS laptop, not the Pi -- no `pip install` or Pi-specific commands
- Grafana API key: check 1Password under "Grafana" or "shit-of-theseus"
- This phase is in the home-ops repo, not the shitbox repo

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vanilla JS (IIFE) | ES5 style | All interactivity | Existing codebase standard; no build step |
| Leaflet | 1.9.4 | Map rendering, circle markers, popups | Already loaded via CDN; existing map works |
| Grafana HTTP API | v1 | Dashboard JSON CRUD | Official REST endpoint for dashboard updates |

### No New Dependencies

This phase introduces zero new external dependencies. All new UI is vanilla HTML/CSS/JS. The
Grafana dashboard update uses the existing Grafana instance's REST API.

**Installation:** None required. The website has no package.json, no npm, no build step.

---

## Architecture Patterns

### Project Structure (home-ops repo target)

```text
kubernetes/apps/default/shit-of-theseus/app/
├── webroot/
│   └── index.html          # Single-file SPA — all HTML + CSS + JS inline
└── nginx-config/
    └── default.conf        # Nginx config; cache headers for /captures/*.json
```

Supporting change in shitbox repo:

```text
src/shitbox/sync/
└── batch_sync.py           # Add shitbox_lux metric; add probe label to shitbox_temp
```

### Pattern 1: Existing Nav Tab Extension

The existing nav uses `data-section` attributes and a click handler at line 882. To add a new
Drivers tab:

1. Add `<a href="#drivers" data-section="drivers">Drivers</a>` after Status in `<nav>`
2. Add `<div id="drivers-section" class="section">` in `<main>`
3. Add `'drivers'` to `validSections` array (line 908)

No changes to the click handler itself -- it's generic. The map/timelapse initialisation guards
are the only special cases, and Drivers needs none.

Insert order per UI-SPEC: Status | **Drivers** | Videos | Timelapse | Map | Dashboard | The Car |
Route | About

### Pattern 2: Parallel JSON Fetch on Page Load

Existing pattern (line 914):

```js
// Source: index.html line 914
fetch('/captures/events.json', { cache: 'no-cache' })
    .then(function(r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
    })
    .then(function(events) {
        eventsData = events;
        renderEvents(events);
        renderStatus(events);
    })
    .catch(function() {
        // show error state
    });
```

The three new fetches follow this exact pattern. They are parallel (not chained). Each stores
its result in a module-level `var` for use by tab-activation guards.

Add at IIFE top (alongside `var eventsData = null`):

```js
var notesData = null;
var fuelData = null;
var driverStatsData = null;
```

### Pattern 3: Leaflet Circle Marker (existing, reuse for fuel stops)

```js
// Source: index.html line 1307 -- existing event marker pattern
var marker = L.circleMarker([ev.lat, ev.lng], {
    radius: 8,
    fillColor: color,
    color: '#fff',
    weight: 2,
    opacity: 0.9,
    fillOpacity: 0.85
}).bindPopup(popupLines.join(''));
marker.addTo(map);
```

Fuel stops use `fillColor: '#c06000'` (accent orange, per UI-SPEC). Added after the events
loop in `initMap()` so fuel pins appear on top of event pins.

### Pattern 4: status-card Injection

The `.status-grid` is a CSS grid with `repeat(auto-fill, minmax(200px, 1fr))`. Adding another
`.status-card` div simply adds another cell -- the grid reflows automatically. No layout
changes needed.

### Pattern 5: Grafana Dashboard via HTTP API

Grafana supports reading and writing dashboard JSON via REST:

```bash
# Read current dashboard JSON
GET https://grafana.shit-of-theseus.com/api/dashboards/uid/shitbox-rally-command

# Write updated dashboard JSON
POST https://grafana.shit-of-theseus.com/api/dashboards/db
Content-Type: application/json
Authorization: Bearer <api-key>

{"dashboard": {...updated panels...}, "overwrite": true, "folderId": 0}
```

API key: check 1Password at `my.1password.com` under "Grafana" or "shit-of-theseus".

### Anti-Patterns to Avoid

- **`const`/`let`:** The existing codebase uses `var` throughout. Using modern syntax breaks
  the existing style contract and may cause confusion. Match `var`.
- **Chained fetches:** Do not chain the three new fetches. Run them in parallel. The rendering
  functions handle the case where their data arrives null.
- **Mutating eventsData:** Note badges require correlating events with notes by event_id. Do
  this after `renderEvents()` populates the DOM -- inject badges by iterating `notesData`.
- **Light tile layer on main map:** The main map currently uses `light_all` CartoDB tiles (line
  1263), NOT `dark_all`. The status mini-map uses dark tiles. The UI-SPEC refers to "dark
  CartoDB tiles" but the actual code uses light. Do not change the tile layer -- the UI-SPEC
  description is incorrect about current state. Leave existing tiles unless explicitly directed.

---

## Confirmed Data Schemas

These are verified against the actual production code, not assumptions.

### notes.json (from `generate_notes_json()`)

Array of objects, each with:

```json
{
  "id": 1,
  "timestamp_utc": "2026-04-10T03:00:00+00:00",
  "body": "Note text here",
  "event_id": 42,
  "lat": -16.9186,
  "lng": 145.7781,
  "gps_stale": false
}
```

Source: `src/shitbox/storage/logbook.py` `list_notes()`, line 140.

`event_id` is an integer (the `events` table primary key), nullable. Deep-linking from a note
to an event card requires matching this against event cards by `id` attribute
(`id="event-{id}"`). The events.json schema does include `id`.

Notes returned in ascending timestamp order (oldest first). The website renders newest first,
so client-side `.reverse()` or sort is needed.

### fuel.json (from `generate_fuel_json()`)

Array of objects, each with:

```json
{
  "id": 1,
  "timestamp_utc": "2026-04-10T05:00:00+00:00",
  "volume_litres": 45.5,
  "lat": -17.1234,
  "lng": 144.5678,
  "gps_stale": false,
  "odometer_km": 1250.0,
  "km_per_litre": 11.2
}
```

Source: `src/shitbox/storage/logbook.py` `generate_fuel_json()`, line 154.

**Critical gap:** `km_per_litre` is per-stop efficiency only. There is no `cumulative_avg_kml`
field. The UI-SPEC popup requires "Running avg: X.X km/L" which is the cumulative efficiency
up to and including that stop. This must be computed client-side by accumulating `odometer_km`
distance and `volume_litres` across stops in order.

Client-side algorithm:

```js
// Compute running average km/L up to each stop
var cumDist = 0, cumVol = 0;
fuelStops.forEach(function(stop, i) {
    if (i > 0 && stop.odometer_km != null && fuelStops[i-1].odometer_km != null) {
        var dist = stop.odometer_km - fuelStops[i-1].odometer_km;
        if (dist > 0) {
            cumDist += dist;
            cumVol += stop.volume_litres;
        }
    }
    stop._cumAvgKml = (cumVol > 0) ? (cumDist / cumVol).toFixed(1) : null;
});
```

First stop always has `_cumAvgKml = null` (no prior stop to measure from). Show as "—" in
popup.

`km_per_litre` for the first stop is also null (same reason -- no prior odometer reading to
calculate distance from). Both null values should display as "—" in the popup.

### driver-stats.json (from `get_driver_stats_payload()`)

```json
{
  "active_driver": "Tony",
  "drivers": [
    {"driver_name": "Tony", "total_seconds": 51780, "pct": 62.3},
    {"driver_name": "Smithy", "total_seconds": 31320, "pct": 37.7}
  ]
}
```

Source: `src/shitbox/storage/driver.py` `get_driver_stats_payload()`, line 85.

`active_driver` is a string (driver name) or null (no driver set). The "Current Driver" card
shows this value or "—" when null.

`drivers` array is sorted by `total_seconds` descending (from the SQL query).

`total_seconds` needs formatting as "Xh Ym" client-side:
`Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm'`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Map markers | Custom SVG/canvas markers | `L.circleMarker()` | Already used for events; consistent visual language; handles projection, clicks, popups |
| JSON fetching | XMLHttpRequest or custom retry | `fetch()` + `.then()` | Already the site pattern; Promise-based; clean error handling |
| Grafana dashboard edit | Manual JSON editing in browser | Grafana HTTP API (`POST /api/dashboards/db`) | Atomic update; preserves dashboard metadata; version-tracked |
| Time formatting | Date arithmetic from scratch | Pattern from existing code: `toLocaleTimeString('en-AU', {timeZone: TIMEZONE})` | Handles AEST/AEDT correctly |

**Key insight:** The hardest part of this phase is paying attention to what already exists in
index.html and following it exactly rather than reinventing. The patterns are already there.

---

## Nginx Cache Gap

**This is a blocker for NOTE-03, FUEL-03, DRVR-04, DRVR-05.**

Current `nginx-config/default.conf`:

```nginx
location ~ ^/captures/(events|timelapse)\.json$ {
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    ...
}

location /captures/ {
    add_header Cache-Control "public, max-age=86400";  # 24-hour cache
}
```

The three new JSON files fall through to the second block and get 24-hour caching. Users would
see stale notes, fuel stops, and driver data for up to 24 hours after a sync.

**Fix:** Update the regex to include the new files:

```nginx
location ~ ^/captures/(events|timelapse|notes|fuel|driver-stats)\.json$ {
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Pragma "no-cache";
    add_header Expires "0";
}
```

This is a one-line change to `nginx-config/default.conf`. The Flux HelmRelease picks it up on
reconcile.

---

## batch_sync.py Metric Gaps

These gaps block the Grafana panel improvements (WEB-04, D-10).

### Gap 1: shitbox_lux not published

`batch_sync.py` has no handling for `SensorType.LIGHT`. The VEML7700 lux readings reach the
database but never reach Prometheus. Code change needed in `_readings_to_metrics()`:

```python
# Add after the 'environment' block in _readings_to_metrics()
elif reading.sensor_type.value == "light":
    if reading.lux is not None:
        metrics.append(
            ("shitbox_lux", labels, reading.lux, timestamp_ms)
        )
```

Verify the field name against `src/shitbox/storage/models.py` -- confirm the Reading model
has a `lux` field and the sensor_type value for VEML7700 is `"light"`.

### Gap 2: shitbox_temp has no probe label

Both DS18B20 probes write to `shitbox_temp` with no distinguishing label. From STATE.md:

- Exterior probe: `28-00000024263a`
- Engine bay probe: `28-0000002405b1`

The temperature collector writes `SensorType.TEMP` readings. The collector (or the reading
model) must include the probe ID or a human-readable label so `_readings_to_metrics()` can
emit `probe` labels.

This requires investigation of `src/shitbox/collectors/temperature.py` and
`src/shitbox/storage/models.py` to determine whether the probe ID is already on the Reading
object or needs adding. If the Reading model has a `sensor_id` or similar field populated by
the DS18B20 collector, the batch_sync change is:

```python
elif reading.sensor_type.value == "temp":
    if reading.temp_celsius is not None:
        probe_id = getattr(reading, 'sensor_id', None)
        probe_label = 'exterior' if probe_id == '28-00000024263a' else \
                      'engine_bay' if probe_id == '28-0000002405b1' else 'unknown'
        temp_labels = dict(labels)
        temp_labels['probe'] = probe_label
        metrics.append(
            ("shitbox_temp", temp_labels, reading.temp_celsius, timestamp_ms)
        )
```

**Important:** This is a Prometheus label change. Adding a `probe` label to an existing metric
creates new series. If there is existing `shitbox_temp` data without the label, Prometheus
will treat them as different series. Old data without labels remains; new data has labels.
This is expected behaviour -- Grafana can show both by querying
`shitbox_temp{probe="exterior"}` for new data.

### Gap 3: LIS3MDL magnetometer not published

`batch_sync.py` has `imu_heading` handling for `heading_deg`, `accel_x` (pitch), `accel_y`
(roll) but the sensor type name needs verification. The heading is already partially published
as `shitbox_heading`. No new metric needed for the basic heading display. Only needed if
individual magnetometer axes (`mx`, `my`, `mz`) are required -- lower priority per D-10.

---

## Grafana Dashboard Investigation

The UI-SPEC documents the full Grafana analysis from prior investigation. Key findings:

### Current State

- **Old dashboard** (`shitbox-telemetry`): Uses OSM light tiles, has a broken
  "Barometric Pressure / Sync Backlog" panel mixing unrelated metrics. Not the iframe target.
- **Current dashboard** (`shitbox-rally-command`): Already uses dark CartoDB tiles and site
  badge colours. This is the one to fix and the iframe to show.

### iframe Fix

Current code (index.html line 632):

```html
<iframe src="https://grafana.shit-of-theseus.com/d/shitbox-telemetry?orgId=1&kiosk" ...>
```

Needs changing to:

```html
<iframe src="https://grafana.shit-of-theseus.com/d/shitbox-rally-command?orgId=1&kiosk" ...>
```

Also: increase height from `80vh` to `90vh`, move "Open full Grafana dashboard" link above the
iframe, add description text, add loading state.

### Dashboard Panel Reorganisation

Per UI-SPEC D-09/D-11 and the panel analysis:

- Row 1 (y=0): Driving metrics -- Speed, G-Force, Top Speed, Peak G, Altitude (keep as-is)
- Row 2: System health -- GPS fix, Sats, Throttle, CPU Temp, Disk Free, CPU %
- Row 3: Environment stats -- Cabin temp, Pressure, Humidity, Power
- New panel: Ambient Light (after DS18B20 labeling and `shitbox_lux` publishing)
- Updated Temperatures panel: add DS18B20 exterior + engine bay series (after probe labeling)

Dashboard update via API requires reading current JSON first (GET), modifying panel definitions,
then writing back (POST with `overwrite: true`).

---

## Common Pitfalls

### Pitfall 1: Note badge breaks event card layout

**What goes wrong:** Adding `.note-badge` as a child of `.event-card` without
`position: relative` on the card causes the badge to position relative to the nearest
positioned ancestor (possibly the body). Cards jump or overlap.

**Why it happens:** `.event-card` has no `position` set currently.

**How to avoid:** Add `position: relative` to `.event-card` CSS rule (or inline on the element
at inject time). The UI-SPEC documents this explicitly.

**Warning signs:** Badge appears in wrong location, overlaps other cards.

### Pitfall 2: Fuel popup shows null for efficiency

**What goes wrong:** The first fuel stop always has `km_per_litre: null` (no prior odometer
reading). The popup renders "This stop: null km/L".

**Why it happens:** Efficiency is calculated from distance since last stop. First stop has no
prior reference.

**How to avoid:** Guard all efficiency values: `stop.km_per_litre != null ? stop.km_per_litre.toFixed(1) + ' km/L' : '—'`.
Same for cumulative avg.

### Pitfall 3: Note event_id deep-link mismatch

**What goes wrong:** The footer of a note card says "View linked event" but the link navigates
to `#videos` and the target card doesn't highlight because the event ID matching fails.

**Why it happens:** Notes have `event_id` as an integer. Event cards are rendered with
`id="event-{id}"` in `renderEvents()`. If the events haven't loaded yet when notes render,
or the event with that ID is filtered out (e.g., before RALLY_START), the element won't exist.

**How to avoid:** Guard the event link: only add it if
`document.getElementById('event-' + note.event_id)` exists. If not, omit the link.

### Pitfall 4: driverStatsData fetch race with renderStatus

**What goes wrong:** `renderStatus()` runs on events.json load. `driver-stats.json` may arrive
before or after. The Current Driver card shows "—" permanently if the data arrives before
the card DOM element exists, or the fetch completes after renderStatus already ran.

**Why it happens:** Parallel async fetches have no guaranteed order.

**How to avoid:** Populate the Current Driver card whenever both conditions are met: DOM exists
AND data available. Check in both the `driver-stats.json` then-handler AND in `renderStatus()`.
Since it's a simple `textContent` set, it's idempotent -- set it whenever the data is present.

### Pitfall 5: 24-hour cached JSON responses

**What goes wrong:** A visitor sees stale notes/fuel/driver data for up to 24 hours after the
Pi syncs new data.

**Why it happens:** The nginx `/captures/` location block applies `max-age=86400` to anything
not matched by the specific `events.json|timelapse.json` pattern.

**How to avoid:** Update nginx config regex before deploying the frontend changes. If the cache
header fix isn't deployed first, the frontend works but serves stale data.

### Pitfall 6: Grafana API authentication

**What goes wrong:** `POST /api/dashboards/db` returns 401 or 403.

**Why it happens:** Grafana requires either a service account token or an API key with Editor
role. Basic auth may not work depending on Grafana config.

**How to avoid:** Use a Bearer token from 1Password (`my.1password.com`, "Grafana" or
"shit-of-theseus"). Retrieve the current dashboard JSON via GET first to confirm auth works
before attempting the write.

---

## Code Examples

### New module-level vars (add near top of IIFE)

```js
// Source: following existing pattern at index.html line 878
var eventsData = null;
var notesData = null;    // add
var fuelData = null;     // add
var driverStatsData = null;  // add
var mapInitialised = false;
```

### notes.json fetch

```js
// Source: following index.html line 914 pattern
fetch('/captures/notes.json', { cache: 'no-cache' })
    .then(function(r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
    })
    .then(function(notes) {
        notesData = notes.slice().reverse(); // newest first
        renderNotes(notesData);
        injectNoteBadges(notesData);
    })
    .catch(function() {
        // silent failure -- notes section shows empty state
    });
```

### driver-stats.json fetch and Current Driver card update

```js
fetch('/captures/driver-stats.json', { cache: 'no-cache' })
    .then(function(r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
    })
    .then(function(data) {
        driverStatsData = data;
        var el = document.getElementById('status-current-driver');
        if (el) {
            el.textContent = data.active_driver || '\u2014';
        }
        renderDrivers(data);
    })
    .catch(function() {
        // silent failure
    });
```

### Fuel stop popup with null guards

```js
// Source: following index.html line 1289 popup pattern
var popupLines = [
    '<div class="map-popup">',
    '<div class="popup-type" style="color:#c06000">Fuel Stop</div>',
    '<div class="popup-detail">',
    dateStr + ' ' + timeStr,
    '<br>Volume: ' + stop.volume_litres.toFixed(1) + ' L',
    '<br>This stop: ' + (stop.km_per_litre != null
        ? stop.km_per_litre.toFixed(1) + ' km/L' : '\u2014'),
    '<br>Running avg: ' + (stop._cumAvgKml != null
        ? stop._cumAvgKml + ' km/L' : '\u2014'),
    '</div></div>'
];
```

### Time formatting for Drivers table

```js
function formatDriveTime(seconds) {
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    return h + 'h ' + m + 'm';
}
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Leaflet 1.9.4 | Map + fuel pins | Loaded via CDN | 1.9.4 | None needed |
| Grafana instance | WEB-04 (dashboard update) | Running at grafana.shit-of-theseus.com | Unknown | Manual JSON edit |
| Grafana API key | WEB-04 (API write) | In 1Password | Unknown | Retrieve before implementing |
| Flux/home-ops | Deployment | Existing infrastructure | Running | N/A |
| `notes.json` endpoint | WEB-01, NOTE-03 | Generated by Phase 12 | Deployed | 404 handled silently |
| `fuel.json` endpoint | WEB-02, FUEL-03 | Generated by Phase 12 | Deployed | 404 handled silently |
| `driver-stats.json` endpoint | DRVR-04, DRVR-05 | Generated by Phase 13 | Deployed | 404 handled silently |

**Missing dependencies with no fallback:**
- Grafana API key (must be retrieved from 1Password before Grafana work begins)

**Missing dependencies with fallback:**
- All three JSON files: if not yet present on NAS (Pi not connected), website silently shows
  empty states. This is by design -- the site degrades gracefully.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (shitbox repo); no test framework for website (static files) |
| Config file | `pytest.ini` / `pyproject.toml` in shitbox repo |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest --cov=shitbox` |

Note: The website itself (index.html) has no automated test framework. Validation is via
manual browser testing of the deployed site. The only automated tests in this phase cover the
`batch_sync.py` metric additions (shitbox repo).

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|--------------|
| WEB-01 | Notes fetch, render, empty state | Manual browser | N/A | N/A |
| WEB-02 | Fuel pins on map, popup content | Manual browser | N/A | N/A |
| WEB-03 | Drivers tab renders, time format correct | Manual browser | N/A | N/A |
| WEB-04 | Grafana iframe src correct, height | Manual browser | N/A | N/A |
| DRVR-04 | Current Driver card shows active_driver | Manual browser | N/A | N/A |
| DRVR-05 | Drivers table row count and data | Manual browser | N/A | N/A |
| NOTE-03 | Notes section visible, GPS link, event link | Manual browser | N/A | N/A |
| FUEL-03 | Fuel pins visible, no cost field | Manual browser | N/A | N/A |
| WEB-04 (backend) | `shitbox_lux` published to Prometheus | unit | `pytest tests/sync/test_batch_sync.py -x -q` | ❌ Wave 0 |
| WEB-04 (backend) | `shitbox_temp` has probe label | unit | `pytest tests/sync/test_batch_sync.py -x -q` | ❌ Wave 0 |

### Sampling Rate

- Per task commit: Manual visual check of affected section in browser
- Per wave merge: Full manual walkthrough of Status, Drivers, Map, and Dashboard tabs
- Phase gate: All tabs functional with mock/real JSON data before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/sync/test_batch_sync.py` -- extend with test for `shitbox_lux` metric emission
- [ ] `tests/sync/test_batch_sync.py` -- extend with test for `probe` label on `shitbox_temp`

If the test file doesn't exist: `pytest tests/sync/` to check current coverage first.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Grafana anonymous iframe (no auth) | Grafana kiosk mode with `?kiosk` param | Already in place | Hides Grafana chrome; correct approach |
| `shitbox-telemetry` dashboard (old) | `shitbox-rally-command` (current) | Prior to Phase 18 | iframe src needs updating |
| Single `shitbox_temp` series | Two labeled series (`probe=exterior/engine_bay`) | Phase 18 | Breaks old panels; plan accordingly |

---

## Open Questions

1. **Does the Reading model have a probe identifier for DS18B20?**
   - What we know: Both DS18B20 probes write to `SensorType.TEMP`; probe IDs are in STATE.md
   - What's unclear: Whether `src/shitbox/storage/models.py` or the temperature collector
     passes the probe ID through to the Reading object
   - Recommendation: Read `src/shitbox/collectors/temperature.py` and
     `src/shitbox/storage/models.py` at plan time to confirm before designing the batch_sync change

2. **Is `shitbox_lux` the right metric name and is `reading.lux` the right field?**
   - What we know: VEML7700 is confirmed on I2C bus; `SensorType.LIGHT` likely exists
   - What's unclear: Exact field name on the Reading model for lux values
   - Recommendation: Read `src/shitbox/storage/models.py` and `src/shitbox/collectors/light.py`
     at plan time to confirm field names

3. **Current driver-stats.json format from Phase 13 -- does `active_driver` match the driver
   name in `drivers[]` array or is it a separate identifier?**
   - What we know: `get_driver_stats_payload()` returns `{"active_driver": driver_state.get_active_driver(), "drivers": [...]}`; `driver_name` in each driver entry is the string name
   - What's unclear: Nothing -- field names are confirmed. Active driver matches by string
     comparison against `driver_name` in each row.
   - Recommendation: No investigation needed; schema is clear.

---

## Sources

### Primary (HIGH confidence)

- `src/shitbox/storage/logbook.py` -- `generate_notes_json()`, `generate_fuel_json()` -- exact JSON schemas confirmed
- `src/shitbox/storage/driver.py` -- `get_driver_stats_payload()` -- driver-stats.json schema confirmed
- `src/shitbox/sync/batch_sync.py` -- `_readings_to_metrics()` -- confirmed no lux metric, no probe labels on temp
- `src/shitbox/sync/capture_sync.py` -- `register_json_generator()` -- confirmed generator pattern
- `~/dev/home-ops/.../webroot/index.html` -- all patterns (nav, fetch, map, status grid) confirmed from source
- `~/dev/home-ops/.../nginx-config/default.conf` -- cache header gap confirmed
- `.planning/phases/18-website-revamp/18-CONTEXT.md` -- locked decisions
- `.planning/phases/18-website-revamp/18-UI-SPEC.md` -- component specifications

### Secondary (MEDIUM confidence)

- Grafana HTTP API (dashboard CRUD): standard Grafana feature, confirmed present in all
  Grafana versions since v5. Full authentication flow depends on Grafana instance config.

### Tertiary (LOW confidence -- validate at plan time)

- DS18B20 probe ID passthrough to Reading model: assumed based on STATE.md probe IDs and
  existing collector patterns; not verified by reading temperature.py or models.py

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH -- no new dependencies; existing site fully read
- Architecture patterns: HIGH -- verified against actual index.html source
- Data schemas: HIGH -- read directly from storage code (logbook.py, driver.py)
- Pitfalls: HIGH -- derived from actual code gaps found during research
- Grafana metric gaps: HIGH -- confirmed by reading batch_sync.py _readings_to_metrics()
- DS18B20 probe label change: MEDIUM -- batch_sync gap confirmed; exact model field name unverified

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable project; 30-day window is conservative)
