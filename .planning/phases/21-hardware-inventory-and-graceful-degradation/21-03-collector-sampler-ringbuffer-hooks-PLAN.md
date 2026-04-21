---
phase: 21
plan: 03
type: execute
wave: 2
depends_on: [1]
files_modified:
  - src/shitbox/collectors/base.py
  - src/shitbox/collectors/environment.py
  - src/shitbox/events/sampler.py
  - src/shitbox/capture/ring_buffer.py
  - tests/collectors/test_base_hardware_hook.py
  - tests/collectors/test_environment_simplified_retry.py
  - tests/test_i2c_recovery.py
  - tests/test_ffmpeg_stall.py
autonomous: true
requirements: [HW-02, HW-04]
estimated_loc: 380
must_haves:
  truths:
    - "BaseCollector has an optional `role` kwarg; when set, successful reads call hw_state.report_present and read-errors / setup-failures call hw_state.report_missing"
    - "EnvironmentCollector.setup() attempts init once (no internal retry loop); the supervisor owns the retry cadence"
    - "HighRateSampler reports PRESENT only on successful sample (Pitfall 2) — not on _i2c_bus_reset() success"
    - "HighRateSampler reports DEGRADED on i2c_bus_lockup_detected and MISSING on i2c_max_resets_exceeded (before the reboot call)"
    - "VideoRingBuffer reports MISSING on video_device_missing, DEGRADED on ffmpeg_stalled, PRESENT on successful ffmpeg start"
    - "None of these hooks alter existing recovery/reboot/reset logic — they are observational only"
  artifacts:
    - path: src/shitbox/collectors/base.py
      provides: "Optional role kwarg + _report_present / _report_missing hooks wired into _run_loop and start()"
      contains: "self.role = role"
    - path: src/shitbox/collectors/environment.py
      provides: "setup() reduced to single attempt; internal retry loop removed"
      contains: "environment_sensor_initialised"
    - path: src/shitbox/events/sampler.py
      provides: "Observational hw_state calls at 3 existing log points"
      contains: "hw_state.report_present"
    - path: src/shitbox/capture/ring_buffer.py
      provides: "Observational hw_state calls at 3 existing log points + accept role kwarg"
      contains: "self.role"
  key_links:
    - from: "BaseCollector._run_loop success branch"
      to: "hw_state.report_present(role)"
      via: "_report_present() helper with role guard"
      pattern: "self\\._report_present\\(\\)"
    - from: "HighRateSampler._sample_loop"
      to: "hw_state (present on successful read; degraded on lockup; missing on max-resets)"
      via: "hw_state.report_* calls inline at existing log sites"
      pattern: "hw_state\\.report_(present|degraded|missing)"
    - from: "VideoRingBuffer._health_monitor + _start_ffmpeg"
      to: "hw_state"
      via: "report_missing / report_degraded / report_present"
      pattern: "hw_state\\.report_"
---

<objective>
Wire observational HardwareState reporting into the three collector tiers that
don't already own their recovery path:

1. Every 1 Hz BaseCollector subclass (via the template method) — report PRESENT
   on successful read, MISSING on read error or setup failure.
2. EnvironmentCollector — simplify `setup()` to a single attempt; the supervisor
   (Plan 02) now owns the retry cadence, so the 5×1s inline retry becomes dead
   weight that delays boot by 5s on the BME680 cold-boot case (Pitfall 7).
3. HighRateSampler (LSM6DSOX IMU) — report at 3 existing log sites, without
   altering the 9-clock reset ladder or reboot semantics (Pitfall 2, Pitfall 6).
4. VideoRingBuffer (front + cabin cameras) — report at 3 existing log sites,
   without altering ffmpeg stall detection / restart logic.

This plan modifies files disjoint from Plan 02, so both run in Wave 2. No
engine wiring here — Plan 05 passes `role=...` kwargs and orchestrates startup.

Purpose: every collector that loses hardware tells HardwareState about it, so
the supervisor has something to observe. No recovery-logic rewrites (Pitfall 1
in the anti-pattern list).

Output:
- `src/shitbox/collectors/base.py` — role kwarg + two _report_* helpers + 3 hook calls
- `src/shitbox/collectors/environment.py` — single-attempt setup + pass role to super
- `src/shitbox/events/sampler.py` — 3 observational calls
- `src/shitbox/capture/ring_buffer.py` — role kwarg + 3 observational calls
- New / extended tests covering each hook
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-01-manifest-state-probes-PLAN.md
@src/shitbox/collectors/base.py
@src/shitbox/collectors/environment.py
@src/shitbox/events/sampler.py
@src/shitbox/capture/ring_buffer.py
@CLAUDE.md

<interfaces>
From src/shitbox/hardware/state.py (Plan 01):
```python
# Only these three functions are consumed here:
hw_state.report_present(role: str) -> Optional[DeviceState]
hw_state.report_missing(role: str) -> Optional[DeviceState]
hw_state.report_degraded(role: str) -> Optional[DeviceState]
```

New or modified in this plan:
```python
# BaseCollector — kwarg addition
class BaseCollector(ABC, Generic[T]):
    def __init__(
        self,
        name: str,
        sample_rate_hz: float,
        callback: Optional[Callable[[Reading], None]] = None,
        role: Optional[str] = None,      # NEW
    ): ...

# VideoRingBuffer — kwarg addition
class VideoRingBuffer:
    def __init__(
        self,
        device: str,
        # ... existing args ...
        role: str = "camera_front",      # NEW — "camera_front" or "camera_cabin"
    ): ...
```

Existing behaviour that MUST NOT change:
- `BaseCollector._max_errors = 10` — safety valve stays.
- `HighRateSampler._i2c_bus_reset()` — 9-clock bit-bang recovery ladder untouched.
- `HighRateSampler._force_reboot()` — still called after `i2c_max_resets_exceeded` (the new report_missing call goes BEFORE the reboot so the supervisor can speak the terminal transition).
- `VideoRingBuffer._check_stall`, `_kill_current`, `_start_ffmpeg` logic — untouched.
- Existing `buzzer.beep_*` and `speaker.speak_i2c_lockup` calls stay (Pitfall 6 — sampler keeps the during-recovery TTS; supervisor speaks terminal only).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: BaseCollector role hook + EnvironmentCollector simplification</name>
  <files>src/shitbox/collectors/base.py, src/shitbox/collectors/environment.py, tests/collectors/test_base_hardware_hook.py, tests/collectors/test_environment_simplified_retry.py</files>
  <read_first>
    - src/shitbox/collectors/base.py (full file — __init__ signature at ~line 28, start() at ~85, _run_loop at ~117-160)
    - src/shitbox/collectors/environment.py (full file — setup() at lines 38-80, module constants at lines 11-12)
    - tests/collectors/ (directory — check existing test style; if `__init__.py` missing, create it)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §base.py (lines 325-403) and §environment.py (lines 405-448)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Pitfall 7 (BME680 double-retry problem)
  </read_first>
  <behavior>
    - `BaseCollector.__init__` accepts `role: Optional[str] = None` after `callback`. Stores `self.role = role`.
    - Two private helpers on BaseCollector: `_report_present()` and `_report_missing()`. Each imports `hw_state` locally (to avoid circular import at collector import time), no-ops if `self.role is None`.
    - `_run_loop` success branch (after `self._error_count = 0`) calls `self._report_present()`.
    - `_run_loop` failure branch (first line of the except block, before the existing `log.error`) calls `self._report_missing()`.
    - `start()` setup-failure branch (inside the existing `except` around `self.setup()`) calls `self._report_missing()` BEFORE the existing `raise`. The `raise` stays — engine's per-collector try/except (Plan 05) is what implements HW-05.
    - `_max_errors` safety valve is unchanged. First OSError triggers report_missing (not the 10th).
    - `EnvironmentCollector.__init__` passes `role="environment"` to `super().__init__`.
    - `EnvironmentCollector.setup()` is reduced to a single attempt: import busio/board/Adafruit_BME680_I2C, init, log `environment_sensor_initialised`. No for-loop, no `time.sleep(_BME680_INIT_RETRY_DELAY_S)`. On failure: log `environment_setup_error` + raise (matches existing final-failure branch; supervisor's backoff ladder owns the retry).
    - Module constants `_BME680_INIT_RETRIES` and `_BME680_INIT_RETRY_DELAY_S` deleted.
  </behavior>
  <action>
Edit `src/shitbox/collectors/base.py`:

1. Add `role: Optional[str] = None` kwarg to `__init__` (after the existing `callback` kwarg). Store: `self.role = role`.

2. Add two private methods just above `_run_loop`:

```python
def _report_present(self) -> None:
    """Report PRESENT to HardwareState. No-op if no role wired."""
    if self.role:
        from shitbox.hardware import state as hw_state  # local import — avoids cycles
        hw_state.report_present(self.role)

def _report_missing(self) -> None:
    """Report MISSING to HardwareState. No-op if no role wired."""
    if self.role:
        from shitbox.hardware import state as hw_state
        hw_state.report_missing(self.role)
```

3. In `_run_loop`, after the existing `self._error_count = 0` (success branch, around line 129), add: `self._report_present()`.

4. In `_run_loop`, as the first statement inside the `except Exception as e:` block (around line 136, before the existing `self._error_count += 1`), add: `self._report_missing()`.

5. In `start()`, inside the existing `try/except` around `self.setup()` (around line 96), add `self._report_missing()` before the `raise`.

Do not change `_max_errors`, `_error_count` semantics, or any log call. Do not remove the `raise` in start().

Edit `src/shitbox/collectors/environment.py`:

1. Delete module constants `_BME680_INIT_RETRIES` and `_BME680_INIT_RETRY_DELAY_S` at the top of the file (lines 11-12 per the analog).
2. In `__init__`, add `role="environment"` to the `super().__init__` call.
3. Replace the entire body of `setup()` with the single-attempt version:

```python
def setup(self) -> None:
    """Initialise BME680 hardware. Single attempt — supervisor's exponential
    backoff ladder owns retry cadence (Plan 21-02), which also resolves the
    documented boot-timing race without the 5s boot delay that the prior
    inline 5×1s loop introduced."""
    try:
        import board
        import busio
        from adafruit_bme680 import Adafruit_BME680_I2C
    except ImportError as e:
        log.error("environment_import_failed", error=str(e))
        raise
    try:
        self._i2c = busio.I2C(board.SCL, board.SDA)
        self._sensor = Adafruit_BME680_I2C(self._i2c, address=self.config.address)
        log.info("environment_sensor_initialised")
    except Exception as e:
        log.error("environment_setup_error", error=str(e))
        raise
```

Keep `self._i2c = None`, `self._sensor = None` in `__init__` if they already exist; the existing `read()` path (checking for None) is untouched.

Create `tests/collectors/__init__.py` if missing (empty package marker).

Create `tests/collectors/test_base_hardware_hook.py`:

Build a tiny `FakeCollector(BaseCollector[int])` with:
- `setup()` that can be patched to raise
- `read()` that can be patched to return an int or raise
- `to_reading(data)` that returns a minimal dummy Reading

Tests:
- `test_no_role_makes_hooks_noop` — instantiate with `role=None`; call `_report_present()` and `_report_missing()`; assert `hw_state.snapshot()` stays empty.
- `test_report_present_on_successful_read` — instantiate with `role="env_test"`; seed `hw_state.initialise({"env_test": "best_effort"})`; drive one `read()` cycle (test-inject by calling the single iteration logic or bypassing the thread — mirror existing BaseCollector tests if any). Assert `snapshot()["env_test"].state == PRESENT`.
- `test_report_missing_on_read_error` — patch read to raise OSError; assert MISSING + consecutive_misses=1.
- `test_report_missing_on_setup_failure` — patch setup to raise; assert `start()` raises (existing behaviour) AND state reports MISSING before the raise.
- `test_max_errors_safety_valve_unchanged` — drive 10 consecutive read errors; assert `_running` flips False and state reports MISSING (first error already marked it, but test confirms).
- `test_role_attribute_set` — `FakeCollector(name="t", sample_rate_hz=1.0, role="foo").role == "foo"`.

Use the autouse `_clear_hw_state` fixture from `tests/hardware/conftest.py` (Plan 01). Add `import` of that via the package — or create a sibling `tests/collectors/conftest.py` that imports the clear helper and applies it autouse to this directory only. Prefer the sibling conftest to avoid cross-directory fixture leakage.

Create `tests/collectors/test_environment_simplified_retry.py`:

- `test_setup_single_attempt_on_success` — patch `busio.I2C` + `Adafruit_BME680_I2C`; call `setup()`; assert it returns without iteration (monkeypatch `time.sleep` and assert it was NOT called during setup).
- `test_setup_raises_immediately_on_failure` — patch `Adafruit_BME680_I2C` to raise; assert `setup()` raises and `time.sleep` was NOT called.
- `test_bme680_constants_removed` — `import shitbox.collectors.environment as env; assert not hasattr(env, "_BME680_INIT_RETRIES"); assert not hasattr(env, "_BME680_INIT_RETRY_DELAY_S")`.
- `test_role_passed_to_base` — `env_collector = EnvironmentCollector(config); assert env_collector.role == "environment"`.

Ruff line length 100. Full type annotations. Preserve all existing structlog keyword-arg logging.
  </action>
  <verify>
    <automated>pytest tests/collectors/test_base_hardware_hook.py tests/collectors/test_environment_simplified_retry.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "role: Optional\[str\] = None" src/shitbox/collectors/base.py`
    - `grep -q "self.role = role" src/shitbox/collectors/base.py`
    - `grep -q "def _report_present" src/shitbox/collectors/base.py`
    - `grep -q "def _report_missing" src/shitbox/collectors/base.py`
    - `grep -c "self._report_present()" src/shitbox/collectors/base.py` outputs `1` (single success-branch call)
    - `grep -c "self._report_missing()" src/shitbox/collectors/base.py` outputs `2` (run_loop except + start setup-fail)
    - `grep -q "role=\"environment\"" src/shitbox/collectors/environment.py`
    - `! grep -q "_BME680_INIT_RETRIES" src/shitbox/collectors/environment.py`
    - `! grep -q "_BME680_INIT_RETRY_DELAY_S" src/shitbox/collectors/environment.py`
    - `! grep -q "time.sleep" src/shitbox/collectors/environment.py` (no retry sleep in setup)
    - `pytest tests/collectors/test_base_hardware_hook.py tests/collectors/test_environment_simplified_retry.py -x -q` exits 0
    - `pytest tests/collectors/ -x -q` exits 0 (existing collector tests still green)
    - `ruff check src/shitbox/collectors/base.py src/shitbox/collectors/environment.py` exits 0
    - `mypy src/shitbox/collectors/base.py src/shitbox/collectors/environment.py` exits 0
  </acceptance_criteria>
  <done>
    BaseCollector's role hook is in place; `_max_errors` behaviour unchanged; EnvironmentCollector's setup is a single attempt, constants removed, role propagated. All new tests pass; all existing collector tests still pass (no regression).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: HighRateSampler + VideoRingBuffer observational hooks</name>
  <files>src/shitbox/events/sampler.py, src/shitbox/capture/ring_buffer.py, tests/test_i2c_recovery.py, tests/test_ffmpeg_stall.py</files>
  <read_first>
    - src/shitbox/events/sampler.py (lines 160-230 — `_sample_loop` success branch, `i2c_bus_lockup_detected` log site, `i2c_max_resets_exceeded` log site, `_force_reboot` call)
    - src/shitbox/capture/ring_buffer.py (lines 760-920 — `_health_monitor`, `_check_stall`, `_start_ffmpeg` function, `video_device_missing` log site)
    - tests/test_i2c_recovery.py (full file — see what scenarios are already covered, extend rather than duplicate)
    - tests/test_ffmpeg_stall.py (full file — see the existing stall detection test fixture)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §sampler.py (lines 451-499) and §ring_buffer.py (lines 503-552)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Pitfall 2 (PRESENT only on successful read) and §Pitfall 6 (don't duplicate sampler's during-recovery TTS)
  </read_first>
  <behavior>
    - Sampler gains `self.role = "imu"` in `__init__` and `from shitbox.hardware import state as hw_state` at module top.
    - In `_sample_loop` at the success branch (after `self._consecutive_failures = 0`), a new line calls `hw_state.report_present(self.role)`. This is the ONLY place PRESENT is reported (Pitfall 2 — never from `_i2c_bus_reset` success alone).
    - At the `log.warning("i2c_bus_lockup_detected", ...)` call, a new line calls `hw_state.report_degraded(self.role)`.
    - At the `log.critical("i2c_max_resets_exceeded", ...)` call, a new line calls `hw_state.report_missing(self.role)` BEFORE `self._force_reboot()` so the supervisor (if it's still ticking) can observe and speak the terminal transition before the reboot yanks the rug.
    - No change to `buzzer.beep_i2c_lockup`, `speaker.speak_i2c_lockup`, the reset ladder, or `_force_reboot` (Pitfall 6).
    - VideoRingBuffer gains `role: str = "camera_front"` kwarg in `__init__` and `self.role = role` assignment. Engine plan (05) passes `role="camera_cabin"` for the second instance.
    - `from shitbox.hardware import state as hw_state` added to the imports.
    - In `_health_monitor`, at the `video_device_missing` log site, add `hw_state.report_missing(self.role)`.
    - In `_health_monitor`, at the `video_ring_buffer_ffmpeg_stalled` log site, add `hw_state.report_degraded(self.role)`.
    - In `_start_ffmpeg`, after the process is confirmed running (locate the `log.info("ffmpeg_started", ...)` or equivalent), add `hw_state.report_present(self.role)`.
  </behavior>
  <action>
Edit `src/shitbox/events/sampler.py`:

1. At the top of the file with the other imports, add:
```python
from shitbox.hardware import state as hw_state
```

2. In `HighRateSampler.__init__`, add `self.role = "imu"` near the other self-attribute initialisations (e.g. after `self._consecutive_failures = 0` is initialised).

3. Locate `_sample_loop`. Right after the existing line `self._consecutive_failures = 0` (inside the success branch at approximately line 178), add:
```python
hw_state.report_present(self.role)
```

4. Locate the `log.warning("i2c_bus_lockup_detected", ...)` call (approximately line 188). Immediately after the log call (or inside the same block, before any other work), add:
```python
hw_state.report_degraded(self.role)
```

5. Locate the `log.critical("i2c_max_resets_exceeded", ...)` call (approximately line 213). Immediately after the log call, BEFORE `self._force_reboot()`, add:
```python
hw_state.report_missing(self.role)
```

Do NOT change `buzzer.beep_i2c_lockup()`, `speaker.speak_i2c_lockup()`, the reset ladder logic, `_i2c_bus_reset`, or `_force_reboot`. Do NOT remove any existing log calls. These 3 new lines are pure additions.

Edit `src/shitbox/capture/ring_buffer.py`:

1. At the top, add:
```python
from shitbox.hardware import state as hw_state
```

2. In `VideoRingBuffer.__init__`, add a new kwarg `role: str = "camera_front"` (append to the existing signature). Store `self.role = role`.

3. In `_health_monitor`, at the `log.warning("video_device_missing", ...)` site (approximately line 881-886), add:
```python
hw_state.report_missing(self.role)
```

4. At the `log.warning("video_ring_buffer_ffmpeg_stalled", ...)` site (approximately line 899-904), add:
```python
hw_state.report_degraded(self.role)
```

5. Locate `_start_ffmpeg`. Find the point where the process is confirmed running (e.g. immediately after the final success log — grep for `log.info("ffmpeg_started"` or `log.info("video_ring_buffer_started"`). Add:
```python
hw_state.report_present(self.role)
```

Do NOT change the ffmpeg argv, `_check_stall`, `_kill_current`, `_cleanup_buffer`, or the existing stall-timeout constant.

Edit `tests/test_i2c_recovery.py`:

Add (not replace — existing tests must still pass):

- `test_successful_sample_reports_present` — mock LSM6DSOX read to return a sample; drive one iteration of `_sample_loop`; assert `hw_state.snapshot()["imu"].state == PRESENT`. (Use the autouse `_clear_hw_state` fixture — if not wired from the `tests/hardware/conftest.py`, add a local conftest in `tests/` or import `state.clear_state()` at test top/bottom.)
- `test_i2c_lockup_reports_degraded` — drive enough OSErrors to trip `i2c_bus_lockup_detected`; assert state is DEGRADED. Verify that the existing reset ladder still runs (mock `_i2c_bus_reset` and assert it was called).
- `test_i2c_max_resets_reports_missing_before_reboot` — drive enough resets to hit `i2c_max_resets_exceeded`; mock `_force_reboot` to record it was called; assert state is MISSING AND `_force_reboot` was called (order: report_missing then reboot).

Edit `tests/test_ffmpeg_stall.py`:

Add:

- `test_video_device_missing_reports_missing` — construct a `VideoRingBuffer` with `role="camera_front"`, `hw_state.initialise({"camera_front": "critical"})`, patch `os.path.exists(self.device)` to return False, drive one `_health_monitor` iteration (existing test file already has a pattern for this). Assert `hw_state.snapshot()["camera_front"].state == MISSING`.
- `test_stall_reports_degraded` — trigger the stall detection path (existing test does this); assert `hw_state.snapshot()["camera_front"].state == DEGRADED`.
- `test_successful_ffmpeg_start_reports_present` — patch out the subprocess.Popen; drive `_start_ffmpeg`; assert state becomes PRESENT. Mirror the existing `_start_ffmpeg` test pattern in the file.

If `tests/test_i2c_recovery.py` or `tests/test_ffmpeg_stall.py` doesn't already import / use `hw_state.clear_state()`, add a `@pytest.fixture(autouse=True)` at the module top that calls `state.clear_state()` before each test so HardwareState is fresh.

Ruff line length 100. Zero logic changes to existing sampler or ring_buffer behaviour — every new line is a `hw_state.report_*` call inserted next to an existing log call.
  </action>
  <verify>
    <automated>pytest tests/test_i2c_recovery.py tests/test_ffmpeg_stall.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "self.role = \"imu\"" src/shitbox/events/sampler.py`
    - `grep -q "from shitbox.hardware import state as hw_state" src/shitbox/events/sampler.py`
    - `grep -q "hw_state.report_present(self.role)" src/shitbox/events/sampler.py`
    - `grep -q "hw_state.report_degraded(self.role)" src/shitbox/events/sampler.py`
    - `grep -q "hw_state.report_missing(self.role)" src/shitbox/events/sampler.py`
    - `grep -q "i2c_max_resets_exceeded" src/shitbox/events/sampler.py` (existing log still present)
    - `grep -q "self._force_reboot" src/shitbox/events/sampler.py` (reboot call still present)
    - `grep -q "speak_i2c_lockup" src/shitbox/events/sampler.py` (sampler's during-recovery TTS still present — Pitfall 6)
    - `grep -q "role: str = \"camera_front\"" src/shitbox/capture/ring_buffer.py`
    - `grep -q "self.role = role" src/shitbox/capture/ring_buffer.py`
    - `grep -q "hw_state.report_missing(self.role)" src/shitbox/capture/ring_buffer.py`
    - `grep -q "hw_state.report_degraded(self.role)" src/shitbox/capture/ring_buffer.py`
    - `grep -q "hw_state.report_present(self.role)" src/shitbox/capture/ring_buffer.py`
    - `pytest tests/test_i2c_recovery.py -x -q` exits 0 (existing + new tests pass)
    - `pytest tests/test_ffmpeg_stall.py -x -q` exits 0 (existing + new tests pass)
    - `pytest tests/test_i2c_recovery.py::test_i2c_max_resets_reports_missing_before_reboot -x -q` exits 0 (HW-04 observational path)
    - `pytest tests/test_ffmpeg_stall.py::test_video_device_missing_reports_missing -x -q` exits 0 (HW-04 USB camera)
    - `ruff check src/shitbox/events/sampler.py src/shitbox/capture/ring_buffer.py` exits 0
  </acceptance_criteria>
  <done>
    Sampler and ring_buffer have 3 observational `hw_state.report_*` calls each, at existing log sites. Zero changes to recovery/reset/reboot logic. Existing sampler's `speak_i2c_lockup` stays (Pitfall 6). Tests confirm PRESENT-on-successful-sample (Pitfall 2), DEGRADED on lockup, MISSING before reboot, and the USB camera parallels.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Collector read loop → HardwareState | In-process; hook calls are GIL-atomic rebinds on the `_state` dict (Plan 01 guarantee). |
| sampler.py / ring_buffer.py → HardwareState | Same — in-process module-level writes. Observational only: never alters recovery behaviour. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-03-01 | Denial of Service | Hook calls slowing the 100 Hz IMU loop | mitigate | Each hook is a single dict-rebind + optional structlog write. Measured ~microsecond overhead; well under 100 Hz budget (10 ms). No blocking calls, no I/O. |
| T-21-03-02 | Tampering | Hook being removed or reordered by future edits | mitigate | Acceptance criteria grep for each `hw_state.report_*` call; CI runs the tests. |
| T-21-03-03 | Information Disclosure | — | N/A | No new log fields expose secrets; device roles/paths already in config.yaml. |
| T-21-03-04 | Denial of Service | Reducing BME680 internal retry causes cold-boot MISSING for 5s | accept | This is the intended behaviour. The supervisor (Plan 02) picks up retry at T+5s; BME680 is best_effort (D-05) so the 5s MISSING window is silent per cadence rules except for the canonical "environment sensor isn't responding" speak — which is desired for the crew. |
| T-21-03-05 | Elevation of Privilege | — | N/A | No new I/O; in-process only. |

**ASVS L1:** V5 Input Validation partial — `role` kwarg is a controlled string supplied by the engine plan (05) from the manifest; no user input path. No other categories apply.
</threat_model>

<verification>
End of plan checks:

- `pytest tests/collectors/ tests/test_i2c_recovery.py tests/test_ffmpeg_stall.py -x -q` — new hooks tests + existing recovery tests pass.
- `pytest` — full suite passes. These hooks are strictly additive.
- `grep -r "hw_state.report_" src/shitbox/` — confirms 3 sampler + 3 ring_buffer + 2 base + 0 collector-specific-overrides = 8 report_* usages.
- No reduction in `pytest tests/test_i2c_recovery.py` count — existing assertions preserved, new ones added.
- `ruff check src/shitbox/collectors src/shitbox/events/sampler.py src/shitbox/capture/ring_buffer.py` exits 0.
- No engine changes — Plan 05 owns passing `role=` kwargs and graceful startup orchestration.
</verification>

<success_criteria>
- HW-02 reporting pathway complete: every collector (1 Hz base + IMU + cameras) now writes into HardwareState. The supervisor (Plan 02) has something to observe.
- HW-04 observational path intact: sampler reports DEGRADED mid-recovery, MISSING on ladder give-up (before reboot); ring_buffer reports MISSING on device-missing, DEGRADED on stall.
- BME680 cold-boot delay fixed (Pitfall 7): setup() is a single attempt. Supervisor's 5s backoff is now the retry home.
- Pitfall 2 respected: sampler reports PRESENT only from a successful sample read, not from `_i2c_bus_reset` success.
- Pitfall 6 respected: sampler's during-recovery `speak_i2c_lockup` stays; terminal MISSING/RESTORED speak lives in the supervisor only.
- BaseCollector `_max_errors=10` safety valve unchanged.
</success_criteria>

<output>
After completion, create `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-03-SUMMARY.md` covering:
- Files modified
- Hook locations (file:line for each of the 3 sampler + 3 ring_buffer + 2 base inserts)
- Confirmation that the existing `tests/test_i2c_recovery.py` count increased (N new assertions added)
- Confirmation that `_BME680_INIT_RETRIES` is removed
</output>
