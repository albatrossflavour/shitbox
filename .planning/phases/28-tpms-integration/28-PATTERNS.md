# Phase 28: TPMS Integration — Pattern Map

**Mapped:** 2026-04-28
**Files analysed:** 19 (5 new modules, 9 modified, 5 new test files, 1 modified test file, 1 modified conftest)
**Analogs found:** 19 / 19 (every file has a concrete prior-art analog in the repo)

## Scope notes

- All paths absolute beneath `/Users/tgreen/dev/shitbox/`.
- Excerpts kept tight (5–15 lines) and quoted with file path + line range.
- 28-RESEARCH.md already reads like a half-written PATTERNS.md; this file consolidates the per-new-file mapping so the planner does not have to re-derive it.

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `src/shitbox/sync/tpms.py` (NEW) | service | event-driven (subprocess stdout stream → state + storage + alerts) | `src/shitbox/capture/ring_buffer.py` (subprocess lifecycle) + `src/shitbox/sync/capture_sync.py` (service shape) | exact (combined) |
| `src/shitbox/utils/config.py` (MOD) | config | n/a | `ParticulateConfig` at lines 157–164 (simple block) and the `temperature.probes` list-of-dataclasses pattern in `load_config` lines 519–525 | exact |
| `src/shitbox/storage/database.py` (MOD) | model / migration | n/a | `_migrate_to_v6` at lines 298–330 (CREATE-TABLE-IF-NOT-EXISTS migration); `get_unsynced_readings` + `update_sync_cursor` lines 556–619 (cursor pattern) | exact |
| `src/shitbox/dashboard/sse.py` (MOD) | controller / render | request-response (SSE poll) | `_system_conditions_payload` at lines 110–151; `/sse/slow` payload assembly lines 246–281 | exact |
| `src/shitbox/dashboard/static/index.html` (MOD) | view | SSE consumer | SYSTEM section at lines 412–422; Alpine state init at lines 466–470 and SSE merge near line 623 | exact |
| `src/shitbox/health/alerts.py` (MOD if helpers added) | utility | n/a | The module is reused as-is; the wiring analog is `src/shitbox/health/thermal_monitor.py` lines 322–340 (UNDERVOLTAGE fire+recovery pair) | exact |
| `src/shitbox/capture/speaker.py` (MOD) | utility | request-response (queue.put) | `speak_power_restored` at lines 445–454; `_CACHED_MESSAGES` dict at lines 47–77 | exact |
| `src/shitbox/events/storage.py` (MOD — empty-CSV branch optional) and `src/shitbox/events/detector.py` (MOD — new `EventType.TPMS_LEAK`) | model | n/a | `EventType` enum at `events/detector.py:15–24`; `save_event` + `_write_csv` shape at `events/storage.py:91–151` | exact |
| `src/shitbox/events/engine.py` (MOD) | service wiring | n/a | `BatchSyncService` instantiation at `engine.py:562–578`; `CaptureSyncService` instantiation at `engine.py:603–622`; flat `EngineConfig` field block at lines 218–222 + `from_yaml_config` mapping at lines 369–372 | exact |
| `src/shitbox/sync/batch_sync.py` (MOD — TPMS branch + cursor) | service | streaming write to remote_write | `_readings_to_metrics` at lines 384–550 (label-shaped metrics); `_sync_batch` cursor advance at lines 184–292 | exact |
| `src/shitbox/hardware/probes.py` (MOD — new `probe_usb_vid_pid`) | utility | request-response | `probe_usb_path` at lines 40–42 (single-shot bool, no held resources); `probe_audio_label` at lines 53–58 (subprocess-style string scan) | role-match |
| `src/shitbox/hardware/supervisor.py` (MOD — new `bus: usb_vid_pid` dispatch) | service | n/a | `_run_probe` at lines 86–105 | exact |
| `config/config.yaml` (MOD) | config | n/a | `hardware.devices` block at lines 316–360 + per-feature blocks like `sensors.particulate` at line 157 | exact |
| `scripts/install.sh` (MOD) | install | n/a | apt-get line at 62 + i2c-tools/sox precedent | exact |
| `tests/test_tpms_parser.py` (NEW) | test (unit) | n/a | `tests/test_alerts.py` (autouse fixture, MagicMock + patch); pure-function unit-test shape | role-match |
| `tests/test_tpms_database.py` (NEW) | test (integration) | n/a | `tests/conftest.py` `db` fixture + `tests/test_database.py` migration tests | role-match |
| `tests/test_tpms_alerts.py` (NEW) | test (unit) | n/a | `tests/test_alerts.py` (sustain + transition + recovery) + `tests/test_thermal_monitor.py` for `monkeypatch.setattr("…time.monotonic", …)` clock-jump pattern | exact |
| `tests/test_tpms_leak.py` (NEW) | test (unit + integration) | n/a | `tests/test_alerts.py` for fire-once-on-transition; `tests/test_events_storage_poster.py` for save_event integration shape | role-match |
| `tests/test_tpms_subprocess.py` (NEW) | test (integration) | n/a | `tests/test_ffmpeg_stall.py` lines 1–160 (`MagicMock` + `monkeypatch.setattr(...time.monotonic...)` + factory helper for the unit under test) | exact |
| `tests/test_dashboard.py` (MOD — extend) | test (unit) | n/a | Existing `_system_conditions_payload` tests at lines 427–499 | exact |
| `tests/conftest.py` (MOD — add fixtures) | test fixture | n/a | Existing `db` and `event_storage` fixtures at lines 21–45 | exact |

## Pattern Assignments

### `src/shitbox/sync/tpms.py` (service, event-driven)

**Primary analog:** `src/shitbox/capture/ring_buffer.py` (subprocess lifecycle + stderr drain + restart-on-death)
**Secondary analog:** `src/shitbox/sync/capture_sync.py` (service start/stop/thread shape)

**Imports pattern** (lift from `capture_sync.py:1–16` and `ring_buffer.py` top-of-file):

```python
# Source: src/shitbox/sync/capture_sync.py:1–16
import json
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Optional

from shitbox.events.storage import EventStorage
from shitbox.health import alerts
from shitbox.hardware import state as hw_state
from shitbox.storage.database import Database
from shitbox.utils.config import TpmsConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)
```

**Subprocess Popen pattern** (lift from `ring_buffer.py:780–786`):

```python
# Source: src/shitbox/capture/ring_buffer.py:780–786
self._process = subprocess.Popen(
    cmd,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,   # tpms.py keeps stdout=PIPE for JSON frames
    stderr=subprocess.PIPE,
    preexec_fn=_nice,
)
```

For tpms.py the stdout must be `subprocess.PIPE` with `text=True, bufsize=1` so `readline()` returns one JSON object per call. The rest is identical.

**Non-blocking stderr drain — copy verbatim** (`ring_buffer.py:827–846`):

```python
# Source: src/shitbox/capture/ring_buffer.py:827–846
def _read_stderr(self) -> str:
    """Read available stderr from the current process without blocking."""
    if self._process and self._process.stderr:
        try:
            fd = self._process.stderr.fileno()
            flags = os.get_blocking(fd)
            os.set_blocking(fd, False)
            try:
                data = b""
                while True:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    data += chunk
            finally:
                os.set_blocking(fd, flags)
            return data.decode(errors="replace")[-500:]
        except Exception:
            pass
    return ""
```

This is the fix for the March 2026 ffmpeg pipe-buffer stall — same root cause applies to rtl_433 at `-vvv`. Don't re-invent.

**Health monitor restart loop** (lift from `ring_buffer.py:926–1010`, simplified — no stall detection because rtl_433 doesn't write segments):

```python
# Source: src/shitbox/capture/ring_buffer.py:934–1011 (skeleton)
def _monitor_loop(self) -> None:
    while self._running:
        time.sleep(self.RESTART_BACKOFF_SECONDS)
        if not self._running:
            break
        try:
            # Always drain stderr — pipe is 64KB, fills under -vvv
            if self._process is not None and self._process.poll() is None:
                self._read_stderr()
            # Restart on death
            if self._process is not None and self._process.poll() is not None:
                rc = self._process.returncode
                stderr = self._read_stderr()
                log.warning("tpms_rtl433_exited", returncode=rc, stderr=stderr)
                # USB device gone → back off, mark MISSING
                if not probe_usb_vid_pid(self.config.usb_vid_pid):
                    hw_state.report_missing("tpms_radio")
                    backoff_end = time.time() + self.DEVICE_MISSING_BACKOFF_SECONDS
                    while time.time() < backoff_end and self._running:
                        time.sleep(1.0)
                    continue
                self._start_subprocess()
        except Exception as e:
            log.error("tpms_monitor_error", error=str(e))
```

**Service start/stop shape** (lift from `capture_sync.py:76–95`):

```python
# Source: src/shitbox/sync/capture_sync.py:76–95
def start(self) -> None:
    if self._running:
        return
    log.info("tpms_starting", ...)
    self._running = True
    self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
    self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
    self._reader_thread.start()
    self._monitor_thread.start()

def stop(self) -> None:
    self._running = False
    if self._process and self._process.poll() is None:
        self._process.terminate()
    for t in (self._reader_thread, self._monitor_thread):
        if t and t.is_alive():
            t.join(timeout=5.0)
```

**Per-wheel state + leak deque** (Pattern 8 from RESEARCH; uses `collections.deque`, GIL-atomic appends):

```python
# Source: 28-RESEARCH.md Pattern 8 (synthesised from project conventions)
self._wheels: Dict[str, WheelState] = {pos: WheelState() for pos in POSITIONS}
self._leak_windows: Dict[str, deque[tuple[float, float]]] = {
    pos: deque(maxlen=120) for pos in POSITIONS
}
```

**Frame handling — log shape** (project convention from CLAUDE.md):

```python
log.info(
    "tpms_frame_received",
    wheel="front-driver",
    pressure_psi=32.1,
    raw_kpa=89.7,
    corrected_kpa=219.8,
)
```

Never positional args — see CLAUDE.md "Code Conventions" line.

---

### `src/shitbox/utils/config.py` (config, MOD)

**Analog (simple dataclass):** `ParticulateConfig` at lines 157–164.

```python
# Source: src/shitbox/utils/config.py:157–164
@dataclass
class ParticulateConfig:
    """SEN0460 PM2.5 particulate sensor (I2C 0x19)."""

    enabled: bool = True
    i2c_bus: int = 1
    address: int = 0x19
    sample_rate_hz: float = 1.0
```

**Analog (list-of-dataclasses with `_dict_to_dataclass` plus an explicit list-build for the inner items):** the DS18B20 probes pattern at lines 519–525:

```python
# Source: src/shitbox/utils/config.py:519–525
# Explicitly convert DS18B20 probes list — _dict_to_dataclass does not handle
# lists of dataclasses, so we do it here.
temp_dict = data.get("sensors", {}).get("temperature", {})
temp_config = _dict_to_dataclass(TemperatureConfig, temp_dict)
probes_data = temp_dict.get("probes", []) if isinstance(temp_dict, dict) else []
temp_config.probes = [
    DS18B20ProbeConfig(**p) for p in (probes_data if isinstance(probes_data, list) else [])
]
```

**TPMS shape to add:** `TpmsSensorMapEntry` and `TpmsConfig` dataclasses (per RESEARCH Pattern at lines 891–922 of RESEARCH.md). Wire in `load_config` using the DS18B20-probes idiom for the `sensors:` list. Add `tpms` field on `Config` (next to `hardware`).

**Hardware manifest entry:** the `HardwareDeviceConfig` dataclass at lines 113–127 already supports `path: Optional[str]`. New bus value `usb_vid_pid` requires no schema change — only a new branch in `supervisor._run_probe`.

---

### `src/shitbox/storage/database.py` (model, MOD)

**Migration analog — copy verbatim shape:** `_migrate_to_v6` at lines 298–330 (creates two new tables, idempotent CREATE-IF-NOT-EXISTS, single commit, single info log):

```python
# Source: src/shitbox/storage/database.py:298–330
def _migrate_to_v6(self, conn: sqlite3.Connection) -> None:
    """Add notes and fuel_stops tables for Phase 12 logbook feature."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            body TEXT NOT NULL,
            event_id INTEGER,
            lat REAL,
            lng REAL,
            gps_stale BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    # ... fuel_stops table omitted ...
    conn.commit()
    log.info("migrated_to_v6", tables=["notes", "fuel_stops"])
```

**Wiring in `connect()`:** add `if current_version < 11: self._migrate_to_v11(conn)` after the v10 block at lines 212–213. Bump `SCHEMA_VERSION = 10` → `11` on line 16.

**Cursor analog:** `get_unsynced_readings` at lines 556–596 + `update_sync_cursor` at lines 598–619. New methods needed: `insert_tpms_reading`, `get_unsynced_tpms_readings`, `update_tpms_cursor` (the latter just delegates to the existing `update_sync_cursor("prometheus_tpms", last_id)` — the `sync_cursors` table is generic).

```python
# Source: src/shitbox/storage/database.py:572–596 (template for get_unsynced_tpms_readings)
conn = self._get_connection()
cursor = conn.execute(
    "SELECT last_synced_id FROM sync_cursors WHERE cursor_name = ?",
    (cursor_name,),
)
row = cursor.fetchone()
last_id = row["last_synced_id"] if row else 0
query = "SELECT * FROM tpms_readings WHERE id > ? ORDER BY id LIMIT ?"
rows = conn.execute(query, (last_id, batch_size)).fetchall()
return [dict(r) for r in rows]   # raw dicts; no Reading model needed
```

**Insert pattern:** mirror `insert_reading` at lines 411–438 — acquire `self._write_lock`, single INSERT, return `cursor.lastrowid`.

---

### `src/shitbox/dashboard/sse.py` (controller, MOD)

**Direct model:** `_system_conditions_payload` at lines 110–151. Same shape: deterministic order (FD/FP/RD/RP), one row per slot, scalar-only fields.

```python
# Source: src/shitbox/dashboard/sse.py:110–151 (excerpt)
def _system_conditions_payload() -> List[Dict[str, Any]]:
    now = time.time()
    snap = alerts.snapshot()

    role_state: Dict[str, Dict[str, Any]] = {
        "undervoltage": {"state": "clear", "since_ms": None},
        ...
    }
    out: List[Dict[str, Any]] = []
    for role, label in _SYSTEM_CONDITION_LABELS.items():
        rs = role_state[role]
        out.append({
            "role": role,
            "label": label,
            "tier": "critical",
            "state": rs["state"],
            "since_ms": rs["since_ms"],
        })
    return out
```

**Graceful-degradation import** (lines 32–44): use the same try/except pattern when wiring in `tpms_service` so the dashboard still serves `/sse/slow` if the TPMS subsystem is absent during unit tests.

**Wiring into `/sse/slow`** (lines 254–276):

```python
# Source: src/shitbox/dashboard/sse.py:254–276 (modify the JSON payload block)
yield {
    "event": "slow",
    "data": json.dumps(
        {
            ...,
            "hardware": _hardware_payload(),
            "system_conditions": _system_conditions_payload(),
            "tpms": _tpms_payload(),     # NEW — slot in here
        },
        default=str,
    ),
}
```

**Snapshot wiring contract:** `_tpms_payload` reads from a module-level `tpms_service` that the engine sets at startup — same convention as `set_recent_events_provider` at lines 175–183.

---

### `src/shitbox/dashboard/static/index.html` (view, MOD)

**Direct model:** SYSTEM section at lines 412–422 — the `x-for` Alpine template with class-by-state and the `hw-row hw-row-lg` shape:

```html
<!-- Source: src/shitbox/dashboard/static/index.html:412–422 -->
<div class="hw-section-eyebrow">SYSTEM</div>
<template x-for="row in systemConditions" :key="row.role">
  <div class="hw-row hw-row-lg" :class="'sc-' + row.state + ' hw-tier-critical'">
    <span class="hw-glyph" x-text="scGlyph(row.state)"></span>
    <span class="hw-label" x-text="row.label"></span>
    <span class="badge" :class="'badge-' + row.tier" x-text="row.tier"></span>
    <span class="hw-state" x-text="scStateText(row.state)"></span>
    <span class="hw-since" x-text="sinceText(row.since_ms)"></span>
  </div>
</template>
```

**Insertion point:** between the SYSTEM block (closes at line 422) and the HARDWARE block (opens at line 424). Use `:key="row.position"` to avoid the `FD` short-label collision (RESEARCH Pitfall 4).

**Alpine state init** (lines 466–470):

```javascript
// Source: src/shitbox/dashboard/static/index.html:466–470 (extend dashboard() return)
hardware: [],
systemConditions: [],
tpms: [],   // NEW
```

**SSE merge** (near line 623):

```javascript
// Source: src/shitbox/dashboard/static/index.html:~623 (extend the /sse/slow handler)
this.systemConditions = d.system_conditions || [];
this.tpms = d.tpms || [];   // NEW
```

---

### `src/shitbox/health/alerts.py` (utility — REUSED AS-IS)

The helper is feature-complete for sustain + transition + recovery. New TPMS subtypes plug into it without a single line of change in `alerts.py`. The wiring lives in `sync/tpms.py` (inside `_handle_frame`).

**Wiring analog:** `health/thermal_monitor.py:322–340` — the canonical pair of `fire_alert` + `fire_recovery` calls:

```python
# Source: src/shitbox/health/thermal_monitor.py:322–340
def _undervoltage_side_effects() -> None:
    beep_under_voltage()
    speak_under_voltage()

alerts.fire_alert(
    "UNDERVOLTAGE",
    active,
    "UNDERVOLTAGE DETECTED",
    _undervoltage_side_effects,
    sustain_required=2,
)
alerts.fire_recovery(
    "UNDERVOLTAGE",
    active,
    "POWER RESTORED",
    speak_power_restored,
    sustain_required=2,
    recovery_subtype="UNDERVOLTAGE_CLEARED",
)
```

**Single-writer invariant:** alerts.py docstring lines 8–15 says each subtype must be written by one thread. With four wheels × two alert types we get eight subtypes — all written from the rtl_433 reader thread. Don't sprinkle TPMS alert calls into other threads.

---

### `src/shitbox/capture/speaker.py` (utility, MOD — three new helpers)

**Direct model:** `speak_power_restored` at lines 445–454:

```python
# Source: src/shitbox/capture/speaker.py:445–454
def speak_power_restored() -> None:
    """Announce that mains power has come back after an undervoltage event.

    Mirrors speak_thermal_recovered ("Much better, Michael. …") — terse,
    cheery, doesn't restate the fault."""
    if not _should_alert():
        return
    _enqueue("Power restored, Michael. We're back to steady.")
```

**Cache pattern:** `_CACHED_MESSAGES` dict at lines 47–77 is the source of truth — every key in this dict gets a pre-rendered WAV in `_warm_cache` (lines 158–187). The `init` boot path at lines 209–215 verifies all WAVs exist before skipping Piper load. Adding twelve TPMS keys here pre-renders them at install time.

**TPMS helper shape (follow `speak_power_restored` literally):**

```python
# Synthesised from src/shitbox/capture/speaker.py:445–454 + RESEARCH.md lines 988–1022
def speak_tpms_low(position: str) -> None:
    if not _should_alert():
        return
    key = f"tpms_low_{position.replace('-', '_')}"
    text = _CACHED_MESSAGES.get(key)
    if text:
        _enqueue(text)
```

Same shape for `speak_tpms_leak` and `speak_tpms_restored`. Twelve new keys in `_CACHED_MESSAGES` (4 wheels × 3 alert types).

---

### `src/shitbox/events/detector.py` + `src/shitbox/events/storage.py` (model, MOD)

**EventType analog:** existing enum at `events/detector.py:15–24`:

```python
# Source: src/shitbox/events/detector.py:15–24
class EventType(Enum):
    """Types of detectable events."""

    HARD_BRAKE = "hard_brake"
    BIG_CORNER = "big_corner"
    ROUGH_ROAD = "rough_road"
    HIGH_G = "high_g"
    MANUAL_CAPTURE = "manual_capture"
    BOOT = "boot"
    ROLLOVER = "rollover"  # Phase 22 (IMU-03)
```

**TPMS addition:** append `TPMS_LEAK = "tpms_leak"` after ROLLOVER. Follow the snake_case-string convention.

**`save_event` reuse:** the existing `events/storage.py:91–151` `save_event` API takes any `Event` object. TPMS_LEAK events have `samples=[]` — the existing `_write_csv` writes an empty file, which is harmless (the `events.json` and rsync paths don't care). RESEARCH Open Question 1 confirms this is the intended choice.

---

### `src/shitbox/events/engine.py` (service wiring, MOD)

**Flat-field block analog:** lines 218–222 for `capture_sync_*`:

```python
# Source: src/shitbox/events/engine.py:218–222
# Capture sync (rsync to NAS)
capture_sync_enabled: bool = False
capture_sync_remote_dest: str = ""
capture_sync_rsync_path: str = "/opt/bin/rsync"
capture_sync_interval_seconds: int = 300
```

**Mapping in `from_yaml_config` analog:** lines 369–372:

```python
# Source: src/shitbox/events/engine.py:369–372
capture_sync_enabled=config.sync.capture_sync.enabled,
capture_sync_remote_dest=config.sync.capture_sync.remote_dest,
capture_sync_rsync_path=config.sync.capture_sync.rsync_path,
capture_sync_interval_seconds=config.sync.capture_sync.interval_seconds,
```

**Service instantiation analog:** lines 603–622 for `CaptureSyncService` — service constructed behind a guard, given config + collaborators:

```python
# Source: src/shitbox/events/engine.py:603–622
self.capture_sync: Optional[CaptureSyncService] = None
if (
    config.capture_sync_enabled
    and config.uplink_enabled
    and config.capture_sync_remote_dest
):
    capture_sync_config = CaptureSyncConfig(
        enabled=True,
        remote_dest=config.capture_sync_remote_dest,
        ...
    )
    self.capture_sync = CaptureSyncService(
        capture_sync_config,
        self.connection,
        config.captures_dir,
        self.event_storage,
        self.timelapse_compiler,
    )
```

**TPMS guard:** `if config.tpms_enabled and tpms.detect_rtl_433_binary(): self.tpms = TPMSService(...)`. Falls through silently if `which rtl_433` returns nothing — matches the "graceful degradation" rule in CLAUDE.md.

**start/stop wiring:** add `self.tpms.start()` next to `self.capture_sync.start()` and matching stop in `stop()`. Both follow the same `Optional[…]` guard.

---

### `src/shitbox/sync/batch_sync.py` (service, MOD — TPMS branch)

**Cursor advance analog:** `_sync_batch` at lines 184–292:

```python
# Source: src/shitbox/sync/batch_sync.py:184–234 (success path)
readings = self.db.get_unsynced_readings(
    cursor_name=self._cursor_name,
    batch_size=self.config.batch_size,
)
if not readings:
    log.debug("batch_sync_no_data")
    return
first_id = readings[0].id
last_id = readings[-1].id
...
self._send_to_prometheus(readings)
self.db.update_sync_cursor(self._cursor_name, last_id)
```

**TPMS metric shape:** `_readings_to_metrics` at lines 384–550 defines the `(metric_name, labels_dict, value, timestamp_ms)` tuple. The `prometheus_write.encode_remote_write` encoder accepts arbitrary label dicts so wheel labels just slot in.

```python
# Source: synthesised from batch_sync.py:392–410 (label-shaped metric)
labels = {"car": "shitbox", "job": "shitbox-mqtt-exporter", "wheel": row["wheel"]}
metrics.append(
    ("shitbox_tpms_pressure_psi", labels, row["pressure_psi"], timestamp_ms)
)
metrics.append(
    ("shitbox_tpms_temperature_c", labels, row["temperature_c"], timestamp_ms)
)
```

**Recommended:** add a separate `_sync_tpms_batch()` method (mirrors `_sync_batch`) using cursor `prometheus_tpms`. Call it from the existing `_sync_loop` after `_sync_batch()`. Keeps the high-cardinality wheel-labelled metrics off the hot 25 Hz IMU cursor (RESEARCH Pattern 5 reasoning).

---

### `src/shitbox/hardware/probes.py` (utility, MOD — new `probe_usb_vid_pid`)

**Closest analog:** `probe_audio_label` at lines 53–58 — string-scan against an external info source (in this case `lsusb` output):

```python
# Source: src/shitbox/hardware/probes.py:53–58
def probe_audio_label(label: str) -> bool:
    """Return True if the given label appears in /proc/asound/cards."""
    try:
        return label in Path("/proc/asound/cards").read_text()
    except OSError:
        return False
```

**Shape to add** (RESEARCH Pattern 10 lines 702–725, simplified):

```python
def probe_usb_vid_pid(vid_pid: str) -> bool:
    """Return True if a USB device matching VVVV:PPPP is enumerated."""
    try:
        result = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=2,
        )
        return result.returncode == 0 and f"ID {vid_pid.lower()}" in result.stdout
    except FileNotFoundError:
        log.warning("lsusb_not_found", hint="apt install usbutils")
        return False
    except subprocess.TimeoutExpired:
        return False
```

Single-shot bool, no held resources — same contract as every other probe in this file.

---

### `src/shitbox/hardware/supervisor.py` (service, MOD — new dispatch branch)

**Direct model:** `_run_probe` at lines 86–105:

```python
# Source: src/shitbox/hardware/supervisor.py:86–105
def _run_probe(self, d: HardwareDeviceConfig, i2c_ok: bool) -> bool:
    """Dispatch a single-shot probe for the device's bus type."""
    if d.bus == "i2c-1":
        ...
    if d.bus == "usb":
        return hw_probes.probe_usb_path(d.path or "")
    if d.bus == "audio":
        return hw_probes.probe_audio_label(d.label or "")
    ...
```

**Add new branch:** `if d.bus == "usb_vid_pid": return hw_probes.probe_usb_vid_pid(d.path or "")`. Reuses the existing `path` field on `HardwareDeviceConfig` — no schema change, no new TPMS-specific code in supervisor.

---

### `config/config.yaml` (config, MOD)

**Hardware manifest analog:** existing `hardware.devices` block at lines 316–360. Add the new entry alongside the others, keeping the criticality grouping comments intact:

```yaml
# Source: config/config.yaml:340–344 (the GPS-USB entry as direct shape model)
- role: gps
  bus: usb
  path: /dev/gps0
  criticality: important
  description: "U-blox USB GPS via gpsd"
```

**TPMS hardware entry to add** (under `# ── best_effort ───`):

```yaml
- role: tpms_radio
  bus: usb_vid_pid
  path: "0bda:2838"
  criticality: best_effort
  description: "Nooelec NESDR Smart v5 (RTL2832U + R820T2)"
```

**Top-level `tpms:` block** — paste the YAML from RESEARCH.md lines 924–947 next to existing top-level keys (e.g. after `drivers:` at line 312–314, before `hardware:` at line 316).

---

### `scripts/install.sh` (install, MOD)

**Direct model:** apt-get line at 62. Simply append two packages:

```bash
# Source: scripts/install.sh:62 — modify in place
apt-get install -y python3-pip python3-venv python3-dev i2c-tools gpsd gpsd-clients alsa-utils fake-hwclock sox libsox-fmt-all rtl-433 librtlsdr-dev
```

**Optional (RESEARCH Pitfall 8):** add a `usb_max_current_enable=1` check pattern mirroring the `i2c_arm_baudrate` block at lines 28–34. Defer if scope creep — daemon survives without it, RTL-SDR will only enumerate flakily.

---

### `tests/test_tpms_parser.py` (NEW — unit, REQ 1/2/3)

**Closest analog:** `tests/test_alerts.py` (autouse-fixture + pure-function shape) but the module under test is a parser, so this is largely fresh code. Test signatures follow `test_alerts.py` style:

```python
# Source pattern: tests/test_alerts.py:25–42 (single-function unit)
def test_pressure_correction() -> None:
    """× 2.45 correction applied before kPa → PSI."""
    from shitbox.sync.tpms import _correct_pressure
    raw_kpa = 89.7
    psi = _correct_pressure(raw_kpa, factor=2.45)
    assert abs(psi - 31.87) < 0.1
```

Pure functions; no fixtures needed beyond pytest's defaults.

---

### `tests/test_tpms_database.py` (NEW — integration, REQ 4/5)

**Closest analog:** the `db` fixture in `conftest.py:21–33`, plus existing migration tests in `tests/test_database.py`.

```python
# Source: tests/conftest.py:21–33
@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "test.db"

@pytest.fixture
def db(tmp_db_path):
    database = Database(tmp_db_path)
    database.connect()
    yield database
    database.close()
```

Use the `db` fixture; assert `tpms_readings` table exists post-`connect()`; assert `SCHEMA_VERSION == 11`; insert four rows; query back; assert cursor advance with `update_sync_cursor("prometheus_tpms", id)`.

---

### `tests/test_tpms_alerts.py` (NEW — unit, REQ 7/9)

**Closest analog:** `tests/test_alerts.py:15–22` (autouse `clear_state`) + `tests/test_thermal_monitor.py` for `time.monotonic` clock-jump:

```python
# Source: tests/test_alerts.py:15–22
@pytest.fixture(autouse=True)
def _clear_alerts_state():
    from shitbox.health import alerts
    alerts.clear_state()
    yield
    alerts.clear_state()
```

**Time-jump pattern (lift from `test_ffmpeg_stall.py:124–128`):**

```python
# Source: tests/test_ffmpeg_stall.py:124–128
seen_at = vrb._last_segment_seen_monotonic
monkeypatch.setattr(
    "shitbox.capture.ring_buffer.time.monotonic",
    lambda: seen_at + VideoRingBuffer.STALL_TIMEOUT_SECONDS + 1,
)
```

For `test_stale_after_5min`, monkeypatch `shitbox.sync.tpms.time.monotonic` to jump 360s past the last frame `last_seen`.

**TTS-fired-or-not pattern:** `MagicMock` + `with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:` directly from `test_alerts.py:30, 50, 69`.

---

### `tests/test_tpms_leak.py` (NEW — unit + integration, REQ 8)

**Unit (deque) analog:** `test_alerts.py` shape — feed a sequence, assert one fire.

**Integration (TPMS_LEAK in events.json):** mirror `tests/test_events_storage_poster.py` for the save_event roundtrip — use `event_storage` fixture from `conftest.py:42–45`, call `save_event` with an Event whose `event_type=EventType.TPMS_LEAK`, assert json file appears.

---

### `tests/test_tpms_subprocess.py` (NEW — integration, REQ 1/10)

**Direct model:** `tests/test_ffmpeg_stall.py:1–160` — factory helper that constructs the unit under test without spawning a real subprocess, MagicMock for `_process`, `monkeypatch.setattr` for `time.monotonic`.

```python
# Source: tests/test_ffmpeg_stall.py:26–69
def _make_vrb(tmp_path: Path) -> VideoRingBuffer:
    """Build a VideoRingBuffer without starting ffmpeg or any threads."""
    vrb: VideoRingBuffer = VideoRingBuffer.__new__(VideoRingBuffer)
    vrb.buffer_dir = tmp_path / "buffer"
    ...
    vrb._process = None
    vrb._running = False
    return vrb
```

Use the same `__new__` + manual-attribute-set pattern for `_make_tpms_service(...)`. Inject a MagicMock `_process` whose `stdout.readline()` returns canned JSON lines and whose `poll()` returns `None` for the alive-path test, then `0` for the death/restart-path test.

**lsusb mock pattern:** lift from `tests/test_capture_title_card.py:354–365`:

```python
# Source: tests/test_capture_title_card.py:361
with mock.patch("shitbox.hardware.probes.subprocess.run", return_value=fake_result):
    assert probe_usb_vid_pid("0bda:2838") is True
```

---

### `tests/test_dashboard.py` (MOD — extend with TPMS payload tests)

**Direct model:** existing `_system_conditions_payload` tests at lines 427–499.

```python
# Source: tests/test_dashboard.py:427–447 (template for _tpms_payload tests)
def test_tpms_payload_four_wheels(monkeypatch):
    from shitbox.dashboard.sse import _tpms_payload
    monkeypatch.setattr("shitbox.dashboard.sse.tpms_service", None)
    rows = _tpms_payload()
    assert len(rows) == 4
    assert [r["position"] for r in rows] == [
        "front-driver", "front-passenger", "rear-driver", "rear-passenger",
    ]
    assert all(r["state"] == "no_data" for r in rows)
```

Mirror the "always emits all rows in deterministic order" assertion shape from line 439.

---

### `tests/conftest.py` (MOD — add fixtures)

**Direct model:** existing `db` and `event_storage` fixtures at lines 21–45.

```python
# Source: tests/conftest.py:42–45
@pytest.fixture
def event_storage(event_storage_dir):
    """Create an EventStorage instance with a temporary base directory."""
    return EventStorage(base_dir=str(event_storage_dir))
```

**Fixtures to add** (per RESEARCH lines 1119–1135):

```python
@pytest.fixture
def fake_rtl433_frames():
    """Yield canned JSON frames for the four wheel sensors."""
    return [
        '{"time":"2026-04-28T12:34:56Z","model":"Abarth-124Spider","type":"TPMS",'
        '"id":"550b57d9","flags":"9300","pressure_kPa":89.7,"temperature_C":22.5,'
        '"status":19,"mic":"CHECKSUM"}',
        # ... three more for the other wheels ...
    ]


@pytest.fixture
def fake_rtl433_subprocess(monkeypatch, fake_rtl433_frames):
    """Stub subprocess.Popen with a Popen-like that emits canned frames."""
    # Returns a MagicMock; stdout.readline() yields each frame in turn then "" on EOF;
    # stderr.fileno() points to an os.pipe() with no writer (returns "" on read).
    ...
```

---

## Shared Patterns

### Structlog keyword logging

**Source:** `CLAUDE.md` — Code Conventions; reinforced at every log site in `health/thermal_monitor.py`, `sync/batch_sync.py`, `capture/ring_buffer.py`.
**Apply to:** all new modules and every log call inside them.

```python
# Convention enforced repo-wide:
log.info("tpms_frame_received", wheel="front-driver", pressure_psi=32.1, raw_kpa=89.7)
# NOT log.info(f"tpms frame received from {wheel}: {pressure_psi} PSI")
```

### Graceful-degradation try/import

**Source:** `src/shitbox/dashboard/sse.py:32–44` and `src/shitbox/health/alerts.py:26–33`.
**Apply to:** `dashboard/sse.py` when importing the new TPMS service; the dashboard must still serve `/sse/slow` if TPMS is absent.

```python
# Source: src/shitbox/dashboard/sse.py:32–44
try:
    from shitbox.health import alerts
except ImportError:
    class _NoopAlertsSnapshot:
        @staticmethod
        def snapshot() -> Dict[str, Any]:
            return {}
    alerts = _NoopAlertsSnapshot()
```

### Service guard + start/stop

**Source:** `src/shitbox/events/engine.py:603–622`.
**Apply to:** every new service in `engine.py`. Construct behind an `if config.X_enabled and …:` guard, store as `Optional[XService]`, `start()` and `stop()` symmetrically, never raise on construction.

### Single-writer-per-alert-subtype invariant

**Source:** `src/shitbox/health/alerts.py:8–15` + `health/thermal_monitor.py:322–340`.
**Apply to:** TPMS alert wiring lives only in the rtl_433 reader thread inside `sync/tpms.py`. Don't sprinkle `fire_alert`/`fire_recovery` into the SSE thread or the batch_sync thread.

### Subprocess lifecycle (drain, restart, back off when device gone)

**Source:** `src/shitbox/capture/ring_buffer.py:740–1050`.
**Apply to:** `sync/tpms.py` only. Lift the stderr drain (827–846) and the monitor loop (926–1011) wholesale.

### Schema migration

**Source:** `src/shitbox/storage/database.py:298–330` (`_migrate_to_v6`).
**Apply to:** `_migrate_to_v11`. Always idempotent CREATE-IF-NOT-EXISTS, always single `commit()` at the end, always one `log.info("migrated_to_vN", tables=…)` line.

### Cursor-based Prometheus exposition

**Source:** `src/shitbox/sync/batch_sync.py:184–292` + `storage/database.py:556–619`.
**Apply to:** new `prometheus_tpms` cursor in `batch_sync.py`. Don't mix wheel labels into the existing 25 Hz IMU cursor.

### Hardware manifest dispatch

**Source:** `src/shitbox/hardware/supervisor.py:86–105`.
**Apply to:** new `usb_vid_pid` bus branch — one `if d.bus == "...": return hw_probes.probe_X(...)` line. The existing `HardwareDeviceConfig.path` field carries `0bda:2838` literally; no schema change.

### Speak helpers (TTS engine fall-through)

**Source:** `src/shitbox/capture/speaker.py:445–454` (`speak_power_restored`).
**Apply to:** `speak_tpms_low`, `speak_tpms_leak`, `speak_tpms_restored`. Always check `_should_alert()` first; always read text from `_CACHED_MESSAGES`; never enqueue raw text directly.

### UK/Aus spelling

**Source:** `CLAUDE.md` (project) and `~/.claude/CLAUDE.md` (global).
**Apply to:** every TPMS string — "tyre" not "tire" in config keys, log keys, dashboard labels, TTS messages, comments, test names.

---

## No Analog Found

None. Every file in the phase has a strong precedent. The single piece of genuinely novel code is the rtl_433 JSON parser (`_handle_frame` inside `sync/tpms.py`), and even that is shaped by repo conventions (structlog keyword logging, dataclass state, deque GIL-atomic appends).

---

## Metadata

**Analog search scope:**

- `src/shitbox/sync/` — services
- `src/shitbox/capture/` — ring_buffer (subprocess), speaker (TTS)
- `src/shitbox/storage/` — database migrations and cursors
- `src/shitbox/dashboard/` — sse.py + static/index.html
- `src/shitbox/events/` — engine wiring + EventType enum + EventStorage save path
- `src/shitbox/health/` — alerts.py + thermal_monitor.py wiring
- `src/shitbox/hardware/` — probes.py + supervisor.py
- `src/shitbox/utils/config.py` — dataclass conventions + load_config wiring
- `tests/` — fixture patterns (conftest, alerts, ffmpeg_stall, dashboard, capture_title_card)
- `config/config.yaml` — manifest shape
- `scripts/install.sh` — apt-get line

**Files scanned:** 18 source files, 6 test files, 1 yaml, 1 shell script.

**Pattern extraction date:** 2026-04-28.
