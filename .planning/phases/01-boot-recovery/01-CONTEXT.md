# Phase 1: Boot Recovery - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>

## Phase Boundary

System survives hard power cuts and starts cleanly after every ignition cycle. The Pi is powered via USB from the cigarette lighter, which cuts immediately on ignition off. Expect 2-4 hard power cuts per day over 8-10 rally days (20-40 total unclean shutdowns). This phase hardens SQLite durability, detects and recovers from crashes, and ensures the system is capturing data within 60 seconds of power-on.

</domain>

<decisions>

## Implementation Decisions

### Shutdown Detection

- Infer crash state from SQLite, not a separate flag file or PID check
- Indicators: open/unclosed events in the database, WAL file state
- No separate "running" sentinel file — keep it simple, use what SQLite already provides

### Recovery Behaviour

- Orphaned events: close and mark as "interrupted" — partial data is better than none
- SQLite integrity failure: log the result and continue — start a fresh DB if needed, never block startup
- Partial video files: keep whatever ffmpeg managed to write — partial video is still useful
- Prometheus sync cursor: trust it after crash — accept possible small gap rather than re-syncing
- Philosophy: capturing new data is always more important than recovering old data perfectly

### Startup Sequence

- Target: under 60 seconds from power-on to capturing data
- Recovery checks (integrity check, orphan cleanup) run in a background thread — do not block data capture
- Preserve the existing 20-second GPS wait (maximum) — this ensures early videos have GPS data and system clock is synced from GPS
- No BOOT events in events.json — boots are not driving events

### Failure Visibility

- Detailed structured logs for every recovery action: which events were closed, integrity check result, WAL state, actions taken
- OLED display shows recovery status ("Recovered from crash", count of closed events) until GPS fix is acquired, then switches to normal display
- Buzzer patterns: single short beep on clean boot, double beep on crash recovery — audibly distinct
- Prometheus metric: increment a crash_recovery counter so recovery history is visible in Grafana

### SQLite Durability

- Configure `synchronous=FULL` to ensure WAL writes survive hard power cuts
- This is the primary defence against data corruption since there is no graceful shutdown mechanism

### Claude's Discretion

- Exact integrity check implementation (full `PRAGMA integrity_check` vs lighter `PRAGMA quick_check`)
- Background thread implementation details for recovery
- How to detect WAL state indicating prior crash
- Prometheus metric naming and labels

</decisions>

<specifics>

## Specific Ideas

- The cigarette lighter cuts power immediately on ignition off — no warning, no grace period
- The existing 20s GPS wait is deliberate and should be preserved (ensures clock sync and GPS in early videos)
- The system already has a health watchdog, OLED display service, and buzzer — recovery should integrate with these existing mechanisms
- The existing `EventStorage` already writes events to JSON/CSV — the "interrupted" marking should follow that pattern

</specifics>

<deferred>

## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-boot-recovery*
*Context gathered: 2026-02-25*
