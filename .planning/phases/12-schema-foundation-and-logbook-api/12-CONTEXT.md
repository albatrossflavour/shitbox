# Phase 12: Schema Foundation and Logbook API - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

REST endpoints for field notes and fuel stops, SQLite schema migration to v6 (new tables: `notes`, `fuel_stops`), and CaptureSyncService extension to export `notes.json` and `fuel.json` before rsync. Entry UI lives in the existing dashboard as modal overlays. Data flows Pi → SQLite → JSON export → NAS → website (Phase 18 consumes on the website side).

This phase does NOT include driver tracking (Phase 13), the driver display (Phase 17), or website integration (Phase 18). The Pi-side backend and entry UI only.

</domain>

<decisions>
## Implementation Decisions

### Logbook UI Shape
- **D-01:** Notes and fuel stop forms are **modal overlays** on the existing dashboard (`dashboard/static/index.html`). No new route, no tab bar. The live telemetry view stays up behind the modal.
- **D-02:** Modals are triggered by **"+ Note" and "+ Fuel" buttons** visible in the dashboard UI. No keyboard shortcuts in this phase — buttons are the primary (and only) trigger.
- **D-03:** The entry UI requires the existing USB keyboard/trackpad setup. On-screen keyboard (simple-keyboard) is deferred — the `simple-keyboard` library is a known option if Phase 17 needs it for the kiosk display, but it is explicitly out of scope here.

### GPS Handling
- **D-04:** When saving a note or fuel stop, the GPS position is taken from `read_snapshot()` — the lock-free snapshot dict already exposes `lat`, `lng`, and `gps_fix_mode`.
- **D-05:** If there is no current GPS fix, **use the last-known position** (most recent non-null lat/lng stored separately from the snapshot). Do not block. Do not save null.
- **D-06:** When the position used is stale (from a prior fix, not the current snapshot), the **modal shows a warning**: "Location from X minutes ago" before the user submits. User can proceed or wait. The staleness is stored as a `gps_stale: bool` flag on the record.
- **D-07:** The "last known position" is maintained by the engine or a lightweight helper — updated whenever a GPS fix is received, never cleared. This persists across brief no-fix windows (tunnels, underpasses, buildings).

### Sync Extension
- **D-08:** `CaptureSyncService` gains a **`register_json_generator(name, fn)`** method. Generators are callables that produce a JSON-serialisable dict/list. They are registered at engine startup — Phase 12 registers `notes` and `fuel`, Phase 13 will register `driver-stats`. No further changes to `CaptureSyncService` internals needed.
- **D-09:** Generator output is written to `{captures_dir}/{name}.json` before the rsync run (after media pass, in the existing two-pass order). Partial write failure in one generator is caught and logged — it must not abort the rsync of other files or media.
- **D-10:** **Fuel cost is hard-excluded from all sync payloads.** The `generate_fuel_json()` function explicitly drops the cost field. This is enforced in code, not by convention.

### Schema
- **D-11:** Schema migrates to **v6** following the existing `SCHEMA_VERSION` / `schema_version` table migration pattern in `database.py`. Two new tables:
  - `notes (id, timestamp_utc, body TEXT, event_id INTEGER NULLABLE, lat REAL NULLABLE, lng REAL NULLABLE, gps_stale BOOLEAN, created_at)`
  - `fuel_stops (id, timestamp_utc, volume_litres REAL, cost_aud REAL, lat REAL NULLABLE, lng REAL NULLABLE, gps_stale BOOLEAN, odometer_km REAL NULLABLE, created_at)`
- **D-12:** Fuel efficiency (km/L) is **calculated at query time** (distance since last stop ÷ volume), not stored as a column. This avoids stale calculated values if odometer data is later corrected.

### Claude's Discretion
- REST endpoint design (URL structure, response shape, error codes) — standard FastAPI patterns
- New router location (suggest `src/shitbox/dashboard/logbook.py`, included via `build_app()`)
- Odometer source for fuel efficiency — use GPS distance accumulator from trip_state if available, else null
- Modal HTML/CSS/JS design — consistent with existing Alpine.js + Tailwind patterns in `dashboard/static/index.html`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Database and schema
- `src/shitbox/storage/database.py` — Schema v5, migration pattern, `SCHEMA_VERSION` constant, `schema_version` table. New migration follows this exact pattern.
- `src/shitbox/storage/models.py` — Reading/SensorType models; understand existing data structures before adding new ones.

### Sync pipeline
- `src/shitbox/sync/capture_sync.py` — CaptureSyncService, `_do_sync_inner()`, two-pass rsync logic. The registry pattern extends this class.

### Dashboard / API
- `src/shitbox/dashboard/server.py` — `build_app()` factory, router inclusion pattern. New `logbook.py` router is included here.
- `src/shitbox/dashboard/snapshot.py` — Lock-free snapshot contract. `lat`, `lng`, `gps_fix_mode` fields already present. `read_snapshot()` is the GPS source.
- `src/shitbox/dashboard/sse.py` — SSE stream structure; understand before adding any new SSE fields (Phase 13 will extend this, not Phase 12).

### Engine wiring
- `src/shitbox/events/engine.py` — UnifiedEngine; where new services are instantiated and started. Follow existing service wiring pattern.

### Requirements
- `.planning/REQUIREMENTS.md` — NOTE-01, NOTE-02, FUEL-01, FUEL-02 are this phase's requirements.

### Project decisions
- `.planning/PROJECT.md` — Offline-first principle, cost-exclusion decision, WAL SQLite.

No external specs — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/shitbox/dashboard/snapshot.py` — `read_snapshot()` returns `lat`, `lng`, `gps_fix_mode` directly. GPS snapshot for note/fuel capture requires no new infrastructure.
- `src/shitbox/dashboard/server.py` — `build_app()` accepts a `db` param convention from research; add logbook router here.
- `src/shitbox/dashboard/static/index.html` — Alpine.js + Tailwind already in use. Modal pattern should follow existing Alpine `x-show`/`x-data` conventions.
- `src/shitbox/storage/database.py` — Existing `_migrate()` method with version checks; v6 migration slots in cleanly.

### Established Patterns
- Schema migration: increment `SCHEMA_VERSION`, add `CREATE TABLE IF NOT EXISTS` to `SCHEMA_SQL`, add migration logic in `_migrate()` for `current_version < N`.
- Service lifecycle: `start()` / `stop()` daemon thread pattern — logbook REST is stateless so no new service thread needed; it's just a router.
- Logging: `structlog` with keyword arguments throughout — follow `log.info("notes_saved", note_id=..., gps_stale=...)`.
- Config: new config fields go in `src/shitbox/utils/config.py` as `@dataclass` fields; wired into `load_config()` via `_dict_to_dataclass`.

### Integration Points
- `CaptureSyncService.__init__()` — add `_json_generators: dict` initialisation.
- `CaptureSyncService._do_sync_inner()` — call registered generators before the existing rsync two-pass.
- `build_app()` in `server.py` — include new `logbook.router`.
- `UnifiedEngine.__init__()` — register generators with CaptureSyncService after constructing EventStorage and the new logbook storage objects.
- `UnifiedEngine.start()` / `stop()` — no new service thread; logbook is REST-only.

</code_context>

<specifics>
## Specific Ideas

- "Modal overlays" on the existing dashboard — not a new page, not tabs. Live telemetry stays visible behind.
- "+ Note" and "+ Fuel" buttons in the dashboard UI as the entry triggers.
- GPS stale warning in modal: "Location from X minutes ago" before submitting.
- Fuel cost stored in `fuel_stops` table but **never emitted in JSON exports**.
- Fuel efficiency calculated at query time from distance/volume, not stored as a column.

</specifics>

<deferred>
## Deferred Ideas

- **simple-keyboard (on-screen keyboard)**: Noted as available for Phase 17 if the kiosk display needs text entry without a physical keyboard. Not needed here since USB keyboard/trackpad is the entry method.
- **Temperature sensors missing from SSE stream** (todo): Monitoring concern — belongs in Phase 15 (Undervoltage and Monitoring).
- **Driver field on notes/fuel**: Notes and fuel stops don't have a driver attribution field in Phase 12 — Phase 13 adds driver tracking to the DB, and Phase 13 can back-fill the relationship via the driver_stints table.
- **Note categories/tags**: Out of scope — freeform text is sufficient for this milestone.
- **Fuel stop history view in dashboard**: Out of scope — data capture only in Phase 12; display on website is Phase 18.

</deferred>

---

*Phase: 12-schema-foundation-and-logbook-api*
*Context gathered: 2026-04-09*
