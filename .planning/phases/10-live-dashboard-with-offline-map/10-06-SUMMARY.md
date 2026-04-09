---
phase: 10-live-dashboard-with-offline-map
plan: "06"
subsystem: ui
tags: [leaflet, sse, alpine, dashboard, javascript]

requires:
  - phase: 10-04
    provides: live position dot, breadcrumb polyline, and SSE events stream with lat/lng fields

provides:
  - "L.circleMarker placed on Leaflet map for each incoming SSE event with non-null lat/lng"
  - "EVENT_COLOURS map inside openEvents() matching the .ev-* CSS palette"
  - "pytest test confirming event payloads carry lat/lng through push_event() to the SSE stream"

affects: [dashboard, sse, testing]

tech-stack:
  added: []
  patterns:
    - "EVENT_COLOURS defined inside openEvents() scope to avoid polluting Alpine data object"
    - "SSE tests drain module-level event_queue before pushing to avoid cross-test contamination"
    - "SSE tests use max_lines=2 with empty seed provider to read exactly one event without blocking"

key-files:
  created: []
  modified:
    - src/shitbox/dashboard/static/index.html
    - tests/test_dashboard.py

key-decisions:
  - "EVENT_COLOURS defined as a local const inside openEvents() so it does not appear on the Alpine reactive data object"
  - "Test uses recent_events_provider=lambda n: [] to bypass stale module-level _recent_provider from previous test runs"
  - "max_lines=2 chosen to read the event: and data: lines of exactly one SSE frame then disconnect, avoiding the 1s queue poll block"

patterns-established:
  - "SSE test isolation: drain event_queue + pass empty recent_events_provider before each SSE events test"

requirements-completed: []

duration: 5min
completed: 2026-04-09
---

# Phase 10 Plan 06: Live Event Markers on Map Summary

**Coloured L.circleMarker placed on Leaflet map in openEvents() for every SSE event with GPS coordinates, closing D-21**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-09T10:24:37Z
- **Completed:** 2026-04-09T10:29:16Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `openEvents()` now places a coloured circle marker on the Leaflet map whenever an event arrives with non-null lat/lng
- Colour lookup uses `EVENT_COLOURS` matching the `.ev-* CSS` palette (HIGH_G red, HARD_BRAKE red, BIG_CORNER amber, ROUGH_ROAD purple, MANUAL/BUTTON green, BOOT blue, fallback grey)
- Each marker binds a popup showing `type · peak_g` (e.g. "HIGH_G · 2.4g"), or just the type if peak_g is null
- Existing strip behaviour (unshift/pop to 10 events) is unchanged
- New pytest test `test_sse_events_payload_has_lat_lng` gives automated regression coverage confirming lat/lng survive the push_event path

## Task Commits

Each task was committed atomically:

1. **Task 1: Add circleMarker call to openEvents()** - `9ad8806` (feat)
2. **Task 2: Add pytest test for event payload lat/lng fields** - `5662d99` (test)

## Files Created/Modified

- `src/shitbox/dashboard/static/index.html` - openEvents() extended with EVENT_COLOURS lookup and L.circleMarker call
- `tests/test_dashboard.py` - import pytest added; test_sse_events_payload_has_lat_lng appended

## Decisions Made

- `EVENT_COLOURS` defined as a local const inside `openEvents()` rather than on the Alpine data object, keeping the reactive state clean
- Test passes `recent_events_provider=lambda n: []` to avoid inheriting the BOOT seed left by `test_sse_events_initial_and_live`
- `max_lines=2` used in the SSE read call -- one event frame is 2 lines (event: + data:) and the loop exits immediately, preventing the 1-second queue poll from causing an httpx ReadTimeout

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test isolation: stale module-level state across test runs**
- **Found during:** Task 2 (Add pytest test)
- **Issue:** The module-level `event_queue` and `_recent_provider` in `sse.py` persist across test runs. `test_sse_events_initial_and_live` sets `_recent_provider` to a BOOT-seeding lambda; our new test inheriting that provider would read the BOOT seed event instead of the HIGH_G we pushed.
- **Fix:** Added queue drain loop before push, and passed `recent_events_provider=lambda n: []` to `build_app()` to reset the provider for this test.
- **Files modified:** tests/test_dashboard.py
- **Verification:** `pytest tests/test_dashboard.py -q` -- 14 passed
- **Committed in:** 5662d99 (Task 2 commit)

**2. [Rule 1 - Bug] `max_lines` sizing for SSE frame read**
- **Found during:** Task 2 (Add pytest test)
- **Issue:** Plan specified `max_lines=10, timeout=4.0` but one SSE frame is only 2 lines (event: + data:). Reading 10 lines requires multiple events; after draining the queue the stream blocks on `event_queue.get(True, 1.0)` per poll, causing httpx ReadTimeout.
- **Fix:** Reduced to `max_lines=2` which reads exactly one event frame and disconnects.
- **Files modified:** tests/test_dashboard.py
- **Verification:** Test passes in 1.5s; full suite passes in 4.2s
- **Committed in:** 5662d99 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs in the test, no changes to production code)
**Impact on plan:** Fixes were necessary for test correctness. No scope creep. Production index.html matches the plan exactly.

## Issues Encountered

None in production code. Two test isolation issues resolved automatically (see deviations above).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

D-21 is fully satisfied: live position dot (Plan 04), breadcrumb polyline (Plan 04), and event markers (this plan) are all in place. The full dashboard test suite passes with 14 tests green.

---
*Phase: 10-live-dashboard-with-offline-map*
*Completed: 2026-04-09*
