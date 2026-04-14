# Phase 18: Website Revamp - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrate field notes, fuel stops, and driver data from the sync pipeline into the public website
(`shit-of-theseus.com`). Improve Grafana dashboard layout and coverage. All changes are to the
home-ops repo (`~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/`) and deploy via
Flux HelmRelease.

This phase does NOT modify the shitbox Pi daemon. It consumes JSON exports already produced by
Phases 12 and 13 (`notes.json`, `fuel.json`, `driver-stats.json`) via NAS rsync.

</domain>

<decisions>
## Implementation Decisions

### Notes Section
- **D-01:** Field notes are embedded in the **Status tab** — no new nav tab. Notes feed sits
  **below the latest event stats** section on the existing Status page.
- **D-02:** Notes are displayed **blog-style**: full note body visible in a card, with timestamp,
  GPS location link (if available), and a link to the associated event if one was pinned at capture
  time. Chronological, newest first.
- **D-03:** Event cards in the Videos/events section get a **small note icon/badge** (e.g. a pencil
  or document icon) in the card corner when a note is attached. The icon is unobtrusive and must not
  change the card layout or height.

### Driver Presentation
- **D-04:** The Status tab gets a **"Current Driver" card** alongside the existing latest stats
  section. Shows the name of the currently active driver. Simple — no percentages on the homepage.
- **D-05:** A new **"Drivers" nav tab** is added with a full per-driver breakdown table:
  Driver Name | Time Driven | % of total. Sorted by time descending.
- **D-06:** No event attribution counts in the Drivers tab for this phase — time and percentage only.

### Fuel Map Layer
- **D-07:** Fuel stops are **always on** — no toggle layer controls. They render as a distinct pin
  type on the existing Map tab alongside event pins.
- **D-08:** Fuel stop popup shows: volume in litres, efficiency for that fill (km/L), and running
  average km/L across all stops to that point. **Cost data is never displayed** (hard exclusion,
  per Phase 12 D-10).

### Grafana Dashboard
- **D-09:** The current Grafana section needs **investigation before implementation**. The planner
  should assess what the iframe is actually showing, what layout/kiosk issues exist, and what a
  UI/UX pass looks like. The surrounding website presentation of the Grafana iframe should also
  be improved — it's not just an iframe problem.
- **D-10:** All available v2 sensors should be graphed: DS18B20 dual-probe temps (exterior +
  engine bay), VEML7700 ambient light (lux), LIS3MDL heading/magnetometer. **INA226 is excluded**
  — not currently wired in, purpose TBD.
- **D-11:** The goal is that the Dashboard tab looks good and shows everything the car is
  measuring. No specific layout prescription — Claude's discretion on graph arrangement.

### Claude's Discretion
- Visual treatment of the notes feed on Status tab (card style, spacing) — consistent with existing
  dark theme (#0d1117 / #161b22 / orange accent)
- Fuel stop pin colour/icon to distinguish from event pins on the map
- Exact HTML/CSS for the Drivers tab table — follow existing table patterns in the site
- How `driver-stats.json` current driver field maps to the "Current Driver" Status widget
- Grafana dashboard panel layout and arrangement

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Website (primary target)
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html` — Single-file
  SPA. All HTML, CSS, and JS inline. 1366 lines. Read this before touching anything.
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/nginx-config/default.conf` —
  Nginx config; understand how `/captures/` paths are served.

### Data sources (JSON files from sync pipeline)
- `notes.json` served from `/captures/notes.json` — produced by Phase 12 `generate_notes_json()`
- `fuel.json` served from `/captures/fuel.json` — produced by Phase 12 `generate_fuel_json()`
  (cost excluded at SQL level)
- `driver-stats.json` served from `/captures/driver-stats.json` — produced by Phase 13 driver
  stats generator; includes current active driver + time/percentage per driver

### Prior phase context (data shape decisions)
- `.planning/phases/12-schema-foundation-and-logbook-api/12-CONTEXT.md` — Notes and fuel stop
  data model, GPS stale flag, cost exclusion enforcement
- `.planning/phases/13-driver-tracking/13-CONTEXT.md` — driver-stats.json payload design,
  active driver field

### Requirements
- `.planning/REQUIREMENTS.md` — WEB-01, WEB-02, WEB-03, WEB-04, DRVR-04, DRVR-05, NOTE-03,
  FUEL-03 are this phase's requirements.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Dark theme CSS variables**: `#0d1117` bg, `#161b22` cards, `#21262d` borders, `#c06000`
  orange accent, `#e0a040` amber, `#f0dbb8` warm white, `#8b949e` muted text
- **Tab/section pattern**: `nav a[data-section]` + `.section.active` CSS + click handler at
  line ~882. Adding a new tab (Drivers) follows this exact pattern.
- **Event card structure**: `.event-card` in `.events-grid` — grid of cards, each with badge,
  stats, video. Note icon goes in card corner without breaking grid layout.
- **Leaflet map** already initialised with CartoDB dark tiles and event pin layer. Fuel stop
  layer is an additional `L.layerGroup()` — follows same pattern as existing event markers.
- **fetch + JSON parse** pattern at line 914 (`fetch('/captures/events.json')`). Notes, fuel,
  and driver-stats follow the same fetch-on-load pattern.

### Established Patterns
- Single-file SPA, no build step, no frameworks — all changes go in `index.html`
- Vanilla JS (`var`, not `const`/`let` — match existing style) and inline CSS
- `BADGE_COLORS` map for event types (lines 855-864) — fuel stops need a distinct colour
- Tab sections are `<div id="{name}-section" class="section">` blocks

### Integration Points
- Nav `<a href="#drivers" data-section="drivers">Drivers</a>` — new tab in nav
- `<div id="drivers-section" class="section">` — new section in main
- `eventsData` loaded at page load — notes/fuel/driver-stats need parallel fetches
- Status tab DOM (line ~580+) — insert "Current Driver" card and notes feed here
- Map initialisation (line ~892 guard) — add fuel stop layer after map is created

</code_context>

<specifics>
## Specific Ideas

- "Current Driver" widget on Status tab is a card-style stat, not a prominent headline — fits
  alongside the existing "today's peak G / top speed" stats section
- Notes feed on Status tab: chronological, newest first, below the stats section — public readers
  can follow along like a trail journal
- Fuel stop pins on the Map should visually differ from event pins so users can immediately
  distinguish them (event pins are colour-coded by type; fuel pins could be a petrol pump icon
  or a distinct neutral colour like blue/green)
- The Grafana tab just "isn't awesome" — planner should do a proper look at the current state
  and propose improvements rather than working from a fixed spec

</specifics>

<deferred>
## Deferred Ideas

- Event attribution counts per driver (e.g. "Tony: 3 HIGH_G, 7 BIG_CORNER") — noted for a
  future pass; time/percentage only for now
- Notes on the Map tab as pins — notes have GPS coordinates but the user didn't ask for map pins;
  Status feed only for this phase
- INA226 power / voltage graphs in Grafana — not wired in, deferred until hardware is confirmed
- Toggle-able fuel stop layer — kept simple with always-on for now

</deferred>

---

*Phase: 18-website-revamp*
*Context gathered: 2026-04-10*
