# Phase 26: Event Video Title Cards - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Insert a 3-second cinematic title slate between the existing intro clip and the captured
event footage. The slate shows place name (reverse-geocoded), date/time, coords, event-type
badge, driver name (when set), and team logo. Rendered by Pillow as a PNG, looped to MP4 by
ffmpeg, and added to the existing concat list in `ring_buffer._concatenate_segments()`.
The rendered PNG is also persisted alongside the MP4 to replace the current
intro-first-frame poster on the public website.

**In scope:**
- Pillow slate renderer (1280×720 canvas matching the capture output resolution)
- Shared human-readable event-label helper (used by slate, and usable by website/TTS later)
- Fallback behaviour for missing GPS / missing place name / manual captures
- `capture.title_card` config block in `config/config.yaml`
- Integration into `_concatenate_segments()` — slate TS inserted between intro and buffer
- PiP sync offset extension: `setpts` / `enable` gates shift by `intro_duration + slate_duration`
- Save rendered PNG as `<event>_poster.png` next to the MP4; expose `poster_path` via
  `EventStorage.generate_events_json()` so the website can use it

**Out of scope (belongs elsewhere):**
- Re-rendering posters for already-captured events (retroactive backfill)
- Fade / xfade transitions (decided against in favour of hard cut)
- Any changes to the existing ASS/HUD subtitle overlay — that burn-in stays as-is
- Website-side consumption of the new `poster_path` field (separate home-ops repo)

</domain>

<decisions>
## Implementation Decisions

### Timing & transition
- **D-01:** Default card duration is `3.0s` on-screen, exposed as
  `capture.title_card.duration_seconds`.
- **D-02:** Transition is a hard cut at both ends (intro→slate, slate→buffer). No fade,
  no xfade — keeps the concat demuxer path clean and avoids `filter_complex` gymnastics.
- **D-03:** The slate always renders. No minimum-clip gate, no "skip when footage is short"
  logic. A 3s card framing a 5s quick event is still the right choice.

### Visual & typography
- **D-04:** Font pairing is `DejaVu Sans` (display) + `DejaVu Sans Mono` (coords).
  Matches the existing HUD overlay (`src/shitbox/capture/overlay.py:110-111`). No new TTFs
  shipped.
- **D-05:** Layout is **place-hero / stacked metadata / badge bottom-left / logo bottom-right**.
  - Place name at ~140pt (display)
  - Date + time row at ~40pt
  - Coord string at ~28pt mono
  - Event-type badge bottom-left (coloured background + human-readable label)
  - Logo bottom-right, reusing `src/shitbox/capture/assets/shitbox_rally_logo.png`
- **D-06:** Canvas is **1280×720** to match the existing capture output. No upscaling
  or letterboxing.
- **D-07:** Event-type badge colours reuse the website palette:
  - HIGH_G `#da3633`, BIG_CORNER `#d29922`, HARD_BRAKE `#f85149`, ROUGH_ROAD `#8957e5`,
    MANUAL/BUTTON `#238636`, BOOT `#1f6feb`
  - **ROLLOVER is new:** `#e74c3c` red with black diagonal hazard stripes behind the label.
    Unambiguously signals "rollover" at a glance and distinguishes from HIGH_G.
- **D-08:** Event labels are rendered **human-readable**, not as enum strings. Lookup
  helper lives in a shared module (`src/shitbox/events/labels.py` or similar neutral
  location) so website renderers and the TTS path can import the same table.
  Canonical mapping:
  - `HARD_BRAKE` → `Hard Brake`
  - `BIG_CORNER` → `Big Corner`
  - `HIGH_G` → `High G`
  - `ROUGH_ROAD` → `Rough Road`
  - `MANUAL` → `Manual Capture`
  - `BUTTON` → `Manual Capture`
  - `BOOT` → `System Start`
  - `ROLLOVER` → `Rollover`

### Fallback behaviour
- **D-09:** No GPS lock at save time → **skip the place name** and use a rotating whimsy
  line instead. Renders with the same typographic weight as a real place name.
  Initial pool (YAML-configurable):
  - `Here be dragons`
  - `GPS off having a lie down`
  - `Somewhere between A and B`
  - `The map ends here`
  - `Lost, but enthusiastic`
  One line is picked per slate. Random selection is fine; no need for round-robin state.
  Coords line is also skipped in this case (we have nothing to show).
- **D-10:** GPS present but reverse_geocoder returns no place (ocean, remote waypoint)
  → show **coords only** on the mono row, skip the place-name row. Same semantics as
  `_resolve_place_name()` returning `None` in `timelapse_compiler.py`.
- **D-11:** Manual / button-press events → **no event badge**. The badge slot is filled
  by the driver credit instead. Keeps the composition balanced without inventing a
  pseudo-event.
- **D-12:** Driver name (from `driver_state.active_driver`) is shown on **every** slate
  when a driver is set — not just on manual captures. Small text below the date line
  (e.g. `Driver: Tony`). Gated by `capture.title_card.show_driver`.

### Integration & config
- **D-13:** Concat sequence is **`intro → slate → buffer`**. Slate lives immediately
  before the footage the viewer cares about. Matches the handoff intent.
- **D-14:** Slate integrates via the existing concat demuxer path. Renderer pre-converts
  the PNG to MPEG-TS (same pattern as `_prepare_intro()` at `ring_buffer.py:374+`) and
  the TS file gets appended after `self._intro_ts` in `_concatenate_segments()` at
  `ring_buffer.py:1337+`. Save as `slate.ts` in the per-save tmp dir so it's cleaned up
  with the rest.
- **D-15:** PiP sync offset shifts by `slate_duration`. The filter graph around
  `ring_buffer.py:1284+` currently does `setpts=PTS-STARTPTS+{intro_duration}/TB` and
  `enable='gte(t,{intro_duration})'` — both terms become `intro_duration + slate_duration`.
  No PiP equivalent of the slate is rendered; the cabin stream stays invisible during
  both intro and slate, then appears from T=intro+slate onward.
- **D-16:** Config block under `capture.title_card`:
  - `enabled: true` — master switch (flip to `false` if slates start misbehaving in the field)
  - `duration_seconds: 3.0`
  - `show_driver: true`
  - `whimsy_lines:` — list of strings; overrides the defaults in code if set
- **D-17:** Rendered PNG is saved as `<event>_poster.png` in the same capture dir as
  the MP4. `EventStorage.generate_events_json()` adds a `poster_path` field to each
  event record. Website consumption is deferred to a follow-up (backwards compatible —
  if the field is absent, existing intro-poster fallback still works).

### Claude's Discretion
- Exact Pillow typography metrics (kerning, leading, precise pixel positions) — iterate
  against real rendered output rather than locking a number now
- Place-name truncation / line-wrap rules for very long names (e.g. "North Queensland
  Hinterland Wilderness Area") — sensible default in code
- File naming / logging keys for the slate render path
- Whether to cache the whimsy-pool selection per event (probably not — re-picking on
  every render is fine)
- Where exactly `labels.py` lives (events vs storage vs utils) — pick whatever couples
  least with existing code
- Testing strategy (golden-image diff vs property-based) — planner decides

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase brief (source of truth for why this exists)
- `.planning/STATE.md` §"Roadmap Evolution" — Phase 26 origin note (2026-04-23);
  SDK `phase.add` numbering bug also logged here
- `.planning/ROADMAP.md` "Phase 26: Event Video Title Cards" line — one-liner goal

### Capture integration points
- `src/shitbox/capture/ring_buffer.py::_concatenate_segments()` (line 1337+) —
  concat list builder; slate TS inserts after `self._intro_ts`, before segments
- `src/shitbox/capture/ring_buffer.py::_prepare_intro()` (line 374+) — TS pre-conversion
  pattern; slate renderer mirrors this for its output
- `src/shitbox/capture/ring_buffer.py:1260-1293` — PiP filter graph with
  `intro_duration` offsets; both `setpts` and `enable` gates extend to
  `intro_duration + slate_duration`
- `src/shitbox/capture/overlay.py:110-111` — DejaVu Sans + Mono in the HUD burn-in
  (reference font match)
- `src/shitbox/capture/assets/shitbox_rally_logo.png` — existing logo asset

### Reverse geocoder reuse
- `src/shitbox/sync/timelapse_compiler.py::_resolve_place_name()` (lines 92-115) —
  copy this pattern; don't re-invent
- `src/shitbox/events/engine.py:776-782` — reverse_geocoder init (guarded)
- `src/shitbox/events/engine.py:1479-1501` — search usage pattern

### Driver state (for D-12)
- `src/shitbox/storage/driver_state.py` (or wherever Phase 13 landed the active-driver
  helper) — source for the driver name on the slate

### Config + events.json (for D-16, D-17)
- `src/shitbox/utils/config.py` §capture block — where the new `title_card` dataclass
  is added
- `src/shitbox/storage/events.py::EventStorage.generate_events_json()` — where
  `poster_path` is added

### Project conventions (must respect)
- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/feedback_play_dont_perfect.md` —
  reach for what's installed; Pillow + ffmpeg, no Blender, no heavy setups
- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/feedback_ai_tells_in_copy.md` —
  UK/Aus English, no em-dashes, dry jokes land on concrete images (applies to whimsy pool)
- `CLAUDE.md` §"Code Conventions" — structlog with kwargs, ruff E/F/I/W, line-length 100,
  Python 3.9 target

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_prepare_intro()`**: PNG → TS conversion pattern (ffmpeg loop + `-f mpegts`)
  with ffprobe duration readback. Slate renderer can mirror this almost line-for-line.
- **`_resolve_place_name()`**: reverse-geocoder wrapper returning `Optional[str]`.
  Already handles the "no lock / no result" branch — we just wire it in.
- **`shitbox_rally_logo.png`**: shipped in `src/shitbox/capture/assets/` for the slate
  corner. No new asset pipeline needed.
- **Website event colours**: already duplicated in site-side code; the `labels.py`
  helper could also hold the colour map so slate and website stay in lockstep.

### Established Patterns
- **Concat demuxer** (not byte-concat) is the committed path for TS joining.
  Documented reasoning in `_concatenate_segments` docstring and in memory
  `project_pip_sync_fix.md`. Slate follows this convention.
- **`intro_duration` as first-class offset**: already used in both the ASS overlay
  shifter (`overlay.py:312+`) and the PiP filter chain. Adding `slate_duration`
  alongside is a natural extension, not a new pattern.
- **Graceful degradation for optional hardware**: GPS absence is routine. Slate
  fallback (D-09, D-10) matches the system's broader attitude.
- **Config loaded into nested dataclasses** via `_dict_to_dataclass`. New
  `TitleCardConfig` dataclass goes under the existing `CaptureConfig`.

### Integration Points
- **`ring_buffer._concatenate_segments()`**: slate TS appended to `files` list after
  intro, before segments (D-13, D-14).
- **PiP filter chain** (`ring_buffer.py:1284+`): single offset term extended from
  `intro_duration` to `intro_duration + slate_duration` (D-15).
- **`EventStorage.generate_events_json()`**: new `poster_path` key on each event
  record (D-17).
- **`config/config.yaml`**: new `capture.title_card` block (D-16).

</code_context>

<specifics>
## Specific Ideas

- The slate should feel like a "location title" from a travel documentary — place name
  as the hero, not the event badge. The viewer's first question is "where are we",
  not "what happened".
- Whimsy in the no-GPS case matters — this is a rally, not enterprise software. Lines
  land on concrete images (`GPS off having a lie down`, `Here be dragons`) rather than
  generic "location unknown" placeholders.
- ROLLOVER hazard stripes should look like actual hazard tape, not just a tint.
  Diagonal 45° black bars at low opacity behind the red badge body.
- Driver credit is deliberately subtle (`Driver: Tony` below the date) — it's a quiet
  attribution, not a hero element.
- The slate doubling as the website poster is a genuine upgrade on a piece of
  long-standing low-grade naff (the current first-frame-of-intro poster is generic
  across every event).

</specifics>

<deferred>
## Deferred Ideas

- **Retroactive poster backfill**: render slates for already-captured events. Nice
  but not urgent, raises questions about events with stale/missing GPS from months
  back. Backlog item.
- **Fade / xfade transitions**: rejected in favour of hard cut (D-02). If the hard cut
  ever starts feeling abrupt in the wild, revisit — likely using baked-in PNG alpha
  animation rather than `filter_complex`.
- **Website-side consumption of `poster_path`**: separate repo (home-ops), separate
  phase. This phase just produces the field.
- **Place-name casing / typography rules for long names**: handled by Claude's
  Discretion; might surface as a follow-up tweak once real footage comes back.
- **Testability approach** (golden-image diff vs property-based): left to
  `/gsd-plan-phase` to resolve.

</deferred>

---

*Phase: 26-event-video-title-cards*
*Context gathered: 2026-04-23*
