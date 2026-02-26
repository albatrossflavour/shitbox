# Phase 3: Thermal Resilience and Storage Management - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Monitor CPU temperature and Pi throttle state to alert the driver before thermal degradation
impacts IMU sampling. Prevent unbounded WAL growth on the SD card. This phase adds a thermal
monitor service and WAL checkpointing — no new UI, no disk eviction, no display integration.

</domain>

<decisions>
## Implementation Decisions

### Thermal thresholds

- Hardcoded thresholds: 70°C warning, 80°C critical — these are Pi hardware limits, no config knob needed
- 3°C hysteresis on both thresholds — alert at 70°C, suppress until below 67°C before re-arming
- Recovery beep when temperature drops back below the warning threshold after an alert
- Thread-safe shared value for current temperature — other subsystems read it cheaply without polling sysfs

### Throttle logging

- Log on state change only — when any vcgencmd get_throttled flag flips, not every interval
- Track both "currently happening" and "has occurred since boot" flag sets in separate structlog fields
- Under-voltage (bit 0) triggers a distinct buzzer alert — driver needs to know about power supply issues
- Same 5-second interval as thermal sampling — one unified health check loop, read temp and throttle together

### WAL checkpoint timing

- Unconditional TRUNCATE checkpoint every 5 minutes on a timer
- Log only when pages were actually truncated — silent when WAL was already clean
- Runs inside the existing Database module — it already holds the connection and write lock, no new service thread

### Claude's Discretion

- Thermal monitor thread design and integration with engine lifecycle
- Exact structlog field names for throttle state
- How to read sysfs thermal zone vs vcgencmd for temperature (either approach acceptable)

</decisions>

<specifics>
## Specific Ideas

- Temperature and throttle should be read in the same health check loop on the same 5-second cadence
- The buzzer already has alert patterns from Phase 2 — add thermal_warning, thermal_critical, under_voltage, and thermal_recovered patterns
- Hysteresis should apply independently to warning and critical thresholds

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-thermal-resilience-and-storage-management*
*Context gathered: 2026-02-26*
