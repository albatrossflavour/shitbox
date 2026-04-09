---
status: partial
phase: 13-driver-tracking
source: [13-VERIFICATION.md]
started: 2026-04-09T14:30:00Z
updated: 2026-04-09T14:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Driver modal renders roster dropdown correctly
expected: Modal opens in browser, dropdown shows -- No driver --, Tony, Smithy, Nav (or configured roster)
result: [pending]

### 2. SSE live-updates top-bar within ~1 second of driver switch
expected: Switching driver via dropdown updates the top-bar Driver label within ~1 second (SSE push)
result: [pending]

### 3. Captured event JSON contains driver_name when driver is active
expected: cat captures/<date>/<event>.json | jq .driver_name returns the active driver name (not null)
result: [pending]

### 4. driver-stats.json written after sync cycle
expected: captures/driver-stats.json exists and contains {active_driver, drivers} after a sync cycle completes
result: [pending]

### 5. Roster enforcement at runtime
expected: curl -X POST http://localhost:8000/api/driver -H 'Content-Type: application/json' -d '{"name":"Mallory"}' returns 422
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
