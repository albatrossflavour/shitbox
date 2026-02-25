# Technology Stack

**Project:** Shitbox Rally Telemetry — Hardening Milestone
**Researched:** 2026-02-25
**Scope:** Libraries and system-level tools needed to add bulletproof boot recovery,
watchdog/self-healing, remote health monitoring, 7" driver display, rally stage
tracking, thermal resilience, and storage management to the existing Python/RPi system.

---

## Existing Stack (Do Not Change)

These are already in the codebase and working. Document them here to establish the
baseline all new additions must be compatible with.

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.9+ | Constrained by `pyproject.toml` |
| Platform | Raspberry Pi OS (Bookworm) | Target production platform |
| Process management | systemd | Already wired; shitbox-telemetry.service |
| Logging | structlog 24.0.0+ | All new code must use the same conventions |
| Config | pyyaml 6.0+ + dataclasses | Extend existing `config/config.yaml` |
| Storage | SQLite (stdlib) + WAL | Offline-first; already hardened |
| Sync | Prometheus remote_write + Snappy | Batch; cursor-based |
| Sensors | smbus2, gpsd-py3, Adafruit libs | I2C bus 1 |
| Video | ffmpeg subprocess | Event-triggered |
| Display (OLED) | SSD1306 via smbus2 | 128x64, existing `OLEDDisplayService` |
| Retry | tenacity 8.0.0+ | Already used for sync retries |

---

## New Stack — Hardening Milestone

### 1. Watchdog and Self-Healing

**Recommendation: systemd hardware watchdog + sdnotify (pure Python)**

The RPi BCM283x hardware watchdog is built-in and managed via systemd's
`RuntimeWatchdogSec`. The Python layer must send `WATCHDOG=1` pings via the
sd_notify socket at intervals shorter than the watchdog deadline.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| sdnotify | 0.3.2+ | Pure Python sd_notify protocol | Zero C dependencies, works on Python 3.9; the existing `UnifiedEngine` health-check loop (30s interval) can send watchdog pings inline without a separate daemon |
| systemd (OS) | n/a | Hardware watchdog via `RuntimeWatchdogSec` | BCM2835 hardware watchdog resets the Pi on hard lock; set to 15s max (hardware limit on RPi) |

**What NOT to use:**

- `systemd-watchdog` (PyPI) — active fork by AaronDMarasco/rtkwlf but adds abstraction over what is essentially a two-line socket write; sdnotify is simpler and more widely tested.
- `watchdog` (PyPI) — filesystem watch library, wrong domain entirely.
- `pywatchdog` (PyPI) — directly opens `/dev/watchdog`, bypasses systemd, fights with `RuntimeWatchdogSec`.

**Confidence: HIGH** — systemd sd_notify protocol is stable and well-documented at freedesktop.org. sdnotify is a pure-Python implementation of a published protocol.

**systemd unit additions required:**

```ini
[Service]
Type=notify
WatchdogSec=30
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
```

---

### 2. Remote Health Monitoring

**Recommendation: prometheus_client (push via existing remote_write) + vcgencmd subprocess**

The infrastructure already pushes metrics to Prometheus via remote_write. Health
metrics should travel the same path — no new infrastructure needed.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| prometheus_client | 0.20.0+ | Expose Gauge/Counter metrics for health state | Official Prometheus Python client; push_to_gateway or manual remote_write both work; integrates with existing BatchSyncService pattern |
| psutil | 6.1.1 | CPU %, memory %, disk %, network I/O | Well-maintained; `sensors_temperatures()` reads Pi CPU temp directly; note: 7.x requires GLIBC_2.34 which Bullseye/Bookworm on RPi4 may not have — pin to 6.1.1 until Bookworm compatibility confirmed |
| vcgencmd (system) | n/a | Throttle and under-voltage detection | Built-in RPi firmware tool; call via `subprocess.run(["vcgencmd", "get_throttled"])`, parse hex bitmask; no Python wrapper needed |

**What NOT to use:**

- A separate Pushgateway — adds an extra service to deploy and maintain; the existing remote_write path is sufficient for a single Pi.
- node_exporter — Go binary, not Python; adds process overhead; duplicates what psutil provides; the existing Prometheus stack already handles custom metrics.

**Throttle bitmask reference (vcgencmd get_throttled):**

```
bit 0: under-voltage now
bit 1: arm freq capped now
bit 2: throttling now
bit 3: soft temp limit active
bit 16-19: historical versions of bits 0-3
```

Parse with `int(value, 16) & 0xF` — non-zero means currently degraded.

**Confidence: HIGH** for psutil + vcgencmd. MEDIUM for prometheus_client version
pinning — GLIBC constraint needs validation on target Bookworm image.

---

### 3. Driver Display (7" Pi Touchscreen)

**Recommendation: pygame-ce 2.5.x (Community Edition)**

The 7" Official Raspberry Pi touchscreen is directly attached to the DSI port. It
presents as a standard framebuffer/KMSDRM display under Bookworm. A fullscreen
Python process with no window manager is the correct pattern for an automotive
dashboard — fast startup, direct framebuffer access, no compositor overhead.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pygame-ce | 2.5.6 | Fullscreen dashboard rendering | Community Edition fork of pygame; more actively maintained (last release Oct 2025 vs pygame's Sep 2024); SDL2-backed; KMSDRM driver works on RPi Bookworm without X11; touch input treated as mouse events |
| Pillow | 10.0.0+ | Image loading for any icons/logos | Already available in most Pi environments; pygame-ce can load PIL images directly |

**What NOT to use:**

- Kivy — heavier framework; has a known issue with the RPi official touchscreen's touch driver; adds significant dependency weight for what is a read-only status display.
- tkinter — requires X11/Wayland; X11 startup adds 10-15s to boot; unacceptable for an automotive display that must show status within seconds of ignition.
- Qt/PyQt5 — heavyweight; licensing complexity; overkill for a single-screen status display.
- pygame (standard) — last release September 2024; pygame-ce is the actively maintained fork used by the community going forward.

**Display architecture:**

Run as a separate systemd service (`shitbox-display.service`) that starts after
`shitbox-telemetry.service`. Read state via a shared in-memory structure or a
small Unix socket IPC. Do NOT import the display into the engine process — keeps
the 100 Hz IMU loop isolated from rendering jank.

The display service runs `pygame.display.set_mode((800, 480), pygame.FULLSCREEN)`
and refreshes at 10 Hz (100ms sleep between frames) — sufficient for speed/heading
display without burning CPU the IMU path needs.

**Confidence: MEDIUM** — pygame-ce KMSDRM on Bookworm is confirmed working in
RPi forum threads. The GLIBC and SDL2 package versions on the specific Pi image
need validation at integration time. Boot without X11 requires `SDL_VIDEODRIVER=kmsdrm`
environment variable set in the systemd unit.

---

### 4. Rally Stage Tracking

**Recommendation: gpxpy 1.6.2 + stdlib math (haversine)**

Stage tracking requires two capabilities: parsing a GPX route file containing the
rally stages, and computing point-on-route progress from live GPS coordinates.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| gpxpy | 1.6.2 | Parse GPX route/track files | Mature, pure Python, no C extensions; provides `get_length_2d()` and `get_nearest_location()` for distance-along-route; PyPI version 1.6.2 is current |

**What NOT to use:**

- shapely / pyproj — geospatial heavyweights; correct for complex polygon operations but severe overkill for "distance along a 1D route". Pull in C extension compilation, large binary wheels.
- geopy — primarily for geocoding/distance calculations; no GPX parsing; reverse_geocoder already handles location names in the existing stack.
- folium / geopandas — visualisation/analysis libraries, not embedded runtime libraries.

**Implementation pattern:**

Pre-load the GPX route at startup. On each GPS fix, find the nearest route point
using `track.get_nearest_location(gpxpy.geo.Location(lat, lon))`. Compute km
remaining using total track length minus cumulative distance to that point. Cache
the result — GPS updates at 1 Hz, route calculation at 1 Hz is acceptable overhead.

**Confidence: HIGH** — gpxpy is the standard Python GPX library; capabilities
verified against PyPI documentation and README.

---

### 5. Thermal Resilience

**Recommendation: stdlib only (subprocess + /sys filesystem) + config thresholds**

Thermal resilience on the Pi is about detecting and responding to throttling events,
not preventing them at the hardware level. The software response is:

1. Detect throttling (`vcgencmd get_throttled` — already covered under health monitoring).
2. Log at WARNING level with structlog.
3. Optionally reduce the timelapse capture rate (highest sustained CPU consumer).
4. Emit a Prometheus metric for remote visibility.

No additional Python library is needed. CPU temperature is read from
`/sys/class/thermal/thermal_zone0/temp` (divide by 1000 for Celsius) — this is
faster and more reliable than psutil's sensor path on RPi.

**Thresholds (RPi hardware, HIGH confidence):**

| Temperature | Condition | Response |
|-------------|-----------|----------|
| < 60°C | Normal | No action |
| 60–80°C | Warm | Log at INFO; emit metric |
| 80°C | Soft throttle begins | Log at WARNING; reduce timelapse rate |
| 82°C+ | Hard throttling active | Log at ERROR; emit degraded metric |
| 85°C | Hardware limit | Pi will throttle aggressively |

**What NOT to add:**

- Active cooling control via GPIO fan — valid engineering but out of scope; the car's cabin airflow provides passive cooling; if throttling is sustained, it is a hardware mounting problem, not a software problem.

**Confidence: HIGH** — temperature limits are documented in official RPi hardware specs.

---

### 6. Storage Management

**Recommendation: log2ram (OS-level) + stdlib (pathlib, shutil) for capture rotation**

Two separate storage problems:

**SD card wear (journald + /var/log writes):**

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| log2ram | latest (azlux/log2ram) | Mount /var/log in RAM, flush periodically | Purpose-built for RPi; syncs to disk on clean shutdown; survives unclean power loss with at most one sync interval of logs lost (acceptable given structlog also writes to journald); install via azlux Debian repo |

Set `SIZE=128M` (default 40M is too small given structlog verbosity at 100 Hz event rate). Configure journald `SystemMaxUse=50M` to bound persistent storage.

**Capture storage rotation (video files filling the SD card):**

No new library needed — the existing `EventStorage` class already has `max_event_age_days` and `max_event_storage_mb` enforcement. Extend this pattern for captures:

- Enforce `max_capture_age_days` in `CaptureSyncService` post-sync: delete local copies of files that have been confirmed synced to NAS.
- Add a disk-space floor check: if free space drops below 500 MB, delete oldest captures regardless of age.

Use `shutil.disk_usage(path)` (stdlib) — no additional library needed.

**What NOT to use:**

- overlayFS (raspi-config) — makes the root filesystem read-only; incompatible with SQLite WAL writes to `/var/lib/shitbox/`; the project needs write access to its data directory at all times.
- logrotate — already present on Raspbian but does not help with journald; use journald's `SystemMaxUse` instead.

**Confidence: HIGH** for log2ram (actively maintained, Bookworm-compatible per azlux
apt repo). HIGH for stdlib disk management.

---

## Installation Summary

### New Python Dependencies

```bash
# In pyproject.toml [project.dependencies]:
pip install sdnotify>=0.3.2
pip install prometheus_client>=0.20.0
pip install psutil==6.1.1
pip install pygame-ce>=2.5.0
pip install gpxpy>=1.6.2
```

### New System-Level Dependencies

```bash
# SD card wear reduction
curl -s https://azlux.fr/repo.gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/azlux-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/azlux-archive-keyring.gpg] http://packages.azlux.fr/debian/ bookworm main" | sudo tee /etc/apt/sources.list.d/azlux.list
sudo apt update && sudo apt install log2ram

# SDL2 for pygame-ce on Bookworm (may already be present)
sudo apt install libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 libsdl2-mixer-2.0-0

# vcgencmd is pre-installed on Raspberry Pi OS
which vcgencmd  # should return /usr/bin/vcgencmd
```

### systemd Unit Changes

The existing `shitbox-telemetry.service` needs these additions:

```ini
[Service]
Type=notify
WatchdogSec=30
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
```

New unit for the driver display:

```ini
# /etc/systemd/system/shitbox-display.service
[Unit]
Description=Shitbox Driver Display
After=shitbox-telemetry.service
Requires=shitbox-telemetry.service

[Service]
Type=simple
User=pi
Environment=SDL_VIDEODRIVER=kmsdrm
ExecStart=/opt/shitbox/venv/bin/python -m shitbox.display.dashboard
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Watchdog Python lib | sdnotify 0.3.2 | systemd-watchdog (PyPI) | systemd-watchdog adds abstraction for no benefit; sdnotify is simpler and more widely used |
| Display framework | pygame-ce 2.5.x | Kivy | Kivy has known RPi touchscreen driver issues; heavier runtime |
| Display framework | pygame-ce 2.5.x | tkinter | Requires X11; slow boot; unacceptable for in-car display |
| Health metrics | psutil + vcgencmd | node_exporter | Go binary adds process weight; duplicates existing Python metrics path |
| Route tracking | gpxpy 1.6.2 | shapely/pyproj | C extension heavyweight; overkill for 1D route progress |
| SD card protection | log2ram | overlayFS | overlayFS makes root read-only, breaks SQLite WAL writes |
| Process supervision | systemd Restart= | supervisord | supervisord adds external dependency; systemd already present |
| pygame version | pygame-ce 2.5.6 | pygame 2.6.1 | pygame-ce is more actively maintained; last pygame release Sep 2024 vs pygame-ce Oct 2025 |

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Watchdog (sdnotify + systemd) | HIGH | Official protocol; well-documented; widely deployed |
| Health monitoring (psutil + vcgencmd) | MEDIUM | psutil version constraint needs GLIBC validation on target image |
| Driver display (pygame-ce) | MEDIUM | KMSDRM path confirmed in forums; exact SDL2 package list needs integration test |
| Rally stage tracking (gpxpy) | HIGH | Standard library; stable API; pure Python |
| Thermal resilience (stdlib) | HIGH | No new library; /sys path and vcgencmd are RPi standards |
| Storage management (log2ram + stdlib) | HIGH | log2ram well-established; stdlib disk management trivial |

---

## Sources

- systemd sd_notify protocol: <https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html>
- sdnotify (pure Python): <https://github.com/bb4242/sdnotify>
- RPi hardware watchdog limit (15s): <https://dri.es/keeping-your-raspberry-pi-online-with-watchdogs>
- RPi forum: watchdog on Pi3B+: <https://forums.raspberrypi.com/viewtopic.php?t=210974>
- pygame-ce PyPI: <https://pypi.org/project/pygame-ce/>
- pygame-ce release history: <https://github.com/pygame-community/pygame-ce/releases>
- pygame-ce on Pi5 + 7" Screen 2: <https://forums.raspberrypi.com/viewtopic.php?t=383284>
- pygame Bookworm KMSDRM: <https://forums.raspberrypi.com/viewtopic.php?t=358144>
- psutil PyPI (version 7.2.2 / GLIBC note): <https://pypi.org/project/psutil/>
- vcgencmd get_throttled bitmask: <https://forums.raspberrypi.com/viewtopic.php?t=257569>
- gpxpy PyPI: <https://pypi.org/project/gpxpy/>
- log2ram GitHub: <https://github.com/azlux/log2ram>
- SD card wear reduction (2024): <https://www.dzombak.com/blog/2024/04/pi-reliability-reduce-writes-to-your-sd-card/>
- Raspberry Pi temperature limits: <https://www.sunfounder.com/blogs/news/raspberry-pi-temperature-guide-how-to-check-throttling-limits-cooling-tips>
- SQLite WAL and power loss: <https://sqlite.org/wal.html>
- overlayFS incompatibility on Bookworm: <https://github.com/raspberrypi/bookworm-feedback/issues/137>
