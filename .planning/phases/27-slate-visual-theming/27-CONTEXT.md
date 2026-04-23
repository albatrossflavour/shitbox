# Phase 27: Slate Visual Theming - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

A typography-led visual design pass over `TitleCardRenderer`
(`src/shitbox/capture/title_card.py`). The rendering pipeline
(Pillow PNG → MPEG-TS via ffmpeg → concat demuxer) is unchanged.
The 1280×720 canvas, the 3-second duration, the layout regions
(place hero / date+driver row / coord row / badge bottom-left /
logo bottom-right), the fallback behaviours (no-GPS whimsy,
coord-only when reverse geocoder returns nothing), the badge
composition, and `TitleCardConfig` shape all stay as Phase 26
shipped them.

The theme is a Game of Thrones gestural homage — engraved Roman
serif typography (Cinzel), place name as a ranked location title
(`WINTERFELL` style), state suffix dropped from the hero. Palette
and badge styling are deliberately preserved for website
consistency. The contrast is the joke: a 2001 Ford Laser's
hard-brake event rendered with the visual gravitas of a Westeros
location title.

**In scope:**

- Bundle Cinzel TTF (OFL-licensed) into `src/shitbox/capture/assets/`
- Replace `FONT_DISPLAY` constant in `title_card.py` with the bundled
  Cinzel path (Bold for hero, Regular for date/driver row)
- Apply ALL CAPS to hero text in `_resolve_strings` / `_compose_png`
- Drop state suffix from hero (skip the existing `_abbreviate_au_states`
  call on the hero path; keep the helper available for elsewhere)
- Re-validate G-02 measure-and-shrink-fit against the new metrics
  (Cinzel ALL CAPS has different glyph widths than DejaVu Sans Bold
  mixed-case; the 1160px safe width still applies but the floor /
  step thresholds may need re-tuning)
- Re-validate `MAX_PLACE_CHARS` cap (28) against Cinzel ALL CAPS
  rendering — letter-spaced caps eat horizontal width fast

**Out of scope (deliberate exclusions):**

- Palette change — `#0d1117` bg, white/grey text stay as-is for
  website parity
- Motif element (crest, ribbon, divider, sigil) — typography is
  the design language; no graphic motif is added
- Event badge styling — Phase 26 solid-rectangle composition,
  per-event hex colours, and ROLLOVER hazard stripes all remain
  untouched
- Coord row typography — DejaVu Sans Mono kept (the modern device
  leaking into the Westeros frame is part of the bit)
- Logo asset — existing `shitbox_rally_logo.png` stays in its
  bottom-right slot
- Per-event-type illustrations / iconography (stretch tier — deferred)
- Animated slate intro variants (stretch tier — deferred)
- Crest-style driver credit block (stretch tier — deferred)
- Retroactive backfill for already-captured events (Phase 26 deferred)
- Website-side consumption changes (separate home-ops repo, separate
  phase)

</domain>

<decisions>
## Implementation Decisions

### Scope

- **D-01:** Scope is **Minimum tier, narrowed to typography-only.**
  Of the four Min-tier elements listed in `ROADMAP.md` Phase 27
  ("one custom typeface, deliberate colour palette, a single motif
  element, badge polish"), Phase 27 delivers only the typeface swap.
  Palette is deliberately preserved (a deliberate decision, not a
  default), motif is deliberately omitted, badge is deliberately
  untouched. Stretch tier elements are not in scope.

- **D-02:** ROADMAP success criterion 1 reads *"a visible design
  language (non-default typeface, intentional palette, at least one
  motif element) distinct from the Phase 26 utilitarian layout"*.
  This phase reinterprets that criterion as: **the Cinzel typeface
  IS the design language**. Verification should treat
  "non-default typeface" + "deliberately preserved palette" +
  "ALL CAPS hero with state dropped" as collectively satisfying
  the "visible design language distinct from Phase 26" intent.
  No separate graphic motif element will be added.

### Typography

- **D-03:** Display typeface is **Cinzel** (the Trajan-alike Google
  Font under SIL Open Font Licence). It is the typeface the public
  reads as "Game of Thrones". Cinzel ships as a TTF and gets
  bundled into `src/shitbox/capture/assets/` rather than relying on
  Pi system fonts (DejaVu is a Pi-image given; Cinzel is not).

- **D-04:** Font roles:
  - Hero: Cinzel **Bold** at FONT_HERO (140pt), measure-and-shrink
    pipeline preserved
  - Date row: Cinzel **Regular** at FONT_DATE (40pt)
  - Driver row: Cinzel **Regular** at FONT_DRIVER (40pt — locked
    from Phase 26 on-Pi UAT)
  - Coord row: **DejaVu Sans Mono** at FONT_COORD (28pt) — kept
    intentionally; the modern coordinate string leaking into the
    Westeros frame is part of the joke
  - Badge label: unchanged (whatever Phase 26 currently uses for
    the badge label — `FONT_DISPLAY` Bold at FONT_BADGE 36pt)

- **D-05:** Hero text is rendered **ALL CAPS** in code (apply
  `.upper()` after place resolution / whimsy selection). Reads as
  an engraved location title.

- **D-06:** Hero **drops the state suffix entirely**. After
  reverse-geocoding, strip everything after the first comma so
  `Narellan, New South Wales` → `Narellan` → `NARELLAN`. The
  existing `_abbreviate_au_states` helper stays in place
  (potentially used elsewhere) but is no longer called on the
  hero path.

- **D-07:** Whimsy lines and any added copy continue to follow
  `feedback_ai_tells_in_copy.md` — UK/Aus English, concrete images,
  no abstract-noun whimsy. No changes to the existing whimsy pool
  in this phase. Whimsy lines also rendered ALL CAPS in Cinzel for
  consistency with the hero.

### Palette and badge (deliberately preserved)

- **D-08:** Background `#0d1117`, primary text `#ffffff`, secondary
  text `#c9d1d9`, mono text `#8b949e` — all unchanged from Phase 26.
  The atmosphere stays consistent with the website rather than
  shifting toward parchment / leather / brass. "Slightly more
  whimsy than real GoT, but consistent" is the explicit user steer.

- **D-09:** Per-event badge hex colours, badge composition (solid
  rectangle), badge label rendering, and ROLLOVER hazard stripes
  are all preserved exactly as Phase 26 shipped them. Phase 27
  does not touch `_draw_badge` or `EVENT_COLOURS`.

### Asset shipping

- **D-10:** Cinzel TTFs bundled in
  `src/shitbox/capture/assets/cinzel/` (subdir to keep the assets
  dir tidy as more files arrive). At minimum: `Cinzel-Bold.ttf`
  and `Cinzel-Regular.ttf`. SIL OFL licence text shipped alongside
  the fonts (`OFL.txt`). No font subsetting — slates only render
  Latin glyphs and the file size is small enough not to warrant it.

- **D-11:** Font path constants in `title_card.py` change from
  hardcoded `/usr/share/fonts/...` system paths to relative
  `Path(__file__).parent / "assets" / "cinzel" / "Cinzel-Bold.ttf"`
  resolution (mirroring the existing `LOGO_PATH` pattern).
  Existing `_font(path, size)` graceful-fallback to
  `ImageFont.load_default()` continues to handle the
  Pillow-not-installed dev-laptop case.

- **D-12:** DejaVu Sans Mono path stays as a system path —
  the mono row continues to use the Pi-image-given DejaVu Mono.
  Only the display family is bundled.

### Re-validation work

- **D-13:** G-02 measure-and-shrink-fit (`_fit_hero_to_canvas`,
  `HERO_FONT_FLOOR=100`, `HERO_FONT_STEP=10`) needs re-tuning
  against Cinzel ALL CAPS metrics. Cinzel caps are wider per glyph
  than DejaVu Sans Bold mixed-case at the same point size. The
  1160px safe width is fixed by the canvas; the floor and step
  may need adjustment so a long ALL CAPS place name still fits
  without dropping below a legible size. **Planner to spec a
  short golden-image / measurement check** during planning, not
  a full re-derivation.

- **D-14:** `MAX_PLACE_CHARS` (currently 28) may need to be
  tightened for Cinzel ALL CAPS. 28 mixed-case DejaVu chars
  ≠ 28 ALL CAPS Cinzel chars in horizontal real estate. Planner
  decides whether to lower the cap or rely on G-02 shrink-fit
  to handle the overflow.

### Claude's Discretion

- Exact Cinzel weight choice for hero if Bold reads too heavy
  ALL CAPS at 140pt (could try Cinzel SemiBold or Cinzel Black —
  iterate against rendered output)
- Letter-spacing / tracking on ALL CAPS hero (Pillow doesn't have
  built-in tracking; if needed, simulate with manual character
  positioning — but only if default kerning looks bad)
- Whether driver row stays Cinzel Regular or shifts to a Cinzel
  italic / SC variant (italics in Cinzel exist; SC = small caps)
- File naming for the bundled font dir layout
- Whether to ship Cinzel SemiBold and Black as options too, or
  just Bold + Regular (asset footprint is small either way)
- Where to apply the `.upper()` call (in `_resolve_strings` vs
  `_compose_png`) — pick whichever is cleaner

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 26 baseline (the slate this phase restyles)

- `.planning/phases/26-event-video-title-cards/26-CONTEXT.md` —
  full Phase 26 context. Decisions D-01 through D-17 are LOCKED
  upstream of this phase; Phase 27 only restyles the visual
  surface, never touches the structural decisions
- `.planning/phases/26-event-video-title-cards/26-PATTERNS.md` —
  ffmpeg / concat-demuxer / TS encoding gotchas; Phase 27 must
  not regress these (silent AAC track requirement, font fallback
  pattern, etc.)
- `src/shitbox/capture/title_card.py` — the file Phase 27 modifies.
  Key sites: `FONT_DISPLAY` / `FONT_MONO` constants (lines 50-51),
  `FONT_HERO` / `FONT_DATE` / `FONT_DRIVER` / `FONT_BADGE` constants
  (lines 71-75), `_resolve_strings` (~line 200+), `_compose_png`
  (~line 289+), `_fit_hero_to_canvas` (line 467+),
  `_abbreviate_au_states` (line 106+ — kept but no longer called
  on the hero path)
- `src/shitbox/events/labels.py` — `EVENT_COLOURS` and
  `ROLLOVER_STRIPE_COLOUR` are the badge palette. NOT modified
  by Phase 27, but the planner needs to know they exist and
  why they're untouched

### Roadmap and scope

- `.planning/ROADMAP.md` Phase 27 block (lines 469-495) — goal,
  scope tiers, success criteria. Note: success criterion 1 is
  reinterpreted by D-02 above

### Voice / copy / asset conventions

- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/feedback_ai_tells_in_copy.md` —
  UK/Aus English, no abstract-noun whimsy, dry register on
  concrete images. Applies to any new copy, e.g. if planner
  invents new whimsy lines or a tagline (it shouldn't, but if
  it does, this file binds)
- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/feedback_play_dont_perfect.md` —
  reach for what's installed; Pillow + ffmpeg, no Blender, no
  heavy setups. Cinzel TTF is the only new asset
- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/project_rally_car_name.md` —
  the car is "Shit of Theseus" (Ship of Theseus paradox pun).
  GoT homage is gestural, not pastiche; the contrast between
  the engraved location title and the 2001 Ford Laser is the joke
- `CLAUDE.md` §"Code Conventions" — structlog with kwargs, ruff
  E/F/I/W, line-length 100, Python 3.9 target

### Cinzel font (asset to bundle)

- Source: <https://fonts.google.com/specimen/Cinzel> — designed by
  Natanael Gama. Licensed under SIL Open Font Licence 1.1.
  Free for embedding and bundling; OFL.txt must ship with the
  font files

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `Path(__file__).parent / "assets" / ...` — already used by
  `LOGO_PATH` in `title_card.py:52`. New `cinzel/` subdir under
  `assets/` follows the same convention. No new path-resolution
  code needed
- `_font(path, size)` helper inside `_compose_png` — already does
  a try/except `ImageFont.truetype` → fallback to
  `ImageFont.load_default()`. Cinzel paths slot in unchanged
- `_fit_hero_to_canvas` (line 467) — measure-and-shrink pipeline
  is font-agnostic; it just takes a font path. New Cinzel Bold
  path drops in. The thresholds may need re-tuning per D-13
- `EVENT_COLOURS` table in `events/labels.py` — Phase 27 reads
  this only via `_draw_badge` calls that are already in place;
  no changes

### Established Patterns

- **Constants at module scope, used everywhere** — `FONT_DISPLAY`,
  `FONT_MONO`, `FONT_HERO` etc. are all module-level constants in
  `title_card.py`. Phase 27 changes the values of `FONT_DISPLAY`
  (and possibly adds `FONT_DISPLAY_BOLD` / `FONT_DISPLAY_REGULAR`
  if we need both weights as separate paths) without restructuring
- **Pillow imported lazily inside `_compose_png`** — keeps the
  module import-safe on dev laptops without PIL. Don't move the
  PIL import to module scope
- **Graceful font fallback to `ImageFont.load_default()`** — already
  exists. Bundled Cinzel + system DejaVu Mono both flow through
  this. Dev laptops without Pillow still pass tests
- **Backwards-compatible config shape** — `TitleCardConfig` shape
  stays the same. No new YAML keys are added by Phase 27 (D-08
  in Phase 26 implied palette/typography were not configurable;
  this phase doesn't change that)

### Integration Points

- `title_card.py` is the only module Phase 27 modifies. No changes
  to `ring_buffer.py`, `events/engine.py`, `events/labels.py`,
  `storage/events.py`, or `utils/config.py`
- `src/shitbox/capture/assets/cinzel/` is a new subdir. The
  packaging config (`pyproject.toml`) likely needs to be checked
  to ensure font files are included in the wheel (Phase 26 added
  the logo asset; planner verifies that pattern is in place)

</code_context>

<specifics>
## Specific Ideas

- The slate should read like a Game of Thrones location title with
  the volume turned down half a notch. The font does the heavy
  lifting; the dark palette stays out of the way; nothing else is
  added on top. Tony's exact words: "slightly more whimsy than
  real GoT, but consistent" and "don't want a hat on a hat".

- The contrast between the engraved Roman serif and the 2001 Ford
  Laser is the punchline. The slate doesn't try to look like a
  rally car telemetry slate any more — it looks like the title
  card for an episode where the protagonist is a 24-year-old
  hatchback with a hard-brake habit. That's the joke.

- Coord row stays in DejaVu Mono on purpose. The modern coordinate
  string is the device tape leaking into the Westeros frame.
  Replacing the mono row with a "cartographer's annotation"
  italic was considered and rejected — the literal mono coords
  are funnier.

- Badge colour palette parity with the website matters. The
  website event feed uses these exact hexes; the slate shouldn't
  drift out of sync just because the hero typography changed.

- Cinzel ALL CAPS hero with state dropped means a place like
  Narellan reads as `NARELLAN`. The same place rendered as
  `WINTERFELL` would feel right. That's the bar.

</specifics>

<deferred>
## Deferred Ideas

- **Stretch tier elements** (per-event-type illustration / iconography,
  animated slate intro variants, crest-style driver credit block) —
  out of scope for Phase 27, kept on the backlog. Revisit only
  if Phase 27 lands well in the wild AND there's still time
  before the rally
- **Hero with state subline** (`NARELLAN` large + `NSW` small under
  it) — rejected for Min, could revisit if same-name town
  ambiguity actually causes problems on the rally
- **House-words ribbon** ("Gaffer Tape It. Drive It. Tape Better."
  rendered small under hero or above bottom row) — rejected as
  "hat on a hat", could revisit if typography alone feels
  under-themed in the wild
- **Engraved hairline divider** (single horizontal hairline between
  hero and date row, GoT title style) — rejected as motif
- **Sigil mark in corner** (small engraved seal replacing or
  complementing the existing logo) — rejected; existing
  rally logo stays in its bottom-right slot
- **Palette shift toward parchment / leather / brass** — rejected
  for Min in favour of website parity; revisit only if a future
  phase decides the website also wants a thematic palette pass

### Reviewed Todos (not folded)

- `2026-04-22-extend-title-card-to-per-capture-videos.md` — todo
  was the precursor of Phase 26 itself, which shipped exactly
  what it asked for. Not folded into Phase 27 (different scope:
  visual theming, not pipeline extension). Should be closed /
  archived as a separate cleanup, not as part of this phase

</deferred>

---

*Phase: 27-slate-visual-theming*
*Context gathered: 2026-04-24*
