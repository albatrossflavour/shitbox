---
phase: 28-tpms-integration
plan: 04
subsystem: tpms
tags: [tpms, service, subprocess, alerts, leak, stale, wave-2]

# Dependency graph
requires:
  - phase: 28-tpms-integration
    provides: "Plan 28-01 — test scaffolding (parser/alerts/leak/subprocess test files)"
  - phase: 28-tpms-integration
    provides: "Plan 28-02 — Database.insert_tpms_reading + EventType.TPMS_LEAK"
  - phase: 28-tpms-integration
    provides: "Plan 28-03 — TpmsConfig + speak_tpms_* + probe_usb_vid_pid"
provides:
  - "src/shitbox/sync/tpms.py with TPMSService class + 4 pure helpers"
  - "Eight active alert subtypes per phase: TPMS_LOW_<WHEEL> + TPMS_LEAK_<WHEEL>"
  - "Recovery subtypes: TPMS_LOW_<WHEEL>_RESTORED (no recovery wired for LEAK by design)"
  - "snapshot() per-wheel state for the dashboard SSE payload (no_data | ok | low | critical | stale)"
affects:
  - "28-05 — engine wires UnifiedEngine to TPMSService.start/stop, dashboard reads snapshot()"
  - "28-06 — Health page row glyphs read alerts.snapshot()[TPMS_*] for fired/active state"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "rtl_433 subprocess lifecycle: lifted from ring_buffer.py's ffmpeg pattern (March 2026), with the BlockingIOError fix for non-blocking pipe drain"
    - "Single-writer-per-subtype invariant: only the reader thread calls fire_alert/fire_recovery; monitor thread does subprocess control only; snapshot() is read-only via the state lock"
    - "Inner def closures over `position` instead of default-arg lambdas — mypy infers the signature cleanly, no late-binding hazard"

key-files:
  created:
    - "src/shitbox/sync/tpms.py (590 lines)"
  modified:
    - "tests/test_tpms_alerts.py (skip-stubs → real bodies, 5/5 pass)"
    - "tests/test_tpms_leak.py (skip-stubs → real bodies, 3/3 pass)"
    - "tests/test_tpms_subprocess.py (skip-stubs → real bodies, 4/4 pass)"

key-decisions:
  - "Subprocess lifecycle uses a Lock-free reader/monitor split. Reader blocks on stdout.readline(); monitor wakes every 5s, drains stderr, restarts dead processes, and reports the SDR missing when probe_usb_vid_pid fails."
  - "Lambda → inner def conversion. The plan skeleton used `lambda p=position: speak_tpms_low(p)` for closure binding; mypy cannot infer the type of default-arg-lambdas. Replaced with `def _say_low() -> None: speak_tpms_low(position)` which closes over the local `position` cleanly. Same runtime behaviour, mypy clean."
  - "Leak alert has no recovery wiring. Once `_detect_leak` returns False, the leak subtype simply stops firing; the Phase 15 helper holds `fired=True` until an explicit fire_recovery sustains. Acceptable per SPEC REQ 8 — a leak is forensic, not a trip-state flag."
  - "Skip-stubs from Plan 28-01 activated as part of THIS plan, not a separate housekeeping pass. 28-01 SUMMARY explicitly said 'bodies activate when Plan 28-NN lands'; the skip strings reference Plan 28-04. Activating them here is the contract 28-01 set up."

patterns-established:
  - "Inner def closures over keyword-only loop variables — replaces `lambda p=position: …` pattern across the codebase where mypy is enabled"
  - "BlockingIOError-aware non-blocking drain — the ring_buffer.py original silently lost data on macOS; tpms.py tightens the loop"

requirements-completed: [SPEC-1, SPEC-2, SPEC-3, SPEC-4, SPEC-7, SPEC-8, SPEC-9]
# SPEC-5 (Prometheus shape) is Plan 28-05; SPEC-6 (dashboard) is Plan 28-05;
# SPEC-10 (hardware probe) was completed in Plan 28-03 + this plan's monitor wiring.

# Metrics
duration: ~13 min
started: 2026-04-28T09:51:48Z
completed: 2026-04-28T10:05:02Z
---

# Phase 28 Plan 04: TPMSService — Summary

**The only fundamentally new module in Phase 28. `TPMSService` owns the rtl_433 subprocess lifecycle, parses 433 MHz TPMS frames, applies the × 2.45 pressure correction, persists each frame to SQLite, drives per-wheel sustained-low + leak + stale alerts via `health/alerts.py` and `speaker.py`, and exposes a `snapshot()` for the dashboard.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-04-28T09:51:48Z
- **Completed:** 2026-04-28T10:05:02Z
- **Tasks:** 2 of 2
- **Files created:** 1 (`src/shitbox/sync/tpms.py`, 590 lines)
- **Files modified:** 3 (test bodies activated from Plan 28-01 skip-stubs)

## Commits

- `a2876cd` — `feat(28-04): TPMSService skeleton + module-level helpers`
- `4762303` — `feat(28-04): implement _handle_frame + leak detector + alert wiring`

## Alert Subtype Naming Convention (for Plan 28-05)

The Phase 15 alerts helper is single-writer-per-subtype. This plan registers eight active alert subtypes per phase plus four recovery subtypes:

| Subtype                            | Fires when                                  | TTS                              | Recovery emits                          |
| ---------------------------------- | ------------------------------------------- | -------------------------------- | --------------------------------------- |
| `TPMS_LOW_FRONT_DRIVER`            | psi ≤ 25 sustained for 2 frames             | `speak_tpms_low("front-driver")` | `TPMS_LOW_FRONT_DRIVER_RESTORED`        |
| `TPMS_LOW_FRONT_PASSENGER`         | psi ≤ 25 sustained for 2 frames             | `speak_tpms_low("front-passenger")` | `TPMS_LOW_FRONT_PASSENGER_RESTORED`     |
| `TPMS_LOW_REAR_DRIVER`             | psi ≤ 25 sustained for 2 frames             | `speak_tpms_low("rear-driver")`  | `TPMS_LOW_REAR_DRIVER_RESTORED`         |
| `TPMS_LOW_REAR_PASSENGER`          | psi ≤ 25 sustained for 2 frames             | `speak_tpms_low("rear-passenger")` | `TPMS_LOW_REAR_PASSENGER_RESTORED`      |
| `TPMS_LEAK_FRONT_DRIVER`           | ≥5 PSI drop within 60s on this wheel        | `speak_tpms_leak("front-driver")` | (none — by design, see Decisions)       |
| `TPMS_LEAK_FRONT_PASSENGER`        | ≥5 PSI drop within 60s on this wheel        | `speak_tpms_leak("front-passenger")` | (none)                                  |
| `TPMS_LEAK_REAR_DRIVER`            | ≥5 PSI drop within 60s on this wheel        | `speak_tpms_leak("rear-driver")` | (none)                                  |
| `TPMS_LEAK_REAR_PASSENGER`         | ≥5 PSI drop within 60s on this wheel        | `speak_tpms_leak("rear-passenger")` | (none)                                  |

Plan 28-05 dashboard payload reads `alerts.snapshot()` and looks for keys with the `TPMS_LOW_*` and `TPMS_LEAK_*` prefixes. The `_RESTORED` recovery subtype is emitted as a one-shot dashboard event (matching Phase 15 `UNDERVOLTAGE_CLEARED`), and the underlying `TPMS_LOW_*` key flips back to `fired=False, active=False` after recovery sustains.

Yellow band (25 < PSI ≤ 28) is **NOT** wired into `alerts.fire_alert` — it is a Health-page row colour only. The dashboard reads `snapshot()[wheel]["state"] == "low"` and renders the row in amber. Red band (PSI ≤ 25) is the only TTS-firing condition.

## Single-Writer Invariant

Confirmed in code: `alerts.fire_alert` and `alerts.fire_recovery` are only called from `_handle_frame`, which only runs in the reader thread (`tpms-reader`). The monitor thread (`tpms-monitor`) handles subprocess lifecycle but never touches the alerts module. The dashboard SSE thread (Plan 28-05) reads `snapshot()` but does not write to `_wheels` — the `_state_lock` is reader-side defensive in case Plan 28-05 introduces a writer path on the SSE side (none expected).

```
$ grep -n "alerts\.fire_" src/shitbox/sync/tpms.py
505:        alerts.fire_alert(
512:        alerts.fire_recovery(
544:        alerts.fire_alert(
```

All three call sites are inside `_wire_low_pressure_alert` or `_wire_leak_alert`, which are only called from `_handle_frame`, which is only called from `_reader_loop`.

## Leak Deque Sizing

Per-wheel `collections.deque(maxlen=120)`. Rationale:

- Steady-state TPMS frame rate is ~1 Hz per wheel (Abarth-124 sensors heartbeat every ~1s).
- Window is 60s.
- 60 frames at 1 Hz × 2 = 120 entries — twice the expected window depth so a transient burst of `0x93` (active-transmit) frames at 4 Hz cannot evict legitimate window data.
- `deque.append` is GIL-atomic in CPython 3.9+ (bugs.python.org/issue15329); the GIL build is the only build on Pi OS bookworm. No lock needed for the single-producer-per-wheel pattern.

## Event Required Fields

`Event` dataclass (`shitbox/events/detector.py`) has three required positional `peak_*` fields after `peak_value`: `peak_ax`, `peak_ay`, `peak_az`. The plan skeleton implied they had defaults; they do not. Supplied as `0.0` for TPMS_LEAK events:

```python
event = Event(
    event_type=EventType.TPMS_LEAK,
    start_time=now_wall,
    end_time=now_wall,
    peak_value=psi,            # the PSI that triggered the leak
    peak_ax=0.0, peak_ay=0.0, peak_az=0.0,   # required, no IMU sample
    samples=[],                # no IMU buffer save
)
```

`peak_gx/gy/gz` and the location fields all have defaults so they're omitted. The `to_dict()` output is forensically correct: `peak_value` is the PSI, the IMU axes are 0.0 (clearly synthetic), and `sample_count: 0` makes it obvious this is a metadata-only event with no CSV.

## Closure Pattern

The plan skeleton specified `lambda p=position: speak_tpms_low(p)` for closure binding (default-arg trick to fix the late-binding hazard). mypy cannot infer the type of default-arg-lambdas — three errors landed on first run. Switched to inner `def`:

```python
def _say_low() -> None:
    speak_tpms_low(position)
```

The function closes over `position` from the enclosing scope. Each call to `_wire_low_pressure_alert(position, ...)` rebinds `position` in its own frame, so there is no late-binding hazard (the lambda hazard only arises when multiple closures share a common loop variable). Same runtime behaviour, mypy clean, easier to read.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] BlockingIOError silently lost data in `_read_stderr_nonblocking`**

- **Found during:** Task 2 verification (`tests/test_tpms_subprocess.py::test_stderr_drained` failed with `assert "X" in ""`).
- **Issue:** The pattern lifted verbatim from `capture/ring_buffer.py:827-846` had the inner loop wrapped only by an outer `try/except Exception: pass`. On a non-blocking pipe with no more data buffered, `os.read` raises `BlockingIOError` rather than returning `b""` (this is documented Python 3 behaviour and reproducible on macOS and Linux). The bare `except` swallowed the exception and the bytes already accumulated in `data` were lost — the function returned `""`.
- **Fix:** Catch `BlockingIOError` inside the inner `while` loop as the loop-exit signal. Outer `except Exception` keeps any bytes already drained as a last-ditch return.
- **Impact:** This is the same bug in `ring_buffer.py`. Tracked for follow-up (`deferred-items.md`) — the ffmpeg helper happens to work today because ffmpeg writes stderr fast enough that the pipe always has data when the helper polls; the bug only manifests when the helper is called against an already-drained non-blocking pipe.
- **Files modified:** `src/shitbox/sync/tpms.py`
- **Commit:** `4762303`

**2. [Rule 1 — Bug] mypy `Cannot infer type of lambda` on default-arg-lambdas**

- **Found during:** Task 2 verification (`mypy src/shitbox/sync/tpms.py` reported 3 errors at lines 503, 510, 537).
- **Issue:** The plan skeleton specified `lambda p=position: speak_tpms_low(p)` for closure-binding. mypy 1.x cannot infer the signature `() -> None` from a default-arg-lambda; it requires an explicit annotation, which is awkward for inline lambdas.
- **Fix:** Inner `def _say_low() -> None: ...` closures with explicit return-type annotations. Same runtime behaviour, mypy clean.
- **Files modified:** `src/shitbox/sync/tpms.py`
- **Commit:** `4762303`

**3. [Rule 2 — Functionality] Activated Plan 28-01 skip-stubs as real test bodies**

- **Found during:** Task 2 verification (`pytest tests/test_tpms_*.py` showed 11 skipped tests with `Plan 28-04 — …` markers).
- **Issue:** Plan 28-01 wrote test files where every test body was `pytest.skip("Plan 28-04 — …")` after the import guard. The 28-01 SUMMARY explicitly said "bodies activate when Plan 28-04 lands the alert wiring" but the bodies were never actually drafted. Plan 28-04 acceptance criteria require these tests to pass (`pytest tests/test_tpms_alerts.py -x` exits 0 with all 5 tests passing — currently 5 skipped).
- **Fix:** Replaced skip stubs with real test bodies in `test_tpms_alerts.py` (5 tests), `test_tpms_leak.py` (3 tests), and `test_tpms_subprocess.py` (2 tests, leaving the two probe tests untouched — they were already real). All bodies use direct `_handle_frame` injection or `_detect_leak` calls; no daemon-thread orchestration. Mocks for the DB, EventStorage, and `speak_tpms_*` callbacks.
- **Files modified:** `tests/test_tpms_alerts.py`, `tests/test_tpms_leak.py`, `tests/test_tpms_subprocess.py`
- **Commit:** `4762303`

### Authentication Gates

None. No network paths, no auth, no external services touched.

## Verification

| Check                                                               | Result                                                                |
| ------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `python -c "from shitbox.sync.tpms import TPMSService, parse_frame, correct_pressure_kpa, kpa_to_psi, lookup_wheel"` | imports succeed |
| `pytest tests/test_tpms_parser.py -x`                               | 6/6 PASS                                                              |
| `pytest tests/test_tpms_alerts.py -x`                               | 5/5 PASS                                                              |
| `pytest tests/test_tpms_leak.py -x`                                 | 3/3 PASS                                                              |
| `pytest tests/test_tpms_subprocess.py -x`                           | 4/4 PASS                                                              |
| `pytest tests/test_tpms_database.py -x`                             | 3 PASS, 1 SKIP (`test_prometheus_metric_shape` waits on Plan 28-05)   |
| `pytest tests/test_tpms_*.py -q`                                    | 21 passed, 1 skipped                                                  |
| `pytest -q` (full suite)                                            | 545 passed, 4 skipped, 0 failed                                       |
| `ruff check src/shitbox/sync/tpms.py`                               | All checks passed                                                     |
| `mypy src/shitbox/sync/tpms.py`                                     | 0 errors in tpms.py (20 pre-existing baseline errors elsewhere)       |
| `wc -l src/shitbox/sync/tpms.py`                                    | 590 (≥350 must_haves minimum)                                         |
| `grep -i "tire" src/shitbox/sync/tpms.py tests/test_tpms_*.py`      | (empty — UK/Aus "tyre" preserved)                                     |

## Acceptance Criteria

All Task 1 + Task 2 acceptance criteria from `28-04-PLAN.md` met:

- `class TPMSService` present (1 match) — `tpms.py:118`
- `def parse_frame` (1) — `tpms.py:43`
- `def correct_pressure_kpa` (1) — `tpms.py:61`
- `def kpa_to_psi` (1) — `tpms.py:71`
- `def lookup_wheel` (1) — `tpms.py:76`
- `_read_stderr_nonblocking` (≥2 matches: definition + monitor call sites) — `tpms.py:285, 341, 360`
- `_monitor_loop` (≥2: definition + call) — `tpms.py:331, 187`
- `probe_usb_vid_pid` (≥1) — `tpms.py:367`
- `hw_state.report_missing` (≥1) — `tpms.py:368`
- `hw_state.report_present` (≥1) — `tpms.py:380`
- `def _handle_frame` (1, no longer stub) — `tpms.py:387`
- `NotImplementedError` (0) — confirmed gone
- `def _detect_leak` (1) — `tpms.py:471`
- `def _wire_low_pressure_alert` (1) — `tpms.py:493`
- `def _wire_leak_alert` (1) — `tpms.py:529`
- `alerts.fire_alert` (2: low + leak) — `tpms.py:505, 544`
- `alerts.fire_recovery` (1: low restored) — `tpms.py:512`
- `EventType.TPMS_LEAK` (1) — `tpms.py:560`
- `self.db.insert_tpms_reading` (1) — `tpms.py:440`
- `tpms_unknown_sensor` (1) — `tpms.py:408`
- `tpms_frame_received` (1) — `tpms.py:428`
- `TYRE LOW PRESSURE` (1) — `tpms.py:511`
- `TYRE LEAKING` (1) — `tpms.py:549`
- `TYRE PRESSURE RESTORED` (1) — `tpms.py:518`

## Deferred Issues

**`ring_buffer._read_stderr` has the same BlockingIOError bug as the pre-fix tpms variant.**

The ring_buffer.py original silently loses bytes when the ffmpeg pipe is fully drained (the `except Exception: pass` swallows `BlockingIOError`). It works in production because ffmpeg writes stderr stats fast enough that the pipe always has data when the health monitor polls every 2s. Fix is mechanical: catch `BlockingIOError` inside the inner loop as the exit signal. Out of scope for this plan (28-04 ships TPMS only); flagged here for the next ring_buffer.py touch. Logged to `.planning/phases/28-tpms-integration/deferred-items.md`.

## Self-Check: PASSED

- File `src/shitbox/sync/tpms.py` exists (590 lines).
- Commit `a2876cd` (Task 1 — skeleton + helpers) present in `git log`.
- Commit `4762303` (Task 2 — _handle_frame + alerts + tests) present in `git log`.
- All required `grep` invariants pass (see Acceptance Criteria table).
- Full pytest suite green (545 passed, 4 skipped, 0 failed).
- ruff + mypy clean for `src/shitbox/sync/tpms.py`.
