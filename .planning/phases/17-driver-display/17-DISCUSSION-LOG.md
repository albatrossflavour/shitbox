# Phase 17: Driver Display - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 17-driver-display
**Areas discussed:** Kiosk page strategy, Layout/map/spacing, Alert overlays, Event ticker

---

## Kiosk Page Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| New `/kiosk` endpoint | Purpose-built page, existing dashboard unchanged | |
| Rework existing `index.html` | Kiosk-first layout, phone version dropped | ✓ |

**User's choice:** Rework existing page, drop phone layout
**Notes:** Clean approach — one file, no parallel maintenance burden.

---

## Layout / Map / Spacing

| Option | Description | Selected |
|--------|-------------|----------|
| Always-on Leaflet map | Map visible in main layout | |
| Map behind a button | Tap to open full-screen overlay, tap to dismiss | ✓ |
| No map | Distance-to-checkpoint tile only | |

**User's choice:** Map behind a button overlay, with distance-to-checkpoint as a data tile
**Notes:** User flagged trackpad inaccuracy on the keyboard — map-on-demand means
one big tap target, no precision required. User deferred visual layout specifics to Claude.

## Claude's layout recommendation (confirmed)
- Top strip: speed (dominant), active driver, GPS badge, sync badge
- Centre left: G-force circle (larger than current — no map competing for space)
- Centre right: IMU temp, SoC temp, distance to next waypoint tiles
- Bottom strip: event ticker
- MAP button: opens full-screen Leaflet overlay, tap anywhere to dismiss

---

## Alert Overlays

| Option | Description | Selected |
|--------|-------------|----------|
| Event overlays only | Telemetry events (HIGH_G etc.) trigger overlays | partial |
| All events + system alerts | Both telemetry events and system alerts trigger overlays | ✓ |
| Tap-to-dismiss | User must dismiss manually | |
| Auto-dismiss, uniform | All overlays same duration | |
| Auto-dismiss, tiered | Event overlays short, system alert overlays longer | ✓ |

**User's choice:** All event types trigger overlay; system alerts stay longer
**Notes:** "They should all auto-dismiss, but maybe the alerts stay for longer?"
Resolved as: event overlays 3s, system alert overlays 10s. System alerts use red
background to distinguish from informational event flashes.

---

## Event Ticker

| Option | Description | Selected |
|--------|-------------|----------|
| Static last-10 list (existing) | List updates in place | |
| CSS horizontal marquee | Events scroll sideways | |
| Push from top (log style) | New events appear at top, older shift down | ✓ |

**User's choice:** New events push in from the top
**Notes:** Last 5 events shown (reduced from existing 10 to fit kiosk layout).
Each entry: event badge + peak G + elapsed time.

---

## Folded Todos

- **Temperature sensors missing from SSE stream** — folded into scope. Working temps are
  required by DISP-01. Investigation and fix is part of this phase's deliverables.

## Claude's Discretion

- Exact CSS proportions for 800x480 layout
- G-force circle sizing
- Haversine JS implementation for distance-to-waypoint
- Map overlay animation and close button placement
- Speed display font size (very large, glanceable)
- Whether driver name animates on change
- Tailwind utility classes

## Deferred Ideas

- Phone/tablet responsive layout — dropped from scope
- On-screen keyboard for driver name — carried from Phase 13 deferred
- Per-driver event counts on kiosk — Phase 18
- Live video preview — separate phase
