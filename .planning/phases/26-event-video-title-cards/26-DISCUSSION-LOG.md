# Phase 26: Event Video Title Cards - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 26-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-23
**Phase:** 26-event-video-title-cards
**Areas discussed:** Timing & transition, Visual & typography, Fallback behaviour, Integration & config, Poster reuse (bonus)

---

## Timing & transition

### Q: Default card duration on-screen?

| Option | Description | Selected |
|--------|-------------|----------|
| 3.0s | Long enough to read place + date + event badge without feeling padded. Handoff default. | ✓ |
| 2.0s | Tighter — good for viewers who already know the context. | |
| 4.0s | More cinematic breathing room. Feels slower in short clips. | |

**User's choice:** 3.0s

### Q: Transition between intro → card → footage?

| Option | Description | Selected |
|--------|-------------|----------|
| Hard cut | Simplest pipeline. PNG → ffmpeg loop → TS → concat demuxer. Matches existing intro→buffer behaviour. | ✓ |
| Fade (in-out, ~0.3s each end) | Needs ffmpeg xfade filter — complicates the concat demuxer approach. Real added code. | |
| Fade-to-black bookends baked into PNG sequence | Middle ground via Pillow alpha animation. Per-frame rendering instead of single-PNG loop. | |

**User's choice:** Hard cut

### Q: When the total saved clip is very short (e.g. a 5s quick event), should the card still appear?

| Option | Description | Selected |
|--------|-------------|----------|
| Always show | Simpler, consistent. A 3s card in front of a 5s clip is still watchable. | ✓ |
| Skip if clip < 10s | Respects the data but adds a config knob for an edge case. | |
| Skip only for manual/boot events | Really a fallback-behaviour concern, not timing. | |

**User's choice:** Always show

---

## Visual & typography

### Q: Font family for the slate?

| Option | Description | Selected |
|--------|-------------|----------|
| DejaVu Sans + Mono | Matches existing HUD overlay (`overlay.py:110-111`). Already on the Pi. Zero new deps. | ✓ |
| Ship a TTF (Inter + IBM Plex Mono) | Adds ~500KB of TTFs to assets; nicer typography. | |
| Different pairing for slate vs HUD | Risks disjointed look; more design work. | |

**User's choice:** DejaVu Sans + Mono

### Q: Slate composition — what's on the card and how's it stacked?

| Option | Description | Selected |
|--------|-------------|----------|
| Place big / date+coords stacked / badge bottom-left / logo bottom-right | Typography-led, documentary-style location slate. | ✓ |
| Centered stack / event badge hero | Event type as the biggest element, feels like a sports graphic. | |
| Left-aligned news-style / colour accent bar | Event-colour vertical bar down the left edge, editorial feel. | |

**User's choice:** Place big / date+coords stacked / badge bottom-left / logo bottom-right
**Notes:** "Yes to the layout but we should parse the event type to be more human readable.
There are only a few, so a lookup table would solve it here (and maybe in other places)" —
captured as D-08 (shared `labels.py` helper).

### Q: ROLLOVER badge colour (new event type, not in the existing palette)?

| Option | Description | Selected |
|--------|-------------|----------|
| #ff8000 orange | Sits between HIGH_G red and BIG_CORNER amber. Reads as 'safety alert'. | |
| #b51f50 crimson/magenta | Beyond HIGH_G on the red spectrum. Risk: close to HARD_BRAKE `#f85149` at small sizes. | |
| #e74c3c with black diagonal hazard stripes | Unambiguously a rollover. More Pillow work for a rarely-rendered badge. | ✓ |

**User's choice:** #e74c3c with black diagonal stripes

### Q: Proposed human-readable event label map — any changes before it's locked?

| Option | Description | Selected |
|--------|-------------|----------|
| Use this mapping | HARD_BRAKE→'Hard Brake', BIG_CORNER→'Big Corner', HIGH_G→'High G', ROUGH_ROAD→'Rough Road', MANUAL/BUTTON→'Manual Capture', BOOT→'System Start', ROLLOVER→'Rollover'. Helper in `src/shitbox/events/labels.py`. | ✓ |
| Same mapping but in `storage/events.py` | Co-locate with EventType enum. Couples presentation to data model. | |
| Let me edit the mapping | Workshop the labels together. | |

**User's choice:** Use this mapping

---

## Fallback behaviour

### Q: No GPS lock at save time — what does the slate show for location?

| Option | Description | Selected |
|--------|-------------|----------|
| Skip location block entirely | Slate degrades: place + coords lines absent. Date + event badge still appear. | |
| Show 'LOCATION UNKNOWN' | Explicit placeholder, a bit clinical. | |
| Use last-known GPS position | `gps_state` tracks last-known, but can stamp a wildly wrong place. | |

**User's choice:** (Other) "Come on — we need whimsy. Here be dragons? Who knows, we were lost?"
**Notes:** Re-framed and expanded into a rotating whimsy pool. See follow-up question and D-09.

### Q: No-GPS whimsy pool — rotating line when we don't know where we are?

| Option | Description | Selected |
|--------|-------------|----------|
| Rotating pool: 'Here be dragons', 'GPS off having a lie down', 'Somewhere between A and B', 'The map ends here', 'Lost, but enthusiastic' | One picked per card. Renders as a place-name substitute. | ✓ |
| One fixed line | Consistent but stops being funny after the 30th event. | |
| Let me write the pool | User supplies the list. | |

**User's choice:** Use the suggested rotation (YAML-overridable via `whimsy_lines`)

### Q: GPS lock present but reverse_geocoder returns nothing (rare but possible)?

| Option | Description | Selected |
|--------|-------------|----------|
| Show coords only | `-20.7256, 139.4927` on the mono row, place-name row skipped. | ✓ |
| Show coords + nearest-country name | Risk: 'Australia' on every card is noise. | |
| Skip location block entirely | Date + badge only. | |

**User's choice:** Show coords only

### Q: Event badge for manual/button-press captures (no detected event type)?

| Option | Description | Selected |
|--------|-------------|----------|
| 'Manual Capture' in MANUAL green | Treats button-press as a first-class event. | |
| No badge for manual captures | Slate shows place + date, badge slot empty. | ✓ |
| 'Driver Flag' label on MANUAL green | Reframes as crew action. | |

**User's choice:** No badge for manual captures
**Notes:** "Ohhhh, could we include the driver in the panel if we have one defined?
And yes, no badge for manual captures" — led to follow-up on driver credit.

### Q: Driver name on the slate — when?

| Option | Description | Selected |
|--------|-------------|----------|
| Always show when a driver is defined | Driver line on every slate (manual or event-triggered). | ✓ |
| Manual captures only | Badge slot becomes driver credit for manual captures only. | |
| Never — slate stays place/date/event only | Cleaner but driver data lost. | |

**User's choice:** Always show when a driver is defined

---

## Integration & config

### Q: Where does the slate sit in the concat sequence?

| Option | Description | Selected |
|--------|-------------|----------|
| Intro → Slate → Buffer | Slate just before the footage the viewer cares about. | ✓ |
| Slate → Intro → Buffer | Card up front, before branding. | |
| Intro → Buffer (slate overlaid on first ~3s of buffer) | filter_complex path — the one we're trying to avoid. | |

**User's choice:** Intro → Slate → Buffer

### Q: PiP sync-offset impact — adding ~3s of slate before buffer shifts `total_offset` in the PiP filter chain (ring_buffer.py:1284+). How to handle?

| Option | Description | Selected |
|--------|-------------|----------|
| Fold slate into front-stream concat only; PiP `setpts` += slate_duration | Single-line extension of the existing offset. Cabin PiP invisible during slate. | ✓ |
| Render the PiP with a matching black/slate hold | Both streams get 3s prepended. More work, no win. | |
| Skip PiP for the slate window | Same thing as option 1, differently framed. | |

**User's choice:** Fold slate into front-stream concat only

### Q: Config knobs to expose in `config/config.yaml` under `capture.title_card`?

| Option | Description | Selected |
|--------|-------------|----------|
| enabled: true/false | Master switch. | ✓ |
| duration_seconds: 3.0 | Override the default card duration. | ✓ |
| show_driver: true/false | Disable the driver line. | ✓ |
| whimsy_lines: [list] | Override the no-GPS whimsy pool. | ✓ |

**User's choice:** All four

---

## Poster reuse (bonus)

### Q: Slate doubles as website poster — what's the scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Save slate PNG next to MP4, poster field in events.json | One-plan addition on top of the slate work. Website falls back to intro-poster when absent. | ✓ |
| Slate only, website stays on intro-poster | Keep scope tight; poster wiring as a follow-up. | |
| Slate + website + retroactive backfill for existing events | Scope creep — adds one-shot backfill script with stale-GPS questions. | |

**User's choice:** Save slate PNG next to MP4, poster field in events.json
**Notes:** Prompted by user's late question — "Is it possible to use the title card as the
'preview' image on the website? Currently they're all just the first frame of the intro
video." Natural byproduct of rendering the PNG anyway.

---

## Claude's Discretion

- Exact Pillow typography metrics (kerning, leading, precise pixel positions)
- Place-name truncation / line-wrap rules for very long names
- File naming / logging keys for the slate render path
- Whether to cache whimsy-pool selection per event (probably not)
- Exact location of `labels.py` (events vs storage vs utils)
- Testing strategy (golden-image vs property-based) — planner to resolve

## Deferred Ideas

- Retroactive poster backfill for already-captured events
- Fade / xfade transitions (rejected in favour of hard cut)
- Website-side consumption of `poster_path` (separate home-ops repo, separate phase)
- Place-name typography tweaks for very long names
