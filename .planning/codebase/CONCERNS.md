# Codebase Concerns

**Analysis Date:** 2026-02-24

## Tech Debt

**Monolithic Engine Class:**
- Issue: `UnifiedEngine` in `src/shitbox/events/engine.py` is 1647 lines with 470+ attributes, mixing high-rate event detection, low-rate telemetry collection, video/audio capture, GPS coordination, and system health checks. Violates single responsibility principle.
- Files: `src/shitbox/events/engine.py`
- Impact: Difficult to test individual subsystems. Changes to one feature (e.g., health check logic) risk breaking unrelated systems. Hard to reuse components independently.
- Fix approach: Extract `HealthChecker`, `TelemetryCollector`, `EventCoordinator`, and `GPSResolver` into separate classes. Use composition/dependency injection instead of monolithic initialization.

**Thread-Local Database Connections with `check_same_thread=False`:**
- Issue: Line 110 in `src/shitbox/storage/database.py` disables SQLite's thread-safety check (`check_same_thread=False`), which is a red flag for concurrent access issues. While the code uses `_write_lock` for writes, reads are unprotected.
- Files: `src/shitbox/storage/database.py`
- Impact: Potential data corruption if multiple threads read/write simultaneously. WAL mode helps but doesn't guarantee isolation. High-rate IMU sampling thread could read stale data while telemetry thread writes.
- Fix approach: Either enforce single reader at a time with a read-write lock, or use SQLite's built-in isolation. Test with concurrent stress scenarios.

**Event Suppression Based on ID Pointers:**
- Issue: `_pending_post_capture` dict in `src/shitbox/events/engine.py` lines 637-641 uses `id(event)` as key. Event objects created in callbacks may be garbage-collected, causing dict key mismatches if the ID is reused.
- Files: `src/shitbox/events/engine.py`
- Impact: Video callbacks for late-arriving captures may fail to update the correct event JSON. Lost metadata links to videos.
- Fix approach: Use UUID or event timestamp+type tuple instead of `id()`. Add explicit object lifetime tracking.

## Known Bugs

**GPS Satellite Count Socket Workaround:**
- Symptoms: The `_get_satellite_count()` method in `src/shitbox/events/engine.py` lines 924-955 opens a raw socket to gpsd instead of using the Python client library, because the gpsd-py3 library has a bug where it doesn't expose the satellite count reliably.
- Files: `src/shitbox/events/engine.py`
- Trigger: Every GPS fix triggers this workaround; the socket is opened fresh each time instead of being reused.
- Workaround: Currently in place (raw socket workaround). Risk: socket leaks if exception occurs between lines 950-954 (exception handler calls `sock.close()` but could fail).

**Socket Cleanup Race Condition:**
- Symptoms: Lines 950-954 in `src/shitbox/events/engine.py` have a bare `except (socket.error, socket.timeout, OSError)` that silently drops errors. If `sock.close()` fails in the finally block, the socket resource leaks.
- Files: `src/shitbox/events/engine.py`
- Trigger: GPS read during high socket load or when gpsd is slow.
- Workaround: Finally block attempts cleanup, but errors are silently swallowed.

**Event JSON Late Arrival Race:**
- Symptoms: `_on_video_complete()` in `src/shitbox/events/engine.py` lines 699-726 stashes video paths in `_event_video_paths` dict if the event JSON hasn't been saved yet. But if the post-capture window expires before the video finishes, the event saves without the video link.
- Files: `src/shitbox/events/engine.py`
- Trigger: Video encoding takes longer than post-event capture window.
- Workaround: `_check_post_captures()` tries to find the video afterwards by filesystem glob (line 755), but this is fragile (filename assumptions, timing windows).

## Security Considerations

**Environment Variable Exposure in Process List:**
- Risk: MQTT password is passed via environment variables (config). If the systemd service or Python process lists are exposed, credentials leak.
- Files: `src/shitbox/events/engine.py` lines 87-88 (config fields), systemd service file
- Current mitigation: Config file (`config/config.yaml`) can be restricted with file permissions. Environment variables are ephemeral.
- Recommendations: (1) Don't log config values. (2) Consider using a secrets manager (e.g., systemd LoadCredential or HashiCorp Vault). (3) Add secret redaction to logging output.

**GPS Clock Sync Without Authorization Check:**
- Risk: `_sync_clock_from_gps()` in `src/shitbox/events/engine.py` lines 858-906 uses `ctypes` to call `clock_settime()`. Requires `CAP_SYS_TIME` capability. If the process is compromised, system time can be corrupted.
- Files: `src/shitbox/events/engine.py`
- Current mitigation: Capability is explicitly documented in CLAUDE.md. systemd service should have `AmbientCapabilities=CAP_SYS_TIME`.
- Recommendations: (1) Log all clock sync events with before/after timestamps. (2) Add sanity checks (e.g., reject time changes >24 hours in past). (3) Rate-limit to once per boot.

**No Bounds Checking on Event Sample Collection:**
- Risk: `samples` list in `Event` objects grows unbounded as more IMU samples are appended (e.g., line 747 in `src/shitbox/events/engine.py`). If an event runs for hours, memory could exhaust.
- Files: `src/shitbox/events/detector.py`, `src/shitbox/events/engine.py`
- Current mitigation: Ring buffer caps samples at `ring_buffer_seconds` (default 30s), but post-event extension can exceed this.
- Recommendations: (1) Cap samples per event (e.g., max 10,000 samples = ~100 seconds at 100 Hz). (2) Downsample if exceeding limit. (3) Stream samples to disk instead of buffering all in memory.

## Performance Bottlenecks

**High-Rate Ring Buffer Growing Without Bound:**
- Problem: `RingBuffer` in `src/shitbox/events/ring_buffer.py` stores every 100 Hz sample for 30 seconds = 3000 samples per event. Events extend the post-capture window, potentially growing the list to 10,000+ samples. Searching/copying these lists happens on every event.
- Files: `src/shitbox/events/ring_buffer.py`, `src/shitbox/events/engine.py`
- Cause: No downsampling or circular buffer optimisation. Full list copies on event retrieval.
- Improvement path: (1) Use `collections.deque` for O(1) rotation. (2) Store as numpy array or mmap for faster slicing. (3) Downsample on event detection (e.g., keep 10 Hz for storage, 100 Hz only for detection).

**GPS Lock Acquisition Blocks Startup (20 seconds):**
- Problem: `_wait_for_gps_fix()` in `src/shitbox/events/engine.py` lines 514-554 blocks for up to 20 seconds waiting for a GPS fix. If GPS is unavailable, startup is delayed.
- Files: `src/shitbox/events/engine.py`
- Cause: Synchronous polling loop during `start()`.
- Improvement path: (1) Move to async background task or timeout after 5s. (2) Log warning but don't block. (3) Boot capture is only valuable if GPS fix exists; consider conditionally triggering it.

**Database Write Lock Held During JSON Serialisation:**
- Problem: `insert_reading()` in `src/shitbox/storage/database.py` lines 210-263 holds `_write_lock` while serialising Reading objects. If JSON serialisation is slow (e.g., large lists), other threads block.
- Files: `src/shitbox/storage/database.py`
- Cause: Write lock covers entire operation, not just the SQL insert.
- Improvement path: Prepare the SQL tuple outside the lock, acquire lock only for the `execute()` and `commit()`.

**Event Storage Generates `events.json` Synchronously:**
- Problem: `generate_events_json()` in `src/shitbox/events/storage.py` reads all event files, deserialises JSON, and writes a new `events.json` file. Called on every event capture (line 766 in engine.py) and on startup. Blocks telemetry thread.
- Files: `src/shitbox/events/storage.py`, `src/shitbox/events/engine.py`
- Cause: No async I/O or background task scheduler.
- Improvement path: (1) Queue JSON regeneration as a background task (e.g., in telemetry loop). (2) Only regenerate on cleanup cycle, not on every event. (3) Use incremental updates instead of full rebuild.

## Fragile Areas

**Video Ring Buffer FFmpeg Process Management:**
- Files: `src/shitbox/capture/ring_buffer.py`
- Why fragile: The `_process` field holds a long-running ffmpeg subprocess. No heartbeat check. If ffmpeg crashes, `is_running` property may report True but process is dead. Recovery requires manual restart or health check triggering.
- Safe modification: Always check `_process.poll()` return value. Add process monitoring thread that tracks exit codes. Test crash scenarios (e.g., simulate `ffmpeg` segfault).
- Test coverage: No unit tests for ffmpeg subprocess crashes. Manual ffmpeg kill test needed.

**Event Detector Cooldown State Machine:**
- Files: `src/shitbox/events/detector.py`
- Why fragile: Event type cooldown is tracked in `_last_event_time` dict (line 134). If an event is never detected, the entry is never created, so first detection always passes cooldown check. Race condition if two threads call `process_sample()` simultaneously (unlikely but possible in high-load scenarios).
- Safe modification: Use a single lock for all cooldown state. Test concurrent sample processing. Add cooldown expiry audit log.
- Test coverage: Only 1 test file in codebase; no detector unit tests.

**GPS Fix State Across Boundaries:**
- Files: `src/shitbox/events/engine.py`
- Why fragile: Multiple flags track GPS state: `_gps_available`, `_gps_has_fix`, `_clock_synced_from_gps`. They're updated in different threads (`_wait_for_gps_fix()`, `_read_gps()`, telemetry loop) without synchronisation. A read in `_on_event()` might see torn state.
- Safe modification: Use a GPS state object with a single lock. Atomic transitions: NOT_CONNECTED → CONNECTED_NO_FIX → FIXED → SYNCED. Audit all state readers.
- Test coverage: No GPS state machine tests.

**Button Handler Polling Loop with No Jitter:**
- Files: `src/shitbox/capture/button.py`
- Why fragile: Lines 122-123 poll GPIO at fixed 10ms interval. If multiple threads also access GPIO (e.g., LED control), there's potential for race conditions on the same pin.
- Safe modification: Centralise GPIO control. Use interrupts instead of polling (if hardware supports). Add mutex around all GPIO calls.
- Test coverage: Simulated press method exists but no automated tests.

**Overlay Text File Updates Race:**
- Files: `src/shitbox/capture/overlay.py`
- Why fragile: `_update_overlay()` in engine.py (line 1214) writes text files that ffmpeg's `drawtext` filter reads. No locking between writer (engine) and reader (ffmpeg). If ffmpeg reads mid-write, text corruption occurs.
- Safe modification: Write to temporary file, then atomic rename. Or use named pipes with explicit handshake.
- Test coverage: No integration tests for overlay rendering.

## Scaling Limits

**Database WAL Checkpoint Frequency:**
- Current capacity: SQLite WAL can grow unbounded if checkpoints don't run. At 100+ readings/sec (GPS + IMU snapshot), WAL grows ~6 MB/min.
- Limit: Breaks if `/var/lib/shitbox` disk fills. 500 MB device fills in ~1.4 hours at peak rate.
- Scaling path: (1) Increase `wal_autocheckpoint` from 1000 to 10,000 pages (but risks larger crash recovery). (2) Implement background checkpoint thread that runs when idle. (3) Batch syncs to Prometheus more aggressively to truncate WAL.

**Event JSON File Count in Directory:**
- Current capacity: EventStorage saves one JSON+CSV pair per event. At 10 events/minute during active driving, that's 1000+ files per hour in a single directory.
- Limit: Some filesystems (especially Ext4 without dir_index) degrade with >10,000 files per directory.
- Scaling path: Already have date-based subdirectories (good). Consider hour-based subdivisions for high-frequency scenarios.

**Video Ring Buffer Disk I/O:**
- Current capacity: 5 segments × 10 seconds × 1280×720 @ 30fps ≈ 400 MB RAM (mpeg-ts) + continuous disk writes at ~15 MB/s.
- Limit: Cheap SD cards (write speed <20 MB/s, endurance <1000 hours) degrade under 24/7 sustained writes.
- Scaling path: (1) Use enterprise-grade SD cards (SLC, not TLC). (2) Monitor SMART health. (3) Implement write rate limiting or buffer to NAS periodically.

## Dependencies at Risk

**gpsd-py3 Library:**
- Risk: Unmaintained library with reported bugs (satellite count not exposed). Workaround is in place but fragile.
- Impact: GPS telemetry is unreliable. Satellite count is hacked around with raw socket calls.
- Migration plan: (1) Consider switching to `pynmea2` or `geopy` for parsing NMEA sentences directly from gpsd. (2) Fork gpsd-py3 to fix satellite count bug. (3) Use gpsd raw socket API directly instead of Python wrapper.

**paho-mqtt Version Mismatch:**
- Risk: Lines 55-62 in `src/shitbox/sync/mqtt_publisher.py` have a `try/except TypeError` to handle both old and new paho-mqtt versions. Fragile version detection.
- Impact: Breaks with future paho-mqtt versions. Type errors silently ignored.
- Migration plan: Pin paho-mqtt to specific version in `setup.py` / `requirements.txt`. Remove fallback code.

**Tenacity Retry Library:**
- Risk: Only used in `batch_sync.py` (imported but not shown in snippets). If dropped or significantly changed API, batch sync breaks.
- Impact: Prometheus sync may not retry on transient failures.
- Migration plan: Either inline retry logic (simple for this codebase) or ensure tenacity is pinned in dependencies.

## Missing Critical Features

**No Persistent Event Queue for Failed Captures:**
- Problem: If video encoding fails or upload fails, there's no persistent queue. Events are lost or orphaned. `_pending_post_capture` is in-memory.
- Blocks: Can't guarantee event capture in failure scenarios. Website may not update if sync fails.
- Fix: Implement persistent event queue in SQLite. Mark as "pending_sync". Retry on next connectivity.

**No Rate Limiting or Backpressure:**
- Problem: If event detection fires faster than video encoding completes, captures queue indefinitely. No explicit queue depth limit.
- Blocks: Can't cap memory usage under high-frequency event scenarios (e.g., rough road on gravel rally).
- Fix: Cap pending captures queue, reject excess events with log warning. Or implement priority queue (manual > auto).

**No Graceful Degradation for Missing Hardware:**
- Problem: System starts with lazy init of sensors (power, environment collectors), but if they fail mid-flight, no fallback. Battery voltage becomes unavailable.
- Blocks: Can't diagnose power issues if INA219 fails mid-flight.
- Fix: Add sensor health checks. If sensor fails, log and continue with lower resolution data.

**No Configuration Hot-Reload:**
- Problem: Changes to `config/config.yaml` require systemd restart. Can't adjust detection thresholds or enable/disable features without downtime.
- Blocks: Can't tune parameters in field after rally starts.
- Fix: Implement signal handler (e.g., `SIGHUP`) to reload config and apply changes to detector/sync configs.

## Test Coverage Gaps

**No Integration Tests:**
- What's not tested: High-rate IMU sample → event detection → video capture → JSON save → events.json generation. Full end-to-end pipeline.
- Files: All files; tests directory has only 1 test file.
- Risk: Refactoring engine.py could break event coordination without detection. Changes to ring buffer could corrupt sample timestamps.
- Priority: High (core functionality).

**No Concurrent Access Tests:**
- What's not tested: Multiple threads writing to database, reading GPS while engine is sampling, video ring buffer concurrent segment access.
- Files: `src/shitbox/storage/database.py`, `src/shitbox/capture/ring_buffer.py`, `src/shitbox/events/engine.py`
- Risk: Thread safety bugs go undetected. Race conditions manifest randomly in production.
- Priority: High (threading model is critical).

**No Failure Scenario Tests:**
- What's not tested: GPS unplugged mid-flight, video device unavailable, disk full, ffmpeg crash, Prometheus endpoint down, MQTT broker unreachable.
- Files: All service classes.
- Risk: Assumptions about hardware availability are untested. Graceful degradation code paths never exercised.
- Priority: Medium (affects reliability).

**No Event Detector Unit Tests:**
- What's not tested: Edge cases in detection thresholds, cooldown logic, event state machine, sample buffer overflow.
- Files: `src/shitbox/events/detector.py`
- Risk: Detection tuning is guesswork. Threshold changes risk false positives/negatives.
- Priority: High (core telemetry).

**No Video Ring Buffer Tests:**
- What's not tested: Segment rotation, concatenation, overlay rendering, cleanup, ffmpeg crash recovery.
- Files: `src/shitbox/capture/ring_buffer.py`
- Risk: Video encoding bugs are catastrophic (silent corruption, missing footage). No validation of output.
- Priority: High (data loss risk).

---

*Concerns audit: 2026-02-24*
