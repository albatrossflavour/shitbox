# Phase 11: v2 Hardware Migration - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Rewrite the sensor layer of the codebase to match the v2 hat build: delete dead v1
collectors, add new v2 sensors, swap the IMU stack, and replace the front camera
wiring. Code-only phase — the physical cutover from old Pi to new Pi is explicitly
out of scope and will be handled separately.

The canonical hardware definition is the brain note
`~/Brain/projects/shitbox-rally-2026.md` (§ "V2 — Telemetry system rebuild").
This phase makes the code match that note, with a handful of corrections captured
below.

### In scope

- Delete dead sensor code and the associated config entries
- Add new sensor collectors wired up to SQLite and existing telemetry paths
- Full IMU swap (MPU6050 → LSM6DSOX + LIS3MDL) including event detection
- Artificial-horizon + heading computation from the new IMU + magnetometer
- Replace UGREEN front camera with ELP 4K (udev rules, camera controls, video pipeline)
- Dead-code cleanup items called out in the brain note
- Fix `pyproject.toml` sensor lib mismatches
- Update `config/config.yaml` to the v2 sensor set, with unpowered sensors present-but-disabled

### Out of scope (explicit)

- **Physical cutover from old Pi to new Pi** — separate op, tracked as a todo
- **Power monitoring** — INA226 collector can exist but stays disabled in config
  (shunt wiring deferred per brain note)
- **Driver display / touchscreen UI** — that's Phase 6 (deferred to v2) or its own phase
- **Storage enhancements** (STOR-02..04) — separate v2 scope
- **Resilience enhancements** (RSLN-01..03) — separate v2 scope
- **New features from brain "New features for v2"** beyond sensors: photo capture,
  night mode, route replay, trip segments, low-battery shutdown, Pi 5 hardware watchdog

</domain>

<decisions>
## Implementation Decisions

### Sensor inventory (code targets)

- **D-01:** **IMU:** LSM6DSOX at 0x6A (accel + gyro, 100 Hz sampler) + LIS3MDL at 0x1C
  (magnetometer). Replaces MPU6050. Existing event detector (HARD_BRAKE, BIG_CORNER,
  HIGH_G, ROUGH_ROAD) must run against the new accel/gyro source without regression.
- **D-02:** **Environment:** Keep **BME680 at 0x77**. The brain note contains a
  BME680/BME280 contradiction — BME680 wins, BME280 references in the brain note are
  stale and should be removed when the brain note is updated. Fix `pyproject.toml` to
  depend on `adafruit-circuitpython-bme680` (not `-bme280`, which was a prior mistake).
- **D-03:** **Temperature:** 2× DS18B20 on 1-Wire (GPIO 4, with 4.7kΩ pull-up).
  Semantic roles: **exterior** + **engine bay**. Collector reads both by 1-Wire ID
  and stores under those logical names. MCP9808 collector deleted entirely.
- **D-04:** **Ambient light:** VEML7700 at 0x10. New collector, low-rate (1 Hz or
  slower). Stored raw for now; no consumers wired up in this phase.
- **D-05:** **Particulate (PM2.5):** SEN0460 at 0x19. Collector written, ships with
  `enabled: false` in config (rail not powered yet, same treatment as INA226).
  **Cable gotcha documented in the collector:** our Gravity 4-pin cable has SDA/SCL
  swapped — red=VCC(5V), black=GND, **cyan=SDA, blue=SCL**.
- **D-06:** **Power:** INA226 at 0x40. Collector written, ships with `enabled: false`.
  Existing INA219 collector deleted.
- **D-07:** **OLED (SSD1306 0x3C):** Optional — present on the new Pi's bus but
  "optional, not wired in v2 unless needed" per brain note. Existing OLED code stays,
  wired to config flag. Graceful degradation if absent.
- **D-08:** **Buzzer:** This is the **same physical buzzer** as v1 (brain note's
  "PiicoDev piezo buzzer — NEW for v2" framing is wrong). No new integration work —
  keep existing `capture/buzzer.py` as-is, just verify it runs on the new Pi. No
  rewiring of existing `beep_*` alert paths.

### IMU + magnetometer scope

- **D-09:** `events/sampler.py` rewritten for LSM6DSOX. Use `adafruit-circuitpython-lsm6ds`
  (researcher to confirm exact lib name and FIFO API). Calibration offsets move
  from MPU6050 config keys to new LSM6DSOX keys. The new chip has a better noise
  floor and built-in FIFO — planner should consider whether to use the FIFO for
  burst reads vs the existing per-sample loop.
- **D-10:** New magnetometer collector (or sampler path) reads LIS3MDL at the
  appropriate rate for heading computation.
- **D-11:** **Artificial horizon + heading** — full complementary filter fusing
  LSM6DSOX accel + gyro + LIS3MDL mag. Outputs pitch, roll, and tilt-compensated
  heading into SQLite. No UI consumer in this phase — the numbers just need to be
  computed and stored so later phases (dashboard, driver display) can read them.
- **D-12:** Heading is available at standstill (the whole point of adding the mag)
  and fills in during GPS shadow. This is a correctness requirement, not a nice-to-have.

### Camera

- **D-13:** **Front camera:** ELP 4K USB (IMX317). Capture at **1080p MJPEG**. New
  udev rule pointing `/dev/camera-front` at the ELP by vendor/product ID. Camera
  controls (`camera_controls` in config) retuned for the ELP — existing UGREEN
  controls deleted. Researcher to check Pi 5 CPU headroom with real-time PiP encode
  at 1080p (brain note flagged this as an open question).
- **D-14:** **Cabin camera:** Brio 100 unchanged. Existing config and udev rule kept.

### Dead code cleanup (bundled into this phase)

- **D-15:** Delete `src/shitbox/capture/pip_compositor.py` entirely.
- **D-16:** Delete `src/shitbox/collectors/power.py` (INA219) and rewrite as INA226.
- **D-17:** Delete the MCP9808 collector / any dedicated MCP9808 code in
  `collectors/temperature.py`. Temperature collector becomes 1-Wire only.
- **D-18:** Remove the MPU6050 sampler path from `events/sampler.py` — no dual-sensor
  fallback.
- **D-19:** Remove dead `import os` and unused `_nice` lambda from
  `events/ring_buffer.py`.
- **D-20:** Fix `_event_json_paths` dict thread-safety bug called out in brain note
  (two threads access without a lock).
- **D-21:** Fix `capture_sync._do_sync()` blocking the telemetry loop synchronously —
  background it (or confirm it's already handled by another phase; verify in research).
- **D-22:** Fix `pyproject.toml` sensor dependency list end-to-end: remove
  `adafruit-circuitpython-bme280`, ensure `adafruit-circuitpython-bme680`,
  `adafruit-circuitpython-lsm6ds`, `adafruit-circuitpython-lis3mdl`,
  `adafruit-circuitpython-veml7700`, `adafruit-circuitpython-ina226` are present.
  `w1thermsensor` for DS18B20. SEN0460 likely needs DFRobot's own lib — researcher
  to pick the approach (vendored driver vs PyPI).

### Config and graceful degradation

- **D-23:** `config/config.yaml` rewritten to the v2 sensor set. Unpowered sensors
  (INA226, SEN0460) ship with `enabled: false`. OLED stays `enabled: false` unless
  wired. Button 17 stays present (code-wise) — the hat build note says it's unwired
  but the GPIO pin and collector stay in the codebase so flipping it on is a
  config + wiring change, not a code change.
- **D-24:** **Graceful hardware degradation** is a non-negotiable. Any new collector
  must fail cleanly if its sensor is absent (I2C NACK, missing 1-Wire device, etc.)
  without taking the engine down. Follow the existing `base.BaseCollector` pattern.
- **D-25:** Add a `Canonical hardware reference:` comment at the top of
  `config/config.yaml` pointing at `~/Brain/projects/shitbox-rally-2026.md`. Code
  stays slim; brain note is the source of truth for wiring, addresses, and intent.

### Brain note corrections (to be fixed in brain note, not code)

- **D-26:** Remove BME280 references from the v2 hardware section (keep BME680 only).
- **D-27:** Stop describing the PiicoDev buzzer as "new for v2" — it's carried over
  from v1.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Hardware definition (source of truth)

- `~/Brain/projects/shitbox-rally-2026.md` §§ "V2 — Telemetry system rebuild",
  "Hardware", "Terminal block wiring", "New features for v2", "Known issues to fix
  in v2" — authoritative hardware list, wiring, addresses, and open questions.
  Note the two brain-note corrections in D-26 and D-27 above.
- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/project_pi5_setup.md` —
  current state of the new Pi 5 build: confirmed i2c addresses, known-offline
  sensors, boot hang fix, and the "services stopped pending cutover" constraint.
- `~/.claude/projects/-Users-tgreen-dev-shitbox/memory/project_power_budget.md` —
  power draw tracking; flag new subsystems that add meaningful load.

### Project-level

- `.planning/PROJECT.md` — offline-first principles, graceful hardware degradation
  as a non-negotiable.
- `.planning/REQUIREMENTS.md` § "v2 Requirements" — DISP/STOR/RSLN lists (all
  out of scope for this phase but note they exist).
- `CLAUDE.md` § "Adding a New Service (Pattern)" — collector pattern this phase's
  new collectors should follow.

### Code entry points (existing)

- `src/shitbox/collectors/base.py` — abstract base collector, template method
- `src/shitbox/collectors/environment.py` — BME680 collector (stays, verify)
- `src/shitbox/collectors/temperature.py` — MCP9808 (delete), rewrite as DS18B20
- `src/shitbox/collectors/power.py` — INA219 (delete), rewrite as INA226
- `src/shitbox/events/sampler.py` — MPU6050 sampler (rewrite for LSM6DSOX + mag)
- `src/shitbox/events/detector.py` — event state machine (must continue to work)
- `src/shitbox/events/ring_buffer.py` — dead imports/lambdas to clean up
- `src/shitbox/capture/video.py`, `src/shitbox/capture/buzzer.py`,
  `src/shitbox/capture/ring_buffer.py` — camera and alerts, mostly unchanged
- `src/shitbox/capture/pip_compositor.py` — delete entirely
- `src/shitbox/utils/config.py` — dataclass layout, add/remove sensor configs here
- `config/config.yaml` — v2 rewrite with canonical brain note reference

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- `BaseCollector` template (daemon thread, `sleep(interval)` + `collect()` hook) —
  every new collector (DS18B20, VEML7700, SEN0460, INA226, LIS3MDL) follows this.
- `EventStorage` / `Database` (SQLite WAL with write locks) — sensor readings go
  here via the existing `collectors.base` plumbing; no schema rewrite needed beyond
  new column sets / tables for new sensor types.
- `UnifiedEngine` lifecycle (`src/shitbox/events/engine.py`) — start/stop pattern
  for every subsystem. New collectors wire in the same way as Phase 10 services.
- `capture/buzzer.py` — preserved as-is per D-08. Existing `beep_*` helpers keep
  working against the same physical buzzer.

### Established patterns

- **Config dataclasses** with `enabled: bool` flag on each subsystem — use this for
  INA226 and SEN0460 to ship "present but disabled".
- **Graceful degradation on bus absence** — current `environment.py` and
  `temperature.py` already handle missing I2C devices; keep that behaviour.
- **Structured logging** via `structlog` with keyword args. Every new collector
  should emit `sensor_init`, `sensor_read`, `sensor_error` events.

### Integration points

- `events/engine.py` wires collectors into the main engine lifecycle — new
  collectors register here.
- `utils/config.py` nested dataclasses loaded from YAML — add new sections here.
- `pyproject.toml` optional deps — all sensor libs declared here.

</code_context>

<specifics>
## Specific Ideas

- Brain note is treated as the canonical hardware spec. Code comments point to it
  rather than duplicating the table in the repo.
- DS18B20 probes have fixed semantic roles (exterior, engine bay). The 1-Wire IDs
  should be mapped to roles in config, not discovered dynamically, so swapping a
  probe requires a config change (visible, intentional).
- SEN0460 cable pinout gotcha (red/black/cyan/blue with SDA/SCL swapped from the
  DFRobot standard colour code) is called out in the brain note and must be
  documented in the collector's module docstring so future-Tony doesn't rewire
  blind.
- Artificial horizon + heading output is stored in SQLite now even though no UI
  consumes it yet — downstream phases (driver display, dashboard) will read it.

</specifics>

<deferred>
## Deferred Ideas

- **Physical cutover from old Pi to new Pi** — not in this phase. Separate op, probably
  manual, tracked as a todo: stop old Pi services → start new Pi services → keep
  Prometheus labels identical so history stays continuous.
- **INA226 wiring + battery SoC tracking** — shunt wiring deferred per brain note,
  coulomb counting / SoC lookup is a later feature.
- **PM2.5 rail wiring** — SEN0460 code ships disabled until the 5V rail is wired.
- **Button 17 wiring** — code stays, button is unwired in hardware build per memory note.
- **Driver display / touchscreen UI (DISP-01..03)** — its own phase (formerly Phase 6,
  deferred to v2).
- **Tilt/roll artificial horizon UI** — the numbers get computed in this phase, but
  the on-screen display is a later phase.
- **Photo capture from button/touchscreen** — v2 brain note feature, separate phase.
- **Night mode camera switching via VEML7700** — the light sensor is read in this
  phase but no consumers are wired up.
- **ELP camera 1080p headroom validation** — flagged as an open question in the brain
  note; researcher should at least sanity-check it during RESEARCH.md so planning can
  adjust if the Pi 5 can't keep up.
- **Low-battery graceful shutdown (INA226 voltage watchdog at 11.5V)** — deferred.
- **Pi 5 hardware watchdog via systemd** — separate phase (RSLN-adjacent).
- **capture_sync background refactor (D-21)** — if researcher finds another phase
  already handled this, drop it from scope; otherwise it stays.

</deferred>

---

*Phase: 11-v2-hardware-migration*
*Context gathered: 2026-04-09*
