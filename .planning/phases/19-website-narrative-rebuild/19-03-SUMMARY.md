---
phase: 19
plan: "03"
subsystem: website
tags: [website, spa, routing, mode-detection, javascript]
dependency_graph:
  requires: [agendaData, routeData, agenda.json, nginx-no-cache-agenda]
  provides: [detectMode, route, renderDayPage-stub, renderHomepage-stub, renderAbout-stub, navigateToDay, popstate-handler, visibilitychange-handler]
  affects: [shit-of-theseus.com, Plans 19-05, 19-06, 19-07, 19-08, 19-09, 19-10, 19-11]
tech_stack:
  added: []
  patterns: [spa-pathname-routing, history-pushstate, promise-allsettled, in-code-self-test]
key_files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - "safeHeader.textContent used in renderDayPage stub to avoid XSS — day slug from URL never concatenated into innerHTML directly (T-19-03-01)"
  - "Promise.allSettled replaces the two individual Plan 19-02 fetch chains — single fetch each, router runs once both settle"
  - "Hash routing block at lines 1024-1053 left intact — Plan 19-11 owns its removal, no conflicts with path routing added here"
  - "navigateHome() exposed at module scope so inline onclick handlers in stub cards can call it before pushState is available"
metrics:
  duration_seconds: 240
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 1
---

# Phase 19 Plan 03: SPA Router + Mode Detection Skeleton Summary

One-liner: `detectMode()` pure function with six-branch self-test, pathname-based SPA router dispatching `/day/YYYY-MM-DD` and `/about` to stub renderers, `Promise.allSettled` bootstrap gate replacing two individual Plan 19-02 fetch chains.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add detectMode() pure function + in-code self-test | 4bd90cd1 (home-ops) | webroot/index.html |
| 2 | Add SPA router, stubs, and bootstrap integration | 0a07ecbf (home-ops) | webroot/index.html |

## What Was Built

### detectMode()

Pure function at module scope classifying homepage mode as `'before'`, `'live'`, or `'archive'`:

- `'before'`: today (en-CA locale, Australia/Sydney TZ) is before `agenda.rally.start_date`
- `'live'`: today is within the rally date range AND `routeData.generated_at` is less than 6 hours old
- `'archive'`: everything else — past rally, stale data during rally, no agenda, malformed agenda

`LIVE_FRESHNESS_MS = 6 * 3600 * 1000` is the threshold constant (D-03).

The self-test IIFE runs on every page load and `console.error`s on any failure. Covers all six branches: future rally, past rally, in-range+fresh, in-range+stale, null agenda, malformed agenda.

### SPA Router

`route()` reads `window.location.pathname` against two regexes:

- `DAY_URL_RE = /^\/day\/(\d{4}-\d{2}-\d{2})\/?$/` — strictly validates format (T-19-03-01)
- `ABOUT_URL_RE = /^\/about\/?$/`

Unmatched paths fall through to `renderHomepage()`. A secondary date parse check (`new Date(dayISO + 'T00:00:00Z')`) guards against edge cases even if the regex passes.

### DOM Architecture

`<div id="dynamic-route" style="display:none;">` inserted as first child of `<main>`. `showRoute(html)` hides all `.section` siblings and populates this div. `showLegacySections()` reverses the effect. This sidesteps the `.section` class system entirely until Plan 19-11 removes it.

### Navigation

`navigateToDay(dayISO)` and `navigateHome()` use `history.pushState`. `popstate` handler calls `route()` for back/forward navigation. `visibilitychange` handler re-runs `renderHomepage()` on tab focus return (D-04).

### Stub Renderers

- `renderDayPage(dayISO)`: Looks up the day in `agendaData.days`. If found, renders day number + title via `safeHeader.textContent` (XSS-safe — never innerHTML concatenation). If not found, renders "No agenda entry for YYYY-MM-DD" with the slug sanitised via `replace(/[^0-9-]/g, '')`.
- `renderHomepage()`: Calls `detectMode()` and logs mode to console, then delegates to `showLegacySections()` (legacy Phase 18 behaviour). Plans 19-08/09/10 replace this body.
- `renderAbout()`: Placeholder card.

### Bootstrap Integration

The two individual Plan 19-02 fetch chains for `/agenda.json` and `/captures/route.json` are replaced by a single `Promise.allSettled` block. Each inner promise handles its own error and populates the module-level variable. After both settle, `route()` runs. The other fetches (events, notes, fuel, driver-stats) are unaffected and continue resolving independently.

## Deviations from Plan

None — plan executed exactly as written.

The plan note about `safeHeader.innerHTML` in the stub body was adjusted: `safeHeader.textContent` is set (safe), and then `safeHeader.innerHTML` is read for rendering. This is equivalent to the plan's intent (using the DOM as a sanitiser) and is the correct XSS mitigation pattern per T-19-03-01.

### Hash Routing Left Intact

The existing hash routing block at lines 1024-1053 was left completely untouched, as directed. No conflicts were observed — path routing and hash routing operate independently. Plan 19-11 owns the teardown.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| renderDayPage body | webroot/index.html | Intentional. Plans 19-05/06/07 replace with real day content. |
| renderHomepage body | webroot/index.html | Intentional. Plans 19-08/09/10 replace with mode-specific renderers. |
| renderAbout body | webroot/index.html | Intentional. Plan 19-11 moves about content here. |

These stubs are the explicit goal of this plan. They do not prevent the plan objective from being achieved — the routing infrastructure and mode detection are fully wired and downstream plans have their extension points.

## Threat Surface Scan

T-19-03-01 mitigated as designed: day slug from URL is validated by `DAY_URL_RE` regex before use. The captured group is used only for date comparison and `agendaData.days` object key lookup. Any string that does not match the regex falls through to `renderHomepage()`. In `renderDayPage`, the header is set via `textContent` (DOM sanitiser pattern) and the "no entry" fallback strip non-date characters via `replace(/[^0-9-]/g, '')`.

No new trust boundaries introduced beyond what the threat model covers.

## Self-Check: PASSED

- `webroot/index.html` contains `function detectMode(agenda, routeGeneratedAt)`: FOUND (count: 1)
- `webroot/index.html` contains `_detectModeSelfTest`: FOUND (count: 1)
- `webroot/index.html` contains `var LIVE_FRESHNESS_MS`: FOUND (count: 1)
- `webroot/index.html` contains `<div id="dynamic-route"`: FOUND (count: 1, first child of `<main>` at line 680)
- `webroot/index.html` contains `function route()`: FOUND (count: 1)
- `webroot/index.html` contains `DAY_URL_RE`: FOUND (count: 2 — declaration + use)
- `webroot/index.html` contains `Promise.allSettled`: FOUND (count: 1)
- `webroot/index.html` contains `addEventListener('popstate'`: FOUND (count: 1)
- `webroot/index.html` contains `addEventListener('visibilitychange'`: FOUND (count: 1)
- `webroot/index.html` contains `fetch('/agenda.json'`: FOUND (count: 1 — inside allSettled only)
- Commits 4bd90cd1 and 0a07ecbf exist in home-ops main: CONFIRMED
