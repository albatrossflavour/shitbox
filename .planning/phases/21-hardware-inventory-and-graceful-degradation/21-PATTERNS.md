# Phase 21: Hardware Inventory and Graceful Degradation - Pattern Map

**Mapped:** 2026-04-21
**Files analysed:** 17 (4 new modules + 6 new test files + 7 edits)
**Analogs found:** 17 / 17
**Graph oriented via:** graphify-out/GRAPH_REPORT.md (communities 0, 1, 2, 10, 12, 17, 20, 23; god nodes `UnifiedEngine`, `BaseCollector`, `BatchSyncService`, `VideoRingBuffer`)

## File Classification

| New/Modified File | Kind | Role | Data Flow | Closest Analog | Match |
|-------------------|------|------|-----------|----------------|-------|
| `src/shitbox/hardware/__init__.py` | new | package init | n/a | `src/shitbox/dashboard/__init__.py` | exact |
| `src/shitbox/hardware/state.py` | new | shared state module | read-heavy / write-occasional | `src/shitbox/dashboard/gps_state.py` | exact |
| `src/shitbox/hardware/supervisor.py` | new | daemon service | tick-loop / event-driven | `src/shitbox/sync/batch_sync.py` + `src/shitbox/display/oled.py` | exact |
| `src/shitbox/hardware/probes.py` | new | utility functions | request-response | `src/shitbox/collectors/power.py` setup + `speaker._detect_usb_speaker` | role-match |
| `src/shitbox/utils/config.py` | edit | config dataclass + loader | transform | `DS18B20ProbeConfig` + `TemperatureConfig` (same file) | exact |
| `src/shitbox/collectors/base.py` | edit | abstract collector | template method | (self — add hook) | n/a |
| `src/shitbox/collectors/environment.py` | edit | collector | CRUD / request-response | (self — simplify retry) | n/a |
| `src/shitbox/events/sampler.py` | edit | high-rate reader | streaming | (self — observational hooks) | n/a |
| `src/shitbox/capture/ring_buffer.py` | edit | ffmpeg wrapper | streaming / health-monitored | (self — observational hooks) | n/a |
| `src/shitbox/display/oled.py` | edit | render service | tick-loop | (self — content change in `_render`) | n/a |
| `src/shitbox/dashboard/sse.py` | edit | SSE route | pub-sub | (self — extend `/sse/slow` payload) | n/a |
| `src/shitbox/dashboard/static/index.html` | edit | SPA view | pub-sub consumer | existing `/sse/slow` consumer in same file | n/a |
| `src/shitbox/capture/speaker.py` | edit | TTS module | event-driven | existing `speak_i2c_lockup` / `speak_service_recovered` | exact |
| `src/shitbox/events/engine.py` | edit | orchestrator | lifecycle | existing OLED + BatchSync wiring | exact |
| `tests/test_hardware_state.py` | new | unit test | pure | `tests/test_dashboard_snapshot.py` (if present) or any simple unit test | role-match |
| `tests/test_hardware_supervisor.py` | new | unit test | time-mocked service | `tests/test_batch_sync.py` | exact |
| `tests/test_hardware_manifest.py` | new | unit test | YAML round-trip | `tests/test_config.py` (existing DS18B20 round-trip) | exact |
| `tests/test_hardware_probes.py` | new | unit test | mocked I/O | `tests/test_speaker.py` (if present) or mocked smbus2 tests | role-match |
| `tests/test_oled_hardware_line.py` | new | unit test | render-to-buffer | existing OLED tests (mock PIL) | role-match |
| `tests/test_sse_hardware.py` | new | unit test | Starlette TestClient async-gen | `tests/test_dashboard.py` (existing SSE infinite-gen drive pattern, see STATE.md Plan 13-03) | exact |

---

## Pattern Assignments

### `src/shitbox/hardware/state.py` (new, shared state module)

**Analog:** `src/shitbox/dashboard/gps_state.py` (entire file, 32 lines)

**Imports + module docstring pattern** (gps_state.py lines 1-7):

```python
"""Last-known GPS position helper. Module-level state, GIL-atomic rebind."""
from __future__ import annotations

import time
from typing import Optional, Tuple

_last: Optional[Tuple[float, float, float]] = None  # (lat, lng, fixed_at_epoch)
```

**Thread-safety comment + rebind pattern** (gps_state.py lines 10-20):

```python
def update_last_known_position(lat: float, lng: float, fixed_at: Optional[float] = None) -> None:
    """Store the most recent valid GPS fix position.

    Safe to call from any thread — the module-level rebind is GIL-atomic.
    Silently ignores None lat/lng so callers can pass raw snapshot values
    without pre-checking.
    """
    global _last
    if lat is None or lng is None:
        return
    _last = (float(lat), float(lng), float(fixed_at if fixed_at is not None else time.time()))
```

**Getter + test helper pattern** (gps_state.py lines 23-31):

```python
def get_last_known_position() -> Optional[Tuple[float, float, float]]:
    """Return (lat, lng, fixed_at_epoch) or None if no position has ever been stored."""
    return _last


def clear_last_known_position() -> None:
    """Reset module state. Test helper only — do not call in production code."""
    global _last
    _last = None
```

**Apply to `state.py`:**

- Use module-level `_state: Dict[str, DeviceStatus] = {}` (single source of truth, GIL-atomic rebind per same rationale)
- Mirror the docstring register ("Safe to call from any thread — the module-level rebind is GIL-atomic")
- Provide public functions: `initialise()`, `report_present()`, `report_missing()`, `report_degraded()`, `snapshot()`
- Provide `clear_state()` as a test-only helper (mirror of `clear_last_known_position`)
- Do **not** use a Lock. Rebinding `_state = new_map` is atomic under CPython GIL; readers get a consistent snapshot by reading the name once into a local.
- `DeviceStatus` should be a `@dataclass(frozen=True, slots=True)` so readers cannot accidentally mutate.

---

### `src/shitbox/hardware/supervisor.py` (new, daemon service)

**Primary analog:** `src/shitbox/sync/batch_sync.py` lines 33-108 (lifecycle + tick loop)
**Secondary analog:** `src/shitbox/display/oled.py` lines 18-94 (TYPE_CHECKING engine ref, graceful-degradation init, render_loop)

**Class skeleton + __init__ pattern** (batch_sync.py lines 33-82):

```python
class BatchSyncService:
    """Sync historical data to Prometheus in batches.

    Uses cursor-based tracking to ensure no data is lost or duplicated.
    Only syncs when network is available.
    """

    MAX_TOO_OLD_RETRIES = 20     # class-level constants for tunables

    def __init__(
        self,
        config: PrometheusConfig,
        database: Database,
        connection_monitor: ConnectionMonitor,
        event_storage: Optional[EventStorage] = None,
    ):
        self.config = config
        self.db = database
        self.connection = connection_monitor
        self._event_storage = event_storage

        self._running = False
        self._thread: Optional[threading.Thread] = None
        # ... additional state ...
```

**start() / stop() lifecycle pattern** (batch_sync.py lines 83-102):

```python
def start(self) -> None:
    """Start batch sync service."""
    if self._running:
        return

    log.info(
        "starting_batch_sync",
        endpoint=self.config.remote_write_url,
        batch_size=self.config.batch_size,
    )

    self._running = True
    self._thread = threading.Thread(target=self._sync_loop, daemon=True)
    self._thread.start()

def stop(self) -> None:
    """Stop batch sync service."""
    self._running = False
    if self._thread and self._thread.is_alive():
        self._thread.join(timeout=5.0)
```

**Tick-loop pattern** (oled.py lines 86-93 — closer to what supervisor needs than batch_sync's longer cycle):

```python
def _display_loop(self) -> None:
    """Main render loop."""
    while self._running:
        try:
            self._render()
        except Exception as e:
            log.error("oled_render_error", error=str(e))
        time.sleep(self.config.update_interval_seconds)
```

**Hardware-library import guarded in start() (so missing libs don't crash engine)** (oled.py lines 35-65):

```python
def start(self) -> None:
    if self._running:
        return

    try:
        import adafruit_ssd1306
        import board
        import busio
        from PIL import Image, ImageDraw, ImageFont
        # ... init hardware ...
        log.info("oled_display_started", ...)
    except Exception as e:
        log.error("oled_display_init_failed", error=str(e))
        self._display = None
        return

    self._running = True
    self._thread = threading.Thread(target=self._display_loop, daemon=True)
    self._thread.start()
```

**Apply to `HardwareSupervisor`:**

- Class-level constants: `TICK_INTERVAL_SECONDS = 1.0`, `CRITICAL_RENAG_SECONDS = 30.0`, `BACKOFF_LADDER = [5.0, 15.0, 60.0, 300.0]`
- `__init__(self, manifest: HardwareManifestConfig, reprobe_callbacks: Dict[str, Callable[[], bool]])` — no module-level state on the supervisor itself; it owns `_last_nag: Dict[str, float]` only.
- `start()`:
  1. Call `hw_state.initialise({d.role: d.criticality for d in self.manifest.devices})`
  2. Call `self._probe_all()` — one-shot boot probe, populates PRESENT/MISSING in state
  3. Set `self._running = True`, spawn daemon thread named `"hw-supervisor"`
- `stop()` — copy batch_sync lines 98-102 verbatim (set `_running=False`, `join(timeout=2.0)`)
- `_tick_loop()` — copy the oled `_display_loop` shape exactly (try/except around `_tick()`, then `time.sleep(self.TICK_INTERVAL_SECONDS)`)
- `_tick()` — walk `hw_state.snapshot().items()`:
  - If `state == MISSING and now >= next_retry_at`: call `self.reprobe.get(role)()`; on True → `hw_state.report_present(role)` + `self._on_restored(st)`; on False → `hw_state.report_missing(role)` (bumps `consecutive_misses`).
  - If `state == MISSING and tier == "critical" and now - _last_nag.get(role, 0) >= CRITICAL_RENAG_SECONDS`: speak missing, update `_last_nag[role] = now`.
- Never let an exception escape `_tick()` — log and continue (matches oled pattern).

---

### `src/shitbox/hardware/probes.py` (new, utility functions)

**Analog 1 (I2C probe):** `src/shitbox/collectors/power.py` lines 56-74 (smbus2 setup pattern)

```python
# power.py lines 68-74 — the reference smbus2 usage
try:
    bus = smbus2.SMBus(self._i2c_bus)
    self._sensor = INA226(bus, address=self._address, shunt_ohms=self._shunt_ohms)
    log.info("ina226_sensor_init")
except Exception as e:
    log.warning("ina226_sensor_init_failed", error=str(e))
    self._sensor = None
```

**Analog 2 (USB device path probe):** `src/shitbox/capture/ring_buffer.py` line 881

```python
# ring_buffer.py line 881 — exactly this idiom
if not os.path.exists(self.device):
    log.warning(
        "video_device_missing",
        device=self.device,
        backoff_seconds=self.DEVICE_MISSING_BACKOFF_SECONDS,
    )
```

**Analog 3 (audio label probe):** `src/shitbox/capture/speaker.py` lines 95-113

```python
def _detect_usb_speaker() -> Optional[str]:
    """Parse /proc/asound/cards to find the Jieli UACDemo USB speaker."""
    try:
        cards = Path("/proc/asound/cards").read_text()
        for line in cards.splitlines():
            if "UACDemo" in line:
                card_num = line.strip().split()[0]
                return f"plughw:{card_num},0"
    except OSError:
        pass
    return None
```

**Apply to `probes.py`:**

- `probe_i2c(bus: int, address: int) -> bool` — wrap `with smbus2.SMBus(bus) as smb: smb.read_byte_data(address, 0x00)` in try/except OSError. Close the bus in the `with` (see RESEARCH.md Pitfall 5 — don't hold the bus handle open).
- `probe_usb_path(path: str) -> bool` — `return os.path.exists(path)` (straight reuse of ring_buffer.py:881 idiom).
- `probe_onewire(sensor_id: str) -> bool` — `return Path(f"/sys/bus/w1/devices/{sensor_id}/w1_slave").exists()`.
- `probe_audio_label(label: str) -> bool` — mirror `_detect_usb_speaker` lines 104-112: read `/proc/asound/cards`, `return label in text`; `except OSError: return False`.
- `probe_hdmi(connector: str) -> bool` — glob `/sys/class/drm/*{connector}/status`, check `status.read_text().strip() == "connected"`.
- `probe_gpio_pin(pin: int) -> bool` — `try: import RPi.GPIO; return True; except ImportError: return False` (matches existing `GPIO_AVAILABLE` flag in `button.py`).
- `probe_i2c_bus_is_bitbang(bus: int) -> bool` — read `/sys/class/i2c-adapter/i2c-{bus}/name` and assert it starts with `i2c-gpio`; log loud error otherwise (RESEARCH.md Pitfall 1).
- All probes must be single-shot, no state, no background threads. Logging via `log = get_logger(__name__)`.

---

### `src/shitbox/utils/config.py` (edit — add HardwareManifestConfig + HardwareDeviceConfig)

**Analog:** `DS18B20ProbeConfig` + `TemperatureConfig` + loader at lines 464-470 (same file)

**Dataclass pattern** (config.py lines 75-94):

```python
@dataclass
class DS18B20ProbeConfig:
    """Single DS18B20 probe config (role + 1-Wire sensor ID)."""

    role: str = ""
    sensor_id: str = ""


@dataclass
class TemperatureConfig:
    """DS18B20 1-Wire config (replaces MCP9808)."""

    enabled: bool = True
    sample_rate_hz: float = 1.0
    probes: List[DS18B20ProbeConfig] = field(default_factory=list)

    @property
    def sensor_ids(self) -> dict:
        """Return {role: sensor_id} dict for DS18B20Collector."""
        return {p.role: p.sensor_id for p in self.probes if p.role and p.sensor_id}
```

**Loader wiring — list-of-dataclass handling** (config.py lines 464-470):

```python
# Explicitly convert DS18B20 probes list — _dict_to_dataclass does not
# handle lists of dataclasses, so we do it here.
temp_dict = data.get("sensors", {}).get("temperature", {})
temp_config = _dict_to_dataclass(TemperatureConfig, temp_dict)
probes_data = temp_dict.get("probes", []) if isinstance(temp_dict, dict) else []
temp_config.probes = [
    DS18B20ProbeConfig(**p) for p in (probes_data if isinstance(probes_data, list) else [])
]
```

**Apply to `config.py`:**

- Add `HardwareDeviceConfig` dataclass next to `DS18B20ProbeConfig` (same shape: all fields default, `Optional[int]` / `Optional[str]` for bus-specific fields). Include `role`, `bus`, `criticality`, `description`, plus `address`, `path`, `sensor_id`, `pin`, `label`, `connector`.
- Add `HardwareManifestConfig` with `devices: List[HardwareDeviceConfig] = field(default_factory=list)` (mirror `TemperatureConfig.probes`).
- In `load_config()`, after the DS18B20 probes stanza, add the identical list-coercion block:

  ```python
  hw_dict = data.get("hardware", {})
  hw_config = HardwareManifestConfig()
  devices_data = hw_dict.get("devices", []) if isinstance(hw_dict, dict) else []
  hw_config.devices = [
      HardwareDeviceConfig(**d) for d in (devices_data if isinstance(devices_data, list) else [])
  ]
  ```

- Thread `hardware=hw_config` into the `Config(...)` return (lines 472-525) as a new top-level field.
- Add `hardware: HardwareManifestConfig = field(default_factory=HardwareManifestConfig)` to the `Config` dataclass.

---

### `src/shitbox/collectors/base.py` (edit — role hook)

**Analog:** `BaseCollector` itself (same file) — the `_run_loop` at lines 117-159 is the existing error-handling structure.

**Existing success/error handling we're hooking into** (base.py lines 121-151):

```python
while self._running:
    loop_start = time.monotonic()

    try:
        data = self.read()

        if data is not None:
            self._last_reading = data
            self._error_count = 0                           # <-- success hook here

            if self.callback:
                reading = self.to_reading(data)
                self.callback(reading)

    except Exception as e:
        self._error_count += 1                              # <-- failure hook here
        log.error(
            "collector_read_error",
            collector=self.name,
            error=str(e),
            error_count=self._error_count,
        )

        if self._error_count >= self._max_errors:           # <-- keep this safety valve
            log.error(
                "collector_max_errors_reached",
                collector=self.name,
                max_errors=self._max_errors,
            )
            self._running = False
            break
```

**Existing `start()` exception handling to respect** (base.py lines 85-97):

```python
def start(self) -> None:
    if self._running:
        log.warning("collector_already_running", collector=self.name)
        return

    log.info("starting_collector", collector=self.name, rate_hz=self.sample_rate_hz)

    try:
        self.setup()
    except Exception as e:
        log.error("collector_setup_failed", collector=self.name, error=str(e))
        raise                                     # <-- re-raises; engine catches
```

**Apply to `base.py`:**

- Add `role: Optional[str] = None` kwarg to `__init__` after `callback` (line 28). Store as `self.role = role`.
- Add two small helpers:

  ```python
  def _report_present(self) -> None:
      if self.role:
          from shitbox.hardware import state as hw_state  # local import avoids cycle
          hw_state.report_present(self.role)

  def _report_missing(self) -> None:
      if self.role:
          from shitbox.hardware import state as hw_state
          hw_state.report_missing(self.role)
  ```

- In `_run_loop` at line 129 (after `self._error_count = 0`): add `self._report_present()`.
- In `_run_loop` at line 136 (first line of the except block, before `log.error`): add `self._report_missing()`.
- In `start()` at line 96 (inside the setup except, before `raise`): add `self._report_missing()`.
- Do **not** change `_max_errors` behaviour. Keep the `raise` in `start()` — the engine's per-collector try/except (see `events/engine.py` lines 1917-1928) is what makes HW-05 work.

---

### `src/shitbox/collectors/environment.py` (edit — reduce internal retry)

**Existing 5x1s retry loop to simplify** (environment.py lines 38-80):

```python
def setup(self) -> None:
    """Initialise BME680 hardware.

    Retries up to _BME680_INIT_RETRIES times to handle the sensor not being
    ready milliseconds after daemon start (I2C bus busy, sensor power-on delay).
    """
    # ... import block ...

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, _BME680_INIT_RETRIES + 1):
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = Adafruit_BME680_I2C(self._i2c, address=self.config.address)
            log.info("environment_sensor_initialised", attempt=attempt)
            return
        except Exception as e:
            last_exc = e
            log.warning(
                "environment_sensor_init_retry",
                attempt=attempt,
                max_attempts=_BME680_INIT_RETRIES,
                error=str(e),
            )
            if attempt < _BME680_INIT_RETRIES:
                time.sleep(_BME680_INIT_RETRY_DELAY_S)

    log.error("environment_setup_error", error=str(last_exc))
    raise last_exc
```

**Apply to `environment.py`:**

- Delete the `for attempt in range(...)` loop and `time.sleep(_BME680_INIT_RETRY_DELAY_S)` sleep.
- Remove the `_BME680_INIT_RETRIES` and `_BME680_INIT_RETRY_DELAY_S` constants at lines 11-12.
- `setup()` body becomes a single attempt — init I2C + sensor, log `environment_sensor_initialised` on success, `environment_setup_error` + raise on failure.
- Pass `role="environment"` to `super().__init__()` in `__init__`.
- `BaseCollector.start()` already catches `setup()` exceptions and re-raises; the engine's per-collector try/except swallows that; the supervisor owns the retry cadence via its backoff ladder.

---

### `src/shitbox/events/sampler.py` (edit — observational hooks, no logic change)

**Existing reset ladder — do not alter** (sampler.py lines 172-214):

```python
try:
    if self._lsm6dsox is None:
        raise OSError("sensor is None — I2C reinit failed")
    sample = self._read_sample()
    self.ring_buffer.append(sample)
    self.samples_total += 1
    self._consecutive_failures = 0                                   # <-- HOOK: report_present

    if self.on_sample:
        self.on_sample(sample)

except OSError as e:
    log.error("sample_read_error", error=str(e))
    self._consecutive_failures += 1

    if self._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
        log.warning(
            "i2c_bus_lockup_detected",                               # <-- HOOK: report_degraded
            consecutive_failures=self._consecutive_failures,
            reset_attempt=self._reset_count + 1,
            max_resets=I2C_MAX_RESETS,
        )
        buzzer.beep_i2c_lockup()
        speaker.speak_i2c_lockup()

        # ... reset attempt ...

        if recovered:
            log.info("i2c_bus_recovery_successful", attempt=self._reset_count)
            # (PRESENT is reported on next successful sample — see Pitfall 2)
        elif self._reset_count >= I2C_MAX_RESETS:
            log.critical("i2c_max_resets_exceeded", reset_count=self._reset_count)  # <-- HOOK: report_missing
            self._force_reboot()
```

**Apply to `sampler.py`:**

- In `__init__`, add `self.role = "imu"`.
- Add `from shitbox.hardware import state as hw_state` import at top.
- At line 178 (after `self._consecutive_failures = 0`): add `hw_state.report_present(self.role)`.
  - **Critical per Pitfall 2:** this goes in the *successful read* branch, not in `_i2c_bus_reset` success. Setup success reports nothing; only a real sample flips state to PRESENT.
- At line 188 (inside `log.warning("i2c_bus_lockup_detected", ...)`): add `hw_state.report_degraded(self.role)`.
- At line 213 (inside `log.critical("i2c_max_resets_exceeded", ...)`, before `self._force_reboot()`): add `hw_state.report_missing(self.role)`.
- Do **not** remove `buzzer.beep_i2c_lockup()` or `speaker.speak_i2c_lockup()` — the during-recovery announcement stays with the sampler per Pitfall 6. The supervisor only speaks terminal transitions.

---

### `src/shitbox/capture/ring_buffer.py` (edit — observational hooks)

**Existing health_monitor points** (ring_buffer.py lines 872-909):

```python
if self._process is not None and self._process.poll() is not None:
    rc = self._process.returncode
    stderr = self._read_stderr()
    log.warning(
        "video_ring_buffer_ffmpeg_crashed",
        returncode=rc,
        stderr=stderr,
    )
    # If the device node is missing, back off instead of tight-looping
    if not os.path.exists(self.device):
        log.warning(
            "video_device_missing",                              # <-- HOOK: report_missing
            device=self.device,
            backoff_seconds=self.DEVICE_MISSING_BACKOFF_SECONDS,
        )
        # ... backoff ...
        continue
    self._start_ffmpeg()                                         # <-- HOOK: report_present after
    # ...

# Restart if ffmpeg is alive but has stopped writing segments
if self._process is not None and self._process.poll() is None:
    if self._check_stall():
        stderr = self._read_stderr()
        log.warning(
            "video_ring_buffer_ffmpeg_stalled",                  # <-- HOOK: report_degraded
            device=self.device,
            stall_timeout_seconds=self.STALL_TIMEOUT_SECONDS,
            stderr=stderr,
        )
        buzzer.beep_ffmpeg_stall()
        self._kill_current()
        self._reset_stall_state()
        self._start_ffmpeg()
```

**Apply to `ring_buffer.py`:**

- Accept a `role: str` kwarg in `__init__` (e.g. `"camera_front"` or `"camera_cabin"`); default to `"camera_front"`. Store as `self.role`.
- Add `from shitbox.hardware import state as hw_state` import at top.
- After `log.warning("video_device_missing", ...)` at line 883: add `hw_state.report_missing(self.role)`.
- After `log.warning("video_ring_buffer_ffmpeg_stalled", ...)` at line 899: add `hw_state.report_degraded(self.role)`.
- In `_start_ffmpeg` (around the `log.info("ffmpeg_started", ...)` call — single grep for it — after the process is confirmed running with `self._process.poll() is None`): add `hw_state.report_present(self.role)`.
- Engine wiring: when instantiating the two `VideoRingBuffer`s in `UnifiedEngine` pass `role="camera_front"` (primary) and `role="camera_cabin"` (PIP).

---

### `src/shitbox/display/oled.py` (edit — hardware rollup line)

**Existing render at lines 108-161** (the full `_render`): line 3 at y=32 is currently `IMU | ENV`. The phase replaces that line.

**Apply to `oled.py`:**

- Import `from shitbox.hardware import state as hw_state` at top.
- Replace the block at lines 145-149 with the hardware rollup:

  ```python
  # Line 3: Hardware rollup — critical tokens inverted when missing, best_effort rolled up
  snap = hw_state.snapshot()

  def _is_present(role: str) -> bool:
      st = snap.get(role)
      return st is not None and st.state == hw_state.DeviceState.PRESENT

  x = 0
  for role, glyph in (("imu", "IMU"), ("camera_front", "CAM"), ("power", "PWR")):
      self._draw_text(x, 32, glyph, inverted=not _is_present(role))
      x += len(glyph) * 8 + 8

  be_roles = ("environment", "magnetometer", "light")
  be_present = sum(1 for r in be_roles if _is_present(r))
  self._draw_text(96, 32, f"ENV:{be_present}/{len(be_roles)}")
  ```

- Use the existing `self._draw_text(x, y, text, inverted=...)` helper exactly as shown in lines 95-106 — inverted=True renders white bg / black text, which is how GPS:NO FIX and IMU-down already signal error state.

---

### `src/shitbox/dashboard/sse.py` (edit — hardware field on /sse/slow)

**Existing `/sse/slow` payload shape** (sse.py lines 124-157):

```python
@router.get("/sse/slow")
async def sse_slow(request: Request) -> Response:
    _check_capacity()

    async def gen() -> AsyncIterator[Dict[str, Any]]:
        try:
            while True:
                snap = read_snapshot()
                yield {
                    "event": "slow",
                    "data": json.dumps(
                        {
                            "ts": snap["ts"],
                            "lat": snap["lat"],
                            "lng": snap["lng"],
                            "fix_mode": snap["gps_fix_mode"],
                            "sats": snap["gps_sat_count"],
                            "hdop": snap["gps_hdop"],
                            "imu_temp": snap["imu_temp_c"],
                            "soc_temp": snap["soc_temp_c"],
                            "sync_connected": snap["sync_connected"],
                            "sync_backlog": snap["sync_backlog"],
                            "event_count": snap["event_count_today"],
                            "active_driver": snap.get("active_driver"),
                            "recording_active": snap.get("recording_active", False),
                        },
                        default=str,
                    ),
                }
                await asyncio.sleep(1.0 / SLOW_HZ)
        finally:
            _release_slot()

    return EventSourceResponse(gen())
```

**Apply to `sse.py`:**

- Add `from shitbox.hardware import state as hw_state` import at top.
- Add `import time` if not already present.
- Inside the inline dict literal (after `recording_active`), add:

  ```python
  "hardware": [
      {
          "role": st.role,
          "tier": st.tier,
          "state": st.state.value,
          "last_seen": st.last_seen,
          "since_ms": int((time.time() - st.last_seen) * 1000) if st.last_seen else None,
          "consecutive_misses": st.consecutive_misses,
      }
      for st in hw_state.snapshot().values()
  ],
  ```

- Do **not** add a new SSE route and do **not** use `push_event` — hardware state is slow-changing context, not a discrete event stream (see Assumption A10).

---

### `src/shitbox/dashboard/static/index.html` (edit — hardware panel)

**Analog:** the existing kiosk layout in the same file (follow its theme + Alpine.js conventions — graph community 6).

**Apply to `index.html`:**

- Inspect the existing `/sse/slow` consumer — the Alpine component already reads the slow payload. Extend its data model with `hardware: []` initialised empty.
- Add a new read-only panel below the existing telemetry cards. Use the existing dark theme tokens (`#0d1117` bg, `#161b22` card, `#21262d` border — per CLAUDE.md website conventions).
- Badge colours per tier:
  - `critical` MISSING → red (`#f85149`)
  - `important` MISSING → amber (`#d29922`)
  - `best_effort` MISSING → grey (`#6e7681`)
  - any PRESENT → green (`#238636`)
  - `DEGRADED` → amber regardless of tier
- Columns: role, tier, state, last seen (humanised — "3s ago", "2m ago", or "never").
- Kiosk-only surface — no link to website (D-11).

---

### `src/shitbox/capture/speaker.py` (edit — hardware speak functions)

**Analog:** existing `speak_i2c_lockup` / `speak_service_recovered` / `_CACHED_MESSAGES` pattern.

**Existing `_CACHED_MESSAGES` dict to extend** (speaker.py lines 47-66):

```python
_CACHED_MESSAGES: dict[str, str] = {
    "system_ready": "Good day, Michael. All systems are operational.",
    # ... 17 more entries ...
    "i2c_lockup": "Michael, I've lost the sensor bus. I can't see what's happening out there.",
    "ffmpeg_stall": "Michael, the recording has stalled. I'm working on it.",
    # ...
}
```

**Existing speak function pattern** (speaker.py line 444):

```python
def speak_service_recovered() -> None:
    # boot-grace check, then _enqueue(_CACHED_MESSAGES["service_recovered"])
```

**Apply to `speaker.py`:**

- Extend `_CACHED_MESSAGES` with the 10 new hardware keys from RESEARCH.md Code Examples (hw_imu_missing, hw_imu_restored, hw_camera_front_missing, hw_camera_front_restored, hw_power_missing, hw_power_restored, hw_gps_missing, hw_gps_restored, hw_env_missing, hw_env_restored). Keep the "Michael, ..." register.
- Add two new functions near the other `speak_*`:

  ```python
  def speak_hardware_missing(role: str, tier: str) -> None:
      """Announce a device going MISSING. best_effort is log-only unless role == 'environment'."""
      if not _should_alert():
          return
      if tier == "best_effort" and role != "environment":
          return
      key = f"hw_{role}_missing"
      text = _CACHED_MESSAGES.get(key, f"{role} offline, Michael.")
      _enqueue(text)

  def speak_hardware_restored(role: str, tier: str) -> None:
      if not _should_alert():
          return
      if tier == "best_effort" and role != "environment":
          return
      key = f"hw_{role}_restored"
      text = _CACHED_MESSAGES.get(key, f"{role} restored, Michael.")
      _enqueue(text)
  ```

- New keys auto-warm-cache at `init()` via the existing `_warm_cache()` loop (speaker.py lines 147-176). No extra plumbing needed.

---

### `src/shitbox/events/engine.py` (edit — wiring)

**Existing service-start pattern — per-collector try/except at lines 1917-1928** (this is the HW-05 precedent):

```python
for collector in (
    self._ds18b20_collector,
    self._light_collector,
    self._particulate_collector,
    self._ina226_collector,
    self._imu_heading_collector,
):
    if collector is not None:
        try:
            collector.start()
        except Exception as e:
            log.error("v2_collector_start_failed", collector=collector.name, error=str(e))
```

**Existing OLED wiring pattern** (engine.py lines 595-603, 1901-1903):

```python
self.oled_display: Optional[OLEDDisplayService] = None
# ... later ...
self.oled_display = OLEDDisplayService(oled_config, self)
# ... in start() ...
if self.oled_display:
    self.oled_display.start()
```

**Apply to `engine.py`:**

- Imports: add `from shitbox.hardware.supervisor import HardwareSupervisor` and `from shitbox.hardware import probes as hw_probes`.
- In `UnifiedEngine.__init__`:
  - Store `self.hardware_manifest = config.hardware` (if the phase decides to put it on EngineConfig, otherwise pull directly from the loaded yaml at wire time).
  - Build the `reprobe_callbacks` dict. For each device role in the manifest, return a closure that calls the appropriate probe:

    ```python
    reprobe_callbacks = {
        d.role: (lambda d=d: _reprobe_device(d))
        for d in self.hardware_manifest.devices
    }
    ```

    where `_reprobe_device(d)` dispatches on `d.bus` into `hw_probes.probe_i2c` / `probe_usb_path` / `probe_onewire` / `probe_audio_label` / `probe_hdmi` / `probe_gpio_pin`.
  - Instantiate: `self.hardware_supervisor = HardwareSupervisor(self.hardware_manifest, reprobe_callbacks)`.
- In `UnifiedEngine.start()` **early** (before sampler / video / collectors so their hooks find a populated state table), call:

  ```python
  if self.hardware_supervisor:
      self.hardware_supervisor.start()
  ```

- In `UnifiedEngine.stop()`, call `self.hardware_supervisor.stop()` alongside the other services.
- Wrap the existing sampler/video/collector starts in the same pattern as lines 1917-1928 — reuse the per-service try/except so a missing critical device cannot prevent engine boot (HW-05). Consider extracting a `_start_service_graceful(name, svc)` helper.
- Pass `role="camera_front"` / `role="camera_cabin"` kwargs when constructing `VideoRingBuffer` at lines 608-615 (wherever the primary and PIP are built).
- Pass `role=...` to each collector constructor (`environment`, `power`, `light`, `magnetometer`, `temperature` per-probe) — collector roles match manifest roles.
- If GPS tracks presence via `_gps_available`, add `hw_state.report_present("gps")` / `report_missing("gps")` at the gpsd connect/disconnect points (Open Question 4 — derive `_gps_available` from hardware_state in a later pass if needed).

---

### Test files

**Pattern for time-mocked service tests (`test_hardware_supervisor.py`):** mirror `tests/test_batch_sync.py` — mock `time.monotonic`, construct service with mocked config + callbacks dict, call `_tick()` directly (don't run the thread), assert state transitions.

**Pattern for YAML round-trip (`test_hardware_manifest.py`):** mirror existing `tests/test_config.py` DS18B20 round-trip — build a YAML string with a `hardware:` block, pass through `load_config()`, assert the dataclass shape.

**Pattern for probes (`test_hardware_probes.py`):** mock `smbus2.SMBus`, `pathlib.Path.exists`, `Path.read_text` via `unittest.mock.patch` and `tmp_path`. Mirror how `tests/test_speaker.py` mocks `_detect_usb_speaker` if that file exists; otherwise use standard `patch("shitbox.hardware.probes.smbus2")` pattern (matches `patch("shitbox.collectors.power.smbus2")` per the comment in power.py line 16).

**Pattern for SSE (`test_sse_hardware.py`):** reuse the Starlette TestClient async-generator drive pattern already established in the dashboard tests (see STATE.md Plan 13-03 note). Hit `/sse/slow`, parse one `slow` payload, assert `hardware` field is a list with the expected roles.

**Pattern for OLED render (`test_oled_hardware_line.py`):** mock the Adafruit SSD1306 display via `unittest.mock.MagicMock`, drive `_render()` with a canned `hw_state.snapshot()`, assert `_draw_text` calls for the expected glyphs with the expected `inverted=` values.

**Pattern for state (`test_hardware_state.py`):** straight unit tests on the module functions — `initialise`, `report_*`, `snapshot`, `clear_state`. Use a fixture in `tests/conftest.py` that calls `clear_state()` before each test.

---

## Shared Patterns

### 1. Structlog keyword-arg logging

**Source:** `src/shitbox/utils/logging.py` + every shipping module.
**Apply to:** All new hardware modules.

```python
from shitbox.utils.logging import get_logger
log = get_logger(__name__)

# Examples from shipped code:
log.info("hw_supervisor_started", devices=len(self.manifest.devices))
log.info("hw_restored", role=st.role, tier=st.tier)
log.warning("hw_reprobe_error", role=role, error=str(e))
log.critical("hw_manifest_bus_check_failed", bus=1, expected="i2c-gpio", got=name)
```

Always keyword args, never f-strings. Event name in snake_case.

### 2. Daemon thread lifecycle

**Source:** `src/shitbox/sync/batch_sync.py` lines 83-102 and `src/shitbox/display/oled.py` lines 35-84.
**Apply to:** `HardwareSupervisor`.

```python
self._running = False
self._thread: Optional[threading.Thread] = None

def start(self) -> None:
    if self._running:
        return
    self._running = True
    self._thread = threading.Thread(target=self._loop, daemon=True, name="hw-supervisor")
    self._thread.start()

def stop(self) -> None:
    self._running = False
    if self._thread and self._thread.is_alive():
        self._thread.join(timeout=2.0)
```

### 3. Hardware-library import inside start() (graceful degradation)

**Source:** `src/shitbox/display/oled.py` lines 40-65, mirrored in `src/shitbox/capture/speaker.py` init.
**Apply to:** `HardwareSupervisor._probe_all` (wrap smbus2 usage in try/except; the probe module itself uses try/except OSError per call).

### 4. Per-service try/except around start (HW-05 graceful boot)

**Source:** `src/shitbox/events/engine.py` lines 1917-1928.
**Apply to:** Any new collector instantiation and the existing sampler/video_ring_buffer/button starts. Factor into `_start_service_graceful(name, svc)` helper.

### 5. Module-level singleton state (GIL-atomic rebind)

**Source:** `src/shitbox/dashboard/gps_state.py`.
**Apply to:** `src/shitbox/hardware/state.py` — same pattern, richer payload. No lock, rebind the `_state` name.

### 6. YAML list-of-dataclass loader

**Source:** `src/shitbox/utils/config.py` lines 464-470.
**Apply to:** `HardwareManifestConfig.devices` — identical `[Config(**d) for d in ...]` coercion.

### 7. `_CACHED_MESSAGES` + `_enqueue` TTS pattern

**Source:** `src/shitbox/capture/speaker.py` lines 47-66, 355-370 (enqueue), 380-470 (speak_* functions).
**Apply to:** `speak_hardware_missing` / `speak_hardware_restored` — just register keys in `_CACHED_MESSAGES`, call `_enqueue(text)`. Warm-cache happens automatically at `init()`.

---

## No Analog Found

None. Every new file has a direct analog in the shipped codebase. The phase is a composition exercise per RESEARCH.md §Summary.

---

## Metadata

**Analog search scope:** `src/shitbox/dashboard/`, `src/shitbox/sync/`, `src/shitbox/display/`, `src/shitbox/events/`, `src/shitbox/capture/`, `src/shitbox/collectors/`, `src/shitbox/utils/`, `tests/`.
**Files scanned (actually read):** 9 (`gps_state.py`, `batch_sync.py`, `oled.py`, `base.py`, `environment.py`, `sampler.py` [lines 160-323], `ring_buffer.py` [lines 760-920], `speaker.py` [lines 1-180, 180-360], `sse.py` [lines 1-160], `power.py` [lines 1-80], `config.py` [lines 70-170, 440-525], `engine.py` [lines 1900-1985 + targeted grep]).
**Graph communities traversed:** 0 (Engine Lifecycle), 1 (Collector Base), 2 (Service Init & Wiring), 10 (I2C Recovery & LSM6DSOX), 12 (Configuration Dataclasses), 17 (Hardware Architecture Overview), 20 (OLED Display Driver), 23 (Video Recorder).
**God nodes leveraged:** `UnifiedEngine` (orchestrator), `BaseCollector` (template method), `BatchSyncService` (tick-loop service), `VideoRingBuffer` (health-monitored streaming).
**Pattern extraction date:** 2026-04-21.
