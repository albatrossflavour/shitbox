---
phase: 19
plan: "11"
subsystem: website
tags: [nav, spa, about-page, purge]
dependency_graph:
  requires: [19-03, 19-08, 19-09, 19-10]
  provides: [nav-shrink, about-route, legacy-purge]
  affects: [shit-of-theseus.com]
tech_stack:
  added: []
  patterns: [SPA pushState routing, escapeHtml XSS guard, onerror image fallback]
key_files:
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - renderDrivers deleted (not adapted): _renderDriversForAbout wrote fresh from plan interfaces block — cleaner than repurposing the DOM-coupled original
  - renderStatus, renderEvents, initMap, loadTimelapses all deleted: they referenced only removed section IDs and had no SPA-router equivalent
  - Fetch calls simplified at load time: data stored to module vars only, no DOM manipulation on initial load (SPA router owns all rendering)
  - showLegacySections() left in place: it is a no-op now (no .section children) but harmless and removal not in scope
metrics:
  duration_minutes: 25
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 1
  lines_before: 3014
  lines_after: 2107
  bytes_before: 137493
  bytes_after: 91389
  line_reduction: 907
  byte_reduction: 46104
---

# Phase 19 Plan 11: Nav Shrink + Legacy Purge + About Page Summary

Nav collapsed from 9 tabs to 4 (Home / Grafana / About / Donate), all legacy tab DOM deleted from `<main>`, dead JS removed, and `renderAbout()` stub replaced with real drivers-grid + car-story + telemetry-explainer content.

## What Was Built

### Task 1: Nav rewrite + legacy DOM purge + dead JS removal

The 9-entry `<nav>` (Status / Drivers / Videos / Timelapse / Map / Dashboard / The Car / Route / About) was replaced wholesale with 4 entries:

- **Home** — pushState via `navigateHome()`
- **Grafana** — `target="_blank" rel="noopener"` to external dashboard
- **About** — pushState via new `navigateToAbout()` function
- **Donate** — `target="_blank" rel="noopener"` to short.albatrossflavour.com/Shitbox

`navigateToAbout()` added alongside `navigateHome` and `navigateToDay`, calling `route()` then `scrollTo(0,0)`.

All 8 legacy section elements deleted from `<main>` (status-section, drivers-section, videos-section, timelapse-section, map-section, dashboard-section, car-section, route-section). The `about-section` was also present and deleted. `<main>` now contains only `<div id="dynamic-route">`.

Dead JS deleted:

- `document.querySelectorAll('nav a').forEach(...)` hash-tab-switching click handler
- `window.jumpToEvent` and `window.jumpToNote`
- `function injectNoteBadges`
- `function renderDrivers` (DOM-coupled; replaced by `_renderDriversForAbout` in Task 2)
- `function formatDriveTime` (replaced by existing `_formatDriveTimeLocal`)
- `function renderStatus`, `function renderEvents`, `function initMap`, `function loadTimelapses`

Fetch calls at load time simplified: data stored to module-level vars only. SPA router owns all rendering.

**Size reduction:** 3,014 lines / 137,493 bytes → 2,047 lines / 86,757 bytes after Task 1 (Task 2 added 60 lines back for renderAbout).

### Task 2: renderAbout real implementation

The Plan 19-03 stub replaced with the full `renderAbout()` function. Composes 5 sections:

1. **Hero** — logo.png with onerror fallback, "The Shit of Theseus" h1, tagline
2. **Drivers** — via `_renderDriversForAbout(driverStatsData)`: responsive card grid, active-driver badge, drive-time + percentage stats
3. **The Car** — car-front.jpg / car-side.jpg gallery with onerror fallbacks, origin story
4. **Why "Shit of Theseus"?** — Ship of Theseus thought experiment explanation
5. **The Telemetry** — Raspberry Pi daemon description, GitHub link (target=_blank rel=noopener)
6. Back-to-home link via `navigateHome()` (pushState, no reload)

`_renderDriversForAbout(ds)` passes all string fields through `escapeHtml` (T-19-11-01 mitigation). Returns "No driver data yet." placeholder when `driverStatsData` is null or empty.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

The plan called `renderDrivers` to be "kept because Task 2 repurposes it". On inspection, `renderDrivers` was tightly coupled to removed DOM IDs (`#drivers-loading`, `#drivers-content`, `#drivers-grid`) and used `formatDriveTime` (also deleted). Writing `_renderDriversForAbout` fresh from the plan's interfaces block was cleaner. This matches the plan's spirit if not the exact letter; tracked as a deliberate deviation rather than a bug.

`showLegacySections()` was not deleted (it calls `querySelectorAll('main > .section')` which now returns nothing — it is a harmless no-op). Out of scope for this plan.

Pre-existing stubs in `renderDayPage` (video highlights, timelapse placeholders from Plan 19-05) remain. Not in scope.

## Known Stubs

The following pre-existing stubs remain from prior plans (not introduced by this plan):

| File | Description | Resolving plan |
|------|-------------|----------------|
| index.html line ~1865 | Video highlights placeholder in renderDayPage | Plan 19-12 or future phase |
| index.html line ~1866 | Timelapse embed placeholder in renderDayPage | Plan 19-12 or future phase |

These do not prevent this plan's goal (/about route, nav shrink) from being achieved.

## Threat Flags

None. All threats in the plan's threat register were mitigated:

- T-19-11-01 (XSS on driver names): mitigated — `escapeHtml` applied to `driver_name`, `initial`, `time`, `pct` in `_renderDriversForAbout`
- T-19-11-02 (hash deep-link regression): accepted per plan — hash links land on `/` homepage
- T-19-11-03 (Grafana link missing rel=noopener): mitigated — nav anchor includes `target="_blank" rel="noopener"`

## Commits

| Task | Commit | Repo | Description |
|------|--------|------|-------------|
| Task 1 | 5d8f7428 | home-ops | refactor(19-11): shrink nav to 4 entries, purge legacy main sections and dead JS |
| Task 2 | f6858b2f | home-ops | feat(19-11): renderAbout with drivers + car + telemetry sections |

## Self-Check: PASSED

- index.html exists and is 2,107 lines
- Both commits verified in home-ops git log
- All automated grep checks pass (data-section=0, jumpToEvent=0, injectNoteBadges=0, legacy section IDs=0, navigateToAbout=1, dynamic-route=1, renderAbout=1, _renderDriversForAbout=1)
- Byte reduction: 137,493 → 91,389 (46,104 bytes removed, well above the 200-line target)
