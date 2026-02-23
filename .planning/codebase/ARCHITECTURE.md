# Architecture

**Analysis Date:** 2026-02-24

## Pattern Overview

**Overall:** Unified daemon with three concurrent data paths

Shitbox is a single-daemon telemetry system that combines high-rate event detection with low-rate telemetry collection and network synchronisation. All three paths run concurrently within the `UnifiedEngine` orchestrator, sharing state through thread-safe components.

**Key Characteristics:**
- **High-rate IMU path (100 Hz)**: Real-time event detection with pre/post event capture
- **Low-rate telemetry path (1 Hz)**: GPS, temperature, power collection into SQLite
- **Network sync path**: Offline-first with cursor-based batch sync to Prometheus
- **Manual capture path**: Button-triggered video recording with GPIO handling
- **Graceful hardware degradation**: System runs with whatever hardware is available (GPS optional, sensors optional)

## Layers

**High-Rate Event Detection:**
- Purpose: Detect significant driving events (hard braking, big corners, rough road, high G) at 100 Hz
- Location: `src/shitbox/events/engine.py`, `src/shitbox/events/detector.py`, `src/shitbox/events/sampler.py`, `src/shitbox/events/ring_buffer.py`
- Contains: IMU sampling, ring buffer, event detector state machine, event throttling
- Depends on: I2C bus (MPU6050), ring buffer for sample storage
- Used by: Event storage, video capture triggers, MQTT publishing

**Event Storage & Video Capture:**
- Purpose: Save detected events as JSON + CSV metadata and trigger video recording
- Location: `src/shitbox/events/storage.py`, `src/shitbox/capture/video.py`, `src/shitbox/capture/ring_buffer.py`
- Contains: Event JSON/CSV persistence, video recording via ffmpeg, video ring buffer (continuous pre-event recording)
- Depends on: Event detector, file system, ffmpeg subprocess, GPIO button handler
- Used by: Engine for event persistence and Grafana annotations

**Low-Rate Telemetry Collection:**
- Purpose: Collect GPS, IMU snapshot, temperature, power data once per second and store locally
- Location: `src/shitbox/collectors/base.py`, `src/shitbox/collectors/temperature.py`, `src/shitbox/collectors/power.py`, `src/shitbox/collectors/environment.py`
- Contains: Base collector template, sensor-specific collectors, thread pool
- Depends on: Various I2C sensors, SQLite database
- Used by: Engine's telemetry loop, batch sync service

**Storage & Synchronisation:**
- Purpose: Persistent offline storage with cursor-based batch sync when online
- Location: `src/shitbox/storage/database.py`, `src/shitbox/sync/batch_sync.py`, `src/shitbox/sync/connection.py`
- Contains: SQLite with WAL mode, sync cursor tracking, Prometheus remote_write encoding
- Depends on: File system, network for Prometheus
- Used by: All telemetry collection, all sync services

**Network Uplink Services:**
- Purpose: Publish data to external services only when connectivity available
- Location: `src/shitbox/sync/batch_sync.py`, `src/shitbox/sync/capture_sync.py`, `src/shitbox/sync/mqtt_publisher.py`, `src/shitbox/sync/grafana.py`
- Contains: Batch sync (Prometheus), capture sync (rsync to NAS), MQTT publisher, Grafana annotator
- Depends on: Network connectivity monitor, database for Prometheus, file system for captures
- Used by: Engine for publishing detected events and periodic metrics

**Configuration & Utilities:**
- Purpose: Load YAML config, manage logging, provide shared utilities
- Location: `src/shitbox/utils/config.py`, `src/shitbox/utils/logging.py`
- Contains: Hierarchical dataclass config, structured logging via structlog
- Depends on: YAML parsing, structlog
- Used by: All components for configuration and logging

## Data Flow

**Event Detection & Capture (High-Rate Path):**

1. `HighRateSampler` reads MPU6050 at ~100 Hz via I2C
2. Each sample appended to `RingBuffer` (30-second circular buffer)
3. Sample passed to `EventDetector.process_sample()`
4. Detector checks thresholds: hard_brake (ax < -0.45g), big_corner (|ay| > 0.6g), rough_road (az stddev > 0.3), high_g (√(ax² + ay²) > 0.85)
5. On threshold breach, detector tracks active event; on return to normal, fires `on_event` callback
6. Engine's `_on_event()` handler:
   - Attaches current GPS, speed, location
   - Triggers video recording (via `VideoRingBuffer.save_event()` or `VideoRecorder`)
   - Queues event for post-capture processing
7. After post-event window, event saved to disk as JSON + CSV
8. Event added to `events.json` and optionally synced to Grafana

**Telemetry Collection & Sync (Low-Rate Path):**

1. `_telemetry_loop()` wakes every 100ms, publishes every 1 second:
   - Reads GPS via gpsd socket (returns latitude, longitude, speed, heading, satellites, fix quality)
   - Reads IMU snapshot from ring buffer (latest sample)
   - Reads optional power sensor (INA219 via I2C)
   - Reads optional environment sensor (BME680 via I2C)
   - Reads Pi CPU temp from `/sys/class/thermal/`
2. All readings inserted into SQLite (thread-safe with write lock)
3. If MQTT enabled: publishes reading to `shitbox/{sensor_type}/{field}` topics
4. `BatchSyncService` runs in background daemon thread:
   - Every 15 seconds checks connectivity against Prometheus host
   - If connected, fetches unsynced readings from database using cursor
   - Encodes as Prometheus remote_write protobuf (Snappy compressed)
   - Posts to Prometheus `/api/v1/write` endpoint
   - Updates sync cursor on success
5. `CaptureSyncService` runs separately:
   - Every 300 seconds checks connectivity
   - If connected, rsyncs captures directory to NAS

**State Management:**

- **Ring Buffer State**: Latest 30 seconds of IMU samples (100 Hz × 30s = 3000 samples max)
- **Event Tracking**: Active events per type tracked in detector; pending post-capture events queued in engine state dict
- **GPS State**: Current position, speed, heading, satellites, fix quality cached in engine
- **Database Cursor**: Tracks last synced row ID per service (mqtt, prometheus) to handle resumption after network loss
- **Sync Backlog**: Calculated on demand from database (count of rows > cursor position)

**Location Resolution:**

- GPS coordinates resolved to place name via `reverse_geocoder` library on interval (300 seconds) or when moved >1 km
- Result cached in engine and embedded in events

**Clock Synchronisation:**

- On GPS fix, drift checked (only sync if >30s off)
- Uses ctypes to call `clock_settime(CLOCK_REALTIME)` via libc
- Requires `CAP_SYS_TIME` capability on systemd service
- Fake hwclock updated hourly to preserve time across reboots without network

## Key Abstractions

**Event:**
- Purpose: Represents a detected driving event
- Location: `src/shitbox/events/detector.py`
- Pattern: Dataclass with temporal bounds, peak metrics, samples, geo metadata
- Serialises to JSON for storage and Grafana annotations

**Reading:**
- Purpose: Single sensor measurement (GPS, IMU snapshot, temperature, power, system)
- Location: `src/shitbox/storage/models.py`
- Pattern: Dataclass with typed fields per sensor type; flexible schema in SQLite
- Can be instantiated for any sensor, converts to/from database rows

**Collector:**
- Purpose: Abstract template for sensor data acquisition
- Location: `src/shitbox/collectors/base.py`
- Pattern: Template method pattern with abstract `setup()`, `read()`, `to_reading()`, `cleanup()`
- Each collector runs in daemon thread, calls callback with readings at configured rate

**Service (Daemon):**
- Purpose: Background work (sync, connectivity checks, video capture)
- Pattern: Daemon thread with `start()` / `stop()` lifecycle, main loop: check condition → do work → sleep
- Examples: `BatchSyncService`, `CaptureSyncService`, `OLEDDisplayService`

**RingBuffer:**
- Purpose: Fixed-duration circular buffer for IMU samples
- Location: `src/shitbox/events/ring_buffer.py`
- Pattern: Thread-safe deque with max capacity; `get_window(seconds)` for time-based slicing

**Database:**
- Purpose: Thread-safe SQLite wrapper with cursor tracking
- Location: `src/shitbox/storage/database.py`
- Pattern: Thread-local connections (each thread gets its own), write lock for mutations, WAL mode for crash resistance
- Maintains sync cursor table for Prometheus, MQTT, and future services

## Entry Points

**Main Daemon:**
- Location: `src/shitbox/events/engine.py` - `main()` function
- Triggers: Systemd service or direct `python -m shitbox.events.engine`
- Responsibilities:
  1. Parse CLI args (config path, --no-uplink)
  2. Load YAML config, create `EngineConfig`
  3. Instantiate `UnifiedEngine`, call `run()`
  4. Handle signals (SIGINT, SIGTERM → stop; SIGUSR1 → manual capture)

**Engine.run():**
- Calls `start()` to initialise all subsystems
- Enters main loop with health checks every 30 seconds
- Calls `stop()` on exit to cleanly shut down all services
- Notifies systemd via NOTIFY_SOCKET for watchdog and readiness

**API Entry Points (in engine):**
- `trigger_manual_capture()` - callable via button or SIGUSR1 signal
- `get_status()` - returns current system status for OLED display

## Error Handling

**Strategy:** Graceful degradation with recovery attempts

**Patterns:**

- **Hardware Unavailable**: Sensors are optional. If GPS doesn't connect, system logs warning and continues. If temperature sensor fails during setup, it's disabled but engine continues.
- **Collector Max Errors**: Each collector tracks consecutive read errors; after 10 failures stops collecting (prevents tight error loops)
- **GPS Timeout**: `_wait_for_gps_fix()` tries for 20 seconds on startup; if no fix, continues anyway (may be indoors)
- **Video Recording Failures**: Logged but don't stop engine. Events are queued even if video fails to record.
- **Network Connectivity**: Services check `connection.is_connected` before attempting sync. Batch sync retries with exponential backoff (tenacity library).
- **Database Write Lock Timeout**: 30-second timeout on SQLite locks; operations fail explicitly rather than hanging
- **Health Watchdog**: Runs every 30 seconds (after 60s startup grace period):
  - Checks IMU sampler has produced new samples (stall detection)
  - Checks telemetry thread is alive (restart if dead)
  - Checks video ring buffer is running
  - Checks GPS reconnects if disconnected
  - Checks disk space (cleanup if low, shutdown if critical <5%)
  - Tracks consecutive failures; beeps alarm after 2 consecutive failures

**Log Levels:**
- ERROR: Subsystem failures requiring attention (hard failures, max retries exceeded)
- WARNING: Degraded operation (stalled sampler, low disk, GPS unavailable)
- INFO: State changes (started, stopped, synced, captured event)
- DEBUG: Sample-by-sample data flow (only in development)

## Cross-Cutting Concerns

**Logging:**
- Framework: `structlog` with keyword arguments (structured logs as JSON in production)
- Pattern: `log.info("event_name", key=value, ...)`
- Examples: `log.info("event_detected", type=event.event_type.value, peak_g=round(event.peak_value, 2))`

**Validation:**
- Location: Config loading in `src/shitbox/utils/config.py`
- Pattern: Dataclass fields with defaults; YAML loaded via `_dict_to_dataclass()` helper
- No runtime validation; relies on type hints and defaults

**Authentication:**
- Prometheus: None (WireGuard tunnel assumed)
- Grafana: API token in config (plaintext, loaded from env or file)
- MQTT: Username/password in config
- Captures sync: SSH key assumed for rsync (via systemd user context)

**Concurrency:**
- High-rate sampler: Runs in dedicated thread, feeds ring buffer
- Event detector: Runs inline in sampler callback (no thread)
- Telemetry loop: Daemon thread, wakes every 100ms
- Collectors (temp, power, env): Each in separate daemon thread
- Services (batch sync, capture sync, OLED): Each in separate daemon thread
- Database: Thread-local connections, write lock for safety
- Video recording: ffmpeg as subprocess (non-blocking)

**Networking:**
- Prometheus batch sync: POST to `/api/v1/write` with protobuf + Snappy
- MQTT: Uses paho-mqtt library (async pub-sub)
- Capture rsync: Subprocess call to rsync binary
- Connectivity check: Simple TCP socket connect to prometheus host

---

*Architecture analysis: 2026-02-24*
