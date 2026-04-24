---
phase: 15-undervoltage-and-monitoring
plan: 01
subsystem: health
tags: [alerts, health, helper, tdd, tts, sustain, recovery]

# Dependency graph
requires:
  - phase: 21-hardware-inventory-and-graceful-degradation
    provides: "module-level GIL-atomic rebind pattern (hardware/state.py), Phase 21 D-04 never-refuse-boot discipline"
  - phase: 10-live-dashboard-with-offline-map
    provides: "dashboard_push_event with type=ALERT, capture-path-sacred rule (D-02)"
  - phase: 05-piper-tts
    provides: "speaker.py utterance catalogue and _should_alert boot-gate"
provides:
  - "src/shitbox/health/alerts.py helper (fire_alert, fire_recovery, snapshot, clear_state, AlertStatus)"
  - "recovery_subtype kwarg on fire_recovery for _CLEARED/_RESTORED suffix routing"
  - "Optional tts_fn with no-op default for Phase 21 D-04 compliance"
  - "speak_power_restored TTS utterance"
affects: [15-02-thermal-monitor, 15-03-ring-buffer, 15-05-dashboard-sse-and-frontend]

# Tech tracking
tech-stack:
  added: []  # Pure stdlib + existing project deps (structlog, pytest)
  patterns:
    - "Module-level GIL-atomic rebind for alert sustain state (mirrors hardware/state.py)"
    - "Separate active_sustain_count + clear_sustain_count counters to keep fire_alert and fire_recovery independent (Pitfall 2: sticky-bit recovery)"
    - "recovery_subtype kwarg on fire_recovery rewrites emitted subtype while bookkeeping stays on base key"
    - "Optional[Callable] TTS with _safe_tts wrapper: None short-circuits, exceptions swallowed and logged (Phase 21 D-04)"
    - "Graceful-degradation import of dashboard_push_event behind try/except ImportError"

key-files:
  created:
    - "src/shitbox/health/alerts.py"
    - "tests/test_alerts.py"
  modified:
    - "src/shitbox/capture/speaker.py"

key-decisions:
  - "AlertStatus uses TWO sustain counters (active_sustain_count + clear_sustain_count) rather than one, so an active-then-clear transition mid-sustain does not collapse recovery tracking (Pitfall 2)"
  - "_safe_tts wrapper short-circuits on None and catches exceptions — the helper never refuses to fire because TTS is absent or broken"
  - "recovery_subtype passed as kwarg to fire_recovery rather than a separate function — keeps one sustain machine per base subtype while allowing the frontend to branch on _CLEARED/_RESTORED suffix"
  - "dashboard_push_event imported as the bound name (not push_event) so tests can patch 'shitbox.health.alerts.dashboard_push_event' without reaching into the SSE module"
  - "Module docstring names all owned subtypes explicitly (UNDERVOLTAGE, UNDERVOLTAGE_CLEARED, CAPTURE_FAILURE, CAPTURE_RESTORED, CAPTURE_DOWN) so 15-02/15-03/15-05 callers have a single reference"

patterns-established:
  - "fire_alert/fire_recovery called every cycle — the helper owns the state machine; callers do not pre-gate on transitions"
  - "ALERT payload shape locked at four scalar keys (type, subtype, message, ts) — recovery events reuse the same channel (D-05)"
  - "Test pattern: autouse fixture calling alerts.clear_state() before and after every test keeps module-level state hermetic"

requirements-completed: [PWR-02, MON-03]

# Metrics
duration: 3min
completed: 2026-04-24
---

# Phase 15 Plan 01: Alerts Helper Summary

**Module-level sustain + transition + recovery helper with independent active/clear counters, Optional tts_fn, and recovery_subtype rewrite — locked down by 10 unit tests.**

## Performance

- **Duration:** ~3 min (173 s, three tasks TDD)
- **Started:** 2026-04-24T06:43:37Z
- **Completed:** 2026-04-24T06:46:30Z
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- Shared alert helper shipped as the Wave 0 seam for 15-02/15-03/15-05. Three downstream plans can now import `fire_alert` and `fire_recovery` instead of each re-implementing sustain counting.
- Pitfall 2 (sticky-bit recovery never firing) closed by keeping active and clear sustain counters separate on `AlertStatus` instead of collapsing to one counter.
- Phase 21 D-04 ("never refuse boot") honoured at two levels: graceful `try/except ImportError` for `dashboard_push_event`, and `Optional[Callable]` tts_fn with `_safe_tts` swallowing exceptions.
- `speak_power_restored` TTS utterance added, style-matched to `speak_thermal_recovered` so the voice stays consistent.
- Capture-path-sacred rule (Phase 10 D-02) enforced in test: `test_no_lock_on_alerts_module` asserts no `Lock` substring appears in either fire_alert or fire_recovery source.

## Task Commits

Each task committed atomically with `--no-verify` (parallel worktree):

1. **Task 1: Create alerts.py helper** — `9dfc9d3` (feat)
2. **Task 2: Add speak_power_restored TTS utterance** — `e38abd7` (feat)
3. **Task 3: Write tests/test_alerts.py** — `3e623d9` (test)

Metadata commit for SUMMARY.md will follow this write (parallel worktree mode — executor commits summary, orchestrator handles STATE/ROADMAP).

## Files Created/Modified

- `src/shitbox/health/alerts.py` (NEW) — module-level GIL-atomic rebind of a `Dict[str, AlertStatus]` keyed on subtype; exposes `fire_alert`, `fire_recovery` (with `recovery_subtype` kwarg), `snapshot`, `clear_state`, `AlertStatus`
- `src/shitbox/capture/speaker.py` (MODIFIED) — appended `speak_power_restored` after `speak_under_voltage`, style-matched to `speak_thermal_recovered`
- `tests/test_alerts.py` (NEW) — 10 unit tests covering sustain + once-on-transition, once-on-recovery, recovery_subtype rewrite, sustain reset on break, snapshot shape, recovery-before-fire no-op, no-lock invariant, broken-TTS resilience, None tts_fn, sustain_required=1 immediate fire

## Decisions Made

- **Independent sustain counters on AlertStatus.** One active_sustain_count for `fire_alert`, one clear_sustain_count for `fire_recovery`. Collapsing to a single signed counter was considered and rejected because a mid-sustain active-then-clear blip would zero the counter and prevent the eventual recovery from firing.
- **recovery_subtype as kwarg, not a separate function.** `fire_recovery_cleared` would have duplicated the entire state machine. Kwarg keeps one state machine per base subtype and lets the helper emit the `_CLEARED`/`_RESTORED` suffix exactly when the frontend needs it for the green branch.
- **Structured `log.exception` inside broad try/except.** Both `fire_alert` and `fire_recovery` wrap their whole body in try/except to guarantee Phase 21 D-04 compliance (never propagate into the caller). The structured log line preserves diagnosability without forcing the daemon to swallow the exception silently.
- **Test module imports inside each test function** (rather than module-level). Keeps import ordering explicit so the autouse fixture can reset state even if pytest reorders test execution.

## Deviations from Plan

None — plan executed exactly as written. Plan text already contained the full module body; implementation matches the plan's `<action>` block line-for-line except for one cosmetic line-length wrap on a test docstring (caught by ruff pre-commit check, fixed in the same commit before staging).

## Issues Encountered

- **Pre-existing mypy error in `src/shitbox/utils/logging.py:53`** (`Returning Any from function declared to return "BoundLogger"`). Flagged by `mypy src/shitbox/health/alerts.py` because mypy walks imports. Not caused by this plan; out of scope per executor scope-boundary rule. Logged here so 15-02 is not surprised. `alerts.py` itself is mypy-clean (zero errors in the new file).
- **ruff E501** on the `test_fire_recovery_emits_with_recovery_subtype` docstring (102 chars). Fixed by shortening the docstring to fit under 100 chars; no behavioural impact.
- **Executor hook prompt on Edit tool** (`READ-BEFORE-EDIT REMINDER`) triggered twice on files created earlier in the same session (speaker.py, test_alerts.py). Edits landed successfully in both cases; verified by grep after each. Not a real blocker — noted for awareness.

## Threat Surface Review

All mitigations from the plan's `<threat_model>` landed in code:

- **T-15-01-01 (DoS via Lock on capture path):** enforced by `test_no_lock_on_alerts_module` which greps the source of both fire functions.
- **T-15-01-02 (DoS via broken TTS):** `_safe_tts` wrapper; locked down by `test_fire_alert_with_broken_tts_never_raises` and `test_fire_alert_with_tts_fn_none_never_raises`.
- **T-15-01-03 (Dashboard import ordering race):** `try/except ImportError` around `dashboard_push_event` — helper importable with no dashboard wired.
- **T-15-01-04 (Info disclosure via ALERT payload):** payload is four scalar keys only (`type`, `subtype`, `message`, `ts`). Verified by `test_fire_alert_once_on_transition` assertions.
- **T-15-01-05 (Tampering via mutation of snapshot dict):** `AlertStatus` is `frozen=True, slots=True`; values are immutable. `snapshot()` docstring warns callers not to mutate.

No new threat surface introduced beyond what the plan catalogued.

## Next Phase Readiness

- Plan 15-02 can now import `from shitbox.health.alerts import fire_alert, fire_recovery` in `thermal_monitor.py` and `from shitbox.capture.speaker import speak_power_restored` for the recovery tts_fn.
- Plan 15-03 can wire `fire_alert("CAPTURE_FAILURE", ...)` / `fire_alert("CAPTURE_DOWN", ...)` / `fire_recovery("CAPTURE_FAILURE", ..., recovery_subtype="CAPTURE_RESTORED")` into `ring_buffer._health_monitor()`.
- Plan 15-05 can call `alerts.snapshot()` from `_system_conditions_payload()` in `sse.py` — the `AlertStatus.active`, `AlertStatus.fired`, and `AlertStatus.last_change_ts` fields are the source of the `active`/`recovering`/`restored`/`clear` state the frontend renders.
- No blockers. Wave 1 can proceed with 15-02, 15-03, 15-04 in parallel.

## Self-Check: PASSED

- File `src/shitbox/health/alerts.py` — FOUND
- File `src/shitbox/capture/speaker.py` (modified) — FOUND
- File `tests/test_alerts.py` — FOUND
- Commit `9dfc9d3` (Task 1) — FOUND
- Commit `e38abd7` (Task 2) — FOUND
- Commit `3e623d9` (Task 3) — FOUND
- `pytest tests/test_alerts.py -x -q` — 10 passed
- `ruff check src/shitbox/health/alerts.py src/shitbox/capture/speaker.py tests/test_alerts.py` — clean
- `mypy src/shitbox/health/alerts.py` — zero errors in alerts.py (one pre-existing error in utils/logging.py out of scope)

---
*Phase: 15-undervoltage-and-monitoring*
*Completed: 2026-04-24*
