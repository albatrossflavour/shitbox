---
phase: 19
plan: "05"
subsystem: website
tags: [website, day-page, css, javascript, xss-mitigation, haversine, agenda-context]
dependency_graph:
  requires: [agendaData, routeData, eventsData, fuelData, renderDayNav, escapeHtml, showRoute, navigateHome, TIMEZONE]
  provides: [renderDayPage-scaffold, renderAgendaContext, computeDayStats, escapeHtml, day-page-css]
  affects: [shit-of-theseus.com, Plans 19-06, 19-07]
tech_stack:
  added: []
  patterns: [haversine-distance, xss-escape-helper, d12-section-order, en-CA-timezone-bucketing]
key_files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - "escapeHtml() added as standalone helper covering all five dangerous chars (&, <, >, \", ') — applied to every agenda field before innerHTML concatenation (T-19-05-01)"
  - "Haversine computed over routeData.days[dayISO].points array to derive km driven — no separate distance field needed from events"
  - "_dayOf() reuses existing en-CA/TIMEZONE bucketing pattern verbatim — no new timezone code (T-19-05-02)"
  - "cost_aud excluded by design: computeDayStats uses only volume_litres from fuelData (T-19-05-03)"
  - "D-12 section order enforced by variable declaration + HTML concat order in renderDayPage — verifiable by grep on concat lines"
metrics:
  duration_seconds: 480
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 1
---

# Phase 19 Plan 05: Day-Page Scaffold Summary

One-liner: Day-page scaffold enforcing D-12 section order (header → agenda → stats → map/spine/videos/timelapse placeholders) with `escapeHtml()` XSS guard, haversine km calculation from route points, and agenda context rendered before all telemetry sections (NARR-04).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CSS scaffold for day-page layout + escapeHtml helper | d5ed152a (home-ops) | webroot/index.html |
| 2 | renderAgendaContext + computeDayStats + rewrite renderDayPage scaffold | fbcf909b (home-ops) | webroot/index.html |

## What Was Built

### CSS (Task 1)

Inserted after the `.day-nav` block (line 171), before `/* Day filter */`:

- `.day-page`: `max-width: 960px; margin: 0 auto` — constrains day content to readable width
- `.day-page > section`: `margin-bottom: 2rem` — consistent vertical rhythm between D-12 sections
- `.day-header`: `#161b22` card with amber `#f0dbb8` h1 and muted subtitle
- `.day-agenda`: same card styling; `.agenda-row` flex layout with `#e0a040` amber labels
- `.day-stats`: CSS grid `repeat(auto-fit, minmax(140px, 1fr))` — fills available columns
- `.day-stat-card`: individual stat tile with uppercase label + large value
- `.day-section-placeholder`: dashed border card for plan-owned future sections
- `@media (max-width: 600px)`: `.day-stats { grid-template-columns: repeat(2, 1fr) }` — 2 columns on mobile, same section order (D-13)

### escapeHtml helper (Task 1)

```js
function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
```

Covers all five dangerous characters. Applied to every agenda field before concatenation.

### renderAgendaContext(agendaDay) (Task 2)

Renders `<section class="day-agenda">` with route, camping, meals (as `<ul class="meals">`), and notes. Every field passes through `escapeHtml()`. Returns a "No agenda entry" fallback if `agendaDay` is null.

### _dayOf / _haversineKm / computeDayStats (Task 2)

- `_dayOf(iso)`: wraps the existing en-CA/TIMEZONE date bucketing in a try/catch — reuses the pattern from line 1348 verbatim
- `_haversineKm`: standard spherical law of cosines via Haversine — sums over route polyline segments
- `computeDayStats(dayISO, events, route, fuel)`: filters each data source by `_dayOf`, sums haversine km from route points, finds peak G + top speed from events, sums `volume_litres` from fuel. Returns `{ km, peakG, topSpeed, fuelBurned, eventCount, hasData }`.

### renderDayPage scaffold (Task 2 — replaces Plan 19-03 stub)

D-12 section order in HTML concat (lines 1381-1388):

1. `headerHtml` — `.day-header` with "Day N — Title" or dayISO fallback
2. `agendaHtml` — `renderAgendaContext(agendaDay)` output
3. `statsHtml` — `.day-stats` grid with km / top speed / peak G / events / fuel
4. `mapPlaceholder` — `<div id="day-map">` dashed card
5. `spinePlaceholder` — `<div id="day-spine">` dashed card
6. `videosPlaceholder` — `<div id="day-videos">` dashed card
7. `timelapsePlaceholder` — `<div id="day-timelapse">` with escaped dayISO in path

All wrapped in `<div class="day-page">`, single vertical scroll, no tabs (D-11).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `#day-map` | webroot/index.html | Intentional. Plan 19-07 wires the Leaflet day map. |
| `#day-spine` | webroot/index.html | Intentional. Plan 19-06 wires the timeline spine. |
| `#day-videos` | webroot/index.html | Intentional. Plan 19-06/Phase 19 backfill wires video highlights. |
| `#day-timelapse` | webroot/index.html | Intentional. Phase 19 backfill wires timelapse embed. |

These stubs are the explicit extension points for downstream plans. The day-page scaffold goal (D-12 section order, agenda context, stats row) is fully achieved.

## Threat Surface Scan

- T-19-05-01 mitigated: `escapeHtml()` applied to all five agenda fields (`title`, `route`, `camping`, `notes`, `meals[].time`, `meals[].where`) before innerHTML concatenation. Verified by grep.
- T-19-05-02 mitigated: `_dayOf()` reuses existing `en-CA` / `Australia/Sydney` bucketing — no new timezone logic.
- T-19-05-03 mitigated: `computeDayStats` uses only `volume_litres` from fuelData. `grep -E 'cost_aud|price_aud'` on new code returns no matches.

No new trust boundaries introduced.

## Self-Check: PASSED

- `function escapeHtml` count: 1 — FOUND
- `function renderAgendaContext` count: 1 — FOUND
- `function computeDayStats` count: 1 — FOUND
- `function _haversineKm` count: 1 — FOUND
- `id="day-map"` count: 1 — FOUND
- `id="day-spine"` count: 1 — FOUND
- `id="day-videos"` count: 1 — FOUND
- `id="day-timelapse"` count: 1 — FOUND
- `.day-page {` exists with `max-width: 960px` — FOUND
- `.day-stats { grid-template-columns: repeat(2, 1fr) }` in `@media (max-width: 600px)` — FOUND
- D-12 concat order: headerHtml (1381) → agendaHtml (1382) → statsHtml (1383) → map (1384) → spine (1385) → videos (1386) → timelapse (1387) — CONFIRMED
- No `cost_aud` in new code — CONFIRMED
- Commits d5ed152a and fbcf909b exist in home-ops main — CONFIRMED
