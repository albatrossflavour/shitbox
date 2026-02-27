# Phase 4: Remote Health and Stage Tracking - Research

**Researched:** 2026-02-27
**Domain:** System metrics collection, GPS odometry, waypoint-based route tracking, SQLite persistence
**Confidence:** HIGH

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Health metrics scope:** Four metrics only — CPU temp, disk %, sync backlog, throttle state. No
  extras. Piggyback on existing batch sync interval (no separate push cadence). CPU temperature read
  from `ThermalMonitorService.current_temp_celsius` (Phase 3 shared value), not an independent sysfs
  read. New `HealthCollector` following the existing `BaseCollector` pattern.

- **Distance tracking:** Odometer stored in SQLite for crash-safe persistence across reboots. Speed
  threshold of 5 km/h to filter GPS noise — only accumulate distance when moving. Accumulate in
  memory on every GPS fix (1 Hz), persist to SQLite every 60 seconds. Integrated into the existing
  GPS collector path (not a separate service thread).

- **Route and stage progress:** No GPX file — route defined as ordered waypoints (town name +
  lat/lng) in YAML config. Each waypoint has a day number for stage identification. Waypoint counted
  as "reached" when GPS is within 5 km radius. Reached waypoints persisted in SQLite — cannot be
  un-reached, survives reboots. Progress shown as waypoints reached / total waypoints for
  stage-level tracking. Cumulative odometer distance serves as overall trip distance.

- **Day boundary logic:** Daily distance resets on first boot of a new calendar day (not a midnight
  timer). Daily distance persists across mid-day reboots — stored in SQLite with last-reset date.
  Fixed AEST (UTC+10) timezone for day boundaries regardless of physical location. Daily distance
  labelled by stage: "Day 3: 512 km" using waypoint day numbers.

### Claude's Discretion

- SQLite table schema for distance/waypoint tracking
- Haversine vs simpler distance calculation
- `HealthCollector` metric naming conventions for Prometheus
- How to wire the route config into the existing YAML config structure

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HLTH-01 | System publishes CPU temp, disk %, sync backlog, and throttle state to Prometheus via existing remote_write | `HealthCollector` reads from `ThermalMonitorService`, `shutil.disk_usage`, `BatchSyncService.get_backlog_count()`, and `_read_throttled()`; inserts a `SensorType.SYSTEM` reading each batch-sync interval; existing `_readings_to_metrics()` in `batch_sync.py` already handles `system` sensor type (maps `cpu_temp_celsius` → `shitbox_cpu_temp`) — three new fields needed |
| STGE-01 | System tracks cumulative distance from GPS (odometer-style total km) | Haversine already implemented as `UnifiedEngine._haversine_km()` — verified correct; accumulate in memory per GPS fix, persist every 60 s to a new `trip_state` SQLite table; load on boot |
| STGE-02 | System tracks daily distance (resets on new driving day) | Daily distance + last-reset date stored in same `trip_state` table; reset check on boot using AEST (UTC+10) via `datetime` with `timedelta`; no external timezone library needed |
| STGE-03 | System loads waypoint-based rally route and tracks stage progress (waypoints reached within 5 km, day label) | Waypoints in YAML config as a list under `sensors.gps.route`; loaded into a new `RouteConfig` dataclass; reached waypoints stored in a `waypoints_reached` SQLite table keyed by waypoint index; 5 km haversine check on every GPS fix |

</phase_requirements>

## Summary

Phase 4 has four concrete deliverables across two concern areas: health metrics publication
(HLTH-01) and GPS-based trip/stage tracking (STGE-01, STGE-02, STGE-03). The good news is that
nearly all the hard infrastructure already exists — the Prometheus remote write path, the haversine
function, the `ThermalMonitorService`, and the GPS read loop are all in place from earlier phases.
This phase is primarily about adding new data flows that attach to that existing infrastructure.

The health metrics work is the smallest piece: create a `HealthCollector` that assembles four
scalar values into a `Reading` object each batch-sync cycle, then extend `_readings_to_metrics()`
in `batch_sync.py` to emit three new Prometheus metric names for disk %, backlog, and throttle
state (CPU temp already maps via `shitbox_cpu_temp`). No new threading is needed — the collection
fires inside the existing `_telemetry_loop` on the existing 1 Hz cadence, and the batch sync path
picks it up on its own interval.

The trip tracking work requires a new SQLite table (`trip_state`) for persisting odometer and daily
distance, and a `waypoints_reached` table for idempotent waypoint detection. The accumulation logic
lives inside `_record_telemetry()` in `engine.py`, integrated directly into the GPS reading block.
Route configuration uses a new `RouteConfig` / `WaypointConfig` dataclass hierarchy wired into the
existing `GPSConfig` → `SensorsConfig` → `Config` chain. The AEST timezone offset is a simple
`timedelta(hours=10)` applied to UTC — no pytz or zoneinfo required.

**Primary recommendation:** Plan this as two tasks — (1) health metrics (HLTH-01) and (2) distance
and waypoint tracking (STGE-01/02/03). Both are self-contained and can be implemented in sequence
within a single plan.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `shutil` (stdlib) | Python stdlib | `disk_usage(path)` for disk % | Already imported in `engine.py`; no new dependency |
| `datetime` + `timedelta` (stdlib) | Python stdlib | AEST day boundary calculation | Already used throughout codebase; `timedelta(hours=10)` avoids any external tz library |
| `sqlite3` (stdlib) | Python stdlib | `trip_state` and `waypoints_reached` tables | Pattern already established in `database.py` |
| `math` (stdlib) | Python stdlib | Haversine already in engine.py as `_haversine_km()` | Already implemented and correct |
| `structlog` | >=24.0.0 | All logging | Project standard — keyword-args style |
| `threading` | stdlib | Lock for in-memory odometer state | Project pattern from `ThermalMonitorService._lock` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess` | stdlib | `vcgencmd get_throttled` for throttle state | Already used in `ThermalMonitorService._read_throttled()`; re-read in `HealthCollector` or read from shared `ThermalMonitorService` |
| `pyproject.toml` existing deps | — | No new pip dependencies required for this phase | All needed capabilities are stdlib or already installed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `timedelta(hours=10)` for AEST | `zoneinfo.ZoneInfo("Australia/Brisbane")` | `zoneinfo` is cleaner but requires Python 3.9+ backport on older Pi images; `timedelta` is zero-dependency and AEST never observes DST (Queensland), so a fixed offset is correct |
| In-engine distance accumulation | Separate `OdometerService` thread | Separate thread adds concurrency complexity; GPS is already read in `_record_telemetry()` at 1 Hz — accumulating there is simpler and the decision is locked |
| Haversine from `geopy` | Custom `_haversine_km()` | Engine already has `_haversine_km()` as a static method — reuse it; don't add a new dependency |

**Installation:** No new packages required.

## Architecture Patterns

### Recommended Project Structure

```text
src/shitbox/
├── health/
│   └── health_collector.py     # NEW: HealthCollector class (HLTH-01)
├── storage/
│   └── database.py             # EXTEND: trip_state + waypoints_reached tables
├── utils/
│   └── config.py               # EXTEND: WaypointConfig, RouteConfig, GPSConfig update
├── events/
│   └── engine.py               # EXTEND: odometer/waypoint logic in _record_telemetry()
├── sync/
│   └── batch_sync.py           # EXTEND: _readings_to_metrics() for health fields
config/
└── config.yaml                 # EXTEND: sensors.gps.route waypoints list
tests/
└── test_health_collector.py    # NEW: HLTH-01 tests
└── test_trip_tracking.py       # NEW: STGE-01/02/03 tests
```

### Pattern 1: HealthCollector Following BaseCollector

The `HealthCollector` does NOT extend `BaseCollector` — it is a value-assembler, not a sensor
poller with its own thread. The correct analogy is the inline `_read_system_status()` method in
`engine.py` which builds a `Reading` from sysfs. `HealthCollector` is a helper class that:

1. Holds references to `ThermalMonitorService`, `BatchSyncService`, and `database_path`
2. Exposes a `collect()` method that returns a `Reading` with all four health fields
3. Is called from `_record_telemetry()` alongside the existing GPS/IMU/system reads

**What it does NOT do:** Run its own thread. The locked decision says "piggyback on existing batch
sync interval" — in practice this means writing a `SensorType.SYSTEM` reading each telemetry cycle
(1 Hz), which the batch sync picks up on its own schedule.

```python
# Source: codebase pattern — existing _read_system_status() in engine.py
class HealthCollector:
    def __init__(
        self,
        thermal_monitor: ThermalMonitorService,
        batch_sync: Optional[BatchSyncService],
        data_dir: str,
    ) -> None:
        self._thermal = thermal_monitor
        self._batch_sync = batch_sync
        self._data_dir = data_dir

    def collect(self) -> Optional[Reading]:
        cpu_temp = self._thermal.current_temp_celsius
        disk = shutil.disk_usage(self._data_dir)
        disk_pct = (disk.used / disk.total) * 100.0
        backlog = self._batch_sync.get_backlog_count() if self._batch_sync else 0
        throttle = self._read_throttle_raw()
        return Reading(
            timestamp_utc=datetime.now(timezone.utc),
            sensor_type=SensorType.SYSTEM,
            cpu_temp_celsius=cpu_temp,
            disk_percent=disk_pct,          # new field on Reading
            sync_backlog=backlog,            # new field on Reading
            throttle_flags=throttle,         # new field on Reading
        )
```

Note: `Reading` dataclass will need three new optional fields: `disk_percent: Optional[float]`,
`sync_backlog: Optional[int]`, `throttle_flags: Optional[int]`. The database `readings` table will
need matching columns via a schema migration (v4).

### Pattern 2: Extending `_readings_to_metrics()` for Health Fields

The existing `elif reading.sensor_type.value == "system":` block in `batch_sync.py` only maps
`cpu_temp_celsius`. Three new metrics need to be emitted:

```python
# Source: existing pattern in batch_sync.py _readings_to_metrics()
elif reading.sensor_type.value == "system":
    if reading.cpu_temp_celsius is not None:
        metrics.append(("shitbox_cpu_temp", labels, reading.cpu_temp_celsius, timestamp_ms))
    if reading.disk_percent is not None:
        metrics.append(("shitbox_disk_pct", labels, reading.disk_percent, timestamp_ms))
    if reading.sync_backlog is not None:
        metrics.append(("shitbox_sync_backlog", labels, float(reading.sync_backlog), timestamp_ms))
    if reading.throttle_flags is not None:
        metrics.append(("shitbox_throttle_flags", labels, float(reading.throttle_flags), timestamp_ms))
```

### Pattern 3: SQLite Tables for Trip State

Two new tables, added as a migration to `database.py` at schema version 4:

```sql
-- Single-row key-value store for persisted trip state
CREATE TABLE IF NOT EXISTS trip_state (
    key TEXT PRIMARY KEY,
    value_real REAL,
    value_text TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Append-only log of reached waypoints (idempotent by waypoint_index)
CREATE TABLE IF NOT EXISTS waypoints_reached (
    waypoint_index INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    reached_at TEXT NOT NULL,
    lat_at_reach REAL,
    lon_at_reach REAL
);
```

Keys for `trip_state`: `odometer_km`, `daily_km`, `daily_reset_date` (ISO date string in AEST).

### Pattern 4: YAML Config for Waypoints

Wire under `sensors.gps` to keep route data co-located with GPS config:

```yaml
# config/config.yaml
sensors:
  gps:
    # ... existing fields ...
    route:
      - name: "Port Douglas"
        day: 1
        lat: -16.4838
        lon: 145.4673
      - name: "Townsville"
        day: 1
        lat: -19.2590
        lon: 146.8169
      # ... etc
```

```python
# config.py dataclasses
@dataclass
class WaypointConfig:
    name: str = ""
    day: int = 1
    lat: float = 0.0
    lon: float = 0.0

@dataclass
class RouteConfig:
    waypoints: list = field(default_factory=list)  # list[WaypointConfig]
```

`GPSConfig` gains a `route: RouteConfig` field. `load_config()` processes the list via a simple
list comprehension since `_dict_to_dataclass` handles nested dataclasses but not lists of
dataclasses — this needs explicit handling.

### Pattern 5: AEST Day Boundary Without External Library

Queensland does not observe daylight saving time, so AEST = UTC+10 permanently. The calculation:

```python
AEST_OFFSET = timedelta(hours=10)

def _current_aest_date() -> str:
    """Return current date in AEST as an ISO date string (YYYY-MM-DD)."""
    return (datetime.now(timezone.utc) + AEST_OFFSET).strftime("%Y-%m-%d")
```

Day reset check on boot:
```python
stored_date = db.get_trip_state("daily_reset_date")
today_aest = _current_aest_date()
if stored_date != today_aest:
    db.set_trip_state("daily_km", 0.0)
    db.set_trip_state("daily_reset_date", today_aest)
```

### Pattern 6: In-Memory Accumulation with Periodic Persist

```python
# Inside UnifiedEngine state
self._odometer_km: float = 0.0       # loaded from DB on start
self._daily_km: float = 0.0          # loaded from DB on start
self._last_known_lat: Optional[float] = None
self._last_known_lon: Optional[float] = None
self._last_trip_persist: float = 0.0
TRIP_PERSIST_INTERVAL_S = 60.0

# Inside _record_telemetry() after GPS fix:
if gps_reading and gps_reading.latitude is not None and gps_reading.speed_kmh >= 5.0:
    if self._last_known_lat is not None:
        delta_km = self._haversine_km(
            self._last_known_lat, self._last_known_lon,
            gps_reading.latitude, gps_reading.longitude
        )
        self._odometer_km += delta_km
        self._daily_km += delta_km
    self._last_known_lat = gps_reading.latitude
    self._last_known_lon = gps_reading.longitude

# Persist every 60 seconds
if (now - self._last_trip_persist) >= TRIP_PERSIST_INTERVAL_S:
    self.database.set_trip_state("odometer_km", self._odometer_km)
    self.database.set_trip_state("daily_km", self._daily_km)
    self._last_trip_persist = now
```

### Pattern 7: Waypoint Detection

```python
# Inside _record_telemetry() after GPS update:
if gps_reading and gps_reading.latitude is not None:
    self._check_waypoints(gps_reading.latitude, gps_reading.longitude)

def _check_waypoints(self, lat: float, lon: float) -> None:
    for i, waypoint in enumerate(self.config.route_waypoints):
        if i in self._reached_waypoints:
            continue   # already reached, idempotent
        dist_km = self._haversine_km(lat, lon, waypoint.lat, waypoint.lon)
        if dist_km <= 5.0:
            self._reached_waypoints.add(i)
            self.database.record_waypoint_reached(i, waypoint.name, lat, lon)
            log.info(
                "waypoint_reached",
                name=waypoint.name,
                day=waypoint.day,
                distance_km=round(dist_km, 2),
            )
```

`self._reached_waypoints` is a `set[int]` loaded from DB on boot. `self.config.route_waypoints` is
a `list[WaypointConfig]` populated in `from_yaml_config()`.

### Anti-Patterns to Avoid

- **Independent sysfs temp read in HealthCollector:** The decision is locked — use
  `ThermalMonitorService.current_temp_celsius`. Avoids duplicate reads and conflicting values.
- **Sentinel lat/lon on GPS miss:** When GPS has no fix, skip distance accumulation entirely —
  do not update `_last_known_lat`. A long GPS outage followed by a new fix would produce a single
  huge delta that corrupts the odometer. Only update `_last_known_lat` when there is a valid fix.
- **Speed threshold applied to haversine delta:** Apply the 5 km/h threshold via
  `gps_reading.speed_kmh`, not by checking the haversine delta itself. The GPS-reported speed is
  more reliable for detecting whether the car is moving.
- **Persisting on every GPS fix:** Persist to SQLite only every 60 seconds — writing on every 1 Hz
  GPS fix would add unnecessary write pressure. In-memory accumulation is sufficient; a crash loses
  at most 60 seconds of odometry.
- **Resetting daily distance via a midnight timer:** The locked decision specifies "first boot of a
  new calendar day" — check the stored date against today's AEST date on boot, not on a timer.
- **Handling the waypoint list in `_dict_to_dataclass`:** The generic `_dict_to_dataclass` handles
  nested dataclasses but not lists of dataclasses. The `load_config()` function must handle the
  `route.waypoints` list explicitly with a list comprehension.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Great-circle distance | Custom trig | `UnifiedEngine._haversine_km()` already in codebase | Already tested implicitly; promotes to a module-level or `Database` utility |
| Disk usage | Subprocess `df` | `shutil.disk_usage(path)` | stdlib, accurate, cross-platform |
| Throttle bitmask reading | New sysfs path | `ThermalMonitorService._read_throttled()` | Already implemented in Phase 3; either share via a module-level function or re-read in `HealthCollector` |
| AEST timezone | `pytz` or `zoneinfo` | `datetime + timedelta(hours=10)` | Queensland has no DST; fixed offset is correct and zero-dependency |
| Prometheus encoding | Custom protobuf | `encode_remote_write()` in `prometheus_write.py` | Already used; `HealthCollector` output flows through existing batch sync path |

**Key insight:** The entire Prometheus pipeline, distance formula, and thermal monitoring are
already built. Phase 4 mostly wires new data into existing flows rather than building new
infrastructure.

## Common Pitfalls

### Pitfall 1: GPS Outage Corrupting Odometer

**What goes wrong:** GPS loses fix for 10 minutes then re-acquires. The car may have moved 15 km
during the outage. When the fix returns, `_haversine_km(last_known, current)` produces a 15 km
jump added to the odometer in a single step.

**Why it happens:** `_last_known_lat` is set to the last-fix position, not the current position.
When connectivity returns, the distance between the two positions is accumulated as one step.

**How to avoid:** Only set `_last_known_lat` when moving (speed >= 5 km/h) and only accumulate
distance when the previous position was also valid. Add an optional cap: reject any single step
larger than a reasonable maximum (e.g., 10 km in one 1-second GPS interval is physically
impossible). Log and skip implausible deltas.

**Warning signs:** Odometer jumps by tens of kilometres in a single cycle.

### Pitfall 2: `_dict_to_dataclass` Does Not Handle Lists

**What goes wrong:** The existing `_dict_to_dataclass` recursively converts dicts to nested
dataclasses but does not handle `list[dict]` → `list[WaypointConfig]`. Passing the waypoints list
through it will silently leave it as a raw list of dicts.

**Why it happens:** `hasattr(field_type, "__dataclass_fields__")` checks the field type, but the
type annotation `list` does not have `__dataclass_fields__`. The list items are never converted.

**How to avoid:** Handle the waypoints list explicitly in `load_config()` with:
```python
waypoints=[
    WaypointConfig(**w) for w in route_data.get("waypoints", [])
]
```

**Warning signs:** `waypoint.lat` raises `AttributeError: 'dict' object has no attribute 'lat'`.

### Pitfall 3: Throttle State in HealthCollector

**What goes wrong:** `HealthCollector._read_throttle_raw()` calls `subprocess.run(["vcgencmd",
"get_throttled"])` — on a dev machine (macOS) this raises `FileNotFoundError`. Tests fail if not
mocked.

**Why it happens:** `vcgencmd` is Pi-specific. The same issue was already solved in
`ThermalMonitorService._read_throttled()` which catches `FileNotFoundError` and returns `None`.

**How to avoid:** Use the same try/except pattern. Return `None` when unavailable. Tests use
`patch.object` to inject a specific raw value. Consider extracting `_read_throttled()` as a module-
level function in `health/` shared between `ThermalMonitorService` and `HealthCollector` — or
simply expose the last raw throttle value from `ThermalMonitorService` directly.

**Warning signs:** Test failures with `FileNotFoundError` on non-Pi hosts.

### Pitfall 4: Reading Model Mismatch Between `insert_reading` and Schema

**What goes wrong:** Adding `disk_percent`, `sync_backlog`, and `throttle_flags` to `Reading`
without also adding them to the `INSERT INTO readings` SQL statement and `_row_to_reading()`.
SQLite silently ignores extra Python fields; data is dropped.

**Why it happens:** `Reading` is a dataclass; `insert_reading()` uses positional SQL parameters.
Adding a field to the dataclass without updating the SQL means the field is never written.

**How to avoid:** The schema migration, `SCHEMA_SQL`, `insert_reading()`, `insert_readings_batch()`,
and `_row_to_reading()` must all be updated atomically in the same task. Increment `SCHEMA_VERSION`
to 4 and add `ALTER TABLE readings ADD COLUMN` for each new field.

**Warning signs:** `reading.disk_percent` is set but `SELECT disk_percent FROM readings` returns
NULL for all rows.

### Pitfall 5: Waypoint Reached Set Not Thread-Safe

**What goes wrong:** `self._reached_waypoints` (a `set[int]`) is read in `_check_waypoints()` on
the telemetry thread. If another component reads it concurrently, a `RuntimeError: Set changed size
during iteration` can occur.

**Why it happens:** Python sets are not thread-safe for concurrent mutation and iteration.

**How to avoid:** `_check_waypoints()` runs only on the telemetry thread (single writer). Reads by
other subsystems (e.g., OLED display or TTS in Phase 5) should copy the set under a lock. Keep the
set as telemetry-thread-private state and expose a `get_current_stage()` method that returns a
snapshot value rather than the raw set.

**Warning signs:** `RuntimeError: Set changed size during iteration` in logs.

## Code Examples

### Reading Disk Usage

```python
# Source: Python stdlib shutil docs — verified against Python 3.9+
import shutil
disk = shutil.disk_usage("/var/lib/shitbox")
disk_pct = (disk.used / disk.total) * 100.0
# disk.total, disk.used, disk.free are all in bytes
```

### AEST Date String (No External Dependency)

```python
# Source: Python stdlib datetime — verified
from datetime import datetime, timezone, timedelta

AEST_OFFSET = timedelta(hours=10)

def _current_aest_date() -> str:
    return (datetime.now(timezone.utc) + AEST_OFFSET).strftime("%Y-%m-%d")
```

### SQLite trip_state Get/Set

```python
# Source: existing database.py pattern adapted for key-value store
def get_trip_state(self, key: str) -> Optional[float]:
    conn = self._get_connection()
    row = conn.execute(
        "SELECT value_real FROM trip_state WHERE key = ?", (key,)
    ).fetchone()
    return row["value_real"] if row else None

def set_trip_state(self, key: str, value: float) -> None:
    conn = self._get_connection()
    with self._write_lock:
        conn.execute(
            """
            INSERT INTO trip_state (key, value_real, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value_real = excluded.value_real,
                updated_at = datetime('now')
            """,
            (key, value),
        )
        conn.commit()
```

### Schema Migration v4

```python
# In database.py — follow existing _migrate_to_v2 / _migrate_to_v3 pattern
def _migrate_to_v4(self, conn: sqlite3.Connection) -> None:
    """Add health metrics columns and trip tracking tables."""
    new_columns = [
        ("disk_percent", "REAL"),
        ("sync_backlog", "INTEGER"),
        ("throttle_flags", "INTEGER"),
    ]
    for col_name, col_type in new_columns:
        try:
            conn.execute(f"ALTER TABLE readings ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trip_state (
            key TEXT PRIMARY KEY,
            value_real REAL,
            value_text TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS waypoints_reached (
            waypoint_index INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            reached_at TEXT NOT NULL,
            lat_at_reach REAL,
            lon_at_reach REAL
        );
    """)
    conn.commit()
    log.info("migrated_to_v4")
```

### EngineConfig Route Wiring

```python
# In EngineConfig (flat fields, per project pattern)
route_waypoints: list = field(default_factory=list)  # list[WaypointConfig]

# In from_yaml_config():
route_waypoints=config.sensors.gps.route.waypoints,
```

### Prometheus Metric Names (HLTH-01)

Following the existing `shitbox_` prefix convention:

| Field | Metric Name | Type |
|-------|-------------|------|
| CPU temp | `shitbox_cpu_temp` | gauge (already exists) |
| Disk % | `shitbox_disk_pct` | gauge |
| Sync backlog | `shitbox_sync_backlog` | gauge |
| Throttle flags | `shitbox_throttle_flags` | gauge (bitmask as float) |

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| `rally_start_lat` / `rally_destination_lat` in GPSConfig | Waypoint list in `route.waypoints` | The current config has point-to-point coordinates only; replacing with an ordered list of waypoints is the Phase 4 change |
| `_distance_from_start_km` computed as haversine from fixed start | Cumulative GPS odometer | The haversine-from-start approach doesn't handle detours or non-straight routes; the odometer accumulates actual distance driven |
| `_read_system_status()` writes only `cpu_temp_celsius` | `HealthCollector` adds disk %, backlog, throttle | Extends the existing `SensorType.SYSTEM` path |

**Deprecated/outdated:**

- `rally_start_lat`, `rally_start_lon`, `rally_destination_lat`, `rally_destination_lon` in
  `GPSConfig` and `EngineConfig` — these are superseded by the waypoints list. They should remain
  in the dataclass for backwards compatibility (they will be unused after Phase 4) or be removed
  from `EngineConfig.from_yaml_config()` — leave this decision to the planner.

## Open Questions

1. **Should `HealthCollector` read throttle state directly or consume it from `ThermalMonitorService`?**
   - What we know: `ThermalMonitorService` already reads `vcgencmd get_throttled` every 5 seconds
     and stores the last raw value in `_last_throttled_raw`. However, `_last_throttled_raw` is a
     private attribute with no public accessor.
   - What's unclear: Whether to expose `last_throttled_raw` on `ThermalMonitorService` or have
     `HealthCollector` do its own `subprocess.run` call.
   - Recommendation: Expose `last_throttled_raw: Optional[int]` as a property on
     `ThermalMonitorService` (consistent with `current_temp_celsius`). This avoids a second
     `vcgencmd` subprocess call every second and keeps thermal state as a single source of truth.

2. **What happens to `_distance_from_start_km` and `_distance_to_destination_km` in engine state?**
   - What we know: These are set in `_record_telemetry()` and used in `_on_event()` and
     `_update_overlay()`. They compute haversine from fixed start/end coordinates.
   - What's unclear: Whether Phase 4 replaces them with odometer/stage values or leaves them
     alongside.
   - Recommendation: Keep them for backwards compatibility with the overlay and event metadata.
     Add `_odometer_km` and `_daily_km` as new parallel fields. The planner can decide whether to
     retire the old fields later.

3. **`WaypointConfig` list type annotation for mypy compatibility with Python 3.9**
   - What we know: Python 3.9 supports `list[WaypointConfig]` in annotations when using
     `from __future__ import annotations`, but `dataclass` field type resolution at runtime may
     differ.
   - Recommendation: Use `field(default_factory=list)` with a comment noting the expected type,
     or use `from typing import List` for the type hint. Both are already used in the codebase.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` if needed, currently using defaults) |
| Quick run command | `pytest tests/test_health_collector.py tests/test_trip_tracking.py -x -q` |
| Full suite command | `pytest --cov=shitbox` |
| Estimated runtime | ~1 second (existing 52 tests run in 0.52 s) |

### Phase Requirements → Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| HLTH-01 | `HealthCollector.collect()` returns a `Reading` with all four health fields populated | unit | `pytest tests/test_health_collector.py -x` | Wave 0 gap |
| HLTH-01 | `batch_sync._readings_to_metrics()` emits `shitbox_disk_pct`, `shitbox_sync_backlog`, `shitbox_throttle_flags` for a system reading | unit | `pytest tests/test_health_collector.py::test_health_metrics_in_prometheus -x` | Wave 0 gap |
| HLTH-01 | `HealthCollector` returns `None` CPU temp gracefully when `ThermalMonitorService` has not read yet | unit | `pytest tests/test_health_collector.py::test_health_collector_no_temp -x` | Wave 0 gap |
| STGE-01 | Odometer accumulates distance when speed >= 5 km/h | unit | `pytest tests/test_trip_tracking.py::test_odometer_accumulates -x` | Wave 0 gap |
| STGE-01 | Odometer does NOT accumulate when speed < 5 km/h | unit | `pytest tests/test_trip_tracking.py::test_odometer_skips_slow -x` | Wave 0 gap |
| STGE-01 | Odometer persists to SQLite every 60 s and survives reboot (loaded on boot) | unit | `pytest tests/test_trip_tracking.py::test_odometer_persists -x` | Wave 0 gap |
| STGE-02 | Daily distance resets on first access of a new AEST day | unit | `pytest tests/test_trip_tracking.py::test_daily_reset_new_day -x` | Wave 0 gap |
| STGE-02 | Daily distance persists across mid-day reboots | unit | `pytest tests/test_trip_tracking.py::test_daily_persists_same_day -x` | Wave 0 gap |
| STGE-03 | Waypoint within 5 km is marked as reached and persisted | unit | `pytest tests/test_trip_tracking.py::test_waypoint_reached -x` | Wave 0 gap |
| STGE-03 | Waypoint > 5 km away is not marked as reached | unit | `pytest tests/test_trip_tracking.py::test_waypoint_not_reached -x` | Wave 0 gap |
| STGE-03 | Reached waypoints survive a reboot (loaded from SQLite) | unit | `pytest tests/test_trip_tracking.py::test_waypoints_loaded_on_boot -x` | Wave 0 gap |
| STGE-03 | `get_current_stage()` returns correct day label from waypoint day numbers | unit | `pytest tests/test_trip_tracking.py::test_stage_label -x` | Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run:
  `pytest tests/test_health_collector.py tests/test_trip_tracking.py -x -q`
- **Full suite trigger:** Before merging final task of any plan wave: `pytest --cov=shitbox`
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~1-2 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_health_collector.py` — covers HLTH-01 (health metrics collection and Prometheus
  emission)
- [ ] `tests/test_trip_tracking.py` — covers STGE-01, STGE-02, STGE-03 (odometer, daily distance,
  waypoint detection)
- [ ] No new conftest fixtures required — existing `db` fixture from `tests/conftest.py` is
  sufficient for database tests

## Sources

### Primary (HIGH confidence)

- Codebase: `/Users/tgreen/dev/shitbox/src/shitbox/events/engine.py` — `_haversine_km()`,
  `_record_telemetry()`, `EngineConfig`, `from_yaml_config()`, `get_status()`
- Codebase: `/Users/tgreen/dev/shitbox/src/shitbox/sync/batch_sync.py` — `_readings_to_metrics()`,
  `get_backlog_count()`
- Codebase: `/Users/tgreen/dev/shitbox/src/shitbox/storage/database.py` — migration pattern,
  `transaction()`, schema version management, `_write_lock` pattern
- Codebase: `/Users/tgreen/dev/shitbox/src/shitbox/health/thermal_monitor.py` — `_read_throttled()`
  pattern, `current_temp_celsius` property pattern
- Codebase: `/Users/tgreen/dev/shitbox/src/shitbox/storage/models.py` — `Reading` dataclass,
  `SensorType.SYSTEM`
- Codebase: `/Users/tgreen/dev/shitbox/src/shitbox/utils/config.py` — `_dict_to_dataclass`,
  `load_config()`, existing dataclass hierarchy
- Codebase: `tests/test_thermal_monitor.py` — `patch.object` pattern for instance method mocking
- Python stdlib docs: `shutil.disk_usage` — confirmed returns `(total, used, free)` namedtuple in
  bytes; available Python 3.3+

### Secondary (MEDIUM confidence)

- Python stdlib docs: `datetime.timedelta` + `timezone.utc` for fixed-offset timezone arithmetic —
  AEST (UTC+10, no DST in Queensland) confirmed via standard timezone references

### Tertiary (LOW confidence)

- None

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all libraries are stdlib or already in pyproject.toml; no new dependencies
- Architecture: HIGH — patterns traced directly from existing codebase; no guesswork
- Pitfalls: HIGH — derived from direct code inspection of the GPS loop, migration pattern, and
  threading model

**Research date:** 2026-02-27
**Valid until:** 2026-04-27 (stable stdlib patterns; project-specific decisions locked in CONTEXT.md)
