---
phase: 26-event-video-title-cards
reviewed: 2026-04-23T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - src/shitbox/capture/ring_buffer.py
  - src/shitbox/events/engine.py
  - tests/test_ring_buffer_slate.py
  - tests/test_engine_slate_wiring.py
  - tests/test_poster_delivery_integration.py
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 26: Code Review Report (re-review after gap-closure plan 26-05)

**Reviewed:** 2026-04-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Plan 26-05 restructures the poster handoff so the slate PNG now outlives the per-save tmp dir. The PNG is relocated to `buffer_dir/pending_slates/<save_id>.png` inside `_do_save_event` *before* the `finally` rmtree runs, the save callback is extended to a 3-arg shape `(output_path, clip_start_mtime, poster_path)`, and the engine stashes the stable path in a lock-protected `_event_poster_paths` dict which `_check_post_captures` then consumes and renames into the per-day events dir. A new `_cleanup_pending_slates` startup sweep drains orphans from prior crashes.

The CR-01 race is closed, and WR-01/WR-02 from the prior review are both addressed — the callback annotation is now accurate at both the public and internal boundaries, and cross-thread `_pending_slate_png` reads from the engine are gone (the integration test `test_check_post_captures_does_not_touch_pending_slate_png` actively enforces this).

The delta is small and the integration test `test_poster_survives_rmtree_and_appears_in_events_json` exercises the full race path. Three issues remain:

1. **WR-01** — The startup sweep's guard logic is wrong. At start(), `_save_counter == 0`, so numeric orphan PNGs from prior runs (`5.png`, `12.png`, etc.) can never satisfy `save_id_from_name < _save_counter` and will *never* be removed. The sweep only works for non-numeric names, defeating its stated purpose.
2. **WR-02** — If `_on_video_complete` fires late (after `_check_post_captures` has already run for the same event), the poster is stashed in `_event_poster_paths` but never consumed — both the dict entry leaks forever, and the PNG stays stranded in `pending_slates/` because the rename-into-day-dir step only happens in `_check_post_captures`.
3. **WR-03** — `shutil.move` across filesystems can fall back to copy+unlink and can succeed partially. The current `OSError` catch covers the common case but doesn't explicitly reason about same-filesystem-only usage (buffer_dir and pending_slates share a parent, so it's fine in practice — worth a comment).

Info items are about test scaffolding (`test_ring_buffer_slate.py` has a dead `if False` and a no-op `_caplog_context` shim) and a couple of carry-overs from the prior review that weren't in 26-05's scope.

## Warnings

### WR-01: `_cleanup_pending_slates` guard logic prevents startup sweep from removing numeric orphans

**File:** `src/shitbox/capture/ring_buffer.py:1677-1710`

**Issue:** The sweep gates each removal on `if mtime_ok and id_ok`, where:

- `mtime_ok = entry.stat().st_mtime < self._process_start_time`
- `id_ok = int(entry.stem) < self._save_counter` (falls back to `True` on non-numeric names)

The sweep is called from `start()` at line 190, immediately after `self._process_start_time = time.time()` on line 189. At that point `self._save_counter == 0` (it's incremented on every `_do_save_event`, which can only run after `start()` returns).

For a legitimate orphan file from a prior run, say `5.png`:

- `mtime_ok` → `True` (file was written before this process started)
- `id_ok` → `5 < 0` → `False`
- `mtime_ok and id_ok` → `False` → **file is NOT removed**

Every numeric-named PNG from a crashed prior run survives the sweep. Only unrecognised-name files get cleaned. The test `test_cleanup_pending_slates_removes_old_files` passes because it explicitly sets `_save_counter = 10` — a state the real startup sequence never reaches before the sweep runs.

Net effect: `pending_slates/` accumulates PNGs over time across restarts. On a Pi with a tmpfs buffer this resets at boot, so on a real rally it's mostly a cosmetic leak. On any system where `buffer_dir` is persistent (dev laptop, NAS mount) it's unbounded growth.

**Fix:** The intent is "anything that predates this process is an orphan, regardless of its numeric save_id" — drop the `id_ok` check at startup and gate purely on mtime. The in-run race the comment calls out (save_event firing before start() completes) is impossible by construction: `save_event` is only reachable once the engine has been built and has called `start()`, and `_save_counter` isn't used for filename collision prevention either way (only the save_id from the save-in-flight ever writes). The simpler correct rule:

```python
def _cleanup_pending_slates(self) -> None:
    """Remove PNGs left over from crashed prior runs.

    Any file whose mtime predates this process's start is an orphan by
    definition — save_event cannot fire until start() returns, so an
    in-run writer will always produce mtime > process_start_time.
    """
    try:
        entries = list(self._pending_slates_dir.iterdir())
    except FileNotFoundError:
        return
    removed = 0
    for entry in entries:
        try:
            if not entry.is_file():
                continue
            if entry.stat().st_mtime < self._process_start_time:
                entry.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        log.info("pending_slates_swept", removed=removed)
```

And update `test_cleanup_pending_slates_removes_old_files` to stop relying on `_save_counter = 10` as the unlock — set `_save_counter = 0` so the test reflects real startup conditions.

### WR-02: Late `_on_video_complete` leaks stashed poster and never emits `poster_url`

**File:** `src/shitbox/events/engine.py:1270-1289`

**Issue:** `_on_video_complete` has two branches after CR-01 was closed:

1. Early callback (video finishes before `_check_post_captures` runs): `json_path = self._event_json_paths.get(event_id)` returns `None`, so the code stashes `video_path` and `poster_path` into the dicts. `_check_post_captures` pops both later, renames the PNG, and passes `poster_path=` into `save_event`. Works.
2. Late callback (video finishes *after* `_check_post_captures` has already run for the event): `json_path` is populated. The code calls `update_event_video(json_path, path)` and re-runs `generate_events_json()`. But there is no matching `update_event_poster` — the stashed `self._event_poster_paths[event_id] = poster_path` (line 1279) is never read or consumed anywhere.

Two concrete problems:

- The dict entry leaks forever — nothing pops it.
- The PNG stays at `buffer_dir/pending_slates/<save_id>.png`. `generate_events_json` reads `poster_path` from the event's JSON, and that JSON still has `poster_path=None` because `_check_post_captures` ran when the stash was empty. So the website feed gets `video_url` but no `poster_url` for late-callback events.

The late-callback branch is rare (requires the video worker to be slower than `post_event_seconds + processing_time`), but the whole point of extending the callback to carry `poster_path` is that it covers *both* orderings. The integration test `test_poster_survives_rmtree_and_appears_in_events_json` only exercises the early-callback path (it calls `_do_save_event` synchronously, then `_check_post_captures` after).

**Fix:** Add a late-callback branch that mirrors `update_event_video` for the poster. Either:

```python
# engine.py _on_video_complete, after update_event_video + generate_events_json:
if json_path and poster_path is not None:
    # Late callback — rename the stashed PNG into the day dir and update JSON.
    try:
        # reconstruct the base_name from json_path.stem
        base_name = json_path.stem
        day_dir = json_path.parent
        dest_png = day_dir / f"{base_name}_poster.png"
        if poster_path.exists():
            poster_path.rename(dest_png)
            self.event_storage.update_event_poster(json_path, dest_png)
            self.event_storage.generate_events_json()
        # Pop the stash — entry is consumed either way.
        with self._event_paths_lock:
            self._event_poster_paths.pop(event_id, None)
    except OSError as move_err:
        log.warning("late_poster_move_failed", event_id=event_id, error=str(move_err))
```

Or simplify: have `_check_post_captures` not pop the poster path; leave it for `_on_video_complete` to consume regardless of ordering. Either way add a test case that fires the callback after `_check_post_captures` has already processed the pending entry.

### WR-03: `shutil.move` semantics across filesystem boundaries not documented

**File:** `src/shitbox/capture/ring_buffer.py:1163-1180`

**Issue:** The PNG relocation uses `shutil.move(str(src), str(dst))` wrapped in an `OSError` catch. `shutil.move` semantics differ by whether src and dst share a filesystem:

- Same filesystem: atomic `os.rename` — either fully moves or fully fails.
- Cross filesystem: falls back to `shutil.copy2(src, dst)` + `os.unlink(src)`. The copy can finish and the unlink can then fail (permission, read-only, race), leaving duplicate content. `shutil.move` raises in that case so the except branch catches it, but the destination file may already be present and valid.

In practice `src` is `tmp_dir/slate.png` (under `buffer_dir`) and `dst` is `_pending_slates_dir/<id>.png` (also under `buffer_dir`), so they always share a filesystem and the move is atomic. But the code doesn't say so, and a future reader moving `_pending_slates_dir` somewhere else (say a tmpfs-mounted `/run/shitbox/pending_slates` while `buffer_dir` stays on SD) would trip the cross-filesystem path silently.

This is a documentation fix more than a code fix, and it's below WR-02 in priority. Flag because the phase introduced the move and the invariant should be nailed down:

**Fix:** Either swap `shutil.move` for `Path.rename` (explicit same-filesystem requirement, raises `OSError` on cross-device, forces the invariant) or add a one-line comment:

```python
# src and dst are both under self.buffer_dir — same filesystem guaranteed,
# so shutil.move is atomic via os.rename. If pending_slates_dir ever moves
# to a different mount, revisit: cross-fs move is copy+unlink and can leave
# partial state on the failure path.
try:
    self._pending_slates_dir.mkdir(parents=True, exist_ok=True)
    src.rename(dst)  # explicit same-fs; raises on cross-device
    stable_png_path = dst
```

## Info

### IN-01: Test file has vestigial `if False` conditional and no-op context manager

**File:** `tests/test_ring_buffer_slate.py:496-518`

**Issue:** `test_slate_png_move_failure_passes_none` contains:

```python
import logging
with pytest.raises(Exception) if False else _caplog_context() as caplog:
    vrb._do_save_event("event", 0, None, callback, event)
```

The `if False else` conditional is always false, so the code always takes the `_caplog_context()` branch. That context manager is a local shim (lines 513-518) whose `__enter__` returns itself and whose `__exit__` does nothing — it's not wired to pytest's actual `caplog` fixture. The `caplog` name is bound but never asserted on inside the test. `import logging` on line 496 is unused.

This looks like a draft where the author started to add caplog assertions, decided they were flaky with structlog, and left the scaffolding in place. The test's behavioural assertions (PNG not in pending_slates, callback gets None as third arg) are solid — the dead caplog path doesn't hide anything, just clutters.

**Fix:** Strip the shim:

```python
def test_slate_png_move_failure_passes_none(tmp_path: Path, monkeypatch) -> None:
    ...
    monkeypatch.setattr(rb_mod.shutil, "move", _boom)
    callback = MagicMock()
    vrb._do_save_event("event", 0, None, callback, event)

    assert callback.called
    call_args = callback.call_args[0]
    assert len(call_args) == 3
    assert call_args[2] is None
    assert list(vrb._pending_slates_dir.glob("*.png")) == []
    assert call_args[0] is not None
```

Delete the `_caplog_context` class, drop the unused `import logging`. The caplog check from the integration test (`test_poster_absent_when_holding_dir_move_fails`) already covers the logging side; this unit test can stay behavioural-only.

### IN-02: `_pending_slates_dir` and `_process_start_time` init order is fragile

**File:** `src/shitbox/capture/ring_buffer.py:130-131, 182-190`

**Issue:** Two new fields are initialised in `__init__`:

```python
self._pending_slates_dir: Path = self.buffer_dir / "pending_slates"
self._process_start_time: float = 0.0  # set in start() for the sweep
```

And then in `start()`:

```python
self.buffer_dir.mkdir(parents=True, exist_ok=True)
self._pending_slates_dir.mkdir(parents=True, exist_ok=True)
self._process_start_time = time.time()
self._cleanup_pending_slates()
```

If anything calls `_cleanup_pending_slates` before `start()` — including in a test that constructs via `__new__` and forgets to set `_process_start_time` — the sweep would compare file mtimes against `0.0` and remove nothing (since mtime is always > 0). The fixture in `test_ring_buffer_slate.py::_make_vrb` correctly sets `_process_start_time = time.time() - 3600.0` to mimic "1h ago," but a future test that forgets this will silently fail the sweep.

Low impact — the sweep is best-effort and the field has a sentinel default — but a guard would make the failure mode explicit.

**Fix:** Either assert `self._process_start_time > 0.0` at the top of the sweep, or initialise it in `__init__` to `time.time()` so the sentinel can never leak:

```python
self._process_start_time: float = time.time()  # overwritten by start()
```

The latter is simpler and matches how `_ffmpeg_started_at` is handled elsewhere in the class.

### IN-03: Driver name re-read in `_check_post_captures` can disagree with slate snapshot

**File:** `src/shitbox/capture/ring_buffer.py:1113`, `src/shitbox/events/engine.py:1356`

**Issue:** Carry-over from the prior review (IN-05). `_do_save_event` reads the active driver via `self._active_driver_fn()` at line 1113 to bake into the slate PNG, and `_check_post_captures` reads `driver_state.get_active_driver()` independently at line 1356 when persisting the event. A driver swap during the window between slate render and post-capture processing (capture_pre_seconds + capture_post_seconds, typically 10s+) would produce a slate showing driver A and an `events.json` entry showing driver B.

Low-probability real-world scenario — driver swaps are a rest-stop affair, not an in-event one — but the invariant still isn't enforced.

**Fix:** Either pass the slate-time driver through the callback (would require a 4-arg callback, which is getting unwieldy), or accept the split and leave a comment noting that slate driver is save-time, JSON driver is post-capture-time. The latter is probably good enough given the field usage.

### IN-04: `test_event_poster_paths_dict_initialised` has a tautological lock assertion

**File:** `tests/test_engine_slate_wiring.py:266-275`

**Issue:**

```python
def test_event_poster_paths_dict_initialised(monkeypatch):
    engine = _build_engine_skeleton_poster(monkeypatch)
    assert hasattr(engine, "_event_poster_paths")
    assert isinstance(engine._event_poster_paths, dict)
    assert len(engine._event_poster_paths) == 0
    # Same lock as _event_video_paths.
    assert engine._event_paths_lock is engine._event_paths_lock
```

The last assertion compares `engine._event_paths_lock` to itself — always True. The intent from the comment is "poster paths use the same lock object as video paths," which would be tested as:

```python
# Same lock object is used for both dicts — implicit via being the same
# attribute, but pin it here so a future refactor that splits locks must
# also update this test.
assert engine._event_paths_lock is not None
# (There is no separate lock attribute for posters — both dicts share
# engine._event_paths_lock by construction.)
```

The test as written passes trivially and doesn't exercise the invariant. Low priority — the behavioural tests further down cover the lock usage via real lock acquisition.

**Fix:** Either delete the tautology or replace with a structural assertion that both dicts are accessed under the same lock (harder to test directly; a comment saying "both use `_event_paths_lock`" is probably fine since there's only one lock attribute to begin with).

---

_Reviewed: 2026-04-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
