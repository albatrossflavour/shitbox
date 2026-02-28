---
phase: 08-capture-integrity
verified: 2026-02-28T08:20:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 8: Capture Integrity Verification Report

**Phase Goal:** Video captures are verified after save, timelapse gaps are detected and
recovered, and ffmpeg crashes during active events preserve whatever footage was captured

**Verified:** 2026-02-28T08:20:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After a video save completes, the MP4 is verified to exist with non-zero size | VERIFIED | `ring_buffer.py` line 649: `if output_path and output_path.exists() and output_path.stat().st_size > 0` |
| 2 | If verification fails, the driver hears an alert and the callback receives None | VERIFIED | `ring_buffer.py` lines 666-673: `buzzer.beep_capture_failed()` + `speaker.speak_capture_failed()` in try/except; `output_path = None` before callback |
| 3 | If no timelapse frame captured within 3x the interval while moving, a warning fires and ffmpeg restarts | VERIFIED | `engine.py` lines 1408-1426: gap watchdog with `TIMELAPSE_GAP_FACTOR = 3`, `timelapse_gap_detected` warning, `_kill_current()` + `_start_ffmpeg()` |
| 4 | Boot events with fewer than 2 buffer segments skip the video save gracefully | VERIFIED | `engine.py` lines 665-675: `boot_capture_skipped_no_segments` log, early return after saving metadata only |
| 5 | Empty post-event segments are logged as a warning for diagnostics | VERIFIED | `ring_buffer.py` lines 633-638: `video_save_post_event_empty` warning when `not post_segments` |

**Score:** 5/5 truths verified

---

## Required Artifacts

### Plan 01 Artifacts

| Artifact | Expected | Exists | Lines | Contains | Wired | Status |
|----------|----------|--------|-------|----------|-------|--------|
| `tests/test_capture_integrity.py` | Unit tests for all 3 CAPT requirements | Yes | 516 | 10 test functions | Imported and run by pytest | VERIFIED |
| `src/shitbox/capture/buzzer.py` | `beep_capture_failed()` function | Yes | 345 | `def beep_capture_failed` at line 247 | Called from `ring_buffer.py` line 669 | VERIFIED |
| `src/shitbox/capture/speaker.py` | `speak_capture_failed()` function | Yes | 450+ | `def speak_capture_failed` at line 415 | Called from `ring_buffer.py` line 670 | VERIFIED |

### Plan 02 Artifacts

| Artifact | Expected | Exists | Contains | Wired | Status |
|----------|----------|--------|----------|-------|--------|
| `src/shitbox/capture/ring_buffer.py` | Post-save verification with alert | Yes | `video_save_verification_failed` at line 658 | buzzer/speaker calls at lines 669-670 | VERIFIED |
| `src/shitbox/events/engine.py` | Boot save guard + timelapse gap watchdog | Yes | `boot_capture_skipped_no_segments` at line 670; `timelapse_gap_detected` at line 1417 | `_get_buffer_segments()` call at line 667; gap watchdog at lines 1408-1426 | VERIFIED |

---

## Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `tests/test_capture_integrity.py` | `src/shitbox/capture/ring_buffer.py` | `from shitbox.capture.ring_buffer import VideoRingBuffer` | WIRED | Line 28 of test file imports VideoRingBuffer and all 10 tests use `_make_vrb()` |
| `src/shitbox/capture/ring_buffer.py` | `src/shitbox/capture/buzzer.py` | `buzzer.beep_capture_failed()` in `_do_save_event` failure path | WIRED | Line 669: `buzzer.beep_capture_failed()` inside try/except |
| `src/shitbox/capture/ring_buffer.py` | `src/shitbox/capture/speaker.py` | `speaker.speak_capture_failed()` in `_do_save_event` failure path | WIRED | Line 670: `speaker.speak_capture_failed()` inside try/except |
| `src/shitbox/events/engine.py` | `src/shitbox/capture/ring_buffer.py` | `_get_buffer_segments()` call for boot guard check | WIRED | Line 667: `self.video_ring_buffer._get_buffer_segments()` |

---

## Test Results

All 10 capture integrity tests pass:

```
tests/test_capture_integrity.py::test_save_verification_missing_file       PASSED
tests/test_capture_integrity.py::test_save_verification_zero_byte          PASSED
tests/test_capture_integrity.py::test_save_verification_success            PASSED
tests/test_capture_integrity.py::test_save_verification_failure_alerts     PASSED
tests/test_capture_integrity.py::test_timelapse_gap_detected               PASSED
tests/test_capture_integrity.py::test_timelapse_gap_no_false_positive_at_boot PASSED
tests/test_capture_integrity.py::test_timelapse_gap_recovery               PASSED
tests/test_capture_integrity.py::test_boot_save_skipped_no_segments        PASSED
tests/test_capture_integrity.py::test_post_event_empty_segments_logged     PASSED
tests/test_capture_integrity.py::test_partial_save_pre_only                PASSED
10 passed in 0.11s
```

---

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CAPT-01 | 08-01, 08-02 | Post-save verification — detect missing/empty MP4 and alert driver | SATISFIED | `ring_buffer.py` lines 649-673: exists+size check, `video_save_verification_failed` log, buzzer/speaker alerts, `None` callback. Tests: `test_save_verification_missing_file`, `test_save_verification_zero_byte`, `test_save_verification_success`, `test_save_verification_failure_alerts` all pass |
| CAPT-02 | 08-01, 08-02 | Timelapse gap watchdog — detect no frame captured in expected interval and attempt recovery | SATISFIED | `engine.py` lines 1408-1426: `TIMELAPSE_GAP_FACTOR = 3`, `timelapse_gap_detected` warning, `_kill_current()` + `_start_ffmpeg()` recovery, `_last_timelapse_time > 0.0` boot sentinel. Tests: `test_timelapse_gap_detected`, `test_timelapse_gap_no_false_positive_at_boot`, `test_timelapse_gap_recovery` all pass |
| CAPT-03 | 08-01, 08-02 | Boot guard and partial save — skip saves with no segments; preserve pre-only footage | SATISFIED | `engine.py` lines 665-675: BOOT guard skips `save_event()` for `< 2` segments. `ring_buffer.py` lines 633-638: `video_save_post_event_empty` warning. Tests: `test_boot_save_skipped_no_segments`, `test_post_event_empty_segments_logged`, `test_partial_save_pre_only` all pass |

All 3 requirements mapped to Phase 8 in REQUIREMENTS.md are marked Complete and verified by passing tests.

---

## Anti-Patterns Found

| File | Line(s) | Pattern | Severity | Assessment |
|------|---------|---------|----------|------------|
| `src/shitbox/events/engine.py` | 397, 915 | E501 line too long | Info | Pre-existing (not in Phase 8 diff). Lines 397 and 915 were not touched by commits `3d2f56d` or `be38a6d` |
| `src/shitbox/events/engine.py` | 886-887 | F401 unused imports (`json`, `socket`) | Info | Pre-existing. Neither import introduced by Phase 8 |
| `tests/test_ffmpeg_stall.py` | 89, 110, 134, 144 | 5 of 6 stall tests fail | Warning | Pre-existing regression from a prior phase change to `_check_stall()` return type (now `Optional[dict]`, tests assert `is False`). Phase 8 summary documented this. Not caused by any Phase 8 change |

No anti-patterns were introduced by Phase 8 changes. All flags above are pre-existing and documented.

---

## Human Verification Required

None. All three CAPT requirements are fully verifiable via automated tests. The alert functions (`beep_capture_failed`, `speak_capture_failed`) require Pi hardware to be heard in the field, but their correct invocation is verified by the mock-based unit tests.

---

## Summary

Phase 8 goal is fully achieved. All three capture integrity requirements (CAPT-01, CAPT-02, CAPT-03) are implemented, tested, and passing. The key behaviours are:

- **CAPT-01** — `_do_save_event()` in `ring_buffer.py` now verifies the output MP4 exists with non-zero size after concatenation. Failure triggers audible alerts via buzzer and TTS, passes `None` to the callback, and logs a structured error.
- **CAPT-02** — `_check_timelapse()` in `engine.py` detects when more than 3x the timelapse interval passes without a capture while moving. It logs `timelapse_gap_detected`, restarts ffmpeg via `_kill_current()` + `_start_ffmpeg()`, and resets the timer. A `_last_timelapse_time > 0.0` sentinel prevents false alarms at boot.
- **CAPT-03** — `_on_event()` in `engine.py` guards BOOT events: if the ring buffer has fewer than 2 complete segments, the video save is skipped but event metadata is persisted. `_do_save_event()` additionally warns when post-event segment copy returns empty (diagnostic, non-blocking).

The 5 pre-existing failures in `test_ffmpeg_stall.py` are a `_check_stall()` return-type mismatch from a prior phase and are out of scope for Phase 8. The 4 ruff errors in `engine.py` are also pre-existing.

---

_Verified: 2026-02-28T08:20:00Z_
_Verifier: Claude (gsd-verifier)_
