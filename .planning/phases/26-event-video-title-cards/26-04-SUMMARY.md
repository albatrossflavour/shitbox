---
phase: 26-event-video-title-cards
plan: 04
subsystem: capture
tags: [ring-buffer, engine-wiring, title-card, ffmpeg-concat, events-json, poster]

# Dependency graph
requires:
  - phase: 26-event-video-title-cards/01
    provides: "TitleCardConfig dataclass + config.yaml title_card section"
  - phase: 26-event-video-title-cards/02
    provides: "Event schema fields (lat, lng, start_time, event_type) the renderer reads"
  - phase: 26-event-video-title-cards/03
    provides: "TitleCardRenderer class with render(event, png, ts, geocoder, driver_name) → float"
provides:
  - "EventStorage.save_event accepts poster_path= and base_name= keyword overrides"
  - "generate_events_json emits poster_url (mirrors video_url pattern with exists-guard)"
  - "VideoRingBuffer slate render hook + pending-state trio (_pending_slate_png/ts/duration)"
  - "VideoRingBuffer _render_slate method with full fallback matrix (no renderer / exception / zero duration / missing TS)"
  - "head_offset_s = intro_duration + slate_duration propagated through:
     single-camera ASS shift, dual-camera ASS shift, PiP setpts, PiP enable gate"
  - "slate.ts inserted into ffmpeg concat demuxer list between intro.ts and live segments"
  - "UnifiedEngine._resolve_place_for_slate adapter (name, admin1 geocoder shape)"
  - "UnifiedEngine instantiates + wires TitleCardRenderer when title_card + video_buffer enabled"
  - "Event save pipeline pre-generates base_name once and threads poster_path into save_event"
  - "25 new unit tests across 3 test files (6 + 10 + 9)"
affects:
  - "website shit-of-theseus.com — events.json now carries poster_url; consumer wiring deferred per D-17"
  - "Any future plan that adds save_event call sites must pass poster_path + base_name to stay counter-safe"

# Tech tracking
tech-stack:
  added:
    - "No new runtime deps (Pillow already installed from 26-03)"
  patterns:
    - "Poster path vs poster URL split — filesystem path on metadata JSON, URL-shape on feed (mirrors video_path/video_url)"
    - "base_name override kwarg as counter-stability pattern — caller pre-generates, save_event trusts"
    - "head_offset_s as a separate local from intro_duration — preserves historical log shape (intro_s=) while introducing new authoritative offset"
    - "TYPE_CHECKING import block for optional wiring types — keeps ring_buffer.py free of hard capture/title_card import at module scope"
    - "Geocoder adapter pattern — engine owns the reverse_geocoder lib, the ring buffer + renderer get a Callable[[float,float], Optional[str]]"

key-files:
  created:
    - "tests/test_events_storage_poster.py (214 lines, 6 tests)"
    - "tests/test_ring_buffer_slate.py (~290 lines, 10 tests)"
    - "tests/test_engine_slate_wiring.py (~240 lines, 9 tests)"
  modified:
    - "src/shitbox/events/storage.py — save_event signature + metadata persistence + generate_events_json poster_url branch"
    - "src/shitbox/capture/ring_buffer.py — slate render hook, pending state, _render_slate fallback matrix, head_offset_s in both build methods"
    - "src/shitbox/events/engine.py — EngineConfig fields, from_yaml_config mapping, renderer wiring, _resolve_place_for_slate adapter, poster-move block at save_event site 1, explicit poster_path=None at save_event site 2"

key-decisions:
  - "base_name override via keyword argument (Option B from plan) — less invasive than a pure _filename_for helper; keeps counter state in EventStorage"
  - "Engine always pre-generates base_name when video_ring_buffer is not None — even if no slate was rendered — so save_event gets a stable base_name on every event and the engine code path is identical whether the slate succeeded or not"
  - "_pending_slate_* reset happens in BOTH places: top of ring_buffer._do_save_event (guards against crashes) AND end of engine poster-move block (guards against late callbacks). Belt-and-braces."
  - "head_offset_s introduced as a new local rather than reassigning intro_duration — keeps the 'intro_s=' log field stable for grep-ability in existing dashboards/alerts"
  - "slate_inserted log is emitted at INFO level with ts path + slate_s; failed-to-insert is simply the absence of the log line (plus the slate_render_failed/slate_render_exception logs from Task 2 / plan 26-03)"
  - "shutdown flush at engine.py:2484 gets an explicit poster_path=None rather than relying on the kwarg default — future readers see the intent"
  - "Test for engine wiring uses monkeypatch to stub out all hardware-adjacent constructors (VideoRingBuffer, HighRateSampler, EventStorage, etc.) — we only need a narrow slice of __init__ to validate the wiring branch, and a full construction wants hardware/GPIO/camera"

patterns-established:
  - "Pattern: exists-guard on URL emission — filesystem paths on metadata are source-of-truth, URL-shape derivation on feed is a derived projection that hides dangling references"
  - "Pattern: bound-method identity in tests — compare .__func__ + .__self__ rather than `is` on the bound method itself (each attribute access creates a new bound method object)"
  - "Pattern: `PYTHONPATH=src python -m pytest` as a dev-mode workaround when pip install -e fails on hardware-adjacent extras (lgpio swig) in a laptop venv"

requirements-completed: [D-02, D-13, D-14, D-15, D-17]

# Metrics
duration: ~55 min
completed: 2026-04-23
tasks: 3
test-files: 3
tests-added: 25
commits: 6
---

# Phase 26 Plan 04: Event Video Title Cards End-to-End Wiring Summary

**Slates now appear in saved event MP4s (intro → slate → footage), poster PNGs land next to MP4s, and events.json carries poster_url. Renderer + geocoder adapter + driver-state resolver injected into the ring buffer with a full graceful-degradation matrix; 25/25 new tests green, 359/359 non-hardware suite green.**

## What shipped

Three modules modified, three test files added, six commits (three RED + three GREEN pairs).

### `src/shitbox/events/storage.py`

`save_event` gained two keyword-only parameters:

- `poster_path: Optional[Path] = None` — persisted to metadata JSON as `"poster_path"` when provided, absent otherwise (mirrors how `video_path` is handled).
- `base_name: Optional[str] = None` — when passed, suppresses the internal `_generate_filename` call. Caller owns the counter increment.

`generate_events_json` gained a sibling block to the existing `video_url` computation that emits `entry["poster_url"] = f"{video_base_url}/{pp.parent.name}/{pp.name}"` when the referenced PNG exists on disk. Missing files yield no `poster_url` key (exists-guard matching video's behaviour).

### `src/shitbox/capture/ring_buffer.py`

`VideoRingBuffer.__init__` grew six optional attributes that the engine wires up at construction time:

- `_title_card_renderer` — the `TitleCardRenderer` instance (from plan 26-03)
- `_geocoder_fn` — `Callable[[float, float], Optional[str]]`
- `_active_driver_fn` — `Callable[[], Optional[str]]`
- `_pending_slate_png` / `_pending_slate_ts` / `_pending_slate_duration` — per-save runtime state reset at the top of each save pass

A new `_render_slate(event, tmp_dir, *, geocoder, driver_name)` method returns `(png, ts, duration)` with a full fallback matrix: no renderer → (None, None, 0.0); renderer raises → logs `slate_render_exception` and degrades to (None, None, 0.0); returns <=0.0 → (None, None, 0.0); succeeds but ts file missing → (None, None, 0.0).

`save_event` now accepts `event: Optional[Event] = None`. When provided, `_do_save_event` renders the slate into `segments[0].parent` before `_concatenate_segments` and stashes the pending paths.

`_concatenate_segments` appends `slate.ts` to the concat file list immediately after `intro.ts` and before the live segments, logs `slate_inserted` with `ts=…, slate_s=…`, then falls through to `files.extend(segments)`. Skipped cleanly when pending state is unset.

Both `_build_concat_reencode_cmd` (single-camera) and `_build_dual_concat_reencode_cmd` (dual-camera PiP) compute a new local:

```python
head_offset_s = intro_duration + slate_duration
```

Applied to:

- Single-camera: `generate_ass_overlay(..., intro_duration=head_offset_s, ...)` — HUD timestamps shift correctly past intro + slate.
- Dual-camera ASS: same `intro_duration=head_offset_s` kwarg.
- Dual-camera PiP `setpts`: `setpts=PTS-STARTPTS+{head_offset_s}/TB` — the cabin stream's timeline starts after the slate instead of at t=0.
- Dual-camera PiP enable: `enable='gte(t,{head_offset_s})'` — overlay only appears once live footage starts.

`intro_duration` is retained as a separate local for log-shape continuity (`intro_s=round(intro_duration, 2)` still appears in `concat_overlay_generated`); `slate_s` and `head_offset_s` are new log fields.

### `src/shitbox/events/engine.py`

`EngineConfig` gained four flat fields matching the existing `video_buffer_*` pattern:

- `title_card_enabled: bool = True`
- `title_card_duration_seconds: float = 3.0`
- `title_card_show_driver: bool = True`
- `title_card_whimsy_lines: list[str] = field(default_factory=list)`

`from_yaml_config` maps `config.capture.title_card.*` into those four fields.

`UnifiedEngine.__init__` now builds a `TitleCardRenderer` and injects three hooks into the ring buffer when `video_buffer_enabled AND title_card_enabled AND self.video_ring_buffer is not None`:

- `self.video_ring_buffer._title_card_renderer = self._title_card_renderer`
- `self.video_ring_buffer._geocoder_fn = self._resolve_place_for_slate`
- `self.video_ring_buffer._active_driver_fn = driver_state.get_active_driver`

A new `_resolve_place_for_slate(lat, lon) -> Optional[str]` method wraps `self._reverse_geocoder.search((lat, lon))` and returns a `"Name, Admin1"` or bare-`"Name"` string, or `None` when the geocoder is absent / empty / raises. This gives the renderer a clean `Callable[[float, float], Optional[str]]` interface without cross-importing `reverse_geocoder`.

Two `save_event` call sites updated:

- **Main path (line 1247):** Before calling `save_event`, pre-generate `base_name = self.event_storage._generate_filename(event)` (counter bumps once). If `_pending_slate_png` exists, move it to `<day_dir>/<base_name>_poster.png` and set `poster_path = dest_png`. Pass both `poster_path=` and `base_name=` into `save_event`. Reset the three `_pending_slate_*` attrs on the ring buffer regardless of outcome.
- **Shutdown flush (line 2484):** Pass `poster_path=None` explicitly — there's no slate render path on the shutdown flush, and being explicit communicates intent.

The `video_ring_buffer.save_event` call at line 1087 now passes `event=event` so the ring buffer's render hook can read event coordinates + type.

## The base_name double-increment hazard (T-26-04-06)

`EventStorage._generate_filename` increments `self._event_counter`. If the engine calls it to derive the poster filename AND `save_event` also calls it to derive the JSON/CSV filename, the counter bumps twice, and JSON/CSV filenames end up one ahead of the poster. Events.json's URL-shape build would then reference a `<base>_poster.png` that doesn't exist.

Two fixes were possible:

**(a)** Extract a pure `_filename_for(event)` helper in `EventStorage` that doesn't mutate state. Use it from both call sites; let `save_event` do the one true counter increment.

**(b)** Pre-generate `base_name` in the engine, pass it into `save_event` via a new `base_name=` override keyword. `save_event` skips `_generate_filename` when `base_name` is provided.

Plan picked (b); so did I. Reasons: keeps counter state owned by `EventStorage`, matches the keyword-only-extension pattern already established for `driver_name` and `poster_path`, and the test for this is a single-line counter-before-and-after assertion (`test_save_event_base_name_override`).

## Concat list order confirmed

Post-implementation the concat.txt layout is:

```
intro.ts
slate.ts          ← NEW (when renderer succeeded + event passed in)
segment_0001.ts
segment_0002.ts
...
```

`slate.ts` is always `segments[0].parent / "slate.ts"` (the same `save_N/` tmp dir that hosts the segments copies + `concat.txt`), so `shutil.rmtree(tmp_dir, ignore_errors=True)` cleans it up alongside everything else. No orphan files survive a failed save.

## head_offset_s propagation — the four places

All four offset consumers now use `head_offset_s = intro_duration + slate_duration`:

| Consumer                              | Site                                               | Effect                                                              |
| ------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------- |
| Single-camera ASS overlay             | `_build_concat_reencode_cmd`                        | HUD timestamps shift past intro + slate                             |
| Dual-camera ASS overlay               | `_build_dual_concat_reencode_cmd`                   | Same, for PiP path                                                  |
| Dual-camera PiP `setpts`              | `_build_dual_concat_reencode_cmd` pip_chain         | Cabin stream's PTS starts after slate, not at t=0                   |
| Dual-camera PiP `enable` gate         | `_build_dual_concat_reencode_cmd` overlay_chain     | Cabin overlay invisible during intro + slate, appears with footage |

When no slate was rendered (`_pending_slate_duration == 0.0`), `head_offset_s == intro_duration` and all four consumers behave identically to pre-phase-26.

## Test counts

| File                                     | Tests | Coverage                                                             |
| ---------------------------------------- | ----- | -------------------------------------------------------------------- |
| `tests/test_events_storage_poster.py`    | 6     | poster_path persistence, poster_url exists-guard, base_name override |
| `tests/test_ring_buffer_slate.py`        | 10    | fallback matrix, concat inclusion, head_offset_s, state hygiene      |
| `tests/test_engine_slate_wiring.py`      | 9     | config mapping, renderer construction, skip branches, geocoder matrix |

Full non-hardware regression suite: **359 passed, 73 deselected** (hardware markers).

## Claude's-Discretion choices

Three places where the plan left wiggle room and I picked a concrete path:

1. **Poster move ordering** — plan suggests moving the PNG into the day dir before calling `save_event`. I chose to do this unconditionally (whenever the ring buffer exists), so `base_name` is generated up front and the counter bumps exactly once on every save, regardless of whether a slate was rendered. The "no slate" path simply skips the rename and passes `poster_path=None`.
2. **Pending-state reset timing** — the engine block resets `_pending_slate_*` to `None/0.0` *after* the poster move, not before. This means a crashed render that wrote the PNG but raised on the TS would still have its PNG moved on the next successful save — but the ring buffer's own reset at the top of `_do_save_event` (from Task 2) shuts that door first. Belt-and-braces is intentional: two processes (engine orchestration + ring buffer save worker thread) need to agree there's no live state between events.
3. **`TYPE_CHECKING` vs runtime import of `TitleCardRenderer` in engine.py** — I chose runtime. Engine.py already imports a lot of heavy capture code (`VideoRingBuffer`, `VideoRecorder`, `overlay`, `buzzer`, `speaker`), so adding `TitleCardRenderer` to that list doesn't meaningfully change the import surface. Ring buffer, by contrast, uses `TYPE_CHECKING` to keep the renderer out of its runtime import path — the renderer is genuinely optional there.

## Website consumer wiring deferred (D-17)

The SoT website at `shit-of-theseus.com` does not yet read `poster_url` — the feed just carries the new field. A follow-up on the website side (separate repo, `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html`) will light up the `<img>` poster on each event card once this Pi-side change has flown through a drive and `events.json` confirms shape in production.

## Out of scope (baseline issues not touched)

Per the scope-boundary rule, I left pre-existing lint/type issues in place:

- `src/shitbox/events/engine.py` — 6 pre-existing E501 line-length warnings (from commit b9c3bc3 "feat(12-04): wire LogbookStorage..."), 6 pre-existing mypy errors (reverse_geocoder import-untyped on line 823, Optional-round on 970, lambda inference on 1136, MQTT attr-defined on 1178, requests stubs on 2308, VideoRingBuffer union-attr on 2476). None of my new lines introduced new warnings or errors.
- `src/shitbox/capture/ring_buffer.py` — 3 pre-existing mypy errors on lines 1086/1137/1142 (`_do_save_event`'s `callback` parameter annotation is `Optional[Callable[[Optional[Path]], None]]` but the outer `save_event` signature declares `Optional[Callable[[Optional[Path], float], None]]` and all call sites pass 2 args). Worth fixing in a follow-up (one-line annotation sync), but unrelated to Task 2.

## Commit trail

```
6f3d0a4 feat(26-04): wire TitleCardRenderer into UnifiedEngine + thread poster_path through save_event
dc41550 test(26-04): add failing tests for UnifiedEngine title-card wiring + geocoder adapter
1e3c6ea feat(26-04): insert title-card slate into concat + propagate head_offset_s
d8abceb test(26-04): add failing tests for VideoRingBuffer slate insertion + head_offset_s
b93af3b feat(26-04): EventStorage.save_event gains poster_path + base_name override, feed emits poster_url
f198fcf test(26-04): add failing tests for EventStorage poster_path/poster_url and base_name override
```

Three TDD RED → GREEN pairs, one per plan task.

## Self-Check: PASSED

- `src/shitbox/events/storage.py` — modified, compiled, `import shitbox.events.storage` OK.
- `src/shitbox/capture/ring_buffer.py` — modified, compiled, `import shitbox.capture.ring_buffer` OK.
- `src/shitbox/events/engine.py` — modified, compiled, `import shitbox.events.engine` OK.
- `tests/test_events_storage_poster.py` — created, 6 tests, all passing.
- `tests/test_ring_buffer_slate.py` — created, 10 tests, all passing.
- `tests/test_engine_slate_wiring.py` — created, 9 tests, all passing.
- Commits `f198fcf`, `b93af3b`, `d8abceb`, `1e3c6ea`, `dc41550`, `6f3d0a4` all present in `git log`.
- Full non-hardware suite: 359 passed, 73 deselected.
- Config round-trip: `title_card_enabled=True, duration=3.0, whimsy=5`.
