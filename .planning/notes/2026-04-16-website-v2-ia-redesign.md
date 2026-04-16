---
created: 2026-04-16
title: Website v2 IA redesign
area: website
source: /gsd-explore session 2026-04-16
feeds: Phase 19
---

## Problem

Current public site (`shit-of-theseus.com`) has grown into a collection of tabs
— Status, Videos, Timelapse, Drivers, Map, Route, Grafana — that each make
sense alone but don't add up to a story. Tony's framing: "lots of good
content, but disjointed."

Telemetry is engineering play; the rally artifacts (videos, GPS tracks, notes)
are the long-term value. Current site is geospatial-first; post-event review
wants chronological and episodic.

Grafana is an unexpected public-facing feature — visitors consistently engage
with it, so it can't be buried.

## Core insight

**Day is already the storage pivot** (captures are stored by date, timelapse
compiles per-day, events and notes have timestamps). It has not yet been
promoted to the UX pivot.

Promote day from storage detail to primary navigation axis. Everything that
happens timestamped threads onto a per-day timeline.

## Target architecture

### Three homepage modes (same layout, state-driven)

Detect mode from most-recent-reading timestamp.

| Mode | Trigger | Content |
|------|---------|---------|
| **Before** | Rally start date still in future | Countdown timer + route map + agenda preview + "follow along from [date]" |
| **Live** | Most recent reading < ~6h old | Today's day view as homepage + current driver + auto-refresh |
| **Archive** | Reading stale / rally finished | Overview card (total km, days, drivers, events) + day grid to browse |

### Day-centric pages

`/day/YYYY-MM-DD` as canonical day URL. Each day page contains:

- **Timeline spine** — timestamped interleave of events, notes, fuel stops,
  start/stop moments. Independent and heterogeneous (a day can have hours of
  events with no notes, a rest stop with four notes and no event).
- **Map slice** — day's GPS polyline highlighted against full-rally polyline
  backdrop, event pins for that day only.
- **Day stats** — km, moving time, top speed, peak G, fuel burned.
- **Video highlights** — day's captured clips.
- **Day timelapse** — embedded.
- **Agenda context** — pre-loaded from hand-authored schedule: camping spot,
  meals, special events, route description.

### Progress-bar day navigator

Single visible element anchoring the whole site. Matches the pattern already
used on the Videos tab.

| Mode | Bar shows |
|------|-----------|
| Before | All segments grey with countdown timer inline ("T-14 days") |
| Live | Completed days filled and clickable, current day highlighted, future days grey |
| Archive | All segments filled and clickable, current selection marked |

Triple duty: arc indicator, navigation, emotional shape of the rally.

### Tab folding

- **Videos tab** → disappears. Videos live inside their day.
- **Timelapse tab** → disappears. Timelapse lives inside its day.
- **Notes feed** → disappears. Notes are part of the day timeline.
- **Drivers tab** → folds into `/about`. Cross-rally driver contribution
  table makes more sense alongside team info than on its own.
- **Map tab and Route tab** → replaced by map-on-day-page (day slice) +
  archive-mode overview (full-rally thumb). No standalone map page.
- **Grafana** → stays as a nav link, not a content tab. Public traffic engages
  with it; it's one click from the homepage.

### About page enhancements

- Tony + Steve bios (already there)
- Total rally stats (distance, days, drivers, events, fuel burned)
- Drivers contribution table (who drove how much)

## Supporting features (tactical)

- **Route polyline** — draw actual GPS track on map, not just event dots.
  Simplified (Douglas-Peucker or similar) so file size stays sensible.
  Day-coloured or day-highlighted. Ship-able independently of the full
  rebuild — has value on the current site.
- **Agenda pre-load** — Tony authors a schedule file (YAML or markdown) with
  day-by-day: route, camping, meals, special events. Site reads this to
  populate day pages *before* telemetry arrives. Turns "day 3" into
  "day 3: Hay → Broken Hill, camping at Mutawintji" without any car data.
- **Mode detection** — single client-side check on page load: compare latest
  reading timestamp against now. Stale = archive mode. Fresh = live mode.
  Future rally start = before mode.

## Decisions locked from this session

1. Day is the primary UX pivot (not event-type, not geography)
2. Three homepage modes, same layout, state-driven
3. Timeline within a day is the spine; notes/events/fuel stops are
   independent items on that spine
4. Progress bar is the day navigator (consistent with Videos tab pattern)
5. Agenda pre-load is content scaffolding; telemetry fills in
6. Grafana stays prominent — it's a public draw, not Tony's hobby corner
7. About page absorbs cross-rally totals + drivers table
8. No standalone map page
9. Route polyline as a separate tactical win, not blocked by rebuild

## Open questions for Phase 19 planning

- Schedule file format (YAML in home-ops? markdown in shitbox repo?)
- Day URL slug — just date, or date + slug ("2026-06-14-hay-broken-hill")?
- How much of the timeline spine is JS-rendered vs server-generated HTML?
- Are agenda files authored pre-rally only, or editable day-of?
- Mobile layout — day view has a lot on it; what collapses?
