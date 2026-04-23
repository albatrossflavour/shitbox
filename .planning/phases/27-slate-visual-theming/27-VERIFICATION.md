---
phase: 27-slate-visual-theming
verified: 2026-04-24T09:24:00Z
status: human_needed
score: 5/5 must-haves verified (SC-1 partial — on-Pi UAT outstanding)
overrides_applied: 0
re_verification: null
human_verification:
  - test: "On-Pi render + eyeball of a real themed slate"
    expected: "Cinzel Bold renders at ~140pt for the hero (not the 10pt bitmap fallback), hero reads ALL CAPS without AU state suffix, date/driver rows render Cinzel Regular, badge composition + palette match Phase 26. Poster PNG and in-video slate (MPEG-TS concat) both show the new design language distinct from Phase 26's DejaVu Sans Bold."
    why_human: "SC-1 calls for a visible design language. Dev-laptop Pillow confirms the TTF loads, the PNG writes, and the TS encodes cleanly (slate_rendered log shows place=NARELLAN), but 'looks right, reads distinct from Phase 26, Cinzel Bold not over-heavy at 140pt' requires visual inspection on the Pi pipeline. Phase 26's VERIFICATION already confirmed the slate → events.json → concat pipeline runs end-to-end on the Pi, so this is a typography-swap UAT, not a pipeline UAT."
---

# Phase 27: Slate Visual Theming Verification Report

**Phase Goal:** Typography-only visual theming pass — vendor Cinzel (SIL OFL 1.1), swap the display typeface in `TitleCardRenderer` to Cinzel Bold for the hero and Cinzel Regular for date/driver rows, render the hero ALL CAPS with the AU state suffix dropped. Palette, badge composition, coord-row DejaVu Mono, and `TitleCardConfig` shape stay as Phase 26 shipped them.

**Verified:** 2026-04-24T09:24:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### ROADMAP Success Criteria

| #   | Truth (SC from ROADMAP)                                                                                                                        | Status     | Evidence                                                                                                                                                                                                                                                        |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SC-1 | Themed slate renders as both poster PNG and in-video slate with a visible design language distinct from Phase 26                              | ? HUMAN    | Automated: TTFs load via Pillow (`test_cinzel_fonts_load`), `FONT_DISPLAY_BOLD` points at `Cinzel-Bold.ttf` (`test_hero_uses_cinzel_bold`), full `render()` produced PNG (53 KB) + TS (60 KB) on the dev laptop with `place=NARELLAN` in the log. Visual "looks distinct from Phase 26" requires Pi eyeball; Phase 26 VERIFICATION already confirmed the pipeline (poster_url on events.json, TS concat) works on the Pi. |
| SC-2 | All event types (HARD_BRAKE, BIG_CORNER, HIGH_G, ROUGH_ROAD, MANUAL_CAPTURE, ROLLOVER, BOOT) + no-GPS whimsy fallback render correctly        | ✓ VERIFIED | `test_all_event_types_render_with_cinzel` parametric over all 7 enum values — 7 PASSED. `test_no_gps_whimsy_still_renders` passes. `test_resolve_strings_whimsy_is_all_caps` confirms whimsy goes uppercase.                                                     |
| SC-3 | `TitleCardConfig` shape stays backward-compatible (no breaking config changes)                                                                 | ✓ VERIFIED | `tests/test_config_title_card.py` green (no changes). Plan 01 `must_haves.truths` and `success_criteria` explicitly gate on "TitleCardConfig shape untouched — no YAML keys added, no dataclass fields added". Grep on `TitleCardConfig` shows no edits in this phase's diff. |
| SC-4 | G-02 measure-and-shrink fit behaviour preserved for long place names                                                                           | ✓ VERIFIED | `HERO_FONT_FLOOR = 100`, `HERO_FONT_STEP = 10`, `SAFE_MARGIN_PX = 60`, `MAX_PLACE_CHARS = 28` all unchanged (module constants verified via Python probe). `test_hero_shrink_fit_cinzel` asserts `NARELLAN` fits at 140, `MOUNT PANORAMA` shrinks >= 100, 28-char all-caps fits safe width or ellipsis-truncates. PASSED. |
| SC-5 | Rendered slate fits the 1280×720 canvas with safe margins                                                                                      | ✓ VERIFIED | `CANVAS_W=1280`, `CANVAS_H=720` unchanged. `test_hero_shrink_fit_cinzel` third assertion measures fitted text width against `CANVAS_W - 2*SAFE_MARGIN_PX = 1160 px`. Shrink-fit loop gates on this width. 18 Phase 27 tests pass, all under the same canvas constants. |

**Score:** 5/5 SCs satisfied in code; SC-1 flagged for Pi visual UAT (design-language judgment is inherently visual).

### Plan-level Must-Have Truths

Plan 27-01 (assets + packaging) — all VERIFIED:
- Cinzel Bold + Regular TTFs are valid TrueType under `src/shitbox/capture/assets/cinzel/` (68 KB / 66 KB; `file` reports "TrueType Font data, digitally signed")
- `OFL.txt` ships alongside (4.4 KB, SIL OFL 1.1 verbatim — the REVIEW flagged WR-01 that the Reserved Font Name line reads "Cinzel Decorative" rather than "Cinzel". This is a licence-hygiene issue, not a Phase 27 SC failure; logged as a follow-up below.)
- `pyproject.toml` `package-data` glob covers `capture/assets/cinzel/*.ttf` and `capture/assets/cinzel/OFL.txt` (verified by reading lines 55-61)
- `test_cinzel_fonts_load` passes; does not fall back to `ImageFont.load_default()`
- `TitleCardConfig` shape untouched (no dataclass-field adds, no YAML-key adds)

Plan 27-02 (typography swap) — all VERIFIED:
- Hero path resolves Cinzel Bold from bundled TTF (module constant + `test_hero_uses_cinzel_bold`)
- Hero is ALL CAPS with state suffix dropped (`Narellan, New South Wales` → `NARELLAN`; 6 parametric cases pass incl. whitespace-normalisation and no-comma edge)
- Date/driver rows load `FONT_DISPLAY_REGULAR` (title_card.py lines 346-347)
- Badge keeps `FONT_DISPLAY` reference (line 351); `_draw_badge` untouched; per-event colours untouched
- Coord row still loads `FONT_MONO` DejaVu Sans Mono at 28pt (line 348)
- Whimsy branch also ALL CAPS (title_card.py line 301; `test_resolve_strings_whimsy_is_all_caps` PASSED)
- `HERO_FONT_FLOOR`, `HERO_FONT_STEP`, `MAX_PLACE_CHARS`, `SAFE_MARGIN_PX` unchanged
- All 7 event types render (`test_all_event_types_render_with_cinzel` 7/7 PASSED)
- Phase 26 regression tests green — full suite `tests/test_capture_title_card.py tests/test_title_card_overflow_and_tz.py tests/test_config_title_card.py` → 68 PASSED

### Required Artifacts

| Artifact                                                        | Expected                                       | Status     | Details                                                                                                     |
| --------------------------------------------------------------- | ---------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------- |
| `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf`             | Cinzel Bold v2.000 TTF, > 50 KB                | ✓ VERIFIED | 68 768 bytes, TrueType digitally signed, "CinzelBold2.000"                                                  |
| `src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf`          | Cinzel Regular v2.000 TTF, > 50 KB             | ✓ VERIFIED | 66 996 bytes, TrueType digitally signed, "CinzelRegular2.000"                                               |
| `src/shitbox/capture/assets/cinzel/OFL.txt`                     | SIL OFL 1.1 verbatim, > 2 KB                   | ⚠️ PRESENT  | 4 486 bytes. Contents are SIL OFL 1.1, but REVIEW WR-01 notes the Reserved Font Name reads "Cinzel Decorative" — sibling family. Does not fail Phase 27 SC but should be fixed for licence hygiene. |
| `pyproject.toml`                                                | Package-data glob extends to Cinzel TTFs + OFL | ✓ VERIFIED | Lines 55-61 list `capture/assets/cinzel/*.ttf` and `capture/assets/cinzel/OFL.txt`, PNG + dashboard globs preserved |
| `src/shitbox/capture/title_card.py`                             | FONT_DISPLAY_BOLD/REGULAR + ALL CAPS + state-drop | ✓ VERIFIED | Lines 53-68 constants; lines 279-301 `_resolve_strings` hero + whimsy; lines 346-364 font loads + hero call site; badge alias preserved |
| `tests/test_capture_title_card.py`                              | Phase 27 typography tests                      | ✓ VERIFIED | `test_cinzel_fonts_load`, `test_font_display_constants_point_at_bundled_cinzel`, `test_resolve_strings_hero_is_all_caps_with_state_dropped`, `test_resolve_strings_coord_only_branch_unchanged`, `test_resolve_strings_whimsy_is_all_caps`, `test_hero_uses_cinzel_bold`, `test_hero_all_caps`, `test_state_suffix_dropped_from_hero` (6 cases), `test_no_gps_whimsy_still_renders`, `test_all_event_types_render_with_cinzel` (7 cases) — all present, all passing |
| `tests/test_title_card_overflow_and_tz.py`                      | Cinzel shrink-fit assertions                   | ✓ VERIFIED | `test_hero_shrink_fit_cinzel` present (line 66) and passing; existing `_abbreviate_au_states` helper tests retained per D-06 (plan Action-text deviation documented in 27-02-SUMMARY) |

### Key Link Verification

| From                                          | To                                                            | Via                                                          | Status  | Details |
| --------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ | ------- | ------- |
| `src/shitbox/capture/assets/cinzel/`          | `pyproject.toml [tool.setuptools.package-data]`               | glob `capture/assets/cinzel/*.ttf` + `.../OFL.txt`           | ✓ WIRED | Verified on lines 58-59 of pyproject.toml; tomllib-parseable |
| `title_card.py FONT_DISPLAY_BOLD`             | `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf`           | `Path(__file__).parent / 'assets' / 'cinzel' / 'Cinzel-Bold.ttf'` | ✓ WIRED | Verified via Python probe — `Path(title_card.FONT_DISPLAY_BOLD).exists() == True`. `test_hero_uses_cinzel_bold` asserts the same. |
| `title_card.py FONT_DISPLAY_REGULAR`          | `src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf`        | `Path(__file__).parent / 'assets' / 'cinzel' / 'Cinzel-Regular.ttf'` | ✓ WIRED | Verified via Python probe; used by `f_date` and `f_driver` loads in `_compose_png` |
| `_resolve_strings` hero path                  | `hero_text`                                                   | `place.split(',', 1)[0].strip() → _truncate(..., 28).upper()` | ✓ WIRED | Live probe: `Narellan, New South Wales` → `NARELLAN`; `  Hobart ,  Tasmania  ` → `HOBART`; `Nimbin` → `NIMBIN` |
| `_compose_png` date/driver rows               | Cinzel Regular                                                | `_font(FONT_DISPLAY_REGULAR, FONT_DATE/FONT_DRIVER)`         | ✓ WIRED | Lines 346-347 in title_card.py |
| `_compose_png` hero call site                 | Cinzel Bold via `_fit_hero_to_canvas`                         | explicit `FONT_DISPLAY_BOLD` argument                        | ✓ WIRED | Line 364 in title_card.py |
| `_compose_png` badge label                    | Cinzel Bold (back-compat alias)                               | `_font(FONT_DISPLAY, FONT_BADGE)` with `FONT_DISPLAY = FONT_DISPLAY_BOLD` | ✓ WIRED | Line 351; alias defined line 63 |

### Data-Flow Trace (Level 4)

| Artifact                        | Data Variable          | Source                                                        | Produces Real Data | Status                |
| ------------------------------- | ---------------------- | ------------------------------------------------------------- | ------------------ | --------------------- |
| `title_card.py` hero rendering  | `hero_text`            | `_resolve_strings` → geocoder callback OR whimsy pool         | Yes (live probe)   | ✓ FLOWING             |
| `title_card.py` coord row       | `coord_text`           | `f"{lat:.4f}, {lng:.4f}"` from event `lat`/`lng`              | Yes                | ✓ FLOWING             |
| `title_card.py` date row        | `date_str`             | `datetime.fromtimestamp(event.start_time).astimezone()`       | Yes                | ✓ FLOWING             |
| `title_card.py` driver credit   | `effective_driver`     | `driver_name` arg passed from `UnifiedEngine` (Phase 26 wire) | Yes (upstream unchanged) | ✓ FLOWING       |
| `title_card.py` badge           | `badge_label`, `badge_colour` | `label_for(event.event_type)`, `colour_for(...)` from `events/labels.py` | Yes (unchanged from Phase 26) | ✓ FLOWING  |
| PNG output file                 | PNG bytes              | `Image.save(png_path, 'PNG')` end of `_compose_png`           | Yes (53 KB in live probe) | ✓ FLOWING       |
| TS output file                  | TS bytes               | ffmpeg subprocess encoding the PNG                            | Yes (60 KB in live probe) | ✓ FLOWING       |

### Behavioural Spot-Checks

| Behaviour                                              | Command                                                                                  | Result           | Status  |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------- | ---------------- | ------- |
| Module imports + font constants resolve                | `python -c "from shitbox.capture import title_card; Path(FONT_DISPLAY_BOLD).exists()"`   | True             | ✓ PASS  |
| `_resolve_strings` state-drop + uppercase              | Live probe: `Narellan, New South Wales` → `NARELLAN`                                     | Match            | ✓ PASS  |
| `_resolve_strings` coord-only branch                   | Live probe: geocoder returns None → `hero_text is None`, `coord_text == '-34.0000, 150.7000'` | Match        | ✓ PASS  |
| `_resolve_strings` whimsy uppercase                    | Live probe: no geocoder → `HERE BE DRAGONS`                                              | Match            | ✓ PASS  |
| Whitespace normalisation                               | Live probe: `"  Hobart ,  Tasmania  "` → `HOBART`                                        | Match            | ✓ PASS  |
| End-to-end render (PNG + TS)                           | `renderer.render(ev, png, ts, geocoder, driver_name='Tony')` on dev laptop               | `duration=1.0, png=53 KB, ts=60 KB, slate_rendered log place=NARELLAN` | ✓ PASS |
| Focused Phase 27 test set                              | `pytest tests/test_capture_title_card.py::test_all_event_types_render_with_cinzel ... -v` | 18/18 PASSED    | ✓ PASS  |
| Full title-card suite                                  | `pytest tests/test_capture_title_card.py tests/test_title_card_overflow_and_tz.py tests/test_config_title_card.py -q` | 68/68 PASSED | ✓ PASS |
| Lint on modified files                                 | `ruff check src/shitbox/capture/title_card.py tests/test_capture_title_card.py tests/test_title_card_overflow_and_tz.py` | All checks passed | ✓ PASS |
| On-Pi visual rendering of Cinzel Bold at 140pt         | Pi eyeball after `git pull` + `scripts/trigger-capture.sh`                               | Not run from dev laptop | ? SKIP (see human_verification) |

### Requirements Coverage

| Requirement | Source Plan | Description                                        | Status     | Evidence                                                                                                    |
| ----------- | ----------- | -------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------- |
| SC-1        | 27-02       | Visible design language, poster + in-video slate   | ? HUMAN    | TTF loads, render produces PNG+TS, place=NARELLAN logs. "Looks distinct from Phase 26" needs Pi eyeball. |
| SC-2        | 27-02       | All 7 event types + no-GPS whimsy render           | ✓ SATISFIED | `test_all_event_types_render_with_cinzel` (7 cases) + `test_no_gps_whimsy_still_renders` all PASSED         |
| SC-3        | 27-01       | `TitleCardConfig` backward-compatible              | ✓ SATISFIED | No edits to dataclass; `test_config_title_card.py` passes                                                    |
| SC-4        | 27-02       | G-02 shrink-fit preserved                          | ✓ SATISFIED | Constants untouched; `test_hero_shrink_fit_cinzel` PASSED                                                    |
| SC-5        | 27-02       | Slate fits 1280×720 with safe margins              | ✓ SATISFIED | Canvas constants unchanged; shrink-fit gates on 1160px safe width; test PASSED                               |

No orphaned requirements — ROADMAP lists SC-1..SC-5; plans 27-01 and 27-02 together claim all five.

### Anti-Patterns Found

| File                                                | Line    | Pattern                                                   | Severity | Impact                                                                                                               |
| --------------------------------------------------- | ------- | --------------------------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------- |
| `src/shitbox/capture/assets/cinzel/OFL.txt`         | 2       | Reserved Font Name reads "Cinzel Decorative" not "Cinzel" | ⚠️ Warning | Licence text does not match the bundled family. Flagged by REVIEW WR-01. Does not block Phase 27 SCs but weakens OFL clause 3 compliance. Fix: swap for NDISCOVER Cinzel's own `OFL.txt`. |
| `src/shitbox/capture/title_card.py`                 | 110-134 | `_abbreviate_au_states` + `AU_STATE_ABBREVIATIONS` retained, no live caller | ℹ️ Info   | Phase 27 explicitly kept the helper (D-06). REVIEW IN-01 suggests either deletion or a docstring note. Not a Phase 27 goal failure.                |
| `src/shitbox/capture/title_card.py`                 | 288     | `.upper()` after `_truncate` may under-run `MAX_PLACE_CHARS` on Unicode-growing input (e.g. `ß`→`SS`) | ℹ️ Info   | REVIEW IN-02. AU geocoder output never hits this case. Defensive swap (`_truncate(hero_raw.upper(), ...)`) is a one-liner. Not a Phase 27 SC failure. |
| `src/shitbox/capture/title_card.py`                 | 59-63, 349-351 | Comments cite decision ID "D-09" which actually covers the whimsy branch, not the badge-alias rationale | ℹ️ Info   | REVIEW IN-03. Documentation drift only.                                                                              |

All four are either intentional (kept helper) or review-flagged polish. None are Phase 27 SC blockers.

### Human Verification Required

**1. On-Pi themed slate UAT (SC-1 visual confirmation)**

- **Test:** On `laser`, `git pull`, confirm venv picks up both the `title_card.py` edits and the bundled Cinzel TTFs (editable install per memory — no `pip install .` needed). Trigger `scripts/trigger-capture.sh` for a manual capture. `rsync` the resulting poster PNG and event MP4 back to the laptop (Pi uses `/opt/bin/rsync` per memory).
- **Expected:** Hero text in Cinzel Bold at ~140pt, ALL CAPS, AU state suffix dropped (so a Narellan capture reads `NARELLAN`, not `Narellan, NSW`). Date + driver rows in Cinzel Regular at 40pt. Badge + palette unchanged from Phase 26. Coord row still DejaVu Sans Mono. If Cinzel Bold reads over-heavy at 140pt ALL CAPS, the follow-up is Cinzel SemiBold (out of Phase 27 scope, noted in 27-02-SUMMARY qualitative section).
- **Why human:** "Visible design language distinct from Phase 26" is the goal (SC-1, D-02). Automated tests confirm TTFs load, PNG + TS render, and the hero string is transformed; none of them can judge "looks right, reads distinct from Phase 26, Cinzel Bold not over-heavy". Phase 26's VERIFICATION already established the pipeline reaches the Pi and the website, so this is a pure typography-swap eyeball.

### Gaps Summary

No goal-blocking gaps. Five of five ROADMAP Success Criteria are satisfied by the code changes; the only outstanding item is the visual UAT for SC-1's design-language assertion, which is inherently a human-visual check. Code-level behaviour (TTF load, ALL CAPS transform, state-drop, Regular-weight date/driver rows, shrink-fit, all seven event types rendering) is covered by 18 Phase 27 tests plus 50 Phase 26 regression tests, all green.

### Follow-ups (not Phase 27 blockers)

- **Licence hygiene (REVIEW WR-01):** `OFL.txt` Reserved Font Name line mismatch. Swap for the NDISCOVER Cinzel upstream's own `OFL.txt`. One-file fix, outside Phase 27 SC scope but worth closing before any public wheel ships.
- **Design polish (REVIEW IN-01, IN-02, IN-03):** dead-code helper retention, Unicode-growth edge case in `.upper()` ordering, and decision-ID comment drift. Low priority.
- **Qualitative:** per 27-02-SUMMARY, if Cinzel Bold at 140pt ALL CAPS reads too heavy after Pi UAT, follow-up is Cinzel SemiBold (27-RESEARCH.md Open Question 1).

---

_Verified: 2026-04-24T09:24:00Z_
_Verifier: Claude (gsd-verifier)_
