---
phase: 21
plan: 02
subsystem: hardware
tags: [hardware-supervisor, tts, graceful-degradation, tdd, hw-03, hw-04]
dependency_graph:
  requires:
    - src/shitbox/hardware/state.py (Plan 01)
    - src/shitbox/hardware/probes.py (Plan 01)
    - src/shitbox/utils/config.py (Plan 01 — HardwareManifestConfig)
  provides:
    - src/shitbox/hardware/supervisor.py (HardwareSupervisor class)
    - src/shitbox/capture/speaker.py (10 new TTS lines + speak_hardware_missing/restored)
  affects:
    - Plan 05 (engine wiring — will start/stop HardwareSupervisor)
    - Plan 03 (collector hooks — will call hw_state.report_missing/present which supervisor reads)
tech_stack:
  added: []
  patterns:
    - Daemon thread with start()/stop() lifecycle (matches BatchSyncService pattern)
    - _prev_state dict for one-shot transition detection (supervisor-local, not in HardwareState)
    - _last_nag dict for critical re-nag cadence (30s bucket)
    - Tier gate duplicated in both supervisor._tick and speaker functions (defence-in-depth for testability)
    - TDD (RED tests committed first, GREEN implementation second)
key_files:
  created:
    - src/shitbox/hardware/supervisor.py
    - tests/hardware/test_hardware_supervisor.py
  modified:
    - src/shitbox/capture/speaker.py
    - tests/test_speaker_alerts.py
decisions:
  - "Tier gating duplicated in supervisor._tick AND speaker functions: supervisor gates before calling speak so tests that mock the speaker function still see correct call counts; speaker gates as defence-in-depth for callers that bypass the supervisor"
  - "consecutive_misses > 0 used as retry-scheduled sentinel instead of next_retry_at > 0: allows next_retry_at=0.0 to mean 'retry immediately at t=0' in tests, which is the natural value when monotonic=0 and report_missing hasn't been called"
  - "hw_env_missing key name corrected to hw_environment_missing: f-string lookup uses the manifest role name directly (role='environment'), so the key must be hw_environment_missing not the abbreviated form from the plan interface block"
metrics:
  duration: "8m"
  completed_date: "2026-04-21"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 2
---

# Phase 21 Plan 02: Supervisor and Speaker Summary

**One-liner:** HardwareSupervisor daemon thread with per-tier alert cadence + 10 Piper-cached hardware TTS lines, implementing HW-03 (critical re-nag every 30s, important once per transition, best_effort log-only except environment) and HW-04 (backoff-driven reprobe, restored TTS).

## What Was Built

**`src/shitbox/hardware/supervisor.py`** — `HardwareSupervisor` is a daemon thread that reads `HardwareState` (Plan 01) and owns three distinct responsibilities: boot probing, retry scheduling, and alert cadence. At `start()`, it initialises `hw_state` from the manifest, runs `_probe_all()` to seed PRESENT/MISSING for every device, then spawns a thread named `"hw-supervisor"`. The `_probe_all()` method includes the Pitfall 1 guard — if `probe_i2c_bus_is_bitbang(1)` returns False, all i2c-1 devices are marked MISSING without calling `probe_i2c` at all, avoiding a hang on a hardware-design-ware bus.

The `_tick()` method runs at 1 Hz and dispatches three branches per device. When `consecutive_misses > 0` and `now >= next_retry_at`, it calls the registered reprobe callback. A True return flips the device PRESENT and speaks the restored TTS line. A False return calls `report_missing` to advance the backoff ladder. The transition branch fires one-shot on first MISSING detection, gated by tier: critical and important always speak, best_effort is silent except the environment role (the canonical BME680 acceptance case). The re-nag branch fires for critical devices every 30s while they remain MISSING, tracked via `_last_nag`. The `_tick_loop` wraps `_tick` in a try/except, logs `hw_supervisor_tick_error`, and continues — no exception ever escapes to the thread root.

**`src/shitbox/capture/speaker.py` additions** — Ten new entries in `_CACHED_MESSAGES` for the five hardware roles with missing/restored pairs. The keys follow the f-string pattern `hw_{role}_{state}` so `speak_hardware_missing("imu", "critical")` looks up `hw_imu_missing` directly. `speak_hardware_missing` and `speak_hardware_restored` enforce `_should_alert()` gate and tier gate identically to the supervisor — this defence-in-depth means tests that mock the speaker functions still see correct tier-gated call counts, and any caller bypassing the supervisor still gets the right behaviour. The 10 new WAVs warm automatically via the existing `_warm_cache()` loop at `speaker.init()` — no extra plumbing needed.

## Test Counts

| Module | Tests | Notes |
|--------|-------|-------|
| test_hardware_supervisor.py | 10 | Tier cadence, backoff, Pitfall 1 guard, canonical BME680 |
| test_speaker_alerts.py (new) | 8 | Tier gating, unknown role fallback, _should_alert gate |
| **New total** | **18** | |

Full suite after plan: 283 passed, 1 skipped, 1 pre-existing warning.

## BME680 Canonical Case

`test_bme680_canonical_case` — **PASS**

Reproduces the documented boot-timing race (STATE.md out-of-band note 2026-04-10): environment (best_effort, i2c-1, 0x77) fails the initial `_probe_all()` because the sensor hasn't settled yet. `consecutive_misses=1`, `next_retry_at=5.0s`. At t=4.9s the retry is not yet due. At t=5.0s the reprobe callback returns True — state flips PRESENT, `speak_hardware_restored("environment", "best_effort")` is called exactly once. The test asserts the final snapshot is PRESENT and the restored function was called once with those exact args.

## Cadence Edge Cases Discovered

**next_retry_at=0.0 semantics:** The initial `DeviceStatus` from `initialise()` has `next_retry_at=0.0` meaning "not yet scheduled". Using `next_retry_at > 0` as the retry gate would have silently skipped devices that haven't been through `report_missing` yet. The correct gate is `consecutive_misses > 0` — a device has been reported missing at least once, so a backoff slot has been computed and stored in `next_retry_at`.

**Key name correction:** The plan interface block named the environment TTS key `hw_env_missing`, but the f-string lookup `f"hw_{role}_missing"` with `role="environment"` produces `"hw_environment_missing"`. The abbreviated form would always fall through to the `"{role} offline, Michael."` fallback. Fixed to `hw_environment_missing` / `hw_environment_restored` so the lookup hits the cached WAV correctly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] hw_env_missing key abbreviation mismatch**

- **Found during:** Task 1 GREEN phase (test failure)
- **Issue:** Plan interface block specified `hw_env_missing` but `speak_hardware_missing("environment", ...)` computes key `"hw_environment_missing"` via f-string. Always fell back to the generic "environment offline, Michael." text.
- **Fix:** Changed both `_CACHED_MESSAGES` keys to `hw_environment_missing` / `hw_environment_restored` and updated test references accordingly.
- **Files modified:** `src/shitbox/capture/speaker.py`, `tests/test_speaker_alerts.py`
- **Commit:** `69d0843`

**2. [Rule 2 - Missing critical functionality] Tier gate duplicated in supervisor._tick**

- **Found during:** Task 2 GREEN phase (test_best_effort_silent_except_environment failed when mock bypassed speaker's internal gate)
- **Issue:** When tests mock `speaker.speak_hardware_missing`, the tier gating inside the speaker function is bypassed. The supervisor was calling speak for all tiers unconditionally, relying entirely on the speaker to gate.
- **Fix:** Added the same `tier != "best_effort" or role == "environment"` check in `supervisor._tick` before calling `speak_hardware_missing`/`speak_hardware_restored`. This is defence-in-depth — both layers gate correctly.
- **Files modified:** `src/shitbox/hardware/supervisor.py`
- **Commit:** `8984e1c`

**3. [Rule 1 - Bug] consecutive_misses sentinel for retry gate**

- **Found during:** Task 2 GREEN phase (test_reprobe_recovers failed)
- **Issue:** Retry condition used `st.next_retry_at > 0` but test fixture set `next_retry_at=0.0` with `monotonic=0.0` to mean "retry is due at t=0". `0.0 > 0` is False so retry never fired.
- **Fix:** Changed condition to `st.consecutive_misses > 0 and now >= st.next_retry_at`. A device with `consecutive_misses=0` has never been reported missing — no retry needed. One with `consecutive_misses > 0` has a valid backoff slot in `next_retry_at`.
- **Files modified:** `src/shitbox/hardware/supervisor.py`
- **Commit:** `8984e1c`

## Known Stubs

None. All public functions are fully implemented and wired to real state/probe/speaker modules.

## Threat Flags

None. No new network endpoints, auth paths, or file access patterns introduced beyond what Plan 01 declared. The supervisor thread is in-process only; all state transitions are GIL-atomic rebinds per the Plan 01 pattern.

## Self-Check: PASSED

- `src/shitbox/hardware/supervisor.py` — FOUND
- `tests/hardware/test_hardware_supervisor.py` — FOUND
- `src/shitbox/capture/speaker.py` (modified) — FOUND, contains hw_imu_missing, speak_hardware_missing
- Commits: eae2358, 69d0843, 34bf34a, 8984e1c — all present in git log
