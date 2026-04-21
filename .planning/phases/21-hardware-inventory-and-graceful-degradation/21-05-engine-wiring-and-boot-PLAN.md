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

must_haves:
  truths:
    - "UnifiedEngine constructs HardwareSupervisor at __init__ and starts it in start() before collectors"
    - "Every collector and both VideoRingBuffer instances receive a role= kwarg matching their manifest device role"
    - "Any single collector setup() failure during start() is caught, logged, and MUST NOT prevent other collectors or services from starting"
    - "IMU sampler setup() failure at boot is logged but MUST NOT call _force_reboot() — reboot is only triggered during runtime recovery per pitfall 5"
    - "Supervisor receives a reprobe_callbacks dict mapping each manifest role to its probe function"
    - "Supervisor is stopped during engine.stop() AFTER collectors so final MISSING transitions are still observed"
    - "The daemon boots with zero hardware present and logs 'unified_engine_started' (HW-05)"
  artifacts:
    - path: "src/shitbox/events/engine.py"
      provides: "HardwareSupervisor instantiation, graceful collector start helper, role kwargs, reprobe dispatch"
      contains: "HardwareSupervisor"
    - path: "tests/test_engine_boot.py"
      provides: "HW-05 boot tests — all critical missing, IMU setup failure non-fatal"
      contains: "test_boot_with_all_critical_missing"
    - path: "tests/hardware/test_engine_integration.py"
      provides: "Canonical BME680 cold-boot integration test end-to-end"
      contains: "test_bme680_cold_boot_then_recovers_via_supervisor"
  key_links:
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/hardware/supervisor.py"
      via: "self.hardware_supervisor = HardwareSupervisor(manifest, hw_state, reprobe_callbacks)"
      pattern: "HardwareSupervisor\\("
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/hardware/probes.py"
      via: "reprobe_callbacks dict built from probes module per role"
      pattern: "reprobe_callbacks"
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/collectors/base.py"
      via: "collector constructors receive role= kwarg"
      pattern: "role=\""
    - from: "src/shitbox/events/engine.py"
      to: "src/shitbox/capture/ring_buffer.py"
      via: "VideoRingBuffer(role='camera_front') and VideoRingBuffer(role='camera_cabin')"
      pattern: "VideoRingBuffer\\(.*role="
---

<objective>
Wire the HardwareSupervisor into UnifiedEngine, thread role= kwargs through every collector and both VideoRingBuffer instances, and enforce HW-05 by refactoring the per-collector try/except block into a single _start_service_graceful helper that guarantees the daemon boots regardless of which hardware is missing or broken.

Purpose: Close HW-04 (supervisor lifecycle) and HW-05 (daemon never refuses to boot) end-to-end. This is the final plan for phase 21 and the only plan that modifies engine.py — all prior plans built the primitives that plug in here.

Output:
- Supervisor instantiated, started, and stopped as a first-class engine service
- Every collector and both VideoRingBuffers report to HardwareState with a stable role identifier
- _start_service_graceful(name, start_fn) ensures a single failure cannot take the process down
- HW-05 acceptance tests in tests/test_engine_boot.py
- End-to-end BME680 integration test confirming cold-boot → probe FALSE → retry → probe TRUE → PRESENT + "BME680 restored" TTS
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
@tests/test_ffmpeg_stall.py

<interfaces>
<!-- Contracts established by plans 01-03 that this plan consumes. -->

From src/shitbox/hardware/state.py (created in plan 01):
```python
class HardwareState:
    def __init__(self, manifest: HardwareManifestConfig) -> None: ...
    def report_present(self, role: str) -> None: ...
    def report_missing(self, role: str) -> None: ...
    def report_degraded(self, role: str) -> None: ...
    def get(self, role: str) -> DeviceStatus: ...
    def all(self) -> dict[str, DeviceStatus]: ...
```

From src/shitbox/hardware/supervisor.py (created in plan 02):
```python
class HardwareSupervisor:
    TICK_INTERVAL_SECONDS: float = 1.0
    CRITICAL_RENAG_SECONDS: float = 30.0

    def __init__(
        self,
        manifest: HardwareManifestConfig,
        hw_state: HardwareState,
        reprobe_callbacks: dict[str, Callable[[], bool]],
    ) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

From src/shitbox/hardware/probes.py (created in plan 01):
```python
def probe_i2c(address: int, bus: int = 1) -> bool: ...
def probe_i2c_bus_is_bitbang() -> bool: ...
def probe_1wire(device_id: str) -> bool: ...
def probe_usb(device_path: str) -> bool: ...
def probe_audio(card_name: str) -> bool: ...
def probe_hdmi() -> bool: ...
def probe_gpio() -> bool: ...
```

From src/shitbox/collectors/base.py (modified in plan 03):
```python
class BaseCollector(ABC):
    def __init__(
        self,
        name: str,
        interval: float,
        database: Database,
        *,
        role: str | None = None,  # NEW
        hw_state: HardwareState | None = None,  # NEW
    ) -> None: ...
```

From src/shitbox/capture/ring_buffer.py (modified in plan 03):
```python
class VideoRingBuffer:
    def __init__(
        self,
        config: VideoBufferConfig,
        *,
        role: str = "camera_front",  # NEW
        hw_state: HardwareState | None = None,  # NEW
    ) -> None: ...
```
</interfaces>

<ui_spec_reference>
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md
No direct UI changes in this plan — engine wiring is invisible to operators, but the supervisor this plan starts is what makes OLED/SSE/TTS copy in Plan 04 come to life.
</ui_spec_reference>

<existing_engine_call_sites>
<!-- Known engine.py reference points from 21-PATTERNS.md. Lines approximate — read before editing. -->
- Line ~471: first per-collector try/except at start() (the block to extract into helper)
- Line ~613: self.video_ring_buffer = VideoRingBuffer(... )  — front camera
- Line ~1917-1928: per-collector try/except block (primary refactor target)
- Collector construction points: MPU6050 / LSM6DSOX sampler, GPS, BME680 environment, INA226/INA219 power, DS18B20 temperature, light, air quality, button — all in __init__
- Engine has second VideoRingBuffer for camera_cabin — thread role="camera_cabin" there
</existing_engine_call_sites>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Wire HardwareSupervisor into UnifiedEngine and thread role kwargs</name>
  <files>src/shitbox/events/engine.py</files>

  <read_first>
    <file>src/shitbox/events/engine.py</file>
    <why>Need exact line numbers for __init__, start(), stop(), the per-collector try/except block (~lines 1917-1928), and the two VideoRingBuffer construction sites. Line numbers in 21-PATTERNS.md are approximate.</why>
    <file>src/shitbox/hardware/supervisor.py</file>
    <why>Confirm HardwareSupervisor.__init__ signature matches the reprobe_callbacks dict you build.</why>
    <file>src/shitbox/hardware/probes.py</file>
    <why>Confirm probe function names and signatures before building the reprobe_callbacks dispatch dict.</why>
    <file>.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md</file>
    <why>D-01 manifest role names, D-05 tier assignments, D-11 (no Prometheus / no website sync for hardware state).</why>
  </read_first>

  <behavior>
    - UnifiedEngine.__init__ constructs: HardwareState(manifest), then HardwareSupervisor(manifest, hw_state, reprobe_callbacks)
    - reprobe_callbacks is a dict[str, Callable[[], bool]] keyed by device role, built by inspecting manifest.devices and dispatching on device.bus:
        - bus == "i2c" → lambda bound to probe_i2c(device.address, bus=device.i2c_bus or 1)
        - bus == "1wire" → lambda bound to probe_1wire(device.device_id)
        - bus == "usb" → lambda bound to probe_usb(device.device_path)
        - bus == "audio" → lambda bound to probe_audio(device.card_name)
        - bus == "hdmi" → probe_hdmi
        - bus == "gpio" → probe_gpio
    - Every collector constructor call passes role="<manifest_role>" and hw_state=self.hw_state:
        - MPU6050/LSM6DSOX sampler path: role="imu"
        - GPSCollector: role="gps"
        - EnvironmentCollector (BME680): role="environment"
        - PowerCollector (INA226/INA219): role="power"
        - TemperatureCollector (DS18B20): role="temperature_<id>" (one per configured probe; acceptable to pass "temperature_cabin" / "temperature_engine_bay" per manifest)
        - LightCollector (BH1750): role="light"
        - AirQualityCollector (SEN0460): role="air_quality"
        - ButtonHandler (GPIO 17): role="button"
    - Both VideoRingBuffer constructions pass role= matching manifest: front camera → role="camera_front", cabin camera → role="camera_cabin". Also pass hw_state=self.hw_state.
    - start() sequence MUST be: self.hardware_supervisor.start() BEFORE any collector start — supervisor tick loop must be running so probe-TRUE events from collector setup() can be observed, and so the supervisor owns the first TTS cadence window.
    - stop() sequence MUST be: stop collectors first, then self.hardware_supervisor.stop() LAST — otherwise final MISSING transitions during teardown are swallowed.
    - A new private method _start_service_graceful(name: str, start_fn: Callable[[], None]) -> bool wraps every collector/service start:
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
    - Sampler boot-time guard: the IMU sampler's setup() failure must NOT trigger _force_reboot (pitfall 5). The graceful helper catches the exception and returns False; the sampler.start() path is only entered if setup() succeeds. Concretely: the sampler must expose setup() as a pre-start step, and _start_service_graceful wraps sampler.setup() + sampler.start() together so a setup failure never transitions to the _force_reboot-eligible runtime path.
  </behavior>

  <action>
    Modify src/shitbox/events/engine.py (this is the ONLY file this task touches):

    1. **Imports** at module top:
       ```python
       from shitbox.hardware.state import HardwareState
       from shitbox.hardware.supervisor import HardwareSupervisor
       from shitbox.hardware import probes
       ```

    2. **UnifiedEngine.__init__** — after config is loaded and before any collector is constructed:
       ```python
       self.hw_state = HardwareState(config.hardware)
       reprobe_callbacks = self._build_reprobe_callbacks(config.hardware)
       self.hardware_supervisor = HardwareSupervisor(
           config.hardware, self.hw_state, reprobe_callbacks
       )
       ```

    3. **New private method _build_reprobe_callbacks(manifest)**:
       ```python
       def _build_reprobe_callbacks(
           self, manifest: HardwareManifestConfig
       ) -> dict[str, Callable[[], bool]]:
           cbs: dict[str, Callable[[], bool]] = {}
           for dev in manifest.devices:
               bus = dev.bus
               if bus == "i2c":
                   addr = dev.address
                   i2c_bus = dev.i2c_bus or 1
                   cbs[dev.role] = lambda a=addr, b=i2c_bus: probes.probe_i2c(a, bus=b)
               elif bus == "1wire":
                   did = dev.device_id
                   cbs[dev.role] = lambda d=did: probes.probe_1wire(d)
               elif bus == "usb":
                   dp = dev.device_path
                   cbs[dev.role] = lambda p=dp: probes.probe_usb(p)
               elif bus == "audio":
                   cn = dev.card_name
                   cbs[dev.role] = lambda n=cn: probes.probe_audio(n)
               elif bus == "hdmi":
                   cbs[dev.role] = probes.probe_hdmi
               elif bus == "gpio":
                   cbs[dev.role] = probes.probe_gpio
               else:
                   log.warning("unknown_bus_for_reprobe", role=dev.role, bus=bus)
           return cbs
       ```
       Note the default-argument capture (`a=addr, b=i2c_bus`) — critical to avoid late-binding closure bugs in the loop.

    4. **Thread role + hw_state kwargs through every collector constructor.** Search for each collector class instantiation in __init__ and append `role=<role>, hw_state=self.hw_state`. Example:
       ```python
       # BEFORE
       self.environment_collector = EnvironmentCollector(
           name="environment", interval=config.sensors.environment.interval,
           database=self.database, config=config.sensors.environment,
       )
       # AFTER
       self.environment_collector = EnvironmentCollector(
           name="environment", interval=config.sensors.environment.interval,
           database=self.database, config=config.sensors.environment,
           role="environment", hw_state=self.hw_state,
       )
       ```
       Apply to: IMU sampler, GPSCollector, EnvironmentCollector, PowerCollector, TemperatureCollector (one per probe — use per-probe role), LightCollector, AirQualityCollector, ButtonHandler.

    5. **Thread role + hw_state into both VideoRingBuffer calls.** At the ~line 613 site (front) and the cabin site:
       ```python
       self.video_ring_buffer = VideoRingBuffer(
           config.capture.video,
           role="camera_front",
           hw_state=self.hw_state,
       )
       # ...later...
       self.video_ring_buffer_cabin = VideoRingBuffer(
           config.capture.video_cabin,
           role="camera_cabin",
           hw_state=self.hw_state,
       )
       ```

    6. **Add _start_service_graceful helper** (place near the top of the methods block after __init__):
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

    7. **Refactor start().** At the top of start(), call:
       ```python
       self.hardware_supervisor.start()
       log.info("hardware_supervisor_started")
       ```
       THEN replace the existing per-collector try/except block (lines ~1917-1928 and the ~471 site) with:
       ```python
       started = {}
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
       log.info("unified_engine_started", collectors=started)
       ```
       Preserve existing ordering constraints (e.g. database must be ready before collectors start — that block stays as-is).

    8. **Refactor stop().** Add at the very end of stop(), AFTER all collectors have been stopped:
       ```python
       try:
           self.hardware_supervisor.stop()
           log.info("hardware_supervisor_stopped")
       except Exception as e:
           log.error("hardware_supervisor_stop_failed", error=str(e))
       ```

    9. **Sampler boot-time reboot guard (pitfall 5).** If the IMU sampler exposes a separate setup() method today that feeds into start(), wrap both in one graceful call so a setup() exception never puts the sampler into the runtime state where _force_reboot is reachable. If setup() is folded inside start(), the existing pattern already works — just confirm via grep that _force_reboot has no call sites outside the runtime reset-count ladder (search existing code for `_force_reboot` to confirm it's only called after I2C_MAX_RESETS is hit at runtime).
  </action>

  <verify>
    <automated>pytest tests/ -x -q --no-cov 2>&1 | tail -30 && ruff check src/shitbox/events/engine.py && mypy src/shitbox/events/engine.py</automated>
  </verify>

  <acceptance_criteria>
    - [ ] engine.py imports HardwareState, HardwareSupervisor, and probes module
    - [ ] grep "self.hardware_supervisor = HardwareSupervisor" src/shitbox/events/engine.py returns 1 match
    - [ ] grep "_build_reprobe_callbacks" src/shitbox/events/engine.py returns >=2 matches (definition + call site)
    - [ ] grep -c 'role="imu"' src/shitbox/events/engine.py returns 1
    - [ ] grep -c 'role="environment"' src/shitbox/events/engine.py returns 1
    - [ ] grep -c 'role="gps"' src/shitbox/events/engine.py returns 1
    - [ ] grep -c 'role="power"' src/shitbox/events/engine.py returns 1
    - [ ] grep -c 'role="camera_front"' src/shitbox/events/engine.py returns 1
    - [ ] grep -c 'role="camera_cabin"' src/shitbox/events/engine.py returns 1
    - [ ] grep "_start_service_graceful" src/shitbox/events/engine.py returns >=6 call sites (one per major collector/service)
    - [ ] The block previously at lines ~1917-1928 now uses _start_service_graceful — no inline try/except for collector.start() remains
    - [ ] self.hardware_supervisor.start() is called BEFORE any collector.start in start()
    - [ ] self.hardware_supervisor.stop() is called LAST in stop() (after all collector stops)
    - [ ] Default-argument capture used in every loop lambda (grep "lambda a=" / "lambda d=" / "lambda p=" / "lambda n=" in _build_reprobe_callbacks)
    - [ ] ruff check passes with zero findings
    - [ ] mypy passes with zero errors
    - [ ] All existing pytest tests still pass (no regressions)
  </acceptance_criteria>

  <done>
    engine.py instantiates HardwareState and HardwareSupervisor, threads role + hw_state through every collector and both VideoRingBuffers, wraps every service start in _start_service_graceful, starts the supervisor before collectors, and stops it last. Existing test suite stays green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: HW-05 boot tests — engine boots with all critical hardware missing</name>
  <files>tests/test_engine_boot.py</files>

  <read_first>
    <file>tests/test_i2c_recovery.py</file>
    <why>Existing pattern for mocking smbus2 + GPIO + subprocess to simulate hardware-absent environment in unit tests. Follow the same mock-layering style.</why>
    <file>src/shitbox/events/engine.py</file>
    <why>Know the exact UnifiedEngine constructor signature and start()/stop() flow you're testing.</why>
    <file>.planning/phases/21-hardware-inventory-and-graceful-degradation/21-VALIDATION.md</file>
    <why>Confirms the two HW-05 test names and their intent.</why>
  </read_first>

  <behavior>
    Two tests prove HW-05.

    - **test_boot_with_all_critical_missing:** All hardware probes return False; every collector's setup/start raises a hardware exception. UnifiedEngine.start() MUST complete without raising, log "unified_engine_started" at INFO, and HardwareSupervisor must be running (alive thread). stop() MUST then complete cleanly without raising.

    - **test_imu_setup_failure_is_nonfatal:** Only the IMU sampler's setup/start raises (IOError "imu init failed"); all other hardware is present. start() MUST complete, MUST log "service_start_failed" with service="imu_sampler", and MUST NOT call _force_reboot. Other collectors MUST be observed to have started (log "service_started" for at least one other service).
  </behavior>

  <action>
    Create tests/test_engine_boot.py:

    ```python
    """HW-05 boot resilience tests — daemon MUST boot regardless of hardware state.

    Proves that a fully-missing hardware set does not prevent the engine from starting,
    and that a single failing collector (the IMU) does not cascade into a reboot or
    take down other services.
    """
    from __future__ import annotations

    from unittest.mock import MagicMock, patch

    import pytest

    from shitbox.events.engine import UnifiedEngine
    from shitbox.utils.config import load_config


    @pytest.fixture
    def minimal_config(tmp_path):
        """Load a config with every hardware role declared but nothing actually present."""
        # Use the real config.yaml as the starting point so manifest shape is accurate
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
            patch("shitbox.hardware.probes.probe_1wire", return_value=False),
            patch("shitbox.hardware.probes.probe_usb", return_value=False),
            patch("shitbox.hardware.probes.probe_audio", return_value=False),
            patch("shitbox.hardware.probes.probe_hdmi", return_value=False),
            patch("shitbox.hardware.probes.probe_gpio", return_value=False),
            patch("shitbox.hardware.probes.probe_i2c_bus_is_bitbang", return_value=True),
            # Collector .start() mocks that all raise
            patch("shitbox.events.sampler.IMUSampler.start", side_effect=IOError("no imu")),
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


    def test_boot_with_all_critical_missing(
        minimal_config, all_hardware_missing, caplog
    ):
        """HW-05: engine.start() completes with every critical service failing."""
        engine = UnifiedEngine(minimal_config)

        # Must not raise
        engine.start()

        # Supervisor must be alive
        assert engine.hardware_supervisor is not None
        assert engine.hardware_supervisor._thread is not None  # type: ignore[attr-defined]
        assert engine.hardware_supervisor._thread.is_alive()  # type: ignore[attr-defined]

        # unified_engine_started logged at INFO
        assert any(
            r.message == "unified_engine_started" or "unified_engine_started" in r.getMessage()
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
            "shitbox.events.sampler.IMUSampler.start",
            side_effect=IOError("imu init failed"),
        ), patch(
            "shitbox.events.sampler.IMUSampler._force_reboot"
        ) as mock_reboot, patch(
            "shitbox.hardware.probes.probe_i2c", return_value=True
        ), patch(
            "shitbox.hardware.probes.probe_gpio", return_value=True
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
    - The internal thread attribute `_thread` on HardwareSupervisor is inspected directly — acceptable for a lifecycle test, but keep it private-but-tested. If supervisor exposes `is_running` property, prefer that.
    - If some collector classes have different start() paths (e.g. collector groups via `_start_service`), extend the patch list rather than shimming. Prefer real classes + mocked leaf methods over full class mocks.
  </action>

  <verify>
    <automated>pytest tests/test_engine_boot.py -v --no-cov</automated>
  </verify>

  <acceptance_criteria>
    - [ ] tests/test_engine_boot.py exists
    - [ ] test_boot_with_all_critical_missing passes
    - [ ] test_imu_setup_failure_is_nonfatal passes
    - [ ] No test marks or xfails — both assert real, required behaviour
    - [ ] Both tests use the real UnifiedEngine + HardwareSupervisor (only leaf hardware calls are mocked)
    - [ ] test_imu_setup_failure_is_nonfatal asserts _force_reboot was NOT called (pitfall 5)
    - [ ] ruff check tests/test_engine_boot.py passes
    - [ ] No sleeps longer than supervisor TICK_INTERVAL_SECONDS (1.0s) — tests must be fast
  </acceptance_criteria>

  <done>
    HW-05 has concrete test coverage. An engine with zero hardware boots cleanly, and an IMU-only failure doesn't reboot the Pi.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Canonical BME680 cold-boot integration test</name>
  <files>tests/hardware/test_engine_integration.py</files>

  <read_first>
    <file>.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md</file>
    <why>Look up pitfall 2 (PRESENT only on successful sample), pitfall 6 (supervisor owns RESTORED TTS), and the canonical BME680 acceptance scenario described in the research doc.</why>
    <file>tests/hardware/test_hardware_state.py</file>
    <why>Use the same in-process HardwareState + manifest construction idiom established in plan 01.</why>
    <file>src/shitbox/hardware/supervisor.py</file>
    <why>Confirm TICK_INTERVAL_SECONDS and backoff ladder [5.0, 15.0, 60.0, 300.0]; the test needs to advance time past 5.0s for the first retry tier.</why>
  </read_first>

  <behavior>
    End-to-end: boot with BME680 probe FALSE at T=0. Supervisor marks environment MISSING. TTS "Environment sensor offline" fires (best_effort tier is the ONE best-effort role that still speaks per D-05). At T+5s (first backoff tier), probe returns TRUE, supervisor retries, sampler reads successfully on next collector tick, HardwareState.report_present("environment") is called, supervisor observes PRESENT transition, TTS "BME680 restored" fires once.

    Key contract points this test defends:
    - Supervisor-owned re-adoption at the 5s backoff tier, not the sampler
    - PRESENT transition triggered only by successful sample (pitfall 2), not probe-TRUE alone
    - Single RESTORED TTS from supervisor, not duplicate from sampler (pitfall 6)
    - No call to BME680 5×1s internal retry loop during this scenario (pitfall 7) — supervisor's backoff is the single source of retry cadence
  </behavior>

  <action>
    Create tests/hardware/test_engine_integration.py:

    ```python
    """Canonical BME680 cold-boot → recover scenario (Phase 21 integration).

    This is the end-to-end truth test for the supervisor + collector + state
    contract. If this passes, hardware graceful degradation is working.
    """
    from __future__ import annotations

    import time
    from unittest.mock import MagicMock, patch

    import pytest

    from shitbox.hardware.state import HardwareState
    from shitbox.hardware.supervisor import HardwareSupervisor
    from shitbox.utils.config import HardwareManifestConfig, HardwareDeviceConfig


    @pytest.fixture
    def manifest_bme680_only():
        """Minimal manifest with only the BME680 environment device."""
        return HardwareManifestConfig(
            devices=[
                HardwareDeviceConfig(
                    role="environment",
                    bus="i2c",
                    address=0x77,
                    tier="best_effort",
                ),
            ]
        )


    def test_bme680_cold_boot_then_recovers_via_supervisor(
        manifest_bme680_only, caplog
    ):
        """Cold boot BME680 absent → supervisor retries at T+5s → PRESENT + TTS.

        Timeline:
          T=0.0   probe False → supervisor marks MISSING, speak_hardware_missing
          T=5.1   probe True  → supervisor retries, state stays MISSING until sample
          T=5.2   collector reads successfully → state.report_present → PRESENT
          T=5.2   supervisor next tick observes PRESENT transition → speak_hardware_restored
        """
        hw_state = HardwareState(manifest_bme680_only)

        # Probe flips from False to True at T+5s
        start_time = time.monotonic()
        def probe_fn() -> bool:
            return (time.monotonic() - start_time) >= 5.0

        reprobe_callbacks = {"environment": probe_fn}

        with patch(
            "shitbox.capture.speaker.speak_hardware_missing"
        ) as mock_missing, patch(
            "shitbox.capture.speaker.speak_hardware_restored"
        ) as mock_restored:
            supervisor = HardwareSupervisor(
                manifest_bme680_only, hw_state, reprobe_callbacks
            )
            supervisor.start()

            # Wait for supervisor to observe MISSING (within first tick + 1s margin)
            time.sleep(2.0)
            assert hw_state.get("environment").state == "MISSING"
            mock_missing.assert_called_once_with("environment", tier="best_effort")

            # Probe still returns False until T+5s — simulate successful sample
            # arriving AFTER probe flips True (pitfall 2: PRESENT only on sample)
            time.sleep(4.0)  # now T+6
            hw_state.report_present("environment")

            # Supervisor next tick observes transition → RESTORED TTS
            time.sleep(1.5)
            assert hw_state.get("environment").state == "PRESENT"
            mock_restored.assert_called_once_with("environment", tier="best_effort")

            supervisor.stop()

    def test_bme680_probe_true_without_sample_stays_missing(
        manifest_bme680_only
    ):
        """Pitfall 2 guard: probe True alone must NOT transition to PRESENT."""
        hw_state = HardwareState(manifest_bme680_only)

        with patch(
            "shitbox.capture.speaker.speak_hardware_missing"
        ), patch(
            "shitbox.capture.speaker.speak_hardware_restored"
        ) as mock_restored:
            supervisor = HardwareSupervisor(
                manifest_bme680_only, hw_state, {"environment": lambda: True}
            )
            supervisor.start()

            # Give supervisor 3 ticks to probe
            time.sleep(3.5)

            # No report_present called → state must still be MISSING
            assert hw_state.get("environment").state == "MISSING"
            # And no RESTORED TTS — pitfall 2 enforced
            mock_restored.assert_not_called()

            supervisor.stop()

    def test_bme680_supervisor_does_not_invoke_internal_retry_loop(
        manifest_bme680_only
    ):
        """Pitfall 7 guard: BME680 collector's legacy 5×1s retry must NOT run.

        If the supervisor is the single source of retry cadence, the collector's
        internal _BME680_INIT_RETRIES loop must be gone (deleted in Plan 03).
        This test proves the import doesn't re-introduce it.
        """
        from shitbox.collectors import environment

        source = open(environment.__file__).read()
        assert "_BME680_INIT_RETRIES" not in source, (
            "pitfall 7: environment.py must not re-introduce internal retry loop"
        )
        assert "time.sleep(1)" not in source or source.count("time.sleep(1)") == 0, (
            "environment.py setup must be single-attempt; supervisor owns retry"
        )
    ```

    Notes:
    - The sleeps are unavoidable given the real 1s tick and 5s backoff — the test takes ~7s in total. Fast enough for CI.
    - The second and third tests are guard tests for pitfalls 2 and 7 respectively; they isolate one contract rule each.
    - Patching `speak_hardware_missing` / `speak_hardware_restored` at the speaker module level requires those functions to be imported in supervisor.py as module-level references (not re-exported attributes). If supervisor does `from shitbox.capture.speaker import speak_hardware_missing`, patch at `shitbox.hardware.supervisor.speak_hardware_missing` instead.

    Add `tests/hardware/__init__.py` if it doesn't already exist (plan 01 should have created it).
  </action>

  <verify>
    <automated>pytest tests/hardware/test_engine_integration.py -v --no-cov</automated>
  </verify>

  <acceptance_criteria>
    - [ ] tests/hardware/test_engine_integration.py exists
    - [ ] test_bme680_cold_boot_then_recovers_via_supervisor passes
    - [ ] test_bme680_probe_true_without_sample_stays_missing passes
    - [ ] test_bme680_supervisor_does_not_invoke_internal_retry_loop passes
    - [ ] The canonical test asserts: MISSING observed within 2s, PRESENT observed after report_present + 1.5s tick, exactly one missing TTS, exactly one restored TTS
    - [ ] Pitfall 2 guard test proves probe-TRUE alone does not cause PRESENT
    - [ ] Pitfall 7 guard test proves environment.py has no _BME680_INIT_RETRIES and no time.sleep(1)
    - [ ] Total test module runtime <10s
    - [ ] ruff check tests/hardware/test_engine_integration.py passes
  </acceptance_criteria>

  <done>
    The full Phase 21 contract is demonstrated by a single passing integration test: cold boot → supervised retry → successful sample → PRESENT transition → restored TTS. Pitfalls 2 and 7 have dedicated guard tests.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| engine → hardware | Probe functions issue smbus2/filesystem/subprocess calls; engine consumes their boolean return values |
| engine → systemd | Process lifecycle; systemd restarts the daemon on crash but Phase 21 goal is to never crash on hardware absence |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-05-01 | Denial of Service | UnifiedEngine.start() | mitigate | _start_service_graceful wraps every collector.start() — a single raising collector cannot prevent boot. HW-05 test asserts this. |
| T-21-05-02 | Denial of Service | IMU sampler _force_reboot | mitigate | Sampler boot-time setup failure goes through _start_service_graceful, which catches and logs. _force_reboot remains reachable only from the runtime reset-count ladder after I2C_MAX_RESETS (pitfall 5). test_imu_setup_failure_is_nonfatal asserts _force_reboot.assert_not_called(). |
| T-21-05-03 | Tampering | reprobe_callbacks dispatch | accept | Manifest is a local config file the operator controls. No external input crosses this boundary. |
| T-21-05-04 | Information Disclosure | log.info("unified_engine_started", collectors=started) | accept | Log contains bool map of role → started; no secrets, no PII, no addresses. Local systemd journal only, not shipped off-device (D-11 — no Prometheus sync for hw state). |
| T-21-05-05 | Elevation of Privilege | HardwareSupervisor thread | accept | Thread runs as the shitbox service user, same privileges as existing collectors. No new syscall surface. |

Notes: ASVS L1 has no authentication/session controls in scope for this in-car local-only daemon. The threats that apply are all availability-oriented, and the two DoS threats are directly mitigated by the graceful helper and the sampler reboot guard.
</threat_model>

<verification>
End-to-end checks after all three tasks:

1. **Full suite:** `pytest --no-cov -x` — all tests green, no regressions in existing suites
2. **Lint/types:** `ruff check src/` and `mypy src/` — zero findings
3. **Cold-boot smoke (on Pi, manual):** stop BME680 I2C line, restart shitbox-telemetry, verify systemd shows the service active, journalctl shows `unified_engine_started` followed by `service_start_failed` for environment, and `hardware_supervisor_started`
4. **Supervisor liveness:** `journalctl -u shitbox-telemetry -f` should show supervisor tick logs if debug logging is enabled
5. **BME680 hot-plug (on Pi, manual):** with supervisor running and BME680 MISSING, reconnect the sensor cable. Within 5-60s (depending on backoff tier) OLED ENV count should tick up, dashboard HARDWARE card should flip to PRESENT, TTS should say "BME680 restored"
</verification>

<success_criteria>
- [ ] engine.py constructs HardwareSupervisor in __init__, starts it before collectors, stops it last
- [ ] Every collector and both VideoRingBuffers receive role= + hw_state= kwargs matching their manifest role
- [ ] _start_service_graceful wraps every collector/service start — no single failure can abort boot
- [ ] HW-05 tests pass: all-critical-missing boot + IMU-failure-non-fatal
- [ ] Canonical BME680 cold-boot integration test passes
- [ ] Pitfall 2 and pitfall 7 guard tests pass
- [ ] _force_reboot is provably unreachable from boot-time setup failure
- [ ] ruff + mypy clean on engine.py
- [ ] Full test suite remains green with no xfails added
</success_criteria>

<output>
After completion, create `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-05-SUMMARY.md` documenting:
- engine.py wiring changes and line-number deltas
- The _start_service_graceful helper and why it exists
- Supervisor lifecycle ordering (start before collectors, stop after)
- Reprobe_callbacks dispatch table — one lambda per role, default-arg captures
- HW-05 test coverage and the BME680 canonical scenario
- Any real-hardware verification notes from the Pi
</output>
