# Milestones

## v1.0 Operational Hardening (Shipped: 2026-04-09)

**Phases completed:** 9 phases, 27 plans, 48 tasks

**Key accomplishments:**

- One-liner:
- BootRecoveryService wired into UnifiedEngine.start() with WAL-based crash detection, recovery-specific buzzer tones, get_status() recovery fields, and a best-effort Prometheus boot metric
- Systemd unit hardened with WatchdogSec=10 and unlimited restarts via StartLimitIntervalSec=0; five 330 Hz failure alert functions added to buzzer.py with 5-minute escalation tracking and 30-second boot grace period suppression
- Mtime+size-based ffmpeg stall detection in VideoRingBuffer health monitor with 30-second timeout, startup grace, and buzzer alert on frozen output
- 9-clock SCL bit-bang I2C recovery in HighRateSampler with GPIO3, selective cleanup, MPU6050 reinit, reboot fallback, and buzzer alerting
- One-liner:
- ThermalMonitorService daemon thread with 5C hysteresis alerts at 70/80C, throttle decode on bitmask change, and 5-minute WAL TRUNCATE checkpoint wired into engine lifecycle
- Schema v4 migration with health columns, HealthCollector assembling CPU temp/disk/backlog/throttle into Prometheus metrics
- Database helpers (4):
- Engine and thermal monitor wired with Piper TTS spoken announcements for boot, crash recovery, waypoints, distance milestones, and all thermal alert events alongside existing buzzer tones
- Escalating I2C bus reset with 3-attempt backoff ([0,2,5]s) before forced reboot, eliminating the crash-loop that produced ~7 PIDs in 3 minutes during field testing
- Speaker worker thread watchdog added to _health_check() with cleanup()+init() reinit, plus

TTS and buzzer recovery confirmation announcements after all subsystem recoveries (HEAL-01 and
HEAL-03).

- beep_capture_failed() + speak_capture_failed() alert functions added, and 10 RED-phase TDD tests created covering post-save verification (CAPT-01), timelapse gap watchdog (CAPT-02), and boot guard with partial saves (CAPT-03)
- Post-save verification, timelapse gap watchdog, and boot save guard implemented in ring_buffer.py and engine.py — all 10 capture integrity tests pass
- Failing test scaffolds for the dashboard surface and tile downloader, covering snapshot, SSE streams, MBTiles y-flip, and corridor maths — every Wave 1+ implementation task now has a pre-existing automated check.
- Backfilled tests/test_download_tiles.py
- Operator kiosk smoke test passed: all visual, interaction, capture-path, and failure-mode checks verified on Pi hardware
- Coloured L.circleMarker placed on Leaflet map in openEvents() for every SSE event with GPS coordinates, closing D-21
- Six failing test stubs covering LSM6DSOX sampler, IMU heading filter, DS18B20 dual-probe, VEML7700, SEN0460, and INA226 — wave 0 RED phase complete, concrete DS18B20 IDs and ELP VID:PID recorded from Pi 5
- LSM6DSOX replaces MPU6050 with explicit m/s2-to-g and rad/s-to-deg/s conversion; new IMUHeadingCollector fuses LSM6DSOX and LIS3MDL via complementary filter for standstill heading (D-12)
- DS18B20 dual-probe 1-Wire collector, VEML7700 lux collector, SEN0460 PM2.5 stub (disabled), and INA226 power monitor (disabled) — four wave-0 RED tests turned green, MCP9808 and INA219 deleted
- config/config.yaml
- Commit:

---
