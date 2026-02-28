# Phase 8: Capture Integrity - Research

**Researched:** 2026-02-28
**Domain:** ffmpeg segment pipeline integrity, file verification, timelapse monitoring
**Confidence:** HIGH

## Summary

Phase 8 hardens the video capture pipeline against three classes of failure that field-testing
exposed: (1) successful concatenation producing a missing or zero-byte output file, (2) the
timelapse monitor silently falling behind when `capture_frame()` fails repeatedly, and (3) the
boot event firing before ffmpeg has produced any buffer segments, resulting in a save with zero
pre-event footage.

The good news is that the core architecture is sound. `VideoRingBuffer._concatenate_segments()`
already checks `output_path.exists()` and `size > 0` before returning — it will return `None`
on empty output. What it does NOT do is (a) report this failure loudly back to the engine via the
callback so the driver is alerted, (b) retry from the same segments, or (c) skip gracefully when
called with zero segments at boot. The timelapse path has no watchdog — `_check_timelapse()` only
records `_last_timelapse_time` when `capture_frame()` succeeds, so a stuck segment source will
cause the interval to fire repeatedly but produce no frames and log only at DEBUG level.

All three fixes are surgical additions to existing methods. No new classes or modules are required.
The changes live entirely in `ring_buffer.py` and `engine.py`. The self-healing pattern from Phase
7 (detect → log → alert → recover) should be applied consistently.

**Primary recommendation:** Add post-save verification with TTS/buzzer alert to
`_do_save_event()`, add a timelapse gap watchdog to `_check_timelapse()`, and guard
`_on_event()` against zero-segment boot saves — all using existing infrastructure.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `subprocess` | stdlib | ffmpeg process management | Already used throughout `ring_buffer.py` |
| `pathlib.Path` | stdlib | File existence and size checks | Already used throughout; `.exists()`, `.stat().st_size` |
| `shutil` | stdlib | Segment copy and cleanup | Already used in `_copy_complete_segments()` |
| `threading` | stdlib | Background save threads | Already used for `save_event()` |
| `structlog` | `>=24.0` | Structured logging | Project standard — `log.warning(...)` with keyword args |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `shitbox.capture.speaker` | internal | TTS spoken alert | On save failure or timelapse gap — driver must hear it |
| `shitbox.capture.buzzer` | internal | Buzzer fallback alert | When speaker not available |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-process file check after concat | `ffprobe` to validate MP4 structure | `ffprobe` catches corrupt moov atoms but adds 1-2s latency per save; file size check catches the field-observed failure (zero-byte output) and is instant |
| Retry from buffer segments | Re-run full save pipeline | Segments may have been cleaned up by the time retry runs; the retry must use the segments already copied to `tmp_dir` before cleanup |
| Timelapse gap counter | Separate watchdog thread | Simpler to check age of `_last_timelapse_time` inside the existing `_check_timelapse()` call |

**Installation:** No new packages required.

## Architecture Patterns

### Recommended Project Structure

No structural changes. All modifications are in existing files:

```
src/shitbox/capture/ring_buffer.py   — VideoRingBuffer._do_save_event(), save_event() guard
src/shitbox/events/engine.py          — _check_timelapse() watchdog, _on_event() boot guard
```

### Pattern 1: Post-Save Verification (CAPT-01)

**What:** After `_concatenate_segments()` returns, verify the output MP4 exists and has non-zero
size. If verification fails, log an error, alert the driver, and invoke the callback with `None`.

**When to use:** At the end of `_do_save_event()`, after the existing `if output_path:` check.

**Current code in `_do_save_event()`** (lines 640-653 of `ring_buffer.py`):

```python
# 4. Concatenate into a single MP4
output_path = self._concatenate_segments(all_segments, prefix)
if output_path:
    log.info("video_save_complete", ...)
else:
    log.error("video_save_concatenation_failed", save_id=save_id)
if callback:
    callback(output_path)
```

**After fix** — the concatenation already returns `None` on empty/missing output; the change is
adding an explicit verification log and alert before the callback:

```python
output_path = self._concatenate_segments(all_segments, prefix)
if output_path and output_path.exists() and output_path.stat().st_size > 0:
    log.info("video_save_complete", save_id=save_id, output=str(output_path),
             size_mb=round(output_path.stat().st_size / (1024 * 1024), 2))
else:
    # Verification failed — alert driver
    log.error("video_save_verification_failed", save_id=save_id,
              output=str(output_path) if output_path else "None",
              exists=output_path.exists() if output_path else False,
              size=output_path.stat().st_size if output_path and output_path.exists() else 0)
    from shitbox.capture import buzzer, speaker
    buzzer.beep_capture_failed()
    speaker.speak_capture_failed()
    output_path = None
if callback:
    callback(output_path)
```

Note: `buzzer.beep_capture_failed()` and `speaker.speak_capture_failed()` do not yet exist — they
must be added in this phase (see Wave 0 Gaps).

### Pattern 2: Boot Save Guard — Zero Segments (CAPT-03 partial)

**What:** When the boot event fires before ffmpeg has produced any buffer segments, `save_event()`
will call `_do_save_event()` which will find zero pre-segments and log `video_save_no_segments`.
This is correct behaviour — but the log line is currently `WARNING` level and there is no guard
in `engine.py` to skip the save entirely when the buffer is clearly not ready.

**When to use:** In `engine.py` `_on_event()` before calling `video_ring_buffer.save_event()` for
`BOOT` events. A `BOOT` event with zero buffer segments should skip the video save, log at INFO,
and not call `save_event()` at all.

The `_do_save_event()` already handles the zero-segment case gracefully (`callback(None)`), so
this is a defence-in-depth guard, not a correctness fix. The key field-test finding was:

```
video_save_pre_segments count=0
```

The guard should check if the buffer has at least one complete segment before triggering the boot
save:

```python
# In engine.py _on_event(), before the existing save_event() call for VIDEO_CAPTURE_EVENTS:
if event.event_type == EventType.BOOT:
    segments = self.video_ring_buffer._get_buffer_segments()
    if len(segments) < 2:  # Need at least 2 (newest is being written)
        log.info("boot_capture_skipped_no_segments",
                 segment_count=len(segments))
        return  # Skip video save — buffer not ready
```

### Pattern 3: Timelapse Gap Watchdog (CAPT-02)

**What:** `_check_timelapse()` only updates `_last_timelapse_time` on success. If
`capture_frame()` fails repeatedly (e.g. corrupt segment, wrong mtime ordering), the engine
will call `_check_timelapse()` every loop iteration but never update the timestamp. This means
the log goes silent at DEBUG level while the driver has no timelapse images.

The fix is a separate "gap alarm" threshold. If more than `N * timelapse_interval_seconds` have
elapsed since the last successful capture while moving, log a WARNING and attempt timelapse
recovery (restart the ring buffer).

```python
# In engine.py _check_timelapse():
TIMELAPSE_GAP_FACTOR = 3  # Alert if 3x the interval passes with no capture

elapsed = now - self._last_timelapse_time
if (elapsed > self.config.timelapse_interval_seconds * TIMELAPSE_GAP_FACTOR
        and self._last_timelapse_time > 0.0
        and self._current_speed_kmh >= self.config.timelapse_min_speed_kmh):
    log.warning("timelapse_gap_detected",
                elapsed_seconds=round(elapsed),
                expected_interval=self.config.timelapse_interval_seconds)
    # Attempt recovery: restart ring buffer (calls _start_ffmpeg internally)
    if self.video_ring_buffer and self.video_ring_buffer.is_running:
        self.video_ring_buffer._kill_current()
        self.video_ring_buffer._start_ffmpeg()
    self._last_timelapse_time = now  # Reset to avoid repeat alerts
```

**Note on `_last_timelapse_time = 0.0` initialisation:** The gap check is guarded by
`_last_timelapse_time > 0.0` to avoid false alarms before the first capture attempt. This is
correct — at boot, the timelapse has never fired, so a gap is expected.

### Pattern 4: ffmpeg Crash During Active Save (CAPT-03)

**What:** When ffmpeg crashes during the `post_seconds` wait in `_do_save_event()`, the health
monitor restarts ffmpeg — but the save thread is sleeping through `time.sleep(post_seconds)`.
After the sleep, `_copy_complete_segments()` picks up whatever segments exist in the buffer. If
ffmpeg crashed mid-segment, those partial segments are filtered out by the `MIN_SEGMENT_BYTES`
check. The result is a shorter MP4 with only the pre-event footage — which is still valuable.

This is already handled correctly. The field-test finding "ffmpeg crashes during active event
recording" was caused by crash-looping (Phase 7 root cause, now fixed). With Phase 7 complete,
this scenario is rare. The verification in Pattern 1 above is the correct safety net: if the
concat produces a zero-byte file, that is caught and reported.

The one gap: if ffmpeg is completely down during the post-event sleep, the post-segment copy
will find zero new segments and the final MP4 will contain only pre-event footage. This should be
logged explicitly so it's distinguishable from a full-success save:

```python
if not post_segments:
    log.warning("video_save_post_event_empty",
                save_id=save_id,
                hint="ffmpeg may have been restarting during post-event window")
```

### Anti-Patterns to Avoid

- **Re-opening the camera device for retry:** The buffer architecture explicitly avoids this
  (`capture_frame()` reads from a completed segment, not the device). Never call
  `VideoRecorder.capture_image()` as a fallback during active ring buffer recording.
- **Blocking the event callback on retry:** `_do_save_event()` runs in a background thread;
  keeping it there is correct. Don't move save logic onto the main event loop.
- **Resetting `_last_timelapse_time` to `now` on every failed attempt:** This hides repeated
  failures. Only reset on success (existing behaviour) OR on explicit recovery action.
- **Calling `_get_buffer_segments()` without holding `_lock`:** The method itself is not
  thread-safe in the segment enumeration sense (files can be added/removed by ffmpeg), but
  calling it from the main engine thread (for the boot guard) is safe since the engine reads
  only and does not modify segments.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MP4 structural validity | Custom moov-atom parser | `output_path.stat().st_size > 0` | File size catches the field-observed failure; moov validation is overkill for this use case |
| Segment health check | Re-run ffprobe on every segment | `MIN_SEGMENT_BYTES = 10_000` (already in code) | Already filters corrupt/incomplete segments |
| Retry state machine | Custom retry manager | Simple counter + log + callback(None) | Two attempts is sufficient; the driver alert is the action |

**Key insight:** The existing `_concatenate_segments()` already handles almost all failure modes
correctly. The gap is in reporting and alerting when those failures occur, not in the detection
logic itself.

## Common Pitfalls

### Pitfall 1: `_check_stall()` Returns `Optional[dict]`, Not `bool`

**What goes wrong:** Tests in `test_ffmpeg_stall.py` assert `vrb._check_stall() is False` and
`vrb._check_stall() is True`. The actual return type is `Optional[dict[str, object]]` — `None`
for no-stall, a dict for a detected stall. `None is False` evaluates to `True` in Python (they
are different objects), but truthiness works: `if stall_info:` is correct in the health monitor.
The tests happen to pass because `None` is falsy and a non-empty dict is truthy, but new tests
should not assert `is False` — assert `is None` instead.

**Why it happens:** The test was written before the return type was changed from bool to
`Optional[dict]`.

**How to avoid:** New tests for this phase should assert `is None` (not stalled) and
`isinstance(result, dict)` (stalled).

### Pitfall 2: Boot Segment Guard Races With `_start_ffmpeg()`

**What goes wrong:** The boot event fires ~20 seconds after `video_ring_buffer.start()`. If the
Pi is slow to enumerate the camera, ffmpeg may not have produced any segments yet. The guard
`len(segments) < 2` correctly skips the save, but if the engine later processes another BOOT
event (impossible in normal flow but worth guarding), the check must not be cached.

**Why it happens:** `_get_buffer_segments()` reads the filesystem at call time, so it is always
current. No caching issue.

**How to avoid:** Call `_get_buffer_segments()` directly in the guard, not any cached state.

### Pitfall 3: `_last_timelapse_time` Resets at Boot

**What goes wrong:** `_last_timelapse_time` is initialised to `0.0`. If the gap watchdog does
not guard against this, it will fire immediately after boot (elapsed = `now - 0.0` is large)
before any timelapse has been attempted.

**Why it happens:** `0.0` is a sentinel for "never captured" but looks like a very large elapsed
time.

**How to avoid:** Guard the gap alarm with `self._last_timelapse_time > 0.0` as shown in
Pattern 3 above.

### Pitfall 4: `buzzer.beep_capture_failed()` Does Not Exist Yet

**What goes wrong:** If the verification alert calls a function that doesn't exist, it raises
`AttributeError` inside the save thread, causing the callback to never fire.

**Why it happens:** The buzzer module has pattern-specific functions (e.g.
`beep_capture_start()`, `beep_ffmpeg_stall()`) but no `beep_capture_failed()`.

**How to avoid:** Add `beep_capture_failed()` and `speak_capture_failed()` to `buzzer.py` and
`speaker.py` respectively in Wave 0 of the plan.

### Pitfall 5: Timelapse Recovery Restarts ffmpeg During an Active Save

**What goes wrong:** If the timelapse gap watchdog kills and restarts ffmpeg while a
`_do_save_event()` is in its `post_seconds` sleep, the post-event segments will come from the
newly restarted ffmpeg and may have a gap. The save is still valid (pre-event footage is already
copied) but the post-event capture will be shorter.

**Why it happens:** `_kill_current()` terminates the process; the save thread doesn't know.

**How to avoid:** Check `self._lock` state before killing, or accept the truncated post-event
footage as valid (the driver alert is more important than a complete post-event clip). Given
field usage (timelapse gap = something is already wrong), the truncated save is acceptable.

## Code Examples

Verified patterns from existing codebase:

### File Existence and Size Check (CAPT-01)

```python
# Source: src/shitbox/capture/ring_buffer.py _concatenate_segments() (existing)
if result.returncode == 0 and output_path.exists():
    size = output_path.stat().st_size
    if size > 0:
        return output_path
    # ffmpeg succeeded but produced empty file
    input_mb = round(total_input_bytes / (1024 * 1024), 2)
    log.error("concat_empty_output", input_mb=input_mb)
    output_path.unlink(missing_ok=True)
    return None
```

The verification fix in `_do_save_event()` adds a second check after `_concatenate_segments()`
returns, to confirm the file is still present (it might have been deleted by a concurrent cleanup)
and non-empty.

### Speaker Alert Pattern (from Phase 7 precedent)

```python
# Source: src/shitbox/capture/ring_buffer.py _health_monitor() (existing)
from shitbox.capture import buzzer, speaker
buzzer.beep_ffmpeg_stall()
speaker.speak_ffmpeg_stall()
```

The same import-inside-method pattern avoids circular imports and matches the Phase 7 convention.

### Structlog Keyword Pattern

```python
# Project convention: CLAUDE.md
log.warning("timelapse_gap_detected",
            elapsed_seconds=round(elapsed),
            expected_interval=self.config.timelapse_interval_seconds)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct camera capture for timelapse | Extract frame from ring buffer segment | Phase 2 (VideoRingBuffer introduction) | Avoids camera device conflict with active ffmpeg |
| Log-only on save failure | Alert + callback(None) | This phase | Driver hears the failure |
| No timelapse monitoring | Gap watchdog with recovery | This phase | Silent timelapse failures detected |

## Open Questions

1. **Should `beep_capture_failed()` use a distinct tone pattern?**
   - What we know: `beep_capture_start()` uses a short beep; `beep_ffmpeg_stall()` uses a
     distinct pattern
   - What's unclear: Whether the driver can distinguish "capture failed" from "ffmpeg stall" by
     sound alone in a noisy car
   - Recommendation: Use a double-descending tone (different from stall) for the plan; the
     planner can pick the exact Hz/ms values

2. **Should timelapse recovery restart only the ffmpeg process or also clear the buffer dir?**
   - What we know: `_start_ffmpeg()` re-creates the buffer dir; `_kill_current()` does not clear
     it
   - What's unclear: Whether stale segments in the buffer dir will confuse the new ffmpeg process
   - Recommendation: Call `_kill_current()` then `_start_ffmpeg()` (existing health monitor
     pattern); the new ffmpeg process will overwrite segments by index, not clear the dir

3. **Is a single retry sufficient for CAPT-01?**
   - What we know: `_concatenate_segments()` already includes a 60s timeout; the field failure
     was zero-byte output (not timeout)
   - What's unclear: Whether a single retry from the same segments is worthwhile (segments may
     be stale by the time of retry)
   - Recommendation: No retry — log error, alert driver via TTS/buzzer, callback(None); the
     event metadata (JSON + CSV) is already saved regardless of video success

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `pyproject.toml` (no `[tool.pytest.ini_options]` section — uses defaults) |
| Quick run command | `pytest tests/test_capture_integrity.py -x` |
| Full suite command | `pytest --cov=shitbox` |
| Estimated runtime | ~5 seconds (no subprocess calls in unit tests) |

### Phase Requirements → Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| CAPT-01 | Post-save verification detects missing file | unit | `pytest tests/test_capture_integrity.py::test_save_verification_missing_file -x` | Wave 0 gap |
| CAPT-01 | Post-save verification detects zero-byte file | unit | `pytest tests/test_capture_integrity.py::test_save_verification_zero_byte -x` | Wave 0 gap |
| CAPT-01 | Verification success logs and calls callback with path | unit | `pytest tests/test_capture_integrity.py::test_save_verification_success -x` | Wave 0 gap |
| CAPT-01 | Verification failure calls callback with None and alerts | unit | `pytest tests/test_capture_integrity.py::test_save_verification_failure_alerts -x` | Wave 0 gap |
| CAPT-02 | Timelapse gap watchdog fires after 3x interval | unit | `pytest tests/test_capture_integrity.py::test_timelapse_gap_detected -x` | Wave 0 gap |
| CAPT-02 | Timelapse gap watchdog does not fire before first capture | unit | `pytest tests/test_capture_integrity.py::test_timelapse_gap_no_false_positive_at_boot -x` | Wave 0 gap |
| CAPT-02 | Timelapse recovery restarts ffmpeg | unit | `pytest tests/test_capture_integrity.py::test_timelapse_gap_recovery -x` | Wave 0 gap |
| CAPT-03 | Zero-segment boot save is skipped gracefully | unit | `pytest tests/test_capture_integrity.py::test_boot_save_skipped_no_segments -x` | Wave 0 gap |
| CAPT-03 | Empty post-event segments logged as warning | unit | `pytest tests/test_capture_integrity.py::test_post_event_empty_segments_logged -x` | Wave 0 gap |
| CAPT-03 | Partial segments produce valid save (pre-only) | unit | `pytest tests/test_capture_integrity.py::test_partial_save_pre_only -x` | Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run:
  `pytest tests/test_capture_integrity.py -x`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~5 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_capture_integrity.py` — covers CAPT-01, CAPT-02, CAPT-03; uses `_make_vrb()`
  factory pattern from `test_ffmpeg_stall.py`
- [ ] `src/shitbox/capture/buzzer.py` — add `beep_capture_failed()` function
- [ ] `src/shitbox/capture/speaker.py` — add `speak_capture_failed()` function

No new framework install required — pytest is already in `[project.optional-dependencies]`.

## Sources

### Primary (HIGH confidence)

- `src/shitbox/capture/ring_buffer.py` — Full implementation of `VideoRingBuffer`, read in full
- `src/shitbox/events/engine.py` — Full implementation of `UnifiedEngine`, read in full
- `src/shitbox/events/storage.py` — `EventStorage.save_event()` and `update_event_video()`
- `tests/test_ffmpeg_stall.py` — Existing test factory pattern (`_make_vrb`)
- `.planning/STATE.md` — Field-test findings and decisions
- `.planning/REQUIREMENTS.md` — CAPT-01, CAPT-02, CAPT-03 definitions

### Secondary (MEDIUM confidence)

- Field-test log evidence from STATE.md: `video_save_pre_segments count=0` confirms boot event
  timing; `timelapse extraction fails with "Nothing was written"` confirms corrupt segment issue

### Tertiary (LOW confidence)

- None

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new libraries; all patterns verified from existing source
- Architecture: HIGH — patterns derived directly from current implementation and field findings
- Pitfalls: HIGH — all derived from actual field-test logs and code inspection

**Research date:** 2026-02-28
**Valid until:** 2026-03-30 (stable domain — no external dependency changes)
