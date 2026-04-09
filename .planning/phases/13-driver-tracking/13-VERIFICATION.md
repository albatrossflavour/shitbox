---
phase: 13-driver-tracking
verified: 2026-04-09T00:00:00Z
status: human_needed
score: 11/11 automated must-haves verified
human_verification:
  - test: "Open dashboard in browser, click the '---' driver label, verify stats modal opens"
    expected: "Modal opens with dropdown listing Tony, Steve, and '-- No driver --'"
    why_human: "Alpine.js rendering and modal interaction cannot be verified without a browser"
  - test: "Select a driver from the dropdown, confirm top-bar label updates live via SSE"
    expected: "Top bar shows 'Driver: Tony' within ~1 second of selection"
    why_human: "SSE live-update behaviour requires a running server and browser"
  - test: "Trigger a test event while a driver is active, inspect the saved JSON metadata"
    expected: "Event JSON file contains 'driver_name' key with the active driver's name"
    why_human: "Requires running daemon on Pi and a real or simulated capture event"
  - test: "Wait for a sync cycle and confirm driver-stats.json exists in captures dir"
    expected: "captures/driver-stats.json written with {active_driver, drivers: [...]}"
    why_human: "Requires live CaptureSyncService run; not testable without connected NAS or local rsync"
  - test: "POST /api/driver with invalid name via curl"
    expected: "Returns 422 with detail indicating name not in roster"
    why_human: "Verifiable with curl against a running instance; confirms roster enforcement end-to-end"
---

# Phase 13: Driver Tracking Verification Report

**Phase Goal:** Driver tracking — record who is driving at event-record time, expose driver stats via API, and show a switcher in the dashboard.
**Verified:** 2026-04-09
**Status:** human_needed (all automated checks pass; 5 items need live system verification)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Schema v7 migration creates `driver_stints` table with correct columns | VERIFIED | `_migrate_to_v7` present at line 317, wired at line 197; migration tests pass |
| 2  | SCHEMA_VERSION bumped to 7 and wired into `connect()` | VERIFIED | Line 16: `SCHEMA_VERSION = 7`; line 197–198: `if current_version < 7: self._migrate_to_v7(conn)` |
| 3  | `DriverStorage` class provides `set_driver`, `clear_driver`, `get_stats`, `get_driver_stats_payload` | VERIFIED | `src/shitbox/storage/driver.py` (95 lines), all four methods substantive |
| 4  | POST `/api/driver` closes previous stint atomically and opens new one | VERIFIED | `driver.py` router validates roster and calls `storage.set_driver()`; `test_stint_switch_closes_previous` passes |
| 5  | POST `/api/driver` with unknown name returns 422 | VERIFIED | Line 47–51 of `driver.py`; `test_set_driver_unknown_name` passes |
| 6  | GET `/api/driver/stats` returns per-driver time and percentage | VERIFIED | GET endpoint in `driver.py` returns `{active_driver, drivers, roster}`; `test_driver_stats` passes |
| 7  | Drivers roster loads from `config/config.yaml` | VERIFIED | `Config.drivers: List[str]` field at line 375 of `config.py`; loaded at line 520; `config.yaml` has Tony and Steve |
| 8  | Snapshot dict has `active_driver` key | VERIFIED | `snapshot.py` line 42: `"active_driver": None` |
| 9  | `save_event()` accepts `driver_name` kwarg and writes it into JSON metadata | VERIFIED | `storage.py` lines 81–106; `test_event_attribution` and `test_event_attribution_no_driver` pass |
| 10 | Engine wires active driver into every `save_event()` call at event-record time | VERIFIED | `engine.py` lines 1032 and 2020: `driver_name=driver_state.get_active_driver()` |
| 11 | `/sse/slow` payload includes `active_driver` field from snapshot | VERIFIED | `sse.py` line 141: `"active_driver": snap.get("active_driver")` |
| 12 | `driver-stats.json` generator registered with `CaptureSyncService` | VERIFIED | `engine.py` lines 557–561: `register_json_generator("driver-stats", self.driver_storage.get_driver_stats_payload)` |
| 13 | Dashboard top bar shows active driver label with stats modal and switcher | VERIFIED (grep) | `index.html` has `showDriverModal`, `openDriverModal`, `activeDriver`, `fetch('/api/driver/stats')`, `fetch('/api/driver'`, `-- No driver --`, `@keydown.escape.window`; old `Driver: ---` placeholder gone |

**Score:** 13/13 truths verified (5 require live system confirmation — see Human Verification section)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_driver.py` | 8 test stubs covering all DRVR cases | VERIFIED | 8 tests collected and passing |
| `src/shitbox/storage/database.py` | `_migrate_to_v7` + `SCHEMA_VERSION=7` | VERIFIED | Both present and wired |
| `src/shitbox/storage/driver.py` | `DriverStorage` with 4 methods | VERIFIED | 95 lines, all methods substantive |
| `src/shitbox/dashboard/driver_state.py` | Module-level active driver state | VERIFIED | 28 lines, `set/get/clear_active_driver` all present |
| `src/shitbox/dashboard/driver.py` | FastAPI router `/api/driver` and `/api/driver/stats` | VERIFIED | 64 lines, both endpoints substantive |
| `src/shitbox/dashboard/server.py` | `build_app` wires driver router | VERIFIED | Lines 61–66 include driver router when `driver_storage` provided |
| `src/shitbox/dashboard/snapshot.py` | `"active_driver": None` in default dict | VERIFIED | Line 42 confirmed |
| `src/shitbox/events/storage.py` | `save_event(driver_name=...)` kwarg | VERIFIED | Lines 81–106 add kwarg and conditional metadata write |
| `src/shitbox/events/engine.py` | `DriverStorage` instantiation + all wiring | VERIFIED | Lines 30, 42, 355, 556–561, 639–641, 805, 1032, 2020 |
| `src/shitbox/dashboard/sse.py` | `active_driver` in `/sse/slow` payload | VERIFIED | Line 141 confirmed |
| `src/shitbox/dashboard/static/index.html` | Driver top-bar + stats modal | VERIFIED (grep) | All required patterns present; placeholder gone |
| `config/config.yaml` | `drivers:` roster section | VERIFIED | Lines 235–238: `Tony`, `Steve` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `database.connect()` | `_migrate_to_v7` | `if current_version < 7` branch | WIRED | Lines 197–198 confirmed |
| `dashboard/driver.py` | `storage/driver.py` | `set_storage()` injector | WIRED | `set_storage` present; `server.py` calls it at include-router time |
| `dashboard/server.py` | `dashboard/driver.py` | `build_app` includes `driver_mod.router` | WIRED | Lines 61–66 of `server.py` |
| `events/engine.py` | `events/storage.py save_event` | `driver_name=driver_state.get_active_driver()` | WIRED | Two call sites at lines 1032 and 2020 |
| `events/engine.py` | `sync/capture_sync.py register_json_generator` | `"driver-stats"` generator | WIRED | Lines 557–561 of `engine.py`; `register_json_generator` takes `(name, fn)` matching the actual 2-arg signature |
| `dashboard/sse.py` | `snapshot active_driver` | SSE slow payload field | WIRED | Line 141 of `sse.py` |
| SSE slow handler | `activeDriver` Alpine state | `this.activeDriver = data.active_driver` | WIRED | `index.html` line 305: assignment present |
| `index.html` driver top-bar | POST `/api/driver` | `switchDriver()` with `fetch('/api/driver', ...)` | WIRED | `index.html` lines 437–444 |
| `index.html` stats modal | GET `/api/driver/stats` | `openDriverModal()` fetch | WIRED | `index.html` line 425 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `dashboard/driver.py GET /api/driver/stats` | `storage.get_stats()` | SQLite query via `DriverStorage.get_stats()` — COALESCE aggregation | Yes — DB query returns live rows | FLOWING |
| `index.html` driver label | `activeDriver` | SSE `active_driver` field populated from `snapshot.py` → `driver_state.get_active_driver()` → set by `DriverStorage.set_driver()` | Yes — set on DB write success | FLOWING |
| `events/storage.py` JSON metadata | `metadata["driver_name"]` | `driver_state.get_active_driver()` passed as kwarg from engine | Yes — conditional write when not None | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 8 driver tests pass | `pytest tests/test_driver.py -x` | 8 passed in 0.55s | PASS |
| Schema v7 migration tests pass | `pytest tests/test_database.py::test_migration_v7_creates_driver_stints tests/test_database.py::test_migration_v7_from_v6` | 2 passed | PASS |
| Full suite — no regressions | `pytest -q` | 196 passed, 1 warning (pre-existing uvicorn thread warning unrelated to Phase 13) | PASS |
| `driver-stats` generator registered with 2-arg API | `register_json_generator("driver-stats", fn)` matches `def register_json_generator(self, name: str, fn: Callable[[], Any])` | Signatures align | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DRVR-01 | 13-01, 13-02, 13-04 | User can set and change the active driver from the Pi UI | SATISFIED | POST `/api/driver` endpoint, roster validation, dashboard driver modal all implemented and tested |
| DRVR-02 | 13-01, 13-02, 13-04 | System tracks driving time and calculates percentage per driver across the rally | SATISFIED | `DriverStorage.get_stats()` with COALESCE for open stints; `test_driver_stats` and `test_driver_stats_open_stint` pass |
| DRVR-03 | 13-01, 13-03 | Driver attributed to events — who was driving when an event occurred | SATISFIED | `save_event(driver_name=...)` kwarg; engine passes `driver_state.get_active_driver()` at both call sites; `test_event_attribution` passes |
| DRVR-04 | Phase 18 | Website "who's in charge" widget | NOT THIS PHASE | Correctly deferred to Phase 18 |
| DRVR-05 | Phase 18 | Website per-driver stats | NOT THIS PHASE | Correctly deferred to Phase 18 |

No orphaned requirements: DRVR-01, DRVR-02, DRVR-03 all claimed by Phase 13 plans and verified.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

No TODOs, FIXMEs, stubs, or hardcoded empty returns in any modified file. All return paths produce real data.

### Human Verification Required

#### 1. Driver modal opens and renders correctly

**Test:** Open dashboard in browser, click the `---` driver label in the top bar.
**Expected:** Stats modal opens; dropdown lists "-- No driver --" plus configured roster names; stats table is empty before any stints.
**Why human:** Alpine.js `x-show`/`x-for` rendering and click handler behaviour cannot be verified without a browser runtime.

#### 2. SSE live-update of active driver

**Test:** Select "Tony" from the dropdown in the modal while the daemon is running.
**Expected:** Top bar updates from `---` to `Tony` within ~1 second via SSE without a page reload.
**Why human:** Requires a running server and browser with SSE connection open.

#### 3. Event attribution in JSON metadata

**Test:** With Tony set as active driver, trigger a capture event (GPIO button or simulated high-G). Then `cat captures/<date>/<event>.json | jq .driver_name`.
**Expected:** Output is `"Tony"`.
**Why human:** Requires running daemon on Pi and actual event capture.

#### 4. driver-stats.json written on sync cycle

**Test:** After setting a driver and waiting for a sync cycle (or forcing one), check for `captures/driver-stats.json`.
**Expected:** File exists and contains `{"active_driver": "Tony", "drivers": [...]}`.
**Why human:** `CaptureSyncService` only writes generators before rsync, which requires connectivity or manual trigger.

#### 5. Roster enforcement end-to-end

**Test:** `curl -X POST http://localhost:8000/api/driver -H 'Content-Type: application/json' -d '{"name":"Mallory"}'`
**Expected:** HTTP 422 with detail about name not being in roster.
**Why human:** Confirms the roster loaded from `config.yaml` is actually enforced at runtime, not just in tests.

### Notes

One naming deviation between plan and implementation: Plan 13-02 specified `drivers_roster` as the `build_dashboard_server` kwarg name; implementation uses `drivers` throughout (`build_app`, `build_dashboard_server`, engine call site). This is internally consistent — all three points use `drivers` — so the wiring is correct. The plan name was the deviation, not the code.

The `register_json_generator` plan spec listed a 3-argument call with a `filename` third argument. The actual Phase 12 implementation takes only `(name, fn)` and derives the filename as `{name}.json`. The engine correctly calls the 2-argument form. No issue; plan was slightly ahead of the actual API surface.

---

_Verified: 2026-04-09_
_Verifier: Claude (gsd-verifier)_
