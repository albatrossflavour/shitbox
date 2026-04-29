---
phase: 28
plan: 01
subsystem: tpms
tags: [tpms, tests, wave-0, scaffolding, red-phase]
requires: []
provides:
  - tests/conftest.py::fake_rtl433_frames
  - tests/conftest.py::fake_rtl433_subprocess (skip-stub)
  - tests/test_tpms_parser.py (6 tests)
  - tests/test_tpms_database.py (4 tests)
  - tests/test_tpms_alerts.py (5 tests)
  - tests/test_tpms_leak.py (3 tests)
  - tests/test_tpms_subprocess.py (4 tests)
  - tests/test_dashboard.py::test_tpms_payload_* (2 tests)
affects:
  - tests/conftest.py
  - tests/test_dashboard.py
tech-stack:
  added: [pytest skip-stub pattern, mock.MagicMock for lsusb subprocess]
  patterns: [per-test guards over module-level importorskip, explicit Plan-NN skip reasons]
key-files:
  created:
    - tests/test_tpms_parser.py
    - tests/test_tpms_database.py
    - tests/test_tpms_alerts.py
    - tests/test_tpms_leak.py
    - tests/test_tpms_subprocess.py
    - .planning/phases/28-tpms-integration/deferred-items.md
  modified:
    - tests/conftest.py
    - tests/test_dashboard.py
decisions:
  - "Use per-test skip guards instead of module-level pytest.importorskip so pytest --collect-only enumerates every behavioural test name in the must_haves contract"
  - "Skip reasons include explicit Plan-NN markers so executors of later plans can grep their TODO list out of the test files"
metrics:
  completed: 2026-04-28
  tasks: 3
  new-tests: 24
  files-created: 6
  files-modified: 2
requirements: [SPEC-1, SPEC-2, SPEC-3, SPEC-4, SPEC-5, SPEC-6, SPEC-7, SPEC-8, SPEC-9, SPEC-10]
---

# Phase 28 Plan 01: TPMS Wave 0 Test Scaffolding — Summary

Twenty-four named pytest tests covering every behavioural requirement in `28-VALIDATION.md` are now committed to the repository as skip-stubs. Each test imports the unit under test inside the function body and `pytest.skip`s with an explicit `Plan 28-NN` marker until the matching downstream plan lands. Two shared fixtures (`fake_rtl433_frames`, `fake_rtl433_subprocess`) are wired into `tests/conftest.py` for the implementation plans to import directly.

## Test File Inventory

### `tests/conftest.py` (modified)

Two new fixtures appended after the existing `mbtiles_fixture`:

| Fixture | Purpose | Skip-stub? |
|---------|---------|------------|
| `fake_rtl433_frames` | Returns four canned `rtl_433 -F json` frames keyed to the four bench-validated Abarth-124Spider sensor IDs (`550b57d9`, `54d96e8f`, `550d14ed`, `550b5d8a`) at the standard 31 PSI pre-correction kPa | No — fully implemented |
| `fake_rtl433_subprocess` | MagicMock-shaped Popen yielding frames on stdout, drainable stderr | Yes — body lands with Plan 28-04 |

### `tests/test_tpms_parser.py` (new — 6 tests, SPEC-1/2/3)

| Test | Spec | Skip marker |
|------|------|-------------|
| `test_valid_abarth_frame` | SPEC-1 | Plan 28-04 |
| `test_unknown_sensor_drop` | SPEC-3 | Plan 28-04 |
| `test_malformed_json_skipped` | SPEC-1 | Plan 28-04 |
| `test_pressure_correction` | SPEC-2 | Plan 28-04 |
| `test_kpa_to_psi` | SPEC-2 | Plan 28-04 |
| `test_wheel_mapping` | SPEC-3 | Plan 28-04 |

### `tests/test_tpms_database.py` (new — 4 tests, SPEC-4/5)

| Test | Spec | Skip marker |
|------|------|-------------|
| `test_migrate_v11` | SPEC-4 | Plan 28-02 (SCHEMA_VERSION still 10) |
| `test_insert_retrieve` | SPEC-4 | Plan 28-02 |
| `test_prometheus_metric_shape` | SPEC-5 | Plan 28-05 |
| `test_cursor_advance` | SPEC-5 | Plan 28-02 |

### `tests/test_tpms_alerts.py` (new — 5 tests, SPEC-7/9)

| Test | Spec | Skip marker |
|------|------|-------------|
| `test_low_pressure_red_fires` | SPEC-7 | Plan 28-04 |
| `test_yellow_no_tts` | SPEC-7 | Plan 28-04 |
| `test_low_pressure_restored` | SPEC-7 | Plan 28-04 |
| `test_stale_after_5min` | SPEC-9 | Plan 28-04 |
| `test_stale_clears` | SPEC-9 | Plan 28-04 |

`@pytest.fixture(autouse=True) _clear_alerts_state` mirrors the `test_alerts.py` pattern so when bodies activate they get a clean slate.

### `tests/test_tpms_leak.py` (new — 3 tests, SPEC-8)

| Test | Spec | Skip marker |
|------|------|-------------|
| `test_leak_detected` | SPEC-8 | Plan 28-04 |
| `test_slow_deflation_no_leak` | SPEC-8 | Plan 28-04 |
| `test_leak_writes_event_json` | SPEC-8 | Plan 28-02 (EventType.TPMS_LEAK) → Plan 28-04 (engine wiring) |

### `tests/test_tpms_subprocess.py` (new — 4 tests, SPEC-1/10)

| Test | Spec | Skip marker |
|------|------|-------------|
| `test_probe_finds_sdr` | SPEC-10 | Plan 28-03 (probe_usb_vid_pid) |
| `test_probe_missing_sdr` | SPEC-10 | Plan 28-03 |
| `test_restart_on_exit` | SPEC-1+10 | Plan 28-04 |
| `test_stderr_drained` | SPEC-1 | Plan 28-04 |

The two `probe_*` tests already wire a real `mock.patch` against `shitbox.hardware.probes.subprocess.run` and will run for real the moment Plan 28-03 lands `probe_usb_vid_pid`.

### `tests/test_dashboard.py` (modified — 2 new tests, SPEC-6)

| Test | Spec | Skip marker |
|------|------|-------------|
| `test_tpms_payload_four_wheels` | SPEC-6 | Plan 28-05 |
| `test_tpms_payload_no_data` | SPEC-6 | Plan 28-05 |

Appended after the existing `_system_conditions_payload` block at line 549.

## Skip-Reason Convention

Every skip in this plan uses the format:

```
Plan 28-NN — <one-sentence reason>
```

Implementation executors of plans 28-02 through 28-06 can grep their TODO list out of the test files:

```bash
grep -rn "Plan 28-02" tests/      # schema migration TODOs
grep -rn "Plan 28-03" tests/      # USB probe TODOs
grep -rn "Plan 28-04" tests/      # TPMSService TODOs (the bulk)
grep -rn "Plan 28-05" tests/      # batch_sync + dashboard wiring TODOs
```

When a plan is implemented its skips flip to real pass/fail without anyone needing to edit the test files except to add new bodies.

## Decisions Made

1. **Per-test guards over module-level `pytest.importorskip`.** The plan's example code used `tpms = pytest.importorskip(...)` at module scope. That pattern hides every test from `pytest --collect-only` because the module raises `Skipped` before pytest can introspect functions. The success criterion in the prompt explicitly required `pytest --collect-only tests/test_tpms_*.py tests/test_dashboard.py` to list every export from `must_haves.artifacts`. I switched to a private `_import_tpms()` helper called from inside each test body. Functional behaviour is identical (skip on missing module) but every test name is visible in collection output now and forever.

2. **Sensor-ID source of truth.** The four sensor IDs live in three places (`28-SPEC.md` Background, `28-PATTERNS.md` Pattern 1, the `fake_rtl433_frames` fixture). The fixture is now the canonical bench-validated copy that downstream test code will import; if those IDs ever change after the Thursday hardware bring-up they only need updating in one file.

3. **Pre-existing `test_dashboard.py` ruff failures left alone.** Eleven `ruff check tests/test_dashboard.py` errors predate Plan 28-01 (lines 70 through 367, all before my insertion at line 549). Per the scope-boundary rule these are out of scope; logged to `deferred-items.md` for Plan 28-05 or a standalone housekeeping pass to address.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Switched from module-level `pytest.importorskip` to per-test guards**
- **Found during:** Task 2 verification
- **Issue:** Plan's specified `tpms = pytest.importorskip(...)` at module level prevents pytest from collecting test names; `pytest --collect-only` shows zero tests instead of the six required by the prompt-level success criterion.
- **Fix:** Replaced module-level `importorskip` with a private `_import_tpms()` helper called inside each test body. Same skip behaviour, but `pytest --collect-only` now lists every test name.
- **Files modified:** `tests/test_tpms_parser.py`, `tests/test_tpms_alerts.py`, `tests/test_tpms_leak.py`
- **Commit:** `dcd463d` (parser+database) and `a09e7b8` (alerts/leak/subprocess)

**2. [Rule 1 — Bug] Ruff I001 import sort in test_tpms_database.py**
- **Found during:** Task 2 verification
- **Issue:** `from shitbox.storage.database import Database, SCHEMA_VERSION` failed `ruff I001` — alphabetical sort puts the constant first.
- **Fix:** Reordered to `import SCHEMA_VERSION, Database`.
- **Files modified:** `tests/test_tpms_database.py`
- **Commit:** `dcd463d`

### Authentication Gates

None. Wave 0 is pure test-file scaffolding; no auth, no network.

## Verification

| Command | Result |
|---------|--------|
| `pytest tests/test_tpms_*.py tests/test_dashboard.py --collect-only -q` | 47 tests collected (24 new + 23 existing) |
| `pytest tests/test_tpms_*.py tests/test_dashboard.py -x --tb=short -q` | 23 passed, 24 skipped (all skips reference Plan 28-NN) |
| `pytest -x --tb=short -q` (full suite) | 522 passed, 25 skipped, 0 failed |
| `ruff check tests/test_tpms_*.py` | All checks passed |
| `ruff check tests/conftest.py` | All checks passed |
| `grep -i "tire" tests/test_tpms_*.py tests/conftest.py` | No matches (UK/Aus spelling preserved) |

## Deferred Issues

See `.planning/phases/28-tpms-integration/deferred-items.md` for the full list. Summary: `tests/test_dashboard.py` carries 11 pre-existing ruff failures unrelated to this plan; my insertion is clean.

## Self-Check: PASSED

Verified files exist and commits are recorded:

```
FOUND: tests/test_tpms_parser.py
FOUND: tests/test_tpms_database.py
FOUND: tests/test_tpms_alerts.py
FOUND: tests/test_tpms_leak.py
FOUND: tests/test_tpms_subprocess.py
FOUND: tests/conftest.py (modified)
FOUND: tests/test_dashboard.py (modified)
FOUND: .planning/phases/28-tpms-integration/deferred-items.md

FOUND commit: 86aab04 (Task 1 — fixtures)
FOUND commit: dcd463d (Task 2 — parser + database)
FOUND commit: a09e7b8 (Task 3 — alerts + leak + subprocess + dashboard)
```
