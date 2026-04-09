---
phase: 11
slug: v2-hardware-migration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-09
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest --cov=shitbox` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest --cov=shitbox`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 11-01 | 01 | 1 | D-09 | unit | `pytest tests/events/test_sampler.py -x -q` | ⬜ pending |
| 11-02 | 01 | 1 | D-10/D-11 | unit | `pytest tests/collectors/test_imu_heading.py -x -q` | ⬜ pending |
| 11-03 | 02 | 2 | D-03 | unit | `pytest tests/collectors/test_temperature.py -x -q` | ⬜ pending |
| 11-04 | 02 | 2 | D-04 | unit | `pytest tests/collectors/test_light.py -x -q` | ⬜ pending |
| 11-05 | 03 | 2 | D-05 | unit | `pytest tests/collectors/test_pm25.py -x -q` | ⬜ pending |
| 11-06 | 03 | 2 | D-06 | unit | `pytest tests/collectors/test_power.py -x -q` | ⬜ pending |
| 11-07 | 04 | 3 | D-13 | manual | SSH to Pi 5, run `v4l2-ctl -d /dev/camera-front --list-formats-ext` | ⬜ pending |
| 11-08 | 04 | 3 | D-22 | automated | `pip check && python -c "import shitbox"` | ⬜ pending |
| 11-09 | 05 | 4 | D-15..D-19 | automated | `pytest tests/ -x -q` + `ruff check src/` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/events/test_sampler.py` — RED stubs for LSM6DSOX sampler (unit conversion, 100 Hz output, graceful i2c absent)
- [ ] `tests/collectors/test_imu_heading.py` — RED stubs for complementary filter + LIS3MDL heading
- [ ] `tests/collectors/test_temperature.py` — RED stubs for DS18B20 dual-probe, role mapping
- [ ] `tests/collectors/test_light.py` — RED stubs for VEML7700 lux collector
- [ ] `tests/collectors/test_pm25.py` — RED stubs for SEN0460 (disabled path + graceful absent)
- [ ] `tests/collectors/test_power.py` — RED stubs for INA226 (disabled path + graceful absent)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ELP 4K camera symlinks to `/dev/camera-front` | D-13 | Requires Pi 5 hardware | SSH to Pi 5, plug in ELP, run `ls -la /dev/camera-front` |
| DS18B20 probe IDs map to exterior/engine_bay roles | D-03 | Requires 1-Wire hardware | SSH to Pi 5, run `python -c "from w1thermsensor import W1ThermSensor; print([s.sensor_id for s in W1ThermSensor.get_available_sensors()])"` then compare to config |
| BME680 detected at 0x77 (not BME280) | D-02 | Requires I2C hardware | SSH to Pi 5, run `python -c "import board, busio, adafruit_bme680; i2c=busio.I2C(board.SCL,board.SDA); bme=adafruit_bme680.Adafruit_BME680_I2C(i2c); print(bme.temperature)"` |
| 100 Hz sampler + PiP encode don't starve each other | D-09/D-13 | Requires both devices | Run engine on Pi 5, start video capture, verify `journalctl -u shitbox-telemetry` shows no sampler_lag > 2ms |
| Artificial horizon values are plausible | D-11 | Requires IMU hardware | Place Pi flat: pitch≈0, roll≈0. Tilt 45°: value tracks. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
