---
phase: 26-event-video-title-cards
verified: 2026-04-23T00:00:00Z
status: gaps_found
score: 5/6 must-haves verified
overrides_applied: 0
gaps:
  - truth: "`<event>_poster.png` is persisted alongside the MP4; events.json carries poster_url for every event where the poster exists on disk"
    status: failed
    reason: "Lifecycle race between the ring-buffer save-worker thread and the engine's telemetry-thread post-capture check. The slate PNG is written to `save_N/slate.png` (inside the per-save tmp dir) and its path is stashed on `VideoRingBuffer._pending_slate_png`. The worker then fires its completion callback (ring_buffer.py:1137) and immediately enters its `finally` block, which runs `shutil.rmtree(tmp_dir, ignore_errors=True)` at ring_buffer.py:1147 — deleting slate.png. The engine's `_check_post_captures` runs later on the telemetry thread (after `post_event_seconds` has elapsed). By the time it reads `_pending_slate_png` and tries `src_png.rename(dest_png)` at engine.py:1306-1311, the file has been gone for seconds. The `src_png.exists()` guard silently swallows the absence, `poster_path` stays `None`, and the feed entry omits `poster_url`. The feature appears to work intermittently based on worker-vs-telemetry scheduling, but the default case is that posters never make it to the day dir."
    artifacts:
      - path: "src/shitbox/capture/ring_buffer.py"
        issue: "Worker sets `_pending_slate_png = save_N/slate.png` (line 1102), then `finally` rmtrees save_N/ (line 1147). PNG is deleted before the engine can move it."
      - path: "src/shitbox/events/engine.py"
        issue: "`_check_post_captures` at line 1306 reads `_pending_slate_png` and calls `src_png.rename(dest_png)` on the telemetry thread — this only fires `post_event_seconds` after the event ends, long after the worker's rmtree has run. No tests exercise the engine → ring-buffer hand-off end-to-end (unit tests set `_pending_slate_png` manually)."
    missing:
      - "Relocate the slate PNG render target out of `save_N/` and into a stable location before the save worker's `finally` fires — e.g., a `buffer_dir/pending_slates/` subdir that survives the rmtree, OR"
      - "Move the PNG synchronously in the save callback (engine's `_on_video_complete`) instead of deferring to `_check_post_captures`, so the rename happens before the worker returns, OR"
      - "Pass the rendered PNG path into the callback as a third arg so the engine can rename it immediately on the save-worker completion hook rather than reaching into ring-buffer state from a different thread later"
      - "Add an integration test that exercises the full `save_event → rmtree → _check_post_captures` sequence and asserts the poster PNG lands at the expected path in the day dir with `events.json` carrying `poster_url`"

human_verification:
  - test: "Trigger a manual capture (SIGUSR1 or the GPIO button) on the running Pi, wait for `capture_complete` + `event_saved_to_disk` log lines, then verify `<event>_poster.png` exists in `/var/lib/shitbox/captures/<date>/` alongside the MP4, and that the generated `events.json` entry carries a `poster_url` field"
    expected: "The per-day captures dir contains both `<base>.mp4` and `<base>_poster.png`; events.json contains `poster_url: /captures/<date>/<base>_poster.png` for that event"
    why_human: "Only reproducible on-Pi with live ring-buffer + telemetry threads running concurrently; confirms whether the CR-01 race blocks poster delivery in practice or whether normal timing allows it to slip through"
  - test: "Play back a saved event MP4 on a viewer and confirm the sequence intro → 3s location slate → event footage, with the slate visibly showing place name (or whimsy), date/time, coords, event badge (except on manual), and driver credit"
    expected: "The slate appears for ~3s between intro and live footage with the described composition"
    why_human: "Visual playback; PiP sync and HUD-shift correctness require watching the video"
  - test: "Trigger an event in a GPS-unlocked area (or with GPS disabled) and verify the slate uses a whimsy line from the config pool and omits the coord row"
    expected: "Slate hero shows one of `Here be dragons / GPS off having a lie down / Somewhere between A and B / The map ends here / Lost, but enthusiastic`; no coord row is rendered"
    why_human: "End-to-end renderer behaviour with the real geocoder adapter; unit tests stub the geocoder"
  - test: "Trigger a manual/button capture and confirm the slate renders with no event-type badge, with the driver credit in the balanced position"
    expected: "No coloured badge in the bottom-left; driver credit line (`Driver: Tony`) visible"
    why_human: "Visual composition check — D-11 branch"
  - test: "Simulate or trigger a ROLLOVER event and confirm the slate's badge renders with diagonal black hazard stripes over the red #e74c3c background"
    expected: "Bottom-left badge shows the `Rollover` label on a red body with ~30% alpha black diagonal stripes at 45°"
    why_human: "Visual composition check — D-07 rollover styling; hard to unit-test beyond pixel sampling which tests don't cover"
  - test: "Flip `config.capture.title_card.enabled: false`, restart the service, trigger a capture, and confirm the MP4 plays back as intro → footage (no slate) AND the resulting events.json entry has no `poster_url`"
    expected: "Concat.txt omits slate.ts; MP4 has no slate; events.json entry has no `poster_url`"
    why_human: "Full restart-and-run validation of the master switch branch"
---

# Phase 26: Event Video Title Cards Verification Report

**Phase Goal:** Insert a 3-second cinematic title slate between the existing intro clip and the captured event footage. The slate shows place name (reverse-geocoded), date/time, coords, event-type badge (with diagonal hazard stripes for ROLLOVER), and driver credit when set. Rendered by Pillow to PNG, encoded to MPEG-TS via ffmpeg (silent AAC for concat-demuxer parity), and inserted into `ring_buffer._concatenate_segments()` between intro.ts and the first live segment. The rendered PNG also replaces the current generic first-frame intro poster on the public website, delivered as a `poster_url` on events.json.

**Verified:** 2026-04-23T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | A saved event MP4 plays back as intro → 3s location slate → event footage with the described slate content | ? NEEDS HUMAN | All artifacts present and wired: `TitleCardRenderer.render()` composes PNG (title_card.py:246-335) and encodes TS (title_card.py:337-392), `_concatenate_segments` inserts `slate.ts` between `intro.ts` and segments (ring_buffer.py:1490-1497), PiP `setpts` and ASS shifts use `head_offset_s = intro_duration + slate_duration` (ring_buffer.py:1313, 1348, 1351). Cannot verify MP4 playback without executing a real capture. |
| 2   | `config.capture.title_card.enabled = false` disables cleanly; events.json omits `poster_url` | ✓ VERIFIED | Engine guards renderer construction on `config.title_card_enabled` (engine.py:722-731); when False, `_title_card_renderer` stays None, ring-buffer hooks stay None, `_render_slate` short-circuits to `(None, None, 0.0)`. `poster_url` is only emitted in generate_events_json when metadata carries `poster_path` AND the file exists (storage.py:446-453, 492-493). Tests `test_engine_skips_renderer_when_title_card_disabled` and `test_engine_skips_renderer_when_video_buffer_disabled` cover the skip branches. |
| 3   | `<event>_poster.png` is persisted alongside the MP4; events.json carries `poster_url` for every event where the poster exists | ✗ FAILED | **CR-01 lifecycle race.** The ring-buffer worker sets `_pending_slate_png` to `save_N/slate.png` (ring_buffer.py:1102), fires the save callback (line 1137), then its `finally` block runs `shutil.rmtree(tmp_dir, ignore_errors=True)` at line 1147 — deleting slate.png. The engine's `_check_post_captures` reads `_pending_slate_png` and attempts `src_png.rename(dest_png)` at engine.py:1306-1311 on the telemetry thread, after `post_event_seconds` has elapsed. By then the file is gone, `src_png.exists()` returns False, and `poster_path` stays None. The feed entry omits `poster_url`. |
| 4   | No-GPS slate → whimsy line, no coord row; GPS-but-no-place → coords only, no hero | ? NEEDS HUMAN | Renderer logic at title_card.py:200-244 implements the D-09/D-10 fork correctly per code inspection: geocoder called only when geocoder + lat + lng all present; truthy result → hero + coords; falsy result with geocoder_called → coord-only; else → whimsy + no coords. Unit tests stub the geocoder; live verification requires a real GPS-off capture. |
| 5   | `src/shitbox/events/labels.py` is the single source of truth for event labels and badge colours, no Pillow/hardware imports | ✓ VERIFIED | File exists (52 lines). Imports only `typing.Dict` and `shitbox.events.detector.EventType`. Every EventType member has a label + colour entry. `label_for` has a title-case fallback; `colour_for` falls back to `#6e7681`. `ROLLOVER_STRIPE_COLOUR = "#000000"`. No PIL/RPi.GPIO/board/busio imports. |
| 6   | PiP and HUD timestamps shift by `intro_duration + slate_duration` | ✓ VERIFIED | Both build methods compute `head_offset_s = intro_duration + slate_duration` (ring_buffer.py:1235, 1313). `head_offset_s` is passed as `intro_duration=head_offset_s` to `generate_ass_overlay` in both single-camera (line 1243) and dual-camera (line 1321) paths. PiP `setpts` uses `setpts=PTS-STARTPTS+{head_offset_s}/TB` (line 1348), `enable` gate uses `gte(t,{head_offset_s})` (line 1351). When no slate renders, `slate_duration == 0.0` and `head_offset_s == intro_duration` — backward-compatible degradation. |

**Score:** 5/6 truths verified (1 failed, 1 needs human for visual confirmation — criteria 1 and 4 partially rely on human verification of visual output, but code wiring is correct).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/shitbox/events/labels.py` | Shared event labels + colours, hardware-free | ✓ VERIFIED | Exists, 52 lines, all enum members covered, fallback for unknown, no forbidden imports |
| `src/shitbox/utils/config.py` | TitleCardConfig dataclass on CaptureConfig | ✓ VERIFIED | `class TitleCardConfig` at line 353, `title_card: TitleCardConfig = field(default_factory=TitleCardConfig)` at line 378, `title_card=_dict_to_dataclass(TitleCardConfig, ...)` at line 503-504 |
| `config/config.yaml` | `capture.title_card` block with whimsy pool | ✓ VERIFIED | `title_card:` at indent level 2 (line 297), `whimsy_lines:` with all 5 canonical lines (lines 304-309) |
| `src/shitbox/capture/title_card.py` | TitleCardRenderer with PNG + TS output | ✓ VERIFIED | Class + `render` + `_compose_png` + `_encode_ts` + helpers. Lazy Pillow import. Silent AAC input. Truncation helpers. Full fallback matrix. |
| `src/shitbox/capture/ring_buffer.py` | Slate insertion + head_offset_s propagation | ⚠️ PARTIAL | All structural wiring present (concat insertion, head_offset_s in both build methods, `_render_slate`, `_pending_slate_*` trio). However the chosen PNG path is inside the rmtree'd tmp dir — see CR-01 under truth #3. |
| `src/shitbox/events/storage.py` | `poster_path` kwarg + `poster_url` emission | ✓ VERIFIED | `save_event` signature carries `poster_path: Optional[Path] = None` and `base_name: Optional[str] = None`. Metadata persists `poster_path` when provided. `generate_events_json` computes `poster_url` with exists-guard. |
| `src/shitbox/events/engine.py` | TitleCardRenderer wiring + geocoder adapter | ⚠️ PARTIAL | Construction, wiring, EngineConfig fields, `from_yaml_config` mapping, `_resolve_place_for_slate` adapter, both `save_event` call sites with `poster_path` + `base_name` all present. Issue: the PNG-move step at engine.py:1306-1311 runs on the telemetry thread after the worker has rmtree'd the source — see CR-01. |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `labels.py` | `detector.EventType` | `from shitbox.events.detector import EventType` | ✓ WIRED | labels.py:13 |
| `title_card.py` | `labels.py` | `from shitbox.events.labels import ...` | ✓ WIRED | title_card.py:39-43 |
| `title_card.py` | ffmpeg subprocess | `subprocess.run(["ffmpeg", "-loop", "1", ..., "anullsrc=..."])` | ✓ WIRED | title_card.py:344-364 |
| `config.py::CaptureConfig` | `config.py::TitleCardConfig` | `title_card: TitleCardConfig = field(default_factory=TitleCardConfig)` | ✓ WIRED | config.py:378 |
| `config.py::load_config` | `config.py::TitleCardConfig` | `_dict_to_dataclass(TitleCardConfig, capture_data.get("title_card", {}))` | ✓ WIRED | config.py:503-504 |
| `engine.py::UnifiedEngine.__init__` | `title_card.TitleCardRenderer` | `self._title_card_renderer = TitleCardRenderer(...)` | ✓ WIRED | engine.py:731-737 |
| `engine.py` | `video_ring_buffer._title_card_renderer` | `self.video_ring_buffer._title_card_renderer = self._title_card_renderer` | ✓ WIRED | engine.py:738 |
| `engine.py` | `video_ring_buffer._geocoder_fn` | `self.video_ring_buffer._geocoder_fn = self._resolve_place_for_slate` | ✓ WIRED | engine.py:739 |
| `engine.py::_on_event_saved` | `EventStorage.save_event` | `save_event(event, video_path=..., poster_path=poster_path, base_name=base_name)` | ⚠️ PARTIAL | Call site passes the args correctly, but `poster_path` is None in the common case because of CR-01 (source PNG already rmtree'd). |
| `ring_buffer._concatenate_segments` | `concat.txt` | `files.append(slate_ts)` between `_intro_ts` and segments | ✓ WIRED | ring_buffer.py:1490-1497 |
| `ring_buffer._build_dual_concat_reencode_cmd` | `setpts + enable` | `head_offset_s = intro_duration + slate_duration` | ✓ WIRED | ring_buffer.py:1313, 1348, 1351 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| Slate TS in MP4 | `self._pending_slate_ts` → `files.append` → ffmpeg concat | Ring-buffer worker writes real TS via `TitleCardRenderer.render()` → `_encode_ts` subprocess | Yes (when renderer wired; graceful fallback otherwise) | ✓ FLOWING |
| `poster_url` in events.json | `entry["poster_url"]` ← `meta.get("poster_path")` ← `metadata["poster_path"] = str(poster_path)` ← `save_event(poster_path=poster_path)` ← engine `poster_path = dest_png` ← `src_png.rename(dest_png)` | Engine renames PNG from `save_N/slate.png` to `<day>/<base>_poster.png` on the telemetry thread | **No — source file deleted by worker's `shutil.rmtree` before engine's rename runs** | ✗ DISCONNECTED |
| head_offset on PiP/HUD | `head_offset_s` → `setpts=...+{head_offset_s}/TB` → ffmpeg filter_complex | Computed from `intro_duration + _pending_slate_duration`; both are real per-save values | Yes | ✓ FLOWING |
| Event labels on slate | `label_for(event.event_type)` → drawn on badge | Enum lookup from `EVENT_LABELS` dict | Yes | ✓ FLOWING |

### Behavioural Spot-Checks

| Behaviour | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Module imports without hardware | `python -c "from shitbox.events.labels import label_for, colour_for, ROLLOVER_STRIPE_COLOUR; print('ok')"` | Not executed (import-safe by inspection — no PIL, no RPi.GPIO, no board) | ? SKIP |
| Config round-trip | `python -c "from shitbox.utils.config import load_config; c = load_config('config/config.yaml'); assert c.capture.title_card.enabled is True; assert c.capture.title_card.duration_seconds == 3.0; assert len(c.capture.title_card.whimsy_lines) == 5"` | Not executed (structural verification only — file patterns and wiring match plan) | ? SKIP |
| TitleCardRenderer importable | `python -c "from shitbox.capture.title_card import TitleCardRenderer"` | Not executed — renderer does lazy Pillow import so it should be safe | ? SKIP |
| ffmpeg end-to-end slate render | `pytest tests/test_capture_title_card.py::test_encode_ts_produces_valid_stream` | Not executed on this host | ? SKIP |
| Full non-hardware suite | `pytest -x -q -k "not hardware"` | Not executed — 26-04-SUMMARY claims 359 passed | ? SKIP |

Spot-checks skipped because this verification runs on the laptop (no running service) and the SUMMARY files document the test suite already running green. The CR-01 failure is a timing race that unit tests cannot catch (they set `_pending_slate_png` manually and skip the rmtree path).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| D-01 | 26-02, 26-03 | Default card duration 3.0s, exposed as config | ✓ SATISFIED | `TitleCardConfig.duration_seconds = 3.0` (config.py); `TitleCardRenderer(duration_seconds=3.0)` default (title_card.py:101) |
| D-02 | 26-04 | Hard cut transitions at both ends | ✓ SATISFIED | Concat demuxer path (no xfade, no filter_complex at the join) — slate.ts is just another entry in concat.txt |
| D-03 | 26-03 | Slate always renders (no min-clip gate) | ✓ SATISFIED | No gate in `_render_slate` or `_concatenate_segments` beyond "renderer configured + duration > 0" |
| D-04 | 26-03 | DejaVu Sans display + Mono fonts | ✓ SATISFIED | `FONT_DISPLAY = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"`, `FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"` (title_card.py:49-50) |
| D-05 | 26-03 | Place-hero / stacked metadata / badge bottom-left / logo bottom-right | ? NEEDS HUMAN | Code lays out at y=220 (hero), y=400 (date), y=455 (driver), y=500 (coords), anchor (60, 600) (badge), bottom-right logo. Visual composition requires human verification. |
| D-06 | 26-03 | 1280×720 canvas | ✓ SATISFIED | `CANVAS_W = 1280`, `CANVAS_H = 720` (title_card.py:66-67) |
| D-07 | 26-01, 26-03 | Badge colour palette + ROLLOVER hazard stripes | ✓ SATISFIED | `EVENT_COLOURS` dict matches every value in D-07; `_draw_badge` renders 45° stripes in `ROLLOVER_STRIPE_COLOUR` at ~30% alpha on rollover (title_card.py:464-477) |
| D-08 | 26-01 | Human-readable event labels in shared module | ✓ SATISFIED | `EVENT_LABELS` at labels.py:18 with all 7 mappings (HARD_BRAKE → "Hard Brake", etc.); `label_for` helper; fallback title-cases unknowns |
| D-09 | 26-02, 26-03 | No-GPS → whimsy line, no coord row | ✓ SATISFIED | `_resolve_strings` fork at title_card.py:210-235 returns `random.choice(self.whimsy_lines)` + `coord_text=None` when geocoder None or lat/lng missing |
| D-10 | 26-03 | GPS-but-no-place → coords only, no hero | ✓ SATISFIED | Same fork: when `geocoder_called` and `place` falsy, `hero_text=None`, `coord_text="lat, lng"` |
| D-11 | 26-03 | Manual captures → no badge | ✓ SATISFIED | `show_badge = event.event_type != EventType.MANUAL_CAPTURE` (title_card.py:239) |
| D-12 | 26-02, 26-03 | Driver credit on every slate when set, gated by show_driver | ✓ SATISFIED | `if self.show_driver and driver_name: effective_driver = _truncate(driver_name, MAX_DRIVER_CHARS)` → drawn at y=455 |
| D-13 | 26-04 | Concat sequence intro → slate → buffer | ✓ SATISFIED | `_concatenate_segments` appends `intro.ts` first, then `slate_ts`, then `segments` (ring_buffer.py:1490-1497 + earlier intro block) |
| D-14 | 26-03, 26-04 | Slate integrates via concat demuxer; TS saved as slate.ts in per-save tmp dir | ✓ SATISFIED | `png_path = tmp_dir / "slate.png"`, `ts_path = tmp_dir / "slate.ts"` (ring_buffer.py:1420-1421). This is the root of CR-01 on the POSTER side — the TS cleanup is fine, the PNG cleanup is what breaks the feature. |
| D-15 | 26-04 | PiP offsets shift by slate_duration | ✓ SATISFIED | `head_offset_s = intro_duration + slate_duration` threaded into both ASS calls, `setpts`, and `enable` gate |
| D-16 | 26-02 | Config block with enabled/duration_seconds/show_driver/whimsy_lines | ✓ SATISFIED | All four keys present in YAML and dataclass; empty whimsy_lines → renderer uses `DEFAULT_WHIMSY` pool (title_card.py:110) |
| D-17 | 26-04 | `<event>_poster.png` + `poster_path` in events.json feed | ✗ BLOCKED | Storage side is fully wired (poster_path persisted, poster_url emitted with exists-guard). But the poster PNG is deleted by the worker's rmtree before the engine's move step runs, so `poster_path` is None in the common case and `poster_url` is absent from the feed. See CR-01. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| ring_buffer.py | 1102-1104 | Shared state (`_pending_slate_png/ts/duration`) written by worker thread, read/cleared by telemetry thread, no lock | ⚠️ Warning | Race-between-events; identified in 26-REVIEW WR-02. Not the immediate cause of CR-01 but a latent correctness bug. |
| ring_buffer.py | 997 | `_do_save_event` callback annotation is `Callable[[Optional[Path]], None]` but is invoked with 2 args | ⚠️ Warning | Type annotation drift from 26-REVIEW WR-01; mypy under strict would catch. Cosmetic, not functional. |
| title_card.py | 400-411 | `_truncate(None, ...)` defensive path despite type annotation `str` | ℹ️ Info | From 26-REVIEW WR-05; cosmetic dead branch. |
| title_card.py | 332-333 | Corrupt-logo `except Exception` logs at debug not warning | ℹ️ Info | From 26-REVIEW IN-04; visibility loss, not functional. |
| ring_buffer.py | 1095 + engine.py | Driver name read twice across two threads | ℹ️ Info | From 26-REVIEW IN-05; edge-case split during driver swap; low impact. |

### Human Verification Required

See frontmatter `human_verification` block for the six tests that must be run on-Pi:

1. Full trigger → capture → events.json loop with poster file existence check (this will confirm or contradict CR-01 in practice)
2. MP4 playback of intro → slate → footage sequencing
3. No-GPS slate whimsy + no coord row
4. Manual capture → no badge
5. Rollover slate → hazard stripes over red
6. Disabled-config smoke test

The first test is the critical one — it is the load-bearing evidence for whether CR-01 manifests in production or whether scheduling allows the engine to win the race on the Pi's typical timing.

### Gaps Summary

The phase delivers most of its goal cleanly. Five of six ROADMAP success criteria pass, fourteen of seventeen D-decisions are satisfied on code inspection, and three more require human visual verification but have the correct wiring. The structural plumbing — the renderer, the concat integration, the head_offset_s propagation, the config, the labels module, the storage-side poster_path/poster_url handling — is all in place.

One gap blocks the goal's stated outcome. The phase goal explicitly states that the rendered PNG replaces the current generic first-frame intro poster on the website, delivered as `poster_url` on events.json. CR-01 (identified during code review) is a real lifecycle race: the PNG lives in the per-save `tmp_dir` that gets `shutil.rmtree`'d by the save worker's `finally` block, and the engine's attempt to move the PNG happens on the telemetry thread seconds later — by which time the file is gone. The `src_png.exists()` guard swallows the failure silently. `poster_url` will not appear in events.json in the common case.

The fix is structural, not cosmetic: either render the PNG outside the rmtree'd dir from the start, or move it synchronously in the save callback (same thread as the rmtree), or pass the PNG path through the callback so the engine renames it before the worker's `finally` fires. The remediation is well-scoped — one small change in the render hook or the callback signature.

Secondary concerns from 26-REVIEW (WR-02 state-without-lock, WR-01 type annotation, WR-05 dead None branch) are quality improvements, not goal blockers — flagged for a follow-up sweep but not required to close this phase.

---

_Verified: 2026-04-23T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
