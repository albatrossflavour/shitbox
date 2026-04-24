---
phase: 15-undervoltage-and-monitoring
verified: 2026-04-24T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
notes:
  - "REQUIREMENTS.md ledger drift: PWR-01, PWR-02, MON-03 still show [ ]. Code is complete; the checkbox flip is the only outstanding artefact. Flagged as info, not a gap — the orchestrator can flip these as part of phase-close bookkeeping."
---

# Phase 15: Undervoltage and Monitoring — Verification Report

**Phase Goal:** Undervoltage is detectable and visible; the health monitoring gaps from v1.0 are closed; critical system events surface on the live dashboard.

**Verified:** 2026-04-24
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Software reads throttled bitmask and identifies current undervoltage from bits 0-3 only, ignoring sticky bits 16-19 | VERIFIED | `thermal_monitor.py:307` computes `low = raw & 0xf`; old `if raw == self._last_throttled_raw` full-word gate removed (grep returns 0 matches). Tests `test_pwr01_sticky_bits_ignored`, `test_pwr01_low_nibble_change_clears_sticky_gate` lock the behaviour in. |
| 2 | Undervoltage triggers visible alert overlay AND spoken TTS | VERIFIED | `thermal_monitor._check_throttled` calls `alerts.fire_alert("UNDERVOLTAGE", …, speak_under_voltage, sustain_required=2)` and `alerts.fire_recovery(…, speak_power_restored, recovery_subtype="UNDERVOLTAGE_CLEARED")`. Dashboard `showAlert` branches green on `_CLEARED`/`_RESTORED` suffixes. User UAT confirmed green overlay + red overlay both appear live on the Pi. |
| 3 | CPU temp, disk %, sync backlog metrics reach Prometheus end-to-end | VERIFIED | `database.py:64` schema has `cpu_percent REAL`; `insert_readings_batch` persists at lines 469 and 543; `batch_sync.py:538` emits `shitbox_cpu_pct` to Prometheus. Per D-09 and 15-04 SUMMARY, operationally confirmed in Phase 11-14; no re-verification required. |
| 4 | Prometheus scrape job label conflict resolved (shitbox-mqtt-exporter) | VERIFIED | 15-04 deleted `apps/observability/shitbox-mqtt-exporter/` in home-ops (commit `0b3dadd1`, pushed to main). Kustomize entry removed. REQUIREMENTS.md MON-02 flipped to `[x]`. |
| 5 | Thermal, undervoltage, capture failures all surface in live dashboard | VERIFIED | `sse.py` `_system_conditions_payload` emits three rows (undervoltage, thermal, capture), plumbed into `/sse/slow`. Frontend Health modal renders SYSTEM section via Alpine `x-for` above HARDWARE section. Ring buffer wires CAPTURE_FAILURE / CAPTURE_DOWN / CAPTURE_RESTORED through `alerts.fire_alert` / `fire_recovery`. Thermal was already surfacing; user UAT confirmed clean live behaviour on the Pi. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/health/alerts.py` | fire_alert, fire_recovery with recovery_subtype, snapshot, clear_state, AlertStatus; no threading.Lock | VERIFIED | All exports present (lines 32, 72, 131, 219, 224). `recovery_subtype: Optional[str] = None` at line 137. Graceful-degradation import of `dashboard_push_event`. No `threading.Lock` anywhere. |
| `src/shitbox/capture/speaker.py::speak_power_restored` | Style-matched to speak_thermal_recovered | VERIFIED | Line 445 defines `speak_power_restored`; line 454 has exact utterance `"Power restored, Michael. We're back to steady."` |
| `src/shitbox/health/thermal_monitor.py::_check_throttled` | low-nibble compare, delegates to alerts helper every cycle, no full-word gate | VERIFIED | Line 307 computes `low = raw & 0xf`; lines 326, 333-339 delegate to `alerts.fire_alert` / `fire_recovery("UNDERVOLTAGE", …, recovery_subtype="UNDERVOLTAGE_CLEARED")`. Old full-word gate gone. |
| `src/shitbox/capture/ring_buffer.py::_health_monitor` | CAPTURE_FAILURE on stall, CAPTURE_DOWN at >= 3 consecutive restarts, CAPTURE_RESTORED on recovery | VERIFIED | `_consecutive_restart_count` instance attribute at line 140. Stall branch fires CAPTURE_FAILURE (line 1013) + escalates to CAPTURE_DOWN at `>= 3` (lines 1025-1026). Crash branch does same (lines 986-988). Recovery branch fires `fire_recovery("CAPTURE_FAILURE", …, recovery_subtype="CAPTURE_RESTORED")` and resets counter (lines 952-960). Graceful-degradation import at lines 29-41. |
| `src/shitbox/dashboard/sse.py::_system_conditions_payload` | 5-scalar × 3-row payload, state derived from AlertStatus.fired/active/last_change_ts | VERIFIED | `_SYSTEM_CONDITION_LABELS` (line 92), `_SUBTYPE_TO_ROLE` (line 101), `_system_conditions_payload` (line 110), wired into `/sse/slow` at line 272. Graceful-degradation import stub present. |
| `src/shitbox/dashboard/static/index.html` | Health title, SYSTEM x-for, sc-* CSS, showAlert green branch, scGlyph/scStateText, hwBadgeClass extension | VERIFIED | Modal title "Health" (line 402). SYSTEM/HARDWARE eyebrows (lines 413, 424). `x-for="row in systemConditions"` (line 414). sc-clear/active/recovering/restored CSS (lines 44-51). showAlert `isRecovery` branch on `_CLEARED`/`_RESTORED` (line 570). `this.systemConditions = d.system_conditions` (line 623). hwBadgeClass active-condition pre-check (lines 848-850). scStateText/scGlyph (lines 892, 896). |
| `.planning/REQUIREMENTS.md` | MON-01, MON-02 flipped to [x] | PARTIAL | MON-01 and MON-02 correctly flipped to `[x]` (lines 56-57). PWR-01, PWR-02, MON-03 still show `[ ]` (lines 51, 52, 58) — these were assigned to plans 15-02, 15-03 but no plan actually flipped them. Code-level work for all three is complete; this is a ledger bookkeeping drift, not a goal gap. |
| `tests/test_alerts.py` | 10 tests covering sustain, transition, recovery, snapshot, recovery_subtype, no-lock, broken-TTS, None tts_fn | VERIFIED | All 10 test functions present (lines 25, 44, 65, 97, 111, 122, 135, 145, 158, 170). |
| `tests/test_thermal_monitor.py` | PWR-01 sticky bits, sustain-required, single-read, PWR-02 fires+recovers, TTS-once, low-nibble-change | VERIFIED | All 6 new regression tests present (lines 260, 283, 303, 321, 351, 370) alongside 11 pre-existing. |
| `tests/test_ffmpeg_stall.py` | MON-03 capture_failure_fires, capture_down_after_threshold, capture_restored_fires | VERIFIED | All 3 new tests present (lines 364, 412, 454) alongside 9 pre-existing. |
| `tests/test_dashboard.py` | 7 system_conditions payload tests | VERIFIED | All 7 tests present (lines 427, 439, 451, 470, 487, 505, 530). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `thermal_monitor._check_throttled` | `alerts.fire_alert` | Direct call with `active=bool(raw & 0xf)` | WIRED | Line 326-331 (thermal_monitor.py) |
| `thermal_monitor._check_throttled` | `alerts.fire_recovery` | `recovery_subtype="UNDERVOLTAGE_CLEARED"` | WIRED | Line 333-339 (thermal_monitor.py) |
| `thermal_monitor` | `speaker.speak_power_restored` | Import + tts_fn arg | WIRED | Import at line 25 (thermal_monitor.py); graceful fallback at line 45 |
| `ring_buffer._health_monitor` | `alerts.fire_alert("CAPTURE_FAILURE", …)` | Direct call on stall + crash branches | WIRED | Lines 1012-1013, 1025-1026 |
| `ring_buffer._health_monitor` | `alerts.fire_recovery("CAPTURE_FAILURE", …, recovery_subtype="CAPTURE_RESTORED")` | Clean segment after prior stall | WIRED | Lines 952-960 |
| `sse._system_conditions_payload` | `alerts.snapshot` | Direct call reading AlertStatus.fired/active/last_change_ts | WIRED | Lines 121, 132-139 |
| `/sse/slow` generator | `_system_conditions_payload()` | Dict entry | WIRED | Line 272 |
| `index.html openSlow()` | `/sse/slow` payload.system_conditions | `this.systemConditions = d.system_conditions \|\| []` | WIRED | Line 623 |
| `index.html showAlert` | ALERT subtype suffix | `endsWith('_CLEARED') \|\| endsWith('_RESTORED')` | WIRED | Line 570 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|---------------------|--------|
| `_system_conditions_payload` | `snap` | `alerts.snapshot()` | Returns live `_state` dict from alerts.py module-level map; module-level rebind is GIL-atomic | FLOWING |
| `index.html systemConditions` | `this.systemConditions` | Populated every `/sse/slow` tick via `openSlow()` assignment; payload populated from `_system_conditions_payload()` | FLOWING |
| `showAlert` green branch | `payload.subtype` | ALERT events emitted by alerts.py on transition (line 169 of alerts.py emits `_emit_alert(recovery_subtype or subtype, ...)`) | FLOWING |
| `thermal_monitor._last_throttled_raw` | `prev & 0xf` | Read via `_read_throttled()` (vcgencmd); low nibble gating ensures real undervoltage state drives alerts | FLOWING |
| `ring_buffer._consecutive_restart_count` | Instance attribute | Incremented on every stall/crash restart; reset on recovery | FLOWING |

### Behavioural Spot-Checks

| Behaviour | Command | Result | Status |
|-----------|---------|--------|--------|
| Full pytest suite | `pytest` | 522 passed, 1 skipped, 0 failed (per orchestrator context) | PASS |
| Live service behaviour on Pi | `systemctl status shitbox-telemetry` on 10.10.20.107 | active, sampler ~20 Hz, Prometheus writes succeeding, no error cascades (per orchestrator context) | PASS |
| User UAT of end-to-end alert → recovery dance | Manual test by user | "Manual testing looks good" — explicit confirmation | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PWR-01 | 15-02 | Current-undervoltage detection via bits 0-3, not sticky bits | SATISFIED | `raw & 0xf` gate in thermal_monitor.py:307; 4 PWR-01 tests green. **Ledger**: REQUIREMENTS.md still shows `[ ]` — flip needed at phase close. |
| PWR-02 | 15-01, 15-02, 15-05 | Undervoltage alert visible on dashboard + TTS | SATISFIED | alerts.fire_alert + fire_recovery path wired; Health modal surfaces state; `speak_under_voltage` + `speak_power_restored` fire once on transition. **Ledger**: REQUIREMENTS.md still shows `[ ]` — flip needed at phase close. |
| MON-01 | 15-04 | CPU / disk / sync backlog metrics reaching Prometheus | SATISFIED | REQUIREMENTS.md line 56 shows `[x]`. Schema + insert + emit path verified in code. |
| MON-02 | 15-04 | shitbox-mqtt-exporter scrape job retired | SATISFIED | home-ops commit `0b3dadd1` deletes the directory; REQUIREMENTS.md line 57 shows `[x]`. |
| MON-03 | 15-01, 15-03, 15-05 | Thermal + undervoltage + capture failures all visible in dashboard | SATISFIED | Ring buffer wires CAPTURE_FAILURE / CAPTURE_DOWN / CAPTURE_RESTORED; SYSTEM section in Health modal surfaces all three categories; 3 MON-03 tests green. **Ledger**: REQUIREMENTS.md still shows `[ ]` — flip needed at phase close. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODO/FIXME/placeholder markers in any Phase 15 artifact | — | Clean. |
| — | — | `threading.Lock` absent from alerts.py (capture-path-sacred rule honoured) | — | Clean. |
| — | — | `innerHTML` count unchanged in index.html (no new DOM injection risk) | — | Clean. |

### Human Verification Required

None. User explicitly confirmed UAT against the live Pi covers the visual and end-to-end dance (red overlay on failure, green overlay on recovery, Health modal SYSTEM rows reacting correctly). Treating human_verification items as satisfied per orchestrator guidance.

### Gaps Summary

No code-level gaps. One informational note:

- **REQUIREMENTS.md ledger drift**: PWR-01 (line 51), PWR-02 (line 52), and MON-03 (line 58) still carry `[ ]` despite all their code-level work being complete and confirmed via UAT. Plan 15-04 only scoped MON-01/MON-02 flips; PWR-01/02 were assigned to 15-02 and MON-03 to 15-03/15-05, but neither plan flipped the checkbox at execution time. This is a bookkeeping artifact, not a goal gap — the phase is functionally complete. Orchestrator can flip the three boxes during phase close, or leave them to a follow-up docs commit.

---

*Verified: 2026-04-24*
*Verifier: Claude (gsd-verifier)*
