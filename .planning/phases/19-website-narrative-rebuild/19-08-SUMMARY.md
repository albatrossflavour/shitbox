---
phase: 19
plan: "08"
subsystem: website
tags: [website, before-mode, countdown, spa, javascript, narr-01]
dependency_graph:
  requires:
    - phase: 19-02
      provides: agendaData, agenda.json (rally + days schema)
    - phase: 19-03
      provides: detectMode, renderHomepage stub, navigateToDay, showRoute, renderDayNav
    - phase: 19-04
      provides: escapeHtml, _formatShortDate
    - phase: 19-07
      provides: _teardownDayMap, _currentDayMap, day-map-container CSS insertion point
  provides:
    - renderHomepageBefore(agenda) — full before-mode homepage layout
    - _startCountdown(targetIso, hostEl) — 1Hz countdown ticker with auto-transition
    - _stopCountdown() — idempotent countdown teardown
    - _countdownTimer — module-level cleanup ref
    - before-mode CSS (.before-hero, .before-countdown, .countdown-tile, .before-cta, .before-planned-route, .before-stats, .before-day-list, .before-day-row)
    - renderHomepage() mode dispatch (before branch wired; live/archive stub placeholders)
  affects: [shit-of-theseus.com, NARR-01, Plans 19-09, 19-10, 19-11]
tech-stack:
  added: []
  patterns: [module-level-timer-ref, dom-mount-then-wire, spa-mode-dispatch, sydney-midnight-countdown]
key-files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
key-decisions:
  - "Rally start parsed as T00:00:00+10:00 (Sydney midnight, UTC+10 fixed offset) — matches D-16 rally-day boundary"
  - "_startCountdown called after showRoute() so the #before-countdown-host element is in the DOM before the interval starts"
  - "_countdownTimer module-level ref + _stopCountdown() called from renderHomepage, renderAbout, renderDayPage — prevents stale interval surviving SPA navigation (T-19-08-02 mitigated)"
  - "Live/archive placeholder text hardcoded in renderHomepage fallback — Plans 19-09 and 19-10 replace those branches"
  - "/route.jpg img has onerror=this.style.display=none — graceful degradation if image not yet uploaded"
patterns-established:
  - "Module-level timer ref + idempotent stop function: same teardown pattern as _currentDayMap / _teardownDayMap"
  - "DOM-mount then wire: showRoute() first, then getElementById to get the countdown host — never getElementById before DOM insertion"
requirements-completed: [NARR-01]
duration: 18min
completed: "2026-04-16"
---

# Phase 19 Plan 08: Before-Mode Homepage Summary

**Before-mode homepage with 1Hz countdown to rally start (2026-05-27 Sydney midnight), planned-route image, stat cards, and clickable 10-day itinerary — live on shit-of-theseus.com right now.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-04-16T13:40:00Z
- **Completed:** 2026-04-16T13:58:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Before-mode homepage is now the default view at `/` while today (2026-04-16) is before the rally start (2026-05-27)
- Countdown ticks every second with tabular-nums rendering — days, hours, minutes, seconds — and auto-transitions to `renderHomepage()` when delta reaches zero (live-mode handoff)
- Day-list preview renders all 10 agenda days with day number, short date, title, and route prose, each linking to `/day/YYYY-MM-DD` via `navigateToDay`
- Stat cards at top: total distance (3534 km), days count (10), team name, start date
- Timer leak prevention: `_stopCountdown()` called at top of `renderHomepage`, `renderAbout`, and `renderDayPage` — matches the `_teardownDayMap` pattern from Plan 19-07

## Task Commits

1. **Task 1: Before-mode CSS + countdown ticker + _startCountdown helper** - `7dd1fd37` (feat)
2. **Task 2: renderHomepageBefore + before-mode dispatch in renderHomepage** - `f4f07ca9` (feat)

## Files Created/Modified

- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html` — before-mode CSS block, `_countdownTimer` var, `_stopCountdown`, `_startCountdown`, `renderHomepageBefore`, updated `renderHomepage` with mode dispatch

## Decisions Made

- Rally start parsed as `T00:00:00+10:00` (Sydney midnight, UTC+10 fixed offset) — matches the D-16 rally-day boundary. Consistent with `_dayOf` timezone approach from Plan 19-01.
- `_startCountdown` is called after `showRoute(html)` so `#before-countdown-host` is in the DOM before `getElementById` runs. Calling it before would silently fail.
- `_countdownTimer` follows the same module-level ref + idempotent-stop pattern as `_currentDayMap` / `_teardownDayMap` from Plan 19-07. Clean SPA lifecycle without special-casing.
- `/route.jpg` uses `onerror="this.style.display='none';"` — the image may not be deployed yet; the page should not show a broken-image placeholder.
- Live/archive branches in `renderHomepage` are left as readable placeholder strings rather than `showLegacySections()` — the legacy sections are no longer the right fallback once mode dispatch is live.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `renderHomepage` live branch | webroot/index.html | Intentional. Plan 19-09 replaces with live-mode renderer. |
| `renderHomepage` archive branch | webroot/index.html | Intentional. Plan 19-10 replaces with archive-mode renderer. |
| `/route.jpg` image | webroot/index.html | Static asset not yet deployed. `onerror` hides the broken element gracefully. |

These stubs do not prevent the plan's goal from being achieved. Before-mode (the active mode as of 2026-04-16) is fully wired.

## Threat Surface Scan

- T-19-08-01 mitigated: all `rally.*` and `day.*` string fields pass through `escapeHtml()` before innerHTML assignment. `total_distance_km` coerced via `Number()`.
- T-19-08-02 mitigated: `_countdownTimer` module-level ref + `_stopCountdown()` called from `renderHomepage`, `renderAbout`, `renderDayPage` — 3 non-self call sites. Interval cannot survive SPA route change.
- T-19-08-03 accepted: clock skew edge case documented in plan threat register. Graceful because live-mode will show the placeholder until Plan 19-09 lands.

No new trust boundaries introduced.

## Self-Check: PASSED

- `function renderHomepageBefore` count: 1 — FOUND
- `function _startCountdown` count: 1 — FOUND
- `function _stopCountdown` count: 1 — FOUND
- `var _countdownTimer` count: 1 — FOUND
- `.before-countdown` CSS selector count: 1 — FOUND
- `.before-day-row` CSS selector count: 8 — FOUND
- `mode === 'before'` count: 1 — FOUND
- `renderHomepageBefore(agendaData)` count: 1 — FOUND
- `before-countdown-host` count: 2 — FOUND (definition + getElementById)
- `/route.jpg` count: 2 — FOUND (img src + onerror)
- `_stopCountdown()` non-self references: 4+ — FOUND (renderHomepage, renderAbout, renderDayPage, _startCountdown tick)
- Commits 7dd1fd37 and f4f07ca9 exist in home-ops main: CONFIRMED
