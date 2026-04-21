---
phase: 21
plan: 01
subsystem: hardware
tags: [hardware-inventory, graceful-degradation, config, state, probes, tdd]
dependency_graph:
  requires: []
  provides:
    - src/shitbox/hardware/state.py (HardwareState module)
    - src/shitbox/hardware/probes.py (per-bus probe primitives)
    - src/shitbox/utils/config.py (HardwareManifestConfig + HardwareDeviceConfig)
    - config/config.yaml (hardware: block, 14 devices)
  affects:
    - downstream plans (21-02 through 21-05) that consume hw_state and probes
tech_stack:
  added: []
  patterns:
    - Module-level GIL-atomic singleton state (mirrors gps_state.py)
    - YAML list-of-dataclass loader coercion (mirrors DS18B20ProbeConfig pattern)
    - smbus2 context manager for probe isolation (Pitfall 5 guard)
    - Backoff ladder [5.0, 15.0, 60.0, 300.0]s as module-level constant
    - TDD (RED tests committed first, GREEN implementation second)
key_files:
  created:
    - src/shitbox/hardware/__init__.py
    - src/shitbox/hardware/state.py
    - src/shitbox/hardware/probes.py
    - tests/hardware/__init__.py
    - tests/hardware/conftest.py
    - tests/hardware/test_hardware_state.py
    - tests/hardware/test_hardware_probes.py
    - tests/hardware/test_hardware_manifest.py
  modified:
    - src/shitbox/utils/config.py
    - config/config.yaml
    - tests/test_config.py
decisions:
  - "HardwareDeviceConfig Optional fields (address/path/sensor_id/pin/label/connector) allow HardwareDeviceConfig(**d) for any bus type without validation failure"
  - "slots=True on DeviceStatus annotated with type: ignore[call-overload] — pre-existing mypy limitation with Python 3.9 target; ring_buffer.py has the same pattern"
  - "probe_gpio_pin checks module availability only (not pin state) — matches GPIO_AVAILABLE flag precedent in button.py"
metrics:
  duration: "7m"
  completed_date: "2026-04-21"
  tasks_completed: 3
  tasks_total: 3
  files_created: 8
  files_modified: 3
---

# Phase 21 Plan 01: Manifest, State, Probes Summary

**One-liner:** HardwareState GIL-atomic singleton + 7 per-bus probe functions + 14-device typed manifest loaded from config.yaml — Wave 1 foundations for Phase 21 graceful degradation.

## What Was Built

Three independent modules that form the vocabulary for all downstream Phase 21 plans:

**`src/shitbox/hardware/state.py`** — Module-level `_state: Dict[str, DeviceStatus]` with GIL-atomic rebind, directly mirroring `gps_state.py`. Provides `initialise` / `report_present` / `report_missing` / `report_degraded` / `snapshot` / `clear_state`. The backoff ladder `[5.0, 15.0, 60.0, 300.0]` is a module-level constant; `consecutive_misses` is clamped to `len(ladder)` so the 5-minute cap holds forever. `DeviceStatus` is a frozen slotted dataclass — readers cannot accidentally mutate it.

**`src/shitbox/hardware/probes.py`** — Seven single-shot probe functions covering every bus type in the manifest: `probe_i2c` (smbus2 context manager per Pitfall 5), `probe_usb_path`, `probe_onewire`, `probe_audio_label`, `probe_hdmi`, `probe_gpio_pin`, and `probe_i2c_bus_is_bitbang`. The bitbang guard logs `hw_manifest_bus_check_failed` at critical level when `/sys/class/i2c-adapter/i2c-1/name` does not start with `"i2c-gpio"` — this is the exact failure mode that took three days to diagnose in April 2026.

**`src/shitbox/utils/config.py` + `config/config.yaml`** — `HardwareDeviceConfig` and `HardwareManifestConfig` dataclasses inserted after the existing `DS18B20ProbeConfig` block, following the identical list-coercion pattern. The `hardware:` block in config.yaml declares 14 devices across three tiers (2 critical, 2 important, 10 best_effort) per D-05.

## Test Counts

| Module | Tests | Skipped | Notes |
|--------|-------|---------|-------|
| test_hardware_state.py | 9 | 0 | Backoff ladder, transitions, clear_state |
| test_hardware_probes.py | 13 | 1 | GPIO test skipped (no RPi on macOS) |
| test_hardware_manifest.py | 4 | 0 | 14-device count, field round-trip, absent block, isolation |
| test_config.py (new) | 1 | 0 | Full production config.yaml round-trip (HW-01) |
| **Total** | **27** | **1** | |

Full suite: 265 passed, 1 skipped, 1 warning (pre-existing uvicorn warning in dashboard tests).

## Verification Checks Passed

- `pytest tests/hardware/ -x -q` — 26 passed, 1 skipped
- `pytest tests/test_config.py -x -q` — 2 passed
- `python -c "from shitbox.utils.config import load_config; cfg = load_config('config/config.yaml'); assert len(cfg.hardware.devices) == 14"` — exits 0 (HW-01)
- `python -c "from shitbox.hardware import state as s, probes as p; s.initialise({'imu':'critical'}); s.report_missing('imu'); assert s.snapshot()['imu'].next_retry_at > 0"` — exits 0 (HW-02 substrate)
- `ruff check src/shitbox/hardware tests/hardware src/shitbox/utils/config.py` — all checks passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mypy slots=True on Python 3.9 target**

- **Found during:** Task 1 GREEN phase
- **Issue:** `@dataclass(frozen=True, slots=True)` causes `mypy` to emit `No overload variant of "dataclass" matches argument types "bool", "bool"` when `python_version = "3.9"` in pyproject.toml. `slots=True` was added in Python 3.10.
- **Fix:** Added `# type: ignore[call-overload]` to the `DeviceStatus` dataclass decorator. Pre-existing identical issue exists in `src/shitbox/events/ring_buffer.py` (same pattern).
- **Files modified:** `src/shitbox/hardware/state.py`
- **Commit:** `4e9191a`

**2. [Rule 1 - Bug] logging.py pre-existing mypy error blocks mypy acceptance check**

- **Issue:** `src/shitbox/utils/logging.py:53` has a pre-existing `Returning Any from function declared to return "BoundLogger"` error that surfaces whenever any file importing `get_logger` is checked. `gps_state.py` (the analog) passes mypy only because it does not import `get_logger`. State.py uses it for structlog event logging.
- **Impact:** `mypy src/shitbox/hardware/state.py` exits 1 due to the logging.py error (not due to anything in state.py itself). This is a pre-existing project-wide issue.
- **Decision:** Accepted as pre-existing. mypy check on state.py passes for state.py's own code — the failure is in a dependency.
- **Files modified:** None (pre-existing issue, not introduced by this plan)

## Known Stubs

None. All public API functions are fully implemented.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary crossings introduced. All probe functions read kernel-exposed read-only files or call smbus2 in-process per the existing collector pattern.

## Self-Check: PASSED

- `src/shitbox/hardware/__init__.py` — FOUND
- `src/shitbox/hardware/state.py` — FOUND
- `src/shitbox/hardware/probes.py` — FOUND
- `tests/hardware/conftest.py` — FOUND
- `tests/hardware/test_hardware_state.py` — FOUND
- `tests/hardware/test_hardware_probes.py` — FOUND
- `tests/hardware/test_hardware_manifest.py` — FOUND
- Commits: 4e9191a, 70d9903, 1d5fced — all present in git log
