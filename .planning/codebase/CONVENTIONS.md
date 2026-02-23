# Coding Conventions

**Analysis Date:** 2026-02-24

## Naming Patterns

**Files:**
- `snake_case.py` for all Python modules
- Descriptive, domain-specific names: `database.py`, `batch_sync.py`, `event_detector.py`
- Private/internal modules use underscore prefix when needed: `_internal.py`
- Config files follow package naming: `config.py`, `config/config.yaml`

**Functions:**
- `snake_case` for all function names: `process_sample()`, `_sync_batch()`, `get_logger()`
- Private/internal functions prefixed with single underscore: `_on_event()`, `_read_gps()`, `_get_connection()`
- Boolean-returning functions typically use `is_*` or `has_*` prefix: `is_connected`, `is_running`, `has_fix`
- Callback functions use `on_*` pattern: `on_event`, `on_sample`, `on_press`

**Variables:**
- `snake_case` for local variables and attributes: `ring_buffer`, `peak_value`, `sample_rate_hz`
- Constants in `UPPER_SNAKE_CASE`: `HEALTH_CHECK_INTERVAL`, `VIDEO_CAPTURE_EVENTS`, `DISK_LOW_PCT`
- Private attributes use leading underscore: `_running`, `_thread`, `_last_health_time`
- Dictionary keys use `snake_case`: `"event_type"`, `"start_time"`, `"peak_ax"`

**Types:**
- Class names in `PascalCase`: `EventDetector`, `BatchSyncService`, `UnifiedEngine`, `Database`
- Enum names in `PascalCase` with `UPPER_SNAKE_CASE` members: `class EventType(Enum): HARD_BRAKE = "hard_brake"`
- Dataclass names in `PascalCase`: `DetectorConfig`, `EngineConfig`, `Reading`
- Custom exceptions in `PascalCase` with `Error` suffix: `DuplicateDataError`, `TooOldSampleError`

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `pyproject.toml`)
- Python version target: 3.9+
- Use double quotes for strings (enforced by ruff)
- Imports sorted by: stdlib, third-party, local (via ruff rule I)
- No trailing commas required; style varies but consistent within modules

**Linting:**
- Ruff with rules: E, F, I, W (see `pyproject.toml`)
- E: PEP 8 errors (whitespace, naming, indentation)
- F: Pyflakes (undefined names, unused imports)
- I: Isort (import sorting)
- W: Warnings (blank lines, indentation consistency)
- No linting configuration overrides in place (e.g., no `.ruffignore` or flake8 config)

**Type Checking:**
- mypy enforced (configured in `pyproject.toml`)
- `warn_return_any = true`: catches implicit Any returns
- `warn_unused_configs = true`: catches unused mypy settings
- Full type annotations required on public functions and class methods
- Private helper functions may have less strict annotation if context is clear

## Import Organization

**Order:**
1. Standard library imports (`import sys`, `import threading`, `from dataclasses import dataclass`)
2. Third-party imports (`import yaml`, `import requests`, `from tenacity import retry`)
3. Local imports (`from shitbox.utils.logging import get_logger`, `from shitbox.storage.models import Reading`)

**Path Aliases:**
- No explicit path aliases configured in `pyproject.toml`
- All imports use full qualified paths from project root: `from shitbox.events.detector import Event`
- Project structure enables clean imports without aliases

**Examples from codebase:**
```python
# From src/shitbox/events/engine.py
import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from shitbox.capture import buzzer, overlay
from shitbox.capture.button import ButtonHandler
from shitbox.events.detector import DetectorConfig, Event, EventDetector, EventType
from shitbox.utils.config import load_config
from shitbox.utils.logging import get_logger
```

## Error Handling

**Patterns:**
- Custom exception classes extend `Exception` and document their purpose: see `DuplicateDataError`, `TooOldSampleError` in `src/shitbox/sync/batch_sync.py`
- Broad exception catching with detailed logging: `except Exception as e: log.error("context_error", error=str(e))`
- No silent failures: all exceptions are logged with context
- Recoverable errors (e.g. transient network issues) raise for caller to handle: `raise` in `_send_to_prometheus()`
- Critical initialization failures prevent startup: `raise` in collector `setup()` methods
- Graceful degradation for hardware: optional sensors fail silently and continue (see GPS/Power/Environment in `UnifiedEngine.__init__()`)

**Examples:**
- `src/shitbox/collectors/base.py`: Track `_error_count`, stop after `_max_errors = 10` consecutive errors
- `src/shitbox/events/engine.py`: Lazy initialization with try/except, log errors but continue if sensor unavailable
- `src/shitbox/sync/batch_sync.py`: Specific exception handling (duplicate data vs too old data) with different recovery strategies

## Logging

**Framework:** structlog with structured keyword arguments

**Patterns:**
- Get logger once at module level: `log = get_logger(__name__)`
- Log events with descriptive snake_case event names and keyword arguments: `log.info("event_queued_for_save", event_type=event.event_type.value, event_id=id(event))`
- Numeric values rounded/formatted for readability: `log.info("gps_fix_acquired_at_startup", lat=round(reading.latitude, 4), lon=round(reading.longitude, 4))`
- Avoid string interpolation; use keyword arguments: `log.error("error_name", field=value)` not `log.error(f"Error: {value}")`
- Use descriptive log levels:
  - `log.debug()` for low-level diagnostics (e.g. "batch_sync_no_data")
  - `log.info()` for state transitions and significant events (e.g. "unified_engine_started")
  - `log.warning()` for recoverable issues (e.g. "gps_fix_timeout_at_startup")
  - `log.error()` for failures that degrade functionality (e.g. "gps_init_failed")

**Examples from codebase:**
```python
# From src/shitbox/events/engine.py line 641
log.info(
    "event_queued_for_save",
    event_type=event.event_type.value,
    event_id=id(event),
    pending_count=len(self._pending_post_capture),
    save_after_seconds=self.config.detector.post_event_seconds,
)

# From src/shitbox/utils/logging.py line 9
log = get_logger(__name__)
```

## Comments

**When to Comment:**
- Complex algorithms (e.g. haversine distance calculation in `_haversine_km()`)
- Non-obvious design decisions or workarounds (e.g. gpsd-py3 bug workaround in `_get_satellite_count()`)
- Hardware-specific behaviour (e.g. MPU6050 address constants)
- Temporal logic or timing requirements (e.g. "skip checks during startup" grace period)
- Avoid comments restating obvious code: `x = x + 1  # increment x` is noise

**Docstrings:**
- All public functions and classes have docstrings
- Format: Google-style with Args, Returns, Raises sections
- Single-line summary for simple functions
- Multi-line for complex logic

**Examples:**
```python
# From src/shitbox/events/detector.py lines 145-153
def process_sample(self, sample: IMUSample) -> Optional[Event]:
    """Process a new sample and check for events.

    Args:
        sample: New IMU sample.

    Returns:
        Completed Event if one just ended, None otherwise.
    """

# From src/shitbox/events/engine.py lines 858-868
def _sync_clock_from_gps(self, gps_time: datetime) -> None:
    """Set the system clock from GPS time on first fix.

    Runs once per boot to correct the clock when NTP is unavailable
    (e.g. no network). Only adjusts if the drift is >30 seconds to
    avoid fighting NTP when it is available.

    Uses clock_settime via ctypes — requires CAP_SYS_TIME capability
    on the systemd service.
    """
```

## Function Design

**Size:**
- Functions typically 20-100 lines; longer functions (300+ lines like `engine.py` methods) break down into private helpers or are well-justified by complexity
- High-rate callbacks (e.g. `_on_imu_sample()`) are minimal: delegate to other objects
- Loops with complex body factor out helper methods (e.g. `_telemetry_loop()` calls `_check_post_captures()`, `_check_timelapse()`)

**Parameters:**
- Explicit typed parameters: no `*args` or `**kwargs` except in special cases (e.g. callback patterns)
- Reasonable parameter count (typically 1-5); if >5, consider grouping into a config dataclass
- Use dataclasses for configuration objects: `EngineConfig`, `DetectorConfig`, `PrometheusConfig`
- Optional parameters have defaults: `Optional[str] = None`, `bool = True`

**Return Values:**
- Functions return typed values: avoid bare `return` (must be `return None` explicitly if needed)
- Callbacks return `None` (callbacks are side-effect functions)
- Methods that perform work on self typically return `None` or Optional results
- Queries/reads return the data type (e.g. `get_latest(n) -> List[IMUSample]`)

**Examples:**
```python
# From src/shitbox/events/engine.py lines 556-558
def _on_imu_sample(self, sample: IMUSample) -> None:
    """Called for each high-rate IMU sample."""
    self.detector.process_sample(sample)

# From src/shitbox/collectors/base.py lines 104-120
def _get_connection(self) -> sqlite3.Connection:
    """Get thread-local database connection."""
    if not hasattr(self._local, "conn") or self._local.conn is None:
        self._local.conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False,
        )
        # ... rest of initialization
    return self._local.conn
```

## Module Design

**Exports:**
- Modules export their main class/function at the top level
- Private helpers use leading underscore (not re-exported)
- No wildcard imports (`from module import *`) in codebase

**Barrel Files:**
- Package `__init__.py` files are minimal or empty (no re-exports)
- Consumers import directly: `from shitbox.events.detector import Event` not `from shitbox.events import Event`
- Examples: `src/shitbox/capture/__init__.py`, `src/shitbox/collectors/__init__.py` are empty

**Class Structure:**
- Single responsibility: each class does one job (detector detects, database manages schema, etc.)
- Composition over inheritance: see `UnifiedEngine` which composes services rather than extending base
- Factory methods for complex object creation: `EngineConfig.from_yaml_config()`, `Reading.from_gps()`

**Dataclass Usage:**
- Prefer dataclasses over manual `__init__`: `@dataclass class DetectorConfig`
- Use `field(default_factory=...)` for mutable defaults: `samples: List[IMUSample] = field(default_factory=list)`
- Dataclasses used for: configuration, models/data containers, event objects
- Not used for: stateful services (use regular classes with `__init__`)

---

*Convention analysis: 2026-02-24*
