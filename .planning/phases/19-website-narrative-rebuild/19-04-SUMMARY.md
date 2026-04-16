---
phase: 19
plan: "04"
subsystem: website
tags: [website, day-nav, css, javascript, a11y, xss-mitigation]
dependency_graph:
  requires: [agendaData, navigateToDay, renderDayPage-stub, renderHomepage-stub, renderAbout-stub]
  provides: [renderDayNav, _formatShortDate, day-nav-css, day-nav-container]
  affects: [shit-of-theseus.com, Plans 19-05, 19-06, 19-07, 19-08, 19-09, 19-10, 19-11]
tech_stack:
  added: []
  patterns: [css-grid-auto-flow-column, focus-visible-a11y, xss-integer-coercion, utc-date-formatting]
key_files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - "UTC Date object used in _formatShortDate rather than local TZ — date field is a calendar date (YYYY-MM-DD), not a timestamp; UTC prevents midnight-crossing shifts"
  - "future segments rendered as <span> (not <a>) to avoid disabled-anchor antipattern — pointer-events:none on <a> still focusable via Tab; <span> is both inert and semantically correct"
  - "highlightDayISO takes priority over today comparison — on /day/YYYY-MM-DD pages the explicit arg overrides the calendar check, ensuring the correct segment is amber even if the device clock is wrong"
metrics:
  duration_seconds: 300
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 1
---

# Phase 19 Plan 04: Day-Nav Progress Bar Summary

One-liner: Site-wide day-nav progress bar using CSS grid with completed/current/future segment states, `_formatShortDate()` UTC date helper, and `renderDayNav()` wired as first call in all three stub renderers.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CSS + HTML container for day-nav | 40b8b242 (home-ops) | webroot/index.html |
| 2 | renderDayNav function + wire into renderDayPage + renderHomepage | 138a8f0d (home-ops) | webroot/index.html |

## What Was Built

### CSS

Inserted after `.rally-progress-fill` (line 134), extending the existing rally-progress visual language:

- `.day-nav`: `display:grid; grid-auto-columns:1fr; grid-auto-flow:column` — one equal column per day, no JS layout calculations needed
- `.day-nav-segment`: flex column, centred text, `text-decoration:none` baseline for anchor form
- `.day-nav-segment.completed`: `#c06000` orange + `#fff` text (matches `.rally-progress-fill`)
- `.day-nav-segment.current`: `#e0a040` amber + `#0d1117` dark text + `font-weight:600`
- `.day-nav-segment.future`: `#21262d` grey + `#484f58` muted text + `pointer-events:none; cursor:default`
- `.day-nav-segment:focus-visible`: 2px amber outline for keyboard navigation
- Mobile `@media (max-width: 600px)`: `.day-nav-date { display:none }` — only day numbers visible

### HTML Container

`<div id="day-nav" class="day-nav" style="display:none;">` inserted between `</nav>` and `<main>`. Starts hidden; `renderDayNav` removes `display:none` once agenda data is available.

### JavaScript

`_formatShortDate(iso)` — splits ISO string, constructs UTC Date, returns `'27 May'` format via `toLocaleDateString('en-GB', { timeZone: 'UTC' })`. Handles malformed input by returning the raw string.

`renderDayNav(agenda, highlightDayISO)` — iterates `agenda.days`:

- State priority: explicit `highlightDayISO` match → current; `day.date < today` → completed; `day.date === today` → current; otherwise → future
- `today` computed via `en-CA` locale + `TIMEZONE` (Australia/Sydney) — consistent with rest of site
- Integer coercion: `String(Number(day.day_number) || 0)` prevents XSS from agenda title contamination (T-19-04-01)
- `dateLabel` from `_formatShortDate` — derived from the ISO date field only, no agenda title involved
- future → `<span>` (semantically inert, not focusable, no onclick)
- completed/current → `<a href="/day/{date}">` with `onclick` calling `navigateToDay` for pushState; real `href` preserves middle-click and copy-link behaviour

### Wire-up

`renderDayNav(agendaData, dayISO)` is the first statement in `renderDayPage`.
`renderDayNav(agendaData, null)` is the first statement in `renderHomepage` and `renderAbout`.
Because `renderDayNav` handles null agenda gracefully (early return + hide), the call is safe before `Promise.allSettled` resolves — but in practice the router only runs after both fetches settle.

## Deviations from Plan

None — plan executed exactly as written.

One implementation note worth recording: the plan's action text showed `toLocaleDateString('en-GB', {...})` for `_formatShortDate`. This was kept as-is — `en-GB` gives `27 May` format, which is the intended output. Sydney locale (`en-AU`) would give the same format, but `en-GB` is unambiguous and already in the plan spec.

## Known Stubs

None introduced by this plan. The day-nav is fully functional. Segment states will be all `.future` until the rally `start_date` (2026-05-27) passes — this is correct behaviour.

## Threat Surface Scan

T-19-04-01 mitigated as designed: `day_number` passes through `String(Number(...))` integer coercion before insertion into innerHTML. The `date` field is formatted via a UTC `Date` object — no raw string concatenation from agenda fields. Agenda `title` is never rendered in day-nav segments.

No new trust boundaries introduced.

## Self-Check: PASSED

- `.day-nav-segment.completed` rule exists (count: 2 — CSS + hover group): FOUND
- `.day-nav-segment.current` rule exists (count: 2 — CSS + hover group): FOUND
- `.day-nav-segment.future` rule exists (count: 1): FOUND
- `<div id="day-nav" class="day-nav"` exists (count: 1): FOUND
- `.rally-progress-fill` still present (not deleted): FOUND
- `:focus-visible` on `.day-nav-segment`: FOUND
- `function renderDayNav(agenda, highlightDayISO)` count: 1 — FOUND
- `function _formatShortDate(iso)` count: 1 — FOUND
- `renderDayNav(agendaData,` call sites: 3 (renderDayPage, renderHomepage, renderAbout) — FOUND
- `String(Number(day.day_number)` integer coercion: FOUND
- Commits 40b8b242 and 138a8f0d exist in home-ops main: CONFIRMED
