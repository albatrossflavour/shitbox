# Technology Stack

**Project:** Shitbox Rally Telemetry
**Researched:** 2026-04-09 (v2.0 Rally Ready milestone)
**Confidence:** MEDIUM-HIGH (see per-area assessment below)

---

## Baseline Stack (v1.0 — Do Not Re-research)

Already in `pyproject.toml` and confirmed working:

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.9+ | Pinned in `pyproject.toml` |
| Platform | Raspberry Pi OS Bookworm | Pi 5 |
| Process management | systemd + sdnotify | watchdog wired |
| Logging | structlog 24.0.0+ | keyword-args convention |
| Config | pyyaml + dataclasses | `config/config.yaml` hierarchy |
| Storage | SQLite WAL (stdlib) | offline-first, crash-hardened |
| Sync | Prometheus remote\_write + Snappy | cursor-based batch |
| Sensors | smbus2, gpsd-py3, Adafruit libs | I2C bus 1 |
| Video | ffmpeg subprocess | event-triggered |
| Web API | FastAPI 0.115+ + uvicorn + sse-starlette | in-process dashboard |
| Frontend | Alpine.js + Tailwind + Leaflet | vendored to `/static/vendor/` |
| Health | psutil 6.1.1 + vcgencmd subprocess | CPU/disk/throttle |
| IMU | adafruit-circuitpython-lsm6ds 4.6.2+ | LSM6DSOX |
| Magnetometer | adafruit-circuitpython-lis3mdl 1.2.7+ | LIS3MDL |
| Stage tracking | gpxpy 1.6.2 | GPX route parsing |
| Display | pygame-ce 2.5.x | KMSDRM fullscreen |
| TTS | piper-tts 1.4.0+ | spoken alerts |

---

## v2.0 New Stack Additions

### 1. Field Notes / Blog Entry (NOTE-01)

**Problem:** Text entry from a touchscreen kiosk with no physical keyboard wired.
Physical USB keyboard is also a valid input path — the car will sometimes be parked.

**Recommendation: simple-keyboard (JS, CDN) + vanilla input handling in Alpine.js**

The dashboard is already a FastAPI-served HTML page with Alpine.js. The right
approach is a floating on-screen keyboard rendered in the browser, not a system-level
virtual keyboard. This avoids the Chromium kiosk + Wayland layer-shell conflict that
affects both wvkbd and squeekboard on Bookworm.

The Wayland/kiosk problem: on Bookworm (Labwc compositor), squeekboard and wvkbd are
hardcoded to appear on the `top` layer but Chromium in kiosk mode requires
`overlay` layer. The issue is open against labwc as of late 2024 and has no clean fix
without patching the compositor. A JS in-browser keyboard sidesteps this entirely.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| simple-keyboard | 3.x (CDN) | On-screen soft keyboard in browser | Pure JS, no framework deps, mobile-touch native, actively maintained (hodgef/simple-keyboard), vanilla JS usage supported via CDN |
| simple-keyboard CSS | 3.x (CDN) | Keyboard visual styling | Companion CSS for simple-keyboard |
| FastAPI new route | n/a | `POST /notes` endpoint | Stores note to SQLite with GPS + timestamp from existing data; no new library needed |

**What NOT to use:**

- squeekboard / wvkbd (system OSK) — both fail to appear above Chromium kiosk on Bookworm/Wayland as of early 2025; tracked in labwc issue #2926. LOW reliability.
- matchbox-keyboard / Florence — X11-only; Bookworm defaults to Wayland; would require forcing X11 session which breaks pygame-ce display path.
- Physical keyboard GPIO wiring — unnecessary; USB HID keyboards work natively on Pi 5 and the browser `<input>` elements accept them without any code changes.

**Confidence: MEDIUM** — simple-keyboard CDN path is reliable; the Wayland/kiosk
issue is confirmed in multiple forum threads and a tracked labwc issue. The JS-in-browser approach is a proven workaround in kiosk deployments (Home Assistant community, BrewPi).

**Integration note:** simple-keyboard is loaded from CDN (or vendored into
`/static/vendor/` like the existing Alpine/Leaflet/Tailwind files). The keyboard
component renders inside the existing Alpine.js dashboard context. Physical USB
keyboards continue to work transparently via browser `<input>` events.

---

### 2. Refueling Log (FUEL-01)

**No new Python libraries needed.**

The refueling log is a new SQLite table (`refuel_events`) with columns for
timestamp, GPS lat/lng, volume (litres), odometer reading, and a calculated
efficiency field. The storage pattern is identical to the existing event storage.

The website integration requires `refuel_events` to be included in the events.json
generation (`EventStorage.generate_events_json()`) — already the right integration
point.

**FastAPI:** New `POST /refuel` and `GET /refuel` routes. No new dependencies.

**Confidence: HIGH** — pure CRUD on existing SQLite infrastructure.

---

### 3. Driver Tracking (DRVR-01, DRVR-02)

**No new Python libraries needed.**

Driver sessions are a new SQLite table (`driver_sessions`) with columns for driver
name, start/end timestamp, and start/end odometer. Event attribution (which driver
was active when an event fired) is a join against this table at query time.

The driver selection UI is a touch-friendly dropdown or button group in the existing
Alpine.js dashboard. `POST /driver/start` and `POST /driver/end` FastAPI routes.

Driver stats (time/percentages/event counts) are computed as SQLite aggregates at
read time — no caching layer needed at this scale (a 10-day rally generates thousands
of rows, not millions).

**Confidence: HIGH** — same pattern as all other data in the system.

---

### 4. ELP 4K Video Capture Tuning (VID-01)

**Recommendation: v4l2-ctl (system, already in v4l-utils) + subprocess from Python**

The ELP 4K camera is a UVC USB device. V4L2 controls (brightness, contrast,
saturation, sharpness, exposure, white balance, gain) are set via `v4l2-ctl` before
or at ffmpeg startup. There is no reason to use a Python v4l2 binding library when
`subprocess.run(["v4l2-ctl", "--device", "/dev/video0", "--set-ctrl", "brightness=128"])`
does the job cleanly.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| v4l-utils (system) | system package | `v4l2-ctl` for camera control | Standard tool, pre-installed on Bookworm or `apt install v4l-utils`; enumerate controls with `--list-ctrls`, set with `--set-ctrl` |
| ffmpeg (system) | system package | Video capture and encoding | Already in use; relevant flags below |

**ffmpeg flags for UVC 4K capture:**

```
-f v4l2
-input_format mjpeg          # ELP cameras output MJPEG in hardware at high res
-video_size 3840x2160        # or 1920x1080 depending on actual mount/field of view
-framerate 30                # confirm with v4l2-ctl --list-formats-ext
-i /dev/video0
-c:v copy                    # if MJPEG → keep as-is for recording
```

Note: confirm actual supported resolutions and framerates with
`v4l2-ctl --device /dev/video0 --list-formats-ext` on the mounted camera. ELP 4K
cameras often only achieve 4K at 15fps; 1080p60 may be more practical for
event recording.

**What NOT to use:**

- v4l2py (PyPI) — adds a Python binding for what is a one-line subprocess call; overkill, and adds a C-extension dependency.
- OpenCV for camera control — `cv2.CAP_*` props often silently fail on UVC cameras; v4l2-ctl is authoritative.
- libcamera — libcamera is for the CSI camera port (RPi Camera Module); the ELP is USB/UVC; v4l2 is correct.

**Confidence: MEDIUM** — v4l2-ctl subprocess pattern is confirmed working on Pi 5 in
forum threads. Exact ELP control names need empirical listing on the actual hardware
(`v4l2-ctl --list-ctrls` output varies by camera firmware).

---

### 5. Sensor Calibration (CAL-01)

**Recommendation: numpy (stdlib-like at this point) + manual offset constants in config YAML**

Calibration for the v2 sensor hat involves:

- **Accelerometer (LSM6DSOX):** Stationary bias measurement. Record mean of N samples in each axis, subtract from readings. Store as `accel_offset_x/y/z` in `config.yaml`. No library needed beyond numpy for averaging.
- **Gyroscope (LSM6DSOX):** Zero-rate offset (drift at rest). Same approach.
- **Magnetometer (LIS3MDL):** Hard-iron calibration. Rotate sensor through full 3D sphere, fit ellipsoid, apply offset + scale matrix. This is the only one needing more than numpy.
- **Temperature (DS18B20):** Validate against known reference. Offset constant in config if needed.
- **Lux (VEML7700):** Validate gain settings match environment. Adafruit library already handles gain/integration time.
- **Power (INA226):** Validate shunt resistance value in library init matches actual hardware. Already configured in existing collector.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| numpy | 1.24.0+ (already available on Bookworm) | Statistical averaging for bias calculation | Already a transitive dep via Adafruit libs; no new install needed |
| scipy (optional) | 1.11.0+ | Ellipsoid fitting for magnetometer hard-iron calibration | Only needed if magnetometer calibration is in-scope; scipy.optimize.least\_squares fits the sphere/ellipsoid; not needed for accel/gyro |

**Calibration procedure pattern:**

Offsets go into `config.yaml` under a new `calibration:` section and are applied in
the sampler/collector classes at read time — not in a separate calibration daemon.
Calibration is a one-time tool run, not a runtime service.

**What NOT to add:**

- imu-calibration (PyPI, careweather) — targets MPU9250 specifically, not LSM6DSOX; the
  calibration math is simple enough to implement directly.
- Full AHRS (complementary filter, Madgwick, Mahony) — that is attitude estimation,
  not calibration; out of scope for this milestone.

**Confidence: HIGH** for accel/gyro (standard numpy averaging). MEDIUM for
magnetometer (ellipsoid fitting with scipy is well-understood but needs careful
rotation procedure on the actual hardware).

---

### 6. Undervoltage Detection and Alerting (PWR-01)

**Recommendation: vcgencmd subprocess + INA226 existing readings (already in stack)**

This is already 90% in the stack from v1.0. The gaps are:

1. The existing `HealthCollector` already reads `vcgencmd get_throttled` — it just
   needs to emit a Prometheus metric AND trigger a TTS alert when bit 0 is set
   (under-voltage currently active).

2. The INA226 collector already reads bus voltage. Add a threshold check: if
   `bus_voltage < 4.7V` (below the PMIC threshold of 4.63V, with margin), emit an
   alert. This catches brown-out conditions before the PMIC fires.

3. Pi 5 also supports `vcgencmd pmic_read_adc` for detailed PMIC voltage rails.
   Worth adding to HealthCollector.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| vcgencmd pmic\_read\_adc (system) | n/a | Pi 5 PMIC rail voltages | Pi 5 specific; provides 3V3, 5V, VDDCORE readings; call via subprocess same as get\_throttled |

**Bitmask reference for get\_throttled:**

```
bit  0: under-voltage currently detected (PMIC threshold: 4.63V)
bit  1: ARM frequency capped
bit  2: currently throttled
bit  3: soft temperature limit active
bit 16: under-voltage has occurred since boot (sticky)
bit 17: ARM freq cap has occurred since boot (sticky)
bit 18: throttling has occurred since boot (sticky)
bit 19: soft temp limit has occurred since boot (sticky)
```

Parse: `throttled = int(vcgencmd_output.split("=")[1], 16)`. Current state is
`throttled & 0xF`. Historical is `(throttled >> 16) & 0xF`.

**What NOT to use:**

- A dedicated Python undervoltage library — none of sufficient quality exist; the
  vcgencmd + subprocess pattern is two lines and well-understood.
- Reading `/sys/class/hwmon` for voltage — works but provides less information than
  `pmic_read_adc` on Pi 5 specifically.

**Confidence: HIGH** — vcgencmd bitmask is documented in multiple official and
community sources. INA226 readings are already in the system.

---

### 7. Monitoring Completeness (MON-01)

**No new Python libraries needed.**

HLTH-01 closure requires:

- Confirming `HealthCollector` metrics appear in Prometheus. Debug with
  `promtool query instant http://prometheus:9090 'shitbox_health_cpu_percent'`.
- Fixing the Prometheus scrape label conflict (likely a `job` or `instance` label
  collision between the push path and any existing scrape config).

Grafana embedding improvements for the website (WEB-01):

- Grafana 11.3.0+ broke `&kiosk` mode (time picker moved into content pane, not
  hidden by kiosk). Workaround: add `&_dash.hideTimePicker=true` to the iframe URL.
  Variables panel still shows — no clean fix yet in 11.4.x as of early 2025.
- The correct iframe URL pattern:
  `https://grafana.host/d/<dashboard-id>?orgId=1&kiosk&_dash.hideTimePicker=true&theme=dark&from=now-1h&to=now`
- Variables can be pre-set via `&var-<name>=<value>` URL params. Useful for
  pre-filtering by driver or day.
- `allow_embedding = true` in Grafana's `grafana.ini` [security] section is required.
  Already should be set given it's an embedded iframe use case.

**Grafana version note:** If self-hosted Grafana is on 11.3.0+, the kiosk issue is
active. Pinning to 11.2.x or waiting for a fix in 11.5.x is the pragmatic choice.
Check current version with `grafana-server --version`.

**Confidence: MEDIUM** — kiosk regression is confirmed in GitHub issues #97759 and
#98724. The hideTimePicker workaround is partial and confirmed in community threads.

---

### 8. Website Revamp (WEB-01)

**No new server-side libraries needed.**

The public website (`shit-of-theseus.com`) is plain HTML/CSS/JS. Integrating new
data streams means:

- Extending `EventStorage.generate_events_json()` to include refuel events, driver
  session boundaries, and field notes in the output.
- Adding new sections/tabs to `index.html` for the blog/notes view and driver stats.
- Existing Leaflet map already accepts multiple data types; refuel stops can be new
  marker icons.

The website has no build step. No framework to add. Keep it that way.

**Grafana dashboard improvements** are config/JSON work in Grafana, not code changes.

---

## Summary: New Python Dependencies Required

| Library | Version | Purpose | Already Installed? |
|---------|---------|---------|-------------------|
| numpy | 1.24.0+ | Calibration averaging | Yes (transitive) |
| scipy | 1.11.0+ | Magnetometer ellipsoid fitting (optional) | No — only if doing full mag cal |

No other new Python packages are required. All v2.0 features extend the existing
FastAPI/SQLite/structlog/subprocess infrastructure.

---

## Summary: New System Dependencies Required

| Package | Install | Purpose |
|---------|---------|---------|
| v4l-utils | `sudo apt install v4l-utils` | `v4l2-ctl` for ELP camera tuning |

v4l-utils may already be installed; confirm with `which v4l2-ctl`.

---

## Summary: New JS Dependencies Required

| Library | Source | Purpose |
|---------|--------|---------|
| simple-keyboard | CDN or vendor to `/static/vendor/` | On-screen keyboard for notes/field entry |
| simple-keyboard CSS | CDN or vendor | Keyboard styling |

CDN: `https://cdn.jsdelivr.net/npm/simple-keyboard/build/index.modern.js`

Vendor locally (recommended, matches existing pattern for Alpine/Tailwind/Leaflet).

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| On-screen keyboard | simple-keyboard (JS in-browser) | squeekboard (system OSK) | squeekboard fails to appear above Chromium kiosk on Bookworm/Wayland; labwc issue #2926, no fix as of early 2025 |
| On-screen keyboard | simple-keyboard (JS in-browser) | wvkbd | Same Wayland layer-shell problem as squeekboard |
| On-screen keyboard | simple-keyboard (JS in-browser) | matchbox-keyboard | X11-only; Bookworm uses Wayland by default |
| Camera control | v4l2-ctl subprocess | v4l2py (PyPI) | subprocess is two lines; v4l2py adds a C-extension dep for no practical benefit |
| Camera control | v4l2-ctl subprocess | OpenCV cv2.CAP\_\* | CAP props silently fail on many UVC cameras; v4l2-ctl is authoritative |
| Magnetometer cal | numpy + scipy | imu-calibration (PyPI) | Targets MPU9250; calibration math is simple enough to write directly |
| Undervoltage | vcgencmd subprocess | python-rpi-bad-power (PyPI) | python-rpi-bad-power reads the same `/sys` path; no advantage over direct subprocess |
| Grafana kiosk | `&_dash.hideTimePicker=true` workaround | Grafana 11.2.x pin | Pin is safer if rally date is imminent; workaround is partial |

---

## Version Compatibility Notes

| Concern | Detail |
|---------|--------|
| numpy on Pi 5 Bookworm | numpy 1.24+ is available as a Bookworm apt package (`python3-numpy`) and via pip; already a transitive dep of the Adafruit libraries so almost certainly installed |
| scipy on Pi 5 | Available as `python3-scipy` (Bookworm apt) or via pip wheel; reasonably large install (~60 MB) — only add if magnetometer calibration is in scope |
| simple-keyboard version | 3.x is current; API stable since 2020; no breaking changes expected |
| Grafana kiosk regression | Confirmed broken in 11.3.0, 11.4.x; workaround `&_dash.hideTimePicker=true` is partial |
| wvkbd / squeekboard Wayland | Issue is in labwc compositor, not the keyboard apps; not fixed in Bookworm as of 2025-04 |

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Field notes / keyboard | MEDIUM | JS-in-browser path is solid; Wayland OSK problem is confirmed |
| Refuel + driver tracking | HIGH | Pure CRUD on existing stack; no new dependencies |
| ELP camera tuning | MEDIUM | v4l2-ctl pattern solid; exact control names need empirical listing on hardware |
| Sensor calibration | HIGH (accel/gyro) / MEDIUM (mag) | Numpy averaging is trivial; ellipsoid fit needs care |
| Undervoltage | HIGH | vcgencmd path already in codebase; pmic\_read\_adc is Pi 5 specific and documented |
| Grafana embedding | MEDIUM | Kiosk regression confirmed; workaround is partial; full fix TBD by upstream |
| Website revamp | HIGH | Plain HTML/JS; no new stack; extend existing JSON generation |

---

## Sources

- simple-keyboard GitHub: <https://github.com/hodgef/simple-keyboard>
- simple-keyboard npm: <https://www.npmjs.com/package/simple-keyboard>
- Squeekboard above Chromium kiosk (Wayland): <https://github.com/labwc/labwc/issues/2926>
- RPi Bookworm OSK + Chromium kiosk: <https://forums.raspberrypi.com/viewtopic.php?t=389707>
- Grafana kiosk broken 11.3.0: <https://github.com/grafana/grafana/issues/97759>
- Grafana time picker kiosk 11.2.2: <https://github.com/grafana/grafana/issues/96595>
- Grafana allow\_embedding config: <https://last9.io/blog/how-to-get-grafana-iframe-embedding-right/>
- v4l2-ctl USB camera controls Pi 5: <https://forums.raspberrypi.com/viewtopic.php?t=364972>
- v4l2-ctl Python subprocess pattern: <https://gist.github.com/jwhendy/12bf558011fe5ff58bd5849954e84af4>
- vcgencmd get\_throttled bitmask Pi 5: <https://forums.raspberrypi.com/viewtopic.php?t=377392>
- vcgencmd pmic\_read\_adc Pi 5: <https://forums.raspberrypi.com/viewtopic.php?t=313358>
- IMU calibration with numpy (MPU9250, same principles): <https://makersportal.com/blog/calibration-of-an-inertial-measurement-unit-imu-with-raspberry-pi-part-ii>
- Adafruit LSM6DS Python library: <https://learn.adafruit.com/lsm6dsox-and-ism330dhc-6-dof-imu/python-circuitpython>

---

*Stack research for: Shitbox Rally Telemetry v2.0 Rally Ready milestone*
*Researched: 2026-04-09*
