# Phase 28: TPMS Integration — Specification

**Created:** 2026-04-28
**Ambiguity score:** 0.13 (gate: ≤ 0.20)
**Requirements:** 10 locked

## Goal

Receive 433 MHz TPMS sensor frames from the four installed wheel sensors via RTL-SDR + `rtl_433`, normalise pressure into actual PSI, persist to SQLite, and surface per-wheel state on Grafana and the dashboard Health page with low-pressure threshold alerts and rapid-deflation (leak) alerts via the existing TTS engine.

## Background

No TPMS code exists in the codebase today. `rtl_433` is not installed on the Pi and not referenced anywhere in `src/`. The aftermarket TPMS kit (4 sensors, 433 MHz, decodes under `rtl_433 -R 156` Abarth-124Spider/VDO-TG1C profile) was bench-validated 2026-04-28; all four sensor IDs were captured and mapped to wheel positions:

- `550b57d9` — front-driver
- `550d14ed` — rear-driver
- `550b5d8a` — rear-passenger
- `54d96e8f` — front-passenger

The `rtl_433` Abarth-124 decoder applies `kPa = byte_5 × 1.38` (max 350 kPa). Calibration against four fitted tyres at 31-32 PSI showed the aftermarket sensor's actual LSB is ≈3.37 kPa/count, giving a correction factor of **× 2.45** to convert decoder output to real kPa. The decoder source itself flags this uncertainty (`"to be checked, VDO says 450/900kPa"`).

Existing patterns this phase plugs into:

- `BaseCollector` in `src/shitbox/collectors/base.py` is built for synchronous polled sensors and is **not** a good fit — TPMS frames arrive asynchronously when the radio receives them. The closer analog is `src/shitbox/capture/video.py`, which manages a long-running ffmpeg subprocess with stderr drain and restart-on-death.
- Hardware manifest in `config.yaml hardware: devices` (Phase 21) governs presence/criticality.
- `src/shitbox/health/alerts.py` (shipped Phase 15) handles sustain + transition + recovery semantics.
- Dashboard Health page (`dashboard/sse.py` + `dashboard/static/index.html`) renders alert state via SSE + Alpine.js `x-for`.
- TTS engine (Phase 5) speaks driver-facing alerts.

Hardware in flight: Nooelec NESDR Smart v5 (RTL2832U + R820T2 + 0.5 PPM TCXO + magnetic-base antenna) arriving Thursday 2026-04-30; TEKERA powered USB hub for keyboard + touchscreen-touch HID.

## Requirements

1. **TPMS frame ingestion**
   - Current: No TPMS code; `rtl_433` not in the source tree or systemd unit.
   - Target: Long-running `rtl_433 -R 156 -F json` subprocess wrapped by a shitbox-managed service that parses the JSON stream and accepts frames matching configured sensor IDs.
   - Acceptance: With the SDR plugged in and four sensors fitted, every configured sensor ID produces ≥1 parsed frame per minute under typical bench/driveway RF conditions.

2. **Pressure correction**
   - Current: rtl_433 reports `pressure_kPa = raw_byte × 1.38` — wrong for this aftermarket kit by ≈×2.45.
   - Target: Collector applies a configurable correction factor (default `2.45`) to the decoder's `pressure_kPa` before any downstream use (storage, alerting, display).
   - Acceptance: Stored pressure values are within ±3 PSI of a stick-gauge reference at the same fitted pressure.

3. **Wheel-position mapping**
   - Current: Sensor IDs are anonymous hex strings; no mapping exists.
   - Target: YAML config maps each known sensor ID to a wheel-position label (`front-driver`, `rear-driver`, `front-passenger`, `rear-passenger`).
   - Acceptance: All readings appear with a wheel label. Frames from sensor IDs not in config are logged at INFO (`tpms_unknown_sensor`) and discarded — no row in SQLite, no metric exposition.

4. **SQLite persistence**
   - Current: No `tpms_readings` table exists in `src/shitbox/storage/`.
   - Target: New table with columns `(timestamp, sensor_id, wheel, pressure_psi, temperature_c, status, raw_pressure_kpa)`. Schema migration follows the existing `database.py` pattern.
   - Acceptance: Every parsed frame for a known sensor produces exactly one row. Row count over a 60-second observation window matches the parsed-frame count from logs.

5. **Prometheus exposition**
   - Current: `batch_sync` does not expose TPMS metrics.
   - Target: Per-wheel `tpms_pressure_psi{wheel="..."}` and `tpms_temperature_c{wheel="..."}` gauge metrics, scraped from SQLite via the existing batch_sync cursor pattern.
   - Acceptance: Grafana shows four time series per metric (one per wheel) with values matching SQLite to within one sample.

6. **Dashboard Health page TPMS section**
   - Current: Phase 15 Health page renders only the SYSTEM (alerts) section.
   - Target: New TPMS section showing four wheel slots with current PSI, last-update timestamp (relative, e.g. "3s ago"), and a colour state (grey NO DATA / green OK / yellow LOW / red CRITICAL / amber STALE).
   - Acceptance: Section renders one slot per configured wheel. Pre-first-frame state shows "NO DATA" grey. Slot value updates within 2 seconds of new frame arrival via SSE.

7. **Low-pressure threshold alerting**
   - Current: No TPMS alert path.
   - Target: Per-wheel sustained-low-pressure alert at **28 PSI yellow / 25 PSI red**, configurable in YAML. Yellow fires Health-page banner only; red fires Health-page red banner + TTS spoken alert with the wheel label (e.g. "Front driver tyre low pressure"). Reuses `health/alerts.py` sustain + transition + recovery helpers.
   - Acceptance: Bench-test deflating one sensor below 25 PSI fires the red banner and TTS within 5 seconds. Re-inflation above 28 PSI clears the alert with the existing `_RESTORED` suffix pattern shipped in Phase 15.

8. **Rapid-deflation (leak) detection**
   - Current: No rate-of-change detection.
   - Target: Per-wheel sliding 60-second window. A drop of **≥5 PSI within the window** fires a CRITICAL leak alert: TTS spoken alert + Health-page red banner + a `TPMS_LEAK` event written to `events.json` (no dashcam-buffer save — pressure data alone tells the story). Threshold values configurable in YAML.
   - Acceptance: Bench-test rapidly deflating one sensor by ≥5 PSI within 60s fires the alert and records a `TPMS_LEAK` event. Slow deflation (≤1 PSI per minute) does **not** fire the leak alert.

9. **Stale-sensor detection**
   - Current: No silence detection.
   - Target: Per-wheel STALE warning if no frame received for **5 minutes**. Clears on the next received frame. Surfaced on Health page as the wheel's amber state. No TTS for STALE (different from a real alert — wheels can fade out under bad RF without the driver needing to know).
   - Acceptance: Disconnect or RF-shield one sensor; Health page shows STALE for that wheel after 5 minutes. Re-enabling the sensor clears STALE within one heartbeat (≤2 seconds typical).

10. **Hardware manifest entry — graceful degradation**
    - Current: No `tpms_radio` role in `config.yaml hardware: devices`.
    - Target: New manifest entry `role: tpms_radio`, `bus: usb`, `path: /dev/...` (RTL-SDR device node, exact path resolved during planning), `criticality: best_effort`, description noting the model.
    - Acceptance: Boot probe records PRESENT when SDR is plugged in and MISSING when unplugged. Daemon starts cleanly in both states. `HardwareSupervisor` re-adopts when the SDR is replugged within the existing exponential-backoff window.

## Boundaries

**In scope:**

- All ten requirements above.
- New TPMS service module under `src/shitbox/` managing the `rtl_433` subprocess lifecycle (start, monitor, stderr drain, restart on death) — pattern follows `capture/video.py`.
- YAML config additions: TPMS section with sensor-id → wheel mapping, correction factor, low-pressure thresholds, leak-detection window/delta, stale-sensor timeout.
- New SQLite table + schema migration via the existing `storage/database.py` migration pattern.
- Grafana dashboard panel additions for the four wheel pressures + temperatures.
- Dashboard Health page TPMS section + SSE payload extension.
- TTS spoken alerts for low-pressure (red threshold) and leak (≥5 PSI/60s) events.
- `TPMS_LEAK` event type written to `events.json` (no dashcam buffer save).
- `rtl_433` install path (apt or built from source) documented + added to `install.sh`.

**Out of scope:**

- **Patching rtl_433 or filing upstream PR for the TG1C decoder LSB issue.** Separate tidy-up task once calibration is tighter. The correction factor lives in shitbox config for now.
- **Roof-mounted antenna install** (cable through roof, bulkhead, magnetic-base placement). Separate hardware task — phase 28 assumes the antenna is plugged in somewhere reasonable and signal arrives.
- **OTA learn-mode for replacing a sensor mid-rally.** Sensor replacement requires YAML edit + daemon restart.
- **Per-sensor calibration table.** Single global × 2.45 only; refine if a future bench session shows individual sensor drift.
- **TPMS triggering dashcam-buffer video capture.** Low-pressure and leak events are recorded in `events.json` but do **not** trigger the same buffer-save path as HIGH_G/HARD_BRAKE.
- **Temperature alerting.** Temperature is captured, stored, and graphed; no thresholds, no alerts at this phase.
- **Anti-theft / sensor cloning detection.** Out of scope — open RF, anyone with a transmitter could spoof; not a problem worth solving for a rally car.

## Constraints

- `rtl_433` must be installed on the Pi (apt package or built from source) — not currently in `install.sh`. Plan must address.
- RTL-SDR USB device must be on a direct USB 2.0 port, not behind a hub (per memory: bus contention causes sample drops).
- Storage volume: ~1 frame/sec/wheel × 4 wheels = ~14,400 rows/hour ≈ 14 MB/day. Negligible.
- Single-tuner SDR can only listen on one frequency at a time; 433.92 MHz is fixed for this kit.
- Pressure correction × 2.45 is empirically calibrated to 31-32 PSI fitted tyres; treat absolute values as ±3 PSI accuracy until a sub-PSI digital-gauge calibration tightens it.
- Pi 5 USB power budget is tight (front + cabin cameras already drawing); RTL-SDR draws ~250 mA at full sample rate. Verify `usb_max_current_enable=1` is set in `/boot/firmware/config.txt`.
- TTS engine (Phase 5) must be available for spoken alerts. If TTS is unavailable, alerts still fire on the Health page banner — TTS failure must not suppress visual alerts.

## Acceptance Criteria

- [ ] All four configured sensor IDs produce parsed frames in SQLite at ≥1 frame/min/wheel under typical bench/driveway RF conditions.
- [ ] Stored pressure values within ±3 PSI of stick-gauge reference at the same fitted pressure.
- [ ] Unknown sensor IDs are logged at INFO and discarded; no storage pollution, no metric exposition.
- [ ] Grafana shows four time series per metric (pressure, temperature) with values matching SQLite to within one sample.
- [ ] Health page TPMS section renders four wheel slots; "NO DATA" grey before first frame; value updates within 2s of frame arrival via SSE.
- [ ] Bench-deflate one sensor below 25 PSI → Health page banner red + TTS speaks within 5s. Re-inflation above 28 PSI clears with `_RESTORED` suffix pattern.
- [ ] Bench-deflate one sensor by ≥5 PSI within 60s → `TPMS_LEAK` event in `events.json` + Health red + TTS speaks within 5s.
- [ ] Slow deflation (≤1 PSI/min) does **not** fire the leak alert.
- [ ] Disconnect one sensor for 5 minutes → Health page shows STALE for that wheel; reconnect clears STALE within one heartbeat (≤2s).
- [ ] Unplug RTL-SDR → Health page shows TPMS offline (MISSING) per Phase 21 supervisor pattern; daemon keeps running; replug restores within `HardwareSupervisor` backoff window.
- [ ] Driving UAT: short loop with all four sensors fitted; all four wheels appear in Grafana with values matching a stick-gauge reference (±3 PSI); intentionally deflate one tyre to below 28 PSI mid-loop and confirm the Health-page banner fires and TTS speaks.

## Ambiguity Report

| Dimension          | Score | Min   | Status | Notes                                                   |
|--------------------|-------|-------|--------|---------------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75  | ✓      | Two-axis goal (steady-state thresholds + leak rate) explicit |
| Boundary Clarity   | 0.85  | 0.70  | ✓      | In/out lists are concrete; OTA, antenna install, rtl_433 PR explicitly out |
| Constraint Clarity | 0.85  | 0.65  | ✓      | USB topology, install path, calibration accuracy bounds noted |
| Acceptance Criteria| 0.85  | 0.70  | ✓      | All criteria are pass/fail with measurable thresholds   |
| **Ambiguity**      | 0.13  | ≤0.20 | ✓      | Gate passed                                             |

## Interview Log

| Round | Perspective      | Question summary                            | Decision locked                                                                                          |
|-------|------------------|---------------------------------------------|----------------------------------------------------------------------------------------------------------|
| 1     | Researcher       | Driver alert surfaces                       | Dashboard banner + TTS spoken alert. No video event-trigger. Not telemetry-only.                          |
| 1     | Researcher       | Temperature data treatment                  | Capture, store, graph (no alerting yet).                                                                  |
| 1     | Researcher       | Stale-sensor timeout                        | 5 minutes silent → STALE warning.                                                                         |
| 2     | Simplifier       | Threshold model (single vs per-axle/wheel)  | Single threshold all wheels: 28 PSI yellow / 25 PSI red, configurable in YAML.                            |
| 2     | Simplifier       | Calibration approach                        | Single global × 2.45 correction in YAML config. No per-sensor table.                                      |
| 2     | Simplifier       | Storage cadence                             | Every frame written to SQLite (~14 MB/day).                                                               |
| 3     | Boundary Keeper  | Out-of-scope confirmation                   | rtl_433 PR, roof antenna install, OTA learn-mode all explicitly OUT. Leak detection STAYS IN.             |
| 3     | Boundary Keeper  | Missing-SDR behaviour                       | Graceful degrade per Phase 21: `tpms_radio` role, `criticality: best_effort`, supervisor handles re-adopt. |
| 3     | Boundary Keeper  | Done check (canonical UAT)                  | All four wheels in Grafana + Health-page banner + TTS UAT during a short driving loop.                    |
| 4     | Failure Analyst  | Leak detection definition                   | ≥5 PSI drop within 60s → CRITICAL: TTS + Health red + `TPMS_LEAK` event in events.json. No video trigger. |
| 4     | Failure Analyst  | Cold-start display state                    | All wheels show "NO DATA" grey until first frame arrives per wheel.                                       |

---

*Phase: 28-tpms-integration*
*Spec created: 2026-04-28*
*Next step: `/gsd-discuss-phase 28` — implementation decisions (how to build what's specified above)*
