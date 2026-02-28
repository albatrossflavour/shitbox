# Phase 7: Self-Healing and Crash-Loop Prevention - Research

**Researched:** 2026-02-28
**Domain:** Embedded Python resilience patterns — I2C bus recovery escalation, TTS speaker
health monitoring, and consistent detect-alert-recover-escalate across subsystems
**Confidence:** HIGH

## Summary

Phase 7 addresses three concrete field failures by extending infrastructure that was partially
built in earlier phases. The I2C crash-loop root cause is already partially understood: the
9-clock bit-bang recovery in `sampler.py` (`_i2c_bus_reset`) was built in Phase 2 (WDOG-04).
However, that recovery is missing two critical behaviours: it only triggers after READ failures
(not during `setup()` at startup), and it has no escalation — one attempt then immediate reboot.
When the I2C bus is still locked after a reboot, systemd restarts the process, which calls
`setup()` again, which times out again, giving ~7 PIDs in 3 minutes with all I2C devices dead.

The TTS speaker in `speaker.py` is a module-level singleton: `_voice`, `_worker`, `_running`,
`_queue`. The worker thread can silently die from a `piper` exception or a USB disconnect, and
the `_voice` reference remains non-None, causing all `speak_*()` calls to enqueue silently
(queue never drains). There is no watchdog for this thread. Detection requires checking
`_worker.is_alive()` and confirming audio output is actually happening.

The ffmpeg stall detection already exists (mtime-based, in `VideoRingBuffer`), and the
`_health_check()` method in `engine.py` already restarts `video_ring_buffer` if dead. Phase 7
must ensure ffmpeg recovery follows the same pattern as I2C and TTS (structured log,
alert via available audio, confirm recovery). The existing health check fires every 30 seconds
and already calls `buzzer.beep_alarm()` / `speaker.speak_health_alarm()` on consecutive
failures — but it does not speak a recovery confirmation, which is HEAL-03's requirement.

**Primary recommendation:** Implement escalating I2C recovery (multi-attempt with backoff
before reboot), TTS speaker watchdog in the existing `_health_check` loop, and add recovery
confirmation announcements to all three subsystems. No new service class is needed.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HEAL-01 | When the TTS speaker stops producing audio, the system detects the failure and re-initialises the speaker subsystem | `speaker._worker.is_alive()` check in `_health_check`; `speaker.init()` is idempotent and can be called again after `speaker.cleanup()` |
| HEAL-02 | When I2C bus lockups recur after a reset attempt, the system escalates (multiple reset attempts before reboot fallback) | Escalation counter on `HighRateSampler`; `_i2c_bus_reset()` already exists; `setup()` in `start()` must be wrapped in the same recovery path |
| HEAL-03 | Each self-healing subsystem follows a consistent pattern: detect failure → log → alert → attempt recovery → escalate if recovery fails | The pattern is already partially present (thermal, health watchdog); Phase 7 applies it uniformly and adds recovery confirmation TTS |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `threading` (stdlib) | Python 3.9 | Worker thread health detection (`is_alive()`) | Already used throughout; `is_alive()` is the canonical liveness check |
| `structlog` | 24.x | Structured log events for all self-healing actions | Project convention; already in use |
| `RPi.GPIO` | system | 9-clock bit-bang I2C recovery | Already used in `_i2c_bus_reset`; no alternative available |
| `smbus2` | 0.4.x | Reopen I2C bus after bit-bang | Already in use in sampler |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess` (stdlib) | Python 3.9 | `systemctl reboot` as last-resort escalation | Only after all recovery attempts exhausted |
| `time` (stdlib) | Python 3.9 | Backoff delays between recovery attempts | Built-in; no external dependency needed |
| `queue` (stdlib) | Python 3.9 | Monitoring speaker queue drain state | Already used in `speaker.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual escalation counter in `HighRateSampler` | External circuit-breaker library (`tenacity`) | `tenacity` is already a dependency but adds indirection; inline counter is simpler and testable |
| `_worker.is_alive()` check in engine `_health_check` | Dedicated speaker watchdog thread | A separate thread adds complexity; piggybacking on the existing 30-second health check is sufficient and avoids thread proliferation |
| Silence detection via audio probe | Checking `_worker.is_alive()` + queue state | Silence detection would require a loopback test; thread liveness is sufficient for the field failure modes |

**Installation:** No new packages required. All dependencies are already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure

```
src/shitbox/
├── events/
│   └── sampler.py           # Escalating I2C recovery (I2C_MAX_RESETS, reset counter)
├── capture/
│   └── speaker.py           # reinit() function; expose _worker for health check
└── events/
    └── engine.py            # _health_check extended: speaker watchdog + recovery TTS
```

No new files. All changes are modifications to existing files.

### Pattern 1: Escalating Recovery with Counter and Backoff

**What:** Rather than a single recovery attempt before reboot, maintain a reset counter.
Attempt recovery up to `I2C_MAX_RESETS` times with increasing backoff before treating the
failure as unrecoverable and rebooting.

**When to use:** I2C bus lockup in `_sample_loop` and in `setup()` during startup.

**Example:**

```python
# In HighRateSampler
I2C_MAX_RESETS = 3                  # Maximum recovery attempts before reboot
I2C_RESET_BACKOFF_SECONDS = [0, 2, 5]  # Delay before each attempt (index = attempt number)

self._reset_count: int = 0          # Persistent across the lifetime of the sampler

# In _sample_loop exception path:
if self._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
    log.warning("i2c_bus_lockup_detected",
                consecutive_failures=self._consecutive_failures,
                reset_attempt=self._reset_count + 1,
                max_resets=I2C_MAX_RESETS)
    buzzer.beep_i2c_lockup()
    speaker.speak_i2c_lockup()

    backoff = I2C_RESET_BACKOFF_SECONDS[min(self._reset_count, len(I2C_RESET_BACKOFF_SECONDS) - 1)]
    if backoff > 0:
        time.sleep(backoff)

    self._reset_count += 1
    recovered = self._i2c_bus_reset()
    if recovered:
        log.info("i2c_bus_recovery_successful", attempts=self._reset_count)
        buzzer.beep_service_recovered("i2c")
        speaker.speak_service_recovered()
        self._consecutive_failures = 0
        self._reset_count = 0       # Reset counter on success
    elif self._reset_count >= I2C_MAX_RESETS:
        log.critical("i2c_max_resets_exceeded", reset_count=self._reset_count)
        self._force_reboot()
    # else: loop continues, next failure will trigger another attempt
```

**Key insight:** The counter persists across individual failure cycles. After a successful
recovery, it resets to 0. This means a marginal I2C bus gets 3 full bit-bang attempts before
reboot — not 1.

### Pattern 2: Startup I2C Recovery (setup() wrapping)

**What:** The `setup()` method can raise `TimeoutError` when called from `start()` if the I2C
bus is locked at boot. This kills the process before the recovery logic in `_sample_loop` can
run. Wrap `setup()` with the same escalating recovery pattern.

**When to use:** In `HighRateSampler.start()` before entering `_sample_loop`.

**Example:**

```python
def start(self) -> None:
    """Start sampling in background thread."""
    if self._running:
        return

    if self._bus is None:
        for attempt in range(I2C_MAX_RESETS + 1):
            try:
                self.setup()
                break                     # Success — continue to thread start
            except Exception as e:
                log.error("sampler_setup_failed", error=str(e), attempt=attempt + 1)
                if attempt < I2C_MAX_RESETS:
                    buzzer.beep_i2c_lockup()
                    speaker.speak_i2c_lockup()
                    self._i2c_bus_reset()
                    time.sleep(I2C_RESET_BACKOFF_SECONDS[attempt])
                else:
                    log.critical("sampler_setup_unrecoverable")
                    self._force_reboot()
                    return
    # ... rest of start()
```

### Pattern 3: Speaker Worker Watchdog in Existing Health Check

**What:** Extend `engine._health_check()` to detect dead speaker worker threads and
re-initialise the speaker subsystem. The health check already runs every 30 seconds —
this satisfies the "detect within 30 seconds" requirement.

**When to use:** Inside `_health_check()` as a new numbered check after the existing ones.

**Example:**

```python
# In engine._health_check():
# 6. Speaker worker health
if self.config.speaker_enabled:
    import shitbox.capture.speaker as spk
    if spk._voice is not None and spk._worker is not None:
        if not spk._worker.is_alive():
            log.warning("speaker_worker_dead", restarting=True)
            issues.append("speaker_worker_dead")
            try:
                spk.cleanup()
                spk.init(self.config.speaker_model_path)
                recovered.append("speaker")
            except Exception as e:
                log.error("speaker_reinit_failed", error=str(e))
```

**Note:** `speaker.init()` is already written to be safe to call multiple times (it sets
`_running = True`, starts a new thread, and warms the cache). `speaker.cleanup()` stops the
existing worker and sets `_voice = None`. The `_detect_usb_speaker()` call inside `init()`
handles the case where the USB device was reconnected.

### Pattern 4: Recovery Confirmation Announcements

**What:** After a self-healing recovery, announce it via TTS (with buzzer fallback). The
existing `speaker.speak_service_recovered()` and `buzzer.beep_service_recovered()` functions
already exist. The gap is that `_health_check()` logs `health_check_recovered` but does not
call them.

**When to use:** At the end of `_health_check()` when `len(recovered) > 0`.

**Example:**

```python
if recovered:
    log.info("health_check_recovered", subsystems=recovered)
    buzzer.beep_service_recovered("subsystem")
    speaker.speak_service_recovered()
```

### Anti-Patterns to Avoid

- **Global `GPIO.cleanup()`:** Phase 2 already established: use `GPIO.cleanup([SCL_PIN, SDA_PIN])` only.
  Global cleanup would disrupt the button handler on GPIO17.
- **Resetting `_reset_count` inside `_i2c_bus_reset()`:** The escalation counter must be managed
  by the caller (`_sample_loop` and `start()`), not inside the recovery function itself — keeping
  `_i2c_bus_reset()` stateless and testable.
- **Thread proliferation:** Do not add a new watchdog thread for the speaker. The existing 30-second
  health check is sufficient and already tested.
- **Calling `speaker.init()` without `speaker.cleanup()` first:** The `_worker` will be left
  running and a second worker thread will be started alongside it, causing double-play.
- **Catching `BaseException` or `SystemExit`:** Use bare `Exception` in recovery paths so that
  `KeyboardInterrupt` and `SystemExit` are not accidentally suppressed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exponential backoff timing | Custom backoff algorithm | Inline list `[0, 2, 5]` seconds | Simple, explicit, testable; the full `tenacity` API is overkill for 3 attempts |
| Thread health monitoring | New `WatchdogThread` class | `thread.is_alive()` in existing `_health_check` | `is_alive()` is the stdlib canonical check; no edge cases |
| I2C bus locking across devices | `threading.Lock()` shared bus lock | Not needed in Phase 7 | The field test found crash-loop is the cause of multi-device failures; once crash-loop is fixed, bus contention is not the root cause. Bus-level locking is deferred. |
| Speaker audio probe | Loopback test / silence detection | `_worker.is_alive()` + `_voice is not None` | The failure modes are thread crash and USB disconnect — both are detectable without audio probing |

**Key insight:** This phase is about filling gaps in existing infrastructure, not building new
machinery. The recovery functions exist; the escalation logic and wiring are missing.

## Common Pitfalls

### Pitfall 1: `setup()` Called During `_i2c_bus_reset()` Can Raise

**What goes wrong:** `_i2c_bus_reset()` calls `self.setup()` internally (line 259 of sampler.py).
If the bus is still locked after the bit-bang, `setup()` raises again. This is currently caught
by the outer `except Exception` in `_i2c_bus_reset()` which returns `False` — correct behaviour.
However, in the `start()` wrapping pattern, calling `_i2c_bus_reset()` from the startup path
also calls `setup()`, so the caller must not call `setup()` again after `_i2c_bus_reset()`.

**How to avoid:** In the `start()` escalation loop, call only `_i2c_bus_reset()` (which includes
`setup()` internally). Do not call `setup()` separately after it.

### Pitfall 2: `speaker.init()` Silently Does Nothing When Piper Unavailable

**What goes wrong:** If `PIPER_AVAILABLE` is False or `_detect_usb_speaker()` returns None,
`speaker.init()` returns False but sets no error state. After the health check calls `init()`,
`_voice` remains None and `speak_*()` functions continue to be no-ops. This is correct
degraded behaviour but the health check must not loop calling `init()` every 30 seconds if the
USB speaker is genuinely absent.

**How to avoid:** Only trigger speaker re-initialisation when `_voice is not None` (speaker
was previously working) and `_worker is not None` and `not _worker.is_alive()` (thread
specifically died). Do not attempt re-initialisation if the speaker was never successfully
initialised in the first place (`_voice is None`).

### Pitfall 3: `_reset_count` Not Resetting After Successful Recovery

**What goes wrong:** If `_reset_count` is not reset to 0 after a successful `_i2c_bus_reset()`,
the second lockup after a recovery will immediately use the highest backoff delay and count
towards the reboot threshold as if prior recoveries failed.

**How to avoid:** Reset `_reset_count = 0` immediately after the `if recovered:` branch in
`_sample_loop`. The reset in `start()` is separate — startup attempts count independently.

### Pitfall 4: Systemd `StartLimitIntervalSec` Blocking Recovery

**What goes wrong:** The Phase 2 systemd fix set `StartLimitIntervalSec=0` (infinite restarts),
but the I2C escalation adds a reboot as last resort. If the I2C bus remains permanently locked
(hardware fault), the escalating reboot path will keep rebooting indefinitely. This is the
intended behaviour — the hardware watchdog is the final safety net.

**How to avoid:** No code fix needed. Document that `I2C_MAX_RESETS = 3` gives ~7 seconds of
recovery attempts before reboot, which is the correct trade-off for field conditions.

### Pitfall 5: Speaker Reinit During Active Audio Playback

**What goes wrong:** `speaker.cleanup()` joins the worker thread with `timeout=5.0`. If `aplay`
is mid-playback (e.g. a TTS announcement is playing), `cleanup()` sends the None sentinel and
waits up to 5 seconds. This is fine but must complete before `init()` is called.

**How to avoid:** Call `cleanup()` before `init()` in the health check re-initialisation path.
The current `cleanup()` implementation handles this correctly (sentinel + join with timeout).

### Pitfall 6: `_worker` Reference After Cleanup

**What goes wrong:** After `speaker.cleanup()`, `_worker` is set to `None`. The health check
must check for `_worker is not None` before calling `_worker.is_alive()`, or it will get
`AttributeError`.

**How to avoid:** Guard: `if spk._worker is not None and not spk._worker.is_alive()`.

## Code Examples

### Example 1: Escalation Constants (sampler.py)

```python
# Source: existing codebase pattern; extended for Phase 7
I2C_MAX_RESETS = 3
I2C_RESET_BACKOFF_SECONDS = [0, 2, 5]  # Seconds to wait before attempt 1, 2, 3
```

### Example 2: Modified `_sample_loop` Exception Path (sampler.py)

```python
except Exception as e:
    log.error("sample_read_error", error=str(e))
    self._consecutive_failures += 1

    if self._consecutive_failures >= I2C_CONSECUTIVE_FAILURE_THRESHOLD:
        log.warning(
            "i2c_bus_lockup_detected",
            consecutive_failures=self._consecutive_failures,
            reset_attempt=self._reset_count + 1,
            max_resets=I2C_MAX_RESETS,
        )
        buzzer.beep_i2c_lockup()
        speaker.speak_i2c_lockup()

        backoff = I2C_RESET_BACKOFF_SECONDS[
            min(self._reset_count, len(I2C_RESET_BACKOFF_SECONDS) - 1)
        ]
        if backoff > 0:
            time.sleep(backoff)

        self._reset_count += 1
        recovered = self._i2c_bus_reset()

        if recovered:
            log.info(
                "i2c_bus_recovery_successful",
                attempt=self._reset_count,
            )
            buzzer.beep_service_recovered("i2c")
            speaker.speak_service_recovered()
            self._consecutive_failures = 0
            self._reset_count = 0
        elif self._reset_count >= I2C_MAX_RESETS:
            log.critical(
                "i2c_max_resets_exceeded",
                reset_count=self._reset_count,
            )
            self._force_reboot()
        # else: continue loop, next lockup fires another attempt
```

### Example 3: Speaker Health Check Insertion (engine.py `_health_check`)

```python
# 6. Speaker worker health (HEAL-01)
import shitbox.capture.speaker as _spk
if (
    self.config.speaker_enabled
    and _spk._voice is not None
    and _spk._worker is not None
    and not _spk._worker.is_alive()
):
    log.warning("speaker_worker_dead", restarting=True)
    issues.append("speaker_worker_dead")
    try:
        _spk.cleanup()
        if _spk.init(self.config.speaker_model_path):
            recovered.append("speaker")
            log.info("speaker_reinitialised")
        else:
            log.error("speaker_reinit_failed_no_device")
    except Exception as e:
        log.error("speaker_reinit_exception", error=str(e))
```

### Example 4: Recovery Confirmation in `_health_check` (HEAL-03)

```python
# After the existing `if recovered:` block:
if recovered:
    log.info("health_check_recovered", subsystems=recovered)
    buzzer.beep_service_recovered("subsystem")
    speaker.speak_service_recovered()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One bit-bang attempt then immediate reboot | Escalating multi-attempt with backoff | Phase 7 | Eliminates crash-loop for transient lockups; permanent failures still reboot |
| No setup() protection | setup() wrapped in escalation loop | Phase 7 | Prevents startup crash-loop that caused the field failures |
| No speaker health check | 30s health check includes `is_alive()` guard | Phase 7 | Silent TTS failures detectable within 30 seconds |
| Health check logs recovery but doesn't announce | Recovery confirmed via TTS/buzzer | Phase 7 | Driver hears confirmation — HEAL-03 |

**Deprecated/outdated:**

- The single-attempt `_force_reboot()` immediately after `_i2c_bus_reset()` returns False: replaced
  by counter-gated reboot with escalation. The `_force_reboot()` function itself is kept but
  called only after `_reset_count >= I2C_MAX_RESETS`.

## Open Questions

1. **Should `_reset_count` persist across `stop()`/`start()` cycles?**
   - What we know: The engine health check calls `sampler.stop()` then `sampler.start()` if the
     thread is dead (line 1778-1779 of engine.py). If `_reset_count` persists, a restarted
     sampler inherits prior failure state.
   - What's unclear: Should a clean restart credit the sampler with a clean slate?
   - Recommendation: Reset `_reset_count = 0` in `stop()`. A service restart is a clean
     recovery event and should start the escalation counter fresh.

2. **Should the I2C `setup()` startup protection call `_i2c_bus_reset()` or a simpler retry?**
   - What we know: `_i2c_bus_reset()` always performs GPIO bit-bang. During startup, the bus
     may not be locked — it might just be slow. A retry without GPIO manipulation is safer.
   - What's unclear: The field logs show `TimeoutError in sampler.py:setup()` — bus is locked.
   - Recommendation: Use the same `_i2c_bus_reset()` for consistency (HEAL-03 requires uniform
     pattern). Add a log distinguishing startup vs runtime recovery.

3. **Is speaker `_worker.is_alive()` sufficient to detect queue overflow silence?**
   - What we know: Queue overflow causes messages to be dropped (debug-logged), but the worker
     thread stays alive. `_worker.is_alive()` does not detect queue overflow.
   - What's unclear: Whether queue overflow silence is a persistent state or self-clearing.
   - Recommendation: Queue is `maxsize=2` and drains after each message (serial playback).
     Overflow is transient — low-priority messages get dropped, high-priority ones eventually
     get through when queue drains. This is acceptable and does not need health-check coverage.
     If the worker is alive and `_voice is not None`, the speaker is functional.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` not present — uses defaults) |
| Quick run command | `pytest tests/test_i2c_recovery.py tests/test_speaker_alerts.py -x -q` |
| Full suite command | `pytest -x -q` |
| Estimated runtime | ~5 seconds |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| HEAL-02 | Escalation counter increments across reset attempts | unit | `pytest tests/test_i2c_recovery.py -x -q` | Partial — existing file needs new tests |
| HEAL-02 | Reboot not triggered until `_reset_count >= I2C_MAX_RESETS` | unit | `pytest tests/test_i2c_recovery.py -x -q` | Partial |
| HEAL-02 | Backoff delay applied between attempts | unit | `pytest tests/test_i2c_recovery.py -x -q` | Partial |
| HEAL-02 | `setup()` in `start()` attempts recovery on `TimeoutError` | unit | `pytest tests/test_i2c_recovery.py -x -q` | Partial |
| HEAL-02 | `_reset_count` resets to 0 after successful recovery | unit | `pytest tests/test_i2c_recovery.py -x -q` | Partial |
| HEAL-01 | Dead speaker worker detected by `_health_check` within 30s | unit | `pytest tests/test_speaker_alerts.py -x -q` | Partial |
| HEAL-01 | `speaker.cleanup()` + `speaker.init()` called when worker dead | unit | `pytest tests/test_speaker_alerts.py -x -q` | Partial |
| HEAL-01 | No reinit attempted when `_voice is None` (never initialised) | unit | `pytest tests/test_speaker_alerts.py -x -q` | Partial |
| HEAL-03 | `speak_service_recovered()` called after successful health-check recovery | unit | `pytest tests/test_speaker_alerts.py -x -q` | Partial |
| HEAL-03 | All three subsystems (I2C, TTS, ffmpeg) log `structured` event before alert | unit | `pytest tests/test_i2c_recovery.py tests/test_speaker_alerts.py -x -q` | Partial |

"Partial" = test file exists but does not yet contain tests for the new behaviour.
New test functions must be added to existing files.

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run:
  `pytest tests/test_i2c_recovery.py tests/test_speaker_alerts.py -x -q`
- **Full suite trigger:** Before merging the final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~5 seconds

### Wave 0 Gaps

No new test files need to be created. All new tests are added to existing files:

- `tests/test_i2c_recovery.py` — add escalation tests (multi-attempt, backoff, `setup()` startup)
- `tests/test_speaker_alerts.py` — add health-check watchdog tests (dead worker, reinit, no-op
  when never initialised)

*(No new framework install required — pytest already configured)*

## Sources

### Primary (HIGH confidence)

- Codebase read: `src/shitbox/events/sampler.py` — complete I2C recovery implementation
- Codebase read: `src/shitbox/capture/speaker.py` — complete speaker module-level state
- Codebase read: `src/shitbox/events/engine.py` — `_health_check()` implementation (lines
  1763-1847), `start()` method (lines 1447-1640), `sampler.start()` wiring (line 1603)
- Codebase read: `tests/test_i2c_recovery.py` — existing 6 tests for Phase 2 recovery
- Codebase read: `tests/test_speaker_alerts.py` — existing 12 tests for Phase 5 audio
- Python docs: `threading.Thread.is_alive()` — canonical thread liveness check (stdlib)

### Secondary (MEDIUM confidence)

- Field test findings in `.planning/STATE.md`: I2C crash-loop pattern (~7 PIDs in 3 min),
  TTS silence modes (USB power, queue overflow, worker thread crash), crash-loop kills in-
  progress video saves
- Phase 2 summary (`02-03-SUMMARY.md`): GPIO mock pattern, selective cleanup decision,
  `I2C_RECOVERY_DELAY_SECONDS` rationale

### Tertiary (LOW confidence)

- None. All findings are from direct codebase inspection or project documentation.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — verified by reading pyproject.toml and all affected source files
- Architecture: HIGH — patterns derived from existing code; no speculation
- Pitfalls: HIGH — each pitfall identified from direct code inspection, not general knowledge
- Validation: HIGH — existing test infrastructure confirmed by reading test files

**Research date:** 2026-02-28
**Valid until:** 2026-04-28 (stable — no fast-moving dependencies)
