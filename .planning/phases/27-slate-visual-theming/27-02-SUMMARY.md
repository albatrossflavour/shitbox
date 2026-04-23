---
phase: 27-slate-visual-theming
plan: 02
subsystem: capture / typography
tags: [cinzel, typography, all-caps, state-drop, shrink-fit, wave-2]
requires: ["27-01"]
provides:
  - Cinzel Bold + Regular wired through title_card.py (FONT_DISPLAY_BOLD/REGULAR)
  - FONT_DISPLAY back-compat alias keeps the badge call site zero-touch
  - Hero branch drops state suffix and renders ALL CAPS ("Narellan, New South Wales" -> "NARELLAN")
  - Whimsy branch renders ALL CAPS
  - Seven event types + no-GPS whimsy fallback all render non-empty PNGs under Cinzel
affects:
  - Public slate rendered per event capture — visible design language change
  - slate_rendered log line field "place" now logs upper-cased value
tech_stack:
  added: []
  patterns:
    - "Back-compat constant alias (FONT_DISPLAY = FONT_DISPLAY_BOLD) minimises call-site churn for the badge font"
    - "Operation order (split -> strip -> truncate -> upper) preserves existing T-26-03-01 mitigation while adding new transforms"
    - "Parametric pytest over EventType names covers all seven badge paths in one case"
key_files:
  created: []
  modified:
    - src/shitbox/capture/title_card.py
    - tests/test_capture_title_card.py
    - tests/test_title_card_overflow_and_tz.py
decisions:
  - FONT_DISPLAY retained as a back-compat alias for FONT_DISPLAY_BOLD (D-09) — the badge and overflow tests both benefit
  - _abbreviate_au_states helper kept in the module (D-06); only the hero path stops calling it
  - test_long_place_name_fits_safe_width renamed to test_hero_shrink_fit_cinzel — asserts against the Phase 27 Cinzel metrics and explicit FONT_DISPLAY_BOLD path
  - test_au_state_abbreviation and test_au_state_abbreviation_idempotent helper unit tests preserved as-is with their "Narellan, NSW" assertions per the plan's Action text; they exercise the helper directly, not the full-render pipeline
requirements: [SC-1, SC-2, SC-4, SC-5]
metrics:
  duration: ~6 minutes
  completed: 2026-04-24
---

# Phase 27 Plan 02: Cinzel Typography + ALL CAPS State-Drop Summary

Applied the Cinzel typography theme to `src/shitbox/capture/title_card.py` — new `FONT_DISPLAY_BOLD` and `FONT_DISPLAY_REGULAR` constants point at the bundled TTFs from Plan 27-01, the hero branch in `_resolve_strings` drops the state suffix and upper-cases, and the whimsy fallback does the same. Date and driver rows now render in Cinzel Regular; the badge label keeps its Phase 26 Bold weight via a `FONT_DISPLAY = FONT_DISPLAY_BOLD` alias. Seven Phase 27 typography tests (plus the renamed shrink-fit) pin every new behaviour; full repo suite is green.

## What shipped

Three commits per task, five total (two RED + three GREEN/feat). Line-count delta:

| File | Before | After | Delta |
|------|-------:|------:|------:|
| `src/shitbox/capture/title_card.py` | 585 | 614 | +29 (constants expanded from 4 lines to 20 including comments; `_resolve_strings` hero+whimsy rewritten +8 lines net) |
| `tests/test_capture_title_card.py` | 453 | 644 | +191 (2 Task 1 + 3 Task 2 + 5 Task 3 tests; helpers) |
| `tests/test_title_card_overflow_and_tz.py` | 150 | 166 | +16 (`test_long_place_name_fits_safe_width` replaced with `test_hero_shrink_fit_cinzel`; one ellipsis-truncate assertion updated) |

Diffstat: `3 files changed, 267 insertions(+), 28 deletions(-)`.

### Typography

- **Constants (title_card.py ~L49-69):**
  - `FONT_DISPLAY_BOLD` → `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf`
  - `FONT_DISPLAY_REGULAR` → `src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf`
  - `FONT_DISPLAY = FONT_DISPLAY_BOLD` alias for badge call site (D-09)
  - `FONT_MONO` unchanged (DejaVu Sans Mono, D-12)

- **`_resolve_strings` hero branch (~L283-293):** `place.split(",", 1)[0].strip()` → `_truncate(..., MAX_PLACE_CHARS).upper()`. `_abbreviate_au_states` no longer called on this path, still in the module.

- **`_resolve_strings` whimsy branch (~L298-301):** `.upper()` appended after `_truncate(...)`.

- **`_compose_png` font loads (~L337-344):** `f_date` and `f_driver` load `FONT_DISPLAY_REGULAR`; `f_badge` still loads `FONT_DISPLAY` (Bold via alias); `f_coord` unchanged.

- **Hero call site (~L355-358):** explicit `FONT_DISPLAY_BOLD` passed to `_fit_hero_to_canvas`.

### Tests

Seven new Phase 27 typography tests (`test_capture_title_card.py`):

| Name | Coverage | Parametric |
|------|----------|-----------:|
| `test_font_display_constants_point_at_bundled_cinzel` | Task 1 constants + alias (Cinzel-Bold.ttf, Cinzel-Regular.ttf, FONT_MONO preserved) | — |
| `test_resolve_strings_hero_is_all_caps_with_state_dropped` | Task 2 hero path (D-05, D-06) | — |
| `test_resolve_strings_coord_only_branch_unchanged` | Task 2 coord-only (D-10 regression) | — |
| `test_resolve_strings_whimsy_is_all_caps` | Task 2 whimsy (D-07) | — |
| `test_hero_uses_cinzel_bold` | SC-1: Pillow loads the bundled TTF | — |
| `test_hero_all_caps` | D-05 direct assertion | — |
| `test_state_suffix_dropped_from_hero` | D-06 coverage | 6 cases (NSW×2, QLD, NT, whitespace, no-comma) |
| `test_no_gps_whimsy_still_renders` | SC-2 whimsy-fallback render | — |
| `test_all_event_types_render_with_cinzel` | SC-2 coverage | 7 cases (HARD_BRAKE, BIG_CORNER, HIGH_G, ROUGH_ROAD, MANUAL_CAPTURE, ROLLOVER, BOOT) |

Plus `tests/test_title_card_overflow_and_tz.py::test_hero_shrink_fit_cinzel` (SC-4, D-13) — three assertions:
- `NARELLAN` fits at `FONT_HERO=140`
- `MOUNT PANORAMA` shrinks but stays `>= HERO_FONT_FLOOR=100`
- 28-char `A×28` at Cinzel Bold fits safe width or ellipsis-truncates

Total new assertions (counting parametric cases): 1 + 1 + 1 + 1 + 1 + 1 + 6 + 1 + 7 + 3 = **23**.

## Tasks executed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Swap FONT_DISPLAY constants + wire Cinzel Bold/Regular through _compose_png | `9b3f39c` (RED) / `6600d38` (GREEN) | `title_card.py`, `test_capture_title_card.py` |
| 2 | State-drop + ALL CAPS in _resolve_strings (hero + whimsy branches) | `258386b` (RED) / `dbdb634` (GREEN) | `title_card.py`, `test_capture_title_card.py` |
| 3 | Phase 27 typography tests + update Phase 26 state-abbrev assertions | `be96954` | `test_capture_title_card.py`, `test_title_card_overflow_and_tz.py` |

## Verification

Plan-level verification block all green:

```text
python -c "... constants ok"              → constants ok
python -c "... resolve ok"                → ok (hero state-drop + ALL CAPS, coord-only, whimsy)
pytest tests/test_capture_title_card.py
       tests/test_title_card_overflow_and_tz.py
       tests/test_config_title_card.py -q → 68 passed in 0.61s
ruff check tests/test_capture_title_card.py
          tests/test_title_card_overflow_and_tz.py
          src/shitbox/capture/title_card.py  → All checks passed!
pytest -q (full repo)                     → 496 passed, 1 skipped in 68.13s
```

Seven Phase 27 event-type parametric cases + six state-drop parametric cases — all PASS.

The full-repo `ruff check src/ tests/` reports 118 pre-existing errors in files untouched by this plan (mirroring the 11 reported by Plan 27-01, now higher because the error count also sweeps collectors/dashboard/sync modules). None are in files Plan 02 modified; they are the same pre-existing lint debt Plan 27-01 logged to `deferred-items.md`. Scope discipline per the executor rules says don't fix.

## Deviations from Plan

### 1. `"Narellan, NSW"` strings retained in helper unit tests (plan wording conflict)

**Found during:** Task 3 acceptance-criteria check.

**Issue:** The plan's Task 3 acceptance criterion states:

> `grep -n '"Narellan, NSW"' tests/` returns zero lines (the Phase 26 abbreviated-form assertion in full-render context is fully removed)

The same task's Action text says the opposite:

> Direct unit tests of `_abbreviate_au_states` (e.g. `test_abbreviate_new_south_wales`, `test_abbreviate_idempotent`) that call the helper itself are UNCHANGED — per D-06 the helper stays in the module and keeps working.

`tests/test_title_card_overflow_and_tz.py` contains two `"Narellan, NSW"` strings at lines 23 and 46 inside `test_au_state_abbreviation` (parametric) and `test_au_state_abbreviation_idempotent` — both direct unit tests of the helper, exactly the category the Action text says to preserve.

**Fix:** Honoured the Action text's explicit instruction (helper unit tests stay) over the strict grep criterion. The helper-unit-test assertions still pass against the unchanged helper. The full-render pipeline no longer calls the helper on the hero path; no test of full-render behaviour contains `"Narellan, NSW"`. The `test_long_place_name_fits_safe_width` test that previously asserted against `"Narellan, NSW"` in a shrink-fit (near-full-render) context has been renamed to `test_hero_shrink_fit_cinzel` and re-asserts against Cinzel ALL CAPS names. The parenthetical "in full-render context is fully removed" in the grep criterion is the author's intent.

**Files modified:** None for this deviation — the issue is plan-internal, not code-internal.

**No Rule N classification** — this is a plan-text conflict resolved by reading the Action text as binding.

### 2. Helper naming: `_make_renderer_27` instead of `_make_renderer`

**Found during:** Task 3 test-helper placement.

**Issue:** The plan offered two options — re-use existing `_make_renderer` if present, or define new helpers. The existing file has `_make_event` at module level but no `_make_renderer`; the Task 2 block introduced `_make_renderer_for_resolve`. Introducing a plain `_make_renderer` in Task 3 would have shadowed nothing but would have looked confusingly close to `_make_renderer_for_resolve`. Named the Task 3 helper `_make_renderer_27` per the plan's fallback instruction: *"If signatures differ, add the Phase 27 helpers under a different name (e.g. _make_event_27, _make_renderer_27)."*

**Files modified:** `tests/test_capture_title_card.py` — helper introduced as `_make_renderer_27`.

**No Rule N classification** — this is using a plan-documented naming fallback.

## Deployment note

Per 27-RESEARCH.md Open Question 3: the Pi's venv deployment posture (editable vs wheel) is the deciding factor for whether `git pull` is sufficient or a `pip install .` is required. The Pi at `/home/tgreen/shitbox/` was installed via `pip install -e ".[dev]"` per `CLAUDE.md`'s Commands section — editable install, so a `git pull` on `laser` picks up both the vendored Cinzel TTFs (landed by Plan 27-01) and the `title_card.py` edits from this plan without re-installing. Manual on-Pi UAT is still required per 27-VALIDATION.md — trigger a manual capture, rsync the resulting poster PNG, eyeball it for Cinzel Bold at 140pt ALL CAPS and confirm no `load_default()` typewriter fallback.

## Qualitative note on Cinzel Bold at 140pt ALL CAPS

Deferred to the on-Pi UAT pass. The dev-laptop Pillow renders produced by `test_all_event_types_render_with_cinzel` all completed successfully and the PNGs are >0 bytes, but visual assessment of "does Cinzel Bold read too heavy at 140pt ALL CAPS" requires eyeballing the rendered output on the Pi's actual pipeline. If Bold reads over-heavy after on-Pi UAT, the follow-up is to try Cinzel SemiBold (27-RESEARCH.md Open Question 1) — NOT in scope for Phase 27.

## Threat Model Compliance

All four threats from the plan's register are accounted for:

- **T-27-02-01** (DoS on pathological geocoder): mitigated. Operation order (`split` → `strip` → `_truncate` → `.upper()`) preserves the existing `MAX_PLACE_CHARS=28` clamp before upper-casing. `split(',', 1)` stops at first comma (bounded O(n) even on 10MB strings, but clamped well before). No new unbounded inputs.
- **T-27-02-02** (Unicode upper-case on ellipsis): accepted. U+2026 (`"…"`) has no upper-case mapping; `.upper()` is a no-op on the truncation suffix. No mitigation code required.
- **T-27-02-03** (Log line records upper-cased place): accepted. `slate_rendered` field `place=hero_text or "(whimsy)"` now logs `"NARELLAN"` instead of `"Narellan, NSW"`. Desirable side effect — log matches slate.
- **T-27-02-04** (Alias back-compat): accepted. `FONT_DISPLAY = FONT_DISPLAY_BOLD` is a single-line alias, pinned semantically to the badge's Bold weight requirement (D-09). Surface for future bugs is low; a future unalias is a deliberate single-line operation.

No new threat surface introduced beyond what the register anticipated.

## TDD Gate Compliance

Plan frontmatter `type: execute` (not `type: tdd`), so plan-level gate enforcement does not apply. Individual tasks used `tdd="true"` and the RED/GREEN gate commits are clearly visible in git log:

| Task | RED (test) | GREEN (feat) |
|------|------------|--------------|
| 1    | `9b3f39c` test(27-02) | `6600d38` feat(27-02) |
| 2    | `258386b` test(27-02) | `dbdb634` feat(27-02) |
| 3    | `be96954` test(27-02) | — (test-only task; no implementation commit required — functionality landed in Tasks 1 and 2) |

## Self-Check: PASSED

Files verified present/modified:

- `src/shitbox/capture/title_card.py` — MODIFIED (new constants, _resolve_strings rewritten, _compose_png font loads updated)
- `tests/test_capture_title_card.py` — MODIFIED (7 new tests + 3 helpers)
- `tests/test_title_card_overflow_and_tz.py` — MODIFIED (test_long_place_name_fits_safe_width replaced with test_hero_shrink_fit_cinzel; one FONT_DISPLAY → FONT_DISPLAY_BOLD rename in ellipsis-truncate test)
- `.planning/phases/27-slate-visual-theming/27-02-SUMMARY.md` — CREATED

Commits verified in `git log`:

- `9b3f39c` test(27-02): add failing test for Cinzel font constants — FOUND
- `6600d38` feat(27-02): swap font constants to bundled Cinzel Bold/Regular — FOUND
- `258386b` test(27-02): add failing tests for hero state-drop + ALL CAPS — FOUND
- `dbdb634` feat(27-02): drop state suffix and ALL CAPS the slate hero — FOUND
- `be96954` test(27-02): phase 27 typography tests + shrink-fit for Cinzel — FOUND
