# Phase 10: Live Dashboard with offline map - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

A local web dashboard served by the shitbox daemon that displays live telemetry (GPS, speed, G-forces, IMU/SoC temps, sync status), recent events, and an offline map of the rally route with current position. Reachable from the on-board Chromium kiosk and from any phone on the rally wifi. Read-only for this phase — crew/fuel/blog/breakdowns persistence is Phase 11+.

The capture path is sacred: nothing in this phase may block, slow, or destabilise the 100 Hz IMU sampler or the existing storage/sync paths.

</domain>

<decisions>
## Implementation Decisions

### Server architecture
- **D-01:** FastAPI runs **in-process** inside `UnifiedEngine`, in its own daemon thread, using uvicorn programmatically. Lifecycle is owned by the engine — start with `start()`, stop with `stop()`, alongside the existing services.
- **D-02:** **Capture path is sacred.** All web reads go through a **lock-free snapshot dict** updated by the high-rate path (single writer, many readers; copy-on-write or `dict.copy()` per read). Web code never holds locks the sampler needs and never blocks on I/O the capture path depends on.
- **D-03:** Hard cap of **8 concurrent SSE clients**; new connections beyond the cap are rejected with 503. Prevents a runaway phone from eating memory or scheduler time.
- **D-04:** Web subsystem failing (uvicorn crash, port bind error, exception in a handler) **must not** take down the daemon. Catch and log via `structlog`, keep capturing.
- **D-05:** Listen on `0.0.0.0:8080` so both `localhost` (kiosk) and the Pi's LAN IPs (phones on rally wifi) work. No auth.

### Module layout
- **D-06:** New package: **`src/shitbox/dashboard/`**. Will grow in Phase 11 to hold the persistence/forms code as well. Suggested initial files: `server.py` (FastAPI app + lifecycle), `snapshot.py` (lock-free shared state), `sse.py` (SSE endpoints), `tiles.py` (MBTiles serving), `static/` (vendored frontend assets).

### Live data transport
- **D-07:** **SSE** (server-sent events) for live telemetry. Auto-reconnects on flaky wifi, no framing weirdness, no ping/pong bookkeeping.
- **D-08:** **Two SSE streams** at different rates so we don't ship slow-changing data fast:
  - **`/sse/fast`** at **10 Hz** — speed, G-forces (X/Y/Z), heading. Used by the gauge and the speed display.
  - **`/sse/slow`** at **1 Hz** — GPS fix mode + sat count + HDOP, lat/lng for the map breadcrumb, IMU temp, SoC temp, Prometheus sync status, current driver placeholder, current event count.
- **D-09:** Events are pushed on a **third stream `/sse/events`** as they happen (not polled), so the bottom event scroll updates instantly when an event is detected. Stream sends the last 10 on connect, then incremental ones live.

### Frontend
- **D-10:** **Single HTML file** served from `dashboard/static/index.html`. **Alpine.js + Tailwind + Leaflet**, all **vendored** into `dashboard/static/vendor/` — no CDN at runtime, no build step. Versions pinned in repo.
- **D-11:** Layout — top bar (GPS fix/sat/HDOP, speed, driver placeholder, sync status), main split (G-force gauge as X/Y dot on a circle, IMU + SoC temps as numeric tiles, map), bottom strip (last 10 events, scrolling). Mobile reflows to a single column.
- **D-12:** **No voltage / INA219 readout** on screen for this phase.

### G-force gauge
- **D-13:** **Auto-ranging** scale that grows to peak — display priority is "looks cool", not measurement accuracy. Capture/storage paths remain unaffected and continue to use real values.
- **D-14:** Auto-range decay: scale shrinks back down slowly (e.g. over 30–60 s) so the gauge doesn't stay zoomed-out forever after a single big hit. Planner's discretion on the exact decay.

### Map
- **D-15:** Tile source: **CartoDB dark** raster tiles, pre-downloaded as **MBTiles** (single SQLite file) and stored under `data_dir`. Matches the dark theme of shit-of-theseus.com.
- **D-16:** Tile endpoint: `GET /tiles/{z}/{x}/{y}.png` reads from the MBTiles file. SQLite is already a project dependency. 404 on missing tiles (Leaflet handles gracefully).
- **D-17:** Pre-download **corridor: 20 km either side** of the route line built from `config/config.yaml` waypoints. Disk is plentiful (500 GB NVMe), prefer over-fetch to running off the map on a detour.
- **D-18:** Pre-download **zoom range 5–15** — country overview down to "which side road am I on". Planner can adjust if size estimates are wildly off.
- **D-19:** **One-shot pre-download tool** lives in **`tools/`** (not part of the daemon). Run manually when the route changes or when topping up tiles. Reads waypoints from `config/config.yaml`, walks the tile pyramid, fetches tiles politely (rate-limited, descriptive User-Agent), writes MBTiles. Skips already-present tiles so it can be re-run cheaply.
- **D-20:** **Map follow behaviour: auto-recentre after 10 s of no user interaction.** Always-follow fights the user when they pan; free-pan-only is bad for glance use. 10 s idle timeout is the stable middle. Frontend tracks Leaflet drag/zoom events and resets a timer.
- **D-21:** Map shows: live position dot, breadcrumb of recent GPS fixes (last ~5 minutes, planner's discretion on point count), event markers as they fire on `/sse/events`.

### Event display
- **D-22:** Bottom strip shows **last 10 events** (HIGH_G, BIG_CORNER, HARD_BRAKE, ROUGH_ROAD, MANUAL/BUTTON, BOOT). Reuses the existing event type → colour mapping from shit-of-theseus.com (HIGH_G red, BIG_CORNER amber, HARD_BRAKE red, ROUGH_ROAD purple, MANUAL/BUTTON green, BOOT blue) — frontend mirror, not a backend dependency.

### Out of scope (deferred)
- **D-23:** All Phase 11 stuff — driver swaps, refuel logging, blog entries, breakdown counts. New SQLite tables in the same DB and new POST endpoints will land in Phase 11.

### Claude's Discretion
- Exact uvicorn config (workers, log level — but must integrate with `structlog`)
- Snapshot dict update mechanism (set new dict reference vs in-place update under a quick lock)
- Breadcrumb point count and decimation strategy
- G-gauge auto-range decay curve and timing
- Tailwind config approach (precompiled CSS file in vendor/, or twind/play CDN baked in offline)
- SSE keepalive interval
- Frontend vendor versions (pin to current stable at time of implementation)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & roadmap
- `.planning/PROJECT.md` — Vision, principles, "data capture trumps everything"
- `.planning/ROADMAP.md` — Phase 10 entry
- `CLAUDE.md` — Project conventions (structlog, ruff line 100, threading model, hardware degradation philosophy)

### Existing daemon code (the integration surface)
- `src/shitbox/events/engine.py` — `UnifiedEngine` lifecycle and where the new `dashboard` subsystem must hook in (`__init__`, `start()`, `stop()`)
- `src/shitbox/events/sampler.py` — High-rate IMU loop. **Read-only reference** — never to be touched or slowed by web code
- `src/shitbox/events/ring_buffer.py` — Pre-event IMU buffer; understand the data shape that will feed `/sse/fast`
- `src/shitbox/events/detector.py` — Event types and detection state machine; informs event payload schema for `/sse/events`
- `src/shitbox/storage/database.py` — SQLite WAL + write-lock pattern. The dashboard reads but does not write in Phase 10
- `src/shitbox/sync/connection.py` — Used for Prometheus sync status indicator
- `src/shitbox/sync/batch_sync.py` — Cursor pattern for "what's been synced" — informs the sync status badge
- `src/shitbox/utils/config.py` — Where the dashboard config dataclass goes; rally route waypoints live in `sensors.gps.route.waypoints`

### Existing dashboard reference
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html` — Existing public dashboard. Use for visual style reference (dark theme palette, event badge colours, Leaflet usage). **Do not depend on it** — Phase 10 is fully self-contained on the Pi.

### Add-a-service pattern
- `CLAUDE.md` § "Adding a New Service (Pattern)" — `BatchSyncService` / `CaptureSyncService` lifecycle template that the dashboard subsystem should mirror (config dataclass, daemon thread, start/stop, engine wiring)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`UnifiedEngine` lifecycle pattern** — Existing services (`BatchSyncService`, `CaptureSyncService`) already follow a `start()`/`stop()` daemon-thread template. The dashboard subsystem should mirror this exactly so engine wiring is uniform.
- **`structlog` keyword logging** — Established convention; the dashboard must use the same so logs are consistent.
- **SQLite WAL + write-lock** — Already in `storage/database.py`. Phase 10 only reads, but Phase 11's new tables will reuse this infrastructure.
- **Event type → colour mapping** — Already exists on shit-of-theseus.com webroot. Mirror it client-side in the new `index.html`.

### Established Patterns
- **Hierarchical YAML config → nested dataclasses** — Add a `dashboard:` section to `config/config.yaml` and a `DashboardConfig` dataclass to `utils/config.py`, wired through `_dict_to_dataclass`.
- **Hardware graceful degradation** — Same philosophy applies to the web subsystem: if it fails to start (port in use, missing tiles), the daemon must keep capturing.

### Integration Points
- **`UnifiedEngine.__init__`** — instantiate `DashboardServer` behind a config guard
- **`UnifiedEngine.start()` / `stop()`** — start and stop the dashboard alongside other services
- **High-rate sample loop** — must update the snapshot dict (single writer); this is the only contact between the capture path and the web path
- **Event detection callback** — must push events into the `/sse/events` queue (non-blocking, drop if full)
- **`config/config.yaml`** — new `dashboard:` section
- **`tools/`** — new pre-download script (or new directory if `tools/` doesn't exist yet)

</code_context>

<specifics>
## Specific Ideas

- Display priority is "looks cool" for the live G-gauge (auto-range), accuracy lives in the captured data
- Match the dark visual style of shit-of-theseus.com so the Pi screen and the public site feel like the same project
- 500 GB NVMe — over-fetch tiles rather than risk falling off the map on a detour
- "Most people won't be wankers" — no auth, trust the rally wifi
- Phone access matters: layout must reflow to a single column on mobile
- Chromium kiosk URL: `http://localhost:8080`

</specifics>

<deferred>
## Deferred Ideas

### For Phase 11 (Crew & Trip Log)
- Driver swap logging (who's currently driving)
- Refuel entries (litres, location, $/L, odometer)
- Short blog posts during the trip
- Breakdown count and notes
- New SQLite tables in the existing data DB
- Form-based POST endpoints
- Optional: batch-sync these new tables upstream the same way as telemetry

### Possible later
- Voltage / INA219 readout on the dashboard (excluded for Phase 10)
- Self-rendered tiles via tilemaker (instead of pre-downloaded raster) if the OSM tile policy ever becomes a problem
- Live video preview embedded in the dashboard (separate phase)

</deferred>

---

*Phase: 10-live-dashboard-with-offline-map*
*Context gathered: 2026-04-09*
