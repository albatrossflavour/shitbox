---
phase: 21
plan: 04
subsystem: hardware-ui
tags: [oled, sse, dashboard, hardware-inventory, graceful-degradation, tdd, hw-02, hw-03]
dependency_graph:
  requires:
    - src/shitbox/hardware/state.py (Plan 01 — hw_state.snapshot())
    - src/shitbox/hardware/supervisor.py (Plan 02 — initialises state)
  provides:
    - src/shitbox/display/oled.py (line 3 hardware rollup)
    - src/shitbox/dashboard/sse.py (hardware field on /sse/slow)
    - src/shitbox/dashboard/static/index.html (HARDWARE panel)
  affects:
    - Plan 05 (engine wiring + on-Pi smoke test validates these three surfaces)
tech_stack:
  added: []
  patterns:
    - hw_state.snapshot() read path (GIL-atomic, no lock — same as gps_state.py)
    - Alpine x-for + computed helpers (sortedHardware, criticalMissing, beRollup)
    - TDD (RED tests committed first, GREEN implementation second, all three tasks)
    - Live uvicorn server pattern for SSE tests (Plan 13-03 precedent)
key_files:
  created:
    - tests/hardware/test_oled_hardware_line.py
    - tests/hardware/test_sse_hardware.py
  modified:
    - src/shitbox/display/oled.py
    - src/shitbox/dashboard/sse.py
    - src/shitbox/dashboard/static/index.html
decisions:
  - "HARDWARE panel placed between the main grid and the footer strip — the kiosk layout stacks vertically (header 100px, main flex-1, hardware panel max-height 200px, footer 130px); this avoids displacing any existing critical telemetry card and keeps the panel visible without scrolling on 1024x600"
  - "oled_service fixture bypasses start() entirely and wires mock _draw + _font directly — cleaner than patching PIL at import time and avoids the Adafruit driver touching I2C in test"
  - "SSE tests use the live-uvicorn _start_live_server/_read_sse_lines helpers from test_dashboard.py verbatim — consistent with Plan 13-03 decision; starlette TestClient cannot consume infinite async generators"
  - "Task 3 (HTML panel) has no pytest unit tests per plan intent; verification is grep-based acceptance criteria (all 14 pass); functional browser render deferred to Plan 05 on-Pi smoke test"
metrics:
  duration: "18m"
  completed_date: "2026-04-21"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 3
---

# Phase 21 Plan 04: OLED, SSE, Dashboard Summary

**One-liner:** HardwareState wired to all three Pi-local UI surfaces — OLED line 3 token grid with critical inversion, /sse/slow hardware array with 14-role label table, and kiosk HARDWARE panel with red critical banner, tier-sorted rows, and best_effort rollup.

## What Was Built

### Task 1: OLED line 3 hardware rollup

`src/shitbox/display/oled.py` line 3 (`y=32`) replaced: the old `imu_ok` / `env_ok` engine status dict lookup is gone. The new block calls `hw_state.snapshot()` and renders:

- `x=0` `IMU` — inverted when `imu` is MISSING (critical tier)
- `x=32` `CAM` — inverted when `camera_front` is MISSING (critical tier)
- `x=64` `PWR` — never inverted even when MISSING (important tier, per UI-SPEC)
- `x=96` `ENV:N/3` — rollup count for environment/magnetometer/light

Empty snapshot (supervisor not yet started) renders safely: critical tokens inverted, `ENV:0/3`.

### Task 2: SSE /sse/slow hardware field

`src/shitbox/dashboard/sse.py` gains:

- `_HARDWARE_LABELS` dict — all 14 roles from UI-SPEC copy table
- `_hardware_label(role)` — falls back to `role.replace("_", " ").title()` for unknown roles
- `_hardware_payload()` — serialises `hw_state.snapshot()` to `list[dict]` with `role`, `label`, `tier`, `state`, `last_seen` (null when 0.0), `since_ms` (null when never seen)
- `"hardware": _hardware_payload()` appended to the existing `/sse/slow` yield dict

No new SSE route. No `push_event` for hardware (slow-changing context, not an event stream).

### Task 3: Dashboard HARDWARE panel

`src/shitbox/dashboard/static/index.html` gains:

- 19 CSS rules covering panel layout, banner, row grid, glyph/label/state/since columns, tier badge colours, empty-state and rollup styles — all using inherited GitHub-dark tokens, no new palette entries
- `hardware: []` in Alpine `x-data`
- `this.hardware = d.hardware || []` in `openSlow()` EventSource handler
- Six computed helpers: `criticalMissing()`, `sortedHardware()`, `beRollup()`, `stateText()`, `stateGlyph()`, `sinceText()`
- HARDWARE card between main grid and footer: critical red banner (auto-hides when no critical MISSING), per-device rows sorted critical → important → best_effort then alphabetical by role, best_effort rollup line, amber empty-state message when manifest not loaded

## Panel Placement Decision

The HARDWARE card is positioned as a flex item between `<main>` and `<footer>` in the vertical stack. It uses `flex-shrink: 0` and `max-height: 200px` with `overflow-y: auto`. This sits cleanly between the main telemetry grid (flex-1) and the existing event ticker footer (h=130px) without displacing any existing card. On the 1024x600 kiosk, this leaves ~170px for the main grid — slightly reduced but acceptable given the crew needs hardware visibility.

## Test Counts

| Module | Tests | Notes |
|--------|-------|-------|
| test_oled_hardware_line.py | 6 | all-present, imu-missing, cam-missing, power-no-invert, rollup-partial, empty-snapshot |
| test_sse_hardware.py | 6 | includes-field, labels-spot-check, last_seen/since_ms, empty-snapshot, fallback-label, existing-fields-unchanged |
| test_dashboard.py (regression) | 16 | all pass unchanged |
| **Total new** | **12** | |

Full suite after plan: 311 passed, 1 skipped (pre-existing GPIO on macOS), 1 pre-existing uvicorn warning.

## CSS and Copy Ambiguities Resolved

- **`badge-best_effort` class name:** The CSS class uses an underscore (`badge-best_effort`) to match the `tier` value from `hw_state.snapshot()`. Alpine binds `:class="'badge-' + row.tier"` so the CSS must match the API value exactly. The hyphen variant (`badge-best-effort`) would require a separate mapping.
- **`stateGlyph` for `◐` (DEGRADED):** The plan spec uses `◐` (U+25D0, circle with left half black) for the degraded state. Implemented as specified.
- **Banner copy:** `CRITICAL: <ROLE> OFFLINE` where role is uppercased via `label.toUpperCase()` (the label is already human-readable e.g. "Front Cam" → "FRONT CAM"). This matches UI-SPEC intent: the label, not the raw role, appears in the banner.

## Deviations from Plan

### Auto-fixed Issues

None. All three tasks executed exactly as specified in the plan. The OLED implementation follows the plan's action block verbatim (fixed x=0/32/64/96 positions, role-in-tuple inversion guard). The SSE implementation matches the pattern block exactly. The HTML panel matches the plan's code snippet with minor additions (inline `style` on the card wrapper for layout fit).

### Minor Implementation Note

The plan's PATTERNS.md shows the OLED token loop using a dynamic `x += len(glyph) * 8 + 8` stride, but the PLAN action block specifies fixed positions `x=0`, `x=32`, `x=64`. Fixed positions were implemented per the PLAN (authoritative) since they match the UI-SPEC `y=32 IMU● CAM● PWR●    ENV:2/3` grid.

## Known Stubs

None. All three surfaces read live `hw_state.snapshot()` data. The `hardware: []` initial Alpine value is intentional — it populates on the first `/sse/slow` tick (within 1s of dashboard load). No hardcoded placeholder values flow to UI rendering.

## Threat Flags

No new threat flags. The plan's threat model (T-21-04-01 through T-21-04-05) is fully addressed:

- T-21-04-01 (XSS): All dynamic content uses Alpine `x-text` (not `x-html`) — text-only escape confirmed by inspection.
- T-21-04-03 (DoS empty OLED): `test_oled_line_3_empty_snapshot` enforces graceful render; outer `_display_loop` try/except remains second line of defence.
- T-21-04-04 (DoS empty SSE): `test_sse_slow_hardware_empty_snapshot` confirms `[]` returned safely.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `0304bd3` | test | RED: failing tests for OLED line 3 hardware rollup (6 tests) |
| `4fd62ea` | feat | GREEN: OLED line 3 hardware rollup implementation |
| `2ccde16` | test | RED: failing tests for /sse/slow hardware field (6 tests) |
| `5f743ed` | feat | GREEN: SSE /sse/slow hardware field + label table |
| `d925d07` | feat | Dashboard HARDWARE panel HTML + CSS + Alpine helpers |

## Self-Check: PASSED

- `src/shitbox/display/oled.py` — FOUND, contains `from shitbox.hardware import state as hw_state`
- `src/shitbox/dashboard/sse.py` — FOUND, contains `_HARDWARE_LABELS`, `_hardware_payload`, `"hardware": _hardware_payload()`
- `src/shitbox/dashboard/static/index.html` — FOUND, contains `HARDWARE`, `hw-panel`, `criticalMissing`, `badge-critical`
- `tests/hardware/test_oled_hardware_line.py` — FOUND (6 tests)
- `tests/hardware/test_sse_hardware.py` — FOUND (6 tests)
- Commits: 0304bd3, 4fd62ea, 2ccde16, 5f743ed, d925d07 — all present in git log
