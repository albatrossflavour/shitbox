---
phase: 15-undervoltage-and-monitoring
plan: 03
type: execute
status: complete
completed: 2026-04-24
requirements: [MON-03]
---

# 15-03 — MON-03 Capture-Failure Alerts

## What changed

`src/shitbox/capture/ring_buffer.py` `_health_monitor` now emits dashboard ALERT events for ffmpeg stalls via the 15-01 alerts helper:

- Import `alerts` module behind try/except ImportError (Phase 21 D-04 graceful degradation)
- New `self._consecutive_restart_count` counter initialised in `__init__`
- On stall detection: `alerts.fire_alert("CAPTURE_FAILURE", active=True, message="CAPTURE STALLED", tts_fn=speak_ffmpeg_stall)`
- After 3 consecutive restarts without a clean segment: `alerts.fire_alert("CAPTURE_DOWN", active=True, message="CAPTURE DOWN", tts_fn=speak_capture_failed)`
- On recovery (clean segment after prior stall): `alerts.fire_recovery("CAPTURE_FAILURE", active=False, message="RECORDING RESUMED", recovery_subtype="CAPTURE_RESTORED", tts_fn=speak_service_recovered)` and reset counter to 0
- `hw_state.report_degraded` + `buzzer.beep_ffmpeg_stall` still fire on every stall (no Phase 21 regression)

## Tests added (4)

- `test_mon03_capture_failure_fires` — single stall fires exactly one CAPTURE_FAILURE
- `test_mon03_capture_down_after_three_restarts` — 3rd consecutive restart fires CAPTURE_DOWN
- `test_mon03_capture_restored_on_recovery` — clean segment after prior stall fires CAPTURE_RESTORED, counter resets
- `test_mon03_no_phase21_regression` — hw_state.report_degraded + buzzer.beep_ffmpeg_stall still called on every stall

All 12 ffmpeg-stall tests pass (8 pre-existing + 4 new).

## Commits

- `7891304` feat(15-03): wire capture-failure alerts into ring buffer health monitor
- (pending) test(15-03): add MON-03 regression tests
- (pending) docs(15-03): complete capture-alerts plan

## Deviations

None.

## Downstream

15-05 Health page will surface CAPTURE state via `alerts.snapshot()["CAPTURE_FAILURE"]` in the SYSTEM section. CAPTURE_RESTORED suffix routes the green-branch overlay.
