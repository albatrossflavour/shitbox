---
phase: 15-undervoltage-and-monitoring
reviewed: 2026-04-24
depth: standard
status: issues_found
files_reviewed: 10
findings:
  critical: 0
  warning: 7
  info: 5
  total: 12
---

# Phase 15: Code Review Report

**Reviewed:** 2026-04-24
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 15 delivers the shared `alerts.py` sustain helper, fixes the PWR-01 sticky-bit regression in `thermal_monitor.py`, wires capture-stall alerts through the ring buffer, and surfaces a SYSTEM section on the Health modal. The mechanical work is sound: the PWR-01 fix correctly masks `raw & 0xf` (thermal_monitor.py:307-313), sticky-bit regression coverage exists in `test_pwr01_low_nibble_change_clears_sticky_gate`, the SSE payload sticks to exactly five scalar fields per row, and the Alpine bindings on the SYSTEM section use `x-text` throughout (no `x-html`/`innerHTML` injection vector).

There are several real concurrency and correctness issues worth fixing. The alerts helper's claim of "GIL-atomic rebind" for safety from multiple threads is incorrect in the general case. In practice the caller pattern here is single-threaded per-subtype, so the race is cosmetic for now, but the docstring overstates the safety guarantee. There's also a genuine latent bug in the `CAPTURE_DOWN` wiring: it fires via `fire_alert` but never gets a matching `fire_recovery`, so after one escalation episode `_state["CAPTURE_DOWN"].fired` is stuck at True for the process lifetime, blocking a second escalation from firing.

No critical security or crash-risk issues. The TTS and dashboard push paths are both wrapped and swallow exceptions, so a broken subsystem cannot crash the caller — tests assert this explicitly.

## Warnings

### WR-01: `fire_alert` read-modify-write is not thread-safe for same-subtype concurrent callers

**File:** `src/shitbox/health/alerts.py:86-128`
**Issue:** The docstring claims "Safe to call from any thread — the module-level rebind is GIL-atomic". Misleading. The GIL only makes the bytecode of `_state = new_map` atomic. The sequence `prev = _get_or_init(subtype)` → build `new_map` from `_state` → `_state = new_map` is a classic lost-update race. If two threads call `fire_alert("UNDERVOLTAGE", True, ...)` concurrently, both read the same `prev`, both build a dict from the same snapshot of `_state`, and whichever assigns last wins.

Today this is unreachable in practice because per-subtype writers are single-threaded (thermal_monitor owns UNDERVOLTAGE; ring_buffer owns CAPTURE_*). But the docstring encourages callers to assume otherwise.

**Fix:** Tighten the docstring to "Safe to call from any thread **provided each subtype has a single writer**", or add a module-level `threading.Lock` around state machine transitions.

### WR-02: `CAPTURE_DOWN` never clears — stuck `fired=True` after first escalation

**File:** `src/shitbox/health/alerts.py:119-126` and `src/shitbox/capture/ring_buffer.py:985-992, 1024-1031`
**Issue:** When `fire_alert` observes `active=False` after a prior fire, it resets `active_sustain_count` to 0 but does not reset `fired` or advance `clear_sustain_count`. The comment says "fire_recovery owns that edge" — true, but only works if every caller that uses `fire_alert` also calls `fire_recovery` in the same cycle.

The ring_buffer wiring is vulnerable: `CAPTURE_DOWN` is fired via `fire_alert` with no matching `fire_recovery("CAPTURE_DOWN", ...)` anywhere. Once it fires, `_state["CAPTURE_DOWN"].fired` stays True for the life of the process. If CAPTURE_FAILURE → CAPTURE_RESTORED recovery runs but CAPTURE_DOWN has already fired once, a second escalation period cannot re-fire CAPTURE_DOWN.

**Fix:** Add `fire_recovery("CAPTURE_DOWN", active, ...)` alongside the CAPTURE_FAILURE recovery in `ring_buffer.py`, or have the recovery branch fire a recovery for both subtypes.

```python
# ring_buffer.py near line 960
alerts.fire_recovery(
    "CAPTURE_FAILURE", active=False, message="RECORDING RESUMED",
    tts_fn=speak_service_recovered, sustain_required=1,
    recovery_subtype="CAPTURE_RESTORED",
)
alerts.fire_recovery(  # <-- add this
    "CAPTURE_DOWN", active=False, message="RECORDING RESUMED",
    sustain_required=1,
)
self._consecutive_restart_count = 0
```

### WR-03: `_check_stall` uses wall-clock `time.time()` — susceptible to GPS clock jumps

**File:** `src/shitbox/capture/ring_buffer.py:904-906`
**Issue:** `age = time.time() - self._last_segment_mtime` mixes wall-clock time (GPS can step) with filesystem mtime. If the Pi's clock jumps forward when GPS acquires a fix, this returns a false-positive stall and kicks ffmpeg. The existing codebase acknowledges GPS clock jumps elsewhere; the stall window is 30 s, so a typical GPS step post-boot can trigger.

**Fix:** Use `time.monotonic()` with a baseline recorded when the segment is first seen:

```python
if not self._stall_check_armed:
    self._stall_check_armed = True
    self._last_segment_mtime = mtime
    self._last_segment_size = size
    self._last_segment_seen_monotonic = time.monotonic()
    return False
# ...
if mtime != self._last_segment_mtime or size != self._last_segment_size:
    self._last_segment_mtime = mtime
    self._last_segment_size = size
    self._last_segment_seen_monotonic = time.monotonic()
    return False
age = time.monotonic() - self._last_segment_seen_monotonic
return age > self.STALL_TIMEOUT_SECONDS
```

### WR-04: `_system_conditions_payload` non-deterministic when both `CAPTURE_FAILURE` and `CAPTURE_DOWN` are `restored`

**File:** `src/shitbox/dashboard/sse.py:128-139`
**Issue:** The roll-up guard on line 137 correctly protects `active` from being downgraded to `restored`. But the reverse is not handled: if both subtypes under the same role end up in `restored`, the second will overwrite the first's `since_ms`, which may be older or newer depending on which cleared first. Harmless but non-deterministic. The test `test_system_conditions_payload_capture_down_rolls_up_same_role` only covers both-active.

**Fix:** When both subtypes under the same role are `restored`, pick the most recent `last_change_ts` deterministically:

```python
elif status.fired and not status.active:
    if role_state[role]["state"] == "active":
        continue
    candidate_ms = int((now - status.last_change_ts) * 1000)
    if (role_state[role]["state"] != "restored"
            or candidate_ms < role_state[role]["since_ms"]):
        role_state[role]["state"] = "restored"
        role_state[role]["since_ms"] = candidate_ms
```

Add a test asserting the pick is deterministic.

### WR-05: `push_event` holds `_event_listeners_lock` during per-client `put_nowait`

**File:** `src/shitbox/dashboard/sse.py:193-198`
**Issue:** The lock scope covers every client's `put_nowait`. `put_nowait` is non-blocking, but the loop is O(clients) under the lock. With the 8-client cap and a 256-slot queue this is fine today. The docstring promises "non-blocking and drops on full so the 100 Hz capture path … is never made to wait" — and the capture path does touch `push_event` via `alerts._emit_alert` during a stall. If a future change makes the listener list larger or `put_nowait` more expensive, the lock becomes a latent serialisation point on the capture path.

**Fix:** Snapshot the listeners list under the lock, release it, then iterate:

```python
def push_event(event: Dict[str, Any]) -> None:
    with _event_listeners_lock:
        listeners = list(_event_listeners)
    for q in listeners:
        try:
            q.put_nowait(event)
        except queue.Full:
            log.warning("dashboard_event_queue_full", dropped=event.get("type"))
```

### WR-06: Dashboard `scStateText` returns "RECOVERING" but Python payload never emits `recovering`

**File:** `src/shitbox/dashboard/static/index.html:892-894`
**Issue:** `scStateText` and `scGlyph` both map a `"recovering"` state, but `_system_conditions_payload` only ever emits `"clear" | "active" | "restored"`. The frontend branch is dead. Not a bug per se, but either the payload should emit `recovering` during the sustain window, or the frontend should drop the dead branch.

**Fix:** Either wire the `recovering` state through `_system_conditions_payload` (during the `clear_sustain_count > 0 and fired` window) or remove the `recovering` arms from `scStateText`/`scGlyph` and the `.sc-recovering` CSS class.

### WR-07: Pre-existing — `thermal_monitor._check_thermal` can spam warning recovery on oscillation

**File:** `src/shitbox/health/thermal_monitor.py:266-270`
**Issue:** If `temp` bumps to 70 C (re-triggers warning) then back to 64 C in consecutive polls, the recovery beep + TTS fire every cycle. No sustain gating. Not a Phase 15 regression — this code is older — but Phase 15 is the moment the alerts helper exists and could subsume this logic.

**Fix:** Consider migrating `THERMAL_WARNING` / `THERMAL_CRITICAL` to the alerts helper in a follow-up phase for consistency with UNDERVOLTAGE.

## Info

### IN-01: `clear_state` labelled "TEST-ONLY" but has no guard

**File:** `src/shitbox/health/alerts.py:224-227`
**Issue:** Docstring says "TEST-ONLY helper — do not call in production code" but the function is freely callable. Convention-only guard. Consider naming it `_clear_state`.

### IN-02: Unused import + lambda in `ring_buffer.py` — already tracked

**File:** `src/shitbox/capture/ring_buffer.py:8, 771`
**Issue:** Known cleanup items per project audit notes (not a Phase 15 regression).

### IN-03: `_SUBTYPE_TO_ROLE` map omits recovery subtypes — intentional, could be better documented

**File:** `src/shitbox/dashboard/sse.py:101-107`
**Issue:** Correct behaviour, comment could point at `fire_recovery`'s `recovery_subtype` parameter for clarity.

### IN-04: `_hardware_label` default fallback untested

**File:** `src/shitbox/dashboard/sse.py:66-67`
**Issue:** Pre-existing, not a Phase 15 surface.

### IN-05: Alpine XSS risk check passes — SYSTEM section uses only `x-text`

**File:** `src/shitbox/dashboard/static/index.html:414-422`
**Issue:** Confirmed safe. All SYSTEM bindings use `x-text`; `:class="'sc-' + row.state"` concatenates into a class name (malformed at worst, not executable). Five scalar fields are typed server-side.

## Verdict

No commit blockers. WR-02 (CAPTURE_DOWN never clears) is a real latent bug that becomes visible as soon as a field test has two separate stall episodes in one run. WR-01 (docstring accuracy) is easy and worth doing. WR-03 (clock jump) is a lurking false-positive that will eventually bite once vehicle testing stretches long enough to catch a GPS step past the 30-second stall threshold. The rest are polish or noted for awareness.
