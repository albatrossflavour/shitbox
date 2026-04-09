# Phase 10: Live Dashboard with offline map - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-09
**Phase:** 10-live-dashboard-with-offline-map
**Areas discussed:** Server architecture, transport, frontend stack, layout, offline maps, G-gauge behaviour, follow behaviour, tile corridor, event scroll length, module layout, SSE update rate

---

## Server architecture (in-process vs separate)

| Option | Description | Selected |
|--------|-------------|----------|
| In-process FastAPI in daemon thread | Web runs inside `UnifiedEngine`, shares memory, single systemd unit. Risk: stability/perf must be carefully isolated from capture path. | ✓ |
| Separate process | Cleaner isolation, web survives daemon restarts. Cost: IPC, more moving parts. | |

**User's choice:** In-process, conditional on stability — "data capture trumps data display".
**Notes:** Mitigations agreed: own daemon thread, lock-free snapshot, hard client cap, web exceptions never propagate to capture path.

---

## Live data transport

| Option | Description | Selected |
|--------|-------------|----------|
| WebSocket | Bidirectional, good for future writes. More framing/keepalive bookkeeping. | |
| SSE | One-way, auto-reconnect, simpler. Bidirectional handled separately by POST. | ✓ |

**User's choice:** "Whatever you think as long as it's reliable" → Claude chose SSE.
**Notes:** Phase 11 writes are infrequent (refuel, blog) and tolerate plain POST, so SSE's one-way limitation is fine.

---

## Frontend stack

| Option | Description | Selected |
|--------|-------------|----------|
| Plain HTML/JS (no framework) | Zero deps. Reactive UI gets painful. | |
| Alpine + Tailwind + Leaflet (vendored) | No build step, reactive enough, mobile-friendly, matches shit-of-theseus.com vibe. | ✓ |
| Full SPA (Svelte/Vue/React + Vite) | Best DX, build step on/off Pi. | |

**User's choice:** "Your choice" → Claude chose Alpine + Tailwind + Leaflet, all vendored.

---

## SSE update rate

| Option | Description | Selected |
|--------|-------------|----------|
| 1 Hz everything | Light, choppy gauge | |
| 5 Hz everything | Medium | |
| 10 Hz everything | Smooth, ~10x browser load | |
| Tiered (10 Hz fast / 1 Hz slow / push events) | Speed/G smooth, slow data slow, events instant | ✓ |

**User's choice:** "10 Hz? Way faster than I thought! Speed/G can be higher, happy with the rest being whatever timing makes it easy on the system."
**Notes:** Tiered streams adopted: `/sse/fast` 10 Hz for speed+G, `/sse/slow` 1 Hz for everything else, `/sse/events` push-on-detect.

---

## G-force gauge scale

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed (e.g. ±2g clamped) | Reads honestly, doesn't lie about peaks | |
| Auto-ranging | Rescales to peak, "looks cool" but lies | ✓ |

**User's choice:** Auto — "we don't care about accuracy for this display piece, we want it looking cool! (just for this though)"
**Notes:** Capture/storage paths still use real values. Display-only auto-range with slow decay so the gauge doesn't stay zoomed out forever.

---

## Map follow behaviour

| Option | Description | Selected |
|--------|-------------|----------|
| Always centre on vehicle | Glance-friendly, fights user when panning | |
| Free-pan + manual recentre button | Stable, requires interaction to recover | |
| Auto-recentre after N seconds idle | Stable, doesn't fight user, recovers automatically | ✓ |

**User's choice:** "Your call, whatever is more stable and easy" → Claude chose auto-recentre after 10 s idle.

---

## Tile corridor / zoom range

| Option | Description | Selected |
|--------|-------------|----------|
| Tight (5 km, z 8–12) | Small, risks falling off on detours | |
| Medium (10 km, z 6–13) | Balanced | |
| Generous (20 km, z 5–15) | Larger pre-download but covers detours and zooms in further | ✓ |

**User's choice:** "We've got 500 GB disk space..." → generous.

---

## Event scroll length

| Option | Description | Selected |
|--------|-------------|----------|
| Last 10 | Compact, mobile-friendly | ✓ |
| Last 50 | More history, bigger DOM | |
| Whole session | Most context, biggest DOM | |

**User's choice:** Last 10.

---

## Module layout

| Option | Description | Selected |
|--------|-------------|----------|
| `src/shitbox/web/` | Generic | |
| `src/shitbox/dashboard/` | Specific to the dashboard product | ✓ |

**User's choice:** "dashboard"

---

## Claude's Discretion

- Exact uvicorn config (workers, log integration with structlog)
- Snapshot dict update mechanism (CoW vs short lock)
- Breadcrumb point count and decimation
- G-gauge auto-range decay curve and timing
- Tailwind packaging approach (precompiled CSS file vs alternative)
- SSE keepalive interval
- Vendored frontend library versions

## Deferred Ideas

- Driver swaps, refuel logging, blog posts, breakdown counts (Phase 11)
- Voltage / INA219 display
- Self-rendered tiles via tilemaker
- Live video preview embedded in the dashboard
