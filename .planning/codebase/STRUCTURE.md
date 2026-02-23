# Codebase Structure

**Analysis Date:** 2026-02-24

## Directory Layout

```
shitbox/
├── config/
│   └── config.yaml                 # Main YAML config (sensors, sync, capture, display)
├── src/shitbox/
│   ├── __init__.py
│   ├── events/                     # High-rate event detection
│   │   ├── __init__.py
│   │   ├── engine.py               # UnifiedEngine orchestrator (1600+ lines)
│   │   ├── detector.py             # EventDetector state machine
│   │   ├── sampler.py              # HighRateSampler (MPU6050 I2C reader)
│   │   ├── ring_buffer.py          # RingBuffer circular buffer
│   │   └── storage.py              # EventStorage JSON/CSV persistence
│   ├── capture/                    # Video and manual capture
│   │   ├── __init__.py
│   │   ├── video.py                # VideoRecorder ffmpeg wrapper
│   │   ├── ring_buffer.py          # VideoRingBuffer continuous recording
│   │   ├── button.py               # ButtonHandler GPIO debounce
│   │   ├── buzzer.py               # Buzzer control module
│   │   └── overlay.py              # Video HUD text overlay
│   ├── collectors/                 # Low-rate sensor collectors
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseCollector template (abstract)
│   │   ├── temperature.py          # TemperatureCollector (MCP9808)
│   │   ├── power.py                # PowerCollector (INA219)
│   │   └── environment.py          # EnvironmentCollector (BME680)
│   ├── storage/                    # Data persistence
│   │   ├── __init__.py
│   │   ├── database.py             # Database SQLite wrapper (WAL mode)
│   │   └── models.py               # Reading, SensorType, SyncCursor dataclasses
│   ├── sync/                       # Network uplink services
│   │   ├── __init__.py
│   │   ├── batch_sync.py           # BatchSyncService Prometheus batch uploader
│   │   ├── capture_sync.py         # CaptureSyncService rsync to NAS
│   │   ├── connection.py           # ConnectionMonitor TCP connectivity
│   │   ├── mqtt_publisher.py       # MQTTPublisher paho-mqtt wrapper
│   │   ├── grafana.py              # GrafanaAnnotator API annotations
│   │   └── prometheus_write.py     # Remote write encoding (protobuf + Snappy)
│   ├── display/                    # Output displays
│   │   ├── __init__.py
│   │   └── oled.py                 # OLEDDisplayService I2C display updates
│   └── utils/                      # Shared utilities
│       ├── __init__.py
│       ├── config.py               # Config dataclasses + load_config()
│       └── logging.py              # structlog setup
├── scripts/
│   ├── install.sh                  # Installation script
│   ├── imu_test.py                 # Standalone IMU test
│   ├── trigger-capture.sh          # Manual capture trigger script
│   └── shitbox-health.sh           # Health check script
├── systemd/
│   └── shitbox-telemetry.service   # systemd service unit
├── grafana/
│   └── dashboards/
│       └── shitbox-telemetry.json  # Grafana dashboard JSON
├── pyproject.toml                  # Python package metadata
└── README.md                       # Project documentation
```

## Directory Purposes

**src/shitbox/events/:**
- Purpose: High-rate IMU sampling and real-time event detection
- Contains: Sampler thread, detector state machine, ring buffer, event storage
- Key files: `engine.py` (orchestrator), `detector.py` (thresholds), `sampler.py` (I2C), `ring_buffer.py` (3000-sample circular buffer)

**src/shitbox/capture/:**
- Purpose: Video and audio recording, manual trigger handling, video overlay
- Contains: ffmpeg video recorder, video ring buffer (continuous pre-event), GPIO button handler, buzzer control
- Key files: `video.py` (VideoRecorder), `ring_buffer.py` (VideoRingBuffer), `button.py` (GPIO debounce)

**src/shitbox/collectors/:**
- Purpose: Low-rate sensor data acquisition (temperature, power, environment)
- Contains: Abstract collector template, concrete sensor collectors, daemon thread per collector
- Key files: `base.py` (template pattern), `temperature.py`, `power.py`, `environment.py`

**src/shitbox/storage/:**
- Purpose: Persistent data storage and sync state management
- Contains: SQLite database with WAL mode, schema migrations, cursor tracking
- Key files: `database.py` (thread-safe wrapper), `models.py` (Reading dataclass, SensorType enum)

**src/shitbox/sync/:**
- Purpose: Network synchronisation when connectivity available
- Contains: Prometheus batch uploader, rsync to NAS, MQTT publisher, Grafana annotator, connectivity monitor
- Key files: `batch_sync.py` (Prometheus), `capture_sync.py` (rsync), `connection.py` (TCP check)

**src/shitbox/display/:**
- Purpose: Output to OLED or other displays
- Contains: OLEDDisplayService with I2C control
- Key files: `oled.py` (1.3" OLED display updates)

**src/shitbox/utils/:**
- Purpose: Shared configuration and logging
- Contains: YAML config loading, dataclass hierarchy, structlog setup
- Key files: `config.py` (Config, EngineConfig, all sensor configs), `logging.py` (structlog)

## Key File Locations

**Entry Points:**
- `src/shitbox/events/engine.py`: `main()` - systemd service entry point; `UnifiedEngine` orchestrator
- `scripts/imu_test.py`: Standalone IMU sampler test (development)
- `scripts/trigger-capture.sh`: Send SIGUSR1 to engine for manual capture

**Configuration:**
- `config/config.yaml`: YAML master config (loaded by `load_config()`)
- `src/shitbox/utils/config.py`: Dataclass hierarchy matching YAML structure
- `systemd/shitbox-telemetry.service`: systemd unit with capabilities and environment

**Core Logic:**
- `src/shitbox/events/engine.py`: Main daemon loop, 1600+ lines, orchestrates all subsystems
- `src/shitbox/events/detector.py`: Event detection state machine with thresholds
- `src/shitbox/storage/database.py`: SQLite wrapper with thread-local connections and WAL mode
- `src/shitbox/sync/batch_sync.py`: Prometheus remote_write batch uploader

**Testing:**
- `pytest` run from root directory (no explicit test directory in repo, tests may be external)
- Coverage: `pytest --cov=shitbox`

## Naming Conventions

**Files:**
- Modules: `module_name.py` (snake_case)
- Service classes: `ServiceName` suffix (e.g., `BatchSyncService`, `OLEDDisplayService`)
- Dataclasses: `NameConfig` for configuration (e.g., `EngineConfig`, `PrometheusConfig`)
- Example: `src/shitbox/events/detector.py` contains `EventDetector` class and `EventType` enum

**Directories:**
- Functional areas: lowercase plural (e.g., `events`, `capture`, `collectors`, `sync`)
- No nested subdirectories within functional areas except `src/shitbox/display/` (flat structure)

**Classes:**
- PascalCase (e.g., `UnifiedEngine`, `EventDetector`, `RingBuffer`)
- Abstract bases: `Base` prefix (e.g., `BaseCollector`)
- Enums: PascalCase singular (e.g., `EventType`, `SensorType`)

**Functions & Methods:**
- snake_case (e.g., `process_sample()`, `get_window()`, `_sync_loop()`)
- Private/internal: `_underscore_prefix()`
- Properties: `is_running`, `duration` (no getter prefix)

**Constants:**
- SCREAMING_SNAKE_CASE (e.g., `HEALTH_CHECK_INTERVAL = 30.0`, `VIDEO_CAPTURE_EVENTS = {...}`)

**Event Types:**
- Values: snake_case (e.g., `"hard_brake"`, `"big_corner"`, `"manual_capture"`)
- Enum members: SCREAMING_CASE (e.g., `EventType.HARD_BRAKE`)

## Where to Add New Code

**New Event Type:**
1. Add enum member to `EventType` in `src/shitbox/events/detector.py`
2. Add `DetectorConfig` threshold fields (thresholds, min_duration_ms)
3. Add detection method `_check_<type>()` in `EventDetector`
4. Add entry to `process_sample()` dispatch
5. Add to `VIDEO_CAPTURE_EVENTS` in `engine.py` if video should trigger

**New Sensor/Collector:**
1. Create collector class in `src/shitbox/collectors/<sensor_type>.py` extending `BaseCollector`
2. Implement: `setup()`, `read()`, `to_reading()`, optional `cleanup()`
3. Add config dataclass to `src/shitbox/utils/config.py` (e.g., `NewSensorConfig`)
4. Instantiate in `UnifiedEngine.__init__()` and wire into `_record_telemetry()`
5. Add to config YAML under `sensors` section

**New Sync Service:**
1. Create service class in `src/shitbox/sync/<service_name>.py`
2. Follow pattern: `start()`/`stop()` lifecycle, `_service_loop()` daemon thread
3. Main loop: `sleep(interval)` → `if connection.is_connected:` → do work
4. Add config dataclass to `src/shitbox/utils/config.py`
5. Instantiate in `UnifiedEngine.__init__()` behind `if config.service_enabled and config.uplink_enabled:`
6. Call `start()` and `stop()` alongside existing services
7. Add YAML config section under `sync:`

**New Display Output:**
1. Create service in `src/shitbox/display/<display_type>.py`
2. Extend service pattern: daemon thread, `start()`/`stop()`, update loop
3. Engine's `get_status()` returns dict for display to read
4. Add config dataclass to `src/shitbox/utils/config.py` (e.g., `OLEDConfig`)
5. Instantiate in `UnifiedEngine.__init__()` and wire `start()`/`stop()`

**New Utility Function:**
- GPS distance: `src/shitbox/events/engine.py` static method `_haversine_km()`
- Location reverse lookup: `src/shitbox/events/engine.py` `_resolve_location()`
- System temp read: `src/shitbox/events/engine.py` `_read_pi_temp()`
- These are in engine.py because they're specific to the engine's telemetry loop

**Tests:**
- Use pytest; import from `src/shitbox`
- Mock I2C buses, GPIO, subprocess for video/capture tests
- Test collector pattern with mock `read()` implementations
- Example commands in CLAUDE.md: `pytest`, `pytest --cov=shitbox`

## Special Directories

**config/:**
- Purpose: YAML configuration
- Generated: No
- Committed: Yes
- Single file: `config.yaml` loaded at engine startup via `load_config()`

**/var/lib/shitbox/ (on running system):**
- Purpose: Runtime data storage on Raspberry Pi
- Generated: Yes (created by engine if missing)
- Committed: No
- Subdirectories:
  - `telemetry.db` - SQLite database with readings
  - `events/` - JSON/CSV event files organised by date
  - `captures/` - Video files in YYYY-MM-DD subdirs
  - `video_buffer/` - Temporary segments for ring buffer

**systemd/:**
- Purpose: Service unit file
- Generated: No (hand-written)
- Committed: Yes
- Provides: Type=notify, Restart=on-failure, systemd integration
- Requires: `ReadWritePaths=/var/lib/shitbox`, `CAP_SYS_TIME` for clock sync

**grafana/:**
- Purpose: Grafana dashboard definitions
- Generated: No (hand-written JSON)
- Committed: Yes
- Dashboard shows: Events on map (Leaflet), metrics timeline, sync status

**scripts/:**
- Purpose: Developer and admin utilities
- `imu_test.py`: Test I2C MPU6050 connectivity standalone
- `install.sh`: Install package, set up systemd
- `trigger-capture.sh`: Send SIGUSR1 to running engine
- `shitbox-health.sh`: Poll systemd for health status

---

*Structure analysis: 2026-02-24*
