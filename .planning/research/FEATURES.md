# Feature Landscape

**Domain:** Hardened automotive telemetry — multi-day rally across remote Australia
**Researched:** 2026-02-25
**Milestone context:** Rally-readiness hardening of an existing telemetry system

---

## Framing

The Shitbox Rally runs ~4,000 km from Far North Queensland to Melbourne over eight or more days.
It traverses outback stations, gravel roads, and remote communities with no mobile coverage for hours
at a time. The car is a 2001 Ford Laser with no OBD-II. The Pi system is powered directly off 12V
with ignition-switched supply, meaning it sees dozens of hard power cuts per day (ignition off at
fuel stops, camp sites, checkpoints). "Multi-day" here means 8 consecutive driving days, not a
single stage race.

This framing changes the feature calculus significantly. Systems that would be "nice to have" for a
weekend event become mandatory for 4,000 km of continuous operation.

---

## Table Stakes

Features the system must have or it fails during the rally. Missing any of these risks data loss,
system failure with no recovery path, or the system becoming a hazard to the crew.

| Feature | Why Table Stakes | Complexity | Already Exists? |
|---------|-----------------|------------|----------------|
| Bulletproof boot after hard power cut | Ignition cycling 20+ times/day; filesystem corruption kills the event | Low–Med | Partial — WAL mode exists, boot capture exists, but no boot-state recovery audit |
| Hardware watchdog (BCM2835 /dev/watchdog) | Software-only health check cannot recover a fully hung kernel; hardware watchdog reboots it | Low | No — systemd health checks exist, not hardware watchdog |
| Automatic service restart on any crash | Crash during driving means no data until someone notices | Low | Partial — systemd `Restart=always` likely needed audit |
| Disk space management with safe eviction | SD card fills in <2 days at current write rate; existing check only warns and shuts down | Med | Partial — disk check exists, eviction strategy incomplete |
| SQLite WAL checkpoint management | WAL grows unbounded; at 100+ readings/sec fills 500 MB in ~1.4 hours | Med | No — autocheckpoint tuning and background checkpoint not implemented |
| Read-only filesystem mount for OS partition | Prevents SD card corruption on hard power cut to OS partition | Med | No |
| GPS-based time sync on every boot | No RTC on Pi; clock will be wrong without GPS sync; timestamps wrong on all data | Low | Yes — implemented |
| Structured boot event capture | Need to know when system came up and went down to align telemetry across days | Low | Yes — BOOT event captured |
| Storage rotation for captured video | Videos are never deleted; SD card exhaustion guaranteed on multi-day rally | Med | Partial — disk threshold triggers warning but no proactive deletion |
| ffmpeg process monitoring and recovery | ffmpeg crash silently stops recording; no detection currently | Low–Med | No — flagged in CONCERNS.md as fragile area |
| Graceful shutdown on detected power loss | Reduces filesystem corruption risk; GPIO line from power supply can signal imminent cutoff | Med | No — no power loss signal wiring or handler |
| Connectivity-resilient sync (already exists) | Prometheus batch sync must handle days without any signal | Low | Yes — cursor-based batch sync implemented |

---

## Differentiators

Features that add value beyond data capture — primarily for driver awareness and public engagement.
Not required for the system to function but meaningfully improve the experience.

| Feature | Value Proposition | Complexity | Dependencies |
|---------|-------------------|------------|--------------|
| Driver dashboard on 7" touchscreen | Speed, heading, trip distance, system health at a glance; driver awareness without phone | High | GPS collector, display service, tkinter or pygame |
| Rally stage/day progress tracking | Distance covered today, cumulative total, estimated progress to destination | Med | GPS track accumulator, route waypoint data |
| Thermal resilience monitoring and alerts | Australian summer cabin temps exceed 50°C; Pi throttles at 80°C; need early warning and graceful degradation | Med | Existing CPU temp metric, new threshold alerts |
| Remote health reporting via Prometheus | When connectivity is available, push a health summary (CPU temp, disk %, battery V, sync backlog) so crew can monitor from home | Low–Med | Existing batch sync, new health metrics readings |
| Live website updates with position | When connected, push current GPS coordinates so followers can see route progress on the map | Med | GPS collector, new sync endpoint or events.json update |
| Donor engagement stats on website | Events triggered, km covered, days into rally — gives followers something to follow beyond just event videos | Med | Route tracking, event counts, website update |
| In-car audio alert on system fault | Piezo buzzer already wired; beep pattern on watchdog failure or critical fault | Low | Existing buzzer GPIO; currently only beeps on 2 consecutive health failures |
| Configuration hot-reload via SIGHUP | Tune detection thresholds from laptop via SSH without restarting (losing data in flight) | Low–Med | New signal handler in engine |
| Persistent event queue for failed captures | Events and videos that fail to upload are retried on next connectivity rather than lost | Med | SQLite, new pending_sync state |
| OLED display showing current mode/health | Already exists — ensure it degrades gracefully (turn off if display fails) | Low | Existing OLEDDisplayService |

---

## Anti-Features

Things to explicitly NOT build for this milestone. Each has a clear reason.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time video streaming | Connectivity too sparse for reliable streaming; waste of mobile data | Batch rsync video to NAS when connected |
| OBD-II / ECU integration | 2001 Ford Laser is OBD-I; no practical interface | Not applicable to this vehicle |
| Mobile app | Adds cross-platform build complexity for no benefit; driver can't use phone while driving | Web-based display on Pi touchscreen is sufficient |
| G-force live display for driver | Driver does not need live accelerometer readout; it is a distraction | Event detection handles this autonomously |
| Full filesystem read-only (overlay rootfs) | Complex to set up; risks breaking Python venv and config writes; overkill for this timeline | Read-only OS partition only; data partition stays writable |
| Multi-vehicle tracking | Single car event; tracking infra is the rally organiser's job | Focus on single-vehicle reliability |
| AI/ML event classification | Existing threshold-based detection is well-suited to this hardware; ML adds weight and complexity | Tune existing thresholds if needed |
| Cloud video transcoding | Adds latency and cost; NAS rsync is sufficient | rsync to NAS; website serves direct MP4 |
| Automatic over-the-air updates | High risk during rally; a bad update bricks the car mid-trip | Disable auto-update; update only at camp sites via SSH |
| MQTT re-enable | MQTT causes duplicate metrics with Prometheus; currently correctly disabled | Leave disabled |
| Per-session lap timing | Not a lap-based event; no stages in the motorsport sense | Trip odometer is sufficient |

---

## Feature Dependencies

```
Hardware watchdog (BCM2835)
  └─ Requires: dtparam=watchdog=on in /boot/config.txt + RuntimeWatchdogSec in systemd.conf

Disk space management (proactive eviction)
  └─ Requires: Priority ordering for deletion (oldest video first, then old DB rows)
  └─ Blocks: Storage rotation for captured video

SQLite WAL checkpoint management
  └─ Requires: Background checkpoint thread or autocheckpoint tuning
  └─ Blocks: Long-term multi-day data integrity

Read-only OS filesystem
  └─ Requires: overlayfs or ro mount configuration in /boot/cmdline.txt
  └─ Requires: Data partition (SQLite, captures) must remain on writable partition
  └─ Blocks: Bulletproof boot after hard power cut

Driver dashboard (7" touchscreen)
  └─ Requires: GPS collector (position, speed, heading) — exists
  └─ Requires: Rally stage/day progress tracking (new)
  └─ Requires: System health metrics (CPU temp, disk %, sync backlog) — partial
  └─ Requires: Display framework choice (tkinter or pygame)

Rally stage/day progress tracking
  └─ Requires: GPS track accumulator (distance calculation from coordinates)
  └─ Requires: Day boundary detection (new boot = new day, or GPS date change)

Remote health reporting
  └─ Requires: Health metrics as Prometheus readings (new reading types)
  └─ Requires: Existing batch sync — no change needed

Live website position update
  └─ Requires: GPS collector (exists)
  └─ Requires: New sync endpoint or periodic events.json position injection

Graceful shutdown on power loss
  └─ Requires: GPIO-connected power-loss signal from power supply (hardware)
  └─ Requires: Signal handler and ordered shutdown sequence

Thermal resilience monitoring
  └─ Requires: Existing CPU temp metric (exists)
  └─ Requires: New threshold logic (warning at 70°C, throttle-aware at 80°C)
  └─ Blocks: Remote health reporting (temp is a key health metric)

Persistent event queue for failed captures
  └─ Requires: New SQLite table for pending captures
  └─ Requires: CaptureSyncService retry loop changes
```

---

## Complexity Assessment

### Low complexity (days, not weeks)

- Hardware watchdog configuration (kernel module + systemd.conf line)
- systemd `Restart=always` audit and fix
- In-car audio alert expansion (buzzer already wired)
- Remote health reporting (new reading types on existing sync path)
- Configuration hot-reload via SIGHUP
- ffmpeg process monitoring (poll `_process.poll()` in health check)

### Medium complexity (weeks, careful testing)

- Disk space management with safe priority eviction (must not delete in-progress captures)
- SQLite WAL checkpoint management (background thread, tuning)
- Read-only OS filesystem (overlayfs or ro mount; must test boot/write paths carefully)
- Driver dashboard on 7" touchscreen (UI framework, layout, refresh loop)
- Rally stage/day progress tracking (GPS distance accumulation, persistence across reboots)
- Live website position update (new sync logic, website change)
- Persistent event queue (schema change, retry logic, race condition care)

### High complexity (requires significant investigation)

- Graceful shutdown on power loss (requires hardware GPIO signal from power supply; wiring work not just software)
- Full overlayfs read-only root (significant Raspbian-specific complexity; easy to break the system)

---

## MVP Recommendation for Rally Readiness

Prioritise in this order — earlier items protect data, later items improve experience.

**Must ship (system survival):**

1. Hardware watchdog via BCM2835 — prevents silent hangs with no recovery
2. systemd restart policy audit — ensures all services recover from crashes
3. Proactive disk eviction — prevents SD card exhaustion on day 3
4. SQLite WAL checkpoint management — prevents WAL overflow
5. ffmpeg health monitoring and restart — silent video loss is unacceptable
6. Thermal monitoring with alerts — 50°C cabin, Pi throttles at 80°C; need warning

**Should ship (data quality and crew confidence):**

7. Remote health reporting via Prometheus — crew visibility from home
8. Persistent event queue — no lost events if sync fails mid-rally
9. Configuration hot-reload — ability to tune thresholds without restart

**Nice to have (engagement and driver awareness):**

10. Driver dashboard on 7" touchscreen — speed, heading, trip stats
11. Rally stage/day progress tracking — cumulative distance, current day distance
12. Live website position update — followers can see route progress

**Defer (hardware work or high risk):**

13. Graceful shutdown on power loss — needs hardware; WAL mode already mitigates corruption risk adequately
14. Read-only OS filesystem — high implementation risk; WAL + good power supply is sufficient mitigation

---

## Context-Specific Notes

**Australian summer heat.** The Pi 4 throttles at 80°C SoC temperature. With ambient cabin temps
of 50-55°C and direct sun, the Pi needs active cooling and thermal monitoring. The system should
log thermal events as readings and alert via OLED and buzzer before throttling degrades 100 Hz
sampling. Confidence: HIGH (official Raspberry Pi docs confirm throttle threshold).

**SD card endurance.** At 100+ readings/second into SQLite plus continuous video ring buffer writes
(~15 MB/s), a consumer-grade SD card will fail within the rally. The system must use an endurance
card (SanDisk High Endurance or equivalent) AND reduce write load via WAL checkpoint tuning and
reduced ring buffer write frequency. Software mitigations are insufficient alone — card selection
is a prerequisite. Confidence: HIGH (Raspberry Pi forum community data, multiple sources).

**Hardware watchdog maximum.** The BCM2835 hardware watchdog maximum timeout is 15 seconds.
`RuntimeWatchdogSec=14` in `/etc/systemd/system.conf` is the correct configuration.
Values above 15s are silently ignored — this is a known gotcha. Confidence: HIGH (systemd
GitHub issue #27427, multiple Raspberry Pi forum threads confirm).

**No GPS = no time sync = wrong timestamps.** On multi-day rally with hard power cuts, the Pi
clock will drift significantly overnight. GPS-based clock sync on boot is table stakes.
The existing implementation is correct but should be validated in the field.
Confidence: HIGH (existing implementation, well-understood Pi limitation).

**Shitbox Rally connectivity profile.** Long stretches (Outback Way route segments, Gibb River Road)
have zero mobile coverage. The system must operate fully offline for 12+ hour periods, then batch
sync at camp sites and towns. The existing offline-first architecture is the right model.
Confidence: HIGH (Shitbox Rally website confirms outback/off-road route characteristics).

---

## Sources

- [Shitbox Rally 2025 — route and event details](https://www.shitboxrally.com.au/rallies)
- [Raspberry Pi thermal throttling — 80°C threshold (official)](https://www.sunfounder.com/blogs/news/raspberry-pi-temperature-guide-how-to-check-throttling-limits-cooling-tips)
- [BCM2835 hardware watchdog — 15s maximum, RuntimeWatchdogSec](https://bends.se/?page=notebook%2Fsbc%2Fraspberry-pi%2Fhw-watchdog)
- [systemd RuntimeWatchdogSec silent failure above 15s — GitHub issue #27427](https://github.com/systemd/systemd/issues/27427)
- [SD card endurance — TLC consumer cards: 3K-10K write cycles per block](https://forums.raspberrypi.com/viewtopic.php?t=317568)
- [SanDisk High Endurance SD card on Raspberry Pi](https://forums.raspberrypi.com/viewtopic.php?t=288190)
- [SQLite VACUUM and WAL growth on embedded devices](https://www.theunterminatedstring.com/sqlite-vacuuming/)
- [Watchdogd — advanced system monitor for embedded Linux](https://github.com/troglobit/watchdogd)
- [In-vehicle power ignition management patterns](https://premioinc.com/blogs/blog/power-ignition-management-for-in-vehicle-computing)
- [Prometheus Pushgateway — limitations for continuous device monitoring](https://prometheus.io/docs/practices/pushing/)
- [Rally telemetry display features — speed, heading, trip distance](https://www.rally.cc/)
- [Telemetry in Rally — special case for multi-day events](https://www.canevarally.com/gravel/telemetry-in-rally-a-special-case/)
- [watchdog firmware best practices — Interrupt blog](https://interrupt.memfault.com/blog/firmware-watchdog-best-practices)
- [Leveraging systemd for hardware watchdog control](https://cornersoftsolutions.com/leveraging-systemd-for-hardware-watchdog-control-in-embedded-linux/)
