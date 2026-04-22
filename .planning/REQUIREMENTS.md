# Requirements — v2.0 Rally Ready

## Milestone v2.0 Requirements

### Driver Display (DISP)

- [x] **DISP-01**: User can view a fullscreen kiosk layout on the 7" touchscreen showing speed, G-force circle, temperatures, GPS status, and sync status
- [x] **DISP-02**: User can see a live event ticker scrolling recent events with event type and peak G value
- [ ] **DISP-03**: Display shows the currently active driver, pulled live from driver tracking
- [x] **DISP-04**: Critical events (high G, thermal alerts, undervoltage) trigger visible alert overlays on the display

### Field Notes (NOTE)

- [x] **NOTE-01**: User can compose a field note from the Pi UI using a keyboard, with DTS and GPS location auto-captured
- [x] **NOTE-02**: User can optionally pin a field note to an existing event
- [ ] **NOTE-03**: Field notes sync to shit-of-theseus.com and display in a blog/notes section

### Refueling Log (FUEL)

- [x] **FUEL-01**: User can log a fuel stop with volume and location from the Pi UI
- [x] **FUEL-02**: System calculates and tracks fuel efficiency (km/L) per stop and as a running cumulative average
- [ ] **FUEL-03**: Fuel stop locations and efficiency data sync to the website map; cost data never syncs

### Driver Tracking (DRVR)

- [x] **DRVR-01**: User can set and change the active driver from the Pi UI
- [x] **DRVR-02**: System tracks driving time and calculates percentage per driver across the rally
- [x] **DRVR-03**: Driver is attributed to events — who was driving when an event occurred
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

### Narrative (NARR)

- [x] **NARR-01**: Homepage adapts to rally mode -- before-mode (countdown + itinerary), live-mode (today IS the homepage with current-driver widget and 2-minute refresh), archive-mode (overview stats + linear day grid)
- [x] **NARR-02**: Site routes /day/YYYY-MM-DD as a first-class URL via single-file SPA using history.pushState and popstate
- [x] **NARR-03**: Each day page has a timeline spine merging events, notes, fuel stops, driver changes, stage bookends, and agenda markers -- sorted by timestamp
- [x] **NARR-04**: Day page renders agenda context (route, camping, meals) BEFORE any telemetry section
- [x] **NARR-05**: Site-wide day-nav progress bar visible on homepage, day pages, and /about with completed/current/future segment states
- [x] **NARR-06**: Top nav shrunk from 9 tabs to 4 entries: Home / Grafana / About / Donate
- [x] **NARR-07**: /about consolidates drivers roster + car story + telemetry explainer into one page
- [x] **NARR-08**: Pi-side RouteStorage generator emits route.json with Douglas-Peucker-simplified per-day polylines (10m tolerance), integrated with CaptureSyncService
- [x] **NARR-08b**: Home-address exclusion enforced in route.json (points within configurable radius of home_lat/home_lng are dropped)
- [x] **NARR-09**: Day-page map shows full-rally polyline as grey backdrop with current day slice highlighted in orange, event pins colour-coded via BADGE_COLORS
- [x] **NARR-10**: agenda.json authored as single source of rally-shape truth (JSON not YAML, served via home-ops ConfigMap with no-cache nginx rule)

### Physical Integration (PHYS)

- [ ] **PHYS-01**: Pi 5 stack housed in a 3D-printed PETG enclosure with active fan cooling, GX12 sensor loom connector, SMA GPS bulkhead, sized cable exits, and M2.5 rubber standoff vibration isolation
- [ ] **PHYS-02**: Waveshare 7" screen mounted in a 3D-printed bezel with VESA 75mm backplate, bolted to passenger-side dash via a fixed-angle gusset-braced bracket
- [ ] **PHYS-03**: ELP 4K front camera mounted on dash via a 3D-printed cradle bracket
- [ ] **PHYS-04**: Full system boots and runs in installed in-car configuration with all sensors detected

### Hardware Inventory and Graceful Degradation (HW)

- [ ] **HW-01**: A top-level `hardware:` block in `config.yaml` declares every expected device with `role`, `bus`, `address`/`path`, and `criticality`, and loads cleanly into a typed dataclass via `load_config()`
- [ ] **HW-02**: At boot, each declared device is probed and its presence (PRESENT / MISSING) is recorded in a central `HardwareState` object, which is visible to the dashboard and OLED within one status refresh
- [ ] **HW-03**: Alert cadence follows the criticality tier — `critical` devices trigger repeated TTS plus red dashboard banner plus OLED invert; `important` devices trigger single TTS plus orange badge; `best_effort` devices log only
- [x] **HW-04
**: Any collector that loses contact with its device (setup failure, consecutive I2C errors, ffmpeg stall, USB disappearance) reports MISSING into `HardwareState` and is retried on exponential backoff (5s → 15s → 60s → 5-minute cap); recovery flips state back and speaks a positive-confirmation TTS. The BME680 cold-boot init failure documented in STATE.md (2026-04-10) is the canonical acceptance case and must resolve end-to-end via this path
- [x] **HW-05
**: The daemon boots and runs its main loop even when `critical`-tier devices are absent — no systemd crash-loop, no boot refusal, regardless of what the probe reports

### IMU Signal Quality and Rollover Detection (IMU)

- [ ] **IMU-01**: `HighRateSampler.setup()` configures the LSM6DSOX via direct register writes to `CTRL1_XL` (0x52 — ODR 208 Hz + FS ±2 g + LPF2_XL_EN=1), `CTRL2_G` (0x54 — ODR 208 Hz + FS ±500 dps), and `CTRL8_XL` (0x28 — HPCF_XL = ODR/10 ≈ 20.8 Hz cutoff + FASTSETTL_MODE_XL=1), followed by a 50 ms sleep citing ST app note AN5272 for filter settling. Register-write failures trigger `hw_state.report_degraded("imu")` and fall through to the existing I2C recovery ladder.
- [ ] **IMU-02**: The sample loop polls at the configured `sample_rate_hz` (default 25 Hz after 22-07 retarget; documented acceptance floor 10 Hz). The sensor runs internally at 208 Hz ODR with LPF2 cutoff at ODR/10, which suppresses aliasing well below the Nyquist of any configured poll rate down to the 10 Hz floor. The application poll rate was retargeted from ~100 Hz (inherited from the MPU6050 era) to 25 Hz on 2026-04-22 after baseline diagnostics (see `.planning/phases/22-imu-signal-quality-and-rollover-detection-exploit-lsm6dsox-c/22-poll-rate-baseline-analysis.md`) confirmed the detector's sustain-duration gates have comfortable margin at rates well below 100 Hz (ROLLOVER 150 ms = 3-4 samples at 25 Hz; BIG_CORNER 300 ms = 7-8; HARD_BRAKE / HIGH_G 200-300 ms = 5-8). `sample_rate_hz` in config is the application poll rate; sensor ODR is independent and stays at 208 Hz internally. Dropped-sample budget: up to 5% of expected samples per 10 s window is acceptable (informational — observable via `sampler_read_rate` structlog, not alarmed).
- [ ] **IMU-03**: `EventType.ROLLOVER` is added to the detector enum. Sustained `|gx| > rollover_threshold_dps` OR `|gy| > rollover_threshold_dps` for `rollover_min_duration_ms` (default 250 dps / 150 ms) fires a ROLLOVER event. Transient spikes shorter than the minimum duration do not fire. The `Event` dataclass records `peak_gx`, `peak_gy`, `peak_gz` alongside the existing accel peaks. ROLLOVER is added to `VIDEO_CAPTURE_EVENTS` so rollovers trigger video capture.
- [ ] **IMU-04**: `_check_big_corner` fires on EITHER `|ay| > big_corner_threshold_g` (existing) OR `|gz| > big_corner_yaw_dps` (default 60 dps), preserving the current `big_corner_min_duration_ms` gate. Yaw-rate path catches slow-tight corners that lateral-g alone misses.
- [ ] **IMU-05**: Engine telemetry loop detects stationary windows (GPS speed < `auto_zero_stationary_kmh` for `auto_zero_window_seconds`, defaults 1.0 km/h / 30 s), computes mean accel over the window from the ring buffer, and applies tolerance-based rejection: if `max(|new_offset - stored|)` exceeds `auto_zero_tolerance_g` (0.05 g), reject with a structured warning. Plausibility guards: minimum 2500 samples, no raw sample exceeds `auto_zero_motion_reject_g` (0.2 g), and no resulting offset exceeds `auto_zero_max_abs_g` (0.5 g).
- [ ] **IMU-06**: First stationary window after engine boot always accepts the new offset unconditionally (bootstrap rule — in-memory boolean resets on every daemon start). Accepted offsets are persisted via `Database.set_trip_state("accel_offset_x"/"y"/"z", value)` and reloaded at engine startup with fallback to `config.accel_offset_*` seed when `trip_state` is empty. The sampler's offsets are updated live via a new `HighRateSampler.update_offsets(x, y, z)` method without restarting the sampler thread.

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
- **Cable loom routing**: Full cable loom design (split tubing, connector choices for engine bay and exterior sensor runs) is deferred from Phase 20.
- **Power distribution**: 12V fused circuit from car battery, buck converter placement, ignition-linked vs always-on, clean shutdown is deferred from Phase 20.
- **LSM6DSOX MLC (Machine Learning Core)**: Deferred from Phase 22 — separate future discussion.
- **On-chip FIFO + DRDY hardware interrupts (INT1/INT2)**: Deferred from Phase 22 — polling loop is sufficient for 100 Hz application rate.
- **Gyro LPF1 (CTRL6_C FTYPE) tuning**: Deferred from Phase 22 — default ULTRA_LIGHT bandwidth is acceptable; revisit only if noise-driven false ROLLOVER triggers appear in field data.
- **Website ROLLOVER badge styling**: Out of scope for Phase 22 (which produces the event). One-line `BADGE_COLORS` addition is a follow-up in the `home-ops` repo.

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| DISP-01 | Phase 17 | Complete |
| DISP-02 | Phase 17 | Complete |
| DISP-03 | Phase 17 | Pending |
| DISP-04 | Phase 17 | Complete |
| NOTE-01 | Phase 12 | Complete |
| NOTE-02 | Phase 12 | Complete |
| NOTE-03 | Phase 18 | Pending |
| FUEL-01 | Phase 12 | Complete |
| FUEL-02 | Phase 12 | Complete |
| FUEL-03 | Phase 18 | Pending |
| DRVR-01 | Phase 13 | Complete |
| DRVR-02 | Phase 13 | Complete |
| DRVR-03 | Phase 13 | Complete |
| DRVR-04 | Phase 18 | Pending |
| DRVR-05 | Phase 18 | Pending |
| WEB-01 | Phase 18 | Pending |
| WEB-02 | Phase 18 | Pending |
| WEB-03 | Phase 18 | Pending |
| WEB-04 | Phase 18 | Pending |
| CAL-01 | Phase 14 | Pending |
| CAL-02 | Phase 14 | Pending |
| VID-01 | Phase 16 | Pending |
| VID-02 | Phase 16 | Pending |
| PWR-01 | Phase 15 | Pending |
| PWR-02 | Phase 15 | Pending |
| MON-01 | Phase 15 | Pending |
| MON-02 | Phase 15 | Pending |
| MON-03 | Phase 15 | Pending |
| NARR-01 | Phase 19 | Complete |
| NARR-02 | Phase 19 | Complete |
| NARR-03 | Phase 19 | Complete |
| NARR-04 | Phase 19 | Complete |
| NARR-05 | Phase 19 | Complete |
| NARR-06 | Phase 19 | Complete |
| NARR-07 | Phase 19 | Complete |
| NARR-08 | Phase 19 | Complete |
| NARR-08b | Phase 19 | Complete |
| NARR-09 | Phase 19 | Complete |
| NARR-10 | Phase 19 | Complete |
| PHYS-01 | Phase 20 | Pending |
| PHYS-02 | Phase 20 | Pending |
| PHYS-03 | Phase 20 | Pending |
| PHYS-04 | Phase 20 | Pending |
| HW-01 | Phase 21 | Pending |
| HW-02 | Phase 21 | Pending |
| HW-03 | Phase 21 | Pending |
| HW-04 | Phase 21 | Pending |
| HW-05 | Phase 21 | Pending |
| IMU-01 | Phase 22 | Pending |
| IMU-02 | Phase 22 | Complete |
| IMU-03 | Phase 22 | Pending |
| IMU-04 | Phase 22 | Pending |
| IMU-05 | Phase 22 | Pending |
| IMU-06 | Phase 22 | Pending |
