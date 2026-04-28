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

## Wave 2 (Plan 28-04)

- **`src/shitbox/capture/ring_buffer.py:_read_stderr` silently loses
  data on a fully-drained non-blocking pipe.** Same root cause as the
  bug found and fixed in `src/shitbox/sync/tpms.py:_read_stderr_nonblocking`
  during Plan 28-04 verification. The inner `while True: chunk =
  os.read(fd, 4096)` loop has no `BlockingIOError` handler; on the
  iteration where the pipe is fully drained, `os.read` raises
  `BlockingIOError` (Python 3 documented behaviour for non-blocking
  pipes), the bare `except Exception: pass` swallows it, and the
  bytes already accumulated in `data` are lost — the function returns
  `""`.

  In production this rarely manifests because ffmpeg writes stats to
  stderr fast enough that the pipe always has data when the health
  monitor polls every 2s. The bug only surfaces if the helper is
  called against a pipe that was emptied between writes. Risk of
  losing useful diagnostic stderr context on a real ffmpeg failure
  exists but is small.

  Fix is mechanical: lift the BlockingIOError handler from the
  Plan 28-04 fix in `tpms.py:285-321` to `ring_buffer.py:827-846`.

  Out of scope for Plan 28-04 (TPMS-only); track for the next
  ring_buffer.py touch.
