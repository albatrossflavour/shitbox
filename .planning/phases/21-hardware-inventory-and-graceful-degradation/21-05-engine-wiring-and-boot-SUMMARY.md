---
phase: 21
plan: "05"
subsystem: engine
tags: [engine, boot, supervisor, graceful-degradation, hardware, hw-state]
depends_on:
  requires: ["21-01", "21-02", "21-03"]
  provides: ["hw_state-wired", "supervisor-lifecycle", "HW-04", "HW-05"]
  affects: ["src/shitbox/events/engine.py"]
tech_stack:
  added: []
  patterns: ["_start_service_graceful helper", "reprobe_callbacks dispatch table", "module-level singleton state"]
key_files:
  created:
    - tests/hardware/test_engine_integration.py
  modified:
    - src/shitbox/events/engine.py
    - src/shitbox/collectors/light.py
    - src/shitbox/collectors/power.py
    - tests/test_engine_boot.py
decisions:
  - "caplog cannot capture structlog messages after cache_logger_on_first_use=True; engine.log patched directly in HW-05 tests"
  - "camera_cabin has no separate VideoRingBuffer (PIP is embedded in front buffer); role kwarg omitted per plan note on devices with no collector"
  - "HighRateSampler hardcodes role='imu' internally (Plan 03); no role= kwarg at engine construction site"
  - "EnvironmentCollector hardcodes role='environment' internally (Plan 03); no role= kwarg at engine construction site"
  - "cast(Callable[[], bool], lambda ...) used in _build_reprobe_callbacks to resolve mypy Cannot infer type of lambda errors"
  - "supervisor background thread stopped immediately in integration tests; _tick() driven manually to avoid real sleeps"
metrics:
  duration: "~10 minutes"
  completed: "2026-04-21"
  tasks_completed: 3
  files_changed: 5
requirements: [HW-04, HW-05]
---

# Phase 21 Plan 05: Engine Wiring and Boot Summary

Wire HardwareSupervisor and module-level hw_state into UnifiedEngine, thread
`role=` kwargs through collectors, and enforce HW-05 (daemon boots regardless of
hardware state) via `_start_service_graceful`.

## What Was Built

### engine.py wiring changes

`UnifiedEngine.__init__` now seeds module-level hw_state from the manifest tier map
and constructs `HardwareSupervisor(config.hardware, reprobe_callbacks)` before any
collector. Approximate line deltas: +135 insertions, -12 deletions from the WIP base
(which was already partially implemented as described in the plan prompt).

Key additions:

1. **hw_state.initialise()** called once at `__init__` with `{d.role: d.criticality for d in config.hardware.devices}`. This seeds the module registry so collector `report_*` calls during their own `__init__` land on a registered role.

2. **HardwareSupervisor construction** at `self.supervisor = HardwareSupervisor(config.hardware, reprobe_callbacks)` -- exactly 2 positional args. No `hw_state=` kwarg exists or is passed; the supervisor imports `hw_state` itself (D-04).

3. **`_build_reprobe_callbacks(manifest)`** builds a `dict[str, Callable[[], bool]]` keyed by device role, dispatching on canonical bus literals:

   | Bus literal | Probe function | Field used |
   |-------------|----------------|------------|
   | `"i2c-1"` | `probes.probe_i2c(1, address)` | `dev.address` |
   | `"1-wire"` | `probes.probe_onewire(sensor_id)` | `dev.sensor_id` |
   | `"usb"` | `probes.probe_usb_path(path)` | `dev.path` |
   | `"audio"` | `probes.probe_audio_label(label)` | `dev.label` |
   | `"hdmi"` | `probes.probe_hdmi(connector)` | `dev.connector` |
   | `"gpio"` | `probes.probe_gpio_pin(pin)` | `dev.pin` |

   All lambdas use default-argument capture (`a=addr`, `s=sid`, etc.) to prevent late-binding closure bugs. Devices with `None` for their required field are skipped with a warning. `cast(Callable[[], bool], ...)` applied to resolve mypy type inference limitation on parametrised lambdas.

4. **`_start_service_graceful(name, start_fn)`** wraps every collector `start()` call. Returns `True` if the service started cleanly, `False` if it raised. A single failure cannot prevent other services from booting (HW-05).

5. **`role=` kwargs** threaded to collectors that accept them:
   - `VEML7700Collector(role="light")`
   - `INA226Collector(role="power")`
   - `VideoRingBuffer(role="camera_front")`

   `HighRateSampler` and `EnvironmentCollector` hardcode their own role internally (Plan 03). `DS18B20Collector` manages per-probe roles inside its read loop. The GPS device has no collector (gpsd-only). The cabin camera is embedded as PIP within the single VideoRingBuffer instance; no separate `VideoRingBuffer` for `camera_cabin` exists in the current architecture.

6. **Lifecycle ordering** in `start()`:
   - `supervisor.start()` fires BEFORE any collector.start() calls
   - `log.info("unified_engine_started", collectors=started)` records the started/failed map
   
   In `stop()`:
   - All collectors stop first
   - `supervisor.stop()` fires LAST, wrapped in try/except

### hw_state is a module, not an instance (D-04)

No `self.hw_state` attribute exists on `UnifiedEngine`. The module `shitbox.hardware.state` imported as `hw_state` IS the singleton, mirroring `gps_state.py`. `grep -c "self.hw_state" src/shitbox/events/engine.py` returns 0.

### HW-04 and HW-05 closure

HW-04 (supervisor lifecycle): supervisor starts before collectors, stops after -- confirmed by line ordering in `start()` (line 1997) and `stop()` (line 2209).

HW-05 (daemon never refuses to boot): every collector.start() is wrapped in `_start_service_graceful`. The IMU sampler's `_force_reboot` remains reachable only from the runtime i2c_max_resets ladder; boot-time setup failure bubbles to the helper, is caught, and the sampler never reaches the runtime path.

## Test Coverage

### tests/test_engine_boot.py (2 new tests added to existing file)

**test_boot_with_all_critical_missing**: All probes return False, all collector
`start()` calls raise IOError. `UnifiedEngine.start()` must not raise, supervisor
thread must be alive, `unified_engine_started` must be logged, at least one
`service_start_failed` must be logged.

**test_imu_setup_failure_is_nonfatal**: IMU `start()` raises IOError. `_force_reboot`
must never be called (pitfall 5). Service must log `service_start_failed` for
`imu_sampler`.

Note: structlog's `cache_logger_on_first_use=True` prevents caplog from capturing
messages after initial logger binding. Tests patch `shitbox.events.engine.log.info`
and `log.error` directly to record calls instead.

### tests/hardware/test_engine_integration.py (new file)

**test_bme680_cold_boot_then_recovers_via_supervisor**: End-to-end scenario.
`time.monotonic` monkeypatched on both `shitbox.hardware.supervisor` and
`shitbox.hardware.state` modules. Background tick thread stopped immediately after
`supervisor.start()`. `_tick()` driven manually:

- First tick at T=0: state MISSING, `speak_hardware_missing("environment", "best_effort")` called once
- Clock advanced to T=5.1
- Second tick: reprobe returns True, `report_present` called, `speak_hardware_restored("environment", "best_effort")` called once

Total runtime: 1.05s (under the 2s target).

**test_bme680_supervisor_does_not_invoke_internal_retry_loop**: Static source guard
confirming `_BME680_INIT_RETRIES` and `time.sleep` are absent from `environment.py`
(pitfall 7 guard -- supervisor owns retry cadence exclusively).

## Deviations from Plan

### Architecture mismatches (no code change needed)

The plan's acceptance criteria included grep checks for `role="imu"`, `role="gps"`,
`role="environment"`, and `role="camera_cabin"` appearing in engine.py. These could
not be met:

- `HighRateSampler` hardcodes `self.role = "imu"` internally (Plan 03 decision) and
  does not accept a `role=` constructor arg. No change needed.
- GPS uses gpsd directly -- there is no GPSCollector class. No `role="gps"` wiring
  point exists. The GPS device's reprobe callback (usb bus, `/dev/gps0`) IS wired
  via `_build_reprobe_callbacks`.
- `EnvironmentCollector.__init__` calls `super().__init__(..., role="environment")`
  internally. The engine passes no `role=` kwarg to it.
- `camera_cabin` is the PIP camera embedded within the single `VideoRingBuffer`
  instance. No separate VideoRingBuffer for the cabin exists. The role still appears
  in the manifest and gets a reprobe callback.

All functional requirements are met. The grep criteria in the plan were written against
a theoretical two-VideoRingBuffer architecture.

### mypy lambda inference fix (Rule 1 -- Bug)

- **Found during:** Task 1
- **Issue:** `lambda a=addr: probes.probe_i2c(1, a)` inside `_build_reprobe_callbacks` produced 6 `Cannot infer type of lambda [misc]` mypy errors. The lambdas have default-arg parameters which mypy cannot narrow for `Callable[[], bool]` dict values.
- **Fix:** Applied `cast(Callable[[], bool], lambda ...)` to all 6 reprobe lambdas. Added `cast` to the `typing` import.
- **Files modified:** `src/shitbox/events/engine.py`
- **Commit:** 4bfc509

### caplog structlog cache issue (Rule 3 -- Blocking)

- **Found during:** Task 2
- **Issue:** `caplog.set_level(logging.DEBUG, logger="shitbox")` did not capture structlog messages because `cache_logger_on_first_use=True` binds the output pipeline before caplog adds its handler.
- **Fix:** Replaced caplog assertions with direct `patch("shitbox.events.engine.log.info", ...)` and `patch("shitbox.events.engine.log.error", ...)` to record calls in plain lists.
- **Files modified:** `tests/test_engine_boot.py`
- **Commit:** 81e160d

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.
The reprobe callbacks issue local filesystem and I2C syscalls -- same surface as the
existing probe functions. No new trust boundaries.

## Self-Check: PASSED

- `src/shitbox/events/engine.py` exists and contains HardwareSupervisor, hw_state.initialise, _build_reprobe_callbacks, _start_service_graceful
- `tests/test_engine_boot.py` contains test_boot_with_all_critical_missing and test_imu_setup_failure_is_nonfatal
- `tests/hardware/test_engine_integration.py` exists and contains both test functions
- All 3 task commits exist: 4bfc509, 81e160d, 664fbe5
- Full test suite: 315 passed, 1 skipped
