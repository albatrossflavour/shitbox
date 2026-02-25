# Phase 1: Boot Recovery - Research

**Researched:** 2026-02-25
**Domain:** SQLite durability, crash detection, startup recovery, Python threading
**Confidence:** HIGH

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Shutdown Detection**

- Infer crash state from SQLite, not a separate flag file or PID check
- Indicators: open/unclosed events in the database, WAL file state
- No separate "running" sentinel file — keep it simple, use what SQLite already provides

**Recovery Behaviour**

- Orphaned events: close and mark as "interrupted" — partial data is better than none
- SQLite integrity failure: log the result and continue — start a fresh DB if needed, never block startup
- Partial video files: keep whatever ffmpeg managed to write — partial video is still useful
- Prometheus sync cursor: trust it after crash — accept possible small gap rather than re-syncing
- Philosophy: capturing new data is always more important than recovering old data perfectly

**Startup Sequence**

- Target: under 60 seconds from power-on to capturing data
- Recovery checks (integrity check, orphan cleanup) run in a background thread — do not block data capture
- Preserve the existing 20-second GPS wait (maximum) — this ensures early videos have GPS data and system clock is synced from GPS
- No BOOT events in events.json — boots are not driving events

**Failure Visibility**

- Detailed structured logs for every recovery action: which events were closed, integrity check result, WAL state, actions taken
- OLED display shows recovery status ("Recovered from crash", count of closed events) until GPS fix is acquired, then switches to normal display
- Buzzer patterns: single short beep on clean boot, double beep on crash recovery — audibly distinct
- Prometheus metric: increment a crash_recovery counter so recovery history is visible in Grafana

**SQLite Durability**

- Configure `synchronous=FULL` to ensure WAL writes survive hard power cuts
- This is the primary defence against data corruption since there is no graceful shutdown mechanism

### Claude's Discretion

- Exact integrity check implementation (full `PRAGMA integrity_check` vs lighter `PRAGMA quick_check`)
- Background thread implementation details for recovery
- How to detect WAL state indicating prior crash
- Prometheus metric naming and labels

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BOOT-01 | System runs SQLite `PRAGMA integrity_check` after detecting unclean shutdown | WAL file presence is a reliable crash indicator; `quick_check` recommended for speed; run in background thread |
| BOOT-02 | System closes orphaned events from prior crash and marks them as interrupted on boot | EventStorage uses JSON files per event; scan for events with no `end_time` or with a sentinel status field |
| BOOT-03 | SQLite configured with `synchronous=FULL` for WAL durability across hard power cuts | Verified: WAL + `synchronous=FULL` prevents lost committed transactions on power loss on Linux |

</phase_requirements>

## Summary

This phase hardens the Shitbox system against the inevitable hard power cuts (2-4 per day) from the cigarette lighter cutting immediately on ignition off. The three requirements are straightforward but must be woven into the existing `UnifiedEngine` startup sequence without blocking the 60-second capture readiness target.

The current codebase has `synchronous=NORMAL` in `database.py` — this is the most critical gap to fix. With WAL + `synchronous=NORMAL`, committed transactions can be rolled back on power loss because WAL writes are only flushed at checkpoint boundaries. Changing to `synchronous=FULL` adds a sync after every transaction commit, making all committed writes durable at the cost of one fsync per transaction. On a Raspberry Pi writing 1 Hz telemetry readings, this is negligible overhead.

Crash detection uses the WAL file's persistence as a signal: if `/var/lib/shitbox/telemetry.db-wal` exists at startup, the previous shutdown was unclean. Orphaned event recovery targets the `EventStorage` JSON files — events that were being written at crash time may have no `end_time` field or be structurally incomplete. Recovery runs in a background thread so the main data path (IMU sampling, GPS) starts immediately.

**Primary recommendation:** Change `synchronous=NORMAL` to `synchronous=FULL` in `database.py._get_connection()`, add a `BootRecoveryService` that runs on startup in a daemon thread, and add two new buzzer patterns and an OLED recovery state.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` | stdlib | Database operations including PRAGMAs | Already in use; no new dependency |
| `threading` | stdlib | Background recovery thread | Already used throughout the engine |
| `pathlib.Path` | stdlib | WAL file existence check | Already used throughout the codebase |
| `structlog` | `>=24.0.0` | Structured recovery logging | Already used; project convention |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` | stdlib | Read/write event JSON metadata | EventStorage already uses it; orphan recovery needs it |
| `time` | stdlib | Startup timing for 60s gate | Already used in engine |

### No New Dependencies Required

All recovery work uses Python stdlib and existing project libraries. No new packages needed.

**Installation:** None required.

## Architecture Patterns

### Recommended Project Structure

```
src/shitbox/
├── storage/
│   └── database.py         # BOOT-03: change synchronous=NORMAL → FULL
├── events/
│   ├── engine.py           # Wire BootRecoveryService; add OLED/buzzer recovery state
│   └── storage.py          # Add close_orphaned_events() method
└── sync/
    └── boot_recovery.py    # NEW: BootRecoveryService (daemon thread)
```

### Pattern 1: WAL File as Crash Indicator

**What:** Check for `{db_path}-wal` existence before the first `Database.connect()` call. If it exists, the previous shutdown was unclean. This is reliable because SQLite only removes the WAL file on clean connection close; after a hard power cut it will always persist.

**When to use:** At engine startup, before `database.connect()` is called.

**Example:**

```python
# Source: SQLite official docs - https://sqlite.org/wal.html
def detect_unclean_shutdown(db_path: Path) -> bool:
    """WAL file persists after unclean shutdown; SQLite only removes it on clean close."""
    wal_file = Path(str(db_path) + "-wal")
    return wal_file.exists()
```

**Important caveat:** SQLite automatically incorporates (replays) WAL content on next open —
this is not corruption recovery, it is normal WAL behaviour. The WAL presence just signals
that we need to check for application-level orphans.

### Pattern 2: Background Recovery Thread

**What:** A `BootRecoveryService` that implements the project's daemon-thread pattern (matching `BatchSyncService`). It is started immediately after `database.connect()` and performs integrity check + orphan close without blocking the GPS wait or IMU startup.

**When to use:** Every boot. Detects clean/crash state and routes accordingly.

**Example:**

```python
# Follows BatchSyncService pattern from src/shitbox/sync/batch_sync.py
import threading
from pathlib import Path
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class BootRecoveryService:
    """Runs integrity check and orphan cleanup after unclean shutdown.

    Runs in a daemon thread so it does not block data capture startup.
    Sets self.recovery_complete event when done; callers can wait or
    proceed immediately.
    """

    def __init__(self, db: "Database", event_storage: "EventStorage") -> None:
        self.db = db
        self.event_storage = event_storage
        self.was_crash = False
        self.orphans_closed = 0
        self.integrity_ok = True
        self.recovery_complete = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="boot-recovery"
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            self._detect_and_recover()
        finally:
            self.recovery_complete.set()

    def _detect_and_recover(self) -> None:
        wal_path = Path(str(self.db.db_path) + "-wal")
        self.was_crash = wal_path.exists()

        if self.was_crash:
            log.info("crash_detected", wal_file=str(wal_path))
            self._run_integrity_check()
            self.orphans_closed = self.event_storage.close_orphaned_events()
            log.info(
                "crash_recovery_complete",
                integrity_ok=self.integrity_ok,
                orphans_closed=self.orphans_closed,
            )
        else:
            log.info("clean_boot_detected")
```

### Pattern 3: Orphaned Event Detection in EventStorage

**What:** Scan the event JSON directory for events that have no `end_time` field or are otherwise structurally incomplete. Write them back with `status: "interrupted"` and an `end_time` set to the file's mtime.

**When to use:** Called from `BootRecoveryService._detect_and_recover()`.

**Example:**

```python
# Add to src/shitbox/events/storage.py
def close_orphaned_events(self) -> int:
    """Close any events left open by a prior crash.

    Sets status='interrupted' and end_time to file mtime on any
    event JSON that is missing end_time.

    Returns:
        Number of events closed.
    """
    closed = 0
    for json_file in self.base_dir.rglob("*.json"):
        try:
            with open(json_file) as f:
                meta = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        if "end_time" not in meta or meta.get("status") == "open":
            # Use file mtime as best estimate of when crash occurred
            meta["end_time"] = json_file.stat().st_mtime
            meta["status"] = "interrupted"
            with open(json_file, "w") as f:
                json.dump(meta, f, indent=2)
            log.info(
                "orphaned_event_closed",
                file=str(json_file),
                type=meta.get("type"),
            )
            closed += 1

    return closed
```

### Pattern 4: PRAGMA quick_check (Claude's Discretion)

**Recommendation: use `quick_check` not `integrity_check`.**

`integrity_check` runs in O(N log N) time and verifies index consistency against table content. `quick_check` runs in O(N) time and skips the index-content cross-check. For crash recovery on an embedded system where the primary concern is WAL replay correctness (not index drift), `quick_check` is appropriate. SQLite's WAL replay mechanism is atomic — if the WAL was partially written, the incomplete transactions are simply not replayed. Index drift is extremely unlikely after a power cut; it requires logical bugs in the application, not storage failures.

```python
# Source: https://sqlite.org/pragma.html#pragma_quick_check
def run_integrity_check(self) -> bool:
    """Returns True if database passes quick_check."""
    conn = self.db._get_connection()
    cursor = conn.execute("PRAGMA quick_check")
    rows = [row[0] for row in cursor.fetchall()]
    ok = rows == ["ok"]
    if not ok:
        log.error("integrity_check_failed", errors=rows)
    else:
        log.info("integrity_check_passed")
    return ok
```

If `quick_check` returns anything other than `["ok"]`, log the errors and continue — per the locked decision, never block startup.

### Pattern 5: PRAGMA synchronous=FULL Change (BOOT-03)

**What:** Change the `_get_connection()` method in `database.py` to set `synchronous=FULL`.

**Current code (line 116):**

```python
self._local.conn.execute("PRAGMA synchronous=NORMAL")
```

**Replace with:**

```python
self._local.conn.execute("PRAGMA synchronous=FULL")
```

**Why this works:** In WAL mode with `synchronous=NORMAL`, SQLite only issues an `fsync` at checkpoint time. Transactions written to the WAL between checkpoints are not flushed to the OS and can be lost on power cut. With `synchronous=FULL`, SQLite issues an `fsync` after every WAL write, making every committed transaction durable. On Raspberry Pi OS (Linux), `fsync()` is real — unlike macOS where it is sometimes a no-op. No `fullfsync` setting is needed on Linux.

### Pattern 6: Buzzer Patterns (Claude's Discretion)

The existing `buzzer.py` has `beep_boot()` (three ascending tones). Add two new functions:

```python
def beep_clean_boot() -> None:
    """Single short tone: clean boot confirmed."""
    _play_async([(880, 200)], name="buzzer-clean-boot")


def beep_crash_recovery() -> None:
    """Double beep: crash was detected, recovery ran."""
    _play_async([(880, 200), (880, 200)], name="buzzer-crash-recovery")
```

Call `beep_crash_recovery()` instead of `beep_boot()` when `was_crash` is `True`.

**Note:** The existing `beep_boot()` (three ascending tones) already plays on every boot. The new single/double patterns are the recovery-specific signals that play *after* `beep_boot()` — once the recovery check completes.

### Pattern 7: Prometheus Crash Counter (Claude's Discretion)

**Metric name recommendation:** `shitbox_crash_recovery_total`

This follows Prometheus naming conventions: `{namespace}_{subsystem}_{name}_total` for counters.

The metric is written via `encode_remote_write()` at the end of each boot recovery run. It is a counter that increments by 1 on each crash boot (value 0 for clean boot, 1 for crash). Since Prometheus remote_write sends raw time series values (not increments), the metric should be a gauge with value `1` on crash, `0` on clean boot — or a counter that accumulates across restarts by reading the prior value from the DB first.

**Simplest approach (Claude's Discretion):** Write a gauge `shitbox_boot_was_crash` with value `1.0` if crash, `0.0` if clean. This avoids needing to persist a counter across restarts and is immediately visible in Grafana as a timeline of crash events.

```python
# In BootRecoveryService, after recovery completes:
metric_value = 1.0 if self.was_crash else 0.0
timestamp_ms = int(time.time() * 1000)
metrics = [
    (
        "shitbox_boot_was_crash",
        {"instance": "shitbox-car"},
        metric_value,
        timestamp_ms,
    )
]
```

This metric is sent via the existing `encode_remote_write()` + `requests.post()` path when connectivity is available. It does not need to go through `BatchSyncService` or the `readings` table — it can be a one-shot write in the recovery service.

### Anti-Patterns to Avoid

- **Blocking `start()` on recovery completion:** Recovery runs in a background thread. Do not call `recovery_service.recovery_complete.wait()` in the main startup sequence — let it run concurrently. The OLED recovery status can be shown based on the `was_crash` flag set before the thread starts.
- **Re-running integrity check on every boot:** Only run `quick_check` when `was_crash` is `True`. On clean boots it is unnecessary overhead.
- **Modifying the sync cursor during recovery:** The locked decision is to trust the Prometheus sync cursor after a crash. Do not reset it.
- **Deleting partial video files:** Keep them. The user decision is that partial video is still useful.
- **Raising exceptions from recovery that block engine start:** Wrap the entire recovery thread in a try/except that logs and sets `recovery_complete` even on failure.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WAL crash detection | Custom journal parsing | `Path(db_path + "-wal").exists()` | SQLite spec guarantees WAL persistence after unclean close |
| Database integrity check | Custom page scanner | `PRAGMA quick_check` | Comprehensive O(N) check covering all relevant failure modes |
| Durable writes | Custom fsync wrapper | `PRAGMA synchronous=FULL` | SQLite's built-in mechanism; handles all edge cases |
| Background startup work | `asyncio` or custom executor | `threading.Thread(daemon=True)` | Matches existing engine patterns; no new concurrency primitives |

**Key insight:** SQLite already solves WAL replay on next open automatically. The application only needs to handle the higher-level orphan problem (open events in JSON files) and set the correct PRAGMA for durability.

## Common Pitfalls

### Pitfall 1: synchronous=NORMAL Is Not Durable in WAL Mode

**What goes wrong:** Transactions committed between checkpoint intervals are lost on power cut. The WAL is in memory/OS cache, not on disk.

**Why it happens:** `synchronous=NORMAL` is the project's current setting (line 116 of `database.py`). It is the documented default for WAL mode performance, but it sacrifices durability.

**How to avoid:** Change to `synchronous=FULL` before any other recovery work.

**Warning signs:** After a power cut, the database opens cleanly (WAL replay works) but recent readings are missing from the `readings` table.

### Pitfall 2: WAL File Always Exists During Normal Operation

**What goes wrong:** Treating WAL file presence as always meaning a crash, when in fact SQLite keeps the WAL file open during normal operation. Between process starts, if the last process exited cleanly, the WAL file is removed.

**Why it happens:** The WAL file is present while any connection is open. After clean close, it is deleted. After unclean close (crash, power cut), it persists.

**How to avoid:** The detection logic only runs at startup, before `database.connect()` is called. At that point, if the WAL file exists, the last process did not close cleanly. This is correct.

**Warning signs:** False positives on clean boots if the check is done after `database.connect()` (which creates the WAL file).

### Pitfall 3: Event JSON Files May Be Partially Written

**What goes wrong:** An event JSON file may be written but truncated (crash mid-write), resulting in invalid JSON. `json.load()` will raise `JSONDecodeError`.

**Why it happens:** `open(json_path, "w")` followed by `json.dump()` is not atomic. A crash mid-write leaves the file with partial content.

**How to avoid:** The `close_orphaned_events()` method must wrap each file read in try/except for `JSONDecodeError` and `IOError`. Partially written files should be logged and skipped (or optionally deleted, since they cannot be recovered).

**Warning signs:** `JSONDecodeError` in recovery logs.

### Pitfall 4: OLED Recovery Status Needs to Be Set Before Thread Starts

**What goes wrong:** The OLED render loop reads `engine.get_status()` which returns a dict. If the recovery status is not in that dict, the OLED cannot display it.

**Why it happens:** `get_status()` currently does not have a recovery state field.

**How to avoid:** Set `was_crash` on the engine before the background thread starts. Add a `recovery_status` field to the engine's status dict that the OLED can read. The OLED should show the recovery state until the GPS fix is acquired (following the locked decision).

**Warning signs:** OLED shows normal status immediately without ever indicating recovery.

### Pitfall 5: Thread-Local Connections and Recovery Thread

**What goes wrong:** `Database._get_connection()` returns thread-local connections. The recovery thread will get its own connection — which is correct and safe — but it must not hold the connection open indefinitely after recovery completes.

**Why it happens:** Thread-local connections persist for the thread's lifetime. The daemon recovery thread exits after `_run()` completes, so the connection is released.

**How to avoid:** No special action needed — the thread exits after recovery, releasing its connection. But do not convert the recovery thread to a long-lived thread without adding connection close logic.

## Code Examples

### BOOT-03: Change synchronous=FULL in database.py

```python
# Source: https://sqlite.org/pragma.html#pragma_synchronous
# In Database._get_connection(), replace line 116:
# BEFORE:
self._local.conn.execute("PRAGMA synchronous=NORMAL")
# AFTER:
self._local.conn.execute("PRAGMA synchronous=FULL")
```

This is a one-line change. The PRAGMA is set per-connection on every new thread-local connection, so all threads get the correct setting automatically.

### BOOT-01: quick_check after crash detection

```python
# Source: https://sqlite.org/pragma.html#pragma_quick_check
# Returns list of strings; ["ok"] means pass
cursor = conn.execute("PRAGMA quick_check")
results = [row[0] for row in cursor.fetchall()]
integrity_ok = (results == ["ok"])
log.info(
    "quick_check_result",
    ok=integrity_ok,
    errors=results if not integrity_ok else [],
)
```

### Engine startup wiring

```python
# In UnifiedEngine.start(), after database.connect():
wal_exists_before_open = Path(str(self.database.db_path) + "-wal").exists()
# Note: check BEFORE database.connect() — connect() creates the WAL file

self.database.connect()

# Start recovery in background (does not block)
self.boot_recovery = BootRecoveryService(self.database, self.event_storage)
self.boot_recovery.was_crash = wal_exists_before_open  # Set immediately for OLED
self.boot_recovery.start()

# Continue with GPS init, IMU start, etc. — recovery runs concurrently
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `synchronous=NORMAL` (current) | `synchronous=FULL` (BOOT-03) | This phase | Commits durable across power cuts in WAL mode |
| No crash detection (current) | WAL file + orphan scan (this phase) | This phase | Automated recovery without manual intervention |
| `beep_boot()` on all boots (current) | Different tones: clean vs crash (this phase) | This phase | Audible crash history for the driver |

**Currently missing from codebase:**

- `BootRecoveryService` class (does not exist — must be created)
- `EventStorage.close_orphaned_events()` method (does not exist — must be added)
- `status` field in event JSON metadata (not written on save — check needed)
- `engine.get_status()` recovery fields (not present — must be added)
- `buzzer.beep_clean_boot()` and `buzzer.beep_crash_recovery()` (not present — must be added)

## Open Questions

1. **Does EventStorage write an `end_time` field today?**

   - What we know: `EventStorage.save_event()` calls `event.to_dict()` — need to check `Event.to_dict()` in `detector.py` to see if `end_time` is included.
   - What's unclear: If `end_time` is always written, orphan detection uses its absence. If it is never written, we need a different sentinel (e.g., a `status: "open"` field written at event-start, updated to `status: "complete"` at event-end).
   - Recommendation: Inspect `Event.to_dict()` in `detector.py` before implementing. Add `status: "open"` on initial write and `status: "complete"` on close if `end_time` is not reliable.

2. **Prometheus metric delivery timing**

   - What we know: The `BatchSyncService` only runs when `connection.is_connected` is `True`. A crash recovery boot may not have connectivity immediately.
   - What's unclear: Should the crash metric be sent immediately (one-shot at recovery time) or queued for the next sync window?
   - Recommendation: Enqueue it in the recovery service and let `BatchSyncService` pick it up, OR write it as a special one-shot send with a short timeout. Simplest approach: write a row to a `boot_events` table (or use a shared state dict on the engine) that `BatchSyncService` checks on its first successful sync. This is a planning detail.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest `>=7.0` (in `pyproject.toml` dev dependencies) |
| Config file | `pyproject.toml` (no `[tool.pytest]` section yet — uses defaults) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ --cov=shitbox` |
| Estimated runtime | ~5 seconds (pure unit tests, no hardware) |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| BOOT-03 | `database.py` sets `synchronous=FULL` on every new connection | unit | `pytest tests/test_database.py::test_synchronous_full -x` | No — Wave 0 gap |
| BOOT-01 | `quick_check` runs after crash detection, result logged | unit | `pytest tests/test_boot_recovery.py::test_integrity_check_on_crash -x` | No — Wave 0 gap |
| BOOT-01 | Clean boot skips integrity check | unit | `pytest tests/test_boot_recovery.py::test_no_integrity_check_clean_boot -x` | No — Wave 0 gap |
| BOOT-02 | Orphaned events (missing `end_time`) are closed and marked `interrupted` | unit | `pytest tests/test_boot_recovery.py::test_orphan_events_closed -x` | No — Wave 0 gap |
| BOOT-02 | Partially-written JSON (invalid JSON) is handled without crashing | unit | `pytest tests/test_boot_recovery.py::test_corrupt_json_handled -x` | No — Wave 0 gap |
| BOOT-01 | WAL file presence correctly detected as crash indicator | unit | `pytest tests/test_boot_recovery.py::test_wal_crash_detection -x` | No — Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `pytest tests/ -x -q`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~5 seconds

### Wave 0 Gaps (must be created before implementation)

- `tests/__init__.py` — package marker
- `tests/conftest.py` — shared fixtures: `tmp_path` DB, mock EventStorage, mock engine
- `tests/test_database.py` — covers BOOT-03 (synchronous=FULL PRAGMA verification)
- `tests/test_boot_recovery.py` — covers BOOT-01 and BOOT-02 (WAL detection, quick_check, orphan closure)

All tests are pure unit tests using `tmp_path` SQLite files — no hardware required.

## Sources

### Primary (HIGH confidence)

- `https://sqlite.org/wal.html` — WAL file persistence after unclean shutdown; automatic recovery on next open; WAL cleanup behaviour
- `https://sqlite.org/pragma.html#pragma_synchronous` — Exact `synchronous=FULL` vs `NORMAL` behaviour in WAL mode; fsync guarantees
- `https://sqlite.org/pragma.html#pragma_integrity_check` — `integrity_check` vs `quick_check` differences, return values, complexity

### Secondary (MEDIUM confidence)

- `https://avi.im/blag/2025/sqlite-fsync/` — Cross-referenced `synchronous=FULL` + WAL = durable on Linux (confirmed by official docs); macOS `fullfsync` caveat (not applicable on Pi/Linux)
- `https://www.agwa.name/blog/post/sqlite_durability` — Confirms NORMAL mode is not durable across power loss in WAL mode
- `https://prometheus.io/docs/practices/naming/` — Counter naming convention `_total` suffix

### Tertiary (LOW confidence)

- Community discussion on WAL file cleanup patterns — consistent with official docs, not independently verified

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all stdlib, all existing project dependencies
- Architecture: HIGH — WAL file detection and `quick_check` verified against official SQLite docs; patterns match existing codebase conventions
- Pitfalls: HIGH — `synchronous=NORMAL` gap confirmed by reading the code; thread-local connection behaviour confirmed by reading `database.py`

**Research date:** 2026-02-25
**Valid until:** SQLite docs are stable; valid indefinitely for these PRAGMA behaviours. Prometheus naming conventions — valid 90 days.
