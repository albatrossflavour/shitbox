# Architecture Patterns

**Domain:** Rally car telemetry — hardening, driver display, route tracking
**Researched:** 2026-02-25
**Overall confidence:** HIGH (existing system well-documented; new component patterns well-established)

## Existing Architecture Baseline

The system runs as a single `UnifiedEngine` daemon with three concurrent paths:

- **High-rate path (100 Hz):** MPU6050 IMU sampler → ring buffer → event detector → SQLite event
  storage + ffmpeg video capture
- **Low-rate path (1 Hz):** GPS/IMU/temperature collectors → SQLite telemetry → batch sync to
  Prometheus over WireGuard
- **Capture path:** GPIO button → manual video recording via ffmpeg subprocess

Key structural properties to preserve:

- All collectors run as daemon threads under `UnifiedEngine`
- All sensor data lands in SQLite first (offline-first guarantee)
- Services have `start()`/`stop()` lifecycle with `connection.is_connected` guard
- Config flows from YAML → nested dataclasses → flat `EngineConfig` fields

## Recommended Architecture for New Components

The milestone adds five new subsystems. They integrate as satellites around the existing engine
without restructuring it. The engine stays the source of truth; new subsystems consume from it.

```
┌─────────────────────────────────────────────────────────────────┐
│                        UnifiedEngine                            │
│                                                                 │
│  [High-rate path]   [Low-rate path]   [Capture path]           │
│  IMU → RingBuf  →   GPS/Temp/IMU  →   Button → ffmpeg         │
│  EventDetector  →   SQLite        →                            │
│  EventStorage   →   BatchSync     →                            │
│                                                                 │
│  [NEW: Health subsystem]                                        │
│  HealthMonitor ──publishes──→ health_state (in-process dict)   │
│       ↓                                                         │
│  systemd sd_notify (WatchdogSec keepalive)                     │
│       ↓                                                         │
│  Prometheus remote_write (health metrics via BatchSync)        │
│                                                                 │
│  [NEW: Stage tracker]                                           │
│  StageTracker ──reads── GPSCollector output                    │
│  StageTracker ──writes─→ stage_state (in-process dict)         │
│                                                                 │
│  [NEW: Thermal monitor]                                         │
│  ThermalMonitor ──reads── /sys/class/thermal/thermal_zone0/temp│
│  ThermalMonitor ──writes─→ thermal_state (in-process dict)     │
│                                                                 │
│  [NEW: Storage lifecycle]                                       │
│  StorageManager ──manages── SQLite WAL + disk quota            │
│                                                                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │  read-only state dicts (thread-safe)
                       ▼
        ┌──────────────────────────┐
        │      DisplayProcess      │
        │  (separate OS process)   │
        │                          │
        │  pygame → /dev/fb0       │
        │  Panels: speed/heading/  │
        │  trip / health / stage   │
        └──────────────────────────┘
```

### Design decisions

**In-process shared state dicts for IPC** — The display is the only consumer outside the engine
process. The simplest correct approach is a small number of `threading.Lock`-protected dicts
published by engine subsystems, exposed to the display via `multiprocessing.Queue` or a
`multiprocessing.shared_memory` slab. Queue is preferred: simpler, lower coupling, naturally
rate-limited to display refresh (~10 Hz). Shared memory is only needed if latency becomes
measurable, which it will not at these data rates.

**Display as a separate process, not thread** — pygame/SDL holds a lock on `/dev/fb0` and
must be the sole owner of that device. Running it as a thread inside `UnifiedEngine` risks
blocking the GIL at inconvenient moments and complicates crash isolation. A separate process
(launched by the engine, supervised by systemd) means the display can crash and restart
without affecting data capture. The engine drops display state updates into a `Queue` at each
1 Hz low-rate tick.

**Stage tracker as a daemon thread inside the engine** — It only reads GPS output that the
existing `GPSCollector` already produces. No new I/O path required. It can subscribe to the
same data flowing to SQLite by writing a thin observer or by reading the most recent GPS row
from SQLite at 1 Hz. SQLite read inside the engine is safe with the existing thread-local
connection pattern.

## Component Boundaries

| Component | Responsibility | Reads From | Writes To |
|---|---|---|---|
| `UnifiedEngine` | Orchestrates all daemon threads; owns lifecycle | YAML config | Nothing directly |
| `HealthMonitor` | Aggregates per-service liveness; sends sd_notify keepalive; emits health metrics | Thread liveness flags, `/proc`, thermal state | `health_state` dict, systemd socket, Prometheus |
| `StageTracker` | Loads GPX route; calculates nearest waypoint, distance-to-finish, elapsed km | GPS collector output / SQLite | `stage_state` dict |
| `ThermalMonitor` | Reads CPU temperature from sysfs; applies threshold policy (warn / throttle) | `/sys/class/thermal/thermal_zone0/temp` | `thermal_state` dict, log |
| `StorageManager` | Enforces disk quota; prunes old SQLite rows and video files; checkpoints WAL | SQLite, filesystem | SQLite (DELETE), filesystem (unlink) |
| `DisplayProcess` | Renders driver dashboard on 7" framebuffer; no writes to engine state | `multiprocessing.Queue` fed by engine | `/dev/fb0` via pygame/SDL |
| `BootRecovery` | Validates prior-shutdown state at startup; resets corrupted flags; writes boot event | SQLite `events` table | SQLite, log |

## Data Flow

### Health monitoring flow

```
[Thread liveness flags]  ──┐
[ThermalMonitor state]   ──┤
[SQLite row counts]      ──┤──→ HealthMonitor (10s interval)
[disk usage]             ──┤         │
[GPS fix quality]        ──┘         ├──→ sd_notify(WATCHDOG=1)  → systemd
                                     ├──→ health_state dict      → DisplayProcess queue
                                     └──→ Prometheus metrics     → BatchSync (existing)
```

### Stage tracking flow

```
[GPSCollector] ──(1 Hz fix)──→ StageTracker
                                    │
                               [GPX waypoints loaded at boot]
                                    │
                               haversine distance to each waypoint
                                    │
                               nearest point index → progress %,
                               distance-to-finish, segment bearing
                                    │
                               stage_state dict ──→ DisplayProcess queue
```

### Display flow

```
Engine (1 Hz tick):
  gps_state     ──┐
  stage_state   ──┤──→ Queue.put_nowait(snapshot)  [non-blocking, drops if full]
  health_state  ──┤
  thermal_state ──┘

DisplayProcess (10 Hz render loop):
  Queue.get_nowait() or use last snapshot
       │
  pygame surface composition:
    Panel A: Speed (km/h), heading, GPS fix age
    Panel B: Stage progress %, distance-to-finish, elapsed km
    Panel C: System health badges (each subsystem OK/WARN/FAIL)
    Panel D: Thermal bar + throttle warning
       │
  pygame.display.flip() → /dev/fb0
```

### Boot recovery flow

```
systemd starts UnifiedEngine
       │
BootRecovery.run() (first action in __init__, before other threads start)
       │
  ├── Check SQLite for open events (no end_time) → close them with reason="unclean_shutdown"
  ├── Check WAL file exists from prior crash → log warning, let SQLite self-heal on first open
  ├── Validate config integrity → abort with clear error if invalid
  └── Write BOOT event to events table
       │
Continue normal engine startup → start all daemon threads
```

### Thermal management flow

```
ThermalMonitor (5s interval):
  read /sys/class/thermal/thermal_zone0/temp
       │
  < 70°C → OK, publish to thermal_state
  70-80°C → WARN, log, reduce high-rate IMU poll if possible
  > 80°C  → CRITICAL, log, alert via health_state
       │
  thermal_state dict ──→ HealthMonitor ──→ DisplayProcess
```

### Storage lifecycle flow

```
StorageManager (15 min interval):
  ├── Check disk usage (shutil.disk_usage)
  │     > 85% used → prune oldest N video files by mtime
  │     > 95% used → prune oldest SQLite telemetry rows (keep events)
  ├── SQLite WAL checkpoint (PRAGMA wal_checkpoint(TRUNCATE))
  │     run every 6 hours regardless of usage
  └── Log storage stats → Prometheus via BatchSync
```

## Patterns to Follow

### Pattern 1: State dict publisher (existing pattern extended)

Each new subsystem maintains a module-level `threading.Lock` and a dict. The engine calls
`get_snapshot()` to read a copy without holding the lock beyond a single `dict.copy()` call.

```python
import threading

_lock = threading.Lock()
_state: dict = {"cpu_temp_c": 0.0, "status": "unknown"}

def update(temp_c: float, status: str) -> None:
    with _lock:
        _state["cpu_temp_c"] = temp_c
        _state["status"] = status

def get_snapshot() -> dict:
    with _lock:
        return _state.copy()
```

This is zero-dependency, testable in isolation, and matches the existing engine style.

### Pattern 2: Daemon thread service (existing pattern)

All new engine-side subsystems follow `BatchSyncService` exactly:

```python
class ThermalMonitor:
    def __init__(self, config: ThermalConfig) -> None:
        self._config = config
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="thermal-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.wait(self._config.interval_s):
            # do work
```

### Pattern 3: Display process with queue

The engine spawns the display process once at startup and passes it one end of a
`multiprocessing.Queue`. Engine drops non-blocking snapshots; display drains at its own rate.

```python
import multiprocessing

class DisplayProcess:
    def __init__(self) -> None:
        self._queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=2)
        self._proc: multiprocessing.Process | None = None

    def start(self) -> None:
        self._proc = multiprocessing.Process(
            target=_display_main, args=(self._queue,), daemon=True, name="display"
        )
        self._proc.start()

    def push(self, snapshot: dict) -> None:
        try:
            self._queue.put_nowait(snapshot)
        except multiprocessing.queues.Full:
            pass  # display is behind; drop frame, never block engine
```

`_display_main` runs the pygame event loop entirely in the child process. If it crashes,
systemd restarts the display unit independently (or the engine detects `proc.is_alive()`
and respawns).

### Pattern 4: GPX route loading + nearest-point matching

```python
import gpxpy
from haversine import haversine, Unit

def load_route(gpx_path: str) -> list[tuple[float, float]]:
    with open(gpx_path) as f:
        gpx = gpxpy.parse(f)
    return [
        (pt.latitude, pt.longitude)
        for track in gpx.tracks
        for seg in track.segments
        for pt in seg.points
    ]

def nearest_waypoint_index(
    waypoints: list[tuple[float, float]], lat: float, lng: float
) -> int:
    pos = (lat, lng)
    return min(range(len(waypoints)), key=lambda i: haversine(pos, waypoints[i], unit=Unit.METERS))
```

Route progress = `index / len(waypoints)`. Cumulative distance = sum of successive haversine
segments up to `index`. This is O(N) per GPS fix but for rally stage lengths (< 500 waypoints
at 100 m spacing = 50 km stage) it is negligible at 1 Hz.

### Pattern 5: systemd watchdog integration

The existing systemd unit already uses `Type=notify`. Extend `HealthMonitor` to send keepalives:

```python
import sdnotify  # sdnotify PyPI package

notifier = sdnotify.SystemdNotifier()

def _run(self) -> None:
    while not self._stop_event.wait(self._config.watchdog_interval_s):
        if self._all_subsystems_healthy():
            notifier.notify("WATCHDOG=1")
        else:
            notifier.notify("STATUS=degraded: " + self._degraded_summary())
```

`WatchdogSec` in the unit file should be set to `2 * watchdog_interval_s`. If any critical
subsystem hangs, `HealthMonitor` withholds the keepalive and systemd kills + restarts the engine
after the timeout. This is the correct pattern — do not send keepalives unconditionally.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking the high-rate path with display work

**What:** Calling any display rendering, file I/O, or network operation from the 100 Hz IMU
sampler thread.
**Why bad:** A 10 ms display frame blocks 1 full IMU sample period. Jitter accumulates.
**Instead:** IMU sampler writes only to the ring buffer. Display reads from snapshot dicts at 10 Hz.

### Anti-Pattern 2: Unconditional watchdog keepalives

**What:** Sending `WATCHDOG=1` on a fixed timer regardless of subsystem health.
**Why bad:** Defeats the entire purpose of the watchdog. A hung GPS thread goes undetected.
**Instead:** `HealthMonitor` gates keepalives on verified per-thread liveness (heartbeat timestamps
updated by each thread; `HealthMonitor` checks age against threshold).

### Anti-Pattern 3: Display as a thread inside UnifiedEngine

**What:** Running pygame in a daemon thread sharing the engine process.
**Why bad:** pygame/SDL requires exclusive framebuffer ownership. GIL contention during rendering
can introduce latency spikes in the low-rate collector threads. A display crash brings down the
entire engine.
**Instead:** Separate OS process. Engine survives display crashes. Isolation is worth the IPC cost.

### Anti-Pattern 4: Storage pruning inside the hot write path

**What:** Checking disk space and deleting old files every time a new event or telemetry row
is written.
**Why bad:** File deletion can stall. SQLite DELETE with scan is slow. These block the SQLite
write lock.
**Instead:** `StorageManager` runs on a long interval (15 minutes) in its own daemon thread.

### Anti-Pattern 5: Reading thermal state inside the IMU sampler

**What:** Checking `/sys/class/thermal/...` from the high-rate path to throttle sampling.
**Why bad:** sysfs reads can block briefly. At 100 Hz, every block matters.
**Instead:** `ThermalMonitor` writes to a shared `thermal_state` dict. Sampler reads the dict
(lock-free via a single atomic reference read — acceptable for a float).

### Anti-Pattern 6: Overlayfs for data directories

**What:** Mounting the entire SD card read-only with overlayfs + tmpfs overlay to prevent
corruption.
**Why bad:** SQLite WAL data and video captures must persist across reboots. tmpfs loses everything
on power cycle. Overlayfs is appropriate only for the root OS partition, not the data mount.
**Instead:** Mount `/` read-only (optional hardening), keep `/var/lib/shitbox/` and `/captures/`
on a separate ext4 partition with `noatime,commit=60` mount options. WAL mode already protects
SQLite against unclean shutdowns.

## Scalability Considerations

| Concern | Current | After Milestone | Risk |
|---|---|---|---|
| SQLite write contention | 1 Hz telemetry + sporadic events | + storage pruning thread | Low — prune uses separate connection, long interval |
| CPU load | ~15% at 100 Hz IMU | + display render process | Medium — display is separate process, no GIL impact |
| Memory | Single engine process | + display process (~20 MB pygame) | Low on Pi 4/5 (4 GB RAM) |
| SD card writes | 1 Hz telemetry, event blobs, video | + no new write paths | Neutral — StorageManager reduces net writes |
| Thermal throttle | Passive management | Active monitoring + logging | Positive — early warning prevents data loss |

## Suggested Build Order

Dependencies between new components determine the order:

1. **Boot recovery** — Must be first. Protects data integrity from the very first run after changes
   are deployed. No dependencies on other new components. Validates the baseline before adding
   complexity.

2. **Health monitor + watchdog** — Second. Provides observability for everything built after it.
   Other new threads register their heartbeat with `HealthMonitor` as they are added. Can emit
   Prometheus metrics immediately via the existing `BatchSync` path.

3. **Thermal monitor + storage manager** — Third (can be parallel). Both are standalone daemon
   threads with no dependencies on display or stage tracking. Thermal state feeds `HealthMonitor`.
   Storage manager is self-contained.

4. **Stage tracker** — Fourth. Depends on GPS collector being stable (it already is). Requires a
   GPX route file to exist on disk (operational dependency, not code dependency). Feeds display.

5. **Driver display** — Last. Consumes all other state dicts. Can be built incrementally: first
   panel shows only GPS data, subsequent panels add stage and health as those components land.

## Sources

- [BCM2835 hardware watchdog driver](https://github.com/torvalds/linux/blob/master/drivers/watchdog/bcm2835_wdt.c) — HIGH confidence (kernel source)
- [systemd-watchdog PyPI (AaronDMarasco, Aug 2025)](https://github.com/AaronDMarasco/systemd-watchdog) — HIGH confidence (official release)
- [sd_notify freedesktop reference](https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html) — HIGH confidence (official docs)
- [haversine PyPI](https://pypi.org/project/haversine/) — HIGH confidence (official package)
- [gpxpy — GPX parsing Python](https://pypi.org/project/gpxpy/) — MEDIUM confidence (PyPI, widely used)
- [pygame framebuffer / SDL_VIDEODRIVER pattern (Adafruit)](https://learn.adafruit.com/pi-video-output-using-pygame/pointing-pygame-to-the-framebuffer) — MEDIUM confidence (official Adafruit guide)
- [Raspberry Pi thermal sysfs](https://dev.to/pfs/monitoring-and-controlling-cpu-temperature-on-raspberry-pi-5-using-buildroot-31gp) — MEDIUM confidence (multiple forum corroboration)
- [SQLite WAL checkpoint](https://sqlite.org/wal.html) — HIGH confidence (official SQLite docs)
- [ext4 noatime + commit interval for SD longevity](https://www.dzombak.com/blog/2021/11/Reducing-SD-Card-Wear-on-a-Raspberry-Pi-or-Armbian-Device.html) — MEDIUM confidence (verified against multiple Pi forum threads)
- [multiprocessing.Queue Python stdlib](https://docs.python.org/3/library/multiprocessing.html) — HIGH confidence (official docs)
- [overlayfs read-only root on Raspberry Pi](https://forums.raspberrypi.com/viewtopic.php?t=173063) — MEDIUM confidence (community verified, multiple threads)
