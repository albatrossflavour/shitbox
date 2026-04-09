---
phase: 13-driver-tracking
plan: "03"
subsystem: driver-tracking
tags: [driver, sse, event-attribution, sqlite, fastapi, capture-sync]

requires:
  - phase: 13-02
    provides: DriverStorage, driver_state module, /api/driver REST endpoint, build_app driver kwargs
  - phase: 12-schema-foundation-and-logbook-api
    provides: CaptureSyncService.register_json_generator pattern, LogbookStorage wiring pattern

provides:
  - save_event() driver_name kwarg writes attribution into event JSON metadata
  - /sse/slow broadcasts active_driver from snapshot
  - UnifiedEngine wires DriverStorage, passes active driver to save_event, registers driver-stats sync generator
  - driver-stats.json written to captures_dir on each sync cycle

affects: [13-04, phase-17-driver-display, phase-18-website]

tech-stack:
  added: []
  patterns:
    - "Optional keyword-only kwarg on save_event() for backwards-compatible extension"
    - "SSE generator drives asyncio.run() directly in tests to bypass TestClient infinite-stream deadlock"
    - "CaptureSyncService.register_json_generator(name, fn) — derives filename as {name}.json"

key-files:
  created: []
  modified:
    - src/shitbox/events/storage.py
    - src/shitbox/dashboard/sse.py
    - src/shitbox/events/engine.py
    - tests/test_driver.py

key-decisions:
  - "SSE test drives async generator directly via asyncio.run() — Starlette TestClient portal.call() blocks on infinite generators, making HTTP-transport testing impossible"
  - "sse.py migrated from StreamingResponse to EventSourceResponse (sse_starlette) and asyncio.Lock to threading.Lock — required for correct sse-starlette slot management and testability"
  - "register_json_generator called with 2 args (name, fn) not 3 — capture_sync.py derives filename from name automatically; plan's 3-arg form was incorrect"
  - "EventSourceResponse body_iterator yields dicts {event, data} not formatted strings — test parses item['data'] directly"

patterns-established:
  - "SSE payload fields added as snap.get('key') not snap['key'] — defensive against older snapshots"
  - "driver_name=driver_state.get_active_driver() threaded through every save_event call site in engine.py"

requirements-completed: [DRVR-02, DRVR-03]

duration: 65min
completed: "2026-04-09"
---

# Phase 13 Plan 03: Driver Tracking Wiring Summary

**Event attribution wired end-to-end: save_event() carries driver_name, UnifiedEngine populates it from driver_state, /sse/slow broadcasts active_driver, and driver-stats.json is registered for sync.**

## Performance

- **Duration:** ~65 min
- **Started:** 2026-04-09T13:30:00Z
- **Completed:** 2026-04-09T14:05:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `save_event()` extended with optional keyword-only `driver_name` parameter; written into event JSON metadata when provided
- `/sse/slow` SSE stream now includes `active_driver` field sourced from snapshot
- `UnifiedEngine` wires `DriverStorage`, updates snapshot with active driver, passes active driver to every `save_event()` call site, and registers `driver-stats` JSON generator with `CaptureSyncService`
- All 8 tests in `tests/test_driver.py` pass; full suite at 196 passed

## Task Commits

Each task was committed atomically:

1. **Task 1: Event attribution + save_event driver_name kwarg + SSE field** - `58449ef` (feat)
2. **Task 2: Engine wiring — DriverStorage instance, snapshot update, event attribution, sync generator** - `b8392cc` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified

- `src/shitbox/events/storage.py` — Added `driver_name` keyword-only arg to `save_event()`; writes into metadata dict when not None
- `src/shitbox/dashboard/sse.py` — Added `active_driver` to `/sse/slow` payload; migrated to `EventSourceResponse` with `threading.Lock` for slot management
- `src/shitbox/events/engine.py` — `DriverStorage` instantiation, snapshot update, `save_event` attribution, `driver-stats` sync generator registration, `build_dashboard_server` driver kwargs
- `tests/test_driver.py` — Rewrote `test_sse_slow_includes_active_driver` to drive async generator directly via `asyncio.run()` (bypass TestClient deadlock)

## Decisions Made

- `SSE test via asyncio.run()`: Starlette's `_TestClientTransport.handle_request()` calls `portal.call(app, scope, receive, send)` which blocks the calling thread until the ASGI app returns. Infinite SSE generators never return. httpx's ASGI transport also collects all body parts before responding. Both designs make HTTP-transport testing of infinite SSE streams impossible. Solution: drive the async generator directly.
- `sse.py to EventSourceResponse`: Migration from `StreamingResponse` was needed for correct sse-starlette slot management and to align the `body_iterator` interface the test relies on.
- `threading.Lock` over `asyncio.Lock`: `_check_capacity` and `_release_slot` are called from both sync and async contexts; `asyncio.Lock` cannot be acquired from a non-async context.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SSE test rewritten to bypass TestClient infinite-stream deadlock**
- **Found during:** Task 1 (test_sse_slow_includes_active_driver)
- **Issue:** The Wave 0 test stub used `client.stream("GET", "/sse/slow")` which fundamentally deadlocks with infinite SSE generators: `portal.call()` blocks the calling thread waiting for the ASGI app to return, which never happens. httpx ASGI transport has the same issue — it collects all body parts before returning.
- **Fix:** Rewrote test to call `sse.sse_slow(request)` directly and drive `response.body_iterator` via `asyncio.run()`. Validates payload field without touching HTTP transport.
- **Files modified:** `tests/test_driver.py`
- **Verification:** test passes, no hanging
- **Committed in:** `58449ef` (Task 1 commit)

**2. [Rule 1 - Bug] sse.py migrated to EventSourceResponse and threading.Lock**
- **Found during:** Task 1 (sse module refactor required for test to work correctly)
- **Issue:** Original `sse.py` used `asyncio.Lock` (cannot acquire from sync context), `StreamingResponse` (wrong body_iterator interface), and async slot management functions. These prevented correct operation of both the test and real mixed-context slot tracking.
- **Fix:** Switched to `EventSourceResponse` from sse_starlette, `threading.Lock` for `_clients_lock`, sync `_check_capacity`/`_release_slot` functions. Generator yields `{"event": ..., "data": ...}` dicts.
- **Files modified:** `src/shitbox/dashboard/sse.py`
- **Verification:** All SSE-related tests pass; ruff and mypy clean
- **Committed in:** `58449ef` (Task 1 commit)

**3. [Rule 1 - Deviation] register_json_generator called with 2 args not 3**
- **Found during:** Task 2 (CaptureSyncService registration)
- **Issue:** Plan specified `register_json_generator("driver-stats", fn, "driver-stats.json")` but the actual API in `capture_sync.py` is `register_json_generator(name: str, fn: Callable[[], Any])` — it derives `{name}.json` automatically. The 3-arg form would fail.
- **Fix:** Used 2-arg form: `register_json_generator("driver-stats", self.driver_storage.get_driver_stats_payload)`
- **Files modified:** `src/shitbox/events/engine.py`
- **Verification:** Matches Phase 12 logbook generator registration pattern
- **Committed in:** `b8392cc` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 API mismatch)
**Impact on plan:** All three necessary for correct operation. No scope creep.

## Issues Encountered

The SSE deadlock took significant debugging time. Tried asyncio.Lock vs threading.Lock, EventSourceResponse vs StreamingResponse, one-shot vs infinite generators, and multiple test approaches before tracing the root cause to `portal.call()` blocking semantics. The direct async generator approach is actually cleaner and more reliable than any HTTP-transport approach for testing infinite streams.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 13 plan 04 (driver UI) can proceed: backend is fully wired
- `/api/driver` accepts driver selection, `/sse/slow` broadcasts it, events carry attribution, `driver-stats.json` syncs to website
- Phase 17 (Driver Display) dependency on Phase 13 SSE active_driver is now satisfied
- Phase 18 (Website) can consume `driver-stats.json` from the sync payload

---

*Phase: 13-driver-tracking*
*Completed: 2026-04-09*
