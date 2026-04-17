---
phase: 19
plan: "12"
subsystem: planning
tags: [close-out, requirements, traceability, brain-doc]
dependency_graph:
  requires: [19-11]
  provides: [phase-19-close-out, narr-traceability]
  affects: [.planning/REQUIREMENTS.md, Brain/projects/shitbox-rally-2026.md]
tech_stack:
  added: []
  patterns: []
key_files:
  modified:
    - .planning/REQUIREMENTS.md
    - ~/Brain/projects/shitbox-rally-2026.md
decisions:
  - Brain vault is Obsidian Sync (not git) -- no git commit possible for Brain file, edit in-place suffices
  - Rally date in Brain entry uses confirmed July 10 2026 (Box Rallies newsletter 2026-04-16), not the placeholder 2026-05-27 from agenda.json
  - agenda.json placeholder dates flagged as Phase 19.1 candidate -- needs update before rally
metrics:
  duration_minutes: 14
  completed_date: "2026-04-16"
  tasks_completed: 2
  files_modified: 2
---

# Phase 19 Plan 12: Phase Close-Out Summary

Phase 19 housekeeping: NARR-01..NARR-10 added to REQUIREMENTS.md with full traceability, Brain project doc updated to reflect Phase 19 completion, rollback tag confirmed, and mid-rally refinements flagged for Phase 19.1.

## What Was Built

### Task 1: NARR requirements + traceability

`.planning/REQUIREMENTS.md` now has a `### Narrative (NARR)` section between `### Monitoring (MON)` and `## Future Requirements`. 10 primary requirements (NARR-01..NARR-10) plus NARR-08b (home-address exclusion) all marked `[x]` complete. 11 traceability rows appended to the Traceability table, all pointing to Phase 19 / Complete.

### Task 2: Brain project doc update

`~/Brain/projects/shitbox-rally-2026.md` Active Now section updated with a 2026-04-16 Phase 19 completion entry. Previous V2 hardware prep content moved under `### Previous` heading. Entry uses the confirmed rally date (July 10 2026) rather than the placeholder dates from agenda.json. Brain vault uses Obsidian Sync, not git -- no commit step required.

### Task 3: Live-site verification (auto-approved)

Auto-advance mode active. Checkpoint auto-approved. Rollback tag confirmed:

- **Tag**: `shitbox-pre-phase-19`
- **SHA**: `b9f9ff6638ffd1a73d5894edcafa30114dea3fba`
- **Rollback command**: `git -C ~/dev/home-ops checkout b9f9ff6638ffd1a73d5894edcafa30114dea3fba -- kubernetes/apps/default/shit-of-theseus/app/webroot/index.html && git -C ~/dev/home-ops commit -m "revert: rollback index.html to pre-phase-19"` then Flux reconcile.

## index.html Byte Count Before / After Phase 19

| Point | Lines | Bytes |
|-------|-------|-------|
| Pre-phase-19 (shitbox-pre-phase-19 tag) | 1,717 | 74,948 |
| Post-phase-19 (after Plan 19-11) | 2,107 | 91,389 |
| Net change | +390 lines | +16,441 bytes |

The net increase looks wrong at first glance -- the rebuild _added_ code. But the pre-phase starting point (1,717 lines) was the already-refactored Phase 18 result. Phase 19 added entirely new functionality (SPA router, day pages, agenda rendering, timeline spine, map slices, before/live/archive mode logic, day-nav progress bar) while simultaneously removing the 9-tab legacy shell. The code is denser but does significantly more.

## Phase 19 Retrospective

### What landed cleanly (no rework)

- Plans 19-01 (route.json generator) and 19-02 (agenda.json + data fetch) -- pure Python/JSON, no DOM entanglement, clean interfaces
- Plans 19-04 (day-nav progress bar) and 19-05 (day page scaffold + agenda context) -- well-scoped, single-concern
- Plan 19-09 (before/live/archive homepage modes) -- state machine was clear from research, implementation matched spec
- Plan 19-11 (nav shrink + legacy purge) -- demolition work, straightforward

### What required rework or adjustment

- Plan 19-03 (SPA router) -- Promise.allSettled added to replace individual fetch chains after router integration revealed race conditions. Minor but tracked as deviation.
- Plan 19-06 (timeline spine) -- stage bookend approach changed from GPS motion detection to first/last event of day (simpler, deferred GPS transitions as future extension point)
- Plan 19-07 (per-day map) -- straightforward but the map teardown pattern needed careful alignment with SPA navigation to avoid Leaflet container reuse errors
- Plan 19-10 (live-mode driver widget + 2-minute refresh) -- timer lifecycle required same teardown discipline as map; `_stopCountdown()` pattern added

### Context budget usage

12 plans across 4 waves, each plan a separate agent context. Wave structure worked well -- dependencies were clear, no plan blocked on ambiguous interfaces. Research phase (19-RESEARCH.md) paid off: NARR-XX definitions were stable across all 12 plans, no mid-phase requirement drift.

The most context-heavy plans were 19-03 (SPA router foundation, establishes all patterns) and 19-11 (destructive purge, large file, many greps needed). Both completed without overflow.

## Phase 19.1 Candidates

| Item | Priority | Trigger |
|------|----------|---------|
| agenda.json placeholder dates (2026-05-27..2026-06-05) need updating to confirmed 2026-07-10 start | High | Before rally starts -- before-mode countdown will be wrong |
| Shake-down drive to validate route.json on real GPS data | High | First long drive with Pi installed |
| Video/timelapse stubs in renderDayPage (lines ~1865-1866) | Medium | After Phase 18 WEB-01/WEB-02 land |
| Live-mode test after first rally day -- any rendering issues with real data | Medium | Day 1 of rally |
| DRVR-04 current-driver widget (was in live-mode plan, currently uses driverStatsData[0] as placeholder) | Low | Depends on Phase 13 driver SSE data flowing through |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Brain vault has no git repo**

- **Found during**: Task 2
- **Issue**: Plan specified `git add / git commit` from `cwd=~/Brain/`. Brain is an Obsidian vault with Obsidian Sync -- no `.git` directory exists.
- **Fix**: Edit applied in-place via Edit tool. File will sync via Obsidian Sync as designed. No git commit step. This matches the CLAUDE.md sequential execution note: "No git commit needed for the Brain vault."
- **Files modified**: `~/Brain/projects/shitbox-rally-2026.md`

**2. [Rule 1 - Adjustment] Rally date uses confirmed date, not plan placeholder**

- **Found during**: Task 2
- **Issue**: Plan text specified "Rally starts 2026-05-27" (placeholder agenda.json dates). Brain doc already records confirmed rally date as July 10 2026 (from Box Rallies newsletter entry in the same file).
- **Fix**: Brain doc entry uses 2026-07-10 (correct). Agenda.json placeholder dates flagged as Phase 19.1 candidate.

## Commits

| Task | Commit | Repo | Description |
|------|--------|------|-------------|
| Task 1 | cd9f17f | shitbox | docs(19): add NARR-01..NARR-10 requirements + traceability rows |
| Task 2 | (Brain vault -- Obsidian Sync, no git) | Brain | shitbox-rally-2026.md Active Now updated |
| Meta | (this commit) | shitbox | docs(19-12): phase close-out SUMMARY + state updates |

## Self-Check: PASSED

- `.planning/REQUIREMENTS.md` contains `### Narrative (NARR)` section: confirmed (grep count = 1)
- NARR-01..NARR-10 all marked complete: confirmed (11 traceability rows present including NARR-08b)
- Brain doc contains "Phase 19 website narrative rebuild": confirmed (grep count = 1)
- Brain doc contains "2026-04-16": confirmed (grep count = 5)
- Rollback tag `shitbox-pre-phase-19` exists in home-ops: confirmed (SHA b9f9ff6638ffd1a73d5894edcafa30114dea3fba)
- Commit cd9f17f exists in shitbox git log: verified
