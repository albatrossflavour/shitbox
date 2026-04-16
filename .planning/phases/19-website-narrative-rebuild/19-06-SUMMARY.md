---
phase: 19
plan: "06"
subsystem: website
tags: [website, day-page, timeline-spine, javascript, css, xss-mitigation]
dependency_graph:
  requires: [escapeHtml, _dayOf, BADGE_COLORS, TIMEZONE, eventsData, notesData, fuelData, agendaData, renderDayPage-scaffold]
  provides: [buildSpine, renderSpine, _spineEventCard, _spineNoteCard, _spineFuelCard, _spineDriverChange, _spineStageBookend, _spineAgendaMeal, _spineAgendaCamping, _formatSpineTime, spine-css]
  affects: [shit-of-theseus.com, Plan 19-07]
tech_stack:
  added: []
  patterns: [timeline-spine, kind-dispatch, xss-escape, pii-exclusion-guard, nan-guard-timestamp]
key_files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - "Stage bookends derived from first/last event of the day — GPS motion transitions deferred as a future extension point (comment marks it)"
  - "Agenda meal timestamps use +10:00 fixed offset for ordering only — not displayed, just sorts correctly relative to Sydney events"
  - "Camp marker pinned to 20:00 local — narrative anchor, not a precise timestamp"
  - "PII guard comment in _spineFuelCard names cost_aud and price_aud explicitly to make the exclusion auditable; comment itself is the mitigation trail (T-19-06-02)"
  - "Driver-change markers derived from active_driver field transitions on events — no separate driver_stints source needed at this point"
metrics:
  duration_seconds: 1300
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 1
---

# Phase 19 Plan 06: Timeline Spine Summary

One-liner: Timestamp-sorted timeline spine merging events, notes, fuel stops, driver changes, agenda markers, and stage bookends into a single chronological day narrative, rendered as a left-rail timeline with per-kind cards and kind-specific dot colours.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CSS + buildSpine merge + renderSpine dispatcher | 11902f0e (home-ops) | webroot/index.html |
| 2 | Per-kind cards + wire into renderDayPage | e7ec35f8 (home-ops) | webroot/index.html |

## What Was Built

### CSS (Task 1)

Inserted after `.day-section-placeholder` / `.day-section-heading` block:

- `.spine`: container, no extra padding
- `.spine-empty`: dashed fallback card for days with no data
- `.spine-item`: `grid-template-columns: 72px 24px 1fr` — time column, rail column, card column
- `.spine-time`: tabular-nums, right-aligned, muted colour
- `.spine-rail` / `.spine-rail::before`: vertical connecting line using `#2a1f0e` (brand amber-dark)
- `.spine-dot`: 16x16 circle, kind-specific colours for all 8 item types
- `.spine-card`: `#161b22` card with title / meta / body / video sub-elements
- `@media (max-width: 600px)`: grid tightens to `56px 20px 1fr`, time font drops to 0.72rem

Kind-specific dot colours:

| Kind | Colour |
|------|--------|
| event | `#da3633` (red — matches HIGH_G badge) |
| note | `#1f6feb` (blue) |
| fuel | `#2ea043` (green) |
| driver_change | `#8957e5` (purple) |
| stage_start | `#e0a040` (amber) |
| stage_end | `#8b949e` (muted) |
| agenda_meal | `#d29922` (gold) |
| agenda_camping | `#6e7681` (grey) |

### buildSpine(dayISO, data) (Task 1)

Pure merge-and-sort over six sources:

1. **events** — filtered by `_dayOf(ev.timestamp) === dayISO`, `Date.parse` NaN guard
2. **notes** — filtered by `_dayOf(n.timestamp_utc) === dayISO`
3. **fuel** — filtered by `_dayOf(f.timestamp_utc) === dayISO`
4. **driver_change** — derived from `active_driver` transitions on day's events (sorted, prev-tracking loop)
5. **agenda_meal** — from `agendaDay.meals[]`, time parsed as `dayISO + 'T' + m.time + ':00+10:00'`
6. **agenda_camping** — pinned to `dayISO + 'T20:00:00+10:00'`
7. **stage_start / stage_end** — synthetic bookends at `first_event._ts - 1` and `last_event._ts + 1`

Final `items.sort((a, b) => a._ts - b._ts)` gives ascending chronological order.

### renderSpine(items) (Task 1)

Dispatcher: empty input returns `.spine-empty` div. Otherwise, wraps items in `.spine` and dispatches each to its per-kind renderer via `switch`. Each item gets `.spine-item {kind}` wrapper with time column, rail, and card.

### Per-kind renderers (Task 2)

- `_spineEventCard`: BADGE_COLORS lookup with `#8b949e` fallback; peak_g / peak_speed_kmh / duration_ms meta; video element if video_url or video_path present
- `_spineNoteCard`: note body via `escapeHtml`
- `_spineFuelCard`: volume_litres + km_per_litre + odometer_km only — no cost fields
- `_spineDriverChange`: `from → to` arrow (unicode `\u2192`); `from` defaults to "Start" for first driver
- `_spineStageBookend`: amber for start, muted for end
- `_spineAgendaMeal`: gold title, `m.where` body
- `_spineAgendaCamping`: grey title, `p.where` body

### renderDayPage wiring (Task 2)

Two changes:

1. `spinePlaceholder` declaration simplified to `<section><h3>Timeline</h3><div id="day-spine"></div></section>` — `day-section-placeholder` class removed so `.spine-empty` handles the empty-day case
2. After `showRoute(html)`, immediately: `document.getElementById('day-spine').innerHTML = renderSpine(buildSpine(dayISO, { events, notes, fuel, agendaDay }))`

## Deviations from Plan

None — plan executed exactly as written.

The `cost_aud`/`price_aud` grep in the verify block produces a match on the PII guard comment itself (`// PII guard: NEVER read cost_aud or price_aud from fuel payloads.`). This is intentional: the comment is the audit trail documenting the exclusion. No actual field access occurs.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `#day-map` | webroot/index.html | Intentional. Plan 19-07 wires the Leaflet day map. |
| `#day-videos` | webroot/index.html | Intentional. Phase 19 backfill wires video highlights. |
| `#day-timelapse` | webroot/index.html | Intentional. Phase 19 backfill wires timelapse embed. |
| Stage bookends from GPS motion | webroot/index.html | Intentional. Current bookends use first/last event timestamp. GPS-motion derivation is a future extension point (commented in buildSpine). |

## Threat Surface Scan

- T-19-06-01 mitigated: all string fields flowing to innerHTML pass through `escapeHtml()` — notes body, driver names, event types, meal/camping locations, video src
- T-19-06-02 mitigated: `_spineFuelCard` reads only `volume_litres`, `km_per_litre`, `odometer_km`. `grep -n 'cost_aud\|price_aud'` returns only the guard comment, no field access
- T-19-06-03 accepted: no virtualisation — rally day realistically <50 events, pure string concat is fast enough
- T-19-06-04 mitigated: each source mapper computes `Date.parse(...)` and skips NaN results before pushing to items array; final sort operates only on valid `_ts` values

No new trust boundaries introduced.

## Self-Check: PASSED

- `function buildSpine` count: 1 — FOUND
- `function renderSpine` count: 1 — FOUND
- `function _formatSpineTime` count: 1 — FOUND
- `function _spineEventCard` count: 1 — FOUND
- `function _spineNoteCard` count: 1 — FOUND
- `function _spineFuelCard` count: 1 — FOUND
- `function _spineDriverChange` count: 1 — FOUND
- `function _spineStageBookend` count: 1 — FOUND
- `function _spineAgendaMeal` count: 1 — FOUND
- `function _spineAgendaCamping` count: 1 — FOUND
- `renderSpine(buildSpine(` count: 1 — FOUND
- `id="day-spine"` count: 1 — FOUND
- `.spine-item.event` CSS: FOUND
- `.spine-item.note` CSS: FOUND
- `.spine-item.fuel` CSS: FOUND
- `.spine-item.driver_change` CSS: FOUND
- `.spine-item.stage_start` CSS: FOUND
- `.spine-item.stage_end` CSS: FOUND
- `.spine-item.agenda_meal` CSS: FOUND
- `.spine-item.agenda_camping` CSS: FOUND
- "Timeline spine placeholder" text: NOT FOUND (removed)
- `cost_aud` / `price_aud` field access: NOT FOUND (only in guard comment)
- Commits 11902f0e and e7ec35f8 exist in home-ops main: CONFIRMED
