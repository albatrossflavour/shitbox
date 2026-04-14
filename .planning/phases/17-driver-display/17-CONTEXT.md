# Phase 17: Driver Display - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Productionise the 7" touchscreen (800x480) as a fullscreen kiosk display. The existing
`dashboard/static/index.html` is reworked to be kiosk-first — phone/laptop layout is dropped.
The kiosk shows speed, G-force, active driver, temperatures, distance to next waypoint, a
scrolling event ticker, and alert overlays for both telemetry events and system alerts.

No new backend data sources. No new SSE streams. Everything the display needs already
exists in the engine and snapshot.

Phase 15 (undervoltage alerting) is a dependency for DISP-04 system alerts — the thermal
monitor already fires TTS on undervoltage/thermal events; this phase adds the SSE bridge
so the display can react too.

</domain>

<decisions>
## Implementation Decisions

### Page strategy
- **D-01:** Rework the existing `dashboard/static/index.html` into a kiosk-first layout.
  Phone and laptop browser layout is dropped — the target is 800x480 landscape only.
  The existing modals (notes, fuel, driver stats) can stay in the HTML but are not
  a layout priority — they exist behind button taps if needed.

### Layout (Claude's Discretion)
- **D-02:** 800x480 layout structure (planner has discretion on exact proportions):
  - **Top strip**: speed (large, dominant), active driver name, GPS status badge, sync badge
  - **Centre left**: G-force circle (auto-ranging, Phase 10 D-13/D-14 behaviour kept)
  - **Centre right**: data tiles — IMU temp, SoC temp, distance to next waypoint
  - **Bottom strip**: scrolling event ticker
  - **MAP button**: dedicated tap target opens a full-screen Leaflet map overlay;
    tap anywhere on the map overlay to dismiss. Map does not appear in the main layout.
- **D-03:** Distance to next waypoint replaces the always-on map in the main view.
  Calculated client-side from the current GPS lat/lng (SSE slow stream) and the ordered
  waypoints array (already in `config/config.yaml`). Show as "XX km to [waypoint name]".
  Planner decides the JS implementation approach (haversine in-page or pre-baked waypoint list).

### Alert overlays (DISP-04)
- **D-04:** Two overlay categories, both auto-dismiss, different durations:
  - **Telemetry event overlays** (HIGH_G, HARD_BRAKE, BIG_CORNER, ROUGH_ROAD, MANUAL/BUTTON):
    triggered when an event fires on `/sse/events`. Display event type + peak G. Auto-dismiss
    after **3 seconds**. Use event badge colour (existing colour mapping).
  - **System alert overlays** (undervoltage, thermal warning, thermal critical):
    triggered via a new `alert` event type pushed on the SSE events queue. Display alert
    type + message (e.g. "UNDERVOLTAGE DETECTED", "THERMAL WARNING: 75°C"). Auto-dismiss
    after **10 seconds**. Red background (#da3633) regardless of alert subtype.
- **D-05:** Bridge mechanism: the thermal monitor and undervoltage check already call
  `speak_thermal_warning()` / `speak_under_voltage()` etc. The engine must also call
  `dashboard_push_event()` with `{"type": "ALERT", "subtype": "UNDERVOLTAGE" | "THERMAL_WARNING"
  | "THERMAL_CRITICAL", "message": "..."}` at the same points. Planner locates the exact
  call sites in `engine.py` / `thermal_monitor.py`.
- **D-06:** Only one overlay visible at a time. If a second event fires while an overlay
  is showing, the new one replaces it (last-write wins). No queue of overlays.

### Event ticker (DISP-02)
- **D-07:** New events push in from the top; older events shift down. Show the last
  **5 events** in the ticker (kiosk has less vertical space than the existing 10-event list).
  Each entry: event type badge (existing colour) + peak G value + elapsed time ("2m ago").
  Planner's discretion on the CSS transition (slide-in or fade-in from top).

### Active driver display (DISP-03)
- **D-08:** Active driver name is shown prominently in the top strip. It updates live from
  the `active_driver` field already present in `/sse/slow`. No separate interaction needed
  on the kiosk — driver switching remains in the driver modal (Phase 13). If no driver is
  set, show a dash.

### Temperature sensors (folded todo)
- **D-09:** The existing todo "temperature sensors missing from dashboard SSE stream" is
  folded into this phase. The kiosk requires working temps (DISP-01). The planner must
  investigate and fix before the kiosk display is considered done. Likely causes: DS18B20
  collector init, snapshot field not populated, or SSE field name mismatch. See todo for
  investigation checklist.

### Claude's Discretion
- Exact CSS proportions for 800x480 (top strip height, centre split ratio, ticker height)
- G-force circle sizing — likely larger than current since it no longer competes with the map
- Haversine implementation for distance-to-waypoint (inline JS function or small utility)
- Map overlay z-index, close button placement, animation (slide up from bottom or fade in)
- Exact font sizes for speed display (should be very large — glanceable at a glance)
- Whether the driver name flashes/animates briefly on driver change
- Tailwind utility classes and responsive tweaks

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing dashboard code
- `src/shitbox/dashboard/static/index.html` — The file being reworked. Read fully before
  planning layout changes — all existing Alpine.js data properties, SSE handlers, and modals
  must be understood before restructuring.
- `src/shitbox/dashboard/snapshot.py` — Current 17-key snapshot contract. `active_driver`,
  `imu_temp_c`, `soc_temp_c`, `speed_kmh`, `g_x/y/z`, `lat/lng` all already present.
- `src/shitbox/dashboard/sse.py` — SSE stream structure. `push_event()` is the bridge
  function for telemetry events; system alerts use this same function with `type: "ALERT"`.

### Engine and alert sources
- `src/shitbox/events/engine.py` — `dashboard_push_event` import and call sites. Planner
  must find where thermal/undervoltage alerts are currently handled and add
  `dashboard_push_event()` calls alongside existing TTS calls.
- `src/shitbox/health/thermal_monitor.py` — `_check_thermal()` and `_check_throttled()` —
  the two methods that fire TTS alerts. System alert SSE bridge calls go here or in the
  engine callback that processes thermal monitor state.

### Config (for waypoints)
- `config/config.yaml` — `sensors.gps.route.waypoints` — ordered waypoint list used for
  distance-to-next-waypoint calculation in Phase 10 tile pre-download. Same data feeds
  the client-side distance calc.

### Prior phase context
- `.planning/phases/10-live-dashboard-with-offline-map/10-CONTEXT.md` — D-13/D-14 (G-gauge
  auto-range), D-20 (map auto-recentre), D-22 (event colour mapping). All still apply.
- `.planning/phases/13-driver-tracking/13-CONTEXT.md` — D-05 (active_driver in SSE slow),
  D-06/D-07 (driver modal Alpine.js pattern). Driver display is built on top of this.

### Requirements
- `.planning/REQUIREMENTS.md` — DISP-01, DISP-02, DISP-03, DISP-04 are this phase's
  requirements.

### No external specs
No third-party API or ADR references beyond what is listed above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Alpine.js data properties** — `speed`, `imuTemp`, `socTemp`, `activeDriver`, `events`,
  `syncBadge/Class` already wired to SSE. Kiosk rework builds on these, not from scratch.
- **Event colour mapping** — `HIGH_G: '#da3633'` etc. already in the Alpine data function.
  Reuse for both the ticker badges and the event overlay background.
- **G-force circle SVG** — existing implementation from Phase 10. Will be enlarged in
  the kiosk layout but logic unchanged.
- **Leaflet map** — already initialised in `index.html`. For the map overlay button,
  show/hide the existing map container rather than creating a new Leaflet instance.
- **`push_event()` in sse.py** — non-blocking, drop-on-full. System alert events use the
  same function with `type: "ALERT"` so the frontend event handler dispatches by type.

### Established Patterns
- **Single writer snapshot** — never add a new SSE key; use existing snapshot fields. No
  new snapshot keys needed for this phase.
- **Alpine.js x-show modals** — Phase 12/13 modal pattern. Map overlay follows this.
- **Event ticker at bottom** — existing `x-for="ev in events"` loop. Rework to show 5
  items, add push-from-top animation.

### Integration Points
- `thermal_monitor.py` `_check_thermal()` and `_check_throttled()` — add `dashboard_push_event`
  calls here, imported via the same pattern as the existing TTS calls. Be careful: thermal
  monitor runs in its own daemon thread — `push_event()` is thread-safe (uses a Queue).
- `index.html` body layout — restructure from the current top-bar + main-split + bottom-strip
  into the kiosk layout described in D-02. Keep existing Alpine data() function and SSE
  handler logic intact; change only HTML structure and CSS.

</code_context>

<specifics>
## Specific Ideas

- Speed display should be very large — primary glance datum for the co-driver
- Map is useful but not always-on; a single tap to open/close is the right trade-off
  given trackpad inaccuracy on the keyboard being used
- "Distance to checkpoint" is more operationally useful than a persistent map thumbnail
- System alert overlays are distinct from event overlays — red background, longer duration —
  because they signal something requiring attention, not just "a driving event happened"

</specifics>

<deferred>
## Deferred Ideas

- On-screen keyboard for driver name entry (noted in Phase 13 deferred — still deferred)
- Per-driver event counts on the kiosk display (Phase 18 alongside website)
- Live video preview embedded in kiosk (separate phase, noted in Phase 10 deferred)
- Phone/tablet-optimised responsive layout (dropped from scope per D-01 — may revisit
  post-rally if the dashboard is accessed frequently from phones)

### Reviewed Todos (not folded)
- None — the one matching todo (temperature sensors missing from SSE) was folded into scope (D-09).

</deferred>

---

*Phase: 17-driver-display*
*Context gathered: 2026-04-10*
