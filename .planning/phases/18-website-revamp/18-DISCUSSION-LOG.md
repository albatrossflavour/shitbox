# Phase 18: Website Revamp - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 18-website-revamp
**Areas discussed:** Notes section, Driver presentation, Fuel map layer, Grafana issues

---

## Notes Section

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated "Notes" nav tab | Separate tab alongside Status, Videos, Map | |
| Integrated into Status tab | Notes appear as a section within the existing Status page | ✓ |

**Clarification from user:** Many tabs already — user suggested embedding a notes feed on the
front page (Status tab) with links to events, and putting a subtle note indicator on event cards
rather than showing note content there.

| Placement on Status | Description | Selected |
|---------------------|-------------|----------|
| Below latest event stats | Scroll down from the rally stats section | ✓ |
| Above events list | Notes first, events below | |

| Event card indicator | Description | Selected |
|----------------------|-------------|----------|
| Small icon/badge only | Unobtrusive, doesn't change card layout | ✓ |
| Expand to show note snippet | Collapsed preview at bottom of card | |

**User's choice:** Notes embedded in Status tab below stats; blog-style cards with event links;
note icon badge on event cards.

---

## Driver Presentation

| Status widget | Description | Selected |
|---------------|-------------|----------|
| "Current Driver" card alongside stats | Simple card showing active driver name | ✓ |
| In page header/banner | Prominent headline at top of Status | |

**User's note:** Label should be "Current driver" not "who's in charge."

| Full stats location | Description | Selected |
|---------------------|-------------|----------|
| Dedicated "Drivers" tab | New nav tab with breakdown table | ✓ |
| Expand from Status widget | Inline reveal from the homepage widget | |

| Drivers tab content | Description | Selected |
|---------------------|-------------|----------|
| Time driven + percentage | Tony: 14h 22m (62%) | ✓ |
| Event counts by type | HIGH_G / BIG_CORNER / HARD_BRAKE per driver | |
| Visual bar breakdown | Progress bars for time share | |

**User's choice:** New Drivers tab with name + time + percentage only. No event attribution
counts in this phase.

---

## Fuel Map Layer

| Layer visibility | Description | Selected |
|-----------------|-------------|----------|
| Always on | Fuel stops always visible on map | ✓ |
| Toggle-able layer | Layer controls to show/hide | |

| Popup content | Description | Selected |
|---------------|-------------|----------|
| Efficiency this stop + running average | Volume + km/L this stop + km/L average | ✓ |
| Just this stop's efficiency | Per-stop figure only | |

**User's choice:** Always on, popup shows volume + per-stop efficiency + running average.
Cost data never displayed (hard exclusion from Phase 12).

---

## Grafana Issues

| Approach | Description | Selected |
|----------|-------------|----------|
| Describe specific issues | User types description of what's broken | |
| Needs investigation | Planner investigates before implementing | ✓ |

**User's note:** "Needs investigation and a UI/UX pass. It's just not... awesome."

| v2 sensor priority | Selected |
|---------------------|----------|
| INA226 (power/voltage) | — (not wired, deferred) |
| VEML7700 (ambient light/lux) | ✓ |
| DS18B20 dual-probe temps | ✓ |
| LIS3MDL (heading) + anything else in Prometheus | ✓ |

**User's note:** "Anything we have! INA226 isn't wired in and we're not sure what we'll use it
for, so we can skip that one for now."

---

## Claude's Discretion

- Visual treatment of notes feed on Status tab
- Fuel stop pin icon/colour (distinct from event pins)
- Grafana dashboard panel layout and arrangement
- HTML/CSS for the Drivers tab table

---

## Deferred Ideas

- Event attribution counts per driver — future pass
- Notes as map pins — not requested, Status feed only
- INA226 Grafana panels — hardware not confirmed
- Toggle-able fuel stop layer — always-on simpler for now
