# Phase 13: Driver Tracking - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Active driver selection from the Pi dashboard, SQLite stint recording (schema v7), event attribution to the active driver, SSE broadcast of the active driver, and a driver stats modal on the dashboard. Drivers are configured in `config.yaml` before the rally.

This phase does NOT include the website driver stats page (Phase 18) or the driver-selector kiosk display (Phase 17). Pi-side backend and dashboard UI only.

</domain>

<decisions>
## Implementation Decisions

### Driver Roster
- **D-01:** Driver names come from **`config.yaml`** — a `drivers:` list (e.g. `drivers: [Tony, Smithy, Nav]`). No edit UI on the Pi. Change the file to change the roster. Planner decides the exact YAML key and config dataclass field.
- **D-02:** The driver selector in the dashboard is a **dropdown in the top bar**, replacing the current "Driver: —" placeholder (index.html line 35). Clicking the displayed driver name opens the dropdown. Single tap to switch — no confirm modal. Switching POSTs to a new `/api/driver` endpoint.

### Stint Recording
- **D-03:** A new **`driver_stints`** table is added in schema **v7** migration (following the v6 pattern). Columns: `id INTEGER PRIMARY KEY, driver_name TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NULLABLE, created_at TEXT`. When a driver is selected, the current open stint (ended_at IS NULL) is closed with `ended_at = NOW()`, and a new stint is opened. On first driver selection after boot (no prior stint), create the first stint directly.
- **D-04:** **Event attribution** via a `driver_name TEXT NULLABLE` column added to the **`events`** table in the same v7 migration. The engine sets this at event-record time using the in-memory active driver. If no driver is set (no selection made yet), the field is null.

### SSE Broadcast
- **D-05:** The `/sse/slow` stream gains an **`active_driver`** field (string or null) in its payload. The engine maintains `self.active_driver: Optional[str]` in memory and exposes it via the snapshot dict (key `active_driver`). The SSE reads it from the snapshot — no lock needed (string assignment is atomic).

### Dashboard Stats Modal
- **D-06:** Clicking the driver name in the top bar opens a **stats modal** (Alpine.js `x-show`, consistent with Phase 12 modals). The modal fetches `/api/driver/stats` — a list of `{driver_name, total_seconds, pct}` rows, sorted by total time descending. Displays: Name | Time driven | % of total. ESC closes.
- **D-07:** The modal also has the **driver selection dropdown** — selecting a new driver from the modal (or the top bar dropdown) sends `POST /api/driver {name: "..."}` to switch.

### Sync Export
- **D-08:** Phase 12 registered the JSON generator pattern. Phase 13 registers a `driver-stats` generator that writes `{captures_dir}/driver-stats.json` before each rsync. Payload: current active driver + time/percentage per driver (no cost or private data). This feeds Phase 18's website widget.

### Claude's Discretion
- API endpoint design (`/api/driver`, `/api/driver/stats`) — standard FastAPI patterns, consistent with logbook router
- Config dataclass field name for the drivers list
- Exact snapshot dict key name for active driver (suggest `active_driver`)
- How to handle "no driver selected" in the dropdown (blank/dash option at top)
- Whether to show a "since" timestamp on the active driver in the top bar (e.g. "Tony (2h 15m)")

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Database and schema
- `src/shitbox/storage/database.py` — Schema v6, migration pattern, `_migrate_to_v6()` as the template for v7. Both `driver_stints` table and `driver_name` column on events follow the same approach.

### Dashboard and SSE
- `src/shitbox/dashboard/sse.py` — `/sse/slow` payload structure. Add `active_driver` to the slow event dict.
- `src/shitbox/dashboard/snapshot.py` — Snapshot dict contract. Add `active_driver` key here.
- `src/shitbox/dashboard/server.py` — `build_app()` factory pattern. New driver router included here.
- `src/shitbox/dashboard/logbook.py` — Phase 12 router pattern to follow for the new driver router.
- `src/shitbox/dashboard/static/index.html` — Line 35: existing `Driver: —` placeholder. Alpine.js and Tailwind patterns for modals (Phase 12 added notes/fuel modals — follow the same pattern).

### Engine wiring
- `src/shitbox/events/engine.py` — UnifiedEngine. Follow Phase 12 wiring pattern: in-memory state, snapshot update, service registration.

### Sync export
- `src/shitbox/sync/capture_sync.py` — `register_json_generator()` pattern added in Phase 12. Register `driver-stats` generator here.

### Config
- `src/shitbox/utils/config.py` — Config dataclass pattern. Add `drivers: List[str]` field to the appropriate parent config.
- `config/config.yaml` — Add `drivers:` list here.

### Requirements
- `.planning/REQUIREMENTS.md` — DRVR-01, DRVR-02, DRVR-03 are this phase's requirements. DRVR-04 and DRVR-05 are Phase 18.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/shitbox/dashboard/logbook.py` — FastAPI router with `set_storage()` injector. Driver router follows this pattern exactly.
- `src/shitbox/dashboard/gps_state.py` — Module-level atomic state (Phase 12). Driver state can use the same pattern (`active_driver: Optional[str] = None`, `set_active_driver()`, `get_active_driver()`).
- Alpine.js modal pattern from Phase 12 in `index.html` — reuse for the stats modal.

### Established Patterns
- Schema migration: `_migrate_to_v6()` pattern — new tables, `SCHEMA_VERSION` bump, wired into `connect()`.
- Snapshot dict: single writer (engine), many readers (SSE). Adding `active_driver` follows existing pattern.
- Engine service wiring: instantiate in `__init__`, expose to dashboard via `build_dashboard_server()` kwargs.

### Integration Points
- `UnifiedEngine._record_telemetry()` — where events are saved. Add `driver_name=self.active_driver` here.
- `/sse/slow` payload dict in `sse.py` — add `active_driver: snap["active_driver"]`.
- `snapshot.py` — add `"active_driver": None` to the default snapshot.

</code_context>

<specifics>
## Specific Ideas

- Driver selection is fast and frequent during a rally — one tap, no confirm step. Keep it light.
- Stats modal is on-demand, not always visible — a glance feature between stages.
- The `driver-stats.json` sync export is the bridge to the Phase 18 website widget (DRVR-04, DRVR-05).

</specifics>

<deferred>
## Deferred Ideas

- Per-driver event counts in the stats modal (event attribution stats belong in Phase 18 alongside the website view)
- On-screen keyboard for freeform driver name entry (Phase 17 kiosk consideration)
- Retroactive stint correction if the wrong driver was set

</deferred>

---

*Phase: 13-driver-tracking*
*Context gathered: 2026-04-09 via /gsd:discuss-phase*
