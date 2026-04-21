---
phase: 21
slug: hardware-inventory-and-graceful-degradation
status: draft
shadcn_initialized: false
preset: none
created: 2026-04-21
---

# Phase 21 — UI Design Contract

> Visual and interaction contract for the three Pi-local UI surfaces touched by hardware inventory + graceful degradation: OLED status line, kiosk dashboard hardware panel, and Piper TTS copy. Read-only surfaces, no interactive controls, no website changes.

---

## Scope Recap

| Surface | Mechanism | Refresh cadence | Source of truth |
|---------|-----------|-----------------|-----------------|
| OLED (SSD1306 128×64) | `OLEDDisplayService._render()` line 3 repurpose | `oled.update_interval_seconds` (current default, 1 Hz class) | `hw_state.snapshot()` |
| Dashboard hardware panel | New panel in `src/shitbox/dashboard/static/index.html`, fed by `/sse/slow` payload field `hardware[]` | 1 Hz slow stream | `hw_state.snapshot()` serialised in `sse.py` |
| TTS (Piper) | New `speak_hardware_missing` / `_restored` helpers in `capture/speaker.py`, driven by `HardwareSupervisor` | Per-tier cadence (see Copywriting) | Supervisor tick |

Out-of-scope surfaces (explicitly deferred per CONTEXT.md §Deferred and REQUIREMENTS.md traceability): shit-of-theseus.com "what's online" widget, `hardware.json` sync generator, `events.json` HW fields, Prometheus `up` gauge.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (shadcn not applicable — plain HTML/CSS/Alpine kiosk + bitmap-font OLED + Piper WAV) |
| Preset | not applicable |
| Component library | none (Alpine.js directives + hand-rolled CSS in `dashboard/static/index.html`; SSD1306 + PIL on OLED) |
| Icon library | none — status uses filled/hollow glyphs (●, ○) on OLED and CSS-coloured badges on dashboard |
| Font (dashboard) | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` (system stack — matches shipped kiosk, source: `index.html` line 10) |
| Font (OLED) | `ImageFont.load_default()` — PIL 5×7 bitmap, fixed at 8px row metrics (source: `oled.py` line 55) |

**Design system state:** pre-populated from existing codebase (`index.html` line 10, `oled.py` line 55). `components.json` absent (not a React project). shadcn gate: not applicable.

---

## Spacing Scale

Declared values (must be multiples of 4):

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Card inner gaps (`gap: 4px` in footer ticker and stat columns) |
| sm | 8px | Compact element spacing, badge padding top/bottom equivalents |
| md | 16px | Default spacing between HW rows in the panel, header padding |
| lg | 24px | Header horizontal padding, modal padding |
| xl | 32px | Reserved for section breaks (unused in hardware panel) |

**Exceptions:**
- OLED uses a 0/16/32/48 px row grid (4 lines at 16 px row spacing) — these are hardware-driven bitmap rows, not design tokens. Line 3 is at `y=32` per `oled.py`.
- Dashboard hardware panel internal row height: `28px` (to fit 4 visible rows in a 120 px card at 1024×600 kiosk). This is the one non-multiple-of-4 value and is inherited from the existing footer `.num` row rhythm at 1024×600 — noted as an exception, not a new scale value.

---

## Typography

### Dashboard hardware panel

| Role | Size | Weight | Line Height | Usage |
|------|------|--------|-------------|-------|
| Panel heading | 13px | 600 | 1.2 | "HARDWARE" card label, uppercase, letter-spacing 0.05em (matches existing `Cabin Temp` / `SoC Temp` labels, `index.html` lines 92, 96) |
| Row label | 18px | 600 | 1.3 | Device role ("IMU", "Front Cam", "Power", "GPS", "Environment") |
| Tier badge | 15px | 600 | 1.0 | Inline badge text next to the role, matches existing `.badge` rule (`index.html` line 14) |
| Last-seen meta | 13px | 400 | 1.3 | Timestamp / since-ms, in `#8b949e` grey |

Inherited from shipped kiosk: 13/15/18 are already in use; 400/600 are the only two weights in the shipped stylesheet. No new sizes introduced.

### OLED

Single font (PIL default bitmap, ~6px wide per glyph, 8px row). No size variation possible. Weight inferred through inversion (inverted = bold equivalent).

### Pre-populated from

- Dashboard font sizes verified from `src/shitbox/dashboard/static/index.html` lines 14, 92, 93, 96, 97, 104, 105, 140, 142, 144.
- OLED font constraint verified from `src/shitbox/display/oled.py` line 55.

---

## Color

Inherited from the shipped GitHub-dark kiosk theme. No new tokens introduced. All values verified from `src/shitbox/dashboard/static/index.html` lines 10-25 and the website `~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html` (CLAUDE.md §Website stack).

### Dashboard hardware panel

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#0d1117` | Kiosk page background, OLED black |
| Secondary (30%) | `#161b22` (card) + `#21262d` (card border) | Hardware panel card surface |
| Accent — critical missing (10%) | `#da3633` (red) | Red banner overlay when any `critical` device is MISSING; tier badge fill for critical-missing rows; stale-state text colour (matches shipped `.stale` and `.ev-HIGH_G`) |
| Accent — important missing | `#d29922` (amber) | Tier badge fill for `important`-missing rows; non-fix GPS status text (matches shipped `.ev-BIG_CORNER` and non-fix GPS pattern line 229) |
| Accent — degraded | `#f85149` (red, lighter) | Reserved for DEGRADED state (mid-recovery): inline text colour only, no fill, to distinguish from solid-red MISSING banner |
| Accent — present | `#238636` (green) | Tier badge fill when device is PRESENT; matches shipped `.ev-MANUAL / .ev-BUTTON` and header live dot line 74 |
| Muted | `#8b949e` (grey) | `best_effort` tier badge text, last-seen meta text, "—" when never seen |
| Text default | `#e6edf3` | Row labels |

**Accent reserved for (explicit list, no blanket use):**

- `#da3633` red — critical-tier MISSING: full-width banner across top of hardware panel, inline text on row, OLED token inversion equivalent
- `#d29922` amber — important-tier MISSING: badge fill on row only; NO banner
- `#f85149` red-light — DEGRADED state inline text colour only, for mid-recovery transitions
- `#238636` green — PRESENT badge fill on row; no other use
- `#8b949e` grey — `best_effort` badge fill, last-seen timestamps, `—` placeholders

**Destructive:** not applicable — phase has no destructive actions (panel is read-only; no retry button, no toggles, no disable).

### 60 / 30 / 10 discipline

- 60% `#0d1117` (page bg) + `#161b22` (card bg) = dominant dark surface
- 30% `#21262d` (borders) + `#8b949e` (muted text) = secondary chrome
- 10% tier badges (`#da3633` / `#d29922` / `#238636`) + red banner — accent used exclusively for state communication, never for decoration

### OLED

Monochrome (white on black). Presence is communicated by:

- Glyph: `●` (filled = PRESENT) vs `○` (hollow = MISSING) next to each critical/important token
- Inversion: critical-missing tokens render with `inverted=True` (white box, black text — see `oled.py` `_draw_text` line 96)
- Roll-up count: `ENV:N/M` where N = present best_effort env devices, M = total

No colour tokens on OLED.

---

## Component Inventory

### Dashboard hardware panel

Panel location: bottom-left of kiosk main grid, sized to sit beside the event ticker footer OR as a tab-toggle on the existing layout. Planner picks exact slot; the contract is the **panel internals**, not its grid placement.

Structure (each row renders from one `hardware[]` SSE entry):

```text
┌──────────────────────────────────────────────┐
│ HARDWARE                                     │   ← panel heading, 13px/600/uppercase/#8b949e
├──────────────────────────────────────────────┤
│  ▓▓▓▓▓ CRITICAL: IMU OFFLINE  ▓▓▓▓▓         │   ← red banner, only when any critical MISSING
├──────────────────────────────────────────────┤
│ ● IMU           [critical] PRESENT     2s    │   ← row: glyph | role | tier badge | state | since
│ ○ Front Cam     [critical] MISSING    47s    │
│ ● Power         [important] PRESENT    1s    │
│ ○ GPS           [important] MISSING   12s    │
│ ● Environment   [best_effort] PRESENT  3s    │
│ 6 best_effort present / 9 declared           │   ← roll-up row, grey
└──────────────────────────────────────────────┘
```

Row composition (left to right, fixed column order, 16 px inter-column gap):

1. **State glyph** — `●` green (`#238636`) when PRESENT, `○` grey (`#8b949e`) when MISSING, `◐` amber (`#d29922`) when DEGRADED. 18 px Unicode glyph.
2. **Role label** — 18 px / weight 600, `#e6edf3`. Human-readable name from the CTA copy table (e.g. "Front Cam", not "camera_front").
3. **Tier badge** — 15 px / weight 600, using the existing `.badge` class (`padding: 2px 8px; border-radius: 4px;` from `index.html` line 14). Fill per tier: `#da3633` critical, `#d29922` important, `#8b949e` best_effort. Text `#fff` except `#000` on amber (matches existing `ev-BIG_CORNER` pattern line 17).
4. **State text** — 18 px / weight 400, colour per state (`#e6edf3` PRESENT, `#f85149` DEGRADED, `#da3633` MISSING).
5. **Since-last-seen** — 13 px / weight 400, `#8b949e`, right-aligned. Format: `Ns` (<60s), `Nm` (<60m), `Nh` (>=1h), `—` if never seen.

**Banner rule:** Red banner (`#da3633`, white text, 18 px / 600, full panel width, 8 px vertical padding) appears above the row list **only** when any `critical`-tier device is in state MISSING. Content: `CRITICAL: <ROLE> OFFLINE` (upper-case role; multiple roles comma-separated). Banner disappears as soon as the critical device flips back to PRESENT — no manual dismiss.

**best_effort roll-up row (dashboard):** single-line summary at the bottom of the list: `N best_effort present / M declared`, 13 px / 400 / `#8b949e`. Individual best_effort devices are still rendered as rows above — the roll-up is additional context, not a replacement. (OLED uses roll-up as the *only* representation; dashboard uses both per-device rows + roll-up.)

Row ordering: `critical` rows first, then `important`, then `best_effort`, within each tier alphabetical by role. Stable across re-renders — no jumping when state changes.

### OLED line 3 layout

```text
y=32  IMU● CAM● PWR● GPS●     ENV:2/3
```

Token grid (4 bytes × ~20 px each, leaves ~16 px for roll-up on the right):

- `x=0`   token 1: `IMU` + glyph — LSM6DSOX (critical). Glyph: `●` present, `○` missing. Whole token (role + glyph) renders inverted when MISSING.
- `x=32`  token 2: `CAM` + glyph — front camera (critical). Same rules.
- `x=64`  token 3: `PWR` + glyph — INA226 (important). MISSING: non-inverted but glyph `○`. (Important tier does not invert on OLED — invert is reserved for critical so the crew can distinguish at a glance.)
- `x=96`  token 4 OR roll-up: either `GPS` + glyph (important) OR roll-up `ENV:N/M`. Pick GPS at `x=96` and move roll-up to `x=116+` if width allows; otherwise drop GPS to line 1 area (the existing GPS block on line 1 already covers it, so **recommendation: drop GPS token from line 3** and use the freed space for a longer roll-up).

**Final prescribed layout (uses existing GPS on line 1 as the GPS truth):**

```text
y=32  IMU● CAM● PWR●    ENV:2/3
```

- Tokens 1-3: critical + important, 4-char width each, 8 px gap between.
- Right side `x=96`: `ENV:N/M` roll-up for best_effort I2C env devices (BME680, LIS3MDL, VEML7700). N = present, M = 3.

**Drop from old line 3:** existing `IMU`/`ENV` pair. Replaced by the above.

### Dashboard SSE payload shape (consumed by panel)

```jsonc
{
  "hardware": [
    {
      "role": "imu",               // matches manifest role
      "label": "IMU",              // human-readable, from copy table below
      "tier": "critical",          // critical | important | best_effort
      "state": "present",          // present | degraded | missing
      "last_seen": 1713661234.5,   // unix seconds, nullable (null = never)
      "since_ms": 2100             // ms since state entered, nullable
    }
    // ... one entry per declared manifest device
  ]
}
```

---

## Copywriting Contract

Human-readable role labels (used across OLED tokens where space allows, full dashboard rows, and TTS). This is the canonical mapping — planner and executor use these strings verbatim.

| Manifest role | OLED token | Dashboard label | TTS subject |
|---------------|-----------|-----------------|-------------|
| `imu` | `IMU` | IMU | "IMU" |
| `camera_front` | `CAM` | Front Cam | "front camera" |
| `power` | `PWR` | Power | "power monitor" |
| `gps` | (line 1 already) | GPS | "GPS" |
| `environment` | (in roll-up) | Environment | "environment sensor" |
| `magnetometer` | (in roll-up) | Magnetometer | "magnetometer" |
| `light` | (in roll-up) | Ambient Light | "light sensor" |
| `oled` | (n/a — self) | OLED | "OLED display" |
| `temp_exterior` | (not shown) | Exterior Probe | "exterior temp probe" |
| `temp_engine_bay` | (not shown) | Engine Bay Probe | "engine bay probe" |
| `camera_cabin` | (not shown) | Cabin Cam | "cabin camera" |
| `audio_mic` | (not shown) | USB Mic | "microphone" |
| `button` | (not shown) | Button | "button" |
| `display_hdmi` | (not shown) | HDMI | "HDMI display" |

### TTS lines (Piper pre-cached WAVs)

Pattern follows the shipped "Michael" register (direct, calm, first-person, no panic — matches `capture/speaker.py` `_CACHED_MESSAGES`).

| Event | Line |
|-------|------|
| Critical MISSING (IMU) | "Michael, I've lost the IMU. Event detection is down." |
| Critical MISSING (front cam) | "Michael, the front camera is offline. I can't record." |
| Critical RESTORED (IMU) | "IMU back with me, Michael." |
| Critical RESTORED (front cam) | "Front camera restored, Michael." |
| Important MISSING (power) | "Michael, I've lost the power monitor." |
| Important MISSING (GPS) | "Michael, I've lost GPS." |
| Important RESTORED (power) | "Power monitor back, Michael." |
| Important RESTORED (GPS) | "GPS fix restored, Michael." |
| best_effort MISSING (environment only) | "Environment sensor isn't responding, Michael." |
| best_effort RESTORED (environment only) | "Environment sensor back, Michael." |

**Cadence per CONTEXT.md D-05 (supervisor enforces, not the speaker):**

| Tier | MISSING cadence | RESTORED cadence |
|------|----------------|------------------|
| critical | Re-speak every 30 s while missing (supervisor `_last_nag` dict) | Once on transition |
| important | Once on transition | Once on transition |
| best_effort | Log-only (no TTS) — except environment (canonical acceptance case) speaks once on transition | Once on transition (environment only) |

**DEGRADED state is silent.** Mid-recovery ("I'm trying to fix the bus") is owned by the sampler's existing `speak_i2c_lockup()` — supervisor does not duplicate (Pitfall 6 in RESEARCH.md).

### Other copy

| Element | Copy |
|---------|------|
| Panel heading | `HARDWARE` (uppercase) |
| Critical banner template | `CRITICAL: <ROLE> OFFLINE` (role uppercased; multiple comma-joined: `CRITICAL: IMU, FRONT CAM OFFLINE`) |
| State text — PRESENT | `PRESENT` |
| State text — DEGRADED | `RECOVERING` (softer than "degraded" — the crew sees "it's working on it") |
| State text — MISSING | `OFFLINE` (shorter than "MISSING", matches TTS register and existing `GPS:NO FIX` pattern on OLED) |
| Never-seen timestamp | `—` (em-dash, `#8b949e`) |
| Empty state (no manifest loaded) | `No hardware manifest — check config.yaml` (single row, `#d29922` amber, 15px/400) |
| best_effort roll-up (dashboard) | `{N} best_effort present / {M} declared` |
| Primary CTA | not applicable — panel is read-only (CONTEXT.md §Out of scope) |
| Destructive confirmation | not applicable — no destructive actions |

**Style rules (copy):**

- UK spelling in code comments and dashboard labels (project global rule)
- TTS keeps the shipped "Michael, I …" opener for parity with existing messages
- No exclamation marks in TTS or dashboard copy — calm register per project voice
- Never use "error" in user-visible copy — use `OFFLINE`, `RECOVERING`, or the TTS sentence
- Don't say "retrying in 5 seconds" — the crew can't act on it and the supervisor owns the timing

---

## Interaction Contract

Read-only surface. No clicks, no drags, no keyboard. Documented explicitly so the checker, planner, and auditor don't infer hidden controls.

| Surface | User input accepted? | Notes |
|---------|---------------------|-------|
| OLED line 3 | None | Glyph / inversion state is the only output |
| Dashboard panel | None | No retry buttons, no row expand, no dismissals. Banner auto-clears on recovery |
| TTS | None — system-initiated | Existing mute behaviour (speaker `_should_alert()`) still applies |

**State transitions visible to user (Pi-local, within one SSE tick ≤ 1.1 s):**

- PRESENT → DEGRADED: glyph swaps ●→◐, state text `PRESENT`→`RECOVERING`, colour shifts default→`#f85149`. No banner. No TTS.
- PRESENT → MISSING: glyph swaps ●→○, state `PRESENT`→`OFFLINE`, colour default→`#da3633`, banner appears if critical, TTS per cadence table.
- DEGRADED → PRESENT: glyph ◐→●, row returns to default colour. RESTORED TTS fires (per tier).
- MISSING → PRESENT: glyph ○→●, banner clears if this was the last critical-missing, RESTORED TTS fires.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable |
| third-party | none | not applicable |

No npm/shadcn registries used — this is a Python + static HTML/CSS/Alpine project. No third-party block ingestion. Safety gate: not applicable.

---

## Implementation Hooks (for planner/executor, not the checker)

The contract terminates here; these are pointers to where each surface gets edited, lifted verbatim from RESEARCH.md §Component responsibilities so the executor has a single sheet.

| Surface | File to edit | What changes |
|---------|-------------|--------------|
| OLED line 3 | `src/shitbox/display/oled.py` `_render()` around lines 146-149 | Replace `IMU` / `ENV` pair with the 3-token critical/important grid + right-side `ENV:N/M` roll-up |
| Dashboard panel | `src/shitbox/dashboard/static/index.html` | Add a new card with the row structure above. Alpine binds to `hardware` array from `/sse/slow` |
| Dashboard SSE feed | `src/shitbox/dashboard/sse.py` around lines 132-150 | Add `hardware` array to the yielded slow payload per shape above |
| TTS cache | `src/shitbox/capture/speaker.py` `_CACHED_MESSAGES` dict | Add the 10 keys from the TTS table; pre-cache at `speaker.init()` |
| Banner logic | dashboard Alpine component (in `index.html`) | Computed property: any row with `tier==='critical' && state==='missing'` → render banner |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending

---

### Sources

- `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md` — all locked decisions (D-01 through D-11), criticality tiers, tier-to-visual mapping, deferred items
- `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-RESEARCH.md` — SSE payload shape, component edit points, OLED line-3 rollup recommendation, TTS wording register, pitfall-6 split of sampler vs supervisor TTS ownership
- `.planning/REQUIREMENTS.md` §HW-01..HW-05 — acceptance surface the panel/OLED/TTS must satisfy
- `src/shitbox/dashboard/static/index.html` lines 10-25, 92-127, 140-144 — existing GitHub-dark tokens, `.card`, `.badge`, event colour map
- `src/shitbox/display/oled.py` lines 86-161 — 4-line render budget, `_draw_text` inversion primitive, existing line 3 contents being replaced
- CLAUDE.md §Website stack — shipped BADGE_COLORS palette and GitHub-dark theme the dashboard panel inherits from
