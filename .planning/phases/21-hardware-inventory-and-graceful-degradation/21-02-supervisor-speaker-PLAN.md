---
phase: 21
plan: 02
type: execute
wave: 2
depends_on: [1]
files_modified:
  - src/shitbox/hardware/supervisor.py
  - src/shitbox/capture/speaker.py
  - tests/hardware/test_hardware_supervisor.py
  - tests/test_speaker_alerts.py
autonomous: true
requirements: [HW-03, HW-04]
estimated_loc: 420
must_haves:
  truths:
    - "HardwareSupervisor daemon thread runs a 1 Hz tick loop with start() / stop() lifecycle"
    - "Boot probe populates HardwareState for every manifest device before the tick loop starts"
    - "Critical-tier MISSING re-speaks every 30s via _last_nag dict; important speaks once per transition; best_effort is log-only except 'environment'"
    - "Supervisor tick calls reprobe callback when now >= next_retry_at; success flips to PRESENT + speak_hardware_restored; failure calls report_missing (bumps ladder)"
    - "speak_hardware_missing / speak_hardware_restored honour tier gating and speaker _should_alert()"
    - "Tick loop never raises — exceptions logged + continue"
  artifacts:
    - path: src/shitbox/hardware/supervisor.py
      provides: "HardwareSupervisor service class"
      contains: "class HardwareSupervisor"
    - path: src/shitbox/capture/speaker.py
      provides: "10 new cached hardware TTS lines + speak_hardware_missing / _restored"
      contains: "speak_hardware_missing"
    - path: tests/hardware/test_hardware_supervisor.py
      provides: "Tick-loop + cadence + backoff + canonical-BME680 tests"
  key_links:
    - from: "HardwareSupervisor._tick"
      to: "shitbox.hardware.state.report_present/missing + speaker.speak_hardware_*"
      via: "supervisor reads state.snapshot(), dispatches per-tier"
      pattern: "hw_state\\.report_present"
    - from: "speaker._CACHED_MESSAGES"
      to: "Piper pre-cache warm loop"
      via: "10 new keys auto-cache at speaker.init()"
      pattern: "hw_imu_missing"
---

<objective>
Build the HardwareSupervisor daemon thread and the 10 cached hardware-event
TTS lines. Together they implement HW-03 (per-tier alert cadence — critical
re-nag every 30s, important once per transition, best_effort log-only except
environment) and HW-04 (exponential backoff re-adoption, restored TTS).

The supervisor is observational — it never duplicates the sampler's existing
recovery logic (Pitfall 6). It reads HardwareState, dispatches callbacks when
a MISSING device's `next_retry_at` elapses, and speaks on terminal transitions
(MISSING became terminal, RESTORED).

Plan 03 (collector hooks) and this plan modify disjoint files, so both run
in Wave 2.

Purpose: one place to reason about alert cadence + retry timing. No engine
wiring here (Plan 05 owns that).

Output:
- `src/shitbox/hardware/supervisor.py` — HardwareSupervisor class
- 10 new keys in `_CACHED_MESSAGES` + `speak_hardware_missing` / `speak_hardware_restored` in `speaker.py`
- `tests/hardware/test_hardware_supervisor.py` — 8+ tests covering tier cadence, backoff, canonical BME680 case
- New tests added to `tests/test_speaker_alerts.py` for the hardware speak functions
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
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-01-manifest-state-probes-PLAN.md
@src/shitbox/sync/batch_sync.py
@src/shitbox/display/oled.py
@src/shitbox/capture/speaker.py
@CLAUDE.md

<interfaces>
From src/shitbox/hardware/state.py (Plan 01):
```python
# See Plan 01 interfaces. Key functions used here:
hw_state.initialise(devices: Dict[str, str]) -> None      # called from supervisor.start()
hw_state.snapshot() -> Dict[str, DeviceStatus]            # called from supervisor._tick()
hw_state.report_present(role: str) -> Optional[DeviceState]
hw_state.report_missing(role: str) -> Optional[DeviceState]
```

From src/shitbox/utils/config.py (Plan 01):
```python
HardwareManifestConfig.devices: List[HardwareDeviceConfig]
HardwareDeviceConfig.role / .criticality / .bus / .address / .path / etc.
```

New from this plan (src/shitbox/hardware/supervisor.py):
```python
class HardwareSupervisor:
    TICK_INTERVAL_SECONDS: float = 1.0
    CRITICAL_RENAG_SECONDS: float = 30.0

    def __init__(
        self,
        manifest: HardwareManifestConfig,
        reprobe_callbacks: Dict[str, Callable[[], bool]],
    ) -> None: ...
    def start(self) -> None: ...  # initialise state, probe all, spawn thread
    def stop(self) -> None: ...
    def _probe_all(self) -> None: ...       # boot probe
    def _tick(self) -> None: ...            # one iteration
```

New from this plan (src/shitbox/capture/speaker.py additions):
```python
def speak_hardware_missing(role: str, tier: str) -> None: ...
def speak_hardware_restored(role: str, tier: str) -> None: ...

# 10 new entries in _CACHED_MESSAGES — keys from UI-SPEC §Copywriting:
#   hw_imu_missing / _restored
#   hw_camera_front_missing / _restored
#   hw_power_missing / _restored
#   hw_gps_missing / _restored
#   hw_env_missing / _restored
```

Per UI-SPEC copy (§Copywriting → TTS lines):
- hw_imu_missing: "Michael, I've lost the IMU. Event detection is down."
- hw_imu_restored: "IMU back with me, Michael."
- hw_camera_front_missing: "Michael, the front camera is offline. I can't record."
- hw_camera_front_restored: "Front camera restored, Michael."
- hw_power_missing: "Michael, I've lost the power monitor."
- hw_power_restored: "Power monitor back, Michael."
- hw_gps_missing: "Michael, I've lost GPS."
- hw_gps_restored: "GPS fix restored, Michael."
- hw_env_missing: "Environment sensor isn't responding, Michael."
- hw_env_restored: "Environment sensor back, Michael."
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: speaker.py TTS lines + speak_hardware_* functions</name>
  <files>src/shitbox/capture/speaker.py, tests/test_speaker_alerts.py</files>
  <read_first>
    - src/shitbox/capture/speaker.py (full file — especially `_CACHED_MESSAGES` dict at lines 47-66 and the `speak_*` function pattern at line 444)
    - tests/test_speaker_alerts.py (full file — how existing speak functions are asserted, mock patterns)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md §Copywriting (TTS lines table) — copy these strings verbatim
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §speaker.py (lines 670-719)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Code Examples (New TTS lines, lines 737-777)
  </read_first>
  <behavior>
    - `_CACHED_MESSAGES` dict gains exactly 10 new keys (5 missing + 5 restored pairs) with the UI-SPEC strings verbatim.
    - `speak_hardware_missing(role, tier)` honours `_should_alert()` gate, returns silently if tier == "best_effort" AND role != "environment", otherwise `_enqueue(_CACHED_MESSAGES.get(f"hw_{role}_missing", f"{role} offline, Michael."))`.
    - `speak_hardware_restored(role, tier)` mirrors the missing function.
    - Piper warm-cache at `speaker.init()` automatically renders the 10 new WAVs — no extra plumbing needed (the existing `_warm_cache()` iterates `_CACHED_MESSAGES`).
    - Tests prove each tier gating rule and that the correct cache key is looked up for the 5 supported roles.
  </behavior>
  <action>
Edit `src/shitbox/capture/speaker.py`:

1. Locate the `_CACHED_MESSAGES` dict (around lines 47-66). Extend it with the 10 keys from the interfaces block above, preserving dictionary style (one key per line, trailing comma). Keep UK English where the phrase calls for it (UI-SPEC uses "isn't" not "is not"; keep those exact strings).

2. Near the existing `speak_*` functions (grep for `def speak_service_recovered` — add after it), add:

```python
def speak_hardware_missing(role: str, tier: str) -> None:
    """Announce a device going MISSING. Tier governs whether we speak at all at
    this transition — best_effort is log-only unless role == 'environment'
    (the canonical BME680 acceptance case). Critical re-nag cadence is
    HardwareSupervisor's responsibility; this function always speaks when gated."""
    if not _should_alert():
        return
    if tier == "best_effort" and role != "environment":
        return
    key = f"hw_{role}_missing"
    text = _CACHED_MESSAGES.get(key, f"{role} offline, Michael.")
    _enqueue(text)


def speak_hardware_restored(role: str, tier: str) -> None:
    """Announce a device recovering. Same tier gating as speak_hardware_missing."""
    if not _should_alert():
        return
    if tier == "best_effort" and role != "environment":
        return
    key = f"hw_{role}_restored"
    text = _CACHED_MESSAGES.get(key, f"{role} restored, Michael.")
    _enqueue(text)
```

Do NOT change `_enqueue`, `_should_alert`, `_warm_cache`, `init`, or any other existing function. New keys integrate automatically at warm-cache time.

Edit `tests/test_speaker_alerts.py`:

Add tests (matching the file's existing style — mock `_enqueue` or assert via the existing mock pattern used for other speak functions):

- `test_speak_hardware_missing_critical_enqueues` — patch `_enqueue` and `_should_alert` (return True), call `speak_hardware_missing("imu", "critical")`, assert `_enqueue` called once with the hw_imu_missing text.
- `test_speak_hardware_missing_important_enqueues` — same for `("power", "important")` and `("gps", "important")`.
- `test_speak_hardware_missing_best_effort_silent_except_env` — `("magnetometer", "best_effort")` → `_enqueue` NOT called; `("environment", "best_effort")` → `_enqueue` called with hw_env_missing text.
- `test_speak_hardware_missing_unknown_role_uses_fallback` — `("weirdrole", "critical")` → `_enqueue` called with "weirdrole offline, Michael."
- `test_speak_hardware_restored_tier_gating` — mirror the missing gating tests for restored.
- `test_speak_hardware_missing_respects_should_alert` — patch `_should_alert` to return False; `_enqueue` must NOT be called regardless of tier.
- `test_cached_messages_contains_10_hardware_keys` — assert all 10 keys exist in `_CACHED_MESSAGES` with non-empty strings.

Ruff line length 100. Match the structlog-free (speaker.py uses its own logger wrapper — mirror the surrounding style).
  </action>
  <verify>
    <automated>pytest tests/test_speaker_alerts.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "hw_imu_missing" src/shitbox/capture/speaker.py`
    - `grep -q "hw_imu_restored" src/shitbox/capture/speaker.py`
    - `grep -q "hw_camera_front_missing" src/shitbox/capture/speaker.py`
    - `grep -q "hw_camera_front_restored" src/shitbox/capture/speaker.py`
    - `grep -q "hw_power_missing" src/shitbox/capture/speaker.py`
    - `grep -q "hw_power_restored" src/shitbox/capture/speaker.py`
    - `grep -q "hw_gps_missing" src/shitbox/capture/speaker.py`
    - `grep -q "hw_gps_restored" src/shitbox/capture/speaker.py`
    - `grep -q "hw_env_missing" src/shitbox/capture/speaker.py`
    - `grep -q "hw_env_restored" src/shitbox/capture/speaker.py`
    - `grep -q "def speak_hardware_missing" src/shitbox/capture/speaker.py`
    - `grep -q "def speak_hardware_restored" src/shitbox/capture/speaker.py`
    - `grep -q "Michael, I've lost the IMU" src/shitbox/capture/speaker.py` (exact copy from UI-SPEC)
    - `pytest tests/test_speaker_alerts.py -x -q` exits 0
    - `ruff check src/shitbox/capture/speaker.py` exits 0
  </acceptance_criteria>
  <done>
    All 10 UI-SPEC TTS lines present verbatim in `_CACHED_MESSAGES`. `speak_hardware_missing` and `speak_hardware_restored` exist, enforce tier gating (best_effort silent except environment), honour `_should_alert()`, and test coverage asserts every gating combination. No behaviour changes to existing speak_* functions.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: HardwareSupervisor class</name>
  <files>src/shitbox/hardware/supervisor.py, tests/hardware/test_hardware_supervisor.py</files>
  <read_first>
    - src/shitbox/sync/batch_sync.py (lines 33-108 — canonical service lifecycle with start/stop/_thread)
    - src/shitbox/display/oled.py (lines 35-94 — hardware-import-inside-start pattern, `_display_loop` tick structure)
    - src/shitbox/hardware/state.py (Plan 01 output — the module this class reads and writes)
    - src/shitbox/hardware/probes.py (Plan 01 output — reprobe dispatch targets)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §supervisor.py (lines 94-205)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Pattern 2 (lines 249-331) and §Pitfall 6 (duplicate TTS ownership)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md §Copywriting (TTS cadence table)
  </read_first>
  <behavior>
    - Construction takes a manifest and a `Dict[role, Callable[[], bool]]` of reprobe callbacks. No module-level state on the supervisor; it owns `_last_nag: Dict[str, float]` only.
    - `start()` initialises `hw_state` from the manifest, calls `_probe_all()` to seed PRESENT/MISSING, then spawns a daemon thread named `"hw-supervisor"`. Idempotent (second call is a no-op if already running).
    - `stop()` sets `_running = False` and joins the thread with timeout 2.0 (matches batch_sync pattern).
    - `_probe_all()` iterates `self.manifest.devices`, calls the appropriate probe per `d.bus`, reports PRESENT or MISSING into hw_state. For i2c-1, first checks `probe_i2c_bus_is_bitbang(1)` — if False, log.critical and mark all i2c-1 devices MISSING without calling probe_i2c.
    - `_tick()` walks `hw_state.snapshot()`:
      - If state == MISSING AND now >= next_retry_at AND next_retry_at > 0:
        - Call reprobe callback → True: `hw_state.report_present(role)` + `speak_hardware_restored(role, tier)` + structlog info `"hw_restored"`.
        - False: `hw_state.report_missing(role)` (bumps ladder).
      - If state == MISSING AND tier == "critical" AND now - self._last_nag.get(role, 0) >= CRITICAL_RENAG_SECONDS:
        - `speak_hardware_missing(role, tier)` + update `_last_nag[role] = now`.
      - If state transitioned MISSING just now (detected via previous-state return on report_missing — pass through a small `_transition_cache`), speak once per tier per UI-SPEC cadence table (important: once per transition; best_effort: log only except environment).
    - `_tick_loop()` wraps `_tick()` in try/except — log error, continue, sleep `TICK_INTERVAL_SECONDS`. No exception ever escapes.
    - Log events: `hw_supervisor_started`, `hw_supervisor_stopped`, `hw_probe_all_complete`, `hw_state_changed`, `hw_restored`, `hw_reprobe_error`, `hw_supervisor_tick_error`. All structlog keyword args.
  </behavior>
  <action>
Create `src/shitbox/hardware/supervisor.py`.

Imports:

```python
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

from shitbox.capture import speaker
from shitbox.hardware import probes as hw_probes
from shitbox.hardware import state as hw_state
from shitbox.utils.config import HardwareDeviceConfig, HardwareManifestConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)
```

Class skeleton (follow PATTERNS.md §supervisor.py and RESEARCH.md §Pattern 2 — do not reinvent). Key requirements:

```python
class HardwareSupervisor:
    """Daemon thread: probes at boot, then ticks every second to drive
    re-adoption + alert cadence. Composes HardwareState, per-bus probes, and
    TTS — but duplicates none of the sampler's existing recovery logic."""

    TICK_INTERVAL_SECONDS: float = 1.0
    CRITICAL_RENAG_SECONDS: float = 30.0

    def __init__(
        self,
        manifest: HardwareManifestConfig,
        reprobe_callbacks: Dict[str, Callable[[], bool]],
    ) -> None:
        self.manifest = manifest
        self.reprobe = reprobe_callbacks
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._last_nag: Dict[str, float] = {}
        self._prev_state: Dict[str, hw_state.DeviceState] = {}  # for one-shot transition detection

    def start(self) -> None:
        if self._running:
            return
        devices = {d.role: d.criticality for d in self.manifest.devices}
        hw_state.initialise(devices)
        self._probe_all()
        self._running = True
        self._thread = threading.Thread(target=self._tick_loop, daemon=True, name="hw-supervisor")
        self._thread.start()
        log.info("hw_supervisor_started", device_count=len(devices))

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        log.info("hw_supervisor_stopped")

    def _probe_all(self) -> None:
        # If i2c-1 is expected but the bus is not bit-bang, mark all i2c-1 devices MISSING
        # without probing (Pitfall 1 guard).
        i2c_ok = hw_probes.probe_i2c_bus_is_bitbang(1)
        for d in self.manifest.devices:
            present = self._run_probe(d, i2c_ok=i2c_ok)
            if present:
                hw_state.report_present(d.role)
            else:
                hw_state.report_missing(d.role)
        log.info("hw_probe_all_complete", i2c_bus_ok=i2c_ok)

    def _run_probe(self, d: HardwareDeviceConfig, i2c_ok: bool) -> bool:
        if d.bus == "i2c-1":
            if not i2c_ok:
                return False
            if d.address is None:
                return False
            return hw_probes.probe_i2c(1, d.address)
        if d.bus == "1-wire":
            return hw_probes.probe_onewire(d.sensor_id or "")
        if d.bus == "usb":
            return hw_probes.probe_usb_path(d.path or "")
        if d.bus == "audio":
            return hw_probes.probe_audio_label(d.label or "")
        if d.bus == "hdmi":
            return hw_probes.probe_hdmi(d.connector or "")
        if d.bus == "gpio":
            return hw_probes.probe_gpio_pin(d.pin or 0)
        log.warning("hw_unknown_bus", role=d.role, bus=d.bus)
        return False

    def _tick_loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as e:
                log.error("hw_supervisor_tick_error", error=str(e))
            time.sleep(self.TICK_INTERVAL_SECONDS)

    def _tick(self) -> None:
        now = time.monotonic()
        for role, st in hw_state.snapshot().items():
            prev = self._prev_state.get(role)
            # Retry due?
            if st.state == hw_state.DeviceState.MISSING and st.next_retry_at and now >= st.next_retry_at:
                cb = self.reprobe.get(role)
                if cb is not None:
                    try:
                        if cb():
                            hw_state.report_present(role)
                            speaker.speak_hardware_restored(role, st.tier)
                            log.info("hw_restored", role=role, tier=st.tier)
                            self._last_nag.pop(role, None)
                            self._prev_state[role] = hw_state.DeviceState.PRESENT
                            continue
                    except Exception as e:
                        log.warning("hw_reprobe_error", role=role, error=str(e))
                hw_state.report_missing(role)
            # One-shot transition speak on first MISSING detection (covers collector-reported misses)
            if st.state == hw_state.DeviceState.MISSING and prev != hw_state.DeviceState.MISSING:
                speaker.speak_hardware_missing(role, st.tier)
                log.info("hw_state_changed", role=role, tier=st.tier, state="missing")
                self._last_nag[role] = now
            # Critical re-nag
            elif (
                st.state == hw_state.DeviceState.MISSING
                and st.tier == "critical"
                and now - self._last_nag.get(role, 0) >= self.CRITICAL_RENAG_SECONDS
            ):
                speaker.speak_hardware_missing(role, st.tier)
                self._last_nag[role] = now
            # One-shot restored transition when collector flipped state to PRESENT without our retry
            if st.state == hw_state.DeviceState.PRESENT and prev == hw_state.DeviceState.MISSING:
                speaker.speak_hardware_restored(role, st.tier)
                log.info("hw_restored", role=role, tier=st.tier)
                self._last_nag.pop(role, None)
            self._prev_state[role] = st.state
```

Key rules enforced by this structure:
- `_tick` dispatches retry via callback BEFORE the transition-speak branch, so a device that recovers on its scheduled retry speaks only `speak_hardware_restored` (no duplicate missing-speak that same tick).
- `_prev_state` is supervisor-local; HardwareState is the source of truth for readers (OLED/SSE). The supervisor uses `_prev_state` only to detect first-time transitions for one-shot speaks.
- Critical re-nag fires only while state remains MISSING; as soon as state flips PRESENT the `_last_nag.pop(role)` clears it for future MISSING cycles.

Create `tests/hardware/test_hardware_supervisor.py`. Mirror `tests/test_batch_sync.py`'s shape — no live thread, tests call `_tick()` directly, monkeypatch `time.monotonic`, mock `speaker.speak_hardware_missing` / `speak_hardware_restored`, build a manifest fixture with 3 devices (imu critical, power important, environment best_effort).

Required tests:
- `test_start_seeds_state_from_manifest` — stop the thread (`supervisor.stop()` immediately) but assert `hw_state.snapshot()` has all 3 roles with the right tier.
- `test_probe_all_marks_missing_when_bus_not_bitbang` — monkeypatch `hw_probes.probe_i2c_bus_is_bitbang` to return False; call `_probe_all`; assert all i2c-1 devices MISSING and `probe_i2c` was NOT called.
- `test_probe_all_reports_present_when_probe_returns_true` — mock all probes → True; assert all state PRESENT.
- `test_critical_tier_renags_every_30s` — put imu into MISSING state, set `_last_nag["imu"] = 0`, call `_tick()` at monotonic=0; assert speak_hardware_missing called once. Advance time to 29s, call `_tick()`; assert NOT called again. Advance to 31s, call `_tick()`; assert called again.
- `test_important_tier_speaks_once_per_transition` — put power into MISSING; call `_tick()` (prev_state empty → first detection, speaks once). Call `_tick()` again 5s later without state change; assert speak NOT called again. Call `_tick()` again 31s later; still MISSING, important tier → no re-nag.
- `test_best_effort_silent_except_environment` — magnetometer MISSING, tick; speak NOT called. environment MISSING (add to fixture), tick; speak CALLED once.
- `test_reprobe_recovers` — imu MISSING with next_retry_at set to 0; reprobe callback returns True; tick at monotonic=0; assert hw_state flips to PRESENT, speak_hardware_restored called once, no speak_missing this tick.
- `test_reprobe_failure_reschedules` — imu MISSING with next_retry_at=0, consecutive_misses=1; reprobe returns False; tick; assert `snapshot()["imu"].next_retry_at > 0`, `consecutive_misses == 2` (advances to 15s bucket).
- `test_tick_swallows_exceptions` — patch `hw_state.snapshot` to raise RuntimeError once, call `_tick()`; assert no exception propagates and `hw_supervisor_tick_error` was logged (caplog or structlog helper).
- `test_bme680_canonical_case` — CANONICAL ACCEPTANCE PER HW-04:
  - manifest has environment (best_effort, i2c-1, 0x77)
  - reprobe callback `attempts = [False, True]` — first call returns False, second True (simulates the documented boot-timing race)
  - supervisor start → probe_all marks environment MISSING (with `probe_i2c` mocked to return False initially); consecutive_misses=1, next_retry_at=5s
  - monotonic time advances to 5s; `_tick()` runs; reprobe returns True → environment flips PRESENT, speak_hardware_restored("environment", "best_effort") called (environment is the allowed exception)
  - assert final snapshot state PRESENT and that speak_hardware_restored was called exactly once with args ("environment", "best_effort")

Use fixtures: `supervisor_fixture(monkeypatch)` builds a `HardwareManifestConfig` + `reprobe_callbacks` dict, returns `HardwareSupervisor` without starting the thread; the autouse conftest fixture from Plan 01 (`_clear_hw_state`) ensures a clean state dict per test.

Ruff line length 100. Full type annotations.
  </action>
  <verify>
    <automated>pytest tests/hardware/test_hardware_supervisor.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/shitbox/hardware/supervisor.py`
    - `grep -q "class HardwareSupervisor" src/shitbox/hardware/supervisor.py`
    - `grep -q "TICK_INTERVAL_SECONDS: float = 1.0" src/shitbox/hardware/supervisor.py`
    - `grep -q "CRITICAL_RENAG_SECONDS: float = 30.0" src/shitbox/hardware/supervisor.py`
    - `grep -q "name=\"hw-supervisor\"" src/shitbox/hardware/supervisor.py`
    - `grep -q "probe_i2c_bus_is_bitbang" src/shitbox/hardware/supervisor.py` (Pitfall 1 guard)
    - `grep -q "speak_hardware_restored" src/shitbox/hardware/supervisor.py`
    - `grep -q "speak_hardware_missing" src/shitbox/hardware/supervisor.py`
    - `grep -q "hw_supervisor_tick_error" src/shitbox/hardware/supervisor.py` (swallow-and-log)
    - `pytest tests/hardware/test_hardware_supervisor.py -x -q` exits 0
    - `pytest tests/hardware/test_hardware_supervisor.py::test_critical_tier_renags_every_30s -x -q` exits 0 (HW-03)
    - `pytest tests/hardware/test_hardware_supervisor.py::test_bme680_canonical_case -x -q` exits 0 (HW-04 CANONICAL)
    - `pytest tests/hardware/test_hardware_supervisor.py::test_reprobe_recovers -x -q` exits 0 (HW-04)
    - `pytest tests/hardware/test_hardware_supervisor.py::test_best_effort_silent_except_environment -x -q` exits 0 (HW-03)
    - `ruff check src/shitbox/hardware/supervisor.py tests/hardware/test_hardware_supervisor.py` exits 0
    - `mypy src/shitbox/hardware/supervisor.py` exits 0
  </acceptance_criteria>
  <done>
    HardwareSupervisor class exists, tick loop handles cadence + backoff + retry, 10 tests pass including the canonical BME680 acceptance case. Zero logic overlap with sampler's existing I2C recovery ladder (supervisor only speaks on terminal transitions). No engine wiring in this plan.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| supervisor thread → speaker queue | In-process async queue; speaker enqueues WAV bytes for Piper. No cross-process IPC. |
| reprobe callbacks → hardware | Callables run in supervisor thread context; each calls a per-bus probe primitive from Plan 01 (with smbus2 context manager, /sys / /proc / /dev reads). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-02-01 | Denial of Service | Blocking TTS inside tick | mitigate | `speaker._enqueue` is async-queued (Piper synthesis happens on speaker's worker); `speak_hardware_*` never blocks — verified by `_enqueue` semantics in capture/speaker.py and enforced by RESEARCH.md anti-pattern list. Tick-spam prevented by `_last_nag` dict (critical re-nag every 30s, not every tick). |
| T-21-02-02 | Denial of Service | Tick-loop exception taking out the supervisor | mitigate | `_tick_loop` wraps `_tick` in try/except, logs, continues; test `test_tick_swallows_exceptions` enforces. |
| T-21-02-03 | Tampering | Malicious reprobe callback | accept | Callbacks are code owned by the engine plan (05) — same trust domain as all other in-process code. No external callable injection. |
| T-21-02-04 | Information Disclosure | Log entries naming device roles/addresses | accept | Roles/addresses already in config.yaml; no secrets. |
| T-21-02-05 | Repudiation | Missing audit trail for state transitions | mitigate | Every transition logs `hw_state_changed` / `hw_restored` with structlog keyword args (role, tier, prev, new) — sufficient for local post-mortem. |

**ASVS L1:** V5 Input Validation partial — manifest typed via dataclass; bus dispatch uses exhaustive string match with default `log.warning("hw_unknown_bus")` + return False. No other categories apply (read-only Pi-local service, no auth, no network).
</threat_model>

<verification>
End of plan checks:

- `pytest tests/hardware/test_hardware_supervisor.py tests/test_speaker_alerts.py -x -q` — all new tests pass.
- `pytest tests/hardware/ -x -q` — Plan 01 suite still green + new supervisor tests.
- `pytest` — full project suite passes. Speaker changes are additive, no regressions expected.
- `python -c "from shitbox.hardware.supervisor import HardwareSupervisor; print(HardwareSupervisor.TICK_INTERVAL_SECONDS, HardwareSupervisor.CRITICAL_RENAG_SECONDS)"` prints `1.0 30.0`.
- `ruff check src/shitbox/hardware src/shitbox/capture/speaker.py tests/hardware` exits 0.
- `mypy src/shitbox/hardware` exits 0.

No engine wiring in this plan — the supervisor is instantiable but nothing yet starts it. That wiring is Plan 05.
</verification>

<success_criteria>
- HW-03 met: supervisor re-nags critical tier every 30s, speaks important once per transition, best_effort is log-only except environment — enforced by 3 distinct tests.
- HW-04 met: backoff schedule drives retries; reprobe success flips state + speaks restored; BME680 canonical case passes end-to-end in `test_bme680_canonical_case`.
- 10 UI-SPEC TTS strings present verbatim in `_CACHED_MESSAGES`.
- No duplication with the sampler's `speak_i2c_lockup` — supervisor speaks only on terminal MISSING / RESTORED transitions (Pitfall 6).
- Pitfall 1 guard lives in `_probe_all` — i2c-1 devices marked MISSING without probing if the bus isn't bit-bang.
</success_criteria>

<output>
After completion, create `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-02-SUMMARY.md` covering:
- Supervisor class structure + tick-loop semantics (1-2 paragraphs)
- Test counts (supervisor / speaker)
- Confirmation that the BME680 canonical test passes (name and pass/fail)
- Any cadence edge cases discovered
</output>
