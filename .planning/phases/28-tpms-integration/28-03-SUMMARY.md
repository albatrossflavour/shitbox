---
phase: 28-tpms-integration
plan: 03
subsystem: tpms-foundations
tags: [tpms, config, speaker, hardware, install, scaffolding]

# Dependency graph
requires: []
provides:
  - "TpmsConfig + TpmsSensorMapEntry dataclasses with bench-validated defaults"
  - "load_config() wires the tpms: YAML block via _dict_to_dataclass + explicit list build"
  - "Top-level tpms: block in config/config.yaml with all four bench-validated sensor IDs mapped to wheel positions"
  - "tpms_radio hardware manifest entry (bus: usb_vid_pid, criticality: best_effort)"
  - "speak_tpms_low / speak_tpms_leak / speak_tpms_restored helpers backed by 12 cached messages"
  - "probe_usb_vid_pid for USB chipset enumeration via lsusb"
  - "HardwareSupervisor._run_probe dispatch for bus: usb_vid_pid"
  - "rtl-433 + librtlsdr-dev added to install.sh apt deps"
affects:
  - "28-01 (subprocess + parser tests) — test_probe_finds_sdr / test_probe_missing_sdr will go green once those tests land"
  - "28-04 (TPMSService) — imports TpmsConfig.sensor_map, sustain_required, leak_*, stale_timeout_seconds; calls speak_tpms_*"
  - "28-05 / 28-06 (engine wire-in + Health page) — read c.tpms.* and rely on hardware manifest probe"

# Tech tracking
tech-stack:
  added:
    - "rtl-433 + librtlsdr-dev system packages (Pi OS bookworm)"
  patterns:
    - "TpmsSensorMapEntry — same shape as DS18B20ProbeConfig and HardwareDeviceConfig: minimal dataclass, populated from YAML list, exposed via @property dict on parent"
    - "Explicit list-build idiom for sensors (mirrors DS18B20 probes, hardware manifest devices, GPS waypoints) — _dict_to_dataclass does not recurse into lists of dataclasses"
    - "USB VID:PID probe — subprocess.run(['lsusb'], timeout=2) with FileNotFoundError + TimeoutExpired + non-zero-exit guards, matches existing hardware/probes.py shape"
    - "TPMS speaker helpers — copy speak_power_restored shape exactly: _should_alert gate, build cache key from position, look up in _CACHED_MESSAGES, _enqueue if found"

key-files:
  created: []
  modified:
    - "src/shitbox/utils/config.py (+58 lines)"
    - "src/shitbox/capture/speaker.py (+57 lines)"
    - "src/shitbox/hardware/probes.py (+34 lines)"
    - "src/shitbox/hardware/supervisor.py (+2 lines)"
    - "config/config.yaml (+34 lines)"
    - "scripts/install.sh (+1 modified line — apt-get install gains rtl-433 librtlsdr-dev)"
    - "tests/test_config.py (+1 line — bumped device count 14 → 15)"

key-decisions:
  - "TpmsConfig defaults match SPEC verbatim: 28/25 PSI yellow/red, 5 PSI / 60 s leak window, 300 s stale timeout, sustain_required=2, x 2.45 pressure correction. Sensible TPMSService consumption defaults baked in so a missing tpms: block doesn't break load."
  - "usb_vid_pid is a NEW bus type, not a reuse of bus: usb. The existing usb branch checks /dev paths (e.g. /dev/camera-front) — RTL-SDR devices don't have stable /dev nodes, so chipset enumeration via lsusb is the correct shape."
  - "subprocess was NOT previously imported in hardware/probes.py — added at top alongside import os. Lines up alphabetically after the from __future__ block."
  - "Test for full_config_roundtrip_includes_hardware bumped from 14 to 15 devices to account for the new tpms_radio manifest entry. Documented inline that Phase 28 added the 15th device."
  - "TPMS messages are short and PSI-free per D-04 — numbers articulate poorly in a noisy cabin, and the wheel position is what the driver needs to act on. Three distinct utterance shapes ('low pressure', 'leaking', 'pressure restored') so the driver can ear-distinguish alert types from a single announcement."
  - "Invalid wheel positions are silently dropped in the speak_tpms_* helpers (no log warning). Misconfiguration only path; log noise is more annoying than useful in a noisy cabin."

requirements-completed: [SPEC-3, SPEC-7, SPEC-8, SPEC-10]

# Metrics
duration: ~9 min
completed: 2026-04-28
---

# Phase 28 Plan 03: TPMS Foundations Summary

**Configuration dataclass, three speaker helpers, USB VID:PID probe, and apt deps for rtl_433 — the scaffolding TPMSService (Plan 28-04) drops onto.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-28T09:26:25Z
- **Completed:** 2026-04-28T09:35:10Z
- **Tasks:** 3 of 3
- **Files modified:** 7

## Commits

- `a917092` — `feat(28-03): add TpmsConfig dataclass + YAML wiring`
- `b1ac152` — `feat(28-03): add speak_tpms_low/leak/restored helpers + 12 cached messages`
- `f22f8d1` — `feat(28-03): add probe_usb_vid_pid + supervisor dispatch + rtl-433 apt deps`

## Accomplishments

### Task 1: TpmsConfig + load_config wiring + config.yaml block

Added `TpmsConfig` and `TpmsSensorMapEntry` dataclasses to `src/shitbox/utils/config.py`. Wired `tpms` field onto `Config` root. Extended `load_config()` with the explicit-list-build idiom for the `sensors:` field (the same idiom used for DS18B20 probes, hardware manifest devices, and GPS waypoints — `_dict_to_dataclass` does not recurse into lists of dataclasses).

Added top-level `tpms:` block to `config/config.yaml` with all four bench-validated sensor IDs:

| Sensor ID  | Position         |
| ---------- | ---------------- |
| 550b57d9   | front-driver     |
| 54d96e8f   | front-passenger  |
| 550d14ed   | rear-driver      |
| 550b5d8a   | rear-passenger   |

Added `tpms_radio` entry to the `hardware.devices` manifest (`bus: usb_vid_pid, path: "0bda:2838", criticality: best_effort, description: "Nooelec NESDR Smart v5 ..."`).

Bumped the device-count assertion in `tests/test_config.py` from 14 to 15 (Rule 1 fix — pre-existing test asserted a hard-coded count that the new device made stale).

### Task 2: speaker.py TPMS helpers + 12 cached messages

Added 12 entries to `_CACHED_MESSAGES` covering the 4-wheel × 3-alert-type matrix. Wording per `28-CONTEXT.md` D-04, D-05, D-07:

```python
# Low pressure (sustained, 28/25 PSI thresholds)
"tpms_low_front_driver":     "Front driver tyre low pressure."
"tpms_low_front_passenger":  "Front passenger tyre low pressure."
"tpms_low_rear_driver":      "Rear driver tyre low pressure."
"tpms_low_rear_passenger":   "Rear passenger tyre low pressure."

# Active leak (5 PSI drop in 60 s)
"tpms_leak_front_driver":    "Tyre leaking, front driver."
"tpms_leak_front_passenger": "Tyre leaking, front passenger."
"tpms_leak_rear_driver":     "Tyre leaking, rear driver."
"tpms_leak_rear_passenger":  "Tyre leaking, rear passenger."

# Recovery (back above yellow threshold)
"tpms_restored_front_driver":    "Front driver tyre pressure restored."
"tpms_restored_front_passenger": "Front passenger tyre pressure restored."
"tpms_restored_rear_driver":     "Rear driver tyre pressure restored."
"tpms_restored_rear_passenger":  "Rear passenger tyre pressure restored."
```

Added three helpers (`speak_tpms_low`, `speak_tpms_leak`, `speak_tpms_restored`), each shaped exactly like `speak_power_restored`: `_should_alert` gate, build cache key from position (`f"tpms_{type}_{position.replace('-', '_')}"`), look up in `_CACHED_MESSAGES`, `_enqueue` if found. Invalid positions silently no-op.

`_warm_cache()` picks up the new keys automatically — it iterates `_CACHED_MESSAGES.items()`, so adding entries to the dict is the only change required for cached WAV pre-rendering on Pi boot.

### Task 3: probe_usb_vid_pid + supervisor dispatch + install.sh

Added `import subprocess` to `src/shitbox/hardware/probes.py` (it was NOT previously imported — the existing probes use `Path`, `os.path`, and `smbus2`). Added `probe_usb_vid_pid(vid_pid: str) -> bool` modelled on `probe_audio_label`'s subprocess-style string-scan shape:

- `subprocess.run(["lsusb"], capture_output=True, text=True, timeout=2)`
- Match `f"ID {vid_pid.lower()}"` substring in stdout
- Return `False` on `FileNotFoundError`, `subprocess.TimeoutExpired`, or non-zero exit
- structlog warning kwargs: `lsusb_not_found`, `lsusb_timeout`, `lsusb_failed`

Added `bus == "usb_vid_pid"` branch to `HardwareSupervisor._run_probe`, dispatching to `hw_probes.probe_usb_vid_pid(d.path or "")`. The existing `path` field on `HardwareDeviceConfig` carries the `0bda:2838` literal — no schema change to the manifest dataclass.

Updated `scripts/install.sh` to append `rtl-433 librtlsdr-dev` to the apt-get install line. Per `28-CONTEXT.md` D-08: Pi OS bookworm ships `rtl_433 22.11-1` which already includes protocol 156 (Abarth-124Spider / VDO-TG1C). Apt path; zero maintenance burden.

## Verification

- `tests/test_config.py` — 2/2 passed (1 modified to update device count).
- `tests/test_speaker_alerts.py` — 36/36 passed (no regression).
- `tests/hardware/` — 57 passed, 1 skipped (no regression).
- 6/6 ad-hoc verification tests for `probe_usb_vid_pid` and supervisor dispatch passed via mocked `subprocess.run` (test file deleted after verification).
- `ruff check` — clean for all six source files.
- `mypy` — only pre-existing errors (yaml stubs, RPi.GPIO stubs, `__dataclass_fields__` attr-defined, X|Y syntax) — none introduced by this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_config.py device count assertion**

- **Found during:** Task 1 verification
- **Issue:** `tests/test_config.py::test_full_config_roundtrip_includes_hardware` asserted `len(cfg.hardware.devices) == 14` — the new `tpms_radio` entry made this 15.
- **Fix:** Bumped the assertion from 14 to 15, added a one-line comment explaining Phase 28 added the 15th device.
- **Files modified:** `tests/test_config.py`
- **Commit:** `a917092` (rolled into Task 1 commit since it's a direct consequence of the same change)

## TPMSService Consumption Reference (Plan 28-04)

Plan 28-04 will read these fields from `TpmsConfig`:

| Field                          | Default            | Purpose                                        |
| ------------------------------ | ------------------ | ---------------------------------------------- |
| `enabled`                      | `False`            | Master switch                                   |
| `rtl433_protocol_id`           | `156`              | `rtl_433 -R 156` (Abarth-124Spider / VDO-TG1C) |
| `rf_frequency_hz`              | `433_920_000`      | Tuner centre frequency                          |
| `rf_gain_db`                   | `30`               | R820T2 gain                                     |
| `pressure_correction_factor`   | `2.45`             | Multiplied against decoded kPa                  |
| `low_pressure_yellow_psi`      | `28.0`             | First-warning threshold                         |
| `low_pressure_red_psi`         | `25.0`             | Critical threshold                              |
| `leak_window_seconds`          | `60.0`             | Sliding window for leak detection               |
| `leak_drop_psi`                | `5.0`              | Drop within window that fires leak alert        |
| `stale_timeout_seconds`        | `300.0`            | Mark sensor stale after this long without frame |
| `sustain_required`             | `2`                | Frames below threshold before red fires         |
| `usb_vid_pid`                  | `"0bda:2838"`      | RTL2832U + R820T2 chipset family                |
| `sensors`                      | `[]`               | List of TpmsSensorMapEntry                      |
| `sensor_map` (property)        | `{}`               | `{lower_id: position}` dict for fast lookup     |

Speaker keys for Plan 28-04 alert wiring:

```python
speak_tpms_low(position)       # position ∈ {front-driver, front-passenger, rear-driver, rear-passenger}
speak_tpms_leak(position)
speak_tpms_restored(position)
```

## Hardware Validation Flag

The lsusb VID:PID for the Nooelec NESDR Smart v5 (`0bda:2838`) is taken from `28-CONTEXT.md` D-09 (RTL2832U + R820T2 chipset family). This will need real-hardware verification on Thursday 2026-04-30 when the dongle arrives — see `28-VALIDATION.md` A4. If the actual VID:PID differs (e.g. some Nooelec stock ships with a different USB ID descriptor), update both:

1. `config/config.yaml` — `tpms.usb_vid_pid` and the `tpms_radio` device's `path` field
2. `src/shitbox/utils/config.py` — `TpmsConfig.usb_vid_pid` default

The probe code itself is VID:PID-agnostic — it just substring-matches whatever value is configured.

## Notable Implementation Notes

**`import subprocess` was added** to `src/shitbox/hardware/probes.py`. The existing probes (`probe_i2c`, `probe_usb_path`, `probe_onewire`, `probe_audio_label`, `probe_hdmi`, `probe_gpio_pin`, `probe_i2c_bus_is_bitbang`) all use `Path`, `os.path`, or `smbus2` — none had a subprocess dependency. The new import lives alongside `import os` at the top of the file, keeping the module's growing surface honest.

**The `usb_vid_pid` bus type is genuinely new.** The existing `bus: usb` checks for stable `/dev` paths (e.g. `/dev/camera-front`) backed by udev rules. RTL-SDR devices don't get udev'd to a fixed path by default — chipset enumeration via lsusb is the correct check shape, and saves us from writing yet another udev rule for hardware that has nothing to anchor a stable path against.

**Wording is locked.** Plan 28-04 should not paraphrase the cached strings — they are pre-rendered to WAV at first boot (`_warm_cache`) and any change forces a re-render cycle. If wording needs to evolve, change `_CACHED_MESSAGES` and let the next deploy regenerate the cache.

## Self-Check: PASSED

- `src/shitbox/utils/config.py` modified — verified (TpmsConfig + TpmsSensorMapEntry + tpms field on Config + tpms_config wiring in load_config)
- `src/shitbox/capture/speaker.py` modified — verified (12 _CACHED_MESSAGES keys + 3 speak_tpms_* helpers)
- `src/shitbox/hardware/probes.py` modified — verified (subprocess import + probe_usb_vid_pid)
- `src/shitbox/hardware/supervisor.py` modified — verified (`d.bus == "usb_vid_pid"` branch)
- `config/config.yaml` modified — verified (top-level tpms: block + tpms_radio device entry)
- `scripts/install.sh` modified — verified (rtl-433 librtlsdr-dev present in apt-get line)
- `tests/test_config.py` modified — verified (device count 14 → 15)
- Commits `a917092`, `b1ac152`, `f22f8d1` exist in git log
- `pytest tests/test_config.py tests/test_speaker_alerts.py tests/hardware/` — 95 passed, 1 skipped
