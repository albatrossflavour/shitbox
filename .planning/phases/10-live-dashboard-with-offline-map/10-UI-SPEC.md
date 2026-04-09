---
phase: 10
slug: live-dashboard-with-offline-map
status: draft
shadcn_initialized: false
preset: none
created: 2026-04-09
---

# Phase 10 — UI Design Contract

> Visual and interaction contract for the in-car live dashboard. Glanceable at speed, readable on a phone, dark theme matching shit-of-theseus.com. No build step — all assets vendored.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (no shadcn — Python/FastAPI project, single static HTML file) |
| Preset | not applicable |
| Component library | none — plain HTML + Alpine.js directives |
| Icon library | inline SVG only (no icon font, no runtime fetch) |
| Font | system UI stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` — zero network, works offline, reads well on the Pi's Chromium kiosk |

Styling: **Tailwind CSS precompiled to a single static file** in `dashboard/static/vendor/tailwind.css`. No CDN, no JIT, no build step at runtime. The CSS file is generated once against the final `index.html` and committed. (Source: CONTEXT D-10, discretion on "Tailwind config approach".)

---

## Spacing Scale

Multiples of 4, consistent with Tailwind defaults. In-car use biases toward the larger end of the scale — nothing tighter than `sm` inside interactive regions.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon-to-label gaps, badge inner padding |
| sm | 8px | Compact element spacing inside cards |
| md | 16px | Default gap between tiles, card inner padding |
| lg | 24px | Card-to-card gaps, section padding |
| xl | 32px | Top bar vertical padding, main region gutters |
| 2xl | 48px | Page-edge gutters on desktop/kiosk |
| 3xl | 64px | Reserved — not used in this phase |

Exceptions:

- G-force gauge is a fixed square region sized by viewport (`min(40vh, 40vw)`), not on the token grid
- Event strip row height is `56px` (14 × 4) so six to ten rows remain thumb-reachable on mobile without scroll fatigue

---

## Typography

The dashboard is read from the driver's seat of a moving rally car. Body is large by web standards. Only two weights — regular for everything, semibold for the numeric readouts that matter at a glance.

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body / labels | 16px | 400 (regular) | 1.5 |
| Section heading | 20px | 600 (semibold) | 1.2 |
| Numeric readout (speed, temps, G values) | 48px | 600 (semibold) | 1.0 |
| Hero speed display | 96px | 600 (semibold) | 1.0 |

Numeric readouts use tabular figures (`font-variant-numeric: tabular-nums`) so digits don't jitter as values change. Units (`km/h`, `°C`, `g`) render at 16px regular next to the value, not inside it.

---

## Color

Dark theme, GitHub-inspired, identical palette to shit-of-theseus.com so the two screens feel like the same project. High contrast on all text (white on near-black clears WCAG AA comfortably).

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#0d1117` | Page background, map container |
| Secondary (30%) | `#161b22` | Cards, tiles, top bar, event strip background |
| Tertiary border | `#21262d` | Card borders, dividers (not a design-token "color", just structure) |
| Text primary | `#e6edf3` | Body text, labels, numeric readouts |
| Text muted | `#8b949e` | Secondary labels, units, timestamps |
| Accent (10%) | `#1f6feb` | Reserved for: live position dot on map, "sync online" status pip, current-selection highlight on event strip |
| Destructive / alert | `#da3633` | Reserved for: GPS NO FIX badge, sync offline badge, stale-data indicator |

Accent reserved for: map live-position dot, Prometheus sync "online" pip, selected event row highlight. **Not** used for body text, icons, hover states, or decoration.

Event type colours (mirrored from shit-of-theseus.com, frontend-only mapping, applied only to event badges in the bottom strip and map markers):

| Event | Hex |
|-------|-----|
| HIGH_G | `#da3633` |
| HARD_BRAKE | `#f85149` |
| BIG_CORNER | `#d29922` |
| ROUGH_ROAD | `#8957e5` |
| MANUAL / BUTTON | `#238636` |
| BOOT | `#1f6feb` |

These are data-carrying colours, not UI accents — the 10% rule applies to interface accent only. Event badges are the data.

---

## Copywriting Contract

No buttons in this phase (read-only dashboard). "CTA" below is really the single active interaction: tap-to-dismiss banner when data goes stale.

| Element | Copy |
|---------|------|
| Primary CTA (stale data banner dismiss) | `Dismiss` |
| Empty state heading (no GPS fix yet) | `Waiting for GPS` |
| Empty state body (no GPS fix yet) | `No fix yet. Map will centre once the GPS locks on.` |
| Empty state heading (no events yet) | `No events yet` |
| Empty state body (no events yet) | `Events show up here as they happen. Drive something.` |
| Error state — SSE disconnected | `Live feed dropped. Reconnecting…` (auto-retries, no user action) |
| Error state — tile missing | silent — Leaflet shows a grey square, no toast |
| Error state — sync offline | badge reads `SYNC OFFLINE` in destructive red, no modal |
| Destructive confirmation | not applicable — no destructive actions in this phase |
| GPS fix badge (no fix) | `NO FIX` |
| GPS fix badge (2D) | `2D · {sats} sats` |
| GPS fix badge (3D) | `3D · {sats} sats · HDOP {x.x}` |
| Sync status (online) | `SYNC OK` |
| Sync status (offline) | `SYNC OFFLINE` |
| Sync status (backlog) | `SYNC {n} pending` |
| Driver placeholder | `Driver: —` (Phase 11 replaces with real data) |
| Map follow resumed toast | none — silent auto-recentre after 10s idle |

Voice: short, blunt, no marketing. Units always spelled out (`km/h` not `kph`). Temperatures with degree symbol (`°C`). G values to one decimal (`1.4 g`). Speed as integer (`87 km/h`).

---

## Layout Contract

Locked by CONTEXT D-11, recorded here for the planner and executor.

**Desktop / kiosk (≥768px):**

```
┌────────────────────────────────────────────────────────────┐
│ TOP BAR  GPS · SPEED · DRIVER · SYNC                       │  h: 80px
├───────────────┬────────────────────────────────────────────┤
│ G-GAUGE       │                                            │
│ (square)      │               MAP                          │
│               │        (offline MBTiles)                   │
├───────────────┤                                            │
│ IMU TEMP      │                                            │
│ SoC TEMP      │                                            │
│ (tiles)       │                                            │
├───────────────┴────────────────────────────────────────────┤
│ EVENT STRIP  last 10, newest left, scrolls horizontally    │  h: 88px
└────────────────────────────────────────────────────────────┘
```

**Mobile (<768px):** single column — top bar, speed hero, G-gauge, temp tiles, map (40vh), event strip. Reflow via Tailwind `md:` breakpoint.

**Chromium kiosk target:** the Pi's screen runs at its native resolution in fullscreen Chromium. Layout must work at anything ≥1024×600 without horizontal scroll.

---

## Interaction Contract

- **Map auto-recentre:** after 10s of no `dragstart`/`zoomstart`, map smooth-pans back to live position. Timer resets on any user interaction. (D-20)
- **G-gauge auto-range:** scale grows to peak, decays back over 30-60s. Visual priority only — capture path unaffected. (D-13, D-14)
- **SSE reconnect:** automatic, silent, handled by the browser's EventSource. Stale indicator appears if fast stream has no message for >2s.
- **Event strip:** new events slide in from the left with a brief highlight pulse (200ms, accent colour), then settle. No auto-scroll — always shows newest 10.
- **No auth, no login, no modals, no settings page.** Trust the rally wifi. (D-05, "most people won't be wankers")

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| none | — | not applicable — no component registry in use |

All frontend assets (Alpine.js, Tailwind-compiled CSS, Leaflet) are vendored into `dashboard/static/vendor/` with pinned versions checked into the repo. Vendor vetting happens at the planner/executor stage when versions are pinned — record SHA256 of each vendored file in the plan. No runtime CDN fetch, so no supply-chain surface at runtime. (D-10)

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
