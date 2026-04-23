# Phase 27: Slate Visual Theming - Research

**Researched:** 2026-04-24
**Domain:** Pillow typography (TTF bundling, ALL CAPS rendering, measure-and-shrink-fit metrics)
**Confidence:** HIGH

## Summary

Phase 27 is a targeted typography swap on a pipeline Phase 26 already proved works. The code locus is narrow (one module, a handful of module-level constants, two helpers), the risks are well-bounded, and the empirical work done in this research session pins down the two numerical unknowns the planner needs: Cinzel Bold ALL CAPS at 140pt is roughly **1.12-1.21x** the width of DejaVu Sans Bold mixed-case at the same point size on realistic AU place names, and once the state suffix is dropped, every AU place name on any rally route fits the 1160px safe width without triggering the shrink-fit — with generous headroom for anything up to 11 characters at 140pt. The existing `_fit_hero_to_canvas` floor (100pt) and step (10pt) do not need to change.

The one piece of genuine tech debt this phase exposes is the `pyproject.toml` packaging glob — `shitbox = ["capture/assets/*.png", ...]` is non-recursive and globs only PNG, so dropping a `cinzel/` subdirectory of TTFs into `capture/assets/` without updating that glob would silently ship an unusable wheel. That fix is a one-line change but it must land in the same phase, not a follow-up.

**Primary recommendation:** Ship both weights as static TTFs (`Cinzel-Bold.ttf` ~68KB + `Cinzel-Regular.ttf` ~66KB) under `src/shitbox/capture/assets/cinzel/` alongside `OFL.txt`, apply `.upper()` in `_resolve_strings` (keep the hero path as-is: drop state suffix before the existing truncation + abbreviation dance, then upper), widen the `package-data` glob to include TTFs and the licence, leave `HERO_FONT_FLOOR` / `HERO_FONT_STEP` unchanged, and extend the existing Phase 26 tests with Cinzel-specific assertions rather than building new infrastructure.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Font file storage | Python package assets (`src/shitbox/capture/assets/cinzel/`) | — | Mirrors existing `shitbox_rally_logo.png` pattern; `Path(__file__).parent / "assets" / ...` is already the in-tree convention |
| Font path resolution | `title_card.py` module constants | — | `FONT_DISPLAY_*` constants replace the hardcoded `/usr/share/fonts/truetype/dejavu/...` paths; same shape as `LOGO_PATH` |
| String transform (ALL CAPS, state-drop) | `TitleCardRenderer._resolve_strings` | — | Upstream of measurement; keeps `_compose_png` purely rendering; `_abbreviate_au_states` stays in the tree but is no longer called on the hero path |
| Width measurement + shrink-fit | `_fit_hero_to_canvas` helper (unchanged) | — | Font-agnostic already; takes a path argument; receiving Cinzel Bold path instead of DejaVu path is all that changes |
| Asset packaging for wheel | `pyproject.toml` `[tool.setuptools.package-data]` | — | Phase 26 shipped only PNG glob; TTF extension is load-bearing for Phase 27 |
| Licence compliance (SIL OFL 1.1) | `OFL.txt` shipped alongside binaries | — | OFL requires the licence text ship with redistributed font software; the wheel counts as redistribution |

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scope**

- **D-01:** Minimum tier, narrowed to typography-only. Of the four Min-tier ROADMAP elements ("one custom typeface, deliberate colour palette, a single motif element, badge polish"), deliver only the typeface swap. Palette preserved deliberately. Motif omitted. Badge untouched.
- **D-02:** ROADMAP success criterion 1 ("visible design language distinct from Phase 26") is satisfied by Cinzel + ALL CAPS + state-drop collectively. No separate motif element.

**Typography**

- **D-03:** Display typeface is Cinzel (Trajan-alike, SIL OFL). Bundled into `src/shitbox/capture/assets/` rather than relying on Pi system fonts.
- **D-04:** Font roles:
  - Hero: Cinzel **Bold** at `FONT_HERO=140pt`, measure-and-shrink pipeline preserved
  - Date row: Cinzel **Regular** at `FONT_DATE=40pt`
  - Driver row: Cinzel **Regular** at `FONT_DRIVER=40pt`
  - Coord row: **DejaVu Sans Mono** at `FONT_COORD=28pt` (kept; the joke)
  - Badge label: unchanged (`FONT_DISPLAY` Bold at `FONT_BADGE=36pt`)
- **D-05:** Hero rendered ALL CAPS via `.upper()` after place resolution / whimsy selection.
- **D-06:** Hero drops state suffix entirely. Strip everything after the first comma: `Narellan, New South Wales` → `Narellan` → `NARELLAN`. `_abbreviate_au_states` stays in place, no longer called on hero path.
- **D-07:** Whimsy pool continues to follow `feedback_ai_tells_in_copy.md` (UK/Aus English, concrete images). Whimsy rendered ALL CAPS in Cinzel for consistency.

**Palette and badge (preserved)**

- **D-08:** Background `#0d1117`, primary `#ffffff`, secondary `#c9d1d9`, mono `#8b949e` — all unchanged.
- **D-09:** Per-event badge colours, badge composition, ROLLOVER hazard stripes — all preserved. Phase 27 does not touch `_draw_badge` or `EVENT_COLOURS`.

**Asset shipping**

- **D-10:** Cinzel TTFs bundled in `src/shitbox/capture/assets/cinzel/` subdir. Minimum `Cinzel-Bold.ttf` + `Cinzel-Regular.ttf`. SIL OFL licence text shipped alongside (`OFL.txt`). No subsetting.
- **D-11:** Font path constants resolve relative to `Path(__file__).parent / "assets" / "cinzel" / ...`, mirroring `LOGO_PATH`. Existing `_font()` fallback to `ImageFont.load_default()` continues to handle dev-laptop cases.
- **D-12:** DejaVu Sans Mono path stays a system path — only the display family is bundled.

**Re-validation work**

- **D-13:** G-02 measure-and-shrink-fit (`_fit_hero_to_canvas`, `HERO_FONT_FLOOR=100`, `HERO_FONT_STEP=10`) re-validated against Cinzel ALL CAPS metrics. Planner specs a short golden-image / measurement check, not a full re-derivation.
- **D-14:** `MAX_PLACE_CHARS=28` re-examined for Cinzel ALL CAPS. Planner decides whether to lower the cap or rely on shrink-fit.

### Claude's Discretion

- Exact Cinzel weight for hero if Bold reads too heavy ALL CAPS at 140pt (Cinzel SemiBold or Cinzel Black — iterate against rendered output)
- Letter-spacing / tracking on ALL CAPS hero (Pillow lacks built-in tracking; simulate with manual positioning only if default kerning looks bad)
- Whether driver row stays Cinzel Regular or shifts to italic / SC variant
- File naming for the bundled font dir
- Whether to ship Cinzel SemiBold / Black as additional options or just Bold + Regular
- Where to apply `.upper()` (`_resolve_strings` vs `_compose_png`)

### Deferred Ideas (OUT OF SCOPE)

- Stretch tier (per-event-type iconography, animated slate variants, crest-style driver credit)
- Hero with state subline (NARELLAN large + NSW small)
- House-words ribbon / engraved hairline divider / sigil mark
- Palette shift toward parchment / leather / brass
- Retroactive poster backfill (Phase 26 deferred, still deferred)

## Phase Requirements

No explicit REQ-IDs are mapped to this phase — ROADMAP success criteria SC1-SC5 apply directly:

| ID | Description | Research Support |
|----|-------------|------------------|
| SC1 | Themed slate renders as both poster PNG and in-video slate with visible design language distinct from Phase 26 | Cinzel + ALL CAPS + state-drop is the design language (per D-02); pipeline unchanged means both surfaces inherit the typography for free |
| SC2 | All event types + no-GPS whimsy render correctly under new theme | Only the display typeface changes; badge logic is untouched; whimsy pool re-renders via the same `_resolve_strings` path |
| SC3 | `TitleCardConfig` shape stays backward-compatible | CONTEXT.md confirms no new YAML keys — dataclass shape frozen |
| SC4 | G-02 measure-and-shrink fit behaviour preserved for long place names | Empirical widths (below) show floor/step thresholds do not need changing; existing `_fit_hero_to_canvas` is font-agnostic |
| SC5 | Rendered slate fits 1280×720 canvas with safe margins | `SAFE_MARGIN_PX=60` → `safe_w=1160` unchanged; Cinzel Bold 140pt "NARELLAN" measures 805px — well inside |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pillow | 11.3.0 dev / pyproject pinned `>=10.0.0` | TTF rendering via `ImageFont.truetype` + `ImageDraw.text` | Already the only renderer in-tree (Phase 26); has native TTF support with FreeType, kerning enabled by default for TTF |
| Cinzel (SIL OFL 1.1) | Static TTF v2.000 (NDISCOVER upstream) or `Cinzel[wght].ttf` variable (Google Fonts) | Display typeface, Bold for hero + Regular for date/driver | Explicit user choice (D-03); Trajan-alike; reads unmistakably as "Game of Thrones" |
| DejaVu Sans Mono | Pi-image system font | Coord row at 28pt (unchanged) | Kept on purpose (D-12) — the modern coordinate string in the Westeros frame is the joke |

**Installation:** No pip additions. `pillow>=10.0.0` already in `pyproject.toml`.

**Version verification (2026-04-24):**

- Pillow current stable: 11.3.0 (dev box has this installed). `features.check("raqm")` is True on dev, so OpenType feature control is available if ever needed — not used in the plan. `[VERIFIED: local import]`
- Cinzel variable font `Cinzel[wght].ttf`: 122KB, weight axis covers 400-900. Canonical fetch: `github.com/google/fonts/raw/main/ofl/cinzel/Cinzel%5Bwght%5D.ttf`. `[VERIFIED: downloaded, file command confirms TrueType with weight axis]`
- Cinzel static Bold (v2.000): 68KB. Canonical fetch: `github.com/NDISCOVER/Cinzel/raw/master/fonts/ttf/Cinzel-Bold.ttf` (NDISCOVER is the upstream referenced in OFL.txt). `[VERIFIED: downloaded, 67.2 KB]`
- Cinzel static Regular (v2.000): 66KB. `[VERIFIED: downloaded, 65.4 KB]`
- Cinzel static Black (v2.000): 66KB. `[VERIFIED: downloaded, should Bold-at-140pt-UC read too heavy]`

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None | — | — | This is a pure-typography phase; no new dependencies |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Two static TTFs (Bold + Regular) | Single variable `Cinzel[wght].ttf` (122KB) | Variable is slightly smaller in total than Bold+Regular combined (122 vs 134 KB). But: Pillow's `ImageFont.truetype` needs the `font_variation_axes=` keyword to select a weight along the wght axis — extra plumbing for no real gain at ~12KB savings. Static TTFs match the existing `_font(path, size)` helper shape with zero changes. **Recommend: static TTFs.** `[VERIFIED: empirical download]` |
| Bundle Bold + Regular only | Bundle Bold + Regular + SemiBold + Black (4 statics) | Extra ~132KB. Worth it only if the planner wants to defer the Bold-vs-Black weight choice to runtime iteration. Bold at 140pt UC was measured on real AU place names and looked fine in the width test; Black is ~3-6% wider which may make long names clip-prone. **Recommend: Bold + Regular now; defer others to a follow-up if Bold reads too heavy in field footage.** `[VERIFIED: measurements below]` |
| Ship fonts inside Python package | System install via apt (`fonts-cinzel`) | No such Debian package exists in stable repos. Bundling in-package is the right pattern anyway — matches `shitbox_rally_logo.png` precedent. `[ASSUMED — not verified against current Debian archive but training knowledge says Google Fonts are rarely packaged for apt]` |

## Architecture Patterns

### System Architecture Diagram

```
Event triggers save
        |
        v
  UnifiedEngine._on_video_complete
        |
        v
  TitleCardRenderer.render(event, png_path, ts_path, geocoder=..., driver_name=...)
        |
        +---------------+---------------+
        |               |               |
        v               v               v
  _resolve_strings  _compose_png    _encode_ts
        |               |               |
        |               |               |
  (place | whimsy)      |          (PNG -> MPEG-TS
        |               |           via ffmpeg loop+AAC)
        |               |               |
        v               v               v
  hero_text        Pillow draws    slate.ts in
  coord_text       PNG at 1280x720 segments[0].parent
  badge flags      using bundled
                   Cinzel TTFs
                   + system DejaVu Mono
        |               |               |
        +-------+-------+               |
                |                       |
                v                       v
         png saved as          ts appended to concat
         <event>_poster.png    list in ring_buffer
                                _concatenate_segments
                                       |
                                       v
                                intro.ts -> slate.ts ->
                                segments -> final MP4
```

**Phase 27 delta:** only the `_compose_png` box changes. The `_resolve_strings` box gets the `.upper()` + state-drop edit. Everything else is literally unchanged.

### Recommended Project Structure

```
src/shitbox/capture/
├── title_card.py          # MODIFY: font constants, _resolve_strings, _compose_png
└── assets/
    ├── shitbox_rally_logo.png
    └── cinzel/            # NEW subdir
        ├── Cinzel-Bold.ttf       # ~68KB
        ├── Cinzel-Regular.ttf   # ~66KB
        └── OFL.txt              # ~4.3KB (SIL OFL 1.1 text)
```

### Pattern 1: Bundled TTF path constants (mirror LOGO_PATH)

**What:** Replace hardcoded system paths with `Path(__file__).parent / "assets" / "cinzel" / ...`.
**When to use:** Any in-tree asset that's going into a Python distribution.
**Example:**

```python
# src/shitbox/capture/title_card.py — replace lines 49-52
_ASSETS_DIR = Path(__file__).parent / "assets"
_CINZEL_DIR = _ASSETS_DIR / "cinzel"

FONT_DISPLAY_BOLD = str(_CINZEL_DIR / "Cinzel-Bold.ttf")
FONT_DISPLAY_REGULAR = str(_CINZEL_DIR / "Cinzel-Regular.ttf")
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"  # unchanged
LOGO_PATH = str(_ASSETS_DIR / "shitbox_rally_logo.png")  # unchanged

# For backward-compatible references elsewhere (e.g. badge font, still Bold):
FONT_DISPLAY = FONT_DISPLAY_BOLD
```

`[CITED: src/shitbox/capture/title_card.py:49-52]`

### Pattern 2: Apply `.upper()` + state-drop in `_resolve_strings`

**What:** Do the hero-path text transforms upstream of measurement so the downstream pipeline sees the final string.
**When to use:** Any transform that affects width measurement and must feed into the shrink-fit loop.
**Recommendation:** apply in `_resolve_strings` (cleaner locus; D-05 discretion). Logging lines downstream already happen after this function returns, so they'll show the upper-cased string — this is fine for field diagnostics (`place="NARELLAN"` in the log reads correctly) and is actively *better* than logging the mixed-case intermediate. The whimsy pool gets upper-cased by the same code path (D-07), not by duplicating `.upper()` calls.

**Example:**

```python
# src/shitbox/capture/title_card.py — current _resolve_strings lines 263-278
if place:
    # Phase 27 (D-06): drop state suffix. Everything after the first comma
    # is stripped from the hero. The full geocoder output is kept for logging.
    hero_raw = place.split(",", 1)[0].strip()
    hero_text = _truncate(hero_raw, MAX_PLACE_CHARS).upper()  # D-05
    coord_text = f"{lat:.4f}, {lng:.4f}" if (lat is not None and lng is not None) else None
elif geocoder_called:
    hero_text = None
    coord_text = f"{lat:.4f}, {lng:.4f}"
else:
    hero_text = _truncate(random.choice(self.whimsy_lines), MAX_WHIMSY_CHARS).upper()  # D-07
    coord_text = None
```

> Note: `_abbreviate_au_states` is **not** called on this path anymore. It stays in the module (might be useful for a future subline feature or for non-hero copy). The AU-state abbreviation tests in `test_title_card_overflow_and_tz.py` stay valid as unit tests for the helper, but the full-render assertion "Narellan, New South Wales → Narellan, NSW" changes to "... → NARELLAN".

`[CITED: src/shitbox/capture/title_card.py:263-278]`

### Pattern 3: Wheel packaging for fonts

**What:** Extend `package-data` to cover the new TTF+licence artefacts.
**When to use:** Any time you add a non-Python asset under a package directory.
**Example:**

```toml
# pyproject.toml — line 55-56 (current)
# [tool.setuptools.package-data]
# shitbox = ["capture/assets/*.png", "dashboard/static/**/*"]

# Phase 27 replacement:
[tool.setuptools.package-data]
shitbox = [
    "capture/assets/*.png",
    "capture/assets/cinzel/*.ttf",
    "capture/assets/cinzel/OFL.txt",
    "dashboard/static/**/*",
]
```

> Non-recursive glob: `capture/assets/*.png` matches `shitbox_rally_logo.png` but would NOT match `capture/assets/cinzel/Cinzel-Bold.ttf` even if the extension matched. Both the subdir glob and the licence line are load-bearing. **This is genuine tech debt inherited from Phase 26** — the planner should call it out in a task note, not treat it as phase-scope creep.

`[VERIFIED: pyproject.toml:55-56 grep]`

### Anti-Patterns to Avoid

- **Relying on Pi system Cinzel:** `fonts-cinzel` is not a standard Debian package. If the font is not bundled, the `_font()` helper will silently fall through to `ImageFont.load_default()` (10pt bitmap) and every slate will ship with typewriter text. **Bundle the TTFs.**
- **Simulating letter-spacing with manual positioning:** Pillow has no `tracking=` parameter. CONTEXT.md (Claude's Discretion) calls this out as a fallback if default kerning looks bad. **Don't build manual glyph positioning speculatively.** Cinzel Bold has well-designed metrics; its default kerning at 140pt ALL CAPS already reads as an engraved title. If it looks wrong on the Pi, revisit — but not in plan v1.
- **Using Cinzel variable font:** Requires `font_variation_axes={"wght": 700}` on `ImageFont.truetype` which isn't in the existing `_font()` helper shape. Small saving in bytes, non-trivial cost in complexity. **Ship statics.**
- **Swapping the `FONT_DISPLAY` constant name without rename:** existing code uses `FONT_DISPLAY` for both hero and date/driver. Phase 27 needs two separate paths. Either introduce `FONT_DISPLAY_BOLD` / `FONT_DISPLAY_REGULAR` and keep `FONT_DISPLAY` as an alias for the Bold path (for the badge font call site at `title_card.py:323`), or rename every call site. The alias approach is surgically smaller.
- **Moving `.upper()` into `_compose_png`:** splits the transform pipeline across two functions and makes the logging string ambiguous. Keep it in `_resolve_strings`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Letter-spacing for ALL CAPS hero | Manual glyph-by-glyph positioning | Accept Pillow's default kerning for the TTF | Cinzel's designer (Natanael Gama) already tuned the metrics. Manual tracking is a rabbit hole of Pi-specific FreeType subpixel rendering quirks. `[CITED: github.com/python-pillow/Pillow/issues/3977 — letter-spacing issues are a long-standing pain point with no clean API]` |
| Width measurement | Re-derive per-font-weight heuristics | `draw.textlength(text, font=f)` — what `_fit_hero_to_canvas` already uses | Measurement is font-agnostic; it's just the path that changes. The shrink-fit loop at `title_card.py:491-496` works unchanged. `[CITED: src/shitbox/capture/title_card.py:467-508]` |
| Font file resolution | `subprocess.run(["fc-match", ...])` font-config lookup | `Path(__file__).parent / "assets" / "cinzel" / ..." | The logo asset already uses this pattern. Don't introduce a second asset-resolution style. `[CITED: src/shitbox/capture/title_card.py:52]` |
| Licence compliance | "Nobody checks" | Ship OFL.txt in the wheel | SIL OFL 1.1 explicitly requires the licence ship with binary redistributions. Cost is negligible (4.3KB), risk of omission is everything from silly to embarrassing. `[CITED: fonts.google.com/specimen/Cinzel SIL OFL 1.1 terms]` |

**Key insight:** The entire phase is about pointing Pillow at a different TTF and upper-casing one string. Every clever optimisation beyond that is an opportunity to break something Phase 26 already verified.

## Runtime State Inventory

Not a rename/refactor/migration phase — this is a pure code+asset addition. No stored data, live service config, OS-registered state, secrets, or build artefacts carry the old font path forward:

- **Stored data:** None. Font paths are code constants, not database values.
- **Live service config:** None. `TitleCardConfig` shape unchanged (D-16 in Phase 26 made typography non-configurable by design).
- **OS-registered state:** None. No systemd unit, pm2 registration, or task scheduler reference the font.
- **Secrets/env vars:** None.
- **Build artefacts:** The installed Python package on the Pi will need `pip install -e .` (or equivalent) to pick up the new TTF files. If the Pi runs from a source checkout (per memory: `/home/tgreen/shitbox/` with a venv), a `pip install -e .` after the git pull is the deployment step. If it runs from a built wheel, the wheel has to be rebuilt and reinstalled. **Planner should include a deployment note, not a migration task.**

## Common Pitfalls

### Pitfall 1: Non-recursive `package-data` glob silently drops TTFs

**What goes wrong:** `shitbox = ["capture/assets/*.png", ...]` does NOT match `capture/assets/cinzel/Cinzel-Bold.ttf`. Wheel builds succeed; TTFs are missing from the installed package; `ImageFont.truetype` falls through to `_font()`'s `load_default()` bitmap fallback; every slate ships with 10pt system text. The fallback log line (`slate_font_fallback`) is DEBUG level so it won't necessarily scream at you in production. **This is the single most likely way Phase 27 ships broken.**

**Why it happens:** `setuptools` package-data globs are non-recursive by default. Phase 26 added the PNG glob when it shipped the logo asset; the pattern was never exercised on a subdirectory.

**How to avoid:** Include both `capture/assets/cinzel/*.ttf` and `capture/assets/cinzel/OFL.txt` explicitly in `package-data`. After implementation, verify with `pip install -e . && python -c "from pathlib import Path; from shitbox.capture import title_card; print(Path(title_card.FONT_DISPLAY_BOLD).exists())"` — any False is a packaging miss.

**Warning signs:** Slate PNG shows skeletal bitmap-font typewriter text instead of Cinzel. The `slate_font_fallback` DEBUG log would confirm if logging is turned up.

### Pitfall 2: `.upper()` applied after truncation ellipsis

**What goes wrong:** `_truncate("Narellan, New South Wales", 28).upper()` works fine — but if the order is reversed, you get the ellipsis character clobbered or the truncation math off by one. Unicode ellipsis `"…"` (which `_truncate` uses) survives `.upper()` unchanged, so this is low-risk, but the D-06 transform (split-on-comma, take [0], strip) must happen *before* truncation so the count is counting the right string.

**Why it happens:** The current order is `_abbreviate_au_states(place)` → `_truncate(abbreviated, MAX_PLACE_CHARS)`. Phase 27 changes that to `place.split(",", 1)[0].strip()` → `_truncate(hero_raw, MAX_PLACE_CHARS).upper()`. Getting the order wrong produces either an upper-cased ellipsis stub or a doubly-processed string.

**How to avoid:** split → strip → truncate → upper, in that order. Unit-test the composition.

**Warning signs:** Hero reads `NARELLAN, NEW SOUTH WA…` (state kept) or `NARELLAN,` (trailing comma not stripped).

### Pitfall 3: Cinzel per-glyph width is 1.05x-1.21x DejaVu at the same size

**What goes wrong:** Assuming "ALL CAPS means more horizontal space so bigger strings will fit" — wrong in the opposite direction. ALL CAPS uses only cap-height glyphs, most of which are wider than their lowercase equivalents. Cinzel specifically is an engraved Roman face with wide caps. Empirical measurement (Pillow 11.3.0, Cinzel Bold v2.000 from NDISCOVER upstream):

| String | 140pt width | vs DejaVu Sans Bold mixed-case same string |
|--------|------------|------------------------------------------|
| `NARELLAN` (8ch) | 805px | 666px (Narellan mixed) → **1.21x wider** |
| `BRISBANE` (8ch) | 733px | 696px (Brisbane mixed) → **1.05x wider** |
| `MELBOURNE` (9ch) | 947px | 842px (Melbourne mixed) → **1.12x wider** |
| `BATHURST` (8ch) | 787px | 687px (Bathurst mixed) → **1.15x wider** |

Average ~1.13x on a small AU place-name sample. **Critically: the state-drop (D-06) more than compensates.** `Narellan, New South Wales` at DejaVu Bold mixed-case 140pt is 2140px (triggers shrink-fit aggressively); `NARELLAN` at Cinzel Bold 140pt is 805px (fits at 140pt with 355px of headroom).

**Why it happens:** Cap-only rendering + a serif face with wide lapidary strokes. The "Trajan-alike" aesthetic is the slow-reading monumental feel, which is a direct product of those wide caps.

**How to avoid:** Trust the empirical measurements (below), not intuition. Keep the existing shrink-fit thresholds. The only realistic AU place name that forces shrink-fit after state-drop is something like `MOUNT PANORAMA` (14 chars, fits at 110pt) or `ULURU-KATA TJUTA` (16 chars, fits at 110pt) — and both of those shrink well within the existing 100pt floor.

**Warning signs:** Hero renders but the fit size logs `fit_size < 140` frequently on short names (e.g. 8-char names shouldn't shrink).

### Pitfall 4: Per-char width varies by 2.5x (I vs W) at 140pt

**What goes wrong:** `MAX_PLACE_CHARS=28` (D-14 question) conceals a large variance. At Cinzel Bold 140pt the safe width of 1160px holds:

- `A` × 11 (average width caps)
- `W` × 8 (widest caps)
- `M` × 8 (widest caps)

So "28 characters" means "safe for single-I/L narrow words, clipped for any realistic place name." Even at the 100pt floor, it's only `A` × 16 / `W` × 11. The cap is not the right guardrail for Cinzel ALL CAPS; `_fit_hero_to_canvas` shrink-fit does the actual work.

**Why it happens:** Character caps were tuned for DejaVu Sans Bold mixed-case. ALL CAPS Cinzel is a different beast.

**How to avoid:** Leave `MAX_PLACE_CHARS=28` in place as a defence-in-depth against pathological geocoder output (the 10MB-whimsy-string attack surface from T-26-03-01). Rely on `_fit_hero_to_canvas` to handle the "long name" case — which it already does correctly, empirically verified against 28 realistic AU place names including long ones (`COFFS HARBOUR`, `PORT MACQUARIE`, `ROCKHAMPTON`, `NORTH SYDNEY`, `MOUNT PANORAMA`, `ULURU-KATA TJUTA`). **Recommend planner: no change to `MAX_PLACE_CHARS`.**

**Warning signs:** A place name that looked fine on Phase 26 is clipped on Phase 27. (Empirical answer: doesn't happen on tested AU names.)

### Pitfall 5: ASS overlay / PiP sync drift from the wrong offset

**What goes wrong:** Phase 26's concat demuxer, PiP filter chain, and ASS burn-in all reference `intro_duration + slate_duration` as the head offset. Phase 27 changes nothing about this. But any planner who thinks "typography change, only touch title_card.py" could accidentally modify the constant set in a way that perturbs duration arithmetic elsewhere.

**Why it happens:** The Phase 26 Pattern Map specifically calls out the ASS shift (`overlay.py::generate_ass_overlay`) as a call site that reads `intro_duration`.

**How to avoid:** Phase 27 does NOT touch `ring_buffer.py`, `overlay.py`, `events/engine.py`, `events/labels.py`, `events/storage.py`, or `utils/config.py`. The only module it touches is `title_card.py` (plus `pyproject.toml` for packaging). CONTEXT.md D-01, D-04, D-08, D-09, D-10, D-12 all reinforce this — the scope is deliberately narrow. The plan-checker should verify the diff stays in `title_card.py` + `pyproject.toml` + `src/shitbox/capture/assets/cinzel/*`.

**Warning signs:** PiP appears before the slate ends, HUD subtitles drift, concat demuxer fails on stream mismatch. All Phase 26 gap-closure scenarios — Phase 27 should reproduce zero of them.

## Code Examples

Verified patterns from the existing codebase, adjusted for Phase 27:

### Module-level font constants (replace lines 49-52)

```python
# src/shitbox/capture/title_card.py
# Source: src/shitbox/capture/title_card.py:52 (existing LOGO_PATH pattern)

_ASSETS_DIR = Path(__file__).parent / "assets"
_CINZEL_DIR = _ASSETS_DIR / "cinzel"

# Display typeface bundled in-tree (D-10, D-11). SIL OFL 1.1 — see
# assets/cinzel/OFL.txt for the licence text shipped alongside the binaries.
FONT_DISPLAY_BOLD = str(_CINZEL_DIR / "Cinzel-Bold.ttf")
FONT_DISPLAY_REGULAR = str(_CINZEL_DIR / "Cinzel-Regular.ttf")

# Back-compat alias: badge font site at _compose_png (currently
# f_badge = _font(FONT_DISPLAY, FONT_BADGE)) still wants Bold.
FONT_DISPLAY = FONT_DISPLAY_BOLD

# Mono row stays on the system DejaVu (D-12) — the modern coord string
# in the Westeros frame is intentional.
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
LOGO_PATH = str(_ASSETS_DIR / "shitbox_rally_logo.png")
```

### Updated `_resolve_strings` (replace lines 263-278 of the `if place:` branch)

```python
# src/shitbox/capture/title_card.py
# Source: src/shitbox/capture/title_card.py:263-278

if place:
    # D-06: drop state suffix. Everything after the first comma is stripped
    # from the hero — "Narellan, New South Wales" becomes "Narellan".
    # The full geocoder output stays in the log line.
    hero_raw = place.split(",", 1)[0].strip()
    # D-05: ALL CAPS hero. Applied AFTER truncation so the character count
    # is measured on the natural-case string (Unicode upper-case round-trips
    # the ellipsis character unchanged).
    hero_text = _truncate(hero_raw, MAX_PLACE_CHARS).upper()
    coord_text = f"{lat:.4f}, {lng:.4f}" if (lat is not None and lng is not None) else None
elif geocoder_called:
    # D-10 unchanged: geocoder called, returned None → coord-only.
    hero_text = None
    coord_text = f"{lat:.4f}, {lng:.4f}"
else:
    # D-09: no GPS / no geocoder → whimsy. D-07: upper-cased for consistency.
    hero_text = _truncate(
        random.choice(self.whimsy_lines), MAX_WHIMSY_CHARS
    ).upper()
    coord_text = None
```

### Updated font loading in `_compose_png` (replace lines 320-323)

```python
# src/shitbox/capture/title_card.py
# Source: src/shitbox/capture/title_card.py:320-323

# f_hero is still allocated inside _fit_hero_to_canvas (G-02 unchanged).
# Date + driver rows use Cinzel Regular (D-04), not Bold — a tonal contrast
# with the hero that reinforces the ranked-location feel.
f_date = _font(FONT_DISPLAY_REGULAR, FONT_DATE)
f_driver = _font(FONT_DISPLAY_REGULAR, FONT_DRIVER)
f_coord = _font(FONT_MONO, FONT_COORD)
# Badge label stays Bold — the badge is deliberately unchanged (D-09).
f_badge = _font(FONT_DISPLAY, FONT_BADGE)
```

And in the hero call site (replace line 333-335):

```python
# src/shitbox/capture/title_card.py
# Source: src/shitbox/capture/title_card.py:333-335

# Hero uses Cinzel BOLD at up to FONT_HERO=140pt. Measure-and-shrink still
# runs — empirically most realistic AU place names fit at 140pt with the
# state suffix dropped, so the shrink rarely fires.
fitted_text, fitted_font = _fit_hero_to_canvas(
    draw, hero_text, FONT_DISPLAY_BOLD, max_size=FONT_HERO
)
```

### Updated `pyproject.toml` packaging stanza

```toml
# pyproject.toml
# Source: pyproject.toml:55-56

[tool.setuptools.package-data]
shitbox = [
    "capture/assets/*.png",
    "capture/assets/cinzel/*.ttf",
    "capture/assets/cinzel/OFL.txt",
    "dashboard/static/**/*",
]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded system font paths (`/usr/share/fonts/...`) for display text | Bundled TTF assets inside the Python package | This phase | Reproducible typography across dev and Pi; no dependence on Debian font packages; wheel is self-contained |
| Mixed-case place-hero with full state name | ALL CAPS hero with state suffix dropped | This phase | Gestural GoT homage — the contrast with a 24-year-old hatchback is the joke |

**Deprecated/outdated:**

- Nothing is being deprecated. `_abbreviate_au_states` stays as a utility (Claude's Discretion; it might be useful for a future subline element or for non-hero copy). The full Phase 26 pipeline continues to work; this is additive typography.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No `fonts-cinzel` apt package exists on Debian stable | Alternatives Considered | Low — even if one exists, bundling is still preferable (reproducibility, version-locking). No code difference if A1 is wrong. |
| A2 | Pi's Pillow has libraqm (required for OpenType features=) | Pitfalls (implicit) | Low — the recommendation explicitly avoids `features=`, so libraqm availability doesn't matter. Only relevant if the plan wants advanced kerning control, which it shouldn't. |
| A3 | Pillow's default TTF kerning is "good enough" for Cinzel Bold ALL CAPS at 140pt visual quality | Anti-Patterns, Claude's Discretion | Medium — if Cinzel caps look too tight or too loose on the Pi render, the planner may want to try Cinzel SemiBold or add manual spacing. Both are Claude's Discretion in CONTEXT.md and would be iterative tweaks on top of Phase 27, not plan-v1 risks. |
| A4 | Pi runs from `/home/tgreen/shitbox/` via `pip install -e .` so TTF additions are picked up on git pull | Runtime State Inventory | Low — confirmed via memory file `project_pi_environment`. If the Pi runs from a built wheel, the deployment step changes from "git pull" to "build + scp wheel + pip install". |

**Three items are assumed**; none affect plan-v1 correctness. A3 is the one most worth a render-and-review loop during Wave 1 of implementation.

## Open Questions

1. **Should Cinzel Bold be replaced by SemiBold if 140pt ALL CAPS reads too heavy?**
   - What we know: Bold has clean metrics and fits the "engraved location title" brief; Black is wider and heavier (may clip more long names).
   - What's unclear: visual tone — is Bold the right weight for "slightly more whimsy than real GoT"? Real GoT opening titles use a heavier cut.
   - Recommendation: Ship Bold as the default. The first on-Pi render review after Wave 1 either confirms Bold reads right, or the plan adds a Wave 2 task to swap for SemiBold (static file already available via `Cinzel[wght].ttf` axis interpolation or NDISCOVER upstream — though NDISCOVER static upstream only ships Regular/Bold/Black, SemiBold requires the variable font or a separate fetch). Defer weight iteration to post-merge.

2. **Does the existing `test_capture_title_card.py` real-ffmpeg test need updating for the new font paths?**
   - What we know: `test_render_end_to_end_integration` (line 396) does a full render with real ffmpeg. It relies on `ImageFont.truetype(FONT_DISPLAY, ...)` where `FONT_DISPLAY` points to the system DejaVu path, falling back to `load_default()` on dev boxes.
   - What's unclear: whether the dev-laptop test path picks up the bundled Cinzel (which DOES exist in the source tree after Phase 27) or still falls through.
   - Recommendation: After Phase 27, the bundled TTF is the source of truth on dev too. The test should still pass as-is (Pillow can load any TTF on any platform), and now produces a *real* Cinzel render in CI instead of a DejaVu fallback. Planner should explicitly verify the dev laptop test run loads Cinzel, not falls back to `load_default()`.

3. **Does the Pi need a `pip install -e .` after the git pull to pick up the new TTFs?**
   - What we know: The project ships as a source layout at `src/shitbox/`. With `pip install -e .` (editable install), file additions under `src/shitbox/` are live-readable without reinstall.
   - What's unclear: whether the Pi venv is editable-installed or wheel-installed.
   - Recommendation: Planner should include a deployment checklist note. If editable, the git pull is sufficient. If wheel, a `pip install .` is needed. Probably include both as conditional guidance.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.9+ | runtime | ✓ | 3.11+ on dev, 3.11 on Pi | — |
| Pillow | TTF rendering | ✓ | 11.3.0 dev / `>=10.0.0` pinned in pyproject | `ImageFont.load_default()` bitmap — slate renders with typewriter text (not acceptable, but does not crash) |
| libfreetype2 (shipped with Pillow wheel) | TTF glyph rendering | ✓ (via Pillow) | bundled | — |
| libraqm | Advanced OpenType features (not used in this plan) | ✓ on dev mac | — | Plan explicitly does not use `features=`, so raqm presence is irrelevant |
| ffmpeg | PNG → MPEG-TS encoding (unchanged from Phase 26) | ✓ on Pi | — | Phase 26 already handles missing ffmpeg via `_encode_ts` returning False |
| Internet access during install | Not used — fonts are vendored in the repo | ✓ | — | Fonts ship with the wheel; no runtime download |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None (the `load_default()` fallback is fundamentally not acceptable for this phase — if Cinzel doesn't load, Phase 27 has shipped broken. Treat as "no fallback" for success criteria purposes).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ (via `.[dev]` extra) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`pythonpath = ["src"]`) |
| Quick run command | `pytest tests/test_capture_title_card.py tests/test_title_card_overflow_and_tz.py -x` (~2s) |
| Full suite command | `pytest` (~15-30s; skips real-ffmpeg and real-Pillow-font tests on machines without those tools) |
| Phase gate | Full suite green before `/gsd-verify-work` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC1 (Cinzel loaded, no fallback) | `ImageFont.truetype(FONT_DISPLAY_BOLD, 140)` succeeds without `load_default` fallback | unit | `pytest tests/test_capture_title_card.py::test_cinzel_bold_loads_from_bundled_asset -x` | ❌ NEW |
| SC1/D-05 (ALL CAPS hero) | `_resolve_strings` returns upper-cased hero for a place-string input | unit | `pytest tests/test_capture_title_card.py::test_resolve_strings_hero_is_all_caps -x` | ❌ NEW |
| D-06 (state drop) | `"Narellan, New South Wales"` → hero is `"NARELLAN"` (not `"NARELLAN, NSW"`) | unit | `pytest tests/test_capture_title_card.py::test_resolve_strings_drops_state_suffix -x` | ❌ NEW |
| D-07 (whimsy upper-cased) | Whimsy path returns an upper-cased string from the pool | unit | `pytest tests/test_capture_title_card.py::test_resolve_strings_whimsy_is_all_caps -x` | ❌ NEW |
| SC2 (all event types render) | Each of HARD_BRAKE, BIG_CORNER, HIGH_G, ROUGH_ROAD, MANUAL_CAPTURE, ROLLOVER, BOOT produces a non-black 1280×720 PNG under the new typography | integration | `pytest tests/test_capture_title_card.py::test_render_all_event_types_under_cinzel -x` | ❌ NEW (parameterised) |
| SC2 (no-GPS whimsy) | Existing `test_render_whimsy_when_no_gps` still passes under new typography | regression | `pytest tests/test_capture_title_card.py::test_render_whimsy_when_no_gps -x` | ✅ |
| SC3 (config back-compat) | Existing `test_config_title_card.py` still passes unchanged | regression | `pytest tests/test_config_title_card.py -x` | ✅ |
| SC4 (G-02 shrink-fit preserved) | "NARELLAN" at 140pt Cinzel Bold fits safe width unchanged; "MOUNT PANORAMA" shrinks to ≤130pt not below 100pt | unit | `pytest tests/test_title_card_overflow_and_tz.py::test_cinzel_hero_fits_safe_width -x` | ❌ NEW (replace `test_long_place_name_fits_safe_width` assertions) |
| SC4 (ellipsis truncation at floor) | 200-char synthetic string still ellipsis-truncates at 100pt Cinzel Bold | unit | `pytest tests/test_title_card_overflow_and_tz.py::test_extremely_long_unabbreviated_string_ellipsis_truncates -x` | ✅ (assertion update only — function under test unchanged) |
| SC5 (safe margins respected) | Rendered PNG's hero glyph cluster lies within x=[60, 1220] | integration | `pytest tests/test_capture_title_card.py::test_hero_respects_safe_margins -x` | ❌ NEW |
| Phase 26 regression (AAC silent track) | `test_encode_ts_produces_valid_stream` still passes | regression | `pytest tests/test_capture_title_card.py::test_encode_ts_produces_valid_stream -x` | ✅ |
| Phase 26 regression (font fallback) | `test_pillow_missing_fails_gracefully` still passes with new font paths | regression | `pytest tests/test_capture_title_card.py::test_pillow_missing_fails_gracefully -x` | ✅ |
| Packaging (TTFs in wheel) | Built wheel contains `capture/assets/cinzel/Cinzel-Bold.ttf`, `Cinzel-Regular.ttf`, `OFL.txt` | integration | `python -m build --wheel && unzip -l dist/*.whl | grep cinzel` (manual one-off or CI smoke) | manual / CI |
| Package path resolution | `Path(title_card.FONT_DISPLAY_BOLD).exists()` is True after `pip install -e .` | unit | `pytest tests/test_capture_title_card.py::test_bundled_cinzel_exists -x` | ❌ NEW |

### Sampling Rate

- **Per task commit:** `pytest tests/test_capture_title_card.py tests/test_title_card_overflow_and_tz.py tests/test_config_title_card.py -x` (~3s)
- **Per wave merge:** `pytest` (full suite; ~20s expected)
- **Phase gate:** Full suite green + a manual on-Pi render-and-eyeball of one real event (see "Open Questions" A3) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_capture_title_card.py` — add: `test_cinzel_bold_loads_from_bundled_asset`, `test_resolve_strings_hero_is_all_caps`, `test_resolve_strings_drops_state_suffix`, `test_resolve_strings_whimsy_is_all_caps`, `test_render_all_event_types_under_cinzel` (parameterised over EventType), `test_hero_respects_safe_margins`, `test_bundled_cinzel_exists`
- [ ] `tests/test_title_card_overflow_and_tz.py` — rename or add: `test_cinzel_hero_fits_safe_width` (update from Phase 26's `test_long_place_name_fits_safe_width` which asserts NSW-abbreviated state still shows); update ellipsis-truncation assertion font path
- [ ] No new framework install needed — `pytest` + `pillow` already in dev extras

*(The test file already covers the core renderer contract; Phase 27 adds targeted assertions for typography changes. No new fixtures or conftest changes needed — the `png_and_ts` fixture and `_make_event` helper remain the vocabulary.)*

## Project Constraints (from CLAUDE.md)

The following project directives MUST be honoured by the plan. Copied from `CLAUDE.md` and `~/.claude/CLAUDE.md`:

- **structlog with kwargs:** any new log line must follow `log.info("event_name", key=value, ...)` — no f-strings in event names, past-tense snake_case verbs.
- **ruff E/F/I/W, line length 100:** all edits pass `ruff check src/`.
- **mypy strict:** full type annotations maintained (`from __future__ import annotations` is already in the file).
- **Python 3.9 target:** no `match` statements, no `|`-union syntax in annotations (use `Optional[...]`, `Union[...]`), no `str.removeprefix` without an explicit version guard.
- **Hardware graceful degradation:** the existing `_font()` fallback and `render()` returning `0.0` on failure is the established pattern — preserve it for the new font paths.
- **UK/Aus English:** any new copy (unlikely — no new whimsy lines in this phase) follows `feedback_ai_tells_in_copy.md`. No em-dashes. Concrete images over abstract nouns.
- **No fewer/less error:** use "fewer" for countable nouns.
- **Brain updates:** after Phase 27 ships, update `~/Brain/projects/shitbox-rally-2026.md` "Active Now" section.
- **No emojis** in code or docs unless the user explicitly asks.
- **Markdownlint compliance:** for any markdown this phase creates.

## Sources

### Primary (HIGH confidence)

- `src/shitbox/capture/title_card.py` — full Phase 26 implementation read line-by-line; constants at 49-52, font-size constants at 71-75, palette at 78-81, `MAX_PLACE_CHARS` at 86, state-abbrev helper at 106-118, shrink-fit thresholds at 125-127, `_resolve_strings` at 240-287, `_compose_png` at 289-388, `_fit_hero_to_canvas` at 467-508. `[VERIFIED: Read tool]`
- `pyproject.toml` lines 55-56 — current `package-data` glob is `capture/assets/*.png` only; NON-RECURSIVE. `[VERIFIED: Read tool]`
- `tests/test_capture_title_card.py` — existing test inventory read in full; covers PNG composition, fallback matrix, ffmpeg encoding, graceful failure. `[VERIFIED: Read tool]`
- `tests/test_title_card_overflow_and_tz.py` — G-02 shrink-fit and AU-state abbreviation tests; assertions will need updating for Phase 27 (state-drop, not state-abbrev, and ALL CAPS strings). `[VERIFIED: Read tool]`
- `.planning/phases/26-event-video-title-cards/26-CONTEXT.md` + `26-PATTERNS.md` — upstream locked context; ASS shift + PiP offset caveat; silent AAC parity for concat demuxer. `[VERIFIED: Read tool]`
- Empirical Pillow measurements (dev laptop, Pillow 11.3.0, Cinzel Bold v2.000 from NDISCOVER, DejaVu Sans Bold 2.37): per-glyph width ratios, fit sizes for 28 realistic AU place names, char-cap at 100pt floor, all numerical claims in Pitfall 3 and Pitfall 4. `[VERIFIED: Python/Pillow direct measurement this session]`
- NDISCOVER upstream repo `github.com/NDISCOVER/Cinzel` — static TTFs list (Regular/Bold/Black only for Cinzel, not SemiBold), file sizes (~66-68KB each). `[VERIFIED: GitHub API contents call]`
- `github.com/google/fonts/tree/main/ofl/cinzel` — Google Fonts canonical distribution; single variable TTF `Cinzel[wght].ttf` 122KB + `OFL.txt` 4.3KB. `[VERIFIED: GitHub raw fetch + file command]`

### Secondary (MEDIUM confidence)

- `fonts.google.com/specimen/Cinzel` — weights 400/700/900 Regular/Bold/Black; variable features for Regular/Bold/Black; Latin + Latin-1 Supplement coverage; 353 glyphs in Regular. `[CITED: WebSearch summary from fontsquirrel.com, cufonfonts.com, adobefonts.com]`
- `github.com/python-pillow/Pillow/issues/3977` — letter-spacing issues in Pillow are a long-standing area with no clean API; workarounds are manual glyph positioning. `[CITED: GitHub issue link]`
- Pillow docs on `ImageDraw.text` `features=` parameter + libraqm requirement for OpenType shaping. `[CITED: pillow.readthedocs.io + WebSearch summary]`
- SIL OFL 1.1 terms — requires OFL.txt ship with binary redistributions, allows use/modification/redistribution, forbids selling the fonts by themselves. `[CITED: OFL.txt head via raw GitHub fetch]`

### Tertiary (LOW confidence)

- Whether `fonts-cinzel` exists as a Debian package (assumed not). `[ASSUMED — not verified against Debian archive this session]`
- Pi libraqm availability (not tested — Pi unreachable this session). Not relevant: plan avoids `features=`. `[ASSUMED]`

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — versions verified via live download and file inspection; existing Pillow/pyproject reading confirmed.
- Architecture: HIGH — call sites pinpointed by line number; existing Phase 26 pipeline end-to-end functioning.
- Pitfalls: HIGH — pitfalls 1, 3, 4 have empirical support; pitfall 2 is straightforward string-op ordering; pitfall 5 is a scope-discipline reminder.
- Typography metrics: HIGH — direct Pillow measurement on real TTFs.
- Deployment steps: MEDIUM — depends on whether Pi runs editable or wheel install (flagged as open question).

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (typography and Pillow are stable domains; 30 days is conservative)
