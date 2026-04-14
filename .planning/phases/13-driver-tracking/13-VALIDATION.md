---
phase: 13
slug: driver-tracking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-09
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` (existing discovery) |
| **Quick run command** | `pytest tests/test_driver.py -x` |
| **Full suite command** | `pytest --cov=shitbox` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_driver.py -x`
- **After every plan wave:** Run `pytest --cov=shitbox`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-??-01 | TBD | 0 | DRVR-01 | unit | `pytest tests/test_driver.py::test_set_driver -x` | Wave 0 | ⬜ pending |
| 13-??-02 | TBD | 0 | DRVR-01 | unit | `pytest tests/test_driver.py::test_set_driver_unknown_name -x` | Wave 0 | ⬜ pending |
| 13-??-03 | TBD | 0 | DRVR-01 | unit | `pytest tests/test_driver.py::test_sse_slow_includes_active_driver -x` | Wave 0 | ⬜ pending |
| 13-??-04 | TBD | 0 | DRVR-02 | unit | `pytest tests/test_driver.py::test_driver_stats -x` | Wave 0 | ⬜ pending |
| 13-??-05 | TBD | 0 | DRVR-02 | unit | `pytest tests/test_driver.py::test_driver_stats_open_stint -x` | Wave 0 | ⬜ pending |
| 13-??-06 | TBD | 0 | DRVR-02 | unit | `pytest tests/test_driver.py::test_stint_switch_closes_previous -x` | Wave 0 | ⬜ pending |
| 13-??-07 | TBD | 0 | DRVR-03 | unit | `pytest tests/test_driver.py::test_event_attribution -x` | Wave 0 | ⬜ pending |
| 13-??-08 | TBD | 0 | DRVR-03 | unit | `pytest tests/test_driver.py::test_event_attribution_no_driver -x` | Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_driver.py` — stubs for DRVR-01, DRVR-02, DRVR-03 (all 8 cases above)

*Wave 0 must run green (as stubs) before any implementation tasks begin.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Driver dropdown populates from config roster | DRVR-01 | Requires browser on Pi | Open dashboard, verify driver names from config appear in dropdown |
| Active driver persists across page refresh | DRVR-01 | Requires browser | Refresh dashboard, verify driver name still shown |
| Stats modal shows time/% breakdown | DRVR-02 | Requires browser | Click driver name, verify modal shows each driver's time and % |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
