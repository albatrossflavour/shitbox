# Pitfalls Research

**Domain:** Embedded rally telemetry -- adding features to a running offline-first system
**Researched:** 2026-04-09
**Confidence:** HIGH (based on direct codebase analysis)

## Critical Pitfalls

### Pitfall 1: Calibration Offsets Shifting Event Detection Without Warning

**What goes wrong:**
`EngineConfig` exposes `accel_offset_x/y/z` which are subtracted from raw IMU readings before
event detection. `DetectorConfig` thresholds (`hard_brake_threshold_g: -0.35`,
`big_corner_threshold_g: 0.45`, `rough_road_threshold_stddev: 0.3`, `high_g_threshold: 0.8`)
were tuned against uncalibrated data from v1.0 field testing. Applying calibration offsets moves
the effective signal but does not adjust the thresholds. A -0.1 g static Z-axis offset means the
rough-road stddev window now includes a DC bias, reducing sensitivity. A lateral offset makes
the car appear to always be cornering slightly, which can fire BIG_CORNER events at rest or
suppress real ones at the margin.

**Why it happens:**
Calibration and detection are configured separately. It feels correct to add offsets in config and
leave thresholds alone. Nobody tests event detection with a stationary car after calibration.

**How to avoid:**
- Before applying any calibration offset, record at least 30 seconds of stationary data and verify
  that zero-motion reads as approximately 0 g lateral, approximately 1 g vertical, approximately 0
  g longitudinal after the offset.
- After applying offsets, run the detector in a log-only mode (no capture triggered) during a slow
  carpark drive and verify event counts are plausible. Compare against v1.0 baseline rates.
- Do not change offsets and thresholds in the same commit -- change offsets first, observe, then
  tune thresholds if needed.

**Warning signs:**
- Events firing at idle (car parked, engine off)
- Zero ROUGH_ROAD events on rough surfaces that triggered them reliably in v1.0
- Event rate dramatically different from v1.0 on the same roads

**Phase to address:** CAL-01 (Sensor Calibration)

---

### Pitfall 2: New SQLite Tables Breaking the Batch Migration Sequence

**What goes wrong:**
`database.py` runs migrations sequentially: `< 2`, `< 3`, `< 4`, `< 5`. The `SCHEMA_SQL`
block at the top uses `CREATE TABLE IF NOT EXISTS` for all tables including `trip_state` and
`waypoints_reached`. New tables for notes, fuel logs, and driver tracking will be added in v2.0.
If a v2.0 table is added to `SCHEMA_SQL` (safe on fresh DBs) but the corresponding migration
is not correctly guarded, it will run `CREATE TABLE IF NOT EXISTS` (idempotent, fine) on existing
databases -- but only if the version check logic is correct. The bug vector is: someone adds a
table to `SCHEMA_SQL` and a new migration function, but forgets to bump `SCHEMA_VERSION` and
add the `if current_version < 6` guard, or bumps it without the guard. On an existing Pi database
at version 5, none of the new migration runs, and the new tables silently do not exist until the
service crashes on first insert.

**Why it happens:**
The pattern of adding to `SCHEMA_SQL` for new DBs and adding a separate migration for existing
DBs requires keeping two places in sync. It is easy to do one and not the other, or to test
only on a fresh database.

**How to avoid:**
- Increment `SCHEMA_VERSION` and add the version guard in the same commit as the migration
  function. Never separate them.
- Test on a copy of the live Pi database, not a fresh one. `scp` the `.db` off the Pi and run
  `connect()` against it on the laptop before deploying.
- Add a post-startup assertion: check that all expected tables exist and log their row counts.

**Warning signs:**
- `OperationalError: no such table: field_notes` on first write
- Service starts without error but `SELECT COUNT(*) FROM field_notes` returns nothing because the
  table was never created

**Phase to address:** NOTE-01 / FUEL-01 / DRVR-01 (whichever adds the first new table)

---

### Pitfall 3: `insert_readings_batch` Missing `cpu_percent` Column

**What goes wrong:**
This is an existing bug in `database.py`. `insert_reading` (singular) includes `cpu_percent`
in both the column list and values tuple. `insert_readings_batch` does not -- it lists
`cpu_temp_celsius, disk_percent, sync_backlog, throttle_flags` but skips `cpu_percent`. Any
batch insert of SYSTEM-type readings silently drops CPU percent, producing NULL for that column.
The HealthCollector uses the singular `insert_reading`, so the live health path is unaffected.
But if anything ever batch-inserts health readings (a replay or import flow for MON-01),
`cpu_percent` will be silently lost.

**Why it happens:**
`cpu_percent` was added in the v5 migration, which post-dates the batch insert method. The
singular version was updated; the batch version was not.

**How to avoid:**
Fix `insert_readings_batch` to include `cpu_percent` in both the column list and the values
tuple. Add a unit test that asserts both insert methods produce identical column sets.

**Warning signs:**
- `shitbox_cpu_pct` metric missing from Prometheus during backlog replay
- HealthCollector readings in the DB with `cpu_percent = NULL`

**Phase to address:** MON-01 (Monitoring Completeness)

---

### Pitfall 4: Chromium Kiosk Leaking Memory Against a Long-Running SSE Connection

**What goes wrong:**
The driver display (DISP-01) runs Chromium in kiosk mode continuously for days. The dashboard
holds three SSE connections simultaneously (`/sse/fast` at 10 Hz, `/sse/slow` at 1 Hz,
`/sse/events`). Chromium on Linux has well-documented memory leaks under continuous SSE and DOM
updates, particularly when the page re-renders the map (Leaflet) at high frequency. At 10 Hz,
`/sse/fast` pushes 864,000 events per day. If the JavaScript handler does any DOM manipulation
on each fast event without explicit cleanup (removing old nodes, cancelling animation frames,
clearing object references), heap usage climbs over hours and Chromium OOMs.

Works fine in testing (20 minutes). The problem only shows at 12-24 hour timescales.

**Why it happens:**
Nobody runs a kiosk stability test before deploying. The Pi 5 has 4 GB RAM, which creates false
confidence. Memory pressure is worst when the system is also recording video in summer heat.

**How to avoid:**
- The fast SSE stream should not drive DOM updates directly. Use it to update a JavaScript
  variable, and let a `requestAnimationFrame` loop read that variable and repaint at 30-60 Hz.
  This decouples the SSE ingest rate from the render rate.
- Add a nightly Chromium restart via cron (e.g., 03:00 AEST) timed to a known rest period.
- Use `--disable-dev-shm-usage --disable-gpu --no-sandbox` in the Chromium launch flags for
  kiosk on Pi. These are not optional for embedded kiosk use.
- Memory-test by leaving the display running for 8+ hours before the rally starts.

**Warning signs:**
- Chromium becoming unresponsive after several hours
- `dmesg` showing OOM killer entries
- Chromium process consuming > 500 MB RSS

**Phase to address:** DISP-01 (Driver Display)

---

### Pitfall 5: ELP 4K v4l2 Controls Causing ffmpeg to Hang at Startup

**What goes wrong:**
`VideoRecorder._configure_camera()` applies v4l2 controls before recording starts. The current
list is minimal (`backlight_compensation`, `exposure_dynamic_framerate`). For a 4K ELP camera,
the temptation is to add controls: manual exposure, white balance, focus. Some v4l2 controls on
UVC cameras require the device to be in a specific state to accept them. Setting `exposure_auto`
to manual mode and then immediately setting `exposure_absolute` can cause the UVC driver to stall
waiting for the camera firmware to acknowledge the change. If `v4l2-ctl` times out silently (5s
timeout is already coded), the device state is indeterminate: the camera received the first
control but not the second. ffmpeg then opens the device and tries to negotiate 4K MJPEG against
a partially-applied control state, which can cause ffmpeg to hang on device open. There is no
timeout on the `subprocess.Popen` call.

**Why it happens:**
Controls work fine when tested interactively (human pacing between commands). The automated
sequence runs too fast for some camera firmware.

**How to avoid:**
- Add a 200ms sleep between v4l2-ctl calls for any camera where controls depend on each other
  (exposure mode then exposure value, WB lock then WB value).
- Always verify the control was applied by reading it back and logging a warning if it does not
  match the intended value.
- Add a startup timeout to the ffmpeg monitoring thread: check `is_recording` after 10 seconds
  and kill/restart if ffmpeg has not produced output. This is already a known gap in
  `_monitor_recording()`.
- Verify with `v4l2-ctl --list-formats-ext` that the camera actually supports the target
  resolution at the target framerate. 4K at 30 fps is often USB 3.0 bandwidth-limited.

**Warning signs:**
- Silent hang rather than `ffmpeg_not_found` log (process started but `video_recording_complete`
  never appears)
- `dmesg` showing USB reset events on the camera device
- `v4l2-ctl --list-ctrls-menu` showing the control in a different state than configured

**Phase to address:** VID-01 (ELP 4K Video Tuning)

---

### Pitfall 6: Driver Attribution Time Gaps During Handovers and Parking

**What goes wrong:**
DRVR-01 requires tracking who is driving, with time and percentage per driver. The naive
implementation: when a driver change is recorded, close the previous session with
`end_time = now()` and open a new one. Edge cases that break this:

1. **Handover gap**: Driver A stops; driver B has not been assigned yet. An event fires during
   the gap (GPS jump, road bump at rest). If attribution queries "which driver session overlaps
   this event's timestamp", a gap means the event is unattributed.

2. **No GPS fix at handover**: If the driver change is recorded without a GPS fix, the stored
   location is NULL or the last-known position, which may be many kilometres stale.

3. **Multi-day sessions**: A driver is assigned at 08:00, the system shuts down at 23:00
   (ignition off), restarts at 07:00 next day. The session `end_time` is never written because
   the shutdown was unclean. If boot recovery closes orphaned events but not orphaned driver
   sessions, the session appears to span the overnight stop.

4. **Boundary conditions**: An event fires at the exact same millisecond as a driver handover
   is recorded. Depending on query boundary conditions (`>=` vs `>`), the event may be attributed
   to either driver.

**Why it happens:**
Attribution by time overlap is simple to implement for the happy path and only breaks in boundary
conditions that do not appear in short testing sessions.

**How to avoid:**
- Store a `driver_id` directly on the Event record at the time of detection (not derived later
  by query). The current driver is always known at event-fire time.
- Use closed intervals: when driver A hands over to driver B, write B's start timestamp as
  exactly 1ms after A's end timestamp.
- Extend boot recovery (BootRecoveryService) to also close open driver sessions with an
  estimated end time (last known event timestamp or a shutdown timestamp persisted to SQLite).
- When GPS fix is unavailable, still record the handover with the correct timestamp and NULL
  location. Do not defer the handover waiting for a fix.

**Warning signs:**
- Events with `driver_id = NULL` in the database after a full day's driving
- Driver session coverage percentage summing to less than 100% of driving time
- The same driver appearing twice with different session IDs on the stats page

**Phase to address:** DRVR-01 (Driver Tracking)

---

### Pitfall 7: CaptureSyncService JSON Race When Adding New Index Files

**What goes wrong:**
`_do_sync_inner()` uses a two-pass rsync: pass 1 syncs media excluding `events.json` and
`timelapse.json`; pass 2 syncs everything including the index files. This protects against the
website referencing videos that have not yet arrived. The risk when adding new JSON index files
for field notes, fuel logs, and driver stats: if the new JSON files are generated before pass 1
but not excluded from pass 1, the website receives the new index before the data it references
exists.

More specifically: new JSON files that reference IDs in SQLite (e.g., `driver_id` in an event
record references a row in a `drivers` table that only lives on the Pi) have no second-pass
protection. The two-pass pattern protects file references (video path X exists on NAS). It does
not protect data references (driver ID Y has a stats record). These are different problems.

**Why it happens:**
People assume the two-pass rsync solves both "file not yet transferred" and "data not yet
available". It only solves the first.

**How to avoid:**
- New JSON files that are self-contained (all referenced data embedded inline) are safe.
  Generate them the same way as `events.json`.
- New JSON files that reference IDs in a separate data store must either embed the referenced
  data inline, or the website must handle missing references gracefully (show "unknown driver"
  rather than crashing).
- Explicitly add any new JSON index files to the pass 1 exclusion list and add a comment
  explaining why.

**Warning signs:**
- Website showing `undefined` or blank values for new data types immediately after a sync
- Console errors in the website JS about missing referenced objects

**Phase to address:** NOTE-01 / FUEL-01 / DRVR-01 / WEB-01

---

### Pitfall 8: Pi 5 Throttle Bitmask Misreading "Has Ever Seen" as "Currently"

**What goes wrong:**
`thermal_monitor.py` correctly defines both current-state flags (bits 0-3) and historical
"since boot" flags (bits 16-19). `HealthCollector` stores `throttle_flags` as the raw integer.
The risk is in how this is displayed and alerted on.

Bit 16 (`under_voltage_since_boot`) is set if undervoltage occurred at any point since boot,
even if it only lasted 50ms at startup and the power supply is fine now. If PWR-01 alert logic
reads the raw flags integer and checks `flags & 0x10000`, it fires an alert every single cycle
for the entire session even after the hardware fix. That makes the alert useless and trains
occupants to ignore it.

For the Pi 5 specifically: it uses a Renesas DA9091 PMIC rather than the discrete power circuit
of the Pi 4. The `vcgencmd get_throttled` output format is identical but the voltage thresholds
differ. The Pi 5 minimum input voltage is approximately 5.1V vs 4.63V for Pi 4. A supply that
was borderline acceptable on Pi 4 hardware will trip undervoltage flags on Pi 5 more easily.

**Why it happens:**
The `get_throttled` bitmask is widely copy-pasted without noting the "since boot" vs "current"
distinction. Alert code written without reading the bitmask spec will use the full integer.

**How to avoid:**
- Alert only on current-state bits (bits 0-3, mask `0x0000000F`), not the historical bits.
- Log the full raw integer for debugging, but separate the display and alert logic.
- For PWR-01 validation: after the hardware fix, reboot and verify that bits 0-3 are clear
  within 10 seconds of startup. Bits 16-19 may still be set and that is acceptable.
- Measure the actual 5V rail voltage under full load (4K camera recording + GPS + all sensors
  active) with a multimeter. Do not trust software indicators alone.

**Warning signs:**
- `speak_under_voltage` TTS alert firing on every thermal monitor cycle, not just at startup
- `shitbox_throttle_flags` Prometheus metric stuck at a non-zero value that never clears

**Phase to address:** PWR-01 (Undervoltage Resolution) / MON-01 (Monitoring Completeness)

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Adding new writer threads calling `db.insert_reading()` directly | Fast to implement, follows existing pattern | `_write_lock` serialises all writes; adding notes/fuel/driver writers increases contention during the 1 Hz telemetry cycle | Only if write rate is low (< 1 Hz per new service) |
| Storing driver name as free text rather than a foreign key to a `drivers` table | Simpler schema, no migration needed | Typos create duplicate drivers; stats aggregation breaks | Never for v2 -- use an ID |
| Generating new JSON files inside the existing `generate_events_json()` call | One code change | Function does multiple things; harder to test; all-or-nothing failure | Never -- keep each JSON generator separate |
| Sharing the existing `event_queue` (used by the capture path) for new feature events | No new queue | The `event_queue` is bounded at 256 and drops on full to protect the capture path; non-capture events competing for the same queue will be dropped under load | Never -- separate queue for non-capture SSE events |
| Using `trip_state` key-value table to persist driver tracking state | No new table needed | `trip_state` is a flat KV store; storing multiple driver sessions as JSON blobs in it is unqueryable | Never -- add proper tables |

---

## Integration Gotchas

Common mistakes when connecting to external services or subsystems.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| FastAPI REST endpoints for notes/fuel entry | Instantiating a new `Database` object per request | Pass the single `Database` instance through dependency injection at app startup, same as the dashboard server |
| Chromium kiosk adding a REST POST endpoint for driver selection | Assuming the API is only accessible locally | The current dashboard has no auth; document this and ensure the API is not accessible outside the WireGuard interface |
| ELP 4K replacing the 1280x720 configuration | Changing `capture_video_resolution` and `video_buffer_resolution` to 4K simultaneously | Change one at a time; 4K ring buffer segments use dramatically more disk -- recalculate `video_buffer_segments` first |
| HealthCollector adding new Prometheus metric names | Naming new metrics inconsistently with existing `shitbox_*` labels | Check `_readings_to_metrics()` in `batch_sync.py` -- add new SYSTEM sensor fields there too, or the data lands in SQLite but never reaches Prometheus |
| New REST API sharing the uvicorn event loop with SSE generators | Blocking database calls inside async route handlers | Use `asyncio.to_thread()` for any SQLite access inside FastAPI routes, as established in `sse.py` |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `get_sync_backlog_count()` running a full `COUNT(*)` scan at 1 Hz | No immediate symptom; disk I/O visible in iostat | Already the pattern; SQLite `COUNT(*)` with WAL is fast at current scale | Noticeable above approximately 1 million rows |
| Leaflet map re-centering on every GPS update at 1 Hz | Map jerks every second; distracting in a car | Smooth interpolation in JS; only re-centre if position moved more than N metres from view centre | Immediately annoying regardless of scale |
| `EventStorage.generate_events_json()` scanning all events on every sync | Slow generation as event count grows | Add a date range limit (last 7 days) or stream JSON generation | Noticeable at approximately 5,000+ events (1-3 seconds at rally day 5) |
| 4K ring buffer filling the SD card | Capture path fails silently with "no space left" | Check disk space before starting any recording; the stall detection watchdog catches a dead ffmpeg process but does not check space first | At 4K MJPEG 30 fps, each 10-second segment is 200-400 MB; 5 segments = up to 2 GB for the ring buffer alone |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Driver display productionised**: Often missing a Chromium restart cron job -- verify the kiosk
  recovers after an 8-hour soak test, not just a 20-minute demo.
- [ ] **Field notes syncing to website**: Often missing handling for notes entered without GPS fix --
  verify that NULL lat/lng does not break the Leaflet map rendering.
- [ ] **Undervoltage fix confirmed**: Often declared done after `vcgencmd` shows zero flags -- verify
  under full load (4K recording + GPS + sensors active), not just at idle.
- [ ] **HealthCollector end-to-end (HLTH-01)**: "Implemented but not confirmed" means the metric exists
  in SQLite but the Grafana panel shows no data -- verify the Prometheus scrape job label matches
  what `_readings_to_metrics()` emits for `sensor_type == "system"`.
- [ ] **Sensor calibration applied**: Often stops at "offsets calculated" -- verify event detection
  rates are unchanged by running a test drive before and after and comparing event counts by type.
- [ ] **ELP 4K tuning complete**: Often stops at "v4l2-ctl commands found" -- verify a full 60-second
  recording at the target resolution plays back without artefacts and the file size is within
  expected bounds.
- [ ] **Driver tracking attribution**: Often complete for the happy path -- verify event attribution
  works through a simulated overnight power cycle (shutdown with open driver session, restart,
  check boot recovery closed the session).

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Migration ran but new tables missing | LOW | Open `sqlite3 telemetry.db`; manually run the `CREATE TABLE` statements; update `schema_version`; restart service |
| Calibration offsets caused false-positive event storm | LOW | Set all offsets back to 0 in config; restart service; re-run calibration with longer stationary sample |
| Chromium OOM on display | LOW | `sudo systemctl restart kiosk`; add the nightly cron restart as an immediate mitigation |
| ffmpeg hanging after v4l2 control change | MEDIUM | Kill the ffmpeg process manually; unplug/replug the camera; revert the control change; restart the service |
| Driver sessions with no end_time after unclean shutdown | LOW | Run the boot recovery extension via a one-shot script, or manually `UPDATE sessions SET end_time = ? WHERE end_time IS NULL` in the sqlite3 shell |
| Throttle alert firing every cycle despite hardware fix | LOW | Check bits 0-3 of the raw flags integer; if clear, the fix worked -- update the alert mask in the alert logic |
| events.json referencing videos not yet on NAS | LOW | Next sync cycle will push the videos; website already handles missing video paths with a fallback state |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Calibration offsets shifting detection thresholds | CAL-01 | Pre/post detection rate comparison on a known road segment |
| New table migration sequence bug | First phase adding new tables (NOTE-01 or FUEL-01) | Test migration against a copy of the live Pi DB before deploying |
| `insert_readings_batch` missing cpu_percent | MON-01 | Unit test asserting column parity between singular and batch insert methods |
| Chromium kiosk memory leak | DISP-01 | 8-hour soak test; monitor RSS growth over time |
| ELP 4K v4l2 hang | VID-01 | Full recording test at target resolution; verify no ffmpeg zombie processes after 10 minutes |
| Driver attribution gaps | DRVR-01 | Simulated overnight power cycle with open driver session; verify boot recovery closes it |
| CaptureSyncService JSON race for new data | NOTE-01 / FUEL-01 / WEB-01 | Inspect NAS after sync: all new JSON uses embedded data only, no external ID references without inline data |
| Pi 5 throttle bitmask misread | PWR-01 / MON-01 | Alert only fires when bits 0-3 are non-zero; clears after hardware fix under full load |

---

## Sources

- Direct analysis of `src/shitbox/storage/database.py` -- migration sequence and batch insert column mismatch
- Direct analysis of `src/shitbox/events/detector.py` -- threshold values and calibration offset integration points
- Direct analysis of `src/shitbox/dashboard/sse.py` -- SSE architecture and queue design constraints
- Direct analysis of `src/shitbox/capture/video.py` -- ffmpeg subprocess pattern and v4l2 control sequence
- Direct analysis of `src/shitbox/health/health_collector.py` and `thermal_monitor.py` -- throttle bitmask implementation
- Direct analysis of `src/shitbox/sync/capture_sync.py` -- two-pass rsync pattern and its limits
- Pi Foundation documentation: `vcgencmd get_throttled` bitmask definition; Pi 5 PMIC minimum voltage differs from Pi 4
- Chromium kiosk memory behaviour: established pattern in Pi display deployments; scheduled restart is standard mitigation

---

*Pitfalls research for: Shitbox Rally Telemetry v2.0 feature additions*
*Researched: 2026-04-09*
