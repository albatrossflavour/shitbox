# Phase 17: Driver Display — Research

**Researched:** 2026-04-10
**Domain:** Alpine.js dashboard restructure, SSE alert bridge, temperature sensor fix
**Confidence:** HIGH — all findings from direct code inspection, no external sources needed

---

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Rework the existing `dashboard/static/index.html` into a kiosk-first layout.
  Phone and laptop browser layout is dropped. Target is 800x480 landscape only. Existing modals
  (notes, fuel, driver stats) stay in the HTML but are not a layout priority.
- **D-04:** Two overlay categories, both auto-dismiss:
  - Telemetry event overlays (HIGH_G, HARD_BRAKE, BIG_CORNER, ROUGH_ROAD, MANUAL/BUTTON): 3 seconds
  - System alert overlays (undervoltage, thermal warning, thermal critical): 10 seconds, red background #da3633
- **D-05:** Bridge mechanism: add `dashboard_push_event()` calls in `thermal_monitor.py`
  `_check_thermal()` and `_check_throttled()` alongside existing TTS calls.
  Payload: `{"type": "ALERT", "subtype": "UNDERVOLTAGE" | "THERMAL_WARNING" | "THERMAL_CRITICAL", "message": "..."}`
- **D-06:** Only one overlay visible at a time. New overlay replaces existing (last-write wins).
- **D-07:** Event ticker shows last 5 events (down from 10). New events push in from the top.
  Each entry: event type badge + peak G + elapsed time ("2m ago").
- **D-08:** Active driver name shown in top strip. Updates from `active_driver` field in `/sse/slow`.
  No driver set: show dash.
- **D-09:** Temperature sensors showing `-- °C` is folded into scope. Planner must investigate
  and fix before kiosk is considered done.

### Claude's Discretion

- Exact CSS proportions for 800x480 (top strip height, centre split ratio, ticker height)
- G-force circle sizing
- Haversine implementation for distance-to-waypoint (inline JS or utility)
- Map overlay z-index, close button, animation
- Font sizes for speed display
- Whether driver name flashes on driver change
- Tailwind utility classes

### Deferred Ideas (OUT OF SCOPE)

- On-screen keyboard for driver name entry
- Per-driver event counts on kiosk display (Phase 18)
- Live video preview embedded in kiosk (separate phase)
- Phone/tablet-optimised responsive layout

</user_constraints>

---

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DISP-01 | Fullscreen kiosk on 7" touchscreen: speed, G-force circle, temperatures, GPS status, sync status | Layout restructure + temperature bug fix |
| DISP-02 | Live event ticker: event type + peak G, scrolling real-time | Existing ticker reworked to 5 events, push-from-top |
| DISP-03 | Display shows currently active driver, updated live from SSE | `active_driver` already in `/sse/slow` payload |
| DISP-04 | Critical events trigger visible alert overlays | New `ALERT` type in SSE events stream; thermal bridge |

</phase_requirements>

---

## Summary

This phase is almost entirely a frontend rework of an already-functional system. The backend plumbing
is in good shape — three SSE streams running, Alpine.js data properties all wired, event push
mechanism solid. What the planner needs to do is three distinct things:

1. **Restructure the HTML layout** for 800x480. The current layout is a responsive two-column grid;
   that needs to become a fixed kiosk layout with a dominant speed display, resized G-gauge, a MAP
   button that opens an overlay, data tiles for temps and waypoint distance, and a 5-item event
   ticker at the bottom.

2. **Fix the temperature sensor bug.** This is the most important backend change. `imu_temp_c` in
   the snapshot is populated from `SensorType.ENVIRONMENT` readings only (BME680). The DS18B20
   collector fires `SensorType.TEMPERATURE` readings and the `_on_reading()` callback does not
   pick them up for the snapshot. Additionally, the BME680 is currently failing to initialise at
   daemon startup (boot timing issue). So "CABIN TEMP" shows `--` for two compounding reasons.
   The fix must address both: populate snapshot from DS18B20 as a fallback, and add a retry loop
   to BME680 init.

3. **Bridge thermal/undervoltage alerts into the SSE stream.** `thermal_monitor.py` currently
   only calls `beep_*()` and `speak_*()` functions. Adding `dashboard_push_event()` calls at the
   same points is a small, surgical change — `push_event()` is thread-safe (queue-based,
   non-blocking).

The kiosk display setup (Chromium autostart) is **not in the repo** — it is configured directly on
the Pi. The planner should include a deployment note for the operator to verify/create the Chromium
autostart service, but this is not a code task.

**Primary recommendation:** Fix the temperature bug first (it blocks DISP-01), then restructure
the HTML, then add the alert bridge.

---

## Standard Stack

No new libraries needed. Everything in this phase uses what is already deployed.

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Alpine.js | 3.x (vendored) | Reactive data bindings | Already in use — all SSE handlers wired |
| Tailwind CSS | 3.x (vendored) | Utility CSS | Already in use — card/badge classes defined |
| Leaflet.js | 1.9.x (vendored) | Map overlay | Already initialised in index.html |
| FastAPI / sse-starlette | current | SSE router | Already powering all three streams |

### No new npm packages or Python packages are required for this phase.

---

## Architecture Patterns

### Current HTML Structure (to be replaced)

```
<body x-data="dashboard()">
  <header>  <!-- top bar: GPS badge | speed | driver | notes/fuel buttons | sync badge -->
  <main class="grid md:grid-cols-2">
    <section>  <!-- G-gauge + two temp tiles (2-col grid) -->
    <section>  <!-- Leaflet map, 60vh height -->
  </main>
  <footer>  <!-- horizontal scrolling event strip, 88px -->
  <!-- modals: note, fuel, driver stats -->
  <script>function dashboard() { ... }</script>
```

### Target Kiosk Structure (800x480, fixed heights)

```
<body x-data="dashboard()" style="height:480px; overflow:hidden">
  <header>  <!-- h: ~72px. Speed (dominant), driver name, GPS badge, sync badge -->
  <main style="height: ~280px; display:flex">
    <div style="width:~50%">  <!-- G-gauge canvas, enlarged -->
    <div style="width:~50%; display:flex; flex-direction:column; gap:8px">
      <!-- temp tile: CABIN / SoC -->
      <!-- distance-to-waypoint tile -->
      <!-- MAP button -->
  </main>
  <footer>  <!-- h: ~88px. 5-item event ticker, vertical (push-from-top) -->
  <!-- MAP overlay: position:fixed inset:0 z-index:100; contains Leaflet map -->
  <!-- alert overlay: position:fixed inset:0 z-index:200; auto-dismisses -->
  <!-- existing modals: note, fuel, driver stats (z-index:1000, unchanged) -->
  <script>function dashboard() { ... }</script>
```

Key layout points:
- Total: 72 + 280 + 88 = 440px, leaving 40px margin for rounding. Exact numbers are planner's call.
- Speed: `text-8xl` or `text-9xl` — needs to be readable at a glance from the passenger seat.
- G-gauge canvas: enlarge from 400x400 to fill the left half of main (approximately 380x280).
- Map is NOT in the main layout; it lives in a fixed overlay, shown/hidden by `x-show="showMap"`.

### Pattern: MAP Overlay

The existing Leaflet map is already initialised in `initMap()`. The overlay reuses the same `#map`
div. The planner just needs to wrap it in a `position:fixed` container with `x-show="showMap"`,
ensure Leaflet `.invalidateSize()` is called when the overlay opens (Leaflet caches viewport
dimensions and breaks when its container is hidden on init), and provide a close tap target.

```javascript
// In dashboard():
showMap: false,

// In initMap() — map already created, just needs invalidateSize on show:
openMap() {
  this.showMap = true;
  this.$nextTick(() => this.map.invalidateSize());
},
closeMap() {
  this.showMap = false;
},
```

### Pattern: Alert Overlay

```javascript
// In dashboard():
alertOverlay: null,  // { message, colour, type } or null
_alertTimer: null,

showAlert(payload) {
  if (this._alertTimer) clearTimeout(this._alertTimer);
  const isSystem = payload.type === 'ALERT';
  this.alertOverlay = {
    message: isSystem ? payload.message : `${payload.type} · ${(payload.peak_g||0).toFixed(1)}g`,
    colour: isSystem ? '#da3633' : (EVENT_COLOURS[payload.type] || '#8b949e'),
  };
  const duration = isSystem ? 10000 : 3000;
  this._alertTimer = setTimeout(() => { this.alertOverlay = null; }, duration);
},
```

The `openEvents()` SSE handler dispatches to `showAlert()` for all incoming events. Telemetry
events (existing types) trigger 3-second overlays. Events with `type === 'ALERT'` trigger 10-second
system alert overlays.

### Pattern: Event Ticker — Push From Top

The existing ticker is a horizontal `x-for` loop showing badge pills. The kiosk version is a
vertical 5-item list, newest on top. The Alpine data update is already correct — `events.unshift(ev)`
and `events.pop()` when length > 5. The CSS transition is a planner call (slide-in or fade).

```javascript
// Change in openEvents():
this.events.unshift(ev);
if (this.events.length > 5) this.events.pop();  // was 10, now 5
this.showAlert(ev);  // NEW: trigger overlay for every incoming event
```

### Pattern: Elapsed Time Display

```javascript
relativeTime(ts) {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  const m = Math.floor(diff / 60);
  return m < 60 ? `${m}m ago` : `${Math.floor(m/60)}h ${m%60}m ago`;
},
```

### Pattern: Distance to Waypoint

Waypoints are already in `config/config.yaml` under `sensors.gps.route.waypoints`. There are 8
waypoints: Port Douglas through to Melbourne, ordered by day. The distance calculation is pure
client-side JS — no backend changes.

**Approach:** Bake the ordered waypoint array directly into the Alpine data function as a JS literal
(copy from config.yaml). The JS then runs haversine against the current `lat`/`lng` from the slow
SSE stream to find the nearest waypoint not yet passed, and displays distance.

```javascript
// Waypoints array baked into dashboard() data:
_waypoints: [
  { name: "Port Douglas", lat: -16.4838, lng: 145.4673 },
  { name: "The Oasis Roadhouse", lat: -18.8797, lng: 144.5436 },
  { name: "Aramac", lat: -22.9667, lng: 145.2333 },
  { name: "Toompine", lat: -27.8500, lng: 144.4833 },
  { name: "Louth", lat: -30.5333, lng: 145.1167 },
  { name: "Narrandera", lat: -34.7475, lng: 146.5533 },
  { name: "Dargo", lat: -37.4975, lng: 147.2692 },
  { name: "Melbourne", lat: -37.8679, lng: 144.9743 },
],
waypointText: '-- km to --',

// Haversine helper (inline, no dependencies):
_haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
            Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
},

// Called in openSlow() handler when lat/lng arrive:
_updateWaypoint(lat, lng) {
  // Find nearest waypoint (simple: find closest; could also track "passed" by proximity)
  let best = null, bestDist = Infinity;
  for (const wp of this._waypoints) {
    const d = this._haversineKm(lat, lng, wp.lat, wp.lng);
    if (d < bestDist) { bestDist = d; best = wp; }
  }
  if (best) this.waypointText = `${Math.round(bestDist)} km to ${best.name}`;
},
```

Note: "nearest waypoint" is fine. A "next waypoint not yet passed" approach requires tracking which
waypoints have been visited, which adds state. Simple nearest is sufficient for co-driver glance use.
The planner can choose either; research recommends nearest for simplicity.

### Anti-Patterns to Avoid

- **Calling `this.map.invalidateSize()` synchronously when opening the overlay.** Leaflet needs the
  container to be visible in the DOM first. Always use `this.$nextTick(...)`.
- **Creating a second Leaflet instance.** The existing map in `initMap()` is the one to reuse.
  Show/hide its wrapper container, do not call `L.map()` again.
- **Adding new SSE keys to the snapshot.** CONTEXT.md D-09 is explicit: no new snapshot keys.
  The `ALERT` event goes through the existing `event_queue` / `push_event()` path.
- **Blocking `_on_reading()` with retry logic.** The callback runs from collector threads; any
  sleep blocks that collector's sample loop. Retry logic for BME680 belongs in its `setup()`,
  not in the callback.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Haversine distance | External library | 6-line inline JS function | Dependency-free, offline, trivial formula |
| SSE alert delivery | New SSE stream | Existing `push_event()` + `event_queue` | Already thread-safe, already connected to frontend |
| Auto-dismiss timer | Complex queue | `setTimeout` + `clearTimeout` | Last-write-wins is a single timer swap |

---

## Temperature Sensor Bug — Root Cause Analysis

**Confidence: HIGH** — confirmed by direct code inspection.

### Bug 1: `_cabin_temp_c` only updated from `SensorType.ENVIRONMENT`

In `engine.py` `_on_reading()` (line 769):

```python
if reading.sensor_type == SensorType.ENVIRONMENT and reading.env_temp_celsius is not None:
    self._cabin_temp_c = reading.env_temp_celsius
```

The DS18B20 collector emits `SensorType.TEMPERATURE` readings. The `_on_reading()` callback writes
them to SQLite but **does not update `_cabin_temp_c`**. The `_cabin_temp_c` is what populates
`imu_temp_c` in the snapshot, which becomes `imu_temp` in the SSE slow stream.

The SSE field name is correct (`imu_temp` in sse.py, read as `d.imu_temp` in index.html). There is
no field name mismatch. The value is simply never written because the wrong sensor type is checked.

### Bug 2: BME680 failing to init (boot timing)

`STATE.md` records: BME680 at 0x77 physically present (confirmed i2cdetect) but logs
`No I2C device at address: 0x77` at daemon startup. This is the backup source for `_cabin_temp_c`.
With both the DS18B20 path not updating the snapshot AND the BME680 failing to init, the result
is `imu_temp_c: null` → `imu_temp: null` → `--°C` on the dashboard.

### Fix (both parts)

**Part A: Update `_on_reading()` to also capture DS18B20 readings.**

The DS18B20 `Reading` object uses `temp_celsius` (not `env_temp_celsius`). The planner needs to
identify which DS18B20 role to use as the "cabin temp" proxy. Given the two probes are `exterior`
and `engine_bay`, neither is literally "cabin temp". The BME680 (environment sensor) is the true
cabin temp source. However, until BME680 is reliable, using the `exterior` probe temperature
(or the first available DS18B20 reading) is a reasonable fallback.

Looking at `DS18B20Collector.to_reading()`:

```python
def to_reading(self, data: "DS18B20Reading") -> Reading:
    return Reading(
        sensor_type=SensorType.TEMPERATURE,
        temp_celsius=data.temp_celsius,
    )
```

The `Reading` model has `temp_celsius` as a field. The snapshot update should be extended:

```python
def _on_reading(self, reading: Reading) -> None:
    try:
        self.database.insert_reading(reading)
        self.telemetry_readings += 1
        if reading.sensor_type == SensorType.ENVIRONMENT and reading.env_temp_celsius is not None:
            self._cabin_temp_c = reading.env_temp_celsius
        elif reading.sensor_type == SensorType.TEMPERATURE and reading.temp_celsius is not None:
            # DS18B20 fallback — updates cabin temp until BME680 is stable
            self._cabin_temp_c = reading.temp_celsius
    except Exception as e:
        log.error("v2_collector_db_write_error", error=str(e))
```

**Part B: Add retry loop to BME680 `setup()`.**

The environment collector is `self._environment_collector` in the engine. Looking at the init
block (line 450-451 region), it's a legacy path gated on `config.environment_enabled`. The real
v2 path is the separate `EnvironmentCollector` class. The planner should check
`src/shitbox/collectors/environment.py` and add a retry with backoff in its `setup()` method.

Note: the planner should confirm whether `EnvironmentCollector` (BME680) is used via the legacy
path or via a v2 collector. The engine code at line 450 references `_environment_collector` with
"legacy" comment. However, the STATE.md records BME680 is still failing — this warrants reading
the environment collector setup code before writing the fix plan.

### SSE Field Name Mapping — Confirmed Correct

| Snapshot key | SSE key (sse.py) | JS variable (index.html) |
|---|---|---|
| `imu_temp_c` | `imu_temp` | `d.imu_temp` |
| `soc_temp_c` | `soc_temp` | `d.soc_temp` |
| `active_driver` | `active_driver` | `d.active_driver` |
| `lat` | `lat` | `d.lat` |
| `lng` | `lng` | `d.lng` |

No field name mismatches. The entire `--°C` problem is the `_on_reading()` type guard.

---

## Alert Bridge — Thermal Monitor

### Current State

`thermal_monitor.py` has three alert call sites:

1. `_check_thermal()` — warning threshold (≥70°C):
   ```python
   beep_thermal_warning()
   speak_thermal_warning()
   ```

2. `_check_thermal()` — critical threshold (≥80°C):
   ```python
   beep_thermal_critical()
   speak_thermal_critical()
   ```

3. `_check_throttled()` — undervoltage (bit 0 of throttle bitmask):
   ```python
   beep_under_voltage()
   speak_under_voltage()
   ```

### Required Change

Import `push_event` at the top of `thermal_monitor.py` (same pattern as existing imports):

```python
try:
    from shitbox.dashboard.sse import push_event as dashboard_push_event
except ImportError:
    def dashboard_push_event(event: dict) -> None:  # type: ignore[misc]
        pass
```

Then at each alert site, add a `dashboard_push_event()` call alongside the existing TTS calls.

Example for warning:
```python
beep_thermal_warning()
speak_thermal_warning()
dashboard_push_event({
    "type": "ALERT",
    "subtype": "THERMAL_WARNING",
    "message": f"THERMAL WARNING: {round(temp, 1)}°C",
    "ts": time.time(),
})
```

**Thread-safety:** `push_event()` uses `queue.Queue.put_nowait()` — it is non-blocking and
thread-safe. The thermal monitor runs in a daemon thread. No locking changes needed.

**Import guard:** The `try/except ImportError` pattern is already used throughout `thermal_monitor.py`
for buzzer and speaker imports. Wrapping the dashboard import the same way ensures the thermal
monitor still works if the dashboard module is somehow unavailable.

---

## Chromium Kiosk — Not in Repo

There is **no Chromium autostart service or config in the shitbox repository**. The kiosk setup
is managed directly on the Pi. From Phase 10 CONTEXT.md: `Chromium kiosk URL: http://localhost:8080`.

From STATE.md (hardware session notes): "Display boot race: still intermittent. Suspect
`display_auto_detect=1` in config.txt probing absent DSI-1. Next step: set `display_auto_detect=0`."

The plan should include a **deployment note** (not a code task) reminding the operator to verify
or create the Chromium kiosk autostart on the Pi. A typical RPi kiosk autostart entry is a `.desktop`
file in `~/.config/autostart/` or a `@chromium-browser` line in `/etc/xdg/lxsession/LXDE-pi/autostart`.
The URL to load: `http://localhost:8080`. Flags: `--kiosk --noerrdialogs --disable-infobars`.

The `display_auto_detect=0` fix is a separate hardware task, already recorded in STATE.md.
The planner should note it but it is not a code task for this phase.

---

## Common Pitfalls

### Pitfall 1: Leaflet map breaks when container is hidden at init

**What goes wrong:** If `showMap` starts as `false`, Leaflet initialises with a zero-size container
and renders nothing (or misaligned tiles) when the overlay is first opened.
**Why it happens:** Leaflet caches viewport size on init. If the container has `display:none`,
the cached size is 0x0.
**How to avoid:** Call `this.map.invalidateSize()` after opening the overlay. Must be called inside
`this.$nextTick()` so Alpine has already applied `x-show` before Leaflet measures.
**Warning signs:** Map shows grey tiles or a tiny dot; panning doesn't work.

### Pitfall 2: Fixed height layout overflows on 480px display

**What goes wrong:** The `<body>` height is 480px. If header + main + footer exceeds 480px,
the ticker gets clipped or the page scrolls, breaking the "no scroll" kiosk feel.
**How to avoid:** Use explicit `height` and `flex-shrink:0` on header and footer. Let main fill
the remaining space with `flex-grow:1` or explicit calculated height. Test with `height:480px`
on the `<body>` and `overflow:hidden`.
**Warning signs:** Scrollbar appears; bottom strip partially visible.

### Pitfall 3: DS18B20 readings arrive before/after BME680 — race in `_cabin_temp_c`

**What goes wrong:** Both collectors update `_cabin_temp_c` from different threads. The last
writer wins, which could be either sensor.
**Why it happens:** The fix in Part A makes both sensor types update the same variable.
**How to avoid:** This is fine in practice — both read from the same physical location (cabin),
and the snapshot update is a GIL-protected assignment. The note is: the dashboard shows "whichever
sensor last updated", which is acceptable. Add a log line to indicate which sensor is providing
the value if debugging is needed later.

### Pitfall 4: Alert overlay blocks touch input to modals

**What goes wrong:** If the alert overlay `div` is positioned above the modals in z-index
(z:200) but a modal opens at the same time, the modal is unreachable.
**How to avoid:** Set alert overlay z-index below modals (z:150). Modals are z:1000. Order:
`alert overlay (150) < map overlay (100) < modals (1000)`. Alert auto-dismisses anyway.

### Pitfall 5: `elapsed time` display is stale after first render

**What goes wrong:** The "2m ago" display on the event ticker uses `Date.now()` at render time.
After a few minutes the "2m ago" is wrong — it keeps showing 2m even after 10 minutes.
**How to avoid:** Use a `setInterval` to trigger Alpine reactivity for time values, or recompute
elapsed time in the `drawGauge()` animation loop. Simplest: a 1-second `setInterval` in `init()`
that updates a `now` property, used in a computed function.

---

## Waypoint Config Shape

From `config/config.yaml` — the 8 ordered waypoints:

```yaml
route:
  waypoints:
    - { name: "Port Douglas",       day: 1, lat: -16.4838, lon: 145.4673 }
    - { name: "The Oasis Roadhouse",day: 1, lat: -18.8797, lon: 144.5436 }
    - { name: "Aramac",             day: 2, lat: -22.9667, lon: 145.2333 }
    - { name: "Toompine",           day: 3, lat: -27.8500, lon: 144.4833 }
    - { name: "Louth",              day: 4, lat: -30.5333, lon: 145.1167 }
    - { name: "Narrandera",         day: 5, lat: -34.7475, lon: 146.5533 }
    - { name: "Dargo",              day: 6, lat: -37.4975, lon: 147.2692 }
    - { name: "Melbourne",          day: 7, lat: -37.8679, lon: 144.9743 }
```

Note: YAML key is `lon`, JavaScript convention is `lng`. When baking this into the Alpine data
function, use `lng` keys in the JS literal to match the SSE slow stream field names.

---

## Environment Availability

> All work is code/config changes to existing running software. No new external dependencies.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|---------|
| Alpine.js | Frontend reactivity | Vendored | 3.x | — |
| Leaflet.js | Map overlay | Vendored | 1.9.x | — |
| Tailwind CSS | Layout | Vendored | 3.x | — |
| `queue.Queue` | Alert SSE bridge | stdlib | — | — |
| Chromium (Pi) | Kiosk display | On Pi (not repo) | — | Manual verify on Pi |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run | `pytest tests/test_dashboard.py tests/test_thermal_monitor.py -x` |
| Full suite | `pytest --cov=shitbox` |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|--------------|
| DISP-01 | Kiosk layout renders at 800x480 | manual | Browser on Pi at 800x480 | N/A |
| DISP-01 | `imu_temp` in slow SSE payload is non-null when DS18B20 active | unit | `pytest tests/test_dashboard.py::test_sse_slow_schema -x` | Yes (extend) |
| DISP-01 | `_on_reading()` updates `_cabin_temp_c` for `SensorType.TEMPERATURE` | unit | `pytest tests/test_engine_boot.py -x` | Yes (add case) |
| DISP-02 | Event ticker shows 5 events max | unit | `pytest tests/test_dashboard.py -x -k ticker` | No — Wave 0 |
| DISP-03 | `active_driver` field present in slow SSE | unit | `pytest tests/test_dashboard.py::test_sse_slow_schema -x` | Yes (verify key present) |
| DISP-04 | `push_event()` called with `ALERT` type on thermal warning | unit | `pytest tests/test_thermal_monitor.py -x -k alert` | No — Wave 0 |
| DISP-04 | `push_event()` called with `ALERT` type on undervoltage | unit | `pytest tests/test_thermal_monitor.py -x -k alert` | No — Wave 0 |
| DISP-04 | Alert overlay auto-dismisses after correct duration | manual | Browser interaction | N/A |

### Sampling Rate

- Per task commit: `pytest tests/test_dashboard.py tests/test_thermal_monitor.py -x`
- Per wave merge: `pytest --cov=shitbox`
- Phase gate: full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_thermal_monitor.py` — add `test_thermal_warning_pushes_dashboard_alert()` and
  `test_undervoltage_pushes_dashboard_alert()` — covers DISP-04
- [ ] `tests/test_dashboard.py` — add `test_sse_slow_has_active_driver_key()` — covers DISP-03
- [ ] `tests/test_dashboard.py` — add `test_event_ticker_max_five()` — covers DISP-02
- [ ] `tests/test_engine_boot.py` — add `test_on_reading_temperature_updates_cabin_temp()` — covers
  DISP-01 temperature fix

---

## Open Questions

1. **Which BME680 path is active — legacy or v2 collector?**
   - What we know: engine.py line 450 has comment "Legacy environment collector (BME280 on old
     boards — kept for graceful transition)". The `EnvironmentCollector` for BME680 is also present.
   - What's unclear: Is there a v2 `EnvironmentCollector` used via `_on_reading()`, or is the BME680
     read via the legacy blocking path in `_record_telemetry()`?
   - Recommendation: **Planner must read `src/shitbox/collectors/environment.py` before writing the
     BME680 retry task.** The fix depends on which path is active.

2. **DS18B20 probe role to use for `_cabin_temp_c` fallback.**
   - What we know: Two probes — `exterior` and `engine_bay`. Neither is the cabin temp sensor.
     BME680 is the true cabin sensor.
   - What's unclear: Is `exterior` probe the most useful proxy for cabin conditions?
   - Recommendation: Use `exterior` probe as fallback (it's outside the engine bay and closer to
     cabin ambient). The label on the dashboard ("CABIN TEMP") can remain — it's a proxy label,
     not a precise description. Alternatively, the planner could rename the tile to "EXT TEMP"
     when the value comes from DS18B20. Planner's call.

3. **`display_auto_detect=0` fix — is it needed before this phase can be tested on Pi?**
   - What we know: STATE.md records intermittent display boot race. Setting `display_auto_detect=0`
     in `/boot/firmware/config.txt` is the next step.
   - Recommendation: Include as a deployment step in the plan, but not a code change task. It is a
     one-liner on the Pi and should be done as part of deploying this phase.

---

## Sources

### Primary (HIGH confidence)

- Direct inspection of `src/shitbox/dashboard/static/index.html` — 470 lines, full Alpine.js
  data function, SSE handlers, existing HTML structure
- Direct inspection of `src/shitbox/dashboard/snapshot.py` — 17-key snapshot contract confirmed
- Direct inspection of `src/shitbox/dashboard/sse.py` — SSE field names confirmed, `push_event()`
  thread-safety confirmed (queue-based)
- Direct inspection of `src/shitbox/events/engine.py` — `_on_reading()` logic, `_cabin_temp_c`
  population, `dashboard_push_event` import and call sites
- Direct inspection of `src/shitbox/health/thermal_monitor.py` — alert call sites confirmed,
  no existing `dashboard_push_event` calls
- Direct inspection of `src/shitbox/collectors/temperature.py` — DS18B20 emits
  `SensorType.TEMPERATURE`, not `SensorType.ENVIRONMENT`
- Direct inspection of `config/config.yaml` — 8 waypoints confirmed, shape and coordinates

---

## Metadata

**Confidence breakdown:**

- Temperature bug root cause: HIGH — both causes confirmed by direct code inspection
- Alert bridge approach: HIGH — `push_event()` thread-safety confirmed in sse.py source
- HTML restructure pattern: HIGH — current structure fully read and understood
- Kiosk autostart: HIGH — confirmed absent from repo, Pi-side config only
- BME680 collector path: MEDIUM — legacy vs v2 path not fully traced (Open Question 1)
- Waypoint haversine implementation: HIGH — formula is standard, offline, no library needed

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable codebase, no external APIs)
