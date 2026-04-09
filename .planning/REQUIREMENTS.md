# Requirements — v2.0 Rally Ready

## Milestone v2.0 Requirements

### Driver Display (DISP)

- [ ] **DISP-01**: User can view a fullscreen kiosk layout on the 7" touchscreen showing speed, G-force circle, temperatures, GPS status, and sync status
- [ ] **DISP-02**: User can see a live event ticker scrolling recent events with event type and peak G value
- [ ] **DISP-03**: Display shows the currently active driver, pulled live from driver tracking
- [ ] **DISP-04**: Critical events (high G, thermal alerts, undervoltage) trigger visible alert overlays on the display

### Field Notes (NOTE)

- [ ] **NOTE-01**: User can compose a field note from the Pi UI using a keyboard, with DTS and GPS location auto-captured
- [ ] **NOTE-02**: User can optionally pin a field note to an existing event
- [ ] **NOTE-03**: Field notes sync to shit-of-theseus.com and display in a blog/notes section

### Refueling Log (FUEL)

- [ ] **FUEL-01**: User can log a fuel stop with volume and location from the Pi UI
- [ ] **FUEL-02**: System calculates and tracks fuel efficiency (km/L) per stop and as a running cumulative average
- [ ] **FUEL-03**: Fuel stop locations and efficiency data sync to the website map; cost data never syncs

### Driver Tracking (DRVR)

- [ ] **DRVR-01**: User can set and change the active driver from the Pi UI
- [ ] **DRVR-02**: System tracks driving time and calculates percentage per driver across the rally
- [ ] **DRVR-03**: Driver is attributed to events — who was driving when an event occurred
- [ ] **DRVR-04**: Website shows a "who's in charge" widget on the homepage with current driver and running percentages
- [ ] **DRVR-05**: Website shows per-driver stats including driving time, percentage, and event attribution

### Website (WEB)

- [ ] **WEB-01**: Website integrates field notes as a blog/notes section with timestamp and location
- [ ] **WEB-02**: Website shows fuel stop pins as a Leaflet map layer with efficiency data
- [ ] **WEB-03**: Website shows driver stats page with time percentages and event attribution
- [ ] **WEB-04**: Grafana graph layouts improved; iframe kiosk iframe issues resolved; metric coverage improved with v2.0 sensors

### Sensor Calibration (CAL)

- [ ] **CAL-01**: All sensors (LSM6DSOX accel/gyro, LIS3MDL, DS18B20, VEML7700, INA226) validated against known reference with calibration offsets applied
- [ ] **CAL-02**: Event detection thresholds re-validated and confirmed accurate after calibration offsets applied

### Video Capture (VID)

- [ ] **VID-01**: ELP 4K camera supported modes empirically listed from mounted hardware; optimal resolution/framerate selected for event recording
- [ ] **VID-02**: v4l2 controls and ffmpeg settings tuned for the actual mounted camera and confirmed producing clean output

### Undervoltage (PWR)

- [ ] **PWR-01**: Undervoltage hardware fix confirmed; software correctly detects current undervoltage using bits 0-3 only (not sticky historical bits)
- [ ] **PWR-02**: Undervoltage alert surfaces visibly in the live dashboard and triggers a spoken TTS alert

### Monitoring (MON)

- [ ] **MON-01**: HLTH-01 closed — CPU temp, disk %, and sync backlog metrics confirmed reaching Prometheus end-to-end; `insert_readings_batch` cpu_percent bug fixed
- [ ] **MON-02**: Prometheus scrape job label conflict resolved (job: shitbox-mqtt-exporter no longer collides with shitbox metrics)
- [ ] **MON-03**: All critical events (thermal, undervoltage, capture failure) surface visibly in the live dashboard

## Future Requirements

- Magnetometer (LIS3MDL) ellipsoid calibration — deferred; rough heading accuracy sufficient for current use; revisit if compass display is added
- Co-driver support — multiple occupants tracked simultaneously; deferred, single-active-driver model covers the rally
- Automatic OTA configuration updates — too risky for remote rally conditions
- Mobile-optimised website — current site is adequate for phone browsers

## Out of Scope

- **Cost data on website**: Fuel stop cost is private and must never appear in sync payloads or the website. This is a hard exclusion enforced in sync code.
- **GPS-inferred driver attribution**: Driver is set explicitly by the crew; inferring from GPS patterns adds complexity with no benefit.
- **Touchscreen OSK**: Wayland/Chromium kiosk OSK is unreliable on Pi 5 (confirmed upstream issue); USB keyboard is the required input method.
- **Separate databases for new data**: All new tables (notes, fuel_stops, driver_stints, calibration) go into the existing telemetry.db. No separate databases.
- **Real-time video streaming**: Connectivity too sparse; batch sync remains the model.
- **AI/ML event classification**: Unnecessary complexity.
- **OBD/ECU data**: 2001 Ford Laser is OBD-I only.

## Traceability

_To be filled by roadmapper._

| REQ-ID | Phase | Status |
|--------|-------|--------|
| DISP-01 | — | Active |
| DISP-02 | — | Active |
| DISP-03 | — | Active |
| DISP-04 | — | Active |
| NOTE-01 | — | Active |
| NOTE-02 | — | Active |
| NOTE-03 | — | Active |
| FUEL-01 | — | Active |
| FUEL-02 | — | Active |
| FUEL-03 | — | Active |
| DRVR-01 | — | Active |
| DRVR-02 | — | Active |
| DRVR-03 | — | Active |
| DRVR-04 | — | Active |
| DRVR-05 | — | Active |
| WEB-01 | — | Active |
| WEB-02 | — | Active |
| WEB-03 | — | Active |
| WEB-04 | — | Active |
| CAL-01 | — | Active |
| CAL-02 | — | Active |
| VID-01 | — | Active |
| VID-02 | — | Active |
| PWR-01 | — | Active |
| PWR-02 | — | Active |
| MON-01 | — | Active |
| MON-02 | — | Active |
| MON-03 | — | Active |
