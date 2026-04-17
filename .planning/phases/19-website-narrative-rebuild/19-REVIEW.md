---
phase: 19-website-narrative-rebuild
status: issues_found
depth: standard
files_reviewed: 4
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
---

# Phase 19 Code Review

Files reviewed:

- `src/shitbox/storage/route.py`
- `src/shitbox/events/engine.py` (RouteStorage wiring section)
- `tests/test_route_storage.py`
- `tests/test_capture_sync_generators.py`

## Findings

### WR-01 — `generate_route_json` uses a write transaction for a pure SELECT

**File:** `src/shitbox/storage/route.py:119`
**Severity:** warning

`generate_route_json` wraps its SELECT query with `self.db.transaction()`. By convention in this codebase, `transaction()` acquires a write lock (SQLite WAL deferred transaction that upgrades on first write). For a read-only query this is harmless in WAL mode but it unnecessarily contends with the telemetry write path. If `database.py` exposes a read-only connection path, the SELECT should use it. If not, a comment explaining the intent would reduce confusion.

---

### WR-02 — `_json_generators` dict is not thread-safe for post-start registration

**File:** `src/shitbox/sync/capture_sync.py:48,56,67`
**Severity:** warning

`_json_generators` is a plain `dict`. Generators are registered from the engine's main thread via `register_json_generator()`, and iterated from the background sync thread in `_run_json_generators()`. The current wiring in `engine.py` always registers before calling `start()`, so in practice this is safe. However, there is no documented or enforced ordering requirement, and nothing prevents a future caller registering a generator after `start()`. Under CPython the GIL makes concurrent dict mutation detectable but not crash-safe; under free-threaded Python 3.13+ or PyPy this would be a data race. The dict should either be protected by a lock, or the docstring should explicitly state that `register_json_generator` must only be called before `start()`.

---

### WR-03 — `test_size_budget` inserts 504,000 rows in individual transactions

**File:** `tests/test_route_storage.py:136-148`
**Severity:** warning

The `test_size_budget` test loops 14 days * 36,000 points = 504,000 iterations, each wrapped in a separate `db.transaction()`. SQLite commits to disk on every transaction. On a laptop with an SSD this might be tolerable but will be slow (likely 30+ seconds); on CI with emulated storage it may time out or cause flakey runs. The loop should batch-insert using `executemany` inside a single transaction, which would reduce runtime by two orders of magnitude and is more representative of actual write behaviour anyway.

---

### IR-01 — `RouteStorage` instantiated unconditionally regardless of `capture_sync` state

**File:** `src/shitbox/events/engine.py:570`
**Severity:** info

`self.route_storage = RouteStorage(self.database)` is created unconditionally, but the generator is only registered when `self.capture_sync is not None`. When capture sync is disabled (e.g., in the field without uplink or with `capture_sync_enabled: false`), `route_storage` sits as an unused object. The pattern is inconsistent with how other conditional services are handled in the engine. Not a bug, but it reads as though someone will later add a REST endpoint for route data -- if that is not planned, the instantiation should be gated on `self.capture_sync is not None` for clarity.

---

### IR-02 — Hardcoded UTC+10 offset silently misfires outside QLD

**File:** `src/shitbox/storage/route.py:15,82-88`
**Severity:** info

`_SYDNEY_OFFSET_HOURS = 10` and the associated comment acknowledge that QLD (no DST) and NSW (which observes AEDT, UTC+11 Oct-Apr) are conflated. During AEDT season, a reading timestamped at e.g. `2026-01-01T13:00:00Z` (midnight in QLD, 00:00) would be `23:00` local in AEDT, placing it in the previous calendar day. For the current use case (QLD rally) this is correct. The risk is silent miscategorisation if the car ever operates in NSW, VIC, or ACT without a config change. The comment should be promoted to a more prominent warning, or `tolerance_m` should have a companion `utc_offset_hours` constructor parameter to make the assumption visible at the call site.

---

### IR-03 — `generate_route_json` loads all GPS rows into memory at once

**File:** `src/shitbox/storage/route.py:120-125`
**Severity:** info

The query fetches every GPS reading for the full history of the database via `fetchall()` with no LIMIT or date bounding. At 1 Hz GPS over a 14-day rally, that is roughly 504,000 rows held in memory simultaneously before the Douglas-Peucker pass. The `test_size_budget` test confirms the output JSON fits in 1 MB after simplification, but the in-memory row list before simplification is considerably larger. On a Pi 4 with 4 GB RAM this is not immediately dangerous, but it will grow with each campaign. Consider streaming by day (query one day at a time) or adding a configurable lookback window (e.g., last N days) to bound memory use.
