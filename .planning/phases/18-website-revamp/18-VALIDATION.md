---
phase: 18
slug: website-revamp
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (shitbox repo); no test framework for website (static files) |
| **Config file** | `pytest.ini` / `pyproject.toml` in shitbox repo |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest --cov=shitbox` |
| **Estimated runtime** | ~10 seconds |

Note: The website (index.html) has no automated test framework. Validation is via manual browser
testing of the deployed site. Automated tests in this phase cover `batch_sync.py` metric additions
only (shitbox repo).

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest --cov=shitbox`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-xx-01 | batch_sync | 1 | WEB-04 | unit | `pytest tests/test_batch_sync_metrics.py -x -q` | W0 | pending |
| 18-xx-02 | batch_sync | 1 | WEB-04 | unit | `pytest tests/test_batch_sync_metrics.py -x -q` | W0 | pending |
| 18-xx-03 | website | 1 | WEB-01 | manual | N/A | N/A | pending |
| 18-xx-04 | website | 1 | WEB-02 | manual | N/A | N/A | pending |
| 18-xx-05 | website | 1 | WEB-03 | manual | N/A | N/A | pending |
| 18-xx-06 | website | 1 | DRVR-04 | manual | N/A | N/A | pending |
| 18-xx-07 | website | 1 | DRVR-05 | manual | N/A | N/A | pending |
| 18-xx-08 | website | 1 | NOTE-03 | manual | N/A | N/A | pending |
| 18-xx-09 | website | 1 | FUEL-03 | manual | N/A | N/A | pending |
| 18-xx-10 | nginx | 1 | WEB-01 | manual | N/A | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_batch_sync_metrics.py` — stubs for batch_sync metric additions (shitbox_lux, shitbox_temp probe label)

*Existing pytest infrastructure covers the automated subset. Wave 0 only needs the new test file.*

---

## Manual-Only Verifications

| Behaviour | Requirement | Why Manual | Test Instructions |
|-----------|-------------|------------|-------------------|
| Notes section renders with timestamp and GPS link | NOTE-03, WEB-01 | Static HTML/JS; no test framework | Open deployed site, navigate to Notes tab, verify at least one note renders with a map link |
| Fuel pins appear on Leaflet map with popup | FUEL-03, WEB-02 | DOM/Leaflet interaction | Open site, click Events tab, verify fuel pins visible as distinct colour; click one to confirm popup shows km/L, no cost field |
| Drivers tab shows current driver widget + table | DRVR-04, DRVR-05, WEB-03 | DOM rendering | Open site, click Drivers tab, verify current driver card and table both visible |
| Grafana iframe loads correct dashboard | WEB-04 | External service dependency | Open Dashboard tab, confirm iframe loads shitbox-rally-command, not shitbox-telemetry |
| Nginx serves new JSON files without stale cache | WEB-01-04 | Requires live request inspection | curl -I the site URL for notes.json and confirm Cache-Control is no-cache or short TTL |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
