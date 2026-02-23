# External Integrations

**Analysis Date:** 2026-02-24

## APIs & External Services

**Prometheus:**
- Service: Prometheus time-series database (monitored via WireGuard)
- Used for: Metrics time-series storage and queries
- Integration: Remote write API via `src/shitbox/sync/batch_sync.py`
- SDK/Client: Custom protobuf encoder in `src/shitbox/sync/prometheus_write.py`
- Auth: None (IP-based via WireGuard VPN)
- Config key: `sync.prometheus.remote_write_url` (default: `http://prometheus.albatrossflavour.com/api/v1/write`)
- Batch interval: `sync.prometheus.batch_interval_seconds` (15 seconds)
- Batch size: `sync.prometheus.batch_size` (2000 readings)
- Encoding: Protobuf + Snappy compression, content-type `application/x-protobuf`
- Compression header: `Content-Encoding: snappy`
- Metrics namespace: `shitbox_*` with labels `car=shitbox` and `job=shitbox-mqtt-exporter`

**Grafana:**
- Service: Grafana dashboard and annotation API (optional)
- Used for: Event annotations on Grafana dashboards
- Integration: `src/shitbox/sync/grafana.py`
- Auth: Bearer token via `sync.grafana.api_token`
- Endpoint: `{url}/api/annotations`
- Config key: `sync.grafana.enabled` (default: false)
- Payload: Annotations with event type, peak G, duration, video URLs
- Async: Posts annotations in background thread (non-blocking)

**MQTT Broker:**
- Service: MQTT message broker (disabled in default config)
- Used for: Real-time telemetry streaming
- Integration: `src/shitbox/sync/mqtt_publisher.py`
- SDK/Client: paho-mqtt 2.0.0+
- Auth: Username/password
- Config keys:
  - `sync.mqtt.enabled` (default: false - using batch sync instead to avoid duplicates)
  - `sync.mqtt.broker_host` (example: `emqx.albatrossflavour.com`)
  - `sync.mqtt.broker_port` (default: 1883)
  - `sync.mqtt.username`
  - `sync.mqtt.password`
  - `sync.mqtt.client_id` (default: `shitbox-car`)
  - `sync.mqtt.qos` (default: 1 - at least once)
  - `sync.mqtt.topic_prefix` (default: `shitbox`)
- Reconnection: Exponential backoff with `reconnect_delay_min` (1s) and `reconnect_delay_max` (120s)
- Status: Disabled in current config (line 59 of `config/config.yaml`) to prevent duplicate metrics

## Data Storage

**Databases:**
- Type/Provider: SQLite (local file-based)
- Location: `/var/lib/shitbox/telemetry.db`
- Connection: Thread-safe via write locks in `src/shitbox/storage/database.py`
- Mode: WAL (Write-Ahead Logging) for crash resistance
- Schema version: 3 (`SCHEMA_VERSION` constant line 16 of `src/shitbox/storage/database.py`)
- Tables:
  - `readings` - Telemetry data (GPS, IMU, temperature, power, environment, system)
  - `sync_cursors` - Sync position tracking (for Prometheus batch sync)
  - `schema_version` - Migration tracking
- Backup: Enabled by default (`storage.backup_enabled: true`), interval 6 hours, max 10 backups

**File Storage:**
- Local filesystem at `/var/lib/shitbox/captures/` for event video files
- Ring buffer segments: `/var/lib/shitbox/video_buffer/`
- Files synced to NAS via rsync (not cloud storage)

**Caching:**
- None - all data goes directly to SQLite

## Authentication & Identity

**Auth Provider:**
- Type: Custom (none for public APIs, token/certificate-based for others)
- GPS: Socket connection (no auth)
- I2C/GPIO: Hardware bus (no auth)
- Prometheus: IP-based access via WireGuard VPN (checked at `sync.connectivity.check_host`)
- Grafana: Bearer token (`sync.grafana.api_token`)
- MQTT: Username/password (currently disabled)

## Monitoring & Observability

**Error Tracking:**
- None - errors logged to syslog via systemd
- Log level configurable: `app.log_level` (default: INFO)
- Structured logging: All logs via structlog with keyword arguments

**Logs:**
- Output: systemd journal (viewed via `journalctl -u shitbox-telemetry -f`)
- Format: Structured JSON via structlog
- Level: Configurable in `app.log_level` field
- Rotation: Handled by systemd

**Health Monitoring:**
- Service: Internal health reporting (optional)
  - Config: `health.enabled` (default: true)
  - Interval: `health.report_interval_seconds` (60)
  - Thresholds:
    - `health.temp_warning_celsius` (70)
    - `health.temp_critical_celsius` (80)
    - `health.disk_warning_percent` (80)
    - `health.disk_critical_percent` (95)
- Monitored via OLED display (`src/shitbox/display/oled.py`)

## CI/CD & Deployment

**Hosting:**
- Target: Raspberry Pi running Raspbian
- Entry: systemd service at `/etc/systemd/system/shitbox-telemetry.service`

**CI Pipeline:**
- None detected - manual deployment via git clone and install script

**Deployment Method:**
- Installation: `sudo ./scripts/install.sh` (in `scripts/install.sh`)
- Service management: systemd (`systemctl start shitbox-telemetry`)
- Config: `/etc/shitbox/config.yaml` (copied from repo if not exists)
- Venv: `.venv` in application directory (created by install script)

## Environment Configuration

**Required Environment Variables:**
- None explicitly required - all configuration via YAML file
- MQTT credentials in config file: `sync.mqtt.username`, `sync.mqtt.password`
- Grafana API token in config file: `sync.grafana.api_token`
- Note: No secrets in environment; credentials in `/etc/shitbox/config.yaml` (should restrict permissions)

**Secrets Location:**
- `/etc/shitbox/config.yaml` - Contains MQTT credentials, Grafana API token
- Recommendation: Restrict file permissions to user ownership only
- Note: Install script should set permissions, but verify: `chmod 600 /etc/shitbox/config.yaml`

## Webhooks & Callbacks

**Incoming:**
- None - system does not expose endpoints for external webhooks

**Outgoing:**
- Prometheus remote_write: `sync.prometheus.remote_write_url`
  - POST endpoint for metric ingestion
  - Protocol: Custom protobuf + snappy (not JSON)
  - Triggered every `sync.prometheus.batch_interval_seconds` when connected
- Grafana annotations: `{sync.grafana.url}/api/annotations`
  - POST endpoint for event annotations
  - Triggered on driving events when `sync.grafana.enabled: true`
- rsync to NAS: `sync.capture_sync.remote_dest`
  - SSH-based file sync
  - Destination format: `user@host:/path`
  - Interval: `sync.capture_sync.interval_seconds` (300)
  - Triggered via `src/shitbox/sync/capture_sync.py`

## Connectivity & VPN

**VPN:**
- Type: WireGuard (external to application)
- Used for: Secure tunnel to Prometheus host
- Connectivity check: TCP socket to `sync.connectivity.check_host` (default: `prometheus.albatrossflavour.com:80`)
- Check interval: `sync.connectivity.check_interval_seconds` (30)
- Timeout: `sync.connectivity.timeout_seconds` (3)
- Implementation: `src/shitbox/sync/connection.py` (pure socket, no VPN library required)

## Network Topology

**Data Flow:**
1. Sensors (GPS, IMU, environment) → SQLite (offline-first)
2. Event detector triggers on high-rate IMU data
3. On trigger: Video recording starts, event metadata stored in SQLite
4. When connected (WireGuard up):
   - BatchSyncService reads SQLite via cursor, encodes metrics, POSTs to Prometheus
   - CaptureSyncService regenerates events.json, rsyncs captures to NAS
   - GrafanaAnnotator (if enabled) POSTs event annotations to Grafana
5. Website (separate repo) reads from NAS via NFS mount at `/captures/events.json` and MP4 files

## Event Publishing

**Events Captured:**
- HARD_BRAKE - Rapid deceleration
- BIG_CORNER - High lateral G
- HIGH_G - Vertical acceleration
- ROUGH_ROAD - High-frequency vibration
- MANUAL/BUTTON - Manual trigger via GPIO button
- BOOT - System startup

**Event Data Sent to Prometheus:**
Metric names:
- `shitbox_lat`, `shitbox_lon` - GPS position
- `shitbox_spd` - Speed km/h
- `shitbox_alt` - Altitude m
- `shitbox_sat`, `shitbox_fix` - GPS quality
- `shitbox_ax`, `shitbox_ay`, `shitbox_az` - Acceleration g
- `shitbox_gx`, `shitbox_gy`, `shitbox_gz` - Gyro deg/s
- `shitbox_temp` - Temperature C
- `shitbox_bus_voltage`, `shitbox_current`, `shitbox_power` - Power metrics
- `shitbox_pressure`, `shitbox_humidity`, `shitbox_env_temp`, `shitbox_gas_resistance` - Environment
- `shitbox_cpu_temp` - System temperature

## Sensor Integrations

**GPS (via gpsd):**
- Connection: TCP socket to localhost:2947
- Data: Position, speed, altitude, heading, fix quality, satellite count
- Sampling: 1 Hz

**IMU (MPU6050):**
- Connection: I2C bus 1, address 0x68
- Data: 3-axis acceleration (±4g), 3-axis gyroscope (±500 deg/s)
- Sampling: 100 Hz (high-rate), 1 Hz snapshot for telemetry

**Temperature (MCP9808, optional):**
- Connection: I2C bus 1, address 0x18
- Sampling: 0.1 Hz

**Power (INA219, optional):**
- Connection: I2C bus 1, address 0x40
- Data: Bus voltage, current draw, power
- Sampling: 1 Hz

**Environment (BME680):**
- Connection: I2C bus 1, address 0x77
- Data: Pressure, humidity, temperature, gas resistance (air quality)
- Sampling: 1 Hz

**OLED Display (SSD1306):**
- Connection: I2C bus 1, address 0x3C
- Purpose: Real-time status display
- Update interval: 1 Hz

## Rate Limiting

**Prometheus batch sync:**
- Interval: `sync.prometheus.batch_interval_seconds` (15s)
- Max batch: `sync.prometheus.batch_size` (2000 readings)
- Automatic retry: Exponential backoff (max 3 attempts)

**Capture sync (rsync):**
- Interval: `sync.capture_sync.interval_seconds` (300s)
- Timeout: 600 seconds

**Connectivity checks:**
- Interval: `sync.connectivity.check_interval_seconds` (30s)

---

*Integration audit: 2026-02-24*
