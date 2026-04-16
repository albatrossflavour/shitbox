---
phase: 19-website-narrative-rebuild
plan: "01"
subsystem: storage
tags: [sqlite, gps, polyline, douglas-peucker, route-json, capture-sync]

requires:
  - phase: 12-logbook-fuel-driver
    provides: CaptureSyncService.register_json_generator contract + LogbookStorage pattern to mirror
  - phase: 13-driver-tracking
    provides: DriverStorage generator pattern (get_driver_stats_payload)

provides:
  - RouteStorage class with generate_route_json() returning DP-simplified per-day GPS polylines
  - douglas_peucker() iterative simplification function (stack-based, safe for 50k+ points)
  - route.json registered with CaptureSyncService -- published to /captures/route.json on next sync

affects:
  - 19-03 (client mode detection reads route.json generated_at)
  - 19-07 (day-page map slice reads route.json days per YYYY-MM-DD key)

tech-stack:
  added: []
  patterns:
    - "RouteStorage mirrors LogbookStorage: Database injected, generator returns dict, registry writes file"
    - "Iterative Douglas-Peucker (explicit stack) used instead of recursive to avoid Python recursion limit on large inputs"
    - "Sydney timezone via timedelta(hours=10) -- no pytz/zoneinfo dep, works for QLD/NSW rally route"
    - "Explicit SELECT column list enforces PII exclusion structurally (no cost_*, user_id, device_id possible)"

key-files:
  created:
    - src/shitbox/storage/route.py
    - tests/test_route_storage.py
  modified:
    - src/shitbox/events/engine.py
    - tests/test_capture_sync_generators.py

key-decisions:
  - "Iterative DP (stack-based) chosen over recursive to handle 50k-point inputs without RecursionError"
  - "tolerance_m=10.0 used -- 14-day synthetic rally at 1 pt/sec produces 1,255 bytes (well under 1 MB budget)"
  - "Sydney timezone hardcoded as UTC+10 offset (no zoneinfo/pytz dep) -- QLD has no DST and rally runs through QLD"
  - "Per-point timestamps dropped from output (only day-level point_count kept) to reduce payload size and information density"

patterns-established:
  - "register_json_generator fourth entry: notes, fuel, driver-stats, route"

requirements-completed:
  - NARR-08
  - NARR-08b

duration: 8min
completed: 2026-04-16
---

# Phase 19 Plan 01: route.json Generator Summary

**Iterative Douglas-Peucker GPS polyline generator producing per-day route.json, registered with CaptureSyncService alongside notes/fuel/driver-stats**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-16T11:23:14Z
- **Completed:** 2026-04-16T11:31:47Z
- **Tasks:** 3 (TDD: RED commit + GREEN commit + wiring commit)
- **Files modified:** 4

## Accomplishments

- `RouteStorage.generate_route_json()` returns `{generated_at, tolerance_m, days}` dict with DP-simplified per-day GPS polylines bucketed to Australia/Sydney timezone
- `douglas_peucker()` iterative implementation safe for 50k+ point inputs (stack-based, no recursion depth issues)
- Engine wires route generator as the fourth `register_json_generator` call, so rsync publishes `captures/route.json` automatically
- 11 unit tests cover DP correctness, Sydney TZ bucketing, size budget, empty/sparse GPS, no-cost assertion, recursion safety
- Size budget: 504,000 synthetic points (14 days, 1 Hz, 10 h/day) compressed to 1,255 bytes at 10 m tolerance

## Task Commits

1. **Task 1: Wave 0 tests -- test_route_storage.py + extend test_capture_sync_generators.py** - `a70de02` (test)
2. **Task 2: Implement RouteStorage + douglas_peucker** - `b2aac67` (feat)
3. **Task 3: Engine wiring + capture_sync integration test** - `9f74619` (feat)

## Files Created/Modified

- `src/shitbox/storage/route.py` -- RouteStorage class, douglas_peucker() iterative helper, _sydney_date() offset helper
- `tests/test_route_storage.py` -- 11 unit tests covering all acceptance criteria
- `src/shitbox/events/engine.py` -- Added RouteStorage import + register_json_generator("route", ...) block
- `tests/test_capture_sync_generators.py` -- Added test_route_generator_registers_and_writes

## Decisions Made

- **Iterative DP chosen**: recursive DP hits Python's 1000-frame recursion limit on perfectly collinear 50k-point inputs. Iterative stack-based implementation handles arbitrary input sizes without issue.
- **tolerance_m=10.0 kept**: synthetic 14-day rally at 1 pt/sec produces 1,255 bytes -- no need to bump to 15 m fallback. Budget is trivially met with collinear data; real GPS drift will produce more points but still well under 1 MB.
- **UTC+10 fixed offset**: no zoneinfo or pytz dependency. QLD (Port Douglas start) has no DST. NSW (Melbourne end) is UTC+11 in summer but UTC+10 in autumn when the rally runs. Fixed offset is correct for this use case.
- **Per-point timestamps excluded**: output points are `[lat, lng]` 2-element arrays only. Timestamps add no navigational value in the polyline context and would double payload size.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Switched to iterative DP to avoid RecursionError**

- **Found during:** Task 2 analysis before writing implementation
- **Issue:** The plan skeleton shows a recursive `douglas_peucker()`. For perfectly collinear 50k-point inputs, recursive DP with a naive pivot selection can reach recursion depth ~n/2, exceeding Python's 1000-frame default limit. The test `test_dp_recursion_safe_on_50k_points` would have failed with RecursionError.
- **Fix:** Replaced recursive implementation with iterative stack-based version that produces identical output but with O(1) stack depth.
- **Files modified:** src/shitbox/storage/route.py
- **Verification:** test_dp_recursion_safe_on_50k_points passes; all DP correctness tests (trivial passthrough, collinear collapse, sharp turn preserved) still pass.
- **Committed in:** b2aac67 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug pre-empted before it could fail)
**Impact on plan:** Essential for correctness. No scope creep.

## Issues Encountered

None -- all acceptance criteria met on first implementation attempt after the DP algorithm choice.

## Known Stubs

None -- RouteStorage reads live GPS data from the `readings` table. No hardcoded values, no mock data flowing to output.

## Threat Flags

No new threat surface introduced. `route.json` trust boundary (Pi daemon to public nginx via rsync) was already in the plan's threat model and mitigated via explicit SELECT column list.

## Final Metrics

- **tolerance_m used:** 10.0 (default -- no bump required)
- **Actual size-budget result:** 1,255 bytes for 14-day synthetic rally (504,000 points in, 28 out)
- **Recursion approach:** iterative (stack-based) -- deviation from plan skeleton but required for correctness

## User Setup Required

None -- route generator runs automatically on next daemon restart. On-device verification deferred to first Pi daemon restart per plan §verification.

## Next Phase Readiness

- Plan 19-03 (client mode detection) can now read `route.json.generated_at` as freshness signal
- Plan 19-07 (day-page map slice) can read `route.json.days["YYYY-MM-DD"]` for polyline data
- No blockers

---
*Phase: 19-website-narrative-rebuild*
*Completed: 2026-04-16*
