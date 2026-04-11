---
phase: 18-website-revamp
plan: 03
type: summary
status: complete
---

# Plan 18-03 Summary — Fuel Map Pins + Grafana Fix + Nginx Cache

## What was done

### Task 1: index.html

**Fuel stop map layer** added inside `initMap()`, after the existing event markers loop:

- Orange `fillColor: '#c06000'` circle markers for each fuel stop with GPS coordinates
- Popup shows: date/time, volume (L), per-stop km/L, running cumulative average km/L
- First stop always shows em dash for both efficiency values (no prior odometer reference)
- No cost data referenced anywhere
- Variable names prefixed `f` to avoid collision with event loop variables

**Grafana iframe** updated:

- `src` changed from `shitbox-telemetry` to `shitbox-rally-command`
- iframe height raised from `80vh` to `90vh`
- "Open full Grafana dashboard" link moved above the iframe, URL updated to `shitbox-rally-command`
- Description paragraph added: "Live sensor data from the Shit of Theseus. Updated every 30 seconds while the car is connected."
- `grafana-loading` div added with onload handler to hide it once iframe loads

### Task 2: nginx default.conf

No-cache regex expanded from `(events|timelapse)` to `(events|timelapse|notes|fuel|driver-stats)`.
`notes.json`, `fuel.json`, and `driver-stats.json` now get `Cache-Control: no-cache, no-store, must-revalidate` instead of the 24-hour `max-age=86400` from the `/captures/` catch-all.

## Verification

```
grep -c "fillColor.*c06000\|shitbox-rally-command\|Fuel Stop\|cumAvgKml\|grafana-loading" index.html
# → 9

grep "notes|fuel|driver-stats" nginx-config/default.conf
# → location ~ ^/captures/(events|timelapse|notes|fuel|driver-stats)\.json$ {
```

No `shitbox-telemetry` in any iframe src (only remaining reference is the about-card `<code>` tag for the systemd service name).

## Files modified

- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html`
- `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/nginx-config/default.conf`
