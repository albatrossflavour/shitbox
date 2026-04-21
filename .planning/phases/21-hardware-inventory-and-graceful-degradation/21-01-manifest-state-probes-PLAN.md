---
phase: 21
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/shitbox/hardware/__init__.py
  - src/shitbox/hardware/state.py
  - src/shitbox/hardware/probes.py
  - src/shitbox/utils/config.py
  - config/config.yaml
  - tests/hardware/__init__.py
  - tests/hardware/conftest.py
  - tests/hardware/test_hardware_state.py
  - tests/hardware/test_hardware_manifest.py
  - tests/hardware/test_hardware_probes.py
  - tests/test_config.py
autonomous: true
requirements: [HW-01, HW-02]
estimated_loc: 520
must_haves:
  truths:
    - "config.yaml hardware: block loads into HardwareManifestConfig with all 14 declared devices"
    - "HardwareState module provides initialise / report_present / report_missing / report_degraded / snapshot / clear_state"
    - "report_missing schedules next_retry_at per [5s, 15s, 60s, 300s] ladder indexed by consecutive_misses"
    - "probe_i2c / probe_usb_path / probe_onewire / probe_audio_label / probe_hdmi / probe_gpio_pin return bool cleanly under mocked I/O"
    - "probe_i2c_bus_is_bitbang checks /sys/class/i2c-adapter/i2c-1/name starts with i2c-gpio (Pitfall 1 guard)"
  artifacts:
    - path: src/shitbox/hardware/state.py
      provides: "Module-level HardwareState (mirrors gps_state)"
      contains: "DeviceStatus"
    - path: src/shitbox/hardware/probes.py
      provides: "Per-bus probe functions (i2c, usb, 1-wire, audio, hdmi, gpio, bus-is-bitbang)"
    - path: src/shitbox/utils/config.py
      provides: "HardwareDeviceConfig + HardwareManifestConfig dataclasses + loader coercion"
      contains: "class HardwareManifestConfig"
    - path: config/config.yaml
      provides: "hardware: block declaring all 14 devices per D-05 criticality map"
      contains: "hardware:"
    - path: tests/hardware/test_hardware_state.py
      provides: "Unit tests for HardwareState (initialise, report_*, backoff ladder)"
    - path: tests/hardware/test_hardware_manifest.py
      provides: "YAML round-trip test for HardwareManifestConfig"
    - path: tests/hardware/test_hardware_probes.py
      provides: "Mocked probe function tests for all 7 probe primitives"
  key_links:
    - from: "config/config.yaml (hardware:)"
      to: "src/shitbox/utils/config.py HardwareManifestConfig"
      via: "load_config() -> HardwareDeviceConfig(**d) list coercion"
      pattern: "HardwareDeviceConfig\\(\\*\\*d\\)"
    - from: "src/shitbox/hardware/state.py"
      to: "downstream consumers (supervisor, OLED, SSE, collectors)"
      via: "module-level import `from shitbox.hardware import state as hw_state`"
      pattern: "hw_state\\.(report_present|report_missing|report_degraded|snapshot)"
---

<objective>
Lay the Wave 1 foundations for Phase 21: the typed hardware manifest loaded from
config.yaml (HW-01), the module-level HardwareState that everything else will
read and write (HW-02 substrate), the per-bus probe primitives, and all Wave 0
test scaffolds for these three modules plus the manifest round-trip in
test_config.py.

These three pieces are independent: none import each other's business logic,
and none require changes to the engine or any existing collector. They exist so
that Waves 2 and 3 can wire them up without further foundation work.

Purpose: establish the vocabulary (manifest → state → probes) that every later
plan composes. No daemon or collector behaviour changes in this plan.

Output:
- `src/shitbox/hardware/__init__.py`, `state.py`, `probes.py`
- `HardwareDeviceConfig` + `HardwareManifestConfig` in `utils/config.py`
- `hardware:` block in `config/config.yaml`
- Wave 0 test files under `tests/hardware/`
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-VALIDATION.md
@CLAUDE.md
@src/shitbox/dashboard/gps_state.py
@src/shitbox/utils/config.py
@src/shitbox/collectors/power.py
@tests/test_config.py

<interfaces>
<!-- Concrete contracts downstream plans will consume from this plan. -->
<!-- Copy these signatures exactly — do not invent variations. -->

From src/shitbox/hardware/state.py (new, this plan):
```python
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional

class DeviceState(str, Enum):
    PRESENT = "present"
    DEGRADED = "degraded"
    MISSING = "missing"

@dataclass(frozen=True, slots=True)
class DeviceStatus:
    role: str
    tier: str                    # "critical" | "important" | "best_effort"
    state: DeviceState
    last_seen: float             # time.time() of last successful read; 0.0 if never
    since_monotonic: float       # time.monotonic() when current state began
    next_retry_at: float         # time.monotonic(); 0.0 = not scheduled
    consecutive_misses: int

def initialise(devices: Dict[str, str]) -> None: ...     # {role: tier} — seeds MISSING
def report_present(role: str) -> Optional[DeviceState]: ...   # returns previous state
def report_missing(role: str) -> Optional[DeviceState]: ...   # bumps consecutive, schedules next_retry_at
def report_degraded(role: str) -> Optional[DeviceState]: ...  # in-recovery; no next_retry_at change
def snapshot() -> Dict[str, DeviceStatus]: ...          # do not mutate
def clear_state() -> None: ...                          # TEST-ONLY helper
```

From src/shitbox/hardware/probes.py (new, this plan):
```python
def probe_i2c(bus: int, address: int) -> bool: ...
def probe_usb_path(path: str) -> bool: ...
def probe_onewire(sensor_id: str) -> bool: ...
def probe_audio_label(label: str) -> bool: ...
def probe_hdmi(connector: str) -> bool: ...
def probe_gpio_pin(pin: int) -> bool: ...
def probe_i2c_bus_is_bitbang(bus: int) -> bool: ...
```

From src/shitbox/utils/config.py (additions, this plan):
```python
@dataclass
class HardwareDeviceConfig:
    role: str = ""
    bus: str = ""                    # i2c-1 | 1-wire | usb | gpio | hdmi | audio
    criticality: str = "best_effort" # critical | important | best_effort
    description: str = ""
    address: Optional[int] = None    # i2c (0x6a)
    path: Optional[str] = None       # usb (/dev/camera-front)
    sensor_id: Optional[str] = None  # 1-wire (28-00000024263a)
    pin: Optional[int] = None        # gpio (17)
    label: Optional[str] = None      # audio (UACDemo)
    connector: Optional[str] = None  # hdmi (HDMI-A-1)

@dataclass
class HardwareManifestConfig:
    devices: List[HardwareDeviceConfig] = field(default_factory=list)
```

Backoff ladder (exact, no variation): `[5.0, 15.0, 60.0, 300.0]`.
`consecutive_misses` is clamped to `len(schedule)` so the 5-min cap holds forever.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: HardwareState module + its Wave 0 tests</name>
  <files>src/shitbox/hardware/__init__.py, src/shitbox/hardware/state.py, tests/hardware/__init__.py, tests/hardware/conftest.py, tests/hardware/test_hardware_state.py</files>
  <read_first>
    - src/shitbox/dashboard/gps_state.py (complete file — the direct analog, copy its register)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §`src/shitbox/hardware/state.py` (lines 37-91)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Pattern 1 (lines 151-247) — reference implementation
    - tests/conftest.py (top of file — how fixtures are organised project-wide)
  </read_first>
  <behavior>
    - `initialise({"imu": "critical", "power": "important"})` seeds both roles in state MISSING with `consecutive_misses=0`, `next_retry_at=0.0`.
    - `report_present("imu")` with no previous state returns None and does nothing (no silent initialise — tests assert the state dict stays empty).
    - After initialise, `report_present("imu")` returns `DeviceState.MISSING` (the previous state), flips state to PRESENT, updates `last_seen` to current `time.time()`, resets `consecutive_misses` to 0, clears `next_retry_at` to 0.0.
    - `report_missing("imu")` after a PRESENT sets `consecutive_misses=1`, `next_retry_at == time.monotonic() + 5.0` (±5ms).
    - Repeated `report_missing` bumps ladder: misses 1→5s wait, 2→15s, 3→60s, 4→300s, 5→300s (cap holds).
    - `report_degraded("imu")` sets state to DEGRADED without touching `next_retry_at` or `consecutive_misses`.
    - `snapshot()` returns the exact `_state` dict (readers treat as immutable; `DeviceStatus` is frozen).
    - `clear_state()` empties the dict so subsequent `initialise` works from a clean slate.
    - Every report_* function is safe to call from any thread — rebind is atomic under the GIL (no Lock).
  </behavior>
  <action>
Create `src/shitbox/hardware/__init__.py` as an empty package marker (single-line docstring: `"""Hardware inventory and graceful-degradation subsystem."""`).

Create `src/shitbox/hardware/state.py` with the exact `DeviceState` enum, frozen `DeviceStatus` dataclass, and module-level `_state: Dict[str, DeviceStatus] = {}` per the interfaces block and RESEARCH.md §Pattern 1. Match `gps_state.py`'s `from __future__ import annotations` + docstring register verbatim ("Safe to call from any thread — the module-level rebind is GIL-atomic.").

Backoff ladder is a module-level constant `_BACKOFF_LADDER_SECONDS: list[float] = [5.0, 15.0, 60.0, 300.0]`. Inside `report_missing`:

```python
consecutive = min(prev.consecutive_misses + 1, len(_BACKOFF_LADDER_SECONDS))
wait = _BACKOFF_LADDER_SECONDS[consecutive - 1]
```

Writers must rebind via a copy-then-assign pattern (never mutate `_state[key]` in place) — see RESEARCH.md §Pattern 1 lines 210-219 for the exact `new_map = dict(_state); new_map[role] = ...; _state = new_map` shape.

structlog logging:
- `log.info("hw_state_initialised", devices=len(devices))`
- `log.info("hw_state_transition", role=role, prev=prev.state.value, new="present")` on state change only (not on repeated same-state reports)
- `log.debug("hw_state_missing_rescheduled", role=role, misses=consecutive, wait_s=wait)` on repeated missing

Create `tests/hardware/__init__.py` (empty, package marker).

Create `tests/hardware/conftest.py` with a single autouse fixture that calls `state.clear_state()` before each test:

```python
import pytest
from shitbox.hardware import state as hw_state

@pytest.fixture(autouse=True)
def _clear_hw_state():
    hw_state.clear_state()
    yield
    hw_state.clear_state()
```

Create `tests/hardware/test_hardware_state.py` with one test per behaviour bullet:
- `test_initialise_seeds_all_devices_missing`
- `test_report_present_unknown_role_returns_none`
- `test_report_present_returns_previous_state`
- `test_report_present_resets_consecutive_misses`
- `test_backoff_schedule` — iterate 6 report_missing calls, assert the `next_retry_at - time.monotonic()` deltas sit at 5, 15, 60, 300, 300, 300 (±10ms tolerance). Monkeypatch `time.monotonic` to a controllable stub for determinism.
- `test_report_degraded_preserves_next_retry_at`
- `test_snapshot_returns_current_state`
- `test_clear_state_empties_dict`

Use `structlog` keyword logging only. No `print`. Ruff line length 100. Full type annotations (mypy --strict-ish).
  </action>
  <verify>
    <automated>pytest tests/hardware/test_hardware_state.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/shitbox/hardware/__init__.py`
    - `test -f src/shitbox/hardware/state.py`
    - `test -f tests/hardware/conftest.py`
    - `grep -q "^class DeviceState" src/shitbox/hardware/state.py`
    - `grep -q "frozen=True" src/shitbox/hardware/state.py` (DeviceStatus is immutable)
    - `grep -q "_BACKOFF_LADDER_SECONDS" src/shitbox/hardware/state.py`
    - `grep -q "5.0, 15.0, 60.0, 300.0" src/shitbox/hardware/state.py`
    - `grep -q "def initialise" src/shitbox/hardware/state.py`
    - `grep -q "def report_present" src/shitbox/hardware/state.py`
    - `grep -q "def report_missing" src/shitbox/hardware/state.py`
    - `grep -q "def report_degraded" src/shitbox/hardware/state.py`
    - `grep -q "def snapshot" src/shitbox/hardware/state.py`
    - `grep -q "def clear_state" src/shitbox/hardware/state.py`
    - `pytest tests/hardware/test_hardware_state.py -x -q` exits 0
    - `pytest tests/hardware/test_hardware_state.py::test_backoff_schedule -x -q` exits 0 (HW-04 substrate)
    - `ruff check src/shitbox/hardware/state.py tests/hardware/` exits 0
    - `mypy src/shitbox/hardware/state.py` exits 0
  </acceptance_criteria>
  <done>
    HardwareState module exists with the 6 public functions + 1 test helper. All 8 unit tests pass. DeviceStatus is a frozen slotted dataclass. The backoff ladder is a module-level constant and the test asserts the 5/15/60/300/300/300 sequence. No Lock, no threading, no external deps beyond stdlib + the project's structlog wrapper.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Per-bus probe functions + tests</name>
  <files>src/shitbox/hardware/probes.py, tests/hardware/test_hardware_probes.py</files>
  <read_first>
    - src/shitbox/collectors/power.py (lines 1-80 — the reference smbus2 usage pattern in production)
    - src/shitbox/capture/ring_buffer.py (lines 870-895 — `os.path.exists(self.device)` USB idiom)
    - src/shitbox/capture/speaker.py (lines 95-113 — `_detect_usb_speaker` /proc/asound/cards parser)
    - src/shitbox/capture/button.py (lines 1-40 — `GPIO_AVAILABLE` flag pattern)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §`src/shitbox/hardware/probes.py` (lines 207-261)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Pitfall 1 (bus-is-bitbang guard) and §Pitfall 5 (close the smbus)
  </read_first>
  <behavior>
    - `probe_i2c(1, 0x6a)` opens `smbus2.SMBus(1)` under a `with` block, calls `read_byte_data(addr, 0x00)`, closes the bus. Returns True on success, False on OSError. Unexpected exceptions log a warning and return False.
    - `probe_usb_path("/dev/camera-front")` returns `os.path.exists(path)` verbatim.
    - `probe_onewire("28-00000024263a")` returns True iff `/sys/bus/w1/devices/28-00000024263a/w1_slave` exists.
    - `probe_audio_label("UACDemo")` returns True iff the label substring is present in `/proc/asound/cards`. Returns False on OSError reading the file.
    - `probe_hdmi("HDMI-A-1")` globs `/sys/class/drm/*HDMI-A-1*/status`; returns True iff any matching file contains `"connected"` after strip.
    - `probe_gpio_pin(17)` returns True iff `RPi.GPIO` imports successfully (pin arg is accepted for future extension; the current check is module availability per button.py precedent).
    - `probe_i2c_bus_is_bitbang(1)` reads `/sys/class/i2c-adapter/i2c-1/name`; returns True iff text starts with `"i2c-gpio"`. Logs `hw_manifest_bus_check_failed` at log.critical when False (Pitfall 1 guard).
  </behavior>
  <action>
Create `src/shitbox/hardware/probes.py`. Imports:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import smbus2

from shitbox.utils.logging import get_logger

log = get_logger(__name__)
```

Implement each probe exactly per RESEARCH.md §Code Examples lines 573-656 and PATTERNS.md §probes.py lines 250-259. Key details:

- `probe_i2c`: `with smbus2.SMBus(bus) as smb:` context manager is mandatory (Pitfall 5 — do not hold the bus open). One `except OSError: return False`; one `except Exception as e: log.warning("i2c_probe_unexpected_error", bus=bus, address=hex(address), error=str(e)); return False`.
- `probe_onewire`: `return Path(f"/sys/bus/w1/devices/{sensor_id}/w1_slave").exists()`.
- `probe_audio_label`: `try: return label in Path("/proc/asound/cards").read_text() \n except OSError: return False`.
- `probe_hdmi`: iterate `Path("/sys/class/drm").glob(f"*{connector}")`, check `(path / "status").read_text().strip() == "connected"`. Wrap in try/OSError returning False.
- `probe_gpio_pin`: `try: import RPi.GPIO as _gpio; return True; except ImportError: return False; except Exception: return False`. The unused `pin` arg stays in the signature for manifest dispatch symmetry — add a `# noqa: ARG001` comment or reference pin in a log line.
- `probe_i2c_bus_is_bitbang`: read `/sys/class/i2c-adapter/i2c-{bus}/name`. If missing or not starting with `"i2c-gpio"`, call `log.critical("hw_manifest_bus_check_failed", bus=bus, expected="i2c-gpio", got=name or "")` and return False.

Ruff line length 100. Full type annotations. Every public function has a docstring matching the 1-line pattern in the analogs.

Create `tests/hardware/test_hardware_probes.py`:

- `test_probe_i2c_present` — patch `shitbox.hardware.probes.smbus2.SMBus`; context manager returns a mock whose `read_byte_data` returns 0. Assert True. Assert `__exit__` called (bus closed).
- `test_probe_i2c_absent_raises_oserror` — same patch, `read_byte_data` raises OSError; assert False.
- `test_probe_i2c_unexpected_error_returns_false` — `read_byte_data` raises ValueError; assert False and that a warning was logged (capture with structlog test helper or `caplog`).
- `test_probe_usb_path_exists` — use `tmp_path`, create a file, assert True; delete, assert False.
- `test_probe_onewire_exists` — monkeypatch `Path.exists` for the specific path; assert True for a real-looking sensor_id.
- `test_probe_audio_label_present` — monkeypatch `Path("/proc/asound/cards").read_text` to return `"0 [UACDemo ...]"`; assert True for "UACDemo"; assert False for "Absent".
- `test_probe_audio_label_oserror_returns_false` — monkeypatch `read_text` to raise OSError; assert False.
- `test_probe_hdmi_connected` — tmp_path fixture emulating `/sys/class/drm/card0-HDMI-A-1/status` with content `"connected\n"`. Patch `Path("/sys/class/drm")` to point to tmp. Assert True.
- `test_probe_hdmi_disconnected` — same setup, status reads `"disconnected\n"`; assert False.
- `test_probe_gpio_pin_module_available` — let the real `RPi.GPIO` import succeed or skip (`pytest.importorskip("RPi.GPIO")`); assert True.
- `test_probe_gpio_pin_module_missing` — patch `sys.modules["RPi.GPIO"] = None` then monkeypatch the import to raise ImportError; assert False.
- `test_probe_i2c_bus_is_bitbang_true` — monkeypatch `Path("/sys/class/i2c-adapter/i2c-1/name").read_text` to return `"i2c-gpio-1\n"`; assert True.
- `test_probe_i2c_bus_is_bitbang_false_logs_critical` — monkeypatch read_text to return `"i2c-designware\n"`; assert False and that the critical log was emitted (capture with caplog or structlog test fixture).

Use `unittest.mock.patch` with path `shitbox.hardware.probes.smbus2.SMBus` (matches how `test_power.py` / equivalent would patch — follow the `patch("shitbox.collectors.power.smbus2")` comment in power.py line 16 as the pattern reference).
  </action>
  <verify>
    <automated>pytest tests/hardware/test_hardware_probes.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/shitbox/hardware/probes.py`
    - `grep -q "def probe_i2c" src/shitbox/hardware/probes.py`
    - `grep -q "def probe_usb_path" src/shitbox/hardware/probes.py`
    - `grep -q "def probe_onewire" src/shitbox/hardware/probes.py`
    - `grep -q "def probe_audio_label" src/shitbox/hardware/probes.py`
    - `grep -q "def probe_hdmi" src/shitbox/hardware/probes.py`
    - `grep -q "def probe_gpio_pin" src/shitbox/hardware/probes.py`
    - `grep -q "def probe_i2c_bus_is_bitbang" src/shitbox/hardware/probes.py`
    - `grep -q "with smbus2.SMBus" src/shitbox/hardware/probes.py` (Pitfall 5: bus closed in `with` block)
    - `grep -q "hw_manifest_bus_check_failed" src/shitbox/hardware/probes.py` (Pitfall 1 critical log)
    - `pytest tests/hardware/test_hardware_probes.py -x -q` exits 0
    - `ruff check src/shitbox/hardware/probes.py` exits 0
    - `mypy src/shitbox/hardware/probes.py` exits 0
  </acceptance_criteria>
  <done>
    All 7 probe functions exist, all tests pass with mocks, bus-is-bitbang guard logs critical when the wrong driver is active, smbus2 is used via `with` to close the bus (Pitfall 5), no subprocess calls (no `i2cdetect`).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: HardwareManifestConfig + config.yaml hardware: block + manifest round-trip test</name>
  <files>src/shitbox/utils/config.py, config/config.yaml, tests/hardware/test_hardware_manifest.py, tests/test_config.py</files>
  <read_first>
    - src/shitbox/utils/config.py (full file — especially DS18B20ProbeConfig and TemperatureConfig at lines 75-94, loader at lines 464-470, Config dataclass at lines 472-525)
    - config/config.yaml (full file — see existing sensors: / display: block style to mirror)
    - tests/test_config.py (existing DS18B20 round-trip test — the analog to mirror)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §`src/shitbox/utils/config.py` (lines 263-322)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Code Examples (HardwareManifest YAML block, lines 444-529, and HardwareDeviceConfig dataclass, lines 534-570)
  </read_first>
  <behavior>
    - `HardwareDeviceConfig` is a `@dataclass` with bus-agnostic fields (role/bus/criticality/description) and Optional bus-specific fields (address/path/sensor_id/pin/label/connector). All have defaults so `HardwareDeviceConfig(**d)` works for any subset of fields.
    - `HardwareManifestConfig.devices` defaults to empty list via `field(default_factory=list)`.
    - `load_config()` pulls `data["hardware"]["devices"]` (if present) into a list of `HardwareDeviceConfig` and attaches it to the returned `Config` under a top-level `hardware` attribute. Absent block → empty devices list (no exception — D-04 says booting never refuses).
    - `config/config.yaml` declares all 14 devices per D-05 criticality mapping (CONTEXT.md §Decisions and RESEARCH.md §Code Examples lines 446-529).
    - YAML round-trip: load config.yaml → assert `config.hardware.devices` has 14 entries, each with the expected role/tier/bus/address-or-path.
  </behavior>
  <action>
Edit `src/shitbox/utils/config.py`:

1. After the existing `DS18B20ProbeConfig` + `TemperatureConfig` block (around line 94), insert `HardwareDeviceConfig` and `HardwareManifestConfig` verbatim per the interfaces block above. Fields:

```python
@dataclass
class HardwareDeviceConfig:
    """Single expected device in the hardware manifest."""
    role: str = ""
    bus: str = ""
    criticality: str = "best_effort"
    description: str = ""
    address: Optional[int] = None
    path: Optional[str] = None
    sensor_id: Optional[str] = None
    pin: Optional[int] = None
    label: Optional[str] = None
    connector: Optional[str] = None


@dataclass
class HardwareManifestConfig:
    devices: List[HardwareDeviceConfig] = field(default_factory=list)
```

2. Add `hardware: HardwareManifestConfig = field(default_factory=HardwareManifestConfig)` to the `Config` dataclass (around line 472-525 where all other top-level config fields are defined).

3. In `load_config()`, after the existing DS18B20 probes coercion (around line 464-470), add the identical list-coercion block:

```python
hw_dict = data.get("hardware", {})
hw_config = HardwareManifestConfig()
devices_data = hw_dict.get("devices", []) if isinstance(hw_dict, dict) else []
hw_config.devices = [
    HardwareDeviceConfig(**d) for d in (devices_data if isinstance(devices_data, list) else [])
]
```

4. Thread `hardware=hw_config` into the `Config(...)` return at the end of `load_config()`.

Edit `config/config.yaml`:

Append a top-level `hardware:` block with all 14 devices per RESEARCH.md §Code Examples lines 444-529 (verbatim). Preserve the 3-band comment structure (`── critical ──`, `── important ──`, `── best_effort ──`). Addresses as `0xNN` literals (YAML parses to int). Paths as plain strings.

The 14 devices:
- critical: imu (i2c-1 / 0x6a), camera_front (usb / /dev/camera-front)
- important: power (i2c-1 / 0x40), gps (usb / /dev/gps0) — verify the path by reading config/config.yaml for existing gps section before writing; if config uses a different device node use that value.
- best_effort: environment (i2c-1 / 0x77), magnetometer (i2c-1 / 0x1c), light (i2c-1 / 0x10), oled (i2c-1 / 0x3c), temp_exterior (1-wire / 28-00000024263a), temp_engine_bay (1-wire / 28-0000002405b1), camera_cabin (usb / /dev/camera-cabin), audio_mic (audio / UACDemo), button (gpio / pin 17), display_hdmi (hdmi / HDMI-A-1).

Add `tests/hardware/test_hardware_manifest.py`:
- `test_hardware_manifest_loads_all_14_devices` — builds a tmp YAML string with the hardware: block, passes to a direct `yaml.safe_load` + manual coercion matching `load_config`'s logic (or calls `load_config(tmp_path)` if config loader accepts a path). Asserts `len(cfg.hardware.devices) == 14`.
- `test_hardware_manifest_device_field_round_trip` — pick the `imu` device (role=imu, bus=i2c-1, criticality=critical, address=0x6a, description="LSM6DSOX accel+gyro"). Assert each field matches.
- `test_hardware_manifest_absent_block_yields_empty_list` — YAML with no `hardware:` key → `cfg.hardware.devices == []`, no exception (D-04 contract).
- `test_hardware_manifest_bus_specific_fields` — a device with only `path` set has `address is None`; a device with only `sensor_id` has `path is None`. No cross-pollination.

Edit `tests/test_config.py`:
- Add `test_full_config_roundtrip_includes_hardware` — load the actual `config/config.yaml` via the production `load_config` path. Assert `cfg.hardware.devices` has 14 entries. Spot-check: assert any device with `role == "imu"` has `criticality == "critical"` and `address == 0x6a`.

Ruff line length 100. Full type annotations. Preserve the comment register in config.yaml ("# Each entry declares expected hardware. Boot probe verifies and records ...").
  </action>
  <verify>
    <automated>pytest tests/hardware/test_hardware_manifest.py tests/test_config.py::test_full_config_roundtrip_includes_hardware -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "class HardwareDeviceConfig" src/shitbox/utils/config.py`
    - `grep -q "class HardwareManifestConfig" src/shitbox/utils/config.py`
    - `grep -q "hardware: HardwareManifestConfig" src/shitbox/utils/config.py`
    - `grep -q "HardwareDeviceConfig(\*\*d)" src/shitbox/utils/config.py`
    - `grep -q "^hardware:" config/config.yaml`
    - `grep -c "role:" config/config.yaml` outputs >= 14 (14 in the hardware block; may be higher if `role:` appears elsewhere — confirm the hardware: block contains exactly 14 device entries via a secondary grep: `awk '/^hardware:/,/^[a-z]/' config/config.yaml | grep -c "^    - role:"` must equal 14)
    - `grep -q "criticality: critical" config/config.yaml`
    - `grep -q "criticality: important" config/config.yaml`
    - `grep -q "criticality: best_effort" config/config.yaml`
    - `grep -q "address: 0x6a" config/config.yaml` (IMU sanity check)
    - `grep -q "sensor_id: \"28-00000024263a\"" config/config.yaml` (exterior probe sanity check)
    - `pytest tests/hardware/test_hardware_manifest.py -x -q` exits 0
    - `pytest tests/test_config.py::test_full_config_roundtrip_includes_hardware -x -q` exits 0
    - `python -c "from shitbox.utils.config import load_config; cfg = load_config('config/config.yaml'); assert len(cfg.hardware.devices) == 14"` exits 0 (HW-01 end-to-end)
    - `ruff check src/shitbox/utils/config.py` exits 0
    - `mypy src/shitbox/utils/config.py` exits 0
  </acceptance_criteria>
  <done>
    HW-01 end-to-end: `load_config('config/config.yaml').hardware.devices` returns 14 typed `HardwareDeviceConfig` entries. The YAML block is readable, the loader accepts absent/malformed blocks without raising, and the round-trip test in test_config.py asserts the real config file parses correctly.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| config.yaml → runtime | YAML file read from disk at boot; parsed via `yaml.safe_load`. No untrusted remote input. |
| /sys, /proc, /dev | Kernel-exposed read-only files/paths probed by manifest probes. In-process, no subprocess, no privilege elevation. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-01-01 | Tampering | config.yaml | accept | Pi-local file ownership; no remote config push exists; editing config.yaml requires shell access to the Pi. No new attack surface over existing config. |
| T-21-01-02 | Information Disclosure | Probe log output | accept | Probe logs device addresses and paths — all already present in config.yaml and public in the repo. No secrets touched. |
| T-21-01-03 | Denial of Service | smbus2 probe holding bus open | mitigate | Probe uses `with smbus2.SMBus(bus) as smb:` to guarantee release per RESEARCH.md Pitfall 5. Enforced in acceptance criteria (grep check). |
| T-21-01-04 | Spoofing | Malicious device on I2C bus | accept | In-car physical, no public access. Any device on the bus is one we wired. Documented as out-of-scope in RESEARCH.md §Security Domain. |
| T-21-01-05 | Elevation of Privilege | `/sys` / `/proc` file reads | accept | Read-only access to kernel-exposed status files. Shitbox daemon already reads these paths (button.py, temperature.py). No new capability. |

**ASVS L1:** V5 (Input Validation) partial — YAML parsed via `safe_load`; dataclass field types constrain shape. No other categories apply (no auth, no sessions, no network, no crypto, no user-supplied runtime input).
</threat_model>

<verification>
End of plan checks:

- `pytest tests/hardware/ -x -q` — 21 (8 state + 13 probes) + 4 manifest tests = ~25 tests pass.
- `pytest tests/test_config.py -x -q` — existing tests still pass + new hardware round-trip.
- `python -c "from shitbox.utils.config import load_config; cfg = load_config('config/config.yaml'); print(len(cfg.hardware.devices))"` prints `14`.
- `python -c "from shitbox.hardware import state as s, probes as p; s.initialise({'imu':'critical'}); s.report_missing('imu'); assert s.snapshot()['imu'].next_retry_at > 0"` exits 0.
- `ruff check src/shitbox/hardware tests/hardware src/shitbox/utils/config.py` exits 0.
- `mypy src/shitbox/hardware src/shitbox/utils/config.py` exits 0.

No engine, collector, OLED, dashboard, speaker, or SSE behaviour changes in this plan — existing full test suite (`pytest`) must still pass unchanged.
</verification>

<success_criteria>
- HW-01 met: `config.yaml hardware:` block with 14 devices loads into typed `HardwareManifestConfig` with every field accessible via `.role`/`.bus`/`.address`/`.criticality`/etc.
- HW-02 substrate met: `HardwareState` module exists with `initialise`/`report_*`/`snapshot`, and per-bus probe primitives exist for i2c / 1-wire / usb / audio / hdmi / gpio plus the bit-bang bus guard.
- Backoff ladder `[5.0, 15.0, 60.0, 300.0]` is a module-level constant with a test asserting the exact schedule.
- Wave 0 test scaffolds (`tests/hardware/conftest.py` + 3 test files) exist and pass.
- No regression in the existing test suite — this plan is additive only.
</success_criteria>

<output>
After completion, create `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-01-SUMMARY.md` capturing:
- Files added / modified (list)
- Test counts (state / probes / manifest)
- Any deviations from the interfaces block (expected: none)
- Confirmation that `load_config('config/config.yaml').hardware.devices` returns 14 entries on a local dev run
</output>
