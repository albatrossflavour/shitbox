---
created: 2026-04-22T10:45:00.000Z
title: Extend timelapse title card to per-capture (event) videos
area: capture
files:
  - src/shitbox/sync/timelapse_compiler.py
  - src/shitbox/capture/
  - src/shitbox/events/engine.py
---

## Context

Timelapse title card feature landed with location + date + start time reverse-geocoded from the first GPS fix of the day (see `TimelapseCompiler._generate_title_card`).

User's original intent was for **every saved capture video** (event-triggered + manual) to carry a title card, not just the daily timelapse. The current implementation only applies to the timelapse pipeline.

## Questions to answer

- Does the ring-buffer `save_capture` path have access to (or can derive) the first GPS fix + location for the triggering event?
- Should the title card reuse `_generate_title_card` as-is, or does per-capture want different content (event type, G-force, speed at trigger)?
- How much does the extra ffmpeg concat add to capture finalisation time? Capture saves are already the slow path on the Pi.
- Render-time cost: per-capture title cards means a `subprocess.run` ffmpeg invocation per save. Timelapse is once a day; captures can be dozens per drive.

## Not blocking

Ship current timelapse title card now; revisit per-capture scope separately.
