---
phase: 15
slug: undervoltage-and-monitoring
status: draft
nyquist_compliant: true
wave_0_complete: true
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
| **Quick run command** | `pytest tests/test_alerts.py tests/test_thermal_monitor.py tests/test_ffmpeg_stall.py tests/test_dashboard.py -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30s quick / ~120s full |

---

## Sampling Rate

- **After every task commit:** Run the quick command above
- **After every plan wave:** Run `pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Each task maps to a REQ-ID, a test type, and an automated command. Commands mirror the `<verify><automated>` blocks inside each plan.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 15-01 | 0 | PWR-02, MON-03 | T-15-01-01 / 03 / 04 / 05 | sustain + transition + recovery_subtype emit | unit | `ruff check src/shitbox/health/alerts.py && python -c "from shitbox.health import alerts; assert callable(alerts.fire_alert) and callable(alerts.fire_recovery)"` | ✅ produced by this task | ⬜ pending |
| 15-01-02 | 15-01 | 0 | PWR-02 | T-15-01-02 | recovery TTS utterance exists, style-matched | unit | `grep -c "def speak_power_restored" src/shitbox/capture/speaker.py \| grep -q "^1$" && ruff check src/shitbox/capture/speaker.py` | ✅ produced by this task | ⬜ pending |
| 15-01-03 | 15-01 | 0 | PWR-02, MON-03 | T-15-01-01 / 02 / 03 / 04 / 05 | sustain, once-on-transition, Optional tts_fn, recovery_subtype rewrite, no lock | unit | `pytest tests/test_alerts.py -x -q` | ✅ produced by this task | ⬜ pending |
| 15-02-01 | 15-02 | 1 | PWR-01, PWR-02 | T-15-02-01 / 02 / 03 | low-nibble mask, delegates to helper every cycle, no full-word gate | unit | `ruff check src/shitbox/health/thermal_monitor.py && mypy src/shitbox/health/thermal_monitor.py && python -c "from shitbox.health.thermal_monitor import ThermalMonitorService; s = ThermalMonitorService(); assert hasattr(s, '_check_throttled')"` | ✅ after Task 1 | ⬜ pending |
| 15-02-02 | 15-02 | 1 | PWR-01, PWR-02 | T-15-02-01 | sticky bits ignored, sustain required, UNDERVOLTAGE + UNDERVOLTAGE_CLEARED round-trip | unit | `pytest tests/test_thermal_monitor.py -x -q` | ✅ after Task 2 | ⬜ pending |
| 15-03-01 | 15-03 | 1 | MON-03 | T-15-03-01 / 02 | CAPTURE_FAILURE fires on stall, three-strike escalation to CAPTURE_DOWN, recovery fires CAPTURE_RESTORED | unit | `ruff check src/shitbox/capture/ring_buffer.py && mypy src/shitbox/capture/ring_buffer.py` | ✅ after Task 1 | ⬜ pending |
| 15-03-02 | 15-03 | 1 | MON-03 | T-15-03-01 / 02 / 03 / 04 | MON-03 failure / escalation / recovery regression, `_read_stderr` mocked on stall-branch tests | unit | `pytest tests/test_ffmpeg_stall.py -x -v` | ✅ after Task 2 | ⬜ pending |
| 15-04-01 | 15-04 | 1 | MON-01, MON-02 | — | REQUIREMENTS checkboxes flipped | paperwork | `grep -c "^- \[x\] \*\*MON-01\*\*" .planning/REQUIREMENTS.md && grep -c "^- \[x\] \*\*MON-02\*\*" .planning/REQUIREMENTS.md` | ✅ existing file | ⬜ pending |
| 15-04-02 | 15-04 | 1 | MON-02 | T-15-04-01 / 02 | home-ops directory deleted, no kustomization entry | paperwork | `test ! -d /Users/tgreen/dev/home-ops/kubernetes/apps/observability/shitbox-mqtt-exporter && ! grep -q "shitbox-mqtt-exporter" /Users/tgreen/dev/home-ops/kubernetes/apps/observability/kustomization.yaml` | ✅ after Task 2 | ⬜ pending |
| 15-04-03 | 15-04 | 1 | MON-02 | T-15-04-01 | human diff review before push | checkpoint | n/a (human gate) | ✅ checkpoint | ⬜ pending |
| 15-04-04 | 15-04 | 1 | MON-01, MON-02 | — | both commits landed | paperwork | `git -C /Users/tgreen/dev/shitbox log --oneline -1 .planning/REQUIREMENTS.md \| grep -q "MON-01" && git -C /Users/tgreen/dev/home-ops log --oneline -1 -- kubernetes/apps/observability/ \| grep -q "shitbox-mqtt-exporter"` | ✅ after push | ⬜ pending |
| 15-05-01 | 15-05 | 2 | PWR-02, MON-03 | T-15-05-01 / 02 / 03 / 04 | five-scalar payload, always three rows, state from real AlertStatus fields | unit | `ruff check src/shitbox/dashboard/sse.py && mypy src/shitbox/dashboard/sse.py && pytest tests/test_dashboard.py -x -v -k "system_conditions"` | ✅ after Task 1 | ⬜ pending |
| 15-05-02 | 15-05 | 2 | PWR-02, MON-03 | T-15-05-01 / 03 | Alpine x-for SYSTEM block, sc-* CSS, showAlert green branch, hwBadgeClass extension | unit + markup | `python -c "import html.parser; p=html.parser.HTMLParser(); p.feed(open('src/shitbox/dashboard/static/index.html').read())" && grep -c 'x-for="row in systemConditions"' src/shitbox/dashboard/static/index.html && grep -c "_CLEARED" src/shitbox/dashboard/static/index.html` | ✅ after Task 2 | ⬜ pending |
| 15-05-03 | 15-05 | 2 | PWR-02, MON-03 | T-15-05-01 | driver-eye on modal + overlay + HW button colour | checkpoint | n/a (human gate) | ✅ checkpoint | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 for this phase is Plan 15-01 itself — the helper module plus `tests/test_alerts.py`. Every subsequent plan depends on the helper; no separate scaffolding required because the test files for 15-02, 15-03, and 15-05 are created inside those same plans (TDD-style).

- [x] `src/shitbox/health/alerts.py` — `fire_alert`, `fire_recovery` (with `recovery_subtype` kwarg), `snapshot`, `clear_state`, `AlertStatus` (15-01 Task 1)
- [x] `src/shitbox/capture/speaker.py` — `speak_power_restored` utterance (15-01 Task 2)
- [x] `tests/test_alerts.py` — 10 unit tests covering sustain, transition, recovery, Optional tts_fn, recovery_subtype rewrite, no-lock assertion (15-01 Task 3)

All subsequent test extensions (`tests/test_thermal_monitor.py`, `tests/test_ffmpeg_stall.py`, `tests/test_dashboard.py`) are additive and live inside their own plan tasks, not as pre-plan scaffolding.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Piper TTS audibly speaks "power restored" on undervoltage recovery | PWR-02 | Real audio output needs a human listener | On Pi, force low-voltage state (bench PSU or USB-C power dip); confirm Piper speaks "Power restored, Michael" exactly once on the sustained clear |
| Full-screen overlay branches red vs green by subtype | PWR-02 | Frontend render in Chromium needs a human eye | Force UNDERVOLTAGE → confirm red 10s overlay; force UNDERVOLTAGE_CLEARED → confirm green 3s overlay |
| Health modal renders SYSTEM section above HARDWARE | D-13 | New UI surface needs visual confirmation | Open Health modal; confirm SYSTEM eyebrow above HARDWARE eyebrow; confirm three rows (UNDERVOLTAGE, THERMAL, CAPTURE) always present |
| HW top-strip button flips red on any active system condition | D-13 | Cross-element reactive binding | Force UNDERVOLTAGE; confirm HW button goes red (bg-red-700); release; confirm returns to green |
| MON-02 — deleted scrape job has no Prometheus series | MON-02 | Prometheus TSDB query, not a unit test | After home-ops merge + Flux reconcile, query `up{job="shitbox-mqtt-exporter"}` — should return empty |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (only human checkpoints break continuity, and each is preceded + followed by automated work)
- [x] Wave 0 covers all helper dependencies (Plan 15-01 IS Wave 0)
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick command runs 4 test files in under 30s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
