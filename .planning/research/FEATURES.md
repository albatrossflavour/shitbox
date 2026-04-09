# Feature Landscape

**Domain:** Rally car companion system — driver display, logging, fuel tracking, driver attribution, website
**Researched:** 2026-04-09
**Milestone context:** v2.0 — new capabilities layered onto a working telemetry system
**Confidence:** HIGH (existing system well-understood; new features draw on established patterns)

---

## Framing

The v1.0 system does the hard thing well: it captures data reliably across thousands of kilometres
of hard power cycles, heat, and intermittent connectivity. v2.0 is about making that data useful
to the people in the car and the people following from home.

The new features split into two audiences:

- **In-car crew**: driver display, field notes, fuel log, who's driving
- **Public website**: followers want to know what's happening, who's driving, how far they've gone

These are genuinely different. In-car features must work completely offline and survive a 50°C
cabin. Website features need to handle data arriving in batches after hours without signal.

---

## Table Stakes

Features that must work or the new capability is broken. Missing any of these means the feature
ship is not ready.

### Driver Display

| Feature | Why Table Stakes | Complexity | Notes |
|---------|-----------------|------------|-------|
| Speed in large, readable text | First thing any driver looks for; missing = useless display | LOW | Already in SSE stream from GPS collector |
| G-force circle (traction circle) | The whole point of having IMU data displayed — lateral/longitudinal dot | MED | Two axes from existing IMU readings; canvas/SVG dot on live stream |
| Current temperature(s) | Engine bay temp is operational; Pi temp is system health; both matter in Aus summer | LOW | DS18B20 readings already in SSE stream |
| GPS signal status indicator | Crew needs to know if GPS has a fix; bad fix = wrong speed displayed | LOW | Fix quality already in GPS collector output |
| Sync backlog indicator | Crew needs to know if data is accumulating behind schedule | LOW | Already tracked by batch sync cursor delta |
| Event ticker (last N events) | What just happened — hard brake, high G, etc. — crew situational awareness | MED | Events already stored; need live feed on display |
| Driver name shown prominently | Who is driving, displayed at all times — "are we logging Tony or Hannah?" | LOW | Simple display of active driver string; set via UI |
| Alerts visible when triggered | Thermal alert, undervoltage, system fault — must be visible in cabin | MED | Needs alert overlay on display; sources already exist |

### Field Notes

| Feature | Why Table Stakes | Complexity | Notes |
|---------|-----------------|------------|-------|
| Free text entry from Pi UI | The whole feature — if you can't type a note, it doesn't exist | MED | On-screen keyboard or USB keyboard input on 7" screen |
| Auto-timestamp on save | Manual timestamps are wrong or forgotten; auto is the only correct default | LOW | `datetime.now()` at save time |
| Auto GPS coordinates on save | Context of where you were is the main value; optional if no fix | LOW | Snapshot of last known GPS fix at time of save |
| Offline-first storage | Notes go to SQLite immediately; sync happens later when connected | LOW | Follows existing batch sync pattern |
| Pin note to a recent event | "That high-G event we just had — here's what happened" is valuable context | MED | FK to event table; recent events list in UI |
| Sync to website | Notes appear on the public blog; the whole point of the feature | MED | New JSON payload in CaptureSyncService or dedicated sync |

### Fuel Log

| Feature | Why Table Stakes | Complexity | Notes |
|---------|-----------------|------------|-------|
| Log fuel stop: volume in litres | Core data capture — without this there's nothing to calculate | LOW | Simple form entry; saves to SQLite |
| Log fuel stop: GPS location auto-captured | Where you stopped is the map pin on the website | LOW | Same as field notes — snapshot GPS at save time |
| km/L efficiency calculated per segment | The metric everyone cares about — how far per litre between stops | LOW | (distance since last stop) / litres added |
| Cumulative efficiency | Overall rally average builds over time | LOW | Simple running average from all stops |
| Website map pins for fuel stops | Followers can see where you refuelled across 4,000 km | MED | New data type in events.json or separate JSON file |
| Efficiency visible on website | "Currently doing 11.3 km/L" is engaging for followers | LOW | Derived stat in website data payload |

### Driver Tracking

| Feature | Why Table Stakes | Complexity | Notes |
|---------|-----------------|------------|-------|
| Set active driver from Pi UI | The entry point — without this nothing else works | LOW | Simple button/select in display UI |
| Record driver stints (who, start time, end time) | Time attribution needs this granularity | LOW | SQLite table: driver, start_ts, end_ts |
| Total time per driver | The headline stat — "Tony drove 52% of the rally" | LOW | Sum stint durations per driver name |
| Allocate driving events to active driver | High-G event at 14:32 → Tony was driving at 14:32 | MED | Join events to stints by timestamp at query time |
| Website: "who's driving now" widget | Public-facing — followers want to know | LOW | Syncs active driver in health/status payload |

### Website Integration

| Feature | Why Table Stakes | Complexity | Notes |
|---------|-----------------|------------|-------|
| Notes appear as blog entries | The feature doesn't exist if it's not visible | MED | New section on website; render from JSON |
| Fuel stop pins on existing map | Map already exists with events; fuel stops are just another layer | MED | Leaflet layer toggle; existing Leaflet map |
| Driver stats shown somewhere | Even a simple percentage breakdown satisfies the question | LOW | New section or sidebar on website |
| "Who's driving now" on homepage | Prominent because it drives engagement; people check it | LOW | Top-of-page widget using synced status payload |

---

## Differentiators

Features beyond the minimum that meaningfully improve the product.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| G-force circle with trail (last N seconds) | More useful than a single dot — shows corner shape, not just peak | MED | Keep circular buffer of last 30s of IMU; fade older points |
| Fuel cost per km (private — Pi only) | Actual operating cost of the rally — useful for crew, not website | LOW | Price per litre field on fuel stop entry; calculated stat; never synced |
| "Better driver" comparison on website | Fun public stat — who triggered more events per km driven? | MED | Events per km by driver; requires stint + event join at sync time |
| Note pinning on website map | Click a map location, see the note written there | MED | lat/lng on note → marker on Leaflet map |
| Event attribution on website | "This hard brake was during Tony's stint" — richer event context | LOW | Driver name in events.json alongside event data |
| Daily fuel efficiency chart | Bar chart: efficiency per day, showing how driving style or terrain affected it | MED | Day-bucketed fuel data; simple chart.js addition to website |
| Note attachments: photos from Pi camera | Take a photo from the Pi at note time to accompany the log entry | HIGH | Complex: needs camera control, thumbnail sync, storage budget |
| Grafana improved graphs on website | Better Grafana embedding, longer time windows, per-driver overlays | MED | Grafana configuration work; iframe improvements on website |

---

## Anti-Features

Things that seem like good ideas but are wrong for this context.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time display refresh below ~500ms | At 100 Hz IMU, driving too many DOM updates slows Chromium → display freezes mid-rally | Throttle display to 2 Hz for speed/G; event ticker on-demand |
| Complex OSK (on-screen keyboard) | Linux/Chromium OSK is flaky on Pi touch display; touch targets unreliable at 50°C with sweaty hands | USB keyboard for notes; minimal tap targets for driver/fuel UI |
| Rich text editor for field notes | Markdown/WYSIWYG adds complexity for zero benefit; these are rally notes not blog posts | Plain textarea, render as `<pre>` or simple `<p>` on website |
| Per-km or per-minute fuel efficiency | Too granular and noisy; segment efficiency (stop to stop) is the right unit | Segment km/L from GPS odometer delta between fuel stops |
| Shared editing / conflict resolution | Two people editing the same note from different devices is not a thing that happens here | Single-writer (Pi is the only entry point); no conflict resolution needed |
| Driver GPS-track deduplication | Auto-detecting who's driving from GPS patterns is a research project; unreliable without OBD data | Explicit driver selection from UI; simple and correct |
| Cost data on website | Fuel cost is private crew information; putting it in the sync payload risks accidental exposure | Store cost in SQLite only; never include in sync or events.json |
| Note editing after sync | Edit-then-resync creates conflict surface; not worth it for occasional rally notes | Notes are append-only; add a new note instead of editing |
| Driver photo / avatar | Adds media management complexity for negligible public engagement gain | Driver name string is sufficient |
| Automated "best driver" algorithm | Defining "best" is contested; ranking creates crew friction for a charity rally | Show raw stats (km/L, events/km); let people draw their own conclusions |

---

## Feature Dependencies

```
Driver Display
  └─ requires ──> GPS collector (speed, lat/lng, fix status) — EXISTS
  └─ requires ──> IMU SSE stream (lateral/longitudinal G) — EXISTS
  └─ requires ──> DS18B20 temperature readings — EXISTS
  └─ requires ──> Driver tracking (active driver name) — NEW
  └─ requires ──> Alert subsystem hook (thermal, undervoltage) — EXISTS (partial)
  └─ requires ──> Event storage (recent events for ticker) — EXISTS

Driver Tracking
  └─ requires ──> Driver stint table in SQLite — NEW (schema)
  └─ requires ──> Pi UI for driver selection — NEW
  └─ enhances ──> Event attribution (join stints to events at query time)
  └─ feeds ──> Website driver stats widget

Field Notes
  └─ requires ──> On-screen or USB keyboard input — NEW (USB keyboard simplest)
  └─ requires ──> GPS collector (location snapshot) — EXISTS
  └─ requires ──> Notes table in SQLite — NEW (schema)
  └─ requires ──> Sync payload extension (notes JSON) — NEW
  └─ optionally pins to ──> Event storage (FK to events table)

Fuel Log
  └─ requires ──> Pi UI form entry — NEW
  └─ requires ──> GPS collector (location snapshot) — EXISTS
  └─ requires ──> GPS odometer (distance since last stop) — EXISTS (stage tracking)
  └─ requires ──> Fuel stops table in SQLite — NEW (schema)
  └─ requires ──> Sync payload extension (fuel JSON) — NEW
  └─ cost field ──> MUST NOT sync to website (private)

Website Revamp
  └─ requires ──> Notes sync payload — NEW (from field notes)
  └─ requires ──> Fuel sync payload — NEW (from fuel log)
  └─ requires ──> Driver stats sync payload — NEW (from driver tracking)
  └─ requires ──> Active driver in status payload — NEW
  └─ builds on ──> Existing Leaflet map (existing)
  └─ builds on ──> Existing events.json pattern (existing)
```

### Dependency Notes

- **All new features require SQLite schema additions**: notes, fuel_stops, driver_stints tables. These should be designed together in a single schema migration phase.
- **Sync payload is the integration point**: Pi calculates all derived stats (km/L, driver percentages, event attribution) before syncing; website is read-only. Keeps website dumb and simple.
- **Driver selection gates event attribution**: Events before first driver selection have no driver. This is acceptable — the first thing crew does on day 1 is set the driver.
- **Field notes and fuel log share the same GPS-snapshot pattern**: Consolidate into a single helper.

---

## MVP Definition

The system is going on a rally. Rally readiness = MVP.

### Ship With (v2.0)

- Driver display: speed, G-circle, temps, driver name, GPS fix, sync status, event ticker, alerts
- Driver tracking: set active driver from UI, basic stint tracking, time percentages
- Field notes: text entry (USB keyboard), auto-timestamp + GPS, pin to event, sync to website
- Fuel log: volume entry, location auto-captured, km/L per segment, sync to website (no cost)
- Website: blog entries section, fuel stop map pins, driver stats section, "who's driving" widget

### Defer Post-Rally

- G-force trail (nice visual improvement; single dot is functional for v2.0)
- "Better driver" comparison stats (needs full rally data to be interesting anyway)
- Daily fuel efficiency chart (same — data accumulates over the rally)
- Note map pins on website (useful but not blocking)
- Grafana deep improvements (cosmetic; existing graphs work)
- Photo attachments on notes (HIGH complexity, LOW priority)

---

## Feature Prioritisation Matrix

| Feature | Driver Value | Public Value | Implementation Cost | Priority |
|---------|-------------|--------------|---------------------|----------|
| Driver display productionised | HIGH | NONE | MED | P1 |
| Driver name on display | HIGH | LOW | LOW | P1 |
| G-force circle | MED | NONE | MED | P1 |
| Alert overlay on display | HIGH | NONE | MED | P1 |
| Driver tracking (stints, time %) | MED | HIGH | LOW | P1 |
| Field notes entry | HIGH | MED | MED | P1 |
| Fuel log (volume + location) | MED | MED | LOW | P1 |
| km/L efficiency | MED | MED | LOW | P1 |
| Website: notes as blog | LOW | HIGH | MED | P1 |
| Website: fuel stop map pins | LOW | HIGH | MED | P1 |
| Website: driver stats | LOW | HIGH | LOW | P1 |
| Website: "who's driving now" | LOW | HIGH | LOW | P1 |
| G-force trail (last 30s) | LOW | NONE | MED | P2 |
| "Better driver" stats | LOW | MED | MED | P2 |
| Fuel cost tracking (Pi only) | MED | NONE | LOW | P2 |
| Daily fuel efficiency chart | LOW | MED | MED | P2 |
| Note map pins on website | LOW | MED | MED | P2 |
| Grafana graph improvements | LOW | MED | MED | P2 |
| Note photo attachments | LOW | MED | HIGH | P3 |

---

## Context-Specific Notes

**Touch input at 50°C is unreliable.** Jeff Geerling's testing on the Pi Touch Display 2 confirmed
that the onscreen keyboard in Chromium is intermittent. For field notes, a USB keyboard is the
right call — rally crew already have one for SSH. For driver selection and fuel entry, large tap
targets are sufficient because these are simple selections, not text entry.

**Driver stint overlap does not happen.** There is one driver and one co-driver. Co-driver doesn't
drive. The stint model is simple: one driver active at any time, changed explicitly from the UI.
No need for overlap handling or GPS-based inference.

**Fuel cost stays private, always.** The sync payload must explicitly exclude the cost field.
This is not a configuration option — it is a hard rule. Cost data lives in SQLite only.

**km/L is the right unit for Australia.** L/100km is what Australian drivers use on the road,
but for a rally context where you're tracking "how far can we go on this tank" the km/L form
is more intuitive. Use km/L on the Pi display and the website; L/100km is for sedans on the highway.

**Website is append-only during the rally.** The sync model pushes from Pi to NAS; the website
reads from NAS. Notes and fuel stops are append-only. No editing from the website, no conflicts.

**Event attribution is a join, not a write.** Don't store driver name on each event row.
Query the driver_stints table at sync time to determine who was driving for each event's timestamp.
This means you can correct a stint assignment after the fact (fix the stint record) without touching
the events table.

**Grafana graphs on the website need better framing, not rebuilding.** The existing iframe
embedding works. The issue is context — unlabelled graphs with no time window or legend description.
Fix with better URL parameters and surrounding HTML explanation, not a Grafana overhaul.

---

## Sources

- [AIM Technologies MX Series dash displays — data shown by professional rally systems](https://www.aimtechnologies.com/mx-series/)
- [Traction circle G-G diagram explained — VR Performance Development](https://vrperfdev.wordpress.com/2016/01/01/traction-circle-g-g-diagram-explained/)
- [G-Force Meter real-time display — VBOX Automotive app](https://www.vboxautomotive.co.uk/index.php/en/customer-area/app-store/vb-touch-g-force-meter)
- [Offline field data collection patterns — Felt platform](https://felt.com/blog/field-data-collection-app)
- [GPS-tagged offline notes with sync-later — NestForms](https://www.nestforms.com/blog/276/Data-Collection-with-your-Offline-GPS-Survey-App)
- [Fuel efficiency KPIs — fleet context, same metrics apply](https://heavyvehicleinspection.com/blog/post/fuel-efficiency-kpis-for-fleets-mileage-idle-time-cost-km)
- [Pi kiosk mode touchscreen — Jeff Geerling's real-world Pi Touch Display 2 assessment](https://www.jeffgeerling.com/blog/2024/home-assistant-and-carplay-pi-touch-display-2/)
- [Offline-first sync patterns — LogRocket 2025](https://blog.logrocket.com/offline-first-frontend-apps-2025-indexeddb-sqlite/)

---

*Feature research for: shitbox v2.0 — rally companion features*
*Researched: 2026-04-09*
