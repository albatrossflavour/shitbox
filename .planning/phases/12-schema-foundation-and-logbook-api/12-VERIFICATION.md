---
phase: 12-schema-foundation-and-logbook-api
verified: 2026-04-09T12:43:40Z
status: human_needed
score: 8/9 must-haves verified
human_verification:
  - test: "Start engine on Pi or local uvicorn, open dashboard in browser. Click '+ Note', enter a note, click 'Save Note'. Then click '+ Fuel', enter a volume, click 'Log Fuel Stop'."
    expected: "Both modals open and close correctly, green confirmation badge appears for ~3s, rows land in telemetry.db (notes and fuel_stops tables). After a sync cycle, notes.json and fuel.json appear in the captures dir. fuel.json contains no cost_aud key."
    why_human: "Visual modal behaviour, ESC-to-close, live telemetry continuing behind the backdrop, and sync artefact inspection all require a running system. The test suite cannot exercise the Alpine.js frontend or the actual rsync pipeline."
---

# Phase 12: Schema Foundation and Logbook API Verification Report

**Phase Goal:** The Pi can record field notes and fuel stops via REST endpoints, with all new data landing in telemetry.db and the sync pipeline updated to export notes and fuel data (without cost fields) alongside events.

**Verified:** 2026-04-09T12:43:40Z
**Status:** human_needed (8/9 automated must-haves verified; 1 item requires human testing)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Fresh database on first connect contains `notes` and `fuel_stops` tables | VERIFIED | `test_v6_fresh_schema` passes; SCHEMA_SQL contains both CREATE TABLE IF NOT EXISTS statements |
| 2 | Existing v5 database migrates to v6 and gains both tables without data loss | VERIFIED | `test_v6_migration` passes; `_migrate_to_v6` branch at `current_version < 6` confirmed in database.py:194 |
| 3 | POST /api/notes persists a note row with GPS capture or staleness fallback | VERIFIED | `test_api_create_note_201`, `test_create_note`, `test_note_gps_stale` all pass; `_resolve_gps()` in logbook.py calls `get_last_known_position()` on no-fix path |
| 4 | POST /api/fuel persists a fuel_stops row | VERIFIED | `test_api_create_fuel_and_list`, `test_create_fuel_stop` pass; `create_fuel_stop` inserts with all required columns |
| 5 | GET /api/fuel returns per-stop km_per_litre and cumulative_km_per_litre | VERIFIED | `test_api_create_fuel_and_list` asserts cumulative=10.0; `test_fuel_efficiency` asserts per-stop and cumulative; `list_fuel_stops` calculates at query time |
| 6 | generate_fuel_json() output never contains a cost_aud key | VERIFIED | SELECT in `generate_fuel_json` (logbook.py:163) explicitly omits cost_aud; `test_fuel_json_no_cost` passes |
| 7 | CaptureSyncService.register_json_generator wires notes and fuel generators pre-rsync | VERIFIED | engine.py:546-547 registers both; `_do_sync_inner` calls `_run_json_generators()` as first line; Pass 1 rsync uses `--exclude=*.json` |
| 8 | UnifiedEngine updates gps_state on every valid GPS fix | VERIFIED | engine.py:1449-1450 calls `gps_state.update_last_known_position` inside the `latitude is not None and longitude is not None` guard |
| 9 | Dashboard modals open, POST to API, show success/error feedback, and allow live telemetry to continue | HUMAN NEEDED | index.html contains all required elements (`showNoteModal`, `showFuelModal`, both fetch calls, all UI-SPEC copy); correctness of modal UX, ESC-close, and success badge requires a running browser |

**Score:** 8/9 truths verified automatically

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/shitbox/storage/database.py` | SCHEMA_VERSION=6, notes+fuel_stops in SCHEMA_SQL, `_migrate_to_v6()` | VERIFIED | SCHEMA_VERSION=6 (line 16), both tables in SCHEMA_SQL (lines 98, 109), `_migrate_to_v6` method at line 280 |
| `tests/test_logbook.py` | 11 tests (7 storage + 4 HTTP), all passing | VERIFIED | 11 test functions present, all 11 passed in test run |
| `tests/test_capture_sync_generators.py` | 3 tests for registry, run, and failure isolation | VERIFIED | 3 tests, all passed |
| `tests/test_database.py` | `test_v6_fresh_schema` and `test_v6_migration` | VERIFIED | Both present and passing |
| `src/shitbox/storage/logbook.py` | LogbookStorage with create/list/generate methods | VERIFIED | Class confirmed at line 16 with all 6 required methods |
| `src/shitbox/dashboard/gps_state.py` | `update_last_known_position`, `get_last_known_position`, `clear_last_known_position` | VERIFIED | All three functions confirmed present |
| `src/shitbox/dashboard/logbook.py` | FastAPI router with POST /api/notes, POST /api/fuel, GET /api/fuel, GET /api/logbook/gps | VERIFIED | All 4 routes confirmed at lines 45, 51, 59, 65 |
| `src/shitbox/dashboard/server.py` | `build_app` and `build_dashboard_server` accept `logbook_storage=None` | VERIFIED | Kwarg present at lines 41 and 136; router included conditionally at lines 55-57 |
| `src/shitbox/sync/capture_sync.py` | `register_json_generator`, `_run_json_generators`, `_json_generators` dict, Pass 1 `--exclude=*.json` | VERIFIED | All confirmed: lines 48, 50, 59, 136, 167 |
| `src/shitbox/events/engine.py` | LogbookStorage instantiation, generator registration, GPS state update, logbook_storage kwarg forwarded | VERIFIED | All four wiring points confirmed: lines 544, 546-547, 624, 1450 |
| `src/shitbox/dashboard/static/index.html` | `+Note` and `+Fuel` buttons, two modals, Alpine state, fetch calls to all three API endpoints | VERIFIED | All elements confirmed; all 6 UI-SPEC copy strings present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `database.connect()` | `_migrate_to_v6` | `if current_version < 6` branch | WIRED | database.py:194 |
| `POST /api/notes` handler | `LogbookStorage.create_note` | module-level `_storage` set by `set_storage()` | WIRED | logbook.py:46, calls `_require_storage().create_note` |
| `LogbookStorage.create_note` | `get_last_known_position()` | GPS staleness fallback in `_resolve_gps` | WIRED | logbook.py:43, `_resolve_gps` calls `gps_state.get_last_known_position()` |
| `generate_fuel_json` | `fuel_stops` table | explicit SELECT column list excluding `cost_aud` | WIRED | logbook.py:163, column list confirmed cost_aud-free |
| `UnifiedEngine.__init__` | `LogbookStorage` + `register_json_generator` | startup wiring after storage construction | WIRED | engine.py:544-547 |
| `index.html + Note button` | `POST /api/notes` | Alpine fetch in `saveNote()` | WIRED | index.html, `fetch('/api/notes'` confirmed |
| `index.html + Fuel button` | `POST /api/fuel` | Alpine fetch in `saveFuel()` | WIRED | index.html, `fetch('/api/fuel'` confirmed |
| `engine GPS callback` | `gps_state.update_last_known_position` | inside existing lat/lng not-None guard | WIRED | engine.py:1449-1450 |
| `_do_sync_inner` | `_run_json_generators` | pre-rsync call as first line | WIRED | capture_sync.py:136 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `LogbookStorage.create_note` | `note_id`, returned dict | SQLite INSERT into `notes` via `db.transaction()` | Yes — real DB write, `lastrowid` returned | FLOWING |
| `LogbookStorage.generate_fuel_json` | `stops` list | `SELECT ... FROM fuel_stops` query | Yes — real DB read, explicit column list | FLOWING |
| `_run_json_generators` | `{name}.json` file | calls each registered Callable, writes `json.dumps(data)` | Yes — driven by real LogbookStorage generators | FLOWING |
| `index.html modal` | `gpsHasFix`, `gpsStaleMinutes` | `fetchGpsStatus()` fetches `/api/logbook/gps` on modal open | Yes — reads live snapshot and gps_state module | FLOWING (automated trace only; live behaviour is human-verified) |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SCHEMA_VERSION is 6 | `grep "SCHEMA_VERSION = 6" src/shitbox/storage/database.py` | Match found line 16 | PASS |
| Engine imports cleanly | `python -c "from shitbox.events.engine import UnifiedEngine"` | `import OK` | PASS |
| 19 phase 12 tests pass | `pytest tests/test_database.py tests/test_logbook.py tests/test_capture_sync_generators.py` | 19 passed | PASS |
| Full suite clean | `pytest tests/ -x --ignore=tests/test_hardware` | 185 passed, 1 pre-existing warning | PASS |
| cost_aud absent from generate_fuel_json SELECT | `grep -A 6 "def generate_fuel_json" ... \| grep SELECT` | SELECT omits cost_aud | PASS |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| NOTE-01 | 12-01, 12-02, 12-04 | User can compose a field note from the Pi UI with DTS and GPS auto-captured | SATISFIED | `notes` table created; `create_note` captures GPS at insert time; `/api/notes` endpoint confirmed; `+ Note` button and modal in index.html |
| NOTE-02 | 12-01, 12-02, 12-04 | User can optionally pin a field note to an existing event | SATISFIED | `notes.event_id` column in schema; `create_note(body, event_id=)` parameter; `test_note_event_pin` passes; `NoteRequest.event_id` optional field |
| FUEL-01 | 12-01, 12-02, 12-03, 12-04 | User can log a fuel stop with volume and location from the Pi UI | SATISFIED | `fuel_stops` table created; `create_fuel_stop` persists volume + GPS; `/api/fuel` POST endpoint; `+ Fuel` button and modal in index.html |
| FUEL-02 | 12-02, 12-04 | System calculates and tracks km/L per stop and running cumulative average | SATISFIED | `list_fuel_stops` computes at query time; `GET /api/fuel` returns `cumulative_km_per_litre`; `test_fuel_efficiency` and `test_api_create_fuel_and_list` both assert cumulative=10.0 |
| NOTE-03 | Not in scope for phase 12 | Field notes sync to website | ORPHANED to future phase | REQUIREMENTS.md maps this to a future phase, not phase 12 |
| FUEL-03 | Not in scope for phase 12 | Fuel data syncs to website map; cost never syncs | PARTIALLY ENABLED | sync mechanism (register_json_generator) and cost exclusion (generate_fuel_json) are complete; website consumption is a future phase |

No orphaned phase-12 requirements — NOTE-03 and FUEL-03 are explicitly unchecked in REQUIREMENTS.md and not claimed by any plan.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

No TODO/FIXME/placeholder comments, no empty returns, no hardcoded empty data flowing to render paths were found in the phase 12 artifacts. The `list_fuel_stops` return is populated from a real DB query. The `generate_fuel_json` SELECT list is non-empty and driven by real data.

---

### Human Verification Required

#### 1. End-to-end modal UX and sync artefact inspection

**Test:** Start the dashboard (`python -m shitbox.events.engine` on the Pi, or `uvicorn` locally). Open the dashboard in a browser. Click `+ Note`, enter text, click `Save Note`. Click `+ Fuel`, enter a volume, click `Log Fuel Stop`. Press ESC with a modal open. Confirm live telemetry kept updating throughout.

**Expected:**
- Both modals open with correct layout and GPS status line
- Successful save closes the modal and shows a green confirmation badge for ~3 seconds
- Rows appear in `notes` and `fuel_stops` tables in telemetry.db
- After a sync cycle, `notes.json` and `fuel.json` exist in the captures directory
- `fuel.json` contains no `cost_aud` key in any object
- ESC closes the open modal
- SSE telemetry (speed, temps, events) continues updating while a modal is open

**Why human:** Alpine.js reactivity, modal overlay rendering, ESC keydown event handling, and the success badge timeout are browser-side behaviours that cannot be exercised programmatically. The rsync pipeline and NAS filesystem inspection require a running Pi with network access.

---

### Gaps Summary

No automated gaps found. All four requirements are implemented and wired end-to-end. The single human verification item is a UX and integration check, not a code defect — the code paths for every behaviour are substantive and wired.

The one design note worth recording: plan 04 includes a checkpoint task (Task 3) marked `autonomous: false` with a human-verify gate. The summary documents this was "auto-approved per user instruction." The human verification listed above covers that outstanding checkpoint.

---

_Verified: 2026-04-09T12:43:40Z_
_Verifier: Claude (gsd-verifier)_
