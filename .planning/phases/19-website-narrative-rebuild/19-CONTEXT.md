# Phase 19: Website Narrative Rebuild - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Transform `shit-of-theseus.com` from a tab-collection into a day-centric rally scrapbook.

Three homepage modes (before / live / archive), per-day pages at `/day/YYYY-MM-DD` with a
chronological timeline spine, a site-wide day-nav progress bar, and tab folding that
collapses Videos / Timelapse / standalone Map / Route into day pages, and Drivers / The Car
into `/about`. Grafana stays one click from home.

Route polyline (`route.json` generation + Leaflet polyline rendering) is **folded in** from
the pending todo so day pages can show a day-slice track against a full-rally backdrop.

Out of scope: a build step for the website (locked from Phase 18); Pi-side API editing of
agenda content (static YAML in home-ops is sufficient); fuel cost data anywhere on the site
(hard exclusion from Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Routing and URLs
- **D-01:** `/day/YYYY-MM-DD` served via nginx `try_files $uri $uri/ /index.html`; the SPA
  reads `location.pathname` on load to decide which day to render. Real URLs, shareable, no
  build step, no hash routing for day pages.
- **D-02:** Day URL slug is date-only — no descriptor (no `/day/2026-06-14-hay-broken-hill`).
  Human-readable titles ("Day 3: Hay → Broken Hill") live in the day header, sourced from
  the agenda file. Keeps URLs stable across agenda edits and protects deep links.

### Mode detection
- **D-03:** Rally `start_date` and `end_date` live in the agenda YAML. Mode resolved
  client-side on page load:
  - `before` when today < start_date
  - `live` when start_date ≤ today ≤ end_date AND latest reading < 6 h old
  - `archive` otherwise
- **D-04:** One check on load; re-check on tab focus and on the 2-minute poll interval in
  live mode. No state machine beyond that.

### Timeline data pipeline
- **D-05:** Data join is **client-side**. Browser fetches `events.json` + `notes.json` +
  `fuel.json` + `driver-stats.json` + `route.json` + `agenda.json` once, filters by day on
  navigation. No new Pi generators for per-day JSON (reuses the fetch-and-filter pattern
  established in Phase 18).
- **D-06:** Timeline spine items (interleaved chronologically for each day):
  - All event types in `events.json` (HIGH_G, BIG_CORNER, HARD_BRAKE, ROUGH_ROAD, MANUAL/BUTTON, **BOOT**).
    BOOT clips stay on the spine — they mark departures from stops ("pulling out of a
    roadhouse") and have dashcam footage worth showing.
  - Notes (full body rendered inline)
  - Fuel stops (volume + efficiency, link to map pin)
  - Stage start/stop (derived from first/last reading of the day — narrative bookends)
  - Driver changes (from `driver_stints` — e.g. "Tony takes over near Roma at 11:30")
  - Agenda markers (camping spot in evening, meals at midday — styled italic/muted to
    distinguish from telemetry)
- **D-07:** Explicitly **excluded** from the spine: thermal / undervoltage alerts and other
  system blips that don't produce an event record with video. Those live in Grafana for the
  operational view.
- **D-08:** Live-mode refresh: 2-minute poll of the source JSON files. Polling faster burns
  bandwidth with no freshness gain — Pi sync cadence is the actual floor. Also refresh when
  the tab regains visibility.

### Agenda content
- **D-09:** Agenda is **static YAML** committed to the home-ops repo alongside `webroot/`.
  Deploys with the site via Flux HelmRelease. Day-of edits go through git push + Flux
  reconcile (tolerable — agenda is mostly pre-rally planning content).
- **D-10:** Rough shape (final schema pinned down during planning):

  ```yaml
  rally:
    start_date: YYYY-MM-DD
    end_date: YYYY-MM-DD
    team: "A Team Has No Name"
    title: "Shitbox Rally 2026"
  days:
    - date: YYYY-MM-DD
      title: "Hay → Broken Hill"
      route: "prose description of the day's route"
      camping: "Mutawintji NP"
      meals:
        - { time: "12:30", where: "Cobar bakery" }
      notes: "optional prose for the day"
  ```

### Day page structure
- **D-11:** Single vertical scroll. No tabs-within-day, no collapsible sections. Scrapbook
  reads top-to-bottom like a journal.
- **D-12:** Section order:
  1. Day header (date, "Day N of M", title from agenda)
  2. Agenda context block (camping, meals, route description)
  3. Day stats row (km, moving time, top speed, peak G, fuel burned)
  4. Map slice (full-rally polyline as grey backdrop, day slice highlighted, day's event
     pins only)
  5. Timeline spine
  6. Video highlights (day's clips, reusing the Phase 18 event-card pattern)
  7. Day timelapse (embedded, visual payoff)
- **D-13:** Mobile uses the same section order, no collapse, sized for phone width.
  Desktop gets a centred max-width container. Rally-watchers read on phones — don't make
  them hunt.

### Day-nav progress bar
- **D-14:** Site-wide, sits under the top nav. One segment per rally day (count derived
  from agenda `start_date` / `end_date`). Each segment shows day number (big) + date (small).
- **D-15:** Segment states: filled orange = completed, bright orange = current, grey =
  future. Completed and current days are clickable (navigate to `/day/YYYY-MM-DD`); future
  days are inert (no content to show yet). Visually extends the existing rally-progress bar
  style — not a new pattern.

### Homepage by mode
- **D-16:** `before`: countdown to `start_date` + planned-route map (rendered from agenda
  coordinates) + day-list preview ("Day 1: ..., Day 2: ..., Day 3: ...") + "Follow along
  from [start_date]" CTA.
- **D-17:** `live`: today's day page **is** the homepage. 2-minute auto-refresh.
  Current-driver widget near the top.
- **D-18:** `archive`: overview card (total km, active days, events, fuel burned, drivers
  count) + **linear** day grid (not calendar — rally has no rest days; calendar implies
  gaps that won't exist). Each day card shows date, title, and a thumbnail (day timelapse
  poster frame, falling back to the day's first event still).

### Nav after rebuild
- **D-19:** Top nav shrinks to: **Home, Grafana, About, Donate**.
- **D-20:** Removed from nav:
  - **Status** — becomes the homepage (mode-dependent content)
  - **Drivers** — folds into `/about` (team + driver contribution table)
  - **Videos, Timelapse** — live inside day pages
  - **Map** — replaced by day-slice maps + archive-mode overview map
  - **Route** — folds into agenda + archive-mode overview
  - **The Car** — folds into `/about`

### Route polyline (folded from todo)
- **D-21:** `route.json` generation is part of Phase 19. New JSON generator reads from
  `gps_readings`, applies Douglas-Peucker simplification (~10 m tolerance), groups by day
  so the website can highlight a day slice against the full rally. Target: < 1 MB for full
  rally. Cost field: N/A (gps_readings has no cost column; still nothing sensitive in the
  output).
- **D-22:** Full-rally polyline rendered on archive-mode overview map. Day-slice polyline
  highlighted on day-page map, with the remaining polyline shown as a grey backdrop so the
  day's segment is visually obvious.

### Claude's Discretion
- Card styling, exact spacing, typography refinements (stay consistent with existing dark
  theme: `#0d1117` / `#161b22` / `#c06000` orange)
- Timeline icon set (SVG per spine-item type) — reuse `BADGE_COLORS` for event icons
- Thumbnail fall-back chain for archive day-grid cards
- Progress-bar segment hover / focus states
- Exact nginx rewrite rule placement in `default.conf`
- Simplification tolerance refinement if `route.json` exceeds 1 MB at ~10 m

### Folded Todos
- **Draw actual GPS route polyline on map** (`.planning/todos/pending/2026-04-16-draw-actual-gps-route-polyline-on-map.md`)
  — generates `route.json` via `CaptureSyncService`, renders as Leaflet polyline. Folded
  into D-21 / D-22 because the day-slice polyline is part of the day-page map and sharing a
  single generator is simpler than doing it twice.

</decisions>

<canonical_refs>
## Canonical References

Downstream agents **MUST** read these before planning or implementing.

### Source doc (read first)
- `.planning/notes/2026-04-16-website-v2-ia-redesign.md` — /gsd-explore session that framed
  the phase. Three homepage modes, day-centric IA, progress-bar day navigator, tab folding,
  and the open questions this discussion resolved.

### Website repo (primary implementation target)
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html` — current
  single-file SPA (1717 lines). Read before touching anything. Existing dark theme,
  fetch-on-load JSON pattern, and the rally-progress bar style at lines 99–131 that the
  day-nav progress bar extends.
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/nginx-config/default.conf` —
  nginx config. Needs `try_files $uri $uri/ /index.html` for `/day/*` rewrite (D-01).
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/helmrelease.yaml` — Flux
  HelmRelease. Agenda YAML either lands in `webroot/` or as a ConfigMap-mounted volume.

### Pi-side data sources (consumed unchanged, except `route.json` is new)
- `src/shitbox/events/storage.py` — `EventStorage.generate_events_json()` is the template
  for the new `generate_route_json()` method.
- `src/shitbox/sync/capture_sync.py` — `CaptureSyncService` + `register_json_generator` (2-arg
  form: `(name, fn)`; filename derived as `{name}.json`). Route generator registers here.
- `notes.json` served from `/captures/notes.json` — Phase 12 `generate_notes_json()`.
- `fuel.json` served from `/captures/fuel.json` — Phase 12 `generate_fuel_json()`, cost
  excluded at SQL level.
- `driver-stats.json` served from `/captures/driver-stats.json` — Phase 13 generator.
- `events.json` served from `/captures/events.json` — existing generator.

### Prior phase context (locked decisions to respect)
- `.planning/phases/18-website-revamp/18-CONTEXT.md` — single-file SPA, vanilla JS, dark
  theme, fetch-on-load, Leaflet/CartoDB dark tiles, no cost data ever.
- `.planning/phases/12-schema-foundation-and-logbook-api/12-CONTEXT.md` — notes / fuel
  payload shape, cost exclusion enforcement.
- `.planning/phases/13-driver-tracking/13-CONTEXT.md` — `driver-stats.json` payload shape,
  active driver field.

### Folded todo
- `.planning/todos/pending/2026-04-16-draw-actual-gps-route-polyline-on-map.md` — route.json
  generator + polyline rendering acceptance criteria.

### Requirements
- `.planning/ROADMAP.md` §"Phase 19: Website Narrative Rebuild" — phase goal and the seven
  success criteria this phase must hit.
- `.planning/REQUIREMENTS.md` — no NARR-* REQ-IDs yet; the planner should propose NARR-01
  through NARR-N covering the success criteria (or extend existing WEB-* IDs if the
  planner decides that fits better).

### Rollback anchor
- home-ops git tag **`shitbox-pre-phase-19`** (pushed 2026-04-16, pins `e5bb8389`) —
  rollback target if the rebuild needs reverting. `git reset --hard shitbox-pre-phase-19`
  from the home-ops repo root.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Rally progress bar CSS** (`webroot/index.html` lines 99–131): `.rally-progress`,
  `.rally-progress-header`, `.rally-progress-bar`, `.rally-progress-fill`. Day-nav bar
  extends this visual style — new segment logic and states, same typographic treatment.
- **Dark theme tokens**: `#0d1117` bg, `#161b22` cards, `#21262d` borders, `#c06000` orange
  accent, `#e0a040` amber, `#f0dbb8` warm white, `#8b949e` muted text. Locked from Phase 18.
- **BADGE_COLORS map** (`webroot/index.html` lines 855–864): per-event-type colours.
  Timeline spine icons reuse this mapping so event spine items carry their type colour.
- **Event card pattern** (`.event-card` in `.events-grid`): reused for day-page video
  highlights (D-12 step 6).
- **fetch-on-load pattern** (line 914, `fetch('/captures/events.json')`): Phase 18
  established parallel fetches for events/notes/fuel/driver-stats. Day pages add
  `agenda.json` and `route.json` to the same pattern.
- **Leaflet dark map initialisation** (~line 892, CartoDB dark tiles): reused for both the
  day-slice map and the archive-mode overview map. Polyline is a new `L.polyline()` layer
  with day-highlighting logic.
- **Section/tab pattern** (`data-section` attr + `.section.active` + click handler ~line
  1027): being dismantled this phase. SPA routes off `location.pathname` for day pages and
  keeps simple `data-section` state for homepage modes (or replaces it entirely — planner
  decides).

### Established Patterns
- Single-file SPA, no build step, no frameworks — all changes in `index.html`. Locked.
- Vanilla JS: `var`, not `const` / `let`. Match existing style.
- Inline CSS; no external CSS file.
- JSON fetched from `/captures/*.json` (nginx serves from NFS mount of the Pi's sync dir).

### Integration Points
- `nginx-config/default.conf` — add `try_files` rewrite for `/day/*` paths.
- `webroot/index.html` nav block (lines ~667–677) — shrink to Home / Grafana / About /
  Donate.
- `webroot/index.html` section blocks (lines ~680–950) — Status folds into homepage
  rendering; Videos / Timelapse / Map / Route / Drivers / Car sections are removed or
  content-folded.
- `webroot/agenda.json` (new) — hand-authored rally schedule (or `agenda.yaml` with a
  one-line JS YAML loader — planner's call).
- `webroot/captures/route.json` (new, generated by Pi, rsynced via `CaptureSyncService`).
- `src/shitbox/events/storage.py` — new `generate_route_json()` method registered via
  `register_json_generator('route', ...)` in the engine's generator-registry wiring.

</code_context>

<specifics>
## Specific Ideas

- Scrapbook feel — read the journal top-to-bottom. No tabs-within-day fragmentation.
- BOOT events matter narratively: the "pulling out of a roadhouse" clip is context, not
  noise. System-only blips (thermal / undervoltage alerts with no video) stay in Grafana.
- Progress bar is triple-duty: arc indicator, navigation, emotional shape of the rally.
- Grafana stays prominent as a public draw — it's unexpected engagement, not a hobby
  corner. One click from home.
- Tag `shitbox-pre-phase-19` is the rollback anchor. If the rebuild goes sideways, hard
  reset and re-deploy.

</specifics>

<deferred>
## Deferred Ideas

- **Pi-side API editability for agenda** — considered, rejected. Agenda is mostly pre-rally
  planning; day-of edits via git push are acceptable. Revisit if the workflow breaks during
  the rally itself.
- **Pre-generated per-day JSON from the Pi** — considered, rejected. Client-side filter
  scales fine for a ~14-day rally. Revisit if total payload exceeds ~2 MB or if mobile
  performance degrades.
- **Calendar grid for archive mode** — rejected. Rally has no rest days; calendar implies
  gaps that won't exist. Linear day grid chosen instead.
- **Descriptor slugs in day URLs** — rejected. Couples URL to agenda text; agenda edits
  would break deep links.
- **Mobile-specific tab / accordion collapse** — rejected. Single vertical scroll works on
  all widths.
- **Boot / system blips on the timeline** — rejected (clarified, not deferred). BOOT events
  with video DO make the spine; only noise-only alerts are filtered.
- **More on `/about`**: event attribution counts per driver were deferred in Phase 18; not
  pulled forward here unless the planner finds a natural fit.

### Reviewed Todos (not folded)
- `2026-04-09-investigate-temperature-sensors-missing-from-dashboard-sse-stream.md` —
  scope-matched on keyword noise only; belongs in Phase 15 (Undervoltage and Monitoring),
  not a website phase.

</deferred>

---

*Phase: 19-website-narrative-rebuild*
*Context gathered: 2026-04-16*
