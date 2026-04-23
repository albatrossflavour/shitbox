---
phase: 26-event-video-title-cards
plan: "06"
subsystem: capture/engine
tags: [poster, late-update, event-id-pairing, slate-overflow, local-tz, sweep-guard, gap-closure, G-01, G-02, G-03, G-04, G-05]
requirements: [D-17, G-01, G-02, G-03, G-04, G-05]
dependency_graph:
  requires: [26-05]
  provides:
    - late-update-poster-delivery
    - event-id-pairing-hardened
    - slate-overflow-fit
    - local-tz-slate
    - startup-sweep-fixed
  affects: [engine, storage, ring_buffer, title_card, test_suite]
tech_stack:
  added: []
  patterns:
    - lock-protected-late-update-branch
    - event-id-strict-lookup
    - measure-and-shrink-fit
    - regex-word-boundary-abbreviation
    - process-mtime-only-sweep
key_files:
  created:
    - tests/test_engine_late_update_poster.py
    - tests/test_title_card_overflow_and_tz.py
  modified:
    - src/shitbox/events/engine.py
    - src/shitbox/events/storage.py
    - src/shitbox/capture/title_card.py
    - src/shitbox/capture/ring_buffer.py
    - tests/test_ring_buffer_slate.py
decisions:
  - "Late-update branch holds _event_paths_lock for the full pop + rename + JSON rewrite window — no mid-operation release. Concurrent _check_post_captures for a subsequent event must never observe 'PNG renamed, JSON not yet updated'."
  - "event_id-keyed lookup is the only trusted pairing source in the late branch. _find_capture_video (MP4 type-scan) is explicitly downgraded to last-resort with an event_find_capture_video_type_scan warning log; the late branch refuses to use it."
  - "AU state abbreviation applied BEFORE char-truncation in _resolve_strings so 'Narellan, New South Wales' becomes 'Narellan, NSW' before the 28-char clamp; otherwise the clamp would truncate the state name mid-word."
  - "Hero font shrink step 10pt, floor 100pt. Char-truncation-with-ellipsis is the floor fallback for pathological inputs; bounded by len(input) which is already clamped upstream."
  - "datetime.fromtimestamp(start_time).astimezone() uses the system TZ (Australia/Sydney on the Pi). No config override — the TZ is an environmental constant on the target hardware."
  - "Sweep is purely mtime < process_start. The prior AND-guard (mtime_ok AND id_ok) could never remove numeric orphans at real startup because _save_counter == 0 means 3 < 0 is False. save_event cannot fire until start() returns, so mtime alone is correctness-complete."
metrics:
  duration_minutes: 45
  completed_date: "2026-04-23"
  tasks_completed: 4
  files_modified: 5
  files_created: 2
---

# Phase 26 Plan 06: Gap-Closure Summary (G-01..G-05)

**One-liner:** Late-update poster delivery + strict event_id pairing (G-01, G-05), AU state abbreviation and measure-and-shrink fit at 1160px safe width (G-02), local TZ strftime on the slate date line (G-03), and a mtime-only `_cleanup_pending_slates` sweep that actually removes orphans at startup (G-04).

## Context

On-Pi UAT against the 26-05 build surfaced five gaps that the dev-laptop integration tests missed:

- **G-01** — `event_video_updated` late-update path never wrote `poster_url` or renamed the PNG; PNGs stranded in `pending_slates/` because `save_event` fired before `_check_post_captures` ran on this Pi's scheduling.
- **G-02** — `"Narellan, New South Wales"` at 140pt overflowed the 1280px slate canvas.
- **G-03** — Slate date line rendered in UTC; the Pi's local time is Sydney (AEST/AEDT). User-visible wrong timestamp.
- **G-04** — `_cleanup_pending_slates` guard required `save_id < _save_counter`, unreachable at real startup because `_save_counter == 0`.
- **G-05** — `event_video_updated` could pair a MP4 with a prior-session event JSON via the type-scan fallback.

## Exact Changes

### `src/shitbox/events/engine.py` (commit `ed95da1`)

- `_on_video_complete` restructured into EARLY / LATE branches under `_event_paths_lock`.
- LATE branch keys strictly on `event_id`:
  - Pops from `_event_poster_paths[event_id]` and `_event_video_paths[event_id]`.
  - Renames the PNG to `<day_dir>/<base>_poster.png`.
  - Calls `self.event_storage.update_event_poster(event_id, poster_path)` to rewrite the saved JSON.
  - Emits `event_video_update_orphan` log when no pairing is found — no fallback to MP4 type-scan.
- `_find_capture_video` docstring updated: marked as last-resort, emits `event_find_capture_video_type_scan` warning on match.

### `src/shitbox/events/storage.py` (commit `ed95da1`)

- New `update_event_poster(event_id, poster_path)` method. Reads the on-disk event JSON, patches `poster_path` and `poster_url`, writes back atomically.

### `src/shitbox/capture/title_card.py` (commit `cf36fb1`)

- Added module-scope `AU_STATE_ABBREVIATIONS: List[Tuple[str, str]]` — 8 entries, longest-first (ACT, NT, WA, SA, NSW, QLD, TAS, VIC).
- Added `_abbreviate_au_states(place: str) -> str`. Word-boundary regex via `re.escape` on the long form; idempotent.
- Added `_fit_hero_to_canvas(draw, text, font_path, max_size=FONT_HERO)`. Shrinks 140 → 130 → 120 → 110 → 100 in 10pt steps; falls through to char-truncation with `...` suffix at 100pt floor. `SAFE_MARGIN_PX = 60` each side; safe width 1160 of 1280.
- `_resolve_strings`: abbreviation applied before `_truncate(..., MAX_PLACE_CHARS)`.
- `_compose_png`: `_fit_hero_to_canvas` picks the font per render; removed the constant `f_hero = _font(FONT_DISPLAY, FONT_HERO)` allocation.
- `_compose_png`: date line now `datetime.fromtimestamp(start_time).astimezone()` with `strftime("%d %b %Y  %H:%M %Z")`. `timezone` import dropped.

### `src/shitbox/capture/ring_buffer.py` (commit `d209956`)

- `_cleanup_pending_slates` rewritten. Old body tried `mtime_ok AND id_ok`; `save_id_from_name` and `id_ok` gone. New body: any file with `mtime < _process_start_time` is removed. Directory-not-found and per-entry `OSError` still tolerated silently. `pending_slates_swept` log kwarg preserved (info + debug).

### `tests/test_engine_late_update_poster.py` (created, commit `120d1bc`)

- 4 tests — late-update happy path delivers `poster_url`, late-update under `_event_paths_lock` is atomic pop+rename+update, missing event_id surfaces `event_video_update_orphan`, MP4 type-scan is NOT used in the late branch.

### `tests/test_title_card_overflow_and_tz.py` (created, commit `cf36fb1`)

- 16 tests: 11 parametrised AU state abbreviations (NSW, WA, SA, VIC, QLD, TAS, NT, ACT + 3 pass-through), idempotence, longest-first map-invariant, long name fits safe width, extreme-length ellipsis truncation, local-TZ date string.

### `tests/test_ring_buffer_slate.py` (modified, commit `0edbe47`)

- `test_cleanup_pending_slates_removes_old_files` rewritten against real startup state. `_save_counter = 0`. Asserts numeric orphan `3.png` (old mtime) IS removed, in-run `4.png` (new mtime) is kept, non-numeric `junk.png` (old mtime) IS removed.

## Gaps Closed

### G-01 — Late-update poster delivery

**Symptom:** PNGs stayed in `pending_slates/`; `events.json` never gained `poster_url`.

**Root cause:** `_on_video_complete` had no late-update branch. `_check_post_captures` was the only site that consumed `_event_poster_paths`, but on this Pi `save_event` fires after video completion, not before.

**Fix:** LATE branch added to `_on_video_complete`; lock held for the full pop-rename-update window.

**Evidence:**
- `tests/test_engine_late_update_poster.py::test_late_update_delivers_poster_url`
- `tests/test_engine_late_update_poster.py::test_late_update_is_atomic_under_lock`
- `tests/test_engine_late_update_poster.py::test_late_update_missing_event_id_logs_orphan`

### G-02 — Slate overflow

**Symptom:** `"Narellan, New South Wales"` hero at 140pt overflowed 1280px canvas.

**Fix:** Abbreviation map pre-truncation (`Narellan, NSW`) + measure-and-shrink fit at 10pt steps down to 100pt floor with ellipsis truncation fallback.

**Evidence:**
- `tests/test_title_card_overflow_and_tz.py::test_au_state_abbreviation` — 11 parametrised cases
- `tests/test_title_card_overflow_and_tz.py::test_au_state_abbreviation_idempotent`
- `tests/test_title_card_overflow_and_tz.py::test_au_state_abbreviation_longest_first`
- `tests/test_title_card_overflow_and_tz.py::test_long_place_name_fits_safe_width`
- `tests/test_title_card_overflow_and_tz.py::test_extremely_long_unabbreviated_string_ellipsis_truncates`

### G-03 — Local TZ render

**Symptom:** Slate read `04:25 UTC` instead of the human-useful `14:25 AEST`.

**Fix:** `datetime.fromtimestamp(ts).astimezone()` + `strftime("%d %b %Y  %H:%M %Z")`. System TZ is Australia/Sydney on the Pi.

**Evidence:**
- `tests/test_title_card_overflow_and_tz.py::test_local_tz_in_slate_date` — forces `TZ=Australia/Sydney` via `monkeypatch` + `time.tzset()`, asserts `AEST` or `AEDT` in output, asserts no `UTC`, asserts `14:25` for 04:25 UTC input.

### G-04 — Sweep guard fix

**Symptom:** Orphan PNGs from crashed prior runs accumulated in `pending_slates/`.

**Root cause:** AND-guard required `save_id < _save_counter`; at startup `_save_counter = 0`, so no numeric filename could ever satisfy the check.

**Fix:** Sweep is purely `mtime < _process_start_time`. `save_event` cannot fire before `start()` returns, so mtime alone is correctness-complete.

**Evidence:**
- `tests/test_ring_buffer_slate.py::test_cleanup_pending_slates_removes_old_files` — now pins real startup state with `_save_counter = 0` and asserts numeric orphans DO get removed.

### G-05 — event_id-strict pairing

**Symptom:** `_find_capture_video` type-scan could pick up MP4s from a prior session.

**Fix:** Late branch refuses to use type-scan. Lookup keys strictly on `event_id` from `_event_video_paths` / `_event_poster_paths`. `_find_capture_video` emits `event_find_capture_video_type_scan` warning when it does match, so cross-session pickups show in the trace.

**Evidence:**
- `tests/test_engine_late_update_poster.py::test_late_update_does_not_use_type_scan` — asserts the late branch never calls `_find_capture_video` even when `_event_video_paths` is empty.

## On-Device UAT Handoff

All six items from `26-VERIFICATION.md` require re-running on the Pi against the new build. The previous UAT run was against the pre-26-06 build, so every item is effectively unverified against the fixes shipped here. Item 1 is the critical re-run for G-01 / G-05; item 2 is the visual check for G-02 / G-03.

1. **Trigger a manual capture (SIGUSR1 or GPIO button).** Verify `<event>_poster.png` exists in `/var/lib/shitbox/captures/<date>/` alongside the MP4, and that the generated `events.json` entry carries a `poster_url` field pointing to `/captures/<date>/<base>_poster.png`. This is the direct G-01 / G-05 regression guard.

2. **Play back a saved event MP4.** Confirm the sequence intro → 3s location slate → event footage, with the slate showing place name (or whimsy), date/time in **AEST/AEDT** (not UTC — this is the G-03 check), coords, event badge (except on manual), and driver credit. The `Narellan, New South Wales` case from the original UAT should now render as `Narellan, NSW` and fit the canvas (G-02 check).

3. **Trigger an event in a GPS-unlocked area (or with GPS disabled).** Verify the slate uses a whimsy line from the config pool and omits the coord row.

4. **Trigger a manual/button capture.** Confirm the slate renders with no event-type badge, with the driver credit in the balanced position.

5. **Simulate or trigger a ROLLOVER event.** Confirm the slate's badge renders with diagonal black hazard stripes over the red `#e74c3c` background.

6. **Flip `config.capture.title_card.enabled: false`, restart the service, trigger a capture.** Confirm the MP4 plays back as intro → footage (no slate) AND the resulting events.json entry has no `poster_url`.

## Re-verification Pointer

`/gsd-verify-phase 26` should now pass its automated suite (pytest green, ruff clean on new code, mypy clean on new code). UAT items 1–6 above still need re-running on the Pi before phase 26 closes.

## Verification Results

- **pytest full non-hardware suite:** 471 passed, 1 skipped (hardware-gated). Comfortably above the ≥454 target.
- **Ruff on plan-26-06 code paths:** clean. Pre-existing E501 lines in `src/shitbox/events/engine.py` (lines 627, 628, 995, 1040, 1041, 1863 — from April 9 / April 11 commits) are pre-existing, out of scope per the deviation-rules scope boundary.
- **Mypy on modified source files:** clean on `title_card.py`, `storage.py`, `ring_buffer.py`. Pre-existing errors in `engine.py` (lines 829, 976, 1142, 1184, 2402, 2570) are pre-existing and out of scope.

## Deviations from Plan

None — plan executed exactly as written. The RED → GREEN atomic commit pattern was held for each of Tasks 1, 2, 3. Task 4 is the verification + summary task and produces no code changes.

## Deferred Issues

None blocking. Pre-existing ruff / mypy debt in `engine.py` (6 E501 + 6 mypy errors) and `tests/test_ring_buffer_slate.py` (6 ruff errors — F401, E501, F841 from pre-26-06 commits) is logged for a future hygiene pass but not in scope for this plan.

## Self-Check: PASSED

- Created files exist:
  - `tests/test_engine_late_update_poster.py` (4 tests, all green)
  - `tests/test_title_card_overflow_and_tz.py` (16 tests, all green)
- Modified files exist and contain the expected changes (verified via pytest green + acceptance-criteria greps).
- Commits on the branch above base `614d87a`:
  - `7dc5f02` test(26-06): add failing tests for G-02 slate overflow fit and G-03 local TZ
  - `cf36fb1` feat(26-06): slate overflow fit + local TZ render (G-02, G-03)
  - `0edbe47` test(26-06): RED — pin G-04 sweep against real startup state
  - `d209956` fix(26-06): _cleanup_pending_slates sweeps purely on mtime (G-04)
  - (plus the task 1 commits that were merged back before this executor started: `120d1bc`, `ed95da1`, `614d87a`)
