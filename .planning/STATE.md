---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: — Rally Ready
status: unknown
stopped_at: Phase 26 context gathered — ready for /gsd-plan-phase 26
last_updated: "2026-04-23T02:26:00.823Z"
last_activity: 2026-04-23 -- Phase 26 execution started
progress:
  total_phases: 13
  completed_phases: 8
  total_plans: 46
  completed_plans: 45
  percent: 98
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-09)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Phase 26 — event-video-title-cards

## Current Position

Phase: 26 (event-video-title-cards) — EXECUTING
Plan: 1 of 4
  All 3 plans done:

    - 23-01: 18-VERIFICATION.md created (8 Phase 18 requirements satisfied)
    - 23-02: NARR-08b corrected in 19-VERIFICATION.md (stale BLOCKED → SATISFIED, score 11/11)
    - 23-03: REQUIREMENTS.md traceability refreshed (17 checkboxes + 19 rows flipped); ROADMAP.md Phase 21/22 rows updated
  23-VERIFICATION.md: 5/5 success criteria VERIFIED; one informational note re IMU-02 checkbox/table mismatch (pre-existing Phase 22 Pi UAT deferral, out of scope for this phase).

Phase: 22 (imu-signal-quality-and-rollover-detection-exploit-lsm6dsox-c) — COMPLETE
  7/7 plans; verified 2026-04-22 with deferred Pi UAT on IMU-02 sustained poll rate.

Phase: 21 (hardware-inventory-and-graceful-degradation) — COMPLETE
  5/5 plans; verified 2026-04-21. 4 REVIEW warnings (WR-01..WR-04) carried forward as hardening follow-ups, non-blocking.

Next: Phase 24 (Phase 20 Physical Integration Completion) waits on 3D prints; Phase 25 (Nyquist validation sweep) queued after 24.

Last activity: 2026-04-23 -- Phase 26 execution started

Progress: 8/13 phases complete (v2.0 milestone); v1.0 [██████████] 100%

v1.0 shipped: 9 phases, 27 plans, 2026-04-09

## Accumulated Context

### Decisions (carry-forward from v1.0)

- Offline-first SQLite with WAL — confirmed correct, never changing
- Batch sync over WireGuard — confirmed working (1,288 readings synced in 281ms in field test)
- Piper TTS over buzzer — confirmed better in car
- Escalating I2C reset (backoff before reboot) — eliminated crash-loops
- In-process FastAPI dashboard — no process coordination overhead, SSE clean
- LSM6DSOX+LIS3MDL now the active IMU pair on Pi 5 v2 hat
- DS18B20 probe IDs: exterior=28-00000024263a, engine_bay=28-0000002405b1
- SEN0460 (PM2.5) and INA226 default disabled — enable via config when wired
- Pi 5 IP: 10.10.20.107
- All new v2.0 tables (notes, fuel_stops, driver_stints, calibration) go into telemetry.db — no separate databases
- Touchscreen OSK deferred — USB keyboard required (Wayland/Chromium OSK unreliable on Pi 5)
- Cost data hard exclusion: fuel cost must never appear in sync payloads or on the website
- Plan 12-01: cost_aud stored in fuel_stops (nullable) but excluded from sync payloads at API layer (plan 12-02)
- Plan 12-01: no indexes added on notes/fuel_stops — low-write tables, add later if query patterns demand
- Plan 12-02: snapshot_fn injected into LogbookStorage for testability without hardware dependency
- Plan 12-02: generate_fuel_json enforces cost_aud exclusion at SQL SELECT level, not post-processing (D-10)
- Plan 12-04: LogbookStorage registered unconditionally in UnifiedEngine.__init__ — cheap, REST-only, idempotent; generators guarded on capture_sync not None
- Plan 12-04: gps_state.update_last_known_position co-located with existing lat/lng not-None guard in _record_telemetry
- Plan 13-01: Wave 0 test stubs use pytest.skip inside fixtures (not pytest.mark.xfail) — explicit skip reasons, clean collection
- Plan 13-01: v6 migration test assertions relaxed from == 6 to >= 6 after SCHEMA_VERSION bumped to 7
- Plan 13-03: SSE test drives async generator directly via asyncio.run() — Starlette TestClient portal.call() blocks on infinite generators, making HTTP-transport testing impossible
- Plan 13-03: sse.py migrated to EventSourceResponse + threading.Lock — required for correct slot management in mixed sync/async context
- Plan 13-03: register_json_generator uses 2-arg form (name, fn) — capture_sync derives filename as {name}.json automatically
- Plan 13-04: switchDriver() refreshes /api/driver/stats inline after POST — avoids stale modal table without requiring modal re-open
- Plan 13-04: activeDriver SSE field is nullable — null maps to '---' in top bar via Alpine x-text || fallback
- Plan 17-01: dashboard_push_event imported via try/except in thermal_monitor — mirrors buzzer/speaker pattern, graceful degradation when dashboard absent
- Plan 17-01: elif SensorType.TEMPERATURE branch in _on_reading uses last-write wins — DS18B20 and BME680 can coexist without coordination
- Plan 19-01: Iterative DP (stack-based) chosen over recursive for douglas_peucker -- handles 50k+ inputs without RecursionError
- Plan 19-01: tolerance_m=10.0 default kept -- 14-day synthetic rally produces 1,255 bytes (trivially under 1 MB budget)
- Plan 19-01: Sydney timezone as UTC+10 fixed offset -- QLD/NSW rally timing, no pytz/zoneinfo dep required
- Plan 19-02: Placeholder rally dates (27 May - 5 June 2026) used in agenda.json -- Brain doc shows rally postponed indefinitely; update before race day
- Plan 19-02: routeData declared and fetched alongside agendaData in same plan -- natural fit, Plan 19-03 consumers expect both
- Plan 19-03: safeHeader.textContent pattern used for XSS-safe day slug rendering in renderDayPage stub (T-19-03-01)
- Plan 19-03: Promise.allSettled replaces Plan 19-02 individual fetch chains for agenda/route -- router runs once both settle
- Plan 19-04: UTC Date object used in _formatShortDate -- calendar date field not a timestamp, prevents midnight-crossing TZ shifts
- Plan 19-04: future day-nav segments rendered as <span> not <a> -- pointer-events:none on <a> still focusable; <span> is inert and semantically correct
- Plan 19-04: highlightDayISO arg takes priority over today-comparison in renderDayNav -- explicit day-page highlight overrides calendar check
- Plan 19-06: stage bookends derived from first/last event of the day -- GPS motion transitions deferred as a future extension point (comment in buildSpine)
- Plan 19-06: PII guard comment in _spineFuelCard names cost_aud/price_aud explicitly to make the exclusion auditable -- comment is the mitigation trail (T-19-06-02)
- Plan 19-08: Rally start parsed as T00:00:00+10:00 (Sydney midnight) for countdown -- matches D-16 rally-day boundary
- Plan 19-08: _countdownTimer module-level ref + _stopCountdown() mirrors _teardownDayMap pattern -- prevents timer leak on SPA navigation

### Known Constraints for v2.0

- Phase 17 (Driver Display) depends on Phase 13 (active driver in SSE) and Phase 15 (undervoltage alerts)
- Phase 18 (Website) depends on Phase 12 (notes/fuel in sync payload) and Phase 13 (driver data)
- Phase 18 is in a separate repo (home-ops) and deploys via Flux — not the shitbox repo
- PWR-01 bitmask fix: read bits 0-3 only for current undervoltage, never bits 16-19 (sticky historical)
- CAL-01/CAL-02 can run in parallel with Phases 12-13 but must complete before Phase 17 is relied on for accuracy

### Blockers/Concerns

None.

### Roadmap Evolution

- Phase 21 added: hardware inventory and graceful degradation
- Phase 22 added: IMU signal quality and rollover detection — gyro-based rollover/yaw event, on-chip LPF2 + 208 Hz ODR with decimation, stationary auto-zero with tolerance-based rejection
- Phase 26 added (2026-04-23): event video title cards — cinematic title frame between intro clip and event footage (location, date, event badge) via Pillow PNG → ffmpeg loop → concat demuxer. SDK phase-add bug: returned phase_number 25 despite existing 25-milestone-v2-0-nyquist-validation-sweep; manually renamed dir and patched ROADMAP.md.

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 26 context gathered — ready for /gsd-plan-phase 26
Resume file: --resume-file

## Out-of-Band Hardware Work (2026-04-10)

Post-phase-13 session — hardware issues discovered and partially resolved during UAT.

### Hardware changes made

- **PSU replaced**: Official Raspberry Pi 5 PSU installed after full power brownout
- **I2C driver replaced**: Switched from i2c_designware (Pi 5 RP1 chip, buggy clock-stretch handling) to i2c-gpio bit-bang driver. config.txt change: `#dtparam=i2c_arm=on` disabled, `dtoverlay=i2c-gpio,bus=1,i2c_gpio_sda=2,i2c_gpio_scl=3` added. All sensors confirmed present on bit-bang bus 1 via i2cdetect.
- **Display boot race**: Still intermittent. DSI-1 entry removed from cmdline.txt previously but race returned. Suspect `display_auto_detect=1` in config.txt probing absent DSI-1. Next step: set `display_auto_detect=0`.

### Sensors confirmed on bit-bang i2c-1 (i2cdetect -y 1)

- 0x10 — VEML7700
- 0x1c — LIS3MDL
- 0x3c — OLED
- 0x40 — INA226
- 0x6a — LSM6DSOX
- 0x77 — BME680 (present on bus but failing to init at daemon startup — timing issue, needs retry on setup or delayed init)

### Code fixes committed (ae7676f, branch gsd/phase-13-driver-tracking)

1. **sampler.py**: Added `if self._lsm6dsox is None: raise OSError(...)` guard before read — routes None sensor into existing OSError recovery path instead of flooding log at 100Hz with AttributeError
2. **temperature.py**: Added `SensorNotReadyError` retry (150ms sleep, one retry) — DS18B20 needs up to 750ms to convert at 12-bit, 1Hz polling was occasionally catching it mid-conversion
3. **light.py**: Fixed VEML7700 using hardcoded `busio.I2C(1, 2)` — changed to `board.SCL/board.SDA` to work with bit-bang bus. Added `board` import alongside `busio`.

### Outstanding issues

- **BME680 (0x77) not initialising**: Physically present (confirmed i2cdetect), but daemon logs `No I2C device at address: 0x77` at startup. Likely a boot timing issue — sensor not ready when daemon starts. Fix options: add retry loop in EnvironmentCollector.setup(), or add a startup delay. Dashboard shows `--` for CABIN TEMP as a result.
- **CPU temp 70.5°C at idle**: Hitting warning threshold. May need airflow improvement.
- **RPi.GPIO on Pi 5**: The existing 9-clock bit-bang I2C recovery in sampler._i2c_bus_reset() uses RPi.GPIO which is not officially supported on Pi 5 — recovery calls likely silently fail. Not critical now that bit-bang bus is stable, but worth replacing with lgpio if lockups recur.
- **DS18B20 errors**: Still appearing but should reduce with retry fix. Both probes intermittently not ready.

**Planned Phase:** 26 (Event Video Title Cards) — 4 plans — 2026-04-23T01:27:56.715Z
