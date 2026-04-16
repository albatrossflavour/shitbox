---
phase: 19
plan: "10"
subsystem: website
tags: [website, archive-mode, scrapbook, day-grid, thumbnails, spa, javascript, narr-01]
dependency_graph:
  requires:
    - phase: 19-02
      provides: agendaData, routeData, agenda.json (rally + days schema)
    - phase: 19-03
      provides: detectMode, renderHomepage dispatch, navigateToDay, showRoute, renderDayNav
    - phase: 19-04
      provides: escapeHtml, _formatShortDate
    - phase: 19-05
      provides: computeDayStats, _haversineKm, _dayOf
    - phase: 19-08
      provides: renderHomepageBefore, .day-stat-card CSS, .day-section-heading CSS
    - phase: 19-09
      provides: renderHomepageLive, _stopLiveRefresh, renderHomepage dispatch (live branch)
  provides:
    - renderHomepageArchive() — archive-mode homepage (overview stats + linear day grid)
    - _rallyTotals(events, fuel, route, agenda) — cross-day aggregator for km/events/fuel/drivers
    - .archive-overview, .archive-stats, .archive-day-grid, .archive-day-card CSS
    - renderHomepage() — final mode dispatch (all three modes: before, live, archive fully wired)
  affects: [shit-of-theseus.com, NARR-01]
tech-stack:
  added: []
  patterns: [newest-first-sort, onerror-fallback-chain, spa-navigation, xss-escapeHtml, haversine-aggregation]
key-files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
key-decisions:
  - "Day grid sorted newest-first via b.date.localeCompare(a.date) on ISO date strings — lexicographic sort is correct for YYYY-MM-DD format"
  - "_rallyTotals aggregates km by iterating route.days directly (same _haversineKm reuse as computeDayStats) — avoids double-accounting vs per-day calls"
  - "Thumbnail onerror chain uses dataset.step flag to distinguish first vs second failure — prevents infinite onerror loops if both hero.jpg and timelapse-poster.jpg 404"
  - "archive/unknown both dispatch to renderHomepageArchive — unknown is effectively archive (data present but mode undetermined)"
  - "Defensive fallback renderHomepageArchive() after switch branches — should never hit, but prevents blank page if detectMode returns unexpected value"
  - "statsLine in day cards uses escapeHtml on the combined string — numeric toFixed() output is safe but wrapping the whole line is belt-and-suspenders"
  - "Hero image convention: /captures/YYYY-MM-DD/hero.jpg for curated photo; falls back to timelapse-poster.jpg; falls back to text Day N — three levels of graceful degradation"
metrics:
  duration: ~15min
  completed: "2026-04-16"
  tasks: 2
  files_modified: 1
---

# Phase 19 Plan 10: Archive-Mode Homepage Summary

**Archive-mode homepage: overview stats card + linear day grid with thumbnail fallback chain. The rally is over; the site becomes a scrapbook index.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-04-16
- **Tasks:** 2
- **Files modified:** 1

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Archive-mode CSS + _rallyTotals aggregator | `9456138a` (home-ops main) | webroot/index.html |
| 2 | renderHomepageArchive + final renderHomepage mode dispatch | `0fc3fb03` (home-ops main) | webroot/index.html |

## What Was Built

### CSS (Task 1)

Appended after the `.current-driver-widget` block from Plan 19-09:

- `.archive-overview`: amber-bordered card with dark background, holds title + subtitle + stats grid
- `.archive-subtitle`: muted date range and team name
- `.archive-stats`: `repeat(auto-fit, minmax(130px, 1fr))` grid reusing `.day-stat-card` tiles from Plan 19-08
- `.archive-day-grid`: flex column with 0.75rem gap
- `.archive-day-card`: two-column grid (140px thumb | flex body), amber hover border
- `.adc-thumb`: 100px min-height flex container for image or text fallback
- `.adc-thumb-fallback`: amber oversized day number shown when both images 404
- `.adc-body`, `.adc-header`, `.adc-num`, `.adc-date`, `.adc-title`, `.adc-stats`: body hierarchy in site palette
- Mobile `@media (max-width: 600px)`: thumbnail column narrows to 90px, title to 1rem

### _rallyTotals aggregator (Task 1)

`_rallyTotals(events, fuel, route, agenda)` returns:

- `km`: sum of haversine distances across all `route.days` entries
- `eventCount`: `events.length`
- `fuelLitres`: sum of `volume_litres` from all fuel entries (cost_aud/price_aud never read — T-19-10-02 mitigated)
- `driverCount`: distinct `active_driver` values from events
- `dayCount`: `agenda.days.length`
- `startDate`, `endDate`: from `agenda.rally`

### renderHomepageArchive (Task 2)

1. Derives rally/days from `agendaData`, totals from `_rallyTotals`
2. Renders overview card: title (escapeHtml), date range, team, 5 stat tiles
3. Sorts days newest-first via `b.date.localeCompare(a.date)`
4. For each day: calls `computeDayStats` for per-day km/events/fuel, builds day card with:
   - Thumbnail: `hero.jpg` with onerror chain to `timelapse-poster.jpg` then text fallback `Day N`
   - `dataset.step` flag prevents infinite onerror loops on double-404
   - Day number, short date, title, stats line — all strings through `escapeHtml`
   - `<a>` with `href="/day/YYYY-MM-DD"` and `onclick="navigateToDay()"` — pushState SPA nav + middle-click fallback
5. Wraps in `.day-page` div, calls `showRoute(html)`

### renderHomepage dispatch (Task 2)

Final form — all three modes wired:

```
before  → renderHomepageBefore(agendaData)
live    → renderHomepageLive()
archive → renderHomepageArchive()
unknown → renderHomepageArchive()  (defensive — same as archive)
fallback → renderHomepageArchive() (should never hit)
```

Placeholder text "archive homepage lands in Plan 19-10" purged.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All three modes are fully wired. Hero images and timelapse posters will 404 gracefully until the rally produces real captures — the three-level fallback handles this at runtime.

### Thumbnail/Hero Image Conventions (for future backfill)

For each rally day `YYYY-MM-DD`, the archive homepage looks for:

1. `/captures/YYYY-MM-DD/hero.jpg` — curated hero photo (best shot of the day)
2. `/captures/YYYY-MM-DD/timelapse-poster.jpg` — timelapse poster frame (auto-generated)
3. Text fallback: amber "Day N" displayed in the thumbnail cell

To add curated heroes: drop a `hero.jpg` into each day's capture directory on the NAS at `192.168.1.22:/volume2/apps/shitbox/YYYY-MM-DD/hero.jpg`. No code changes needed.

## Threat Surface Scan

- T-19-10-01 mitigated: `escapeHtml()` applied to `rally.title`, `rally.start_date`, `rally.end_date`, `rally.team`, `d.title`, `_formatShortDate(d.date)`, and the combined `statsLine` string. No raw agenda string reaches innerHTML.
- T-19-10-02 mitigated: `_rallyTotals` reads only `volume_litres` from fuel entries. `cost_aud`/`price_aud` fields are never accessed. Verified by grep: only the existing PII guard comment references these field names.
- T-19-10-03 accepted: 404 noise for missing hero.jpg / timelapse-poster.jpg is a minor dev-tools friction. The onerror chain handles it gracefully — no broken image icons visible in UI.

No new trust boundaries introduced.

## Self-Check: PASSED

- `function renderHomepageArchive` count: 1 — FOUND
- `function _rallyTotals` count: 1 — FOUND
- `.archive-overview` CSS: 1 — FOUND
- `.archive-day-card` CSS selectors: 14 — FOUND
- `.archive-stats` CSS: 1 — FOUND
- `.archive-day-grid` CSS: 1 — FOUND
- `mode === 'archive'` dispatch: 1 — FOUND
- `renderHomepageArchive()` call sites: 4 — FOUND (archive branch, unknown branch, defensive fallback, overshoot guard in renderHomepageLive)
- Placeholder text "archive homepage lands in Plan 19-10": ABSENT — PASS
- Sorted newest-first `b.date.localeCompare(a.date)`: FOUND
- onerror fallback chain with `dataset.step`: FOUND
- `cost_aud`/`price_aud` usage (excluding PII guard comment): ABSENT — PASS
- Commits 9456138a and 0fc3fb03 exist in home-ops main: CONFIRMED
