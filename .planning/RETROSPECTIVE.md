# Retrospective: Shitbox Rally Telemetry

---

## Milestone: v1.0 — Operational Hardening

**Shipped:** 2026-04-09
**Phases:** 9 | **Plans:** 27 | **Tasks:** 48

### What Was Built

- Boot recovery with WAL crash detection and orphan event closure
- Systemd hardening + hardware watchdog; ffmpeg stall detection; 9-clock I2C bit-bang recovery
- Thermal monitor (70/80°C alerts, throttle decode, WAL TRUNCATE checkpoint)
- Health collector (CPU temp, disk %, sync backlog, throttle state to Prometheus)
- GPS distance tracking, daily odometer, waypoint detection for rally stage progress
- Piper TTS replacing buzzer tones — contextual spoken alerts for all system events
- Escalating I2C crash-loop prevention (3-attempt backoff before reboot)
- Speaker watchdog with auto-reinit and recovery confirmation TTS
- Capture integrity: post-save MP4 verification, timelapse gap watchdog, boot save guard
- Live in-process FastAPI dashboard: three SSE streams, MBTiles offline map, Alpine/Tailwind/Leaflet frontend
- V2 hardware migration: LSM6DSOX+LIS3MDL IMU, DS18B20 dual-probe, VEML7700, INA226, ELP 4K camera

### What Worked

- TDD (RED → GREEN) gave confidence on hardware-adjacent code that can't easily be tested on Pi — especially the I2C recovery, capture integrity, and SSE rate tests
- Inserting phases as needed (10, 11) without derailing the milestone flow
- Smoke test checkpoint (plan 10-05) catching the D-21 map markers omission before closing the phase — worth the friction
- V2 hardware migration as a discrete phase kept the sensor rewrite clean and testable

### What Was Inefficient

- Phase 9 (Sync Reliability) was scoped based on field-test symptoms but was already largely fixed by prior work — could have been caught with a shorter investigation before full planning
- Some summaries (11-03, 11-04) have thin one-liners that don't describe the actual work — limits future context recall
- The HLTH-01 requirement (Prometheus metrics) was marked complete in planning but never confirmed end-to-end — left as a known gap

### Patterns Established

- Hardware sensor stubs follow `busio.I2C` over `smbus2` for test patchability
- Collector constructors use `(config, callback)` signature consistently
- SSE test isolation: drain `event_queue` + reset `_recent_provider` before each test to avoid module-level state bleed
- `EVENT_COLOURS` scoped inside JS methods (not Alpine reactive data) to keep the reactive object clean
- Checkpoint plans (`autonomous: false`) as human gates before closing UI/hardware phases

### Key Lessons

- Field-test evidence is the most reliable source of requirements — the v1.1 scope was shaped entirely by one test drive log
- Crash-looping deserved to be addressed before capture integrity — the root cause order matters
- The dashboard phase needed a smoke test gate; don't skip human verification for anything with a visual component
- Platform: Pi 5 is meaningfully different from Pi 4 — the v2 hardware migration was the right call before shipping

### Cost Observations

- Model mix: opus for planning, sonnet for execution/verification
- Sessions: multiple across 70 days
- Notable: regression gate (running full test suite after each wave) caught no regressions — the test suite isolation was solid

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Duration | Key challenge |
|-----------|--------|-------|----------|---------------|
| v1.0 Operational Hardening | 9 | 27 | 70 days | I2C crash-loop root cause; hardware migration mid-milestone |
