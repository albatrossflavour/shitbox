---
phase: 19
plan: "07"
subsystem: website
tags: [website, day-page, leaflet, map, polyline, spa-lifecycle, route-json]
dependency_graph:
  requires: [routeData, eventsData, BADGE_COLORS, _dayOf, _formatSpineTime, escapeHtml, renderDayPage-scaffold, renderHomepage, renderAbout]
  provides: [initDayMap, _teardownDayMap, _currentDayMap, day-map-container-css]
  affects: [shit-of-theseus.com, NARR-09]
tech_stack:
  added: []
  patterns: [spa-leaflet-lifecycle, module-level-instance-tracker, fitBounds-day-slice, singletons-with-teardown]
key_files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - "Module-level _currentDayMap tracks the single active Leaflet instance — _teardownDayMap() called at top of initDayMap (re-render) and at top of renderHomepage/renderAbout (route change)"
  - "invalidateSize() called after 100ms setTimeout — Leaflet measures the container dimensions after the SPA div is painted, not just inserted into the DOM"
  - "No-route-data case renders .day-map-empty (muted dashed placeholder) rather than hiding the section — preserves D-12 section order on the page"
  - "Day slice fitBounds uses padding:[20,20] so the orange line doesn't touch the map edge on mobile"
metrics:
  duration_seconds: 480
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 1
---

# Phase 19 Plan 07: Day-Page Map Summary

One-liner: Leaflet day-page map with the full-rally polyline as a grey backdrop and the current day's slice highlighted in rally orange on top, event pins colour-coded via BADGE_COLORS, with teardown-safe SPA lifecycle via a module-level instance tracker.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CSS + initDayMap + teardown-safe Leaflet lifecycle | 9edab652 (home-ops) | webroot/index.html |
| 2 | Wire initDayMap into renderDayPage + teardown on route change | 36ae3788 (home-ops) | webroot/index.html |

## What Was Built

### CSS (Task 1)

Inserted after `.spine-item.agenda_camping` block:

- `.day-map-container`: `width: 100%; height: 400px; background: #0d1117; border: 1px solid #2a1f0e; border-radius: 8px; overflow: hidden`
- `.day-map-empty`: dashed `#30363d` border, muted italic text — used when routeData has no entries for the day
- `@media (max-width: 600px)`: `.day-map-container { height: 280px }` — functional on mobile

### Module-level state (Task 1)

`var _currentDayMap = null` added alongside the other six data vars (`eventsData`, `notesData`, `fuelData`, `driverStatsData`, `agendaData`, `routeData`).

### _teardownDayMap() (Task 1)

Calls `_currentDayMap.remove()` (wrapped in try/catch for Leaflet edge cases) and nulls the reference. Called from:

1. Top of `initDayMap` — handles day→day navigation
2. Top of `renderHomepage` — handles day→home navigation
3. Top of `renderAbout` — handles day→about navigation

### initDayMap(dayISO, route, events) (Task 1)

Full function flow:

1. `_teardownDayMap()` — always runs first
2. Early exit if `#day-map` div not in DOM
3. No-data path: if `route` is null or has no days at all, set `.day-map-empty` class + textContent, return
4. Build Leaflet map on `#day-map` with CartoDB `dark_all` tile layer (matches Status map exactly)
5. Backdrop: iterate all days in `route.days`, skip `dayISO`, draw grey polylines (`#484f58`, weight 3, opacity 0.55, non-interactive)
6. Day slice: draw orange polyline (`#e0a040`, weight 5, opacity 0.95) and call `fitBounds` with 20px padding
7. Event pins: filter `eventsData` by `_dayOf(ev.timestamp) === dayISO && ev.lat != null && ev.lng != null`, draw `L.circleMarker` with `BADGE_COLORS[ev.type]` fill, bind popup with escaped type + `_formatSpineTime` timestamp
8. `setTimeout(invalidateSize, 100)` — prevents Leaflet rendering into a zero-height container on initial SPA mount

### renderDayPage wiring (Task 2)

Two changes:

1. `mapPlaceholder` declaration changed from `day-section-placeholder` with placeholder text to `<div id="day-map" class="day-map-container"></div>` — clean empty host for Leaflet
2. After the spine-wiring block, added: `initDayMap(dayISO, routeData, eventsData);`

## Leaflet Init-Timing Notes

The `invalidateSize()` call with a 100ms delay is the key gotcha for SPA-mounted Leaflet maps. When Leaflet initialises inside a div that was just injected by `showRoute(html)`, the browser may not have performed layout yet. Leaflet reads the container dimensions at init time — if it measures zero, it renders tile requests at the wrong zoom level and the map appears blank. The 100ms delay gives the browser one layout pass. This is the same pattern used by any Leaflet-in-tabs or Leaflet-in-modal implementation.

If future plans embed the day map in a collapsible section or a CSS `display:none` panel, a longer delay (or an explicit `ResizeObserver` trigger) may be needed. 100ms is enough for the current flat-page SPA layout.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `#day-videos` | webroot/index.html | Intentional. Phase 19 backfill wires video highlights. |
| `#day-timelapse` | webroot/index.html | Intentional. Phase 19 backfill wires timelapse embed. |

The `#day-map` stub from Plans 19-05 and 19-06 is now resolved.

## Threat Surface Scan

- T-19-07-01 accepted at Plan 19-01: home address exclusion is in `RouteStorage` (Pi-side). Day-map consumes `route.json` as-is. No new client-side mitigation needed.
- T-19-07-02 mitigated: `_currentDayMap` + `_teardownDayMap()` pattern prevents Leaflet instance accumulation on SPA navigation. Verified: 4 `_teardownDayMap` call sites (definition + initDayMap + renderHomepage + renderAbout).
- T-19-07-03 accepted: Douglas-Peucker at 10m tolerance on Pi side caps day slices at ~1-2k points. No client-side thinning needed.

No new trust boundaries introduced.

## Self-Check: PASSED

- `function initDayMap` count: 1 — FOUND
- `function _teardownDayMap` count: 1 — FOUND
- `var _currentDayMap` count: 1 — FOUND
- CartoDB `dark_all` tile URL count (>=2): 2 — FOUND
- Backdrop colour `#484f58`: FOUND
- Day-slice colour `#e0a040` in initDayMap (line 1607): FOUND
- `BADGE_COLORS[ev.type]` in initDayMap: FOUND
- `_dayOf(ev.timestamp) === dayISO` filter: FOUND
- `invalidateSize()` call: FOUND
- `fitBounds` call: FOUND
- `initDayMap(dayISO, routeData, eventsData)` in renderDayPage: 1 — FOUND
- `_teardownDayMap()` first line of renderHomepage: CONFIRMED (line 1762)
- `_teardownDayMap()` first line of renderAbout: CONFIRMED (line 1772)
- "Day map placeholder" text: NOT FOUND (removed)
- `id="day-map" class="day-map-container"` in HTML: 1 — FOUND
- Commits 9edab652 and 36ae3788 exist in home-ops main: CONFIRMED
