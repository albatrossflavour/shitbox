# Architecture Research

**Domain:** Rally car telemetry — v2.0 feature integration (field logging, driver tracking, display, calibration, health)
**Researched:** 2026-04-09
**Confidence:** HIGH (based on direct codebase inspection; all integration points verified against source)

## Existing Architecture Baseline

The system runs as a single `UnifiedEngine` daemon managing:

- **High-rate path (100 Hz):** LSM6DSOX IMU → ring buffer → event detector → event storage + video capture
- **Low-rate path (1 Hz):** GPS/IMU/temp/power/light collectors → SQLite → Prometheus batch sync
- **Capture path:** GPIO button → ffmpeg subprocess wrapper
- **Dashboard path (in-process):** FastAPI + three SSE streams on a daemon thread (uvicorn), reads from shared `snapshot` dict

SQLite at `/var/lib/shitbox/telemetry.db` is schema version 5. Thread-safety via `_write_lock` + thread-local connections. `CaptureSyncService` rsyncs `/var/lib/shitbox/captures/` to NAS in two passes (media first, index files second).

## System Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              UnifiedEngine                                    │
│                                                                               │
│  [High-rate path]      [Low-rate path]         [Capture path]                 │
│  LSM6DSOX (100 Hz) ─→  GPS/Temp/Light/Power ─→  Button ─→ ffmpeg            │
│  RingBuffer        ─→  SQLite (telemetry.db)                                  │
│  EventDetector     ─→  BatchSync ─→ Prometheus                               │
│  EventStorage      ─→                                                         │
│                                                                               │
│  [Dashboard path — in-process FastAPI]                                        │
│  DashboardServer (uvicorn, daemon thread)                                     │
│    /sse/fast, /sse/slow, /sse/events                                          │
│    /tiles/{z}/{x}/{y}  (MBTiles offline map)                                  │
│    /static/index.html  (Alpine + Tailwind + Leaflet)                          │
│                                                                               │
│  [NEW v2.0: logbook subsystem]                                                │
│  FieldNotesRouter  ─→ SQLite (same DB, new tables)                           │
│  RefuelRouter      ─→ SQLite (same DB, new tables)                           │
│  DriverRouter      ─→ SQLite (same DB, new tables)                           │
│                                                                               │
│  [NEW v2.0: calibration]                                                      │
│  CalibrationRouter ─→ SQLite calibration table                               │
│    applied at: HighRateSampler (accel offsets)                                │
│                DS18B20Collector (temp offsets)                                │
│                                                                               │
│  [NEW v2.0: health/monitoring]                                                │
│  HealthCollector ─→ throttle_flags (already in readings schema)               │
│  ThermalMonitor.last_throttled_raw ─→ HealthCollector (already wired)        │
│                                                                               │
└──────────────────────┬────────────────────────────────────────────────────────┘
                       │ rsync (CaptureSyncService — extended)
                       ▼
            /var/lib/shitbox/captures/
              events.json          (existing)
              timelapse.json       (existing)
              blog.json            (NEW — field notes)
              refuel.json          (NEW — refuel log)
              driver-stats.json    (NEW — driver time percentages)
                       │
                       │ rsync over WireGuard → NAS → website
                       ▼
            shit-of-theseus.com (reads JSON from /captures/)
```

## Integration Points

### SQLite: Same DB, New Tables

All new logbook data (field notes, refuel, driver sessions) goes into the **existing** `telemetry.db`. The case for this is straightforward:

- Single WAL, single lock, single connection pool — no inter-DB synchronisation needed
- `CaptureSyncService` generates JSON exports; the DB is never read directly from outside the Pi
- Migration pattern already established (version-gated `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS`)
- Calibration data also lives here as a lookup table, loaded at collector init

The case against separate DBs: none compelling at this scale. Separate files would only make sense if the logbook needed independent backup or schema versioning from telemetry, which it does not.

**Schema additions (migration v6):**

```sql
-- Field notes / blog posts
CREATE TABLE IF NOT EXISTS field_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    body TEXT NOT NULL,
    lat REAL,
    lng REAL,
    speed_kmh REAL,
    event_id TEXT,          -- optional FK to an event JSON filename
    created_at TEXT DEFAULT (datetime('now'))
);

-- Refueling log
CREATE TABLE IF NOT EXISTS refuel_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    volume_litres REAL NOT NULL,
    odometer_km REAL,       -- from trip_state.odometer at time of entry
    lat REAL,
    lng REAL,
    station_name TEXT,      -- freeform, optional
    cost_aud REAL,          -- optional
    created_at TEXT DEFAULT (datetime('now'))
);

-- Driver sessions
CREATE TABLE IF NOT EXISTS driver_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,          -- NULL = currently driving
    odometer_start_km REAL,
    odometer_end_km REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Sensor calibration offsets
CREATE TABLE IF NOT EXISTS calibration (
    sensor TEXT NOT NULL,   -- e.g. 'accel', 'ds18b20_engine', 'ds18b20_cabin'
    axis TEXT,              -- 'x', 'y', 'z' for IMU; NULL for scalar sensors
    offset REAL NOT NULL DEFAULT 0.0,
    scale REAL NOT NULL DEFAULT 1.0,
    calibrated_at TEXT,
    notes TEXT,
    PRIMARY KEY (sensor, axis)
);

CREATE INDEX IF NOT EXISTS idx_field_notes_timestamp ON field_notes(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_refuel_log_timestamp ON refuel_log(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_started ON driver_sessions(started_at);
```

The `driver_sessions` table uses an open `ended_at` to track the active driver — the current driver is `WHERE ended_at IS NULL LIMIT 1`. Closing a session is a single UPDATE. This is simpler than a separate "current driver" key in `trip_state`.

### FastAPI: New Routers on the Existing App

The existing `build_app()` factory in `dashboard/server.py` accepts routers via `app.include_router()`. The correct approach is to add new routers following the same `APIRouter` pattern as `sse.py` and `tiles.py`, then include them in `build_app()`.

The display routes (DISP-01), logbook routes (NOTE-01, FUEL-01, DRVR-01), and calibration routes (CAL-01) are all REST endpoints, not streaming. They do not touch the SSE machinery or the capture path. The only coupling concern is the `_write_lock` on the database, which all writes already go through.

**Router structure:**

```
src/shitbox/dashboard/
    server.py           (modified — include new routers in build_app)
    sse.py              (unchanged)
    tiles.py            (unchanged)
    snapshot.py         (extended — add driver + health fields)
    logbook.py          (NEW — field notes, refuel, driver REST endpoints)
    calibration.py      (NEW — calibration read/write endpoints)
```

Pass `db: Database` to `build_app()` so the new routers can write to SQLite. Currently `build_app()` takes only `mbtiles_path` and `recent_events_provider`. Add `db` as an optional parameter (can be None for tests that don't exercise logbook routes).

**Existing SSE streams are unaffected** — new REST routes run on the same uvicorn event loop but are non-streaming and fast. There is no per-request blocking I/O that would stall SSE generators, because all DB writes go through `_write_lock` which is short-lived at 1 Hz telemetry rates.

**Driver state in SSE slow stream:** Add `active_driver` to the snapshot dict published by `update_snapshot()`. The `/sse/slow` stream already includes this dict. The engine's low-rate tick reads the active driver from SQLite once per second (one `SELECT WHERE ended_at IS NULL` — negligible cost) and writes it to the snapshot.

### CaptureSyncService: Export New JSON Files

The existing `_do_sync_inner()` pattern is:

1. Call `event_storage.generate_events_json()` to regenerate `events.json`
2. Call `timelapse_compiler.generate_timelapse_json()` to regenerate `timelapse.json`
3. rsync media (excluding index files)
4. rsync index files

Extend this by adding generator callables for the new JSON exports. The cleanest approach is a list of registered generator callables rather than hardcoding each:

```python
class CaptureSyncService:
    def register_json_generator(self, name: str, fn: Callable[[], None]) -> None:
        """Register a function that regenerates a JSON index file before each sync."""
        self._json_generators[name] = fn
```

Then `_do_sync_inner()` iterates `self._json_generators.values()` before the rsync calls. The engine wires up `blog.json`, `refuel.json`, and `driver-stats.json` generators alongside the existing `events.json` and `timelapse.json` registrations.

Each generator function queries the relevant SQLite table and writes a JSON file to `captures_dir/`:

```
captures/
    events.json          (EventStorage.generate_events_json — existing)
    timelapse.json       (TimelapseCompiler.generate_timelapse_json — existing)
    blog.json            (LogbookExporter.generate_blog_json — NEW)
    refuel.json          (LogbookExporter.generate_refuel_json — NEW)
    driver-stats.json    (LogbookExporter.generate_driver_stats_json — NEW)
```

The two-pass rsync (media first, then index files) already handles the ordering correctly — all JSON files are excluded from pass 1, synced in pass 2.

### Sensor Calibration: SQLite Table, Applied at Collection Time

The existing `accel_offset_x/y/z` fields in `EngineConfig` are static config. That is correct for boot-time offsets that do not change during a run, but calibration needs to be:

- Writable from the dashboard (without redeploying config)
- Persistent across reboots
- Applied before values reach SQLite (not as a post-processing step on export)

**Decision: SQLite `calibration` table, loaded at collector `__init__`, reloadable via API.**

At `HighRateSampler.__init__()`, read accel offsets from `calibration` table (falling back to `EngineConfig` defaults if the table has no rows for `sensor='accel'`). The `CalibrationRouter` POST endpoint writes to the table and calls a reload method on the sampler. Temperature offsets (`ds18b20_engine`, `ds18b20_cabin`) are loaded the same way by `DS18B20Collector`.

This avoids modifying `config.yaml` from runtime code (bad pattern — file writes to config are fragile). It also keeps the calibration audit trail (the `calibrated_at` and `notes` fields).

**Config.yaml `accel_offset_*` fields remain** as the factory-default fallback. If the calibration table has no entry for a sensor, the config value is used. This preserves backwards compatibility.

### Undervoltage: HealthCollector Already Has It

`ThermalMonitor` already calls `vcgencmd get_throttled` and stores the raw bitmask in `last_throttled_raw`. `HealthCollector.collect()` already reads this and writes it to `throttle_flags` in the `readings` table (SensorType.SYSTEM rows).

The bitmask is:

| Bit | Meaning |
|-----|---------|
| 0 | Under-voltage detected |
| 1 | Arm frequency capped |
| 2 | Currently throttled |
| 3 | Soft temperature limit active |
| 16 | Under-voltage has occurred (since boot) |
| 17 | Arm frequency capping has occurred (since boot) |
| 18 | Throttling has occurred (since boot) |
| 19 | Soft temperature limit has occurred (since boot) |

What is missing is the **alert path**. `ThermalMonitor` has `speak_under_voltage()` and `beep_under_voltage()` already imported and presumably called from somewhere in the thermal loop, but that needs confirming. The monitoring gap (MON-01) is:

1. `throttle_flags` is written to SQLite but not confirmed to reach Prometheus (HLTH-01)
2. No undervoltage alert surfaced on the dashboard SSE slow stream
3. Prometheus scrape label conflict needs investigation separately

**Recommended additions for PWR-01/MON-01:**

- Add `throttle_flags` decode to the dashboard snapshot: parse bit 0 of the last SYSTEM reading's `throttle_flags` and add `undervoltage: bool` to the slow SSE payload
- Confirm `BatchSyncService` is syncing SYSTEM sensor type rows (check Prometheus query)
- No new monitor needed — the existing `ThermalMonitor` + `HealthCollector` + `BatchSync` chain is correct; the gap is in wiring + confirmation, not architecture

### Driver Display: Extending the Existing FastAPI App

The existing display is Chromium in kiosk mode pointing at `localhost:8080`. It already receives:

- `/sse/fast` — 10 Hz: speed, G-force XYZ, heading
- `/sse/slow` — 1 Hz: GPS fix, temps, sync state, event count
- `/sse/events` — live event ticker

For DISP-01 (productionise the 7" touchscreen display), the work is in `dashboard/static/index.html` and expanding the snapshot dict. The SSE transport is already there. What changes:

- `update_snapshot()` gets additional fields: `active_driver`, `undervoltage`, `daily_distance_km`, `total_distance_km`
- `/sse/slow` payload includes these new fields (backwards compatible — clients ignore unknown keys)
- The HTML/JS gets a dedicated driver display layout (full-screen for the 7" kiosk, vs responsive layout for phones)

No new server-side routes needed purely for display. The calibration and logbook REST routes are separate concerns.

## Data Flow

### Logbook write flow (field note example)

```
Touchscreen (kiosk, 127.0.0.1:8080)
    POST /api/notes  {body: "...", event_id: "..."}
         │
    FastAPI logbook router
         │
    db.transaction() → INSERT INTO field_notes
         │
    200 OK {id: N}
         │
    (at next CaptureSyncService tick)
         │
    LogbookExporter.generate_blog_json()
    → writes captures/blog.json
         │
    rsync to NAS
         │
    shit-of-theseus.com reads /captures/blog.json
```

### Driver session flow

```
Driver A presses "I'm driving" on touchscreen
    POST /api/drivers/session/start  {name: "Alice"}
         │
    UPDATE driver_sessions SET ended_at=now() WHERE ended_at IS NULL
    INSERT INTO driver_sessions (driver_name, started_at, odometer_start_km)
         │
    update_snapshot() reads active driver at next 1 Hz tick
         │
    /sse/slow includes active_driver: "Alice"
         │
    (at sync) generate_driver_stats_json() aggregates time/distance per driver
    → captures/driver-stats.json
```

### Calibration flow

```
Technician enters calibration values on touchscreen
    POST /api/calibration  {sensor: "accel", axis: "x", offset: -0.03}
         │
    db.transaction() → UPSERT calibration table
         │
    HighRateSampler.reload_calibration() reads new values
         │
    Applied on next IMU sample cycle (no restart needed)
```

### CaptureSyncService extended flow

```
CaptureSyncService._do_sync_inner():
    for name, fn in self._json_generators.items():
        fn()  ← events.json, timelapse.json, blog.json, refuel.json, driver-stats.json

    rsync pass 1: media (--exclude=*.json)
    rsync pass 2: all (includes *.json)
```

## Component Boundaries

| Component | Responsibility | Modified / New |
|-----------|---------------|----------------|
| `UnifiedEngine` | Orchestrates all paths; wires new routers + generators into existing services | Modified (wire-up only) |
| `database.py` | SQLite schema + migrations; gains v6 migration with 4 new tables | Modified |
| `dashboard/server.py` | `build_app()` gains `db` param; includes `logbook` + `calibration` routers | Modified |
| `dashboard/logbook.py` | REST CRUD for field notes, refuel log, driver sessions | New |
| `dashboard/calibration.py` | REST read/write for calibration offsets; triggers sampler reload | New |
| `dashboard/snapshot.py` | `update_snapshot()` gains `active_driver`, `undervoltage`, distance fields | Modified |
| `dashboard/sse.py` | `/sse/slow` payload extended (backwards compatible — client ignores new keys) | Unchanged (payload extended in snapshot) |
| `sync/capture_sync.py` | `register_json_generator()` method; `_do_sync_inner()` iterates generators | Modified |
| `sync/logbook_exporter.py` | Queries DB → writes `blog.json`, `refuel.json`, `driver-stats.json` | New |
| `events/sampler.py` | `reload_calibration()` method; reads calibration table at init | Modified |
| `collectors/temperature.py` | Reads calibration table for DS18B20 offsets at init | Modified |
| `health/health_collector.py` | Existing — no change needed; `throttle_flags` already captured | Unchanged |
| `health/thermal_monitor.py` | Existing — confirm `speak_under_voltage()` is called on bit 0 detection | Verify only |

## Recommended Build Order

Dependencies between features determine sequencing. Each step should leave the system deployable and testable.

1. **Schema migration v6** — No dependencies. Add all four new tables in one migration. Harmless on existing data. This unblocks everything else. (`database.py` only)

2. **CaptureSyncService: register_json_generator pattern** — No new features required. Refactor existing hardcoded generator calls to use the registry. Write a stub `LogbookExporter` that generates empty JSON files. This proves the sync pipeline before any data exists. (`capture_sync.py`, `logbook_exporter.py` stub)

3. **Logbook REST API (NOTE-01, FUEL-01, DRVR-01)** — Depends on schema. Add `logbook.py` router, wire into `build_app()` with `db` param, register JSON generators in engine. Field notes, refuel, and driver sessions can ship together — they share the same router file and export pattern. Wire `active_driver` into snapshot + `/sse/slow` at this step.

4. **Calibration (CAL-01)** — Depends on schema. Add `calibration.py` router. Modify `HighRateSampler` and `DS18B20Collector` to load from calibration table with config fallback. Wire reload callback. This is self-contained once the schema exists.

5. **Driver display productionisation (DISP-01)** — Depends on step 3 (active driver in snapshot) and step 4 (calibration available). Work is primarily frontend (`static/index.html`): full-screen layout for 7" touchscreen, touch-friendly logbook entry UI, driver swap button. No new backend routes needed beyond what step 3 provides.

6. **Undervoltage + monitoring (PWR-01, MON-01)** — Depends on nothing new architecturally. Verify `throttle_flags` reaching Prometheus. Add `undervoltage` decode to snapshot. Fix Prometheus scrape label conflict (separate investigation). Surface undervoltage on dashboard.

7. **Website revamp (WEB-01)** — Depends on step 2 (JSON files being synced). Update `shit-of-theseus.com` to read `blog.json`, `refuel.json`, `driver-stats.json`. Frontend work in separate repo. Can happen in parallel with steps 4-6.

**Rationale for this order:** Schema migration first because everything else blocks on it. Sync pipeline second because the website depends on it and it has zero feature risk. Logbook API third because driver display depends on active driver state. Calibration fourth because it touches the hot path (sampler) and should be validated before the display is relied upon for rally day. Display fifth because it is primarily UI work and all its data sources exist by then. Monitoring sixth because it is largely verification work. Website last because it is a separate repo with no Pi deployment complexity.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Separate SQLite databases per feature

Adding a `logbook.db` alongside `telemetry.db` splits the write lock, requires two WAL configurations, and complicates the backup story. The existing DB handles concurrent reads cleanly. Add tables to the existing DB.

### Anti-Pattern 2: Writing calibration offsets to config.yaml at runtime

Config files should not be written by the running daemon. It creates a race with the systemd unit file and makes the config the source of truth for runtime state that should live in the DB. Use the calibration table; read config values only as defaults on first boot.

### Anti-Pattern 3: Blocking CaptureSyncService on logbook export

`generate_blog_json()` is a DB read + file write. If it is slow (large dataset), it delays the rsync. Keep the export functions simple: `SELECT * FROM field_notes ORDER BY timestamp_utc` into a JSON array. For a multi-week rally (< 500 notes) this is sub-millisecond. Do not add pagination or streaming — unnecessary at this scale.

### Anti-Pattern 4: A separate `logbook` FastAPI app or process

Everything already runs in-process on the uvicorn event loop. Adding a separate Flask app or process for logbook REST would require CORS configuration, process supervision, port management, and adds latency. Add routers to the existing FastAPI app.

### Anti-Pattern 5: Reloading calibration via config.yaml reload

Calibration changes need to take effect without a service restart (you do not want to restart the daemon while driving). The calibration table + `reload_calibration()` pattern achieves this. A SIGHUP config reload would work but couples calibration changes to the full config reload path unnecessarily.

### Anti-Pattern 6: Driver attribution via event tag at write time

Tagging events with the active driver at the moment of detection (writing `driver_name` into the event JSON) creates coupling between the event detector and the driver session state. Instead, derive driver attribution at export time: `driver_stats.json` is generated by joining `driver_sessions` against event timestamps. Events remain driver-agnostic.

## Sources

- Codebase direct inspection: `src/shitbox/` — HIGH confidence (first-hand source read)
- SQLite `CREATE TABLE IF NOT EXISTS` + versioned migration pattern: `storage/database.py` — HIGH confidence
- `CaptureSyncService` two-pass rsync pattern: `sync/capture_sync.py` — HIGH confidence
- FastAPI `include_router` pattern: `dashboard/server.py` — HIGH confidence
- Pi 5 vcgencmd throttle bitmask: [Raspberry Pi documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#get_throttled) — HIGH confidence

---

*Architecture research for: shitbox v2.0 feature integration*
*Researched: 2026-04-09*
