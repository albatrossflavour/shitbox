# Project Research Summary

**Project:** Shitbox Rally Telemetry — Hardening Milestone
**Domain:** Embedded automotive telemetry — offline-first, multi-day rally in remote Australia
**Researched:** 2026-02-25
**Confidence:** HIGH (existing system well-understood; new component patterns well-established)

## Executive Summary

Shitbox is an offline-first rally telemetry system running on Raspberry Pi in a 2001 Ford Laser
driving 4,000 km across remote Australia. The hardening milestone is not a feature expansion — it
is a reliability campaign. The existing architecture (SQLite WAL, batch Prometheus sync, 100 Hz
IMU event detection) is sound. What it lacks is the operational hardening required to survive
twenty hard power cuts per day, 50°C cabin temperatures, zero mobile coverage for 12-hour
stretches, and ten consecutive driving days without human intervention.

The recommended approach is to add five new subsystems as satellites around the existing
`UnifiedEngine` without restructuring it: a health monitor with hardware watchdog integration, a
thermal monitor, a storage lifecycle manager, a GPS-based stage tracker, and a driver display
process. All new subsystems follow the existing daemon-thread-with-state-dict pattern. The display
is the single exception — it runs as a separate OS process to isolate pygame/SDL from the 100 Hz
IMU path. Dependencies are sequential: boot recovery first, then watchdog, then thermal/storage in
parallel, then stage tracker, then display last.

The two highest-consequence risks are SD card failure from continuous high-rate writes and silent
data loss from storage exhaustion. Both are hardware-and-software problems: the software fixes
(WAL checkpoint tuning, proactive eviction, video buffer to USB drive, high-endurance SD card) are
necessary but not sufficient without the correct physical media. A third risk — thermal throttling
causing IMU sample stalls — requires both software monitoring and physical heat management (heatsink
plus fan in the enclosure). Plan for these before the rally departs; none can be fixed remotely.

## Key Findings

### Recommended Stack

The new hardening milestone adds six targeted dependencies to the existing Python 3.9 / Raspberry
Pi OS Bookworm stack. All choices favour pure Python, minimal C extensions, and proven embedded
Linux patterns over heavyweight frameworks.

See full rationale in `.planning/research/STACK.md`.

**Core technologies:**

- **sdnotify 0.3.2+:** Pure Python sd_notify protocol — sends `WATCHDOG=1` keepalives to systemd;
  zero C dependencies; integrates into the existing `UnifiedEngine` health-check loop
- **prometheus_client 0.20.0+:** Exposes health Gauges/Counters via the existing remote_write
  path; no new infrastructure (no Pushgateway)
- **psutil 6.1.1 (pinned):** CPU/memory/disk/network metrics; pin to 6.1.1 until GLIBC_2.34
  constraint on Bookworm is validated
- **pygame-ce 2.5.6:** Community Edition fork of pygame; more actively maintained than upstream;
  SDL2/KMSDRM path works on Bookworm without X11; runs fullscreen at 10 Hz on the 7" DSI display
- **gpxpy 1.6.2:** Pure Python GPX parsing; provides nearest-point and cumulative distance
  calculation for stage progress tracking
- **log2ram (system):** Mounts `/var/log` in RAM, flushes periodically; reduces journald write
  pressure on the SD card; install from azlux Bookworm repo with `SIZE=128M`
- **vcgencmd / thermal sysfs (stdlib only):** No new library needed for thermal resilience;
  read `/sys/class/thermal/thermal_zone0/temp` directly

**Critical version/config constraints:**

- `RuntimeWatchdogSec=14` maximum — BCM2835 hardware watchdog silently ignores values above 15s
- `pygame-ce` requires `SDL_VIDEODRIVER=kmsdrm` in the systemd unit environment
- `psutil` 7.x requires GLIBC_2.34 — validate before upgrading beyond 6.1.1

### Expected Features

The Shitbox Rally's 4,000 km outback profile makes several "nice to have" features mandatory.
The framing is: systems that fail without recovery during the rally are table stakes; systems
that improve crew confidence and engagement are differentiators.

See full analysis in `.planning/research/FEATURES.md`.

**Must have (system survival):**

- Hardware watchdog via BCM2835 — prevents silent kernel hangs with no recovery path
- systemd `Restart=always` audit and repair — crash during driving means zero data until noticed
- Proactive disk eviction starting at 70% — SD card fills in under two days at current write rate
- SQLite WAL checkpoint management — WAL grows unbounded at 100+ readings/sec
- ffmpeg health monitoring with automatic restart — silent video loss is unacceptable
- Thermal monitoring with OLED/buzzer alerts — 50°C cabin, Pi throttles at 80°C

**Should have (data quality and crew confidence):**

- Remote health reporting via Prometheus — crew visibility from home
- Persistent event queue for failed uploads — no events lost if sync fails mid-rally
- Configuration hot-reload via SIGHUP — tune thresholds without restarting and losing in-flight data

**Nice to have (driver awareness and engagement):**

- Driver dashboard on 7" touchscreen — speed, heading, trip distance, system health
- Rally stage/day progress tracking — cumulative distance, current day distance
- Live website position update — followers track the route in real time

**Defer (hardware work or unacceptable risk):**

- Graceful shutdown on power loss — requires new hardware wiring; WAL mode already mitigates adequately
- Read-only OS filesystem (overlayfs) — high implementation risk; incompatible with SQLite WAL data writes

**Anti-features (explicitly out of scope):**

Real-time video streaming, OBD-II integration (2001 Laser is OBD-I), per-session lap timing,
AI/ML event classification, automatic OTA updates, MQTT re-enable.

### Architecture Approach

New subsystems integrate as satellites around the existing `UnifiedEngine` without restructuring
it. Engine-side subsystems follow the existing daemon-thread-with-state-dict pattern. The display
is the single exception — it runs as a separate OS process so pygame/SDL cannot interfere with the
100 Hz IMU sampler. The engine exposes state via a `multiprocessing.Queue` (maxsize=2, non-blocking
puts); the display consumes at its own 10 Hz render rate and drops frames rather than blocking.

See full component boundaries and data flow in `.planning/research/ARCHITECTURE.md`.

**Major components and their responsibilities:**

1. **BootRecovery** — closes unclosed events from prior crash; validates DB integrity; writes BOOT
   event; runs before any other thread starts
2. **HealthMonitor** — aggregates per-thread liveness heartbeats; gates `WATCHDOG=1` keepalives on
   verified health (not unconditionally); emits Prometheus metrics via existing BatchSync
3. **ThermalMonitor** — reads `/sys/class/thermal/thermal_zone0/temp` on 5s interval; publishes
   to `thermal_state` dict consumed by HealthMonitor and DisplayProcess
4. **StorageManager** — enforces disk quota (prune video at 85%, SQLite rows at 95%); runs WAL
   `TRUNCATE` checkpoint every 6 hours on 15-minute interval daemon thread
5. **StageTracker** — loads GPX route at boot; calculates nearest waypoint and cumulative distance
   at 1 Hz from GPS output; feeds `stage_state` dict
6. **DisplayProcess** — separate OS process; pygame-ce fullscreen at 800x480; renders four panels
   (speed/heading, stage progress, health badges, thermal bar) at 10 Hz

**Key patterns:**

- State dict publisher: `threading.Lock`-protected dict, `get_snapshot()` returns `dict.copy()`
- Daemon thread service: `stop_event.wait(interval)` loop with `start()`/`stop()` lifecycle
- Display queue: `Queue.put_nowait()` in engine (drop if full), `Queue.get_nowait()` in display

### Critical Pitfalls

See full analysis with prevention strategies in `.planning/research/PITFALLS.md`.

1. **SD card corruption on hard power loss** — Configure SQLite with `synchronous=FULL` and
   `journal_mode=WAL` together (WAL alone with `synchronous=NORMAL` is not durable). Move video
   ring buffer to a USB drive. Run `PRAGMA integrity_check` on startup; fall back gracefully.
2. **SD card wear exhaustion from continuous writes** — Mandatory hardware fix: use a high-endurance
   dashcam-rated SD card (Samsung Pro Endurance or SanDisk Max Endurance). Software: move video
   buffer to USB, enable log2ram, disable swap on SD.
3. **Automotive 12V voltage spikes killing the Pi** — Hardware: automotive-grade DC-DC converter
   with transient suppression (not a generic USB car charger). Software: monitor `vcgencmd
   get_throttled` for brownout evidence; log INA219 voltage if wired.
4. **Thermal throttling causing 100 Hz IMU sample stalls** — Hardware: heatsink + fan in enclosure.
   Software: `ThermalMonitor` writes to shared dict; sampler reads dict rather than polling sysfs.
   Log throttle state at every health check interval.
5. **GPS cold start blocking startup, triggering watchdog loop** — Make GPS fix acquisition
   asynchronous; `READY=1` to systemd as soon as daemon is running, not when GPS is fixed. Set
   watchdog timeout generously (120s) to survive cold start. Use `fake-hwclock -n` to save time
   more frequently.

**Additional pitfalls to address before the rally:**

- ffmpeg `is_running` property lies (does not call `poll()`) — fix as a bug in Watchdog phase
- `id(event)` dict keys can be recycled by GC — replace with UUID before the rally
- GPS socket leak in `_get_satellite_count()` — convert to persistent socket in Boot Recovery phase
- WireGuard tunnel stale after 400 km with no signal — set `PersistentKeepalive=25` immediately

## Implications for Roadmap

Research strongly indicates a five-phase sequential build order based on component dependencies.
Each phase enables the next; earlier phases protect data integrity, later phases improve experience.

### Phase 1: Bulletproof Boot Recovery

**Rationale:** Foundation for everything else. Protects data integrity before any new components
are deployed. Fixes existing bugs that will cause data loss during the rally regardless of other
changes. No dependencies on other new components.

**Delivers:** System that survives hard power cuts without data corruption or startup failure.
Existing bugs that silently lose data are closed before adding complexity.

**Addresses:**
- Boot after hard power cut (table stakes)
- GPS cold start blocking startup (critical pitfall)
- SQLite `integrity_check` on startup (critical pitfall)
- GPS socket leak bug (moderate pitfall)
- `id(event)` UUID bug (minor pitfall)
- `synchronous=FULL` validation (critical pitfall)
- GPS stable udev symlink (`/dev/gps0`)
- `fake-hwclock` save frequency increase

**Avoids:** Pitfall 1 (SD card corruption), Pitfall 5 (GPS cold start watchdog loop), Pitfall 11
(clock drift), Pitfall 12 (socket leak), Pitfall 14 (id() key recycling)

**Research flag:** Standard patterns — no deeper research needed. WAL, systemd, udev rules all
well-documented.

---

### Phase 2: Watchdog and Self-Healing

**Rationale:** Provides observability and automatic recovery for everything built after it. Other
new threads register heartbeats with `HealthMonitor`. Must come before Thermal/Storage so those
threads can be monitored from day one.

**Delivers:** Hardware watchdog active; all services auto-restart on crash; ffmpeg zombie fixed;
I2C bus recovery logic in place; health metrics flowing to Prometheus.

**Addresses:**
- Hardware watchdog BCM2835 (`dtparam=watchdog=on`, `RuntimeWatchdogSec=14`)
- systemd `Restart=always` audit for all units
- ffmpeg `is_running` bug fix (use `poll()`)
- ffmpeg mtime-based health check
- I2C bus lockup recovery (9-clock bit-bang reset)
- `HealthMonitor` daemon thread with `sdnotify` keepalive
- prometheus_client health Gauges via BatchSync
- In-car buzzer expansion for fault alerts

**Uses:** sdnotify 0.3.2, prometheus_client 0.20.0, psutil 6.1.1, vcgencmd subprocess

**Avoids:** Pitfall 3 (brownout logging), Pitfall 4 (sampler stall detection), Pitfall 6 (I2C
lockup), Pitfall 8 (ffmpeg zombie)

**Research flag:** Standard patterns. sdnotify + systemd watchdog well-documented. ffmpeg health
check is a straightforward bug fix.

---

### Phase 3: Thermal Resilience and Storage Management

**Rationale:** These two are independent of each other but both depend on HealthMonitor existing
(Phase 2). Can be built in parallel. Both are standalone daemon threads with no cross-dependencies.
Thermal state feeds HealthMonitor. Storage manager is self-contained.

**Delivers:** Early thermal warning before throttling degrades 100 Hz sampling; proactive disk
eviction preventing SD card exhaustion; WAL checkpoint preventing WAL overflow; log2ram reducing
SD card write pressure.

**Addresses:**
- `ThermalMonitor` with 70°C/80°C thresholds (five-second interval)
- vcgencmd throttle bitmask monitoring
- `StorageManager` with 70%/85%/95% thresholds
- Video file eviction (synced files first, unsynced last)
- Sync-status tracking per file in SQLite
- WAL `TRUNCATE` checkpoint every 6 hours
- log2ram system installation (`SIZE=128M`)
- journald `SystemMaxUse=200M` configuration
- swap disable on SD card

**Uses:** stdlib only (pathlib, shutil, subprocess), log2ram system package

**Avoids:** Pitfall 2 (SD wear exhaustion), Pitfall 4 (thermal stalls), Pitfall 9 (storage
exhaustion silent data loss), Pitfall 15 (log volume from ROUGH_ROAD bursts)

**Research flag:** Standard patterns. Thermal sysfs, log2ram, and storage pruning all
well-documented. The sync-status tracking logic (which files are safe to delete) needs careful
design to avoid deleting unsynced video — flag for implementation planning.

---

### Phase 4: Stage Tracking and Remote Health

**Rationale:** Stage tracking depends on GPS collector being stable (Phase 1 ensures this) and
HealthMonitor existing to absorb its health state (Phase 2). Remote health depends on Prometheus
metrics infrastructure from Phase 2. These can be built in parallel.

**Delivers:** Distance-covered-today, cumulative km, progress-to-destination on display and in
Prometheus. Remote crew visibility of CPU temp, disk %, sync backlog, and throttle state.

**Addresses:**
- `StageTracker` daemon thread with gpxpy GPX loading
- Nearest-waypoint haversine calculation at 1 Hz
- Day boundary detection (new boot = new day, or GPS date change)
- `stage_state` dict for display consumption
- Remote health Prometheus metrics (CPU temp, disk %, sync backlog, voltage)
- WireGuard `PersistentKeepalive=25` configuration
- Batch sync cap at 2,000 readings per push
- Configuration hot-reload via SIGHUP

**Uses:** gpxpy 1.6.2, stdlib math (haversine), prometheus_client (existing)

**Avoids:** Pitfall 10 (WireGuard stale tunnel), Pitfall 11 (sync backlog overwhelming Prometheus)

**Research flag:** Stage tracker needs a GPX route file to be defined before implementation can
be tested end-to-end (operational dependency). Confirm the Shitbox Rally 2026 route is available
in GPX format. The haversine nearest-point algorithm is O(N) per GPS fix — validate performance
at expected route density (500+ waypoints).

---

### Phase 5: Driver Display

**Rationale:** Last because it consumes all other state dicts (GPS, stage, health, thermal) which
must exist first. Can be built incrementally: Panel A (GPS only) ships early, subsequent panels
added as Phase 3/4 state dicts become available.

**Delivers:** Fullscreen 7" driver dashboard showing speed, heading, trip distance, stage progress,
system health badges, thermal bar, and throttle warning.

**Addresses:**
- `shitbox-display.service` systemd unit with `SDL_VIDEODRIVER=kmsdrm`
- `multiprocessing.Queue` IPC from engine to display process
- pygame-ce 800x480 fullscreen at 10 Hz
- Four display panels: GPS state, stage state, health state, thermal state
- Display crash isolation from engine (separate process)
- Graceful display-off fallback if pygame fails to initialise

**Uses:** pygame-ce 2.5.6, Pillow 10.0.0+, multiprocessing.Queue (stdlib)

**Avoids:** Anti-pattern: blocking 100 Hz IMU path with display work; anti-pattern: display as
thread inside UnifiedEngine

**Research flag:** pygame-ce KMSDRM path on Bookworm confirmed in forums but needs integration
testing on target hardware. SDL2 package list (`libsdl2-2.0-0`, `libsdl2-image-2.0-0`,
`libsdl2-ttf-2.0-0`) must be validated. Flag for a hardware-in-loop test early in this phase.

---

### Phase Ordering Rationale

- **Boot Recovery first** — fixes existing data-loss bugs before adding any complexity; validates
  baseline
- **Watchdog second** — enables per-thread liveness monitoring for all subsequent phases; is itself
  the self-healing mechanism if phases 3–5 introduce new failure modes
- **Thermal and Storage third (parallel)** — both standalone threads; no cross-dependency; both
  feed Phase 4 health reporting
- **Stage tracking and remote health fourth** — stage tracking feeds Phase 5 display; remote health
  closes the loop to the Prometheus infrastructure already validated in Phase 2
- **Display last** — highest integration complexity; consumes all prior state; can be deferred
  without impacting data integrity if time runs short before the rally

### Research Flags

**Phases needing deeper research or early validation:**

- **Phase 3 (Storage Management):** Sync-status tracking logic — which files are safe to delete
  during proactive cleanup requires careful schema design. Risk of deleting unsynced video during
  connectivity gap. Deserves a planning spike.
- **Phase 4 (Stage Tracking):** GPX route file availability for Shitbox Rally 2026 is an
  operational dependency. Confirm format and download before implementation starts.
- **Phase 5 (Driver Display):** pygame-ce KMSDRM on target Bookworm image needs hardware-in-loop
  validation early. SDL2 package list may differ between Bookworm releases.

**Phases with standard patterns (no research needed):**

- **Phase 1 (Boot Recovery):** WAL config, systemd, udev, gpsd — all well-documented with
  authoritative sources
- **Phase 2 (Watchdog):** sdnotify + systemd watchdog are a published protocol; ffmpeg
  `poll()` fix is a straightforward bug

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All new dependencies have official documentation and known Bookworm compatibility, except psutil GLIBC constraint (MEDIUM for version pinning) |
| Features | HIGH | Feature priority is well-grounded in the rally's specific operational profile; 8-day/4,000 km context makes priority clear |
| Architecture | HIGH | Existing system is well-documented; new component patterns (daemon thread, state dict, multiprocessing.Queue) are established Python patterns |
| Pitfalls | HIGH | Critical pitfalls backed by official SQLite docs, RPi hardware specs, and WireGuard documentation; automotive power pitfall backed by Analog Devices and Littelfuse |

**Overall confidence:** HIGH

### Gaps to Address

- **psutil GLIBC_2.34 constraint:** Pin to 6.1.1 until validated on exact Bookworm Pi image. Add
  a note to Phase 2 planning to validate this before committing the version.
- **pygame-ce KMSDRM exact package list:** The SDL2 package dependencies for Bookworm may vary.
  Validate the full install list on target hardware before Phase 5 planning.
- **Shitbox Rally 2026 GPX route file:** Stage tracker cannot be tested end-to-end without a GPX
  file. Obtain before Phase 4 implementation begins.
- **`synchronous=FULL` current config:** PITFALLS.md identifies this as critical but the current
  config.yaml value is unknown. Verify in Phase 1 before assuming WAL is durable.
- **Video buffer location (SD vs USB):** PITFALLS.md recommends moving the video ring buffer to
  USB. This is a hardware and config change. Confirm physical USB drive is present in the car build
  before Phase 3 implementation.
- **INA219 voltage monitoring:** PITFALLS.md recommends logging brownout events via INA219.
  Confirm whether the INA219 is wired and reading correctly before adding monitoring in Phase 2.

## Sources

### Primary (HIGH confidence)

- [SQLite WAL Mode — Official Docs](https://sqlite.org/wal.html) — durability, WAL checkpoint
- [sd_notify protocol — freedesktop.org](https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html) — watchdog keepalive
- [BCM2835 watchdog driver — Linux kernel](https://github.com/torvalds/linux/blob/master/drivers/watchdog/bcm2835_wdt.c) — 15s hardware maximum
- [systemd RuntimeWatchdogSec silent failure — GitHub #27427](https://github.com/systemd/systemd/issues/27427) — 14s cap
- [WireGuard PersistentKeepalive — official docs](https://www.oreateai.com/blog/understanding-persistentkeepalive-in-wireguard-keeping-your-vpn-connection-alive/abf0b8aa7afab6c76a9910986dce8dcd) — 25s setting
- [Raspberry Pi temperature limits — official](https://www.sunfounder.com/blogs/news/raspberry-pi-temperature-guide-how-to-check-throttling-limits-cooling-tips) — 80°C throttle threshold
- [multiprocessing.Queue — Python stdlib](https://docs.python.org/3/library/multiprocessing.html) — IPC pattern
- [SQLite WAL durability analysis](https://www.agwa.name/blog/post/sqlite_durability) — synchronous=FULL requirement

### Secondary (MEDIUM confidence)

- [pygame-ce KMSDRM on Pi5 + 7" Screen 2 — RPi forums](https://forums.raspberrypi.com/viewtopic.php?t=383284) — confirmed working pattern
- [gpxpy PyPI](https://pypi.org/project/gpxpy/) — nearest-point API
- [log2ram GitHub (azlux)](https://github.com/azlux/log2ram) — Bookworm compatibility, SIZE config
- [SD card endurance — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=317568) — TLC write cycle limits
- [pi-reliability reduce-writes — dzombak.com (2024)](https://www.dzombak.com/blog/2024/04/pi-reliability-reduce-writes-to-your-sd-card/) — log2ram and noatime
- [ext4 noatime + commit interval](https://www.dzombak.com/blog/2021/11/Reducing-SD-Card-Wear-on-a-Raspberry-Pi-or-Armbian-Device.html) — mount options
- [GPS tracking challenges in remote Australia — Locate2u](https://www.locate2u.com/gps-tracking/gps-tracking-challenges-in-regional-and-remote-australia/) — cold start profile
- [Automatic I2C stuck bus recovery — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=326603) — 9-clock recovery

### Tertiary (contextual/forum)

- [gpsd fails to reconnect after USB unplug — gpsd GitLab #60](https://gitlab.com/gpsd/gpsd/-/issues/60) — udev rule requirement
- [ffmpeg zombie — moviepy GitHub #833](https://github.com/Zulko/moviepy/issues/833) — poll() pattern
- [Automotive power supply pitfalls — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=352266) — TVS diode recommendation
- [Shitbox Rally 2025 — route details](https://www.shitboxrally.com.au/rallies) — outback connectivity profile

---

*Research completed: 2026-02-25*
*Ready for roadmap: yes*
