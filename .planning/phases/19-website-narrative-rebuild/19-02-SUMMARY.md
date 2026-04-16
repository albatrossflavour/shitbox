---
phase: 19
plan: "02"
subsystem: website
tags: [website, agenda, nginx, spa, json]
dependency_graph:
  requires: []
  provides: [agendaData, routeData, agenda.json, nginx-no-cache-agenda]
  affects: [shit-of-theseus.com, Plans 19-03 through 19-08]
tech_stack:
  added: []
  patterns: [parallel-fetch, module-level-data-vars, nginx-location-exact-match]
key_files:
  created:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/agenda.json
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/nginx-config/default.conf
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - "Placeholder rally dates used (27 May - 5 June 2026) — Brain doc shows rally postponed from 1 May with no new date set; plan defaults applied"
  - "routeData declared and fetched here alongside agendaData — same plan scope, natural fit, Plan 19-03 consumers expect both"
metrics:
  duration_seconds: 1226
  completed_date: "2026-04-16"
  tasks_completed: 3
  files_modified: 3
---

# Phase 19 Plan 02: Agenda JSON + Nginx Cache + SPA Fetch Plumbing Summary

One-liner: Static agenda.json with full D-10 schema (10-day rally schedule), nginx no-cache block for `/agenda.json` and extended captures regex to include `route.json`, and two new fetch chains wired into the SPA parallel-fetch pipeline.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Author webroot/agenda.json with full schedule | e480a1b4 (home-ops) | webroot/agenda.json |
| 2 | Add nginx no-cache rule for /agenda.json | e6d3effd (home-ops) | nginx-config/default.conf |
| 3 | Add agendaData fetch to SPA parallel-fetch pipeline | 84a48e89 (home-ops) | webroot/index.html |

## What Was Built

### agenda.json

Full 10-day Shitbox Rally 2026 schedule at `webroot/agenda.json`. Schema matches D-10 exactly:

- `rally` envelope: `start_date`, `end_date`, `team`, `title`, `start_location`, `end_location`, `total_distance_km` (3534), `timezone`
- `days[]` array: 10 entries, `date` sequential from 2026-05-27 to 2026-06-05, `day_number` 1..10, `title` with U+2192 arrow, `route` prose, `camping` string or null, `meals[]` array (never null), `notes` string or null
- Placeholder route/camping data for each day — real content lands via git edits during the rally
- Final day (Melbourne) has a non-null `notes` field as proof of concept

### nginx-config/default.conf

Two changes in one commit:

1. Extended the existing captures regex from `(events|timelapse|notes|fuel|driver-stats)` to include `|route` — covers the `route.json` artefact from Plan 19-01
2. New `location = /agenda.json` block with the same three no-cache headers as `index.html` and the captures regex

File went from 29 to 35 lines. `try_files` SPA fallback preserved intact.

### webroot/index.html

Two surgical edits:

1. Added `var agendaData = null;` and `var routeData = null;` alongside the four existing module-level data variable declarations (lines ~1017-1021). Total module-level data vars: 6.
2. Added two new fetch chains after the driver-stats fetch, following the exact same pattern as existing fetches. Both have `.catch` handlers that `console.warn` and set the variable to null — graceful degradation on 404.

No existing render functions modified. No existing fetch chains altered.

## Deviations from Plan

### Rally dates: placeholder used, Brain doc shows postponement

**Found during:** Task 1

**Issue:** The Brain doc (`~/Brain/projects/shitbox-rally-2026.md`) states "Rally originally 1 May 2026, postponed indefinitely due to fuel price hikes and shortages (the war)". No new date is recorded in the Brain doc.

**Resolution:** Plan 19-02 explicitly instructs using the placeholder dates (27 May - 5 June 2026) if the Brain doc doesn't give a different canonical range. Applied as instructed. The placeholder is correct to use — agenda.json will be edited via git before the rally with the confirmed dates.

**No schema deviation** — the dates are a content stub, not a structural issue.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `route`, `camping`, `meals` are placeholder content for days 3-10 | webroot/agenda.json | Intentional. Content lands via git edits during rally planning and race day. Plan 19-02 explicitly says "stub is fine". |
| Rally dates 2026-05-27 to 2026-06-05 | webroot/agenda.json | Placeholder per plan instruction. Actual dates TBD — rally postponed indefinitely. Update before deploy. |

These stubs do not prevent the plan's goal from being achieved. The data contract (schema shape, fetch plumbing, cache headers) is fully wired. Plans 19-03 through 19-08 consume `agendaData` and `routeData` — both are available.

## Threat Surface Scan

No new trust boundaries introduced beyond what the threat model covers. `agenda.json` is public-facing static content (T-19-02-01 accepted). No PII, no phone numbers, no home addresses in the file. Supply chain remains git-controlled (T-19-02-02 mitigated by design). SPA consumers will need `if (agendaData && agendaData.rally ...)` guards — T-19-02-03 mitigation deferred to Plans 19-03+ where consumption happens.

## Self-Check: PASSED

- `webroot/agenda.json` exists and validates: FOUND
- `nginx-config/default.conf` contains `location = /agenda.json`: FOUND
- `index.html` contains `var agendaData = null;` and `fetch('/agenda.json'`: FOUND
- Commits e480a1b4, e6d3effd, 84a48e89 exist in home-ops main: FOUND
