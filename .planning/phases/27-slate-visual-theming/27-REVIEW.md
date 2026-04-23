---
phase: 27-slate-visual-theming
reviewed: 2026-04-24T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - pyproject.toml
  - src/shitbox/capture/title_card.py
  - tests/test_capture_title_card.py
  - tests/test_title_card_overflow_and_tz.py
  - src/shitbox/capture/assets/cinzel/OFL.txt
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-04-24
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 27 vendors the Cinzel typeface under `src/shitbox/capture/assets/cinzel/`, widens the wheel glob in `pyproject.toml`, and rewires `title_card.py` to use Cinzel Bold for the hero (ALL CAPS + drop-everything-after-first-comma transform) and Cinzel Regular for the date/driver rows. Badge and coord row are unchanged, and the `FONT_DISPLAY` alias keeps the badge call site zero-touch. Tests were extended to cover the new constants, the state-suffix drop, the ALL CAPS hero and whimsy paths, and per-event-type render smoke-coverage.

The code changes are small, well-commented, and consistent with the plan. No correctness, security, or thread-safety issues in the Python diff. The one substantive finding is the bundled `OFL.txt`: it is a verbatim SIL OFL 1.1 licence with an intact permission grant and disclaimer, but the Reserved Font Name line reads "Cinzel Decorative" — that is the sibling family, not the "Cinzel" family whose TTFs are actually shipped. Since clause 3 of the OFL constrains what you can do with the Reserved Font Name, the licence text must match the font you are redistributing.

Everything else is style-level polish.

## Warnings

### WR-01: OFL.txt Reserved Font Name does not match the bundled font family

**File:** `src/shitbox/capture/assets/cinzel/OFL.txt:2`
**Issue:** The vendored TTFs are `Cinzel-Bold.ttf` and `Cinzel-Regular.ttf` (the Cinzel family). The bundled licence line reads:

```
Copyright © 2012 Natanael Gama (www.ndiscovered.com), with Reserved Font Name "Cinzel Decorative"
```

"Cinzel Decorative" is a separate font family by the same designer. The upstream Cinzel repo's OFL.txt reserves the name "Cinzel" (singular, without "Decorative"). Two problems with shipping a mismatched licence:

1. The Reserved Font Name in the shipped licence does not cover the font files we are actually redistributing, which weakens our claim that we are complying with OFL clause 3.
2. It looks like the OFL.txt was lifted from a different sibling project. Downstream readers (or anyone auditing the wheel contents) will notice.

The prompt explicitly asked us to verify the licence grant is present (it is — clause-by-clause text on lines 48-80) and that the Reserved Font Name matches "Cinzel" (it does not).

**Fix:** Replace the copy with the OFL.txt from the actual Cinzel upstream (`https://github.com/NDISCOVER/Cinzel/blob/master/OFL.txt`). The correct second line for this family is:

```
Copyright (c) 2012, Natanael Gama (info@ndiscovered.com), with Reserved Font Name "Cinzel"
```

The rest of the licence body (PREAMBLE through DISCLAIMER) can stay as-is since the OFL template text is identical.

## Info

### IN-01: Dead code — `_abbreviate_au_states` and `AU_STATE_ABBREVIATIONS` no longer called on any live path

**File:** `src/shitbox/capture/title_card.py:110-134`
**Issue:** Phase 27 changed the hero derivation to drop everything after the first comma (`place.split(",", 1)[0]`) before shrink-fit runs. The comment on line 283 even spells this out:

```
# D-06 (Phase 27): drop the state suffix entirely. Everything after
# the first comma is stripped from the hero — "Narellan, New South
# Wales" becomes "Narellan". _abbreviate_au_states stays in the
# module as a utility but is no longer called on this path.
```

`_abbreviate_au_states` and the `AU_STATE_ABBREVIATIONS` table are now only exercised by the Phase 26 regression tests in `tests/test_title_card_overflow_and_tz.py`. No production path calls them. Keeping an unused abbreviation table bolted to the hero pipeline is mild technical debt: future readers will assume it still has a job, and the longest-first-ordering invariant gets maintained for nothing.

**Fix:** Either delete the function, table, and associated tests now that the hero transform is simpler, or add a one-line module docstring note explaining why the helper is retained (e.g. "kept for future coord-row formatting"). If there is no future use, deletion is cheaper than the maintenance burden. If kept, `test_au_state_abbreviation_longest_first` is still useful as a sanity check.

### IN-02: Truncation may emit a trailing ellipsis followed by `.upper()` round-trip that silently breaks the `max_chars` guarantee for edge inputs

**File:** `src/shitbox/capture/title_card.py:288`
**Issue:** The comment on line 285-287 reads:

```
# D-05 (Phase 27): ALL CAPS hero. Applied AFTER truncation so the
# character count is measured on the natural-case string; Unicode
# upper-case round-trips the ellipsis character ("…") unchanged.
```

The claim is correct for the Pillow-encodeable ellipsis, but there is a subtle pitfall: `str.upper()` can lengthen a string under Unicode case folding (e.g. German `ß` → `SS`, Turkish dotless `ı` → `I` is fine, but a few German/Greek ligatures grow by one character). For realistic AU geocoder output this never fires, so it is an info-level note, not a warning. `_truncate` is measuring characters pre-upper, so a pathological input could end up one or two characters over `MAX_PLACE_CHARS` after the `.upper()` call.

**Fix:** If you want the bound to hold in all cases, apply `.upper()` before `_truncate`:

```python
hero_text = _truncate(hero_raw.upper(), MAX_PLACE_CHARS)
```

The ellipsis-roundtrip concern the comment raises does not actually apply when the upper-case is done first, because `_truncate` chooses where to cut and appends the ellipsis itself. Either pattern works; current code is defensible given AU-only input, but flipping the order is one line and removes the caveat.

### IN-03: `FONT_DISPLAY` alias is documented against the wrong decision ID

**File:** `src/shitbox/capture/title_card.py:59-63`
**Issue:** The comment cites "D-09" for the `FONT_DISPLAY` back-compat alias, but D-09 in the module docstring (line 21-27) refers to the whimsy-fallback hero path, not the badge-font stability decision. The actual Phase 27 plan decision for keeping the badge on Bold appears to be D-11 (badge unchanged) and D-13 (Bold on hero). Small documentation drift that future-you will have to untangle when cross-referencing the plan.

**Fix:** Swap the D-09 citation on line 59 to whichever plan decision actually covers "badge stays on Cinzel Bold, keep the call-site zero-touch." Also worth double-checking line 349-351 which cites D-09 for the same reason.

---

_Reviewed: 2026-04-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
