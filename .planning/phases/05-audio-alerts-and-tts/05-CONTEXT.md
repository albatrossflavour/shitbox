# Phase 5: Audio Alerts and TTS - Context

**Gathered:** 2026-02-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace buzzer tone patterns with spoken TTS alerts via USB speaker. Add contextual
announcements for system events. The buzzer becomes a fallback if the speaker is unavailable.
This phase does not add new alert conditions — it changes the output medium for existing alerts
and adds informational announcements using data from Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Audio output device

- USB speaker: Jieli Technology UACDemoV1.0 (Bus 001 Device 004)
- Speaker replaces buzzer as primary alert output
- Buzzer remains as fallback if USB speaker is not detected or fails

### TTS engine

- Piper (offline neural TTS) for natural-sounding voice
- ~10-15% CPU for 1-2 seconds per utterance, acceptable for infrequent messages
- ~50-100MB model files on disk
- No internet required — fully offline

### Message types

- Everything contextual: alerts, milestones, periodic updates, and status confirmations
- Alert announcements: thermal warning/critical, under-voltage, I2C lockup, ffmpeg stall, service crash/recovery
- Stage milestones: "Waypoint reached: Broken Hill", "Day 3 complete"
- Periodic updates: distance driven today
- System status: "System ready" on boot, recovery confirmations

### Claude's Discretion

- Audio playback architecture (aplay, pygame, subprocess)
- Piper model selection (voice, language, quality tier)
- Message queue design to avoid overlapping announcements
- How to detect USB speaker presence and fall back to buzzer
- Exact wording of each announcement message

</decisions>

<specifics>
## Specific Ideas

- The buzzer is overloaded with 9+ distinct tone patterns at various frequencies — no driver can learn them all mid-rally
- Spoken messages are immediately understandable without training
- Audio must not block the engine thread or interfere with IMU sampling

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-audio-alerts-and-tts*
*Context gathered: 2026-02-27*
