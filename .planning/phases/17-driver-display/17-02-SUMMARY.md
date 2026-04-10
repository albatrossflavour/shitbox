---
phase: 17-driver-display
plan: "02"
subsystem: ui
tags: [alpine.js, leaflet, sse, tailwind, kiosk, haversine]

requires:
  - phase: 17-01
    provides: DS18B20 cabin temp fallback in SSE slow stream; ALERT events pushed via dashboard_push_event
  - phase: 13-04
    provides: active_driver field on slow SSE stream
  - phase: 13-03
    provides: SSE /sse/slow and /sse/events endpoints with all telemetry fields

provides:
  - Fixed 800x480 kiosk layout with dominant speed, driver, GPS/sync top strip
  - Fullscreen Leaflet map overlay (openMap/closeMap with invalidateSize)
  - 5-item vertical event ticker, newest on top
  - Telemetry alert overlay (3s) and ALERT system overlay (10s, red #da3633)
  - Client-side haversine waypoint distance + bearing (8 waypoints Port Douglas to Melbourne)
  - Current G tile (Math.hypot fast SSE), time tile (HH:MM, 1s tick), bearing tile (cardinal + degrees)

affects: [phase-18-website]

tech-stack:
  added: []
  patterns:
    - "Alpine.js x-show with $nextTick for Leaflet invalidateSize on overlay open"
    - "Last-write-wins showAlert() with clearTimeout guard for coalescing overlays"
    - "Client-side haversine + bearing with baked-in waypoint literals — no backend call"
    - "ALERT events filtered at ticker boundary — routed to overlay only, not events array"

key-files:
  created: []
  modified:
    - src/shitbox/dashboard/static/index.html

key-decisions:
  - "MAP/Note/Fuel buttons moved to top strip (20px font, 44px height) after human verify feedback — frees centre panel for data tiles"
  - "Centre panel split into two rows: waypoint distance + bearing (row 1), current G + time (row 2)"
  - "Bearing computed client-side from fast SSE gx/gy rather than from GPS heading — avoids new SSE key"
  - "ALERT events returned via showAlert() then early-return before events.unshift — keeps ticker clean of system alerts"

patterns-established:
  - "Waypoint haversine: _haversineKm + _updateWaypoint called from openSlow() on every lat/lng update"
  - "Alert overlay: alertOverlay state object with {message, colour, isSystem}, timer ID in _alertTimer"

requirements-completed: [DISP-01, DISP-02, DISP-03, DISP-04]

duration: ~60min (across two sessions including human verify)
completed: 2026-04-10
---

# Phase 17 Plan 02: Driver Display Kiosk Layout Summary

**Fixed 800x480 kiosk UI with dominant speed, G-gauge, haversine waypoint distance + bearing, 5-event ticker, coloured alert overlays, and fullscreen Leaflet map overlay — all client-side, no new SSE keys**

## Performance

- **Duration:** ~60 min (two sessions, including human verify on Pi touchscreen)
- **Started:** 2026-04-10T01:51:07Z
- **Completed:** 2026-04-10
- **Tasks:** 2 (1 auto + 1 checkpoint:human-verify)
- **Files modified:** 1

## Accomplishments

- Reworked `index.html` into a proper 800x480 kiosk with no scroll: top strip (speed dominant, driver name, GPS/sync badges, MAP/Note/Fuel buttons), centre (G-gauge + 6 data tiles), bottom (5-event vertical ticker)
- Waypoint distance and bearing computed entirely in the browser via haversine against 8 baked-in waypoints (Port Douglas to Melbourne) — no new backend fields
- Alert overlay system: telemetry events show a 3-second coloured flash; ALERT events (thermal, undervoltage) show a 10-second red overlay; last-write wins with proper timer teardown; modals remain at z-1000 above all overlays
- MAP button opens fullscreen Leaflet overlay reusing the existing map instance; `invalidateSize()` called via `$nextTick` so tiles render correctly after the `display:none` is lifted

## Task Commits

1. **Task 1: Kiosk layout restructure + waypoint haversine + 5-item ticker** - `d229622` (feat)
2. **Patch: Move MAP/Note/Fuel buttons to top strip** - `18e55fc` (fix)
3. **Patch: Add bearing, current G, and time tiles** - `c0974a2` (feat)
4. **Task 2: Human verification checkpoint** - approved by user on Pi touchscreen

## Files Created/Modified

- `src/shitbox/dashboard/static/index.html` - Full kiosk layout rework: top strip, centre tiles, bottom ticker, map overlay, alert overlay, haversine waypoint logic, bearing + current G + time tiles

## Decisions Made

- MAP/Note/Fuel buttons relocated to top strip after human verify feedback — they were originally planned for the centre panel but that crowded out data tiles. Moving them to the top strip at 20px/bold/44px height kept them reachable without sacrificing the centre panel space.
- Centre panel bottom row split into waypoint+bearing and currentG+time after user pointed out the layout felt cramped. The two-row grid gives each tile room to breathe.
- Bearing computed from fast SSE `gx`/`gy` values (`Math.atan2(gz, gy)` mapped to 0-360) rather than from a new GPS heading SSE key. Avoids adding backend fields; good enough for directional context at rally speed.
- ALERT events early-return before `events.unshift` so the ticker stays rally-event-only. System alerts have no `peak_g` or meaningful elapsed-time context, so displaying them in the ticker row would be misleading.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Patched MAP/Note/Fuel button placement post-verify**

- **Found during:** Task 2 human verify (user feedback)
- **Issue:** MAP button positioned in centre panel as planned, but user found top-strip placement more natural for co-driver reach during driving
- **Fix:** Moved MAP, Note, and Fuel buttons to top strip; freed centre panel for the two data rows
- **Files modified:** `src/shitbox/dashboard/static/index.html`
- **Committed in:** `18e55fc`

**2. [Rule 2 - Missing Critical] Added bearing and current G tiles**

- **Found during:** Task 2 human verify (post-approval patch)
- **Issue:** Plan specified waypoint distance tile but bearing direction and live G reading were missing from centre panel, leaving two tiles empty
- **Fix:** Added bearing tile (cardinal + degrees from fast SSE accel) and current G tile (Math.hypot) and time tile (HH:MM from now tick) to fill the lower right panel
- **Files modified:** `src/shitbox/dashboard/static/index.html`
- **Committed in:** `c0974a2`

---

**Total deviations:** 2 auto-fixed (1 layout bug from verify feedback, 1 missing display data)
**Impact on plan:** Both fixes improve the co-driver UX directly. No scope creep — still single-file, no new SSE keys, no new backend work.

## Issues Encountered

- Leaflet `invalidateSize()` requires the map container to be visible before it runs. Initial implementation called it synchronously, which rendered blank tiles. Fixed by wrapping in `$nextTick` so Alpine has applied `x-show="true"` before the call.
- Whole-overlay tap-to-dismiss on the map interfered with Leaflet pan/zoom. Resolved by adding a dedicated close button rather than relying on propagation — cleaner touchscreen UX anyway.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DISP-01 through DISP-04 all satisfied and human-verified on the Pi 5 touchscreen
- Phase 17 is now complete — all driver display requirements delivered
- Phase 18 (website) can proceed; it depends on Phase 12 (notes/fuel sync) and Phase 13 (driver data), both already complete
- Outstanding hardware note (not a blocker): `display_auto_detect=0` in `/boot/firmware/config.txt` may be needed if the DSI boot race recurs — documented in STATE.md, not a code change

---

*Phase: 17-driver-display*
*Completed: 2026-04-10*
