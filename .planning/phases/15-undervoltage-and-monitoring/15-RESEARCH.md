# Phase 15: Undervoltage and Monitoring - Research

**Researched:** 2026-04-24
**Domain:** Raspberry Pi throttle-bitmask decoding, SSE alert fan-out, ffmpeg stall bookkeeping, Prometheus scrape retirement
**Confidence:** HIGH (all claims verified in live source; no guessing)

---

## Summary

Phase 15 is a surgical close-out of four v1.0 monitoring gaps plus a sticky Health-page
expansion. Almost every moving part already exists in the codebase — the work is fix, wire, and
extract, not invent.

The undervoltage bug is real and sits at `src/shitbox/health/thermal_monitor.py:297`: the code
short-circuits when `raw == self._last_throttled_raw`, which is a **full-word** compare. The
sticky since-boot bits (bit 16-19) latch at first brownout and never clear, so after the very
first dip the full-word is stable and the current-undervoltage bit (bit 0) never again wins an
alert cycle. Fix is a low-nibble compare (`raw & 0xf`) plus an N-read sustain counter. Everything
else downstream already works: `dashboard_push_event` with `type: "ALERT"` already lights the red
overlay; `speak_under_voltage` is already in `capture/speaker.py:435`; the hardware panel in the
frontend already renders per-device sticky state with tier colours.

Capture-failure surfacing is even smaller: `ring_buffer._health_monitor` at line ~891-967 already
detects ffmpeg crashes and stalls and already calls `hw_state.report_degraded(self.role)` plus
`buzzer.beep_ffmpeg_stall()` on a stall. Wiring a `fire_alert("CAPTURE_FAILURE", ...)` next to
those calls plus a small counter for `CAPTURE_DOWN` is the whole change.

The `alerts.py` helper should mirror `hardware/state.py`'s module-level GIL-atomic rebind pattern
— same file size, same conventions, same graceful-degradation stance. Each alert subtype owns a
small frozen dataclass tracking `sustain_count`, `fired`, and `last_state`. No external lock, no
class wrapper.

**Primary recommendation:** Extract `src/shitbox/health/alerts.py` first (Wave 0), then fix
PWR-01 in thermal_monitor (Wave 1), wire MON-03 in ring_buffer (Wave 1 parallel), extend
`_hardware_payload` siblinged by `_system_conditions_payload` (Wave 2), delete the commented-out
`shitbox-mqtt-exporter` tree in home-ops plus audit Grafana (Wave 2 parallel), flip MON-01 flag
in REQUIREMENTS.md (Wave 2 trivial). The Health-page frontend rendering is a near-copy of the
existing hardware row template.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Undervoltage detection from kernel bitmask | Pi-local daemon (thermal_monitor) | — | `vcgencmd` is Pi-firmware-only; no other tier has access |
| Capture-stall detection | Pi-local daemon (ring_buffer.health_monitor) | — | ffmpeg lives in the daemon; nothing else sees segment mtimes |
| Alert fan-out transport | In-process FastAPI SSE | Browser (frontend) | `push_event` already runs in-process; clients consume via SSE |
| TTS speech | Pi-local daemon (speaker.py) | — | Piper + ALSA are Pi-local by design (Phase 5) |
| Sticky Health-page rendering | Browser (Alpine.js) | FastAPI (SSE slow payload) | Same pattern as the existing hardware panel |
| Prometheus scrape config | home-ops repo (Flux HelmRelease) | — | Cluster-side; orthogonal to the Pi |
| Grafana dashboard queries | home-ops repo (Grafana ConfigMap JSON) | — | Dashboard-side, downstream of the scrape |

---

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Undervoltage detection (PWR-01, PWR-02):**

- **D-01 — Bitmask read:** Compare only the low nibble, `raw & 0xf`, against the prior reading.
  Sticky bits 16-19 are decoded for logging but are never part of the alert trigger. The current
  bug is in `src/shitbox/health/thermal_monitor.py:297` where the full raw value is compared.
- **D-02 — Sustain before alerting:** Require a non-zero mask to persist across N consecutive
  reads (~2-3 seconds) before firing. Transient cranking dips must not alert.
- **D-03 — Recovery signal:** When the mask returns to zero and stays zero for N reads, fire a
  "power restored" TTS + 3-second green overlay. Matches Phase 21 D-09 recovery discipline.
- **D-04 — Surface pattern:** Spoken TTS (Piper) plus the existing full-screen red ALERT overlay.
  No buzzer beep on undervoltage in this phase — buzzer stays as the fallback path Phase 5
  already wired.

**Alert channel shape:**

- **D-05 — Reuse existing channel:** Keep using `dashboard_push_event({"type": "ALERT",
  "subtype": X, "message": ..., "ts": ...})` on `/sse/events`. Do not invent a new `system_event`
  channel — the frontend already routes `type === "ALERT"` to the full-screen overlay.
- **D-06 — Subtypes:** `UNDERVOLTAGE` / `UNDERVOLTAGE_CLEARED`, `CAPTURE_FAILURE`,
  `CAPTURE_RESTORED`, `CAPTURE_DOWN`. `THERMAL_*` already exists in thermal_monitor.py — leave
  alone.

**Capture-failure detection (MON-03):**

- **D-07 — Trigger source:** Reuse the existing `_is_stalled()` check in `ring_buffer.py`. One
  signal: ffmpeg stopped producing segments.
- **D-08 — Restart bookkeeping:** Count consecutive restart attempts. N (small integer, e.g. 3)
  in a rolling window triggers `CAPTURE_DOWN`; a clean segment after restart triggers
  `CAPTURE_RESTORED`.

**Monitoring plumbing:**

- **D-09 — HLTH-01 closure:** No code change. Metrics are confirmed live in Grafana. Flag MON-01
  closed in REQUIREMENTS.md with a one-line note.
- **D-10 — MQTT scrape retirement:** Delete the `shitbox-mqtt-exporter` scrape entry from the
  home-ops Prometheus config entirely. Before deleting, grep Grafana dashboards + alerting rules
  for `job="shitbox-mqtt-exporter"` and migrate survivors to `job="shitbox"`.

**Debounce / cadence seam:**

- **D-11 — Tiny shared helper:** Extract `src/shitbox/health/alerts.py` exposing
  `fire_alert(subtype, message, tts_fn)` and `fire_recovery(subtype, message, tts_fn)`. Owns
  sustain counting, once-on-transition semantics, recovery semantics.
- **D-12 — TTS cadence:** Once on transition, once on recovery. No repeat-until-acknowledged.

**Health page:**

- **D-13 — Expand the hardware panel into a Health page.** Sticky colour state for `undervoltage`,
  `thermal`, `capture` alongside existing devices. Payload extension in `sse.py` next to
  `_hardware_payload()`; frontend rendering extends the existing hardware list.

### Claude's Discretion

- Exact N for sustain-before-alert (2 or 3 reads) — pick based on the 5 s read cadence.
- Exact N for `CAPTURE_DOWN` threshold — reasonable default.
- Wording of TTS phrases — stay consistent with existing Phase 5 phrasing, keep short.
- Health page colour scheme for system conditions — follow the hardware panel's existing palette.
- Whether `alerts.py` uses class/instance state or module-level counters — pick whichever matches
  existing conventions.

### Deferred Ideas (OUT OF SCOPE)

- `HardwareState` / `SystemCondition` unified abstraction — Phase 21 retrofit.
- Button-as-acknowledge for critical alerts — Phase 21 D-05.
- Broader capture-failure surface detection (`/dev/video*`, audio device, encoder CPU) — Phase 21.
- MQTT exporter resurrection — not Phase 15's problem.
- Repeat-until-acknowledged TTS, criticality-tier alert escalation — Phase 21.
- Pi 5 firmware mailbox hang (2026-04-24) — separate `/gsd-debug`.

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PWR-01 | Software correctly detects current undervoltage using bits 0-3 only, not sticky historical | Bug confirmed at `thermal_monitor.py:297`; fix is `raw & 0xf` mask + sustain counter. Decoder `_decode_throttled` at line 93 already separates current from since_boot. |
| PWR-02 | Undervoltage alert surfaces visibly in live dashboard and triggers spoken TTS | `dashboard_push_event` at line 311-316 already fires with `type: "ALERT"` subtype; `speak_under_voltage()` at `speaker.py:435` already exists; frontend `showAlert` at `index.html:536` already routes ALERT to red overlay. Recovery path is new: add `UNDERVOLTAGE_CLEARED` subtype + green overlay. |
| MON-01 | HLTH-01 closed — CPU temp, disk %, sync backlog metrics confirmed reaching Prometheus | `health_collector.py:101-109` emits `cpu_temp_celsius`, `cpu_percent`, `disk_percent`, `sync_backlog`; `batch_sync.py:524-548` remote-writes them under `shitbox_cpu_temp`, `shitbox_cpu_pct`, `shitbox_disk_pct`, `shitbox_sync_backlog`. No code change needed — just flip the checkbox. |
| MON-02 | MQTT scrape job label conflict resolved | `shitbox-mqtt-exporter/ks.yaml` entry already commented out in `observability/kustomization.yaml:20`. Directory `kubernetes/apps/observability/shitbox-mqtt-exporter/` still on disk and needs `rm -rf`. `externalsecret.yaml` in that tree also references the name. No Grafana dashboards or custom-alerts reference `job="shitbox-mqtt-exporter"` (grep confirmed zero matches) — safe to delete. |
| MON-03 | All critical events (thermal, undervoltage, capture failure) surface visibly in live dashboard | Thermal already wired. Undervoltage covered by PWR-02. Capture-failure wires at `ring_buffer.py:938-953` where `_check_stall()` already triggers `hw_state.report_degraded(self.role)` + `buzzer.beep_ffmpeg_stall()`. Add `fire_alert("CAPTURE_FAILURE", ...)` alongside; add consecutive-restart counter + `CAPTURE_DOWN` threshold + `CAPTURE_RESTORED` on clean segment post-restart. |

---

## Project Constraints (from CLAUDE.md)

- **structlog keyword logging:** `log.info("alert_fired", subtype=..., sustain_reads=...)` — never
  positional/f-string.
- **Line length 100, ruff E/F/I/W, target Python 3.9.**
- **Full mypy annotations required** on all new code.
- **In-process FastAPI:** SSE fan-out runs in the dashboard thread; the capture path is sacred —
  alerts must be non-blocking (D-02 Phase 10 reference).
- **Graceful degradation pattern for dashboard imports:** `try: from shitbox.dashboard.sse import
  push_event; except ImportError: def push_event(*a, **k): pass` — mirror the thermal_monitor
  approach at lines 45-50. Keeps `alerts.py` importable from unit tests without the dashboard
  subsystem booted.
- **Phase 21 D-04 "never refuse boot":** alerts helper must tolerate TTS or dashboard being
  absent without raising.

---

## Standard Stack

### Core (already in project — no new deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `structlog` | `>=24.0.0` | Keyword logging for alert events | Project convention |
| `fastapi` | `>=0.115` | `/sse/events` route | Already serving the dashboard |
| `sse-starlette` | `>=2.1` | SSE response machinery | Already used by `sse.py` |
| `piper-tts` | `>=1.4.0` | `speak_under_voltage`, TTS speech | Phase 5 in production |
| `psutil` | `>=5.9.0` | CPU/disk metrics (MON-01 verification) | Already in `health_collector.py` |

### Supporting (test-only)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `>=7.0` | Unit + integration tests | All new test files |
| `unittest.mock` | stdlib | Patch `_read_throttled`, `dashboard_push_event`, `speak_under_voltage` | Alert-path tests |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Module-level state in alerts.py | Class-based `AlertTracker` singleton | Module-level matches `hardware/state.py` precedent; class adds ceremony with no benefit |
| New `/sse/alerts` stream | Reuse `/sse/events` with `type: "ALERT"` | D-05 locks the latter; frontend already routes it |
| Per-alert-subtype stderr-style channel | Shared helper | D-11 locks the helper; keeps logic in one place |

**Installation:** Nothing new to install. All dependencies already in `pyproject.toml`.

**Version verification:** Not applicable — no new pins. [VERIFIED: `pyproject.toml`]

---

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Pi-local daemon                             │
│                                                                     │
│  ┌──────────────────┐      ┌────────────────────────────────────┐  │
│  │ thermal_monitor  │      │ ring_buffer._health_monitor        │  │
│  │ _loop() @ 0.2 Hz │      │ tick @ RESTART_BACKOFF_SECONDS=2s  │  │
│  │                  │      │                                    │  │
│  │ _read_throttled  │      │ _check_stall() / process poll      │  │
│  │   ↓              │      │   ↓                                │  │
│  │ raw & 0xf ≠ prev │      │ stall or crash                     │  │
│  │   ↓              │      │   ↓                                │  │
│  │ sustain counter  │      │ restart + increment counter        │  │
│  └────────┬─────────┘      └──────────────┬─────────────────────┘  │
│           │                               │                         │
│           └──────────┬────────────────────┘                         │
│                      ↓                                              │
│           ┌──────────────────────────┐                              │
│           │  health/alerts.py        │                              │
│           │                          │                              │
│           │  fire_alert(subtype,     │                              │
│           │             msg, tts_fn) │                              │
│           │  fire_recovery(...)      │                              │
│           │                          │                              │
│           │  state: {subtype:        │                              │
│           │    (sustain, fired)}     │                              │
│           └────┬───────┬─────────────┘                              │
│                │       │                                            │
│                │       └────────────────────┐                       │
│                ↓                            ↓                       │
│   ┌──────────────────────┐    ┌──────────────────────────┐         │
│   │ dashboard_push_event │    │ speak_under_voltage /    │         │
│   │ (/sse/events)        │    │ speak_capture_failed /   │         │
│   │ type: "ALERT"        │    │ speak_thermal_* (Piper)  │         │
│   └──────────┬───────────┘    └──────────────────────────┘         │
│              │                                                      │
│              ↓                                                      │
│   ┌──────────────────────────┐                                     │
│   │ /sse/slow                │                                     │
│   │   adds system_conditions │                                     │
│   │   beside hardware[]      │                                     │
│   └──────────┬───────────────┘                                     │
└──────────────┼──────────────────────────────────────────────────────┘
               │ HTTP SSE
               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   Browser (index.html, Alpine.js)                   │
│                                                                     │
│   showAlert(ev) → red/green full-screen overlay (transient 3-10s)   │
│                                                                     │
│   systemConditions[] render beside hardware[] in Hardware modal     │
│   → sticky colour state until cleared (Health page)                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/shitbox/health/
├── alerts.py               # NEW — fire_alert / fire_recovery + sustain state
├── thermal_monitor.py      # MODIFY — fix line 297 compare, delegate to alerts
└── health_collector.py     # UNCHANGED — already correct for MON-01

src/shitbox/capture/
└── ring_buffer.py          # MODIFY — wire fire_alert on stall path

src/shitbox/dashboard/
├── sse.py                  # MODIFY — add _system_conditions_payload()
└── static/index.html       # MODIFY — render sticky system conditions

tests/
├── test_alerts.py          # NEW — sustain + once-on-transition tests
├── test_thermal_monitor.py # EXTEND — add PWR-01 sticky-bit regression test
├── test_ffmpeg_stall.py    # EXTEND — add CAPTURE_FAILURE / CAPTURE_DOWN flow
└── test_dashboard.py       # EXTEND — assert system_conditions in slow payload
```

### Pattern 1: Module-level GIL-atomic rebind (mirrors `hardware/state.py`)

**What:** Mutable state is held in a single module-level dict; updates build a new dict and
rebind the module-level name in one step. Python's GIL makes the rebind atomic, so readers
either see the old dict or the new one, never a half-written mutation.

**When to use:** Shared state across daemon threads where locks would block the capture path.

**Example:**

```python
# Source: src/shitbox/hardware/state.py (lines 37-87, current production code)
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True, slots=True)
class AlertStatus:
    subtype: str
    sustain_count: int
    fired: bool
    last_ts: float

_state: Dict[str, AlertStatus] = {}

def _observe(subtype: str, active: bool, tts_fn, message: str, push_fn, sustain_required: int) -> None:
    prev = _state.get(subtype)
    if prev is None:
        prev = AlertStatus(subtype=subtype, sustain_count=0, fired=False, last_ts=0.0)
    # ... decide transition, build new_state, rebind _state
    global _state
    new_map = dict(_state)
    new_map[subtype] = new_status
    _state = new_map  # GIL-atomic rebind
```

### Pattern 2: Graceful-degradation import wrapper (mirrors `thermal_monitor.py:45-50`)

**What:** Each alert helper imports `dashboard_push_event` and TTS functions behind a
`try/except ImportError` so the module stays importable in unit tests without the dashboard or
Piper wired.

**When to use:** Any module whose callers may run in reduced configurations (tests, boot-
failure, degraded TTS).

**Example:**

```python
# Source: src/shitbox/health/thermal_monitor.py:45-50
try:
    from shitbox.dashboard.sse import push_event as dashboard_push_event
except ImportError:
    def dashboard_push_event(event: dict) -> None:  # type: ignore[misc]
        pass
```

### Pattern 3: Sibling payload extension (mirrors `_hardware_payload()`)

**What:** Add a new `_system_conditions_payload()` function with the same shape as
`_hardware_payload()` — list of dicts with `role`, `label`, `tier`, `state`, `since_ms`.
Splice into the `/sse/slow` JSON under a new key.

**When to use:** Dashboard state that needs per-condition sticky rendering.

**Example:**

```python
# Source: src/shitbox/dashboard/sse.py:56-70 (reference shape)
def _system_conditions_payload() -> List[Dict[str, Any]]:
    now = time.time()
    out = []
    for st in alerts.snapshot().values():
        if not st.fired:
            continue
        out.append({
            "role": st.subtype.lower(),       # e.g. "undervoltage"
            "label": st.subtype.replace("_", " ").title(),
            "tier": "critical",               # all three system conditions are critical
            "state": "degraded" if st.fired else "present",
            "since_ms": int((now - st.last_ts) * 1000) if st.last_ts else None,
        })
    return out
```

### Anti-Patterns to Avoid

- **Comparing full-word throttle bitmask:** the bug we are fixing. Always mask to low nibble for
  alert decisions. Keep sticky bits for logging only.
- **Locking across the capture path:** alerts.py MUST NOT call into any code path that can block
  the 100 Hz sampler. `push_event` is already drop-on-full; TTS `_enqueue` is
  already a queue push. Do not add a `threading.Lock` around the sustain counter — the GIL-atomic
  rebind is the lock.
- **New SSE channel:** D-05 locks `/sse/events` + `type: "ALERT"`. Do not introduce a new URL.
- **Nested `HardwareSupervisor`-style class:** D-11 explicitly says "the seam, not the cathedral."
  Two module functions + a module-level dict.
- **Counting restarts in a class-level attribute on `VideoRingBuffer`:** the helper already
  tracks sustain and transition counts per subtype. Pass the consecutive-restart count into
  `fire_alert("CAPTURE_DOWN", ...)` as the sustain-trigger, not as a separate bookkeeping field.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Throttle bitmask decode | Custom bitfield parser | Existing `_decode_throttled()` at `thermal_monitor.py:93` | Already tested and shipped |
| SSE fan-out with drop-on-full | Queue management | Existing `push_event` in `sse.py:104` | Already non-blocking; already broadcasts per-client |
| ffmpeg stall detection | Mtime watcher | Existing `_check_stall()` at `ring_buffer.py:840` | Already handles armed/unarmed state transitions |
| TTS utterance gating | Cadence tracking | Phase 5 `_should_alert()` already in speaker.py | Boot grace period already baked in |
| Full-screen alert overlay | New CSS/markup | Existing `alertOverlay` in `index.html:217-224` | Already z-indexed above map, below modals |
| Hardware-style sticky row | New component | Existing `.hw-row` template in `index.html:396-404` | Exact same tier/state/glyph/since layout |
| Per-device state dataclass | New dataclass | `DeviceStatus` shape from `hardware/state.py:23-33` is the direct template | Matches existing serialisation |

**Key insight:** Phase 15 is 80% delegation to existing primitives. The genuinely new code is
~150 lines in `alerts.py` plus two short wiring changes. Anyone proposing more than that should
be challenged.

---

## Runtime State Inventory

*Not a rename/refactor/migration phase — inventory not required. The only state-touching change
is `rm -rf kubernetes/apps/observability/shitbox-mqtt-exporter/` in home-ops plus Flux reconcile;
Prometheus will stop scraping that target automatically when the ServiceMonitor disappears. No
stored data migration, no OS-registered state change, no env-var rename.*

---

## Common Pitfalls

### Pitfall 1: "I fixed the mask, why does it still not alert?"

**What goes wrong:** After replacing `raw == self._last_throttled_raw` with `(raw & 0xf) ==
(self._last_throttled_raw & 0xf)`, the alert still only fires on first nibble-change after boot.
**Why it happens:** The outer control flow at line 297 `return` short-circuits on "no change",
so a sustained undervoltage after boot will set the mask once, store it, and never fire again —
same bug, masked differently.
**How to avoid:** Do not gate the alert decision on "change since last read." Instead:
(1) read the raw value every cycle, (2) compute the low-nibble active state, (3) feed it into
the alerts helper every cycle — the helper owns sustain and once-on-transition. The
`_last_throttled_raw` field keeps its logging role (decode + structlog the change) but stops
being the alert gate.
**Warning signs:** If the fix still lives inside the `if raw == self._last_throttled_raw:
return` block, the pitfall is still there.

### Pitfall 2: Sticky-bit recovery never fires

**What goes wrong:** Undervoltage clears in hardware, but the green overlay + "power restored"
TTS never fires.
**Why it happens:** The recovery branch requires the low-nibble-active state to transition from
True to False AND sustain at False for N reads. If `fire_recovery` only checks `not active` at
the instant, a single transient zero-read after a sustained brownout can fire a spurious
recovery, or — if gated by transition-only — the recovery is missed entirely because the caller
stopped sending the "active" signal.
**How to avoid:** The helper's `fire_alert` and `fire_recovery` should BOTH be called every
cycle (alerts.observe(subtype, active_bool, ...) is cleaner). Internal state transitions from
`fired=True, sustain_count=N` → when `active=False` observed, drain a `clear_sustain_count` → at
threshold, emit recovery, reset both counters.
**Warning signs:** Tests where a two-read blip of `active=False` mid-sustained-undervoltage
triggers recovery.

### Pitfall 3: Capture-stall alert fires repeatedly per restart cycle

**What goes wrong:** `_health_monitor` detects a stall, restarts ffmpeg, stall re-occurs in 30s,
restart, stall — alert fires every ~30s forever.
**Why it happens:** If `fire_alert("CAPTURE_FAILURE", ...)` is called on every stall detection
without once-on-transition gating, the "fired" flag needs to persist across the restart.
**How to avoid:** Helper tracks `fired=True` on first alert, does not re-fire until
`fire_recovery` is observed (clean segment after restart) OR the threshold crosses into
`CAPTURE_DOWN`. Restart-counter separately accumulates; crossing threshold = one new transition
`CAPTURE_FAILURE` → `CAPTURE_DOWN`, no retriggering of `CAPTURE_FAILURE`.
**Warning signs:** More than one `CAPTURE_FAILURE` log line between a `CAPTURE_RESTORED` and the
next genuine new stall.

### Pitfall 4: Frontend overlay colour stays red for undervoltage clear

**What goes wrong:** The full-screen overlay for `UNDERVOLTAGE_CLEARED` renders red instead of
green because `showAlert` at `index.html:538-545` hard-codes red for `type === "ALERT"`.
**Why it happens:** The current `showAlert` treats all ALERT events as red. For recovery we
need a green variant.
**How to avoid:** Extend `showAlert` to branch on subtype ending in `_CLEARED` or `_RESTORED`
(green `#238636`, short duration 3s) vs generic (red `#da3633`, 10s). Keep the generic path for
unknown subtypes.
**Warning signs:** Any hardcoded `#da3633` / "red" in the alert path without a subtype branch.

### Pitfall 5: Health-page payload inflates `/sse/slow` beyond JSON size comfort

**What goes wrong:** Adding `system_conditions` to the 1 Hz stream pushes the per-message size
over 8 KB once all three conditions fire simultaneously with nested detail.
**Why it happens:** Over-serialising internal state (history, recent restart timestamps, raw
throttle bitmask per condition).
**How to avoid:** Payload shape mirrors `_hardware_payload()` exactly — 5-6 scalar fields per
entry. No arrays of history. Log detail goes to structlog, not to SSE.
**Warning signs:** A `system_conditions[i].history` field or anything with a list in it.

### Pitfall 6: MON-02 deletion breaks an unrelated Grafana panel

**What goes wrong:** Deleting the `shitbox-mqtt-exporter` scrape removes the Prometheus
metric source a Grafana panel still queries.
**Why it happens:** Grep for `job="shitbox-mqtt-exporter"` missed a panel that queried
`{__name__=~"shitbox_mqtt_.*"}` without the job label.
**How to avoid:** Grep broadly for both `shitbox-mqtt-exporter` (the job name) and any metric
name prefix unique to the exporter. Current `grafana/app/dashboards/` confirmed zero matches for
either pattern in this session. [VERIFIED: ripgrep over `home-ops/kubernetes/apps/observability/`
returned no matches in `grafana/app/dashboards/` or `custom-alerts/`.]
**Warning signs:** Any dashboard JSON querying a metric prefix that does not appear in
`batch_sync.py` — those came from the MQTT exporter.

---

## Code Examples

Verified patterns from the project sources — not synthesised.

### Current buggy compare (what to replace)

```python
# Source: src/shitbox/health/thermal_monitor.py:290-316 (current production)
def _check_throttled(self) -> None:
    """Read and decode throttle bitmask; alert on under-voltage."""
    raw = self._read_throttled()
    if raw is None:
        return

    with self._lock:
        if raw == self._last_throttled_raw:           # ← BUG: full-word compare
            return  # No change — stay silent
        self._last_throttled_raw = raw
    decoded = _decode_throttled(raw)
    log.warning(
        "throttle_state_changed",
        raw_hex=hex(raw),
        current=decoded["current"],
        since_boot=decoded["since_boot"],
    )

    if decoded["current"].get("under_voltage"):       # ← never reached after first sticky set
        beep_under_voltage()
        speak_under_voltage()
        dashboard_push_event({
            "type": "ALERT",
            "subtype": "UNDERVOLTAGE",
            "message": "UNDERVOLTAGE DETECTED",
            "ts": time.time(),
        })
```

### Capture-stall detection site (where to wire `fire_alert`)

```python
# Source: src/shitbox/capture/ring_buffer.py:936-953 (current production)
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
        hw_state.report_degraded(self.role)           # ← existing
        buzzer.beep_ffmpeg_stall()                    # ← existing
        # ★ wire fire_alert("CAPTURE_FAILURE", …) here
        # Kill before replacing _process reference to avoid zombies
        self._kill_current()
        self._reset_stall_state()
        self._start_ffmpeg()
        # ★ increment consecutive_restart_count; if >= 3, fire_alert("CAPTURE_DOWN", …)
        last_audio_retry = time.time()
        continue
```

Successful segment production after restart → `fire_recovery("CAPTURE_FAILURE"/"CAPTURE_DOWN",
..., tts_fn=...)` resets the count. Tricky detail: the "successful segment" observation is
easiest done by watching `_check_stall()` return False a cycle after it returned True — the
helper's internal re-arm already tracks first-observation; when `_check_stall_armed` flips True
again and `consecutive_restart_count > 0`, fire `CAPTURE_RESTORED`.

### Existing SSE payload shape (model for system_conditions)

```python
# Source: src/shitbox/dashboard/sse.py:56-70 (current production)
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

### Existing frontend `showAlert` (where to add green-for-recovery branch)

```javascript
// Source: src/shitbox/dashboard/static/index.html:536-548 (current production)
showAlert(payload) {
  if (this._alertTimer) { clearTimeout(this._alertTimer); this._alertTimer = null; }
  const isSystem = payload.type === 'ALERT';
  const colour = isSystem
    ? '#da3633'                              // ← always red — needs subtype branch
    : (this.EVENT_COLOURS[payload.type] || '#8b949e');
  const message = isSystem
    ? payload.message
    : `${payload.type} · ${(payload.peak_g || 0).toFixed(1)}g`;
  this.alertOverlay = { message, colour, isSystem };
  const duration = isSystem ? 10000 : 3000;
  this._alertTimer = setTimeout(() => { this.alertOverlay = null; }, duration);
},
```

### Existing hardware row template (model for sticky system-condition rows)

```html
<!-- Source: src/shitbox/dashboard/static/index.html:396-404 -->
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

### Existing TTS wording style (model for new phrases)

```python
# Source: src/shitbox/capture/speaker.py:435-442 (current production)
def speak_under_voltage() -> None:
    """Announce an under-voltage condition detected by the kernel."""
    if not _should_alert():
        return
    _enqueue("Michael, the electrical supply is unsteady.")
```

Style pattern: second-person, addresses Michael, terse, observational rather than alarmed. New
wording should match. Suggested new utterances (Claude's discretion per D-13): `"Power restored,
Michael. We're back to steady."` / `"Michael, the recording has failed repeatedly — capture is
down."` / `"Recording is back, Michael."`

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MQTT exporter scrape job | Batch sync over remote_write to Prometheus | Phase 13 era | MQTT permanently off; the exporter becomes dead weight |
| Full-word throttle compare | Low-nibble compare | This phase | Undervoltage alerts actually fire after brownout |
| Per-collector alert logic | `health/alerts.py` helper | This phase | Three alert paths share sustain + transition semantics |
| Transient ALERT overlay only | Transient ALERT + sticky Health panel | This phase (D-13) | Driver sees condition after the overlay times out |

**Deprecated/outdated:**

- `shitbox-mqtt-exporter` (`home-ops/kubernetes/apps/observability/shitbox-mqtt-exporter/`):
  already commented out in `observability/kustomization.yaml:20`; directory + externalsecret still
  on disk. Delete the directory and the ks-reference remains consistent.
- The "`insert_readings_batch` cpu_percent bug" language in earlier staging docs: stale.
  `database.py:469` already handles `cpu_percent`, and `batch_sync.py:536-539` already emits
  `shitbox_cpu_pct` correctly. Document the miscue in RESEARCH so the planner does not
  accidentally write a "fix" for a non-bug.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | — | — | — |

All factual claims in this research were verified against live source in this session. Every
line number, every function name, and every file path was read directly from the repo.

---

## Open Questions

1. **Sustain-read count N (2 vs 3).**
   - What we know: `thermal_monitor._loop()` sleeps `POLL_INTERVAL_S = 5.0` seconds between
     reads. Two reads = 5 s sustain; three reads = 10 s.
   - What's unclear: the canonical "transient cranking dip" duration on the Ford Laser. Starter
     motor load drops battery ~1-2 s.
   - Recommendation: N=2 (10 s total including first-observation). Longer than any crank, shorter
     than driver attention span. Document the number inline so it can be tuned from a single
     constant.

2. **`CAPTURE_DOWN` threshold.**
   - What we know: `_health_monitor` cycles every `RESTART_BACKOFF_SECONDS = 2.0` s; a stall
     takes `STALL_TIMEOUT_SECONDS = 30.0` s to detect. Each failed cycle is ~30 s before the next
     restart chance.
   - What's unclear: How many repeated restarts indicate "the camera is really gone" vs "bus hiccup."
   - Recommendation: 3 consecutive restart attempts within a rolling 5-minute window. Matches
     Phase 21 backoff philosophy (5s → 15s → 60s → 5 min cap).

3. **Health-page placement of system_conditions rows.**
   - What we know: Existing hardware modal renders devices grouped by tier (critical first).
   - What's unclear: whether system conditions get their own section ("System") or mix in as
     additional "critical" rows.
   - Recommendation: separate section with its own label, rendered above devices. They describe
     state of subsystems, not state of physical hardware.

4. **Recovery TTS phrasing consistency.**
   - What we know: Phase 5 style is second-person, addresses Michael, terse and observational.
   - What's unclear: Whether "power restored" should feel relieved (tonal match to
     `speak_boot_thanks`) or matter-of-fact (tonal match to `speak_thermal_recovered`).
   - Recommendation: Matter-of-fact. Longer-form relief phrases already exist for boot/service-
     recovered paths.

---

## Environment Availability

*No external tools or services beyond the existing daemon runtime. Skip.*

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 7.0 (pyproject.toml line 42) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` sets `pythonpath = ["src"]`) |
| Quick run command | `pytest tests/test_thermal_monitor.py tests/test_alerts.py tests/test_ffmpeg_stall.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| PWR-01 | Sticky bits 16-19 do not fire alert; low-nibble change does fire | unit | `pytest tests/test_thermal_monitor.py::test_pwr01_sticky_bits_ignored -x` | ❌ Wave 0 |
| PWR-01 | Sustain N reads required before alert | unit | `pytest tests/test_thermal_monitor.py::test_pwr01_sustain_required -x` | ❌ Wave 0 |
| PWR-02 | `dashboard_push_event` fires with `type:"ALERT", subtype:"UNDERVOLTAGE"` on sustained low-nibble | unit (mock push_event) | `pytest tests/test_thermal_monitor.py::test_pwr02_undervoltage_dashboard_fires -x` | ❌ Wave 0 |
| PWR-02 | `speak_under_voltage()` called once on transition, not per cycle | unit (mock TTS) | `pytest tests/test_thermal_monitor.py::test_pwr02_tts_once_on_transition -x` | ❌ Wave 0 |
| PWR-02 | `UNDERVOLTAGE_CLEARED` fires after sustained-zero following sustained-nonzero | unit | `pytest tests/test_thermal_monitor.py::test_pwr02_recovery_fires -x` | ❌ Wave 0 |
| MON-01 | `batch_sync._readings_to_metrics` emits `shitbox_cpu_pct`, `shitbox_cpu_temp`, `shitbox_disk_pct`, `shitbox_sync_backlog` | unit (existing) | `pytest tests/test_batch_sync_metrics.py -x` | ✅ (extend if needed) |
| MON-01 | Requirements checkbox flipped (closure artefact) | manual | `grep -n "MON-01" .planning/REQUIREMENTS.md` — expect `[x]` | n/a |
| MON-02 | Directory `home-ops/.../shitbox-mqtt-exporter/` is gone | manual | `test ! -d ~/dev/home-ops/kubernetes/apps/observability/shitbox-mqtt-exporter` | n/a |
| MON-02 | Grafana dashboards contain no `shitbox-mqtt-exporter` references | manual audit | `rg "shitbox[-_]mqtt" ~/dev/home-ops/kubernetes/apps/observability/grafana/` — expect zero matches | already zero |
| MON-03 | `fire_alert("CAPTURE_FAILURE", ...)` fires on first stall | unit (mock push_event) | `pytest tests/test_ffmpeg_stall.py::test_mon03_capture_failure_fires -x` | ❌ Wave 0 |
| MON-03 | `CAPTURE_DOWN` fires after N=3 consecutive restart attempts | unit | `pytest tests/test_ffmpeg_stall.py::test_mon03_capture_down_after_threshold -x` | ❌ Wave 0 |
| MON-03 | `CAPTURE_RESTORED` fires on clean segment after restart | unit | `pytest tests/test_ffmpeg_stall.py::test_mon03_capture_restored_fires -x` | ❌ Wave 0 |
| D-13 | `/sse/slow` includes `system_conditions` alongside `hardware` | integration | `pytest tests/test_dashboard.py::test_sse_slow_contains_system_conditions -x` | ❌ Wave 0 |
| D-13 | System-condition entry has role/label/tier/state/since_ms | unit | `pytest tests/test_dashboard.py::test_system_conditions_payload_shape -x` | ❌ Wave 0 |
| Helper | `alerts.fire_alert` emits exactly once on transition | unit | `pytest tests/test_alerts.py::test_fire_alert_once_on_transition -x` | ❌ Wave 0 |
| Helper | `alerts.fire_recovery` emits exactly once on transition | unit | `pytest tests/test_alerts.py::test_fire_recovery_once_on_transition -x` | ❌ Wave 0 |
| Helper | Sustain counter resets on intermittent zeros | unit | `pytest tests/test_alerts.py::test_sustain_resets_on_break -x` | ❌ Wave 0 |
| Helper | `snapshot()` returns all subtypes with current state | unit | `pytest tests/test_alerts.py::test_snapshot_contains_all_tracked -x` | ❌ Wave 0 |
| Pi UAT | On-Pi: trigger brownout with bench PSU, observe overlay + TTS + sticky Health row | manual-only | — (driver-in-the-seat check) | n/a |

### Sampling Rate

- **Per task commit:** `pytest tests/test_thermal_monitor.py tests/test_alerts.py
  tests/test_ffmpeg_stall.py tests/test_dashboard.py -x`
- **Per wave merge:** `pytest` (full suite)
- **Phase gate:** Full suite green + manual Pi UAT with bench PSU brownout simulation before
  `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/test_alerts.py` — new file; covers `fire_alert`, `fire_recovery`, sustain reset,
  snapshot
- [ ] `tests/test_thermal_monitor.py` extension — add PWR-01 sticky-bits regression, PWR-02
  undervoltage + recovery flow with mocks
- [ ] `tests/test_ffmpeg_stall.py` extension — add MON-03 stall → `CAPTURE_FAILURE` →
  `CAPTURE_DOWN` → `CAPTURE_RESTORED` flow
- [ ] `tests/test_dashboard.py` extension — assert `system_conditions` key and shape in `/sse/slow`
- [ ] No framework install needed (pytest already a dev dep)

---

## Security Domain

*Security enforcement defaults on. For this phase the attack surface is near-zero: all changes
are Pi-local daemon code or Kubernetes manifests deleted behind the cluster firewall. No new
endpoints, no new auth, no new secrets.*

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Dashboard has no auth (Phase 10 D-05: "most people won't be wankers" — trust the rally wifi). Unchanged. |
| V3 Session Management | no | No sessions. |
| V4 Access Control | no | Read-only dashboard on LAN. |
| V5 Input Validation | no | No new input surfaces. SSE is outbound. |
| V6 Cryptography | no | No new crypto. |
| V7 Error Handling | yes | Graceful-degradation imports for dashboard/TTS — existing pattern |
| V8 Data Protection | no | No new data categories. |

### Known Threat Patterns for Pi-local FastAPI + Kubernetes GitOps

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret in plain-text externalsecret | Information Disclosure | Already using ExternalSecret references; deleting the shitbox-mqtt-exporter externalsecret removes a stale reference, no new secret |
| Stale scrape target returns 404 indefinitely | DoS (minor) | ServiceMonitor disappears when the HelmRelease does; Prometheus stops scraping automatically |
| Dashboard payload size growth leaks internal state | Information Disclosure (minor) | Keep `system_conditions` entries to scalar role/label/tier/state/since_ms — no history, no raw bitmasks |

---

## Sources

### Primary (HIGH confidence — read directly from the repo this session)

- `src/shitbox/health/thermal_monitor.py` (lines 45-50, 93-105, 290-316) — bug site, decoder,
  import pattern
- `src/shitbox/capture/ring_buffer.py` (lines 826-967) — stall detection, health monitor wiring
- `src/shitbox/dashboard/sse.py` (lines 34-70, 104-116, 164-198) — `push_event`,
  `_hardware_payload`, `/sse/slow` shape
- `src/shitbox/dashboard/static/index.html` (lines 217-224, 380-420, 536-548, 605-625,
  810-858) — `alertOverlay`, hardware modal, `showAlert`, SSE event handler, panel helpers
- `src/shitbox/hardware/state.py` (entire file, 159 lines) — module-level GIL-atomic rebind
  reference
- `src/shitbox/capture/speaker.py` (lines 405-530) — existing TTS functions, voice style
- `src/shitbox/sync/batch_sync.py` (lines 520-548) — MON-01 verification of metric names
- `src/shitbox/health/health_collector.py` (entire file, 109 lines) — MON-01 source of metrics
- `pyproject.toml` — dependency pins, ruff/mypy/pytest config
- `.planning/config.json` — nyquist_validation enabled
- `graphify-out/GRAPH_REPORT.md` — god nodes `ThermalMonitorService` (123 edges), `VideoRingBuffer`
  (95 edges); Communities 14 (Dashboard & Website Concepts), 37 (FFmpeg Process Health), 41 (CPU
  Temperature), 42 (Throttle State)
- `~/dev/home-ops/kubernetes/apps/observability/shitbox-mqtt-exporter/` (ks.yaml, helmrelease,
  externalsecret) — MON-02 target for deletion
- `~/dev/home-ops/kubernetes/apps/observability/kustomization.yaml:20` — already commented out
- `~/dev/home-ops/kubernetes/apps/observability/grafana/app/dashboards/shitbox-*.json` — verified
  zero references to mqtt-exporter
- `~/dev/home-ops/kubernetes/apps/observability/custom-alerts/app/prometheusrule.yaml` — verified
  zero references to shitbox
- `.planning/phases/15-undervoltage-and-monitoring/15-CONTEXT.md` — 13 locked decisions
- `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md` — tier model,
  recovery discipline (D-09), graceful-degradation stance (D-04)
- `.planning/phases/10-live-dashboard-with-offline-map/10-CONTEXT.md` — SSE stream conventions,
  capture-path-sacred rule (D-02)

### Secondary (MEDIUM confidence)

- None — no external sources needed. Every fact is in-tree.

### Tertiary (LOW confidence)

- None flagged.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — nothing new to pin; every dep already in pyproject.toml
- Architecture: HIGH — every pattern mirrors a production file read this session
- Pitfalls: HIGH — pitfalls 1 and 2 are derived directly from the code path; 3-6 are preventive
  for foreseeable traps, inspected against existing behaviour
- Test map: HIGH — test file names already match project convention; target test IDs inferred
  from Phase 21 test structure
- MON-02 scope: HIGH — ripgrep over home-ops returned empty for Grafana/alert references; only
  the exporter tree itself carries the name

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (30 days — no dependencies on external APIs that churn fast). The
only external dependency is the home-ops Flux reconcile; if somebody re-enables
`shitbox-mqtt-exporter/ks.yaml` in `kustomization.yaml` between now and planning, re-run the
ripgrep audit.
