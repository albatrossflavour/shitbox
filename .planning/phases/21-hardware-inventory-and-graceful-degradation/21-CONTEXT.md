# Phase 21: Hardware Inventory and Graceful Degradation - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Know what hardware should be present, verify it at boot, notice when it
disappears mid-rally, and surface that state where the crew can see it.
The daemon must never refuse to start because a device is missing, and
must automatically re-adopt devices that come back.

**In scope:**

- A declared hardware manifest in `config.yaml` with expected devices (role, bus, address/path, criticality)
- Boot-time probe that verifies each expected device and classifies it PRESENT / MISSING
- A central `HardwareState` object that collectors report PRESENT / DEGRADED / MISSING into at runtime
- A `HardwareSupervisor` thread that owns alert cadence (TTS, OLED state, dashboard banner) driven off `HardwareState`
- Exponential-backoff re-adoption for every device tier (5s → 15s → 60s → 5 min cap)
- Pi-local status rendering on OLED, dashboard, and TTS

**Out of scope:**

- Prometheus per-device `up` gauge
- `hardware.json` rsynced to the website
- Hardware state fields in `events.json` or any other sync payload
- Website "what's online" widget
- Physically replacing or wiring new hardware (that belongs in Phase 20)
- Configuration UX on the driver display (hardware status is a read-only panel)

</domain>

<decisions>
## Implementation Decisions

### Manifest

- **D-01:** The manifest is **hybrid** — expected devices are declared in `config.yaml`, then verified at boot by probing the real hardware. Missing devices are recorded as absent, not silently ignored.
- **D-02:** The manifest lives under a new top-level `hardware:` block in `config.yaml`. Existing sensor-specific blocks (imu:, environment:, etc.) keep their tuning knobs; presence metadata lives in the new block.
- **D-03:** Each entry carries at minimum: `role`, `bus` (one of `i2c-1`, `1-wire`, `usb`, `gpio`, `hdmi`, `audio`), `address` or `path`, and `criticality` (one of `critical`, `important`, `best_effort`). Extra fields allowed per-bus (e.g. USB `vendor_id:product_id` or label).

### Criticality policy

- **D-04:** Booting **never** refuses to start because of missing hardware. The daemon always comes up; the alert loudness is what differs per tier.
- **D-05:** Criticality mapping:
  - **critical** — LSM6DSOX (IMU), front camera (UGREEN). Repeated TTS until acknowledged, red dashboard banner, OLED line inverts.
  - **important** — INA226 (power), GPS. Single TTS at boot + on state change, orange dashboard badge, OLED line.
  - **best_effort** — BME680, LIS3MDL, VEML7700, OLED self, DS18B20 probes (exterior + engine_bay), cabin camera (Brio 100), USB mic, button, HDMI display. Log only, grey dashboard badge, OLED line.

### Runtime detection and recovery

- **D-06:** Detection stays **distributed** — each collector keeps its existing `OSError` / setup-failure paths. They report presence changes into a central `HardwareState` object; no collector logic is rewritten.
- **D-07:** A single `HardwareSupervisor` thread reads `HardwareState` and owns alert cadence. It's the one place that decides "the front camera has been MISSING for 20s, speak the TTS now" — so collectors don't duplicate alert policy.
- **D-08:** Every tier gets automatic **re-adoption on exponential backoff**: 5s, 15s, 60s, with a 5-minute cap between retries. Applies to I2C, USB, and 1-wire. No manual trigger required when the crew replugs a camera or reseats a loom.
- **D-09:** When a device re-adopts, the `HardwareSupervisor` emits a "recovered" TTS line and the OLED/dashboard state flips back — the crew must get positive confirmation, not just the absence of the alert.

### Status surface

- **D-10:** Status is **Pi-local only**. The surfaces are:
  - **OLED** — one line per critical/important device; best_effort devices share a roll-up line.
  - **Dashboard** — dedicated hardware panel in the kiosk UI (fed via SSE), showing per-device tier + state + last-seen time.
  - **TTS (Piper)** — alert cadence per D-05.
- **D-11:** No Prometheus `shitbox_hardware_up` gauge, no `hardware.json` sync generator, no extra fields on `events.json`, no website widget. If remote visibility becomes necessary later it's a separate phase.

### Claude's Discretion

- Exact YAML shape of the `hardware:` block (list vs map, field ordering) — pick a shape that reads cleanly in git diffs and round-trips through the existing `_dict_to_dataclass` loader.
- How `HardwareState` is threaded to consumers (module-level singleton vs passed into `UnifiedEngine` and fanned out) — should mirror how existing shared state like `gps_state` is wired.
- OLED line layout within the 4-line budget — roll up best_effort devices into a single "env: 2/3" style summary line if space is tight.
- TTS wording — keep short, unambiguous, and consistent with existing TTS patterns (e.g. "IMU offline", "camera restored").
- Dashboard panel visual treatment — follow existing GitHub-dark theme and BADGE_COLORS conventions.
- Exponential backoff implementation detail (global scheduler vs per-collector timer) — whichever needs less churn in existing collectors.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context

- `.planning/PROJECT.md` — vision and non-negotiables
- `.planning/REQUIREMENTS.md` — HW-* requirements (to be added for this phase)
- `.planning/ROADMAP.md` §Phase 21 — phase scope bullet
- `.planning/STATE.md` §"Out-of-Band Hardware Work (2026-04-10)" — documents the BME680 init-timing issue, the i2c_designware → i2c-gpio switch, and the sampler/temperature/light collector fixes; this is the lived experience driving the phase

### Code to read before touching

- `src/shitbox/events/engine.py` — `UnifiedEngine` owns service lifecycle; new `HardwareState` + `HardwareSupervisor` wire here
- `src/shitbox/events/sampler.py` — existing escalating I2C reset ladder for LSM6DSOX; pattern to respect, not rewrite
- `src/shitbox/collectors/base.py` — abstract collector (template method) that every 1Hz collector inherits; presence reporting hooks into this
- `src/shitbox/collectors/temperature.py` — DS18B20 role-based config already present, reference pattern for per-device config
- `src/shitbox/collectors/environment.py` — BME680 is the canonical retry case
- `src/shitbox/utils/config.py` — `load_config()` + `_dict_to_dataclass`; this is where the new `hardware:` block enters the type system
- `src/shitbox/capture/video.py` / `src/shitbox/events/ring_buffer.py` — ffmpeg health monitor pattern for USB camera presence
- `src/shitbox/display/oled.py` (if present) — existing OLED render surface
- `src/shitbox/dashboard/` — FastAPI + SSE + Alpine dashboard for the hardware panel surface
- `src/shitbox/utils/tts.py` (or wherever Piper is invoked) — TTS invocation pattern

### Conventions

- `CLAUDE.md` — project conventions, graceful-degradation stance, service pattern
- `graphify-out/GRAPH_REPORT.md` — community structure; communities 0 (Engine Lifecycle), 1 (Collector Base), 8 (Button/IMU/Sensors), 10 (I2C Recovery), 17 (Hardware Overview) are the ones to traverse before planning

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- **`UnifiedEngine`** — already orchestrates the three concurrent paths; owns service start/stop lifecycle. `HardwareSupervisor` slots in next to `BatchSyncService` / `CaptureSyncService`.
- **Collector template method** (`collectors/base.py`) — every 1Hz collector already has a setup / read / error loop. A one-line "I failed setup" / "I read successfully" hook into `HardwareState` is enough; no rewrites.
- **Existing I2C reset ladder** in `sampler.py` — 9-clock bit-bang recovery + escalating reset counter before reboot. The LSM6DSOX critical path already has the right semantics; `HardwareState` just needs to be notified when the ladder ticks.
- **FFmpeg health monitor pattern** in `ring_buffer.py` — stall detection via `mtime` + stderr drain. USB camera presence reuses this directly.
- **`gps_state`** helper — module-level shared state used by `LogbookStorage` and the SSE pipeline; natural analog for `HardwareState`.
- **Piper TTS** is already wired for alerts (Phase 5). No new audio primitive needed.
- **OLED driver** is already in the codebase (Community 20 in the graph). Rendering a status line is a content change, not a new surface.
- **SSE pipeline** in the dashboard publishes fast/slow streams. A `hardware` slot (or adding fields to the slow stream) is the natural wiring for the dashboard panel.

### Established patterns

- **Hierarchical YAML → nested dataclasses** via `load_config()` + `_dict_to_dataclass` — new `hardware:` block follows this pattern.
- **Daemon thread per service** with `start()` / `stop()` lifecycle — `HardwareSupervisor` is just another instance of this.
- **Graceful degradation is already a pattern**, not a new concept — GPIO, GPS, cameras, and some I2C sensors are already optional. This phase formalises and centralises the pattern, not invents it.

### Integration points

- New `HardwareState` object lives alongside `gps_state`; ref passed into collectors that need to report (most already have `BaseCollector.setup()` / error hooks).
- New `HardwareSupervisor` wires into `UnifiedEngine.__init__()` + `start()` / `stop()`.
- OLED render loop reads `HardwareState` in addition to whatever it shows today.
- Dashboard SSE "slow" stream gains a `hardware` field carrying the current snapshot (or a sibling SSE stream — planner's call, see Claude's Discretion).
- `config.yaml` gains `hardware:` top-level block; `config.py` gains `HardwareManifestConfig` dataclass.

</code_context>

<specifics>
## Specific Ideas

- The STATE.md out-of-band section (2026-04-10) names the exact devices on the I2C bus today. That list is the authoritative starting point for the manifest: 0x10 VEML7700, 0x1c LIS3MDL, 0x3c OLED, 0x40 INA226, 0x6a LSM6DSOX, 0x77 BME680. Plus DS18B20 probes by role, USB GPS / front camera / cabin camera / mic, GPIO button 17, HDMI display.
- The BME680 "not initialising at boot" issue is the canonical reason for this phase existing. It should be the acceptance-test case: cold-boot, BME680 fails first init, supervisor reports DEGRADED, retry succeeds on backoff, state flips to PRESENT, "env sensor restored" TTS fires.
- LSM6DSOX critical tier should not duplicate the existing 9-clock reset ladder — that ladder remains the first line of defence. `HardwareState` is observational for it; the supervisor only speaks TTS if the ladder escalates to "give up after N resets".
- The i2c-gpio (bit-bang) bus is the active I2C bus. `i2c_designware` is off in config.txt. Manifest probe must target bit-bang bus 1.

</specifics>

<deferred>
## Deferred Ideas

- **Prometheus `shitbox_hardware_up` gauge** — could be added later as a thin extension to the existing `BatchSyncService`; explicitly deferred (D-11).
- **`hardware.json` rsynced to the website + "what's online" badge** — feasible (we have the `CaptureSyncService` JSON generator registry), but not worth the website-repo churn right now.
- **Hardware status embedded in `events.json`** — would help post-mortem analysis but adds noise to every event and has no current consumer.
- **Magnetometer (LIS3MDL) elliposid calibration** — already deferred in REQUIREMENTS.md; surface here that "present but uncalibrated" is a valid state for the manifest.
- **ESP32-based I2C buffering / TCA4307 hardening** — covered separately in `project_i2c_hardening_plan` memory; not part of this phase.
- **Manual recovery trigger** (button-long-press to force re-probe all devices) — backoff already covers this need; revisit only if the crew actually wants it in the field.

</deferred>

---

*Phase: 21-hardware-inventory-and-graceful-degradation*
*Context gathered: 2026-04-21*
