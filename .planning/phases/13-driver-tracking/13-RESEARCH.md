# Phase 13: Driver Tracking - Research

**Researched:** 2026-04-09
**Domain:** FastAPI REST, SQLite migration, Alpine.js UI, in-memory engine state
**Confidence:** HIGH

## Summary

Phase 13 is well-scoped and follows patterns that already exist in the codebase.
Every subsystem it touches -- schema migration, FastAPI router, snapshot dict, SSE
stream, Alpine.js modal, JSON sync generator -- has a Phase 12 counterpart to copy
from. This is essentially a second pass of the Phase 12 pattern with driver-specific
logic instead of notes/fuel logic.

The one area that needs a decision before planning is **event attribution**: the
CONTEXT.md (D-04) says to add a `driver_name` column to the "events table" in the
v7 migration, but there is no SQL `events` table. Events are stored as JSON files on
disk by `EventStorage.save_event()`. The planner must choose one of two
interpretations: (a) add `driver_name` to the JSON metadata written by
`save_event()` (no SQL migration needed), or (b) create a new SQL `events` table in
v7 and migrate event storage to use it (significant scope). Option (a) is consistent
with the existing architecture and requires only a one-line change to `save_event()`.

The driver roster is static YAML -- no edit UI. The active driver is in-memory
module-level state (same pattern as `gps_state.py`). Stint timing goes in a new
`driver_stints` SQLite table. The top-bar dropdown and stats modal are new Alpine.js
UI additions. All sync export follows the Phase 12 JSON generator pattern.

**Primary recommendation:** Follow the Phase 12 router/storage/snapshot pattern
exactly. Add `driver_name` to JSON event metadata (not a new SQL events table) to
stay consistent with the existing `EventStorage` architecture.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Driver names come from `config.yaml` -- a `drivers:` list (e.g.
  `drivers: [Tony, Smithy, Nav]`). No edit UI on the Pi. Change the file to change
  the roster. Planner decides the exact YAML key and config dataclass field.
- **D-02:** The driver selector in the dashboard is a dropdown in the top bar,
  replacing the current "Driver: ---" placeholder (index.html line 35). Clicking the
  displayed driver name opens the dropdown. Single tap to switch -- no confirm modal.
  Switching POSTs to a new `/api/driver` endpoint.
- **D-03:** A new `driver_stints` table is added in schema v7 migration (following
  the v6 pattern). Columns: `id INTEGER PRIMARY KEY, driver_name TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT NULLABLE, created_at TEXT`. When a driver
  is selected, the current open stint (ended_at IS NULL) is closed with
  `ended_at = NOW()`, and a new stint is opened. On first driver selection after boot
  (no prior stint), create the first stint directly.
- **D-04:** Event attribution via a `driver_name TEXT NULLABLE` column added to the
  `events` table in the same v7 migration. The engine sets this at event-record time
  using the in-memory active driver. If no driver is set, the field is null. (See
  research note on what "events table" means in this codebase -- see Architecture
  Patterns below.)
- **D-05:** The `/sse/slow` stream gains an `active_driver` field (string or null)
  in its payload. The engine maintains `self.active_driver: Optional[str]` in memory
  and exposes it via the snapshot dict (key `active_driver`). No lock needed (string
  assignment is atomic).
- **D-06:** Clicking the driver name in the top bar opens a stats modal (Alpine.js
  `x-show`, consistent with Phase 12 modals). The modal fetches `/api/driver/stats`
  -- a list of `{driver_name, total_seconds, pct}` rows, sorted by total time
  descending. Displays: Name | Time driven | % of total. ESC closes.
- **D-07:** The modal also has the driver selection dropdown -- selecting a new
  driver from the modal (or the top bar dropdown) sends `POST /api/driver {name:
  "..."}` to switch.
- **D-08:** Phase 12 registered the JSON generator pattern. Phase 13 registers a
  `driver-stats` generator that writes `{captures_dir}/driver-stats.json` before
  each rsync. Payload: current active driver + time/percentage per driver. No cost or
  private data.

### Claude's Discretion

- API endpoint design (`/api/driver`, `/api/driver/stats`) -- standard FastAPI
  patterns, consistent with logbook router
- Config dataclass field name for the drivers list
- Exact snapshot dict key name for active driver (suggest `active_driver`)
- How to handle "no driver selected" in the dropdown (blank/dash option at top)
- Whether to show a "since" timestamp on the active driver in the top bar (e.g.
  "Tony (2h 15m)")

### Deferred Ideas (OUT OF SCOPE)

- Per-driver event counts in the stats modal (event attribution stats belong in
  Phase 18 alongside the website view)
- On-screen keyboard for freeform driver name entry (Phase 17 kiosk consideration)
- Retroactive stint correction if the wrong driver was set

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DRVR-01 | User can set and change the active driver from the Pi UI | D-02: dropdown in top bar, `/api/driver` POST endpoint, `DriverStorage.set_active_driver()` |
| DRVR-02 | System tracks driving time and calculates percentage per driver across the rally | D-03: `driver_stints` table, `/api/driver/stats` endpoint computing `SUM(ended_at - started_at)`, percentage from total |
| DRVR-03 | Driver is attributed to events -- who was driving when an event occurred | D-04: `driver_name` added to event metadata at `save_event()` call time using in-memory `active_driver` |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | REST router for `/api/driver` | Already in use; follow logbook.py pattern |
| SQLite (stdlib) | existing | `driver_stints` table, migration v7 | Project-wide storage; WAL mode already configured |
| Alpine.js | existing (loaded in index.html) | Dropdown and stats modal | Phase 12 established this as the dashboard UI pattern |
| Pydantic | existing | Request body validation for POST /api/driver | Used in logbook.py already |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | existing | Logging in DriverStorage and router | All modules use structlog with keyword args |
| Python threading | stdlib | Module-level atomic state (same as gps_state.py) | GIL-atomic string rebind for active driver |

**No new dependencies.** This phase is entirely within the existing stack.

## Architecture Patterns

### Recommended Project Structure

New files to create:

```
src/shitbox/
├── storage/
│   └── driver.py           # DriverStorage (new -- follows logbook.py shape)
└── dashboard/
    ├── driver_state.py     # Module-level active_driver state (new -- follows gps_state.py)
    └── driver.py           # FastAPI router /api/driver, /api/driver/stats (new)
```

Modifications to existing files:

```
src/shitbox/
├── storage/database.py     # _migrate_to_v7(), SCHEMA_VERSION = 7
├── dashboard/snapshot.py   # Add "active_driver": None to default snapshot
├── dashboard/sse.py        # Add "active_driver" to /sse/slow payload
├── dashboard/server.py     # build_app() accepts driver_storage kwarg; includes driver router
├── events/engine.py        # active_driver in-memory field; pass to save_event(); snapshot update
├── events/storage.py       # save_event() accepts optional driver_name kwarg; writes to JSON
├── utils/config.py         # Add drivers field to Config (or AppConfig); load_config() handles it
├── sync/capture_sync.py    # register_json_generator("driver-stats", ...) called by engine
└── dashboard/static/index.html  # Replace "Driver: ---" placeholder with dropdown + stats modal
config/
└── config.yaml             # Add `drivers:` list
```

### Pattern 1: Module-level atomic driver state (driver_state.py)

**What:** Same pattern as `gps_state.py` -- module-level `Optional[str]` with
setter/getter. GIL-atomic rebind means no lock needed for reads.

**When to use:** Any time the active driver needs to be read by the SSE stream,
the snapshot writer, or the event recorder without acquiring a lock.

```python
# Source: src/shitbox/dashboard/gps_state.py (existing pattern)
from __future__ import annotations
from typing import Optional

_active_driver: Optional[str] = None

def set_active_driver(name: Optional[str]) -> None:
    global _active_driver
    _active_driver = name

def get_active_driver() -> Optional[str]:
    return _active_driver

def clear_active_driver() -> None:
    """Test helper only."""
    global _active_driver
    _active_driver = None
```

### Pattern 2: DriverStorage class (storage/driver.py)

**What:** Wraps the `driver_stints` SQLite table. Injected into the router via
`set_storage()`, same as `LogbookStorage` in `logbook.py`.

Key methods:

- `set_driver(name: str) -> dict` -- closes current open stint, opens new one, returns
  `{driver_name, started_at}`
- `get_stats() -> list[dict]` -- returns `[{driver_name, total_seconds, pct}, ...]`
  sorted descending by `total_seconds`
- `get_driver_stats_payload() -> dict` -- returns sync export dict:
  `{active_driver, drivers: [...]}`

Stint SQL for `set_driver()`:

```sql
-- Close current open stint
UPDATE driver_stints
SET ended_at = datetime('now')
WHERE ended_at IS NULL;

-- Open new stint
INSERT INTO driver_stints (driver_name, started_at, created_at)
VALUES (?, datetime('now'), datetime('now'));
```

Stats query:

```sql
SELECT
    driver_name,
    SUM(
        CAST(
            (julianday(COALESCE(ended_at, datetime('now'))) -
             julianday(started_at)) * 86400
        AS INTEGER)
    ) AS total_seconds
FROM driver_stints
GROUP BY driver_name
ORDER BY total_seconds DESC
```

Percentage is calculated in Python from `total_seconds / sum(all total_seconds) * 100`.

### Pattern 3: FastAPI driver router (dashboard/driver.py)

**What:** Follows `logbook.py` shape exactly -- module-level `_storage`, `set_storage()`,
`_require_storage()`, Pydantic request model, router endpoints.

```python
# Source: src/shitbox/dashboard/logbook.py (existing pattern)
router = APIRouter()
_storage: Optional[DriverStorage] = None

def set_storage(storage: DriverStorage) -> None:
    global _storage
    _storage = storage

class DriverRequest(BaseModel):
    name: str = Field(..., min_length=1)

@router.post("/api/driver", status_code=200)
def set_driver(payload: DriverRequest) -> dict:
    ...

@router.get("/api/driver/stats")
def get_driver_stats() -> dict:
    ...
```

### Pattern 4: Schema v7 migration

**What:** Follows `_migrate_to_v6()` exactly. Creates `driver_stints` table and adds
`driver_name` column to events metadata (see critical note below).

```python
def _migrate_to_v7(self, conn: sqlite3.Connection) -> None:
    """Add driver_stints table for Phase 13 driver tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS driver_stints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    log.info("migrated_to_v7", tables=["driver_stints"])
```

Wire into `connect()`:

```python
if current_version < 7:
    self._migrate_to_v7(conn)
```

And bump `SCHEMA_VERSION = 7`.

### Pattern 5: Engine wiring

**What:** In `UnifiedEngine.__init__()`, add `self.active_driver: Optional[str] =
None`. Update `_update_snapshot()` to include `"active_driver":
self.active_driver`. Pass `driver_name=self.active_driver` when calling
`self.event_storage.save_event()`.

The driver router needs access to `DriverStorage`. Wire via `build_dashboard_server()`
kwarg, same as `logbook_storage`.

### Critical Note: "Events Table" Interpretation

The CONTEXT.md (D-04) refers to adding `driver_name` to the "events table" in v7.
**There is no SQL events table.** Events are stored as JSON files on disk by
`EventStorage.save_event()`. The correct interpretation, consistent with the
existing architecture, is:

- Add an optional `driver_name: Optional[str] = None` parameter to
  `EventStorage.save_event()`
- Write `driver_name` into the JSON metadata dict alongside `type`, `timestamp`, etc.
- No SQL migration needed for this -- `driver_stints` is the only new SQL table

This keeps the codebase consistent. Creating a new SQL events table would be a
significant scope change outside the phase boundary.

The v7 migration therefore only creates `driver_stints`. There is no `events` SQL
table to alter.

### Anti-Patterns to Avoid

- **Locking on driver state reads:** Module-level string rebind is GIL-atomic. No
  lock needed for reads in the SSE stream or snapshot writer. Lock is only needed in
  `DriverStorage` write operations (same as `logbook.py` using
  `db.transaction()`).
- **Storing drivers list in the database:** Drivers come only from config. The DB
  only stores stints (which driver drove when). The roster itself is never persisted.
- **Blocking the 100 Hz capture path:** `save_event()` runs in a thread separate
  from the SSE/API path. Adding a `driver_name` kwarg is a pass-through -- no I/O
  overhead added to the capture path.
- **Confirming driver switch in the UI:** D-02 is explicit: single tap, no confirm.
  No confirm modal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stint duration calculation | Custom Python timedelta arithmetic | SQLite `julianday()` function | Handles open stints (no `ended_at`) correctly with `COALESCE(ended_at, datetime('now'))` |
| Thread-safe active driver | Mutex + shared state | Module-level rebind (GIL atomic) | Proven pattern already used for GPS state in this codebase |
| Router injection | Constructor DI | Module-level `set_storage()` | Phase 12 established this; TestClient can call `set_storage()` directly |

**Key insight:** Every mechanism needed here was solved in Phase 12. The planner
should not invent new patterns.

## Common Pitfalls

### Pitfall 1: Forgetting `ended_at IS NULL` guard

**What goes wrong:** When opening a new stint, all existing stints with a null
`ended_at` must be closed first. If the guard is missing, two open stints exist
simultaneously, and stats queries double-count time.

**Why it happens:** Simple INSERT without first closing the open stint.

**How to avoid:** Always close any open stint before inserting a new one. Wrap both
operations in a `db.transaction()` context to make them atomic.

**Warning signs:** `get_stats()` returns a driver's total time exceeding the rally
duration.

### Pitfall 2: Active driver not in snapshot before first driver selection

**What goes wrong:** The SSE stream sends `active_driver: null` until the crew
selects a driver. The UI must handle null gracefully -- showing a dash or "No
driver" rather than crashing.

**Why it happens:** `driver_state._active_driver` is `None` at boot.

**How to avoid:** Default snapshot value is `"active_driver": None`. The UI reads
it as a falsy value and shows the dash. The JS `x-text` expression should handle
null: `x-text="activeDriver || '---'"`.

### Pitfall 3: Stats query returns zero rows for a driver with only an open stint

**What goes wrong:** If a driver has never ended a stint (still driving), the
`julianday` subtraction returns the correct live value via `COALESCE(ended_at,
datetime('now'))`. But if `COALESCE` is omitted, `ended_at IS NULL` causes the row
to produce NULL duration and `SUM` drops it.

**How to avoid:** Use `COALESCE(ended_at, datetime('now'))` in the stats query.
Covered in Pattern 2 above.

### Pitfall 4: `drivers` list not loading from YAML

**What goes wrong:** `_dict_to_dataclass()` handles nested dataclasses and
primitive values, but `List[str]` is a primitive list and should be handled
correctly as-is. However, if the YAML key is under a nested config (e.g.
`SyncConfig`) rather than a top-level key, `load_config()` must explicitly extract
it.

**Why it happens:** `load_config()` has explicit handling for some fields (route
waypoints, DS18B20 probes) and generic `_dict_to_dataclass()` for others. A new
`List[str]` field on an existing dataclass should work with `_dict_to_dataclass()`
without special handling, but only if it's added to a dataclass that is already
handled.

**How to avoid:** Add `drivers: List[str]` to `Config` directly (or `AppConfig`)
and verify `_dict_to_dataclass()` passes it through. Write a test that loads a
YAML string with `drivers:` and asserts the list is populated. `List[str]` does not
need the special list-of-dataclasses handling that `waypoints` and `probes` needed.

### Pitfall 5: Driver name POST with a name not in the config roster

**What goes wrong:** The API accepts any string. If the UI only shows configured
drivers but the API is open, a malformed request could create a stint for an
unrecognised name. Stats would still work (SQL-based), but the UX is off.

**How to avoid:** In `POST /api/driver`, validate that `payload.name` is in the
configured `drivers` list. Return HTTP 422 if not found. The drivers list must be
accessible to the router -- pass it in via `set_storage()` or a separate
`set_drivers()` injector.

### Pitfall 6: Missing `driver_name` in the snapshot before engine starts writing it

**What goes wrong:** If `"active_driver"` is not in the default snapshot dict
(`snapshot.py`), SSE consumers hit a `KeyError` during the boot window before the
engine's first snapshot update.

**How to avoid:** Add `"active_driver": None` to the default `_snapshot` dict in
`snapshot.py`. This follows the existing 16-key contract documented in that file.

## Code Examples

### Closed vs open stint query (duration calculation)

```python
# Source: SQLite julianday() arithmetic -- standard SQLite
stats = conn.execute("""
    SELECT
        driver_name,
        SUM(CAST(
            (julianday(COALESCE(ended_at, datetime('now'))) -
             julianday(started_at)) * 86400
        AS INTEGER)) AS total_seconds
    FROM driver_stints
    GROUP BY driver_name
    ORDER BY total_seconds DESC
""").fetchall()
total = sum(r["total_seconds"] or 0 for r in stats)
return [
    {
        "driver_name": r["driver_name"],
        "total_seconds": r["total_seconds"] or 0,
        "pct": round((r["total_seconds"] or 0) / total * 100, 1) if total > 0 else 0.0,
    }
    for r in stats
]
```

### Atomic stint switch (transaction pattern)

```python
# Source: src/shitbox/storage/database.py -- transaction() context manager pattern
def set_driver(self, name: str) -> dict:
    with self._db.transaction() as conn:
        conn.execute(
            "UPDATE driver_stints SET ended_at = datetime('now') WHERE ended_at IS NULL"
        )
        conn.execute(
            "INSERT INTO driver_stints (driver_name, started_at, created_at) "
            "VALUES (?, datetime('now'), datetime('now'))",
            (name,),
        )
    # Update module-level state after successful DB write
    from shitbox.dashboard import driver_state
    driver_state.set_active_driver(name)
    return {"driver_name": name}
```

### Adding active_driver to SSE slow payload

```python
# Source: src/shitbox/dashboard/sse.py -- sse_slow() generator (existing)
yield _format_sse(
    "slow",
    {
        "ts": snap["ts"],
        # ... existing fields ...
        "active_driver": snap["active_driver"],  # new
    },
)
```

### save_event() driver attribution

```python
# Source: src/shitbox/events/storage.py -- save_event() (existing, add kwarg)
def save_event(
    self,
    event: Event,
    video_path: Optional[Path] = None,
    driver_name: Optional[str] = None,  # new
) -> tuple[Path, Path]:
    ...
    metadata = event.to_dict()
    metadata["csv_file"] = csv_path.name
    metadata["saved_at"] = datetime.now(timezone.utc).isoformat()
    if video_path:
        metadata["video_path"] = str(video_path)
    if driver_name is not None:          # new
        metadata["driver_name"] = driver_name  # new
    ...
```

### Alpine.js driver dropdown (top bar)

```html
<!-- Replace existing "Driver: ---" div at index.html line 35 -->
<div class="text-sm text-gray-400" style="position: relative;">
  <span style="cursor: pointer;"
        @click="showDriverModal = true"
        x-text="activeDriver ? activeDriver : '--- Driver'">
  </span>
</div>
```

## Environment Availability

Step 2.6: SKIPPED (no external dependencies -- pure Python/SQL/JS changes within existing stack).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pytest.ini` or `pyproject.toml` (existing) |
| Quick run command | `pytest tests/test_driver.py -x` |
| Full suite command | `pytest --cov=shitbox` |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| DRVR-01 | POST /api/driver switches active driver, returns 200 | unit | `pytest tests/test_driver.py::test_set_driver -x` | Wave 0 |
| DRVR-01 | POST /api/driver with unknown name returns 422 | unit | `pytest tests/test_driver.py::test_set_driver_unknown_name -x` | Wave 0 |
| DRVR-01 | GET /sse/slow includes active_driver field | unit | `pytest tests/test_driver.py::test_sse_slow_includes_active_driver -x` | Wave 0 |
| DRVR-02 | get_stats() returns total_seconds and pct per driver | unit | `pytest tests/test_driver.py::test_driver_stats -x` | Wave 0 |
| DRVR-02 | Open stint (no ended_at) counts live time via COALESCE | unit | `pytest tests/test_driver.py::test_driver_stats_open_stint -x` | Wave 0 |
| DRVR-02 | Switching driver closes previous stint atomically | unit | `pytest tests/test_driver.py::test_stint_switch_closes_previous -x` | Wave 0 |
| DRVR-03 | save_event() writes driver_name to JSON metadata | unit | `pytest tests/test_driver.py::test_event_attribution -x` | Wave 0 |
| DRVR-03 | driver_name is null in JSON when no driver set | unit | `pytest tests/test_driver.py::test_event_attribution_no_driver -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_driver.py -x`
- **Per wave merge:** `pytest --cov=shitbox`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_driver.py` -- covers all DRVR-01/02/03 cases above
- [ ] `src/shitbox/dashboard/driver_state.py` -- needs `clear_active_driver()` test
  helper (same as `gps_state.clear_last_known_position()`)

## Open Questions

1. **Config placement for `drivers` list**
   - What we know: CONTEXT.md says the planner decides the exact YAML key and
     dataclass field.
   - What's unclear: Whether to add to `Config` directly (top-level `drivers:` in
     YAML) or nest under `app:` or a new `rally:` section.
   - Recommendation: Add `drivers: List[str]` directly to `Config` dataclass as a
     top-level field. YAML key `drivers:`. Simplest, no new nesting. Default
     `field(default_factory=list)`. The `load_config()` function would pass
     `data.get("drivers", [])` directly to `Config()`.

2. **"Since" timestamp on top bar driver display**
   - What we know: CONTEXT.md marks this as Claude's Discretion.
   - What's unclear: Whether the overhead (API call or SSE field) is worth it.
   - Recommendation: Yes, show it. The active driver's `started_at` is already in
     the most recent stint row. Return it from `POST /api/driver` response and store
     in Alpine.js state. No extra API call needed. Display as "Tony (2h 15m)" using
     elapsed time computed client-side from the `started_at` timestamp. Low cost,
     useful at a glance during a stage.

3. **"No driver selected" option in dropdown**
   - What we know: CONTEXT.md marks this as Claude's Discretion.
   - What's unclear: Whether to allow unsetting a driver (setting to null).
   - Recommendation: Include a "-- No driver --" blank option at the top of the
     dropdown. `POST /api/driver` with `name: ""` (or a special sentinel) clears the
     active driver. `DriverStorage.clear_driver()` closes the open stint without
     opening a new one. This handles the crew break case.

## Sources

### Primary (HIGH confidence)

- `src/shitbox/storage/database.py` -- migration pattern v2-v6, transaction context
  manager, SCHEMA_VERSION mechanism
- `src/shitbox/dashboard/logbook.py` -- router injection pattern, Pydantic models,
  `set_storage()` / `_require_storage()`
- `src/shitbox/dashboard/gps_state.py` -- module-level atomic state pattern for
  active driver
- `src/shitbox/dashboard/snapshot.py` -- snapshot dict contract, default keys,
  GIL-atomic rebind
- `src/shitbox/dashboard/sse.py` -- `/sse/slow` payload structure, where to add
  `active_driver`
- `src/shitbox/dashboard/server.py` -- `build_app()` kwarg injection pattern
- `src/shitbox/sync/capture_sync.py` -- `register_json_generator()` API
- `src/shitbox/events/storage.py` -- `save_event()` signature, JSON metadata dict
  (confirms there is no SQL events table)
- `src/shitbox/utils/config.py` -- `_dict_to_dataclass()`, `load_config()`, where to
  add `drivers` field
- `src/shitbox/dashboard/static/index.html` line 35 -- existing "Driver: ---"
  placeholder, Alpine.js modal patterns

### Secondary (MEDIUM confidence)

- `tests/test_logbook.py` -- confirms test pattern: `tmp_db` fixture, TestClient,
  `set_storage()` in tests
- `tests/test_capture_sync_generators.py` -- confirms JSON generator test pattern

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH -- no new libraries, all existing
- Architecture: HIGH -- every pattern has a direct existing analogue
- Pitfalls: HIGH -- identified from reading actual code paths
- "Events table" interpretation: HIGH -- confirmed by reading `EventStorage.save_event()`;
  no SQL events table exists

**Research date:** 2026-04-09
**Valid until:** Stable (no external dependencies; only project-internal code)
