---
phase: 21
plan: 04
type: execute
wave: 3
depends_on: [1, 2]
files_modified:
  - src/shitbox/display/oled.py
  - src/shitbox/dashboard/sse.py
  - src/shitbox/dashboard/static/index.html
  - tests/hardware/test_oled_hardware_line.py
  - tests/hardware/test_sse_hardware.py
autonomous: true
requirements: [HW-02, HW-03]
estimated_loc: 460
must_haves:
  truths:
    - "OLED line 3 renders IMU/CAM/PWR tokens with inversion on MISSING for critical tier, plus `ENV:N/M` roll-up for best_effort env devices"
    - "`/sse/slow` payload includes a `hardware` array with one entry per manifest device: role, label, tier, state, last_seen, since_ms"
    - "Dashboard index.html renders a HARDWARE panel: critical banner when any critical MISSING, per-device rows ordered critical→important→best_effort, best_effort roll-up count, colours per UI-SPEC"
    - "Row label / tier badge / state text use the copy table from UI-SPEC verbatim (PRESENT / RECOVERING / OFFLINE)"
    - "No new SSE route; piggy-back on /sse/slow at 1 Hz cadence"
  artifacts:
    - path: src/shitbox/display/oled.py
      provides: "Line 3 replaced with hardware rollup (3 critical/important tokens + ENV:N/M)"
      contains: "from shitbox.hardware import state as hw_state"
    - path: src/shitbox/dashboard/sse.py
      provides: "`hardware` field on /sse/slow payload"
      contains: "\"hardware\":"
    - path: src/shitbox/dashboard/static/index.html
      provides: "HARDWARE panel with banner + rows + best_effort roll-up"
      contains: "HARDWARE"
  key_links:
    - from: "hw_state.snapshot()"
      to: "/sse/slow JSON payload"
      via: "list comprehension serialising DeviceStatus fields"
      pattern: "\"hardware\":"
    - from: "/sse/slow hardware array"
      to: "dashboard HARDWARE panel"
      via: "Alpine x-for over hardware rows + computed critical-banner state"
      pattern: "x-for=\"row in hardware\""
    - from: "hw_state.snapshot()"
      to: "OLED line 3"
      via: "_draw_text per critical token + inversion on MISSING"
      pattern: "_draw_text.*inverted"
---

<objective>
Wire HardwareState into the three Pi-local surfaces defined by UI-SPEC: OLED
line 3, dashboard SSE payload, and dashboard HARDWARE panel. All three read
`hw_state.snapshot()` — none writes. Readers are decoupled from the supervisor;
they show whatever state exists at the moment of their render / SSE tick.

HW-02 acceptance ("visible to dashboard + OLED within one status refresh")
is enforced at three points:

1. OLED line 3 reflects state within one `oled.update_interval_seconds` tick.
2. `/sse/slow` emits a new `hardware` array at its 1 Hz cadence.
3. Dashboard Alpine component binds to that array and re-renders per tick.

HW-03 visual cadence (red banner for critical MISSING, tier-colored badges,
PRESENT / RECOVERING / OFFLINE state text) is enforced in the HTML per
UI-SPEC §Component Inventory.

Purpose: crew sees what the supervisor knows. No backend logic change.

Output:
- `display/oled.py` line 3 rewrite
- `dashboard/sse.py` payload extension
- `dashboard/static/index.html` HARDWARE panel
- Two new unit tests (OLED render, SSE payload)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-01-manifest-state-probes-PLAN.md
@.planning/phases/21-hardware-inventory-and-graceful-degradation/21-02-supervisor-speaker-PLAN.md
@src/shitbox/display/oled.py
@src/shitbox/dashboard/sse.py
@src/shitbox/dashboard/static/index.html
@CLAUDE.md

<interfaces>
From src/shitbox/hardware/state.py (Plan 01):
```python
hw_state.snapshot() -> Dict[str, DeviceStatus]   # role -> DeviceStatus(frozen)
hw_state.DeviceState.PRESENT / .DEGRADED / .MISSING
```

DeviceStatus fields consumed here:
```python
st.role            # e.g. "imu"
st.tier            # "critical" | "important" | "best_effort"
st.state           # DeviceState enum; st.state.value = "present"|"degraded"|"missing"
st.last_seen       # unix seconds; 0.0 if never
```

SSE payload shape (from UI-SPEC §Dashboard SSE payload shape, verbatim):
```jsonc
{
  "hardware": [
    {
      "role": "imu",
      "label": "IMU",
      "tier": "critical",
      "state": "present",
      "last_seen": 1713661234.5,
      "since_ms": 2100
    }
  ]
}
```

Copy table (from UI-SPEC §Copywriting — verbatim):
| role              | label              |
|-------------------|--------------------|
| imu               | IMU                |
| camera_front      | Front Cam          |
| power             | Power              |
| gps               | GPS                |
| environment       | Environment        |
| magnetometer      | Magnetometer       |
| light             | Ambient Light      |
| oled              | OLED               |
| temp_exterior     | Exterior Probe     |
| temp_engine_bay   | Engine Bay Probe   |
| camera_cabin      | Cabin Cam          |
| audio_mic         | USB Mic            |
| button            | Button             |
| display_hdmi      | HDMI               |

State text (verbatim): PRESENT / RECOVERING / OFFLINE.
State colours (CSS hex): green `#238636` PRESENT, amber `#d29922` DEGRADED / important-missing, red `#da3633` critical-missing, grey `#8b949e` best_effort badge + since-ms.
Banner copy (verbatim): `CRITICAL: <ROLE> OFFLINE` — role uppercase; multiple roles comma-separated.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: OLED line 3 hardware rollup + tests</name>
  <files>src/shitbox/display/oled.py, tests/hardware/test_oled_hardware_line.py</files>
  <read_first>
    - src/shitbox/display/oled.py (full file — especially `_render()` at lines 108-161 and `_draw_text` at lines 95-106)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md §OLED line 3 layout (lines 168-189) — final prescribed layout: `IMU● CAM● PWR●    ENV:2/3`
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §oled.py (lines 555-583)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Pitfall 4 (4-line budget)
  </read_first>
  <behavior>
    - Line 3 (y=32) now renders three fixed-width tokens: IMU / CAM / PWR at x=0, x=32, x=64.
    - For each of the three tokens, the text string is just the 3-letter role name (no glyph character on OLED — inversion communicates missing per UI-SPEC).
    - Critical-tier tokens (IMU, CAM) render with `inverted=True` when their device is MISSING in hw_state; important-tier (PWR) uses `inverted=False` always but DOES show the roll-up / state visually by the presence of the token text (on MISSING it still draws but stays non-inverted — matches UI-SPEC "Important tier does not invert on OLED").
    - A right-side roll-up `ENV:N/M` draws at x=96, y=32 where M = 3 (environment, magnetometer, light) and N = count present.
    - The OLD `IMU | ENV` block at lines 145-149 is removed; line 3 is entirely replaced.
    - If `hw_state.snapshot()` is empty (supervisor not started yet / test state), tokens render as MISSING (inverted for critical, non-inverted for important) and roll-up renders as `ENV:0/3`.
    - Error safety: if `hw_state.snapshot()` raises (shouldn't, but defensive), the `try/except` surrounding `_render` already catches at `_display_loop` — no new exception handling required inside this change.
  </behavior>
  <action>
Edit `src/shitbox/display/oled.py`:

1. At the top imports, add:
```python
from shitbox.hardware import state as hw_state
```

2. In `_render()`, locate the block at approximately lines 145-149 (the existing `IMU | ENV` line at y=32). Replace that entire block with:

```python
# Line 3: Hardware rollup — critical tokens invert when MISSING (Phase 21, HW-02)
snap = hw_state.snapshot()

def _is_present(role: str) -> bool:
    st = snap.get(role)
    return st is not None and st.state == hw_state.DeviceState.PRESENT

# Fixed 3-token grid for critical + important
for role, glyph, x in (
    ("imu", "IMU", 0),
    ("camera_front", "CAM", 32),
    ("power", "PWR", 64),
):
    missing = not _is_present(role)
    # Critical tier (imu, camera_front) inverts when MISSING; important (power) never inverts.
    invert = missing and role in ("imu", "camera_front")
    self._draw_text(x, 32, glyph, inverted=invert)

# Right-side rollup for best_effort env sensors
be_roles = ("environment", "magnetometer", "light")
be_present = sum(1 for r in be_roles if _is_present(r))
self._draw_text(96, 32, f"ENV:{be_present}/{len(be_roles)}")
```

Do not alter line 1, 2, 4 rendering. Do not add a Lock (GIL-atomic per Plan 01). Do not change `_draw_text`'s signature.

Create `tests/hardware/test_oled_hardware_line.py`:

Mock the Adafruit SSD1306 display and PIL dependencies the way `oled.py` initialises them inside `start()` — the simplest test bypasses `start()` entirely and drives `_render` with a manually-constructed `OLEDDisplayService` whose `_display` is a `MagicMock` and whose underlying draw context records calls. Alternative: make `_draw_text` a spyable method and assert call args.

Required tests:
- `test_oled_line_3_all_present` — seed `hw_state.initialise({"imu":"critical","camera_front":"critical","power":"important","environment":"best_effort","magnetometer":"best_effort","light":"best_effort"})`; `report_present` on all 6; render; assert `_draw_text` called with `(0, 32, "IMU", inverted=False)`, `(32, 32, "CAM", inverted=False)`, `(64, 32, "PWR", inverted=False)`, `(96, 32, "ENV:3/3")`.
- `test_oled_line_3_imu_missing_inverts` — same fixture, leave imu MISSING; assert IMU drawn with `inverted=True`.
- `test_oled_line_3_camera_front_missing_inverts` — camera_front missing → CAM drawn with `inverted=True`.
- `test_oled_line_3_power_missing_does_not_invert` — power MISSING but still `inverted=False` (UI-SPEC: important tier does not invert on OLED).
- `test_oled_line_3_env_rollup_partial` — environment present, magnetometer and light missing → rollup text `"ENV:1/3"`.
- `test_oled_line_3_empty_snapshot` — `clear_state()` only (no initialise); all critical tokens render inverted, rollup renders `"ENV:0/3"`.

Use the autouse `_clear_hw_state` fixture from `tests/hardware/conftest.py` (Plan 01).

The test harness can construct an `OLEDDisplayService` with a minimal config, bypass `start()`, set `self._draw_text = MagicMock()` or equivalent, and call `_render()` directly. Document this in a test helper fixture if it improves readability.

Ruff line length 100. Do not introduce PIL as a test dep if unavailable — mock it.
  </action>
  <verify>
    <automated>pytest tests/hardware/test_oled_hardware_line.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "from shitbox.hardware import state as hw_state" src/shitbox/display/oled.py`
    - `grep -q "ENV:{be_present}/{len(be_roles)}" src/shitbox/display/oled.py`
    - `grep -q "role in (\"imu\", \"camera_front\")" src/shitbox/display/oled.py` (critical-only inversion rule)
    - `! grep -q "IMU | ENV" src/shitbox/display/oled.py` (old line 3 gone)
    - `pytest tests/hardware/test_oled_hardware_line.py -x -q` exits 0 (all 6 tests)
    - `pytest tests/hardware/test_oled_hardware_line.py::test_oled_line_3_imu_missing_inverts -x -q` exits 0
    - `pytest tests/hardware/test_oled_hardware_line.py::test_oled_line_3_empty_snapshot -x -q` exits 0 (HW-02: snapshot empty → still renders safely)
    - `ruff check src/shitbox/display/oled.py tests/hardware/test_oled_hardware_line.py` exits 0
  </acceptance_criteria>
  <done>
    OLED line 3 reads HardwareState, renders per UI-SPEC final prescribed layout, critical tokens invert on MISSING, important does not, rollup shows `ENV:N/3`. 6 render tests pass. No regression on the other OLED lines (manual check — on-Pi verification is in Plan 05 smoke test).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: SSE /sse/slow hardware field + test</name>
  <files>src/shitbox/dashboard/sse.py, tests/hardware/test_sse_hardware.py</files>
  <read_first>
    - src/shitbox/dashboard/sse.py (full file — especially the `/sse/slow` generator at lines 124-157 and the yield block)
    - tests/test_dashboard.py (full file — the existing SSE test drive pattern; per STATE.md Plan 13-03 note, SSE tests call the async generator directly via `asyncio.run()` rather than using Starlette TestClient)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md §Dashboard SSE payload shape (lines 194-209) — this is the contract
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §sse.py (lines 585-647)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md §Code Examples (SSE hardware payload, lines 808-832)
  </read_first>
  <behavior>
    - The `/sse/slow` async generator yields a dict whose `data` JSON string includes a new `hardware` field: a list with one entry per device in `hw_state.snapshot()`.
    - Each hardware entry: `role`, `label` (from copy table), `tier`, `state` (lower-case string), `last_seen` (unix seconds or None if 0), `since_ms` (int milliseconds since `last_seen`, or None if never seen).
    - `label` is derived via an internal lookup dict defined in `sse.py` (matching UI-SPEC copy table verbatim). If a role isn't in the lookup, fall back to `role.replace("_", " ").title()`.
    - Field order and the rest of the existing `/sse/slow` payload are unchanged; this is additive.
    - Snapshot emptiness is handled: an empty snapshot yields `"hardware": []` (no exception).
  </behavior>
  <action>
Edit `src/shitbox/dashboard/sse.py`:

1. Add to the top imports (if not present):
```python
import time
from shitbox.hardware import state as hw_state
```

2. Near the top of the module (module-level), add the label lookup (keeps the generator clean):

```python
_HARDWARE_LABELS = {
    "imu": "IMU",
    "camera_front": "Front Cam",
    "power": "Power",
    "gps": "GPS",
    "environment": "Environment",
    "magnetometer": "Magnetometer",
    "light": "Ambient Light",
    "oled": "OLED",
    "temp_exterior": "Exterior Probe",
    "temp_engine_bay": "Engine Bay Probe",
    "camera_cabin": "Cabin Cam",
    "audio_mic": "USB Mic",
    "button": "Button",
    "display_hdmi": "HDMI",
}


def _hardware_label(role: str) -> str:
    return _HARDWARE_LABELS.get(role, role.replace("_", " ").title())


def _hardware_payload() -> list[dict]:
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

3. Inside the `/sse/slow` generator `yield` dict (around lines 132-150), extend the inline `json.dumps({...})` dict with the new field:

```python
"hardware": _hardware_payload(),
```

Place it after the existing fields (end of dict), before the closing brace. The `default=str` argument on `json.dumps` handles any str-coercible edges; all fields here are already JSON-serialisable.

Do NOT add a new SSE route. Do NOT touch the `/sse/fast` stream. Do NOT introduce `push_event` for hardware state (Research A10 — hardware is slow-changing context, not an event).

Create `tests/hardware/test_sse_hardware.py`:

Mirror the existing `tests/test_dashboard.py` pattern for SSE tests — drive the async generator directly via `asyncio.run()` and capture the first yielded payload rather than going through Starlette's TestClient (per STATE.md Plan 13-03 decision).

If the existing `/sse/slow` test helper is importable, reuse it. Otherwise, write a minimal helper:

```python
import asyncio
import json
from shitbox.dashboard import sse

async def _first_slow_payload():
    # Build a minimal Request mock or use whatever the test_dashboard.py pattern provides.
    # Drive the async generator one step, parse the data field, return the dict.
    ...
```

Required tests:
- `test_sse_slow_includes_hardware_field` — seed hw_state with imu present, power missing, environment present; call _first_slow_payload; assert `payload["hardware"]` is a list of length 3; assert the imu entry has `state=="present"`.
- `test_sse_slow_hardware_labels` — seed all 14 roles; assert every entry's `label` matches the copy table (spot-check 5: imu→"IMU", camera_front→"Front Cam", temp_exterior→"Exterior Probe", audio_mic→"USB Mic", display_hdmi→"HDMI").
- `test_sse_slow_hardware_last_seen_and_since_ms` — a device never seen (`last_seen=0.0`) → entry has `last_seen is None and since_ms is None`. A device seen recently → `last_seen > 0` and `since_ms >= 0`.
- `test_sse_slow_hardware_empty_snapshot` — `clear_state()` only; payload `hardware == []` (no error, empty list).
- `test_sse_slow_hardware_unknown_role_fallback_label` — state has role `"new_widget"` not in the label table; assert label == `"New Widget"` (the fallback).
- `test_sse_slow_other_fields_unchanged` — assert the existing fields (ts, lat, lng, fix_mode, sats, hdop, imu_temp, soc_temp, sync_connected, sync_backlog, event_count, active_driver, recording_active) all still appear in the payload (regression guard).

Ruff line length 100. Use the autouse `_clear_hw_state` fixture.
  </action>
  <verify>
    <automated>pytest tests/hardware/test_sse_hardware.py tests/test_dashboard.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "_HARDWARE_LABELS" src/shitbox/dashboard/sse.py`
    - `grep -q "def _hardware_payload" src/shitbox/dashboard/sse.py`
    - `grep -q "\"hardware\": _hardware_payload()" src/shitbox/dashboard/sse.py`
    - `grep -q "\"imu\": \"IMU\"" src/shitbox/dashboard/sse.py`
    - `grep -q "\"camera_front\": \"Front Cam\"" src/shitbox/dashboard/sse.py`
    - `grep -q "\"audio_mic\": \"USB Mic\"" src/shitbox/dashboard/sse.py`
    - `pytest tests/hardware/test_sse_hardware.py -x -q` exits 0
    - `pytest tests/test_dashboard.py -x -q` exits 0 (existing dashboard SSE tests still pass — regression guard)
    - `ruff check src/shitbox/dashboard/sse.py` exits 0
  </acceptance_criteria>
  <done>
    `/sse/slow` emits a `hardware` array per UI-SPEC payload shape with every one of the 14 role labels wired. Empty-snapshot path safe. Existing SSE test suite green. 6 new tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Dashboard HARDWARE panel HTML</name>
  <files>src/shitbox/dashboard/static/index.html</files>
  <read_first>
    - src/shitbox/dashboard/static/index.html (full file — existing Alpine component structure, `.card` / `.badge` CSS classes at lines 14-17 per PATTERNS.md, slow-payload consumer shape)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md §Component Inventory / Dashboard hardware panel (lines 132-166) and §Copywriting (banner + state text + best_effort rollup copy)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-UI-SPEC.md §Color (tier colour mapping and 60/30/10 discipline)
    - .planning/phases/21-hardware-inventory-and-graceful-degradation/21-PATTERNS.md §index.html (lines 649-667)
  </read_first>
  <behavior>
    - A new card titled `HARDWARE` appears on the kiosk layout. Exact grid slot: planner-discretion per UI-SPEC, but prefer the bottom-left main grid adjacent to the event ticker (must not displace any existing critical telemetry card).
    - Above the row list, a red banner `CRITICAL: <ROLE> OFFLINE` shows when ANY critical-tier row has state `missing`. Banner hides when no critical is missing.
    - Rows render from the `hardware` array on the slow payload. Sort order: critical first, then important, then best_effort; within each tier alphabetical by role.
    - Row columns left to right: state glyph (● green PRESENT / ◐ amber DEGRADED / ○ grey MISSING), role label, tier badge (pill with `.badge` class + tier colour), state text (PRESENT / RECOVERING / OFFLINE), since-last-seen (`3s` / `2m` / `1h` / `—`).
    - Below the row list, a single-line summary: `{N} best_effort present / {M} declared` (grey, 13px).
    - Empty manifest (`hardware` array empty) shows a single row: `No hardware manifest — check config.yaml` in amber.
    - No interactive controls. No retry buttons.
  </behavior>
  <action>
Edit `src/shitbox/dashboard/static/index.html`:

1. Locate the existing Alpine component's `x-data` declaration. Add a `hardware: []` initial property alongside the other slow-stream fields. Add computed helpers either inline or as Alpine methods:

- `criticalMissing()` — returns a comma-joined, uppercased list of `row.label` for every row where `tier === 'critical' && state === 'missing'`. Returns `''` if none.
- `sortedHardware()` — returns `this.hardware.slice().sort((a,b) => tierOrder(a.tier) - tierOrder(b.tier) || a.role.localeCompare(b.role))` where `tierOrder({'critical':0,'important':1,'best_effort':2})`.
- `beRollup()` — `{present: N, total: M}` where both filter `row.tier === 'best_effort'`.
- `stateText(state)` — `{present:'PRESENT', degraded:'RECOVERING', missing:'OFFLINE'}[state] || state.toUpperCase()`.
- `stateGlyph(state)` — `{present:'●', degraded:'◐', missing:'○'}[state] || '?'`.
- `sinceText(ms)` — if `ms == null` → `'—'`; `<60000` → `${Math.floor(ms/1000)}s`; `<3600000` → `${Math.floor(ms/60000)}m`; else → `${Math.floor(ms/3600000)}h`.

2. Inside the slow-stream EventSource handler, copy `data.hardware` into `this.hardware` each tick (additive to the existing assignments that already copy `data.ts`, `data.lat`, etc.).

3. Add the new card HTML block near the existing card cluster:

```html
<div class="card hw-panel">
  <div class="card-label">HARDWARE</div>
  <div x-show="criticalMissing()" class="hw-banner"
       x-text="'CRITICAL: ' + criticalMissing() + ' OFFLINE'"></div>
  <template x-for="row in sortedHardware()" :key="row.role">
    <div class="hw-row" :class="'hw-' + row.state + ' hw-tier-' + row.tier">
      <span class="hw-glyph" x-text="stateGlyph(row.state)"></span>
      <span class="hw-label" x-text="row.label"></span>
      <span class="badge" :class="'badge-' + row.tier" x-text="row.tier"></span>
      <span class="hw-state" x-text="stateText(row.state)"></span>
      <span class="hw-since" x-text="sinceText(row.since_ms)"></span>
    </div>
  </template>
  <div x-show="hardware.length === 0" class="hw-empty">
    No hardware manifest — check config.yaml
  </div>
  <div x-show="hardware.length > 0" class="hw-rollup"
       x-text="`${beRollup().present} best_effort present / ${beRollup().total} declared`">
  </div>
</div>
```

4. Extend the existing `<style>` block with panel CSS. Use ONLY the existing design tokens from UI-SPEC §Color; introduce no new palette entries:

```css
.hw-panel { /* follows existing .card sizing */ }
.hw-banner { background: #da3633; color: #fff; font-weight: 600; padding: 8px 12px; border-radius: 4px; margin-bottom: 8px; }
.hw-row { display: grid; grid-template-columns: 24px 1fr auto auto 48px; gap: 12px; align-items: center; padding: 4px 0; }
.hw-glyph { font-size: 18px; }
.hw-label { font-size: 18px; font-weight: 600; color: #e6edf3; }
.hw-state { font-size: 18px; font-weight: 400; }
.hw-since { font-size: 13px; color: #8b949e; text-align: right; }
.hw-missing .hw-glyph { color: #8b949e; }
.hw-missing .hw-state { color: #da3633; }
.hw-degraded .hw-glyph { color: #d29922; }
.hw-degraded .hw-state { color: #f85149; }
.hw-present .hw-glyph { color: #238636; }
.badge-critical { background: #da3633; color: #fff; }
.badge-important { background: #d29922; color: #000; }
.badge-best_effort { background: #8b949e; color: #fff; }
.hw-empty { color: #d29922; font-size: 15px; }
.hw-rollup { color: #8b949e; font-size: 13px; margin-top: 8px; }
```

UK spelling in all code comments (global rule). No emojis anywhere.

This is a visual, manual-verified change. It has no unit test beyond the SSE payload test (Task 2) — the browser render is verified in the Plan 05 smoke test on-Pi. Keep the CSS embedded in `<style>` (single-file SPA pattern per CLAUDE.md §Website stack).
  </action>
  <verify>
    <automated>bash -c 'grep -q "HARDWARE" src/shitbox/dashboard/static/index.html && grep -q "hw-panel" src/shitbox/dashboard/static/index.html && grep -q "criticalMissing" src/shitbox/dashboard/static/index.html && grep -q "CRITICAL: " src/shitbox/dashboard/static/index.html && grep -q "best_effort present" src/shitbox/dashboard/static/index.html'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "HARDWARE" src/shitbox/dashboard/static/index.html`
    - `grep -q "hw-panel" src/shitbox/dashboard/static/index.html`
    - `grep -q "hw-banner" src/shitbox/dashboard/static/index.html`
    - `grep -q "hw-row" src/shitbox/dashboard/static/index.html`
    - `grep -q "criticalMissing" src/shitbox/dashboard/static/index.html`
    - `grep -q "stateText" src/shitbox/dashboard/static/index.html`
    - `grep -q "best_effort present" src/shitbox/dashboard/static/index.html`
    - `grep -q "check config.yaml" src/shitbox/dashboard/static/index.html`
    - `grep -q "badge-critical" src/shitbox/dashboard/static/index.html`
    - `grep -q "badge-important" src/shitbox/dashboard/static/index.html`
    - `grep -q "badge-best_effort" src/shitbox/dashboard/static/index.html`
    - `grep -q "#da3633" src/shitbox/dashboard/static/index.html` (critical red from UI-SPEC)
    - `grep -q "#d29922" src/shitbox/dashboard/static/index.html` (important amber)
    - `grep -q "#238636" src/shitbox/dashboard/static/index.html` (present green)
    - No JavaScript or template syntax errors on a quick visual inspection of the file (the Plan 05 on-Pi smoke test is the final functional gate)
  </acceptance_criteria>
  <done>
    HARDWARE panel rendered per UI-SPEC: card + banner + sorted rows + rollup + empty-state message. Uses only inherited GitHub-dark tokens (no new palette). Panel reads from `hardware[]` on the slow payload — re-renders at 1 Hz.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| `hw_state.snapshot()` → `/sse/slow` JSON | In-process read; serialised via `json.dumps`. |
| `/sse/slow` → browser (Chromium kiosk, Pi-local) | Existing 0.0.0.0:8080 bind; no new port, no new route. |
| `index.html` templating | Alpine bindings on server-supplied data; no `x-html`, no `eval`, no innerHTML writes. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-04-01 | Injection (XSS) | Hardware label / role rendered in panel | mitigate | Alpine `x-text` (not `x-html`) is used for all dynamic content → text-only escape. Role values originate from config.yaml, not user input. |
| T-21-04-02 | Information Disclosure | Dashboard exposing device paths and addresses | accept | Addresses / paths already in config.yaml; dashboard is Pi-local only (D-10, D-11). No remote exposure. |
| T-21-04-03 | Denial of Service | Empty snapshot crashing OLED render | mitigate | Test `test_oled_line_3_empty_snapshot` enforces graceful empty-state render. Outer `_display_loop` try/except remains as a second line of defence. |
| T-21-04-04 | Denial of Service | Empty snapshot crashing SSE generator | mitigate | `_hardware_payload()` returns `[]` on empty snapshot — covered by `test_sse_slow_hardware_empty_snapshot`. |
| T-21-04-05 | Tampering | A client-side override of hardware state | N/A | Dashboard is read-only; no POST to alter state. |

**ASVS L1:** V4 Access Control not applicable (Pi-local, D-10). V5 Input Validation partial — SSE payload fields are typed and serialised with `json.dumps`. No other categories apply.
</threat_model>

<verification>
End of plan checks:

- `pytest tests/hardware/test_oled_hardware_line.py tests/hardware/test_sse_hardware.py tests/test_dashboard.py -x -q` — all new + existing pass.
- `pytest` — full suite passes (SSE changes additive; OLED line 3 rewrite covered by dedicated tests).
- `python -c "from shitbox.dashboard.sse import _hardware_label; print(_hardware_label('imu'), _hardware_label('temp_exterior'))"` prints `IMU Exterior Probe`.
- `ruff check src/shitbox/display/oled.py src/shitbox/dashboard/sse.py tests/hardware` exits 0.
- Manual browser verification is deferred to Plan 05's smoke test on-Pi.
</verification>

<success_criteria>
- HW-02 visual path complete: OLED line 3 and dashboard HARDWARE panel both read `hw_state.snapshot()` and re-render at ≤1 Hz.
- HW-03 visual cadence met: critical-tier MISSING drives inverted OLED tokens + red dashboard banner; important tier gets an orange/amber badge but no banner; best_effort rolls up into a count (OLED) plus per-row display (dashboard).
- UI-SPEC copy observed verbatim: PRESENT / RECOVERING / OFFLINE state text, banner template `CRITICAL: <ROLE> OFFLINE`, empty-state `No hardware manifest — check config.yaml`.
- No new SSE routes, no new JS deps, no new CSS palette.
</success_criteria>

<output>
After completion, create `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-04-SUMMARY.md` covering:
- Files modified (three surfaces)
- Panel placement decision (grid slot chosen for the HARDWARE card)
- Test counts (OLED / SSE)
- Any CSS or copy ambiguities resolved in implementation
- Confirmation that existing SSE dashboard tests still pass
</output>
