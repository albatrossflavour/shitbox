# Phase 19: Website Narrative Rebuild - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-16
**Phase:** 19-website-narrative-rebuild
**Areas discussed:** Polyline todo fold-in, Timeline data pipeline, Mobile + day-page layout
**Areas deferred to Claude's discretion:** Routing + page shape, Agenda file format + home,
Mode detection rules, Day-nav progress bar, Archive overview + day grid

---

## Polyline todo fold-in

| Option | Description | Selected |
|--------|-------------|----------|
| Fold into Phase 19 | `route.json` generation + day-slice polyline ships as part of this phase | ✓ |
| Ship separately first | Tactical todo before rebuild starts | |
| Defer polyline entirely | Pins only for now | |

**User's choice:** Fold into Phase 19.
**Notes:** Route polyline data model aligns with day-page needs; shared generator is simpler than separate efforts.

---

## Gray area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Routing + page shape | SPA hash routing vs nginx rewrite vs SSG | (Claude's discretion — not selected for discussion) |
| Agenda file: format + home | YAML in home-ops vs markdown vs API-editable | (Claude's discretion — not selected for discussion) |
| Timeline data pipeline | Client-side filter vs per-day JSON vs hybrid | ✓ |
| Mobile + day-page layout | Stacking, collapse behaviour, progress-bar UX | ✓ |

**User's choice:** Timeline data pipeline, Mobile + day-page layout.
**Notes:** Routing and agenda-file-format left as Claude's discretion with defaults presented for approval at the end.

---

## Timeline data pipeline

### Initial multi-question probe (rejected; user asked for clarification)

User responded "I don't know which to pick" to the initial 4-question batch. Reformulated
as thinking-partner recommendations with reasoning, below.

### Recommendations presented and approved

| Sub-decision | Options considered | Chosen | Rationale |
|--------------|--------------------|--------|-----------|
| Data join location | Client-side filter / Pi emits per-day JSON / Hybrid | **Client-side filter** | Reuses existing fetch-and-filter pattern from Phase 18; zero new Pi generators for per-day JSON; route.json stays under 1 MB so single fetch is fine |
| Spine items | Events+notes+fuel only / +stage start/stop / +driver changes / +agenda markers / +system blips | Events (all types, **incl. BOOT**) + notes + fuel + stage start/stop + driver changes + agenda markers | Narrative texture without noise |
| Agenda content home | Static YAML in home-ops / Markdown in shitbox repo / API-editable via Pi | **Static YAML in home-ops** | Matches existing deploy model; agenda is mostly pre-rally content; API-editable is over-engineered for a 3-week event |
| Live-mode refresh | 30 s poll / 2 min poll / Tab-focus only | **2-minute poll** | Pi sync cadence is the actual freshness floor; faster polling burns bandwidth; tab-focus alone is too passive |

### Clarification from user

**User's distinction on "boot events":** System-only restart blips (thermal / undervoltage
alerts with no video) stay in Grafana and are filtered from the spine. BOOT events in
`events.json` that carry dashcam footage ("pulling out of a roadhouse") ARE narrative and
belong on the spine — they mark departures from stops and add context, not noise.

**Recorded as D-06 / D-07 in CONTEXT.md.**

---

## Mobile + day-page layout

### Recommendations presented and approved

| Sub-decision | Options considered | Chosen | Rationale |
|--------------|--------------------|--------|-----------|
| Day page structure | Tabs within day / Collapsible sections / Single vertical scroll | **Single vertical scroll** | Scrapbook reads top-to-bottom like a journal; tabs fragment the story |
| Section order | (various orderings) | Day header → Agenda context → Day stats → Map slice → Timeline spine → Video highlights → Day timelapse | Context first, narrative body, visual payoff at the bottom |
| Mobile behaviour | Desktop-first with mobile collapse / Mobile-first stack, no collapse | **Same order on mobile, no collapse** | Rally-watchers read on phones; don't make them hunt |
| Day-nav progress bar placement | Floating / Top-of-section / Under top nav | **Under top nav, site-wide** | Always visible, consistent across homepage and day pages |
| Progress-bar segment design | Day number only / Date only / **Day number big + date small** | Day number big + date small | Primary nav handle is day-count, date is disambiguation |
| Progress-bar click behaviour | All clickable / Only completed / **Completed + current clickable, future inert** | Completed + current clickable | Future days have no content to show — don't pretend otherwise |

**User response:** "Feels good to start with."

---

## Remaining defaults proposed and approved

Routing, day URL slugs, mode detection rules, archive overview, nav-after-rebuild, and
progress-bar placement were surfaced as Claude's-discretion recommendations at the end of
the discussion, with user approval ("Sounds reasonable"):

| Area | Chosen default |
|------|----------------|
| Routing | nginx `try_files $uri $uri/ /index.html` rewrite for `/day/*`, SPA reads `location.pathname` |
| Day URL slug | Date-only (`/day/2026-06-14`) — no descriptor |
| Mode detection | Rally start/end in agenda; before / live (< 6 h freshness) / archive triaged client-side |
| Archive overview | Totals card + linear day grid (no calendar); day cards with date, title, thumbnail |
| Nav after rebuild | Home, Grafana, About, Donate — everything else folds in |
| Agenda YAML shape | `rally: { start_date, end_date, team, title }` + `days: [{ date, title, route, camping, meals[], notes }]` |

**User response:** "Sounds reasonable. Tag the home-ops repo before we start."

---

## Pre-phase actions taken during discussion

- **home-ops repo tagged**: `shitbox-pre-phase-19` (annotated, pushed to origin 2026-04-16)
  pinning commit `e5bb8389`. Rollback target if the rebuild needs reverting.

---

## Claude's Discretion

- Card styling, spacing, typography refinements (within locked dark theme)
- Timeline icon set (reuse `BADGE_COLORS` for event icons)
- Thumbnail fallback chain for archive day-grid cards
- Progress-bar segment hover / focus states
- Exact nginx rewrite rule placement in `default.conf`
- Simplification tolerance refinement if `route.json` exceeds 1 MB at ~10 m

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section:

- Pi-side API editability for agenda
- Pre-generated per-day JSON from Pi
- Calendar grid for archive mode
- Descriptor slugs in day URLs
- Mobile-specific tab collapse
- Event attribution counts per driver on `/about` (deferred from Phase 18, not pulled forward)
