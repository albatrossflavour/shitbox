# Phase 2: Watchdog and Self-Healing - Research

**Researched:** 2026-02-25
**Domain:** Embedded Linux self-healing — hardware watchdog, systemd service recovery, ffmpeg stall detection, I2C bus recovery
**Confidence:** HIGH

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- Hardware watchdog timeout: 10 seconds
- 30-second grace period at boot before watchdog enforcement begins
- No special reboot loop detection — each reboot is a fresh attempt
- Watchdog pet source: Claude's discretion (main loop vs dedicated thread)
- I2C: automatic bit-bang reset after 5 consecutive read failures (~50ms at 100 Hz)
- I2C: use the same GPIO2/GPIO3 SDA/SCL pins — temporarily switch to output mode, pulse 9 clock cycles, switch back
- If bit-bang reset fails to recover the bus: force a full system reboot
- No intermediate escalation — go straight from bit-bang to reboot
- Distinct buzzer patterns per failure type (1 long = service crash, 3 short = I2C lockup, 2 long = watchdog miss)
- Escalating repeat alerts: first occurrence brief, recurrence within 5 minutes triggers louder/longer pattern
- Recovery confirmation: short chirp when a failed service comes back
- Silent during boot: suppress all buzzer alerts during the 30-second settling period
- Unlimited restart attempts for crashed services — never give up
- Exponential backoff between attempts: 1s, 2s, 4s, 8s, etc.
- ffmpeg stall detection via output file size monitoring — if file size unchanged for N seconds, kill and restart ffmpeg
- After backoff reaches a ceiling, reset counter and try again with fresh backoff

### Claude's Discretion

- Watchdog pet source architecture (main engine loop vs dedicated thread)
- Exact buzzer tone frequencies and durations for each pattern
- Exponential backoff ceiling value
- ffmpeg stall detection timeout threshold
- Specific structlog fields for health monitoring events

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WDOG-01 | BCM2835 hardware watchdog enabled (`dtparam=watchdog=on`, `RuntimeWatchdogSec=14`) | Systemd unit file already has `WatchdogSec=30` and `Type=notify`; needs to change to 14s and add `StartLimitIntervalSec=0` |
| WDOG-02 | All systemd services audited and configured with `Restart=always` | Current unit file already has `Restart=always`, `RestartSec=5`; needs `StartLimitIntervalSec=0` to prevent permanent failure after rapid restarts |
| WDOG-03 | ffmpeg `is_running` bug fixed to use `poll()` with mtime-based health check and auto-restart | `VideoRingBuffer._health_monitor()` already restarts on process death but does NOT detect stall (alive process, frozen output); mtime monitoring of newest segment file is the fix |
| WDOG-04 | I2C bus lockup detected and recovered via 9-clock bit-bang reset | No existing I2C recovery in sampler.py; needs consecutive-failure counter + RPi.GPIO bit-bang on GPIO2/GPIO3 + smbus2 close/reopen; fallback is `os.system("sudo reboot")` |
| HLTH-02 | In-car buzzer alerts on service failures, I2C lockup, and watchdog miss | `buzzer.py` already has `_play_async(tones, name)` pattern; needs new pattern functions + escalation state tracker |

</phase_requirements>

## Summary

Phase 2 is a self-healing layer built on top of the existing engine. The codebase already has most infrastructure in place: `WatchdogSec=30` in the systemd unit file, `WATCHDOG=1` petting via `_notify_systemd()` in the main loop, and a `_health_monitor()` thread in `VideoRingBuffer` that restarts ffmpeg on process death. This means the work is largely about fixing gaps rather than building from scratch.

The five requirement areas are: (1) reduce the systemd watchdog timeout to 14s and prevent the unit from permanently failing after rapid restarts; (2) audit the single service unit file; (3) add mtime-based stall detection to the existing ffmpeg health monitor; (4) add a consecutive-failure counter and GPIO bit-bang recovery to `HighRateSampler._sample_loop()`; (5) add per-failure-type buzzer patterns to `buzzer.py` and an escalation state object.

The primary risk area is I2C bit-bang recovery: temporarily switching GPIO2/GPIO3 to output mode while the I2C driver still owns them requires careful sequencing (close smbus2, manipulate GPIO, reopen smbus2). This is well-understood in the embedded Linux community and is exactly the pattern that survives in Raspberry Pi forum discussions and the Adafruit CircuitPython issue tracker. The fallback to reboot is the correct safety net.

**Primary recommendation:** Implement in three focused plans: (1) systemd watchdog wiring + WDOG-01/WDOG-02; (2) I2C recovery service (WDOG-04) + buzzer patterns (HLTH-02); (3) ffmpeg stall detection fix (WDOG-03).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| RPi.GPIO | system package | GPIO pin mode switching for bit-bang reset | Already on Pi; direct hardware control; no daemon needed |
| smbus2 | >=0.4.0 (in pyproject.toml) | I2C bus open/close during bit-bang recovery | Already a project dependency |
| Python stdlib `socket` | stdlib | sd_notify / WATCHDOG=1 petting | Already used in engine `_notify_systemd()`; zero new deps |
| Python stdlib `os` | stdlib | Triggering reboot via `os.system("sudo systemctl reboot")` | Simplest safe escalation path |
| Python stdlib `time` | stdlib | Exponential backoff timing | No external dep needed |
| PiicoDev_Buzzer | >=1.0.0 (in pyproject.toml) | Playing buzzer tones via `.tone(freq, duration_ms)` | Already a project dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `threading.Event` | stdlib | Shutdown signalling for the watchdog pet thread | If pet source is dedicated thread (Claude's discretion) |
| `structlog` | >=24.0.0 | Structured log fields for health events | Already the project logging standard |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| RPi.GPIO for bit-bang | pigpio daemon | pigpio is more capable but requires a running daemon (`pigpiod`), adding a systemd dependency; RPi.GPIO is simpler for 9-pulse recovery |
| Pure socket `_notify_systemd()` | `systemd-watchdog` PyPI package | Package adds a dep and version surface; existing socket impl already works and is in production |
| `os.system("reboot")` | `subprocess.run(["systemctl", "reboot"])` | Both work; `subprocess.run` is cleaner and avoids shell injection; prefer subprocess |

**Installation:** No new packages required. All dependencies already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure

```
src/shitbox/
├── capture/
│   └── buzzer.py              # Add: beep_service_crash(), beep_i2c_lockup(),
│                              #      beep_watchdog_miss(), beep_service_recovered()
│                              #      BuzzerAlertState (escalation tracker)
├── events/
│   ├── engine.py              # Change: WatchdogSec pet interval; wire HealthMonitorService
│   └── sampler.py             # Add: consecutive-failure counter; I2CRecoveryMixin
├── capture/
│   └── ring_buffer.py         # Fix: add mtime-based stall detection to _health_monitor()
└── sync/
    └── health_monitor.py      # NEW: HealthMonitorService (service-crash watchdog + alerts)

systemd/
└── shitbox-telemetry.service  # Change: WatchdogSec=14, StartLimitIntervalSec=0
```

### Pattern 1: Systemd Hardware Watchdog (WDOG-01)

**What:** Two-layer watchdog. Hardware BCM2835 chip is armed by systemd's `RuntimeWatchdogSec` in `/etc/systemd/system.conf`. Kernel resets the Pi if systemd itself hangs. Systemd's `WatchdogSec` in the service unit controls service-level petting — if the Python process stops sending `WATCHDOG=1`, systemd kills and restarts it.

**When to use:** Always. Hardware watchdog is the last resort; service-level watchdog handles application hangs.

**Configuration in `/etc/systemd/system.conf`:**

```ini
# /etc/systemd/system.conf.d/watchdog.conf  (drop-in preferred)
[Manager]
RuntimeWatchdogSec=14
ShutdownWatchdogSec=5min
```

**Configuration in the service unit (already exists, needs changes):**

```ini
[Service]
Type=notify
Restart=always
RestartSec=5
WatchdogSec=14
StartLimitIntervalSec=0   # CRITICAL: never give up restarting
```

**Python petting (already in engine.py main loop — just confirm interval):**

```python
# engine.py run() - existing pattern, send every ~5s (well under half of 14s)
while self._running:
    self._notify_systemd("WATCHDOG=1")
    # ... health check logic ...
    time.sleep(1.0)
```

The existing `_notify_systemd()` uses `NOTIFY_SOCKET` via a Unix datagram socket. This is the correct pattern — no library needed.

**Confidence:** HIGH — verified against systemd man pages and Raspberry Pi forum discussions.

### Pattern 2: I2C Bus Lockup Recovery (WDOG-04)

**What:** The `HighRateSampler._sample_loop()` already catches exceptions on read. The fix adds a consecutive-failure counter. At 5 consecutive failures (~50ms at 100 Hz), trigger the bit-bang recovery sequence before giving up.

**Bit-bang sequence:**

```python
import RPi.GPIO as GPIO
import time

def _i2c_bus_reset(self) -> bool:
    """Attempt 9-clock bit-bang recovery on GPIO2 (SDA) / GPIO3 (SCL).

    Returns True if recovery appears successful (no exception after reopen).
    """
    SCL_PIN = 3  # GPIO3 = physical pin 5
    SDA_PIN = 2  # GPIO2 = physical pin 3

    # 1. Close the smbus2 handle so the I2C driver releases the pins
    try:
        self._bus.close()
    except Exception:
        pass

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SCL_PIN, GPIO.OUT, initial=GPIO.HIGH)

        # 2. Pulse SCL 9 times to clock out any stuck byte on SDA
        for _ in range(9):
            GPIO.output(SCL_PIN, GPIO.LOW)
            time.sleep(0.000005)   # 5 µs half-cycle (~100 kHz)
            GPIO.output(SCL_PIN, GPIO.HIGH)
            time.sleep(0.000005)

        # 3. Generate STOP condition: SDA low → SDA high while SCL high
        GPIO.setup(SDA_PIN, GPIO.OUT, initial=GPIO.LOW)
        time.sleep(0.000005)
        GPIO.output(SDA_PIN, GPIO.HIGH)

    finally:
        GPIO.cleanup([SCL_PIN, SDA_PIN])  # Returns pins to I2C driver control

    # 4. Reopen smbus2
    try:
        import smbus2
        self._bus = smbus2.SMBus(self.i2c_bus)
        return True
    except Exception:
        return False
```

**Key constraint:** `GPIO.cleanup([SCL_PIN, SDA_PIN])` releases only the pins used during recovery, leaving other GPIO state intact. This is essential because other subsystems (button handler, buzzer) use GPIO.

**Fallback (bit-bang failed or bus still locked after reopen attempt):**

```python
import subprocess
subprocess.run(["sudo", "systemctl", "reboot"], check=False)
```

The systemd unit's `Restart=always` ensures the service comes back after reboot.

**Confidence:** MEDIUM — the 9-clock technique is well-documented in I2C spec and Raspberry Pi forums. The `GPIO.cleanup([pin_list])` selective cleanup is verified in RPi.GPIO docs. The exact timing (5 µs half-cycle = 100 kHz) is conventional I2C recovery speed.

### Pattern 3: ffmpeg Stall Detection (WDOG-03)

**What:** `VideoRingBuffer._health_monitor()` already restarts ffmpeg when the process dies (`poll() is not None`). The bug (WDOG-03) is that ffmpeg can be alive but producing no output — the process runs but writes nothing to the segment files.

**Fix:** Track the modification time (`st_mtime`) and size of the newest segment file. If neither changes for N seconds, the process is stalled.

```python
# In VideoRingBuffer._health_monitor() — add alongside existing crash check
STALL_TIMEOUT_SECONDS = 30  # Claude's discretion; conservative for 10s segments

_last_segment_mtime: float = time.time()
_last_segment_size: int = 0

def _check_stall(self) -> bool:
    """Return True if newest segment file is stalled."""
    segments = self._get_buffer_segments()
    if not segments:
        return False  # No segments yet — give it time to start
    newest = segments[-1]
    try:
        st = newest.stat()
    except OSError:
        return False
    if st.st_mtime != self._last_segment_mtime or st.st_size != self._last_segment_size:
        self._last_segment_mtime = st.st_mtime
        self._last_segment_size = st.st_size
        return False
    # File unchanged — stalled if beyond timeout
    return (time.time() - self._last_segment_mtime) > self.STALL_TIMEOUT_SECONDS
```

On stall detection: log, buzz, kill process, call `_start_ffmpeg()`. The existing `_kill_current()` + `_start_ffmpeg()` are already there.

**Confidence:** HIGH — file mtime monitoring is the standard approach; used in production video monitoring systems. The existing ring_buffer.py already uses `st_mtime` for segment ordering.

### Pattern 4: Buzzer Alert Patterns (HLTH-02)

**What:** Add new alert functions to `buzzer.py` following the existing `_play_async(tones, name)` pattern. Add an `BuzzerAlertState` class to track escalation (recurrence within 5 minutes triggers louder/longer pattern).

**Tone pattern assignment (Claude's discretion — recommend):**

| Failure | Pattern | Frequencies |
|---------|---------|-------------|
| Service crash | 1 long low | `[(330, 800)]` |
| I2C lockup | 3 short low | `[(330, 200), (330, 200), (330, 200)]` |
| Watchdog miss | 2 long low | `[(330, 600), (330, 600)]` |
| ffmpeg stall | 2 short + 1 long | `[(330, 200), (330, 200), (330, 600)]` |
| Service recovered | 1 short high chirp | `[(880, 150)]` |
| Escalated (any) | Same pattern × 2, louder | Use `volume(2)` before playing |

330 Hz is a low C (learnable as "warning"), distinct from the existing 440/660/880 Hz boot and capture tones.

**BuzzerAlertState** (simple Python class, not a new file — add to buzzer.py):

```python
import time

class BuzzerAlertState:
    """Track alert recurrence for escalation."""
    ESCALATION_WINDOW_SECONDS = 300  # 5 minutes

    def __init__(self) -> None:
        self._last_alerts: dict[str, float] = {}  # alert_type → last_time

    def should_escalate(self, alert_type: str) -> bool:
        now = time.time()
        last = self._last_alerts.get(alert_type, 0)
        self._last_alerts[alert_type] = now
        return (now - last) < self.ESCALATION_WINDOW_SECONDS
```

**Silence during boot:** Check against engine start time before calling any alert function. The engine already tracks `_engine_start_time` and uses `HEALTH_GRACE_PERIOD = 60.0`.

**Confidence:** HIGH — directly extends the existing buzzer.py pattern.

### Pattern 5: Watchdog Pet Source (Claude's Discretion)

**What:** The existing main loop in `engine.run()` already sends `WATCHDOG=1` every ~1 second. The question is whether to keep it there or move to a dedicated thread.

**Recommendation: keep in the main loop.** Rationale:
- The main loop is the single point of engine liveness. If the main loop hangs, the watchdog naturally times out.
- A dedicated thread could keep petting even if the main loop deadlocks, defeating the purpose.
- The current 1-second sleep in the main loop pets far more frequently than needed (half of 14s = 7s max interval).

**Only use a dedicated thread if** health checks are moved out of the main loop and could block it (unlikely given their current structure).

### Anti-Patterns to Avoid

- **Using `StartLimitBurst=` without disabling `StartLimitIntervalSec`:** systemd will permanently stop restarting after burst limit. Use `StartLimitIntervalSec=0` to disable the limit entirely.
- **GPIO.cleanup() on all pins during I2C recovery:** Will reset button GPIO, LED state, etc. Use `GPIO.cleanup([SCL_PIN, SDA_PIN])` for selective cleanup.
- **Calling `GPIO.setmode()` if another module already set it:** Check or use `GPIO.setwarnings(False)` and handle the `GPIO.WrongDirectionException`. Alternatively, use the already-available `gpiozero` (which wraps RPi.GPIO) — but RPi.GPIO's direct control is simpler for this use case.
- **Not reinitialising MPU6050 after bus recovery:** After `smbus2.SMBus()` reopen, call `setup()` (the MPU6050 init sequence) before resuming reads, as the power registers may have been reset.
- **Petting watchdog in the wrong thread:** The pet must come from a thread that is only alive when the whole system is healthy. Main loop is correct.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Systemd sd_notify protocol | Custom socket protocol | Existing `_notify_systemd()` in engine.py | Already implemented and tested |
| Service restart exponential backoff | Python retry loop | systemd `Restart=always` + `RestartSec=5` | systemd handles it; exponential inside the process is for I2C/internal recovery |
| ffmpeg process health | Custom subprocess tracking | File mtime monitoring on existing segments | The segment files are the ground truth of ffmpeg output |
| Buzzer hardware protocol | Direct I2C writes | `PiicoDev_Buzzer.tone()` | Already in project; handles I2C communication |

**Key insight:** This phase is fundamentally configuration + small code additions to existing modules, not new services.

## Common Pitfalls

### Pitfall 1: RuntimeWatchdogSec vs WatchdogSec

**What goes wrong:** Configuring only `WatchdogSec=14` in the service file without setting `RuntimeWatchdogSec=14` in `system.conf`. Result: the BCM2835 hardware watchdog is never armed; only the service-level watchdog fires.
**Why it happens:** The two settings control different layers. `WatchdogSec` in a service unit controls systemd's software watchdog (pet via `WATCHDOG=1`). `RuntimeWatchdogSec` in `system.conf` controls the hardware `/dev/watchdog` device.
**How to avoid:** Set both. `RuntimeWatchdogSec` must be set to a value ≤ 15 on Raspberry Pi (hardware limit).
**Warning signs:** If `cat /sys/class/watchdog/watchdog0/status` shows `inactive`, `RuntimeWatchdogSec` is not set or not reaching the driver.

### Pitfall 2: StartLimitIntervalSec Causes Permanent Service Death

**What goes wrong:** Service crashes 5 times in 10 seconds (e.g. during I2C init on a locked bus), systemd hits `DefaultStartLimitBurst=5`, marks the service as `failed`, and stops restarting.
**Why it happens:** systemd's default `StartLimitIntervalSec=10s` and `StartLimitBurst=5` are designed for servers, not embedded systems.
**How to avoid:** Add `StartLimitIntervalSec=0` to the `[Service]` section. This disables the limit entirely.
**Warning signs:** `systemctl status shitbox-telemetry` shows `Active: failed` with `(Result: start-limit-hit)`.

### Pitfall 3: I2C GPIO Cleanup Stomps Other GPIO

**What goes wrong:** `GPIO.cleanup()` (no arguments) resets ALL GPIO pins, not just SCL/SDA. The button handler on GPIO17 loses its configuration.
**Why it happens:** `GPIO.cleanup()` without arguments is a global reset.
**How to avoid:** Use `GPIO.cleanup([2, 3])` to selectively reset only the pins used for bit-bang recovery.
**Warning signs:** Button stops working after an I2C recovery event.

### Pitfall 4: MPU6050 Silently Stale After Bus Recovery

**What goes wrong:** After I2C bus recovery (smbus2 close + reopen), reads succeed (no exception) but return stale data because the MPU6050's FIFO or registers are in an unknown state.
**Why it happens:** SMBus reopen does not reinitialise the sensor; the hardware reset state is not guaranteed.
**How to avoid:** After successful `smbus2.SMBus()` reopen, call `self.setup()` to reinitialise MPU6050 registers before resuming the sample loop.
**Warning signs:** Samples after recovery show identical or zero values.

### Pitfall 5: ffmpeg Stall Detector False Positive at Start

**What goes wrong:** The stall detector fires immediately on startup because no segment files exist yet, or immediately after a crash restart while ffmpeg is initialising.
**Why it happens:** Checking `st_mtime` when no segments have been written yet returns nothing; an incorrect implementation might treat "no segments" as a stall.
**How to avoid:** Only arm the stall detector after the first segment appears. Reset the stall timer on every ffmpeg restart.
**Warning signs:** ffmpeg immediately killed and restarted in a loop; log shows `ffmpeg_stall_detected` at launch.

### Pitfall 6: Buzzer Alert During Boot Grace Period

**What goes wrong:** A transient I2C error during the 30-second settling window triggers a buzzer alert, confusing the driver before the system has stabilised.
**Why it happens:** Alert functions called without checking boot grace period.
**How to avoid:** Pass engine start time to the alert dispatcher; suppress alerts if `time.time() - engine_start_time < GRACE_PERIOD_SECONDS`.
**Warning signs:** Buzzer alerts sound within 30 seconds of boot.

## Code Examples

Verified patterns from existing code and official sources:

### Existing sd_notify Pattern (engine.py)

```python
# Source: src/shitbox/events/engine.py (existing, verified)
@staticmethod
def _notify_systemd(state: str) -> None:
    """Send notification to systemd."""
    try:
        import os
        import socket as sock
        notify_socket = os.environ.get("NOTIFY_SOCKET")
        if not notify_socket:
            return
        s = sock.socket(sock.AF_UNIX, sock.SOCK_DGRAM)
        try:
            s.connect(notify_socket)
            s.sendall(state.encode())
        finally:
            s.close()
    except Exception:
        pass
```

Call as: `self._notify_systemd("WATCHDOG=1")` — already done in `run()` every second.

### Existing Buzzer Pattern (buzzer.py)

```python
# Source: src/shitbox/capture/buzzer.py (existing, verified)
def _play_async(tones: list[tuple[int, int]], name: str = "buzzer") -> None:
    if _buzzer is None:
        return
    thread = threading.Thread(target=_play, args=(tones,), daemon=True, name=name)
    thread.start()

# New function (same pattern):
def beep_service_crash() -> None:
    """1 long low tone: service crash detected."""
    _play_async([(330, 800)], name="buzzer-service-crash")
```

### Existing VideoRingBuffer Health Monitor (ring_buffer.py)

```python
# Source: src/shitbox/capture/ring_buffer.py (existing, verified)
def _health_monitor(self) -> None:
    while self._running:
        time.sleep(self.RESTART_BACKOFF_SECONDS)
        if not self._running:
            break
        # Crash detection (existing):
        if self._process is not None and self._process.poll() is not None:
            self._start_ffmpeg()
            continue
        # Stall detection (to add):
        if self._is_stalled():
            log.warning("ffmpeg_stall_detected")
            buzzer.beep_ffmpeg_stall()  # new pattern
            self._kill_current()
            self._start_ffmpeg()
```

### Systemd Service Unit Drop-in

```ini
# /etc/systemd/system/shitbox-telemetry.service.d/watchdog.conf
# OR edit systemd/shitbox-telemetry.service directly (it's in the repo)
[Service]
WatchdogSec=14
StartLimitIntervalSec=0
```

### System.conf Drop-in for Hardware Watchdog

```ini
# /etc/systemd/system.conf.d/watchdog.conf  (deployed to Pi)
[Manager]
RuntimeWatchdogSec=14
ShutdownWatchdogSec=5min
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `watchdog` apt package daemon | systemd `RuntimeWatchdogSec` | systemd v220+ (2015) | Simpler; no extra process |
| `StartLimitBurst=0` (old syntax) | `StartLimitIntervalSec=0` | systemd v229 | Different semantics; old syntax may still work but is non-obvious |
| `GPIO.cleanup()` (all pins) | `GPIO.cleanup([pin_list])` | RPi.GPIO 0.6.2 | Essential for selective cleanup |
| Polling subprocess.stdout for ffmpeg progress | File mtime monitoring | N/A | mtime works for segment muxer; stdout is suppressed in this project |

**Deprecated/outdated:**

- Using `watchdog` apt package: superseded by systemd `RuntimeWatchdogSec` for simple hang detection; still useful for load-based reset but not required for this phase.
- `RestartSteps=` (systemd exponential backoff): Added in systemd v254 (2023) but not available on Raspberry Pi OS Bookworm's systemd version (v252). Do not rely on it; use application-level exponential backoff instead.

## Open Questions

1. **RPi.GPIO availability vs gpiozero**
   - What we know: `pyproject.toml` does not list RPi.GPIO or gpiozero as a dependency. The project uses PiicoDev (which uses I2C, not GPIO directly).
   - What's unclear: Whether `RPi.GPIO` is available on the target Pi without explicit installation.
   - Recommendation: Add `RPi.GPIO` to `pyproject.toml` dependencies. On Raspberry Pi OS it is pre-installed system-wide but making it explicit avoids silent failures in dev. Alternatively, use `gpiozero` (also pre-installed) with `gpiozero.OutputDevice` which wraps RPi.GPIO.

2. **dtparam=watchdog=on requirement**
   - What we know: On modern Raspberry Pi OS (Bookworm), the BCM2835 watchdog driver is built into the kernel and may be auto-enabled. But `dtparam=watchdog=on` in `/boot/firmware/config.txt` (Bookworm path) is the safe explicit enabler.
   - What's unclear: Whether the production Pi has this already set.
   - Recommendation: Add a check or deployment note; the plan should include verifying `/boot/firmware/config.txt` (or `/boot/config.txt` on older Pi OS) and adding `dtparam=watchdog=on` if absent.

3. **smbus2 reinitialise after GPIO recovery**
   - What we know: After `GPIO.cleanup([2, 3])`, the I2C driver should re-claim the pins. But there is no documented guarantee of the recovery timing.
   - What's unclear: Whether a `time.sleep(0.1)` delay is needed between `GPIO.cleanup` and `smbus2.SMBus()` reopen.
   - Recommendation: Include a 100ms sleep after cleanup before reopening smbus2. This is conservative and safe.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ |
| Config file | `pyproject.toml` (no `[tool.pytest.ini_options]` section yet — works without it) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest --cov=shitbox tests/` |
| Estimated runtime | ~5 seconds (all existing tests run in <3s) |

### Phase Requirements to Test Map

| Req ID | Behaviour | Test Type | Automated Command | File Exists? |
|--------|-----------|-----------|-------------------|-------------|
| WDOG-01 | `WatchdogSec=14` present in unit file; `_notify_systemd("WATCHDOG=1")` sends correctly | unit | `pytest tests/test_watchdog.py::test_watchdog_unit_file_has_14s -x` | ❌ Wave 0 gap |
| WDOG-01 | sd_notify petting happens at least once per 7s in main loop simulation | unit | `pytest tests/test_watchdog.py::test_watchdog_pet_frequency -x` | ❌ Wave 0 gap |
| WDOG-02 | `Restart=always` and `StartLimitIntervalSec=0` in unit file | unit | `pytest tests/test_watchdog.py::test_service_unit_restart_policy -x` | ❌ Wave 0 gap |
| WDOG-03 | Stall detector returns `False` when segment mtime changes | unit | `pytest tests/test_ffmpeg_stall.py::test_stall_not_detected_on_activity -x` | ❌ Wave 0 gap |
| WDOG-03 | Stall detector returns `True` after STALL_TIMEOUT with no mtime change | unit | `pytest tests/test_ffmpeg_stall.py::test_stall_detected_after_timeout -x` | ❌ Wave 0 gap |
| WDOG-03 | Stall detection arms only after first segment appears | unit | `pytest tests/test_ffmpeg_stall.py::test_stall_not_triggered_before_first_segment -x` | ❌ Wave 0 gap |
| WDOG-04 | Consecutive failure counter resets to 0 on successful read | unit | `pytest tests/test_i2c_recovery.py::test_failure_counter_resets_on_success -x` | ❌ Wave 0 gap |
| WDOG-04 | Bit-bang recovery called after 5 consecutive failures | unit (mocked GPIO) | `pytest tests/test_i2c_recovery.py::test_bitbang_triggered_after_5_failures -x` | ❌ Wave 0 gap |
| WDOG-04 | Reboot triggered when bit-bang recovery fails | unit (mocked subprocess) | `pytest tests/test_i2c_recovery.py::test_reboot_on_bitbang_failure -x` | ❌ Wave 0 gap |
| HLTH-02 | `beep_service_crash()` calls `_play_async` with correct tone | unit | `pytest tests/test_buzzer_alerts.py::test_beep_service_crash_pattern -x` | ❌ Wave 0 gap |
| HLTH-02 | `beep_i2c_lockup()` calls `_play_async` with 3-short pattern | unit | `pytest tests/test_buzzer_alerts.py::test_beep_i2c_lockup_pattern -x` | ❌ Wave 0 gap |
| HLTH-02 | Escalation: second alert within 5min uses louder pattern | unit | `pytest tests/test_buzzer_alerts.py::test_escalation_within_window -x` | ❌ Wave 0 gap |
| HLTH-02 | Alerts suppressed during boot grace period | unit | `pytest tests/test_buzzer_alerts.py::test_alerts_suppressed_during_grace -x` | ❌ Wave 0 gap |
| HLTH-02 | `beep_service_recovered()` plays chirp pattern | unit | `pytest tests/test_buzzer_alerts.py::test_beep_service_recovered -x` | ❌ Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `pytest tests/ -x -q`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~5 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_watchdog.py` — covers WDOG-01, WDOG-02 (unit file parsing + sd_notify)
- [ ] `tests/test_ffmpeg_stall.py` — covers WDOG-03 (mtime-based stall detection with tmp_path)
- [ ] `tests/test_i2c_recovery.py` — covers WDOG-04 (mocked GPIO and smbus2)
- [ ] `tests/test_buzzer_alerts.py` — covers HLTH-02 (new buzzer patterns and escalation)
- [ ] No framework install needed — pytest already in dev deps

## Sources

### Primary (HIGH confidence)

- systemd man page `sd_notify(3)` — <https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html> — WATCHDOG=1 semantics, petting frequency recommendation
- Existing `engine.py` (lines 1565–1681) — `_notify_systemd()` socket implementation, current `WATCHDOG=1` petting in main loop
- Existing `ring_buffer.py` (lines 454–488) — `_health_monitor()` crash restart pattern
- Existing `buzzer.py` — `_play_async(tones, name)` pattern all new alerts must follow

### Secondary (MEDIUM confidence)

- Michael Stapelberg's systemd indefinite restarts (2024) — <https://michael.stapelberg.ch/posts/2024-01-17-systemd-indefinite-service-restarts/> — `StartLimitIntervalSec=0` pattern
- Adafruit CircuitPython issue #2635 — <https://github.com/adafruit/circuitpython/issues/2635> — 9-clock bit-bang I2C recovery code shape in Python
- Raspberry Pi forum watchdog not working thread — <https://forums.raspberrypi.com/viewtopic.php?t=353094> — confirms 15s hardware limit and `RuntimeWatchdogSec=14` pattern
- IoT Assistant Raspberry Pi watchdog guide — <https://iotassistant.io/raspberry-pi/how-to-set-watchdog-timer-raspberrypi/> — `dtparam=watchdog=on` enablement

### Tertiary (LOW confidence)

- FFmpeg stall monitoring blog post — <https://til.yulrizka.com/unix/ffmpeg-monitor-and-restart-stream-when-it-hung-or-stall> — log-line comparison approach; this phase uses mtime instead (more reliable for segment muxer)
- systemd-watchdog PyPI package — <https://pypi.org/project/systemd-watchdog/> — confirms existing socket approach is equivalent to a full library; not adopted

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all dependencies already in project; patterns directly derived from existing code
- Architecture: HIGH — WDOG-01/02/HLTH-02 are configuration + small additions; WDOG-03 is a targeted fix to an existing method
- Pitfalls: MEDIUM — I2C GPIO recovery pitfalls derived from forum research and I2C spec knowledge; not empirically tested in this codebase
- I2C bit-bang specifics: MEDIUM — technique is documented but timing constants (5µs half-cycle) are conventional, not Pi-specific measurements

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable embedded Linux / systemd domain)
