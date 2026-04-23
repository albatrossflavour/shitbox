---
phase: 26-event-video-title-cards
plan: "01"
subsystem: events
tags: [labels, colours, event-types, lookup-table, tdd]
dependency_graph:
  requires: []
  provides: [shitbox.events.labels]
  affects: [capture/title_card.py, events/storage.py]
tech_stack:
  added: []
  patterns: [pure-data-module, parametrised-pytest, typed-dict]
key_files:
  created:
    - src/shitbox/events/labels.py
    - tests/test_events_labels.py
  modified: []
decisions:
  - "labels.py placed in events/ (not utils/ or storage/) to pair naturally with detector.EventType and avoid circular imports"
  - "MANUAL_CAPTURE is the single Python enum key; MANUAL/BUTTON website tokens are feed-layer concerns handled elsewhere (D-11)"
  - "No Pillow, hardware, or IO imports — module stays safe for TTS and website reuse paths"
  - "colour_for fallback returns #6e7681 (GitHub dim grey) for any unknown EventType"
  - "label_for fallback title-cases enum .value with underscores converted to spaces"
metrics:
  duration_minutes: 1
  completed_date: "2026-04-23"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
---

# Phase 26 Plan 01: Canonical Event Label and Colour Lookup Summary

One-liner: Pure lookup table mapping every EventType to a human-readable label and badge colour, hardware-free so TTS and website paths can import it without pulling Pillow.

## What Was Built

`src/shitbox/events/labels.py` — a 51-line, dependency-light module containing:

| Export | Purpose |
|--------|---------|
| `EVENT_LABELS` | Dict mapping each of the 7 EventType members to a display string |
| `EVENT_COLOURS` | Dict mapping each EventType to a hex badge colour (matches website palette) |
| `ROLLOVER_STRIPE_COLOUR` | `"#000000"` — stripe colour for the ROLLOVER hazard overlay |
| `label_for(event_type)` | Lookup with title-case fallback on unknown types |
| `colour_for(event_type)` | Lookup with `#6e7681` grey fallback on unknown types |

### Canonical mapping (D-07, D-08)

| EventType | Label | Colour |
|-----------|-------|--------|
| HARD_BRAKE | Hard Brake | #f85149 |
| BIG_CORNER | Big Corner | #d29922 |
| HIGH_G | High G | #da3633 |
| ROUGH_ROAD | Rough Road | #8957e5 |
| MANUAL_CAPTURE | Manual Capture | #238636 |
| BOOT | System Start | #1f6feb |
| ROLLOVER | Rollover | #e74c3c |

`ROLLOVER_STRIPE_COLOUR = "#000000"` (for the hazard-stripe overlay, slate-renderer only).

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED — failing tests | b0d20e2 | PASS |
| GREEN — implementation | a599a04 | PASS |
| REFACTOR | N/A — code is already minimal | skipped (no cleanup required) |

19 tests pass: 7 label assertions (parametrised), 7 colour assertions (parametrised), 2 dict-coverage assertions, 1 constant assertion, 2 fallback assertions.

## Verification

```
pytest tests/test_events_labels.py -x -q    → 19 passed
ruff check src/shitbox/events/labels.py     → All checks passed
mypy src/shitbox/events/labels.py           → Success: no issues found in 1 source file
python -c 'from shitbox.events.labels import label_for; print("ok")'  → ok
grep '^from PIL' src/shitbox/events/labels.py  → 0 matches
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. This is a pure data module; no data source wiring, no placeholder strings.

## Threat Flags

None. No network, IO, subprocess, or new trust boundaries introduced.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| src/shitbox/events/labels.py | FOUND |
| tests/test_events_labels.py | FOUND |
| 26-01-SUMMARY.md | FOUND |
| Commit b0d20e2 (RED) | FOUND |
| Commit a599a04 (GREEN) | FOUND |
