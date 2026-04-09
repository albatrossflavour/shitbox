# Phase 12: Schema Foundation and Logbook API - Research

**Researched:** 2026-04-09
**Domain:** SQLite schema migration, FastAPI REST endpoints, Alpine.js modal UI, sync pipeline extension
**Confidence:** HIGH

## Summary

Phase 12 adds two new SQLite tables (`notes`, `fuel_stops`), two REST endpoints, modal UI forms on
the existing dashboard, and a JSON generator registry on `CaptureSyncService`. The codebase already
has every pattern this phase needs: the schema migration system in `database.py`, the
`build_app()` / router-inclusion pattern in `server.py`, the Alpine.js + Tailwind SPA in
`index.html`, and the two-pass rsync pattern in `capture_sync.py`. There is no new runtime
service — the logbook is REST-only, stateless, and no new daemon thread is required.

The main design decisions are already locked in CONTEXT.md. Research validates that all locked
choices map cleanly onto existing code: the `_migrate()` chain slots in a v6 block, the router
inclusion follows the same pattern as `make_tiles_router`, and the `_do_sync_inner()` extension
is a straightforward pre-rsync loop over registered callables. The GPS snapshot contract
(`lat`, `lng`, `gps_fix_mode` in `read_snapshot()`) already provides everything needed for
auto-capture, with no new infrastructure.

The fuel efficiency calculation (km/L at query time from odometer difference / volume) requires
the most careful thought. There is currently no GPS distance accumulator surfaced for this purpose.
The `trip_state` key-value table already exists and could carry an odometer value, but whether it
is populated depends on Phase 11 work. The safe default is to return `null` for efficiency when
odometer is unavailable, and document that clearly in the API response.

**Primary recommendation:** Build in waves: schema migration first, then storage classes, then
REST endpoints, then sync generators, then UI modals. Each wave is independently testable.

---

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Notes and fuel stop forms are modal overlays on the existing dashboard
  (`dashboard/static/index.html`). No new route, no tab bar. Live telemetry stays up behind.
- **D-02:** Modals triggered by `+ Note` and `+ Fuel` buttons in the dashboard UI. No keyboard
  shortcuts in this phase.
- **D-03:** Entry UI requires the existing USB keyboard/trackpad setup. On-screen keyboard
  (simple-keyboard) deferred.
- **D-04:** GPS position taken from `read_snapshot()` — lock-free snapshot already exposes `lat`,
  `lng`, and `gps_fix_mode`.
- **D-05:** If no current GPS fix, use last-known position. Do not block. Do not save null.
- **D-06:** When position is stale, modal shows warning: "Location from X minutes ago". Staleness
  stored as `gps_stale: bool` flag on the record.
- **D-07:** "Last known position" maintained by engine or lightweight helper — updated whenever GPS
  fix received, never cleared.
- **D-08:** `CaptureSyncService` gains `register_json_generator(name, fn)` method. Generators are
  callables producing a JSON-serialisable dict/list. Registered at engine startup.
- **D-09:** Generator output written to `{captures_dir}/{name}.json` before rsync. Partial failure
  is caught and logged — must not abort rsync of other files.
- **D-10:** Fuel cost is hard-excluded from all sync payloads. `generate_fuel_json()` explicitly
  drops the cost field. Enforced in code, not by convention.
- **D-11:** Schema migrates to v6. Two new tables:
  - `notes (id, timestamp_utc, body TEXT, event_id INTEGER NULLABLE, lat REAL NULLABLE, lng REAL NULLABLE, gps_stale BOOLEAN, created_at)`
  - `fuel_stops (id, timestamp_utc, volume_litres REAL, cost_aud REAL, lat REAL NULLABLE, lng REAL NULLABLE, gps_stale BOOLEAN, odometer_km REAL NULLABLE, created_at)`
- **D-12:** Fuel efficiency (km/L) calculated at query time (distance since last stop / volume),
  not stored as a column.

### Claude's Discretion

- REST endpoint design (URL structure, response shape, error codes) — standard FastAPI patterns
- New router location (suggest `src/shitbox/dashboard/logbook.py`, included via `build_app()`)
- Odometer source for fuel efficiency — use GPS distance accumulator from trip_state if available,
  else null
- Modal HTML/CSS/JS design — consistent with existing Alpine.js + Tailwind patterns in
  `dashboard/static/index.html`

### Deferred Ideas (OUT OF SCOPE)

- simple-keyboard (on-screen keyboard) — deferred to Phase 17
- Temperature sensors missing from SSE stream — belongs in Phase 15
- Driver field on notes/fuel — Phase 13 adds driver tracking; can back-fill via driver_stints
- Note categories/tags — freeform text sufficient
- Fuel stop history view in dashboard — display on website is Phase 18

</user_constraints>

---

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NOTE-01 | User can compose a field note from the Pi UI using a keyboard, with DTS and GPS location auto-captured | Alpine modal + POST `/api/notes` + snapshot GPS |
| NOTE-02 | User can optionally pin a field note to an existing event | `event_id NULLABLE` column in `notes` table; event select in modal populated from SSE events array |
| FUEL-01 | User can log a fuel stop with volume and location from the Pi UI | Alpine modal + POST `/api/fuel` + snapshot GPS |
| FUEL-02 | System calculates and tracks fuel efficiency (km/L) per stop and as a running cumulative average | Query-time calculation from ordered `fuel_stops`; trip_state odometer if available |

</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.115 (already in pyproject.toml) | REST endpoints | Already used for dashboard server |
| sqlite3 | stdlib | Database | Already the project's storage layer |
| structlog | >=24.0.0 (already installed) | Logging | Project convention throughout |
| Alpine.js | CDN (vendor'd in static/vendor/) | Reactive modal UI | Already in use in index.html |
| Tailwind CSS | CDN (vendor'd in static/vendor/) | Styling | Already in use |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic (via FastAPI) | bundled with FastAPI | Request body validation | `POST /api/notes` and `POST /api/fuel` request models |
| pytest | >=9.0.2 (confirmed installed) | Testing | All new unit tests |
| httpx / starlette TestClient | bundled with FastAPI dev dependencies | API endpoint testing | Testing REST endpoints without uvicorn |

No new dependencies required. Everything is already installed.

**Installation:** None needed.

---

## Architecture Patterns

### Recommended Project Structure

New files this phase creates or modifies:

```
src/shitbox/
├── dashboard/
│   ├── logbook.py           # NEW — FastAPI router for /api/notes and /api/fuel
│   ├── server.py            # MODIFY — include logbook.router in build_app()
│   └── static/
│       └── index.html       # MODIFY — add modals, trigger buttons, Alpine data
├── storage/
│   └── database.py          # MODIFY — v6 migration, notes/fuel_stops tables
├── sync/
│   └── capture_sync.py      # MODIFY — register_json_generator() + generator loop
└── events/
    └── engine.py            # MODIFY — register generators at startup; last-known GPS helper
```

### Pattern 1: Schema Migration (v5 → v6)

**What:** Add `_migrate_to_v6()` following the identical structure of `_migrate_to_v4()` (which
added new tables). Update `SCHEMA_VERSION = 6` and `SCHEMA_SQL` with `CREATE TABLE IF NOT EXISTS`
for both new tables.

**When to use:** Greenfield tables (not adding columns to existing tables), so the v4 pattern is
the right reference — it uses `CREATE TABLE IF NOT EXISTS` inside `executescript` rather than
`ALTER TABLE`.

**Example (from existing v4 pattern, database.py line 209-243):**

```python
SCHEMA_VERSION = 6

# Add to SCHEMA_SQL:
"""
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    body TEXT NOT NULL,
    event_id INTEGER,
    lat REAL,
    lng REAL,
    gps_stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fuel_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    volume_litres REAL NOT NULL,
    cost_aud REAL,
    lat REAL,
    lng REAL,
    gps_stale BOOLEAN NOT NULL DEFAULT 0,
    odometer_km REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

# In connect():
if current_version < 6:
    self._migrate_to_v6(conn)

def _migrate_to_v6(self, conn: sqlite3.Connection) -> None:
    """Add notes and fuel_stops tables for logbook feature."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            body TEXT NOT NULL,
            event_id INTEGER,
            lat REAL,
            lng REAL,
            gps_stale BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fuel_stops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            volume_litres REAL NOT NULL,
            cost_aud REAL,
            lat REAL,
            lng REAL,
            gps_stale BOOLEAN NOT NULL DEFAULT 0,
            odometer_km REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    log.info("migrated_to_v6", tables=["notes", "fuel_stops"])
```

**Critical detail:** The existing `connect()` method uses a single `if current_version < N` check
per version, not `elif`. This means all migrations run in sequence when jumping multiple versions.
The v6 check must follow the v5 check with the same pattern — no short-circuiting.

### Pattern 2: FastAPI Router Inclusion

**What:** New `logbook.py` creates an `APIRouter`, included in `build_app()` via
`app.include_router()`.

**When to use:** Any new endpoint group added to the dashboard FastAPI app.

**Example (from server.py build_app() pattern):**

```python
# logbook.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
router = APIRouter()

class NoteRequest(BaseModel):
    body: str
    event_id: int | None = None

@router.post("/api/notes", status_code=201)
def create_note(payload: NoteRequest) -> dict:
    ...

# server.py — in build_app():
from shitbox.dashboard.logbook import router as logbook_router
app.include_router(logbook_router)
```

**Critical detail:** `build_app()` is a pure factory with no I/O. The logbook router needs access
to the Database instance. The cleanest approach consistent with the existing pattern is to pass `db`
as a parameter to `build_app()` (following the comment in CONTEXT.md: "add logbook router here" and
"`build_app()` accepts a `db` param convention from research"). The router uses a closure or module-
level reference set before router inclusion.

The exact dependency injection approach (module-level reference vs. FastAPI `Depends`) is left to
Claude's discretion. Module-level reference is simpler and consistent with how `sse_mod` is
currently wired (via `set_recent_events_provider()`).

### Pattern 3: JSON Generator Registry

**What:** `CaptureSyncService` gains a `_json_generators: dict[str, Callable]` and a
`register_json_generator(name, fn)` method. `_do_sync_inner()` iterates generators before the
existing rsync two-pass.

**Example:**

```python
# capture_sync.py — additions

def __init__(self, ...):
    ...
    self._json_generators: dict[str, Callable[[], Any]] = {}

def register_json_generator(self, name: str, fn: Callable[[], Any]) -> None:
    """Register a JSON generator. fn() must return a JSON-serialisable object."""
    self._json_generators[name] = fn

def _run_json_generators(self) -> None:
    """Write each registered generator's output to {captures_dir}/{name}.json."""
    captures = Path(self.captures_dir)
    for name, fn in self._json_generators.items():
        try:
            data = fn()
            out = captures / f"{name}.json"
            out.write_text(json.dumps(data, default=str))
            log.info("json_generator_complete", name=name)
        except Exception as e:
            log.warning("json_generator_failed", name=name, error=str(e))

def _do_sync_inner(self) -> None:
    # Run JSON generators first
    self._run_json_generators()
    # Existing: refresh events index
    if self.event_storage:
        ...
```

**Critical detail:** Generator failures must not stop the rsync. Each generator is wrapped
individually in try/except. The existing events.json and timelapse.json regeneration already happens
before rsync — the new generators slot in at the same point, before the two-pass rsync.

**Exclude new JSON files from Pass 1:** The rsync Pass 1 currently excludes `events.json` and
`timelapse.json`. It must also exclude `notes.json` and `fuel.json`. Otherwise Pass 1 would sync
these files before their backing data (media) is in place — though for these particular files there
is no media dependency, so it is more of a consistency concern. The cleanest approach is to pass
`--exclude=*.json` in Pass 1, or list each file explicitly.

### Pattern 4: Last-Known GPS Position Helper

**What:** A lightweight module-level dict (or two floats) tracking the most recent non-null GPS
fix. Updated by the engine's telemetry loop whenever the GPS collector returns a valid fix.
Exposed as `get_last_known_position() -> tuple[float, float] | None`.

**When to use:** When `read_snapshot()` returns `lat=None` (no current fix), the logbook endpoint
falls back to `get_last_known_position()`.

**Staleness detection:** The last-known position must carry a timestamp so the API can compute
minutes since last fix. Store `(lat, lng, fixed_at: float)` as a module-level state or in
`trip_state` under a well-known key.

**Simple approach:** Module-level in a new `src/shitbox/dashboard/gps_state.py` or inline in
`snapshot.py` as an additional dict. Update it in `engine.py`'s telemetry callback alongside
`update_snapshot()`.

### Pattern 5: Alpine.js Modal (existing SPA pattern)

**What:** Both modals are Alpine.js `x-show`/`x-data` components added to `index.html`. The
existing `dashboard()` function's `x-data` object gains new state keys (`showNoteModal`,
`showFuelModal`, `noteBody`, `fuelVolume`, etc.).

**When to use:** All interactive UI in this SPA.

**Example (condensed, consistent with existing Alpine pattern):**

```javascript
// Add to dashboard() return object:
showNoteModal: false,
showFuelModal: false,
noteBody: '',
noteEventId: null,
fuelVolume: '',
fuelCost: '',
fuelOdo: '',
gpsStaleMinutes: 0,
savingNote: false,
savingFuel: false,

async saveNote() {
  this.savingNote = true;
  try {
    const r = await fetch('/api/notes', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({body: this.noteBody, event_id: this.noteEventId || null})
    });
    if (!r.ok) throw new Error();
    this.showNoteModal = false;
    // show success badge for 3s
  } catch {
    // show error message
  } finally {
    this.savingNote = false;
  }
}
```

**GPS stale minutes:** The POST response (or a pre-flight `GET /api/gps-status`) returns staleness
in seconds. Alpine computes `gpsStaleMinutes = Math.round(staleSeconds / 60)`. Shown with
`x-show="gpsStaleMinutes > 0"`.

Simplest approach: the `+ Note` / `+ Fuel` button click handler fetches current GPS state from
the snapshot endpoint (or a lightweight `GET /api/logbook/gps`) before opening the modal, populates
`gpsStaleMinutes`, then opens the modal.

### Fuel Efficiency Calculation

**What:** Query-time calculation over ordered `fuel_stops`. For each stop N, efficiency is:
`(odometer_km[N] - odometer_km[N-1]) / volume_litres[N]`. Requires two consecutive stops with
non-null odometer values.

**Cumulative average:** Sum of all distances / sum of all volumes where both values are available.

**When odometer is null:** Return `null` for per-stop efficiency. If no stops have odometer,
return `null` for cumulative average.

**Implementation:** Query all stops ordered by `timestamp_utc ASC`, compute in Python (not SQL)
for clarity. This runs in the API response path, so it must be cheap — fine for O(n) over rally-
scale data (tens of stops).

```python
def calculate_fuel_efficiency(stops: list[dict]) -> list[dict]:
    """Add km_per_litre to each stop. Mutates in place, returns list."""
    for i, stop in enumerate(stops):
        if i == 0 or stop["odometer_km"] is None:
            stop["km_per_litre"] = None
            continue
        prev_odo = stops[i - 1]["odometer_km"]
        if prev_odo is None:
            stop["km_per_litre"] = None
            continue
        distance = stop["odometer_km"] - prev_odo
        stop["km_per_litre"] = round(distance / stop["volume_litres"], 2) if distance > 0 else None
    return stops
```

### Anti-Patterns to Avoid

- **Storing efficiency as a column:** Decided against (D-12). Calculated values go stale if
  odometer is later corrected. Calculate at query time.
- **Blocking on GPS fix in the POST handler:** Decided against (D-05). Never block. Use last-known.
- **Saving null GPS coordinates:** Decided against (D-05). Always have a position, even if stale.
- **Letting a generator failure abort rsync:** Must not happen (D-09). Wrap each generator in
  individual try/except.
- **Emitting cost in sync payload:** Hard exclusion (D-10). The `generate_fuel_json()` function
  must explicitly omit `cost_aud`. Do not rely on callers to filter it.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request validation | Manual field checking | Pydantic BaseModel via FastAPI | FastAPI validates automatically; 422 responses are free |
| JSON serialisation | Manual dict building | `json.dumps(data, default=str)` | Handles datetime objects; already used in EventStorage |
| Thread-safe DB writes | Custom locking | Existing `db.transaction()` context manager | Already battle-tested; uses `BEGIN IMMEDIATE` + `_write_lock` |
| Atomic snapshot reads | Locks on GPS state | `read_snapshot()` module-level rebind | GIL-atomic, per existing snapshot.py contract |

**Key insight:** Every infrastructure piece already exists. This phase adds domain logic
(notes/fuel) on top of established infrastructure. Resist the temptation to introduce any new
concurrency primitive or storage abstraction — the existing patterns are sufficient.

---

## Common Pitfalls

### Pitfall 1: Forgetting to Update `SCHEMA_SQL` as well as `_migrate_to_v6()`

**What goes wrong:** `_migrate_to_v6()` creates the tables for existing databases. But
`SCHEMA_SQL` (run via `executescript` on fresh databases) also needs the `CREATE TABLE IF NOT
EXISTS` statements. If you only add the migration method, fresh installs will miss the tables.

**Why it happens:** The v2/v3 migrations only added columns (`ALTER TABLE`), so they didn't touch
`SCHEMA_SQL`. The v4 migration added new tables — it added `CREATE TABLE` to both `SCHEMA_SQL` and
`_migrate_to_v4()`. Phase 12 must follow the v4 pattern, not the v2/v3 pattern.

**How to avoid:** Add `CREATE TABLE IF NOT EXISTS notes (...)` and `CREATE TABLE IF NOT EXISTS
fuel_stops (...)` to `SCHEMA_SQL` before the indexes block. Also add them to `_migrate_to_v6()`.

**Warning signs:** Tests that start from a fresh `tmp_path` database pass. Tests that start from
an existing v5 database and call `connect()` work. But a test that creates a fresh v6 database
and immediately queries `notes` fails. If you see that asymmetry, you've hit this pitfall.

### Pitfall 2: `build_app()` is a Pure Factory — Don't Add I/O or State

**What goes wrong:** Adding database queries or module-level mutable state inside `build_app()`
itself. The docstring in `server.py` explicitly states "Pure factory: no I/O, no thread, no port
bind."

**Why it happens:** It's tempting to initialise the logbook router's DB reference inside
`build_app()`.

**How to avoid:** Pass the `db` (or a logbook storage object) as a parameter to `build_app()` and
wire it into the router via a closure or a `set_db()` call before the router is included. Follow
the existing `set_recent_events_provider()` pattern in `sse_mod`.

**Warning signs:** Tests that call `build_app()` in isolation start hitting database files on disk.

### Pitfall 3: Cost Field Leaks into Sync Payload

**What goes wrong:** `generate_fuel_json()` serialises the full `fuel_stops` row dict without
explicitly dropping `cost_aud`.

**Why it happens:** It's easy to `SELECT *` and serialise the result without thinking about
exclusions.

**How to avoid:** `generate_fuel_json()` must use an explicit column list that does not include
`cost_aud`. Never use `SELECT *` in the fuel JSON generator. This is a hard requirement (D-10).
Add a test that asserts `"cost_aud"` is not a key in any item in the fuel JSON output.

**Warning signs:** Code review catches it if you see `SELECT *` in the fuel query. The test
assertion is the safety net.

### Pitfall 4: GPS Stale Minutes Off-by-One in the Modal

**What goes wrong:** "Location from 0 minutes ago" shows when the fix is very recent, confusing
users. Or the stale warning appears even when GPS has a current fix.

**Why it happens:** Integer rounding of seconds. `gps_fix_mode` in the snapshot is 0 when no fix,
non-zero when fix present. Staleness is only relevant when `gps_fix_mode == 0` but last-known
position is being used.

**How to avoid:** The modal only shows the stale warning when the API response includes
`gps_stale: true`. The backend sets `gps_stale = True` when it uses last-known position
(snapshot has no current fix). The frontend does not independently compute staleness — it reads the
flag from the API response or from the pre-flight GPS status call.

### Pitfall 5: rsync Pass 1 Excludes All JSON — Including New Files

**What goes wrong:** If you change Pass 1's exclude to `--exclude=*.json`, it correctly excludes
`notes.json` and `fuel.json`. But if you use a fixed list, you forget to add them and they sync
in Pass 1 before their associated data is confirmed on the NAS. For notes and fuel there is no
media dependency, so this is low severity — but it breaks the two-pass contract.

**How to avoid:** Either add `--exclude=notes.json --exclude=fuel.json` to the Pass 1 exclude
list alongside `events.json` and `timelapse.json`, or switch to `--exclude=*.json` for Pass 1
generically (simpler and future-proof for any additional JSON generators).

---

## Code Examples

### Existing migration to follow (v4, database.py lines 208-243)

```python
def _migrate_to_v4(self, conn: sqlite3.Connection) -> None:
    """Add health metric columns and trip/waypoint tables for Phase 4."""
    # ... ALTER TABLE calls ...
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trip_state (
            key TEXT PRIMARY KEY,
            value_real REAL,
            value_text TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    log.info("migrated_to_v4", ...)
```

### Existing router inclusion (server.py build_app())

```python
def build_app(mbtiles_path, recent_events_provider=None) -> FastAPI:
    app = FastAPI(...)
    app.include_router(sse_mod.router)
    app.include_router(make_tiles_router(Path(mbtiles_path)))
    ...
    return app
```

### Existing sync inner pattern (capture_sync.py lines 103-168)

```python
def _do_sync_inner(self) -> None:
    if self.event_storage:
        try:
            self.event_storage.generate_events_json()
        except Exception as e:
            log.warning("capture_sync_events_json_error", error=str(e))
    # ... timelapse ...
    # Pass 1: media, excluding JSON index files
    # Pass 2: JSON index files
```

### Existing Alpine.js data pattern (index.html)

```javascript
function dashboard() {
  return {
    speed: 0, imuTemp: '—', ...
    events: [],
    init() { this.initMap(); this.openFast(); ... },
    openFast() {
      const es = new EventSource('/sse/fast');
      es.addEventListener('fast', (e) => { ... });
    }
  }
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No logbook | notes + fuel_stops tables | Phase 12 | New data types in telemetry.db |
| Fixed generators in _do_sync_inner | Registered generator pattern | Phase 12 | Phase 13 can register driver-stats without touching CaptureSyncService internals |
| Schema v5 | Schema v6 | Phase 12 | Two new tables; fresh installs and migrations both covered |

---

## Open Questions

1. **Odometer source for fuel efficiency**
   - What we know: `trip_state` key-value table exists. The GPS collector accumulates speed
     readings. There is no confirmed `odometer_km` key being written to `trip_state` in Phase 11.
   - What's unclear: Whether Phase 11 left an odometer accumulator in `trip_state` or in
     EngineConfig that the logbook can read.
   - Recommendation: Before implementing the efficiency calculation, query `trip_state` for any
     keys containing `odometer` or `distance`. If none found, the fallback is `null` for all
     efficiency values. Document this in the API response schema and move on — the user can enter
     odometer manually in the Fuel Stop modal, which is the primary path anyway.

2. **`build_app()` signature extension for `db`**
   - What we know: The factory currently takes `mbtiles_path` and `recent_events_provider`.
     `build_dashboard_server()` (the convenience factory used by UnifiedEngine) calls `build_app()`.
   - What's unclear: Whether to pass the full `Database` object or a narrower logbook-specific
     storage class.
   - Recommendation: Create a `LogbookStorage` class in `src/shitbox/storage/logbook.py` wrapping
     the DB queries. Pass it to `build_app()` as `logbook_storage: Optional[LogbookStorage] = None`.
     This keeps `build_app()` testable without a full database — pass `None` for tests that don't
     exercise the logbook endpoints.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is code/schema changes only. No new external tools, services, or
CLIs required. rsync, SQLite, FastAPI/uvicorn, and Alpine.js are all already present and confirmed
working in the existing system.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (uses pyproject.toml discovery) |
| Quick run command | `pytest tests/test_database.py tests/test_dashboard.py -x` |
| Full suite command | `pytest --cov=shitbox` |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|--------------|
| NOTE-01 | POST `/api/notes` saves note with auto-captured timestamp + GPS | unit | `pytest tests/test_logbook.py::test_create_note -x` | Wave 0 |
| NOTE-01 | POST `/api/notes` uses last-known GPS when no current fix, sets gps_stale=True | unit | `pytest tests/test_logbook.py::test_note_gps_stale -x` | Wave 0 |
| NOTE-02 | POST `/api/notes` with `event_id` stores association | unit | `pytest tests/test_logbook.py::test_note_event_pin -x` | Wave 0 |
| FUEL-01 | POST `/api/fuel` saves stop with volume and location | unit | `pytest tests/test_logbook.py::test_create_fuel_stop -x` | Wave 0 |
| FUEL-02 | GET `/api/fuel` returns per-stop and cumulative km/L | unit | `pytest tests/test_logbook.py::test_fuel_efficiency -x` | Wave 0 |
| FUEL-02 | km/L is null when odometer absent | unit | `pytest tests/test_logbook.py::test_fuel_efficiency_no_odo -x` | Wave 0 |
| D-10 | fuel JSON generator output never contains cost_aud | unit | `pytest tests/test_logbook.py::test_fuel_json_no_cost -x` | Wave 0 |
| D-11 | Schema v6 migration creates both tables on existing v5 DB | unit | `pytest tests/test_database.py::test_v6_migration -x` | Wave 0 |
| D-11 | Fresh DB connect() creates both tables | unit | `pytest tests/test_database.py::test_v6_fresh_schema -x` | Wave 0 |
| D-08/D-09 | CaptureSyncService runs registered generators before rsync; generator failure does not abort rsync | unit | `pytest tests/test_capture_sync_generators.py -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_logbook.py tests/test_database.py -x`
- **Per wave merge:** `pytest --cov=shitbox`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_logbook.py` — covers NOTE-01, NOTE-02, FUEL-01, FUEL-02, D-10
- [ ] `tests/test_capture_sync_generators.py` — covers D-08, D-09
- [ ] Additional test cases in `tests/test_database.py` — covers D-11 (v6 migration)

---

## Sources

### Primary (HIGH confidence)

- `src/shitbox/storage/database.py` — Schema v5, migration pattern, transaction manager, WAL config
- `src/shitbox/sync/capture_sync.py` — Full `_do_sync_inner()` implementation, two-pass rsync pattern
- `src/shitbox/dashboard/server.py` — `build_app()` factory, router inclusion, pure factory contract
- `src/shitbox/dashboard/snapshot.py` — Lock-free snapshot, `lat`/`lng`/`gps_fix_mode` confirmed present
- `src/shitbox/events/engine.py` — EngineConfig dataclass, service wiring pattern
- `src/shitbox/dashboard/static/index.html` — Alpine.js patterns, event array, SSE subscription
- `src/shitbox/storage/models.py` — Reading, SensorType, SyncCursor — existing data structures
- `.planning/phases/12-schema-foundation-and-logbook-api/12-UI-SPEC.md` — Approved UI design contract

### Secondary (MEDIUM confidence)

- `pyproject.toml` — Confirmed dependency versions (fastapi>=0.115, structlog>=24.0.0, pytest>=7.0)
- `pytest --version` output — Confirmed pytest 9.0.2 installed

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all dependencies confirmed installed, versions from pyproject.toml
- Architecture: HIGH — patterns read directly from source files, no inference required
- Migration pattern: HIGH — v4 is the exact reference for new-table migrations
- Fuel efficiency: MEDIUM — calculation logic is straightforward, odometer source is uncertain
- Pitfalls: HIGH — identified by reading actual code, not general knowledge

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (stable stack; 30-day window appropriate)
