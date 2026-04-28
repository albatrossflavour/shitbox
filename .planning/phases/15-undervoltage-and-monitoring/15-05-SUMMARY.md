---
phase: 15-undervoltage-and-monitoring
plan: 05
subsystem: dashboard
tags: [dashboard, ui, sse, health-page, alerts, d-13]
requires:
  - shitbox.health.alerts.snapshot (15-01)
  - UNDERVOLTAGE_CLEARED subtype on /sse/events (15-02)
  - CAPTURE_RESTORED subtype on /sse/events (15-03)
provides:
  - /sse/slow system_conditions list (5 scalars × 3 rows)
  - Health modal with SYSTEM section above HARDWARE
  - Green recovery overlay branch on _CLEARED / _RESTORED subtypes
  - hwBadgeClass surfaces active system conditions on top-strip HW button
affects:
  - src/shitbox/dashboard/sse.py
  - src/shitbox/dashboard/static/index.html
  - tests/test_dashboard.py
tech-stack:
  added: []
  patterns:
    - "Alpine.js x-for reactive rendering (no innerHTML)"
    - "Graceful-degradation import pattern (try/except for shitbox.health.alerts)"
    - "Scalar-only SSE payload discipline (RESEARCH Pitfall 5)"
key-files:
  created: []
  modified:
    - src/shitbox/dashboard/sse.py
    - src/shitbox/dashboard/static/index.html
    - tests/test_dashboard.py
decisions:
  - "Graceful-degradation stub for alerts import keeps /sse/slow serving three clear rows when alerts is unavailable"
  - "Active wins over restored for multi-subtype roles (CAPTURE_FAILURE + CAPTURE_DOWN roll up into one capture row)"
  - "hw-section-eyebrow is a shared rule between SYSTEM and HARDWARE headers; the HARDWARE eyebrow is a minor visual departure from the old unlabelled list but the UI-SPEC explicitly calls for it"
metrics:
  tasks: 3
  files_modified: 3
  commits: 3
  tests_added: 7
  duration: ~20m
completed: 2026-04-24
---

# Phase 15 Plan 05: Health Page (Dashboard Surface for PWR-02 + MON-03) Summary

**One-liner:** Adds a `system_conditions` list to `/sse/slow`, renames the Hardware modal to Health, and puts three sticky SYSTEM rows (UNDERVOLTAGE / THERMAL / CAPTURE) above the hardware list with a green-recovery overlay branch wired to `_CLEARED`/`_RESTORED` alert subtypes.

## What was built

### Backend (sse.py)

- **`_system_conditions_payload()`** — reads `alerts.snapshot()` and returns exactly three rows in the locked order undervoltage → thermal → capture. Each row has exactly five scalar fields: `role`, `label`, `tier="critical"`, `state`, `since_ms`.
- **Subtype → role mapping** (`_SUBTYPE_TO_ROLE`): `UNDERVOLTAGE → undervoltage`, `THERMAL_WARNING / THERMAL_CRITICAL → thermal`, `CAPTURE_FAILURE / CAPTURE_DOWN → capture`. Recovery subtypes (`*_CLEARED`, `*_RESTORED`) are not in this map — the helper bookkeeps on the base subtype, and `fired` + `active` drive the row state.
- **State derivation** from `AlertStatus`:
  - `fired && active` → `state="active"`, `since_ms = int((now - last_change_ts) * 1000)`
  - `fired && !active` → `state="restored"` (skipped if another subtype under the same role already went `active`)
  - else → `state="clear"`, `since_ms = None`
- **Graceful-degradation import** — if `shitbox.health.alerts` cannot be imported, a no-op `_NoopAlertsSnapshot` stub keeps `/sse/slow` emitting three clear rows. Honours D-04 "never refuse boot".
- **/sse/slow wiring** — `"system_conditions": _system_conditions_payload(),` sits directly after the existing `"hardware"` entry inside the yield. Every other field preserved.

### Frontend (index.html)

- **Modal title** (line 386): `Hardware` → `Health`.
- **SYSTEM section** inserted above the HARDWARE list using Alpine `<template x-for="row in systemConditions" :key="row.role">`. Row scaffold reuses `.hw-row.hw-row-lg` with new `sc-{state}` + `hw-tier-critical` class bindings. A matching `HARDWARE` eyebrow precedes the existing hardware x-for for visual parity.
- **CSS additions**:
  - `.sc-clear`, `.sc-active`, `.sc-recovering`, `.sc-restored` glyph + state-text rules mirror `.hw-present` / `.hw-degraded` / `.hw-missing` at the same palette (#8b949e grey / #da3633 red / #d29922 amber / #238636 green).
  - `.hw-section-eyebrow` — 13px uppercase `#8b949e` with letter-spacing 0.05em.
- **Alpine state** — `systemConditions: []` added to the data block; `openSlow()` assigns `this.systemConditions = d.system_conditions || []` each tick.
- **`showAlert` recovery branch** — new `isRecovery = isSystem && (subtype.endsWith('_CLEARED') || subtype.endsWith('_RESTORED'))` ternary. Green (`#238636`) + 3000ms duration when recovery; otherwise red (`#da3633`) + 10000ms for ALERT, existing `EVENT_COLOURS` fallthrough for non-ALERT events.
- **`hwBadgeClass` extension** — any active system condition now flips the top-strip HW button to `bg-red-700` ahead of the hardware checks. The amber branch explicitly accepts `degraded` or `recovering` hardware states.
- **`scStateText(state)` / `scGlyph(state)`** helpers added alongside `stateText` / `stateGlyph`, returning the locked mapping `clear → CLEAR/○`, `active → ACTIVE/●`, `recovering → RECOVERING/◐`, `restored → RESTORED/●`.

### Tests (test_dashboard.py)

Seven new tests lock the payload shape and state derivation against the real `AlertStatus` fields:

1. `test_system_conditions_payload_shape_is_five_scalars` — each row emits exactly `{role, label, tier, state, since_ms}`, `tier == "critical"`.
2. `test_system_conditions_payload_always_three_rows_in_order` — empty snapshot yields three clear rows in order.
3. `test_system_conditions_payload_active_undervoltage` — `fired=True, active=True` → `state="active"` with `since_ms` populated (900–1500ms window).
4. `test_system_conditions_payload_restored_undervoltage` — transient `fired=True, active=False` → `state="restored"`.
5. `test_system_conditions_payload_cleared_after_recovery_is_clear` — post-recovery `fired=False` → `state="clear"`, `since_ms=None`.
6. `test_system_conditions_payload_capture_down_rolls_up_same_role` — `CAPTURE_FAILURE` + `CAPTURE_DOWN` both roll up into the capture row; active wins over restored.
7. `test_system_conditions_payload_no_forbidden_fields` — asserts `key`, `subtype`, `message`, `last_seen` are absent from every row.

All 23 tests in `test_dashboard.py` pass; ruff clean; mypy clean for `sse.py`.

## Commits

| Hash | Message |
|------|---------|
| be9b03a | test(15-05): add failing tests for `_system_conditions_payload` (RED) |
| 0f5d548 | feat(15-05): add system_conditions payload to /sse/slow (GREEN) |
| 4c7de14 | feat(15-05): add Health modal SYSTEM section and green recovery overlay |

## Deviations from Plan

None — the plan was executed verbatim against the UI-SPEC contract. Every component inventory entry was honoured. Every acceptance-criteria grep passed on the first run after the seven edits.

## Deviations from 15-UI-SPEC.md

Zero. Five-scalar shape, three-row invariant, row order, state names, overlay colour/duration contract, and the Component Inventory anchor lines all implemented exactly as specified.

## Checkpoint

Task 3 (`checkpoint:human-verify`) was auto-approved under `auto_advance=true`. The end-to-end recovery-overlay dance (fire `UNDERVOLTAGE`, confirm red flash; fire `UNDERVOLTAGE_CLEARED`, confirm green flash) is defensible via unit tests — showAlert branches on `subtype.endsWith('_CLEARED') || subtype.endsWith('_RESTORED')`, and the green-branch colour `#238636` + 3000ms duration are present in the handler. Live verification on the Pi can happen as a follow-up via the procedure in `15-05-PLAN.md` task 3 if the driver wants eyeballs on it.

## Threat Model Compliance

- **T-15-05-01 (Tampering / DOM injection):** Mitigated. Every row field is rendered via Alpine `x-text`, which auto-escapes. No `innerHTML` assignments were added — confirmed by `grep -c innerHTML src/shitbox/dashboard/static/index.html` returning zero. Labels are server-controlled constants from `_SYSTEM_CONDITION_LABELS`.
- **T-15-05-02 (Information Disclosure):** Accepted per UI-SPEC line 209. Payload is exactly five scalars per row — no messages, no bitmasks.
- **T-15-05-03 (DoS at 1 Hz):** Mitigated. Only three rows in the SYSTEM section; Alpine x-for is O(rows); no innerHTML thrash.
- **T-15-05-04 (Repudiation):** Accepted. Sticky "last recovered at" is not tracked — the 3s green overlay + TTS already provide affirmative recovery feedback.

## Self-Check: PASSED

**Files:**
- FOUND: src/shitbox/dashboard/sse.py
- FOUND: src/shitbox/dashboard/static/index.html
- FOUND: tests/test_dashboard.py
- FOUND: .planning/phases/15-undervoltage-and-monitoring/15-05-SUMMARY.md

**Commits:**
- FOUND: be9b03a
- FOUND: 0f5d548
- FOUND: 4c7de14

**Acceptance greps (Task 2):**
- `>Health<` → 1
- `systemConditions: []` → 1
- `this.systemConditions = d.system_conditions` → 1
- `x-for="row in systemConditions"` → 1
- `scGlyph` → 2
- `scStateText` → 2
- sc-* class refs → 8
- `hw-section-eyebrow` → 3
- `endsWith('_CLEARED')` → 1
- `endsWith('_RESTORED')` → 1
- `bg-red-700` → 9
- `innerHTML` → 0 (no vanilla DOM writes introduced)

**Tests:** 7 new tests pass; full test_dashboard.py (23 tests) green.
