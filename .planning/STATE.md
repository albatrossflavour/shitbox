---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: — Rally Ready
status: executing
stopped_at: Completed 19-05-PLAN.md
last_updated: "2026-04-16T13:04:13.524Z"
last_activity: 2026-04-16
progress:
  total_phases: 9
  completed_phases: 4
  total_plans: 27
  completed_plans: 20
  percent: 74
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-09)

**Core value:** Never lose telemetry data or video — the system must survive thousands of kilometres
of rough roads, power cycles, heat, and vibration without human intervention.
**Current focus:** Phase 19 — website-narrative-rebuild

## Current Position

Phase: 19 (website-narrative-rebuild) — EXECUTING
Plan: 6 of 12
Status: Ready to execute
Last activity: 2026-04-16

Progress: [██████████] 100% (v2.0, 4/4 plans in phase 12)

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

### Known Constraints for v2.0

- Phase 17 (Driver Display) depends on Phase 13 (active driver in SSE) and Phase 15 (undervoltage alerts)
- Phase 18 (Website) depends on Phase 12 (notes/fuel in sync payload) and Phase 13 (driver data)
- Phase 18 is in a separate repo (home-ops) and deploys via Flux — not the shitbox repo
- PWR-01 bitmask fix: read bits 0-3 only for current undervoltage, never bits 16-19 (sticky historical)
- CAL-01/CAL-02 can run in parallel with Phases 12-13 but must complete before Phase 17 is relied on for accuracy

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-04-16T13:04:13.520Z
Stopped at: Completed 19-05-PLAN.md
Resume file: None

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
