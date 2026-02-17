# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shitbox is an offline-first rally car telemetry system for Raspberry Pi. It captures high-rate IMU data (100 Hz), GPS, and temperature readings, stores them in SQLite, and batch-syncs to Prometheus when network connectivity is available. It also records video on detected driving events (high G-force, hard braking, big corners) and manual button press.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest
pytest --cov=shitbox

# Lint
ruff check src/

# Type check
mypy src/

# Run the daemon
python -m shitbox.events.engine

# Run on RPi via systemd
sudo systemctl start shitbox-telemetry
```

## Architecture

The system runs as a single daemon (`UnifiedEngine`) managing three concurrent paths:

- **High-rate path (100 Hz)**: IMU sampling → ring buffer → event detection → event storage + video capture
- **Low-rate path (1 Hz)**: GPS/IMU/temperature collectors → SQLite → batch sync to Prometheus
- **Capture path**: GPIO button monitoring → video recording via ffmpeg

### Key modules

- `src/shitbox/events/engine.py` — Main daemon orchestrating all subsystems
- `src/shitbox/events/detector.py` — Event detection state machine (HARD_BRAKE, BIG_CORNER, HIGH_G, ROUGH_ROAD)
- `src/shitbox/events/ring_buffer.py` — Circular buffer for pre-event IMU data
- `src/shitbox/events/sampler.py` — High-rate MPU6050 IMU reader
- `src/shitbox/collectors/base.py` — Abstract base collector (template method, runs in daemon thread)
- `src/shitbox/storage/database.py` — SQLite with WAL mode, thread-safe with write locks
- `src/shitbox/sync/batch_sync.py` — Cursor-based Prometheus remote_write with Snappy compression
- `src/shitbox/sync/connection.py` — Network connectivity monitor
- `src/shitbox/capture/video.py` — ffmpeg subprocess wrapper for video recording
- `src/shitbox/capture/button.py` — GPIO button handler with debounce
- `src/shitbox/utils/config.py` — YAML config loading into nested dataclasses

### Data flow

All sensor data goes to SQLite first (offline-first). The batch sync service tracks a cursor to avoid re-transmitting. MQTT is disabled in config to prevent duplicate metrics. Connectivity is checked against the Prometheus host over WireGuard.

## Code Conventions

- **Logging**: Use `structlog` with keyword arguments — `log.info("event_detected", type=event_type.value, duration_ms=int(duration_ms))`
- **Ruff**: Line length 100, rules E/F/I/W, target Python 3.9
- **Types**: Full type annotations; mypy enforced
- **Config**: Hierarchical YAML (`config/config.yaml`) loaded into nested dataclasses
- **Threading**: Each collector runs in a daemon thread; database uses write locks and thread-local connections
- **Hardware graceful degradation**: GPIO, GPS, and sensors are optional — the system runs with whatever hardware is available
