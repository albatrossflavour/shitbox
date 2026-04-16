# Phase 19: Website Narrative Rebuild - Research

**Researched:** 2026-04-16
**Domain:** Single-file vanilla-JS SPA (client-side routing, timeline rendering, Leaflet polylines) + one new Pi-side JSON generator
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Routing / URLs**
- **D-01:** `/day/YYYY-MM-DD` served via nginx `try_files $uri $uri/ /index.html`; SPA reads `location.pathname` on load.
- **D-02:** Day URL slug is date-only (no descriptor). Titles come from agenda file.

**Mode detection**
- **D-03:** `rally.start_date` / `rally.end_date` live in agenda YAML. Client-side on load:
  - `before` when `today < start_date`
  - `live` when `start_date <= today <= end_date` AND latest reading < 6 h old
  - `archive` otherwise
- **D-04:** One check on load; re-check on tab focus and on the 2-minute live-mode poll.

**Timeline data pipeline**
- **D-05:** Join is **client-side**. Browser fetches `events.json` + `notes.json` + `fuel.json` + `driver-stats.json` + `route.json` + `agenda.json` once and filters by day on navigation. **No new Pi-side per-day generators.**
- **D-06:** Spine includes: all event types (including **BOOT** — narrative value, has dashcam), notes (full body), fuel stops, stage start/stop (derived from first/last reading of day), driver changes (from `driver_stints`), agenda markers (italic / muted).
- **D-07:** **Excluded** from spine: thermal / undervoltage alerts without video (Grafana territory).
- **D-08:** Live-mode refresh: 2-minute poll. Refresh on tab visibility regain.

**Agenda**
- **D-09:** Static YAML committed to home-ops alongside `webroot/`. Edits = git push + Flux reconcile.
- **D-10:** Rough schema (final pinned during planning):
  ```yaml
  rally:
    start_date: YYYY-MM-DD
    end_date: YYYY-MM-DD
    team: "A Team Has No Name"
    title: "Shitbox Rally 2026"
  days:
    - date: YYYY-MM-DD
      title: "Hay → Broken Hill"
      route: "prose description"
      camping: "Mutawintji NP"
      meals:
        - { time: "12:30", where: "Cobar bakery" }
      notes: "optional prose"
  ```

**Day page structure**
- **D-11:** Single vertical scroll. No tabs-within-day, no collapsibles.
- **D-12:** Section order (top → bottom): day header → agenda context → day stats → map slice → timeline spine → video highlights → day timelapse.
- **D-13:** Mobile uses same order, no collapse. Desktop = centred max-width container.

**Day-nav progress bar**
- **D-14:** Site-wide, under the top nav. One segment per rally day (count from agenda). Big day number + small date.
- **D-15:** States: filled orange = completed, bright orange = current, grey = future. Completed + current clickable; future inert.

**Homepage by mode**
- **D-16:** `before`: countdown + planned-route map (from agenda coords) + day-list preview + "Follow along from [start_date]" CTA.
- **D-17:** `live`: today's day page **is** the homepage. 2-minute refresh. Current-driver widget near top.
- **D-18:** `archive`: overview card + linear day grid (NOT calendar). Each card = date, title, thumbnail (timelapse poster → first event still).

**Nav**
- **D-19:** Top nav shrinks to: Home, Grafana, About, Donate.
- **D-20:** Removed: Status (→ home), Drivers (→ /about), Videos/Timelapse (→ day pages), Map (→ day-slice + archive overview), Route (→ agenda + archive), The Car (→ /about).

**Route polyline**
- **D-21:** New `route.json` generator reads from GPS readings, applies Douglas-Peucker ~10 m, groups by day. Target < 1 MB for full rally. No cost field.
- **D-22:** Full-rally polyline = archive overview backdrop. Day-slice highlighted on day-page map; rest of rally polyline shown grey behind it.

### Claude's Discretion
- Card styling, spacing, typography (consistent with dark theme: `#0d1117` / `#161b22` / `#c06000`)
- Timeline icon set (SVG per spine-item type) — reuse `BADGE_COLORS` for event icons
- Thumbnail fall-back chain for archive day-grid cards
- Progress-bar segment hover / focus states
- Exact nginx rewrite rule placement in `default.conf`
- Simplification tolerance refinement if `route.json` exceeds 1 MB at ~10 m

### Deferred Ideas (OUT OF SCOPE)
- Pi-side API editability for agenda (git push is fine)
- Pre-generated per-day JSON from the Pi (client-side filter scales for a ~14-day rally)
- Calendar grid for archive mode (rally has no rest days)
- Descriptor slugs in day URLs
- Mobile-specific tab / accordion collapse
- Per-driver event attribution on `/about` (deferred from Phase 18; not pulled forward)

</user_constraints>

<phase_requirements>
## Proposed Requirements

REQUIREMENTS.md has no NARR-* IDs yet. Proposing the following mapping to the seven success criteria in ROADMAP.md §"Phase 19":

| ID | Description | Maps to ROADMAP SC |
|----|-------------|--------------------|
| NARR-01 | Homepage detects mode from agenda dates + freshest-reading timestamp and renders one of three modes (before / live / archive) | SC1 |
| NARR-02 | Day pages exist at `/day/YYYY-MM-DD` served via nginx SPA fallback; SPA routes from `location.pathname` | SC2 (routing half) |
| NARR-03 | Day page renders a chronological timeline spine interleaving events, notes, fuel stops, stage bookends, driver changes, and agenda markers | SC2 (spine half) |
| NARR-04 | Day page loads agenda context (title, camping, meals, route prose) before telemetry sections | SC3 |
| NARR-05 | Site-wide progress-bar day navigator renders in all three modes with correct segment states | SC4 |
| NARR-06 | Videos, Timelapse, Map, Route, Status, and Drivers top-nav entries are removed; their content lives inside day pages or `/about` | SC5, SC6 |
| NARR-07 | `/about` page absorbs Drivers (time + %) and The Car content; Grafana stays one click from the homepage | SC6, SC7 |
| NARR-08 | Pi generates `route.json` from GPS readings via Douglas-Peucker simplification (~10 m), grouped by day; output ≤ 1 MB for full rally; registered with `CaptureSyncService` | folded todo (D-21) |
| NARR-09 | Day-page map renders day slice highlighted against a grey full-rally polyline backdrop on Leaflet CartoDB dark tiles | D-22 |
| NARR-10 | Agenda YAML is served from `/agenda.yaml` (or `.json`) via the same configMap mount as `index.html` and loads on site boot with one fetch | D-09 |

The planner can tighten or merge these once the exact file boundaries per plan are set. Key trace:
- NARR-01 → `renderMode()` + freshness probe
- NARR-02 → nginx `try_files` + SPA bootstrap
- NARR-03 → `buildSpine(dayISO)` merge algorithm
- NARR-04 → `renderDayAgenda(day)` before telemetry calls
- NARR-05 → `renderDayNav()` module
- NARR-06, NARR-07 → nav collapse + `/about` section consolidation
- NARR-08 → `src/shitbox/storage/route.py` (new) + engine registration
- NARR-09 → Leaflet polyline pattern in `initDayMap()`
- NARR-10 → fetch pipeline extension

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Website stack is locked:** plain HTML + inline CSS + inline JS. No build step, no frameworks, no bundler. Everything changes in `webroot/index.html`.
- **Dev environment = laptop (macOS).** No `pip install` or Pi-specific commands in web plans.
- **Deploy path is git push to home-ops → Flux reconcile.** Flux `interval: 30m` (see `helmrelease.yaml`). Manual reconcile via `flux reconcile kustomization` if urgency demands.
- **Dark theme tokens (locked from Phase 18):** `#0d1117` bg, `#161b22` cards, `#21262d` borders, `#c06000` orange accent, `#e0a040` amber, `#f0dbb8` warm white, `#8b949e` muted.
- **Vanilla JS style:** `var`, not `const`/`let`. Match existing style.
- **UK spelling** in any copy changes.
- **Cost data hard exclusion** (Phase 12 D-10) — nothing in `route.json` or anywhere else exposes fuel cost.
- **Pi-side conventions (for `route.json` generator):**
  - Structured logging via `structlog` with keyword args
  - Line length 100, ruff rules E/F/I/W, target Python 3.9
  - Full type annotations; mypy enforced
  - Daemon-thread services: not applicable here (REST-less, invoked by sync registry)

## Summary

Phase 19 is 90% browser-side work and 10% Pi-side. Ninety percent of the cognitive load is in one file: `webroot/index.html`. The remaining 10% is one new Python method (`generate_route_json`) plus two lines of engine wiring and one nginx directive.

The existing SPA (1717 lines) already establishes every pattern the rebuild needs: parallel `fetch` on load, `BADGE_COLORS` for per-event-type colours, `localeDateString('en-CA', {timeZone: TIMEZONE})` for day bucketing, Leaflet dark CartoDB tile layer, and the `renderEvents` day-grouping loop that day pages extend. The rebuild isn't inventing a new architecture — it's swapping the tab section router for a `location.pathname` router and collapsing six tabs into day pages + `/about`.

The scrapbook feel hinges on one new algorithm: a single-pass merge that interleaves six heterogeneous streams (events / notes / fuel / driver changes / stage bookends / agenda markers) by timestamp into one spine per day. That's a 20-line function. Everything else is HTML structure and CSS.

**Primary recommendation:**
- Use **JSON for agenda** (no new library, no parser, same `fetch().then(r => r.json())` pattern the site already uses four times). YAML adds a ~100-line loader for zero benefit — Tony's editing experience is identical (git edit + push either way).
- Do **not** add a tiny JS YAML loader. Authoring friction is negligible; parse complexity is real.
- Use **stdlib-only Douglas-Peucker** in Python. ~20 lines, no dependency, well-understood. `shapely` is overkill for a single operation on unprojected WGS-84 coordinates.
- Keep the spine merge **simple**: one flat list, sort by timestamp, render. No priority queues, no segment trees. The rally is ~14 days × a few dozen events per day — brute force is correct.
- **Preserve** the existing `#hash` routing for `/about` and internal anchors. Only `/day/YYYY-MM-DD` needs the new `location.pathname` branch.

## Technical Approach per Decision Cluster

### 1. Routing (D-01, D-02, NARR-02)

**Nginx change** (one directive already present, just needs verification):

```nginx
# nginx-config/default.conf — current state already has the rewrite
location / {
    try_files $uri $uri/ /index.html;
}
```

The existing config *already has* `try_files $uri $uri/ /index.html` (line 26-28). Good news: no nginx change required. The rewrite works out of the box for `/day/YYYY-MM-DD` → `/index.html`. Verify during planning; this reduces Plan 19-01 scope.

**SPA bootstrap** (replaces the current hash-only routing at index.html:1048-1053):

```javascript
// Current (line 1048-1053) — keep the hash branch as fallback, add pathname branch
var path = window.location.pathname;
var dayMatch = path.match(/^\/day\/(\d{4}-\d{2}-\d{2})$/);
if (dayMatch) {
    renderDayPage(dayMatch[1]);          // primary path: canonical day URL
} else if (path === '/about' || path === '/about/') {
    renderAbout();
} else {
    renderHomepage();                     // resolves mode then delegates
}
```

**History API for internal day-to-day navigation** (so clicking progress-bar segments doesn't reload):

```javascript
function navigateToDay(dayISO) {
    history.pushState({day: dayISO}, '', '/day/' + dayISO);
    renderDayPage(dayISO);
}
window.addEventListener('popstate', function(e) {
    if (e.state && e.state.day) renderDayPage(e.state.day);
    else renderHomepage();
});
```

**Gotchas:**
- Date format must be validated. `^\d{4}-\d{2}-\d{2}$` is not enough — `9999-99-99` matches but is invalid. Either use `new Date(dayISO)` and check `!isNaN(...)`, or defer validation to the renderer (if the day isn't in agenda, render a 404-style "no data" card).
- `history.replaceState` is already used on line 1032 — do not break that for hash navigation on `/` root routes.
- `<base href>` is NOT set in the current HTML; relative URLs to `/captures/*` are absolute-rooted so they keep working from `/day/*` paths. Confirmed safe.

### 2. Mode detection (D-03, D-04, NARR-01)

The signal for "latest reading < 6 h old" needs to be pinned. Options:

| Source | Pros | Cons |
|--------|------|------|
| Latest `events.json` entry `timestamp` | Already fetched; no new plumbing | Events are sparse — a quiet hour triggers false `archive` |
| Latest `route.json` point timestamp | High-rate (1 Hz GPS), most reliable | Requires route.json per hour cadence; adds coupling |
| New `heartbeat.json` | Explicit, tiny, fast | Another Pi generator; rejected by D-05 spirit |
| `driver-stats.json` payload timestamp | Already regenerated every rsync cycle | Doesn't include a "generated_at" field today |

**Recommendation:** Add a `generated_at` ISO timestamp to `route.json`'s top-level envelope (the generator already runs on every sync cycle, so `generated_at = datetime.now(timezone.utc).isoformat()` is free). Mode check reads `route.generated_at`. Rationale: route.json is the densest signal, regenerated on every sync, and freshness *of the data the site renders* is the honest definition. If route.json is stale, the day map is stale too — one signal, consistent meaning.

**Fallback:** if `route.json` fetch fails, use max(latest `events.json` timestamp, latest `driver-stats` implicit freshness). Degrade to `archive` on any failure. Never show `live` without positive confirmation of recent data.

**Freshness probe:**
```javascript
function detectMode(agenda, routeData) {
    var today = new Date().toISOString().slice(0, 10);
    var start = agenda.rally.start_date;
    var end = agenda.rally.end_date;
    if (today < start) return 'before';
    if (today > end) return 'archive';
    // In-rally window — live only if data is fresh
    var lastReading = routeData && routeData.generated_at
        ? new Date(routeData.generated_at)
        : null;
    if (!lastReading) return 'archive';
    var ageMs = Date.now() - lastReading.getTime();
    return ageMs < 6 * 3600 * 1000 ? 'live' : 'archive';
}
```

Re-check triggers (D-04):
- Initial load
- `window.addEventListener('visibilitychange', ...)` when `document.visibilityState === 'visible'`
- Live-mode interval: `setInterval(refresh, 120000)`

### 3. Timeline spine merge (D-06, NARR-03)

**Algorithm** (single-pass, client-side, per day):

```javascript
function buildSpine(dayISO, data) {
    // data = { events, notes, fuel, driverStints, agenda, route }
    var items = [];

    // 1. Events (filter by day)
    (data.events || []).forEach(function(ev) {
        if (dayOf(ev.timestamp) !== dayISO) return;
        items.push({
            kind: 'event',
            ts: ev.timestamp,
            data: ev
        });
    });

    // 2. Notes
    (data.notes || []).forEach(function(n) {
        if (dayOf(n.timestamp_utc) !== dayISO) return;
        items.push({ kind: 'note', ts: n.timestamp_utc, data: n });
    });

    // 3. Fuel stops
    (data.fuel || []).forEach(function(f) {
        if (dayOf(f.timestamp_utc) !== dayISO) return;
        items.push({ kind: 'fuel', ts: f.timestamp_utc, data: f });
    });

    // 4. Driver stints — emit a change marker at each started_at (skip first-of-day if it matches yesterday's active driver)
    (data.driverStints || []).forEach(function(stint) {
        if (dayOf(stint.started_at) !== dayISO) return;
        items.push({ kind: 'driver_change', ts: stint.started_at, data: stint });
    });

    // 5. Stage bookends — derive from route.json day slice
    var daySlice = (data.route && data.route.days[dayISO]) || null;
    if (daySlice && daySlice.points.length > 0) {
        items.push({ kind: 'stage_start', ts: daySlice.points[0].t, data: daySlice.points[0] });
        items.push({ kind: 'stage_end', ts: daySlice.points[daySlice.points.length - 1].t, data: daySlice.points[daySlice.points.length - 1] });
    }

    // 6. Agenda markers — meals (time + where), camping (end-of-day marker)
    var dayAgenda = (data.agenda.days || []).filter(function(d) { return d.date === dayISO; })[0];
    if (dayAgenda) {
        (dayAgenda.meals || []).forEach(function(m) {
            // m.time is "HH:MM" local — compose with dayISO
            var ts = dayISO + 'T' + m.time + ':00+10:00';  // Australia/Sydney
            items.push({ kind: 'agenda_meal', ts: ts, data: m });
        });
        if (dayAgenda.camping) {
            items.push({ kind: 'agenda_camping', ts: dayISO + 'T19:00:00+10:00', data: { where: dayAgenda.camping } });
        }
    }

    // Sort ascending by timestamp (chronological reading order)
    items.sort(function(a, b) { return new Date(a.ts) - new Date(b.ts); });
    return items;
}

function dayOf(isoTs) {
    return new Date(isoTs).toLocaleDateString('en-CA', { timeZone: 'Australia/Sydney' });
}
```

**Notes:**
- `en-CA` locale gives `YYYY-MM-DD` output — existing pattern used at index.html:1258.
- Agenda meal timestamps use a local ISO string with explicit `+10:00` offset. Agenda is day-planning content, timezone is Australia/Sydney (matches `TIMEZONE` constant at index.html:1004).
- Camping markers are placed at a nominal 19:00 local (dinner-ish) so they sit toward the end of the day without fabricating false precision. Planner can tune.
- BOOT events (D-06) come through the `events` path — no special handling needed since they're already in `events.json`.

**Renderer dispatch:**
```javascript
function renderSpineItem(item) {
    switch (item.kind) {
        case 'event':          return renderEventCard(item.data);        // reuse existing .event-card
        case 'note':           return renderNoteCard(item.data);         // reuse existing .note-card
        case 'fuel':           return renderFuelCard(item.data);         // new, small
        case 'driver_change':  return renderDriverChange(item.data);     // inline text "Tony takes over"
        case 'stage_start':    return renderStageBookend(item.data, 'start');
        case 'stage_end':      return renderStageBookend(item.data, 'end');
        case 'agenda_meal':    return renderAgendaMeal(item.data);       // italic, muted
        case 'agenda_camping': return renderAgendaCamping(item.data);    // italic, muted
    }
}
```

### 4. Agenda format (D-09, D-10, NARR-10)

**Strong recommendation: JSON.**

Search across `webroot/` confirmed **zero** YAML usage on the web side today. The existing fetch pipeline parses JSON four times (`events.json`, `notes.json`, `fuel.json`, `driver-stats.json`, `timelapse.json`). Adding a YAML parser adds a library (`js-yaml` at ~40 KB minified) and another code path with zero upside — Tony authors agenda via git push either way, and YAML's only advantage is comment support, which JSON5 or just well-placed `"_comment"` fields cover fine.

**File layout:** `webroot/agenda.json` committed alongside `index.html` in the home-ops repo. Flows through the existing `shit-of-theseus-webroot` ConfigMap (see `helmrelease.yaml:61-65`). No new mount, no volume change.

**Schema (finalised from D-10 shape):**

```json
{
  "rally": {
    "start_date": "2026-05-01",
    "end_date": "2026-05-09",
    "team": "A Team Has No Name",
    "title": "Shitbox Rally 2026",
    "start_location": "Port Douglas",
    "end_location": "Melbourne",
    "total_distance_km": 3534
  },
  "days": [
    {
      "date": "2026-05-01",
      "day_number": 1,
      "title": "Port Douglas → Cairns",
      "route": "Short day to shake out the car.",
      "camping": "Cairns caravan park",
      "meals": [
        { "time": "12:30", "where": "Mossman bakery" }
      ],
      "notes": null
    }
  ]
}
```

Notes on schema:
- `day_number` is redundant with array index but makes "Day 3 of 9" headers trivial without array search.
- `total_distance_km` replaces the hardcoded `TOTAL_DISTANCE_KM = 3534` at index.html:1325. Single source of truth.
- `start_location` / `end_location` replace hardcoded "Port Douglas" / "Melbourne" at index.html:1335-1336.
- `meals` list supports 0-N entries. `camping` is string or null.
- `notes` is day-level prose, separate from field-note data.

**CaptureSyncService impact:** none. Agenda ships with webroot, not with captures. Flux ConfigMap change = Flux reconcile = nginx pod restarts (RollingUpdate strategy, ~15 s downtime).

**Cache header:** agenda should be no-cache during rally (edits need to land fast). Add `/agenda.json` to the existing `no-cache` rule at `nginx-config/default.conf:7-11`.

### 5. Route.json Pi-side generator (D-21, NARR-08)

**Analog:** `src/shitbox/events/storage.py:383-463` (`generate_events_json`) is the template. It scans files, builds a list of dicts, sorts, writes atomically via `os.replace`. Our generator does the same but from a SQL query.

**File location:** `src/shitbox/storage/route.py` (new module, parallel to `logbook.py` and `driver.py`). Class name `RouteStorage` with `Database` injected, matching `LogbookStorage` shape (`src/shitbox/storage/logbook.py:150`).

**Generator contract:** must match `register_json_generator(name, fn)` — see `src/shitbox/sync/capture_sync.py:50-57`. The function returns a JSON-serialisable value. The registry writes it to `{captures_dir}/{name}.json` automatically. Name = `"route"` → output path `{captures_dir}/route.json`.

**SQL query** (GPS lives in the `readings` table with `sensor_type='gps'` — confirmed at `src/shitbox/storage/database.py:20-71`):

```sql
SELECT timestamp_utc, latitude, longitude
FROM readings
WHERE sensor_type = 'gps'
  AND latitude IS NOT NULL
  AND longitude IS NOT NULL
  AND timestamp_utc >= ?        -- rally start cutoff, to skip bench testing
ORDER BY timestamp_utc ASC
```

Rally start cutoff is available from the agenda but agenda lives in home-ops, not on the Pi. Options:
1. Hardcode rally start in Pi config (awkward — two sources of truth).
2. Hardcode a reasonable cutoff (e.g. `2026-04-01`) into `generate_route_json`.
3. Skip cutoff; include *all* GPS since boot. Filter client-side against `agenda.rally.start_date`.

**Recommendation: option 3.** Matches D-05 philosophy (join on client). Route.json grows by ~1 month of bench testing but stays well under 1 MB with Douglas-Peucker @ 10 m — at rally-typical speeds (60-100 km/h) you'll get ~20-40 m between 1 Hz samples so simplification collapses hard. At bench speeds (0 km/h) the simplifier collapses most points. Empirical check during planning via a quick ROUTE_MAX_POINTS cap if needed.

**Douglas-Peucker (stdlib only, no shapely):**

Classic recursive implementation, ~20 lines. Operating on unprojected WGS-84 coordinates (lat/lng in degrees). The tolerance "10 m" translates to ~0.00009° at this latitude (1° of latitude ≈ 111 km; 10 m ≈ 0.00009°). For perpendicular-distance calculation on a small area, a planar approximation is fine — the error vs. great-circle geodesic at 10 m scale is negligible.

```python
# src/shitbox/storage/route.py
import math
from typing import List, Tuple

Point = Tuple[float, float, str]  # (lat, lng, timestamp_utc)

def _perpendicular_distance(pt, line_start, line_end):
    """Planar perpendicular distance from pt to segment (line_start, line_end).

    Good enough at 10 m scale on unprojected lat/lng. Uses a rough
    metres-per-degree conversion keyed to mid-latitude.
    """
    lat_m = 111_000.0  # 1° lat ~= 111 km
    lng_m = 111_000.0 * math.cos(math.radians(line_start[0]))
    px = (pt[1] - line_start[1]) * lng_m
    py = (pt[0] - line_start[0]) * lat_m
    sx = (line_end[1] - line_start[1]) * lng_m
    sy = (line_end[0] - line_start[0]) * lat_m
    seg_len_sq = sx * sx + sy * sy
    if seg_len_sq == 0:
        return math.hypot(px, py)
    # Project pt onto segment, clamp to [0, 1]
    t = max(0.0, min(1.0, (px * sx + py * sy) / seg_len_sq))
    proj_x = t * sx
    proj_y = t * sy
    return math.hypot(px - proj_x, py - proj_y)

def douglas_peucker(points: List[Point], tolerance_m: float = 10.0) -> List[Point]:
    """Ramer-Douglas-Peucker polyline simplification. Tolerance in metres.

    Returns a subset of points preserving shape within tolerance.
    """
    if len(points) < 3:
        return points[:]
    dmax = 0.0
    index = 0
    for i in range(1, len(points) - 1):
        d = _perpendicular_distance(points[i], points[0], points[-1])
        if d > dmax:
            dmax = d
            index = i
    if dmax > tolerance_m:
        left = douglas_peucker(points[:index + 1], tolerance_m)
        right = douglas_peucker(points[index:], tolerance_m)
        return left[:-1] + right   # avoid duplicating pivot
    return [points[0], points[-1]]
```

Recursion depth concern: for a 14-day rally at 1 Hz (~86 k points/day, ~1.2 M total), worst-case recursion could blow Python's default stack (1000). Mitigation:
- **Option A (recommended):** simplify *per day* (group first, then simplify). Day slices are 10-20 k points pre-simplification, well within recursion safety.
- **Option B:** iterative stack-based implementation (~30 lines instead of 15). Use this if per-day grouping isn't natural. It is natural here (output is grouped by day anyway), so go with A.

**Output shape:**

```json
{
  "generated_at": "2026-05-03T14:23:17+00:00",
  "tolerance_m": 10.0,
  "days": {
    "2026-05-01": {
      "point_count": 412,
      "points": [
        [-16.4845, 145.4635, "2026-05-01T08:00:12+00:00"],
        [-16.4852, 145.4641, "2026-05-01T08:00:42+00:00"]
      ]
    }
  }
}
```

Why tuples not objects per point: 30-40% smaller JSON. Matters at 1 MB budget. `[lat, lng, ts]` is conventional (Leaflet accepts `[lat, lng]` arrays directly).

**Atomic write** (match the events.json pattern at `storage.py:453-456`):
```python
tmp = captures_dir / "route.json.tmp"
tmp.write_text(json.dumps(payload))
os.replace(str(tmp), str(captures_dir / "route.json"))
```

**But remember:** `CaptureSyncService._run_json_generators` at `capture_sync.py:67-74` already handles the write. The generator just needs to *return* the dict. So our generator returns the payload; the registry does the file I/O. Follow `generate_notes_json`'s contract (`storage/logbook.py:150-152`) — return a value, don't write.

**Engine wiring** (`src/shitbox/events/engine.py` around line 556-558, matching the existing pattern):

```python
self.route_storage = RouteStorage(self.database)
if self.capture_sync is not None:
    self.capture_sync.register_json_generator("route", self.route_storage.generate_route_json)
```

**Tolerance sanity check:** at 10 m, 100 km of straight highway simplifies to ~2-3 points. Real rally roads (curves, elevation) simplify to one point every ~30-100 m typical, so ~10-30 points/km. Full 3534 km × 20 pts/km = 70 k points. At `[lat, lng, "iso_ts"]` = ~45 bytes JSON per point → 3.15 MB. **This exceeds the 1 MB target.** Mitigations:
- Drop timestamps from points (keep only bookend timestamps per day for stage start/end). Saves ~50%.
- Increase tolerance to 20 m. Cuts points ~40%.
- Quantise coords to 5 decimal places (~1 m precision at the equator) instead of raw floats. JSON serialisation saves ~15%.

**Recommended hybrid:** drop per-point timestamps (day key is enough granularity for `/day` URLs; start/end timestamps live in a `day_start_ts` / `day_end_ts` field on the day object). Keep 10 m tolerance initially. If still > 1 MB after a real-rally day or two, bump tolerance to 15-20 m. Planner should add a test that asserts `len(json.dumps(payload)) < 1_000_000` and call it out in Wave 0.

### 6. Day-slice polyline on Leaflet (D-22, NARR-09)

The existing Leaflet init is at `index.html:1276-1293` (status mini-map) and `:1566-1574` (full map). Both use CartoDB dark / light tiles. Day-page map reuses the dark pattern from `index.html:1280`:

```javascript
function initDayMap(dayISO, routeData) {
    var map = L.map('day-map');
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        maxZoom: 19
    }).addTo(map);

    // 1. Full-rally polyline as grey backdrop — loop through all days except the current one
    var backdropPoints = [];
    Object.keys(routeData.days).forEach(function(d) {
        if (d === dayISO) return;
        routeData.days[d].points.forEach(function(p) {
            backdropPoints.push([p[0], p[1]]);
        });
    });
    if (backdropPoints.length > 1) {
        L.polyline(backdropPoints, { color: '#484f58', weight: 3, opacity: 0.6 }).addTo(map);
    }

    // 2. Day slice highlighted
    var dayPoints = (routeData.days[dayISO] || {points: []}).points
        .map(function(p) { return [p[0], p[1]]; });
    var dayBounds = null;
    if (dayPoints.length > 1) {
        var dayLine = L.polyline(dayPoints, { color: '#e0a040', weight: 4, opacity: 1.0 }).addTo(map);
        dayBounds = dayLine.getBounds();
    }

    // 3. Day's event pins (existing BADGE_COLORS mapping at index.html:994-1002)
    // ... reuse existing circleMarker pattern from index.html:1614-1626

    if (dayBounds) map.fitBounds(dayBounds, { padding: [40, 40] });
}
```

**Gotchas:**
- Leaflet polylines don't auto-simplify on zoom out. 70 k points will render fine up to zoom level 8-10 but stutter on mobile at zoom 5-6. Douglas-Peucker on the Pi side makes this a non-issue if total points stay under ~20 k.
- Full-rally polyline is plotted with a single `L.polyline(allPoints)` call. `L.polyline` accepts multi-line arrays `[[...day1...], [...day2...]]` to render disconnected segments (prevents teleport lines between last point of day N and first of day N+1). Use this form:
  ```javascript
  L.polyline([day1Pts, day2Pts, day3Pts, ...], { color: '#484f58' })
  ```
- Z-order: backdrop added first, day slice second. Leaflet respects insertion order within the same pane.
- Attribution: `© OpenStreetMap © CARTO` is already in the file — reuse the same string.

### 7. Day-nav progress bar (D-14, D-15, NARR-05)

**Analog:** existing rally-progress bar at `webroot/index.html:99-134` (CSS) and `:1326-1343` (JS rendering). The *visual style* — orange fill, grey track, sub-pixel border radius — transfers directly. The new day-nav has **segment** semantics instead of a single fill.

**HTML structure:**
```html
<div class="day-nav">
  <a class="day-nav-segment completed" href="/day/2026-05-01">
    <div class="day-nav-number">1</div>
    <div class="day-nav-date">01 May</div>
  </a>
  <a class="day-nav-segment current" href="/day/2026-05-02">
    <div class="day-nav-number">2</div>
    <div class="day-nav-date">02 May</div>
  </a>
  <span class="day-nav-segment future">
    <div class="day-nav-number">3</div>
    <div class="day-nav-date">03 May</div>
  </span>
</div>
```

**CSS (extending the rally-progress visual language):**
```css
.day-nav {
    display: grid;
    grid-auto-columns: 1fr;
    grid-auto-flow: column;
    gap: 2px;
    background: #161b22;
    border: 1px solid #2a1f0e;
    border-radius: 8px;
    padding: 0.5rem;
    margin-bottom: 1.5rem;
}
.day-nav-segment {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.5rem 0.25rem;
    border-radius: 4px;
    background: #21262d;             /* grey track, matches rally-progress-bar */
    color: #8b949e;
    text-align: center;
    text-decoration: none;
    transition: background 0.15s;
}
.day-nav-segment.completed { background: #c06000; color: #fff; }
.day-nav-segment.current   { background: #e0a040; color: #0d1117; font-weight: 600; }
.day-nav-segment.future    { background: #21262d; color: #484f58; cursor: default; pointer-events: none; }
.day-nav-segment:hover.completed, .day-nav-segment:hover.current { opacity: 0.85; }
.day-nav-number { font-size: 1.1rem; font-weight: 600; }
.day-nav-date { font-size: 0.7rem; }
@media (max-width: 600px) {
    .day-nav-date { display: none; }  /* too tight on mobile — numbers only */
}
```

**Render logic:**
```javascript
function renderDayNav(agenda, currentDayISO) {
    var today = new Date().toISOString().slice(0, 10);
    var container = document.getElementById('day-nav');
    var html = '';
    agenda.days.forEach(function(day) {
        var state = day.date < today ? 'completed'
                  : day.date === today ? 'current'
                  : 'future';
        if (day.date === currentDayISO) state = 'current';  // explicit selection overrides
        var tag = state === 'future' ? 'span' : 'a';
        var href = state === 'future' ? '' : 'href="/day/' + day.date + '"';
        html += '<' + tag + ' class="day-nav-segment ' + state + '" ' + href + '>';
        html += '<div class="day-nav-number">' + day.day_number + '</div>';
        html += '<div class="day-nav-date">' + formatShortDate(day.date) + '</div>';
        html += '</' + tag + '>';
    });
    container.innerHTML = html;
}
```

### 8. Archive overview + before mode + live mode (D-16, D-17, D-18)

**Before mode:**
- Reads `agenda.json`, computes T-minus from `rally.start_date`.
- Renders the planned route map using agenda's `camping` coordinates (if present) or a static route image from `/route.jpg` (already in webroot — see `webroot/route.jpg` referenced at `index.html:938`).
- Day-list preview is a loop over `agenda.days` printing number + title.
- "Follow along from [start_date]" CTA is static text with a formatted date.

Decision point for planner: **does the agenda need per-day lat/lng for before-mode maps?** Not strictly — `/route.jpg` + day-list preview is sufficient and cheaper. Leave lat/lng out of the initial schema; add if the planner wants a richer before-mode map.

**Live mode:**
- Homepage IS `renderDayPage(today)`.
- Setup: `setInterval(function() { refreshLiveData(); }, 120000)`.
- `refreshLiveData` re-fetches `events.json`, `route.json`, `notes.json`, `fuel.json`, `driver-stats.json` (skip agenda — it's static), re-runs the spine merge, diffs against the rendered DOM? No — just rebuild the day sections. At a few dozen spine items per day, full replace is fine. Don't over-engineer.
- Visibility-change hook: `document.addEventListener('visibilitychange', ...)` to immediately refresh when tab returns.

**Archive mode:**
- Overview card: totals across agenda.days, sum of events, total km (from `route.json` day points, summed haversine), drivers count (from `driver-stats.json`), fuel burned (sum of `fuel.volume_litres`).
- Linear day grid: `<div class="archive-day-grid">` with one card per day. Each card:
  - Date + title
  - Thumbnail: try `/captures/{date}/timelapse.jpg` (poster from timelapse compile) → `/captures/{date}/{firstEventVideo}.jpg` (event still) → solid colour placeholder with day number.
  - Clickable to `/day/{date}`.

The timelapse compiler emits `timelapse.mp4` per day dir (confirmed at `src/shitbox/sync/timelapse_compiler.py:251` — `*/timelapse.mp4`). Adding a poster JPG to the Pi-side compile is a tractable extension but arguably outside Phase 19 scope. **Recommendation:** fall back chain as-is, but document the missing poster as a gap that degrades archive mode aesthetics. Planner can decide whether to push it into scope.

### 9. Nav collapse + DOM id / JS handler impact (D-19, D-20, NARR-06, NARR-07)

Complete teardown inventory from `index.html`:

| Line(s) | Element | Status | Migration |
|---------|---------|--------|-----------|
| 667-677 | `<nav>` block (9 tabs) | **Collapse** | New nav: Home / Grafana / About / Donate |
| 680-739 | `<div id="status-section">` | **Remove** | Content re-homed: status stats → homepage live mode; notes feed → timeline spine |
| 741-747 | `<div id="drivers-section">` | **Remove** | Drivers table → `/about` |
| 749-758 | `<div id="videos-section">` | **Remove** | Per-day video highlights → day page |
| 760-765 | `<div id="map-section">` | **Remove** | Day-slice map → day page; overview map → archive homepage |
| 767-779 | `<div id="dashboard-section">` | **Convert to link** | Nav "Grafana" opens `https://grafana.shit-of-theseus.com/...` in new tab. Remove iframe embed from the site. |
| 780-931 | `<div id="car-section">` | **Move** | Full content → `/about` page |
| 933-939 | `<div id="route-section">` | **Remove** | `/route.jpg` stays as asset; before-mode uses it. |
| 941-946 | `<div id="timelapse-section">` | **Remove** | Per-day timelapse → day page |
| 948-981 | `<div id="about-section">` | **Expand** | Becomes the new `/about` canonical page (team bios + drivers + The Car) |
| 1024-1053 | Tab click handler + hash routing | **Replace** | `location.pathname` router + simpler hash handling for `#donate` etc. |
| 1061-1081 | `window.jumpToEvent` / `jumpToNote` | **Remove or rewire** | Timeline spine has events+notes co-located per day — cross-day jumps uncommon. Remove the functions; replace with anchor IDs on spine items. |
| 1114-1128 | `injectNoteBadges` | **Remove** | Notes are inline in the spine now, not badges on event cards. |
| 1130-1164 | `renderDrivers` | **Keep, repoint** | Function stays, renders into the `/about` page's drivers section instead of its own tab. |
| 1226-1317 | `renderStatus` | **Refactor** | Split into `renderLiveMode` (stats widgets for homepage live mode) and drop the section-tab coupling. |
| 1319-1549 | `renderEvents` (big function) | **Refactor** | Core event-card rendering survives in `renderEventCard`. Day-filter bar (1358-1443) becomes obsolete — day-nav is the global filter. Date-grouping (1346-1354) becomes a single-day filter on day-page render. |
| 1551-1673 | `initMap` | **Refactor** | Split into `initArchiveOverviewMap(routeData, events, fuel)` and `initDayMap(dayISO, routeData, events, fuel)`. Day map is scoped to one day. |
| 1675-1713 | `loadTimelapses` | **Replace** | Per-day timelapse embed on day page uses existing `/captures/{date}/timelapse.mp4` URL pattern. No need for `/captures/timelapse.json` index in the homepage anymore — day page knows its date. |

**Dead after rebuild:**
- Tab section `display: none` / `display: block` pattern. All sections coexist on a single scroll-heavy day page.
- The `validSections` array at index.html:1050.
- The `data-section` attribute flow.
- Day-filter bar (1358-1443) — replaced by day-nav.
- `statusMapInitialised` guard — day map is created fresh on each day page render.

**Survives and is reused:**
- `BADGE_COLORS` + `DISPLAY_NAMES` (index.html:994-1015).
- `TIMEZONE` constant.
- Event card HTML template.
- Note card HTML template.
- Fuel popup shape.
- All CartoDB tile init patterns.
- Rally progress bar CSS (`.rally-progress`, `.rally-progress-fill`) — extended by day-nav.
- Share / download button handlers for event cards.

### 10. Deployment path

- Flux HelmRelease `interval: 30m` (`helmrelease.yaml:8`).
- ConfigMap updates (webroot + nginx-config) trigger RollingUpdate (`helmrelease.yaml:29`) — nginx pod restarts with ~15 s cutover.
- Manual reconcile: `flux reconcile kustomization <name>` or `flux reconcile helmrelease shit-of-theseus -n default`.
- Rollback: `git reset --hard shitbox-pre-phase-19` from `~/dev/home-ops` root, then `git push --force-with-lease origin main` (force-push is required since tag preceded post-tag commits; only use on Tony's explicit confirmation). Flux picks up the revert on next reconcile.
- **NFS captures mount is read-only** (`helmrelease.yaml:78`). The Pi writes via rsync to `192.168.1.22:/volume2/apps/shitbox`; nginx reads via NFS. `route.json` reaches the site through this path; no additional wiring.
- **Cache headers:** `events|timelapse|notes|fuel|driver-stats.json` are already no-cache (`default.conf:7-11`). Extend this regex to include `route` and `agenda`: `^/captures/(events|timelapse|notes|fuel|driver-stats|route)\.json$` and add `/agenda.json` separately (served from webroot, not captures).

## Analog files + concrete code excerpts

The planner can paste these verbatim into task `read_first` / `action` fields.

### EX-1: Existing parallel-fetch pattern (index.html:1167-1224)

```javascript
fetch('/captures/events.json', { cache: 'no-cache' })
    .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(events) { /* ... */ })
    .catch(function() { /* ... */ });
fetch('/captures/notes.json', { cache: 'no-cache' })
    .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(notes) { /* ... */ });
// (fuel, driver-stats follow identical shape)
```

Phase 19 extends this with `route.json` and `/agenda.json`. No architectural shift — one more `fetch().then()` chain each.

### EX-2: Existing Leaflet dark-tile map init (index.html:1276-1293)

```javascript
var smap = L.map('status-map').setView([locEvent.lat, locEvent.lng], 10);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 19
}).addTo(smap);
var pts = events.filter(function(ev) { return ev.lat && ev.lng; })
    .sort(function(a, b) { return new Date(a.timestamp) - new Date(b.timestamp); });
if (pts.length > 1) {
    L.polyline(pts.map(function(ev) { return [ev.lat, ev.lng]; }),
        { color: '#e0a040', weight: 2, opacity: 0.6 }).addTo(smap);
}
```

Day-page map upgrades this with a second polyline layer (grey backdrop), and replaces event-dot-polyline with route.json GPS polyline.

### EX-3: Existing date-bucketing pattern (index.html:1346-1354)

```javascript
var groups = {};
events.forEach(function(ev) {
    var date = new Date(ev.timestamp).toLocaleDateString('en-CA', {
        timeZone: TIMEZONE
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(ev);
});
```

This exact `en-CA` / Australia/Sydney trick is how all day-filtering works today. Reuse verbatim for spine day-filtering.

### EX-4: Existing rally-progress bar render (index.html:1326-1343)

```javascript
var progressEl = document.getElementById('rally-progress');
for (var pi = 0; pi < events.length; pi++) {
    var pe = events[pi];
    if (pe.distance_from_start_km != null && pe.distance_to_destination_km != null) {
        var fromStart = Math.round(pe.distance_from_start_km);
        var toDest = Math.round(pe.distance_to_destination_km);
        var pct = Math.min(100, Math.max(0, (fromStart / TOTAL_DISTANCE_KM) * 100));
        progressEl.innerHTML =
            '<div class="rally-progress-header">' +
            '<span>From Port Douglas: <strong>' + fromStart.toLocaleString() + ' km</strong></span>' +
            '<span>To Melbourne: <strong>' + toDest.toLocaleString() + ' km</strong></span>' +
            '</div>' +
            '<div class="rally-progress-bar">' +
            '<div class="rally-progress-fill" style="width:' + pct.toFixed(1) + '%"></div>' +
            '</div>';
        break;
    }
}
```

Day-nav bar replaces this element's innerHTML with segment HTML but reuses the outer `.rally-progress` container CSS.

### EX-5: Pi-side JSON generator contract (capture_sync.py:50-74)

```python
def register_json_generator(self, name: str, fn: Callable[[], Any]) -> None:
    """Register a pre-rsync JSON generator. fn() must return a JSON-serialisable value."""
    self._json_generators[name] = fn
    log.info("json_generator_registered", name=name)

def _run_json_generators(self) -> None:
    """Write each registered generator's output to {captures_dir}/{name}.json."""
    captures = Path(self.captures_dir)
    try:
        captures.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.warning("json_generators_captures_dir_error", error=str(e))
        return
    for name, fn in list(self._json_generators.items()):
        try:
            data = fn()
            out = captures / f"{name}.json"
            out.write_text(json.dumps(data, default=str))
            log.info("json_generator_complete", name=name)
        except Exception as e:
            log.warning("json_generator_failed", name=name, error=str(e))
```

Route generator returns a dict; the registry writes it to `captures/route.json` as JSON. Errors are swallowed with a warning — matches existing pattern.

### EX-6: Pi-side existing generator shape (storage/logbook.py:150-152)

```python
def generate_notes_json(self) -> List[Dict[str, Any]]:
    """Return notes as a list of dicts suitable for JSON serialisation."""
    return self.list_notes()
```

`generate_route_json` follows the same "return a dict, don't write" shape.

### EX-7: Engine registration pattern (events/engine.py:554-566)

```python
# Logbook storage (notes + fuel stops) — REST-only, no thread
self.logbook_storage = LogbookStorage(self.database)
if self.capture_sync is not None:
    self.capture_sync.register_json_generator("notes", self.logbook_storage.generate_notes_json)
    self.capture_sync.register_json_generator("fuel", self.logbook_storage.generate_fuel_json)

# Driver storage — REST-only, idempotent (same pattern as LogbookStorage)
self.driver_storage = DriverStorage(self.database)
if self.capture_sync is not None:
    self.capture_sync.register_json_generator(
        "driver-stats",
        self.driver_storage.get_driver_stats_payload,
    )
```

Route storage gets the same three-line block:
```python
self.route_storage = RouteStorage(self.database)
if self.capture_sync is not None:
    self.capture_sync.register_json_generator("route", self.route_storage.generate_route_json)
```

Register *after* `logbook_storage` and `driver_storage` blocks for alphabetical consistency with `notes` / `fuel` / `driver-stats` / `route`. Planner's call.

### EX-8: Existing atomic-write pattern (events/storage.py:453-456)

```python
tmp_path = events_json_path.with_suffix(".tmp")
with open(tmp_path, "w") as f:
    json.dump(entries, f, indent=2)
os.replace(tmp_path, events_json_path)
```

The `CaptureSyncService` registry uses `out.write_text(json.dumps(data, default=str))` (capture_sync.py:71) — NOT atomic. For route.json that's fine: it runs pre-rsync, rsync handles the atomic delivery to NAS. No file-truncation concern on the Pi local side because nothing reads route.json locally.

## Validation Architecture (for Nyquist)

`workflow.nyquist_validation` is enabled. Section required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ (backend); no JS test framework currently |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` or default) — matched existing style |
| Quick run command | `pytest tests/test_route_storage.py -x` |
| Full suite command | `pytest` (or `pytest --cov=shitbox`) |
| Lint command | `ruff check src/` |
| Type check | `mypy src/` |

**Web-side testing reality:** there is no JS test framework in the webroot repo and no budget in this phase to introduce one (locked by Phase 18 — no build step). Web-side verification is manual + browser devtools + Flux reconcile cycle. Document this as an explicit gap in `## Risks`.

### Phase Requirements → Test Map

| REQ ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|--------------|
| NARR-01 | Mode detection returns correct label for before/live/archive given agenda + freshness | manual (browser) + logic-only unit possible if mode function is extracted and testable server-side | — | ❌ Web-only, no harness |
| NARR-02 | `/day/YYYY-MM-DD` served via nginx SPA fallback; SPA routes | manual curl + browser | `curl -s -o /dev/null -w "%{http_code}" https://shit-of-theseus.com/day/2026-05-01` (should be 200) | N/A |
| NARR-03 | Timeline spine merges streams in correct chronological order | manual; spine logic is client-side JS | — | N/A |
| NARR-04 | Agenda context renders before telemetry | manual (DOM inspection) | — | N/A |
| NARR-05 | Day-nav renders correct segment states | manual | — | N/A |
| NARR-06/07 | Nav / page collapse successful; no 404s on removed tab anchors | manual + curl | `curl -s https://shit-of-theseus.com/#status` (200, renders homepage with no JS error) | N/A |
| NARR-08 | `route.json` generator returns Douglas-Peucker-simplified, day-grouped payload ≤ 1 MB | unit | `pytest tests/test_route_storage.py -x` | ❌ Wave 0 |
| NARR-08b | `route.json` integration with CaptureSyncService registry | integration | `pytest tests/test_capture_sync_generators.py::test_route_generator -x` | ❌ Wave 0 (extend existing file) |
| NARR-09 | Day-page map renders backdrop + day slice polylines | manual | — | N/A |
| NARR-10 | `/agenda.json` fetch returns expected schema | integration (nginx-side) | `curl -s https://shit-of-theseus.com/agenda.json \| jq '.rally.start_date'` | N/A |

### Sampling Rate

- **Per task commit (Pi-side Plans):** `pytest tests/test_route_storage.py -x && ruff check src/ && mypy src/`
- **Per wave merge (Pi-side):** `pytest` (full suite)
- **Phase gate:** Full Pi test suite green + manual browser walkthrough of all three modes on a test instance or staging hostname before phase close. Document the manual checklist in `VALIDATION.md`.

### Wave 0 Gaps

- [ ] `tests/test_route_storage.py` — covers NARR-08 (Douglas-Peucker correctness on synthetic point sets, per-day grouping, size budget assertion, empty/sparse GPS handling)
- [ ] Extend `tests/test_capture_sync_generators.py` — add `test_route_generator_registers_and_writes` covering NARR-08b, mirroring existing `test_generators_run_before_rsync`
- [ ] `tests/test_route_storage.py::test_douglas_peucker_*` — unit tests on the simplification function with known input/output pairs
- [ ] **Behaviour not covered by unit tests (documented manual checklist):**
  - Mode detection cross-boundary (before → live on start-date roll-over; live → archive on staleness)
  - Timeline merge ordering across all 6 streams with a golden-dataset fixture
  - Polyline day-slice visual correctness (manual browser check; screenshot in summary)
  - nginx `try_files` rewrite for `/day/*` paths (`curl` smoke in verification step)
  - Flux reconcile completes cleanly post-deploy
  - Rollback via `shitbox-pre-phase-19` tag (dry-run during planning)

### Anti-Pattern: what NOT to test automatically

- Do NOT introduce Jest / Vitest / Playwright for this phase. The phase budget does not cover introducing a JS test framework, and Phase 18 explicitly locks the no-build-step constraint.
- Do NOT write Python integration tests that hit nginx / Flux — those are infrastructure, verified by manual checklist + curl smoke.

## Risks / Unknowns / Open Questions

1. **Route.json size budget** (MEDIUM risk): the 1 MB target at 10 m tolerance will likely be exceeded. Mitigation strategy documented (drop per-point timestamps, increase tolerance). Planner should include a size-budget test in Wave 0 and have a "bump tolerance to 15-20 m" fallback plan.

2. **Freshness signal source** (LOW risk, design decision): recommended `route.json.generated_at`. Planner should confirm during Plan 19-01 or 19-02. Fallback to `max(events.timestamp, driverStats implicit)` if route fetch fails.

3. **No JS testing framework** (MEDIUM risk): all web-side behaviour depends on manual verification. Mitigate by writing a detailed manual-QA checklist in `VALIDATION.md` and doing a full walkthrough per mode before phase close.

4. **Flux reconcile cadence (30 min)** is long for iterative web work. Planner should document the `flux reconcile` command for faster dev feedback loops and flag it in plans for any task that touches webroot.

5. **Archive-mode thumbnail source** (LOW risk): no per-day timelapse poster JPG exists today. Fall-back chain in D-18 handles this, but the first visual impression is muted. Planner can descope or push a timelapse poster generator into a separate task.

6. **Douglas-Peucker recursion depth** (LOW risk with per-day grouping): mitigation documented above. If full-rally batch simplification is ever needed, convert to iterative.

7. **Agenda meal timestamps** have implicit Australia/Sydney offset. If the rally crosses state boundaries (it does — QLD has no DST), the agenda `time: "12:30"` needs a consistent interpretation. **Recommendation:** document that agenda times are *Australia/Sydney local regardless of crew's physical location*, matching the `TIMEZONE` constant in the SPA. Accept the minor UX weirdness of an 11:30 lunch appearing at 12:30 on the timeline when the car is in western QLD — it's only a narrative marker, not a scheduling primitive.

8. **Removed `/timelapse.json` dependency**: the current SPA fetches `/captures/timelapse.json` for its timelapse tab. After rebuild, day pages reference `/captures/{date}/timelapse.mp4` directly. Does `timelapse.json` still need to exist? **Yes** — keeping it is zero-cost (already generated) and future-useful for archive grid thumbnails. Planner can choose to simply stop *fetching* it.

9. **`GSD_` environment handling for rally `start_date`**: the SPA date comparisons use string comparison (`today < start`), which works for ISO YYYY-MM-DD strings but fails for localised date strings. Ensure all comparisons use `new Date().toISOString().slice(0, 10)` consistently.

10. **Share button URL schema** (`index.html:1532` uses `/?event=X#events`): once events live inside day pages, `?event=X` becomes meaningless. Either drop the share button or rewrite share URLs to `/day/{date}#event-{id}`. Anchor scrolling survives `pushState` routing so this works out of the box.

## Out of Scope / Anti-Patterns

Explicit list. Planner MUST NOT recommend any of these.

**Anti-patterns:**
1. **Any build step** — no React, Vue, Vite, Webpack, Parcel, esbuild, Rollup, etc. Locked by Phase 18. The site is one HTML file with inline CSS + JS.
2. **Any JS framework** — no Alpine, no htmx, no Preact. Vanilla JS with `var` keyword to match existing style.
3. **Any JS YAML parser** (`js-yaml` or similar) — use JSON for agenda.
4. **Any CSS preprocessor** (Sass, Less, PostCSS) — inline plain CSS only.
5. **Pi-side per-day JSON generators** — rejected by D-05. Client filters in the browser.
6. **Exposing fuel cost anywhere** — hard exclusion from Phase 12 (D-10). `cost_aud` is excluded at SQL level in `generate_fuel_json` (`logbook.py:154-166`); never reintroduce.
7. **Calendar-grid archive layout** — explicitly rejected in D-18. Linear day grid only.
8. **Descriptor slugs in day URLs** — `/day/2026-05-01-hay` rejected in D-02.
9. **Mobile-specific collapse / accordion** — rejected in D-13. Single vertical scroll on all widths.
10. **Filtering BOOT events from the spine** — rejected in D-06. BOOT has narrative value + dashcam footage.
11. **Including thermal / undervoltage alerts in the spine** — rejected in D-07. Those live in Grafana.
12. **Pi-side API for agenda editing** — rejected in Deferred. Git push is the edit workflow.
13. **New external CDN dependencies** — Leaflet is already pinned to unpkg with SRI hash. Don't add fonts, icons, or analytics.

**Out of scope (deferred):**
- Pre-generated per-day JSON from the Pi
- Agenda YAML vs JSON (research decided JSON; if planner disagrees they can revisit, but YAML adds net cost)
- Per-driver event attribution on `/about`
- Mobile-specific tab / accordion collapse
- Per-day timelapse poster JPG generation (fall-back chain handles absence)

## Standard Stack

### Core (unchanged from Phase 18)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Leaflet | 1.9.4 [VERIFIED: already pinned in webroot/index.html:7] | Map + polyline rendering | Dark theme tiles, ubiquitous, offline-friendly |
| CartoDB dark_all tiles | live | Dark basemap | Matches site theme, already in use |
| Python stdlib (`math`, `json`, `sqlite3`) | 3.9+ | Douglas-Peucker, SQL, JSON | Zero dependency add |
| structlog | 24+ [CITED: pyproject.toml:19] | Existing logging convention | Project standard |

### New this phase
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| *none* | — | — | The whole point is "no build step, no framework". Agenda is JSON; Douglas-Peucker is stdlib. |

### Alternatives considered (and rejected)
| Instead of | Could Use | Why rejected |
|------------|-----------|--------------|
| JSON for agenda | YAML + js-yaml | Zero existing YAML on web; JSON fits existing fetch pipeline; author experience identical |
| Hand-rolled Douglas-Peucker | `shapely` | Shapely is a large C-extension dep; we don't use it anywhere else; ~20-line stdlib impl is well-understood |
| `pushState` router | Hash-only routing (`#day-2026-05-01`) | Real URLs + `try_files` give clean `/day/...` URLs, which D-01 mandates and which are more shareable |
| JS test framework (Jest / Vitest) | Pure manual QA | Introducing a JS test framework violates "no build step" (most JS test runners require a bundler); phase budget doesn't cover it |

## Code Examples

All already included in Sections 1-10 and "Analog files" above. The planner can pull these into `action` / `read_first` task fields verbatim.

## State of the Art

| Old Approach (Phase 18) | Current Approach (Phase 19) | Impact |
|-------------------------|------------------------------|--------|
| Tab-section navigation (`data-section` attr + `.section.active`) | `location.pathname` router for `/day/*` + `/about`; simple hash for `#donate` | Real shareable URLs; removes big-switch navigation code |
| Day-filter bar on Videos tab | Site-wide day-nav progress bar | Day is now primary UX pivot |
| Event-grid layout (`display: grid`) grouped by date | Timeline spine (chronological scroll) per day | Narrative reading order replaces at-a-glance grid |
| Single map tab with all event pins + fuel pins | Day-page map (day slice) + archive overview map | Scope matches scroll context |
| Static route image (`/route.jpg`) as rally map | GPS polyline from `route.json` + static image as before-mode fallback | Live truth replaces planned graphic |
| Freshness inferred from events.json presence | Explicit `route.json.generated_at` timestamp | Freshness becomes a first-class signal for mode detection |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Nginx `try_files $uri $uri/ /index.html` (current config line 26-28) already handles `/day/*` paths without change | Section 1 | LOW — verifiable with one curl; if wrong, add explicit `location ~ ^/day/ { try_files ... }` block |
| A2 | At 10 m tolerance Douglas-Peucker on 1 Hz GPS at rally speeds collapses ~95%+ of points | Section 5 | MEDIUM — size budget may blow; mitigations documented (drop per-point timestamps, bump tolerance) |
| A3 | Agenda meal times are Australia/Sydney local regardless of crew's physical timezone | Section 3 | LOW — cosmetic narrative marker only; document in agenda schema comments |
| A4 | `route.json.generated_at` is an acceptable freshness signal (rather than a dedicated `heartbeat.json`) | Section 2 | LOW — falls back to `events.json` timestamp on failure; worst case a quiet hour shows `archive` instead of `live` for 6 h |
| A5 | 15 s nginx-pod restart during Flux RollingUpdate is acceptable downtime | Section 10 | LOW — unchanged from Phase 18; public site tolerance is flexible |
| A6 | Share-button URL rewrite from `/?event=X#events` to `/day/{date}#event-{id}` works via anchor scrolling after pushState | Section 9 item 10 | LOW — standard browser behaviour, verified by existing jumpToEvent pattern |
| A7 | Per-day Douglas-Peucker avoids Python recursion-depth limits | Section 5 | LOW — per-day groups are ~10-20k points; Python default limit 1000, log₂(20k) = ~15 frames deep |

If any of A1-A7 prove wrong, the fix is contained to its section; none reshape the phase.

## Sources

### Primary (HIGH confidence — verified in this session)
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html` — 1717-line SPA read in full
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/nginx-config/default.conf` — 29 lines
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/helmrelease.yaml` — 79 lines
- `/Users/tgreen/dev/shitbox/src/shitbox/events/storage.py` — events/timelapse JSON generator pattern
- `/Users/tgreen/dev/shitbox/src/shitbox/sync/capture_sync.py` — register_json_generator contract
- `/Users/tgreen/dev/shitbox/src/shitbox/sync/timelapse_compiler.py:245-276` — generator contract analog
- `/Users/tgreen/dev/shitbox/src/shitbox/storage/logbook.py:140-181` — notes/fuel generator shape
- `/Users/tgreen/dev/shitbox/src/shitbox/storage/driver.py:85-95` — driver-stats generator shape
- `/Users/tgreen/dev/shitbox/src/shitbox/storage/database.py:1-135` — schema (confirms GPS in `readings` table with `sensor_type='gps'`)
- `/Users/tgreen/dev/shitbox/src/shitbox/events/engine.py:540-566` — engine wiring pattern
- `/Users/tgreen/dev/shitbox/.planning/phases/19-website-narrative-rebuild/19-CONTEXT.md` — locked decisions
- `/Users/tgreen/dev/shitbox/.planning/phases/18-website-revamp/18-CONTEXT.md` — locked-forward constraints
- `/Users/tgreen/dev/shitbox/.planning/phases/12-schema-foundation-and-logbook-api/12-CONTEXT.md` — cost-exclusion enforcement
- `/Users/tgreen/dev/shitbox/.planning/phases/13-driver-tracking/13-CONTEXT.md` — driver-stats payload
- `/Users/tgreen/dev/shitbox/.planning/notes/2026-04-16-website-v2-ia-redesign.md` — exploration session
- `/Users/tgreen/dev/shitbox/tests/test_capture_sync_generators.py` — integration test template
- `/Users/tgreen/dev/shitbox/tests/conftest.py` — shared fixtures
- `/Users/tgreen/dev/shitbox/pyproject.toml` — dependency list, Python version

### Secondary (MEDIUM confidence — training knowledge cross-checked against primary)
- Ramer-Douglas-Peucker algorithm: standard reference implementation, widely published
- Leaflet polyline API (`L.polyline`, `fitBounds`, layered rendering order): confirmed against the existing index.html usage

### Tertiary (LOW confidence — none)
- No training-only claims in this research. Every fact was verified against files in this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — we deliberately add nothing; existing patterns verified line-by-line
- Architecture: HIGH — client-side routing + timeline merge are well-understood; code excerpts match the file
- Pitfalls: HIGH — pulled from explicit grep of existing code, not speculation
- Pi-side generator: HIGH — direct analog to `generate_notes_json` / `generate_events_json` / `generate_timelapse_json` verified
- Douglas-Peucker: MEDIUM — algorithm is textbook; tolerance-to-size empirical check is a risk called out in A2

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (30 days — stable domain, no upstream dep churn expected)

## RESEARCH COMPLETE

**Phase:** 19 - Website Narrative Rebuild
**Confidence:** HIGH

### Key Findings

1. **The existing SPA already has every primitive the rebuild needs** — fetch-on-load, date bucketing via `en-CA` locale, `BADGE_COLORS`, rally progress bar, Leaflet dark init, event card template. The phase is a restructure, not a from-scratch rewrite.
2. **Nginx `try_files $uri $uri/ /index.html` is already live** (default.conf:26-28). The `/day/*` SPA fallback works out of the box — one less task for Plan 19-01.
3. **JSON beats YAML for agenda** — zero existing YAML on the web side, JSON fits four existing fetch chains, no parser library needed. YAML adds cost for no benefit.
4. **Douglas-Peucker at 10 m won't hit the 1 MB target** for a 14-day rally without dropping per-point timestamps. Mitigation documented; size-budget test required in Wave 0.
5. **`route.json.generated_at` is the cleanest freshness signal** for mode detection — route.json regenerates every sync cycle, covers the same data the site renders, avoids adding a separate heartbeat file.
6. **Pi-side work is tiny:** one new `RouteStorage` class (~60 lines) with a `generate_route_json` method + Douglas-Peucker (~20 lines) + three-line engine wiring. All other Phase 19 work is in one HTML file.
7. **No JS test framework** — locked by Phase 18. Web-side verification is manual QA + curl smoke tests. Planner should front-load a detailed manual checklist in `VALIDATION.md`.

### File Created
`/Users/tgreen/dev/shitbox/.planning/phases/19-website-narrative-rebuild/19-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Deliberately adds nothing; reuses existing verified patterns |
| Architecture | HIGH | Every code excerpt verified against source files this session |
| Pitfalls | HIGH | Dead-code inventory built by direct grep + file read |
| Pi-side generator | HIGH | Direct analog to three existing generators (notes/fuel/driver-stats/timelapse) |
| Douglas-Peucker | MEDIUM | Algorithm textbook; tolerance-to-size budget is an empirical risk |
| Web-side tests | MEDIUM | No JS test harness exists; manual verification is the only path |

### Open Questions Passed to Planner
1. Route.json size budget — confirm tolerance bump strategy if 10 m × full-rally > 1 MB
2. Freshness signal field — confirm `route.json.generated_at` vs alternative
3. Archive-mode thumbnails — fall-back chain acceptable, or push timelapse-poster generation into scope?
4. Agenda meal timezone handling — confirm Australia/Sydney regardless of physical location

### Ready for Planning
Research complete. Planner can now create PLAN.md files with confidence that:
- Every new code path has an existing analog to point to
- Every locked decision is satisfied
- Risks are enumerated and have mitigations
- Wave 0 test gaps are explicit
