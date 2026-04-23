# Phase 27: Slate Visual Theming - Pattern Map

**Mapped:** 2026-04-24
**Files analysed:** 5 (2 MODIFY, 3 CREATE — 3 of the CREATEs are vendored binary/text assets, not code)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/shitbox/capture/title_card.py` (MODIFY) | renderer / utility | transform (struct → PNG → TS) | itself (module-level constants block lines 49-52, `_resolve_strings` lines 263-278, `_compose_png` font loads lines 320-335) | exact |
| `pyproject.toml` (MODIFY) | build config | static (wheel packaging manifest) | itself (line 56 `package-data` glob for `capture/assets/*.png`) | exact |
| `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf` (CREATE — binary) | vendored font asset | static (shipped in wheel) | `src/shitbox/capture/assets/shitbox_rally_logo.png` (existing PNG asset) | exact |
| `src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf` (CREATE — binary) | vendored font asset | static (shipped in wheel) | `src/shitbox/capture/assets/shitbox_rally_logo.png` | exact |
| `src/shitbox/capture/assets/cinzel/OFL.txt` (CREATE — text) | licence text | static (shipped in wheel) | no in-tree analog — licence files are new to the project | no analog |

> Phase 27 is deliberately the narrowest diff possible: one Python file, one build-config file, and three vendored asset files. The renderer's public contract, class shape, config dataclass, and concat pipeline are all untouched. 26-PATTERNS.md covers the pipeline patterns (concat demuxer, silent AAC track, PiP offsets, ASS shift). This map only covers the typography delta on top of that.

## Pattern Assignments

### `src/shitbox/capture/title_card.py` (renderer, typography-only edits)

**Analog:** itself. Every locus Phase 27 touches already has the correct shape in place — the edits are value-swaps and a reordering of existing string operations.

#### Locus 1: Font path constants (lines 49-52)

**Current code** (`src/shitbox/capture/title_card.py:49-52`):

```python
# Matches overlay.py font choices (D-04). DejaVu ships on the Pi image.
FONT_DISPLAY = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
LOGO_PATH = str(Path(__file__).parent / "assets" / "shitbox_rally_logo.png")
```

`LOGO_PATH` at line 52 is the **exact** analog for the new Cinzel path constants. Same `Path(__file__).parent / "assets" / ...` pattern, same `str(...)` cast so the resulting string drops cleanly into Pillow's `ImageFont.truetype(path, size)` call without further massaging.

**Phase 27 pattern to apply** (D-10, D-11):

```python
# Matches overlay.py font choices (D-04). DejaVu mono still ships on the
# Pi image for the coord row; the display typeface is now bundled in-tree
# (D-10, D-11) because no fonts-cinzel apt package exists.
_ASSETS_DIR = Path(__file__).parent / "assets"
_CINZEL_DIR = _ASSETS_DIR / "cinzel"

FONT_DISPLAY_BOLD = str(_CINZEL_DIR / "Cinzel-Bold.ttf")
FONT_DISPLAY_REGULAR = str(_CINZEL_DIR / "Cinzel-Regular.ttf")

# Back-compat alias: badge font site at _compose_png line 323
# (f_badge = _font(FONT_DISPLAY, FONT_BADGE)) still wants Bold and the
# badge is deliberately unchanged (D-09). Keeping `FONT_DISPLAY` as the
# Bold alias avoids touching the badge call site.
FONT_DISPLAY = FONT_DISPLAY_BOLD

# Coord row stays on Pi-image DejaVu (D-12) — the modern coord string
# leaking into the Westeros frame is the joke.
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
LOGO_PATH = str(_ASSETS_DIR / "shitbox_rally_logo.png")
```

> **Gotcha 1:** the `_CINZEL_DIR` variable is load-bearing only for readability. A one-liner `str(Path(__file__).parent / "assets" / "cinzel" / "Cinzel-Bold.ttf")` is equally valid and matches the existing `LOGO_PATH` shape more literally. Planner picks.
>
> **Gotcha 2:** don't rename `FONT_DISPLAY`. Three call sites (`_compose_png:320,321,323` plus `_fit_hero_to_canvas:334`) reference it. Two of those sites (lines 320 and 321) **must** change to `FONT_DISPLAY_REGULAR` per D-04, so those get touched anyway. Line 323 (`f_badge`) must stay pointing at Bold per D-09, and the hero call at 334 uses the explicit `FONT_DISPLAY_BOLD` name for clarity. Keeping `FONT_DISPLAY = FONT_DISPLAY_BOLD` as an alias means the badge line at 323 is a zero-touch.

#### Locus 2: Hero text transform in `_resolve_strings` (lines 263-278)

**Current code** (`src/shitbox/capture/title_card.py:263-278`):

```python
if place:
    # G-02: abbreviate AU state names before char-truncation so
    # "Narellan, New South Wales" (clips at 140pt) becomes "Narellan, NSW".
    abbreviated = _abbreviate_au_states(place)
    hero_text = _truncate(abbreviated, MAX_PLACE_CHARS)
    coord_text = f"{lat:.4f}, {lng:.4f}" if (lat is not None and lng is not None) else None
elif geocoder_called:
    # D-10: we asked, got nothing; show coords only, no hero.
    hero_text = None
    coord_text = f"{lat:.4f}, {lng:.4f}"
else:
    # D-09: no GPS or no geocoder → whimsy line, no coords.
    hero_text = _truncate(
        random.choice(self.whimsy_lines), MAX_WHIMSY_CHARS
    )
    coord_text = None
```

**Phase 27 pattern to apply** (D-05, D-06, D-07):

```python
if place:
    # D-06: drop the state suffix entirely. Everything after the first
    # comma is stripped from the hero — "Narellan, New South Wales"
    # becomes "Narellan". The full geocoder output stays only in the
    # slate_rendered log line if ever re-added; _abbreviate_au_states
    # stays in the module for potential non-hero re-use but is no
    # longer called on this path.
    hero_raw = place.split(",", 1)[0].strip()
    # D-05: ALL CAPS hero. Apply AFTER truncation so the char count
    # is measured on the natural-case string; Unicode upper-case
    # round-trips the ellipsis character ("…") unchanged.
    hero_text = _truncate(hero_raw, MAX_PLACE_CHARS).upper()
    coord_text = f"{lat:.4f}, {lng:.4f}" if (lat is not None and lng is not None) else None
elif geocoder_called:
    # D-10 unchanged: geocoder called, returned None → coord-only.
    hero_text = None
    coord_text = f"{lat:.4f}, {lng:.4f}"
else:
    # D-09 unchanged structurally; D-07: whimsy upper-cased for consistency.
    hero_text = _truncate(
        random.choice(self.whimsy_lines), MAX_WHIMSY_CHARS
    ).upper()
    coord_text = None
```

> **Gotcha 1:** operation order is load-bearing. `split(",", 1)[0].strip()` → `_truncate(..., MAX_PLACE_CHARS)` → `.upper()`. Reversing any pair produces either a trailing comma (`"NARELLAN,"`), an upper-cased ellipsis stub (visually fine, but the measurement window shifts by one glyph), or a leaked state (`"NARELLAN, NEW SOUTH WA…"`).
>
> **Gotcha 2:** `_abbreviate_au_states` (lines 106-118) is **not deleted**. It remains a module-level helper. The test `tests/test_title_card_overflow_and_tz.py::test_abbreviate_au_states_*` unit tests stay valid against the helper. Only the full-render assertion `"Narellan, New South Wales"` → `"Narellan, NSW"` flips to `"Narellan, New South Wales"` → `"NARELLAN"`.
>
> **Gotcha 3:** the whimsy branch's `.upper()` must be **outside** the `_truncate` call, exactly like the `place` branch. The `_truncate` implementation (lines 458-464) appends `"…"` (U+2026) if it clips. `.upper()` is a no-op on that code point — safe either way, but consistent ordering reduces cognitive load for the next reader.

#### Locus 3: Font loader calls in `_compose_png` (lines 320-335)

**Current code** (`src/shitbox/capture/title_card.py:320-335`):

```python
f_date = _font(FONT_DISPLAY, FONT_DATE)
f_driver = _font(FONT_DISPLAY, FONT_DRIVER)
f_coord = _font(FONT_MONO, FONT_COORD)
f_badge = _font(FONT_DISPLAY, FONT_BADGE)

img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOUR)
draw = ImageDraw.Draw(img)

# Hero row (D-05 — place name, ~140pt). D-10 (coord-only) skips this.
if hero_text:
    # G-02: measure-and-shrink-fit. Abbreviation already applied in
    # _resolve_strings; here we pick the largest size that fits within
    # 1160px safe width, falling through to ellipsis truncation at 100pt.
    fitted_text, fitted_font = _fit_hero_to_canvas(
        draw, hero_text, FONT_DISPLAY, max_size=FONT_HERO
    )
```

**Phase 27 pattern to apply** (D-04):

```python
# Date + driver rows use Cinzel Regular (D-04). The tonal contrast between
# Regular for the meta rows and Bold for the hero reinforces the
# ranked-location feel; a single weight across everything reads as noisy.
f_date = _font(FONT_DISPLAY_REGULAR, FONT_DATE)
f_driver = _font(FONT_DISPLAY_REGULAR, FONT_DRIVER)
f_coord = _font(FONT_MONO, FONT_COORD)
# Badge label stays Bold — the badge is deliberately unchanged (D-09).
# FONT_DISPLAY is aliased to FONT_DISPLAY_BOLD so this call is zero-touch.
f_badge = _font(FONT_DISPLAY, FONT_BADGE)

img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOUR)
draw = ImageDraw.Draw(img)

# Hero row (D-04, D-05). Cinzel Bold ALL CAPS at up to 140pt; empirically
# every realistic AU place name with the state suffix dropped fits at
# 140pt (NARELLAN = 805px, MELBOURNE = 947px, both well inside 1160px
# safe width — see 27-RESEARCH.md Pitfall 3). Shrink-fit rarely fires.
if hero_text:
    fitted_text, fitted_font = _fit_hero_to_canvas(
        draw, hero_text, FONT_DISPLAY_BOLD, max_size=FONT_HERO
    )
```

> **Gotcha 1:** `_font` (defined inline at lines 311-316) is unchanged. Its graceful `ImageFont.truetype` → `ImageFont.load_default()` fallback still handles dev-laptop cases where Pillow can't find or read the TTF. The `load_default()` path for Cinzel would be a regression in production (bitmap typewriter text on every slate) — 27-RESEARCH.md Pitfall 1 covers this; the defence is the packaging glob update in `pyproject.toml`, not changes to `_font`.
>
> **Gotcha 2:** the `_fit_hero_to_canvas` helper (lines 467-508) is font-agnostic — it takes `font_path` as an argument and calls `ImageFont.truetype(font_path, size)` internally. No change needed to the helper; just pass `FONT_DISPLAY_BOLD` instead of `FONT_DISPLAY` at the call site on line 334 for clarity (the alias makes it functionally equivalent either way).
>
> **Gotcha 3:** `HERO_FONT_FLOOR=100` and `HERO_FONT_STEP=10` (lines 125-126) do **not** need re-tuning per 27-RESEARCH.md empirical measurements. D-13's re-validation ask is satisfied by a unit-test assertion (`test_cinzel_hero_fits_safe_width` — `NARELLAN` fits at 140pt, `MOUNT PANORAMA` shrinks but stays ≥ 100pt), not by changing the constants.

#### Locus 4: `MAX_PLACE_CHARS` constant (line 86)

**Current code** (`src/shitbox/capture/title_card.py:86`):

```python
MAX_PLACE_CHARS = 28
```

**Phase 27 pattern to apply** (D-14, per 27-RESEARCH.md Pitfall 4):

```python
# No change. The char cap is defence-in-depth against pathological
# geocoder output (10MB-whimsy attack surface, T-26-03-01). At Cinzel
# Bold 140pt, safe width holds ~11 average-caps A's or 8 widest W/M's —
# the cap is not the primary guardrail anyway; _fit_hero_to_canvas
# shrink-fit is. Cinzel ALL CAPS glyph widths vary 2.5x from I to W,
# so a tighter char cap would either over-clip I-heavy names or
# under-catch W-heavy names. Leave at 28.
MAX_PLACE_CHARS = 28
```

> This is a **no-op locus** — included so the planner can tick D-14 off the re-validation list without hunting for a change that doesn't need to happen.

---

### `pyproject.toml` (build config, one-line glob extension)

**Analog:** itself, line 56. The existing `shitbox = ["capture/assets/*.png", "dashboard/static/**/*"]` line is the exact precedent — Phase 26 added the PNG glob when it shipped the logo asset. Phase 27 extends the same list.

**Current code** (`pyproject.toml:55-56`):

```toml
[tool.setuptools.package-data]
shitbox = ["capture/assets/*.png", "dashboard/static/**/*"]
```

**Phase 27 pattern to apply** (27-RESEARCH.md Pitfall 1):

```toml
[tool.setuptools.package-data]
shitbox = [
    "capture/assets/*.png",
    "capture/assets/cinzel/*.ttf",
    "capture/assets/cinzel/OFL.txt",
    "dashboard/static/**/*",
]
```

> **Gotcha — single most likely way Phase 27 ships broken:** setuptools `package-data` globs are **non-recursive by default**. `capture/assets/*.png` does NOT match `capture/assets/cinzel/Cinzel-Bold.ttf` even if the extension matched, because the subdir crossing isn't expanded. The installed wheel would have the TTFs missing; `ImageFont.truetype` would fall through to `ImageFont.load_default()` (a 10pt bitmap); every slate would ship with typewriter text. The `slate_font_fallback` log line is DEBUG-level (line 315 in `title_card.py`) so it won't scream at you in production.
>
> **Post-install verification** (27-RESEARCH.md Open Question 3): after `pip install -e .` on the Pi, confirm:
> ```python
> from pathlib import Path
> from shitbox.capture import title_card
> assert Path(title_card.FONT_DISPLAY_BOLD).exists()
> assert Path(title_card.FONT_DISPLAY_REGULAR).exists()
> ```
> Any `False` is a packaging miss. A `test_bundled_cinzel_exists` unit test covers this in CI (27-RESEARCH.md Wave 0 gaps).
>
> **Formatting note:** the existing line 56 is a single-line list. The Phase 27 replacement is multi-line for readability with four entries. TOML accepts both; the multi-line form plays better with future additions and diffs cleanly.

---

### `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf` and `Cinzel-Regular.ttf` (vendored binary assets)

**Analog:** `src/shitbox/capture/assets/shitbox_rally_logo.png` (existing vendored binary asset).

**Pattern:** drop the binary file into `src/shitbox/capture/assets/cinzel/` at source checkout. The `package-data` glob extension above ships them into the wheel. No Python code creates these files — they are fetched from upstream and committed to the repo.

**Upstream canonical source** (27-RESEARCH.md, verified 2026-04-24):

- `github.com/NDISCOVER/Cinzel/raw/master/fonts/ttf/Cinzel-Bold.ttf` (~68KB)
- `github.com/NDISCOVER/Cinzel/raw/master/fonts/ttf/Cinzel-Regular.ttf` (~66KB)

NDISCOVER is the upstream designer repo referenced by Google Fonts and by the OFL.txt licence heading. Static TTFs are preferred over the variable font (`Cinzel[wght].ttf`, 122KB) because Pillow's existing `_font()` helper takes a static path and size — the variable font would need `font_variation_axes=` plumbing for a ~12KB saving (net negative).

> **Gotcha 1:** no font subsetting (D-10). Slate text is Latin-only and the full glyph set is ~66KB — subsetting is a maintenance burden for a <0.1MB saving on a 200MB+ wheel.
>
> **Gotcha 2:** Cinzel static upstream ships **Regular, Bold, Black** only. Not SemiBold (SemiBold exists only via the variable weight axis). Planner defers SemiBold / Black to a post-merge iteration if 140pt Bold ALL CAPS reads too heavy on real Pi output (27-RESEARCH.md Open Question 1).
>
> **Gotcha 3:** binary files committed to git should use the same repo convention as `shitbox_rally_logo.png` — no LFS, no compression tricks, just commit. File sizes at 66-68KB each are well within normal limits.

---

### `src/shitbox/capture/assets/cinzel/OFL.txt` (licence text)

**Analog:** no in-tree analog. The project has not shipped a font before; there is no existing licence-text file pattern to mirror.

**Pattern:** single UTF-8 text file, SIL OFL 1.1 verbatim from upstream. Ships with the TTFs per OFL Section 4 (reservation of font names) and Section 5 (redistribution requires licence).

**Upstream canonical source:**

- `github.com/NDISCOVER/Cinzel/raw/master/OFL.txt` (~4.3KB)

OR equivalently:

- `github.com/google/fonts/raw/main/ofl/cinzel/OFL.txt` (same SIL OFL 1.1 text with Natanael Gama's copyright header)

> **Gotcha:** SIL OFL 1.1 is specific — the verbatim header `"Copyright 2012-2020 The Cinzel Project Authors (https://github.com/NDISCOVER/Cinzel)"` (or equivalent) must be preserved at the top of the file. The planner fetches the upstream file directly; does not rewrite it.
>
> **No .md or markdownlint concern:** `OFL.txt` is a plain text file, not markdown. It is shipped as-is from upstream.

---

## Shared Patterns

### Asset path resolution (`Path(__file__).parent / "assets" / ...`)

**Source:** `src/shitbox/capture/title_card.py:52` (`LOGO_PATH` — the sole existing in-tree precedent)

```python
LOGO_PATH = str(Path(__file__).parent / "assets" / "shitbox_rally_logo.png")
```

**Apply to:** the new `FONT_DISPLAY_BOLD` / `FONT_DISPLAY_REGULAR` constants (see Locus 1 above). Same pattern, one subdir deeper.

> This is the **only** asset-resolution style in the project. Do not introduce a second style (e.g. `importlib.resources`, `pkg_resources.resource_filename`, or `subprocess fc-match` font-config lookup). Consistency with the existing logo path is the point.

### Graceful font fallback on import failure

**Source:** `src/shitbox/capture/title_card.py:311-316` (`_font` inline helper inside `_compose_png`)

```python
def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception as exc:
        log.debug("slate_font_fallback", path=path, size=size, error=str(exc))
        return ImageFont.load_default()
```

**Apply to:** unchanged. Both Cinzel paths flow through this helper at the existing call sites (lines 320, 321). No new fallback code is written.

> **Gotcha:** `load_default()` produces a 10pt bitmap typewriter font. Acceptable for dev-laptop tests (keeps imports non-fatal), NOT acceptable for the Pi production path — if `load_default()` fires in production, Phase 27 has shipped broken. The packaging glob update in `pyproject.toml` is the primary defence; the `slate_font_fallback` debug log is the diagnostic. Consider raising it to INFO level in a follow-up once confidence is established.

### Structured logging with structlog kwargs

**Source:** `src/shitbox/capture/title_card.py:225-233` (`slate_rendered` — canonical example in-file)

```python
log.info(
    "slate_rendered",
    event_type=event.event_type.value,
    place=hero_text or "(whimsy)",
    coords=coord_text,
    png=str(png_path),
    ts=str(ts_path),
    duration_s=self.duration_seconds,
)
```

**Apply to:** **no new log lines needed** in Phase 27. The existing `slate_rendered`, `slate_render_failed`, and `slate_font_fallback` log sites all still fire correctly with the new font paths. If the planner wants a Cinzel-specific diagnostic (e.g. `slate_cinzel_loaded` confirming bundled TTF resolved), it follows the same event-verb-past-tense snake_case naming convention.

> **Gotcha:** `place=hero_text or "(whimsy)"` at line 228 will now log the upper-cased string (`"NARELLAN"` not `"Narellan"`). This is a *desirable* side effect — the log line matches what the slate actually displays. No change needed; just be aware that field diagnostics will read in ALL CAPS going forward.

---

## No Analog Found

Only `OFL.txt` has no in-tree analog — the project has not previously shipped a third-party licensed asset requiring a verbatim licence text. The pattern is trivial (commit an upstream text file as-is) and the file itself is vendored, not authored, so the absence of an analog is not a planning blocker.

---

## Metadata

**Analog search scope (from context already in hand, no fresh searches):**

- `src/shitbox/capture/title_card.py` (full read of constants + key functions — line ranges 1-130, 200-390, 460-520)
- `src/shitbox/capture/assets/` (ls — confirmed `shitbox_rally_logo.png` is the sole existing asset)
- `pyproject.toml` (full read — 72 lines, package-data at line 56)
- Upstream context from 26-PATTERNS.md (Pillow usage, structlog kwargs, ffmpeg subprocess — all untouched by Phase 27)

**Files scanned (targeted reads, no full-file loads beyond title_card.py):** 3

**Fresh grep scope:** one grep inside `title_card.py` confirming `FONT_DISPLAY` / `FONT_MONO` / `_abbreviate_au_states` call sites; no cross-repo searches needed since CONTEXT.md pinned every locus by line number.

**Pattern extraction date:** 2026-04-24
