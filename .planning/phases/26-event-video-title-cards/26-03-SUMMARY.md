---
phase: 26-event-video-title-cards
plan: 03
subsystem: capture
tags: [pillow, ffmpeg, mpegts, reverse-geocoder, event-slate, title-card]

# Dependency graph
requires:
  - phase: 26-event-video-title-cards/01
    provides: "label_for / colour_for / ROLLOVER_STRIPE_COLOUR lookup table"
  - phase: 26-event-video-title-cards/02
    provides: "TitleCardConfig dataclass (consumed when plan 26-04 wires the engine)"
provides:
  - "TitleCardRenderer class with full D-09/D-10/D-11/D-12 fallback matrix"
  - "PNG slate composer (1280x720) — place-hero / date / coords / driver / badge / logo"
  - "PNG → MPEG-TS encoder with silent AAC 48 kHz stereo for concat-demuxer parity"
  - "Hazard-stripe overlay for ROLLOVER event badge (D-07)"
  - "14 unit + integration tests covering every fallback and failure branch"
affects:
  - "26-04 (ring_buffer concat wiring) — imports TitleCardRenderer, calls render(event, png, ts, geocoder=..., driver_name=...)"
  - "events/engine.py — will instantiate TitleCardRenderer from TitleCardConfig"

# Tech tracking
tech-stack:
  added:
    - "Pillow (already in pyproject; first in-tree use at 1280x720 display scale)"
  patterns:
    - "Lazy Pillow import inside render-time method body — module stays import-safe without PIL"
    - "PNG → MPEG-TS via ffmpeg -loop 1 + -f lavfi -i anullsrc for concat parity"
    - "Graceful DejaVu truetype fallback to ImageFont.load_default() on dev boxes"
    - "Geocoder injected as callable, never imported inside the renderer"

key-files:
  created:
    - "src/shitbox/capture/title_card.py (487 lines)"
    - "tests/test_capture_title_card.py (415 lines, 14 tests)"

key-decisions:
  - "Lazy Pillow import (module-scope-safe without PIL installed)"
  - "_encode_ts bundled in Task-1 GREEN commit because the module is one file and Task-1 render() calls it directly"
  - "MAX_PLACE_CHARS=28 (hero truncation), MAX_DRIVER_CHARS=40, MAX_WHIMSY_CHARS=40 — T-26-03-01 mitigation"
  - "Hazard stripe opacity ~30% (alpha=76/255), step=24px, width=12px"
  - "Silent AAC via -f lavfi -i anullsrc is NOT optional — intro.ts has AAC, concat demuxer rejects mismatched track layouts"
  - "Geocoder exceptions (not just None returns) fall through to D-09 whimsy so a misbehaving resolver never blocks a render"

patterns-established:
  - "Pattern: render-or-skip — renderer returns 0.0 on any failure and logs slate_render_failed with a stage kwarg; callers degrade to intro→buffer"
  - "Pattern: SimpleNamespace stand-ins for Event in tests — avoids Phase-22 peak_*/samples bookkeeping the renderer never reads"

requirements-completed: [D-01, D-03, D-04, D-05, D-06, D-07, D-09, D-10, D-11, D-12, D-14]

# Metrics
duration: ~5 min
completed: 2026-04-23
---

# Phase 26 Plan 03: Event Video Title Card Renderer Summary

**Pillow slate composer and ffmpeg PNG→TS encoder with full D-09/D-10/D-11/D-12 fallback matrix and ROLLOVER hazard stripes; 14/14 tests green including ffprobe-verified audio parity.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-23T02:00:51Z
- **Completed:** 2026-04-23T02:05:54Z
- **Tasks:** 2 of 2
- **Files created:** 2

## Accomplishments

- Full fallback matrix implemented and independently tested:
  - D-09 (no GPS → whimsy line), D-10 (geocoder returned None → coord-only), D-11 (MANUAL_CAPTURE → no badge), D-12 (driver credit toggled by config and caller).
- ROLLOVER event badge renders a 45° hazard-stripe overlay over the red body (D-07) via an RGBA overlay composited before the label draw.
- `_encode_ts` produces a concat-demuxer-compatible MPEG-TS with silent AAC 48 kHz stereo audio — verified by `test_encode_ts_produces_valid_stream` and confirmed locally by `ffprobe` (`codec_name=h264`, `width=1280`, `height=720`, `pix_fmt=yuv420p`, `codec_name=aac`, `sample_rate=48000`, `channels=2`).
- `render()` never raises: every failure path (PIL ImportError, font missing, ffmpeg missing, ffmpeg timeout, ffmpeg nonzero exit) returns 0.0 and logs `slate_render_failed` with a `stage` kwarg so plan 26-04 can degrade cleanly to intro→buffer.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: failing tests for TitleCardRenderer** — `1a89cb6` (test)
2. **Task 1 GREEN: TitleCardRenderer — PNG composition + fallback matrix** — `9058df1` (feat)
3. **Task 2: tidy imports in title_card tests** — `5394ba9` (test)

> Task 2's RED tests (`test_encode_ts_*`, `test_render_end_to_end_integration`) were included in the single RED commit at the start of the plan. Task-2's GREEN implementation (`_encode_ts`) was bundled into the Task-1 feat commit because `render()` calls `_encode_ts` directly — splitting them would have produced a Task-1 that couldn't satisfy its own behaviour contract. The final commit is the ruff-sort cleanup after `ffmpeg`/`ffprobe` were confirmed to accept the slate.

## Files Created/Modified

- `src/shitbox/capture/title_card.py` — renderer module. Public: `TitleCardRenderer.__init__`, `render(event, png_path, ts_path, *, geocoder, driver_name) -> float`. Internals: `_resolve_strings`, `_compose_png`, `_encode_ts`. Helpers: `_truncate`, `_text_width`, `_draw_centered`, `_draw_badge`, `_hex_to_rgb`.
- `tests/test_capture_title_card.py` — 14 tests: 9 render-path tests (fallback matrix, driver gating, ROLLOVER flag, Pillow-missing, TS-encode failure), 5 encoder tests (two ffmpeg-integration tests skip if ffmpeg absent; three mocked error paths).

## Public Contract

```python
from shitbox.capture.title_card import TitleCardRenderer

renderer = TitleCardRenderer(
    duration_seconds=3.0,
    show_driver=True,
    whimsy_lines=None,          # None or [] → use DEFAULT_WHIMSY
    resolution="1280x720",
    fps=30,
)

duration_s = renderer.render(
    event,                      # Event-shaped: event_type, start_time, optional lat/lng
    png_path,                   # slate poster
    ts_path,                    # concat-ready segment
    geocoder=engine._reverse_geocoder,   # Callable[[float, float], Optional[str]] | None
    driver_name="Tony",                   # Optional[str]
)
# Returns self.duration_seconds on success, 0.0 on any failure.
```

## Fallback Matrix Decision Table

| Event has lat/lng? | Geocoder provided? | Geocoder result | Hero row       | Coord row          | Notes       |
|--------------------|--------------------|-----------------|----------------|--------------------|-------------|
| yes                | yes                | truthy string   | place name     | `lat, lng`         | Happy path  |
| yes                | yes                | None / empty    | **none**       | `lat, lng`         | D-10        |
| yes                | no                 | N/A             | whimsy line    | **none**           | D-09 fork A |
| no                 | yes or no          | N/A             | whimsy line    | **none**           | D-09 fork B |

Place-name is always truncated to 28 chars with an ellipsis before drawing.

## Audio Parity Rationale

`intro.ts` is produced by `ring_buffer._prepare_intro()` with `-c:a aac -b:a 128k -ac 2 -ar 48000`. The concat demuxer requires matching stream layouts across all entries — if `slate.ts` is audio-less or carries a different audio codec / sample rate, ffmpeg fails with `Different streams` and the whole save aborts. The slate encoder therefore synthesises a silent stereo 48 kHz AAC track via `-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000` for the full slate duration. Verified by ffprobe on the rendered sample; asserted by `test_encode_ts_produces_valid_stream`.

## Claude's-Discretion Choices

Documented up front so plan 26-04 (and a future iteration pass on visuals) has the knobs visible:

| Choice                      | Value             | Rationale |
|-----------------------------|-------------------|-----------|
| `MAX_PLACE_CHARS`           | 28                | Fits hero-row centering at 140 pt without wrapping against 1280 px for realistic place names. Anything longer truncates with a `…`. |
| `MAX_DRIVER_CHARS`          | 40                | Driver credit is a small line; 40 chars covers "Driver: Name Surname (co-driver)" style overrides without bleeding into the badge. |
| `MAX_WHIMSY_CHARS`          | 40                | Same ceiling as driver — whimsy is operator-editable via YAML, cap is a DoS mitigation not a UX rule. |
| Hero Y                      | 220               | Balances against date row at y=400 and coord/driver rows at y=455/500, leaves the top 180 px as quiet negative space. |
| Badge anchor                | (60, 600)         | 60 px margin from left/bottom; badge height >=60 px keeps label legible at 36 pt. |
| Logo max height             | 120 px            | Matches the 80×80 HUD version scaled up for the larger title-card canvas. Aspect-preserving. |
| Hazard stripe opacity       | alpha=76/255 (~30%) | Visible but not so dense it obscures the label. Iterate in 26-04 field testing. |
| Hazard stripe step / width  | 24 px / 12 px     | Ratio 1:2 gives distinct stripes; step smaller than badge height ensures at least two strokes cross the label area. |

## Threat-Model Mitigations

| Threat ID  | Mitigation                                                                                            |
|------------|-------------------------------------------------------------------------------------------------------|
| T-26-03-01 | `_truncate` applied to place-name (28), driver (40), whimsy (40) before any Pillow draw call.          |
| T-26-03-02 | `subprocess.run(..., timeout=60)` kills runaway ffmpeg and logs `slate_ts_timeout`.                    |
| T-26-03-05 | `_compose_png` caught in try/except in `render()` → `slate_render_failed` → 0.0; truetype failure falls back to `ImageFont.load_default()` so dev laptops without DejaVu still render. |

## Test Coverage (14 tests)

Task 1 (PNG / fallback / graceful failure):

1. `test_render_with_place_and_driver` — happy path, PNG is 1280×720 and non-black
2. `test_render_whimsy_when_no_gps` — D-09 branch, no lat/lng, no geocoder
3. `test_render_coord_only_when_geocoder_returns_none` — D-10 branch (arg capture on `_compose_png`)
4. `test_manual_capture_no_badge` — D-11, `show_badge=False` when `MANUAL_CAPTURE`
5. `test_rollover_hazard_stripes` — `is_rollover=True` flag set on `ROLLOVER`
6. `test_show_driver_false` — `show_driver=False` propagates as `driver_name=None` into `_compose_png`
7. `test_driver_name_none` — `driver_name=None` from caller also propagates
8. `test_pillow_missing_fails_gracefully` — `ImportError` in `_compose_png` → 0.0, no raise
9. `test_ts_encode_failure_returns_zero` — `_encode_ts` returning False → 0.0

Task 2 (ffmpeg encoder):

10. `test_encode_ts_produces_valid_stream` — **ffmpeg required**; ffprobe confirms h264 1280×720 yuv420p + AAC 48 kHz stereo
11. `test_encode_ts_ffmpeg_missing_returns_false` — `FileNotFoundError` → False
12. `test_encode_ts_timeout_returns_false` — `TimeoutExpired` → False
13. `test_encode_ts_nonzero_exit_returns_false` — returncode 1 → False
14. `test_render_end_to_end_integration` — **ffmpeg required**; full render() call with real ffmpeg produces both PNG and TS, returns duration

## Verification

- `pytest tests/test_capture_title_card.py -x -q` → `14 passed in 0.41s`
- `ruff check src/shitbox/capture/title_card.py tests/test_capture_title_card.py` → `All checks passed!`
- `mypy src/shitbox/capture/title_card.py` → 0 errors in this module (15 pre-existing errors in unrelated files left untouched per scope-boundary rule)
- ffprobe on a locally rendered `slate.ts`: `codec_name=h264`, `width=1280`, `height=720`, `pix_fmt=yuv420p`, `codec_name=aac`, `sample_rate=48000`, `channels=2` — concat-demuxer compatible with `intro.ts`.

## Deviations from Plan

None. Plan executed exactly as written.

The single bookkeeping note: the plan described Tasks 1 and 2 as separate TDD cycles, but because the Task-1 acceptance criterion required `_encode_ts` to be callable (via the `test_ts_encode_failure_returns_zero` test that monkeypatches it) and `render()` calls `_encode_ts` directly, both implementations shipped in the Task-1 GREEN commit (`9058df1`). The Task-2 tests were authored in the same RED commit (`1a89cb6`), so the gate order (RED → GREEN → cleanup) holds across the three commits.

## Self-Check

- `src/shitbox/capture/title_card.py` — **FOUND**
- `tests/test_capture_title_card.py` — **FOUND**
- `.planning/phases/26-event-video-title-cards/26-03-SUMMARY.md` — **FOUND** (this file)
- Commit `1a89cb6` (RED tests) — **FOUND**
- Commit `9058df1` (GREEN implementation) — **FOUND**
- Commit `5394ba9` (cleanup) — **FOUND**

## Self-Check: PASSED
