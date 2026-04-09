---
phase: 10-live-dashboard-with-offline-map
verified: 2026-04-09T11:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "Map shows live position dot, breadcrumb, and event markers (D-21 fully satisfied)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Verify mobile single-column reflow on a real phone"
    expected: "Single column layout — top bar, speed, G-gauge, temps, map, event strip — no horizontal overflow"
    why_human: "Tailwind md: breakpoint and flex layout only verifiable in a real browser viewport; automated check confirms the class is present but cannot simulate narrow viewport rendering"
  - test: "Verify D-21 event markers on map with live GPS on the Pi"
    expected: "Triggering a MANUAL_CAPTURE event drops a green circle on the Leaflet map at the event's GPS coordinates"
    why_human: "Requires live GPS fix, event detection, and real Pi hardware. Code path is verified by test; visual rendering on device cannot be confirmed programmatically."
---

# Phase 10: Live Dashboard with Offline Map — Verification Report

**Phase Goal:** Ship a live telemetry dashboard served directly from the Pi, visible in Chromium kiosk and on mobile over rally wifi. Must work offline (map tiles from MBTiles), update at 10 Hz (fast SSE) and 1 Hz (slow SSE), and not impact the capture path.

**Verified:** 2026-04-09

**Status:** passed

**Re-verification:** Yes — after gap closure via plan 10-06

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dashboard serves on 0.0.0.0:8080, reachable from kiosk and LAN | ✓ VERIFIED | config.yaml `host: 0.0.0.0 port: 8080`; DashboardServer wired in engine; operator smoke test confirmed |
| 2 | SSE updates at 10 Hz (fast) and 1 Hz (slow) | ✓ VERIFIED | sse.py: FAST_HZ=10.0, SLOW_HZ=1.0; engine decimates 100 Hz callback to 10 Hz via `% 10` counter; operator smoke test confirmed rates in DevTools |
| 3 | Map tiles served from MBTiles file, works offline | ✓ VERIFIED | tiles.py: `/tiles/{z}/{x}/{y}.png` with TMS-Y flip; `file:...?mode=ro&immutable=1` URI; test_tiles_y_flip and test_tile_404 both pass; operator smoke test confirmed wifi-disconnect worked |
| 4 | Capture path not impacted by dashboard | ✓ VERIFIED | Snapshot update guarded by `% 10` counter and try/except; push_event is non-blocking queue drop; DashboardServer lifecycle on daemon thread; engine catches all dashboard exceptions |
| 5 | Frontend layout matches spec (single HTML, vendored assets, mobile reflow) | ✓ VERIFIED | index.html 187 lines; vendor/ contains alpine.min.js, leaflet.js, leaflet.css, tailwind.min.css, SHA256SUMS with real hashes; `md:grid-cols-2` class present |
| 6 | Map shows live position dot, breadcrumb, and event markers | ✓ VERIFIED | Live position dot and breadcrumb: present (plan 10-04). Event markers: `openEvents()` now calls `L.circleMarker([ev.lat, ev.lng], ...)` guarded by `ev.lat != null && ev.lng != null`; uses `EVENT_COLOURS` map mirroring `.ev-*` CSS palette; `test_sse_events_payload_has_lat_lng` confirms lat/lng survive push_event to SSE stream |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/dashboard/server.py` | FastAPI app factory + DashboardServer lifecycle | ✓ VERIFIED | Substantive (124 lines), DashboardServer wired in engine |
| `src/shitbox/dashboard/sse.py` | Three SSE endpoints at correct rates, 8-client cap | ✓ VERIFIED | 187 lines; MAX_CLIENTS=8; /sse/fast at 10 Hz, /sse/slow at 1 Hz, /sse/events with seed |
| `src/shitbox/dashboard/snapshot.py` | Lock-free shared snapshot, 16 keys | ✓ VERIFIED | GIL-atomic dict rebind; all 16 keys present; update_snapshot and read_snapshot |
| `src/shitbox/dashboard/tiles.py` | MBTiles router with TMS-Y flip and immutable URI | ✓ VERIFIED | `file:{path}?mode=ro&immutable=1`; XYZ→TMS flip `(1 << z) - 1 - y`; 404 on missing |
| `src/shitbox/dashboard/static/index.html` | Single-file Alpine/Tailwind/Leaflet frontend with event map markers | ✓ VERIFIED | 187 lines; all three EventSource consumers; EVENT_COLOURS lookup; L.circleMarker in openEvents(); tile layer; event strip; auto-recentre |
| `src/shitbox/dashboard/static/vendor/SHA256SUMS` | Real hashes for all four vendored assets | ✓ VERIFIED | Four entries with full SHA256 values, no PENDING placeholders |
| `src/shitbox/events/engine.py` | Dashboard instantiation, start/stop, snapshot hook, event push | ✓ VERIFIED | Lines 609-618 (init), 1803-1809 (start), 1917-1923 (stop), 756-782 (snapshot hook), 1020-1036 (event push with lat/lng) |
| `tools/download_tiles.py` | One-shot tile downloader with corridor, rate-limit, idempotency | ✓ VERIFIED | USER_AGENT = "shitbox-rally-tile-prefetch/1.0"; RATE_LIMIT_SECONDS = 0.15; already_present(); build_corridor_tile_set() |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py` | `snapshot.py` | `update_snapshot` called every 10th sample in IMU callback | ✓ WIRED | Line 758: `if self._snapshot_counter % 10 == 0:` → `update_snapshot({...})` |
| `engine.py` | `sse.py` | `dashboard_push_event` called in event detector callback | ✓ WIRED | Lines 1020-1036: `dashboard_push_event({type, timestamp, peak_g, lat, lng, ...})` |
| `engine.py` | `server.py` | `build_dashboard_server` called on init, `start()`/`stop()` in lifecycle | ✓ WIRED | Lines 611-615, 1805-1809, 1919-1921 |
| `engine.py` | `storage.py` | `recent_events_provider=lambda n: self.event_storage.recent(n)` | ✓ WIRED | Line 615; EventStorage.recent() queries real JSON files from disk |
| `index.html` | `/sse/fast` | `EventSource('/sse/fast')` + `addEventListener('fast', ...)` | ✓ WIRED | Lines 98-108; updates speed, gx, gy, peakG |
| `index.html` | `/sse/slow` | `EventSource('/sse/slow')` + `addEventListener('slow', ...)` | ✓ WIRED | Lines 110-143; updates GPS badge, temps, sync badge, position marker, breadcrumb |
| `index.html` | `/sse/events` | `EventSource('/sse/events')` + `addEventListener('event', ...)` + `L.circleMarker` | ✓ WIRED | Lines 145-163; updates event strip array AND places circleMarker on map for events with lat/lng |
| `index.html` | `/tiles/{z}/{x}/{y}.png` | Leaflet tileLayer | ✓ WIRED | Line 87: `L.tileLayer('/tiles/{z}/{x}/{y}.png', ...)` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `index.html` speed display | `this.speed` | `/sse/fast` → `snapshot.speed_kmh` → `engine._current_speed_kmh` | Yes — from GPS collector | ✓ FLOWING |
| `index.html` G-gauge | `this.gx, this.gy` | `/sse/fast` → `snapshot.g_x/g_y` → `sample.ax/ay` from IMU | Yes — from MPU6050/IMU sampler | ✓ FLOWING |
| `index.html` GPS badge / position | `this.gpsBadge, this.marker` | `/sse/slow` → `snapshot.lat/lng/gps_fix_mode` → engine GPS state | Yes — from GPS collector | ✓ FLOWING |
| `index.html` temp tiles | `this.imuTemp, this.socTemp` | `/sse/slow` → `snapshot.imu_temp_c/soc_temp_c` → BME680/DS18B20 and thermal monitor | Yes — from BME680/DS18B20 and thermal monitor | ✓ FLOWING |
| `index.html` event strip + map markers | `this.events` + `L.circleMarker` | `/sse/events` → `sse.event_queue` + `EventStorage.recent()` + `ev.lat/lng` | Yes — from real event detection; lat/lng from GPS at event time | ✓ FLOWING |
| `index.html` map tiles | Leaflet tile requests | `tiles.py` → MBTiles SQLite | Yes — queries real SQLite file | ✓ FLOWING |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED — dashboard requires a running Pi with live hardware (uvicorn server, GPS, IMU). All behavioural paths verified via the 14-test dashboard suite and the operator smoke test on Pi hardware. Total suite: 169 tests, all passing.

---

### Requirements Coverage

Requirements asserted by plan 10-05 frontmatter: D-05, D-10, D-11, D-15, D-20, D-21.

All requirement definitions sourced from `.planning/phases/10-live-dashboard-with-offline-map/10-CONTEXT.md`.

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| D-05 | 10-05 | Listen on 0.0.0.0:8080, both kiosk and LAN | ✓ SATISFIED | config.yaml `host: 0.0.0.0`; DashboardConfig default `host: "0.0.0.0"`; smoke test confirmed phone access |
| D-10 | 10-05 | Single HTML file, Alpine + Tailwind + Leaflet vendored, no CDN | ✓ SATISFIED | index.html exists; vendor/ contains all four assets; SHA256SUMS has real hashes |
| D-11 | 10-05 | Layout: top bar, G-gauge + temps, map, event strip, mobile reflow | ✓ SATISFIED | HTML structure matches spec; `md:grid-cols-2` for reflow; all four sections present |
| D-15 | 10-05 | CartoDB dark tiles via MBTiles SQLite | ✓ SATISFIED | tiles.py serves from MBTiles; download_tiles.py uses CartoDB dark_all template |
| D-20 | 10-05 | Auto-recentre after 10s no interaction | ✓ SATISFIED | index.html lines 89-95: `dragstart/zoomstart` sets `lastInteract`; setInterval checks `Date.now() - lastInteract > 10000` → `map.panTo()` |
| D-21 | 10-05 | Map: live position dot, breadcrumb, event markers as they fire | ✓ SATISFIED | Live dot and breadcrumb: plan 10-04. Event markers: plan 10-06 adds `L.circleMarker` in `openEvents()` with `EVENT_COLOURS` lookup, guarded by `ev.lat != null`. `test_sse_events_payload_has_lat_lng` gives regression coverage. |

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder comments, no empty implementations, no hardcoded empty data in rendering paths. The previous stub in `openEvents()` is fully resolved.

---

### Human Verification Required

#### 1. Mobile single-column reflow

**Test:** Load `http://<pi-lan-ip>:8080` on a phone in portrait orientation.
**Expected:** Single-column layout — top bar, speed, G-gauge, temp tiles, map section, event strip — no horizontal scroll or overflow.
**Why human:** CSS breakpoint behaviour cannot be verified by static analysis; the Tailwind classes are confirmed present but rendering requires a real browser viewport.

#### 2. Event markers on map — live Pi verification

**Test:** Trigger a MANUAL_CAPTURE event on the Pi (button press) with a live GPS fix. Observe the Leaflet map in Chromium kiosk or mobile browser.
**Expected:** A green circle (`#238636`) appears on the map at the GPS coordinates of the event, with a popup reading "MANUAL" or similar.
**Why human:** Requires live GPS fix, event detection, and real Pi hardware. The code path is fully verified by `test_sse_events_payload_has_lat_lng` and static analysis; visual confirmation on device is the remaining check.

---

### Gaps Summary

No gaps remain. D-21 is fully satisfied by plan 10-06: `openEvents()` in `index.html` now places a coloured `L.circleMarker` on the Leaflet map for every incoming SSE event with non-null `lat`/`lng`, using the `EVENT_COLOURS` map that mirrors the `.ev-*` CSS palette exactly. The test `test_sse_events_payload_has_lat_lng` provides automated regression coverage confirming coordinates survive the `push_event` → SSE stream path.

All six observable truths are verified. All required artifacts pass all four verification levels. All key links are wired.

---

_Verified: 2026-04-09_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes — gap closure after plan 10-06_
