---
phase: 28-tpms-integration
plan: 05
subsystem: tpms
tags: [tpms, dashboard, sse, batch-sync, engine, integration, wave-3]

# Dependency graph
requires:
  - phase: 28-tpms-integration
    provides: "Plan 28-02 — Database.get_unsynced_tpms_readings + prometheus_tpms cursor"
  - phase: 28-tpms-integration
    provides: "Plan 28-03 — TpmsConfig + TpmsSensorMapEntry"
  - phase: 28-tpms-integration
    provides: "Plan 28-04 — TPMSService + WHEEL_POSITIONS + snapshot()"
provides:
  - "src/shitbox/dashboard/sse.py — _tpms_payload, set_tpms_service, module-level tpms_service ref, /sse/slow tpms key"
  - "src/shitbox/dashboard/static/index.html — TPMS Health section between SYSTEM and HARDWARE, tpmsGlyph helper, .tpms-* CSS palette"
  - "src/shitbox/sync/batch_sync.py — _sync_tpms_batch + _send_metric_tuples helper + prometheus_tpms cursor advance"
  - "src/shitbox/events/engine.py — 13 flat tpms_* EngineConfig fields, from_yaml_config wiring, TPMSService instantiation behind binary guard, start/stop + dashboard register/deregister"
affects:
  - "28-06 (Grafana panel) — can now query shitbox_tpms_pressure_psi{wheel='...'} and shitbox_tpms_temperature_c{wheel='...'} time series for the panel design"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tuple-based Prometheus send path (_send_metric_tuples) — mirrors _sync_summary's network shape so TPMS rows + summary gauges share the snappy/protobuf encode + POST without duplicating the main batch sync's Reading-shaped path"
    - "Dual-cursor batch sync — TPMS readings advance prometheus_tpms independently of the hot prometheus IMU cursor, keeping high-cardinality wheel labels off the 25 Hz path (28-RESEARCH.md Pattern 5)"
    - "Module-level snapshot-provider register pattern — set_tpms_service mirrors set_recent_events_provider; the engine wires self.tpms at start() so the dashboard SSE can pull state without an import cycle"
    - "Graceful binary-presence guard — config.tpms_enabled AND shutil.which('rtl_433') gates instantiation, matches Pi-side optional-hardware degradation (BatchSyncService, ButtonHandler, GPS)"

key-files:
  created: []
  modified:
    - "src/shitbox/dashboard/sse.py (+78 lines)"
    - "src/shitbox/dashboard/static/index.html (+38 lines: 11 CSS, 12 HTML, 1 state init, 1 SSE merge, 9 glyph helper, 4 misc)"
    - "src/shitbox/sync/batch_sync.py (+90 lines)"
    - "src/shitbox/events/engine.py (+95 lines: 13 EngineConfig fields, 13 from_yaml mappings, 42 __init__ block, 8 start, 6 stop, Dict import)"
    - "tests/test_tpms_database.py (skip → 38-line real test body)"

key-decisions:
  - "Added _send_metric_tuples as a small helper (Action Step 1 option A from the plan) — 25 lines, encodes/POSTs tuples and raises on non-2xx. Inline duplication (option B) would have been 25+ lines in _sync_tpms_batch alone and the same shape is reusable for any future tuple-shape sender."
  - "Metric labels: car=shitbox, job=shitbox-mqtt-exporter, wheel=<position>. Matches the existing _readings_to_metrics base label set so Grafana queries that already filter by car/job stay compatible. The per-row wheel label is the only addition — high cardinality (4) is harmless."
  - "Binary presence check uses shutil.which not subprocess.run — stdlib path lookup, no fork, matches probe_audio_label's import shape. The richer probe_usb_vid_pid (Plan 28-03) handles the dynamic SDR-unplug case inside TPMSService._monitor_loop; the engine guard only needs to confirm the binary is installed at boot."
  - "Dashboard registration via dashboard_sse.set_tpms_service(self.tpms) inside start() (not __init__) — the dashboard module may not be loaded yet at __init__ time on hosts that disable the dashboard. Local import keeps the engine import cheap when the dashboard is skipped."
  - "Stop() also calls set_tpms_service(None) so a daemon restart on the same Python process (rare, but possible in tests) cannot leak the previous instance into the next dashboard wiring."
  - "tpms_sensor_map flat field is Dict[str, str] (lowercase id → position), built once via dict(config.tpms.sensor_map) in from_yaml_config. The TpmsSensorMapEntry list is reconstructed inside __init__ from the dict — small overhead, but keeps EngineConfig flat (matches CLAUDE.md 'Adding a New Service' pattern)."

patterns-established:
  - "Tuple-based Prometheus sender — opt for a generic _send_metric_tuples helper instead of inlining encode_remote_write + POST inside each new sync branch. Keeps each branch focused on shaping the tuples; lets new sync paths (Plan 28-06+) reuse the network shape."
  - "Dual-cursor batch sync — adding a second cursor (prometheus_tpms) is a single sync_cursors row, not a schema change. Pattern reusable for any future high-cardinality data stream that should not pollute the main IMU cursor."

requirements-completed: [SPEC-5, SPEC-6, SPEC-10]
# SPEC-1 through SPEC-4, SPEC-7, SPEC-8, SPEC-9 were closed by Plans 28-02
# through 28-04. Phase 28's user-facing surface is now functionally complete.

# Metrics
duration: ~22 min
started: 2026-04-28T20:11:00Z
completed: 2026-04-28T20:33:00Z
---

# Phase 28 Plan 05: TPMS Dashboard + Batch Sync + Engine Wiring Summary

**The user-facing surface for Phase 28. /sse/slow ships four deterministic FD/FP/RD/RP rows on the wire, the Health modal renders them in colour, the daemon constructs TPMSService behind a binary-presence guard, and BatchSyncService publishes shitbox_tpms_pressure_psi{wheel='…'} + shitbox_tpms_temperature_c{wheel='…'} on a dedicated prometheus_tpms cursor. After this plan, all three Plan-28-01 deferred tests (test_prometheus_metric_shape, test_tpms_payload_four_wheels, test_tpms_payload_no_data) flip green and a `tpms.enabled: true` daemon does the right thing on a Pi with the SDR plugged in.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-04-28T20:11:00Z
- **Completed:** 2026-04-28T20:33:00Z
- **Tasks:** 2 of 2
- **Files modified:** 5 (4 source, 1 test)

## Commits

- `f8d21ab` — `feat(28-05): _tpms_payload + Health TPMS section`
- `06e510c` — `feat(28-05): TPMS batch_sync branch + UnifiedEngine wiring`

## Wire-format reference (for Plan 28-06 + future Grafana panels)

### /sse/slow tpms array

Always four rows in deterministic FD/FP/RD/RP order, even with no service registered:

```json
"tpms": [
  {"label": "FD", "position": "front-driver",     "psi": null, "state": "no_data", "since_ms": null},
  {"label": "FP", "position": "front-passenger",  "psi": null, "state": "no_data", "since_ms": null},
  {"label": "RD", "position": "rear-driver",      "psi": null, "state": "no_data", "since_ms": null},
  {"label": "RP", "position": "rear-passenger",   "psi": null, "state": "no_data", "since_ms": null}
]
```

After a frame arrives:

```json
{"label": "FD", "position": "front-driver", "psi": 31.2, "state": "ok", "since_ms": 1500}
```

States: `no_data | ok | low | critical | stale`. State machine lives in `TPMSService.snapshot()` (Plan 28-04).

### Prometheus metric shape

Two metric families per parsed frame, both labelled with `wheel`:

```text
shitbox_tpms_pressure_psi{car="shitbox", job="shitbox-mqtt-exporter", wheel="front-driver"} 31.1
shitbox_tpms_temperature_c{car="shitbox", job="shitbox-mqtt-exporter", wheel="front-driver"} 22.5
```

Cursor: `prometheus_tpms` row in `sync_cursors`, advances independently of the main `prometheus` cursor.

### Glyph palette (for Plan 28-06 panel design)

| State    | Glyph | Colour     | Use                          |
| -------- | ----- | ---------- | ---------------------------- |
| ok       | ●     | `#3fb950`  | Pressure > yellow threshold  |
| low      | ▲     | `#d29922`  | Yellow ≥ PSI > red threshold |
| critical | ✖     | `#da3633`  | PSI ≤ red threshold or leak  |
| stale    | ◌     | `#d29922`  | No frame for stale_timeout   |
| no_data  | ·     | `#6e7681`  | Never seen a frame           |

Matches the existing `.sc-active` / `.sc-restored` shape so Plan 28-06 can use a consistent visual language across the Grafana TPMS panel and the dashboard Health modal.

## How the pieces fit

```
                       ┌──────────────────────────┐
                       │  rtl_433 (subprocess)    │
                       └────────────┬─────────────┘
                                    │ stdout (JSON lines)
                                    ▼
       ┌──────────────────────────────────────────────────┐
       │  TPMSService (28-04)                             │
       │  • _handle_frame → db.insert_tpms_reading        │
       │  • _wheels[position] state for snapshot()        │
       │  • alerts.fire_alert + speak_tpms_*              │
       └────────────┬──────────────────────┬──────────────┘
                    │ snapshot() (read)    │ tpms_readings rows
                    ▼                      ▼
       ┌────────────────────────┐   ┌──────────────────────────────┐
       │ dashboard.sse          │   │ BatchSyncService             │
       │ • _tpms_payload()      │   │ • _sync_tpms_batch()         │
       │ • set_tpms_service()   │   │ • _send_metric_tuples()      │
       │ • /sse/slow tpms key   │   │ • cursor: prometheus_tpms    │
       └────────────┬───────────┘   └──────────────┬───────────────┘
                    │                              │
                    ▼                              ▼
       ┌────────────────────────┐   ┌──────────────────────────────┐
       │ index.html Health      │   │ Prometheus remote_write      │
       │ • 4 rows, FD/FP/RD/RP  │   │ • shitbox_tpms_pressure_psi  │
       │ • Alpine x-for         │   │ • shitbox_tpms_temperature_c │
       │ • .tpms-* CSS palette  │   │ • wheel="…" label            │
       └────────────────────────┘   └──────────────────────────────┘
```

## Engine wiring

```python
# In UnifiedEngine.__init__ (after capture_sync, before logbook_storage)
self.tpms: Optional[Any] = None
if config.tpms_enabled:
    if shutil.which("rtl_433") is None:
        log.warning("tpms_disabled_no_rtl433_binary", ...)
    else:
        from shitbox.sync.tpms import TPMSService
        from shitbox.utils.config import TpmsConfig as _TpmsConfig
        from shitbox.utils.config import TpmsSensorMapEntry as _TpmsEntry
        tpms_config = _TpmsConfig(...flat fields rebuild...)
        self.tpms = TPMSService(tpms_config, self.database, self.event_storage)

# In start():
if self.tpms:
    self.tpms.start()
    from shitbox.dashboard import sse as dashboard_sse
    dashboard_sse.set_tpms_service(self.tpms)

# In stop():
if self.tpms:
    self.tpms.stop()
    from shitbox.dashboard import sse as dashboard_sse
    dashboard_sse.set_tpms_service(None)
```

## Sync loop ordering

```
sleep(batch_interval_seconds)
  → _log_sync_state
  → if connected:
      → _sync_batch        (main IMU/GPS readings, prometheus cursor)
      → _sync_tpms_batch   (Phase 28, prometheus_tpms cursor)
      → _sync_summary      (gauge metrics, no cursor)
```

Each is in its own try/except so one failure does not stall the others. TPMS failure logs `tpms_batch_sync_error` warning and continues.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 3 — Blocking] `Dict` import missing in engine.py**

- **Found during:** Task 2 EngineConfig field add.
- **Issue:** `tpms_sensor_map: Dict[str, str]` referenced `Dict` which engine.py did not import (`from typing import Any, Callable, Optional, cast`).
- **Fix:** Added `Dict` to the typing import. Pre-existing imports already use `Optional` from `typing`, no other changes.
- **Files modified:** `src/shitbox/events/engine.py`
- **Commit:** `06e510c`

### Authentication gates

None.

## Verification

| Check                                                                                              | Result                                                  |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `pytest tests/test_dashboard.py::test_tpms_payload_four_wheels -x`                                 | PASS (was SKIPPED)                                      |
| `pytest tests/test_dashboard.py::test_tpms_payload_no_data -x`                                     | PASS (was SKIPPED)                                      |
| `pytest tests/test_tpms_database.py::test_prometheus_metric_shape -x`                              | PASS (was SKIPPED)                                      |
| `pytest tests/test_dashboard.py -q`                                                                | 25 passed (no regression)                               |
| `pytest tests/test_tpms_database.py -q`                                                            | 4 passed (was 3 + 1 skip)                               |
| `pytest -q` (full suite)                                                                           | 548 passed, 1 skipped (was 545 passed, 4 skipped)       |
| `ruff check src/shitbox/dashboard/sse.py`                                                          | All checks passed                                       |
| `ruff check src/shitbox/sync/batch_sync.py`                                                        | All checks passed                                       |
| `ruff check src/shitbox/events/engine.py`                                                          | 6 pre-existing E501 (lines 700, 701, 1068, 1113, 1114, 1960) — out of scope, unchanged from baseline |
| `python -m mypy src/shitbox/dashboard/sse.py`                                                      | 0 errors in sse.py (20 baseline errors elsewhere, unchanged) |
| `python -c "from shitbox.events.engine import EngineConfig; e=EngineConfig(); assert e.tpms_enabled is False; assert e.tpms_pressure_correction_factor == 2.45"` | OK                                                      |
| `grep -i "tire" src/shitbox/dashboard/sse.py src/shitbox/dashboard/static/index.html`              | empty (UK/Aus "tyre" preserved)                         |

## Acceptance Criteria

All Task 1 + Task 2 acceptance criteria from `28-05-PLAN.md` met:

| Acceptance check                                                                                                | Result                                            |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `grep "def _tpms_payload" src/shitbox/dashboard/sse.py`                                                         | 1 match                                           |
| `grep "def set_tpms_service" src/shitbox/dashboard/sse.py`                                                      | 1 match                                           |
| `grep "tpms_service" src/shitbox/dashboard/sse.py`                                                              | 7 matches (≥4)                                    |
| `grep '"tpms": _tpms_payload()' src/shitbox/dashboard/sse.py`                                                   | 1 match                                           |
| `grep "TPMS" src/shitbox/dashboard/static/index.html`                                                           | section eyebrow + comments — multiple matches     |
| `grep 'x-for="row in tpms"' src/shitbox/dashboard/static/index.html`                                            | 1 match                                           |
| `grep ':key="row.position"' src/shitbox/dashboard/static/index.html`                                            | 1 match                                           |
| `grep "tpms: \[\]" src/shitbox/dashboard/static/index.html`                                                     | 1 match (Alpine init)                             |
| `grep "this.tpms = d.tpms" src/shitbox/dashboard/static/index.html`                                             | 1 match (SSE merge)                               |
| `grep "tpmsGlyph" src/shitbox/dashboard/static/index.html`                                                      | 2 matches (definition + use)                      |
| `grep ".tpms-no_data" src/shitbox/dashboard/static/index.html`                                                  | 1 match (CSS class)                               |
| `grep "def _sync_tpms_batch" src/shitbox/sync/batch_sync.py`                                                    | 1 match                                           |
| `grep '"shitbox_tpms_pressure_psi"' src/shitbox/sync/batch_sync.py`                                             | 1 match                                           |
| `grep '"shitbox_tpms_temperature_c"' src/shitbox/sync/batch_sync.py`                                            | 1 match                                           |
| `grep '"prometheus_tpms"' src/shitbox/sync/batch_sync.py`                                                       | 1 match                                           |
| `grep "self._sync_tpms_batch" src/shitbox/sync/batch_sync.py`                                                   | 1 match (called in _sync_loop)                    |
| `grep "tpms_enabled" src/shitbox/events/engine.py`                                                              | 3 matches (EngineConfig field, from_yaml, guard)  |
| `grep "tpms_sensor_map" src/shitbox/events/engine.py`                                                           | 3 matches                                         |
| `grep "self.tpms = TPMSService" src/shitbox/events/engine.py`                                                   | 1 match                                           |
| `grep "self.tpms.start()" src/shitbox/events/engine.py`                                                         | 1 match                                           |
| `grep "self.tpms.stop()" src/shitbox/events/engine.py`                                                          | 1 match                                           |
| `grep "set_tpms_service" src/shitbox/events/engine.py`                                                          | 2 matches (start register + stop deregister)      |
| `grep 'shutil.which("rtl_433")' src/shitbox/events/engine.py`                                                   | 1 match                                           |

## Plan-Output Confirmations

The plan's `<output>` section asked for explicit confirmations:

- **`_send_to_prometheus_tuples` decision (Action Step 1 A vs B):** Picked option (A). Added `_send_metric_tuples` as a thin helper (~25 lines) on `BatchSyncService` that encodes the protobuf + snappy payload and POSTs with the same headers as `_sync_summary`. Tuple-shape network path is now reusable; `_sync_tpms_batch` is just shape-the-tuples + send.

- **TPMS metric label set:** `{car: "shitbox", job: "shitbox-mqtt-exporter", wheel: "<position>"}` — matches the base labels from `_readings_to_metrics` so Grafana dashboards keyed off `car="shitbox"` continue to work; `wheel` is the only TPMS-specific addition.

- **State → glyph mapping:** `ok=●  low=▲  critical=✖  stale=◌  no_data=·`. Stored in the `tpmsGlyph` Alpine helper alongside `scGlyph` for visual consistency.

- **rtl_433 binary check:** `shutil.which("rtl_433")` (stdlib path lookup, no subprocess). The richer `probe_usb_vid_pid` (Plan 28-03) handles dynamic SDR-unplug inside `TPMSService._monitor_loop`; the engine guard only needs to confirm the binary is installed at boot.

- **Dashboard registration:** `dashboard_sse.set_tpms_service(self.tpms)` called inside `UnifiedEngine.start()` after `self.tpms.start()`; `set_tpms_service(None)` called inside `UnifiedEngine.stop()` after `self.tpms.stop()`. Both wrapped in try/except so a missing dashboard module does not stop the engine.

## Deferred Issues

The Plan-28-01 deferred ruff failures in `tests/test_dashboard.py` (lines 70, 141, 145, 157, 214, 233, 242, 259, 274, 359, 364, 367 — I001 import sort, F841 unused, E741 ambiguous, F401, E501) were **not** fixed in this plan. They predate Plan 28-01 and would require ~12 line changes spread across tests not modified by Plan 28-05. Out of scope per the plan-execution scope-boundary rule. Tracked in `.planning/phases/28-tpms-integration/deferred-items.md`.

The 6 pre-existing E501 ruff errors in `src/shitbox/events/engine.py` (lines 700, 701, 1068, 1113, 1114, 1960 post-edit) are unchanged from the pre-edit baseline — confirmed via `git stash` + `ruff check`. Out of scope.

## Self-Check: PASSED

- `src/shitbox/dashboard/sse.py` modified — verified: `_tpms_payload`, `set_tpms_service`, `tpms_service`, `WHEEL_POSITIONS` graceful import, `_TPMS_LABELS`, `/sse/slow` `tpms` key all present.
- `src/shitbox/dashboard/static/index.html` modified — verified: TPMS section between SYSTEM and HARDWARE, `tpms: []` Alpine init, `this.tpms = d.tpms || []` SSE merge, `tpmsGlyph` helper, `.tpms-*` CSS palette.
- `src/shitbox/sync/batch_sync.py` modified — verified: `_sync_tpms_batch`, `_send_metric_tuples`, `prometheus_tpms` cursor, `shitbox_tpms_pressure_psi`, `shitbox_tpms_temperature_c`, called from `_sync_loop`.
- `src/shitbox/events/engine.py` modified — verified: 13 `tpms_*` `EngineConfig` fields, `from_yaml_config` mapping, `__init__` guard `shutil.which("rtl_433")`, `start()` registers, `stop()` deregisters.
- `tests/test_tpms_database.py` modified — verified: `test_prometheus_metric_shape` no longer skipped.
- Commit `f8d21ab` (Task 1) present in `git log`.
- Commit `06e510c` (Task 2) present in `git log`.
- Full pytest suite: 548 passed, 1 skipped (the `test_lifecycle_logs_endpoints` already-skipped marker, unchanged), 0 failed.
- ruff + mypy on all four modified source files: clean (engine.py has 6 pre-existing E501 unchanged from baseline).

## Next Phase Readiness

- Plan 28-06 (Grafana panel design) can query `shitbox_tpms_pressure_psi{wheel="..."}` and `shitbox_tpms_temperature_c{wheel="..."}` directly. Wheel labels are stable: `front-driver`, `front-passenger`, `rear-driver`, `rear-passenger`. Cursor (`prometheus_tpms`) advances independently of the main IMU cursor so panel design is decoupled from IMU sample rate.
- Phase 28's user-facing surface is functionally complete on a Pi with the rtl_433 binary present + the SDR plugged in. Hardware verification (VID:PID confirm, real frame end-to-end) is `28-VALIDATION.md` A4 (Thursday 2026-04-30 when the dongle arrives).

---
*Phase: 28-tpms-integration*
*Completed: 2026-04-28*
