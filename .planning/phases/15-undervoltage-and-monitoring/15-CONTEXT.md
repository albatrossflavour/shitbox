# Phase 15: Undervoltage and Monitoring - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Close four monitoring gaps that slipped through v1.0:

1. **PWR-01** — stop the undervoltage alert mis-firing off sticky since-boot bits in `vcgencmd get_throttled`
2. **PWR-02** — make an active undervoltage condition visible on the dashboard and audible via TTS, with a recovery signal when power is restored
3. **MON-01** — close out the HLTH-01 ticket (CPU temp / disk / sync backlog metrics reaching Prometheus); user has confirmed the pipeline is already working end-to-end, so this is ticket closure, not a bug hunt
4. **MON-02** — retire the duplicate `shitbox-mqtt-exporter` scrape job now that MQTT is permanently off
5. **MON-03** — surface capture-failure events (ffmpeg stall + restart) on the live dashboard the same way undervoltage is surfaced

Scope anchor: three concrete alert paths (undervoltage, thermal already existed, capture-failure) sharing one tiny helper. A full `HardwareState`-style abstraction is **not** in scope — Phase 21 can refactor later if warranted.

</domain>

<decisions>
## Implementation Decisions

### Undervoltage detection (PWR-01, PWR-02)

- **D-01 — Bitmask read:** Compare only the low nibble, `raw & 0xf`, against the prior reading. Sticky bits 16-19 are decoded for logging but are never part of the alert trigger. The current bug is in `src/shitbox/health/thermal_monitor.py:297` where the full raw value is compared.
- **D-02 — Sustain before alerting:** Require a non-zero mask to persist across N consecutive reads (~2-3 seconds) before firing. Transient cranking dips must not alert.
- **D-03 — Recovery signal:** When the mask returns to zero and stays zero for N reads, fire a "power restored" TTS + 3-second green overlay. Matches Phase 21 D-09 recovery discipline.
- **D-04 — Surface pattern:** Spoken TTS (Piper) plus the existing full-screen red ALERT overlay. No buzzer beep on undervoltage in this phase — buzzer stays as the fallback path Phase 5 already wired.

### Alert channel shape (all three alert paths)

- **D-05 — Reuse existing channel:** Keep using `dashboard_push_event({"type": "ALERT", "subtype": X, "message": ..., "ts": ...})` on `/sse/events`. Do not invent a new `system_event` channel — the frontend already routes `type === "ALERT"` to the full-screen overlay.
- **D-06 — Subtypes:**
  - `UNDERVOLTAGE` / `UNDERVOLTAGE_CLEARED`
  - `CAPTURE_FAILURE` (stall detected + restart attempted)
  - `CAPTURE_RESTORED` (restart succeeded)
  - `CAPTURE_DOWN` (persistent failure after N restart attempts)
  - `THERMAL_*` already exists in thermal_monitor.py — leave alone

### Capture-failure detection (MON-03)

- **D-07 — Trigger source:** Reuse the existing `_is_stalled()` check in `src/shitbox/capture/ring_buffer.py`. Do not expand to cover `/dev` node presence, audio device availability, or encoder health — those are Phase 21 hardware-presence concerns. One signal: ffmpeg stopped producing segments.
- **D-08 — Restart bookkeeping:** Count consecutive restart attempts. N (small integer, e.g. 3) in a rolling window triggers `CAPTURE_DOWN`; a clean segment after restart triggers `CAPTURE_RESTORED`.

### Monitoring plumbing (MON-01, MON-02)

- **D-09 — HLTH-01 closure:** No code change. Metrics are confirmed live in Grafana. Flag MON-01 closed in REQUIREMENTS.md with a one-line note. The "insert_readings_batch cpu_percent bug" mentioned in the staging doc is stale — `src/shitbox/storage/database.py:469` and `src/shitbox/sync/batch_sync.py:536` already handle `cpu_percent` correctly.
- **D-10 — MQTT scrape retirement:** Delete the `shitbox-mqtt-exporter` scrape entry from the home-ops Prometheus config entirely. Before deleting, grep Grafana dashboards + alerting rules for `job="shitbox-mqtt-exporter"` and migrate survivors to `job="shitbox"`. No relabelling gymnastics — the job is dead, treat it as dead.

### Debounce / cadence seam (Phase 21 coupling)

- **D-11 — Tiny shared helper:** Extract `src/shitbox/health/alerts.py` exposing `fire_alert(subtype, message, tts_fn)` and `fire_recovery(subtype, message, tts_fn)`. Owns: sustain counting, once-on-transition semantics, recovery semantics. Callers: `thermal_monitor.py`, `ring_buffer.py` (capture stall), and the new undervoltage detector. Phase 21 may later refactor this into a `SystemCondition` abstraction — the helper is the seam, not the cathedral.
- **D-12 — TTS cadence:** Once on transition, once on recovery. No repeat-until-acknowledged in this phase. Persistent visibility is provided by D-13 (Health page), not by nagging audio.

### Health page (the notable specific)

- **D-13 — Expand the hardware panel into a Health page:** The existing `/sse/slow` `hardware` payload (per-device `{role, tier, state, last_seen, since_ms}`) is the scaffold. Add system conditions alongside devices — `undervoltage`, `thermal`, `capture` — each with a state that sticks (red/amber) until cleared. The transient ALERT overlay is easy to miss if the driver is concentrating; the Health page is the durable "something is broken" indicator. Payload extension lives in `src/shitbox/dashboard/sse.py` next to `_hardware_payload()`; frontend rendering extends the existing hardware list on the dashboard.

### Claude's Discretion

- Exact N for sustain-before-alert (2 or 3 reads) — pick based on the read cadence
- Exact N for `CAPTURE_DOWN` threshold — reasonable default, not a user-facing knob
- Wording of TTS phrases ("undervoltage detected" / "power restored" / "capture stalled" etc.) — stay consistent with existing Phase 5 phrasing, keep them short
- Health page colour scheme for system conditions — follow the hardware panel's existing palette
- Whether `alerts.py` uses class/instance state or module-level counters — pick whichever matches existing `thermal_monitor` conventions

</decisions>

<specifics>
## Specific Ideas

- **User's framing of the Health page:** *"we should expand the HW page to be a Health page, so we can query it and the alert colour will stay in place so we don't forget something is broken."* This is the design principle for D-13 — sticky colour state, not transient toast. If the driver looks at the dash five minutes after the overlay cleared, they should still see the condition.
- Follow Phase 21's existing hardware-panel visual conventions. Don't reinvent.
- TTS cadence mirrors Phase 21 D-09: single utterance on transition, single utterance on recovery. No spam.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements and state
- `.planning/REQUIREMENTS.md` §49-58 — PWR-01, PWR-02, MON-01, MON-02, MON-03 requirement text
- `.planning/ROADMAP.md` — Phase 15 scope boundary
- `.planning/STATE.md` — current v2.0 progress

### Prior phase decisions that constrain this phase
- `.planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md` — D-04 (never refuse boot), D-05 (criticality tiers), D-09 (recovery TTS required), D-10 (Pi-local only). The alerts helper must not break these.
- `.planning/phases/10-live-dashboard-with-offline-map/10-CONTEXT.md` — D-02 (capture path sacred — alert pushes must be non-blocking), D-07/D-08 (SSE stream conventions), existing alertOverlay pattern.
- `.planning/phases/05-piper-tts/` (or nearest Phase 5 artifact) — TTS phrasing conventions

### Source files to read before editing

#### PWR-01 / PWR-02 (undervoltage)
- `src/shitbox/health/thermal_monitor.py` — the bug lives at `_decode_throttled` / the compare-on-raw at line ~297; new undervoltage detector likely lives here or in a sibling module calling the shared helper

#### MON-03 (capture-failure)
- `src/shitbox/capture/ring_buffer.py` — `_is_stalled()` health check; this is the trigger point for `CAPTURE_FAILURE` / `CAPTURE_RESTORED` / `CAPTURE_DOWN`

#### Alert fan-out
- `src/shitbox/dashboard/sse.py` — `push_event()` broadcast, `_hardware_payload()` (the Health-page scaffold lives adjacent), `/sse/slow` payload
- `src/shitbox/dashboard/static/index.html` — `showAlert(payload)` routing at lines ~217-223, 536-547, 607-612; hardware panel rendering for D-13 extension

#### Metrics plumbing (MON-01 closure verification)
- `src/shitbox/health/health_collector.py` — reads cpu_percent via psutil, builds Reading
- `src/shitbox/storage/database.py:469` — `insert_readings_batch` cpu_percent persist (already correct)
- `src/shitbox/sync/batch_sync.py:536-539` — `shitbox_cpu_pct` remote_write emit (already correct)

#### Phase 21 seam
- `src/shitbox/hardware/state.py` — `DeviceState`, `DeviceStatus`, `snapshot()`. The new `alerts.py` helper should cohabit this module's conventions (module-level state, GIL-atomic rebind) without importing it — Phase 21 retrofits later.

### External (home-ops repo)
- `~/dev/home-ops/kubernetes/apps/monitoring/` (or wherever Prometheus scrape config lives) — target for MON-02 scrape-entry deletion
- Grafana dashboards + alerting rules — audit for `job="shitbox-mqtt-exporter"` survivors before deleting the scrape

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `dashboard_push_event(...)` — already non-blocking, drop-on-full; the transport for all three alert subtypes
- `_hardware_payload()` in `sse.py` — feeds the current hardware dashboard panel; extend it to include system-condition entries for the Health page
- `_is_stalled()` in `ring_buffer.py` — proven ffmpeg health check (fixed Mar 2026); reuse directly, don't reinvent
- Phase 5 TTS pipeline (`utils/tts.py` or equivalent) — speak_under_voltage already exists
- Phase 21 `hardware/state.py` — reference pattern for thread-safe module-level state in the new `alerts.py`

### Established Patterns
- `dashboard_push_event` with `type: "ALERT"`, `subtype`, `message`, `ts` — the frontend already routes this to the red overlay. No new routing logic needed.
- structlog keyword logging (`log.info("alert_fired", subtype=..., sustain_reads=...)`)
- Graceful-degradation wiring: `try: from shitbox.dashboard import push_event; except ImportError: def push_event(*a, **k): pass` — keeps detectors testable without the dashboard.
- Phase 21 D-04 "never refuse boot" — the alerts helper must tolerate TTS or dashboard being absent.

### Integration Points
- **Undervoltage detector** — hooks into the existing `thermal_monitor` read loop (already polls `vcgencmd get_throttled`); replaces raw-compare with `raw & 0xf` compare and delegates to `alerts.fire_alert`.
- **Capture-failure alert** — fires from `ring_buffer._is_stalled()` detection path; delegates to `alerts.fire_alert("CAPTURE_FAILURE", ...)`. Restart-success path fires `CAPTURE_RESTORED` via `alerts.fire_recovery`.
- **Health page payload** — new `_system_conditions_payload()` beside `_hardware_payload()`; merged into `/sse/slow` under `system_conditions`. Frontend extends the hardware panel section.

</code_context>

<deferred>
## Deferred Ideas

- **`HardwareState` / `SystemCondition` unified abstraction** — Phase 21 retrofits the three ad-hoc alert paths into a single model. Phase 15 ships the three paths via the tiny helper so Phase 21 has a clean seam.
- **Button-as-acknowledge** for critical alerts (Phase 21 D-05 repeated-TTS-until-acknowledged tier). Deferred; Phase 15 uses once-on-transition / once-on-recovery for all three.
- **Broader capture-failure surface detection** — `/dev/video*` node presence, audio device availability at startup, encoder CPU saturation. Belongs in Phase 21 hardware-presence work.
- **MQTT exporter resurrection** — if MQTT is ever re-enabled in v3, give it a distinct job name from `shitbox` at that point. Not Phase 15's problem.
- **Repeat-until-acknowledged TTS** and **criticality-tier alert escalation** — deferred to Phase 21's D-05 implementation.
- **Pi 5 firmware mailbox hang** (observed 2026-04-24 09:34:31) — separate `/gsd-debug` session, not Phase 15.

</deferred>

---

*Phase: 15-undervoltage-and-monitoring*
*Context gathered: 2026-04-24*
