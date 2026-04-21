---
phase: 21
plan: 05
type: execute
wave: 3
depends_on: [1, 2, 3]
files_modified:
  - src/shitbox/events/engine.py
  - tests/test_engine_boot.py
  - tests/hardware/test_engine_integration.py
autonomous: true
requirements: [HW-04, HW-05]
tags: [engine, boot, supervisor, graceful-degradation, hardware]
estimated_loc: 420

must_haves:
  truths:
    - "UnifiedEngine calls hw_state.init(config.hardware) at __init__ and constructs HardwareSupervisor(manifest, reprobe_callbacks) — no HardwareState instance, no hw_state= kwarg threading"
    - "Every collector and both VideoRingBuffer instances receive a role= kwarg matching their manifest device role (only new kwarg added by Plan 03)"
    - "Any single collector setup() failure during start() is caught by _start_service_graceful, logged, and MUST NOT prevent other collectors or services from starting"
    - "IMU sampler setup() failure at boot is logged but MUST NOT call _force_reboot() — reboot remains reachable only from the runtime i2c_max_resets ladder (pitfall 5)"
    - "Supervisor receives a reprobe_callbacks dict mapping each manifest role to its probe function; dispatch uses the canonical bus literals from Plan 01 (i2c-1, 1-wire, usb, gpio, hdmi, audio)"
    - "Supervisor is stopped during engine.stop() AFTER collectors so final MISSING transitions are still observed"
    - "The daemon boots with zero hardware present and logs 'unified_engine_started' (HW-05)"
  artifacts:
    - path: "src/shitbox/events/engine.py"
      provides: "hw_state.init() call, HardwareSupervisor instantiation, graceful collector start helper, role kwargs, reprobe dispatch"
      contains: "HardwareSupervisor"
    - path: "tests/test_engine_boot.py"
      provides: "HW-05 boot tests — all critical missing, IMU setup failure non-fatal"
      contains: "test_boot_with_all_critical_missing"
    - path: "tests/hardware/test_engine_integration.py"
      provides: "Canonical BME680 cold-boot integration test end-to-end (module-level hw_state + injected short backoff ladder)"
      contains: "test_bme680_cold_boot_then_recovers_via_supervisor"
  key_links:
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/hardware/state.py (module-level)"
      via: "hw_state.init(config.hardware) at __init__; no instance, module IS the singleton (D-04)"
      pattern: "hw_state\\.init\\("
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/hardware/supervisor.py"
      via: "self.supervisor = HardwareSupervisor(config.hardware, reprobe_callbacks)"
      pattern: "HardwareSupervisor\\("
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/hardware/probes.py"
      via: "reprobe_callbacks dict built from probes module per role, canonical bus literals"
      pattern: "probes\\.probe_(i2c|onewire|usb_path|audio_label|hdmi|gpio_pin)"
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/collectors/base.py"
      via: "collector constructors receive role= kwarg (Plan 03's single new kwarg)"
      pattern: "role=\""
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/capture/ring_buffer.py"
      via: "VideoRingBuffer(role='camera_front') and VideoRingBuffer(role='camera_cabin')"
      pattern: "VideoRingBuffer\\(.*role="
---

<objective>
Wire the HardwareSupervisor into UnifiedEngine, thread `role=` kwargs through every
collector and both VideoRingBuffer instances, and enforce HW-05 by refactoring the
per-collector try/except block into a single `_start_service_graceful` helper that
guarantees the daemon boots regardless of which hardware is missing or broken.

Critical correction from prior draft: `HardwareState` is **not a class** — Plan 01
ships it as a module (`src/shitbox/hardware/state.py`) mirroring
`src/shitbox/dashboard/gps_state.py` per CONTEXT.md D-04. The engine calls
`hw_state.init(config.hardware)` once at `__init__` (seeds the module registry from
the manifest) and every other read/write goes through the module's public functions.
There is no engine-owned state object and no `hw_state=` kwarg threaded through
collectors. Plan 03 added only one new kwarg to collectors and ring buffers: `role=`.
The collectors import `hw_state` themselves and call `report_present` /
`report_missing` / `report_degraded` directly (Plan 03).

Purpose: close HW-04 (supervisor lifecycle) and HW-05 (daemon never refuses to boot)
end-to-end. This is the final functional plan for phase 21 and the only plan that
modifies engine.py — all prior plans built the primitives that plug in here.

Output:
- `hw_state.init(config.hardware)` called once in `UnifiedEngine.__init__`
- `HardwareSupervisor(config.hardware, reprobe_callbacks)` instantiated, started,
  and stopped as a first-class engine service
- Every collector and both VideoRingBuffer instances receive a `role=` kwarg
  matching their manifest device role
- `_start_service_graceful(name, start_fn)` ensures a single failure cannot take
  the process down
- HW-05 acceptance tests in `tests/test_engine_boot.py`
- End-to-end BME680 integration test confirming cold-boot → probe FALSE → retry →
  probe TRUE → sample succeeds → PRESENT + `speak_hardware_restored` TTS
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-VALIDATION.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-01-manifest-state-probes-PLAN.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-02-supervisor-speaker-PLAN.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-03-collector-sampler-ringbuffer-hooks-PLAN.md

@src/shitbox/events/engine.py
@src/shitbox/hardware/state.py
@src/shitbox/hardware/supervisor.py
@src/shitbox/hardware/probes.py
@src/shitbox/capture/ring_buffer.py
@src/shitbox/collectors/base.py
@src/shitbox/dashboard/gps_state.py
@tests/test_ffmpeg_stall.py

<interfaces>
<!-- Contracts established by plans 01-03 that this plan consumes. COPY VERBATIM. -->

From `src/shitbox/hardware/state.py` (created in Plan 01) — **module, not a class**
(D-04 locked, analog: `src/shitbox/dashboard/gps_state.py`):

```python
# Module-level API. No HardwareState class. No instance. Rebind is GIL-atomic.
from shitbox.hardware import state as hw_state
from shitbox.hardware.state import DeviceState, DeviceStatus

hw_state.initialise(devices: Dict[str, str]) -> None     # {role: tier} — seeds MISSING
hw_state.report_present(role: str) -> Optional[DeviceState]
hw_state.report_missing(role: str) -> Optional[DeviceState]
hw_state.report_degraded(role: str) -> Optional[DeviceState]
hw_state.snapshot() -> Dict[str, DeviceStatus]
hw_state.clear_state() -> None                           # TEST-ONLY

class DeviceState(str, Enum):
    PRESENT = "present"
    DEGRADED = "degraded"
    MISSING = "missing"
```

From `src/shitbox/hardware/supervisor.py` (created in Plan 02) — **2 args**:

```python
class HardwareSupervisor:
    TICK_INTERVAL_SECONDS: float = 1.0
    CRITICAL_RENAG_SECONDS: float = 30.0

    def __init__(
        self,
        manifest: HardwareManifestConfig,
        reprobe_callbacks: Dict[str, Callable[[], bool]],
    ) -> None: ...
    def start(self) -> None: ...  # calls hw_state.initialise + _probe_all + spawns thread
    def stop(self) -> None: ...
```

The supervisor imports `hw_state` itself. The engine does NOT pass a state object.

From `src/shitbox/hardware/probes.py` (created in Plan 01) — **positional signatures**:

```python
def probe_i2c(bus: int, address: int) -> bool: ...       # bus FIRST, then address
def probe_onewire(sensor_id: str) -> bool: ...           # probe_onewire — NOT probe_1wire
def probe_usb_path(path: str) -> bool: ...
def probe_audio_label(label: str) -> bool: ...
def probe_hdmi(connector: str) -> bool: ...
def probe_gpio_pin(pin: int) -> bool: ...
def probe_i2c_bus_is_bitbang(bus: int) -> bool: ...      # takes bus arg
```

From `src/shitbox/utils/config.py` (Plan 01) — `HardwareDeviceConfig` fields.
**Only these fields exist — do not reference any others:**

```python
@dataclass
class HardwareDeviceConfig:
    role: str = ""
    bus: str = ""                    # canonical literals below
    criticality: str = "best_effort" # critical | important | best_effort
    description: str = ""
    address: Optional[int] = None    # i2c (e.g. 0x6a)
    path: Optional[str] = None       # usb (e.g. /dev/camera-front)
    sensor_id: Optional[str] = None  # 1-wire (e.g. 28-00000024263a)
    pin: Optional[int] = None        # gpio (e.g. 17)
    label: Optional[str] = None      # audio (e.g. UACDemo)
    connector: Optional[str] = None  # hdmi (e.g. HDMI-A-1)
```

**Canonical bus literals** (exact strings, from Plan 01 manifest):
`"i2c-1"`, `"1-wire"`, `"usb"`, `"gpio"`, `"hdmi"`, `"audio"`. Do NOT
use `"i2c"` or `"1wire"`.

From `src/shitbox/collectors/base.py` (modified in Plan 03) — **only `role=` added**:

```python
class BaseCollector(ABC, Generic[T]):
    def __init__(
        self,
        name: str,
        sample_rate_hz: float,
        callback: Optional[Callable[[Reading], None]] = None,
        role: Optional[str] = None,      # NEW — the only new kwarg Plan 03 added
    ): ...
```

No `hw_state=` kwarg exists. Collectors import `hw_state` themselves (Plan 03).

From `src/shitbox/capture/ring_buffer.py` (modified in Plan 03) — **only `role=` added**:

```python
class VideoRingBuffer:
    def __init__(
        self,
        device: str,
        # ... existing kwargs unchanged ...
        role: str = "camera_front",      # NEW — the only new kwarg Plan 03 added
    ): ...
```
</interfaces>

<ui_spec_reference>
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md
No direct UI changes in this plan — engine wiring is invisible to operators, but the
supervisor this plan starts is what makes OLED/SSE/TTS copy come to life in later work.
</ui_spec_reference>

<existing_engine_call_sites>
<!-- Known engine.py reference points. Line numbers approximate — read before editing. -->
- Line ~471: first per-collector try/except at start() (the block to extract into helper)
- Line ~613: self.video_ring_buffer = VideoRingBuffer(... )  — front camera
- Line ~1917-1928: per-collector try/except block (primary refactor target)
- Collector construction points: LSM6DSOX/MPU6050 sampler, GPS, BME680 environment,
  INA226 power, DS18B20 temperature (per-probe), light, air quality, button — all in __init__
- Engine has a second VideoRingBuffer for camera_cabin — thread role="camera_cabin" there
</existing_engine_call_sites>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Wire hw_state.init + HardwareSupervisor into UnifiedEngine and thread role= kwargs</name>
  <files>src/shitbox/events/engine.py</files>

  <read_first>
    <file>src/shitbox/events/engine.py</file>
    <why>Need exact line numbers for __init__, start(), stop(), the per-collector try/except block (~lines 1917-1928, ~471), and the two VideoRingBuffer construction sites. Line numbers in 21-PATTERNS.md are approximate.</why>
    <file>src/shitbox/hardware/state.py</file>
    <why>Confirm the module's public functions and their signatures (initialise, report_*, snapshot, clear_state). This module is the singleton — no class, no instance.</why>
    <file>src/shitbox/hardware/supervisor.py</file>
    <why>Confirm HardwareSupervisor.__init__ takes exactly (manifest, reprobe_callbacks) and imports hw_state itself.</why>
    <file>src/shitbox/hardware/probes.py</file>
    <why>Confirm probe function names (probe_onewire, probe_usb_path, probe_audio_label, probe_hdmi, probe_gpio_pin, probe_i2c with signature (bus, address)) before building the reprobe_callbacks dispatch dict.</why>
    <file>src/shitbox/dashboard/gps_state.py</file>
    <why>Canonical analog for module-level singleton state. Confirms the lifecycle shape: the engine imports and uses it, never instantiates it.</why>
    <file>.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md</file>
    <why>D-04 (module-level singleton is locked), D-05 (tier assignments), D-11 (no Prometheus / no website sync for hardware state).</why>
  </read_first>

  <behavior>
    - `UnifiedEngine.__init__` calls `hw_state.initialise({d.role: d.criticality for d in config.hardware.devices})` **before** any collector is constructed so collectors that call `report_*` during their own `__init__` find their role registered. Alternative: supervisor.start() also calls `hw_state.initialise` — the call is idempotent in practice only if `clear_state` ran first; to avoid ambiguity, the engine initialises once, and the supervisor's own `initialise` call becomes a no-op re-seed with the same map. The engine call ensures early registration.
    - `UnifiedEngine.__init__` constructs `self.supervisor = HardwareSupervisor(config.hardware, reprobe_callbacks)` — 2 positional args exactly. No HardwareState instance, no kwarg.
    - `reprobe_callbacks` is a `dict[str, Callable[[], bool]]` keyed by device role, built by inspecting `manifest.devices` and dispatching on `device.bus` using the canonical bus literals:
        - `bus == "i2c-1"` → `lambda a=device.address: probes.probe_i2c(1, a)`  (bus first, then address)
        - `bus == "1-wire"` → `lambda s=device.sensor_id: probes.probe_onewire(s)`
        - `bus == "usb"` → `lambda p=device.path: probes.probe_usb_path(p)`
        - `bus == "audio"` → `lambda l=device.label: probes.probe_audio_label(l)`
        - `bus == "hdmi"` → `lambda c=device.connector: probes.probe_hdmi(c)`
        - `bus == "gpio"` → `lambda pin=device.pin: probes.probe_gpio_pin(pin)`
        - unknown bus → `log.warning("unknown_bus_for_reprobe", role=dev.role, bus=bus)`, skip
    - Devices with `None` for their required bus-specific field (e.g. i2c-1 with `address=None`) MUST be skipped with a warning — don't install a callback that can crash the supervisor tick loop.
    - Every collector constructor gains **only** `role="<manifest_role>"`. No `hw_state=` kwarg — the `hw_state=` kwarg does NOT exist on BaseCollector or VideoRingBuffer (Plan 03 added only `role=`). Existing kwargs stay exactly as they are.
        - LSM6DSOX / IMU sampler path: `role="imu"`
        - GPSCollector: `role="gps"`
        - EnvironmentCollector (BME680): `role="environment"`
        - PowerCollector (INA226): `role="power"`
        - TemperatureCollector: `role="temp_exterior"` / `role="temp_engine_bay"` per per-probe instantiation
        - LightCollector (VEML7700): `role="light"`
        - MagnetometerCollector (LIS3MDL), if present in current engine: `role="magnetometer"`
        - OLED driver instance, if wrapped as a collector: `role="oled"`
        - ButtonHandler (GPIO 17): `role="button"`
        - Audio mic collector, if present: `role="audio_mic"`
        - HDMI display handler, if present: `role="display_hdmi"`
    - The manifest (Plan 01) declares 14 devices; not every manifest device maps to a collector — `camera_front` and `camera_cabin` map to VideoRingBuffer instances (below), and some best_effort devices (e.g. `display_hdmi`) may not have a collector at all. That's fine: those roles still get a reprobe callback and appear in the supervisor's state; they just don't have a `role=` threading point to wire.
    - Both VideoRingBuffer constructions pass `role=`: front → `role="camera_front"`, cabin → `role="camera_cabin"`. No other kwargs change.
    - `start()` sequence MUST be: `self.supervisor.start()` BEFORE any collector start — supervisor tick loop must be running so probe-TRUE events from collector setup() can be observed, and so the supervisor owns the first TTS cadence window. (Supervisor.start() calls `hw_state.initialise` again with the same map — harmless.)
    - `stop()` sequence MUST be: stop collectors first, then `self.supervisor.stop()` LAST — otherwise final MISSING transitions during teardown are swallowed.
    - A new private method `_start_service_graceful(name: str, start_fn: Callable[[], None]) -> bool` wraps every collector/service start:
        ```python
        def _start_service_graceful(self, name: str, start_fn: Callable[[], None]) -> bool:
            try:
                start_fn()
                log.info("service_started", service=name)
                return True
            except Exception as e:
                log.error("service_start_failed", service=name, error=str(e))
                return False
        ```
      Replace the existing per-collector try/except block (lines ~1917-1928 and the earlier ~471 site) with calls to this helper. HW-05 hinges on this: no single collector failure can propagate.
    - Sampler boot-time guard: the IMU sampler's setup() failure must NOT trigger `_force_reboot` (pitfall 5). The graceful helper catches the exception and returns False; the sampler.start() path is only entered if setup() succeeds. `_force_reboot` remains reachable only from the runtime i2c_max_resets ladder (sampler.py's existing code, unchanged by Plan 03).
  </behavior>

  <action>
    Modify `src/shitbox/events/engine.py` (this is the ONLY file this task touches):

    1. **Imports** at module top:
       ```python
       from typing import Callable
       from shitbox.hardware import state as hw_state
       from shitbox.hardware import probes
       from shitbox.hardware.supervisor import HardwareSupervisor
       from shitbox.utils.config import HardwareManifestConfig
       ```

    2. **UnifiedEngine.__init__** — after config is loaded and **before** any collector
       is constructed, initialise the module-level hw_state registry from the manifest
       and build the supervisor:
       ```python
       # Seed module-level hw_state so collectors' role reports during __init__ land
       # on a registered role (D-04: module IS the singleton, mirrors gps_state).
       hw_state.initialise({d.role: d.criticality for d in config.hardware.devices})

       reprobe_callbacks = self._build_reprobe_callbacks(config.hardware)
       self.supervisor = HardwareSupervisor(config.hardware, reprobe_callbacks)
       ```
       Note: there is NO `self.hw_state` attribute. The module IS the state.

    3. **New private method `_build_reprobe_callbacks(manifest)`**:
       ```python
       def _build_reprobe_callbacks(
           self, manifest: HardwareManifestConfig
       ) -> dict[str, Callable[[], bool]]:
           cbs: dict[str, Callable[[], bool]] = {}
           for dev in manifest.devices:
               bus = dev.bus
               if bus == "i2c-1":
                   if dev.address is None:
                       log.warning("reprobe_skip_missing_address", role=dev.role)
                       continue
                   addr = dev.address
                   cbs[dev.role] = lambda a=addr: probes.probe_i2c(1, a)
               elif bus == "1-wire":
                   if not dev.sensor_id:
                       log.warning("reprobe_skip_missing_sensor_id", role=dev.role)
                       continue
                   sid = dev.sensor_id
                   cbs[dev.role] = lambda s=sid: probes.probe_onewire(s)
               elif bus == "usb":
                   if not dev.path:
                       log.warning("reprobe_skip_missing_path", role=dev.role)
                       continue
                   path = dev.path
                   cbs[dev.role] = lambda p=path: probes.probe_usb_path(p)
               elif bus == "audio":
                   if not dev.label:
                       log.warning("reprobe_skip_missing_label", role=dev.role)
                       continue
                   lbl = dev.label
                   cbs[dev.role] = lambda l=lbl: probes.probe_audio_label(l)
               elif bus == "hdmi":
                   if not dev.connector:
                       log.warning("reprobe_skip_missing_connector", role=dev.role)
                       continue
                   conn = dev.connector
                   cbs[dev.role] = lambda c=conn: probes.probe_hdmi(c)
               elif bus == "gpio":
                   if dev.pin is None:
                       log.warning("reprobe_skip_missing_pin", role=dev.role)
                       continue
                   pin = dev.pin
                   cbs[dev.role] = lambda p=pin: probes.probe_gpio_pin(p)
               else:
                   log.warning("unknown_bus_for_reprobe", role=dev.role, bus=bus)
           return cbs
       ```
       Note the default-argument capture (`a=addr`, `s=sid`, etc.) — critical to avoid
       late-binding closure bugs in the loop.

    4. **Thread `role=` kwarg through every collector constructor.** Search for each
       collector class instantiation in `__init__` and append `role="<role>"`. Do NOT
       add any `hw_state=` kwarg — it does not exist on BaseCollector. Example:
       ```python
       # BEFORE
       self.environment_collector = EnvironmentCollector(
           name="environment",
           interval=config.sensors.environment.interval,
           database=self.database,
           config=config.sensors.environment,
       )
       # AFTER — ONLY role= added
       self.environment_collector = EnvironmentCollector(
           name="environment",
           interval=config.sensors.environment.interval,
           database=self.database,
           config=config.sensors.environment,
           role="environment",
       )
       ```
       Apply to: IMU sampler (role="imu"), GPSCollector (role="gps"),
       EnvironmentCollector (role="environment"), PowerCollector (role="power"),
       TemperatureCollector (role="temp_exterior" or "temp_engine_bay" per probe),
       LightCollector (role="light"), ButtonHandler (role="button"), and any other
       collector currently constructed in engine.py's __init__ that maps to a
       manifest role. For best_effort devices that have no collector (e.g. HDMI
       display if not wrapped), no action here — the supervisor probes them via the
       reprobe callback alone.

    5. **Thread `role=` into both VideoRingBuffer calls.** At the ~line 613 site
       (front) and the cabin site:
       ```python
       self.video_ring_buffer = VideoRingBuffer(
           config.capture.video,
           role="camera_front",
       )
       # ...later...
       self.video_ring_buffer_cabin = VideoRingBuffer(
           config.capture.video_cabin,
           role="camera_cabin",
       )
       ```
       Again: no `hw_state=` kwarg. Existing kwargs stay unchanged.

    6. **Add `_start_service_graceful` helper** (place near the top of the methods
       block after `__init__`):
       ```python
       def _start_service_graceful(
           self, name: str, start_fn: Callable[[], None]
       ) -> bool:
           try:
               start_fn()
               log.info("service_started", service=name)
               return True
           except Exception as e:
               log.error("service_start_failed", service=name, error=str(e))
               return False
       ```

    7. **Refactor `start()`.** At the top of `start()` (after any prerequisite
       like database.open() that must happen first), call:
       ```python
       self.supervisor.start()
       log.info("hardware_supervisor_started")
       ```
       THEN replace the existing per-collector try/except block (lines ~1917-1928
       and the ~471 site) with:
       ```python
       started: dict[str, bool] = {}
       started["imu"] = self._start_service_graceful(
           "imu_sampler", self.imu_sampler.start
       )
       started["environment"] = self._start_service_graceful(
           "environment_collector", self.environment_collector.start
       )
       started["gps"] = self._start_service_graceful(
           "gps_collector", self.gps_collector.start
       )
       started["power"] = self._start_service_graceful(
           "power_collector", self.power_collector.start
       )
       # ... etc for every collector and both video ring buffers
       started["camera_front"] = self._start_service_graceful(
           "video_ring_buffer_front", self.video_ring_buffer.start
       )
       started["camera_cabin"] = self._start_service_graceful(
           "video_ring_buffer_cabin", self.video_ring_buffer_cabin.start
       )
       log.info("unified_engine_started", collectors=started)
       ```
       Preserve existing ordering constraints (e.g. database must be ready before
       collectors start — that block stays as-is).

    8. **Refactor `stop()`.** Add at the very end of `stop()`, AFTER all collectors
       have been stopped:
       ```python
       try:
           self.supervisor.stop()
           log.info("hardware_supervisor_stopped")
       except Exception as e:
           log.error("hardware_supervisor_stop_failed", error=str(e))
       ```

    9. **Sampler boot-time reboot guard (pitfall 5).** Verify via grep that
       `_force_reboot` in `src/shitbox/events/sampler.py` has no call sites outside
       the runtime reset-count ladder (search existing code for `_force_reboot`
       to confirm it's only called after `i2c_max_resets_exceeded` at runtime). If
       setup() exposes a separate method that can fail before the sampler reaches
       the runtime state, `_start_service_graceful` wraps `sampler.start()` which
       internally does setup + thread-spawn — a setup exception bubbles to the helper,
       is caught, and the sampler never enters the runtime path where `_force_reboot`
       is reachable. No code change to sampler.py is required in this plan.
  </action>

  <verify>
    <automated>pytest tests/ -x -q --no-cov 2>&1 | tail -40 && ruff check src/shitbox/events/engine.py && mypy src/shitbox/events/engine.py</automated>
  </verify>

  <acceptance_criteria>
    - [ ] engine.py imports `hw_state` (module alias), `HardwareSupervisor`, `probes` module, and `HardwareManifestConfig`
    - [ ] `grep -q "hw_state.initialise({d.role: d.criticality" src/shitbox/events/engine.py` — single-line seed call in `__init__`
    - [ ] `grep -c "self.supervisor = HardwareSupervisor(" src/shitbox/events/engine.py` returns 1
    - [ ] `grep "HardwareSupervisor(config.hardware, reprobe_callbacks)" src/shitbox/events/engine.py` matches (2 positional args only — no `hw_state` arg between them)
    - [ ] `grep -c "self.hw_state" src/shitbox/events/engine.py` returns 0 (no instance attribute — module is the singleton)
    - [ ] `grep -c "hw_state=" src/shitbox/events/engine.py` returns 0 (no hw_state= kwarg on any collector or ring buffer)
    - [ ] `grep "_build_reprobe_callbacks" src/shitbox/events/engine.py` returns >=2 matches (definition + call site)
    - [ ] `grep -q 'bus == "i2c-1"' src/shitbox/events/engine.py` (canonical literal, not "i2c")
    - [ ] `grep -q 'bus == "1-wire"' src/shitbox/events/engine.py` (canonical literal, not "1wire")
    - [ ] `grep -q "probes.probe_i2c(1, a)" src/shitbox/events/engine.py` (bus first, address second)
    - [ ] `grep -q "probes.probe_onewire" src/shitbox/events/engine.py` (function named probe_onewire)
    - [ ] `grep -q "probes.probe_usb_path" src/shitbox/events/engine.py`
    - [ ] `grep -q "probes.probe_audio_label" src/shitbox/events/engine.py`
    - [ ] `grep -q "probes.probe_hdmi" src/shitbox/events/engine.py`
    - [ ] `grep -q "probes.probe_gpio_pin" src/shitbox/events/engine.py`
    - [ ] `! grep -q "dev.i2c_bus" src/shitbox/events/engine.py` (field does not exist)
    - [ ] `! grep -q "dev.device_id" src/shitbox/events/engine.py` (field does not exist)
    - [ ] `! grep -q "dev.device_path" src/shitbox/events/engine.py` (field does not exist)
    - [ ] `! grep -q "dev.card_name" src/shitbox/events/engine.py` (field does not exist)
    - [ ] `grep -c 'role="imu"' src/shitbox/events/engine.py` returns 1
    - [ ] `grep -c 'role="environment"' src/shitbox/events/engine.py` returns 1
    - [ ] `grep -c 'role="gps"' src/shitbox/events/engine.py` returns 1
    - [ ] `grep -c 'role="power"' src/shitbox/events/engine.py` returns 1
    - [ ] `grep -c 'role="camera_front"' src/shitbox/events/engine.py` returns 1
    - [ ] `grep -c 'role="camera_cabin"' src/shitbox/events/engine.py` returns 1
    - [ ] `grep "_start_service_graceful" src/shitbox/events/engine.py` returns >=6 call sites (one per major collector/service)
    - [ ] The block previously at lines ~1917-1928 now uses `_start_service_graceful` — no inline try/except for collector.start() remains
    - [ ] `self.supervisor.start()` is called BEFORE any collector.start in start()
    - [ ] `self.supervisor.stop()` is called LAST in stop() (after all collector stops)
    - [ ] Default-argument capture used in every loop lambda (`grep "lambda a=" / "lambda s=" / "lambda p=" / "lambda l=" / "lambda c=" / "lambda pin=" in _build_reprobe_callbacks`)
    - [ ] `ruff check src/shitbox/events/engine.py` passes with zero findings
    - [ ] `mypy src/shitbox/events/engine.py` passes with zero errors
    - [ ] All existing pytest tests still pass (no regressions)
  </acceptance_criteria>

  <done>
    engine.py calls `hw_state.initialise` once with the manifest tier map, constructs
    `HardwareSupervisor(config.hardware, reprobe_callbacks)` (2 args, no state instance),
    threads only `role=` through every collector and both VideoRingBuffers, wraps every
    service start in `_start_service_graceful`, starts the supervisor before collectors,
    and stops it last. All reprobe callbacks use the canonical bus literals and
    `HardwareDeviceConfig` fields that actually exist. Existing test suite stays green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: HW-05 boot tests — engine boots with all critical hardware missing</name>
  <files>tests/test_engine_boot.py</files>

  <read_first>
    <file>tests/test_i2c_recovery.py</file>
    <why>Existing pattern for mocking smbus2 + GPIO + subprocess to simulate hardware-absent environment. Follow the same mock-layering style.</why>
    <file>src/shitbox/events/engine.py</file>
    <why>Know the exact UnifiedEngine constructor signature and start()/stop() flow under test.</why>
    <file>src/shitbox/hardware/state.py</file>
    <why>Use hw_state.clear_state() in fixtures so module-level state doesn't leak between tests.</why>
    <file>.planning/phases/21-hardware-inventory-and-graceful-degradation/21-VALIDATION.md</file>
    <why>Confirms the two HW-05 test names and their intent.</why>
  </read_first>

  <behavior>
    Two tests prove HW-05.

    - **test_boot_with_all_critical_missing:** All hardware probes return False;
      every collector's `start()` raises a hardware exception. `UnifiedEngine.start()`
      MUST complete without raising, log `"unified_engine_started"` at INFO, and
      `HardwareSupervisor` must be running (alive thread). `stop()` MUST then
      complete cleanly without raising.

    - **test_imu_setup_failure_is_nonfatal:** Only the IMU sampler's `start()` raises
      (`IOError("imu init failed")`); all other hardware probes return True. `start()`
      MUST complete, MUST log `"service_start_failed"` with `service="imu_sampler"`,
      and MUST NOT call `_force_reboot`. Other collectors MUST be observed to have
      started (log `"service_started"` for at least one other service).
  </behavior>

  <action>
    Create `tests/test_engine_boot.py`:

    ```python
    """HW-05 boot resilience tests — daemon MUST boot regardless of hardware state.

    Proves that a fully-missing hardware set does not prevent the engine from starting,
    and that a single failing collector (the IMU) does not cascade into a reboot or
    take down other services.
    """
    from __future__ import annotations

    from unittest.mock import patch

    import pytest

    from shitbox.events.engine import UnifiedEngine
    from shitbox.hardware import state as hw_state
    from shitbox.utils.config import load_config


    @pytest.fixture(autouse=True)
    def _clear_hw_state():
        hw_state.clear_state()
        yield
        hw_state.clear_state()


    @pytest.fixture
    def minimal_config(tmp_path):
        """Load a config with every hardware role declared but nothing actually present."""
        cfg = load_config("config/config.yaml")
        # Redirect all writeable paths to tmp_path to avoid leaking state
        cfg.storage.database_path = str(tmp_path / "test.db")
        cfg.capture.video.buffer_dir = str(tmp_path / "video_buffer")
        cfg.capture.video.captures_dir = str(tmp_path / "captures")
        return cfg


    @pytest.fixture
    def all_hardware_missing():
        """Patch every probe to return False and every collector to raise on start."""
        patches = [
            patch("shitbox.hardware.probes.probe_i2c", return_value=False),
            patch("shitbox.hardware.probes.probe_onewire", return_value=False),
            patch("shitbox.hardware.probes.probe_usb_path", return_value=False),
            patch("shitbox.hardware.probes.probe_audio_label", return_value=False),
            patch("shitbox.hardware.probes.probe_hdmi", return_value=False),
            patch("shitbox.hardware.probes.probe_gpio_pin", return_value=False),
            patch("shitbox.hardware.probes.probe_i2c_bus_is_bitbang", return_value=True),
            # Collector .start() mocks that all raise
            patch("shitbox.events.sampler.HighRateSampler.start", side_effect=IOError("no imu")),
            patch(
                "shitbox.collectors.environment.EnvironmentCollector.start",
                side_effect=IOError("no bme680"),
            ),
            patch(
                "shitbox.collectors.gps.GPSCollector.start",
                side_effect=IOError("no gps"),
            ),
            patch(
                "shitbox.collectors.power.PowerCollector.start",
                side_effect=IOError("no ina226"),
            ),
            patch(
                "shitbox.capture.ring_buffer.VideoRingBuffer.start",
                side_effect=IOError("no camera"),
            ),
        ]
        for p in patches:
            p.start()
        yield
        for p in patches:
            p.stop()


    def test_boot_with_all_critical_missing(minimal_config, all_hardware_missing, caplog):
        """HW-05: engine.start() completes with every critical service failing."""
        engine = UnifiedEngine(minimal_config)

        # Must not raise
        engine.start()

        # Supervisor must be alive
        assert engine.supervisor is not None
        # Supervisor's internal thread attribute is part of the tested lifecycle contract
        assert engine.supervisor._thread is not None  # type: ignore[attr-defined]
        assert engine.supervisor._thread.is_alive()   # type: ignore[attr-defined]

        # unified_engine_started logged at INFO
        assert any(
            "unified_engine_started" in r.getMessage()
            for r in caplog.records
            if r.levelname == "INFO"
        ), "unified_engine_started must be logged"

        # At least one service_start_failed logged (we expect several)
        assert any(
            "service_start_failed" in r.getMessage() for r in caplog.records
        ), "expected service_start_failed for at least one collector"

        # Clean stop must not raise
        engine.stop()


    def test_imu_setup_failure_is_nonfatal(minimal_config, caplog):
        """HW-05 + pitfall 5: IMU setup failure must not call _force_reboot at boot."""
        with patch(
            "shitbox.events.sampler.HighRateSampler.start",
            side_effect=IOError("imu init failed"),
        ), patch(
            "shitbox.events.sampler.HighRateSampler._force_reboot"
        ) as mock_reboot, patch(
            "shitbox.hardware.probes.probe_i2c", return_value=True
        ), patch(
            "shitbox.hardware.probes.probe_gpio_pin", return_value=True
        ), patch(
            "shitbox.hardware.probes.probe_i2c_bus_is_bitbang", return_value=True
        ):
            engine = UnifiedEngine(minimal_config)
            engine.start()

            # IMU failure recorded
            assert any(
                "service_start_failed" in r.getMessage() and "imu" in r.getMessage()
                for r in caplog.records
            )

            # _force_reboot NEVER called during boot
            mock_reboot.assert_not_called()

            engine.stop()
    ```

    Notes:
    - The internal thread attribute `_thread` on `HardwareSupervisor` is inspected
      directly — acceptable for a lifecycle test. If the supervisor exposes an
      `is_running` property after Plan 02 lands, prefer that.
    - If the actual sampler class name differs from `HighRateSampler`, align the
      patch target with the class exported by `shitbox.events.sampler`.
    - If some collector classes have different start() paths, extend the patch list
      rather than shimming. Prefer real classes + mocked leaf methods over full
      class mocks.
  </action>

  <verify>
    <automated>pytest tests/test_engine_boot.py -v --no-cov</automated>
  </verify>

  <acceptance_criteria>
    - [ ] `tests/test_engine_boot.py` exists
    - [ ] `test_boot_with_all_critical_missing` passes
    - [ ] `test_imu_setup_failure_is_nonfatal` passes
    - [ ] No test marks or xfails — both assert real, required behaviour
    - [ ] Both tests use the real `UnifiedEngine` + `HardwareSupervisor` (only leaf hardware calls are mocked)
    - [ ] `test_imu_setup_failure_is_nonfatal` asserts `_force_reboot` was NOT called (pitfall 5)
    - [ ] Tests use `hw_state.clear_state()` autouse fixture so module-level state doesn't leak
    - [ ] `ruff check tests/test_engine_boot.py` passes
    - [ ] No sleeps longer than supervisor `TICK_INTERVAL_SECONDS` (1.0s) — tests must be fast
  </acceptance_criteria>

  <done>
    HW-05 has concrete test coverage. An engine with zero hardware boots cleanly, and
    an IMU-only failure doesn't reboot the Pi.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Canonical BME680 cold-boot integration test (module-level hw_state, fast backoff)</name>
  <files>tests/hardware/test_engine_integration.py</files>

  <read_first>
    <file>.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md</file>
    <why>Look up pitfall 2 (PRESENT only on successful sample), pitfall 6 (supervisor owns RESTORED TTS), pitfall 7 (no internal BME680 retry loop).</why>
    <file>tests/hardware/test_hardware_state.py</file>
    <why>Use the same module-level hw_state idiom established in Plan 01. clear_state autouse fixture lives in tests/hardware/conftest.py.</why>
    <file>src/shitbox/hardware/supervisor.py</file>
    <why>Confirm TICK_INTERVAL_SECONDS and the production backoff ladder [5.0, 15.0, 60.0, 300.0]; the test must either monkeypatch time.monotonic or swap in a fast ladder so the test doesn't sleep 7.5s.</why>
    <file>src/shitbox/hardware/state.py</file>
    <why>Confirm the module API surface: initialise, report_present, report_missing, snapshot, DeviceState enum. No class to instantiate.</why>
  </read_first>

  <behavior>
    End-to-end: boot with BME680 probe FALSE at T=0. Supervisor marks environment
    MISSING. `speak_hardware_missing("environment", "best_effort")` fires (best_effort
    tier is the ONE best-effort role that still speaks per D-05). After the first
    backoff tier elapses (monkeypatched fast), probe returns TRUE, supervisor retries,
    a successful `report_present("environment")` fires, supervisor observes PRESENT
    transition, `speak_hardware_restored("environment", "best_effort")` fires once.

    Key contract points this test defends:
    - Supervisor-owned re-adoption at the first backoff tier, not the sampler
    - PRESENT transition triggered only by successful sample (pitfall 2), not probe-TRUE alone
    - Single RESTORED TTS from supervisor, not duplicate from sampler (pitfall 6)
    - BME680 collector has NO internal 5×1s retry loop (pitfall 7 — enforced in Plan 03)

    **Why fast time?** Production backoff starts at 5s, so waiting real-time for
    re-adoption burns 5+ seconds per test. Use `monkeypatch` on `time.monotonic` (or
    inject a shorter ladder via the supervisor's module-level
    `_BACKOFF_LADDER_SECONDS` constant if Plan 01 made it monkeypatchable) so the
    test completes in <2s. The real-time backoff acceptance is a separate on-Pi
    smoke check in `must_haves.truths`, not in the pytest run.
  </behavior>

  <action>
    Create `tests/hardware/test_engine_integration.py`:

    ```python
    """Canonical BME680 cold-boot → recover scenario (Phase 21 integration).

    This is the end-to-end truth test for the supervisor + module-level hw_state +
    collector contract. If this passes, hardware graceful degradation is working.

    Time is monkeypatched so the test completes quickly — the real backoff ladder
    is validated by on-Pi smoke checks, not by burning 7+ seconds in CI.
    """
    from __future__ import annotations

    import time
    from unittest.mock import patch

    import pytest

    from shitbox.hardware import state as hw_state
    from shitbox.hardware.state import DeviceState
    from shitbox.hardware.supervisor import HardwareSupervisor
    from shitbox.utils.config import HardwareDeviceConfig, HardwareManifestConfig


    @pytest.fixture
    def manifest_bme680_only():
        """Minimal manifest with only the BME680 environment device."""
        return HardwareManifestConfig(
            devices=[
                HardwareDeviceConfig(
                    role="environment",
                    bus="i2c-1",
                    address=0x77,
                    criticality="best_effort",
                ),
            ]
        )


    def test_bme680_cold_boot_then_recovers_via_supervisor(
        manifest_bme680_only, monkeypatch
    ):
        """Cold boot BME680 absent → supervisor retries at first backoff tier → PRESENT + TTS.

        Timeline (virtual time — time.monotonic monkeypatched):
          T=0.0   supervisor.start() → probe False → MISSING, speak_hardware_missing
          T=5.1   probe True → supervisor retry callback runs → calls report_present
          T=5.1   supervisor observes PRESENT → speak_hardware_restored
        """
        # Shared clock we can advance manually
        clock = {"t": 0.0}
        monkeypatch.setattr(
            "shitbox.hardware.supervisor.time.monotonic", lambda: clock["t"]
        )
        monkeypatch.setattr(
            "shitbox.hardware.state.time.monotonic", lambda: clock["t"]
        )

        # Probe flips from False to True at virtual T+5s
        def probe_fn() -> bool:
            return clock["t"] >= 5.0

        reprobe_callbacks = {"environment": probe_fn}

        with patch(
            "shitbox.hardware.supervisor.speaker.speak_hardware_missing"
        ) as mock_missing, patch(
            "shitbox.hardware.supervisor.speaker.speak_hardware_restored"
        ) as mock_restored:
            supervisor = HardwareSupervisor(manifest_bme680_only, reprobe_callbacks)
            # Start seeds the state and runs _probe_all; probe still False here
            # (patch the probe dispatch inside supervisor's _probe_all to honour
            # our probe_fn by routing via reprobe_callbacks, OR monkeypatch
            # probe_i2c to follow clock the same way):
            monkeypatch.setattr(
                "shitbox.hardware.probes.probe_i2c",
                lambda bus, address: clock["t"] >= 5.0,
            )
            monkeypatch.setattr(
                "shitbox.hardware.probes.probe_i2c_bus_is_bitbang",
                lambda bus: True,
            )
            supervisor.start()

            # After start: state MISSING, missing TTS fired once
            snap = hw_state.snapshot()
            assert snap["environment"].state == DeviceState.MISSING
            mock_missing.assert_called_once_with("environment", "best_effort")

            # Advance virtual time past the first backoff tier (5s)
            clock["t"] = 5.1

            # Drive one supervisor tick manually (avoids waiting for real 1s tick)
            supervisor._tick()

            # State should now be PRESENT and restored TTS fired once
            snap = hw_state.snapshot()
            assert snap["environment"].state == DeviceState.PRESENT
            mock_restored.assert_called_once_with("environment", "best_effort")

            supervisor.stop()


    def test_bme680_supervisor_does_not_invoke_internal_retry_loop(
        manifest_bme680_only
    ):
        """Pitfall 7 guard: BME680 collector's legacy 5×1s retry must NOT run.

        If the supervisor is the single source of retry cadence, the collector's
        internal _BME680_INIT_RETRIES loop must be gone (deleted in Plan 03).
        """
        from shitbox.collectors import environment

        with open(environment.__file__) as f:
            source = f.read()
        assert "_BME680_INIT_RETRIES" not in source, (
            "pitfall 7: environment.py must not re-introduce internal retry loop"
        )
        assert "time.sleep" not in source, (
            "environment.py setup must be single-attempt; supervisor owns retry"
        )
    ```

    Notes:
    - `supervisor._tick()` is called directly after advancing the virtual clock.
      This avoids the real 1s tick interval and the 5s real-time backoff.
    - Patching `speaker.speak_hardware_missing` at
      `shitbox.hardware.supervisor.speaker.*` matches Plan 02's import shape
      (`from shitbox.capture import speaker` — attribute access on the module).
      If Plan 02 instead does `from shitbox.capture.speaker import speak_hardware_missing`
      at module top, patch at `shitbox.hardware.supervisor.speak_hardware_missing`.
    - The assertion `mock_missing.assert_called_once_with("environment", "best_effort")`
      uses **positional** args — this matches Plan 02's `_CACHED_MESSAGES` gating
      signature `speak_hardware_missing(role, tier)` (no keyword args).
    - `tests/hardware/conftest.py` (from Plan 01) autouse `_clear_hw_state` fixture
      runs for tests under this directory, so the module-level state is reset per test.

    Leave the "probe True but no sample" pitfall-2 guard test out of this plan — that
    pitfall is enforced by the sampler's hook wiring in Plan 03 (`_sample_loop`
    success branch is the ONLY place `report_present` fires), and is covered by
    `tests/test_i2c_recovery.py::test_successful_sample_reports_present` in Plan 03.
    Repeating it here would double-cover without adding signal.
  </action>

  <verify>
    <automated>pytest tests/hardware/test_engine_integration.py -v --no-cov</automated>
  </verify>

  <acceptance_criteria>
    - [ ] `tests/hardware/test_engine_integration.py` exists
    - [ ] `test_bme680_cold_boot_then_recovers_via_supervisor` passes
    - [ ] `test_bme680_supervisor_does_not_invoke_internal_retry_loop` passes
    - [ ] Canonical test uses `hw_state.snapshot()["environment"].state == DeviceState.MISSING` (module API) and `DeviceState.PRESENT` (enum comparison, not string)
    - [ ] `mock_missing.assert_called_once_with("environment", "best_effort")` — POSITIONAL args (matches Plan 02 signature)
    - [ ] `mock_restored.assert_called_once_with("environment", "best_effort")` — POSITIONAL args
    - [ ] Time is monkeypatched (supervisor and state modules both use the virtual clock) — no real `time.sleep(5)`+ in the test body
    - [ ] Pitfall 7 guard test proves environment.py has no `_BME680_INIT_RETRIES` and no `time.sleep`
    - [ ] Total test module runtime <2s
    - [ ] `ruff check tests/hardware/test_engine_integration.py` passes
  </acceptance_criteria>

  <done>
    The full Phase 21 contract is demonstrated by a single passing integration test:
    cold boot → supervised retry via first backoff tier → probe TRUE → report_present →
    PRESENT transition → restored TTS. Time is monkeypatched so the test runs in
    under 2s. Pitfall 7 has a dedicated static guard.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| engine → hardware | Probe functions issue smbus2/filesystem calls; engine consumes their boolean return values |
| engine → systemd | Process lifecycle; systemd restarts the daemon on crash but Phase 21 goal is to never crash on hardware absence |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-05-01 | Denial of Service | UnifiedEngine.start() | mitigate | `_start_service_graceful` wraps every collector.start() — a single raising collector cannot prevent boot. HW-05 test `test_boot_with_all_critical_missing` asserts this directly. |
| T-21-05-02 | Denial of Service | IMU sampler `_force_reboot` | mitigate | Sampler boot-time setup failure goes through `_start_service_graceful`, which catches and logs. `_force_reboot` remains reachable only from the runtime i2c_max_resets ladder (pitfall 5). `test_imu_setup_failure_is_nonfatal` asserts `_force_reboot.assert_not_called()`. |
| T-21-05-03 | Tampering | reprobe_callbacks dispatch | accept | Manifest is a local config file the operator controls. No external input crosses this boundary. Default-argument capture on every lambda prevents late-binding bugs that could inject the wrong address into a probe call. |
| T-21-05-04 | Information Disclosure | `log.info("unified_engine_started", collectors=started)` | accept | Log contains bool map of role → started; no secrets, no PII, no addresses. Local systemd journal only, not shipped off-device (D-11 — no Prometheus sync for hw state). |
| T-21-05-05 | Elevation of Privilege | HardwareSupervisor thread | accept | Thread runs as the shitbox service user, same privileges as existing collectors. No new syscall surface. |
| T-21-05-06 | Denial of Service | Malformed manifest device (missing address, bad bus) | mitigate | `_build_reprobe_callbacks` skips devices with `None` for their required bus-specific field and logs a warning. An unknown bus string logs a warning and is skipped. No crash, no KeyError in supervisor tick. |

Notes: ASVS L1 has no authentication/session controls in scope for this in-car
local-only daemon. The threats that apply are all availability-oriented, and the
two DoS threats are directly mitigated by the graceful helper and the sampler
reboot guard. T-21-05-06 is new to this revision — the old plan had fewer
bus-literal branches and missed the malformed-device path.
</threat_model>

<verification>
End-to-end checks after all three tasks:

1. **Full suite:** `pytest --no-cov -x` — all tests green, no regressions in existing suites
2. **Lint/types:** `ruff check src/` and `mypy src/` — zero findings
3. **No hw_state instance:** `grep -c "self.hw_state" src/shitbox/events/engine.py` returns 0
4. **No dead fields:** `! grep -q "i2c_bus\|device_id\|device_path\|card_name" src/shitbox/events/engine.py`
5. **Canonical bus literals:** `grep -q '"i2c-1"' src/shitbox/events/engine.py && grep -q '"1-wire"' src/shitbox/events/engine.py`
6. **Cold-boot smoke (on Pi, manual):** stop BME680 I2C line, restart shitbox-telemetry, verify systemd shows the service active, `journalctl` shows `unified_engine_started` followed by `service_start_failed` for environment, and `hardware_supervisor_started`
7. **Supervisor liveness (on Pi, manual):** `journalctl -u shitbox-telemetry -f` should show supervisor tick logs if debug logging is enabled
8. **BME680 hot-plug (on Pi, manual — real-time backoff acceptance):** with supervisor running and BME680 MISSING, reconnect the sensor cable. Within 5-300s (depending on which backoff tier), OLED ENV count should tick up, dashboard HARDWARE card should flip to PRESENT, TTS should say "Environment sensor back, Michael."
</verification>

<success_criteria>
- [ ] engine.py calls `hw_state.initialise(...)` once in `__init__` from the manifest tier map; no `self.hw_state` attribute exists
- [ ] `HardwareSupervisor(config.hardware, reprobe_callbacks)` — exactly 2 positional args
- [ ] Every collector and both VideoRingBuffers receive ONLY `role=` kwarg (no `hw_state=`)
- [ ] `_build_reprobe_callbacks` uses canonical bus literals (`i2c-1`, `1-wire`, `usb`, `audio`, `hdmi`, `gpio`) and correct probe signatures (`probe_i2c(bus, address)`, `probe_onewire(sensor_id)`, etc.)
- [ ] No references to non-existent `HardwareDeviceConfig` fields (`i2c_bus`, `device_id`, `device_path`, `card_name`)
- [ ] `_start_service_graceful` wraps every collector/service start — no single failure can abort boot
- [ ] HW-05 tests pass: all-critical-missing boot + IMU-failure-non-fatal
- [ ] Canonical BME680 cold-boot integration test passes in <2s with monkeypatched time
- [ ] Pitfall 7 guard test passes (no `_BME680_INIT_RETRIES`, no `time.sleep` in environment.py setup)
- [ ] `_force_reboot` is provably unreachable from boot-time setup failure (mock_reboot.assert_not_called)
- [ ] ruff + mypy clean on engine.py
- [ ] Full test suite remains green with no xfails added
</success_criteria>

<output>
After completion, create `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-05-SUMMARY.md` documenting:
- engine.py wiring changes and line-number deltas
- Confirmation that `hw_state` is used as a module (no instance) per D-04
- `HardwareSupervisor` construction signature (2 args) and why
- The `_start_service_graceful` helper and why it exists
- Supervisor lifecycle ordering (start before collectors, stop after)
- `_build_reprobe_callbacks` dispatch table — one lambda per role with default-arg capture, canonical bus literals, correct probe signatures
- HW-05 test coverage and the BME680 canonical scenario (with monkeypatched time)
- Any real-hardware verification notes from the Pi
</output>
