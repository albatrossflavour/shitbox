# Phase 28: TPMS Integration - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

## Phase Boundary

Receive 433 MHz TPMS frames from the four installed wheel sensors via RTL-SDR + `rtl_433`, normalise pressure into actual PSI, persist to SQLite, surface per-wheel state on Grafana and the dashboard Health page with low-pressure threshold alerts (28/25 PSI) and rapid-deflation leak alerts (≥5 PSI/60s) via the existing TTS engine. Hardware manifest entry with `criticality: best_effort` so the daemon degrades gracefully when the SDR is missing.

Locked by `28-SPEC.md` (10 requirements, 0.13 ambiguity). This discussion captures HOW to implement those requirements.

## Implementation Decisions

### Health page TPMS section layout

- **D-01:** Plain text list, four rows. Same shape as the Phase 15 SYSTEM alert section. Each row format: `{wheel_label}  {PSI} PSI  {status}` where `wheel_label` is `FD` / `FP` / `RD` / `RP` (front-driver / front-passenger / rear-driver / rear-passenger). Status values: `NO DATA` (grey, before first frame), `OK` (green), `LOW` (yellow, ≤28 and >25 PSI), `CRITICAL` (red, ≤25 PSI sustained, OR rapid-leak detected), `STALE` (amber, no frame for 5 minutes).
- **D-02:** Temperature is **not** shown on the Health page. It's captured to SQLite and exposed to Grafana but is post-rally analysis territory, not in-cabin driver-facing.
- **D-03:** Section renders via the existing Phase 15 SSE-payload + Alpine `x-for` pattern. `_tpms_payload` sits alongside `_system_conditions_payload` and `_hardware_payload` in `src/shitbox/dashboard/sse.py`.

### TTS alert wording

- **D-04:** Sustained-low utterance (red threshold crossed): `"{position} tyre low pressure"` where position is `front driver` / `front passenger` / `rear driver` / `rear passenger`. Example: "Front driver tyre low pressure". UK/Aus spelling "tyre". No PSI value spoken (numbers articulate poorly in a noisy cabin).
- **D-05:** Leak utterance (≥5 PSI/60s): `"Tyre leaking, {position}"`. Active-verb phrasing distinct from the sustained-low state description so the driver can ear-distinguish the two alert types from one announcement. Example: "Tyre leaking, front driver".
- **D-06:** Reuse the Phase 5 `speak_*` helper pattern in `src/shitbox/capture/speaker.py`. New helpers: `speak_tpms_low(position)` and `speak_tpms_leak(position)`. Both helpers reuse the existing TTS engine fall-through (Piper if available, then espeak-ng, then silent).
- **D-07:** Recovery utterance follows the Phase 15 `_RESTORED` suffix pattern from the alerts helper. Lock the wording during planning — likely `"{position} tyre pressure restored"` to match the speak_power_restored cadence.

### rtl_433 install + device-probe mechanism

- **D-08:** Install rtl_433 via apt in `scripts/install.sh`. Add `rtl-433 librtlsdr-dev` to the existing apt-get install line. Pi OS bookworm ships rtl_433 ≥22.x which already includes protocol 156 (Abarth-124Spider / VDO TG1C). Zero maintenance burden; Debian handles security updates.
- **D-09:** Hardware manifest probe matches the RTL-SDR via lsusb VID:PID. Probe runs `lsusb` and looks for `0bda:2838` (RTL2832U + R820T2 — the chipset family in both the Nooelec NESDR Smart v5 and any compatible aftermarket dongle). Probe lives in the manifest detection path alongside the existing camera `/dev` path checks.
- **D-10:** No librtlsdr Python binding (pyrtlsdr) added — the Python process never talks to librtlsdr directly. All RF work happens in the rtl_433 subprocess, which is a userland binary.

### Claude's Discretion

The following were not selected for discussion. Planner picks sensible defaults during plan-phase:

- **Grafana panel design** — default to four time series (one per wheel) for `tpms_pressure_psi` and another four for `tpms_temperature_c` in the existing `shitbox-rally-command` dashboard. Connects naturally to the standing audit-Grafana-dashboard todo (2026-04-26) but doesn't depend on it.
- **TPMS service module location and naming** — likely `src/shitbox/sync/tpms.py` (sibling to `batch_sync.py`, `capture_sync.py`) given it's a long-running background service that doesn't fit `BaseCollector`. Final naming up to the planner.
- **Subprocess management mechanics** — drain stderr, monitor for stalls, restart on death. Lift the established `capture/ring_buffer.py:740-1050` ffmpeg-management pattern (not `capture/video.py` — the long-running daemon pattern with `_read_stderr` non-blocking drain at lines 827-846, `_health_monitor` restart-on-death loop at lines 926-1050, and `fuser -k` device release at line 752 lives in `ring_buffer.py`).
- **In-memory deque vs SQLite query for leak-detection sliding window** — in-memory deque (per wheel, 60 samples) is the simpler and faster choice; planner picks unless evidence emerges otherwise.
- **Schema migration mechanics** — current `SCHEMA_VERSION` is 10 in `src/shitbox/storage/database.py:16` (verified by researcher 2026-04-28). Bump to 11, add `tpms_readings` table via new `_migrate_to_v11` modelled on `_migrate_to_v6` at `database.py:298-330`. (Earlier CONTEXT.md note saying "v3 → v4" was written from stale memory.)
- **Prometheus metric naming** — `shitbox_tpms_pressure_psi{wheel="..."}` and `shitbox_tpms_temperature_c{wheel="..."}` per the project's `shitbox_*` namespace convention.
- **YAML config schema** — single `tpms:` block with `enabled`, `pressure_correction_factor` (default 2.45), `low_pressure_yellow_psi` (28), `low_pressure_red_psi` (25), `leak_window_seconds` (60), `leak_drop_psi` (5), `stale_timeout_seconds` (300), and `sensors:` mapping ID → wheel position.

## Specific Ideas

- Wheel labels in the Health page are abbreviated `FD/FP/RD/RP`. TTS utterances spell out the full position (`front driver`, etc) for clarity in audio.
- "Tyre" with UK/Aus spelling everywhere — config keys, log messages, dashboard labels, TTS, comments. No "tire".
- Recovery messaging follows the Phase 15 `_RESTORED` suffix pattern — keep operational consistency with the undervoltage / capture restored alerts already shipped.
- TPMS_LEAK event written to `events.json` records the leak occurrence alongside HIGH_G/HARD_BRAKE/etc, but does **not** trigger the dashcam-buffer save path (per SPEC.md boundary).

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/phases/28-tpms-integration/28-SPEC.md` — Locked requirements (10), boundaries, acceptance criteria. Treat all "in scope" / "out of scope" lists as authoritative.

### Existing patterns to reuse
- `src/shitbox/health/alerts.py` — Sustain + transition + recovery helpers from Phase 15. Module-level GIL-atomic rebind pattern for thread-safe state.
- `src/shitbox/capture/video.py` — Subprocess lifecycle: drain stderr, monitor for stalls, restart on death + `fuser -k` + 0.5s sleep before respawn.
- `src/shitbox/capture/speaker.py` — TTS engine wrapper with Piper / espeak-ng / silent fall-through. Existing `speak_*` helpers (e.g. `speak_power_restored` from Phase 15).
- `src/shitbox/dashboard/sse.py` — SSE payload assembly for the Health page; `_system_conditions_payload` and `_hardware_payload` are the precedents for `_tpms_payload`.
- `src/shitbox/dashboard/static/index.html` — Alpine.js `x-for` rendering for the SYSTEM section; new TPMS section follows same shape.
- `src/shitbox/storage/database.py` — Schema migration pattern (currently `SCHEMA_VERSION = 3`, bump to 4). Thread-safe write locks, WAL mode.
- `src/shitbox/sync/batch_sync.py` — Cursor-based Prometheus remote_write pattern. New TPMS metrics follow this same path.
- `src/shitbox/sync/capture_sync.py` — Sibling service shape for a non-collector background service.

### Hardware manifest + supervisor
- `config/config.yaml` § `hardware: devices` — Add `role: tpms_radio`, `bus: usb`, `criticality: best_effort` entry.
- Phase 21 `HardwareSupervisor` (referenced in `21-CONTEXT.md`) — exponential-backoff re-adoption when a missing device returns. New TPMS service plugs into this.

### Decoder reference
- `tpms_abarth124.c` in upstream rtl_433 (`github.com/merbanan/rtl_433/blob/master/src/devices/tpms_abarth124.c`) — Decoder source. `kPa = press_raw × 1.38`, pressure byte is index 5 in 9-byte packet. Source docstring flags VDO-says-450/900-kPa uncertainty that justifies our × 2.45 correction.

### Brain context
- `~/Brain/projects/shitbox-rally-2026.md` § 2026-04-28 log entries — TPMS bench-validation findings, the four sensor IDs and wheel positions, calibration calculation showing × 2.45 correction.

## Existing Code Insights

### Reusable Assets
- **`alerts.py`** (Phase 15): sustain-and-transition pattern for low-pressure alert. Module-level state for current alert status, recovery helper for `_RESTORED` semantics.
- **`capture/video.py`** ffmpeg subprocess pattern: drain stderr, monitor `_is_stalled()`, kill-then-respawn with 0.5s sleep. Direct lift for rtl_433 lifecycle.
- **`capture/speaker.py`** TTS helpers: add `speak_tpms_low(position)` and `speak_tpms_leak(position)` matching the established `speak_*` shape.
- **`dashboard/sse.py`** payload assembly: `_tpms_payload` slots in alongside `_system_conditions_payload`.
- **`dashboard/static/index.html`** Alpine `x-for`: TPMS section renders four-row list using same patterns as SYSTEM.
- **`storage/database.py`** migration pattern: bump `SCHEMA_VERSION` 3 → 4 and add `tpms_readings` table.

### Established Patterns
- **structlog keyword logging**: `log.info("tpms_frame_received", wheel="front-driver", pressure_psi=32.1, raw_kpa=89.7)`. Never positional args.
- **Single flat YAML config → nested dataclasses**: TPMS config block parses into `TpmsConfig` dataclass via `_dict_to_dataclass`.
- **Hardware manifest declarative**: presence/criticality/description in YAML; runtime probe records PRESENT/MISSING; supervisor handles re-adoption.
- **Phase 5 TTS fall-through**: Piper → espeak-ng → silent. Don't suppress visual alerts if TTS unavailable.
- **UK/Aus spelling**: `tyre` not `tire` everywhere.

### Integration Points
- **Engine init**: `UnifiedEngine.__init__()` in `events/engine.py` instantiates the TPMS service alongside batch_sync, capture_sync, etc.
- **Engine config wiring**: TPMS config fields flat on `EngineConfig` (not nested) per the project pattern, mapped from YAML in `from_yaml_config()`.
- **`install.sh`**: add `rtl-433 librtlsdr-dev` to the apt-get install line.
- **`/etc/systemd/system/shitbox-telemetry.service`**: no change needed — rtl_433 runs as a child subprocess of the daemon, not a separate unit.
- **Hardware manifest probe**: extend the existing presence-probe path to handle USB VID:PID matching (currently checks `/dev` paths for cameras).

### Constraints from the codebase
- `BaseCollector` is not a fit (synchronous-polled, doesn't suit rtl_433's async stdout stream). New service module follows the `sync/` pattern instead.
- Schema version is currently 3 — adding `tpms_readings` requires migration to 4. Older databases need to be upgradeable (the existing migration path handles this).

## Deferred Ideas

None — discussion stayed within phase scope per the locked SPEC.md. The following items remain out of scope as previously locked:

- File rtl_433 upstream PR for the TG1C LSB issue (deferred until calibration tighter)
- Roof-mounted antenna install + SMA bulkhead through the case
- OTA learn-mode for replacing a sensor mid-rally
- Per-sensor calibration table
- TPMS triggering dashcam-buffer video capture
- Temperature thresholds / temperature alerting
- Anti-theft / sensor cloning detection

---

*Phase: 28-tpms-integration*
*Context gathered: 2026-04-28*
*Next step: `/gsd-plan-phase 28` — break down into executable plans*
