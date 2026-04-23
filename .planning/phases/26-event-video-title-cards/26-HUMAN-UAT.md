---
status: gaps_found
phase: 26-event-video-title-cards
source: [26-VERIFICATION.md]
started: 2026-04-23T12:00:00Z
updated: 2026-04-23T14:45:00Z
---

## Current Test

[testing complete — gaps recorded]

## Tests

### 1. Manual capture lands poster alongside MP4; events.json carries poster_url
expected: The per-day captures dir contains both `<base>.mp4` and `<base>_poster.png`; events.json contains `poster_url` for that event
result: fail
evidence: On-device boot and manual captures at 14:27 / 14:31 produced MP4s in `/var/lib/shitbox/captures/2026-04-23/` but no corresponding `<base>_poster.png`. PNGs left stranded in `/var/lib/shitbox/video_buffer/pending_slates/` (1.png, 2.png). events.json entries for these events have no `poster_url`. See gap G-01.

### 2. Playback sequence intro → 3s slate → footage with full slate composition
expected: The slate appears for ~3s between intro and live footage showing place name, date/time, coords, event badge, and driver credit
result: pass_with_issues
evidence: MP4 duration 70.8s = intro 7.97s + slate 3.0s + clip 59.97s. Slate visible on playback after browser cache refresh (initial viewing caught a cached copy). Composition shows all fields. Issues visible on the frame: place name "Narellan, New South Wales" overflows the 1280px canvas (clipped both ends) — see G-02. Time stamp renders in UTC ("04:25 UTC") not local — see G-03.

### 3. No-GPS capture uses whimsy line and omits coord row
expected: Slate hero shows one of the whimsy lines; no coord row
result: pending
evidence: Not tested on this run — GPS had a lock at Narellan throughout testing.

### 4. Manual/button capture: slate has no badge, driver credit present
expected: No coloured badge in bottom-left; driver credit visible
result: pending
evidence: Manual capture was triggered but the playback frame checked was from the BOOT event (System Start badge visible). Manual-capture slate composition not visually confirmed.

### 5. ROLLOVER event renders badge with diagonal hazard stripes
expected: Red badge with ~30% alpha black diagonal stripes at 45°
result: pending
evidence: No rollover simulated on this run.

### 6. title_card.enabled=false: no slate in MP4, no poster_url in events.json
expected: MP4 plays intro → footage; events.json omits poster_url
result: pending
evidence: Not tested — master-switch smoke test deferred.

## Summary

total: 6
passed: 1
passed_with_issues: 1
failed: 1
pending: 4
skipped: 0
blocked: 0

## Gaps

### G-01: poster_url never lands in events.json; poster PNGs strand in pending_slates/
severity: high
source: test #1 + logs + code review WR-02
root_cause: |
  On this Pi's timing, the video save takes ~38s (`save_2/` → `capture_complete` at 14:31:42) while `_check_post_captures` fires `save_event` at ~25s post-event. So `save_event` runs with `poster_path=None` (nothing in `_event_poster_paths` yet). The video completes later and the engine's `event_video_updated` late-update path retroactively patches `video_url` into the saved event's JSON — but this path does NOT read from `_event_poster_paths`, does not rename the PNG to `<day_dir>/<base>_poster.png`, and does not write `poster_url`. The PNG sits forever in `pending_slates/<save_id>.png` and events.json has no `poster_url`.
evidence: |
  Logs:
    14:30:27  event_saved         manual_capture_043002_002  (save_event called — no poster available yet)
    14:31:42  video_save_complete save_2 → manual_capture_143104_001.mp4
    14:31:42  event_poster_stashed event_id 140731197926480 → pending_slates/2.png
    14:31:42  event_video_updated  links mp4 to prior event's JSON (no poster_url added)
  Disk state:
    /var/lib/shitbox/captures/2026-04-23/ has mp4s only
    /var/lib/shitbox/video_buffer/pending_slates/ has 1.png + 2.png (stranded)
fix_sketch: |
  Extend the `event_video_updated` late-update path in `src/shitbox/events/engine.py`
  to mirror the video_url patch for poster_url: pop from `_event_poster_paths` under
  `_event_paths_lock`, rename to `<day_dir>/<base>_poster.png`, update the event
  JSON and regenerate events.json. Same shape as the existing video_url update.
  Add a test that simulates `save_event-before-video-complete` (reversing the race
  order from the 26-05 integration test).

### G-02: Long place names overflow the 1280px slate canvas
severity: medium
source: test #2 (visual)
root_cause: |
  TitleCardRenderer draws the place hero at a fixed font size with no
  measure-and-fit pass. "Narellan, New South Wales" rendered wider than 1280px
  and clipped on both ends ("lan, New South V" visible).
fix_sketch: |
  Add a measure-loop in `src/shitbox/capture/title_card.py` that shrinks font
  size (or abbreviates state name to "NSW") until the rendered text fits within
  the safe-margin width. Decide: shrink-to-fit (preserves full name) vs
  abbreviate (preserves font size). Prefer shrink-to-fit to ~2 steps then
  abbreviate. Add unit test with a known-long place name.

### G-03: Slate time renders in UTC, not local time
severity: low
source: test #2 (visual)
root_cause: |
  Rendered as "23 Apr 2026  04:25 UTC" when local Narellan time was 14:25 AEST.
  D-context doesn't explicitly require local — needs a decision.
fix_sketch: |
  Decide: UTC (timezone-agnostic, good for rally travel across TZ) vs local
  (matches the driver's experience). If local: pass the Pi's local TZ into the
  renderer and strftime with %Z. If UTC: leave as-is and move to close.

### G-04: _cleanup_pending_slates sweep guard broken at startup
severity: low
source: code review WR-01
root_cause: |
  `_cleanup_pending_slates()` at `src/shitbox/capture/ring_buffer.py:1677-1710`
  uses `mtime_ok AND id_ok` where `id_ok = save_id < self._save_counter` — but
  `_save_counter == 0` at startup, so numeric orphan PNGs from crashed prior
  runs can NEVER satisfy `save_id < 0` and are never swept. Test passes only
  because it manually pre-sets `_save_counter = 10`.
fix_sketch: |
  Change guard to `mtime_ok OR id_ok` (sweep if EITHER the mtime predates the
  current process or the save_id is from an earlier session), or just `mtime_ok`
  and drop the redundant id check. Fix the test to reflect real startup state
  (counter = 0).

### G-05: event_video_updated attaches MP4 to wrong (prior) event JSON
severity: medium
source: log inspection (independent of poster work)
root_cause: |
  Log lines show:
    event_video_updated {"json": ".../boot_042549_001.json", "video": ".../boot_142635_001.mp4"}
  boot_142635 MP4 was paired with boot_042549's JSON (the previous session's boot).
  The pairing logic in the late-update path does not correctly match the most
  recent unpaired event of the same type.
evidence: |
  Logs at 14:27:13 and 14:31:42 both show MP4s paired with the previous matching
  event's JSON instead of the event that actually triggered the save.
fix_sketch: |
  Pre-26 bug, surfaced by Phase 26 testing. Audit the
  `event_video_updated` path — likely pairing on event-type without a time bound
  or event_id. Should key on `event_id` (the 140731197926480-style tag already
  present in `capture_complete` + `event_poster_stashed` logs) not event_type.
  Needs a log-replay test asserting mp4 lands on the matching event_id.

## Follow-up (out of Phase 26 scope)

- **Home-ops website consumption**: `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html:2541` hard-codes `poster="/captures/intro_poster.jpg"`. ROADMAP explicitly deferred to home-ops. Once G-01 lands and events.json has `poster_url`, a 10-line change there reads `d.poster_url || '/captures/intro_poster.jpg'` as the poster.
