# Phase 4: Remote Health and Stage Tracking - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Publish system health metrics to Prometheus for the crew to monitor remotely during connectivity
windows. Track GPS-based distance (total odometer + daily distance) and rally stage progress via
waypoints. No display UI — that is Phase 5. No disk eviction or storage cleanup.

</domain>

<decisions>
## Implementation Decisions

### Health metrics scope

- Four metrics only: CPU temp, disk %, sync backlog, throttle state — no extras
- Piggyback on existing batch sync interval — no separate push cadence
- CPU temperature read from ThermalMonitorService's shared value (Phase 3), not independent sysfs read
- New HealthCollector following the existing BaseCollector pattern

### Distance tracking

- Odometer stored in SQLite for crash-safe persistence across reboots
- Speed threshold of 5 km/h to filter GPS noise — only accumulate distance when moving
- Accumulate in memory on every GPS fix (1 Hz), persist to SQLite every 60 seconds
- Integrated into the existing GPS collector, not a separate service thread

### Route and stage progress

- No GPX file — route defined as ordered waypoints (town name + lat/lng) in YAML config
- Each waypoint has a day number for stage identification
- Waypoint counted as "reached" when GPS is within 5 km radius
- Reached waypoints persisted in SQLite — cannot be un-reached, survives reboots
- Progress shown as waypoints reached / total waypoints for stage-level tracking
- Cumulative odometer distance serves as overall trip distance

### Day boundary logic

- Daily distance resets on first boot of a new calendar day (not midnight timer)
- Daily distance persists across mid-day reboots — stored in SQLite with last-reset date
- Fixed AEST (UTC+10) timezone for day boundaries regardless of physical location
- Daily distance labelled by stage: "Day 3: 512 km" using waypoint day numbers

### Claude's Discretion

- SQLite table schema for distance/waypoint tracking
- Haversine vs simpler distance calculation
- HealthCollector metric naming conventions for Prometheus
- How to wire the route config into the existing YAML config structure

</decisions>

<specifics>
## Specific Ideas

- The rally is 7 days, Port Douglas to Melbourne, with known overnight stops in towns
- The user can provide approximate town-level GPS coordinates for each overnight stop
- Waypoints should be easy to edit in the YAML config — the user will populate them manually
- Stage labels like "Day 3: Broken Hill to Adelaide" make the data meaningful

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-remote-health-and-stage-tracking*
*Context gathered: 2026-02-27*
