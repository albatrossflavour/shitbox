# Phase 2: Watchdog and Self-Healing - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Hardware watchdog is active, all services restart on crash, and known data-loss bugs
are fixed. Covers: BCM2835 hardware watchdog, service crash recovery, ffmpeg stall
detection, I2C bus lockup recovery, and buzzer alerting for all failure types.

</domain>

<decisions>
## Implementation Decisions

### Watchdog timeout tuning

- Hardware watchdog timeout: 10 seconds
- 30-second grace period at boot before watchdog enforcement begins
- No special reboot loop detection — each reboot is a fresh attempt
- Watchdog pet source: Claude's discretion (main loop vs dedicated thread)

### I2C lockup handling

- Automatic bit-bang reset after 5 consecutive read failures (~50ms at 100Hz)
- Use the same I2C pins (GPIO2/GPIO3 SDA/SCL) — temporarily switch to output mode,
  pulse 9 clock cycles, switch back to I2C
- If bit-bang reset fails to recover the bus: force a full system reboot
- No intermediate escalation steps — go straight from bit-bang to reboot

### Failure alerting policy

- Distinct buzzer patterns per failure type (e.g. 1 long = service crash,
  3 short = I2C lockup, 2 long = watchdog miss)
- Escalating repeat alerts: first occurrence is brief, recurrence within 5 minutes
  triggers louder/longer pattern
- Recovery confirmation: short chirp when a failed service comes back
- Silent during boot: suppress all buzzer alerts during the 30-second settling period

### Recovery aggressiveness

- Unlimited restart attempts for crashed services — never give up
- Exponential backoff between attempts: 1s, 2s, 4s, 8s, etc.
- ffmpeg stall detection via output file size monitoring — if file size unchanged
  for N seconds, kill and restart ffmpeg
- After backoff reaches a ceiling (e.g. 5 minutes), reset counter and try again
  with fresh backoff

### Claude's Discretion

- Watchdog pet source architecture (main engine loop vs dedicated thread)
- Exact buzzer tone frequencies and durations for each pattern
- Exponential backoff ceiling value
- ffmpeg stall detection timeout threshold
- Specific structlog fields for health monitoring events

</decisions>

<specifics>
## Specific Ideas

- The system must keep running with whatever hardware is available — if IMU is down,
  GPS and video should continue
- Buzzer patterns should be learnable by a driver who can't look at a screen
- The car is a rally shitbox — expect rough conditions, vibration, heat

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-watchdog-and-self-healing*
*Context gathered: 2026-02-25*
