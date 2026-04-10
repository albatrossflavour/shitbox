---
phase: 17
slug: driver-display
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_dashboard.py tests/test_thermal_monitor.py -x` |
| **Full suite command** | `pytest --cov=shitbox` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_dashboard.py tests/test_thermal_monitor.py -x`
- **After every plan wave:** Run `pytest --cov=shitbox`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 0 | DISP-01 | unit | `pytest tests/test_engine_boot.py -x -k temperature` | Yes (add) | ⬜ pending |
| 17-01-02 | 01 | 0 | DISP-04 | unit | `pytest tests/test_thermal_monitor.py -x -k alert` | No — Wave 0 | ⬜ pending |
| 17-01-03 | 01 | 0 | DISP-02 | unit | `pytest tests/test_dashboard.py -x -k ticker` | No — Wave 0 | ⬜ pending |
| 17-01-04 | 01 | 0 | DISP-03 | unit | `pytest tests/test_dashboard.py::test_sse_slow_schema -x` | Yes (extend) | ⬜ pending |
| 17-02-01 | 02 | 1 | DISP-01 | manual | Browser on Pi at 800x480 | N/A | ⬜ pending |
| 17-02-02 | 02 | 1 | DISP-04 | unit | `pytest tests/test_thermal_monitor.py -x -k alert` | Wave 0 | ⬜ pending |
| 17-02-03 | 02 | 1 | DISP-01 | unit | `pytest tests/test_dashboard.py::test_sse_slow_schema -x` | Yes | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_thermal_monitor.py` — add `test_thermal_warning_pushes_dashboard_alert()` and `test_undervoltage_pushes_dashboard_alert()` — covers DISP-04
- [ ] `tests/test_dashboard.py` — add `test_sse_slow_has_active_driver_key()` — covers DISP-03
- [ ] `tests/test_dashboard.py` — add `test_event_ticker_max_five()` — covers DISP-02
- [ ] `tests/test_engine_boot.py` — add `test_on_reading_temperature_updates_cabin_temp()` — covers DISP-01 temperature fix

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Kiosk layout renders correctly at 800x480 | DISP-01 | Visual layout requires browser on Pi display | Open `http://localhost:8080` in Chromium at 800x480; verify speed dominant, G-gauge, temps, driver, event ticker all visible without scrolling |
| Alert overlay auto-dismisses after correct duration | DISP-04 | Timing requires human observation | Trigger a HIGH_G event; verify overlay appears and auto-dismisses within ~3s. Trigger a thermal alert (SIGUSR1 or manual); verify overlay stays ~10s |
| Map overlay opens and closes on tap | DISP-01 | Touch interaction on Pi screen | Tap MAP button; verify full-screen Leaflet loads. Tap anywhere to dismiss. |
| Distance to waypoint updates live | DISP-01 | Requires GPS fix or simulated position | With GPS active, verify distance tile shows km to next waypoint and updates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
