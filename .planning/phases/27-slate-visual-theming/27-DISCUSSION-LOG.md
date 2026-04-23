# Phase 27: Slate Visual Theming - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or
> execution agents. Decisions are captured in `27-CONTEXT.md` —
> this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 27-slate-visual-theming
**Areas discussed:** Scope tier, Typography direction, Palette and atmosphere, Motif and badge styling

---

## Scope tier

| Option | Description | Selected |
|---|---|---|
| Minimum (recommended) | One typeface swap, deliberate palette, one motif element, badge polish. Single design pass. | ✓ |
| Stretch | Min PLUS per-event illustration, animated intro variants, crest-style driver credit. | |
| Min + one stretch item | Min baseline plus ONE selected stretch element. | |

**User's choice:** Minimum (recommended)
**Notes:** Tony picked Min straight away. The handoff already flagged this as the open question.

---

## Typography direction

### Q1 — Display typeface character

| Option | Description | Selected |
|---|---|---|
| Vintage rally / motorsport stencil | Condensed stencil / plate-style face. | |
| Field-manual / military spec | Slab serif or typewriter face. | |
| Industrial display sans | Heavy condensed sans, all-caps friendly. | |
| Restyled DejaVu (keep current font) | No new TTF, lean on weight + case + tracking. | |
| **Other** | Free text. | ✓ |

**User's choice:** "Game of thrones theme"
**Notes:** Cinzel (the Trajan-alike Google Font) is the obvious free implementation of the GoT title typeface. Confirmed back to user: "WINTERFELL"-style engraved Roman caps. User accepted.

### Q2 — Hero place name and state suffix

| Option | Description | Selected |
|---|---|---|
| Drop state, place only | "NARELLAN" — closer to GoT bit, drops Phase 26 _abbreviate_au_states from hero path. | ✓ |
| Keep state abbreviated | "NARELLAN, NSW" — Phase 26 G-02 behaviour preserved. | |
| Place hero, state as small subline | "NARELLAN" hero + small "NSW" sub-line. | |

**User's choice:** Drop state, place only
**Notes:** Same-name town ambiguity (e.g. Springwood NSW vs QLD) deferred to "revisit if it actually bites" — see CONTEXT.md `<deferred>`.

### Q3 — Date row treatment

**No question asked.** Tony said "your call".
**Claude's choice:** Cinzel Regular at FONT_DATE (40pt), unchanged Y position from Phase 26.

### Q4 — Coord row treatment

**No question asked.** Tony said "Coord row - mono".
**Locked:** DejaVu Sans Mono kept at FONT_COORD (28pt), unchanged.

---

## Palette and atmosphere

**No multi-option question asked.** Tony stated direction directly:

> Pallette, maybe keep the pallete we already have for the website?
> Slightly more whimsy than real GoT, but consistant

**Locked:** Background `#0d1117`, primary text `#ffffff`, secondary text `#c9d1d9`, mono text `#8b949e` — all unchanged. Typography carries the theme; atmosphere stays consistent with the website.

Alternatives considered in the framing but not formally presented:

- Travelogue cream / sepia
- Weathered field-manual brown
- Hazard yellow + black industrial
- Vintage Aus rally livery
- GoT-literal: warm metallic (deep blue-black + brass + warm gold)

All rejected in favour of website parity.

---

## Motif and badge styling

### Q1 — Motif beyond typography

| Option | Description | Selected |
|---|---|---|
| Nothing (recommended) | Cinzel + ALL CAPS hero IS the design language. No additional element. | ✓ |
| Thin engraved divider | Single hairline between hero and date row. | |
| House-words ribbon | "Gaffer Tape It. Drive It. Tape Better." rendered small. | |
| Small sigil mark in corner | Tiny engraved seal complementing the existing logo. | |

**User's choice:** Nothing (recommended)
**Notes:** Tony's exact words: "don't want a hat on a hat". The Cinzel typography is judged sufficient as the design language.

### Q2 — Badge styling

**No multi-option question asked.** Tony stated direction directly:

> Don't worry about colouring the badges
> We shouldn't touch the event badge, that's not ours

**Locked:** Badge composition (solid rectangle), per-event hex colours, ROLLOVER hazard stripes — all preserved exactly as Phase 26 shipped. Phase 27 does not modify `_draw_badge` or `EVENT_COLOURS`.

Alternatives considered in framing but not formally presented:

- Heraldic shield / pennant shape
- Rallye-plate (outlined number-card) styling
- Enamel sticker treatment
- Blueprint stamp
- Weathered metal plate

All rejected.

---

## Claude's Discretion

- Cinzel weight choice for hero (Bold vs SemiBold vs Black) — iterate against rendered output
- Letter-spacing / tracking on ALL CAPS hero (Pillow has no native tracking)
- Whether driver row stays Cinzel Regular or shifts to a Cinzel italic / SC variant
- Bundled font dir layout under `assets/`
- Whether to ship Cinzel SemiBold and Black as options too, or just Bold + Regular
- Where to apply the `.upper()` call (in `_resolve_strings` vs `_compose_png`)

## Deferred Ideas

- Stretch tier elements (per-event illustration, animated intro, crest-style driver block)
- Hero state-subline variant
- House-words ribbon / tagline element
- Engraved hairline divider
- Sigil mark in corner
- Palette shift toward parchment / leather / brass

## Cross-Phase Notes

- ROADMAP success criterion 1 ("at least one motif element") is reinterpreted by D-02 in CONTEXT.md as: the Cinzel typeface IS the design language. Verifier should not BLOCK on the literal wording.
- Todo `2026-04-22-extend-title-card-to-per-capture-videos.md` is functionally closed by Phase 26. Reviewed during context-gathering, not folded into Phase 27 (different scope). Recommend closing as a separate inbox cleanup.
