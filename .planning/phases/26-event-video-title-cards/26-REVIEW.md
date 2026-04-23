---
phase: 26-event-video-title-cards
reviewed: 2026-04-23T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - src/shitbox/events/labels.py
  - src/shitbox/utils/config.py
  - config/config.yaml
  - src/shitbox/capture/title_card.py
  - src/shitbox/capture/ring_buffer.py
  - src/shitbox/events/storage.py
  - src/shitbox/events/engine.py
  - tests/test_events_labels.py
  - tests/test_config_title_card.py
  - tests/test_capture_title_card.py
  - tests/test_ring_buffer_slate.py
  - tests/test_events_storage_poster.py
  - tests/test_engine_slate_wiring.py
findings:
  critical: 1
  warning: 5
  info: 6
  total: 12
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-04-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 26 introduces a title-card slate renderer that composes a PNG poster per event, encodes it to MPEG-TS, and wedges it between `intro.ts` and live buffer segments via the concat demuxer. The pattern is sound — lazy Pillow import, defence-in-depth `render()` that can't raise, fallback matrix for geocoder failure modes, counter-stable `base_name=` override on `save_event`.

One critical issue: a lifecycle race means the poster PNG can be deleted by the ring-buffer worker's `finally` cleanup before the engine's telemetry thread tries to rename it into the per-day events dir. Under normal timing the PNG is gone by the time `_check_post_captures` fires `post_event_seconds` later — the `src_png.exists()` guard will usually silently swallow it, leaving `poster_url` off the website feed. The feature will appear to work intermittently based on whether the save worker has reached its `finally` yet.

The rest is quality stuff: a stale type annotation, a dead reset, test coverage gaps around the slate happy path at the `_do_save_event` level, and a handful of `except Exception: pass` patterns that obscure real problems.

## Critical Issues

### CR-01: Poster PNG is deleted before engine can move it — lifecycle race

**File:** `src/shitbox/capture/ring_buffer.py:1143-1147`, `src/shitbox/events/engine.py:1293-1315`

**Issue:** The ring-buffer worker thread sets `self._pending_slate_png` to a path inside `tmp_dir` (`save_N/slate.png`) at line 1102, completes the concat at line 1107, invokes the save callback at line 1137, then in its `finally` block at line 1147 runs `shutil.rmtree(tmp_dir, ignore_errors=True)` — deleting `slate.png`.

The engine does NOT move the PNG in the save callback. It waits for `_check_post_captures` (line 1260) to fire on the next telemetry tick after `post_event_seconds` has elapsed, then reads `_pending_slate_png` (line 1304) and tries `src_png.rename(dest_png)` (line 1311). By that point the file has been gone for seconds, because:

1. `_do_save_event` runs in a worker thread (`save_event` spawned at ring_buffer.py:253).
2. The worker finishes and runs `rmtree` in its `finally`.
3. The engine's post-capture check runs later on the telemetry thread.

The `src_png.exists()` guard at engine.py:1306 masks the problem as a silent absence: `poster_path` stays `None`, the feed entry omits `poster_url`, and nobody notices until a field test shows no posters ever appearing on the website. The order-of-operations test (`test_pending_state_reset_between_saves`) does not exercise the engine → ring-buffer hand-off and therefore misses it.

There is also a cross-thread access pattern concern: `_pending_slate_png` is written by the worker under no lock and read/cleared by the telemetry thread under no lock, similar to the existing `_event_json_paths` issue called out in `project_audit_findings.md`. Not the immediate cause here (the file is gone, not racing), but worth noting.

**Fix:** Either (a) move the slate PNG out of `save_N/` and into a stable location inside the ring-buffer worker before the `finally` fires, or (b) have the engine move it synchronously in the save callback, not on the next post-capture tick. Option (b) is closer to the existing video-path flow:

```python
# ring_buffer.py — render slate into a stable tmp outside tmp_dir
slate_persist_dir = self.buffer_dir / "pending_slates"
slate_persist_dir.mkdir(parents=True, exist_ok=True)
png_path, ts_path, dur = self._render_slate(
    event,
    slate_persist_dir,  # survives the save_N rmtree
    geocoder=self._geocoder_fn,
    driver_name=driver,
)
# ts_path still needs to live in tmp_dir for concat OR be copied; simplest:
# render PNG to persist_dir, render TS into tmp_dir via a second ffmpeg pass
# that reads the persisted PNG.
```

Or the cleaner fix — have `_do_save_event` emit the final destination path via an additional callback arg, so the engine can set `poster_path` from the sync callback (same thread as the video rename) without reaching back into ring-buffer state:

```python
# ring_buffer.py: callback signature gains poster_path
if callback:
    callback(output_path, clip_start_mtime, self._pending_slate_png)
# engine side: _on_video_complete stashes the poster path alongside video_path
```

Either way the invariant to restore is: the PNG must live past `_do_save_event.finally`, or it must be renamed to its final home before that `finally` fires.

## Warnings

### WR-01: `_do_save_event` callback type annotation lies about arity

**File:** `src/shitbox/capture/ring_buffer.py:997`

**Issue:** The internal worker declares `callback: Optional[Callable[[Optional[Path]], None]]` (one-arg callable returning None), but the method invokes the callback with two arguments at lines 1086, 1137, and 1142:

```python
callback(None, 0.0)           # line 1086
callback(output_path, clip_start_mtime)  # line 1137
callback(None, 0.0)           # line 1142
```

The public `save_event` at line 227 declares the correct two-arg signature (`Callable[[Optional[Path], float], None]`). The internal method's annotation is wrong — it was probably copied from an older revision and never updated when `clip_start_mtime` was added. mypy under strict mode would catch this; the current mypy config evidently doesn't.

**Fix:**
```python
def _do_save_event(
    self,
    prefix: str,
    post_seconds: int,
    pre_seconds: Optional[int],
    callback: Optional[Callable[[Optional[Path], float], None]],
    event: Optional["Event"] = None,
) -> None:
```

### WR-02: Slate pending-state accessed from two threads without a lock

**File:** `src/shitbox/capture/ring_buffer.py:1102-1104`, `src/shitbox/events/engine.py:1303-1319`

**Issue:** Three related attributes — `_pending_slate_png`, `_pending_slate_ts`, `_pending_slate_duration` — are written by the save-worker thread (ring_buffer.py:1011-1013, 1102-1104) and read+cleared by the telemetry thread (engine.py:1304, 1317-1319). No lock guards either side. Same class of bug as the `_event_json_paths` issue already noted in `project_audit_findings.md`.

Two concrete failure modes:

1. If a second event fires while a prior save is mid-flight (possible during a rapid burst of HIGH_G hits on a corrugated section), the worker resets the pending state to None at line 1011 and then sets fresh paths at 1102-1104. If the telemetry thread runs between those two writes, it sees `None` for the previous event's poster.
2. On aarch64 without sequential consistency, the telemetry thread may see a partial write — `_pending_slate_png` set but `_pending_slate_duration` still zero, or vice versa. Unlikely to bite on CPython given the GIL, but the invariant is "related tuple updated atomically" and it isn't enforced.

**Fix:** Bundle the three fields into a single tuple behind a lock, or use a `threading.Lock()` around the write and read blocks:

```python
# ring_buffer.py
self._pending_slate: Optional[tuple[Path, Path, float]] = None
self._pending_slate_lock = threading.Lock()

# writer
with self._pending_slate_lock:
    self._pending_slate = (png_path, ts_path, dur) if dur > 0 else None

# reader (engine)
with vrb._pending_slate_lock:
    slate = vrb._pending_slate
    vrb._pending_slate = None
```

Bonus: this also closes CR-01 in the same change if you include the rename inside the critical section.

### WR-03: Poster URL builder assumes a specific directory layout

**File:** `src/shitbox/events/storage.py:446-453`

**Issue:** `generate_events_json` builds the poster URL as `f"{video_base_url}/{pp.parent.name}/{pp.name}"`. This silently assumes `poster_path` lives one directory deep under `captures_dir`. If the engine ever changes to store posters in a subdirectory (e.g. `/captures/<date>/posters/<name>.png`), the URL will be wrong and point at a 404.

The video-URL builder four lines up has the same shape, so the assumption is at least consistent, but it's fragile. A relative-path computation against `captures_dir` would be explicit:

**Fix:**
```python
if self.captures_dir:
    try:
        rel = pp.resolve().relative_to(self.captures_dir.resolve())
        poster_url = f"{video_base_url}/{rel.as_posix()}"
    except ValueError:
        # poster is outside captures_dir — log and skip
        log.warning("poster_outside_captures_dir", path=str(pp))
        poster_url = None
```

Do the same for `video_url` while you're in there.

### WR-04: `_render_slate` references local `Any` import that's shadowed by module `typing.Any`

**File:** `src/shitbox/capture/ring_buffer.py:1400`

**Issue:** `_render_slate` declares `geocoder: Optional[Any] = None` but the actual renderer signature is `GeocoderFn = Callable[[float, float], Optional[str]]`. Using `Any` here gives up type checking on the one hand-off where getting the signature wrong would send a wrong-shape callable into `TitleCardRenderer.render`.

This isn't a bug today (the engine passes the right shape), but it hides signature drift. Since `TitleCardRenderer` already exports `GeocoderFn`, use it:

**Fix:**
```python
from shitbox.capture.title_card import GeocoderFn  # TYPE_CHECKING block is fine
...
def _render_slate(
    self,
    event: "Event",
    tmp_dir: Path,
    *,
    geocoder: Optional[GeocoderFn] = None,
    driver_name: Optional[str] = None,
) -> tuple[Optional[Path], Optional[Path], float]:
```

### WR-05: `_truncate(None, ...)` defensive path is unreachable but claims to handle None

**File:** `src/shitbox/capture/title_card.py:400-411`

**Issue:** The helper has `if text is None: return ""` — but every caller (`driver_name`, `place`, whimsy line) pre-filters. The type annotation is `text: str`, not `Optional[str]`. If a caller ever relied on this defence and passed `None`, they'd get an empty string silently rendered centred in a 140pt font — not what you'd want.

Either remove the dead guard and tighten the type to `str`, or accept `Optional[str]` in the annotation and push the None-handling out to callers explicitly. The current shape is "documented lie" — the code says it handles None but the signature forbids it.

**Fix:** Drop the None branch since callers already guard:
```python
def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"
```

## Info

### IN-01: Dead `os` import lingers in ring_buffer (pre-existing, still there)

**File:** `src/shitbox/capture/ring_buffer.py:8`

**Issue:** `import os` is used throughout (`os.path.exists`, `os.nice`, `os.get_blocking`, etc.) so this one's fine. Leaving the note because `project_audit_findings.md` flagged a dead `os` in ring_buffer; that flag appears stale now — os is used. Worth verifying the audit file is current.

**Fix:** Cross-check with `project_audit_findings.md` and drop the stale entry if confirmed.

### IN-02: `_nice` lambda still defined inside `_start_ffmpeg`

**File:** `src/shitbox/capture/ring_buffer.py:731`

**Issue:** `_nice = lambda: os.nice(5)` is defined as a noqa'd E731 inside `_start_ffmpeg` and used as `preexec_fn=_nice`. It's harmless but the audit file called it out as "unused lambda in ring_buffer.py". It's actually used — just in the reverse of how the audit claims. Again worth a cross-check with the living doc.

**Fix:** Same as IN-01 — reconcile with `project_audit_findings.md`.

### IN-03: `generate_events_json` rescans all event JSON files on every call

**File:** `src/shitbox/events/storage.py:400-509`

**Issue:** `_check_post_captures` calls `generate_events_json()` on every event save (engine.py:1335). The function re-scans every `*.json` under `base_dir` via `rglob` each time and rebuilds the full feed. With 14 days × typical event rate on a hard rally day, this is a few thousand stat+open calls per event. Not performance-critical on paper but flagged because:

1. The `poster_path` exists-check adds another stat() per entry.
2. It's already synchronous on the telemetry loop — the audit file already called this out for `capture_sync._do_sync` with the same fix ("needs backgrounding").

Out of scope for v1 performance review (per review rules), but since it was flagged for other services in the audit, the title-card addition shouldn't make it worse. It doesn't, materially — one extra stat per entry is negligible — but the pattern deserves the same background-queue treatment eventually.

**Fix:** Track against the existing background-sync audit item; no code change needed here.

### IN-04: Logo-load `except Exception` swallows corrupt asset warnings at debug level

**File:** `src/shitbox/capture/title_card.py:332-333`

**Issue:** The logo-load path distinguishes `FileNotFoundError` (warning) from other errors (debug). A corrupt PNG under `LOGO_PATH` will render with no logo and no log trail above debug, which makes a "why is the logo missing from production slates" investigation tedious. This is a judgement call — the rest of the module is carefully best-effort, and a corrupt logo shouldn't fail a rollover slate — but the visibility drop from warning to debug is arguably too aggressive.

**Fix:** Bump the non-FileNotFoundError branch to `log.warning`:
```python
except Exception as exc:
    log.warning("slate_logo_skip", path=LOGO_PATH, error=str(exc))
```

### IN-05: `driver_state.get_active_driver` called twice for the same save

**File:** `src/shitbox/capture/ring_buffer.py:1095`, `src/shitbox/events/engine.py:1326`

**Issue:** The slate renderer asks `_active_driver_fn()` inside `_do_save_event` at line 1095, and the engine asks `driver_state.get_active_driver()` again at engine.py:1326 when persisting the event. If a driver swap happens between the two calls (sub-second race during a crash-and-restore), the slate and the metadata could disagree. Low impact — but worth a comment noting that the slate is a snapshot-of-save-time, not a snapshot-of-event-time.

**Fix:** Either pass the slate-time driver name through the callback so the engine reuses it for `save_event`, or add a comment acknowledging the split:

```python
# ring_buffer.py _do_save_event:
# NOTE: driver is re-read by the engine at event persist. Brief
# window where slate shows driver A and events.json shows driver B
# during a driver swap coinciding with a post-event save.
```

### IN-06: `test_engine_skips_renderer_when_title_card_disabled` has vestigial commentary

**File:** `tests/test_engine_slate_wiring.py:154-166`

**Issue:** The test body contains a 10-line comment paragraph about MagicMock attr tracking, wraps up with "To be robust we verify the mock's call list doesn't include a __setattr__...", then just asserts `engine._title_card_renderer is None`. The comment explains what the test *didn't* end up doing. Reads as a draft left in place.

**Fix:** Prune the commentary, keep the assertion:
```python
def test_engine_skips_renderer_when_title_card_disabled(monkeypatch):
    engine = _build_engine_skeleton(
        monkeypatch, video_buffer_enabled=True, title_card_enabled=False
    )
    assert engine._title_card_renderer is None
```

---

_Reviewed: 2026-04-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
