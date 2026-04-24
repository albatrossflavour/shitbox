---
phase: 15-undervoltage-and-monitoring
plan: 02
type: execute
status: complete
completed: 2026-04-24
requirements: [PWR-01, PWR-02]
---

# 15-02 — PWR-01/02 Undervoltage Bug Fix

## What changed

`src/shitbox/health/thermal_monitor.py::_check_throttled` previously short-circuited when `raw == _last_throttled_raw`. That full-word gate swallowed undervoltage transitions because sticky since-boot bits 16-19 change on first occurrence and then stay put forever, masking bit-0/1 transitions that matter.

- Removed the full-word early-return gate
- Every cycle now calls `alerts.fire_alert("UNDERVOLTAGE", active=bool(raw & 0xf), ...)` and `alerts.fire_recovery("UNDERVOLTAGE", active=bool(raw & 0xf), ..., recovery_subtype="UNDERVOLTAGE_CLEARED")`
- `_last_throttled_raw` kept in its logging-only role (delta detection for log-spam reduction)
- `speak_power_restored` (from 15-01) wired behind the same `try/except ImportError` guard as the existing speaker imports

Per D-01/D-02: compare the low nibble only; require 2 consecutive reads before firing.

## Tests added (6)

- `test_pwr01_sticky_bits_ignored` — 0x50000 across 5 reads fires nothing
- `test_pwr01_sustain_required` — 0x1 then 0x0 fires nothing (transient blip)
- `test_pwr01_single_read_no_fire` — single 0x1 read fires nothing
- `test_pwr02_undervoltage_fires_then_recovers` — sustained 0x1 → one UNDERVOLTAGE; sustained 0x0 → one UNDERVOLTAGE_CLEARED with green-branch message
- `test_pwr02_tts_once_on_transition` — 5 sustained cycles fire TTS exactly once (D-12)
- `test_pwr01_low_nibble_change_clears_sticky_gate` — 0x50001 × 2 then 0x50000 × 2 fires exactly UNDERVOLTAGE then UNDERVOLTAGE_CLEARED (proves full-word gate is gone)

All 17 thermal-monitor tests pass (11 pre-existing + 6 new).

## Commits

- `05bcfdf` feat(15-02): fix PWR-01 sticky-bit undervoltage mask in thermal_monitor
- (pending) test(15-02): add PWR-01/02 regression tests
- (pending) docs(15-02): complete undervoltage fix plan

## Deviations

None functional. One docstring trimmed from 107 to under 100 chars to pass ruff.

## Downstream

15-05 Health page will surface UNDERVOLTAGE state via `alerts.snapshot()["UNDERVOLTAGE"]`. The `UNDERVOLTAGE_CLEARED` recovery subtype routes the green-branch overlay per UI-SPEC.
