---
phase: 12
slug: schema-foundation-and-logbook-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-09
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` (discovery, no separate pytest.ini) |
| **Quick run command** | `pytest tests/test_logbook.py tests/test_database.py -x` |
| **Full suite command** | `pytest --cov=shitbox` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_logbook.py tests/test_database.py -x`
- **After every plan wave:** Run `pytest --cov=shitbox`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-??-01 | TBD | 0 | NOTE-01 | unit | `pytest tests/test_logbook.py::test_create_note -x` | Wave 0 | ⬜ pending |
| 12-??-02 | TBD | 0 | NOTE-01 | unit | `pytest tests/test_logbook.py::test_note_gps_stale -x` | Wave 0 | ⬜ pending |
| 12-??-03 | TBD | 0 | NOTE-02 | unit | `pytest tests/test_logbook.py::test_note_event_pin -x` | Wave 0 | ⬜ pending |
| 12-??-04 | TBD | 0 | FUEL-01 | unit | `pytest tests/test_logbook.py::test_create_fuel_stop -x` | Wave 0 | ⬜ pending |
| 12-??-05 | TBD | 0 | FUEL-02 | unit | `pytest tests/test_logbook.py::test_fuel_efficiency -x` | Wave 0 | ⬜ pending |
| 12-??-06 | TBD | 0 | FUEL-02 | unit | `pytest tests/test_logbook.py::test_fuel_efficiency_no_odo -x` | Wave 0 | ⬜ pending |
| 12-??-07 | TBD | 0 | D-10 | unit | `pytest tests/test_logbook.py::test_fuel_json_no_cost -x` | Wave 0 | ⬜ pending |
| 12-??-08 | TBD | 0 | D-11 | unit | `pytest tests/test_database.py::test_v6_migration -x` | Wave 0 | ⬜ pending |
| 12-??-09 | TBD | 0 | D-11 | unit | `pytest tests/test_database.py::test_v6_fresh_schema -x` | Wave 0 | ⬜ pending |
| 12-??-10 | TBD | 0 | D-08/D-09 | unit | `pytest tests/test_capture_sync_generators.py -x` | Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_logbook.py` — stubs for NOTE-01, NOTE-02, FUEL-01, FUEL-02, D-10
- [ ] `tests/test_capture_sync_generators.py` — stubs for D-08, D-09
- [ ] `tests/test_database.py` additions — v6 migration cases (D-11)

*Wave 0 must run green (as stubs) before any implementation tasks begin.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| POST `/api/notes` returns GPS coordinates from live fix | NOTE-01 | Requires hardware GPS fix | curl POST on Pi with active GPS; verify `lat`/`lng` in response body |
| Fuel stop appears in `events.json` payload on Pi | FUEL-01 | Requires live rsync cycle | POST fuel stop, trigger sync, inspect `captures/fuel.json` on NAS |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
