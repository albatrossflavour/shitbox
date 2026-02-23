# Technology Stack

**Analysis Date:** 2026-02-24

## Languages

**Primary:**
- Python 3.9+ - Entire application, daemon, collectors, sync, display, capture orchestration

**Secondary:**
- Bash - Installation scripts, health checks, capture triggering
- YAML - Configuration files
- Protobuf - Prometheus remote_write protocol encoding (compiled to Python at runtime)

## Runtime

**Environment:**
- Python 3.9+ (configured in `pyproject.toml` line 6)
- Raspberry Pi OS (Raspbian) - target platform
- systemd for daemon management

**Package Manager:**
- pip - Python package installation
- Lockfile: Not detected (uses `pyproject.toml` with pinned versions)

## Frameworks

**Core:**
- structlog 24.0.0+ - Structured logging with keyword arguments (`src/shitbox/utils/logging.py`)
- pyyaml 6.0+ - Configuration loading into nested dataclasses (`src/shitbox/utils/config.py`)
- requests 2.28.0+ - HTTP client for Prometheus remote_write and Grafana API

**Hardware & Sensors:**
- gpsd-py3 0.3.0+ - GPS daemon communication (1 Hz position/speed/altitude)
- smbus2 0.4.0+ - I2C bus control for MPU6050 IMU sampling at 100 Hz
- adafruit-circuitpython-mcp9808 3.3.0+ - MCP9808 temperature sensor (optional)
- adafruit-circuitpython-ina219 3.4.0+ - INA219 power monitor (optional)
- adafruit-circuitpython-bme280 2.6.0+ - BME280 environment sensor (optional, actual config uses BME680)
- piicodev 1.0.0+ - General Adafruit sensor driver support
- RPi.GPIO - Raspberry Pi GPIO control (gracefully degraded if unavailable, `src/shitbox/capture/button.py`)

**Data Transport:**
- paho-mqtt 2.0.0+ - MQTT client for real-time telemetry (currently disabled in config, `src/shitbox/sync/mqtt_publisher.py`)
- python-snappy 0.6.0+ - Snappy compression for Prometheus remote_write payloads

**Data Storage:**
- sqlite3 (stdlib) - Offline-first telemetry database with WAL mode (`src/shitbox/storage/database.py`)

**Resilience:**
- tenacity 8.0.0+ - Retry logic with exponential backoff (`src/shitbox/sync/batch_sync.py` line 269-280)

**Video & Overlay:**
- ffmpeg (system dependency) - Subprocess wrapper for video capture at 720p 30fps (`src/shitbox/capture/video.py`)
- OpenCV (implied by overlay functionality) - GPS/speed overlay rendering (`src/shitbox/capture/overlay.py`)

**Geolocation:**
- reverse_geocoder 1.5.1+ - Location name resolution for event metadata

**Serialisation:**
- protobuf 4.0.0+ - Protobuf message encoding for Prometheus (`src/shitbox/sync/prometheus_write.py`)

**Testing & Development:**
- pytest 7.0+ - Test framework
- pytest-cov 4.0+ - Code coverage reporting
- ruff 0.1.0+ - Linting (rules: E, F, I, W; line length 100)
- mypy 1.0+ - Static type checking (Python 3.9 target)

## Configuration

**Environment:**
- Config file: `config/config.yaml` (production: `/etc/shitbox/config.yaml`)
- Fallback search paths in `src/shitbox/utils/config.py` line 289-294:
  - Specified path
  - `config/config.yaml`
  - `/etc/shitbox/config.yaml`
  - `~/.config/shitbox/config.yaml`
- Config format: Flat YAML, parsed into nested dataclasses
- Master switch: `sync.uplink_enabled` (false = offline mode)

**Build:**
- `pyproject.toml` - setuptools build configuration with development extras
- No build step required for runtime
- Package installed via `pip install -e ".[dev]"` (editable mode for development)

## Platform Requirements

**Development:**
- Python 3.9+ with venv
- Ruff and mypy for linting/type checking
- pytest for testing
- No hardware required (graceful degradation for GPIO, GPS, sensors)

**Production (Raspberry Pi):**
- Raspberry Pi (any model with I2C and GPIO)
- Raspbian with I2C interface enabled (`raspi-config nonint do_i2c 0` in `scripts/install.sh`)
- System dependencies: `python3-pip`, `python3-venv`, `python3-dev`, `i2c-tools`, `gpsd`, `gpsd-clients`, `ffmpeg`
- User groups: `i2c` and `gpio` (set via `usermod -aG i2c,gpio` in install script)
- Data directory: `/var/lib/shitbox/` (755 permissions, user-owned)
- VPN: WireGuard for connectivity checks (assumes Prometheus host reachable)

## External System Dependencies

**Sensor Hardware (I2C Bus 1):**
- MPU6050 @ 0x68 - 6-axis IMU, sampled at 100 Hz
- BME680 @ 0x77 - Temperature, humidity, pressure, air quality
- INA219 @ 0x40 - Voltage/current/power monitoring (optional)
- MCP9808 @ 0x18 - Temperature sensor (optional)
- SSD1306 @ 0x3C - OLED display (128x64)

**GPS:**
- USB GPS receiver interfaced via gpsd daemon (port 2947)
- Devices: `/dev/serial0` (serial port) or USB
- Configuration: `/etc/default/gpsd`

**Video:**
- USB webcam `/dev/video0` - 720p 30fps with mic
- Audio device: ALSA (configurable, e.g., `plughw:CARD=Camera,DEV=0`)
- ffmpeg subprocess for capture and post-processing

**GPIO:**
- GPIO 17 - Big red button input (50 ms debounce)
- Piezo buzzer output

**Storage:**
- `/var/lib/shitbox/telemetry.db` - SQLite with WAL
- `/var/lib/shitbox/captures/` - Event video files
- `/var/lib/shitbox/video_buffer/` - ffmpeg ring buffer segments

---

*Stack analysis: 2026-02-24*
