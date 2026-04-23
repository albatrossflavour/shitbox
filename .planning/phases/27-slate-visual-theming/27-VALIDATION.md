---
phase: 27
slug: slate-visual-theming
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_capture_title_card.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~15 seconds (targeted) / ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_capture_title_card.py -q`
- **After every plan wave:** Run `pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds (quick) / 90 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 27-01-XX | 01 | 1 | SC-3 (TitleCardConfig backward-compat) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_cinzel_fonts_load -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | SC-1 (non-default typeface) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_hero_uses_cinzel_bold -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | D-05 (ALL CAPS hero) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_hero_all_caps -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | D-06 (state suffix dropped) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_state_suffix_dropped_from_hero -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | SC-4 (G-02 shrink-fit preserved) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_hero_shrink_fit_cinzel -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | SC-5 (1280×720 canvas fit) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_long_place_name_fits_safe_width -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | SC-2 (all event types render) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_all_event_types_render_with_cinzel -q` | ❌ W0 | ⬜ pending |
| 27-02-XX | 02 | 2 | SC-2 (no-GPS whimsy fallback) | — | N/A | unit | `pytest tests/test_capture_title_card.py::test_no_gps_whimsy_still_renders -q` | ❌ W0 | ⬜ pending |
| 27-01-XX | 01 | 1 | Asset packaging (wheel) | — | N/A | packaging | `python -c "import shitbox.capture; from importlib.resources import files; p = files('shitbox.capture').joinpath('assets/cinzel/Cinzel-Bold.ttf'); assert p.is_file()"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Note: Task IDs are placeholders. The planner assigns real IDs (`27-01-01`, `27-02-01`, etc.) when it writes PLAN.md files. Each unit test above is a Wave 0 stub the planner must create.

---

## Wave 0 Requirements

- [ ] `tests/test_capture_title_card.py` — extend with the nine Phase 27 stubs listed above (file already ships from Phase 26; no new conftest required)
- [ ] Pillow available in dev venv — confirm `pillow` is already a project dep; do not add a new dep

*If Phase 26 already ships `tests/test_capture_title_card.py`, Wave 0 extends it rather than creating from scratch.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cinzel Bold at 140pt ALL CAPS reads right (not too heavy) | D-04 Claude's Discretion | Subjective / typographic judgement | Render a HARD_BRAKE slate for a Narellan-style place on dev laptop; review PNG by eye. If Bold reads over-heavy, iterate to Cinzel SemiBold (via variable font or post-hoc asset swap) |
| Dark-palette-plus-engraved-serif contrast punchline lands | SC-1 (design language intent) | Tone judgement, not a pass/fail | Render one slate per event type + no-GPS whimsy; confirm the "episode title for a hatchback" joke reads |
| On-Pi wheel install packages Cinzel correctly | SC-1, asset packaging | Pi deployment validation | After wheel install on `laser`, run the packaging one-liner from the verification map under the installed env; must return the font path, not raise |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s (quick) / 90s (full)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
