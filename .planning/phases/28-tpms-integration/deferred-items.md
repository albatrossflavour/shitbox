# Phase 28 — Deferred Items

Pre-existing issues found during execution that are out-of-scope for the
current plan (Rule: scope boundary — only fix issues directly caused by the
current task's changes).

## Wave 0 (Plan 28-01)

- **`tests/test_dashboard.py` ruff failures** — 11 pre-existing ruff errors
  (`I001` import sort, `F841` unused variable `last_srv`, `E741` ambiguous
  `l`, `F401` unused `TestClient`, `E501` line too long ≥3 places). These
  predate Plan 28-01; my added `test_tpms_payload_four_wheels` and
  `test_tpms_payload_no_data` blocks are ruff-clean. Plan 28-05 (which
  wires `_tpms_payload` into sse.py and will edit test_dashboard.py
  again) is the natural place to clean these up, OR a standalone
  housekeeping commit.

  Verification command:
  ```
  ruff check tests/test_dashboard.py
  ```

  Lines flagged:
  - 70, 141, 145, 259, 274 — I001 import-sort violations
  - 157 — F841 unused `last_srv`
  - 214, 233 — E741 ambiguous `l` lambda variable
  - 242 — F401 unused `TestClient` import
  - 359, 364, 367 — E501 long lines (path string + assertion message)
