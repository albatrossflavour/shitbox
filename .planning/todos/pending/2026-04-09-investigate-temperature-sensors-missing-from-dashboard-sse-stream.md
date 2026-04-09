---
created: 2026-04-09T09:32:20.265Z
title: Investigate temperature sensors missing from dashboard SSE stream
area: general
files:
  - src/shitbox/collectors/imu_heading.py
  - src/shitbox/events/engine.py
---

## Problem

During Phase 10 smoke test (2026-04-09), the dashboard showed `-- °C` for both
IMU TEMP and SoC TEMP panels. Neither DS18B20 (external temperature probe) nor
the system CPU/SoC temperature are appearing in the SSE stream. The dashboard
panels are rendering but receiving no data.

Possible causes:
- DS18B20 collector not initialising on Pi 5 (1-wire interface may need enabling in config)
- System health collector not wiring temp into the SSE snapshot
- SSE endpoint not including temp fields in the fast/slow payload
- Dashboard JS not mapping the correct field names from the SSE event

## Solution

TBD -- needs investigation on the Pi with the service running. Check:
1. `journalctl -u shitbox-telemetry` for DS18B20 init errors
2. SQLite for recent `sensor_type='temp'` and `sensor_type='system'` rows
3. SSE `/stream/slow` payload to confirm fields are present
4. Dashboard field mapping in `webroot/index.html`
