---
slug: lsm6dsox-stationary-mean-z-zero
status: resolved
trigger: "LSM6DSOX stationary mean_z reads ~0g instead of ~1g on flat desk"
created: 2026-04-22
updated: 2026-04-22
resolved: 2026-04-22
---

# Debug Session: LSM6DSOX stationary mean_z reads ~0g instead of ~1g — RESOLVED

## Symptoms

- **Expected:** Stationary sensor on a flat, level desk reads `mean_z ≈ +1.0 g`.
- **Actual:** Auto-zero logged `mean_z ≈ 0.0004 g` and rejected with `reason=implausible`
  every 30 s window. Also blocked `auto_zero_accepted` from ever firing post-boot.
- **Environment:** Pi "laser" (10.10.20.107), v2 harness with TCA4307, LSM6DSOX at I2C 0x6A.

## Root Cause

Auto-zero's accept path at `src/shitbox/events/engine.py:1969-1973` persisted the **raw** window
mean as `accel_offset_z`. The sampler at `src/shitbox/events/sampler.py:493` subtracts
`accel_offset_z` from every read. On the first stationary accept of a boot, `mean_z ≈ +1.0 g`
(pure gravity) was stored as the offset, so every future read produced
`az = raw_az − offset ≈ 0`. Gate 5 (implausibility, `|mean_z − 1.0| > max_abs_g`) then tripped
every subsequent window because the sampler was subtracting gravity from the ring-buffer data.

Live confirmation on the Pi: `trip_state.accel_offset_z = 1.000351268797`.

## Why the pre-fix symptom looked so stable

Ring-buffer samples are `raw_read − accel_offset_z`. First boot with `offset_z = 0` stores
the gravity-including window mean (~1.000351) as the offset. Second window and onward,
`sampler.az ≈ 0` — reading looks "dead" on Z until the offset is cleared. Meanwhile Gate 6
(tolerance) silently accepted the poisoned value because old code compared `|mean_z − cur_z|`
in the same (poisoned) space.

## Fix

Commit `d413c96` — "auto-zero persists residual on Z not raw window mean".

- `engine.py::_maybe_auto_zero`:
  - Named `residual_z = mean_z - 1.0` (was `z_drift`) at the top of Gate 5, reused for:
  - Gate 6 Z delta: `abs(residual_z - cur_z)` instead of `abs(mean_z - cur_z)`.
  - Accept path: persist `residual_z` via `update_offsets`, `_current_accel_offsets`, and
    `set_trip_state("accel_offset_z", …)`.
  - `auto_zero_accepted` log emits `az=residual_z` (stored value, not raw mean).
  - `auto_zero_persist_failed.attempted_z` likewise.
- `tests/test_auto_zero.py`: post-bootstrap fixture seeds shifted from `(…, 1.02)` to
  `(…, 0.02)` (residual space). Accept-path expectations `az ≈ 1.002` → `0.002` and
  `1.025` → `0.025`. Rollback test updated.

Live DB on Pi: `UPDATE trip_state SET value_real = value_real - 1.0 WHERE key = 'accel_offset_z'`
(1.000351 → 0.000351). X/Y left untouched — they weren't poisoned.

## Verification

- Dev-laptop suite: 361 passed, 1 skipped (unrelated uvicorn test warning).
- Auto-zero suite: 16/16 green.
- Pi live, post-restart:
  - `autozero_offsets_loaded ax=0.0057 ay=-0.0122 az=0.0004 source=trip_state` at 08:55:26 UTC.
  - `auto_zero_accepted ax=0.002 ay=0.0066 az=0.0004 bootstrap=true sample_count=665`
    at 08:55:59 UTC — first stationary window accepted, all three residuals small.
  - No `implausible` rejects after restart.

root_cause: "Auto-zero stored raw window mean (~1.0 g on Z) as accel_offset_z; sampler subtracted the offset from every read, erasing gravity. Gate 5 then rejected every subsequent window as implausible."
fix: "engine.py _maybe_auto_zero: persist `mean_z - 1.0` (residual) instead of `mean_z`; Gate 6 compares residual-to-residual. Live DB on Pi corrected with UPDATE subtracting 1.0 from the poisoned value."
verification: "Dev-laptop test suite 361 passed. Pi post-restart: auto_zero_accepted fired on first stationary window with small residuals, no implausible rejects."
files_changed:
  - src/shitbox/events/engine.py
  - tests/test_auto_zero.py
  - live: /var/lib/shitbox/telemetry.db trip_state.accel_offset_z on 10.10.20.107
