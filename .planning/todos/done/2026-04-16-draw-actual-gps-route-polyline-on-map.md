---
created: 2026-04-16
title: Draw actual GPS route polyline on map
area: website
files:
  - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
  - src/shitbox/events/storage.py
---

## Problem

Current map shows event pins only. The track between events is invisible, so
the map reads as a scatter of dots rather than a journey. Doesn't give a
sense of actual path travelled.

## Solution

Draw the GPS track as a Leaflet polyline on the map.

### Data side

- Generate `/captures/route.json` (or similar) as part of `CaptureSyncService`
  / `EventStorage.generate_events_json()` flow
- GeoJSON LineString (or array of `[lat, lng]` pairs) from the `gps_readings`
  table
- Simplify the track to keep file size reasonable — Douglas-Peucker algorithm
  with a tolerance appropriate for the zoom levels we care about (probably
  ~10m). Avoid downloading 86,400 points per day into the browser.
- Split or group by day to enable day-highlighting in Phase 19

### Website side

- Add `L.polyline()` or `L.geoJSON()` layer to the Leaflet map
- Colour: subtle grey by default so event pins still dominate visually
- Later (Phase 19): colour current day differently, or fade completed vs
  current day segments

## Why independent

Small, testable, useful on the current site. Doesn't require the Phase 19
rebuild to land. Once Phase 19 starts, the day-highlighting behaviour is a
styling change, not a data model change — the polyline data structure is
already what Phase 19 needs.

## Acceptance

- `route.json` generated and rsynced with the existing capture sync
- Leaflet map draws the polyline
- File size < 1 MB for a full rally (simplified track)
- No cost data or sensitive info in the generated file
