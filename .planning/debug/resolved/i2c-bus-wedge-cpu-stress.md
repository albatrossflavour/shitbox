---
slug: i2c-bus-wedge-cpu-stress
status: resolved
trigger: |
  I2C bus wedge under CPU/IO stress on the Pi 5. TCA4307 latch hypothesis ruled
  out today by stress-test evidence. Need to plan the real fix path between
  three options: real-time scheduling for the i2c-gpio kernel thread, hardware
  kill-switch on Qwiic VCC, or accepting operator-workflow recovery. Brain note
  ~/Brain/projects/shitbox-rally-2026.md has the full multi-day history.
created: 2026-04-29T01:28:00Z
updated: 2026-04-29T12:00:00Z
branch: gsd/phase-28-tpms-integration
---

# I2C Bus Wedge Under CPU/IO Stress

## Symptoms

**Expected behaviour:**
I2C bus stays alive under heavy CPU/IO load. All 8 sensors on the Qwiic chain
(0x10 VEML7700, 0x19 PM2.5, 0x1c LIS3MDL, 0x3c OLED, 0x40 INA226, 0x5c buzzer,
0x6a LSM6DSOX, 0x77 BME680) keep ACKing transactions. Sampler at 25 Hz keeps
reading the IMU. Recovery, if needed, is automatic.

**Actual behaviour:**
Under sustained stress (stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 200M
--timeout 60s on a 4-core Pi 5), the bus wedges within ~60 seconds.
i2cdetect -y 1 returns empty across the entire address space. Daemon enters
give-up backoff (60 s) after I2C_MAX_RESETS short retries. IMU role
transitions present → degraded → missing. Bus stays dead until a hard
power-cycle of the Pi (USB-C unplug ~20 s).

**Error markers:**
- `[Errno 6] No such device or address` (ENXIO) bursts of 5+ within ~200 ms
- `i2c_bus_lockup_detected` consecutive_failures=5, reset_attempt=1
- `tca_en_pulsed_low pulse_ok=true` followed by `tca_en_recovery_setup_result recovered=false` × 3
- `i2c_bus_still_wedged` consecutive_failures=8, reset_attempt=4, "manual hard
  power-cycle required if TCA latched"
- `hw_state_transition role=imu prev=degraded new=missing`

**Timeline:**
- 2026-04-28 evening: lockup #1 (Phase 28 deploy churn, attributed to
  RPi.GPIO recovery brittleness at the time)
- 2026-04-29 09:05:50: lockup #2 (morning bench session, first reproduction
  with `rough_road` capture concurrency suspected)
- 2026-04-29 afternoon: lockup #3 (deliberately reproduced with stress-ng,
  third independent occurrence in 24 hours)

**Reproduction:**
```
ssh tgreen@10.10.20.107
sudo systemctl restart shitbox-telemetry
sleep 30  # let daemon settle
stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 200M --timeout 60s --metrics-brief
# Within ~60 s, expect to see i2c_bus_lockup_detected then i2c_bus_still_wedged
```

## Recovery Mechanisms Tested Today

| Mechanism | Outcome |
|---|---|
| TCA4307 EN pulse 10 ms (GPIO 12) | does not recover |
| TCA4307 EN pulse 100 ms | does not recover |
| Kernel `i2c-gpio` unbind/rebind | does not recover |
| Hard power-cycle Pi USB-C ~20 s | **recovers** ✓ |

The TCA EN-pulse fires cleanly each time (`pulse_ok=true`, GPIO 12 toggles
verified by `pinctrl get 12` showing `op dh`). The kernel `i2c-gpio` driver
rebinds successfully (dmesg confirms `using lines 571 (SDA) and 572 (SCL)`
after every bind). Neither restores ACKs from any device on the chain.

Only a real VCC drop on the Qwiic 3.3 V rail recovers the bus.

## Working Hypothesis (entering investigation)

**SCL stuck low via clock-stretching gone wrong on a slave.** Under CPU/IO
jitter, the bit-bang `i2c-gpio` kernel routine extends a clock pulse or
mistimes a START/STOP. One or more slaves on the chain (LSM6DSOX 0x6a
most likely given the original ENXIO source, but symptoms suggest possibly
all of them) see a malformed transaction, enter clock-stretching, and never
release SCL — their state machine is hung in a wait that can only be cleared
by their own VCC dropping. The TCA isn't the actual culprit — it just looks
that way because hard power-cycle (which IS the recovery) also resets the TCA.

This explains why neither EN-pulse nor kernel driver rebind helps: both
operate on the bus topology, neither power-cycles the slaves.

### Evidence from TI app note SCPA069 (saved at .planning/debug/scpa069-i2c-stuck-bus.txt)

Two distinct stuck-bus failure modes per the TI app note:

1. **SDA stuck low** — caused by false clock edges desynchronising the
   target's state machine. Resolution: master toggles SCL 8–16 times +
   stop condition. **The TCA4307 does this in hardware** when it detects
   SDA low > 40 ms (`t_stuckbus`). It disconnects downstream, signals via
   `RDY` pin LOW, runs the 16-pulse sequence, then auto-reconnects.

2. **SCL stuck low via clock-stretching slave** — quoted directly:
   > "there are some I2C target devices which can execute clock stretching
   > and in rare cases can potentially get the clock stuck low. **In these
   > cases, the only recovery method can be a reset or power cycle of the
   > device sticking the bus low.**"

Our empirical evidence (EN pulse fails, kernel rebind fails, only hard
power-cycle of Pi 3.3 V rail recovers) maps cleanly to mode #2. There is
**no software recovery path** for SCL-stuck-by-clock-stretching slave —
the TI app note is explicit about this. This converts the fix-space
analysis: option 2 (hardware kill-switch on Qwiic VCC) is no longer one
option among three; it is the only path that addresses the actual fault
mode. Option 1 (RT scheduling) would only reduce the *probability* of
provoking the hang, not provide recovery. Option 3 (operator workflow)
remains a fallback when option 2 isn't available.

### Open question: is the TCA's stuck-bus recovery firing during our wedges?

The TCA4307 has a `RDY` pin that goes LOW while it's running its own
stuck-bus recovery sequence. We are **not currently observing RDY** —
not wired to a GPIO, not visible in logs. If RDY were going LOW during
our wedges, that would tell us the TCA is detecting SDA-stuck and trying
its 16-pulse sequence (and possibly succeeding for the SDA case while we
still see ENXIO from a different cause). If RDY stays high during a
wedge, the TCA isn't seeing stuck-SDA — supporting the SCL-stuck mode #2
hypothesis. Wiring RDY to a free GPIO and logging its state would
discriminate cleanly. This is diagnostic infrastructure, not a fix.

## Recovery Code Status (already landed, not the subject)

The daemon's behaviour during a wedge is now correct — that's not what we're
debugging. Today's commits on `gsd/phase-28-tpms-integration` already shipped:
- collapsed `OSError`/`Exception` handlers (no more AttributeError-flood-forever)
- dropped `_force_reboot` from the recovery escalation
- give-up backoff (60 s) replaces forced reboot
- TTS announce-once flag (no more Knight Rider voice)
- MISSING reported on hw_state, supervisor will surface it

What's missing is an **actual recovery mechanism** for the wedged-slave fault.

## Three-Option Fix Space (the question to answer)

1. **Real-time priority for `i2c-gpio` kernel thread.** Use `chrt` or
   `isolcpus` boot param to make the bit-bang routine scheduling-immune so
   stress-induced jitter can't deform the waveform. Software-only,
   pre-rally feasible. Reduces probability of slave-state-hang but doesn't
   eliminate it (the fault mode would still exist if jitter ever wins).

2. **Hardware kill-switch on Qwiic VCC.** Inline MOSFET between the Pi's
   3.3 V rail and the Qwiic chain, gate driven by a free GPIO. Daemon can
   hard-power-cycle the slaves. This is the real fix — gives software a
   path to do what only the USB-C unplug currently does. More wiring;
   small physical change. Pre-rally feasible.

3. **Operator-workflow recovery.** Accept that under stress the bus may
   wedge. Leave the daemon's give-up + alert behaviour as-is. Rely on
   driver/co-driver to spot the alert and hard-cycle the Pi. Acceptable
   for fuel stops; painful mid-stage.

The user wants a structured plan: pick the right one (or combination)
based on probability of recurrence in the field, available time before
rally, and risk tolerance.

## Constraints

- Pre-rally must-do timing — limited bench time
- 4 GB Pi 5, NVMe storage, 4-core CPU
- bit-bang i2c on GPIO 2/3 via `dtoverlay=i2c-gpio` (kernel `i2c-gpio` driver
  on platform device `100000002.i2c`); RP1 hardware i2c was disabled earlier
  due to clock-stretch bugs
- TCA4307 already inline on the Qwiic chain, EN now wired to GPIO 12
- Daemon runs as `tgreen` with `SupplementaryGroups=i2c dialout gpio audio`
- /Users/tgreen/Brain/projects/shitbox-rally-2026.md is the canonical
  project doc; open threads and log entries from today document the path

## Current Focus

```yaml
hypothesis: |
  CONFIRMED: SCL-stuck via clock-stretching slave. The fault mode has no
  software recovery path (TI SCPA069 explicit). EN pulse eliminates TCA
  latch as the recovery target. Qwiic VCC kill-switch is the only path
  that gives software what the USB-C unplug does. Fix plan: option 2
  (P-MOSFET or load-switch high-side kill on Qwiic 3V3) combined with
  option 1 (isolcpus probability reduction). Option 3 remains backstop.
test: null
expecting: null
next_action: |
  Implement option 2 hardware kill-switch (free GPIO → P-MOSFET gate →
  Qwiic VCC rail) + option 1 (isolcpus/chrt) then deploy + verify
  stress-ng no longer produces an unrecoverable wedge.
```

## Evidence

- **2026-04-29**: Three independent lockup reproductions within 24 hours.
  stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 200M --timeout 60s reliably
  triggers the wedge in ~60 s on a 4-core Pi 5.
- **2026-04-29**: EN pulse fires cleanly (`pulse_ok=true`, GPIO 12 verified
  via `pinctrl get 12`), followed by `recovered=false` × 3 at both 10 ms
  and 100 ms pulse widths. TCA EN-pulse is not the recovery path for this
  fault mode.
- **2026-04-29**: Kernel `i2c-gpio` unbind/rebind cycles the driver state
  correctly (dmesg: `using lines 571 (SDA) and 572 (SCL)`) but the bus
  stays empty. Kernel driver is not the stuck component.
- **2026-04-29**: `systemctl reboot` fails to recover. Pi 5 PMIC keeps the
  3.3 V rail alive across SoC reset. Confirmed empirically: daemon came back
  up post-reboot, `i2cdetect -y 1` still empty.
- **2026-04-29**: Hard power-cycle (USB-C unplugged ~20 s) recovers fully.
  All 8 devices visible: 0x10 0x19 0x1c 0x3c 0x40 0x5c 0x6a 0x77.
- **TI SCPA069**: Two stuck-bus modes. SDA-stuck is recoverable by the
  TCA4307's own 16-pulse sequence. SCL-stuck (clock-stretching slave) is
  only recoverable by reset or power-cycle of the offending slave. Our
  evidence maps to mode #2: EN pulse doesn't help, only VCC drop recovers.

## Resolution

```yaml
root_cause: |
  SCL stuck low via clock-stretching slave. Under CPU/IO scheduler jitter
  from stress-ng (or rally-equivalent concurrent load: video capture + GPS
  + TPMS decode + DB writes + Prometheus sync), the bit-bang i2c-gpio
  kernel routine mistimes a transaction. One or more slaves on the Qwiic
  chain (LSM6DSOX most likely, possibly others) enter clock-stretching and
  their state machine hangs. TI SCPA069 section 1 is explicit: the only
  recovery is reset or power-cycle of the slave. EN pulse clears TCA latch
  (a different fault mode) and was always the wrong tool for this. The Pi 5
  PMIC keeping 3V3 alive through soft-reboot means there is no software-only
  path to recovery without a dedicated Qwiic VCC kill-switch.

fix: |
  Option 2 (hardware VCC kill-switch) as primary fix + Option 1 (isolcpus)
  as probability reducer. See Fix Plan section below for specifics.
```

## Fix Plan

### Recommendation: Option 2 + Option 1. Option 3 remains backstop.

The fix space has collapsed. EN pulse targets TCA protective isolation
(SDA-stuck mode), which is not what we have. There is no software-only
path to recover a slave whose clock-stretching state machine is hung. The
only thing that works is dropping VCC on the slaves. That means hardware.

**Option 2 is the real fix. Option 1 reduces the probability of needing it.
Option 3 is what we have right now and it's good enough for fuel stops.**

---

### Option 2: Qwiic VCC kill-switch (do this)

**Goal:** give the daemon the ability to drop VCC on the entire Qwiic chain
without pulling the USB-C plug, and bring it back up cleanly.

**Circuit:**

Use a P-channel MOSFET as a high-side switch on the Qwiic 3.3 V line.

```
Pi 3V3 pin ──────┬────── [10 kΩ to gate] ──── MOSFET gate ──── [GPIO N via 470 Ω]
                 │
                 └────── MOSFET source
                                │
                         MOSFET drain ────── Qwiic chain VCC (first device)
                                │
                         [100 nF cap to GND]   (optional, suppresses inrush)
```

P-MOSFET logic:
- Gate HIGH (or floating, pulled to 3V3) = MOSFET off = Qwiic VCC dead
- Gate LOW (GPIO drives low through 470 Ω) = MOSFET on = Qwiic VCC live

The 10 kΩ pull-up to 3V3 ensures Qwiic is off by default if the GPIO
floats (safe-fail: sensors off rather than stuck-on wedged bus).

**Part options** (all SOT-23, available at JayCar / RS Components AU):
- BSS84 (Vishay/Diodes Inc) -- classic, 130 mA, Vgs(th) -0.8V min. Works at 3.3V.
- DMG2301L (Diodes Inc) -- 0.35 A, Vgs(th) -0.4V typ. Better for 3.3V drive.
- SI2301CDS (Vishay) -- 0.76 A, Rds(on) 0.29 Ω at Vgs=-2.5V. Overkill but fine.

Alternatively: a dedicated load switch IC handles all of this with a single
active-high enable pin, no gate resistor calculation needed:
- AP2182W (Diodes Inc, SOT-23-5) -- 1.5 A, active-high, thermal shutdown
- TPS22918 (TI, SOT-23-5) -- 2 A, 11 ms rise time, proper I2C-safe power sequencing

Either works. The discrete P-MOSFET approach uses parts more likely to be
in the junk drawer; the load switch IC is slightly cleaner.

**GPIO choice:** any free BCM GPIO with comfortable header access.
Currently used: 2, 3 (I2C), 4 (1-Wire), 12 (TCA EN), 14, 15 (UART/GPS), 17 (button).
Good candidates: GPIO 5, 6, 13, 16, 19, 20, 21, 22, 23, 24, 25, 26, 27.
Pick whichever has comfortable header spacing on the perma-proto board.
Call it GPIO N in config: `sensors.qwiic_kill_gpio: N`.

**Wire change:** cut the Qwiic 3.3 V wire between the Pi 3V3 pin and the
first Qwiic device (or insert at the terminal block 3V3 pin). Route through
MOSFET source → drain. GND is shared, no change needed.

**Wait time after kill:** bench test suggests 200–500 ms is sufficient.
Hard-cycle test required 20 s but that was discharging the entire Pi 3V3
rail including internal capacitance. The Qwiic chain has minimal bulk
capacitance -- the slaves just need their internal POR (power-on reset)
to fire, which is typically <10 ms per datasheet. Use 500 ms as a
conservative default with a config knob to tune.

**Code change (sampler.py):** extend `_i2c_bus_reset()` with a third
recovery stage after EN-pulse fails:

```python
# After tca_en_pulse_did_not_recover_falling_through:
if self._qwiic_kill_gpio is not None:
    log.warning("qwiic_vcc_kill_starting", pin=self._qwiic_kill_gpio)
    GPIO.output(self._qwiic_kill_gpio, GPIO.HIGH)   # gate high = MOSFET off
    time.sleep(self._qwiic_kill_ms / 1000.0)         # e.g. 500 ms
    GPIO.output(self._qwiic_kill_gpio, GPIO.LOW)    # gate low = MOSFET on
    time.sleep(0.05)  # 50 ms power-on settle
    self.setup()
    recovered = self._lsm6dsox is not None
    log.info("qwiic_vcc_kill_result", recovered=recovered)
    if recovered:
        return True
```

Add `qwiic_kill_gpio: Optional[int] = None` and `qwiic_kill_ms: int = 500`
to `Tca4307Config` (or a new `QwiicConfig`), wire through `EngineConfig`,
and initialise the GPIO in `_setup_tca_en()` (or a new `_setup_qwiic_kill()`).

The recovery ladder then becomes:
1. EN pulse (clears TCA protective isolation if that's the mode)
2. Qwiic VCC kill (clears slave clock-stretch hang -- this is what we need)
3. 9-pulse SCL bit-bang (legacy, SDA-stuck mode, less useful now but harmless)
4. Give-up backoff (nothing worked, operator must intervene)

**Estimated bench time:** 1–2 hours. Physical wiring 20 min; code 30–45 min;
test (stress-ng reproduction + recovery verification) 30 min.

---

### Option 1: `isolcpus` probability reduction (do this too, it's free)

**Goal:** reduce the frequency of bit-bang timing jitter by making the
`i2c-gpio` kernel thread scheduling-immune under load.

The `i2c-gpio` driver creates a platform device that runs I2C transactions
synchronously in the calling context (it doesn't have its own kthread).
Transactions happen in the context of whatever calls `i2c_smbus_*` or
`i2c_transfer`. For us that's the `busio.I2C` in the sampler thread.

The sampler thread already runs in Python userspace. Under stress-ng with
`--cpu 4`, all 4 cores are saturated. The sampler thread gets scheduled
off a core mid-transaction, which is what deforms the bit-bang waveform.

**Fix:**

Set the sampler thread to `SCHED_FIFO` priority 1 (lowest RT priority,
preempts any normal-priority task but not other RT tasks):

```python
import os
import ctypes

def _set_rt_priority(priority: int = 1) -> None:
    """Set SCHED_FIFO on the calling thread. Requires CAP_SYS_NICE."""
    SCHED_FIFO = 1
    class sched_param(ctypes.Structure):
        _fields_ = [("sched_priority", ctypes.c_int)]
    param = sched_param(priority)
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    ret = libc.sched_setscheduler(0, SCHED_FIFO, ctypes.byref(param))
    if ret != 0:
        log.warning("set_rt_priority_failed", errno=ctypes.get_errno())
    else:
        log.info("set_rt_priority_ok", policy="SCHED_FIFO", priority=priority)
```

Call `_set_rt_priority()` at the top of `_sample_loop()`.

The systemd unit needs `AmbientCapabilities=CAP_SYS_NICE` and
`LimitRTPRIO=1` to allow the thread to set its own RT priority.
Or: `sudo setcap cap_sys_nice+ep $(which python3)` on the Pi (cruder).

Alternatively, the blunter approach: `isolcpus=3` in
`/boot/firmware/cmdline.txt` isolates core 3 from the scheduler. Pin the
daemon to core 3 via `taskset -c 3 python3 -m shitbox.events.engine` in
the ExecStart. Core 3 then only runs the daemon's threads; stress-ng can't
saturate it even at `--cpu 4` (Linux still lets stress-ng use it but the
daemon's affinity mask keeps it there without competition).

`isolcpus` is simpler to configure and doesn't require capabilities; the
tradeoff is wasting a core permanently. On a 4-core Pi 5 with modest
baseline load, this is fine.

**Estimated bench time:** 30 min. One cmdline.txt edit, one reboot,
re-run the stress-ng reproduction to verify wedge is harder to trigger.

**Important caveat:** this reduces probability only. A sufficiently hostile
load (or a particularly unlucky clock edge from EMI in the car environment)
can still trigger the hang. Option 1 without Option 2 means you still can't
recover remotely when it happens. Do both.

---

### Option 3: Operator workflow (already in place, keep it)

The daemon already:
- Announces the lockup once via TTS (then suppresses repeats)
- Transitions IMU role to MISSING on hw_state
- Health page shows a red MISSING badge
- Enters 60 s give-up backoff loop

A co-driver who sees the health page can pull the USB-C and replug. That's
acceptable at a fuel stop. It's painful if it happens mid-stage. Options 1+2
together should make mid-stage occurrence rare enough to be not worth worrying about.

---

### Decision

Commit to: **Option 2 (Qwiic VCC kill-switch) + Option 1 (isolcpus). Option 3 retained as backstop.**

Pre-rally feasibility:
- Option 2 hardware: ~1 hr bench time. Parts are a single SOT-23 MOSFET or
  load switch IC. Both available at JayCar (e.g. BSS84 or equivalent on the
  shelf). Wire change is minimal.
- Option 1 software: 30 min. cmdline.txt edit, test.
- Together they make I2C lockups self-healing: fault probability drops
  (option 1) and when one does fire, the daemon recovers without operator
  intervention (option 2). This is what the system should have had from the start.

## Eliminated

- TCA4307 protective-isolation latch as the recovery target. Three EN-pulse
  attempts (10 ms and 100 ms widths) with `pulse_ok=true` each time, all
  followed by `recovered=false`. If the latch were the actual recovery
  target, EN low→high would clear it.
- Kernel `i2c-gpio` driver wedge as the recovery target. Manual unbind/rebind
  of `100000002.i2c` cycles the driver state cleanly (dmesg confirms) but
  the bus stays empty. The kernel driver is fine; something downstream is
  the problem.
- `_force_reboot` (`systemctl reboot`) as a viable recovery action. Pi 5 PMIC
  keeps the 3.3 V rail alive across SoC reset, so the TCA never sees a VCC
  drop. Verified empirically by deliberate `systemctl reboot` in this
  session -- Pi rebooted cleanly, daemon came back up, bus still empty.
- Software-only recovery for the SCL-stuck fault mode. TI SCPA069 is explicit:
  clock-stretching slaves that get the clock stuck low can only be recovered
  by reset or power-cycle of the slave. No amount of clever kernel work or
  GPIO manipulation changes this. EN pulse, bit-bang, unbind/rebind -- none
  of it reaches the slave's VCC.

## Resolution (2026-04-29 afternoon — actual outcome)

**The TCA4307 was installed backwards.** Side 0 (master/IN) was wired to the
slave Qwiic chain, side 1 (slaves/OUT) was wired to the Pi. Tony spotted it
by looking at the silkscreen on the chip after the kill-switch fix-plan
analysis was already in progress.

The TCA4307's hot-insertion protection and stuck-bus recovery are
asymmetric — they are designed to keep side 0 (the controller side) alive
while side 1 (the slave side) is isolated during faults. With the
orientation reversed, the protection ran on the wrong side of the bus:
the master (Pi) was getting the glitches the chip should have absorbed,
and the chip's auto-recovery never engaged on transactions that originated
master-to-slave.

After the flip — three independent stress tests came back clean:

1. **Baseline 60 s stress** (`stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 200M`)
   → no events. Previously this reproduced a wedge in ~60 s.
2. **Active cable unplug + reinsert** → 5 ENXIO bursts → recovery sequence
   fired → EN-pulse path recovered cleanly in 10 s. Auto-recovery worked
   end-to-end. (Previously, recovery from this disturbance also worked in
   one bench test, but lockups in normal use never recovered without hard
   power-cycle.)
3. **Extreme stress 120 s** (`stress-ng --cpu 16 --cpu-method all --io 4
   --vm 4 --switch 4 --timer 4 --cache 2`, ~34 workers on 4 cores) → three
   isolated `EIO` transients spread over 5 minutes, none triggering the
   5-failure threshold, no recovery needed. Sample rate degraded to ~16 Hz
   under brutal load (target 25 Hz, accepts ≥ 10 Hz floor) and recovered
   to 22 Hz post-stress. No throttling. The TCA absorbed the jitter as
   designed.

**The original "scheduler jitter on bit-bang i2c" hypothesis was correct.**
What was wrong was the recovery model — we hypothesised the recovery
mechanism (TCA latch / EN pulse) and built complete fix plans (kernel
unbind/rebind, hardware kill-switch on Qwiic VCC) when the failure was
that the chip's *existing* protection was simply running on the wrong
side. The eliminated hypotheses above (TCA latch as recovery target;
SCL-stuck-via-clock-stretching as the actual fault mode) are still
correct in the *abstract* — those are real failure modes in I2C systems —
but they were not the failure mode we were experiencing.

### What stayed valuable

- **Recovery code rewrite landed regardless** (commit `0d0f2e8`):
  collapsed exception handlers, give-up backoff replaces `_force_reboot`,
  TTS announce-once, MISSING reporting, EN-pulse infrastructure as
  defensive fallback. The daemon under fault is now graceful where it
  used to spin forever logging errors.
- **TCA EN-pin code path** (commits `963c3bf`, `c6e9943`, `8d40e90`) —
  defensive infrastructure, fires on lockups, won't recover an
  unrecoverable fault but will catch SDA-stuck faults the TCA's hardware
  recovery doesn't somehow handle.
- **TI app note** (`scpa069-i2c-stuck-bus.txt`) saved alongside this
  debug session for future reference.
- **The diagnostic discipline** of building the entire fix-space tree
  and the structured `/gsd-debug` session — even when the answer turned
  out to be physical-layer, the analysis covered ground that's worth
  having documented for any future bus issues.

### Lesson

Physical layer first. The TCA had `IN` and `OUT` printed on it. We climbed
the abstraction stack from Python exception handlers through kernel
`i2c-gpio` driver semantics to the TCA datasheet to a TI app note to
hardware kill-switch planning, and the answer was a 30-second cable swap.
This is the dull lesson every engineer already knows; documented here
so future-Tony has it to find.

**Status:** resolved
**Verified:** 3 independent stress tests clean post-flip; bus held under
~34 workers on 4 cores for 120 s
**Files of record:** brain note log entry 2026-04-29 ("TCA4307 was
installed backwards"); commits `675911e` through `c6e9943`/`8d40e90`/
`0d0f2e8`/`072cae3` on `gsd/phase-28-tpms-integration`
