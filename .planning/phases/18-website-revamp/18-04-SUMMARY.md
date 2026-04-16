---
phase: 18-website-revamp
plan: "04"
subsystem: grafana
tags: [grafana, dashboard, prometheus, retroactive]
dependency_graph:
  requires: [18-01]
  provides: [grafana-ambient-light-panel, grafana-ds18b20-probe-series, grafana-logical-grouping]
  affects: [grafana-shitbox-rally-command-dashboard]
tech_stack:
  added: []
  patterns: [Grafana dashboard JSON, Flux reconciliation]
key_files:
  created: []
  modified:
    - (home-ops) kubernetes/apps/observability/grafana/app/dashboards/shitbox-rally-command.json
decisions:
  - Folded into broader NASA/F1 instrument-cluster rewrite instead of the originally planned surgical API patch
  - Dashboard reprovisioned under new UID (shitbox-rally-v2) after the plan-04 API push left a stale DB entry
  - Retroactive summary — work completed Apr 11 2026, summary written 2026-04-16
metrics:
  completed_date: "2026-04-11"
  tasks_completed: 2
  files_changed: 1
---

# Phase 18 Plan 04: Grafana Dashboard API Update

Adds Ambient Light (shitbox_lux) and probe-labelled DS18B20 temperature series to the
shitbox-rally-command dashboard, with stat panels reorganised into logical rows.

## What Was Done

Work was absorbed into a broader dashboard rewrite rather than the originally planned
surgical two-target + one-panel patch. The must_haves from the plan are all satisfied
in the live dashboard JSON at
`home-ops/kubernetes/apps/observability/grafana/app/dashboards/shitbox-rally-command.json`.

### Must-haves check

| Must-have | Evidence |
| --------- | -------- |
| Ambient Light panel showing `shitbox_lux` | Panel title "Ambient Light" at JSON line 3191, Prometheus expr `shitbox_lux` at line 3185 |
| DS18B20 exterior + engine_bay as separate series on Temperatures | Queries `shitbox_temp{probe="exterior"}` and `shitbox_temp{probe="engine_bay"}` at JSON lines 950, 2070, 2077 |
| Stat panels grouped logically | Explicit row layout in commit `40b4495d`: Row 0 instrument cluster, Row 1 system status, Row 2 map + timeseries, Row 3 thermal, Row 4 vehicle dynamics, Row 5 support systems |

### Home-ops commits (relevant to this plan)

- `40b4495d feat(shitbox): full Grafana dashboard rewrite — NASA/F1 instrument cluster layout`
  — the layout regrouping, DS18B20 probe series, shitbox_lux ambient-light panel all land here.
- `d4683123 feat(shitbox): reprovision dashboard as shitbox-rally-v2 to avoid DB conflict`
  — the plan-04 API push from Task 2 left a stale DB entry; reprovisioning under a new UID
  resolved it. Website iframe + link updated to match.
- `e5bb8389 Dashboard` — later tweak, non-structural.

## Deviations from Plan

- **Scope widened.** The plan called for adding one panel and two targets. The actual work
  replaced the whole dashboard layout. Everything the plan asked for is present; plenty
  of extras (instrument-cluster hero row, vehicle dynamics row, support systems row)
  came along for the ride.
- **UID change.** The initial API push from Task 2 went in cleanly but left a DB row that
  conflicted with later file-based reconciliation via Flux. Reprovisioning under
  `shitbox-rally-v2` was the pragmatic fix. Website iframe URL updated in the same commit.
- **No separate summary at the time.** Execution was informal — the dashboard rewrite
  happened alongside 18-05 work. This summary is retroactive, confirmed by grepping
  the live dashboard JSON on 2026-04-16.

## Self-Check: PASSED

```
grep -n 'Ambient Light\|shitbox_lux\|probe="exterior"\|probe="engine_bay"' \
  home-ops/.../dashboards/shitbox-rally-command.json
# 3185: "expr": "shitbox_lux",
# 3191: "title": "Ambient Light",
# 950:  "expr": "shitbox_temp{probe=\"engine_bay\"}",
# 2070: "expr": "shitbox_temp{probe=\"exterior\"}",
# 2077: "expr": "shitbox_temp{probe=\"engine_bay\"}",
```

Live dashboard confirmed at `https://grafana.shit-of-theseus.com/d/shitbox-rally-v2`.
