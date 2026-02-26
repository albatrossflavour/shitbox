# Phase 3: Thermal Resilience and Storage Management - Research

**Researched:** 2026-02-26
**Domain:** Raspberry Pi thermal monitoring, SQLite WAL checkpointing, daemon thread design
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Hardcoded thresholds: 70°C warning, 80°C critical — these are Pi hardware limits, no config knob needed
- 3°C hysteresis on both thresholds — alert at 70°C, suppress until below 67°C before re-arming
- Recovery beep when temperature drops back below the warning threshold after an alert
- Thread-safe shared value for current temperature — other subsystems read it cheaply without polling sysfs
- Log on state change only — when any vcgencmd get_throttled flag flips, not every interval
- Track both "currently happening" and "has occurred since boot" flag sets in separate structlog fields
- Under-voltage (bit 0) triggers a distinct buzzer alert — driver needs to know about power supply issues
- Same 5-second interval as thermal sampling — one unified health check loop, read temp and throttle together
- Unconditional TRUNCATE checkpoint every 5 minutes on a timer
- Log only when pages were actually truncated — silent when WAL was already clean
- Runs inside the existing Database module — it already holds the connection and write lock, no new service thread

### Claude's Discretion

- Thermal monitor thread design and integration with engine lifecycle
- Exact structlog field names for throttle state
- How to read sysfs thermal zone vs vcgencmd for temperature (either approach acceptable)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| THRM-01 | Thermal monitor reads CPU temperature every 5 seconds and publishes to shared state | Sysfs read pattern already in engine; `threading.local` + `threading.Lock` for shared float |
| THRM-02 | System alerts (buzzer + log) at 70°C warning and 80°C throttle thresholds with hysteresis | Buzzer module pattern established; new `beep_thermal_*` functions follow existing conventions |
| THRM-03 | `vcgencmd get_throttled` bitmask decoded and logged at every health check | `subprocess.run` with graceful degradation; bitmask documented below |
| STOR-01 | WAL checkpoint runs periodic TRUNCATE to prevent unbounded WAL growth | `PRAGMA wal_checkpoint(TRUNCATE)` return value tells pages checkpointed; add `checkpoint_wal()` method to Database |
</phase_requirements>

---

## Summary

Phase 3 adds a ThermalMonitorService (daemon thread, 5-second cadence) that reads CPU temperature from sysfs, decodes the `vcgencmd get_throttled` bitmask, maintains hysteresis state, fires buzzer alerts and structured logs on threshold crossings, and publishes the current temperature to a thread-safe shared float that other subsystems can read without polling sysfs themselves.

The WAL checkpoint task is not a new thread — it is a new `checkpoint_wal()` method added to the existing `Database` class, called from a 5-minute timer in either the telemetry loop or the thermal monitor loop. The `PRAGMA wal_checkpoint(TRUNCATE)` call returns the number of pages checkpointed; log only when that value is non-zero.

All implementation follows existing patterns: graceful hardware degradation (try/except around sysfs/subprocess), buzzer alert functions using `_play_async` + `_should_alert()`, structlog keyword arguments, daemon threads with `start()`/`stop()` lifecycle.

**Primary recommendation:** Create `src/shitbox/health/thermal_monitor.py` as a new service class; add `checkpoint_wal()` to `Database`; wire both into `UnifiedEngine.start()`/`stop()`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `subprocess` | stdlib | `vcgencmd get_throttled` invocation | No external dep; Pi firmware command |
| Python stdlib `threading` | stdlib | Daemon thread for 5-second monitor loop | Already used throughout engine |
| Python stdlib `pathlib` | stdlib | Sysfs temperature read | Already used in engine._read_pi_temp() |
| `structlog` | project standard | Structured logging | All logging in codebase uses this |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlite3` stdlib | stdlib | WAL checkpoint PRAGMA | Already used in Database class |
| `shitbox.capture.buzzer` | project | Thermal alert sounds | Same buzzer module used for all alerts |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sysfs `/sys/class/thermal/thermal_zone0/temp` | `vcgencmd measure_temp` | sysfs is faster (file read vs subprocess); both are acceptable per CONTEXT.md; sysfs preferred for temp, vcgencmd for throttle state |
| Separate WAL checkpoint thread | Timer in telemetry loop | Simpler — CONTEXT.md says runs inside existing Database module, no new thread |

**Installation:** No new packages required.

---

## Architecture Patterns

### Recommended Project Structure

The new thermal monitor lives alongside other health services:

```
src/shitbox/
├── health/                    # New package (or add to sync/)
│   └── thermal_monitor.py     # ThermalMonitorService
├── storage/
│   └── database.py            # Add checkpoint_wal() method
├── capture/
│   └── buzzer.py              # Add beep_thermal_warning/critical/under_voltage/recovered
└── events/
    └── engine.py              # Wire thermal_monitor.start()/stop(), call checkpoint_wal()
```

Alternatively, `thermal_monitor.py` can live in `src/shitbox/sync/` (alongside BatchSyncService) to avoid creating a new package. Either placement is acceptable; a new `health/` package is cleaner for Phase 4 which adds more health metrics.

### Pattern 1: ThermalMonitorService Thread

**What:** Daemon thread with `start()`/`stop()` lifecycle, 5-second sleep loop.
**When to use:** Whenever a subsystem needs its own fixed-interval polling independent of the main loop.

```python
# Source: existing BatchSyncService / CaptureSyncService pattern in codebase
import threading
import time
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

TEMP_WARNING_C = 70.0
TEMP_CRITICAL_C = 80.0
HYSTERESIS_C = 3.0  # re-arm at (threshold - 3°C)
POLL_INTERVAL_S = 5.0

class ThermalMonitorService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._current_temp: float | None = None
        # Hysteresis state — independent per threshold
        self._warning_armed = True
        self._critical_armed = True
        # Throttle change detection
        self._last_throttled_raw: int | None = None

    @property
    def current_temp_celsius(self) -> float | None:
        """Thread-safe read of last known CPU temperature."""
        with self._lock:
            return self._current_temp

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="thermal-monitor"
        )
        self._thread.start()
        log.info("thermal_monitor_started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=POLL_INTERVAL_S + 1)
        log.info("thermal_monitor_stopped")

    def _loop(self) -> None:
        while self._running:
            try:
                self._check_thermal()
            except Exception as e:
                log.error("thermal_check_error", error=str(e))
            time.sleep(POLL_INTERVAL_S)
```

### Pattern 2: Sysfs Temperature Read

**What:** Read millidegree value from sysfs, divide by 1000.
**When to use:** Preferred over subprocess for temperature (fast, no shell fork).

```python
# Source: engine._read_pi_temp() — already implemented in engine.py line 979
from pathlib import Path

def _read_sysfs_temp() -> float | None:
    try:
        temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_path.exists():
            return int(temp_path.read_text().strip()) / 1000.0
    except (IOError, ValueError):
        pass
    return None
```

### Pattern 3: vcgencmd Throttle Decode

**What:** `subprocess.run` with graceful degradation; parse hex bitmask.
**When to use:** Only on Raspberry Pi; on dev laptop returns None gracefully.

```python
# Source: Raspberry Pi firmware documentation
import subprocess

# vcgencmd get_throttled returns e.g. "throttled=0x50000"
# Bitmask layout (official Pi firmware):
#   Bit 0:  Under-voltage detected (currently)
#   Bit 1:  Arm frequency capped (currently)
#   Bit 2:  Currently throttled
#   Bit 3:  Soft temperature limit active (currently)
#   Bit 16: Under-voltage has occurred since boot
#   Bit 17: Arm frequency capping has occurred since boot
#   Bit 18: Throttling has occurred since boot
#   Bit 19: Soft temperature limit has occurred since boot

THROTTLE_FLAGS = {
    0: "under_voltage",
    1: "freq_capped",
    2: "throttled",
    3: "soft_temp_limit",
}
BOOT_THROTTLE_FLAGS = {
    16: "under_voltage_since_boot",
    17: "freq_capped_since_boot",
    18: "throttled_since_boot",
    19: "soft_temp_limit_since_boot",
}

def _read_throttled() -> int | None:
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            # "throttled=0x50000\n"
            raw = result.stdout.strip().split("=")[-1]
            return int(raw, 16)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None

def _decode_throttled(value: int) -> dict:
    """Decode bitmask into two flag dicts: current and since-boot."""
    current = {name: bool(value & (1 << bit)) for bit, name in THROTTLE_FLAGS.items()}
    since_boot = {name: bool(value & (1 << bit)) for bit, name in BOOT_THROTTLE_FLAGS.items()}
    return {"current": current, "since_boot": since_boot}
```

### Pattern 4: Hysteresis State Machine

**What:** Two independent armed flags (warning and critical); re-arm when temp drops below `threshold - HYSTERESIS_C`.
**When to use:** Any threshold alert that should not fire repeatedly while temperature oscillates around the threshold.

```python
def _check_thermal(self) -> None:
    temp = _read_sysfs_temp()
    if temp is None:
        return

    with self._lock:
        self._current_temp = temp

    # Warning threshold (70°C, re-arm at 67°C)
    if temp >= TEMP_WARNING_C and self._warning_armed:
        log.warning("cpu_temp_warning", temp_celsius=round(temp, 1), threshold=TEMP_WARNING_C)
        buzzer.beep_thermal_warning()
        self._warning_armed = False
    elif temp < (TEMP_WARNING_C - HYSTERESIS_C):
        if not self._warning_armed:
            log.info("cpu_temp_recovered", temp_celsius=round(temp, 1))
            buzzer.beep_thermal_recovered()
        self._warning_armed = True

    # Critical threshold (80°C, re-arm at 77°C)
    if temp >= TEMP_CRITICAL_C and self._critical_armed:
        log.error("cpu_temp_critical", temp_celsius=round(temp, 1), threshold=TEMP_CRITICAL_C)
        buzzer.beep_thermal_critical()
        self._critical_armed = False
    elif temp < (TEMP_CRITICAL_C - HYSTERESIS_C):
        self._critical_armed = True

    # Throttle state — log only on change
    self._check_throttled()

def _check_throttled(self) -> None:
    raw = _read_throttled()
    if raw is None:
        return
    if raw == self._last_throttled_raw:
        return  # No change — silent
    self._last_throttled_raw = raw
    decoded = _decode_throttled(raw)
    log.info(
        "throttle_state_changed",
        raw_hex=hex(raw),
        current=decoded["current"],
        since_boot=decoded["since_boot"],
    )
    if decoded["current"]["under_voltage"]:
        buzzer.beep_under_voltage()
```

### Pattern 5: WAL Checkpoint with TRUNCATE

**What:** Add `checkpoint_wal()` method to Database; call it on a 5-minute timer from the telemetry loop.
**When to use:** Periodic maintenance to prevent WAL from growing unboundedly.

```python
# Source: SQLite documentation — PRAGMA wal_checkpoint(mode)
# Returns (busy, log, checkpointed): log=WAL pages total, checkpointed=pages written to db
def checkpoint_wal(self) -> None:
    """Run TRUNCATE WAL checkpoint and log when pages were actually written."""
    conn = self._get_connection()
    with self._write_lock:
        cursor = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        row = cursor.fetchone()
    # row = (busy, log, checkpointed)
    # log: total WAL pages; checkpointed: pages written back to db file
    if row and row[2] > 0:
        log.info(
            "wal_checkpoint_completed",
            pages_checkpointed=row[2],
            pages_in_wal=row[1],
        )
    # Else: WAL was already clean or no pages moved — stay silent
```

### Pattern 6: New Buzzer Alert Functions

**What:** Four new functions following the exact established pattern in `buzzer.py`.
**When to use:** Thermal threshold crossing events.

```python
# Follows exact pattern of beep_service_crash() / beep_i2c_lockup() etc.
# Thermal alerts use a distinct higher frequency (500 Hz) to differ from
# service-failure alerts (330 Hz) and boot/capture alerts (440/880 Hz).

def beep_thermal_warning() -> None:
    """Two medium 500 Hz tones: CPU temperature at warning threshold (70°C).

    Pattern: [(500, 400), (500, 400)]. Suppressed during boot grace period.
    """
    if not _should_alert():
        return
    name = "buzzer-thermal-warning"
    tones: list[tuple[int, int]] = [(500, 400), (500, 400)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_thermal_critical() -> None:
    """Three long 500 Hz tones: CPU temperature at critical threshold (80°C).

    Pattern: [(500, 600), (500, 600), (500, 600)]. Suppressed during boot
    grace period.
    """
    if not _should_alert():
        return
    name = "buzzer-thermal-critical"
    tones: list[tuple[int, int]] = [(500, 600), (500, 600), (500, 600)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_under_voltage() -> None:
    """Four rapid 500 Hz tones: under-voltage detected (power supply issue).

    Pattern: [(500, 150), (500, 150), (500, 150), (500, 150)]. Suppressed
    during boot grace period.
    """
    if not _should_alert():
        return
    name = "buzzer-under-voltage"
    tones: list[tuple[int, int]] = [(500, 150), (500, 150), (500, 150), (500, 150)]
    if _alert_state.should_escalate(name):
        tones = tones + tones
    _play_async(tones, name=name)


def beep_thermal_recovered() -> None:
    """Single descending pair: temperature recovered below warning threshold.

    Pattern: [(880, 150), (500, 150)]. Clears thermal warning escalation state.
    Suppressed during boot grace period.
    """
    if not _should_alert():
        return
    _alert_state.reset("buzzer-thermal-warning")
    _play_async([(880, 150), (500, 150)], name="buzzer-thermal-recovered")
```

### Anti-Patterns to Avoid

- **Forking subprocess for temperature reads:** `vcgencmd measure_temp` is a subprocess — use sysfs for temperature, keep subprocess only for throttle state.
- **Polling sysfs from multiple places:** The shared `current_temp_celsius` property on ThermalMonitorService is the single read point; other subsystems (OLED display, health monitor) use it instead of calling `_read_pi_temp()`.
- **TRUNCATE checkpoint inside write transaction:** Call `checkpoint_wal()` outside any transaction; WAL TRUNCATE needs all readers to be done.
- **Logging every throttle read:** Only log when the raw bitmask value changes. Unchanged state = silence.
- **New service thread for WAL checkpoint:** CONTEXT.md says this runs inside Database, on a timer from the telemetry/thermal loop — no new thread.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Throttle bitmask decode | Custom bit twiddler | Standard Python bit operations against documented Pi bitmask | Simple; documented layout is stable across Pi firmware |
| WAL size enforcement | DELETE old rows, schema changes | `PRAGMA wal_checkpoint(TRUNCATE)` | This is what WAL checkpointing is for — built into SQLite |
| Temperature moving average | Rolling buffer | Direct sysfs read every 5 seconds | 5-second cadence is sufficient; averaging adds complexity without benefit |
| Subprocess resilience | Retry loops | Single `subprocess.run` with `timeout=2` + `FileNotFoundError` catch | vcgencmd is fast; on failure just skip this interval |

**Key insight:** SQLite's WAL TRUNCATE checkpoint does exactly what is needed — it writes all WAL pages back to the main database file and resets the WAL to zero length. No custom file management is required.

---

## Common Pitfalls

### Pitfall 1: WAL TRUNCATE Blocked by Active Readers

**What goes wrong:** `PRAGMA wal_checkpoint(TRUNCATE)` returns `busy=1` and checkpoints zero pages if another connection is in the middle of a read transaction.
**Why it happens:** WAL TRUNCATE requires exclusive access — it can't shrink the WAL while readers hold a read lock.
**How to avoid:** Accept that some checkpoint calls will be blocked (busy=1, checkpointed=0). The 5-minute timer means the next attempt will succeed once the reader finishes. Do not hold the write lock across the checkpoint call — use a separate `with self._write_lock` block just for the PRAGMA.
**Warning signs:** WAL file growing beyond a few MB despite checkpoint calls running.

### Pitfall 2: vcgencmd Not Available on Dev Machine

**What goes wrong:** `subprocess.run(["vcgencmd", ...])` raises `FileNotFoundError` on macOS/Linux dev hosts that lack Pi firmware tools.
**Why it happens:** vcgencmd is a Raspberry Pi-specific tool.
**How to avoid:** Catch `FileNotFoundError` in the subprocess call; return `None` and log at debug level. Identical to how GPIO is handled in the codebase.
**Warning signs:** Import-time exceptions or test failures on non-Pi hosts.

### Pitfall 3: Hysteresis State Not Independent Per Threshold

**What goes wrong:** Dropping below the warning threshold re-arms the critical threshold too, causing spurious critical alerts when temperature oscillates between 70°C–80°C.
**Why it happens:** Using a single "armed" flag for both thresholds.
**How to avoid:** Two independent flags: `_warning_armed` and `_critical_armed`. The warning recovery fires a beep; the critical recovery is silent (no recovery beep at critical level — just re-arms).
**Warning signs:** Critical buzzer firing when temperature is at 72°C.

### Pitfall 4: Shared Temperature Value Without Lock

**What goes wrong:** Race condition between writer (thermal loop) and reader (OLED display thread).
**Why it happens:** Python float assignment is not atomic under all interpreters.
**How to avoid:** Use `threading.Lock` around writes and reads of `_current_temp`. Alternatively use `threading.Event` + `float` protected by a lock. The OLED display update path is not performance-critical, so lock overhead is negligible.
**Warning signs:** `None` readings from `current_temp_celsius` when temperature has been set.

### Pitfall 5: WAL Checkpoint Logs Every Run

**What goes wrong:** Log fills with "wal_checkpoint_completed pages_checkpointed=0" every 5 minutes when nothing is dirty.
**Why it happens:** Logging unconditionally rather than checking the return value.
**How to avoid:** Check `row[2] > 0` (pages checkpointed) before logging. Fully silent when WAL was already clean.
**Warning signs:** Logs growing rapidly with checkpoint messages.

---

## Code Examples

Verified patterns from official sources and existing codebase:

### WAL Checkpoint Return Value

```python
# Source: SQLite documentation https://www.sqlite.org/pragma.html#pragma_wal_checkpoint
# PRAGMA wal_checkpoint(TRUNCATE) returns a single row: (busy, log, checkpointed)
#   busy:         1 if WAL could not be fully checkpointed (readers active), 0 otherwise
#   log:          total number of frames in WAL after checkpoint
#   checkpointed: number of frames successfully checkpointed
#
# TRUNCATE mode: after checkpointing, resets WAL file to zero length (most aggressive)
# PASSIVE mode:  checkpoints without blocking readers (used in database.close() already)
cursor = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
row = cursor.fetchone()
busy, log_pages, checkpointed = row[0], row[1], row[2]
```

### Throttle Bitmask — Official Pi Documentation

```
vcgencmd get_throttled
throttled=0x50000

Bit  0: Under-voltage detected (current)
Bit  1: Arm frequency capped (current)
Bit  2: Currently throttled
Bit  3: Soft temperature limit active (current)
Bit 16: Under-voltage has occurred
Bit 17: Arm frequency capping has occurred
Bit 18: Throttling has occurred
Bit 19: Soft temperature limit has occurred

0x50000 = bits 16 and 18 set = "under-voltage occurred" + "throttling occurred"
```

### Engine Wiring (start/stop pattern)

```python
# In UnifiedEngine.__init__():
from shitbox.health.thermal_monitor import ThermalMonitorService
self.thermal_monitor = ThermalMonitorService()

# In UnifiedEngine.start():
self.thermal_monitor.start()

# In UnifiedEngine.stop():
self.thermal_monitor.stop()

# get_status() — expose temp for OLED display:
"cpu_temp": self.thermal_monitor.current_temp_celsius,
```

### WAL Checkpoint Timer in Telemetry Loop

```python
# In _telemetry_loop(), add alongside the existing cleanup timer:
WAL_CHECKPOINT_INTERVAL = 300  # 5 minutes

# In __init__, add:
self._last_wal_checkpoint = 0.0

# In _telemetry_loop():
if (now - self._last_wal_checkpoint) >= WAL_CHECKPOINT_INTERVAL:
    try:
        self.database.checkpoint_wal()
    except Exception as e:
        log.error("wal_checkpoint_error", error=str(e))
    self._last_wal_checkpoint = now
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `PRAGMA wal_autocheckpoint` only | Explicit `PRAGMA wal_checkpoint(TRUNCATE)` periodically | Already configured in codebase | Autocheckpoint uses PASSIVE mode and only triggers at 1000 pages; TRUNCATE is more thorough |
| Polling sysfs from every subsystem that needs temp | Single ThermalMonitorService with shared read property | Phase 3 | Eliminates N independent sysfs readers |

**Note on existing `wal_autocheckpoint=1000`:** Already set in `database.py` line 117. This runs PASSIVE checkpoints automatically at 1000 pages. The Phase 3 TRUNCATE checkpoint is additive — it runs more aggressively on a time schedule to ensure the WAL is fully reset, not just partially drained. Both mechanisms coexist.

**Note on existing `_read_pi_temp()`:** This method already exists in `engine.py` (lines 979–988). The ThermalMonitorService should implement its own sysfs read (same logic) rather than depending on the engine. After Phase 3, `get_status()` should read from `thermal_monitor.current_temp_celsius` instead of calling `_read_pi_temp()` directly — but that refactor is optional in this phase.

---

## Open Questions

1. **Which package for ThermalMonitorService?**
   - What we know: `sync/` has BatchSyncService, CaptureSyncService; no `health/` package exists yet
   - What's unclear: Whether Phase 4 health metrics (HLTH-01) warrants creating `src/shitbox/health/` now
   - Recommendation: Create `src/shitbox/health/__init__.py` + `thermal_monitor.py` to avoid moving the file in Phase 4. Low cost now, prevents later refactor.

2. **Tone frequencies for thermal alerts**
   - What we know: 330 Hz = service failures; 440/880 Hz = boot/capture; 220 Hz = general alarm
   - What's unclear: Whether 500 Hz is distinct enough from 440 Hz for the driver in a car
   - Recommendation: Use 500 Hz for thermal alerts as documented in Code Examples above. Adjust during physical testing if needed; the pattern (count and duration) is more distinguishable than frequency.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pytest.ini` or `pyproject.toml` (check at Wave 0) |
| Quick run command | `pytest tests/test_thermal_monitor.py -x -q` |
| Full suite command | `pytest --cov=shitbox` |
| Estimated runtime | ~2 seconds |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| THRM-01 | ThermalMonitorService exposes `current_temp_celsius` after first poll | unit | `pytest tests/test_thermal_monitor.py::test_temp_published_to_shared_state -x` | ❌ Wave 0 gap |
| THRM-01 | Thread-safe: concurrent reads do not race with writes | unit | `pytest tests/test_thermal_monitor.py::test_temp_thread_safe -x` | ❌ Wave 0 gap |
| THRM-02 | Warning buzzer fires at 70°C when armed | unit | `pytest tests/test_thermal_monitor.py::test_warning_fires_at_threshold -x` | ❌ Wave 0 gap |
| THRM-02 | Warning buzzer suppressed below 67°C after re-arm | unit | `pytest tests/test_thermal_monitor.py::test_hysteresis_suppresses_below_rearm -x` | ❌ Wave 0 gap |
| THRM-02 | Critical buzzer fires at 80°C independently of warning state | unit | `pytest tests/test_thermal_monitor.py::test_critical_fires_independently -x` | ❌ Wave 0 gap |
| THRM-02 | Recovery beep fires when temp drops below 67°C after warning | unit | `pytest tests/test_thermal_monitor.py::test_recovery_beep_on_cooldown -x` | ❌ Wave 0 gap |
| THRM-02 | New buzzer functions have correct tone patterns | unit | `pytest tests/test_buzzer_alerts.py::test_beep_thermal_warning_pattern -x` | ❌ Wave 0 gap |
| THRM-03 | Throttle state logged only on bitmask change, not every poll | unit | `pytest tests/test_thermal_monitor.py::test_throttle_logs_only_on_change -x` | ❌ Wave 0 gap |
| THRM-03 | Under-voltage bit triggers buzzer | unit | `pytest tests/test_thermal_monitor.py::test_under_voltage_triggers_buzzer -x` | ❌ Wave 0 gap |
| THRM-03 | `vcgencmd` unavailable → graceful None return, no exception | unit | `pytest tests/test_thermal_monitor.py::test_vcgencmd_not_found_graceful -x` | ❌ Wave 0 gap |
| STOR-01 | `checkpoint_wal()` logs when pages checkpointed > 0 | unit | `pytest tests/test_database.py::test_checkpoint_wal_logs_when_dirty -x` | ❌ Wave 0 gap |
| STOR-01 | `checkpoint_wal()` silent when WAL already clean | unit | `pytest tests/test_database.py::test_checkpoint_wal_silent_when_clean -x` | ❌ Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task — run: `pytest tests/test_thermal_monitor.py tests/test_database.py -x -q`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~2 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_thermal_monitor.py` — covers THRM-01, THRM-02, THRM-03
- [ ] Add thermal pattern tests to `tests/test_buzzer_alerts.py` — covers THRM-02 buzzer patterns
- [ ] Add `test_checkpoint_wal_*` tests to `tests/test_database.py` — covers STOR-01
- [ ] `src/shitbox/health/__init__.py` — empty init for new health package

---

## Sources

### Primary (HIGH confidence)

- SQLite official docs — `PRAGMA wal_checkpoint` return values and mode semantics: https://www.sqlite.org/pragma.html#pragma_wal_checkpoint
- Raspberry Pi firmware documentation — `vcgencmd get_throttled` bitmask layout: https://www.raspberrypi.com/documentation/computers/os.html#get_throttled
- Existing codebase — `src/shitbox/events/engine.py` lines 574–580 (health constants), 979–988 (`_read_pi_temp`), 1583–1663 (`_health_check`), 181–189 (`database.close` with TRUNCATE checkpoint)
- Existing codebase — `src/shitbox/capture/buzzer.py` (full file — all buzzer patterns and escalation logic)
- Existing codebase — `src/shitbox/storage/database.py` lines 104–120 (WAL configuration, autocheckpoint=1000, write lock pattern)

### Secondary (MEDIUM confidence)

- Existing codebase — `src/shitbox/utils/config.py` lines 157–167 (`HealthConfig` dataclass with `temp_warning_celsius=70`, `temp_critical_celsius=80`) — confirms thresholds match existing config intent

### Tertiary (LOW confidence)

- Tone frequency choices (500 Hz for thermal) — inferred from existing frequency allocation; no official project standard exists for thermal alert pitch

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all libraries are stdlib or already in project
- Architecture: HIGH — patterns confirmed against existing code in engine.py and buzzer.py
- Pitfalls: HIGH — WAL checkpoint blocking behaviour is documented in SQLite official docs; others confirmed from code review
- Validation architecture: HIGH — pytest framework confirmed by existing test files

**Research date:** 2026-02-26
**Valid until:** 2026-04-26 (stable domain — Pi firmware and SQLite behaviour are unlikely to change)
