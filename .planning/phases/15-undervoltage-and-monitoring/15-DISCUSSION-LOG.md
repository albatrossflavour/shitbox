# Phase 15: Undervoltage and Monitoring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 15-undervoltage-and-monitoring
**Areas discussed:** undervoltage detection, alert channel shape, capture-failure surfacing, monitoring plumbing cleanup, Phase 21 seam, TTS cadence, Health page

---

## Gap 1 — Undervoltage: detection and surface

### Q1a — Bitmask and sustain

| Option | Description | Selected |
|--------|-------------|----------|
| Mask + sustain | Compare only `raw & 0xf`, require N consecutive non-zero reads before alerting | ✓ |
| Raw compare (status quo) | Keep compare-on-raw; any change fires | |
| Mask + single read | Mask to current bits, but alert on first non-zero | |

**User's choice:** Mask + sustain (Recommended)
**Notes:** Transient cranking dips must not alert. Recovery requires zero-mask held for N reads too.

### Q1b — Surface pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Spoken + overlay | Piper TTS + full-screen ALERT overlay; no buzzer | ✓ |
| Buzzer + overlay | Short buzzer + ALERT overlay |  |
| Spoken only | TTS only, no visual |  |

**User's choice:** Spoken + overlay (Recommended)
**Notes:** Buzzer stays as the Phase 5 fallback path. Undervoltage already exercises the TTS + overlay pattern.

---

## Gap 2 — Alert channel and capture-failure trigger

### Q2a — Channel shape

| Option | Description | Selected |
|--------|-------------|----------|
| Extend ALERT subtype | Keep `dashboard_push_event({"type":"ALERT","subtype":X,...})` | ✓ |
| New `system_event` channel | Add a second SSE channel for system events | |
| Field on `/sse/slow` only | No event pushes; just state on the slow stream | |

**User's choice:** Extend ALERT subtype (Recommended)
**Notes:** The frontend already routes `type==="ALERT"` to the full-screen red overlay. No new plumbing.

### Q2b — Capture-failure trigger scope

| Option | Description | Selected |
|--------|-------------|----------|
| ffmpeg stall detection only | Reuse `_is_stalled()` — one signal, ffmpeg stopped producing segments | ✓ |
| Stall + `/dev` node presence | Also detect camera device disappearance | |
| Full hardware presence | Cover stall, `/dev`, audio, encoder — overlaps Phase 21 | |

**User's choice:** ffmpeg stall detection only (Recommended)
**Notes:** Stay in-scope. Device-presence coverage belongs in Phase 21.

---

## Gap 3 — MQTT scrape + HLTH-01 closure

### Q3a — MQTT scrape entry

| Option | Description | Selected |
|--------|-------------|----------|
| Delete the scrape entry | Remove `shitbox-mqtt-exporter` job; migrate any lingering Grafana queries to `job="shitbox"` | ✓ |
| Relabel at scrape | Keep the job, relabel metrics to `job="shitbox"` | |
| Rename job | Rename to `shitbox-mqtt` for clarity | |

**User's choice:** Delete the scrape entry (Recommended)
**Notes:** MQTT is permanently off. Audit Grafana dashboards + alerts for survivors before deleting.

### Q3b — HLTH-01 (MON-01) closure

| Option | Description | Selected |
|--------|-------------|----------|
| Skip, just close the ticket | No code change — user confirmed metrics live in Grafana | ✓ |
| Fix cpu_percent bug | Investigate the stale concern anyway | |
| Rebuild health collector | Rewrite with tests | |

**User's choice:** Skip, just close the ticket
**Notes:** User confirmed while viewing Grafana that metrics are arriving. MON-01 is ticket hygiene, not a code task.

---

## Gap 4 — Phase 21 seam + TTS cadence

### Q4a — Where the new code lives

| Option | Description | Selected |
|--------|-------------|----------|
| Ad-hoc + tiny shared helper | Detectors stay in `thermal_monitor.py` / `ring_buffer.py`; extract `health/alerts.py` for debounce+cadence | ✓ |
| Full `SystemCondition` subsystem now | Introduce Phase 21-shape abstraction up front | |
| Hard-code in each detector | No shared helper; duplicate debounce in three places | |

**User's choice:** Ad-hoc + tiny shared helper (Recommended)
**Notes:** Phase 21 may retrofit later. The helper is the seam, not the cathedral.

### Q4b — TTS cadence

| Option | Description | Selected |
|--------|-------------|----------|
| Once on transition, once on recovery | Single utterance on alert; single utterance on clear | ✓ |
| Repeat every N minutes while active | Periodic reminder while the condition holds | |
| Repeat until acknowledged | Button press (or dashboard click) to silence | |

**User's choice:** Once on transition, once on recovery (Recommended) + user addition
**Notes:** User added: *"we should expand the HW page to be a Health page, so we can query it and the alert colour will stay in place so we don't forget something is broken."* This became D-13 — persistent sticky colour state on the Health page replaces nagging audio as the "don't forget" mechanism.

---

## Claude's Discretion

- Exact N for sustain-before-alert and for `CAPTURE_DOWN` threshold
- TTS phrasing (stay consistent with Phase 5)
- Health page colour scheme (follow existing hardware panel palette)
- `alerts.py` internal shape (class vs module-level) — follow existing `thermal_monitor` conventions

## Deferred Ideas

- `HardwareState` / `SystemCondition` unified abstraction — Phase 21
- Button-as-acknowledge for critical alerts — Phase 21 D-05
- Broader capture-failure surface (/dev, audio, encoder) — Phase 21
- Repeat-until-acknowledged TTS / criticality-tier escalation — Phase 21 D-05
- MQTT exporter resurrection with distinct job name — if/when MQTT is re-enabled in v3
- Pi 5 firmware mailbox hang (2026-04-24 09:34:31) — separate `/gsd-debug`

---

*Phase: 15-undervoltage-and-monitoring*
*Discussion log generated: 2026-04-24*
