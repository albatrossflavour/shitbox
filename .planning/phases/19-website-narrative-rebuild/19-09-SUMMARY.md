---
phase: 19
plan: "09"
subsystem: website
tags: [website, live-mode, current-driver, refresh-timer, spa, javascript, narr-01]
dependency_graph:
  requires:
    - phase: 19-02
      provides: agendaData, routeData, agenda.json (rally + days schema)
    - phase: 19-03
      provides: detectMode, renderHomepage dispatch, navigateToDay, showRoute, renderDayNav
    - phase: 19-04
      provides: escapeHtml, _formatShortDate
    - phase: 19-05
      provides: renderDayPage, computeDayStats
    - phase: 19-06
      provides: renderSpine, buildSpine, spine section
    - phase: 19-07
      provides: initDayMap, _teardownDayMap, day map
    - phase: 19-08
      provides: renderHomepageBefore, _stopCountdown, _countdownTimer, renderHomepage mode dispatch
  provides:
    - renderHomepageLive() — live-mode homepage (today's day-page + current-driver widget + LIVE badge + 2-min refresh)
    - renderCurrentDriverWidget(ds) — compact current-driver card (silent when no active driver)
    - _formatDriveTimeLocal(seconds) — local drive-time formatter for widget
    - refreshLiveData() — Promise.all re-fetch of 5 JSON sources + conditional re-render
    - _stopLiveRefresh() — idempotent refresh-timer teardown
    - _liveRefreshTimer — module-level cleanup ref
    - LIVE_REFRESH_MS — 120000 ms interval constant
    - .live-badge CSS + livepulse animation
    - .current-driver-widget CSS (with mobile responsive)
  affects: [shit-of-theseus.com, NARR-01, Plans 19-10, 19-11, 19-12]
tech-stack:
  added: []
  patterns: [module-level-timer-ref, dom-mount-then-wire, spa-mode-dispatch, promise-all-refresh, xss-escapeHtml]
key-files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
key-decisions:
  - "renderHomepageLive delegates entirely to renderDayPage(today) then post-processes the mounted DOM to prepend widget + badge — avoids duplicating day-page render logic"
  - "_stopLiveRefresh() called at top of renderHomepage (before dispatch), renderDayPage, renderAbout — 3 non-self teardown sites. Mirrors _stopCountdown and _teardownDayMap patterns."
  - "refreshLiveData() guards re-render with window.location.pathname check — backgrounded tabs re-fetch data silently but do not clobber the user's current view"
  - "renderHomepageArchive soft-referenced via typeof check in renderHomepageLive overshoot guard — Plan 19-10 defines the function; until then the live renderer continues rather than crashing"
  - "LIVE_REFRESH_MS = 120000 (2 min) is appropriate for a single-user site with ~100KB total payload across 5 JSON files. Pi-side nginx cache headers from Plan 19-02 apply on top."
  - "_formatDriveTimeLocal is a local clone of formatDriveTime — avoids coupling live-mode widget to the legacy drivers-tab helper, which may diverge in future plans"
metrics:
  duration: ~20min
  completed: "2026-04-17"
  tasks: 2
  files_modified: 1
---

# Phase 19 Plan 09: Live-Mode Homepage Summary

**Live-mode homepage: today's day-page with a pulsing LIVE badge, current-driver widget, and a 2-minute auto-refresh loop that tears down cleanly on SPA navigation.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-04-17
- **Tasks:** 2
- **Files modified:** 1

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Live-mode CSS + current-driver widget + refresh timer machinery | `098e6243` (home-ops main) | webroot/index.html |
| 2 | renderHomepageLive + wire live branch in renderHomepage dispatch | `8285f25f` (home-ops main) | webroot/index.html |

## What Was Built

### CSS (Task 1)

Appended after the `.before-*` block from Plan 19-08:

- `.live-badge`: red `#da3633` pill with `livepulse` 2s opacity animation (1.0 to 0.55 and back)
- `.current-driver-widget`: amber-bordered flex card matching the site's dark card pattern
- `.cdw-avatar`: 48px amber circle with driver initial
- `.cdw-label`, `.cdw-name`, `.cdw-time`: label/name/time hierarchy in site palette
- Mobile `@media (max-width: 600px)`: avatar shrinks to 40px, name to 1rem

### JS helpers (Task 1)

- `_formatDriveTimeLocal(seconds)`: local drive-time formatter (hours + minutes, handles null/NaN)
- `renderCurrentDriverWidget(ds)`: builds the current-driver card HTML from `driverStatsData`. Returns `''` silently when `ds.active_driver` is null — no "nobody driving" noise. All string fields pass through `escapeHtml()` (T-19-09-01 mitigated).
- `var _liveRefreshTimer = null` and `LIVE_REFRESH_MS = 120000`: module-level timer ref + interval constant
- `_stopLiveRefresh()`: idempotent clearInterval + null
- `refreshLiveData()`: Promise.all over 5 endpoints (`events.json`, `notes.json`, `fuel.json`, `route.json`, `driver-stats.json`) with `no-cache` headers. Updates globals only when fetch succeeds (null-guards all results). Re-renders via `renderHomepage()` only when `window.location.pathname` is `/` — backgrounded tabs silently refresh data without clobbering the user's current view.
- `_stopLiveRefresh()` added to top of `renderDayPage` and `renderAbout` (alongside existing `_stopCountdown`)

### renderHomepageLive (Task 2)

1. Derives `today` as `en-CA` date string in `TIMEZONE` (Australia/Sydney)
2. Overshoot guard: if `today > rally.end_date`, soft-invokes `renderHomepageArchive` (Plan 19-10 fills it in; until then, continues as live without crashing)
3. Underflow guard: if `today < rally.start_date`, falls back to `renderHomepageBefore(agendaData)` — detectMode should catch this first, but belt-and-suspenders
4. Delegates to `renderDayPage(today)` — full day scaffold, agenda, stats, spine, map
5. Post-mounts current-driver widget: finds `.day-page` inside `#dynamic-route`, inserts widget before `firstChild`
6. Post-mounts LIVE badge: finds `.day-page .day-header h1`, appends `<span class="live-badge">LIVE</span>` with double-insert guard
7. Arms `_liveRefreshTimer = setInterval(refreshLiveData, LIVE_REFRESH_MS)` (after calling `_stopLiveRefresh()` first to prevent double-timer on refresh-triggered re-render)

### renderHomepage dispatch (Task 2)

Rewrote the `renderHomepage()` body to the final form. Key changes from the Plan 19-08 placeholder:

- `_stopLiveRefresh()` added at top (3rd teardown alongside `_teardownDayMap` and `_stopCountdown`)
- `agendaData` null-check moved above mode dispatch (loading-state placeholder shown first)
- `mode === 'before'` branch no longer guards on `agendaData` (null check already handled above)
- `mode === 'live'` branch wired: `renderHomepageLive(); return;`
- Archive/unknown fallback updated to say "archive homepage lands in Plan 19-10" (Plan 19-10 replaces this)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `renderHomepageArchive` | webroot/index.html | Intentional. Plan 19-10 defines this function. Soft-referenced via `typeof` check in overshoot guard so live mode does not crash before it lands. |
| Archive branch in `renderHomepage` | webroot/index.html | Intentional. Plan 19-10 replaces with archive-mode renderer. |

Live mode is fully functional. Both stubs are guarded so they produce no errors before Plan 19-10.

## Threat Surface Scan

- T-19-09-01 mitigated: `escapeHtml()` applied to `active_driver`, `initial`, and `timeLabel` in `renderCurrentDriverWidget`. No raw string reaches innerHTML.
- T-19-09-02 accepted: self-inflicted DoS documented in plan threat register. Single-user site, negligible at 120s intervals.
- T-19-09-03 mitigated: `_liveRefreshTimer` tracked module-level. `_stopLiveRefresh()` called from `renderDayPage`, `renderAbout`, `renderHomepage` (3 non-self sites), and at the start of `renderHomepageLive` itself before arming the new interval.
- T-19-09-04 accepted: clock-skew edge case is browser-clock dependent, no worse than any web app.

No new trust boundaries introduced.

## Refresh Interval Notes

2 minutes is the right interval for this use case. The total payload across 5 JSON files is roughly:

- `events.json`: ~50-80KB (grows during the day as events accumulate)
- `notes.json`, `fuel.json`, `driver-stats.json`: a few KB each
- `route.json`: ~1-2KB (compressed GPS track, DP-simplified)

At 120s intervals over a 10-hour driving day that is ~300 fetches totalling ~25MB. Negligible for a Pi 4 behind nginx with `no-cache` semantics. If payload sizes grow significantly in future phases, bumping `LIVE_REFRESH_MS` to 300000 (5 min) is a one-line change.

## Self-Check: PASSED

- `function renderHomepageLive` count: 1 — FOUND
- `function renderCurrentDriverWidget` count: 1 — FOUND
- `function refreshLiveData` count: 1 — FOUND
- `function _stopLiveRefresh` count: 1 — FOUND
- `var _liveRefreshTimer` count: 1 — FOUND
- `LIVE_REFRESH_MS` count: 1 — FOUND
- `.live-badge` CSS: 1 — FOUND
- `.current-driver-widget` CSS: FOUND (multiple selectors in block)
- `mode === 'live'` dispatch: 1 — FOUND
- `_stopLiveRefresh()` call sites (non-self): 3 — FOUND (renderHomepage, renderDayPage, renderAbout)
- `setInterval(refreshLiveData` count: 1 — FOUND
- `live-badge` references: 3 — FOUND (CSS + className + querySelector guard)
- Commits 098e6243 and 8285f25f exist in home-ops main: CONFIRMED
