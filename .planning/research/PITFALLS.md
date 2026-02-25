# Domain Pitfalls: Rally Car Telemetry Hardening

**Domain:** Raspberry Pi automotive telemetry — multi-day rally in remote Australia
**Researched:** 2026-02-25
**Scope:** Hardening an existing Python/RPi system for a 4,000 km rally from Port Douglas to Melbourne

---

## Critical Pitfalls

Mistakes that cause data loss, hardware failure, or complete system failure with no recovery path.

---

### Pitfall 1: SD Card Corruption on Ignition-Linked Power Loss

**What goes wrong:** The car's ignition cuts power without warning. The Pi is mid-write to the SD
card — kernel page cache, SQLite WAL checkpoint, or video buffer segment. On next boot, the
filesystem is corrupt, the database is unreadable, and the system fails to start.

**Why it happens:** SD cards have no power-fail protection. The OS buffers writes in RAM (dirty
page cache). A sudden power cut means those buffered writes never reach the card. Even with SQLite
WAL mode, if the OS is killed before the WAL file is flushed, you can lose the WAL entirely. The
database itself survives, but recent commits are gone. Worse: if the WAL and database become
desynchronised (e.g., WAL file partially written), SQLite may refuse to open the database at all.

**Consequences:**
- System fails to boot — telemetry lost for entire day
- Database schema corruption requires manual intervention (impossible in the field)
- Video ring buffer segments partially written — ffmpeg crashes on next start trying to read them
- journald corruption causes systemd to refuse to start services

**Warning signs:**
- `fsck` errors on boot
- SQLite `SQLITE_CORRUPT` or `SQLITE_IOERR` on startup
- ffmpeg refusing to open ring buffer segment files
- Journal reporting read errors on `/dev/mmcblk0`

**Prevention:**
1. Configure SQLite with `synchronous=FULL` and `journal_mode=WAL` together — WAL alone with
   `synchronous=NORMAL` (the default) is NOT durable on power loss. HIGH confidence (SQLite
   official docs).
2. Use `log2ram` to keep systemd journal writes in RAM, flushed periodically — stops journal
   growth hammering the card and reduces corruption surface.
3. Store video ring buffer segments on a separate USB drive (even a cheap thumb drive), not on the
   SD card. If the USB drive corrupts, the database and OS survive.
4. On startup, always validate the database with `PRAGMA integrity_check` before beginning
   operations. Log and alert if corrupt, but fall back gracefully (reinitialise database, start
   fresh, do not crash the daemon).
5. Add a `RestartSec=5` and `Restart=always` in the systemd unit so that if something does go
   wrong on boot, the service retries rather than leaving the car with no telemetry.
6. Consider a capacitor/UPS module (e.g., PiJuice) that provides 30 seconds of power after
   ignition cut — time to flush buffers and shutdown gracefully. This is the gold standard for
   ignition-linked Pi deployments.

**Phase mapping:** Address in the Bulletproof Boot Recovery phase (first hardening milestone).

---

### Pitfall 2: SD Card Wear Exhaustion from Continuous High-Rate Writes

**What goes wrong:** At 100 Hz IMU sampling plus 1 Hz telemetry plus continuous video ring buffer
writes (~15 MB/s to the buffer), a consumer SD card's write endurance is exhausted within the
rally. The card starts producing silent write errors that appear as data corruption, not hard
failures. You lose telemetry data without knowing it.

**Why it happens:** Consumer SD cards (TLC NAND) have 3,000–10,000 write cycles per cell.
The video ring buffer alone writes ~900 MB/hour continuously. Over 10 days at 8 hours/day that is
72 GB of writes — achievable on a small card within endurance limits even without accounting for
WAL checkpoints, logs, and OS activity. Consumer cards also lack power-fail protection circuits
that industrial cards have.

**Consequences:**
- Silent data corruption — events write successfully but read back garbage
- Card fails mid-rally with no spare
- `/var/lib/shitbox/` fills with zero-byte files from failed writes
- SQLite silent data corruption is the worst outcome (not detected until Prometheus shows
  anomalous values)

**Warning signs:**
- `dmesg` showing `mmc0: error -110 transferring data` or `mmcblk0: error` messages
- `SMART` not available on SD cards — no early warning mechanism
- Increasing `SQLITE_IOERR` errors in structured logs
- Video segment files writing at less than expected size

**Prevention:**
1. Store the video ring buffer (`/var/lib/shitbox/video_buffer/`) on a USB drive, not the SD
   card. This is the single biggest write amplification source.
2. Use a high-endurance SD card rated for dashcam/continuous recording use (Samsung Pro
   Endurance, SanDisk Max Endurance). These are TLC with power-fail protection and are rated for
   tens of thousands of hours of continuous video.
3. Enable `log2ram` so system logs are written to RAM and flushed infrequently.
4. Disable swap on the SD card (`dphys-swapfile uninstall`) — swap is the highest-wear single
   source on a default Raspbian install.
5. Monitor card health via periodic `df`, `iostat`, and error log scanning in the health watchdog.
   Alert if write errors appear in dmesg.

**Phase mapping:** Address in Storage Management phase. Immediate action: move video buffer to USB.

---

### Pitfall 3: Automotive Power Supply Voltage Spikes Killing the Pi

**What goes wrong:** A 2001 Ford Laser produces voltage transients on the 12V rail every time the
alternator load changes (high-beam headlights, fan, starter motor). Load dump events — where the
battery disconnects while the alternator is running (e.g., loose battery terminal on rough roads)
— can spike to 60–120V for up to 400 ms. A cheap buck converter with no transient suppression
passes these spikes directly to the Pi's 5V rail, frying the SoC or corrupting flash.

**Why it happens:** Automotive 12V is the most hostile power environment for electronics. The
nominal 12V is actually 10–15V depending on charge state, and transients from inductive loads
(fan motors, fuel pumps) are commonplace. A 2001 Laser has no protection for accessories beyond
a fuse. Rough roads loosen battery terminals, increasing the chance of a load dump event.

**Consequences:**
- Pi SoC destroyed — total system loss with no spare
- SD card controller damaged — data unrecoverable
- USB devices (GPS receiver, webcam) damaged
- Intermittent resets that look like software crashes but are actually brownouts

**Warning signs:**
- Pi rebooting unexpectedly on acceleration or when headlights are switched on
- INA219 power monitor showing voltage dropping below 4.8V on the 5V rail
- `under-voltage detected` in dmesg / Pi throttling flags set (`vcgencmd get_throttled` returning
  non-zero)

**Prevention:**
1. Use an automotive-grade DC-DC converter with built-in transient suppression — not a generic
   USB car charger. The Victron Orion-Tr or Pololu automotive-grade regulators are designed for
   this. Budget option: add a TVS diode array on the input side of any converter.
2. Add a 100µF electrolytic capacitor across the 5V rail close to the Pi as a local reservoir.
3. Wire the Pi power from a fused, dedicated circuit — not from the cigarette lighter socket
   (which shares a circuit with many other loads).
4. Monitor the 5V rail voltage via the INA219 and log brownout events. If voltage drops below
   4.75V, the Pi will corrupt writes — treat this as a critical alert.
5. Check `vcgencmd get_throttled` in the health watchdog — a non-zero result means the Pi has
   seen under-voltage. Log this as a warning to prompt investigation of the power supply.

**Phase mapping:** Hardware concern, but add software monitoring (INA219 voltage threshold alerts)
in the Thermal Resilience / Health Monitoring phase.

---

### Pitfall 4: Thermal Throttling Causing IMU Sample Stalls

**What goes wrong:** The cabin of a 2001 Ford Laser with no air conditioning in Australian summer
reaches 50–60°C ambient. The Pi's CPU temperature reaches 80–90°C under load. At 80°C, the Pi
begins soft-throttling (frequency reduction). At 85°C, it hard-throttles. The 100 Hz IMU sampler
loop, which is timing-sensitive, starts missing samples because the CPU cannot complete each
iteration in 10 ms. The health watchdog detects a stalled sampler and restarts it — but the
restart itself takes time, and during restart, no events are detected.

**Why it happens:** Australian summer cabin temperatures in a car with no AC easily exceed 50°C.
With 5–10°C of self-heating from the Pi under load (100 Hz polling is CPU-intensive), the CPU
temperature reaches the throttle threshold. Throttling is not a uniform slowdown — it causes
jitter in the sampler loop timing, which accumulates as missed samples and timestamp drift.

**Consequences:**
- Event detection gaps during the hottest part of the day
- Missed hard braking events on corrugated dirt roads (exactly when you want them most)
- IMU timestamp drift corrupts telemetry time alignment in Prometheus
- Sampler restart causes a 30-second gap in the ring buffer (pre-event context is lost)

**Warning signs:**
- `vcgencmd get_throttled` returning `0x50005` (under-voltage + throttling)
- CPU temperature readings exceeding 75°C in structured logs
- Health watchdog logging `stalled_sampler` events
- Irregular gaps in IMU data visible in Prometheus/Grafana

**Prevention:**
1. Mount the Pi with a heatsink on the SoC (passive cooling). In a closed box, add a small
   5V fan controlled by GPIO based on temperature — even moving the air reduces temperature by
   15–20°C.
2. Configure the health watchdog to log thermal state (`vcgencmd measure_temp` and
   `vcgencmd get_throttled`) at every health check interval, not just on warnings.
3. Use `cpufreq-set` or the Pi's `force_turbo=0` setting to disable automatic frequency scaling —
   prefer consistent lower frequency over burst-and-throttle behaviour for the sampler thread.
4. If the enclosure is in the passenger footwell or boot (better than the dashboard), temperatures
   are significantly lower — physical placement matters as much as software.
5. Mount the Pi vertically if possible — convection cooling works better with vertical boards.

**Phase mapping:** Thermal Resilience phase. Monitor in software; physical mitigation is hardware
concern but must be logged.

---

### Pitfall 5: GPS Cold Start Blocking System Readiness at Each Stage Start

**What goes wrong:** Each morning the car starts in a new town. The Pi boots, the systemd service
starts, and `_wait_for_gps_fix()` blocks for up to 20 seconds waiting for GPS. If the GPS is
still acquiring satellites (cold start after overnight power-off can take 30–60 seconds without
assisted GPS in a remote area), the engine blocks longer than expected, systemd's
`sd_notify(READY=1)` is delayed, and the watchdog may decide the service has failed to start.

In remote Australia, there is no mobile data for assisted GPS (A-GPS). Cold start time to first
fix without A-GPS is 30–90 seconds. If the car is parked under a tree or inside a building
overnight, the GPS has no sky view until it moves.

**Why it happens:** The existing code blocks startup on GPS fix for up to 20 seconds but the
GPS cold start time exceeds this. `_wait_for_gps_fix()` is synchronous during `start()`, which
means if GPS is slow, the entire engine startup blocks, systemd readiness is delayed, and the
watchdog timeout may fire.

**Consequences:**
- System reports unhealthy on startup every morning — creates false alert noise
- Boot events have no GPS coordinates (acceptable) but also block telemetry collection starting
- If systemd watchdog fires, the service is killed and restarted — adding another 20-second delay
  per restart cycle
- Cascading: GPS fix delay → watchdog fires → restart → GPS fix delay → infinite loop

**Warning signs:**
- `journalctl` showing `watchdog_timeout` events on morning starts
- OLED display showing `NO GPS` for minutes after startup
- Boot events consistently missing GPS metadata

**Prevention:**
1. Make GPS fix acquisition asynchronous — fire off a background task on startup and proceed
   immediately. Do not block `start()` on GPS. Report `READY=1` to systemd as soon as the daemon
   is running, not when GPS is fixed.
2. Set systemd watchdog timeout generously (120 seconds) to account for GPS cold start.
3. Use `fake-hwclock` (already in use) to ensure the system clock is reasonable before GPS sync,
   preventing timestamp anomalies during GPS acquisition.
4. Log a structured event when GPS fix is acquired with the time-to-fix so you can diagnose
   acquisition delays over the rally.
5. For the USB GPS, configure `gpsd` with `-n` (no-wait) and ensure udev rules create a stable
   symlink (`/dev/gps0` → `/dev/serial/by-id/...`) so the device path does not change between
   reboots or if the GPS is disconnected and reconnected.

**Phase mapping:** Bulletproof Boot Recovery phase.

---

## Moderate Pitfalls

Mistakes that degrade reliability or cause data loss in specific scenarios but do not destroy the
system.

---

### Pitfall 6: I2C Bus Lockup Taking Down All Sensors

**What goes wrong:** A vibration jolt causes a momentary glitch on the I2C bus while the MPU6050
is mid-transaction. The device holds SDA low (I2C "stuck bus" condition). The Linux I2C driver
returns `EREMOTEIO` for every subsequent read. All sensors on bus 1 (MPU6050, BME680, INA219,
MCP9808, SSD1306) become unresponsive. The health watchdog detects a stalled sampler and attempts
restart, but the restart fails because the I2C bus itself is locked.

**Why it happens:** I2C bus lockup is a known hardware limitation of the I2C protocol. A clock
glitch or power brownout mid-transfer leaves a slave device driving SDA low. The master cannot
recover without bit-banging 9 clock pulses to reset the slave's state machine. The Linux I2C
driver does not do this automatically on Raspberry Pi — it requires either a kernel module reset
or a power cycle.

**Consequences:**
- No IMU data until reboot — no event detection for remainder of day
- All I2C sensors offline simultaneously (one bus, multiple devices)
- OLED display goes blank (also on I2C bus)
- Health watchdog correctly detects failure but cannot self-heal

**Warning signs:**
- `dmesg` showing `i2c i2c-1: sendbytes: error -121` or similar
- `smbus2` raising `OSError: [Errno 121] Remote I/O error`
- Health watchdog logging consecutive sampler stall events
- OLED display going blank mid-journey

**Prevention:**
1. Add an I2C bus reset routine to the health watchdog: if the sampler stalls and I2C reads fail,
   attempt recovery by toggling the SCL pin 9 times via GPIO bit-banging (`pigpio` or direct GPIO
   sysfs) before declaring failure.
2. Use short, shielded I2C cables (< 30 cm) between the Pi and sensor breakout boards. Long
   cables are more susceptible to vibration-induced glitches.
3. Add I2C pull-up resistors (4.7kΩ) externally rather than relying on the Pi's internal weak
   pull-ups — stronger pull-ups make the bus more resistant to noise.
4. Reduce I2C bus speed from 400 kHz to 100 kHz (`dtparam=i2c_arm=on,i2c_arm_baudrate=100000`
   in `/boot/config.txt`) — lower speed is more tolerant of marginal signal quality.
5. As a fallback: have the health watchdog trigger a `systemctl restart shitbox-telemetry` if I2C
   errors persist for > 60 seconds — the service restart re-initialises the I2C bus driver.

**Phase mapping:** Watchdog and Self-Healing phase.

---

### Pitfall 7: USB GPS Device Path Changing After Reconnect

**What goes wrong:** The USB GPS is connected via a cable in a vibrating car. The connector works
loose briefly, the device disconnects and reconnects. Linux assigns it `/dev/ttyUSB1` instead of
`/dev/ttyUSB0`. gpsd, configured with the original path, cannot see the device. GPS telemetry
goes silent. The system runs for hours with no GPS coordinates — events are recorded without
location.

**Why it happens:** USB device enumeration order is not guaranteed after hot-plug events. The
device path (`/dev/ttyUSB0`) is not stable. gpsd requires a stable device path unless configured
with udev hotplug rules.

**Consequences:**
- Events recorded without GPS coordinates for the rest of the day
- No location data on the public website (significant for engagement)
- Speed readings unavailable — event metadata incomplete

**Warning signs:**
- `gpsd` logging `no devices attached`
- `dmesg` showing USB disconnect/reconnect events on the ttyUSB device
- GPS state in engine showing `_gps_available = False` for extended period

**Prevention:**
1. Create a udev rule that creates a stable symlink `/dev/gps0` based on USB serial ID:
   ```
   SUBSYSTEM=="tty", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="XXXX",
   SYMLINK+="gps0", RUN+="/bin/systemctl restart gpsd"
   ```
   Configure gpsd to use `/dev/gps0` instead of `/dev/ttyUSB0`.
2. The udev rule's `RUN` trigger restarts gpsd automatically after reconnect — no manual
   intervention required.
3. Physically secure the GPS USB cable with a zip tie or cable clamp so vibration cannot work
   it loose. This is the simplest fix.
4. Log GPS reconnect events in the engine so you can identify how often this happens.

**Phase mapping:** Bulletproof Boot Recovery phase (udev rules). Hardware fix is immediate.

---

### Pitfall 8: ffmpeg Process Silently Dying, Video Buffer Reporting Running

**What goes wrong:** The video ring buffer runs ffmpeg as a long-lived subprocess. ffmpeg crashes
(SIGSEGV, OOM, codec error on a corrupted segment) and exits. The Python wrapper checks
`is_running` via `self._process is not None`, which returns `True` even after the process exits
because `_process` is not cleared on unexpected death. The health watchdog detects the ffmpeg
process is "running" but video buffer segments stop being written. Events trigger video saves, but
the save fails silently because there is no running ffmpeg to provide the buffer.

**Why it happens:** The existing code uses `_process.poll()` only in limited places. The
`is_running` property (noted in CONCERNS.md) does not check `poll()` return value. ffmpeg can die
for many reasons in an automotive environment: write error to SD card, codec assertion on a
corrupt segment from a previous power cut, signal from OOM killer.

**Consequences:**
- All events after the ffmpeg crash have no video
- Silent failure — no alerts until the health watchdog notices the stall
- Partial video segments on disk are not cleaned up, accumulating corrupt files

**Warning signs:**
- Health watchdog logging `video_ring_buffer_not_running` but the service was supposedly running
- `dmesg` showing OOM kills or `ffmpeg` in kill list
- Video buffer segment files not updating (timestamp not advancing)
- Events saving with `video_path: null` continuously

**Prevention:**
1. Fix `is_running` to always call `self._process.poll()` and return `False` if the process has
   exited. Log the exit code as a structured warning event.
2. Add a dedicated video buffer health check in the watchdog that reads the modification time of
   the latest segment file. If the segment has not been updated in > 30 seconds, the buffer is
   dead regardless of what `is_running` reports.
3. On detection of dead ffmpeg, attempt restart automatically (not just log). The health watchdog
   already has restart logic for the telemetry thread — extend this to the video ring buffer.
4. Clean up partial segment files on ffmpeg restart so corrupt segments do not accumulate.

**Phase mapping:** Watchdog and Self-Healing phase. Fix `is_running` immediately as a bug fix.

---

### Pitfall 9: Storage Exhaustion Silently Stopping Event Writes

**What goes wrong:** The captures directory fills up over multiple days of event recording and
video storage. SQLite write errors are logged but the daemon continues running. New events are
detected but cannot be saved (write fails). The system appears healthy from the OLED display but
telemetry data is silently lost.

**Why it happens:** The existing health watchdog checks disk space but the threshold of 95% may
be too late — video files at 15–50 MB each can fill the last 5% quickly. More importantly, the
disk-full condition does not trigger an emergency cleanup of old data; it only logs a warning and
eventually shuts down when truly critical.

At 10 events/hour with video (~50 MB each) over 8 hours of driving for 10 days, that is 4,000
events × 50 MB = 200 GB of video — vastly more than a 64 GB SD card. The current system relies
on CaptureSyncService to rsync to NAS and then clean up, but this only works when connected.

**Consequences:**
- Events lost silently during storage exhaustion
- Database WAL grows unbounded if checkpoint cannot write (disk full causes WAL checkpoint
  failure, which causes the WAL to grow, which fills disk faster)
- NAS sync fails on next connection (rsync aborts on disk-full conditions at source)

**Warning signs:**
- `df -h` showing > 80% on `/var/lib/shitbox/`
- `SQLITE_FULL` errors in structured logs
- Video files not appearing after events
- CaptureSyncService reporting sync failures

**Prevention:**
1. Implement aggressive proactive cleanup: when disk usage > 70%, start deleting the oldest
   synced video files (not the database). Delete synced files first, unsynced last.
2. Track per-file sync status — CaptureSyncService should mark files as synced in the database
   after successful rsync. Only delete marked files during cleanup.
3. Implement a configurable video retention policy: keep videos for last N days or until disk is
   X% full, delete oldest first.
4. Lower the warning threshold to 70% and critical to 85% — at 95% you have no headroom. Add an
   alert on the OLED display when disk is above warning threshold.
5. Consider splitting the SD card partition: a small root partition (16 GB) and a larger data
   partition, so root filesystem corruption from a full data partition is prevented.

**Phase mapping:** Storage Management phase.

---

### Pitfall 10: WireGuard Tunnel Stale After Long Connectivity Gap

**What goes wrong:** The car drives through 400 km of outback with no mobile signal (not
uncommon on the Nullarbor). WireGuard's UDP tunnel expires. When mobile signal returns, the IP
address changes (mobile carrier reassigns). WireGuard does not automatically re-handshake without
`PersistentKeepalive` configured. The connectivity check (`connection.is_connected`) continues to
report `False` because the TCP socket to the Prometheus host times out, but WireGuard's interface
is up — confusing the diagnosis. The batch sync backlog grows to thousands of readings.

**Why it happens:** WireGuard is a stateless protocol — it does not maintain a connection. After
a long gap with no traffic, the peer's endpoint (IP:port) may change when mobile data reconnects.
Without `PersistentKeepalive`, WireGuard on the Pi does not re-initiate the handshake.

**Consequences:**
- Prometheus sync backlog grows unbounded during multi-day connectivity gaps
- When sync resumes, it attempts to push thousands of readings — may overwhelm Prometheus or
  hit rate limits
- rsync also fails until WireGuard is re-established

**Warning signs:**
- `wg show` reporting last handshake was > 3 minutes ago
- `ping` to WireGuard peer failing while `ip link show wg0` shows interface up
- Connectivity check consistently returning `False` after entering signal coverage

**Prevention:**
1. Set `PersistentKeepalive = 25` in the WireGuard peer config on the Pi. This sends a keepalive
   every 25 seconds, keeping NAT mappings alive and triggering re-handshake when signal returns.
   This is low-bandwidth (one UDP packet per 25 seconds) and has no meaningful data cost. HIGH
   confidence (WireGuard documentation).
2. Add a WireGuard health check to the connectivity monitor: if `is_connected` has been `False`
   for > 5 minutes, run `wg show` to check handshake recency and optionally trigger
   `wg set wg0 peer ... endpoint <current_endpoint>` to force re-handshake.
3. Cap the Prometheus sync batch size aggressively — never send more than 2,000 readings per
   batch. With a 15-second batch interval, catching up from a 24-hour gap takes ~24 minutes of
   connected time. This is acceptable.

**Phase mapping:** Remote Health Monitoring phase.

---

### Pitfall 11: Clock Drift Corrupting Telemetry Timestamps

**What goes wrong:** The Pi has no real-time clock (RTC). On boot without GPS, it reads time from
`fake-hwclock` (last saved time). If the Pi has been off for 12+ hours, `fake-hwclock` may be
hours behind. GPS sync corrects this, but only after GPS fix. Between boot and GPS fix, all
telemetry readings go to SQLite with wrong timestamps. When Prometheus batch sync runs, these
readings arrive out of order. Prometheus rejects out-of-order samples by default (samples must
arrive in increasing timestamp order per series).

The Pi's crystal oscillator drifts ~2 seconds/day without NTP or GPS sync. Over a 10-day rally,
that is 20 seconds of drift — enough to misalign video timestamps with telemetry events.

**Why it happens:** The existing GPS clock sync (`_sync_clock_from_gps`) runs once on first GPS
fix and then hourly via `fake-hwclock`. But if GPS fix takes 60 seconds and telemetry starts
immediately, those first 60 seconds of readings have wrong timestamps that Prometheus will reject.

**Consequences:**
- Prometheus rejects out-of-order telemetry — readings are silently lost
- Video timestamps and telemetry timestamps drift apart, making event correlation difficult
- On the public website, events appear at wrong times

**Warning signs:**
- Prometheus ingestion errors in batch sync logs
- Events appearing at unexpected times in Grafana
- GPS clock sync logging large time corrections (> 30 seconds)

**Prevention:**
1. On startup, before writing any telemetry to the database, wait for GPS fix OR a configurable
   timeout (60 seconds). Tag all pre-GPS-fix readings with a `time_source: fake_hwclock` label
   in the metadata. Prometheus can filter these out.
2. Save `fake-hwclock` more frequently — every 10 minutes instead of the default hourly — to
   reduce boot-time clock error.
3. Log all clock sync events with the before/after delta so you can identify systematic drift.
4. Consider adding a cheap DS3231 RTC module (I2C, ~$3) — a hardware RTC provides accurate time
   from boot without requiring GPS fix. This eliminates the entire class of boot-time clock
   errors.

**Phase mapping:** Bulletproof Boot Recovery phase.

---

## Minor Pitfalls

Mistakes that are annoying or reduce data quality but do not cause system failure.

---

### Pitfall 12: GPS Satellite Workaround Socket Leaks Accumulating

**What goes wrong:** The `_get_satellite_count()` method opens a raw socket to gpsd on every GPS
read (1 Hz). The socket has exception handling, but if `sock.close()` fails inside the `finally`
block (which itself can raise), the socket leaks. Over hours of operation, open file descriptors
accumulate. Linux's default `ulimit` for file descriptors is 1,024. After ~1,000 hours the daemon
runs out of file descriptors and crashes.

At 1 Hz for 10 days (80 hours of driving), that is 288,000 socket open/close cycles. If 0.1%
leak, that is 288 leaked sockets — not immediately fatal but a ticking clock.

**Prevention:**
1. Convert `_get_satellite_count()` to use a persistent socket or a context manager. Open the
   socket once in `__init__`, reuse it, and only reconnect on error.
2. Alternatively, fix the gpsd-py3 bug by switching to `pynmea2` or direct NMEA parsing from
   `/dev/gps0` — eliminates the workaround entirely.
3. Monitor open file descriptor count in the health watchdog (`/proc/<pid>/fd/` count).

**Phase mapping:** Watchdog and Self-Healing phase (monitoring). Fix the socket leak as a bug fix
in Boot Recovery phase.

---

### Pitfall 13: Reverse Geocoder Blocking the Telemetry Thread

**What goes wrong:** `reverse_geocoder` resolves GPS coordinates to a place name. This library
loads a large in-memory dataset on first use and performs a kdtree lookup. The lookup is normally
fast (< 10 ms) but the first call triggers a CSV file load (~200 ms). If this happens during
active driving, the telemetry loop stalls for 200 ms, causing a 200 ms gap in 1 Hz telemetry.
In an extreme case (long overnight with the Pi powered off), the lookup file may not be in the
OS page cache, causing a disk read.

**Prevention:**
1. Pre-warm `reverse_geocoder` during startup (before the telemetry loop starts) by calling it
   once with the last known GPS position from `fake-hwclock` state.
2. Ensure geocoding runs in a background thread with a timeout, not inline in the telemetry loop.

**Phase mapping:** Minor — note for Boot Recovery phase.

---

### Pitfall 14: Event `id()` Keys Causing Silent Video Link Failures

**What goes wrong:** `_pending_post_capture` uses `id(event)` as the dict key. Python recycles
memory addresses — a garbage-collected event object's `id()` may be reused by a new event object.
If the video callback fires for the old event but looks up by the same `id()`, it finds the new
event and writes the video path to the wrong event. Or the old event has been deleted from the
dict and the video path is dropped entirely.

This is most likely during rough road sections where many ROUGH_ROAD events fire in rapid
succession — exactly the conditions of the Shitbox Rally.

**Prevention:**
1. Replace `id(event)` with a UUID generated at event detection time.
2. Alternatively, use `event.start_time` + `event.event_type` as a composite key — this is
   unique per event and stable across the event lifecycle.

**Phase mapping:** Bug fix — can be addressed in any phase, but prioritise before the rally.

---

### Pitfall 15: Log Volume Growing Without Bound on Rough Road Sections

**What goes wrong:** On corrugated dirt roads, ROUGH_ROAD events fire at high frequency. Each
event writes structured log entries at INFO level: event detected, samples collected, JSON saved,
video triggered, video completed. At 10 events/minute, that is several hundred log lines/minute.
`journald` compresses and rotates, but aggressive logging also causes the telemetry thread to
spend CPU time in log formatting — impacting the 100 Hz sampler.

**Prevention:**
1. Set ROUGH_ROAD events to log at DEBUG level rather than INFO, or implement event-type-specific
   log levels. INFO-level log only the first event in a burst, then switch to DEBUG for subsequent
   events within a 60-second window.
2. Configure `journald` with `SystemMaxUse=200M` and `SystemMaxFileSize=20M` in
   `/etc/systemd/journald.conf` to cap log disk usage.

**Phase mapping:** Minor — note during Watchdog and Self-Healing phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Bulletproof Boot Recovery | GPS blocking startup; clock wrong before GPS fix; database corruption check | Async GPS, integrity\_check on startup, RTC module |
| Watchdog and Self-Healing | ffmpeg zombie not detected; I2C bus lockup unrecoverable; `is_running` lying | Fix `is_running`, add I2C reset routine, file-mtime health check for video buffer |
| Thermal Resilience | CPU throttle causing sampler stalls; no passive cooling in enclosure | Heat sink + fan, log throttle state in health check, monitor `vcgencmd get_throttled` |
| Storage Management | Disk fills before NAS sync opportunity; cleanup deletes unsynced files | Track sync status per file in DB, proactive cleanup at 70%, video buffer to USB |
| Remote Health Monitoring | WireGuard tunnel stale after days without signal; clock drift | `PersistentKeepalive=25`, frequent `fake-hwclock` saves |
| Power Supply | Voltage spikes killing Pi; brownout causing write corruption | Automotive-grade DC-DC converter, INA219 voltage monitoring, brownout logging |

---

## Confidence Assessment

| Area | Confidence | Sources |
|------|------------|---------|
| SD card corruption on power loss | HIGH | SQLite official docs, multiple Raspberry Pi Forum case studies |
| SD card wear exhaustion | HIGH | Community measurement data, dashcam card endurance ratings |
| Automotive voltage spikes | HIGH | Analog Devices, Littelfuse, EEVBlog automotive power discussions |
| Thermal throttling thresholds | HIGH | Raspberry Pi official docs (80°C soft limit confirmed) |
| GPS cold start without A-GPS | MEDIUM | GPS vendor documentation, community reports from remote areas |
| I2C bus lockup | HIGH | Raspberry Pi Forums, Linux kernel I2C driver behaviour |
| USB device path instability | HIGH | gpsd GitLab issue tracker, udev documentation |
| ffmpeg zombie process | MEDIUM | GitHub issues across multiple Python-ffmpeg libraries |
| WireGuard reconnection | HIGH | WireGuard official documentation on PersistentKeepalive |
| Clock drift without NTP | HIGH | RPi community measurements (~2 s/day), NTP documentation |

---

## Sources

- [SQLite WAL Mode — Official Documentation](https://sqlite.org/wal.html)
- [SQLite Durability Settings analysis](https://www.agwa.name/blog/post/sqlite_durability)
- [SD Card Power Failure Resilience — Raspberry Pi Forums](https://forums.raspberrypi.com/viewtopic.php?t=253104)
- [Running a Raspberry Pi with a Read-Only Root Filesystem (2024)](https://www.dzombak.com/blog/2024/03/running-a-raspberry-pi-with-a-read-only-root-filesystem/)
- [Pi Reliability: Reduce Writes to SD Card (2024)](https://www.dzombak.com/blog/2024/04/pi-reliability-reduce-writes-to-your-sd-card/)
- [Raspberry Pi Temperature and Throttling — Sunfounder Guide](https://www.sunfounder.com/blogs/news/raspberry-pi-temperature-guide-how-to-check-throttling-limits-cooling-tips)
- [Automotive 12V Load Dump Protection — Analog Devices](https://www.analog.com/en/resources/technical-articles/loaddump-protection-for-24v-automotive-applications.html)
- [TVS Diodes for Automotive Load Dump — Littelfuse](https://www.littelfuse.com/assetdocs/littelfuse-tvs-diode-meet-automotive-load-dump-standard-application-note?assetguid=a53ad6b0-87f7-4ca3-a783-55133fc020dc)
- [Raspberry Pi Automotive Power Supply — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=352266)
- [Automatic Recovery from I2C Stuck Bus — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=326603)
- [I2C Bus Lockup Recovery — Spell Foundry](https://spellfoundry.com/2020/06/25/reliable-embedded-systems-recovering-arduino-i2c-bus-lock-ups/)
- [gpsd fails to reconnect after USB unplug — gpsd GitLab Issue #60](https://gitlab.com/gpsd/gpsd/-/issues/60)
- [GPS Tracking Challenges in Remote Australia — Locate2u](https://www.locate2u.com/gps-tracking/gps-tracking-challenges-in-regional-and-remote-australia/)
- [WireGuard PersistentKeepalive Explained](https://www.oreateai.com/blog/understanding-persistentkeepalive-in-wireguard-keeping-your-vpn-connection-alive/abf0b8aa7afab6c76a9910986dce8dcd)
- [Raspberry Pi Clock Drift Without NTP — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=337797)
- [ffmpeg Zombie Process Issues — moviepy GitHub Issue #833](https://github.com/Zulko/moviepy/issues/833)
- [microSD Endurance and Monitoring — RPi Forums](https://forums.raspberrypi.com/viewtopic.php?t=317568)

---

*Research completed: 2026-02-25*
