# Phase 11: v2 Hardware Migration - Research

**Researched:** 2026-04-09
**Domain:** Sensor drivers, IMU signal processing, complementary filter, camera encoding, dead-code audit
**Confidence:** MEDIUM-HIGH (library APIs verified via PyPI/GitHub; Pi 5 encode headroom MEDIUM due to no exact dual-stream benchmark available)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** IMU: LSM6DSOX at 0x6A (accel + gyro, 100 Hz) + LIS3MDL at 0x1C (magnetometer). MPU6050 deleted.
- **D-02:** Environment: keep BME680 at 0x77. Fix pyproject to use `adafruit-circuitpython-bme680` (not bme280).
- **D-03:** Temperature: 2x DS18B20 on 1-Wire (GPIO 4). Semantic roles: exterior + engine_bay. MCP9808 deleted.
- **D-04:** Ambient light: VEML7700 at 0x10. 1 Hz. No consumers this phase.
- **D-05:** PM2.5: SEN0460 at 0x19. Write collector, ships `enabled: false`. Cable pinout gotcha documented.
- **D-06:** Power: INA226 at 0x40. Write collector, ships `enabled: false`. INA219 collector deleted.
- **D-07:** OLED (SSD1306 0x3C): existing code kept, wired to config flag, graceful degradation.
- **D-08:** Buzzer: same physical buzzer as v1. Keep `capture/buzzer.py` as-is.
- **D-09:** `events/sampler.py` rewritten for LSM6DSOX using `adafruit-circuitpython-lsm6ds`. No dual-sensor fallback.
- **D-10:** LIS3MDL magnetometer collector at appropriate rate for heading computation.
- **D-11:** Artificial horizon + heading via complementary filter from LSM6DSOX + LIS3MDL. Outputs pitch, roll, heading into SQLite.
- **D-12:** Heading available at standstill (correctness requirement, not nice-to-have).
- **D-13:** Front camera: ELP 4K USB (IMX317). 1080p MJPEG. New udev rule. UGREEN controls deleted.
- **D-14:** Cabin camera: Brio 100 unchanged.
- **D-15:** Delete `src/shitbox/capture/pip_compositor.py` entirely.
- **D-16:** Delete `collectors/power.py` (INA219). Rewrite as INA226.
- **D-17:** Delete MCP9808 from `collectors/temperature.py`. Rewrite as 1-Wire only.
- **D-18:** Remove MPU6050 path from `events/sampler.py`.
- **D-19:** Remove dead `import os` and unused `_nice` lambda from `events/ring_buffer.py`.
- **D-20:** Fix `_event_json_paths` dict thread-safety bug.
- **D-21:** Fix or confirm `capture_sync._do_sync()` blocking — researcher to verify.
- **D-22:** Fix `pyproject.toml` sensor dep list end-to-end.
- **D-23:** `config/config.yaml` rewritten for v2 sensor set.
- **D-24:** Graceful hardware degradation: every new collector must fail cleanly if sensor is absent.
- **D-25:** Add canonical hardware reference comment at top of `config/config.yaml`.
- **D-26/D-27:** Brain note corrections (BME280 ref removal, buzzer framing fix) — code follows brain note, not the other way round.

### Claude's Discretion

- Event detection tuning on new LSM6DSOX (noise floor differs from MPU6050).
- Whether to use LSM6DSOX FIFO for burst reads vs the existing per-sample poll loop.
- Exact lib choice for SEN0460 (DFRobot vendor driver vs PyPI alternative).
- Whether D-21 (`capture_sync._do_sync()` backgrounding) is already handled.

### Deferred Ideas (OUT OF SCOPE)

- Physical cutover from old Pi to new Pi
- INA226 wiring + battery SoC tracking
- PM2.5 rail wiring (SEN0460 collector ships disabled)
- Button 17 wiring (code stays, hardware unwired)
- Driver display / touchscreen UI
- Tilt/roll artificial horizon UI consumers
- Photo capture, night mode, route replay, trip segments
- Low-battery graceful shutdown via INA226
- Pi 5 hardware watchdog via systemd
</user_constraints>

---

## Summary

This phase rewrites the sensor layer of the Shitbox codebase to match the v2 Pi 5 hat build. The work has three clusters: (1) sensor swaps with net-new collectors (LSM6DSOX+LIS3MDL replacing MPU6050, DS18B20 replacing MCP9808, plus VEML7700/SEN0460/INA226 new additions), (2) artificial horizon and tilt-compensated heading computed from the new IMU+mag via complementary filter, and (3) dead-code cleanup plus camera config update for the ELP 4K.

The good news is that the Adafruit CircuitPython ecosystem covers most of the new sensors cleanly -- LSM6DSOX, LIS3MDL, VEML7700, and BME680 all have maintained PyPI packages with clean Python APIs following the same `board.I2C() + SensorClass(i2c)` pattern. The exceptions are the two disabled sensors: SEN0460 has no PyPI package (vendor driver only, should be vendored), and INA226 has no official Adafruit CircuitPython package (use the `pi-ina226` smbus-based library from GitHub, which has a setup.py but is not on PyPI -- recommend vendoring a thin smbus2 wrapper instead for consistency).

One significant finding: `capture_sync._do_sync()` is already properly backgrounded in its own daemon thread. The D-21 item is confirmed resolved by prior phases and should be dropped from scope.

**Primary recommendation:** Keep the existing per-sample polling loop for the LSM6DSOX sampler (FIFO offers marginal benefit at 100 Hz on a Pi 5 quad-core ARM, and the library has no FIFO API anyway). Implement complementary filter in the sampler thread itself at 100 Hz for pitch/roll, then downsample to the magnetometer's natural rate (10-20 Hz) for heading update.

---

## Standard Stack

### Core Sensor Libraries

| Library | Version (PyPI) | Purpose | Notes |
|---------|---------------|---------|-------|
| `adafruit-circuitpython-lsm6ds` | 4.6.2 | LSM6DSOX accel+gyro | Covers LSM6DS family; import from `adafruit_lsm6ds.lsm6dsox` |
| `adafruit-circuitpython-lis3mdl` | 1.2.7 | LIS3MDL magnetometer | XYZ in microteslas via `.magnetic` |
| `adafruit-circuitpython-bme680` | 3.7.15 | BME680 environment | Already in use; fix pyproject ref |
| `adafruit-circuitpython-veml7700` | 2.2.1 | VEML7700 ambient light | `.lux` property |
| `w1thermsensor` | 2.3.0 | DS18B20 1-Wire temps | Read by sensor ID |
| `smbus2` | existing | INA226 + SEN0460 raw I2C | Already a dep; use for vendored drivers |

### Libraries to Remove

| Library | Remove | Reason |
|---------|--------|--------|
| `adafruit-circuitpython-mcp9808` | yes | MCP9808 deleted (D-17) |
| `adafruit-circuitpython-ina219` | yes | INA219 deleted (D-16) |

### No-PyPI Sensors (Vendor Driver Pattern)

| Sensor | Approach | Reason |
|--------|----------|--------|
| SEN0460 (PM2.5) | Vendor driver vendored in `src/shitbox/collectors/_vendor/dfrobot_airquality.py` | No PyPI package; DFRobot's official Python lib lives in `python/raspberrypi` on GitHub with no pip release |
| INA226 | Thin smbus2 wrapper written in-tree (`src/shitbox/collectors/power.py`) | No official Adafruit CircuitPython INA226 package on PyPI; `pi-ina226` (GitHub only, no PyPI) works but adds a non-PyPI git dep; writing ~40 lines of smbus2 direct is cleaner and consistent |

**Installation for production:**
```bash
pip install -e ".[dev]"
# After pyproject.toml changes — new packages resolve automatically
```

**Verify current versions:**
```bash
pip index versions adafruit-circuitpython-lsm6ds
pip index versions adafruit-circuitpython-lis3mdl
pip index versions adafruit-circuitpython-veml7700
pip index versions w1thermsensor
```

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
src/shitbox/collectors/
├── temperature.py          # REWRITE: DS18B20 1-Wire (replaces MCP9808)
├── power.py                # REWRITE: INA226 thin smbus2 driver (replaces INA219)
├── light.py                # NEW: VEML7700 ambient light
├── particulate.py          # NEW: SEN0460 PM2.5 (ships enabled:false)
└── _vendor/
    └── dfrobot_airquality.py   # VENDORED: DFRobot I2C driver (no PyPI package)

src/shitbox/events/
├── sampler.py              # REWRITE: LSM6DSOX + complementary filter
└── ring_buffer.py          # CLEANUP: remove dead import os + _nice lambda
```

### Pattern 1: Adafruit CircuitPython Sensor (LSM6DSOX, LIS3MDL, VEML7700)

All three follow the same init pattern. Use this as the template:

```python
# Source: Adafruit CircuitPython LSM6DS GitHub - simpletest.py
import board
import busio
from adafruit_lsm6ds.lsm6dsox import LSM6DSOX
from adafruit_lsm6ds import Rate

i2c = busio.I2C(board.SCL, board.SDA)
sensor = LSM6DSOX(i2c)

# Default data rate is Rate.RATE_104_HZ — close enough to 100 Hz target
# accel_x, accel_y, accel_z = sensor.acceleration  # m/s²
# gx, gy, gz = sensor.gyro                         # rad/s
```

**Key point:** `acceleration` returns m/s², not g. The existing `IMUSample` fields are in g, so the sampler must divide by 9.81. `gyro` returns rad/s; existing fields are deg/s, so multiply by 180/pi.

### Pattern 2: LSM6DSOX Rate Configuration

```python
# Source: Adafruit LSM6DS __init__.py - Rate enum
from adafruit_lsm6ds import Rate

sensor.accelerometer_data_rate = Rate.RATE_104_HZ  # 104 Hz (closest to 100 Hz)
sensor.gyro_data_rate = Rate.RATE_104_HZ

# Available rates: RATE_SHUTDOWN, RATE_12_5_HZ, RATE_26_HZ, RATE_52_HZ,
# RATE_104_HZ, RATE_208_HZ, RATE_416_HZ, RATE_833_HZ, RATE_1_66K_HZ,
# RATE_3_33K_HZ, RATE_6_66K_HZ, RATE_1_6_HZ
# Default is RATE_104_HZ -- no explicit set needed
```

**FIFO decision:** There is no FIFO API in `adafruit-circuitpython-lsm6ds`. The library is property-based polling only. The existing per-sample loop approach is the correct pattern for this library.

### Pattern 3: LIS3MDL Magnetometer

```python
# Source: Adafruit LIS3MDL GitHub - simpletest.py
from adafruit_lis3mdl import LIS3MDL

sensor = LIS3MDL(i2c)
mx, my, mz = sensor.magnetic  # microteslas (µT)
```

The LIS3MDL default output data rate is 10 Hz. Running it in a separate collector thread at 10 Hz, then passing the latest mag reading into the complementary filter when needed, is the right approach.

### Pattern 4: DS18B20 via w1thermsensor

```python
# Source: w1thermsensor GitHub README - v2.x API
from w1thermsensor import W1ThermSensor, Sensor, NoSensorFoundError, SensorNotReadyError

# Read specific sensor by ID (IDs come from config)
try:
    sensor = W1ThermSensor(sensor_type=Sensor.DS18B20, sensor_id="00000588806a")
    temp_c = sensor.get_temperature()
except NoSensorFoundError:
    log.warning("ds18b20_sensor_not_found", sensor_id="00000588806a")
except SensorNotReadyError:
    log.warning("ds18b20_sensor_not_ready", sensor_id="00000588806a")

# Enumerate all available sensors (used once at startup for ID discovery logging)
for s in W1ThermSensor.get_available_sensors([Sensor.DS18B20]):
    log.info("ds18b20_found", sensor_id=s.id)
```

**Kernel prerequisite:** `/boot/firmware/config.txt` must have `dtoverlay=w1-gpio` (default pin GPIO4). The Pi 5 memory confirms two DS18B20 probes are already detected and reading.

### Pattern 5: Complementary Filter (Pitch/Roll/Heading)

Run inside the 100 Hz sampler loop. The magnetometer runs at 10 Hz (a shared `threading.Lock`-protected variable, updated by the LIS3MDL collector, read by the sampler).

```python
import math

# State (initialise once)
pitch = 0.0  # radians
roll = 0.0   # radians

ALPHA = 0.98  # gyro weight; higher = trust gyro more, lower = trust accel more

def update_ahrs(ax_g, ay_g, az_g, gx_rads, gy_rads, gz_rads, dt,
                mx=None, my=None, mz=None):
    """Complementary filter: accel+gyro for pitch/roll, mag for heading.

    ax/ay/az in g. gx/gy/gz in rad/s. dt in seconds. mag in µT.
    Returns (pitch_deg, roll_deg, heading_deg) where heading is
    tilt-compensated if mag values are provided.
    """
    # Accel-only angles (atan2 formulation — stable at ±90° pitch)
    accel_pitch = math.atan2(-ax_g, math.sqrt(ay_g**2 + az_g**2))
    accel_roll  = math.atan2(ay_g, az_g)

    # Complementary filter: blend gyro integration + accel correction
    pitch = ALPHA * (pitch + gy_rads * dt) + (1.0 - ALPHA) * accel_pitch
    roll  = ALPHA * (roll  + gx_rads * dt) + (1.0 - ALPHA) * accel_roll

    heading = None
    if mx is not None:
        # Tilt-compensated heading from magnetometer
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        cos_roll  = math.cos(roll)
        sin_roll  = math.sin(roll)

        # Project magnetometer onto horizontal plane
        hx = mx * cos_pitch + mz * sin_pitch
        hy = mx * sin_roll * sin_pitch + my * cos_roll - mz * sin_roll * cos_pitch

        heading = math.degrees(math.atan2(-hy, hx)) % 360.0

    return math.degrees(pitch), math.degrees(roll), heading
```

**Note on ALPHA:** 0.98 is the standard starting point for a 100 Hz system. At lower sample rates you lower it. Field-tuning may be needed once running on the Pi.

**Note on units:** `sensor.acceleration` is m/s² -- divide by 9.81 to get g before this function. `sensor.gyro` is rad/s -- pass directly. No conversion needed for the filter.

### Pattern 6: INA226 via smbus2 direct (thin in-tree wrapper)

No clean PyPI package exists. The INA226 register map is well-documented and the Pi 5 memory already shows an INA219 at 0x40 (the same address). Write ~60 lines directly in `collectors/power.py`:

```python
# Key INA226 register addresses (datasheet verified)
INA226_ADDR        = 0x40
REG_CONFIG         = 0x00
REG_SHUNT_VOLTAGE  = 0x01  # Raw shunt voltage (1.25 µV/LSB)
REG_BUS_VOLTAGE    = 0x02  # Raw bus voltage (1.25 mV/LSB)
REG_POWER          = 0x03  # Power register
REG_CURRENT        = 0x04  # Current (after calibration)
REG_CALIBRATION    = 0x05  # Calibration register

# Calibration: CAL = trunc(0.00512 / (SHUNT_OHMS * MAX_EXPECTED_AMPS / 32768))
# For 10 mΩ shunt and 20 A max: CAL = trunc(0.00512 / (0.010 * 20 / 32768)) = 838
```

This ships `enabled: false` so the exact shunt value is a config parameter set at wiring time.

### Pattern 7: SEN0460 via vendored DFRobot driver

DFRobot's `DFRobot_AirQualitySensor` Python library lives on GitHub (`DFRobot/DFRobot_AirQualitySensor/python/raspberrypi/`). No pip package. Copy `dfrobot_airqualitysensor.py` into `src/shitbox/collectors/_vendor/`, and wrap it in the standard `BaseCollector` pattern.

```python
# DFRobot API (confirmed from GitHub source)
from shitbox.collectors._vendor.dfrobot_airquality import DFRobot_AirQualitySensor_I2C

sensor = DFRobot_AirQualitySensor_I2C(i2c_addr=0x19)
pm1  = sensor.gain_particle_concentration_ugm3(DFRobot_AirQualitySensor_I2C.PARTICLE_PM1_0_ATMOSPHERE_UGM3)
pm25 = sensor.gain_particle_concentration_ugm3(DFRobot_AirQualitySensor_I2C.PARTICLE_PM2_5_ATMOSPHERE_UGM3)
pm10 = sensor.gain_particle_concentration_ugm3(DFRobot_AirQualitySensor_I2C.PARTICLE_PM10_ATMOSPHERE_UGM3)
```

**Cable gotcha (must be in collector docstring):** The Gravity 4-pin connector on our SEN0460 has SDA/SCL swapped from standard. Pinout: red=VCC(5V), black=GND, **cyan=SDA, blue=SCL**. Connecting per the standard DFRobot colour convention will fail silently.

### Pattern 8: VEML7700

```python
# Source: Adafruit VEML7700 learn.adafruit.com
import adafruit_veml7700

sensor = adafruit_veml7700.VEML7700(i2c)
lux = sensor.lux       # float, lux
light = sensor.light   # raw counts if preferred
```

No gotchas. Runs at 1 Hz in a standard `BaseCollector`.

### Anti-Patterns to Avoid

- **Using smbus2 raw reads for LSM6DSOX:** The Adafruit library manages the register complexity cleanly. Raw smbus2 would require reimplementing scale factor math that the lib handles.
- **Reading LIS3MDL at 100 Hz:** The chip's default output data rate is 10 Hz. Polling faster than the ODR returns stale data and wastes CPU.
- **Running complementary filter state outside the sampler thread:** The filter has internal state (pitch/roll accumulators). It must live in the same thread that calls `update_ahrs()` to avoid data races.
- **Using `sensor.acceleration` directly as g values:** The library returns m/s². Must divide by 9.81. The MPU6050 code returned g directly -- this is a unit change that breaks the detector if not corrected.
- **Passing `board.I2C()` from multiple collectors:** Each collector calling `board.I2C()` independently is fine for Adafruit's Blinka on Linux; they share the underlying kernel I2C bus. But if LSM6DSOX and LIS3MDL share the sampler thread, a single `busio.I2C` object should be created once and shared.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LSM6DSOX register-level accel/gyro reads | Custom smbus2 register map | `adafruit_lsm6ds.lsm6dsox.LSM6DSOX` | Library handles scale factors, data rate config, register layout |
| LIS3MDL register reads | Custom smbus2 | `adafruit_lis3mdl.LIS3MDL` | Library handles gain, ODR, continuous-mode config |
| VEML7700 gain/integration time | Custom smbus2 | `adafruit_veml7700.VEML7700` | Auto-gain logic is non-trivial |
| DS18B20 1-Wire kernel parsing | Read `/sys/bus/w1/devices/` directly | `w1thermsensor` | Handles CRC validation, retry, sensor type checking |
| Full Kalman/Mahony filter | Implement from scratch | Complementary filter | Simpler, deterministic, sufficient for in-car heading at 100 Hz |

---

## Dead Code Audit Findings

### D-19 (ring_buffer.py dead imports)

**Finding:** The current `src/shitbox/events/ring_buffer.py` does NOT contain `import os` or a `_nice` lambda. The file is already clean. This item may refer to an older state of the file captured in the brain note. Verify at execution time before spending effort on it.

### D-20 (_event_json_paths thread-safety)

**Finding:** Already fixed in `engine.py`. All access to `_event_json_paths` and `_event_video_paths` in the current code goes through `_event_paths_lock`. Both write sites (`_on_capture_complete` and `_check_post_captures`) and the read site correctly use `with self._event_paths_lock:`. The brain note flagged this as a known issue but a prior phase resolved it. Drop D-20 from implementation scope -- verify only.

### D-21 (capture_sync._do_sync blocking)

**Finding:** Already properly backgrounded. `CaptureSyncService._sync_loop()` runs in its own daemon thread. `_do_sync()` is called from within that thread and uses a non-blocking `_sync_lock.acquire(blocking=False)` to guard against concurrent runs. The telemetry loop is never blocked. Drop D-21 from implementation scope -- verify only.

### pip_compositor.py (D-15)

**Finding:** `src/shitbox/capture/pip_compositor.py` does not exist in the current codebase (file not found at that path). Either already deleted or never existed. Verify and skip if absent.

---

## Hardware State Discrepancy (IMPORTANT)

The Pi 5 setup memory (`project_pi5_setup.md`) reports **BME280 at 0x77** and **INA219 at 0x40** as the confirmed i2c devices. The CONTEXT.md decisions say BME680 and INA226. This means either:

1. The hat still has the v1 sensors on the bus for now (BME280/INA219), and the v2 sensors (BME680/INA226) are the soldered components that will become active after physical cutover, or
2. The memory note is stale and was written before the v2 hat components were soldered.

**Research conclusion:** Since the CONTEXT.md is authoritative and was written after the memory note, the code should target BME680 and INA226. The `EnvironmentCollector` already uses `adafruit_bme680.Adafruit_BME680_I2C`, which is correct. The live i2c bus on the Pi 5 will not match until cutover. Collectors must degrade gracefully (existing pattern handles this). Flag in the plan for the operator to verify the i2c bus state during integration testing.

---

## Common Pitfalls

### Pitfall 1: LSM6DSOX returns m/s², not g

**What goes wrong:** The MPU6050 sampler produced `IMUSample` with `ax/ay/az` in g. The existing `EventDetector` thresholds (e.g. `hard_brake_threshold_g = -0.35`) are in g. If the new sampler feeds raw `sensor.acceleration` directly into the ring buffer without dividing by 9.81, event detection silently fires at wrong levels (off by a factor of ~9.8).

**How to avoid:** Divide `sensor.acceleration` tuple values by `9.81` before populating `IMUSample`. Document the conversion in the sampler.

**Warning signs:** Events fire far too frequently (threshold effectively ~0.036g instead of 0.35g), or not at all if comparison direction flips.

### Pitfall 2: LSM6DSOX returns gyro in rad/s, not deg/s

**What goes wrong:** `IMUSample.gx/gy/gz` fields are semantically deg/s (the MPU6050 code produced deg/s). If the new sampler feeds rad/s directly, the gyro integration in the complementary filter will produce wrong angle estimates, and any existing consumers expecting deg/s will break.

**How to avoid:** Multiply `sensor.gyro` tuple by `180.0 / math.pi` to convert to deg/s for `IMUSample`. Separately maintain internal rad/s values in the sampler for the complementary filter maths. Document the unit conversions clearly.

### Pitfall 3: 1-Wire probe IDs must be in config, not discovered dynamically

**What goes wrong:** If the collector enumerates all available sensors and assigns roles (exterior/engine_bay) by position in the list, a probe replacement or reboot-order change will swap which probe maps to which role silently.

**How to avoid:** Config holds explicit mappings: `exterior_sensor_id: "28-xxx"`, `engine_bay_sensor_id: "28-yyy"`. The collector reads only those IDs. On startup it logs if a configured ID is not found. Probe IDs can be discovered by running `w1thermsensor list` or reading `/sys/bus/w1/devices/`.

**Warning signs:** Temperature readings appear plausible but roles are swapped (engine bay reading ambient, exterior reading 60°C).

### Pitfall 4: LIS3MDL magnetic interference from other sensors

**What goes wrong:** The LSM6DSOX, INA226, and other components on the hat may generate electromagnetic interference. If the LIS3MDL is physically close to noisy power traces or inductors, heading will drift or oscillate.

**How to avoid:** Nothing software can fix physical placement, but the complementary filter's ALPHA constant (0.98 → lower values weight the magnetometer more) can be tuned. Include a `mag_declination_deg` config parameter for local magnetic declination correction.

**Warning signs:** Heading reports a plausible value when stationary but spins when the engine runs or a 12V supply switches on.

### Pitfall 5: Blinka I2C initialisation on Pi 5

**What goes wrong:** `board.I2C()` on Pi 5 running Raspberry Pi OS (Bookworm) sometimes selects `/dev/i2c-3` (the new RP1-connected bus) rather than `/dev/i2c-1`. The sensors are wired to `/dev/i2c-1`.

**How to avoid:** Use `busio.I2C(board.SCL, board.SDA)` explicitly and verify via `i2cdetect -y 1` that addresses are visible on bus 1. If Blinka picks the wrong bus, fall back to `smbus2.SMBus(1)` with the Adafruit library's I2C bus number parameter.

**Warning signs:** `OSError: [Errno 121] Remote I/O error` at sensor init. All sensors show NACK on init despite being physically present.

### Pitfall 6: Pi 5 has no hardware H.264 encoder

**What goes wrong:** The existing ffmpeg pipeline uses `libx264` with `ultrafast` preset. On Pi 4 and earlier, `h264_v4l2m2m` was the hardware path. On Pi 5, `h264_v4l2m2m` is absent -- the SoC has no H.264 hardware encoder at all. The existing code falls back to `libx264` software encoding, which is correct.

**How to avoid:** No code change needed -- the current ffmpeg command in `video.py` already uses `-c:v libx264 -preset ultrafast`. The Pi 5's quad-core Cortex-A76 at 2.4 GHz can handle 1080p 30fps libx264 at `ultrafast` with significant headroom. Observed reports suggest 1080p encoding consumes one core at roughly 30-50% at the `ultrafast` preset, leaving the other three cores for the 100 Hz IMU sampler, telemetry, and dashboard.

**Warning signs:** If CPU load spikes to 100% across all cores, drop to 720p in config or try `superfast` preset.

---

## Camera Pipeline (ELP 4K)

The ELP 4K camera (IMX317) is UVC compliant. From a Linux/ffmpeg perspective, it behaves identically to the UGREEN except for different v4l2 control defaults. No driver change is needed.

**Udev rule approach (existing pattern):**

```bash
# /etc/udev/rules.d/99-shitbox-cameras.rules
# ELP 4K (IMX317) -- Vendor:Product to be confirmed via: lsusb
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="32e4", ATTRS{idProduct}=="9410", \
    SYMLINK+="camera-front"
```

**Confirm VID:PID:** Run `lsusb` on the Pi 5 with the ELP connected and record the vendor:product IDs. The rule should target by VID:PID, not by bus position, to survive USB port changes.

**v4l2 controls for ELP IMX317:** The camera ships with different defaults to the UGREEN. Start with:

```bash
v4l2-ctl -d /dev/camera-front -L
```

This lists supported controls. The current config has `backlight_compensation`, `contrast`, `saturation`, `exposure_dynamic_framerate`. The ELP IMX317 supports these but at different value ranges. Calibrate empirically.

**In-car daylight recording:** The UGREEN controls (`brightness: 0, contrast: 36, saturation: 80, backlight_compensation: 3`) are starting points but will need adjustment for the new sensor. The ELP's IMX317 tends to expose more aggressively for bright sky than the UGREEN. Consider lowering `saturation` and adjusting `exposure_auto` if the control exists.

---

## Artificial Horizon + Heading Architecture

### Threading model

```
HighRateSampler thread (100 Hz)
  - reads LSM6DSOX accel + gyro
  - maintains complementary filter state (pitch_rad, roll_rad)
  - reads _latest_mag_xyz (shared, Lock-protected) from LIS3MDL thread
  - updates _latest_ahrs (shared, Lock-protected): pitch_deg, roll_deg, heading_deg
  - populates IMUSample with ax/ay/az/gx/gy/gz as before (unchanged for detector)

LIS3MDL collector thread (10-20 Hz via BaseCollector)
  - reads sensor.magnetic
  - writes _latest_mag_xyz under Lock

Telemetry loop (1 Hz)
  - reads _latest_ahrs under Lock
  - writes pitch_deg, roll_deg, heading_deg columns to SQLite
```

### SQLite schema

New columns needed in the `readings` table (or a dedicated `ahrs` table). Recommendation: add `pitch_deg`, `roll_deg`, `heading_deg` REAL columns to the existing `readings` table for the IMU sensor type, since they are derived from IMU+mag data. The telemetry loop writes them alongside the existing IMU snapshot.

### Complementary filter tuning

The existing MPU6050 calibration offsets (`accel_offset_x/y/z`) translate directly to LSM6DSOX -- same physical meaning, different chip. The LSM6DSOX has a lower noise floor, so the offsets may be smaller in magnitude. Keep the same config structure, rename keys from `mpu6050_*` to `imu_*`.

---

## pyproject.toml Changes (D-22)

```toml
# REMOVE:
"adafruit-circuitpython-mcp9808>=3.3.0",
"adafruit-circuitpython-ina219>=3.4.0",

# ADD:
"adafruit-circuitpython-lsm6ds>=4.6.2",
"adafruit-circuitpython-lis3mdl>=1.2.7",
"adafruit-circuitpython-veml7700>=2.2.1",
"w1thermsensor>=2.3.0",
# Note: SEN0460 and INA226 use vendored/in-tree drivers, no PyPI dep needed
```

The `adafruit-circuitpython-bme680` dependency is already present and correct. No change needed there.

---

## Runtime State Inventory

This is a code-only phase. No rename/migration involved. However, several config key names will change in `config/config.yaml`:

| Category | Items | Action |
|----------|-------|--------|
| Stored data | SQLite `readings` table — no schema change for existing columns; new AHRS columns added | Schema migration (ALTER TABLE or new table) in Wave 0 or Wave 1 |
| Live service config | `config.yaml` rewritten in this phase | File edit, no migration |
| OS-registered state | systemd unit unchanged; udev rules updated for ELP camera | udev rule file edit |
| Secrets/env vars | None affected | None |
| Build artifacts | `pip install -e ".[dev]"` reinstall needed after pyproject.toml changes | Reinstall |

**SQLite schema note:** The `readings` table currently uses a `sensor_type` column to distinguish readings. Adding `pitch_deg`, `roll_deg`, `heading_deg` columns to the table requires a migration (`ALTER TABLE readings ADD COLUMN pitch_deg REAL`). These are nullable and default to NULL for non-IMU rows.

---

## Environment Availability

| Dependency | Required By | Available (dev) | Notes |
|------------|------------|-----------------|-------|
| `adafruit-circuitpython-lsm6ds` | LSM6DSOX sampler | After `pip install` | Not in current pyproject.toml |
| `adafruit-circuitpython-lis3mdl` | LIS3MDL collector | After `pip install` | Not in current pyproject.toml |
| `adafruit-circuitpython-veml7700` | VEML7700 collector | After `pip install` | Not in current pyproject.toml |
| `w1thermsensor` | DS18B20 collector | After `pip install` | Not in current pyproject.toml |
| LSM6DSOX hardware (0x6A) | Sampler tests | NOT on dev laptop | Hardware tests must run on Pi 5 |
| LIS3MDL hardware (0x1C) | Heading tests | NOT on dev laptop | Hardware tests must run on Pi 5 |
| DS18B20 1-Wire | Temp tests | NOT on dev laptop | Two probes confirmed on Pi 5 |
| ELP 4K camera | Camera tests | NOT on dev laptop | Must test udev + ffmpeg on Pi 5 |
| BME680 (0x77) | Env sensor | Pi 5 may show BME280 | See hardware discrepancy note above |

**Missing dependencies with no fallback (for Pi hardware tests):**
- LSM6DSOX and LIS3MDL hardware -- test against real hardware on Pi 5 after physical cutover prep

**For dev/CI tests (on this laptop or a Pi without sensors):**
- All sensor hardware is `ImportError`-guarded in existing BaseCollector `setup()` methods, so unit tests that mock the sensor objects work without hardware. This pattern must be followed for all new collectors.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | none (pytest auto-discovery) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest --cov=shitbox` |

### Phase Requirements to Test Map

| Requirement | Behaviour | Test Type | Automated Command |
|-------------|-----------|-----------|-------------------|
| D-01/D-09: LSM6DSOX sampler | `HighRateSampler` populates `IMUSample` with correct units (g, deg/s) | unit | `pytest tests/test_sampler.py -x` |
| D-01/D-09: Unit conversion | accel in g (not m/s²), gyro in deg/s (not rad/s) | unit | `pytest tests/test_sampler.py::test_unit_conversion -x` |
| D-01: Event detector no regression | Existing HARD_BRAKE/BIG_CORNER/HIGH_G/ROUGH_ROAD still trigger correctly with new sampler | unit | `pytest tests/test_event_detector.py -x` |
| D-10/D-11: Complementary filter | `update_ahrs()` returns sensible pitch/roll/heading for known inputs | unit | `pytest tests/test_ahrs.py -x` |
| D-11: Heading at standstill | Non-None heading returned when mag data available | unit | `pytest tests/test_ahrs.py::test_heading_with_mag -x` |
| D-03: DS18B20 collector | `TemperatureCollector` degrades gracefully on `NoSensorFoundError` | unit | `pytest tests/test_temperature_collector.py -x` |
| D-03: DS18B20 sensor mapping | ID-to-role mapping from config, not position | unit | `pytest tests/test_temperature_collector.py::test_sensor_id_mapping -x` |
| D-04: VEML7700 collector | `LightCollector` calls `setup()`, handles ImportError, returns lux reading | unit | `pytest tests/test_light_collector.py -x` |
| D-05: SEN0460 collector | Ships disabled, collector gracefully skips when `enabled: false` | unit | `pytest tests/test_particulate_collector.py -x` |
| D-06: INA226 collector | Ships disabled, smbus2 wrapper reads correct register layout | unit | `pytest tests/test_power_collector.py -x` |
| D-15: pip_compositor deleted | File absent from repo | smoke | File check in test or CI |
| D-16/D-17: deleted collectors | No import of `adafruit_mcp9808` or `adafruit_ina219` anywhere in src | static | `pytest tests/test_dead_code_removed.py -x` |
| D-22: pyproject deps | Removed and added packages present in pyproject.toml | static | `pytest tests/test_pyproject.py -x` |
| D-24: Graceful degradation | All new collectors catch `ImportError` and sensor absence without crashing engine | unit | `pytest tests/test_*_collector.py -x` |

### Wave 0 Gaps (test files that must be created before implementation)

- [ ] `tests/test_sampler.py` -- covers D-01/D-09 (LSM6DSOX sampler unit tests, unit conversion)
- [ ] `tests/test_ahrs.py` -- covers D-10/D-11 (complementary filter maths, known-input assertions)
- [ ] `tests/test_temperature_collector.py` -- covers D-03 (DS18B20 sensor, role mapping, graceful degradation)
- [ ] `tests/test_light_collector.py` -- covers D-04 (VEML7700)
- [ ] `tests/test_particulate_collector.py` -- covers D-05 (SEN0460 enabled:false behaviour)
- [ ] `tests/test_power_collector.py` -- covers D-06 (INA226 collector enabled:false, smbus2 wrapper)
- [ ] `tests/test_dead_code_removed.py` -- covers D-15/D-16/D-17 (import scan, file absence checks)
- [ ] `tests/test_pyproject.py` -- covers D-22 (dep presence/absence in pyproject.toml)

Existing `tests/test_event_detector.py` and `tests/test_i2c_recovery.py` should continue to pass without modification -- they test the detector and I2C recovery patterns that must not regress.

**Per-wave gate:** Run `pytest tests/ -x -q` after each plan merge. Hardware-dependent integration tests (actual sensor reads) are out of scope for automated CI -- they are manual smoke tests on the Pi 5.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| MPU6050 (smbus2 raw reads) | LSM6DSOX (Adafruit CircuitPython lib) | Better noise floor, cleaner API, no manual register map |
| MCP9808 I2C temp | DS18B20 1-Wire | Physically decoupled from I2C bus, simpler wiring for remote probes |
| INA219 (Adafruit lib) | INA226 (in-tree smbus2 wrapper) | INA226 has 16-bit current resolution vs 12-bit; no PyPI lib so write in-tree |
| No heading sensor | LSM6DSOX + LIS3MDL complementary filter | Heading available at standstill; fills GPS shadow gaps |
| UGREEN front camera | ELP 4K (IMX317) | Higher resolution, better low-light; same UVC/MJPEG interface |

**Deprecated/outdated:**
- `adafruit-circuitpython-mcp9808`: removed
- `adafruit-circuitpython-ina219`: removed
- Hardware H.264 encoder (`h264_v4l2m2m`): not available on Pi 5; existing `libx264 ultrafast` is the correct path

---

## Open Questions

1. **INA226 shunt resistance value**
   - What we know: INA226 ships `enabled: false`; calibration depends on the shunt resistor value soldered on the hat
   - What's unclear: The exact shunt resistance is not documented in the brain note. The INA226 calibration register must be set correctly.
   - Recommendation: Add `shunt_ohms: 0.010` (10 mΩ is a common hat default) as a config parameter. Operator must verify with a multimeter before enabling.

2. **ELP camera VID:PID for udev rule**
   - What we know: ELP uses IMX317. UVC compliant. The rule needs ATTRS{idVendor} and ATTRS{idProduct}.
   - What's unclear: The exact VID:PID of this specific ELP model. The Amazon listing does not quote them.
   - Recommendation: Run `lsusb` on the Pi 5 with the ELP connected during integration and capture the IDs before writing the udev rule.

3. **BME680 vs BME280 on live Pi 5 bus**
   - What we know: `project_pi5_setup.md` says BME280 at 0x77. CONTEXT.md says BME680. The addresses are the same.
   - What's unclear: Whether the hat already has a BME680 soldered or still has the BME280. The two sensors use different register maps and different libraries.
   - Recommendation: Run `i2cdetect -y 1` and then attempt a quick BME680 identity check (`0xD0` register = `0x61` for BME680, `0x60` for BME280). If the Pi 5 still has a BME280, it will fail at sensor init -- the existing `EnvironmentCollector` will degrade gracefully. Physical verification is a pre-integration step, not a code problem.

4. **DS18B20 probe 1-Wire IDs**
   - What we know: Two DS18B20 probes are confirmed working on the Pi 5. Their IDs are known to the hardware but not in any config file yet.
   - What's unclear: Which physical probe (exterior vs engine bay) has which 1-Wire ID.
   - Recommendation: Wave 0 task: SSH to Pi 5, run `w1thermsensor list`, record both IDs and which is which by physical position (one probe should be inside the case, one outside). Use those IDs in config.

5. **AHRS SQLite schema migration**
   - What we know: New columns (pitch_deg, roll_deg, heading_deg) need to be added to readings table.
   - What's unclear: Whether to add them to the existing `readings` table or create a dedicated `ahrs` table. A separate table avoids NULLs in existing rows but adds a join.
   - Recommendation: Add nullable columns to `readings` for simplicity. Existing rows get NULL for these columns which is semantically correct. One `ALTER TABLE` migration at service startup if columns don't exist.

---

## Sources

### Primary (HIGH confidence)

- `adafruit-circuitpython-lsm6ds` PyPI -- confirmed v4.6.2; `Rate` enum values from GitHub source (`__init__.py`)
- `adafruit-circuitpython-lis3mdl` PyPI -- confirmed v1.2.7; `.magnetic` property from Adafruit docs
- `adafruit-circuitpython-veml7700` PyPI -- confirmed v2.2.1; `.lux` property from Adafruit learn
- `w1thermsensor` PyPI -- confirmed v2.3.0; API from GitHub README
- Raspberry Pi Forums `[SOLVED: IMPOSSIBLE]` thread -- Pi 5 has no H.264 hardware encoder; confirmed by RPi engineer
- Code audit of `src/shitbox/events/engine.py`, `capture_sync.py`, `ring_buffer.py` -- D-19/D-20/D-21 status confirmed by direct inspection

### Secondary (MEDIUM confidence)

- Complementary filter formulation -- derived from AHRS docs and multiple community implementations; formulation is standard and well-established
- Pi 5 `libx264 ultrafast` CPU headroom -- RPi forum reports suggest 1080p 30fps is well within capability; no exact dual-stream benchmark found
- DFRobot SEN0460 Python API -- confirmed from GitHub source (`python/raspberrypi` directory); no PyPI package confirmed by absence from pip search
- INA226 smbus2 approach -- `pi-ina226` GitHub library confirms register map; no PyPI package confirmed by pip search failure

### Tertiary (LOW confidence -- validate before using)

- ELP IMX317 VID:PID for udev rule -- not confirmed; must be read from device on Pi 5
- BME680 vs BME280 physical presence on Pi 5 hat -- memory note says BME280, context says BME680; unresolved until physical check
- INA226 shunt resistance value -- not documented; operator must measure

---

## Project Constraints (from CLAUDE.md)

- Logging: `structlog` with keyword arguments -- all new collectors must emit `sensor_init`, `sensor_read`, `sensor_error` structured log events
- Ruff: line length 100, rules E/F/I/W, target Python 3.9
- Types: full type annotations; mypy enforced
- Config: hierarchical YAML loaded into nested dataclasses via `_dict_to_dataclass`
- Threading: each collector in a daemon thread; database uses write locks and thread-local connections
- Graceful hardware degradation: every new collector catches ImportError and I2C/1-Wire absence without crashing the engine
- Dev environment is macOS laptop -- do not run `pip install` commands that target Pi hardware

---

## Metadata

**Confidence breakdown:**
- Standard stack (library versions, API shapes): HIGH -- verified directly from PyPI and GitHub
- Dead-code audit findings: HIGH -- verified by direct code inspection
- Architecture/filter maths: MEDIUM -- complementary filter is standard; unit conversions confirmed from lib source; exact ALPHA tuning is empirical
- Pi 5 encode headroom: MEDIUM -- no dual-stream benchmark; single-stream evidence is strong
- Hardware state (BME680 vs BME280, ELP VID:PID): LOW -- discrepancy flagged, physical verification needed

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (library APIs are stable; Pi 5 situation is unlikely to change)
