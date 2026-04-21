---
phase: 21-hardware-inventory-and-graceful-degradation
reviewed: 2026-04-21T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - src/shitbox/hardware/state.py
  - src/shitbox/hardware/supervisor.py
  - src/shitbox/hardware/probes.py
  - src/shitbox/hardware/__init__.py
  - src/shitbox/events/engine.py
  - src/shitbox/events/sampler.py
  - src/shitbox/capture/ring_buffer.py
  - src/shitbox/capture/speaker.py
  - src/shitbox/collectors/base.py
  - src/shitbox/collectors/environment.py
  - src/shitbox/collectors/light.py
  - src/shitbox/collectors/power.py
  - src/shitbox/display/oled.py
  - src/shitbox/utils/config.py
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-04-21T00:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

The hardware inventory subsystem lands cleanly. State uses the GIL-atomic
rebind pattern, probes are single-shot and bus-scoped, and the supervisor
tick loop is well-structured. Boot sequencing in `UnifiedEngine.start()`
correctly wraps each service in `_start_service_graceful` so no single
hardware failure can abort boot. The design pitfalls called out in the
phase brief (report_present only on successful sample, _force_reboot only
reachable at runtime, no inline retry loop in environment.py) are all
honoured.

The issues below are genuine. Nothing is critical — no crash risk, no
security exposure — but a few concurrency and graceful-degradation
assumptions are worth tightening before this goes in the car.

## Warnings

### WR-01: Sampler `start()` can skip thread launch after boot-time reboot trigger

**File:** `src/shitbox/events/sampler.py:109-140`
**Issue:** The boot-time ladder at `start()` (lines 114-135) calls
`self._force_reboot()` on the final attempt and then `return`s. This is
the correct behaviour when we really are on a Pi and really do want a
reboot. However `_force_reboot()` uses `subprocess.run(["sudo",
"systemctl", "reboot"], check=False)` which is fire-and-forget — the
reboot is asynchronous. Between firing the reboot and the kernel actually
taking us down, `start()` returns without setting `self._running = True`
and without spawning the sampler thread. If the reboot is delayed (sudo
needs a TTY, systemctl denied by polkit, test environment) the engine
keeps booting with a dead sampler and no indication to the rest of the
engine. The brief explicitly says `_force_reboot` must only be reachable
from the runtime i2c_max_resets ladder (pitfall 5); boot-time reachability
here contradicts that invariant.
**Fix:** On boot-time setup failure, do not call `_force_reboot()`. Log
critical, report_missing, return without starting the thread, and let
`_start_service_graceful` in the engine record the failure. The runtime
ladder in `_sample_loop` is the only path that should ever reboot.
```python
else:
    log.critical("sampler_setup_unrecoverable_at_boot")
    hw_state.report_missing(self.role)
    return  # engine continues without IMU; runtime ladder owns reboot policy
```

### WR-02: `_last_nag` and `_prev_state` mutated under assumption of single-caller; collectors can race with tick loop on `report_present`

**File:** `src/shitbox/hardware/supervisor.py:42-43, 116-183`
**Issue:** `_last_nag` and `_prev_state` are plain dicts mutated only from
the supervisor tick thread, which is fine in isolation. However the tick
loop reads `hw_state.snapshot()` and then reacts to transitions (speak,
log, clear nag). If a collector thread transitions a device
MISSING→PRESENT between `snapshot()` and the tick's read, the supervisor
correctly observes PRESENT (external recovery branch at line 176). But
the supervisor ALSO still runs the retry branch at line 135 against the
snapshot's stale view, which can be PRESENT from a fresh probe while
`consecutive_misses > 0` is no longer true. Result: the reprobe callback
fires against a device that's already PRESENT. Harmless for most probes,
but `probe_i2c` opens and closes the bus, which briefly contends with
the LSM6DSOX sampler at 100 Hz. On a bit-banged i2c-1 bus this is exactly
the contention that sampler's I2C lockup recovery is designed to avoid.
**Fix:** Gate the retry branch on `st.state == MISSING` (already present
on line 136) AND re-check after the call:
```python
if (
    st.state == hw_state.DeviceState.MISSING
    and st.consecutive_misses > 0
    and now >= st.next_retry_at
):
    # Re-read state to avoid racing a collector's report_present
    current = hw_state.snapshot().get(role)
    if current is None or current.state != hw_state.DeviceState.MISSING:
        continue
    cb = self.reprobe.get(role)
    ...
```
Alternative: hold a lock across the snapshot + reprobe window. The
re-read is cheaper and matches the "GIL-atomic rebind" pattern used
elsewhere.

### WR-03: Double `hw_state.initialise()` call clobbers any state captured between `UnifiedEngine.__init__` and `supervisor.start`

**File:** `src/shitbox/events/engine.py:394, src/shitbox/hardware/supervisor.py:52-53`
**Issue:** `UnifiedEngine.__init__` calls `hw_state.initialise(...)` at
line 394 so that collector role reports during `__init__` land on a
registered role. Then `HardwareSupervisor.start()` calls
`hw_state.initialise(...)` again at line 53. The second call rebuilds the
entire `_state` dict from scratch — every `since_monotonic`,
`consecutive_misses`, and `last_seen` captured in between is lost.
Today this is benign because no collector runs between `__init__` and
`supervisor.start()`. But it's a latent bug: any future code that starts
a thread in `__init__` (reasonable pattern — matches `boot_recovery`)
will have its presence reports silently erased.
**Fix:** Make `hw_state.initialise()` idempotent: if a role already
exists, preserve its state. Or have the supervisor's `start()` skip
initialise if `hw_state.snapshot()` is non-empty. Cheapest fix:
```python
def initialise(devices: Dict[str, str]) -> None:
    global _state
    now = time.monotonic()
    new_map = dict(_state)  # preserve existing entries
    for role, tier in devices.items():
        if role not in new_map:
            new_map[role] = DeviceStatus(
                role=role, tier=tier, state=DeviceState.MISSING,
                last_seen=0.0, since_monotonic=now,
                next_retry_at=0.0, consecutive_misses=0,
            )
    _state = new_map
    log.info("hw_state_initialised", devices=len(devices))
```

### WR-04: `EnvironmentCollector.read()` raises on error; base collector's `_run_loop` marks MISSING but never calls `report_degraded` for transient I2C bounce

**File:** `src/shitbox/collectors/environment.py:56-87, src/shitbox/collectors/base.py:140-172`
**Issue:** `read()` re-raises on exception (line 87). `BaseCollector._run_loop`
catches this, calls `self._report_missing()`, and increments
`_error_count`. After 10 consecutive errors the collector silently stops
(`self._running = False; break` at line 171-172). Once stopped, the
thread terminates and there is no path back to PRESENT — the supervisor's
reprobe is purely a probe_i2c call; it flips state to PRESENT but does
not restart the collector. From then on, every probe returns True,
supervisor speaks "environment restored", but no readings flow. This is
an observable hardware-present-but-silent failure mode.
**Fix:** Either (a) make the collector self-healing by keeping the thread
alive and backing off after max_errors (the supervisor's retry cadence
is intended to own this), or (b) wire the supervisor's reprobe callback
for `environment` to restart the collector when probe succeeds after
thread exit. Option (a) is cheaper and matches the "supervisor owns
retry cadence" principle in pitfall 7:
```python
# base.py after max_errors
log.error("collector_max_errors_reached", collector=self.name, ...)
self._error_count = 0  # reset, sleep long, keep trying
time.sleep(30.0)
```

## Info

### IN-01: `EnvironmentCollector` uses `except (OSError, ValueError, ImportError, RuntimeError, Exception)` — the final `Exception` makes every earlier type redundant

**File:** `src/shitbox/events/sampler.py:105`
**Issue:** `except (OSError, ValueError, ImportError, RuntimeError, Exception) as e:`
collapses to `except Exception`. The enumerated types are dead weight and
mislead readers into thinking the exception set is scoped.
**Fix:** Either commit to the narrow set (drop `Exception`) or drop the
enumeration (`except Exception as e:`). Pick one.

### IN-02: `probe_i2c_bus_is_bitbang` logs critical on any non-`i2c-gpio` result, including OSError

**File:** `src/shitbox/hardware/probes.py:95-115`
**Issue:** The function catches OSError silently then falls through to
`log.critical`. On a machine with no `/sys/class/i2c-adapter/i2c-1`
(dev laptop, test env), this logs critical every time a supervisor boots.
Not wrong exactly, but critical is a strong word for "not running on a
Pi." The supervisor already logs `hw_i2c_bus_not_bitbang` at critical
when this returns False, so the duplication is wasted noise.
**Fix:** Drop the `log.critical` inside probes.py; let the caller decide.
Or split into two log events: `hw_i2c_adapter_missing` (info) vs
`hw_i2c_adapter_not_bitbang` (critical — the dangerous case where
built-in I2C peripheral is active and will hard-lock the bus).

### IN-03: `probe_gpio_pin` ignores the pin argument and only checks module import

**File:** `src/shitbox/hardware/probes.py:79-92`
**Issue:** The docstring acknowledges this (`The pin arg is accepted for
manifest dispatch symmetry`), but the name lies. A reader reasonably
expects `probe_gpio_pin(17)` to verify pin 17 is usable. Today it returns
True if `RPi.GPIO` is importable regardless of whether the pin is
exported, in use, or physically connected.
**Fix:** Rename to `probe_gpio_module_available` (more honest) or
actually probe the pin state via `/sys/class/gpio/` or `gpiod`. The
former is cheaper and matches the current behaviour.

### IN-04: `INA226Collector.to_reading` passes `sensor_type="power"` string with `# type: ignore[arg-type]`

**File:** `src/shitbox/collectors/power.py:95-99`
**Issue:** `sensor_type` is typed as `SensorType` enum. Passing the raw
string works at runtime because `SensorType` inherits from `str`, but
the `# type: ignore[arg-type]` admits a type violation that can be
avoided by just using the enum member. Every other collector in this
phase uses the enum (see `base.py` via `Reading.from_*` helpers).
**Fix:** `sensor_type=SensorType.POWER`, drop the ignore.

### IN-05: `_build_reprobe_callbacks` — `lambda lbl=lbl: ...` uses the same name for default arg and outer var

**File:** `src/shitbox/events/engine.py:787-789`
**Issue:** All other lambdas in the loop use a distinct default arg name
(`a=addr`, `s=sid`, `p=path`, etc.) which makes the late-binding capture
intent obvious. The audio branch uses `lambda lbl=lbl:` where both names
are `lbl`. It's functionally correct — the RHS is evaluated at lambda
creation — but it's visually identical to the late-binding bug pattern
it's guarding against. A reviewer scanning quickly could miss it.
**Fix:** Match the other branches: `label: str = dev.label; cbs[dev.role]
= cast(..., lambda l=label: probes.probe_audio_label(l))`. Or rename the
outer: `lbl_val = dev.label; ... lambda lbl=lbl_val: ...`.

---

_Reviewed: 2026-04-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
