# Phase 11: v2 Hardware Migration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-09
**Phase:** 11-v2-hardware-migration
**Areas discussed:** Scope boundary, Environment sensor, IMU scope, Dead-code cleanup, Cutover, Unpowered sensors, Magnetometer use, Buzzer integration, Brain sync

---

## Scope boundary (freeform clarification)

Initial question: is the phase "migration only", "migration + driver display", or "migration + all v2"?

**User clarified in freeform:** scope is to walk the current codebase, remove all dead sensors, add the new ones listed in the brain note, keep power monitoring disabled, set up 2× DS18B20 one-wire, swap in the new USB webcam (ELP 4K) for the UGREEN front camera, and treat the brain note as canonical source of truth.

**Effect:** Scope is "sensor layer rewrite + dead-code cleanup + camera swap". Driver display, storage enhancements, and resilience enhancements explicitly excluded. Cutover explicitly excluded.

---

## Environment sensor

| Option | Description | Selected |
|--------|-------------|----------|
| Keep BME680 only | 0x77. Keeps gas/VOC. Matches what's on the bus. Remove BME280 refs from brain note as stale. | ✓ |
| Swap to BME280 only | 0x76. No gas/VOC. Simpler lib. | |
| Both on the bus | BME680 at 0x77 + BME280 at 0x76. Two collectors. | |

**User's choice:** Keep BME680 only
**Notes:** Brain note contains a BME680/BME280 contradiction. Brain note will be corrected.

---

## IMU scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full swap | Rewrite sampler for LSM6DSOX + add LIS3MDL mag collector. Event detection runs against new chip. MPU6050 deleted. | ✓ |
| Sampler only, no mag | Rewrite sampler for LSM6DSOX. Mag wired but ignored. | |
| Defer entirely | Leave sampler alone. | |

**User's choice:** Full swap
**Notes:** Confirms the event detector must work against the new accel/gyro source without regression.

---

## Dead-code cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Bundle cleanup | Delete pip_compositor.py, MCP9808, dead imports in ring_buffer.py, fix pyproject. | ✓ |
| Sensor swap only | Leave cleanup for a later phase. | |

**User's choice:** Bundle cleanup
**Notes:** Brain note's "Known issues to fix in v2" list is folded into this phase.

---

## Cutover

| Option | Description | Selected |
|--------|-------------|----------|
| Hard cutover | Stop old Pi services, start new Pi services, same Prometheus labels. | |
| Overlap with distinct labels | Run both with different labels during transition. | |
| Out of scope for this phase | Code-only phase; cutover handled separately. | ✓ |

**User's choice:** Out of scope
**Notes:** This phase is purely a code rewrite. Physical cutover is tracked as a deferred todo.

---

## Unpowered sensors (SEN0460 PM2.5)

| Option | Description | Selected |
|--------|-------------|----------|
| Collector in, disabled in config | Write it, ship with enabled:false, flip on when rail is wired. | ✓ |
| Defer entirely | No SEN0460 code in this phase. | |

**User's choice:** Collector in, disabled in config
**Notes:** Same treatment as INA226 — present-but-disabled pattern. Cable pinout gotcha documented in the collector.

---

## LIS3MDL magnetometer use

| Option | Description | Selected |
|--------|-------------|----------|
| Raw heading collector | 1 Hz tilt-compensated heading stored raw, no UI. | |
| Read and store raw only | Log XYZ, heading computation deferred. | |
| Full artificial horizon + heading | Complementary filter, artificial horizon, full treatment. | ✓ |

**User's choice:** Full artificial horizon + heading
**Notes:** Numbers get computed and stored in SQLite. UI consumer belongs in a later phase.

---

## PiicoDev buzzer

| Option | Description | Selected |
|--------|-------------|----------|
| Replace existing buzzer path | beep_* alerts now drive PiicoDev via I2C. | |
| Add alongside, defer integration | New buzzer interface, no alert rewiring. | |
| Skip for now | No buzzer code. | |

**User's choice:** "it's the same buzzer, so just make sure it works and keep the code"
**Notes:** This was a brain-note error — the PiicoDev buzzer is NOT new for v2, it's carried over from v1. No integration work, just smoke-test that existing `capture/buzzer.py` still runs on the new Pi. Brain note will be corrected.

---

## Brain note sync strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Brain is truth, code references it | Update brain, add canonical-ref comment in config.yaml, list in canonical_refs. | ✓ |
| Mirror brain into the repo | Copy into docs/hardware.md. | |

**User's choice:** Brain is truth, code references it
**Notes:** Repo stays slim. Brain note corrections (BME280 removal, buzzer framing fix) are tracked as follow-up.

---

## Claude's Discretion

- Event detection tuning on the new LSM6DSOX — existing HARD_BRAKE / BIG_CORNER / HIGH_G / ROUGH_ROAD thresholds may need retuning because the new chip has a better noise floor. Researcher and planner decide whether to keep existing thresholds or propose new ones.
- Whether to use LSM6DSOX FIFO for burst reads vs the existing per-sample loop in `events/sampler.py`.
- Exact lib choices where brain note is ambiguous (e.g. SEN0460: DFRobot vendor driver vs a PyPI alternative).
- Whether `capture_sync._do_sync()` backgrounding (D-21) is already handled by another phase — if so, drop it from scope.

## Deferred Ideas

- Physical cutover from old Pi to new Pi (separate op)
- INA226 wiring + battery SoC tracking
- PM2.5 rail wiring
- Button 17 wiring (code stays)
- Driver display / touchscreen UI
- Tilt/roll artificial horizon UI
- Photo capture, night mode, route replay, trip segments
- Low-battery graceful shutdown
- Pi 5 hardware watchdog via systemd
