# Phase 21: Hardware Inventory and Graceful Degradation - Research

**Researched:** 2026-04-21
**Domain:** Hardware presence tracking, graceful degradation, supervisor services
**Confidence:** HIGH (the codebase already implements most of the primitives this phase composes)

## Summary

This phase is a **composition exercise**, not a greenfield design. Every primitive the phase needs already exists in the codebase: module-level shared state (`gps_state`), daemon-thread services with `start()`/`stop()` lifecycle (`BatchSyncService`, `OLEDDisplayService`), ffmpeg stall detection (`VideoRingBuffer._check_stall`), escalating I2C recovery (`HighRateSampler._i2c_bus_reset`), per-role config dataclasses (`DS18B20ProbeConfig`), YAML-to-dataclass loading (`_dict_to_dataclass`), Piper TTS with the "Michael" voice persona, and a 4-line OLED renderer that already inverts lines based on health flags. The phase glues these together behind a single `HardwareState` object and one new `HardwareSupervisor` daemon thread.

The hard bits are **not** the primitives — they are:

1. **Observational coupling to the LSM6DSOX reset ladder.** The sampler already owns critical-path I2C recovery. `HardwareState` must observe that ladder (PRESENT → DEGRADED while resetting → MISSING on give-up) without duplicating its logic. The cleanest hook is to pass a `HardwareState` reference into `HighRateSampler` and call `state.report(role, ...)` at the three existing log points (`i2c_bus_lockup_detected`, `i2c_bus_recovery_successful`, `i2c_max_resets_exceeded`).
2. **BME680 cold-boot retry.** The existing 5x1s retry loop in `EnvironmentCollector.setup()` is too short for the observed boot-timing issue (STATE.md 2026-04-10). The supervisor's exponential-backoff re-adoption is the right retry home; the collector's internal loop should be reduced to a single attempt and failure routed through `HardwareState`.
3. **Per-device backoff scheduling.** 11 devices, each with their own retry clock, should not be 11 sleep threads. A single supervisor tick loop (1 Hz) that walks the state table and compares `next_retry_at` against `time.monotonic()` is the minimum-churn pattern and matches how `ThermalMonitorService` and `BatchSyncService` already tick.

**Primary recommendation:** Build one `HardwareState` module (mirrors `gps_state`), one `HardwareSupervisor` daemon (mirrors `OLEDDisplayService`), and thread the state reference into the three existing reporters that don't already own their recovery path: `BaseCollector` (setup/read hooks for 1Hz collectors), `HighRateSampler` (observational), `VideoRingBuffer` (stall + device-missing hooks). Do not rewrite any existing recovery logic. Add a `hardware:` block to config, populated with the 11 devices from STATE.md 2026-04-10.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hardware manifest declaration | Config (YAML → dataclass) | — | Follows existing `sensors:` / `display:` pattern; the manifest IS configuration |
| Boot-time probe | `HardwareSupervisor` (engine service) | — | One place that knows how to probe each bus type; runs once at start(), then transitions to tick-loop mode |
| Runtime presence reporting | Existing collectors + sampler + ring buffer | — | Already own their OSError/stall paths; just need a hook, not a rewrite |
| Central state | `HardwareState` module (new) | — | Module-level singleton mirrors `gps_state`; GIL-atomic rebind for fast reads |
| Alert cadence (TTS, OLED, banner) | `HardwareSupervisor` | — | Single owner of cadence policy; collectors stay stupid |
| Re-adoption retries | `HardwareSupervisor` tick loop | — | One place to reason about backoff; avoids per-collector timer churn |
| OLED hardware line rendering | `OLEDDisplayService` (existing) | `HardwareState` (read) | `_render()` already reads `engine.get_status()`; extend to read HW state |
| Dashboard SSE hardware panel | `sse_mod` (existing SSE router) | `HardwareState` (read) | Add a new `/sse/slow`-piggyback field or new stream slot |
| TTS invocation for hardware events | `capture.speaker` (existing) | — | Add new `speak_hardware_*()` functions matching existing pattern |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dataclasses (stdlib) | py3.9 | HardwareManifest / HardwareDeviceConfig | Entire config system already uses `@dataclass` — no new dep |
| threading (stdlib) | py3.9 | HardwareSupervisor daemon thread | Every service already uses daemon threads — no new dep |
| structlog | 24.x | Keyword-arg logging of state transitions | Already the project-wide logger; keyword args match conventions |
| pyyaml | 6.x | YAML → dataclass loading | Already in use for all config; `safe_load` only |

All verified `[VERIFIED: pyproject.toml lines 10-33]`.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| smbus2 | 0.4.x | I2C boot probe (`read_byte_data` on each declared address) | For the i2c-gpio bit-bang bus probe — already in deps |
| pathlib (stdlib) | py3.9 | 1-Wire, video device, /proc/asound probes | `/sys/bus/w1/devices/`, `/dev/video*`, `/proc/asound/cards` all already checked this way |
| time.monotonic (stdlib) | py3.9 | Backoff scheduling (retry deadlines) | Already used in sampler's retry loop and thermal monitor |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Module-level HardwareState singleton | Instance on UnifiedEngine, passed to collectors | Instance approach is more testable but adds a constructor arg to every collector already shipping — high churn. `gps_state` proved the singleton pattern works fine for this domain |
| Single supervisor tick loop | Per-device threading.Timer | Per-device timers mean 11 threads; tick loop at 1 Hz is ~20 iterations a second of comparison work, negligible |
| asyncio for the supervisor | threading | The whole codebase is threading-based (`OLEDDisplayService`, `BatchSyncService`, all collectors). asyncio would introduce bridging overhead for no benefit |
| Probing via `i2cdetect -y 1` subprocess | `smbus2.SMBus(1).read_byte_data(addr, 0)` in-process | Subprocess call adds 50ms+ latency per device; in-process read_byte_data is what the existing drivers already do at init |

**Installation:** no new packages required.

**Version verification:** Versions from pyproject.toml `[VERIFIED: pyproject.toml]`. No new dependencies — phase composes existing primitives only.

## Architecture Patterns

### System Architecture Diagram

```
                       config.yaml
                            │
                            │  hardware: block
                            ▼
               _dict_to_dataclass() ← load_config()
                            │
                            │  HardwareManifestConfig (11 devices)
                            ▼
                  ┌──────────────────┐
    engine.start()│ HardwareSupervisor│  (new daemon thread)
    ──────────── ►│                  │
                  │  ._probe_all()   │  ── I2C read_byte_data on each addr
                  │  ._tick_loop()   │  ── 1 Hz: check backoff deadlines
                  └────────┬─────────┘     fire TTS / SSE / OLED updates
                           │
                           │  reports + reads
                           ▼
              ┌──────────────────────────┐
              │  HardwareState (module)  │  ← GIL-atomic dict rebind
              │   role -> DeviceStatus   │     (mirrors gps_state)
              └────────┬──────────┬──────┘
                       ▲          │
       reports         │          │ reads
 ┌─────────────────────┘          ▼
 │                          ┌─────────────┬──────────────┬───────────┐
 │                          │ OLEDDisplay │ SSE /sse/slow│ speaker.* │
 │                          │  _render()  │  (snapshot)  │  TTS lines│
 │                          └─────────────┴──────────────┴───────────┘
 │
 │ (hooks into existing reporters)
 │
 ├── BaseCollector.setup/read (1Hz: BME680, DS18B20, VEML7700, INA226, LIS3MDL)
 ├── HighRateSampler (LSM6DSOX — observational, reset ladder owns recovery)
 └── VideoRingBuffer._health_monitor (front camera + cabin camera stall/missing)
```

Data flow:
- **Boot:** config → supervisor._probe_all() → HardwareState populated with PRESENT/MISSING for each declared device
- **Runtime (collectors):** setup failure / OSError → collector calls `hardware_state.report_missing(role)` → supervisor tick sees MISSING, emits TTS + marks `next_retry_at`
- **Runtime (supervisor tick):** every 1s, walk state table: any MISSING device past `next_retry_at` → call collector's re-adoption callback → success flips state back → supervisor emits "recovered" TTS
- **Readers (OLED, SSE, dashboard):** read `HardwareState.snapshot()` at their own cadence; it's a dict copy, no locks

Component responsibilities:
| File | Responsibility |
|------|----------------|
| `src/shitbox/hardware/state.py` (new) | `HardwareState` module: report_present / report_missing / report_degraded / snapshot |
| `src/shitbox/hardware/supervisor.py` (new) | `HardwareSupervisor` service: _probe_all, _tick_loop, alert cadence |
| `src/shitbox/hardware/manifest.py` (new, optional) | `HardwareManifestConfig` + `HardwareDeviceConfig` dataclasses (or inline in config.py — see "YAML shape" below) |
| `src/shitbox/utils/config.py` (edit) | Add HardwareManifestConfig, wire into load_config() |
| `src/shitbox/collectors/base.py` (edit) | Add optional `role` attr + hook into setup/read error paths that calls HardwareState |
| `src/shitbox/collectors/environment.py` (edit) | Reduce internal retry to 1 attempt; let supervisor handle retry |
| `src/shitbox/events/sampler.py` (edit) | Add `hardware_state` ref; report from 3 existing log points (no logic change) |
| `src/shitbox/capture/ring_buffer.py` (edit) | Add `hardware_state` ref; report from 2 existing log points (stall, device_missing) |
| `src/shitbox/display/oled.py` (edit) | Add line 5-budget hardware summary (currently 4 lines — choose what to drop or roll up) |
| `src/shitbox/dashboard/sse.py` (edit) | Add `hardware` field to /sse/slow payload or add a dedicated slot |
| `src/shitbox/capture/speaker.py` (edit) | Add `speak_hardware_missing / _degraded / _restored` for each tier |
| `src/shitbox/events/engine.py` (edit) | Instantiate supervisor; start()/stop() wiring; pass state refs into reporters |

### Recommended Project Structure

```
src/shitbox/
├── hardware/                       # NEW — HW inventory + supervisor
│   ├── __init__.py
│   ├── state.py                    # HardwareState module (like gps_state)
│   ├── supervisor.py               # HardwareSupervisor daemon thread
│   └── probes.py                   # per-bus probe functions (i2c, 1wire, usb, gpio, hdmi, audio)
├── utils/config.py                 # EDIT — add HardwareManifestConfig
├── collectors/base.py              # EDIT — add role hook
├── collectors/environment.py       # EDIT — reduce internal retry
├── events/sampler.py               # EDIT — observational hooks at 3 points
├── capture/ring_buffer.py          # EDIT — observational hooks at 2 points
├── display/oled.py                 # EDIT — hardware summary line(s)
├── dashboard/sse.py                # EDIT — hardware field
├── dashboard/static/index.html     # EDIT — hardware panel (read-only)
├── capture/speaker.py              # EDIT — 3 new speak_hardware_* functions
└── events/engine.py                # EDIT — wiring, start/stop
```

### Pattern 1: Module-level Singleton State (mirror of gps_state)

**What:** A small module holding a single `_state` dict keyed by device role. Readers call `snapshot()` which returns a reference (or copy) to the dict. Writers call `report_*()` which rebinds via GIL-atomic assignment.

**When to use:** This phase (HardwareState); the pattern already works in production for `gps_state` with the same read-heavy / write-occasional access shape.

**Example:**
```python
# Source: mirrors src/shitbox/dashboard/gps_state.py (shipped pattern)
"""Central hardware presence state. Module-level, GIL-atomic rebind."""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class DeviceState(str, Enum):
    PRESENT = "present"
    DEGRADED = "degraded"
    MISSING = "missing"


@dataclass(slots=True, frozen=True)
class DeviceStatus:
    role: str
    tier: str           # "critical" | "important" | "best_effort"
    state: DeviceState
    last_seen: float    # time.time() of last successful read; 0.0 if never
    since_monotonic: float  # time.monotonic() when current state began
    next_retry_at: float    # time.monotonic() when supervisor should retry; 0.0 if not scheduled
    consecutive_misses: int # for backoff laddering


# Single source of truth. Rebinding is GIL-atomic.
_state: Dict[str, DeviceStatus] = {}


def initialise(devices: Dict[str, str]) -> None:
    """Seed the state table. devices: {role: tier}. Called once at boot
    from HardwareSupervisor before any probes run."""
    global _state
    now = time.monotonic()
    _state = {
        role: DeviceStatus(
            role=role, tier=tier, state=DeviceState.MISSING,
            last_seen=0.0, since_monotonic=now,
            next_retry_at=0.0, consecutive_misses=0,
        )
        for role, tier in devices.items()
    }


def report_present(role: str) -> Optional[DeviceState]:
    """Mark device PRESENT. Returns previous state for transition detection."""
    global _state
    prev = _state.get(role)
    if prev is None:
        return None
    new_map = dict(_state)  # copy
    new_map[role] = DeviceStatus(
        role=role, tier=prev.tier, state=DeviceState.PRESENT,
        last_seen=time.time(),
        since_monotonic=time.monotonic() if prev.state != DeviceState.PRESENT else prev.since_monotonic,
        next_retry_at=0.0, consecutive_misses=0,
    )
    _state = new_map
    return prev.state


def report_missing(role: str) -> Optional[DeviceState]:
    """Mark device MISSING and schedule next retry via backoff ladder."""
    global _state
    prev = _state.get(role)
    if prev is None:
        return None
    # Backoff: 5s, 15s, 60s, then 300s cap
    schedule = [5.0, 15.0, 60.0, 300.0]
    consecutive = min(prev.consecutive_misses + 1, len(schedule))
    wait = schedule[consecutive - 1]
    new_map = dict(_state)
    new_map[role] = DeviceStatus(
        role=role, tier=prev.tier, state=DeviceState.MISSING,
        last_seen=prev.last_seen,
        since_monotonic=time.monotonic() if prev.state != DeviceState.MISSING else prev.since_monotonic,
        next_retry_at=time.monotonic() + wait,
        consecutive_misses=consecutive,
    )
    _state = new_map
    return prev.state


def snapshot() -> Dict[str, DeviceStatus]:
    """Return current state. Do not mutate — reader copies if needed."""
    return _state
```

### Pattern 2: Supervisor Tick Loop (mirror of BatchSyncService)

**What:** Daemon thread that sleeps `interval_seconds`, then wakes and walks state, comparing `next_retry_at` to `time.monotonic()`.

**When to use:** Phase 21 — avoids 11 per-device timers, single place for backoff policy.

**Example:**
```python
# Source: mirrors src/shitbox/sync/batch_sync.py (shipped pattern) and
#         src/shitbox/display/oled.py (shipped pattern)
import threading, time
from typing import Dict, Callable

from shitbox.hardware import state as hw_state

class HardwareSupervisor:
    """Daemon thread: probes at boot, then ticks every second to drive
    re-adoption + alert cadence."""

    TICK_INTERVAL_SECONDS = 1.0
    # Critical-tier TTS re-nag — speak every N seconds until device returns
    CRITICAL_RENAG_SECONDS = 30.0

    def __init__(
        self,
        manifest,                                   # HardwareManifestConfig
        reprobe_callbacks: Dict[str, Callable[[], bool]],
    ) -> None:
        self.manifest = manifest
        self.reprobe = reprobe_callbacks
        self._running = False
        self._thread = None
        self._last_nag: Dict[str, float] = {}

    def start(self) -> None:
        hw_state.initialise({d.role: d.criticality for d in self.manifest.devices})
        self._probe_all()  # seeds PRESENT/MISSING from real hardware
        self._running = True
        self._thread = threading.Thread(
            target=self._tick_loop, daemon=True, name="hw-supervisor",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _tick_loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as e:
                log.error("hw_supervisor_tick_error", error=str(e))
            time.sleep(self.TICK_INTERVAL_SECONDS)

    def _tick(self) -> None:
        now = time.monotonic()
        for role, st in hw_state.snapshot().items():
            if st.state == hw_state.DeviceState.MISSING:
                # Retry if deadline passed
                if st.next_retry_at and now >= st.next_retry_at:
                    cb = self.reprobe.get(role)
                    if cb is not None:
                        try:
                            if cb():
                                prev = hw_state.report_present(role)
                                if prev != hw_state.DeviceState.PRESENT:
                                    self._on_restored(st)
                                continue
                        except Exception as e:
                            log.warning("hw_reprobe_error", role=role, error=str(e))
                    # Re-schedule (will bump consecutive_misses)
                    hw_state.report_missing(role)
                # Re-nag critical tier every 30s while missing
                if st.tier == "critical" and now - self._last_nag.get(role, 0) >= self.CRITICAL_RENAG_SECONDS:
                    self._speak_missing(st)
                    self._last_nag[role] = now

    def _on_restored(self, st) -> None:
        speaker.speak_hardware_restored(st.role, st.tier)
        log.info("hw_restored", role=st.role, tier=st.tier)
```

### Anti-Patterns to Avoid

- **Rewriting existing recovery logic.** The LSM6DSOX 9-clock ladder in `sampler.py` works. The BME680 has its own 5x1s retry that's *too short* but correctly structured. Do not replace these with a unified recovery mechanism — add observational reporting, let the existing ladders run first, and surface state transitions only.
- **Per-collector retry timers.** Eleven threads to re-adopt eleven devices is absurd. One supervisor tick at 1 Hz handles all of them.
- **Probing via `i2cdetect` subprocess.** 50ms+ per probe, requires privilege or group membership, subprocess management overhead. `smbus2.SMBus(1).read_byte_data(addr, 0)` in-process is what the existing drivers do at init.
- **Treating setup() failure as fatal.** `BaseCollector.start()` currently raises on setup failure. For HW-05 (daemon never refuses to boot) the engine's start() logic must catch collector setup failures, report MISSING, and carry on — do NOT make setup() itself swallow the error; the engine handles the catch.
- **Blocking TTS on alerts.** Piper synthesis is async-queued (`speaker._queue`). All speak_*() calls return immediately. The supervisor tick must never block on speech.
- **Emitting TTS on every tick.** Critical re-nag at 30s; important speaks once; best_effort only logs. This is already encoded in D-05 — the supervisor's `_last_nag` dict prevents tick-rate spam.
- **Modifying BaseCollector._max_errors behaviour.** The 10-consecutive-errors stop is a safety valve. Keep it. The HW hook reports MISSING on the first OSError, not the tenth.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| I2C bus probe | Custom i2cdetect wrapper | `smbus2.SMBus(bus).read_byte_data(addr, 0)` | Existing INA226 / BME680 init code uses this pattern; zero-byte read returns data or OSError |
| 1-Wire presence | Parsing `w1_master_slaves` | Check `/sys/bus/w1/devices/28-<id>/w1_slave` exists | `w1thermsensor` library already does this; we just stat the file |
| USB camera presence | UDev subscription | Check `/dev/camera-front` / `/dev/camera-cabin` symlink exists | Symlinks are set up by udev rules; a missing device means the symlink is broken. `VideoRingBuffer` already does `os.path.exists(self.device)` |
| USB audio presence | libasound binding | Parse `/proc/asound/cards` | `speaker._detect_usb_speaker()` already parses this file; reuse that function |
| HDMI display presence | DRM/KMS subscription | Check `/sys/class/drm/card*-HDMI-*/status` reads "connected" | Kernel exposes this as a text file; simpler than D-Bus display manager |
| GPIO button presence | GPIO library probe | Check that `RPi.GPIO` or `lgpio` imports succeed | `button.py` already does this via `GPIO_AVAILABLE` flag |
| Queued alert delivery | New queue | `speaker._queue` + new `speak_hardware_*` functions | Piper pre-cache pattern already in place; fixed-message WAVs render once |
| SSE fanout for hardware panel | New SSE stream | Add field to `/sse/slow` payload | The dashboard already consumes slow stream; one new field vs. a new endpoint + new client connection |
| Exponential backoff math | Custom scheduler | Lookup table `[5.0, 15.0, 60.0, 300.0]` indexed by consecutive_misses | 4-step ladder with a cap; no need for `2 ** n` logic |

**Key insight:** Every primitive for this phase is shipped. The phase's value is in **composing** them behind one observable state object and one supervisor. If research finds itself reaching for new libraries, something is wrong.

## Runtime State Inventory

Not applicable — this is an additive feature phase, not a rename/refactor. No existing runtime state is renamed, and the existing devices keep the same roles and addresses.

Stored data: none renamed. Live service config: new `hardware:` YAML block is additive. OS-registered state: none touched. Secrets/env vars: none. Build artifacts: none invalidated.

## Common Pitfalls

### Pitfall 1: Probing the wrong I2C bus

**What goes wrong:** STATE.md 2026-04-10 records that the Pi 5 switched from `i2c_designware` (hardware I2C with buggy clock-stretch) to `i2c-gpio` (bit-bang). Both appear as bus 1 to userspace, but a boot probe that assumes `i2c_designware` will fail to find any of the 6 I2C devices even though they're physically present and `i2cdetect -y 1` lists them.

**Why it happens:** The bus number in `smbus2.SMBus(1)` is the *kernel's* bus 1, which is now the bit-bang bus thanks to `dtoverlay=i2c-gpio,bus=1,...` in config.txt. If the overlay is removed or a different bus number is specified, the probe silently probes nothing.

**How to avoid:** The probe function must:
1. Confirm the i2c-gpio overlay is active (check `/sys/class/i2c-adapter/i2c-1/name` starts with `i2c-gpio`)
2. If it doesn't, emit a loud error — this is the same failure mode that took 3 days to diagnose in April
3. Only then attempt device reads

**Warning signs:** Every I2C device reports MISSING simultaneously at boot, but `i2cdetect -y 1` works fine from the shell.

### Pitfall 2: Reporting PRESENT from a stale read

**What goes wrong:** The sampler's recovery ladder calls `self._i2c_bus_reset()` and returns `True` on successful sensor reinit. If we hook this into `hw_state.report_present("lsm6dsox")`, we mark it PRESENT before the *first successful sample* is read. If the sensor is intermittent, we'll flap PRESENT/MISSING every 5 seconds and drive Michael mad.

**Why it happens:** Presence is a property of successful reads, not successful setup. The sensor can init cleanly and then fail on the first read.

**How to avoid:** Only report PRESENT after a successful `_read_sample()`. The existing `self._consecutive_failures = 0` reset inside the read-success branch is the natural hook point. Setup success reports nothing; first read success reports PRESENT.

**Warning signs:** Rapid state flipping visible in dashboard history; "LSM6DSOX restored / LSM6DSOX offline" TTS every few seconds.

### Pitfall 3: BaseCollector.start() raising on setup failure

**What goes wrong:** `BaseCollector.start()` catches setup failure, logs, and **re-raises**. If the engine's start() calls `collector.start()` in a loop without a try/except per collector, one sensor's missing hardware kills the whole daemon → systemd crash loop → HW-05 violation.

**Why it happens:** The current engine loop at lines 1917-1928 does wrap collector.start() in try/except per collector (good), but any new collector added that doesn't follow that pattern will fail HW-05.

**How to avoid:** Refactor the try/except into a helper method `_start_collector_graceful(collector)` that ALWAYS catches, reports MISSING, and never re-raises. Use it for every collector start. Alternatively, have `BaseCollector.start()` itself swallow setup errors once `hardware_state` is wired — but that changes existing semantics.

**Warning signs:** systemd `Restart=on-failure` triggering after any sensor removal.

### Pitfall 4: OLED running out of lines

**What goes wrong:** The current OLED renderer uses all 4 lines for GPS / Gs+REC / IMU+ENV / NET+BKL+TEMP. Adding a per-critical/per-important device line would require 2-3 extra lines. The SSD1306 is 128x64 with default 8px font = 8 lines max, but the current layout uses 16px row spacing (4 lines readable from a glance while driving).

**Why it happens:** The panel is glanceable-while-driving; cramming 11 devices in small font defeats the purpose.

**How to avoid:** Use the existing 4-line budget with one repurposed line:
- Line 3 (currently "IMU | ENV") becomes the hardware rollup: `IMU:ok CAM:ok PWR:ok BME:!!` (each device is 3-4 chars + state glyph)
- Drop "ENV" from line 3 — environment presence is now part of the rollup
- Critical missing devices (IMU, front camera) get inverted rendering for that token
- Best-effort devices don't appear on OLED at all (only log + dashboard)

### Pitfall 5: smbus2 probe holding the bus open

**What goes wrong:** `smbus2.SMBus(1)` opens a file handle to `/dev/i2c-1`. If the probe function opens and doesn't close, the existing collectors (which also open the same file) may race or get EBUSY.

**Why it happens:** `i2c-gpio` bit-bang serialises access at the driver level, but multiple open file handles are still legal; what's not legal is two threads trying to read at the same microsecond.

**How to avoid:** Use `with smbus2.SMBus(1) as bus:` in the probe function. Close it before the collectors' setup() runs. The probe is a single-shot at boot, not a long-lived reader.

**Warning signs:** Random OSError on sensor init at boot when everything worked before adding the supervisor.

### Pitfall 6: Duplicating TTS cadence between sampler and supervisor

**What goes wrong:** The sampler already calls `speaker.speak_i2c_lockup()` when consecutive failures hit threshold. If the supervisor *also* speaks on MISSING transition, the driver hears two different messages for the same event.

**Why it happens:** Observational coupling — the sampler owns the recovery, the supervisor owns the cadence policy, but both think they speak.

**How to avoid:** Pick one owner. Recommendation: the sampler keeps its existing `speak_i2c_lockup()` for the during-recovery announcement ("I'm trying to fix the bus"), and the supervisor speaks only on the *terminal* state transition — MISSING (ladder gave up) or RESTORED. The "I2C lockup detected" mid-recovery chatter stays with the sampler; "IMU offline" / "IMU back online" belong to the supervisor.

### Pitfall 7: BME680 internal retry vs supervisor retry

**What goes wrong:** `EnvironmentCollector.setup()` has a 5x1s retry loop. If we also give the supervisor a 5s initial backoff, first failure blocks the daemon for 5 seconds in collector.setup(), then another 5 seconds waiting for supervisor retry. Total: 10s before the caller knows anything.

**Why it happens:** Two retry owners.

**How to avoid:** Reduce `EnvironmentCollector.setup()` internal retries to 1 attempt (delete the for-loop, keep a single `busio.I2C + Adafruit_BME680_I2C` pair). Failure → raise → `BaseCollector.start()` catches → supervisor gets notified → supervisor's 5s backoff owns the retry cadence.

**Warning signs:** 10+ second delays at boot before BME680 either initialises or declares MISSING.

## Code Examples

### Example: HardwareManifest YAML block

```yaml
# Source: proposed — follows existing sensors: / display: block conventions
# in config/config.yaml (shipped). Hybrid manifest per D-01/D-02/D-03.

hardware:
  # Each entry declares expected hardware. Boot probe verifies and records
  # PRESENT/MISSING into HardwareState. Existing sensor blocks (sensors.imu,
  # sensors.environment, etc.) keep their tuning knobs; this block is
  # presence metadata only.
  devices:
    # ── critical ─────────────────────────────────────────────────────────
    - role: imu
      bus: i2c-1
      address: 0x6a
      criticality: critical
      description: "LSM6DSOX accel+gyro"
    - role: camera_front
      bus: usb
      path: /dev/camera-front
      criticality: critical
      description: "UGREEN USB webcam (front dashcam)"

    # ── important ────────────────────────────────────────────────────────
    - role: power
      bus: i2c-1
      address: 0x40
      criticality: important
      description: "INA226 power monitor"
    - role: gps
      bus: usb
      path: /dev/gps0
      criticality: important
      description: "U-blox USB GPS via gpsd"

    # ── best_effort ──────────────────────────────────────────────────────
    - role: environment
      bus: i2c-1
      address: 0x77
      criticality: best_effort
      description: "BME680 temperature/humidity/pressure/gas"
    - role: magnetometer
      bus: i2c-1
      address: 0x1c
      criticality: best_effort
      description: "LIS3MDL"
    - role: light
      bus: i2c-1
      address: 0x10
      criticality: best_effort
      description: "VEML7700 ambient light"
    - role: oled
      bus: i2c-1
      address: 0x3c
      criticality: best_effort
      description: "SSD1306 128x64 status display"
    - role: temp_exterior
      bus: 1-wire
      sensor_id: "28-00000024263a"
      criticality: best_effort
      description: "DS18B20 exterior probe"
    - role: temp_engine_bay
      bus: 1-wire
      sensor_id: "28-0000002405b1"
      criticality: best_effort
      description: "DS18B20 engine bay probe"
    - role: camera_cabin
      bus: usb
      path: /dev/camera-cabin
      criticality: best_effort
      description: "Logitech Brio 100 (cabin)"
    - role: audio_mic
      bus: audio
      label: UACDemo       # matches /proc/asound/cards parsing in speaker.py
      criticality: best_effort
      description: "USB mic for TTS speaker (also playback)"
    - role: button
      bus: gpio
      pin: 17
      criticality: best_effort
      description: "Manual capture button"
    - role: display_hdmi
      bus: hdmi
      connector: HDMI-A-1
      criticality: best_effort
      description: "7in kiosk display"
```

**Why list-of-devices, not map-by-role:** `_dict_to_dataclass` handles flat dataclasses cleanly. A list of `HardwareDeviceConfig` is straightforward. A map `{role: HardwareDeviceConfig}` would need special-case handling (like `DS18B20ProbeConfig` probes list does already, see `utils/config.py` lines 464-470). Lists also read better in git diffs — each addition/deletion is a contiguous 4-6 line block.

### Example: HardwareDeviceConfig dataclass

```python
# Source: proposed — follows src/shitbox/utils/config.py DS18B20ProbeConfig
# pattern (shipped).

@dataclass
class HardwareDeviceConfig:
    """Single expected device in the hardware manifest."""
    role: str = ""
    bus: str = ""          # i2c-1 | 1-wire | usb | gpio | hdmi | audio
    criticality: str = "best_effort"  # critical | important | best_effort
    description: str = ""
    # Bus-specific fields (all optional; validator checks the right ones per bus)
    address: Optional[int] = None     # i2c: 0x6a style
    path: Optional[str] = None        # usb: /dev/camera-front
    sensor_id: Optional[str] = None   # 1-wire: 28-00000024263a
    pin: Optional[int] = None         # gpio: 17
    label: Optional[str] = None       # audio: UACDemo (/proc/asound/cards)
    connector: Optional[str] = None   # hdmi: HDMI-A-1


@dataclass
class HardwareManifestConfig:
    devices: List[HardwareDeviceConfig] = field(default_factory=list)
```

**Loader wiring** (mirrors `temp_config.probes = [DS18B20ProbeConfig(**p) for p in ...]` at line 468-470 of config.py):

```python
hw_dict = data.get("hardware", {})
hw_config = HardwareManifestConfig()
devices_data = hw_dict.get("devices", []) if isinstance(hw_dict, dict) else []
hw_config.devices = [
    HardwareDeviceConfig(**d) for d in (devices_data if isinstance(devices_data, list) else [])
]
```

### Example: I2C probe function

```python
# Source: proposed — mirrors patterns in
#   src/shitbox/collectors/power.py (smbus2 init)
#   src/shitbox/collectors/environment.py (except/log pattern)

import smbus2
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

def probe_i2c(bus: int, address: int) -> bool:
    """Return True if a device responds at (bus, address).

    Reads a single byte from register 0x00. Any successful read — regardless
    of value — confirms a device ACKed. OSError means no ACK → absent.
    """
    try:
        with smbus2.SMBus(bus) as smb:
            smb.read_byte_data(address, 0x00)
        return True
    except OSError:
        return False
    except Exception as e:
        log.warning("i2c_probe_unexpected_error", bus=bus, address=hex(address), error=str(e))
        return False
```

### Example: 1-Wire probe

```python
# Source: proposed — probes the /sys filesystem path that w1thermsensor
# reads internally.
from pathlib import Path

def probe_onewire(sensor_id: str) -> bool:
    """Return True if the DS18B20 slave file is present.
    sensor_id is the bare ID (e.g. '28-00000024263a')."""
    return Path(f"/sys/bus/w1/devices/{sensor_id}/w1_slave").exists()
```

### Example: USB device probe

```python
# Source: proposed — mirrors existing
#   os.path.exists(self.device)
# check in src/shitbox/capture/ring_buffer.py line 881 (shipped).

import os

def probe_usb_path(path: str) -> bool:
    """Return True if the USB device node / symlink exists."""
    return os.path.exists(path)
```

### Example: Audio device probe (reuses existing speaker logic)

```python
# Source: proposed — extract pattern from
# src/shitbox/capture/speaker.py::_detect_usb_speaker (shipped)
from pathlib import Path

def probe_audio_label(label: str) -> bool:
    """Return True if the given label appears in /proc/asound/cards."""
    try:
        return label in Path("/proc/asound/cards").read_text()
    except OSError:
        return False
```

### Example: HDMI connector probe

```python
# Source: proposed — reads the DRM /sys text files the kernel already exposes.
from pathlib import Path

def probe_hdmi(connector: str) -> bool:
    """Return True if the named HDMI connector reports 'connected'.
    connector: e.g. 'HDMI-A-1' (see /sys/class/drm/*-HDMI-*/status)."""
    for path in Path("/sys/class/drm").glob(f"*{connector}"):
        status = path / "status"
        if status.exists() and status.read_text().strip() == "connected":
            return True
    return False
```

### Example: BaseCollector presence hook

```python
# Source: proposed — minimal surface change to src/shitbox/collectors/base.py
# (shipped). Only adds an optional role + reporter; existing collectors
# work unchanged.

class BaseCollector(ABC, Generic[T]):
    def __init__(
        self,
        name: str,
        sample_rate_hz: float,
        callback: Optional[Callable[[Reading], None]] = None,
        role: Optional[str] = None,                  # NEW — maps to manifest role
    ):
        # ... existing body ...
        self.role = role

    def _report_present(self) -> None:
        if self.role:
            from shitbox.hardware import state as hw_state
            hw_state.report_present(self.role)

    def _report_missing(self) -> None:
        if self.role:
            from shitbox.hardware import state as hw_state
            hw_state.report_missing(self.role)

    # In _run_loop, after a successful read:
    #     self._report_present()
    # In _run_loop exception handler, before the max_errors check:
    #     self._report_missing()
    # In start() exception handler:
    #     self._report_missing()
    #     raise          # <- keep existing behaviour; engine catches it
```

### Example: Sampler observational hook (NO logic changes)

```python
# Source: proposed — 4 single-line insertions into src/shitbox/events/sampler.py
# (shipped). Existing reset ladder and reboot semantics untouched.

# In HighRateSampler.__init__, add:
self.role = "imu"  # maps to manifest

# In _sample_loop, after `self._consecutive_failures = 0` (success branch, line 178):
hw_state.report_present(self.role)

# In the existing "i2c_bus_lockup_detected" log call (line 188):
hw_state.report_degraded(self.role)

# In the existing "i2c_max_resets_exceeded" log call (line 213):
hw_state.report_missing(self.role)
# (still followed by _force_reboot() — HW-05 is about graceful NO-hardware
# boot, not "keep running forever with dead IMU". A dead IMU after 3 resets
# IS the crash path. But the supervisor gets to emit the final "IMU offline"
# TTS before reboot.)
```

### Example: VideoRingBuffer observational hook

```python
# Source: proposed — 2 insertions into src/shitbox/capture/ring_buffer.py
# (shipped). Existing stall/restart logic untouched.

# Store role in __init__ (set from config / device path):
self.role = "camera_front"  # or "camera_cabin"

# In _health_monitor, line 882 (the existing "video_device_missing" log):
hw_state.report_missing(self.role)

# In _health_monitor, line 899 (the existing "video_ring_buffer_ffmpeg_stalled" log):
hw_state.report_degraded(self.role)

# In _start_ffmpeg, after the process is confirmed running (line ~770):
hw_state.report_present(self.role)
```

### Example: New TTS lines (speaker.py additions)

```python
# Source: proposed — additions to src/shitbox/capture/speaker.py (shipped).
# Pre-cache new fixed messages; the _CACHED_MESSAGES dict is the only
# mechanism that matters, everything else is driven by it.

_CACHED_MESSAGES.update({
    # Critical-tier — the nag loop repeats these every 30s
    "hw_imu_missing":          "Michael, I have no IMU. Event detection is down.",
    "hw_imu_restored":         "IMU back with me, Michael.",
    "hw_camera_front_missing": "Michael, the front camera is off. I can't record.",
    "hw_camera_front_restored":"Front camera restored, Michael.",

    # Important-tier — spoken once per transition
    "hw_power_missing":        "Michael, I can't see the power monitor.",
    "hw_power_restored":       "Power monitor back, Michael.",
    "hw_gps_missing":          "Michael, I've lost GPS.",
    "hw_gps_restored":         "GPS fix restored, Michael.",

    # Best-effort — only spoken for the canonical acceptance case
    "hw_env_missing":          "Environment sensor is not responding, Michael.",
    "hw_env_restored":         "Environment sensor restored, Michael.",
})

def speak_hardware_missing(role: str, tier: str) -> None:
    """Announce a device going MISSING. Tier governs whether we speak at all
    at this transition — best_effort is log-only by default (D-05)."""
    if not _should_alert():
        return
    if tier == "best_effort" and role != "environment":
        return    # log only
    _enqueue(_CACHED_MESSAGES.get(f"hw_{role}_missing", f"{role} offline, Michael."))

def speak_hardware_restored(role: str, tier: str) -> None:
    if not _should_alert():
        return
    if tier == "best_effort" and role != "environment":
        return
    _enqueue(_CACHED_MESSAGES.get(f"hw_{role}_restored", f"{role} restored, Michael."))
```

Wording follows the shipped "Michael" register (short sentences, first-person computer voice, no alarming superlatives — see speaker.py `_CACHED_MESSAGES` dict for the established register).

### Example: OLED hardware rollup line

```python
# Source: proposed — edit to _render() in src/shitbox/display/oled.py (shipped)
# Keeps the 4-line budget. Line 3 ("IMU | ENV") becomes a rollup.

from shitbox.hardware import state as hw_state

# In _render(), replace lines 146-149:
# Line 3: Hardware rollup — critical tokens only, inverted when missing
snap = hw_state.snapshot()
x = 0
for role, glyph in [("imu", "IMU"), ("camera_front", "CAM"), ("power", "PWR")]:
    st = snap.get(role)
    missing = st is None or st.state != hw_state.DeviceState.PRESENT
    self._draw_text(x, 32, glyph, inverted=missing)
    x += len(glyph) * 8 + 8

# Roll-up for the rest: "env:2/3" meaning 2 of 3 best-effort env devices present
be_roles = ("environment", "magnetometer", "light")
be_present = sum(
    1 for r in be_roles if snap.get(r) and snap[r].state == hw_state.DeviceState.PRESENT
)
self._draw_text(96, 32, f"ENV:{be_present}/{len(be_roles)}")
```

### Example: SSE hardware payload

```python
# Source: proposed — add field to /sse/slow yield in
# src/shitbox/dashboard/sse.py (shipped) around lines 132-150.

yield {
    "event": "slow",
    "data": json.dumps({
        # ... existing 16 fields ...
        "hardware": [
            {
                "role": st.role,
                "tier": st.tier,
                "state": st.state.value,
                "last_seen": st.last_seen,
                "since_ms": int((time.time() - st.last_seen) * 1000)
                    if st.last_seen else None,
            }
            for st in hw_state.snapshot().values()
        ],
    }, default=str),
}
```

No new SSE stream; piggy-backs on slow for one-second cadence which is the right refresh rate for a hardware panel (HW-02 acceptance is "visible within one status refresh").

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `i2c_designware` (RP1 hardware I2C) | `i2c-gpio` bit-bang on bus 1 | 2026-04-10 (STATE.md OOB) | All probe code must target bus 1 but understand it's bit-bang; clock-stretch timing is different |
| MPU6050 (old v1 hardware) | LSM6DSOX + LIS3MDL (v2 hat) | Phase 11 | Critical device role is now "imu" covering LSM6DSOX at 0x6a |
| gpsd-py3 `get_current()` polling | Persistent gpsd JSON-stream client | Phase 10 | GPS presence is a function of the stream client, not a subprocess |
| Adafruit BME680 with in-collector 5x1s retry | Needs to move to supervisor-driven retry | This phase | Eliminates the 5s boot block when BME680 fails cold-boot init |
| RPi.GPIO on Pi 5 | rpi-lgpio shim (dependency in pyproject.toml) | Phase 11 | GPIO probes should work via rpi-lgpio wrapper; actual hardware support unverified for the recovery ladder (STATE.md note about "recovery calls likely silently fail") |

**Deprecated/outdated:**
- `environment_enabled` in `EngineConfig` (from the BME280 days) — now covered by `sensors.environment` and soon by `hardware.devices[role=environment]`. Kept for backwards compat but the new code path should not extend it.
- `MPU6050Config` — fully removed from `utils/config.py` at Phase 11; do not introduce new references.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | HDMI connector name on Pi 5 is `HDMI-A-1` | Code Examples (HDMI probe) | HDMI device probes MISSING at boot — low impact, best_effort tier, log only. Planner should verify with `ls /sys/class/drm/` on laser |
| A2 | The i2c-gpio bus adapter name starts with `i2c-gpio` in `/sys/class/i2c-adapter/i2c-1/name` | Pitfall 1 | Probe function false-alarms if kernel exposes a different name. Easy to verify: `cat /sys/class/i2c-adapter/i2c-1/name` on laser |
| A3 | `smbus2.SMBus(1).read_byte_data(addr, 0x00)` is safe on every declared I2C device | Code Examples (I2C probe) | A device that doesn't tolerate a read of register 0x00 at probe time could glitch. All 6 declared devices (VEML7700, LIS3MDL, OLED, INA226, LSM6DSOX, BME680) accept byte reads; this is standard I2C idiom. Could fall back to `write_quick(addr)` if needed |
| A4 | `/dev/gps0` is a stable symlink for the USB GPS | Code Examples (manifest) | If gpsd reads raw `/dev/ttyUSB0` instead and no symlink exists, probe needs different logic. Planner should verify the actual device path in `config/config.yaml` gps section or via `ls -la /dev/` on laser |
| A5 | USB mic label `UACDemo` is stable across reboots | Code Examples (audio probe) | Known-good: `speaker._detect_usb_speaker()` already greps for this substring and it works in production |
| A6 | rpi-lgpio correctly shims RPi.GPIO for button presence check on Pi 5 | Manifest (button role) | STATE.md 2026-04-10 flags rpi-lgpio as unverified for the sampler's recovery ladder. Button presence check only imports RPi.GPIO and checks the module exists — even if recovery is broken, the import succeeds, so presence probe is robust. Low risk |
| A7 | Critical-tier TTS re-nag interval of 30s is the right default | Pattern 2 (supervisor) | Driver feedback will tune this. Starting at 30s matches "not annoying but not forgettable". Configurable via config.yaml |
| A8 | 5s→15s→60s→300s backoff ladder is appropriate for all tiers | HardwareState Pattern 1 | Same ladder for all devices may be too aggressive for critical (5s is fine) and too tight for best_effort (should maybe be 30s→300s cap). Planner may want per-tier ladders |
| A9 | The BME680 cold-boot issue is fixed by ANY retry at >5s after boot | Summary + Pitfall 7 | STATE.md 2026-04-10 says "timing issue, needs retry on setup or delayed init" — implies a first-few-seconds problem, not a hard-failed sensor. Supervisor's 5s backoff should resolve on first retry |
| A10 | `push_event()` in sse.py is NOT the right channel for hardware state (it's for driving events) | Pattern (SSE) | Decision: use `/sse/slow` field not `push_event`. Planner can confirm — rationale: hardware state is slow-changing context, not discrete event stream |

## Open Questions

1. **Should OLED show best_effort details or just a roll-up?**
   - What we know: 4 lines is the glanceable budget; critical + important devices need their own tokens
   - What's unclear: whether drivers want "BME:!!" when BME680 is down, or are they fine with "env:2/3"
   - Recommendation: start with roll-up for best_effort, per-device token for critical/important. Tune after first real drive.

2. **Does the existing sampler reboot-on-max-resets conflict with HW-05 ("daemon never refuses to start")?**
   - What we know: HW-05 is about boot; the reboot path in sampler fires after 3 failed recoveries at runtime
   - What's unclear: whether a cold boot with LSM6DSOX missing triggers this reboot loop (if setup() fails 3 times at boot it will)
   - Recommendation: setup() failure path at boot must NOT call `_force_reboot()`. Only the runtime ladder (after successful boot) keeps that behaviour. Boot-time setup failure → report MISSING, continue.

3. **Per-tier backoff ladders?**
   - What we know: D-08 specifies "5s → 15s → 60s → 5 min cap" for all tiers
   - What's unclear: whether critical should retry faster (every 2s during the first minute) to minimise TTS lag
   - Recommendation: implement as specified; revisit if driver feedback complains.

4. **What happens when GPS (reported by `_gps_available` flag in engine) and HardwareState disagree?**
   - What we know: `_gps_available` is the existing flag the engine uses; HardwareState would be a parallel source
   - What's unclear: should GPS presence be reported by gpsd client into HardwareState, with `_gps_available` derived from that?
   - Recommendation: gpsd client reports into HardwareState on connect/disconnect; engine keeps `_gps_available` as a local cache for back-compat but the source of truth migrates to HardwareState. This is a small refactor inside `_init_gps()`.

5. **Is the dashboard hardware panel a new tab or inline on the existing kiosk layout?**
   - What we know: CONTEXT.md D-10 says "dedicated hardware panel in the kiosk UI (fed via SSE)"
   - What's unclear: separate route/tab vs a collapsible panel on the main kiosk
   - Recommendation: follow the pattern in `dashboard/static/index.html` — if there's already a tab system, add a tab; if single-page, add a collapsible panel at the bottom. Planner can inspect current index.html to decide.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.9 | All code | ✓ (dev + Pi) | — | — |
| smbus2 | I2C probe + existing INA226 | ✓ | 0.4.x | — |
| pyyaml | Config loader | ✓ | 6.x | — |
| structlog | Logging | ✓ | 24.x | — |
| RPi.GPIO (via rpi-lgpio) | Button presence probe + existing button handler | ✓ on Pi | 0.6 | On dev machine: `GPIO_AVAILABLE = False` path already in button.py |
| piper-tts | Hardware TTS | ✓ on Pi | 1.4+ | Not installed → `_enqueue` silently drops non-cached messages (speaker.py line 367); buzzer.beep_* still fires. Acceptable for dev |
| `/sys/class/drm` | HDMI probe | ✓ on Pi | — | If absent → probe returns False; HDMI is best_effort, log only |
| `/sys/bus/w1/devices` | 1-Wire probe | ✓ on Pi (w1-gpio overlay loaded) | — | If absent → probe returns False; DS18B20 is best_effort |
| `/proc/asound/cards` | Audio probe | ✓ on any Linux | — | Always present on Linux |
| i2c-gpio bit-bang bus 1 | I2C probe | ✓ (confirmed STATE.md 2026-04-10) | — | If `i2c_designware` is re-enabled, probe still works but clock-stretch bugs return. Not our problem for this phase |

**Missing dependencies with no fallback:** None. The phase composes existing primitives.

**Missing dependencies with fallback:** Dev-machine workflow handles GPIO / 1-Wire / I2C absence via the existing `_HAS_*` import guards. Unit tests can mock these via the existing `tests/conftest.py` patterns.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ (from pyproject.toml dev deps) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (pythonpath = ["src"]) |
| Quick run command | `pytest tests/test_hardware_state.py tests/test_hardware_supervisor.py tests/test_hardware_manifest.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HW-01 | Manifest YAML loads into HardwareManifestConfig with all 14 device entries | unit | `pytest tests/test_config.py::test_hardware_manifest_roundtrip -x` | ❌ Wave 0 |
| HW-01 | Each HardwareDeviceConfig bus type validates its required fields | unit | `pytest tests/test_hardware_manifest.py::test_bus_field_validation -x` | ❌ Wave 0 |
| HW-02 | Boot probe on all 6 bus types correctly reports PRESENT for present devices | unit (mocked) | `pytest tests/test_hardware_probes.py -x` | ❌ Wave 0 |
| HW-02 | HardwareState snapshot reflects probe results within the first tick | unit | `pytest tests/test_hardware_state.py::test_initialise_and_probe -x` | ❌ Wave 0 |
| HW-02 | OLED render reads hw_state.snapshot() and emits lines within one update_interval | unit (render-to-buffer) | `pytest tests/test_oled_hardware_line.py -x` | ❌ Wave 0 |
| HW-02 | /sse/slow payload includes hardware field with all declared devices | unit (Starlette TestClient) | `pytest tests/test_sse_hardware.py -x` | ❌ Wave 0 |
| HW-03 | Critical MISSING triggers repeated TTS (nag interval) + inverted OLED token | unit (speaker mock) | `pytest tests/test_hardware_supervisor.py::test_critical_tier_renags -x` | ❌ Wave 0 |
| HW-03 | Important MISSING triggers single TTS per transition (not re-nagged) | unit | `pytest tests/test_hardware_supervisor.py::test_important_tier_once -x` | ❌ Wave 0 |
| HW-03 | best_effort MISSING only logs — no TTS, no banner | unit | `pytest tests/test_hardware_supervisor.py::test_best_effort_silent -x` | ❌ Wave 0 |
| HW-04 | HardwareState.report_missing schedules next_retry_at per [5s, 15s, 60s, 300s] ladder | unit | `pytest tests/test_hardware_state.py::test_backoff_schedule -x` | ❌ Wave 0 |
| HW-04 | Supervisor calls reprobe callback when next_retry_at elapses; success flips to PRESENT | unit (time mocked) | `pytest tests/test_hardware_supervisor.py::test_reprobe_recovers -x` | ❌ Wave 0 |
| HW-04 | Restored transition speaks hw_*_restored | unit | `pytest tests/test_hardware_supervisor.py::test_restored_emits_tts -x` | ❌ Wave 0 |
| HW-04 | BME680 cold-boot failure: setup raises, supervisor retries at T+5s, succeeds → PRESENT | integration (mocked hardware) | `pytest tests/test_hardware_supervisor.py::test_bme680_canonical_case -x` | ❌ Wave 0 |
| HW-04 | ffmpeg stall → VideoRingBuffer reports degraded/missing into HardwareState | unit | `pytest tests/test_ffmpeg_stall.py::test_stall_reports_degraded -x` | partial — test_ffmpeg_stall.py exists, add assertion |
| HW-05 | Engine.start() completes even when every critical device probes MISSING | integration | `pytest tests/test_engine_boot.py::test_boot_with_all_critical_missing -x` | partial — test_engine_boot.py exists, add case |
| HW-05 | No exception propagates out of engine.start() when LSM6DSOX setup fails at boot | integration | `pytest tests/test_engine_boot.py::test_imu_setup_failure_is_nonfatal -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_hardware_*.py -x` (quick — only the new test files)
- **Per wave merge:** `pytest` (full suite green — especially existing test_i2c_recovery.py must still pass unchanged)
- **Phase gate:** Full suite green + manual on-Pi run: disconnect BME680 wire, boot, confirm supervisor reports MISSING within 1s, then DEGRADED/retry, then reconnect and confirm RESTORED TTS within 5s.

### Wave 0 Gaps

- [ ] `tests/test_hardware_state.py` — HardwareState unit tests (initialise, report_*, snapshot, backoff ladder)
- [ ] `tests/test_hardware_supervisor.py` — supervisor tick, per-tier alert cadence, reprobe callback dispatch, canonical BME680 case
- [ ] `tests/test_hardware_manifest.py` — HardwareDeviceConfig/HardwareManifestConfig YAML round-trip; bus-specific field validation
- [ ] `tests/test_hardware_probes.py` — per-bus probe functions (smbus2 mocked, filesystem mocked via tmp_path, /proc/asound stubbed)
- [ ] `tests/test_oled_hardware_line.py` — renders to a mock image buffer, asserts expected glyphs/inversions
- [ ] `tests/test_sse_hardware.py` — uses the existing async-generator drive pattern from `tests/test_dashboard.py` (see STATE.md Plan 13-03 note about Starlette TestClient + infinite generators); asserts `hardware` field appears in slow payload
- [ ] Extensions to existing files:
  - `tests/test_engine_boot.py` — add HW-05 boot-with-missing-critical case
  - `tests/test_ffmpeg_stall.py` — add HardwareState assertion
  - `tests/test_config.py` — add hardware manifest round-trip test
  - `tests/conftest.py` — shared fixture for a HardwareState with predefined devices (clear between tests)
- [ ] Piper pre-cache entries for 10 new fixed messages (`hw_imu_missing` etc.) — warm-cache happens at `speaker.init()`, no separate test needed; covered by on-Pi smoke check

## Security Domain

Not applicable in any meaningful sense:
- No network surface added (SSE panel reuses existing /sse/slow stream on the existing 0.0.0.0:8080 bind; hardware panel is read-only and contains no secrets)
- No authentication/session/session management change
- Hardware state fields are non-sensitive (device roles, addresses, tiers — all in config.yaml already)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no new auth surface) |
| V3 Session Management | no | — (no sessions) |
| V4 Access Control | no | — (dashboard is Pi-local only per D-10) |
| V5 Input Validation | partial | Config YAML is loaded via `yaml.safe_load`; dataclass types validate shape. No user-supplied runtime input. |
| V6 Cryptography | no | — (no secrets handled) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious device on I2C bus | Spoofing | Not in threat model — I2C is in-car physical, not public. Any device on the bus is one we wired |
| Denial-of-service via sensor disconnection | Availability | Addressed by HW-05 (daemon still boots) and supervisor re-adoption (HW-04). This is the whole phase. |

Everything else is out of scope for this phase.

## Sources

### Primary (HIGH confidence)

- `[VERIFIED: src/shitbox/events/sampler.py lines 30-35, 177-215]` — escalating I2C reset ladder with backoff table `[0, 2, 5]` seconds and `I2C_MAX_RESETS = 3`; existing `_i2c_bus_reset()` at line 222
- `[VERIFIED: src/shitbox/collectors/base.py lines 85-160]` — BaseCollector template method with setup/read/error loop; `_max_errors = 10` and `_error_count`
- `[VERIFIED: src/shitbox/collectors/environment.py lines 11-80]` — existing `_BME680_INIT_RETRIES = 5` with `_BME680_INIT_RETRY_DELAY_S = 1.0` in `setup()`
- `[VERIFIED: src/shitbox/capture/ring_buffer.py lines 786-920]` — `_check_stall`, `_is_stalled`, `_health_monitor`, `video_device_missing` log point
- `[VERIFIED: src/shitbox/dashboard/gps_state.py all lines]` — canonical module-level shared-state pattern for `HardwareState` to mirror
- `[VERIFIED: src/shitbox/utils/config.py lines 464-470]` — list-of-dataclass YAML loading pattern (DS18B20ProbeConfig probes)
- `[VERIFIED: src/shitbox/display/oled.py lines 108-161]` — 4-line OLED render with inversion support
- `[VERIFIED: src/shitbox/capture/speaker.py lines 47-67, 95-113]` — Piper pre-cache + `_CACHED_MESSAGES` pattern; `_detect_usb_speaker` parses `/proc/asound/cards`
- `[VERIFIED: src/shitbox/dashboard/sse.py lines 95-157]` — `/sse/slow` yield structure to extend
- `[VERIFIED: src/shitbox/events/engine.py lines 1917-1928]` — per-collector try/except around `collector.start()` (HW-05 precedent)
- `[VERIFIED: config/config.yaml]` — current YAML shape for existing sensor blocks; the hardware block will follow the same style
- `[VERIFIED: .planning/STATE.md lines 112-142]` — out-of-band hardware work (bit-bang bus, BME680 timing, device set)
- `[VERIFIED: .planning/phases/21-hardware-inventory-and-graceful-degradation/21-CONTEXT.md]` — all locked decisions D-01 through D-11
- `[VERIFIED: graphify-out/GRAPH_REPORT.md]` — communities 0, 1, 2, 8, 9, 10, 12, 17, 20 all surveyed; god nodes `UnifiedEngine` (166 edges), `BaseCollector`, `BatchSyncService` confirmed as the service-pattern anchors
- `[VERIFIED: pyproject.toml lines 10-33]` — all libraries already in deps; `rpi-lgpio>=0.6` is the Pi 5 GPIO shim

### Secondary (MEDIUM confidence)

- `[CITED: STATE.md 2026-04-10 "Outstanding issues"]` — BME680 "physically present (confirmed i2cdetect), but daemon logs No I2C device at address: 0x77 at startup"; "Likely a boot timing issue — sensor not ready when daemon starts"

### Tertiary (LOW confidence)

- None. The phase's approach is anchored in shipped patterns; no training-data-only claims are made.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; every primitive already in the codebase and proven in production
- Architecture: HIGH — the module-level state + tick-loop supervisor pattern is a direct parallel to `gps_state` + `BatchSyncService`, both of which have been shipping since v1.0
- Pitfalls: HIGH for 1-7 (all derived from real code paths and STATE.md out-of-band notes); MEDIUM for the HDMI connector name assumption (A1) which could be wrong on first fit without consequence
- Validation: HIGH — test file structure mirrors existing `tests/test_*.py` layout; gaps are explicitly listed for Wave 0

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (30 days — codebase is stable, no upstream library churn expected; re-verify if v2 hardware changes again)
