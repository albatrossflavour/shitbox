---
status: partial
phase: 26-event-video-title-cards
source: [26-VERIFICATION.md]
started: 2026-04-23T12:00:00Z
updated: 2026-04-23T12:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Manual capture lands poster alongside MP4; events.json carries poster_url
expected: The per-day captures dir contains both `<base>.mp4` and `<base>_poster.png`; events.json contains `poster_url: /captures/<date>/<base>_poster.png` for that event
result: [pending]

### 2. Playback sequence intro → 3s slate → footage with full slate composition
expected: The slate appears for ~3s between intro and live footage showing place name (or whimsy), date/time, coords, event badge (except on manual), and driver credit
result: [pending]

### 3. No-GPS capture uses whimsy line and omits coord row
expected: Slate hero shows one of `Here be dragons / GPS off having a lie down / Somewhere between A and B / The map ends here / Lost, but enthusiastic`; no coord row is rendered
result: [pending]

### 4. Manual/button capture: slate has no badge, driver credit present
expected: No coloured badge in the bottom-left; driver credit line (`Driver: Tony`) visible
result: [pending]

### 5. ROLLOVER event renders badge with diagonal hazard stripes
expected: Bottom-left badge shows the `Rollover` label on a red body with ~30% alpha black diagonal stripes at 45°
result: [pending]

### 6. title_card.enabled=false: no slate in MP4, no poster_url in events.json
expected: Concat.txt omits slate.ts; MP4 has no slate; events.json entry has no `poster_url`
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
