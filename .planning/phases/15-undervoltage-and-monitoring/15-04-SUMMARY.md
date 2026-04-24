---
phase: 15-undervoltage-and-monitoring
plan: 04
type: execute
status: complete
completed: 2026-04-24
requirements: [MON-01, MON-02]
---

# 15-04 — MON-01 + MON-02 Bookkeeping Closure

## What changed

**shitbox repo** — `.planning/REQUIREMENTS.md`:
- MON-01 flipped `[ ]` → `[x]` (HLTH-01 metrics already flowing since Phase 11-14)
- MON-02 flipped `[ ]` → `[x]` (replaced by direct Prometheus scrape in Phase 14)

**home-ops repo** — `kubernetes/apps/observability/`:
- Deleted `shitbox-mqtt-exporter/` directory (4 files: `ks.yaml`, `app/externalsecret.yaml`, `app/helmrelease.yaml`, `app/kustomization.yaml`)
- Removed the commented `#- ./shitbox-mqtt-exporter/ks.yaml` line from parent `kustomization.yaml`

## Deviation from plan

Plan expected 3 deletions; actual was 4. Extra file was `shitbox-mqtt-exporter/app/kustomization.yaml` — a nested Kustomize file inside the dead directory. All four files were dead weight; deletion is correct.

## Checkpoint

Cross-repo diff presented to user before commit; user approved.

## Commits

- shitbox: `6439200` docs(15): close MON-01 and MON-02 in requirements
- home-ops: `0b3dadd1` chore(observability): remove dead shitbox-mqtt-exporter (pushed to `main`)

## Flux impact

The Kustomization was already commented out since Phase 14 — Flux dropped the live objects weeks ago. This push only removes the dead asset files. No reconciliation drama expected.

## Downstream

None. MON-01 / MON-02 fully closed. MON-03 remains open until 15-05 lands the Health page.
