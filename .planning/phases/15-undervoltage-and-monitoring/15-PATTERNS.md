# Phase 15: Undervoltage and Monitoring - Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 8 source/test files + 1 home-ops deletion
**Analogs found:** 8 / 8 (every new or modified file has an in-tree analogue with file:line anchors)

Phase 15 is a delegation phase. Almost every moving part mirrors an existing pattern: `hardware/state.py` for module-level GIL-atomic state, `thermal_monitor.py` for the dashboard-push alert shape and graceful-degradation imports, `_hardware_payload()` for the `/sse/slow` sibling payload, the existing `.hw-row-lg` template for sticky row rendering, and the existing `showAlert()` branch for the recovery-green overlay. The planner should lean on these analogues verbatim and resist inventing new abstractions (D-11: "the seam, not the cathedral").

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/shitbox/health/alerts.py` (NEW) | utility / shared-state helper | event-driven (sustain counting + transition emission) | `src/shitbox/hardware/state.py` | exact (frozen dataclass + module-level GIL-atomic rebind) |
| `tests/test_alerts.py` (NEW) | test | unit | `tests/test_thermal_monitor.py` lines 188-239 (mock push_event + TTS; assert subtype/message) | exact |
| `src/shitbox/health/thermal_monitor.py` (MODIFY) | service (daemon thread) | request-response (5 s poll) | self — bug fix in `_check_throttled()` at line 297 | self-reference; fix in place |
| `src/shitbox/capture/ring_buffer.py` (MODIFY) | service (daemon thread) | event-driven (health-monitor tick) | self — alert wire-in at lines 938-953 inside `_health_monitor()` | self-reference; alert wire-in alongside existing `hw_state.report_degraded` |
| `src/shitbox/dashboard/sse.py` (MODIFY) | controller (FastAPI router) | streaming (SSE) | self — `_hardware_payload()` at lines 56-70 | exact sibling |
| `src/shitbox/dashboard/static/index.html` (MODIFY) | component (Alpine.js view) | request-response / streaming consumer | self — `showAlert()` lines 536-548, `.hw-row-lg` template lines 396-404, `hwBadgeClass()` lines 811-818 | self-reference |
| `tests/test_thermal_monitor.py` (EXTEND) | test | unit | self — patterns at lines 188-239 (dashboard_push_event mock pattern) | self-reference |
| `tests/test_ffmpeg_stall.py` (EXTEND) | test | unit | self — `test_health_monitor_restarts_on_stall` at lines 178-216; `_make_vrb` factory at lines 27-67 | self-reference |
| `tests/test_dashboard.py` (EXTEND) | test | integration | self — `test_sse_slow_schema` lines 221-237; `test_sse_slow_has_active_driver_key` lines 376-399 | self-reference |
| home-ops: `shitbox-mqtt-exporter/` (DELETE) | external k8s manifests | n/a | `observability/kustomization.yaml:20` (already commented out) | n/a |
| `.planning/REQUIREMENTS.md` MON-01 (EDIT) | documentation | n/a | existing checkbox pattern in the same file | n/a |

---

## Pattern Assignments

### `src/shitbox/health/alerts.py` (NEW — utility, event-driven)

**Analog:** `src/shitbox/hardware/state.py` (entire file, 159 lines)

**Anchor summary:** mirror the module shape beat-for-beat. Frozen dataclass, module-level `_state` dict, rebind-on-update to get GIL-atomic reads, `snapshot()` returning the dict, `clear_state()` as a test-only helper. Add two module functions `fire_alert()` and `fire_recovery()` that encode sustain counting and once-on-transition semantics.

**Imports pattern** (mirror `hardware/state.py:1-14`):
```python
"""Alert sustain + transition helper. Module-level, GIL-atomic rebind.

Safe to call from any thread — the module-level rebind is GIL-atomic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)
```

**Graceful-degradation imports** (mirror `thermal_monitor.py:23-50`):
```python
try:
    from shitbox.dashboard.sse import push_event as dashboard_push_event
except ImportError:
    def dashboard_push_event(event: dict) -> None:  # type: ignore[misc]
        pass
```
TTS callables are passed in by the caller (not imported here), so this module does not have to mirror the speaker import block — keeps `alerts.py` import-clean for unit tests.

**Frozen dataclass** (mirror `hardware/state.py:23-33`):
```python
@dataclass(frozen=True, slots=True)  # type: ignore[call-overload]
class AlertStatus:
    """Immutable snapshot of a single alert subtype's sustain + transition state."""

    subtype: str
    active: bool           # current debounced state (True once sustained)
    sustain_count: int     # consecutive observations of current raw signal
    fired: bool            # has fire_alert emitted for this active run?
    last_change_ts: float  # time.time() of last state transition (0.0 if never)
```

**Module-level state + rebind** (mirror `hardware/state.py:36-37, 77-87`):
```python
# Single source of truth. Rebinding is GIL-atomic.
_state: Dict[str, AlertStatus] = {}

def _rebind(subtype: str, new_status: AlertStatus) -> None:
    """Rebind module-level dict in a GIL-atomic way."""
    global _state
    new_map = dict(_state)
    new_map[subtype] = new_status
    _state = new_map
```

**Core pattern — `fire_alert` + `fire_recovery`** (new surface; internal semantics locked by CONTEXT D-11/D-12 and RESEARCH Pitfall 1/2/3):
- `fire_alert(subtype, active, message, tts_fn, sustain_required=2)` — called every cycle. Increments sustain_count when `active` matches last raw signal; emits dashboard_push_event + tts_fn exactly once when sustain_count reaches `sustain_required` AND `fired=False`.
- `fire_recovery(subtype, active, message, tts_fn, sustain_required=2)` — called every cycle. Tracks an independent clear-sustain counter; emits recovery ALERT + tts_fn exactly once when `fired=True` AND sustain on `active=False` reaches threshold.
- Both functions use `_rebind()` to update state. Neither takes a lock — the GIL-atomic rebind is the lock (Pattern 1 / RESEARCH line 275).

**Dashboard push shape** (mirror `thermal_monitor.py:311-316` verbatim):
```python
dashboard_push_event({
    "type": "ALERT",
    "subtype": subtype,           # e.g. "UNDERVOLTAGE"
    "message": message,           # e.g. "UNDERVOLTAGE DETECTED"
    "ts": time.time(),
})
```

**Logging pattern** (mirror `hardware/state.py:89, 117, 146` — structlog keyword args):
```python
log.info("alert_fired", subtype=subtype, sustain_reads=status.sustain_count)
log.info("alert_recovered", subtype=subtype, held_ms=int((now - status.last_change_ts) * 1000))
```

**`snapshot()` + `clear_state()`** (mirror `hardware/state.py:150-158`):
```python
def snapshot() -> Dict[str, AlertStatus]:
    """Return current state dict. Do not mutate — AlertStatus is frozen."""
    return _state


def clear_state() -> None:
    """Reset module state. TEST-ONLY helper — do not call in production code."""
    global _state
    _state = {}
```

---

### `tests/test_alerts.py` (NEW — test, unit)

**Analog:** `tests/test_thermal_monitor.py:188-239` (dashboard_push_event mock + subtype assertion pattern) and `tests/test_ffmpeg_stall.py:224-230` (autouse fixture to reset module-level state between tests).

**Autouse fixture pattern** (mirror `test_ffmpeg_stall.py:224-230`):
```python
@pytest.fixture(autouse=True)
def _clear_alerts_state():
    """Reset alerts module state before and after each test."""
    from shitbox.health import alerts
    alerts.clear_state()
    yield
    alerts.clear_state()
```

**fire_alert / fire_recovery assertion pattern** (mirror `test_thermal_monitor.py:215-239`):
```python
def test_fire_alert_once_on_transition() -> None:
    from shitbox.health import alerts

    tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        # sustain_required=2: first call arms, second call fires
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", tts, sustain_required=2)
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", tts, sustain_required=2)
        # Third consecutive call must NOT re-fire
        alerts.fire_alert("UNDERVOLTAGE", True, "UNDERVOLTAGE DETECTED", tts, sustain_required=2)

    assert mock_push.call_count == 1
    event = mock_push.call_args[0][0]
    assert event["type"] == "ALERT"
    assert event["subtype"] == "UNDERVOLTAGE"
    assert "UNDERVOLTAGE" in event["message"]
    tts.assert_called_once()
```

**Sustain-resets-on-break test** (covers Pitfall 2 from RESEARCH):
```python
def test_sustain_resets_on_break() -> None:
    from shitbox.health import alerts

    tts = MagicMock()
    with patch("shitbox.health.alerts.dashboard_push_event") as mock_push:
        alerts.fire_alert("UNDERVOLTAGE", True, "UV", tts, sustain_required=2)
        alerts.fire_alert("UNDERVOLTAGE", False, "UV", tts, sustain_required=2)  # break
        alerts.fire_alert("UNDERVOLTAGE", True, "UV", tts, sustain_required=2)   # rearm start

    assert mock_push.call_count == 0  # never reached sustain threshold
```

**snapshot test** (mirror the shape of the `hw_state.snapshot()` assertion at `test_ffmpeg_stall.py:276-277, 314-315`):
```python
def test_snapshot_contains_all_tracked() -> None:
    from shitbox.health import alerts
    alerts.fire_alert("UNDERVOLTAGE", True, "UV", lambda: None)
    snap = alerts.snapshot()
    assert "UNDERVOLTAGE" in snap
    assert snap["UNDERVOLTAGE"].sustain_count == 1
```

---

### `src/shitbox/health/thermal_monitor.py` (MODIFY — service, request-response)

**Analog:** self — the bug is at `thermal_monitor.py:290-316` (`_check_throttled`), excerpted verbatim.

**Current buggy code to replace** (lines 290-316):
```python
def _check_throttled(self) -> None:
    """Read and decode throttle bitmask; alert on under-voltage."""
    raw = self._read_throttled()
    if raw is None:
        return

    with self._lock:
        if raw == self._last_throttled_raw:        # ← BUG: full-word compare
            return  # No change — stay silent
        self._last_throttled_raw = raw
    decoded = _decode_throttled(raw)
    log.warning(
        "throttle_state_changed",
        raw_hex=hex(raw),
        current=decoded["current"],
        since_boot=decoded["since_boot"],
    )

    if decoded["current"].get("under_voltage"):    # ← never reached after sticky set
        beep_under_voltage()
        speak_under_voltage()
        dashboard_push_event({
            "type": "ALERT",
            "subtype": "UNDERVOLTAGE",
            "message": "UNDERVOLTAGE DETECTED",
            "ts": time.time(),
        })
```

**Replacement shape** (per D-01, D-02, D-03, RESEARCH Pitfall 1/2):
- Stop gating the alert on "change since last read". Read every cycle, decode every cycle, delegate to `alerts.fire_alert` every cycle with `active=bool(raw & 0xf)`.
- Keep `_last_throttled_raw` for logging only: `if (raw & 0xf) != (prev & 0xf)` → emit `log.warning("throttle_state_changed", ...)`. Sticky bits still decoded for the log payload, never for the alert trigger.
- Call order: decode → optional change-log → `alerts.fire_alert("UNDERVOLTAGE", active, "UNDERVOLTAGE DETECTED", speak_under_voltage, sustain_required=2)` → `alerts.fire_recovery("UNDERVOLTAGE", active, "POWER RESTORED", speak_power_restored, sustain_required=2)`.
- Keep `beep_under_voltage()` call inside the alert branch if desired (D-04 keeps the buzzer as a fallback path). Recommendation: move `beep_under_voltage` inside a `fire_alert` wrapper callable so all three side-effects fire together, or leave it direct-called from `_check_throttled` guarded on `not alerts.snapshot().get("UNDERVOLTAGE", None).fired` — planner's choice. The helper owns sustain; `_check_throttled` owns the "which beep for which subtype" mapping.

**New TTS callable** (add to `capture/speaker.py` alongside `speak_under_voltage` at line 435):
```python
def speak_power_restored() -> None:
    """Announce that an under-voltage condition has cleared."""
    if not _should_alert():
        return
    _enqueue("Power restored, Michael. We're back to steady.")
```
Style-match source: `speak_under_voltage` at `speaker.py:435-442` and `speak_thermal_recovered` at `speaker.py:425-432` ("Much better, Michael. Temperature back to normal."). Terse, second-person, addresses Michael, observational. Per UI-SPEC copy contract line 113 overlay string is `POWER RESTORED`; TTS is the longer spoken form.

---

### `src/shitbox/capture/ring_buffer.py` (MODIFY — service, event-driven)

**Analog:** self — `_health_monitor()` at lines 891-967; the wire-in site is lines 936-953 where `_check_stall()` triggers the existing `hw_state.report_degraded` + `buzzer.beep_ffmpeg_stall` calls.

**Current stall-path excerpt** (lines 936-953, the canonical wire-in location):
```python
# Restart if ffmpeg is alive but has stopped writing segments
if self._process is not None and self._process.poll() is None:
    if self._check_stall():
        stderr = self._read_stderr()
        log.warning(
            "video_ring_buffer_ffmpeg_stalled",
            device=self.device,
            stall_timeout_seconds=self.STALL_TIMEOUT_SECONDS,
            stderr=stderr,
        )
        hw_state.report_degraded(self.role)          # ← existing
        buzzer.beep_ffmpeg_stall()                   # ← existing
        # ★ wire alerts.fire_alert("CAPTURE_FAILURE", True, "CAPTURE STALLED", speak_ffmpeg_stall) here
        # Kill before replacing _process reference to avoid zombies
        self._kill_current()
        self._reset_stall_state()
        self._start_ffmpeg()
        # ★ after restart, increment consecutive_restart_count on the instance
        # ★ if consecutive_restart_count >= 3, alerts.fire_alert("CAPTURE_DOWN", ...) — one transition only
        last_audio_retry = time.time()
        continue
```

**What to add (minimal — per D-07, D-08, RESEARCH Pitfall 3):**
1. Instance counter `self._consecutive_restart_count: int = 0` initialised in `__init__` (or in `_reset_stall_state` as appropriate).
2. Alongside `hw_state.report_degraded` + `buzzer.beep_ffmpeg_stall`, call:
   ```python
   alerts.fire_alert(
       "CAPTURE_FAILURE",
       active=True,
       message="CAPTURE STALLED",
       tts_fn=speak_ffmpeg_stall,       # exists at speaker.py:511
       sustain_required=1,              # stall is already sustained — helper-level gating not needed
   )
   ```
3. After `self._start_ffmpeg()` returns and `consecutive_restart_count >= 3`, call:
   ```python
   alerts.fire_alert(
       "CAPTURE_DOWN",
       active=True,
       message="CAPTURE DOWN",
       tts_fn=speak_capture_failed,     # exists at speaker.py:521
       sustain_required=1,
   )
   ```
4. Recovery: after a segment is observed clean (next `_check_stall()` returns False with `_stall_check_armed=True` and `self._consecutive_restart_count > 0`), call:
   ```python
   alerts.fire_recovery("CAPTURE_FAILURE", active=False, message="RECORDING RESUMED", tts_fn=speak_service_recovered, sustain_required=1)
   # and mirror for CAPTURE_DOWN if it had fired
   self._consecutive_restart_count = 0
   ```
   `speak_service_recovered` exists at `speaker.py:455-462` ("All accounted for again, Michael.").

**Import pattern** (add alongside existing imports in `ring_buffer.py` — mirror the graceful-degradation block already used in `thermal_monitor.py:45-50`):
```python
try:
    from shitbox.health.alerts import fire_alert, fire_recovery
except ImportError:
    def fire_alert(*a, **k) -> None: pass        # type: ignore[misc]
    def fire_recovery(*a, **k) -> None: pass     # type: ignore[misc]
```
Rationale per RESEARCH "Project Constraints" line 152: `ring_buffer.py` must remain testable without the dashboard subsystem booted.

**Do NOT:** (RESEARCH Anti-Patterns lines 362-372)
- Add restart counting as a separate bookkeeping field outside the helper. The helper's sustain counting is adjacent but not the same — `consecutive_restart_count` is a monotonic tally owned by the ring buffer; `fire_alert`'s sustain counter is owned by alerts. They do not merge.
- Add a `threading.Lock` around the restart counter. Python int writes are atomic enough for a single-writer (health thread).

---

### `src/shitbox/dashboard/sse.py` (MODIFY — controller, streaming)

**Analog:** self — `_hardware_payload()` at lines 56-70, splice at line 189 inside `/sse/slow`.

**Canonical `_hardware_payload()` shape** (verbatim, lines 56-70):
```python
def _hardware_payload() -> List[Dict[str, Any]]:
    now = time.time()
    out = []
    for st in hw_state.snapshot().values():
        last_seen = st.last_seen if st.last_seen > 0 else None
        since_ms = int((now - st.last_seen) * 1000) if st.last_seen > 0 else None
        out.append({
            "role": st.role,
            "label": _hardware_label(st.role),
            "tier": st.tier,
            "state": st.state.value,
            "last_seen": last_seen,
            "since_ms": since_ms,
        })
    return out
```

**New `_system_conditions_payload()`** (sibling, shape mirrors above per UI-SPEC lines 174-209):
```python
_SYSTEM_CONDITION_LABELS: Dict[str, str] = {
    "undervoltage": "UNDERVOLTAGE",
    "thermal": "THERMAL",
    "capture": "CAPTURE",
}

# Maps alerts subtype → (role, primary-state-from-fired, recovering-state-if-applicable)
_SUBTYPE_TO_ROLE: Dict[str, str] = {
    "UNDERVOLTAGE": "undervoltage",
    "THERMAL_WARNING": "thermal",
    "THERMAL_CRITICAL": "thermal",
    "CAPTURE_FAILURE": "capture",
    "CAPTURE_DOWN": "capture",
}


def _system_conditions_payload() -> List[Dict[str, Any]]:
    """Render the three system conditions (undervoltage/thermal/capture) for /sse/slow.

    Always emits all three rows so the frontend always has a complete set. State
    is derived from alerts.snapshot(): fired+active → "active", fired+cleared
    within 60 s → "restored", capture mid-restart → "recovering", else "clear".
    """
    from shitbox.health import alerts

    now = time.time()
    snap = alerts.snapshot()

    # Roll up per-role state from per-subtype alert entries
    role_state: Dict[str, Dict[str, Any]] = {
        "undervoltage": {"state": "clear", "since_ms": None},
        "thermal": {"state": "clear", "since_ms": None},
        "capture": {"state": "clear", "since_ms": None},
    }
    for subtype, status in snap.items():
        role = _SUBTYPE_TO_ROLE.get(subtype)
        if role is None:
            continue
        if status.fired and status.active:
            role_state[role]["state"] = "active"
            role_state[role]["since_ms"] = int((now - status.last_change_ts) * 1000)
        elif status.fired and not status.active:
            role_state[role]["state"] = "restored"
            role_state[role]["since_ms"] = int((now - status.last_change_ts) * 1000)

    out = []
    for role, label in _SYSTEM_CONDITION_LABELS.items():
        rs = role_state[role]
        out.append({
            "role": role,
            "label": label,
            "tier": "critical",
            "state": rs["state"],
            "since_ms": rs["since_ms"],
        })
    return out
```

**Wire into `/sse/slow` handler** (add a line alongside `"hardware": _hardware_payload()` at line 189):
```python
"hardware": _hardware_payload(),
"system_conditions": _system_conditions_payload(),
```
Location: `sse.py:189`. No other change to the streaming loop.

**Payload-shape discipline** (RESEARCH Pitfall 5 line 460): scalars only — no history arrays, no raw bitmasks, no last-message text. If any field in the list is not `str | int | float | bool | None`, pull it out.

---

### `src/shitbox/dashboard/static/index.html` (MODIFY — component)

Four distinct changes, each with a concrete analogue in the same file.

#### 6a. `showAlert()` colour branch (lines 536-548)

**Analog:** self — verbatim.
```javascript
showAlert(payload) {
  if (this._alertTimer) { clearTimeout(this._alertTimer); this._alertTimer = null; }
  const isSystem = payload.type === 'ALERT';
  const colour = isSystem
    ? '#da3633'                                   // ← always red — needs subtype branch
    : (this.EVENT_COLOURS[payload.type] || '#8b949e');
  const message = isSystem
    ? payload.message
    : `${payload.type} · ${(payload.peak_g || 0).toFixed(1)}g`;
  this.alertOverlay = { message, colour, isSystem };
  const duration = isSystem ? 10000 : 3000;
  this._alertTimer = setTimeout(() => { this.alertOverlay = null; }, duration);
},
```

**Replacement (per UI-SPEC "Alert Overlay — Colour Branch Contract" lines 153-159):**
```javascript
showAlert(payload) {
  if (this._alertTimer) { clearTimeout(this._alertTimer); this._alertTimer = null; }
  const isSystem = payload.type === 'ALERT';
  const subtype = payload.subtype || '';
  const isRecovery = isSystem && (subtype.endsWith('_CLEARED') || subtype.endsWith('_RESTORED'));
  const colour = isRecovery
    ? '#238636'                                   // green — recovery
    : (isSystem
        ? '#da3633'                               // red — failure/active
        : (this.EVENT_COLOURS[payload.type] || '#8b949e'));
  const message = isSystem
    ? payload.message
    : `${payload.type} · ${(payload.peak_g || 0).toFixed(1)}g`;
  this.alertOverlay = { message, colour, isSystem };
  const duration = isRecovery ? 3000 : (isSystem ? 10000 : 3000);
  this._alertTimer = setTimeout(() => { this.alertOverlay = null; }, duration);
},
```

#### 6b. SYSTEM section in the Health modal (insert above the hardware list at line 395)

**Row template analog** (lines 396-404, verbatim):
```html
<template x-for="row in sortedHardware()" :key="row.role">
  <div class="hw-row hw-row-lg" :class="'hw-' + row.state + ' hw-tier-' + row.tier">
    <span class="hw-glyph" x-text="stateGlyph(row.state)"></span>
    <span class="hw-label" x-text="row.label"></span>
    <span class="badge" :class="'badge-' + row.tier" x-text="row.tier"></span>
    <span class="hw-state" x-text="stateText(row.state)"></span>
    <span class="hw-since" x-text="sinceText(row.since_ms)"></span>
  </div>
</template>
```

**New markup to insert above the hardware list (UI-SPEC lines 126-148):**
```html
<!-- SYSTEM conditions section — above HARDWARE list -->
<div class="hw-section-eyebrow">SYSTEM</div>
<template x-for="row in systemConditions" :key="row.role">
  <div class="hw-row hw-row-lg" :class="'sc-' + row.state + ' hw-tier-critical'">
    <span class="hw-glyph" x-text="scGlyph(row.state)"></span>
    <span class="hw-label" x-text="row.label"></span>
    <span class="badge" :class="'badge-' + row.tier" x-text="row.tier"></span>
    <span class="hw-state" x-text="scStateText(row.state)"></span>
    <span class="hw-since" x-text="sinceText(row.since_ms)"></span>
  </div>
</template>

<div class="hw-section-eyebrow" style="margin-top: 12px;">HARDWARE</div>
<!-- existing hw-row template continues here (unchanged) -->
```

#### 6c. CSS additions in the `<style>` block (lines 9-48)

**Analog:** `.hw-present` / `.hw-degraded` / `.hw-missing` at lines 38-42:
```css
.hw-missing .hw-glyph { color: #8b949e; }
.hw-missing .hw-state { color: #da3633; }
.hw-degraded .hw-glyph { color: #d29922; }
.hw-degraded .hw-state { color: #f85149; }
.hw-present .hw-glyph { color: #238636; }
```

**New rules to add (UI-SPEC lines 136-141 state table):**
```css
/* System condition row states — mirror .hw-* pattern */
.sc-clear .hw-glyph { color: #8b949e; }
.sc-clear .hw-state { color: #8b949e; }
.sc-active .hw-glyph { color: #da3633; }
.sc-active .hw-state { color: #f85149; }
.sc-recovering .hw-glyph { color: #d29922; }
.sc-recovering .hw-state { color: #d29922; }
.sc-restored .hw-glyph { color: #238636; }
.sc-restored .hw-state { color: #238636; }
.hw-section-eyebrow { color: #8b949e; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; padding: 12px 0 4px 0; }
```

#### 6d. `hwBadgeClass()` extension (lines 811-818)

**Analog — existing code verbatim:**
```javascript
hwBadgeClass() {
  const h = this.hardware;
  if (!h.length) return 'bg-gray-700';
  if (h.some(r => r.tier === 'critical' && r.state === 'missing')) return 'bg-red-700';
  if (h.some(r => r.tier === 'important' && r.state === 'missing')) return 'bg-yellow-600';
  if (h.some(r => r.state === 'degraded')) return 'bg-yellow-600';
  return 'bg-green-700';
},
```

**Replacement (UI-SPEC line 227):**
```javascript
hwBadgeClass() {
  const h = this.hardware;
  const sc = this.systemConditions || [];
  // Any active system condition → red (matches critical missing)
  if (sc.some(r => r.state === 'active')) return 'bg-red-700';
  if (!h.length) return 'bg-gray-700';
  if (h.some(r => r.tier === 'critical' && r.state === 'missing')) return 'bg-red-700';
  if (h.some(r => r.tier === 'important' && r.state === 'missing')) return 'bg-yellow-600';
  if (h.some(r => r.state === 'degraded' || r.state === 'recovering'))
    return 'bg-yellow-600';
  return 'bg-green-700';
},
```

#### 6e. `openSlow()` payload wiring (line 588)

**Analog — existing code at line 588:**
```javascript
this.hardware = d.hardware || [];
```

**Addition immediately after:**
```javascript
this.hardware = d.hardware || [];
this.systemConditions = d.system_conditions || [];
```

Also add `systemConditions: []` to the Alpine data block at lines 440-472 (next to `hardware: []` at line 440) plus two helper methods mirroring `stateText`/`stateGlyph` at lines 846-852:

```javascript
scStateText(state) {
  return { clear: 'CLEAR', active: 'ACTIVE', recovering: 'RECOVERING', restored: 'RESTORED' }[state]
    || state.toUpperCase();
},
scGlyph(state) {
  return { clear: '○', active: '●', recovering: '◐', restored: '●' }[state] || '?';
},
```

#### 6f. Modal title copy change (line 386)

**Analog — existing line 386:**
```html
<h2 style="position: absolute; top: 24px; left: 48px; font-size: 39px; font-weight: 600; margin: 0; color: #e6edf3;">Hardware</h2>
```

**Replacement (UI-SPEC line 107):** `Hardware` → `Health`. One-word literal edit.

---

### `tests/test_thermal_monitor.py` (EXTEND — test, unit)

**Analog:** self — `test_undervoltage_pushes_dashboard_alert` at lines 215-239 is the template for PWR-01/PWR-02 regressions.

**Existing template pattern** (lines 215-239):
```python
def test_undervoltage_pushes_dashboard_alert() -> None:
    """DISP-04/D-05: _check_throttled() with bit 0 set must call dashboard_push_event."""
    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x1),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.thermal_monitor.dashboard_push_event") as mock_push,
    ):
        service._check_throttled()

    mock_push.assert_called_once()
    event = mock_push.call_args[0][0]
    assert event.get("type") == "ALERT"
    assert event.get("subtype") == "UNDERVOLTAGE"
```

**New tests to add (RESEARCH "Phase Requirements → Test Map" lines 714-719):**

**PWR-01 — sticky bits must not fire:**
```python
def test_pwr01_sticky_bits_ignored() -> None:
    """Bitmask with only sticky bits 16-19 set must NOT trigger an alert."""
    # Reset helper module state so prior tests do not leak fired=True
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    with (
        patch.object(service, "_read_throttled", return_value=0x50000),  # sticky only, low nibble == 0
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.thermal_monitor.dashboard_push_event") as mock_push,
    ):
        # Call multiple times — sustain counter can climb but active=False so no fire
        for _ in range(5):
            service._check_throttled()

    mock_push.assert_not_called()
```

**PWR-01 — sustain required:**
```python
def test_pwr01_sustain_required() -> None:
    """Low nibble set for only 1 cycle must NOT fire — sustain_required=2."""
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    raws = [0x1, 0x0]  # one cycle under, then clear
    with (
        patch.object(service, "_read_throttled", side_effect=raws),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.thermal_monitor.dashboard_push_event") as mock_push,
    ):
        service._check_throttled()
        service._check_throttled()

    mock_push.assert_not_called()
```

**PWR-02 — recovery fires after sustained clear following sustained active:**
```python
def test_pwr02_recovery_fires() -> None:
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    service = ThermalMonitorService()
    # Two cycles of active (arms + fires), then two cycles of clear (arms + fires recovery)
    raws = [0x1, 0x1, 0x0, 0x0]
    with (
        patch.object(service, "_read_throttled", side_effect=raws),
        patch("shitbox.health.thermal_monitor.beep_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_under_voltage"),
        patch("shitbox.health.thermal_monitor.speak_power_restored"),
        patch("shitbox.health.thermal_monitor.dashboard_push_event") as mock_push,
    ):
        for _ in range(4):
            service._check_throttled()

    # 2 calls: UNDERVOLTAGE + UNDERVOLTAGE_CLEARED
    assert mock_push.call_count == 2
    subtypes = [call[0][0]["subtype"] for call in mock_push.call_args_list]
    assert subtypes == ["UNDERVOLTAGE", "UNDERVOLTAGE_CLEARED"]
```

---

### `tests/test_ffmpeg_stall.py` (EXTEND — test, unit)

**Analog:** self — `test_health_monitor_restarts_on_stall` at lines 178-216 (sleep side-effect pattern) and `test_stall_reports_degraded` at lines 280-315 (`hw_state` assertion pattern).

**Existing test pattern to mirror** (lines 178-216):
```python
def test_health_monitor_restarts_on_stall(tmp_path: Path) -> None:
    vrb = _make_vrb(tmp_path)
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    vrb._process = mock_process
    vrb._running = True

    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=True),
        patch.object(vrb, "_kill_current") as mock_kill,
        patch.object(vrb, "_start_ffmpeg") as mock_start,
        patch("shitbox.capture.buzzer.beep_ffmpeg_stall") as mock_beep,
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass
    mock_beep.assert_called_once()
    mock_kill.assert_called_once()
    mock_start.assert_called_once()
```

**New `test_mon03_capture_failure_fires`** — mirrors above, asserts `alerts.fire_alert` is called with `CAPTURE_FAILURE`:
```python
def test_mon03_capture_failure_fires(tmp_path: Path) -> None:
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    vrb = _make_vrb(tmp_path)
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    vrb._process = mock_process
    vrb._running = True

    sleep_calls = [None, SystemExit("stop")]

    def _sleep_side_effect(_duration: float) -> None:
        effect = sleep_calls.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    with (
        patch.object(vrb, "_check_stall", return_value=True),
        patch.object(vrb, "_kill_current"),
        patch.object(vrb, "_start_ffmpeg"),
        patch.object(vrb, "_read_stderr", return_value=""),
        patch("shitbox.capture.buzzer.beep_ffmpeg_stall"),
        patch("shitbox.capture.ring_buffer.fire_alert") as mock_fire,
        patch("time.sleep", side_effect=_sleep_side_effect),
    ):
        try:
            vrb._health_monitor()
        except SystemExit:
            pass

    # At least one call with CAPTURE_FAILURE subtype
    call_subtypes = [c[0][0] for c in mock_fire.call_args_list]
    assert "CAPTURE_FAILURE" in call_subtypes
```

**`test_mon03_capture_down_after_threshold`** — three consecutive stall cycles → CAPTURE_DOWN:
Use the same factory + sleep-side-effect scaffold. Patch `_check_stall` with `side_effect=[True, True, True]` and extend `sleep_calls` to `[None, None, None, SystemExit("stop")]`. Assert `fire_alert` was called with subtype `"CAPTURE_DOWN"` exactly once.

**`test_mon03_capture_restored_fires`** — stall then clean segment → `fire_recovery("CAPTURE_FAILURE", ...)`. Same factory. Patch `_check_stall` with `side_effect=[True, False]` and assert `fire_recovery` call list contains `"CAPTURE_FAILURE"`.

---

### `tests/test_dashboard.py` (EXTEND — test, integration)

**Analog:** self — `test_sse_slow_schema` at lines 221-237 and `test_sse_slow_has_active_driver_key` at lines 376-399.

**Existing template** (lines 376-399 — the more precise of the two, asserts a specific key's presence):
```python
def test_sse_slow_has_active_driver_key(mbtiles_fixture):
    """DISP-03: /sse/slow payload must include 'active_driver' key."""
    import json as _json
    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/slow")
    finally:
        srv.stop()
    data_line = next((line for line in lines if line.startswith("data:")), None)
    assert data_line is not None, "no data lines received from /sse/slow"
    payload = _json.loads(data_line[len("data:"):].strip())
    assert "active_driver" in payload
```

**New tests to add:**

**`test_sse_slow_contains_system_conditions`** — direct copy of the template, asserts the new key:
```python
def test_sse_slow_contains_system_conditions(mbtiles_fixture):
    """D-13: /sse/slow payload must include 'system_conditions' key (sibling of 'hardware')."""
    import json as _json
    from shitbox.dashboard.server import build_app

    app = build_app(mbtiles_path=mbtiles_fixture)
    srv, base = _start_live_server(app)
    try:
        lines = _read_sse_lines(base + "/sse/slow")
    finally:
        srv.stop()
    data_line = next((line for line in lines if line.startswith("data:")), None)
    assert data_line is not None
    payload = _json.loads(data_line[len("data:"):].strip())
    assert "system_conditions" in payload
    assert isinstance(payload["system_conditions"], list)
```

**`test_system_conditions_payload_shape`** — exercise the helper directly (no live server needed — mirrors RESEARCH Pattern 3 shape check):
```python
def test_system_conditions_payload_shape():
    """D-13: each system_conditions entry has role/label/tier/state/since_ms (scalars only)."""
    from shitbox.dashboard.sse import _system_conditions_payload
    from shitbox.health import alerts as alerts_mod
    alerts_mod.clear_state()

    payload = _system_conditions_payload()
    assert len(payload) == 3
    roles = {row["role"] for row in payload}
    assert roles == {"undervoltage", "thermal", "capture"}
    for row in payload:
        assert row["tier"] == "critical"
        assert row["state"] in {"clear", "active", "recovering", "restored"}
        assert row["label"] == row["role"].upper()
        # Scalar-only discipline (RESEARCH Pitfall 5)
        assert row["since_ms"] is None or isinstance(row["since_ms"], int)
```

---

## Shared Patterns

### Module-level GIL-atomic state (Pattern 1)

**Source:** `src/shitbox/hardware/state.py:37-87, 150-158`
**Apply to:** `src/shitbox/health/alerts.py` (new)
**Why:** RESEARCH line 275 locks this. Module-level dict + rebind-on-update + frozen dataclass. No `threading.Lock` on the alert-state path — the capture-path-sacred rule (Phase 10 D-02) forbids any lock on the sustain counter.

### Graceful-degradation imports (Pattern 2)

**Source:** `src/shitbox/health/thermal_monitor.py:23-50`
**Apply to:** `alerts.py`, `ring_buffer.py` (for the new `fire_alert`/`fire_recovery` import)
**Why:** RESEARCH "Project Constraints" line 152 — alerts helper must be importable from unit tests without dashboard or Piper booted. Phase 21 D-04 "never refuse boot" means the helper MUST tolerate TTS absence.

```python
try:
    from shitbox.dashboard.sse import push_event as dashboard_push_event
except ImportError:
    def dashboard_push_event(event: dict) -> None:  # type: ignore[misc]
        pass
```

### Dashboard ALERT payload shape

**Source:** `src/shitbox/health/thermal_monitor.py:252-257, 311-316`
**Apply to:** every `alerts.fire_alert` / `alerts.fire_recovery` call site — must emit the same 4-key dict shape.
```python
{
    "type": "ALERT",
    "subtype": <SUBTYPE_STRING>,
    "message": <UPPERCASE_SHORT_STRING>,
    "ts": time.time(),
}
```
Frontend already routes this to `showAlert` at `index.html:610-612`. No new routing.

### Structlog keyword logging

**Source:** `src/shitbox/hardware/state.py:89, 117, 146` — `log.info("hw_state_transition", role=role, prev=prev.state.value, new="missing")`
**Apply to:** every new `log.*` call in `alerts.py` and any new log line in `thermal_monitor.py` / `ring_buffer.py`.
**Why:** CLAUDE.md project convention. Never positional strings or f-strings.

### Test state-reset fixture

**Source:** `tests/test_ffmpeg_stall.py:224-230` (autouse fixture resetting `hw_state`)
**Apply to:** `tests/test_alerts.py` (for `alerts.clear_state()`) and wherever existing tests call `alerts.fire_alert` transitively.
```python
@pytest.fixture(autouse=True)
def _clear_alerts_state():
    from shitbox.health import alerts
    alerts.clear_state()
    yield
    alerts.clear_state()
```

### TTS style

**Source:** `src/shitbox/capture/speaker.py:435, 425-432, 455-462`
**Apply to:** new `speak_power_restored` utterance (per UI-SPEC line 113 TTS-mate to overlay "POWER RESTORED").
**Style:** terse, second-person, "Michael", observational rather than alarmed. The overlay copy is 1-2 uppercase words; the TTS is one short sentence.

---

## No Analog Found

None. Every file in this phase has a strong analogue already in the codebase. This is a delegation phase by design (RESEARCH "Key insight" line 388: "80% delegation to existing primitives").

---

## Metadata

**Analog search scope:**
- `src/shitbox/hardware/state.py` (module-level state idiom — full file read)
- `src/shitbox/health/thermal_monitor.py` (bug site + alert call shape + graceful-degradation imports — full file read)
- `src/shitbox/capture/ring_buffer.py:820-997` (stall detection + health-monitor wire-in site)
- `src/shitbox/dashboard/sse.py` (full file read — `_hardware_payload` + `/sse/slow` handler)
- `src/shitbox/dashboard/static/index.html` (targeted reads: 1-150, 210-330, 380-420, 525-675, 800-863)
- `src/shitbox/capture/speaker.py:400-540` (TTS voice + candidate recovery callables)
- `tests/test_thermal_monitor.py:150-240` (existing dashboard-push + subtype assertion pattern)
- `tests/test_ffmpeg_stall.py` (full file read — factory helper + health-monitor test pattern + `hw_state` fixture)
- `tests/test_dashboard.py` (full file read — `_start_live_server` scaffold + SSE-key assertion template)

**Files scanned:** 9 source files; every canonical analogue named in RESEARCH was verified in-tree at the stated line numbers.

**Pattern extraction date:** 2026-04-24

**Graphify cross-check:** `graphify-out/GRAPH_REPORT.md` confirms the relevant god-node hubs — `ThermalMonitorService` (123 edges, community 42 "Throttle State"), `VideoRingBuffer` (95 edges, community 37 "FFmpeg Process Health"). No hidden cross-community coupling to this phase's change set; the delegation stance in RESEARCH holds.
