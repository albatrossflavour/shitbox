---
created: 2026-04-26T14:03:50.025Z
title: Audit Grafana shitbox-rally-command dashboard
area: monitoring
files:
  - ~/dev/home-ops/kubernetes/apps/observability/grafana/app/dashboards/shitbox-rally-command.json
  - ~/dev/home-ops/kubernetes/apps/observability/grafana/app/dashboards/shitbox-telemetry.json
  - /tmp/dashboard-update.py (prepared mid-session, may not survive reboot)
---

## Problem

`shitbox-rally-command` is the only Grafana dashboard that's actually consumed (iframed on the public site). Surfaced during the SEN0460-stub-driver investigation (2026-04-26) that the dashboard has gaps: it doesn't render `shitbox_gas_resistance` (BME680 VOC channel) anywhere, and a stuck-stub-style failure on any sensor would not surface visually — diagnosis required SQL against `telemetry.db`. Two dashboards (`shitbox-rally-command.json` and `shitbox-telemetry.json`) exist with overlapping but inconsistent metric coverage and no clear single source of truth. User wants to consolidate.

## Solution

Three concrete items already scoped:

1. **Add `shitbox_gas_resistance` to the Cabin Air Quality panel (id 52).** Right-axis treatment in kΩ (divide raw ohms by 1000), unit `kΩ`, distinct colour from PM2.5. Higher = cleaner air. Field override on series name `VOC` to set `custom.axisPlacement: right`. PM2.5 keeps existing threshold-coloured rendering.

2. **Add a SENSOR HEALTH row.** Per-sensor freshness stat panels using `time() - timestamp(metric)` in seconds. Thresholds: 0–10s green, 10–60s amber, >60s red. Sensors to cover: IMU (`shitbox_ax`), GPS (`shitbox_lat`), Cabin Env (`shitbox_pressure`), PM2.5 (`shitbox_pm25`), VOC (`shitbox_gas_resistance`), 1-Wire Temp (`shitbox_temp`), Light (`shitbox_lux`), Power (`shitbox_bus_voltage`). 8 panels × 3w = full row width. Place at bottom of dashboard (y=59 onward) so it doesn't disrupt existing layout. This panel exists specifically so a future stuck-stub like the SEN0460 surfaces visually without needing a SQL query.

3. **Delete `shitbox-telemetry.json`** once items 1 + 2 land. Single source of truth.

A Python script doing items 1 and 2 was prepared mid-session at `/tmp/dashboard-update.py` — not committed and may not survive reboot. If still there, it's a starting point; otherwise rebuild from the spec above.

While in there, broader audit:

- Panels referencing metrics that no longer exist (drift between code and dashboard).
- Threshold values — sanity-check against typical cabin / on-road ranges.
- Unit consistency.
- Mobile-friendly layout for in-car / passenger viewing during the rally. Current layout is desktop-width; some panels may not render usefully on a phone.
- Consider an event-overlay on the Route geomap — annotations at GPS coords of HIGH_G / HARD_BRAKE / etc.

Deploy path: edit JSON in `~/dev/home-ops/...`, commit + push, Flux reconciles the Grafana ConfigMap automatically.
