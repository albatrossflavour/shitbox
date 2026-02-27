---
phase: 04-remote-health-and-stage-tracking
plan: "02"
subsystem: trip-tracking
tags:
  - gps
  - odometer
  - waypoints
  - aest
  - sqlite
dependency_graph:
  requires:
    - 04-01  # Schema v4 tables (trip_state, waypoints_reached) created in Phase 4-01
  provides:
    - GPS odometer with daily AEST day boundary reset
    - Waypoint-based stage progress tracking persisted in SQLite
  affects:
    - src/shitbox/events/engine.py
    - src/shitbox/utils/config.py
    - config/config.yaml
tech_stack:
  added:
    - WaypointConfig and RouteConfig dataclasses
    - AEST offset helper _current_aest_date()
    - TRIP_PERSIST_INTERVAL_S = 60.0 module constant
  patterns:
    - Odometer accumulation with speed gate (>= 5 km/h) and 1 km/s sanity cap
    - AEST timezone offset for day-boundary logic without tzdata dependency
    - INSERT OR IGNORE for idempotent waypoint persistence
key_files:
  created:
    - tests/test_trip_tracking.py
  modified:
    - src/shitbox/utils/config.py
    - config/config.yaml
    - src/shitbox/events/engine.py
decisions:
  - "Route waypoints stored as flat list on EngineConfig (not nested dataclass) per project pattern"
  - "AEST date calculated via timedelta(hours=10) addition — no tzdata dependency, avoids DST edge cases during non-DST rally period"
  - "Odometer only advances _last_known_lat when speed >= 5 km/h to prevent GPS drift at rest from corrupting accumulator"
  - "Sanity cap of 1 km per fix rejects GPS jumps (3600 km/h would be required to exceed this in 1 second)"
  - "Persistence interval 60 seconds matches existing health report interval — no new timer thread needed"
metrics:
  duration_seconds: 786
  completed_date: "2026-02-27"
  tasks_completed: 2
  files_created: 1
  files_modified: 3
  tests_added: 23
---

# Phase 4 Plan 02: Trip Tracking and Waypoint Detection Summary

GPS-based odometer with AEST daily distance reset and 5 km waypoint proximity detection,
all persisted in SQLite and surviving reboots via the trip_state and waypoints_reached
tables introduced in Phase 4-01.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Config dataclasses, engine distance/waypoint logic, config.yaml route section | 25213b8 | config.py, engine.py, config.yaml |
| 2 | Trip tracking and waypoint detection tests | 83d14dd | tests/test_trip_tracking.py |

## What Was Built

### WaypointConfig and RouteConfig (config.py)

Two new dataclasses added above `GPSConfig`:

- `WaypointConfig(name, day, lat, lon)` — a single named waypoint on the rally route
- `RouteConfig(waypoints: List[WaypointConfig])` — ordered list of waypoints

`GPSConfig` gains `route: RouteConfig = field(default_factory=RouteConfig)`.

`load_config()` handles the waypoints list explicitly after calling `_dict_to_dataclass` on
the GPS dict, because `_dict_to_dataclass` does not recurse into lists of dataclasses.

### config.yaml Route Section

Added under `sensors.gps`:

```yaml
route:
  waypoints: []
  # - name: "Port Douglas"
  #   day: 1
  #   lat: -16.4838
  #   lon: 145.4673
```

Waypoints list is empty in the default config. The user populates it before the rally.

### EngineConfig Extension (engine.py)

- `route_waypoints: list = field(default_factory=list)` added as flat field
- `from_yaml_config()` maps `config.sensors.gps.route.waypoints` to this field

### Module-level Constants and Helpers

- `TRIP_PERSIST_INTERVAL_S = 60.0` — SQLite persistence interval
- `AEST_OFFSET = timedelta(hours=10)` — UTC+10 offset constant
- `_current_aest_date() -> str` — returns today's AEST date string (e.g. `"2026-02-27"`)

### UnifiedEngine Trip Tracking State

New instance variables in `__init__`:

```python
self._odometer_km: float = 0.0
self._daily_km: float = 0.0
self._last_known_lat: Optional[float] = None
self._last_known_lon: Optional[float] = None
self._last_trip_persist: float = 0.0
self._reached_waypoints: set = set()
```

### Boot Loading (start())

After `database.connect()`:

1. Load `odometer_km` and `daily_km` from `trip_state` table
2. Load `daily_reset_date` — if it differs from today's AEST date, reset `daily_km = 0.0`
   and update the stored date
3. Load `_reached_waypoints` from `get_reached_waypoints()`

### Distance Accumulation (_record_telemetry())

After the existing GPS distance-from-start / distance-to-destination block:

- If `speed_kmh >= 5.0` and `_last_known_lat` is set, compute haversine delta
- Reject delta > 1 km (GPS jump protection — 1 km in 1 second = 3600 km/h)
- Accumulate into `_odometer_km` and `_daily_km`
- Update `_last_known_lat` / `_last_known_lon` only when moving
- Persist to SQLite every 60 seconds (checked with `time.monotonic()`)
- Call `_check_waypoints()` unconditionally (waypoints detected regardless of speed)

### Waypoint Detection (_check_waypoints())

For each unreached waypoint in `config.route_waypoints`:

- Compute haversine distance to current position
- If `<= 5.0 km`, add index to `_reached_waypoints`, call `database.record_waypoint_reached()`
- Log `waypoint_reached` with name, day, and distance

Uses `INSERT OR IGNORE` in database layer — idempotent even if called repeatedly.

### get_status() Extension

Four new keys:

- `odometer_km`: `round(self._odometer_km, 1)`
- `daily_km`: `round(self._daily_km, 1)`
- `waypoints_reached`: `len(self._reached_waypoints)`
- `waypoints_total`: `len(self.config.route_waypoints)`

### Tests (test_trip_tracking.py — 506 lines, 23 tests)

**Database helpers (4):** set/get float, set/get text, upsert, missing key returns None.

**Waypoint persistence (3):** record, idempotency, multiple waypoints.

**Haversine (2):** known distance (Port Douglas area), zero distance.

**Odometer logic (4):** accumulates at speed, skips below 5 km/h, rejects delta > 1 km,
persists after interval.

**Daily reset (2):** resets on new AEST day, preserves on same AEST day.

**Waypoint detection (4):** reached, not reached, already-reached skipped, boot load from DB.

**Status fields (2):** `get_status()` counts, AEST date helper.

**AEST helper (2):** UTC 23:00 crosses midnight to AEST next day, UTC noon stays same day.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written with one minor test data correction.

**1. [Rule 1 - Bug] Corrected test coordinate bounds for haversine test**

- **Found during:** Task 2
- **Issue:** Test used Port Douglas to Cairns coordinates expecting ~60-80 km. Actual
  haversine result was ~58.6 km (straight-line < road distance). Lower bound of 60 km failed.
- **Fix:** Changed assertion to `50.0 < dist < 70.0` (accurate for the haversine
  straight-line distance between those specific coordinates).
- **Files modified:** `tests/test_trip_tracking.py`
- **Commit:** 83d14dd (included in Task 2 commit)

**2. [Rule 1 - Bug] Corrected odometer test coordinates to avoid sanity cap rejection**

- **Found during:** Task 2
- **Issue:** Test used coordinates ~1.54 km apart, which exceeded the 1 km/fix sanity cap,
  so the accumulation was correctly rejected. The test expectation was wrong.
- **Fix:** Changed test coordinates to ~0.55 km apart (0.005 degrees latitude) which is
  safely under the 1 km cap. Added `assert expected_delta <= 1.0` as a test precondition guard.
- **Files modified:** `tests/test_trip_tracking.py`
- **Commit:** 83d14dd (included in Task 2 commit)

**3. [Rule 2 - Missing] Added _gps_available and events_captured to engine mock helper**

- **Found during:** Task 2
- **Issue:** `get_status()` accesses `_gps_available` and `events_captured` which were not
  initialised in the `_make_engine_with_state` test helper.
- **Fix:** Added both fields to the helper function.
- **Files modified:** `tests/test_trip_tracking.py`
- **Commit:** 83d14dd (included in Task 2 commit)

## Verification Results

```
pytest tests/test_trip_tracking.py -x -v   → 23 passed
pytest tests/ -x -q                         → 84 passed (61 pre-existing + 23 new)
ruff check src/shitbox/utils/config.py      → 0 errors (new code)
ruff check src/shitbox/events/engine.py     → 4 pre-existing errors (not introduced by this plan)
python -c "load_config(); print(route)"     → RouteConfig(waypoints=[])
```

## Self-Check: PASSED
