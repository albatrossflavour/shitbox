---
phase: 27-slate-visual-theming
plan: 01
subsystem: capture / packaging
tags: [assets, packaging, wave-0, cinzel, typography]
requires: []
provides:
  - Cinzel TTF assets vendored under src/shitbox/capture/assets/cinzel/
  - pyproject.toml package-data glob covering the new TTFs and OFL.txt
  - tests/test_capture_title_card.py::test_cinzel_fonts_load (Wave 0 stub)
affects:
  - Plan 27-02 (typography swap) — can now point title_card.py at the bundled TTFs
tech_stack:
  added: []
  patterns:
    - "Path(__file__).parent / 'assets' / 'cinzel' / ... precedent extended to TTFs"
    - "Explicit per-subdir package-data glob (no recursive **; keeps future asset types deliberate)"
key_files:
  created:
    - src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf
    - src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf
    - src/shitbox/capture/assets/cinzel/OFL.txt
    - .planning/phases/27-slate-visual-theming/deferred-items.md
  modified:
    - pyproject.toml
    - tests/test_capture_title_card.py
decisions:
  - NDISCOVER upstream used (canonical Cinzel source referenced by the OFL header itself); google/fonts mirror not needed
  - Explicit enumeration (capture/assets/cinzel/*.ttf and capture/assets/cinzel/OFL.txt) chosen over recursive capture/assets/**/* glob to keep future asset additions deliberate and auditable
  - Test uses pytest.importorskip("PIL") and lives under tests/, resolving the source tree directly — wheel-packaged verification deferred to Plan 02's broader UAT
requirements: [SC-3]
metrics:
  duration: ~10 minutes
  completed: 2026-04-24
---

# Phase 27 Plan 01: Cinzel Asset Vendoring and Packaging Summary

Vendored the Cinzel Bold and Regular TTFs (v2.000 static) plus the SIL OFL 1.1 licence text into `src/shitbox/capture/assets/cinzel/`, extended the `pyproject.toml` `package-data` glob to cover them, and dropped a Wave 0 packaging-sanity test that drives both TTFs through `PIL.ImageFont.truetype` from the in-tree path.

## What shipped

Three vendored assets from the canonical NDISCOVER upstream:

| File                                                    | Bytes | Notes                                                                                     |
|---------------------------------------------------------|-------|-------------------------------------------------------------------------------------------|
| `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf`     | 68768 | TrueType, digitally signed, "CinzelBold2.000"                                            |
| `src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf`  | 66996 | TrueType, digitally signed, "CinzelRegular2.000"                                         |
| `src/shitbox/capture/assets/cinzel/OFL.txt`             | 4486  | SIL OFL 1.1 verbatim, NDISCOVER copyright header ("Copyright 2020 The Cinzel Project Authors") |

All three from `https://github.com/NDISCOVER/Cinzel/raw/master/` — the repo referenced in the OFL header, so byte-identical to what's linked from the licence itself. No google/fonts fallback needed.

`pyproject.toml` `[tool.setuptools.package-data]` stanza:

**Before:**

```toml
[tool.setuptools.package-data]
shitbox = ["capture/assets/*.png", "dashboard/static/**/*"]
```

**After:**

```toml
[tool.setuptools.package-data]
shitbox = [
    "capture/assets/*.png",
    "capture/assets/cinzel/*.ttf",
    "capture/assets/cinzel/OFL.txt",
    "dashboard/static/**/*",
]
```

Two new explicit globs:

- `capture/assets/cinzel/*.ttf` — picks up both Cinzel TTFs. The subdir path is necessary because setuptools `package-data` globs are non-recursive by default (27-RESEARCH Pitfall 1 — "the single most likely way Phase 27 ships broken").
- `capture/assets/cinzel/OFL.txt` — SIL OFL 1.1 Section 5 requires the licence ship with any binary redistribution; a wheel counts.

Wave 0 test lives at `tests/test_capture_title_card.py:423` as `test_cinzel_fonts_load`. Resolves the TTFs from the source tree via `Path(__file__).resolve().parent.parent / "src" / "shitbox" / "capture" / "assets" / "cinzel" / ...`, asserts both load via `ImageFont.truetype`, and skips cleanly via `pytest.importorskip("PIL")` on machines without Pillow.

## Tasks executed

| # | Name                                             | Commit    | Files                                                                                    |
|---|--------------------------------------------------|-----------|------------------------------------------------------------------------------------------|
| 1 | Vendor Cinzel TTFs and OFL licence               | `a0ff8df` | `Cinzel-Bold.ttf`, `Cinzel-Regular.ttf`, `OFL.txt` under `src/shitbox/capture/assets/cinzel/` |
| 2 | Extend pyproject.toml package-data glob          | `b1b9929` | `pyproject.toml`                                                                         |
| 3 | Wave 0 packaging-sanity test                     | `edc5930` | `tests/test_capture_title_card.py`                                                       |

## Verification

Plan-level automated block (all pass):

```text
test -f src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf     → present
test -f src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf  → present
test -f src/shitbox/capture/assets/cinzel/OFL.txt             → present
grep 'capture/assets/cinzel/\*\.ttf' pyproject.toml           → match
grep 'capture/assets/cinzel/OFL\.txt' pyproject.toml          → match
pytest tests/test_capture_title_card.py::test_cinzel_fonts_load -q  → 1 passed in 0.06s
pytest tests/test_capture_title_card.py tests/test_title_card_overflow_and_tz.py tests/test_config_title_card.py -q  → 48 passed in 0.40s
```

No Phase 26 regression. `title_card.py` untouched (that is Plan 02's remit). `TitleCardConfig` untouched (SC-3 backward-compat honoured).

Manual wheel smoke test (`python -m build --wheel` + unzip check) deferred — `build` isn't installed in this worktree, and the plan marks that step "optional, defers to Plan 02's broader verification."

## Deviations from Plan

None for the plan's stated scope. One adjacent observation logged out-of-scope:

### Pre-existing lint errors on `main` — out of scope, logged for later

Task 2's acceptance criteria asked for `ruff check src/` to exit 0. The command returns 11 errors, but a clean `git stash && ruff check src/` against `ec83ff2` (the plan's base commit) shows the exact same 11 errors before any Phase 27 work touched the tree. They are in `collectors/light.py`, `events/engine.py`, `storage/logbook.py`, and `sync/capture_sync.py` — all files untouched by this plan.

Per the executor scope-boundary rule, pre-existing lint warnings in unrelated files are not my problem here. I recorded them in `.planning/phases/27-slate-visual-theming/deferred-items.md` as a follow-up `chore(lint)` sweep. Plan 27-01 itself introduces zero new lint errors: `ruff check tests/test_capture_title_card.py` passes clean, and `pyproject.toml` is a TOML file outside ruff's scope.

## Threat Model Compliance

Dispositions from the plan's STRIDE register:

- **T-27-01-01** (tampering): fetched only over HTTPS from NDISCOVER; raw bytes committed; `file` confirms TrueType Font data on both TTFs. Mitigated.
- **T-27-01-02** (malformed TTF DoS): accepted — Plan 02's `_font()` helper retains the existing try/except fallback.
- **T-27-01-03** (OFL compliance): `OFL.txt` shipped verbatim and explicitly named in `pyproject.toml`. Mitigated.
- **T-27-01-04** (upstream compromise): accepted — low-value target, no runtime fetch.

No new threat surface introduced beyond what the register anticipated.

## Self-Check: PASSED

Files verified present:

- `src/shitbox/capture/assets/cinzel/Cinzel-Bold.ttf` — FOUND
- `src/shitbox/capture/assets/cinzel/Cinzel-Regular.ttf` — FOUND
- `src/shitbox/capture/assets/cinzel/OFL.txt` — FOUND
- `pyproject.toml` — modified (stanza confirmed)
- `tests/test_capture_title_card.py` — modified (new test at line 423)

Commits verified in `git log`:

- `a0ff8df` — FOUND
- `b1b9929` — FOUND
- `edc5930` — FOUND
