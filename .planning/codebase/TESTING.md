# Testing Patterns

**Analysis Date:** 2026-02-24

## Test Framework

**Runner:**
- pytest (version ≥7.0, configured in `pyproject.toml`)
- Config file: None (uses pytest defaults; can add `pytest.ini` or `[tool.pytest.ini_options]` in `pyproject.toml` if needed)

**Assertion Library:**
- pytest built-in assertions (no external assertion library like hypothesis or testtools)

**Run Commands:**
```bash
pytest                  # Run all tests (currently only integration test tools exist)
pytest --cov=shitbox   # Run with coverage report
pytest -v              # Verbose output
pytest -x              # Stop on first failure
pytest path/to/test    # Run specific test file
```

**Available via pip:**
```bash
pip install -e ".[dev]"  # Installs pytest, pytest-cov, ruff, mypy
```

## Current Testing Status

**No unit test suite exists.** The codebase has:
- One integration/debug script: `scripts/imu_test.py` (interactive IMU alignment test, not automated)
- No test directory: No `tests/` or `test_*.py` files in the repo
- No CI/CD test pipeline configured

**Test coverage:** Not measured (0% baseline)

## Test File Organization

**Expected Location (to be implemented):**
- Co-located pattern: Test files next to source (`src/shitbox/events/test_detector.py` next to `src/shitbox/events/detector.py`)
- OR separate tests directory: `tests/unit/`, `tests/integration/`
- Current convention: Not established; project needs test structure decision

**Naming Convention (when tests added):**
- Use `test_*.py` prefix: `test_detector.py`, `test_database.py`
- Test function names: `test_event_detector_hard_brake()`, `test_database_insert_reading()`
- Test class names (if used): `TestEventDetector`, `TestDatabase`

## Test Structure (Expected Pattern)

Since no tests exist, the following pattern should be followed based on project structure and architecture:

**Unit test structure (example for event detector):**
```python
# tests/unit/test_detector.py or src/shitbox/events/test_detector.py
import pytest
from shitbox.events.detector import EventDetector, EventType, Event
from shitbox.events.ring_buffer import RingBuffer, IMUSample


class TestEventDetector:
    """Unit tests for EventDetector."""

    @pytest.fixture
    def ring_buffer(self):
        """Fixture: populated ring buffer."""
        rb = RingBuffer(max_seconds=30, sample_rate_hz=100)
        return rb

    @pytest.fixture
    def detector(self, ring_buffer):
        """Fixture: detector instance."""
        return EventDetector(ring_buffer)

    def test_detector_initialization(self, detector):
        """Test detector initialises with default config."""
        assert detector.config is not None
        assert detector.ring_buffer is not None
        assert len(detector._active_events) == 0

    def test_hard_brake_detection(self, detector):
        """Test hard brake is detected when ax < threshold."""
        # Arrange: Create samples simulating hard braking
        # Act: Process samples
        # Assert: Event is detected and callback fired
        pass
```

**Integration test structure (example for engine):**
```python
# tests/integration/test_engine.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from shitbox.events.engine import UnifiedEngine, EngineConfig


class TestUnifiedEngine:
    """Integration tests for UnifiedEngine."""

    @pytest.fixture
    def engine_config(self):
        """Fixture: engine config with sensible test defaults."""
        return EngineConfig(
            imu_sample_rate_hz=100.0,
            ring_buffer_seconds=5.0,
            telemetry_interval_seconds=1.0,
            gps_enabled=False,  # Disable for testing
            prometheus_enabled=False,
            mqtt_enabled=False,
        )

    @pytest.fixture
    def engine(self, engine_config, tmp_path):
        """Fixture: engine instance with temp directories."""
        engine_config.events_dir = str(tmp_path / "events")
        engine_config.database_path = str(tmp_path / "test.db")
        return UnifiedEngine(engine_config)

    def test_engine_initialization(self, engine):
        """Test engine initialises components correctly."""
        assert engine.config is not None
        assert engine.sampler is not None
        assert engine.detector is not None
        assert engine.event_storage is not None
        assert engine.database is not None
```

## Mocking

**Framework:** unittest.mock (part of Python stdlib)

**Patterns:**
- Use `Mock()` and `MagicMock()` from `unittest.mock`
- Use `@patch` decorator for replacing module-level dependencies
- Hardware dependencies should be mocked (GPIO, I2C sensors, GPS)
- Network dependencies should be mocked (MQTT, Prometheus, HTTP)
- File I/O can use `tmp_path` pytest fixture for isolation

**What to Mock:**
- Hardware: `smbus2.SMBus`, `gpiozero.Button`, `gpsd-py3` connections
- Network: `requests.post()`, `mqtt.Client()`, socket connections
- System calls: `os.environ`, `subprocess`, system time (with `time.monkeypatch`)
- External files: GPS data files (use fixtures instead of real files)

**What NOT to Mock:**
- Dataclasses and data models (use real instances)
- Core business logic (event detection algorithms)
- Database operations (use in-memory SQLite or temp files)
- Logging (inspect logs via caplog fixture)

**Example mocking patterns (to be implemented):**
```python
from unittest.mock import Mock, patch, MagicMock
import pytest

# Mock hardware I2C sensor
@patch('shitbox.events.sampler.smbus2.SMBus')
def test_sampler_reads_imu(mock_smbus):
    """Test sampler reads from I2C bus."""
    mock_bus = MagicMock()
    mock_smbus.return_value = mock_bus
    mock_bus.read_i2c_block_data.return_value = [0, 1, 2, 3, 4, 5, 6]

    sampler = HighRateSampler()
    # ... assertions

# Mock network connectivity
@patch('shitbox.sync.batch_sync.requests.post')
def test_batch_sync_sends_to_prometheus(mock_post):
    """Test batch sync sends metrics to Prometheus."""
    mock_post.return_value.status_code = 204

    service = BatchSyncService(config, db, connection)
    service._send_to_prometheus([reading])

    mock_post.assert_called_once()

# Use temp directories for file I/O tests
def test_event_storage_saves_to_disk(tmp_path):
    """Test event storage writes JSON files."""
    storage = EventStorage(base_dir=str(tmp_path))
    event = Event(...)

    json_path, video_path = storage.save_event(event)

    assert json_path.exists()
    assert json_path.read_text()  # Has content

# Capture logs
def test_database_logs_errors(caplog):
    """Test database logs connection errors."""
    with pytest.raises(sqlite3.Error):
        db.connect()

    assert "connection_failed" in caplog.text
```

## Fixtures and Factories

**Test Data (to be implemented):**
- Use pytest fixtures for reusable test objects
- Create factory functions for complex objects (e.g. Event with full samples)

**Fixture Examples (to implement):**
```python
# tests/conftest.py - shared fixtures for all tests

import pytest
from datetime import datetime, timezone
from shitbox.events.ring_buffer import IMUSample
from shitbox.events.detector import Event, EventType
from shitbox.storage.models import Reading, SensorType


@pytest.fixture
def imu_sample():
    """Fixture: single IMU sample."""
    return IMUSample(
        timestamp=datetime.now(timezone.utc).timestamp(),
        ax=0.1,
        ay=0.2,
        az=1.0,
        gx=0.0,
        gy=0.0,
        gz=0.0,
    )


@pytest.fixture
def imu_samples(imu_sample):
    """Fixture: list of IMU samples."""
    return [
        IMUSample(
            timestamp=imu_sample.timestamp + i * 0.01,
            ax=0.1 * (i % 2),
            ay=0.2 * (i % 2),
            az=1.0,
            gx=0.0,
            gy=0.0,
            gz=0.0,
        )
        for i in range(100)
    ]


@pytest.fixture
def hard_brake_event():
    """Fixture: event representing hard braking."""
    return Event(
        event_type=EventType.HARD_BRAKE,
        start_time=1234567890.0,
        end_time=1234567891.0,
        peak_value=0.5,
        peak_ax=-0.5,
        peak_ay=0.0,
        peak_az=1.0,
    )


@pytest.fixture
def gps_reading():
    """Fixture: GPS sensor reading."""
    return Reading(
        timestamp_utc=datetime.now(timezone.utc),
        sensor_type=SensorType.GPS,
        latitude=-37.8,
        longitude=144.9,
        altitude_m=100.0,
        speed_kmh=50.0,
        heading_deg=90.0,
        satellites=12,
        fix_quality=2,
    )
```

**Location:**
- Shared fixtures in `tests/conftest.py`
- Module-specific fixtures in test files: `test_detector.py` contains fixtures for detector tests
- Factories for complex objects: helper functions in `tests/factories.py`

## Coverage

**Requirements:** Not currently enforced in CI/CD (no CI configured)

**Target (suggested):**
- Unit tests: 80%+ coverage for core modules (detector, database, sync)
- Integration tests: Key paths (startup, event capture, sync)
- Critical areas: Event detection, database operations, configuration loading

**View Coverage:**
```bash
pytest --cov=shitbox --cov-report=html
# Opens htmlcov/index.html in browser
```

## Test Types

**Unit Tests:**
- Scope: Single class or function in isolation
- Approach: Mock external dependencies (hardware, network, filesystem)
- Speed: <1ms per test (should run hundreds in <1 second)
- Examples: `test_detector.py`, `test_models.py`, `test_config.py`

**Integration Tests:**
- Scope: Multiple components working together (detector + ring buffer, database + sync)
- Approach: Use real objects where possible; mock only external systems (GPIO, network)
- Speed: 10-100ms per test (acceptable as they're fewer)
- Examples: `test_engine_startup.py`, `test_capture_flow.py`

**E2E Tests:**
- Status: Not used in this project (hardware-dependent)
- Would require: Real RPi, GPS simulator, camera, GPIO pins
- Instead: Use device integration tests on actual hardware during deployment

## Common Patterns (to Implement)

**Async Testing:**
```python
# Not applicable - no async/await in codebase
# Threading tests use mocks and time.sleep() for synchronisation
```

**Error Testing:**
```python
# Test exception handling
def test_detector_handles_invalid_sample():
    """Test detector handles malformed samples gracefully."""
    detector = EventDetector(ring_buffer)

    with pytest.raises(ValueError):
        detector.process_sample(None)  # Invalid sample


def test_database_reconnects_on_timeout(monkeypatch):
    """Test database reconnects after temporary loss of connection."""
    db = Database(":memory:")

    # Simulate connection timeout
    with patch.object(db, '_get_connection') as mock_get:
        mock_get.side_effect = sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError):
            db.insert_reading(reading)
```

**Testing Callbacks:**
```python
# Test callback invocation
def test_detector_fires_callback_on_event(ring_buffer):
    """Test event callback is invoked."""
    callback_mock = Mock()
    detector = EventDetector(ring_buffer, on_event=callback_mock)

    # Process samples that trigger event
    for sample in hard_brake_samples:
        detector.process_sample(sample)

    callback_mock.assert_called()
    event = callback_mock.call_args[0][0]
    assert event.event_type == EventType.HARD_BRAKE
```

**Testing Thread Safety (when added):**
```python
# Test concurrent access
import concurrent.futures

def test_database_thread_safe():
    """Test database handles concurrent writes from multiple threads."""
    db = Database(":memory:")
    db.connect()

    def insert_readings():
        for i in range(100):
            reading = gps_reading()
            db.insert_reading(reading)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(insert_readings) for _ in range(4)]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    # Verify all reads were stored
    assert db.get_reading_count() >= 400
```

---

*Testing analysis: 2026-02-24*

## Status Notes

**Current State:**
- Project has pytest and pytest-cov in dev dependencies
- No test suite implemented
- One integration/debug tool exists: `scripts/imu_test.py`
- No CI/CD configured to run tests

**Next Steps (for implementation):**
1. Create `tests/` directory with `conftest.py` for shared fixtures
2. Implement unit tests for `detector.py`, `database.py`, `models.py` (highest ROI)
3. Implement integration tests for `engine.py` startup and event flow
4. Add pytest config to `pyproject.toml` if needed
5. Integrate pytest into CI/CD pipeline (GitHub Actions, etc.)
6. Target 70%+ coverage for critical paths
