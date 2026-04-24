---
phase: 15
slug: undervoltage-and-monitoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (tool.pytest.ini_options) |
| **Quick run command** | `pytest tests/health/ tests/dashboard/ -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30s quick / ~120s full |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/health/ tests/dashboard/ -x -q`
- **After every plan wave:** Run `pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Populated by the planner. Each task maps to a REQ-ID, a test type, and an automated command.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-XX-XX | XX | X | REQ-XX | — | N/A | unit | `pytest tests/...` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/health/test_alerts.py` — stubs for the new `shitbox.health.alerts` helper (sustain counting, once-on-transition, recovery semantics)
- [ ] `tests/health/test_thermal_monitor_undervoltage.py` — stubs for PWR-01 fix (low-nibble compare + N-read sustain) and PWR-02 recovery
- [ ] `tests/capture/test_ring_buffer_capture_alerts.py` — stubs for CAPTURE_FAILURE / CAPTURE_RESTORED / CAPTURE_DOWN fan-out from `_is_stalled()`
- [ ] `tests/dashboard/test_sse_system_conditions.py` — stubs for the new `_system_conditions_payload()` in `/sse/slow`
- [ ] `tests/conftest.py` — shared fixtures for mocked `push_event`, mocked TTS functions, monotonic time freeze

*All are new test files; existing fixtures in tests/conftest.py are reused where possible.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Piper TTS audibly speaks "undervoltage detected" | PWR-02 | Real audio output needs a human listener | On Pi, force low-voltage state (e.g., unplug PSU briefly); confirm Piper speaks once on transition and once on recovery |
| Full-screen red overlay appears for 10s on undervoltage | PWR-02 | Frontend render in Chromium needs a human eye | Force transition; open dashboard in browser; confirm overlay shows + green recovery overlay on clear |
| Health page renders sticky system conditions | D-13 | New UI surface needs visual confirmation | Force a condition; confirm tile stays coloured until clear; refresh page mid-condition — tile colour persists |
| MON-02 — deleted scrape job has no Prometheus series | MON-02 | Prometheus TSDB query, not a unit test | After home-ops merge + Flux reconcile, query `up{job="shitbox-mqtt-exporter"}` — should return empty |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
