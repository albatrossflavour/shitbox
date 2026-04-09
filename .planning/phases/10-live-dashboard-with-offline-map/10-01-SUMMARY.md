---
phase: 10-live-dashboard-with-offline-map
plan: 01
subsystem: dashboard
tags: [dashboard, config, snapshot, fastapi, foundation]
requires:
  - tests/test_dashboard.py (from 10-00)
provides:
  - shitbox.dashboard package (importable)
  - shitbox.dashboard.snapshot.read_snapshot / update_snapshot
  - DashboardConfig dataclass + YAML section
  - fastapi/uvicorn/sse-starlette runtime deps
affects:
  - pyproject.toml
  - config/config.yaml
  - src/shitbox/utils/config.py
tech_stack:
  added: [fastapi, uvicorn, sse-starlette]
  patterns: [lock-free-snapshot, gil-atomic-rebind, dataclass-yaml-config]
key_files:
  created:
    - src/shitbox/dashboard/__init__.py
    - src/shitbox/dashboard/snapshot.py
  modified:
    - pyproject.toml
    - src/shitbox/utils/config.py
    - config/config.yaml
decisions:
  - Bare uvicorn (no [standard] extras) for Pi arm64 compatibility — uvloop/httptools are unreliable there and we only need a handful of SSE clients, so pure asyncio is fine
  - DashboardConfig defaults enabled=false so Wave 4 can flip it on only after the engine wiring is proven
  - Snapshot is a plain module-level dict, rebound atomically in update_snapshot — no locks, no copies on read path
metrics:
  duration_min: 2
  tasks: 3
  files_changed: 5
  completed: 2026-04-09
---

# Phase 10 Plan 01: Dashboard Foundation Summary

One-liner: lays the dependency, config, package, and snapshot substrate for the live dashboard — fastapi/uvicorn/sse-starlette in pyproject, DashboardConfig wired through the YAML loader, and a 16-key lock-free snapshot module that flips the first two Phase 10 tests GREEN.

## What shipped

- pyproject.toml grew three deps (fastapi, uvicorn, sse-starlette) and extended package-data to ship `dashboard/static/**/*` when the package is installed. Deliberately no `uvicorn[standard]` — uvloop is a known headache on Pi arm64 and we have no need for its throughput.
- `DashboardConfig` dataclass landed in `src/shitbox/utils/config.py` with enabled/host/port/mbtiles_path/max_sse_clients, wired through `Config` and the YAML loader. `config/config.yaml` got a matching `dashboard:` section, `enabled: false` by default.
- `src/shitbox/dashboard/` package created with an empty `__init__.py` plus `snapshot.py` implementing the lock-free shared state pattern from the research doc.

## Snapshot module contract

Module-level `_snapshot` dict preseeded with 16 keys: `ts`, `speed_kmh`, `g_x`, `g_y`, `g_z`, `heading_deg`, `lat`, `lng`, `gps_fix_mode`, `gps_sat_count`, `gps_hdop`, `imu_temp_c`, `soc_temp_c`, `sync_connected`, `sync_backlog`, `event_count_today`. Readers never hit KeyError during boot.

`update_snapshot(new)` rebinds the global in one GIL-protected bytecode op. `read_snapshot()` returns the current dict by reference — no locks, no copies. Single writer is the engine sample callback (10 Hz, not the 100 Hz capture path, which per D-02 stays sacred).

## Tests flipped to GREEN

- `tests/test_dashboard.py::test_snapshot_atomicity`
- `tests/test_dashboard.py::test_snapshot_default_keys`

Both confirmed passing locally:

```text
tests/test_dashboard.py ..                                               [100%]
============================== 2 passed in 0.01s ===============================
```

The remaining Phase 10 tests (server, SSE, tiles, download_tiles) stay RED — that is the expected state for Wave 1.

## Verification

- `python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"` — OK
- `python -c "from shitbox.utils.config import load_config; c = load_config('config/config.yaml'); assert c.dashboard.port == 8080 and c.dashboard.enabled is False"` — OK
- `ruff check src/shitbox/dashboard/ src/shitbox/utils/config.py` — clean
- `mypy src/shitbox/dashboard/snapshot.py` — clean
- `pytest tests/test_dashboard.py::test_snapshot_atomicity tests/test_dashboard.py::test_snapshot_default_keys` — GREEN

`ruff check src/shitbox/` as a whole still reports 19 pre-existing errors in modules this plan did not touch. Out of scope, logged here for the verifier rather than fixed.

## Deviations from Plan

None. Plan executed exactly as written.

Note on parallel execution: 10-00 runs in the same wave and produced `tests/test_dashboard.py` in parallel. Verification benefited from it but the implementation here does not depend on it at import time.

## Deferred Issues

- Pre-existing ruff errors in other `src/shitbox/` modules (19 total). Not introduced by this plan, not in scope.

## Commits

- `486de43` — chore(10-01): add fastapi/uvicorn/sse-starlette deps and dashboard package-data
- `5cb9e59` — feat(10-01): add DashboardConfig dataclass and YAML section
- `913f647` — feat(10-01): add dashboard package and lock-free snapshot module

## Self-Check: PASSED

- src/shitbox/dashboard/__init__.py — FOUND
- src/shitbox/dashboard/snapshot.py — FOUND
- pyproject.toml fastapi/uvicorn/sse-starlette — FOUND
- DashboardConfig in config.py — FOUND
- dashboard: section in config.yaml — FOUND
- Commits 486de43, 5cb9e59, 913f647 — FOUND in git log
