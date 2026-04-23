# Phase 27 Deferred Items

Items discovered during Phase 27 execution that are out of scope for the current plan but worth tracking for later.

## Pre-existing lint errors on `main` (discovered during Plan 27-01)

Discovered when Plan 27-01 Task 2 acceptance criteria asked for `ruff check src/` to be clean. These 11 errors exist on the plan base commit `ec83ff2` before any Phase 27 work touched the tree, so they're out of scope for this plan.

- `src/shitbox/collectors/light.py:10` — F401 unused `SensorType` import
- `src/shitbox/collectors/light.py:19` — I001 import block un-sorted
- `src/shitbox/events/engine.py:627,628,995,1040,1041,1887` — E501 line too long (102–105 chars, limit 100)
- `src/shitbox/storage/logbook.py:2` — I001 import block un-sorted
- `src/shitbox/storage/logbook.py:24` — E501 line too long (105)
- `src/shitbox/sync/capture_sync.py:6` — F401 unused `time` import

Four of these are `--fix`-able. Suggested follow-up: a small `chore(lint)` sweep on `main`, independent of Phase 27's scope.

Plan 27-01 itself does not introduce any new lint errors — it only touches `pyproject.toml` (TOML, not ruff-scoped) and `tests/test_capture_title_card.py` (which is lint-clean in the committed form).
