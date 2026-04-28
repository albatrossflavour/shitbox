# Phase 28: TPMS Integration — Research

**Researched:** 2026-04-28
**Domain:** RTL-SDR subprocess management + 433 MHz TPMS frame parsing + integration with shipped Phase 5/15/21 patterns
**Confidence:** HIGH (codebase patterns) / HIGH (rtl_433 invocation) / MEDIUM (rtl_433 stderr behaviour, USB hot-unplug semantics)

## Summary

Phase 28 reuses three established shitbox patterns and adds one new subsystem. The new bit is a long-running `rtl_433 -R 156 -F json` subprocess that streams JSON frames; the rest is the same shape as `BatchSyncService` / `CaptureSyncService` plus Phase 15's alerts helper. There are no novel architectural decisions left to make. Every design choice already has a precedent in the repo.

The two real risks are (1) `rtl_433` mixing some output between stdout and stderr (a known upstream quirk), and (2) USB hot-unplug on the RTL-SDR — the binary exits rather than reconnects, so the wrapper has to detect the exit, decide whether to back off (device gone) or restart (transient), and update `HardwareState`. Both risks are handled cleanly by lifting the `ring_buffer.py` ffmpeg-management pattern wholesale.

A small but important correction: **`SCHEMA_VERSION` is currently `10`, not `3`** as stated in 28-CONTEXT.md D-Discretion. The TPMS migration is `_migrate_to_v11`, not `_migrate_to_v4`. The CONTEXT note appears to have been written from old memory; the planner needs to use the real number.

**Primary recommendation:** Build a `TPMSService` class in `src/shitbox/sync/tpms.py` (sibling to `batch_sync.py` and `capture_sync.py`) that owns: rtl_433 subprocess lifecycle (using ring_buffer's `_read_stderr` non-blocking drain pattern), per-wheel state dict, in-memory leak-detection deque, alert wiring through `health/alerts.py`, and a `tpms_readings` table writer. Insert into `_readings_to_metrics` (batch_sync) for Prometheus exposition. Add `_tpms_payload` to `dashboard/sse.py` slow stream alongside the existing `_system_conditions_payload`.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Health page TPMS section layout (D-01, D-02, D-03):**
- Plain text list, four rows. Same shape as Phase 15 SYSTEM section in `dashboard/static/index.html` lines 412-422.
- Row format: `{wheel_label}  {PSI} PSI  {status}` where `wheel_label` is `FD` / `FP` / `RD` / `RP`.
- Status values: `NO DATA` (grey), `OK` (green), `LOW` (yellow, ≤28 and >25 PSI), `CRITICAL` (red, ≤25 PSI sustained OR rapid-leak), `STALE` (amber, >5min silent).
- Temperature is captured to SQLite + Grafana but **not** displayed on the Health page.
- `_tpms_payload` sits alongside `_system_conditions_payload` and `_hardware_payload` in `src/shitbox/dashboard/sse.py`, emitted on `/sse/slow` (1 Hz).

**TTS alert wording (D-04, D-05, D-06, D-07):**
- Sustained-low (red threshold): `"{position} tyre low pressure"` — e.g. "Front driver tyre low pressure". UK/Aus "tyre". No PSI value spoken.
- Leak (≥5 PSI/60s): `"Tyre leaking, {position}"` — active-verb phrasing distinct from the sustained-low state.
- New helpers in `src/shitbox/capture/speaker.py`: `speak_tpms_low(position)` and `speak_tpms_leak(position)`. Reuse Piper → espeak-ng → silent fall-through.
- Recovery utterance: `"{position} tyre pressure restored"` — matches `speak_power_restored` cadence.

**rtl_433 install + device probe (D-08, D-09, D-10):**
- Install via apt in `scripts/install.sh` — add `rtl-433 librtlsdr-dev` to apt-get install line. Pi OS bookworm ships rtl_433 22.11-1.
- Hardware manifest probe matches RTL-SDR via lsusb VID:PID `0bda:2838`.
- No pyrtlsdr Python binding — Python only talks to rtl_433 over its stdout pipe.

### Claude's Discretion

The following were left to the planner; Brain context + research below provide concrete recommendations:
- Grafana panel design (default: 4 time series per metric on `shitbox-rally-command` dashboard)
- TPMS service module location: `src/shitbox/sync/tpms.py`
- Subprocess management mechanics: lift `capture/ring_buffer.py` patterns
- Sliding window mechanism: in-memory `collections.deque(maxlen=N)` per wheel
- Schema migration mechanics: bump `SCHEMA_VERSION` 10 → 11 (NOT 3 → 4 — see note at top), add `tpms_readings`
- Prometheus metric naming: `shitbox_tpms_pressure_psi{wheel="..."}` and `shitbox_tpms_temperature_c{wheel="..."}`
- YAML schema: single `tpms:` block with sensor map, correction factor, thresholds, windows

### Deferred Ideas (OUT OF SCOPE)

- Patching rtl_433 / filing upstream PR for the TG1C LSB issue
- Roof-mounted antenna install (cable/bulkhead/magnetic-base placement)
- OTA learn-mode for replacing a sensor mid-rally
- Per-sensor calibration table
- TPMS triggering dashcam-buffer video capture
- Temperature thresholds / temperature alerting
- Anti-theft / sensor cloning detection

## Phase Requirements

Phase 28 has 10 falsifiable requirements locked in `28-SPEC.md` (ambiguity 0.13). They are NOT mapped to `.planning/REQUIREMENTS.md` IDs — the SPEC.md numbered list is authoritative.

| ID | Description (from SPEC.md) | Research Support |
|----|----------------------------|------------------|
| 1 | TPMS frame ingestion via rtl_433 subprocess | rtl_433 invocation flags + subprocess pattern from `capture/ring_buffer.py` (Pattern 1, Pitfalls 1-3) |
| 2 | Pressure correction × 2.45 (configurable) | Single multiplier in `TpmsConfig.pressure_correction_factor`; applied in collector before storage/alerting/display |
| 3 | Wheel-position mapping via YAML sensor table | `TpmsConfig.sensors: dict[hex_id, position]` + `unknown_sensor` log+drop |
| 4 | SQLite persistence: new `tpms_readings` table | Schema migration v11 (Pattern 4 below); new dedicated table parallels existing `notes`/`fuel_stops`/`driver_stints` tables |
| 5 | Prometheus exposition with wheel labels | New branch in `BatchSyncService._readings_to_metrics` OR a separate cursor; recommend new cursor (see Pattern 5) |
| 6 | Dashboard Health page TPMS section | `_tpms_payload` in `sse.py`; new Alpine `x-for` template in `index.html` (Pattern 6) |
| 7 | Low-pressure alerting 28/25 PSI via `alerts.py` | sustain (1 sample at 1 frame/sec is enough) + transition + recovery — direct reuse of `health/alerts.py` (Pattern 7) |
| 8 | Rapid-deflation leak detection ≥5 PSI / 60s | Per-wheel `collections.deque[(ts, psi)]`; on each frame compute max-min over window (Pattern 8) |
| 9 | Stale-sensor detection > 5 min silence | Track `last_seen` per wheel; tick once per second from the SSE payload assembly OR a 1 Hz watchdog (Pattern 9) |
| 10 | Hardware manifest entry `tpms_radio`, best_effort | New `bus: usb` entry; new `probe_usb_vid_pid` probe added to `hardware/probes.py` (Pattern 10) |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| RF reception + decode | External binary (rtl_433) | — | Userland tool; Python never touches librtlsdr |
| JSON frame parsing | Python service module (`sync/tpms.py`) | — | One service owns subprocess + parsing + dispatch |
| Pressure correction | Python collector | — | Applied at ingest; downstream sees corrected PSI only |
| Wheel-position mapping | Python collector (config-driven) | — | Lookup table from YAML; unknown IDs logged + dropped |
| SQLite persistence | `storage/database.py` (new method) | TPMSService (caller) | Parallels existing `insert_reading` / `record_waypoint_reached` |
| Prometheus exposition | `sync/batch_sync.py` (extension) | `storage/database.py` (cursor) | New cursor name `prometheus_tpms`; metrics built from `tpms_readings` rows |
| Dashboard SSE payload | `dashboard/sse.py` (new helper) | TPMSService (state source) | `_tpms_payload()` reads from service; mirrors `_system_conditions_payload` |
| Health page rendering | Alpine `x-for` in `static/index.html` | — | Same template shape as the SYSTEM section (lines 412-422) |
| Alert orchestration | `health/alerts.py` (existing helper) | TPMSService (caller) | One subtype per wheel × 2 alert types = 8 keys; reuse fire_alert / fire_recovery |
| TTS speech | `capture/speaker.py` (new helpers) | `health/alerts.py` (callback) | New `speak_tpms_low(position)` / `speak_tpms_leak(position)` enqueue to existing worker |
| Hardware presence | `hardware/probes.py` (new probe) | `hardware/supervisor.py` (existing) | New `probe_usb_vid_pid` function; supervisor handles re-adoption |
| Event recording | `events/storage.py` (new event type) | TPMSService (caller) | New `EventType.TPMS_LEAK` value; `save_event` API unchanged |
| Service lifecycle | `events/engine.py` `UnifiedEngine.__init__` | — | Instantiate alongside `batch_sync` / `capture_sync`; same start/stop pattern |

## Standard Stack

### Core

| Library / Binary | Version | Purpose | Why Standard |
|---|---|---|---|
| `rtl-433` (apt) | 22.11-1 (Debian bookworm) [VERIFIED: packages.debian.org/bookworm/rtl-433] | Decode 433 MHz TPMS frames including protocol 156 (Abarth-124Spider / VDO TG1C) | Already validated end-to-end on the Mac with all 4 sensors decoded. Apt path means zero maintenance burden. Version 22.11 contains the Abarth-124 decoder (added 2021, present since 21.x). [CITED: github.com/merbanan/rtl_433/blob/master/src/devices/tpms_abarth124.c] |
| `librtlsdr-dev` (apt) | bundled with rtl-433 | RTL-SDR USB library | Required runtime dependency of rtl_433; apt pulls it in automatically but installing the dev package documents intent. |
| `subprocess` (stdlib) | 3.9+ | rtl_433 process management | Already used in `capture/ring_buffer.py`, `capture/video.py`, `sync/capture_sync.py`. No third-party process libraries. |
| `json` (stdlib) | 3.9+ | Parse `-F json` frames | One JSON object per line on stdout. |
| `collections.deque` (stdlib) | 3.9+ | Per-wheel sliding-window leak detection | `deque(maxlen=N)` with `append` and iteration is GIL-atomic in CPython for our access pattern (single producer, single consumer per wheel). [CITED: bugs.python.org/issue15329] |

### Supporting

| Library / Binary | Version | Purpose | When to Use |
|---|---|---|---|
| `lsusb` (apt: usbutils) | already installed | Probe RTL-SDR by VID:PID `0bda:2838` | Hardware manifest probe (Phase 21 pattern). Already installed via i2c-tools dependency chain on the Pi. |
| `fuser` (apt: psmisc) | already installed | Force-release USB device handle before respawning rtl_433 (mirrors ring_buffer's `fuser -k` of /dev/video*) | Only needed if rtl_433 zombies hold the USB device open across restarts; lift the pattern from `ring_buffer.py:752`. |

### Alternatives Considered

| Instead of | Could Use | Why Not |
|---|---|---|
| `rtl_433 -F json` subprocess | `pyrtlsdr` + custom decoder in Python | Already locked OUT in D-10. Reimplementing the FSK Manchester demod for one TPMS profile is months of work and gives up the upstream maintenance benefit. |
| In-memory deque for leak detection | SQLite `WHERE timestamp > ?` query per frame | Locked to deque in D-Discretion bullet. SQLite query at 1 Hz × 4 wheels = 4 reads/sec — fine on disk, but the deque is simpler, holds at most 60 floats per wheel, and avoids touching the write lock from a high-frequency callback. |
| New `Reading` columns in `readings` table | New dedicated `tpms_readings` table | The `readings` table is already 30+ columns wide for 9 sensor types. Adding 6 more TPMS-specific columns would push the table further toward "kitchen sink" anti-pattern. The `notes` / `fuel_stops` / `driver_stints` precedent shows the project already adds dedicated tables when the shape diverges. |
| Single Prometheus cursor | Separate `prometheus_tpms` cursor | The existing cursor advances on `id` from `readings`. TPMS rows in a separate table need their own cursor or batch_sync needs to know about both tables. Separate cursor is cleaner and avoids cross-table joins. |

**Installation:**
```bash
# Add to scripts/install.sh apt-get install line:
apt-get install -y rtl-433 librtlsdr-dev
```

**Version verification:**
```bash
# After install, on the Pi:
rtl_433 -V
# Expected: "rtl_433 version 22.11-1-..."
# Confirm protocol 156 present:
rtl_433 -R help 2>&1 | grep -i "abarth\|124"
# Expected: "[156]  Abarth-124Spider / VDO-TG1C TPMS"
```

[VERIFIED 2026-04-28: Debian bookworm packages page lists rtl-433 22.11-1; testing/sid have 25.02-1 but bookworm-stable is fine for our needs.]

## Architecture Patterns

### System Architecture Diagram

```
                      ┌─────────────────────────┐
                      │   RTL-SDR USB dongle    │
                      │   0bda:2838             │
                      │   (Nooelec NESDR v5)    │
                      └────────────┬────────────┘
                                   │ 433.92 MHz RF
                                   │ (FSK Manchester)
                                   ▼
                      ┌─────────────────────────┐
                      │   rtl_433 subprocess    │
                      │   -R 156 -F json        │     stderr
                      │   (managed by shitbox)  │  ───────────► drain to log every cycle
                      └────────────┬────────────┘
                                   │ JSON line per frame on stdout
                                   ▼
       ┌────────────────────────────────────────────────────────────┐
       │                    TPMSService (sync/tpms.py)              │
       │  ┌──────────────────────────────────────────────────────┐  │
       │  │  reader thread: line-by-line stdout JSON parse       │  │
       │  │  → wheel-id lookup (drop unknown)                    │  │
       │  │  → apply × 2.45 correction                           │  │
       │  │  → kPa → PSI                                         │  │
       │  └────────────────┬─────────────────────────────────────┘  │
       │                   │                                        │
       │   ┌───────────────┼────────────────┬──────────────┐        │
       │   ▼               ▼                ▼              ▼        │
       │  per-wheel     SQLite           leak deque    alerts        │
       │  state dict   tpms_readings   (60s window)   wiring        │
       │  (PSI, ts,     INSERT          appendleft    fire_alert    │
       │   status)                       on each      fire_recovery │
       │                                 frame                      │
       └────┬───────────────┬───────────────┬──────────────┬───────┘
            │               │               │              │
            ▼               ▼               ▼              ▼
     dashboard SSE    batch_sync        events.json    speaker.py
     /sse/slow       (Prometheus       (TPMS_LEAK     speak_tpms_low
     _tpms_payload    remote_write)     event)        speak_tpms_leak
            │               │
            ▼               ▼
     Health page         Grafana
     Alpine x-for        4 time series
     SYSTEM-shape        per metric

       ┌────────────────────────────────────────┐
       │  HardwareSupervisor (Phase 21)         │
       │  probe_usb_vid_pid("0bda:2838") tick   │
       │  → reports PRESENT / MISSING           │
       │  → speaks hw_tpms_radio_missing on tier │
       └────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/shitbox/
├── sync/
│   ├── tpms.py                  # NEW — TPMSService class
│   ├── batch_sync.py            # MODIFIED — _readings_to_metrics adds tpms branch
│   └── capture_sync.py          # unchanged
├── storage/
│   └── database.py              # MODIFIED — _migrate_to_v11, insert_tpms_reading,
│                                #            get_unsynced_tpms_readings, update_tpms_cursor
├── hardware/
│   └── probes.py                # MODIFIED — new probe_usb_vid_pid function
├── capture/
│   └── speaker.py               # MODIFIED — new _CACHED_MESSAGES keys + helpers
├── health/
│   └── alerts.py                # unchanged — reused as-is
├── dashboard/
│   ├── sse.py                   # MODIFIED — _tpms_payload helper, /sse/slow includes it
│   └── static/
│       └── index.html           # MODIFIED — TPMS section in Health modal
├── events/
│   ├── detector.py              # MODIFIED — EventType.TPMS_LEAK enum value
│   └── engine.py                # MODIFIED — TpmsConfig flat fields on EngineConfig,
│                                #            from_yaml_config wiring,
│                                #            UnifiedEngine.__init__ instantiates TPMSService
└── utils/
    └── config.py                # MODIFIED — TpmsConfig dataclass + load_config wiring

config/
└── config.yaml                  # MODIFIED — new tpms: block + tpms_radio hw entry

scripts/
└── install.sh                   # MODIFIED — apt-get install adds rtl-433 librtlsdr-dev

tests/
├── test_tpms_parser.py          # NEW — JSON parsing edge cases
├── test_tpms_alerts.py          # NEW — sustain + transition + recovery wiring
├── test_tpms_leak.py            # NEW — deque-based leak detection
├── test_tpms_subprocess.py      # NEW — mock rtl_433 stdout, restart-on-death
└── test_tpms_database.py        # NEW — schema migration + insert/cursor
```

### Pattern 1: rtl_433 Subprocess Lifecycle (lift from ring_buffer.py)

**What:** Long-running child process producing line-delimited JSON on stdout, verbose chatter on stderr. Must drain stderr or it blocks; must restart on exit; must back off if the USB device disappears.

**When to use:** Any stage that wraps `rtl_433`. The exact pattern is already shipped in `src/shitbox/capture/ring_buffer.py` for ffmpeg.

**Example (adapted from ring_buffer.py lines 740-846, 926-1050):**

```python
# Source: src/shitbox/capture/ring_buffer.py (Phase 16/D-13 ffmpeg pattern)
import os
import subprocess
import threading
import time
from typing import Optional

class TPMSService:
    DRAIN_INTERVAL_S = 2.0          # match ring_buffer's stderr-drain cadence
    DEVICE_MISSING_BACKOFF_S = 30.0
    RESTART_BACKOFF_S = 5.0

    def __init__(self, config, database, sensor_map):
        self.config = config
        self.db = database
        self.sensor_map = sensor_map  # dict[hex_id_str, wheel_position_str]
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

    def _build_cmd(self) -> list[str]:
        # -R 156: only the Abarth-124Spider / VDO TG1C decoder
        # -F json: newline-delimited JSON to stdout
        # -M time:utc: ISO timestamps in the frames
        # -g 30: explicit gain in dB (R820T2 max is 49.6; 30 is sensible for own-car short-range)
        # -f 433.92M: TPMS frequency
        return [
            "rtl_433",
            "-R", "156",
            "-F", "json",
            "-M", "time:utc",
            "-g", str(self.config.gain_db),
            "-f", "433.92M",
        ]

    def _start_subprocess(self) -> None:
        cmd = self._build_cmd()
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,           # parse JSON frames here
            stderr=subprocess.PIPE,           # MUST drain or the process blocks
            text=True,
            bufsize=1,                        # line-buffered stdout
        )
        log.info("tpms_rtl433_started", pid=self._process.pid, cmd=" ".join(cmd))

    def _read_stderr_nonblocking(self) -> str:
        # Lifted verbatim from ring_buffer.py:827-846
        if self._process and self._process.stderr:
            try:
                fd = self._process.stderr.fileno()
                flags = os.get_blocking(fd)
                os.set_blocking(fd, False)
                try:
                    data = b""
                    while True:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            break
                        data += chunk
                finally:
                    os.set_blocking(fd, flags)
                return data.decode(errors="replace")[-500:]
            except Exception:
                pass
        return ""

    def _reader_loop(self) -> None:
        """Read JSON lines from stdout. One line per frame."""
        while self._running:
            if self._process is None or self._process.stdout is None:
                time.sleep(0.5)
                continue
            line = self._process.stdout.readline()
            if not line:
                # EOF — process died. Monitor thread will restart it.
                time.sleep(0.5)
                continue
            try:
                self._handle_frame(line.strip())
            except Exception as e:
                log.warning("tpms_frame_handle_error", error=str(e), line=line[:200])

    def _monitor_loop(self) -> None:
        """Drain stderr + restart on death. Mirrors ring_buffer._health_monitor."""
        while self._running:
            time.sleep(self.RESTART_BACKOFF_S)
            if not self._running:
                break
            try:
                # Always drain stderr — pipe buffer is 64 KB, fills in seconds with -v on
                if self._process is not None and self._process.poll() is None:
                    self._read_stderr_nonblocking()

                # Restart if rtl_433 has exited
                if self._process is not None and self._process.poll() is not None:
                    rc = self._process.returncode
                    stderr = self._read_stderr_nonblocking()
                    log.warning("tpms_rtl433_exited", returncode=rc, stderr=stderr)
                    # USB device check by VID:PID — if missing, back off
                    if not self._sdr_present():
                        hw_state.report_missing("tpms_radio")
                        log.warning(
                            "tpms_sdr_missing",
                            backoff_seconds=self.DEVICE_MISSING_BACKOFF_S,
                        )
                        backoff_end = time.time() + self.DEVICE_MISSING_BACKOFF_S
                        while time.time() < backoff_end and self._running:
                            time.sleep(1.0)
                        continue
                    self._start_subprocess()
            except Exception as e:
                log.error("tpms_monitor_error", error=str(e))
```

### Pattern 2: rtl_433 JSON Frame Shape

The Abarth-124 decoder emits the following keys per frame (verified against upstream `tpms_abarth124.c`):

```json
{
  "time": "2026-04-28T12:34:56Z",
  "model": "Abarth-124Spider",
  "type": "TPMS",
  "id": "550b57d9",
  "flags": "9300",
  "pressure_kPa": 89.7,
  "temperature_C": 22.5,
  "status": 19,
  "mic": "CHECKSUM"
}
```

**Notes:**
- Pressure formula in 22.11 source: `pressure_kPa = press_raw * 1.38` (the comment "1.375" in some search results is a documentation drift; the source code uses 1.38). [CITED: github.com/merbanan/rtl_433/blob/master/src/devices/tpms_abarth124.c]
- Temperature formula: `temperature_C = temp_raw - 50.0`.
- `id` is hex string (lower case, no `0x` prefix). Match exactly to YAML keys.
- `status` integer values from Brain note: `0x93` (147) during fast/active transmit, `0x13` (19) heartbeat, `0x1b` (27) during pressure change.
- `mic` is checksum/CRC validation — always present, frame is already validated by rtl_433 if it appears at all.

**Correction pipeline:**
```
raw_byte -> rtl_433 -> pressure_kPa (× 1.38)
                                       │
                              shitbox: × 2.45 correction
                                       │
                              corrected_kPa
                                       │
                              kPa × 0.145038 = PSI
```

### Pattern 3: rtl_433 stdout/stderr separation (KNOWN UPSTREAM QUIRK)

**What goes wrong:** rtl_433 historically mixes some output between stdout and stderr. Issue #2134 reports `-F` not working in some configurations. [CITED: github.com/merbanan/rtl_433/issues/2134]

**Reality on 22.11:**
- Decoded frames in `-F json` mode go to stdout, one JSON object per line.
- Banner ("rtl_433 version ..."), tuner detection, sample stats, and any decoder warnings go to stderr.
- The pipe buffer for stderr is 64 KB on Linux; at default verbosity rtl_433 writes ~30-100 bytes/sec to stderr (much less than ffmpeg's stats output), so it would take ~10 minutes to fill — but a periodic drain every 2-5 seconds is still mandatory because `-vvv` (debug) raises this dramatically.

**Recommended invocation (minimal stderr noise, JSON-only on stdout):**
```bash
rtl_433 -R 156 -F json -M time:utc -g 30 -f 433.92M
```

**What we don't try:** there is no documented flag in 22.11 to suppress the startup banner or the per-second sample-rate log line. Both go to stderr and are harmless once drained. Do not use `2>/dev/null` on the subprocess — that hides genuine errors (USB problems, decoder failures, frequency mismatches).

### Pattern 4: Schema Migration (CORRECTING THE CONTEXT.MD ASSUMPTION)

**CRITICAL CORRECTION:** `28-CONTEXT.md` D-Discretion says "bump SCHEMA_VERSION 3 → 4". This is **wrong** — it was written from old memory. The current value at `src/shitbox/storage/database.py:16` is:

```python
SCHEMA_VERSION = 10
```

Migrations 1 through 10 are already shipped. The TPMS migration is **`_migrate_to_v11`**, and `SCHEMA_VERSION` becomes **11**.

**Pattern (mirrors `_migrate_to_v6` which adds `notes` and `fuel_stops` tables — `database.py:298-330`):**

```python
def _migrate_to_v11(self, conn: sqlite3.Connection) -> None:
    """Add tpms_readings table for Phase 28 TPMS integration."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tpms_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            sensor_id TEXT NOT NULL,
            wheel TEXT NOT NULL,
            pressure_psi REAL NOT NULL,
            temperature_c REAL NOT NULL,
            status INTEGER,
            raw_pressure_kpa REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tpms_timestamp ON tpms_readings(timestamp_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tpms_wheel ON tpms_readings(wheel)"
    )
    conn.commit()
    log.info("migrated_to_v11", tables=["tpms_readings"])
```

**Wiring in `Database.connect()` (`database.py:188-220`):**
```python
if current_version < 11:
    self._migrate_to_v11(conn)
```

**Why a separate table, not new columns on `readings`:** the `readings` table already has 30+ columns covering 9 sensor types. The project precedent for sensor-shapes-that-don't-fit is dedicated tables: `notes`, `fuel_stops`, `driver_stints`, `waypoints_reached`, `trip_state`. TPMS has six fields nobody else cares about (sensor_id hex, wheel label, PSI, °C, status flags, raw kPa) — same logic applies.

### Pattern 5: Prometheus Exposition with Wheel Labels

The existing encoder `src/shitbox/sync/prometheus_write.py:74-131` accepts `(metric_name, labels_dict, value, timestamp_ms)` tuples. Labels become `{wheel="front-driver"}` natively — there's no special handling needed.

**Two options for cursor:**

**Option A (recommended):** New cursor `prometheus_tpms` and a new method on `Database`:
```python
def get_unsynced_tpms_readings(self, batch_size: int = 1000) -> list[dict]:
    """Get TPMS rows past the prometheus_tpms cursor."""
    # Mirrors get_unsynced_readings (database.py:556-596) but on tpms_readings.
```

`BatchSyncService._sync_batch` gains a second sync arm that pulls TPMS rows, builds metrics, sends, advances the `prometheus_tpms` cursor.

**Option B:** Stuff TPMS rows into the existing `readings` table with `sensor_type='tpms'` and per-wheel `sensor_id`, then handle in `_readings_to_metrics`. This is uglier but uses the existing cursor.

**Recommend A.** Reasoning: TPMS rows come at 4 Hz steady-state (4 wheels × 1 frame/sec), the `readings` cursor is already busy with 25 Hz IMU-heading + 1 Hz everything else, mixing high-cardinality wheel labels into the existing metric path adds risk to a code path Phase 15 just shipped, and a dedicated cursor is the same idiom we'd use if anyone added a second sync target.

**Metric format produced:**
```python
# In a new TPMS-aware encoder branch (or new method in BatchSyncService):
metrics.append((
    "shitbox_tpms_pressure_psi",
    {"car": "shitbox", "job": "shitbox-mqtt-exporter", "wheel": row["wheel"]},
    row["pressure_psi"],
    timestamp_ms,
))
metrics.append((
    "shitbox_tpms_temperature_c",
    {"car": "shitbox", "job": "shitbox-mqtt-exporter", "wheel": row["wheel"]},
    row["temperature_c"],
    timestamp_ms,
))
```

### Pattern 6: Dashboard SSE Payload + Alpine `x-for`

**Backend (`dashboard/sse.py`):** Add `_tpms_payload()` helper alongside `_system_conditions_payload()` and `_hardware_payload()`. Service registers a snapshot callable at engine wire-up time, like the alerts module's `snapshot()`.

**Shape (mirrors `_system_conditions_payload` lines 110-151):**
```python
def _tpms_payload() -> List[Dict[str, Any]]:
    """Render four wheel slots for /sse/slow.

    Always emits all four rows in the order FD, FP, RD, RP so the frontend
    always has a complete set. State is derived from TPMSService.snapshot():
      - never seen          → "no_data"
      - last frame > 5 min  → "stale"
      - leak active         → "critical"  (also covers ≤25 PSI sustained)
      - 25 < PSI ≤ 28       → "low"
      - PSI > 28            → "ok"
    """
    snap = tpms_service.snapshot() if tpms_service else {}
    out: List[Dict[str, Any]] = []
    for wheel_label, position in (
        ("FD", "front-driver"),
        ("FP", "front-passenger"),
        ("RD", "rear-driver"),
        ("RP", "rear-passenger"),
    ):
        st = snap.get(position)
        out.append({
            "label": wheel_label,
            "position": position,
            "psi": st["psi"] if st else None,
            "state": st["state"] if st else "no_data",
            "since_ms": st["since_ms"] if st else None,
        })
    return out
```

**Wired into `/sse/slow` JSON (`sse.py:246-281`):** add `"tpms": _tpms_payload()` to the payload dict alongside `"hardware"` and `"system_conditions"`.

**Frontend (`static/index.html`):** new section in the Health modal, mirroring the SYSTEM template at lines 412-422:
```html
<!-- TPMS section — sits between SYSTEM and HARDWARE in the Health modal -->
<div class="hw-section-eyebrow" style="margin-top: 12px;">TPMS</div>
<template x-for="row in tpms" :key="row.position">
  <div class="hw-row hw-row-lg" :class="'tpms-' + row.state">
    <span class="hw-glyph" x-text="tpmsGlyph(row.state)"></span>
    <span class="hw-label" x-text="row.label"></span>
    <span class="hw-state"
          x-text="row.psi !== null ? row.psi.toFixed(1) + ' PSI' : '—'"></span>
    <span class="hw-since"
          x-text="row.state.toUpperCase() + (row.since_ms ? ' · ' + sinceText(row.since_ms) : '')"></span>
  </div>
</template>
```

**Alpine state additions:** add `tpms: []` to `dashboard()` return alongside `hardware: []` and `systemConditions: []` (line 469-470). On `/sse/slow` message, set `this.tpms = d.tpms || []`.

### Pattern 7: Alert Wiring (`health/alerts.py` reuse)

The `alerts.py` helper (Phase 15) takes a subtype string. Eight subtypes per phase (one per wheel × {LOW, LEAK}):

```python
# Subtype convention: TPMS_<TYPE>_<WHEEL>
# Examples:
#   TPMS_LOW_FRONT_DRIVER            (low pressure sustained, fire)
#   TPMS_LOW_FRONT_DRIVER_RESTORED   (recovery_subtype)
#   TPMS_LEAK_FRONT_DRIVER           (rapid deflation)
#   TPMS_LEAK_FRONT_DRIVER_CLEARED   (recovery — wheel re-stable)
```

**Sustain semantics (REQ 7 — low pressure 28/25 PSI):**
- At 1 frame/sec/wheel, `sustain_required=2` means "two consecutive frames below threshold" → ~2 seconds latency. Acceptance criterion is "TTS within 5 seconds" so 2 is fine.
- Yellow (28 PSI) fires Health-page banner only — NOT a TTS alert. Pass `tts_fn=None` to `fire_alert`.
- Red (25 PSI) fires Health-page banner + TTS. Pass `speak_tpms_low(position)` as the side-effect closure.

**Wiring (per-wheel, on every frame):**
```python
# In TPMSService._handle_frame, after computing psi for this wheel:
position = self.sensor_map[id_hex]  # "front-driver"
key_low = f"TPMS_LOW_{position.upper().replace('-', '_')}"
key_leak = f"TPMS_LEAK_{position.upper().replace('-', '_')}"

# Low pressure (red threshold) — sustained
red_active = psi <= self.config.low_pressure_red_psi
def _tts_low():
    speak_tpms_low(position)
alerts.fire_alert(
    key_low,
    red_active,
    f"{position.upper()} TYRE LOW PRESSURE",
    _tts_low,
    sustain_required=2,
)
alerts.fire_recovery(
    key_low,
    red_active,
    f"{position.upper()} TYRE PRESSURE RESTORED",
    lambda: speak_tpms_restored(position),
    sustain_required=2,
    recovery_subtype=f"{key_low}_RESTORED",
)

# Leak alert — single-shot when delta >= 5 PSI in 60s
if leak_detected:
    alerts.fire_alert(
        key_leak,
        True,
        f"TYRE LEAKING, {position.upper()}",
        lambda: speak_tpms_leak(position),
        sustain_required=1,  # leak is instantaneous, no sustain
    )
# Recovery for leak: when wheel has been stable (no further leak) for 60s,
# fire_recovery with active=False.
```

**Yellow (28 PSI) state is tracked separately for the Health-page banner — it does NOT use `alerts.py` (which is for sustain-or-die alerts):**
```python
# Track yellow state in TPMSService.snapshot() output, frontend renders the
# yellow banner from the SSE payload, not from alerts.snapshot().
```

This keeps the `alerts.py` module focused on critical-with-recovery semantics; the yellow-warning state is just a colour on the Health card.

### Pattern 8: Leak-Detection Sliding Window (deque approach)

**Per-wheel `collections.deque` indexed by position:**

```python
from collections import deque
import time

class TPMSService:
    def __init__(self, ...):
        # Each wheel gets a deque of (monotonic_ts, psi) tuples.
        # maxlen sized to prevent unbounded growth; time check still rules.
        # 1 frame/sec/wheel × 60s = 60 entries; double it for headroom.
        self._leak_windows: dict[str, deque[tuple[float, float]]] = {
            position: deque(maxlen=120)
            for position in ("front-driver", "front-passenger",
                             "rear-driver", "rear-passenger")
        }

    def _detect_leak(self, position: str, psi_now: float) -> bool:
        """Append the new sample, prune old, return True if PSI dropped
        ≥leak_drop_psi within leak_window_seconds."""
        now = time.monotonic()
        win = self._leak_windows[position]
        win.append((now, psi_now))
        # Prune entries older than the window. deque does not support
        # arbitrary removal cheaply, but we only need to skip them.
        cutoff = now - self.config.leak_window_seconds
        # Find max PSI within the window (inclusive of `now` entry)
        max_psi_in_window = max(
            psi for ts, psi in win if ts >= cutoff
        )
        # Drop is leak if max - current >= threshold
        return (max_psi_in_window - psi_now) >= self.config.leak_drop_psi
```

**Thread safety:** `deque.append` is GIL-atomic in CPython [CITED: bugs.python.org/issue15329]. The `max(...)` iteration reads a consistent view because nothing else writes between `append` and the iteration (single producer per wheel — the rtl_433 reader thread). The Pi 5 CPython 3.9 build is the standard GIL build; the no-GIL build (PEP 703) is not on bookworm. Safe.

**Why not SQLite query:** the existing `readings` cursor already runs at 4 Hz combined-wheel rate; querying `tpms_readings WHERE timestamp > now-60s AND wheel=?` four times per second adds DB pressure for no benefit. The deque is local memory, no lock acquisition, no IO.

### Pattern 9: Stale-Sensor Detection

**Approach:** Track `last_seen` per wheel as `time.monotonic()` floats. The SSE payload assembly already runs at 1 Hz on `/sse/slow`. In `_tpms_payload`, mark a wheel STALE if `now - last_seen > 5*60`:

```python
# In TPMSService.snapshot() returning per-wheel state for SSE:
def snapshot(self) -> dict[str, dict[str, Any]]:
    now = time.monotonic()
    out = {}
    for position, st in self._wheels.items():
        if st.last_seen is None:
            out[position] = {"state": "no_data", "psi": None, "since_ms": None}
            continue
        age = now - st.last_seen
        if age > self.config.stale_timeout_seconds:
            state = "stale"
        elif st.psi <= self.config.low_pressure_red_psi:
            state = "critical"
        elif st.psi <= self.config.low_pressure_yellow_psi:
            state = "low"
        else:
            state = "ok"
        out[position] = {
            "state": state,
            "psi": round(st.psi, 1),
            "since_ms": int(age * 1000),
        }
    return out
```

**Stale clears automatically on next frame** because `last_seen` updates in `_handle_frame`. No TTS for STALE per SPEC.md REQ 9.

### Pattern 10: Hardware Manifest USB VID:PID Probe

The current `probe_usb_path` (`hardware/probes.py:40-43`) only checks for a `/dev/X` symlink. RTL-SDR doesn't get a stable `/dev` node by default, but a VID:PID match works.

**New probe function:**
```python
def probe_usb_vid_pid(vid_pid: str) -> bool:
    """Return True if a USB device matching vid_pid is enumerated.

    vid_pid is "VVVV:PPPP" hex (e.g. "0bda:2838" for RTL2832U).
    Uses lsusb output (already on the Pi). Multiple matches return True;
    we don't care which physical port.
    """
    try:
        result = subprocess.run(
            ["lsusb"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            log.warning("lsusb_failed", returncode=result.returncode)
            return False
        # lsusb format: "Bus 001 Device 005: ID 0bda:2838 Realtek Semiconductor Corp."
        return f"ID {vid_pid.lower()}" in result.stdout
    except FileNotFoundError:
        log.warning("lsusb_not_found", hint="apt install usbutils")
        return False
    except subprocess.TimeoutExpired:
        return False
```

**Manifest dispatch:** extend `HardwareSupervisor._run_probe` in `hardware/supervisor.py:86-105` with a new branch:
```python
if d.bus == "usb_vid_pid":
    return hw_probes.probe_usb_vid_pid(d.path or "")
    # path field reused — manifest entry uses path: "0bda:2838"
```

**OR** keep `bus: usb` and use a heuristic on `path`: if the path contains `:` and lacks `/dev/`, treat as VID:PID. Cleaner: new bus value `usb_vid_pid` so the dispatch is explicit. Up to the planner.

**HardwareDeviceConfig** in `utils/config.py:113-127` already has `path: Optional[str]`, no schema change needed. Just a new bus value `usb_vid_pid`.

**Manifest entry to add to `config.yaml`:**
```yaml
- role: tpms_radio
  bus: usb_vid_pid
  path: "0bda:2838"
  criticality: best_effort
  description: "Nooelec NESDR Smart v5 (RTL2832U + R820T2)"
```

### Anti-Patterns to Avoid

- **Don't run `rtl_433` as a separate systemd unit.** The shitbox daemon owns the lifecycle. A separate unit means orphan reaping, log scattering, two restart strategies. ring_buffer manages ffmpeg in-process; same here.
- **Don't add a `pyrtlsdr` dependency.** Locked OUT in D-10. Adds a librtlsdr Python binding, an extra failure mode, and zero benefit — rtl_433 already does the radio work.
- **Don't shell out to `bash -c` to pipe rtl_433 through anything.** Direct `subprocess.Popen` with `stdout=PIPE, stderr=PIPE` and read line-by-line. Shells add quoting bugs and zombie children.
- **Don't `2>/dev/null` the stderr.** Hides genuine RF errors. Drain it instead.
- **Don't add a column to the `readings` table for TPMS fields.** Use a dedicated `tpms_readings` table — same precedent as `notes`/`fuel_stops`.
- **Don't speak the PSI value in TTS.** Locked in D-04 — numbers articulate poorly in a noisy cabin.
- **Don't trigger dashcam-buffer save on TPMS_LEAK.** Locked OUT in SPEC.md "Out of scope" — leak data alone tells the story.
- **Don't fire the yellow-low alert through `alerts.py`.** That helper is for critical sustain+recovery semantics. Yellow is a Health-page colour only.
- **Don't keep an open USB handle in Python.** rtl_433 opens it; we never touch it. If we need to release it forcibly, `fuser -k` on the USB device path (mirrors ring_buffer's pattern at `ring_buffer.py:752`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| FSK Manchester demod for 433 MHz | Custom Python decoder | `rtl_433 -R 156` | Months of work; loses upstream maintenance for the ~50 other TPMS profiles we'd want one day. |
| Subprocess restart-on-death | Custom watchdog | Lift `ring_buffer._health_monitor` | Already shipped, already battle-tested for ffmpeg, same shape applies. |
| Sliding-window leak detection | SQL query each frame | `collections.deque(maxlen=N)` | 60-sample buffer; GIL-atomic appends; no IO. |
| Per-wheel alert state machine | Custom dict + flag tracking | `health/alerts.py` `fire_alert` / `fire_recovery` | Phase 15 helper handles sustain + once-on-transition + recovery suffix. Eight subtypes (4 wheels × 2 alert types) wires in cleanly. |
| TTS engine fall-through | Custom Piper/espeak switch | `capture/speaker.py` `_enqueue` | Already does Piper → espeak-ng → silent. Add new helpers, don't rewrite the engine. |
| Hardware presence + re-adoption | Custom polling loop | `HardwareSupervisor` | Phase 21 already speaks missing/restored, handles backoff, calls reprobe callback. Just add new probe + manifest entry. |
| Prometheus protobuf encoding | Direct protobuf | `prometheus_write.encode_remote_write` | Already supports labels dict; no special handling needed. |
| Schema migrations | Manual ALTER TABLE | `Database._migrate_to_vN` pattern | Existing 10-migration sequence handles version detection + idempotent CREATE IF NOT EXISTS. |
| USB VID:PID detection | Custom udev rule + sysfs walk | `lsusb` + grep | One subprocess call, one line of output to match. udev rules are deployed-once-and-forgotten; lsusb runs per probe-tick. |

**Key insight:** every novel piece of work in this phase is `rtl_433`-shaped. Everything around it has a precedent in the repo. Hand-rolling alerts or alert wiring would re-litigate decisions Phase 15 already made.

## Runtime State Inventory

This phase is greenfield (new functionality, no rename/refactor). The Runtime State Inventory section is **omitted** because nothing existing is being moved or renamed.

The closest thing to runtime state is: the new `tpms_readings` table will not be present on databases created before this phase ships. The migration path handles that automatically (Pattern 4 above).

## Common Pitfalls

### Pitfall 1: rtl_433 stderr pipe fills, child blocks

**What goes wrong:** rtl_433 emits stats and decoder noise to stderr. If nothing reads it, the OS pipe buffer fills (~64 KB on Linux), the next stderr write blocks, and the child process freezes. This is the same root cause as the ffmpeg stalls from March 2026 (memory: ffmpeg-stability solved Mar 23 — pipe-buffer drain at 2 Hz).

**Why it happens:** Python doesn't read `subprocess.PIPE` automatically. Without an active reader, kernel buffers up to PIPE_BUF and then blocks the writer.

**How to avoid:** Drain `stderr` non-blockingly every 2 seconds in the monitor thread. Lift the function from `ring_buffer.py:827-846` verbatim.

**Warning signs:**
- rtl_433 process appears alive (`poll() is None`) but stops emitting frames on stdout.
- `top` shows rtl_433 stuck in `D` or sleeping state.
- No new lines from `readline()` for >10 seconds despite known live transmissions.

### Pitfall 2: USB hot-unplug doesn't restart cleanly

**What goes wrong:** rtl_433 doesn't survive USB unplug — it exits with `usb_open error -4` or similar. [CITED: github.com/merbanan/rtl_433/issues/1899] On Linux, sometimes the USB controller hangs and even replug doesn't bring the device back.

**Why it happens:** librtlsdr opens the USB handle once and assumes it stays. Hot-unplug invalidates the handle; the next read fails; rtl_433 exits.

**How to avoid:**
- Detect exit via `poll()` in the monitor thread.
- Probe `lsusb` for the VID:PID before respawning.
- If absent, mark `tpms_radio` MISSING in HardwareState, sleep 30s, re-probe.
- If present, respawn rtl_433 (mirror `ring_buffer._health_monitor` lines 980-1011).
- If 3+ consecutive restarts without producing any frames, escalate to an INFO log so the driver isn't getting nag-spammed.

**Warning signs:** `tpms_rtl433_exited` log lines repeating in rapid succession. SDR PRESENT but no frames decoded → antenna/RF issue, not subprocess.

### Pitfall 3: Pressure correction × 2.45 may drift between sensor batches

**What goes wrong:** The × 2.45 factor was empirically calibrated against four specific aftermarket sensors at 31-32 PSI. A future sensor replacement (different manufacturer, different LSB) could shift the factor. Tony will see "wrong PSI" reported.

**Why it happens:** rtl_433's TG1C decoder uses 1.38 kPa/count assuming the original Abarth/VDO factory sensor. Aftermarket sensors with the same protocol can use a different LSB without changing the protocol ID — the source comment "to be checked, VDO says 450/900kPa" is the upstream maintainer flagging this.

**How to avoid:**
- Make the correction factor a single YAML field `tpms.pressure_correction_factor` with default `2.45`.
- Log the corrected and raw values together: `log.info("tpms_frame_received", wheel="front-driver", pressure_psi=32.1, raw_kpa=89.7, corrected_kpa=219.8)`.
- Document recalibration procedure in a docstring on `TpmsConfig.pressure_correction_factor`.

**Warning signs:** stick-gauge reference vs. dashboard PSI differs by >3 PSI consistently across all four wheels.

### Pitfall 4: Alpine `x-for` losing reactivity on TPMS payload

**What goes wrong:** Alpine's `x-for` reactivity depends on a stable `:key`. If `_tpms_payload` order changes between SSE messages, Alpine re-renders all rows on every tick — flickering on the screen.

**Why it happens:** Python `dict` iteration order is insertion-ordered (3.7+) but easy to break (e.g. building from `set()`, sorting on a different key).

**How to avoid:**
- Build the payload list in a deterministic fixed order: FD, FP, RD, RP. (Pattern 6 above does this.)
- Use `:key="row.position"` (the long-form unique label) — never `:key="row.label"` since `FD` is short and could collide with other tables in the same DOM.

**Warning signs:** Health page wheels jump positions or flicker. Alpine throws "duplicate key" warnings in the browser console.

### Pitfall 5: rtl_433 protocol 156 listing on apt vs. master

**What goes wrong:** Debian bookworm has `rtl-433 22.11`. Search results in 2025 sometimes reference protocol numbers from `master` (24.x, 25.x) which have shifted by ±1-2 as new decoders were added/removed. If the protocol number changes, `-R 156` would silently match the wrong decoder OR fail.

**Why it happens:** rtl_433 protocol numbers are not stable across versions — they're list indices, reassigned on every release.

**How to avoid:**
- After install, run `rtl_433 -R help 2>&1 | grep -i abarth` and verify the line says `[156]  Abarth-124Spider / VDO-TG1C TPMS`.
- If the number shifts, update the YAML config: `tpms.rtl433_protocol_id: 156`. Make it configurable so a future apt upgrade doesn't break us silently.
- Add a Wave 0 boot-time check: TPMSService logs the resolved protocol ID at startup. If `rtl_433 -R help` shows the Abarth-124 line at a different index, log a CRITICAL and refuse to start the rtl_433 subprocess.

**Warning signs:** rtl_433 starts cleanly, decodes nothing, no error messages. Could be RF issue OR wrong protocol.

### Pitfall 6: Schema migration runs on every boot if version-tracking misses

**What goes wrong:** `database.py:182-186` reads `MAX(version)` from `schema_version`. If the migration runs but the `INSERT INTO schema_version (version) VALUES (?)` fails (rare but possible on a corrupted DB), every boot will re-run the migration. Idempotent CREATE TABLE IF NOT EXISTS is fine for `tpms_readings` (no-op on second run), but adding new columns later would error.

**Why it happens:** Existing pattern at lines 215-220 only inserts the version row if `current_version < SCHEMA_VERSION` AT THE END of the function. If a migration crashes partway, version stays old. (Phase 8 fix on `_migrate_to_v9` shows this isn't theoretical — the column-already-exists try/except at line 363 was added because of this.)

**How to avoid:** Wrap the migration in `try`/`except sqlite3.OperationalError` for the CREATE TABLE — match the existing pattern in `_migrate_to_v6` (`database.py:298-330`). Log the migration outcome so a re-run is visible.

**Warning signs:** `migrated_to_v11` log lines appearing on every daemon start (not just the first one).

### Pitfall 7: Threading on the alerts module

**What goes wrong:** `health/alerts.py` (lines 11-15) explicitly states the helper is single-writer-per-subtype. Eight TPMS subtypes (4 wheels × 2 alert types) all share the same `_state` dict, but each subtype only has one writer (the rtl_433 reader thread).

**Why it happens:** Module-level dict rebind in `_rebind` is GIL-atomic for the FINAL assignment, but the read-modify-write inside `fire_alert` is NOT atomic across multiple threads writing the SAME subtype. Reading `_state[subtype]`, modifying, writing back → two threads racing the same key would lose updates.

**How to avoid:**
- Single-thread the alerts wiring: only the TPMSService reader thread calls `fire_alert` / `fire_recovery`.
- Don't sprinkle TPMS alert calls across the dashboard SSE thread or the batch_sync thread.
- The existing `alerts.py` docstring explicitly calls this out at line 11-15.

**Warning signs:** Alert fires intermittently or fires twice. `alerts.snapshot()` shows inconsistent `fired`/`active` flags.

### Pitfall 8: Pi 5 USB power budget

**What goes wrong:** RTL-SDR draws ~250 mA at full sample rate. Front + cabin cameras are already drawing several hundred mA. Without `usb_max_current_enable=1` in `/boot/firmware/config.txt`, the Pi 5 caps total USB at 600 mA total and randomly drops devices.

**Why it happens:** Pi 5 default USB current limit is 600 mA across all ports. Setting the flag enables 1.6 A.

**How to avoid:**
- Add a check to `scripts/install.sh`: grep for `usb_max_current_enable=1` in `/boot/firmware/config.txt`, append if missing, prompt for reboot.
- Document in the SPEC.md constraint already noted.

**Warning signs:** RTL-SDR enumerates briefly then disappears. Cameras reset randomly. `dmesg` shows `over-current detected` lines.

## Code Examples

### TpmsConfig dataclass (`utils/config.py` — new)

```python
# Source: extends src/shitbox/utils/config.py pattern (e.g. ParticulateConfig at line 158-164)
@dataclass
class TpmsSensorMapEntry:
    """Single sensor-id → wheel-position mapping."""
    id: str = ""             # hex string, e.g. "550b57d9"
    position: str = ""       # "front-driver" / "front-passenger" / "rear-driver" / "rear-passenger"


@dataclass
class TpmsConfig:
    """TPMS service configuration.

    Receives 433 MHz TPMS frames via rtl_433 -R 156, applies pressure
    correction, persists to SQLite, and drives Health-page + Grafana exposition.
    """
    enabled: bool = False                            # off by default; flips true once SDR is fitted
    rtl433_protocol_id: int = 156                    # Abarth-124Spider / VDO-TG1C
    rf_frequency_hz: int = 433920000
    rf_gain_db: int = 30                             # R820T2: 0=auto; 30 = sensible default for short-range own-car
    pressure_correction_factor: float = 2.45         # empirical, see Brain note 2026-04-28
    low_pressure_yellow_psi: float = 28.0
    low_pressure_red_psi: float = 25.0
    leak_window_seconds: float = 60.0
    leak_drop_psi: float = 5.0
    stale_timeout_seconds: float = 300.0
    sustain_required: int = 2                        # frames below threshold before red fires
    sensors: List[TpmsSensorMapEntry] = field(default_factory=list)

    @property
    def sensor_map(self) -> dict[str, str]:
        """Return {hex_id: position} dict for fast lookup."""
        return {s.id.lower(): s.position for s in self.sensors if s.id and s.position}
```

**YAML (`config/config.yaml` — new block):**

```yaml
tpms:
  enabled: true
  rtl433_protocol_id: 156
  rf_frequency_hz: 433920000
  rf_gain_db: 30
  pressure_correction_factor: 2.45  # × actual factor; rtl_433 22.11 decoder is wrong by this
  low_pressure_yellow_psi: 28
  low_pressure_red_psi: 25
  leak_window_seconds: 60
  leak_drop_psi: 5
  stale_timeout_seconds: 300
  sustain_required: 2
  sensors:
    - id: "550b57d9"
      position: front-driver
    - id: "550d14ed"
      position: rear-driver
    - id: "550b5d8a"
      position: rear-passenger
    - id: "54d96e8f"
      position: front-passenger

# Add to hardware: devices: list:
hardware:
  devices:
    # ... existing entries ...
    - role: tpms_radio
      bus: usb_vid_pid
      path: "0bda:2838"
      criticality: best_effort
      description: "Nooelec NESDR Smart v5 (RTL2832U + R820T2)"
```

### speak_tpms_low / speak_tpms_leak (`capture/speaker.py` — new helpers)

```python
# Source: matches existing speak_*() pattern at speaker.py:391-596
_TPMS_POSITION_TEXT: dict[str, str] = {
    "front-driver": "front driver",
    "front-passenger": "front passenger",
    "rear-driver": "rear driver",
    "rear-passenger": "rear passenger",
}

# Pre-cached fixed messages — added to _CACHED_MESSAGES dict at speaker.py:47-77
_TPMS_CACHED_MESSAGES = {
    "tpms_low_front_driver": "Front driver tyre low pressure.",
    "tpms_low_front_passenger": "Front passenger tyre low pressure.",
    "tpms_low_rear_driver": "Rear driver tyre low pressure.",
    "tpms_low_rear_passenger": "Rear passenger tyre low pressure.",
    "tpms_leak_front_driver": "Tyre leaking, front driver.",
    "tpms_leak_front_passenger": "Tyre leaking, front passenger.",
    "tpms_leak_rear_driver": "Tyre leaking, rear driver.",
    "tpms_leak_rear_passenger": "Tyre leaking, rear passenger.",
    "tpms_restored_front_driver": "Front driver tyre pressure restored.",
    "tpms_restored_front_passenger": "Front passenger tyre pressure restored.",
    "tpms_restored_rear_driver": "Rear driver tyre pressure restored.",
    "tpms_restored_rear_passenger": "Rear passenger tyre pressure restored.",
}


def speak_tpms_low(position: str) -> None:
    """Announce sustained low pressure on a single wheel.

    Suppressed during the boot grace period (matches speak_thermal_warning shape).
    """
    if not _should_alert():
        return
    key = f"tpms_low_{position.replace('-', '_')}"
    text = _CACHED_MESSAGES.get(key)
    if text:
        _enqueue(text)


def speak_tpms_leak(position: str) -> None:
    """Announce rapid deflation (≥5 PSI / 60s) on a single wheel.

    Suppressed during the boot grace period.
    """
    if not _should_alert():
        return
    key = f"tpms_leak_{position.replace('-', '_')}"
    text = _CACHED_MESSAGES.get(key)
    if text:
        _enqueue(text)


def speak_tpms_restored(position: str) -> None:
    """Announce that a previously-low wheel has recovered."""
    if not _should_alert():
        return
    key = f"tpms_restored_{position.replace('-', '_')}"
    text = _CACHED_MESSAGES.get(key)
    if text:
        _enqueue(text)
```

### EventType.TPMS_LEAK (`events/detector.py` — new value)

```python
# Source: append to existing class at events/detector.py:15-22
class EventType(Enum):
    """Types of detected events."""
    HARD_BRAKE = "hard_brake"
    BIG_CORNER = "big_corner"
    ROUGH_ROAD = "rough_road"
    HIGH_G = "high_g"
    MANUAL_CAPTURE = "manual_capture"
    TPMS_LEAK = "tpms_leak"   # NEW — Phase 28
```

**Note:** `save_event` (`events/storage.py:91-150`) takes an `Event` object whose `event_type` field is `EventType`. TPMS_LEAK events have no IMU samples — pass an empty list. The CSV file will still be created (empty) for shape consistency, or you can short-circuit the CSV write for non-IMU events. Recommend letting it write empty CSV — the existing rsync + events.json path doesn't care.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| CC1101 + ESP32-S3 RF receiver (planned but never built) | rtl_433 + RTL-SDR USB dongle | 2026-04-28 (Brain note) | Path A planning abandoned; aftermarket kit decoded cleanly via rtl_433 protocol 156. CC1101 hardware deferred to "spare parts" pile. |
| Per-sensor calibration table (planned in earlier discussion) | Single global × 2.45 correction | 2026-04-28 (locked in CONTEXT.md D-Discretion / SPEC.md Boundary Keeper round) | Simpler config, accuracy tradeoff documented (±3 PSI). Refine if a future bench session shows individual sensor drift. |
| Patching rtl_433 upstream | Apply correction in shitbox config | 2026-04-28 (locked OUT of scope) | Avoids upstream PR overhead and version drift. Can be revisited once calibration is sub-PSI. |

**Deprecated/outdated:**
- ESP32-S3 OCR fallback (read TPMS LCD via camera) — abandoned 2026-04-28; rtl_433 worked cleanly so OCR not needed.
- pyrtlsdr Python binding — never adopted; no longer relevant since rtl_433 is the boundary.

## Environment Availability

| Dependency | Required By | Available on Pi today | Version | Fallback |
|---|---|---|---|---|
| `rtl-433` | rtl_433 subprocess | ✗ (will install via apt) | 22.11-1 (bookworm) | None — phase blocked without it |
| `librtlsdr0` | rtl-433 runtime dep | ✗ (apt pulls in) | 0.6.0+ (bookworm) | None |
| `lsusb` | hardware probe | ✓ | from usbutils | None — apt installs if missing |
| `subprocess` (stdlib) | TPMSService | ✓ (Python 3.9) | stdlib | None |
| `collections.deque` (stdlib) | leak detection | ✓ | stdlib | None |
| `usb_max_current_enable=1` flag | RTL-SDR power budget | UNKNOWN — needs `grep /boot/firmware/config.txt` | n/a | If absent: install.sh appends + prompts reboot |
| RTL-SDR hardware | radio reception | ✗ (Nooelec NESDR Smart v5 ordered, arrives 2026-04-30) | n/a | None — phase 28 doesn't ship without hardware |

**Missing dependencies with no fallback:**
- `rtl-433` package — install.sh must add it. Without rtl-433 the daemon CAN start (TPMSService gracefully no-ops if `which rtl_433` fails), but no frames are received.
- RTL-SDR hardware — without the dongle the manifest probe reports MISSING, supervisor records best_effort offline, daemon continues. Acceptance criteria "Unplug → MISSING; replug → restored" exercises this fallback.

**Missing dependencies with fallback:**
- USB current flag — install.sh detects + appends + warns about reboot. Boot continues either way; just risks USB drops under load.

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | `pytest` 7.x (already in `pyproject.toml [dev]`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing) |
| Quick run command | `pytest tests/test_tpms_*.py -x` |
| Full suite command | `pytest` |
| Phase gate | Full suite green before `/gsd-verify-work` |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command | File |
|---|---|---|---|---|
| 1 | rtl_433 frame parsed, dispatched | unit | `pytest tests/test_tpms_parser.py::test_valid_abarth_frame -x` | ❌ Wave 0 |
| 1 | unknown sensor ID logged + dropped | unit | `pytest tests/test_tpms_parser.py::test_unknown_sensor_drop -x` | ❌ Wave 0 |
| 1 | malformed JSON line tolerated | unit | `pytest tests/test_tpms_parser.py::test_malformed_json_skipped -x` | ❌ Wave 0 |
| 2 | × 2.45 correction applied | unit | `pytest tests/test_tpms_parser.py::test_pressure_correction -x` | ❌ Wave 0 |
| 2 | kPa → PSI conversion | unit | `pytest tests/test_tpms_parser.py::test_kpa_to_psi -x` | ❌ Wave 0 |
| 3 | wheel position lookup | unit | `pytest tests/test_tpms_parser.py::test_wheel_mapping -x` | ❌ Wave 0 |
| 4 | schema migration v10 → v11 | integration | `pytest tests/test_tpms_database.py::test_migrate_v11 -x` | ❌ Wave 0 |
| 4 | insert + retrieve roundtrip | integration | `pytest tests/test_tpms_database.py::test_insert_retrieve -x` | ❌ Wave 0 |
| 5 | metric format with wheel label | unit | `pytest tests/test_tpms_database.py::test_prometheus_metric_shape -x` | ❌ Wave 0 |
| 5 | cursor advance | integration | `pytest tests/test_tpms_database.py::test_cursor_advance -x` | ❌ Wave 0 |
| 6 | _tpms_payload always 4 rows | unit | `pytest tests/test_dashboard.py::test_tpms_payload_four_wheels -x` | ❌ Wave 0 (extends existing test_dashboard.py) |
| 6 | NO DATA before first frame | unit | `pytest tests/test_dashboard.py::test_tpms_payload_no_data -x` | ❌ Wave 0 |
| 7 | red threshold fires once on transition | unit | `pytest tests/test_tpms_alerts.py::test_low_pressure_red_fires -x` | ❌ Wave 0 |
| 7 | yellow does NOT fire TTS | unit | `pytest tests/test_tpms_alerts.py::test_yellow_no_tts -x` | ❌ Wave 0 |
| 7 | _RESTORED on re-inflation | unit | `pytest tests/test_tpms_alerts.py::test_low_pressure_restored -x` | ❌ Wave 0 |
| 8 | leak fires on ≥5 PSI / 60s | unit | `pytest tests/test_tpms_leak.py::test_leak_detected -x` | ❌ Wave 0 |
| 8 | slow deflation does not fire | unit | `pytest tests/test_tpms_leak.py::test_slow_deflation_no_leak -x` | ❌ Wave 0 |
| 8 | TPMS_LEAK event written | integration | `pytest tests/test_tpms_leak.py::test_leak_writes_event_json -x` | ❌ Wave 0 |
| 9 | wheel goes STALE after 5 min | unit | `pytest tests/test_tpms_alerts.py::test_stale_after_5min -x` | ❌ Wave 0 |
| 9 | STALE clears on next frame | unit | `pytest tests/test_tpms_alerts.py::test_stale_clears -x` | ❌ Wave 0 |
| 10 | probe_usb_vid_pid finds 0bda:2838 | unit | `pytest tests/test_tpms_subprocess.py::test_probe_finds_sdr -x` | ❌ Wave 0 |
| 10 | probe returns False when missing | unit | `pytest tests/test_tpms_subprocess.py::test_probe_missing_sdr -x` | ❌ Wave 0 |
| 1+10 | rtl_433 restart on death | integration | `pytest tests/test_tpms_subprocess.py::test_restart_on_exit -x` | ❌ Wave 0 |
| 1+10 | stderr drain prevents block | integration | `pytest tests/test_tpms_subprocess.py::test_stderr_drained -x` | ❌ Wave 0 |
| Acc | Full UAT (driving loop) | manual-only | n/a | n/a — driver in car |

### Mock Strategies

**rtl_433 stdout simulation** — provide a `FakeRtl433Process` test fixture that emits canned JSON lines on stdout via a real OS pipe. Mirrors how `test_ffmpeg_stall.py` simulates ffmpeg. Pattern:

```python
# tests/conftest.py — extend if a fixture file doesn't exist
@pytest.fixture
def fake_rtl433_frames():
    """Yield canned JSON frames for the four wheel sensors."""
    return [
        '{"time":"2026-04-28T12:34:56Z","model":"Abarth-124Spider","type":"TPMS",'
        '"id":"550b57d9","flags":"9300","pressure_kPa":89.7,"temperature_C":22.5,'
        '"status":19,"mic":"CHECKSUM"}',
        # ... three more for the other wheels ...
    ]


@pytest.fixture
def fake_rtl433_subprocess(monkeypatch, fake_rtl433_frames):
    """Replace subprocess.Popen with a fixture that emits the canned frames."""
    # Returns a stub Popen-like object whose stdout.readline() yields each frame
    # in turn then None on EOF. stderr is a Pipe-like that returns "" on read.
```

**Deflation simulation** — feed a sequence of frames where one sensor's PSI drops by 6 PSI within 30 frames (≈30 seconds at 1 Hz/wheel). Assert `alerts.snapshot()` shows TPMS_LEAK fired exactly once.

**Stale-sensor simulation** — feed three frames for sensor X, then no frames for 360 simulated seconds. Use `time.monotonic` monkeypatch (already a project pattern in `test_thermal_monitor.py`). Assert wheel state == "stale".

**USB-missing simulation** — patch `subprocess.run` so `lsusb` returns output without `0bda:2838`. Assert `probe_usb_vid_pid` returns False, supervisor reports MISSING, daemon continues.

### Sampling Rate

- **Per task commit:** `pytest tests/test_tpms_*.py -x` — runs the new TPMS tests only, ~5-10 sec.
- **Per wave merge:** `pytest` — full suite, runtime currently ~30-45 sec.
- **Phase gate:** Full suite green before `/gsd-verify-work`.

### Wave 0 Gaps

All tests below are NEW. The existing test infrastructure (`pytest`, `conftest.py`, the `test_alerts.py` and `test_thermal_monitor.py` fixture patterns) covers what we need; no framework install required.

- [ ] `tests/test_tpms_parser.py` — JSON parsing, wheel mapping, pressure correction (REQ 1, 2, 3)
- [ ] `tests/test_tpms_database.py` — schema migration v11, insert/cursor, metric format (REQ 4, 5)
- [ ] `tests/test_tpms_alerts.py` — sustain + transition + recovery + stale (REQ 7, 9)
- [ ] `tests/test_tpms_leak.py` — deque-based leak detection + event recording (REQ 8)
- [ ] `tests/test_tpms_subprocess.py` — rtl_433 lifecycle, USB probe, stderr drain (REQ 1, 10)
- [ ] Extension to `tests/test_dashboard.py` — `_tpms_payload` shape (REQ 6)
- [ ] `tests/conftest.py` — `fake_rtl433_subprocess` and `fake_rtl433_frames` fixtures (shared across the new test files)

## Project Constraints (from CLAUDE.md)

| Directive | Where it bites in this phase |
|---|---|
| All logging via structlog with keyword args | Every TPMSService log call: `log.info("tpms_frame_received", wheel="front-driver", pressure_psi=32.1, raw_kpa=89.7)` — never positional. |
| Ruff: line length 100, rules E/F/I/W | The new TPMSService is one module — keep import block sorted, no unused imports, lines ≤ 100. |
| Mypy strict | TPMSService has annotated dataclass for state per wheel; deque type is `deque[tuple[float, float]]`. Subprocess Popen typed as `Optional[subprocess.Popen[str]]`. |
| Hierarchical YAML → nested dataclasses | TpmsConfig follows the existing pattern (e.g. `ParticulateConfig`); add to `Config` and wire in `load_config()`. |
| Threading: each collector runs in a daemon thread | TPMSService spawns: reader thread (stdout JSON parse), monitor thread (stderr drain + restart). Both `daemon=True`. |
| Hardware graceful degradation | `tpms.enabled: false` OR `tpms_radio` MISSING → daemon continues, no TTS, no frames, Health page shows NO DATA grey. |
| BatchSyncService / CaptureSyncService pattern for new services | TPMSService follows: config dataclass → service class with `start()`/`stop()` → engine wiring → YAML config. |
| UK/Aus spelling: "tyre" everywhere | Comments, log keys, dashboard labels, TTS strings, config keys. No "tire" anywhere — including in test names. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | rtl_433 22.11 emits one JSON object per line on stdout for `-F json` | Pattern 2 | LOW — verified against upstream source + multiple search hits + Brain note bench validation |
| A2 | rtl_433 stderr drain at 2 Hz is enough at default verbosity | Pitfall 1 | LOW — same pattern works for ffmpeg which writes much more; raise to 1 Hz if rtl_433 needs `-v` for debugging |
| A3 | `lsusb` is reliably present on bookworm with usbutils | Pattern 10 | LOW — usbutils is a hard dependency of i2c-tools (already in install.sh); `which lsusb` confirms |
| A4 | RTL-SDR VID:PID `0bda:2838` matches all common variants including Nooelec NESDR Smart v5 | Pattern 10 | MEDIUM — Realtek 2832U variants may report `0bda:2832` (old) or other PIDs. Confirm with `lsusb` after Thursday's hardware arrival; widen the match if needed (e.g. accept `0bda:2832` and `0bda:2838`) |
| A5 | Protocol 156 in 22.11 = Abarth-124Spider; index unchanged from upstream master at the time of CONTEXT.md | Pitfall 5 | MEDIUM — apt 22.11 was tagged 2022-11; the decoder was added 2021. Verify with `rtl_433 -R help` after install |
| A6 | `collections.deque(maxlen=120).append` is GIL-atomic for our single-producer usage | Pattern 8 | LOW — Python issue tracker explicitly says append/pop are atomic in CPython |
| A7 | Schema migration ordering is independent — v11 can be added without disturbing v10 or earlier | Pattern 4 | LOW — verified against existing migration sequence in database.py:188-220; each migration is gated on `current_version < N` |
| A8 | RTL-SDR hot-unplug results in rtl_433 exiting (not silently hanging) | Pitfall 2 | MEDIUM — common case from upstream issues but not 100% deterministic on Pi 5 with `usb_max_current_enable=1`. Wave 0 includes a `test_restart_on_exit` integration test that simulates this; UAT confirms in hardware |

**A4 and A5 should be verified by the planner during the Thursday hardware bring-up — both are configurable so the fix is one YAML edit if they shift.**

## Open Questions (RESOLVED)

1. **Should the TPMS_LEAK event open a CSV alongside the JSON?**
   - What we know: existing event types (HARD_BRAKE, BIG_CORNER, etc.) save IMU samples to CSV.
   - What's unclear: TPMS leak events have no IMU samples — passing an empty list works but produces an empty CSV file.
   - RESOLVED: pass `samples=[]` and let `_write_csv` create an empty CSV. Saves the planner from adding a "skip CSV for non-IMU events" branch in `events/storage.py`. The empty file is harmless to rsync + website.

2. **Should the yellow-low (28 PSI) state surface as a Phase-15-style banner, or only as a Health-card colour?**
   - What we know: SPEC.md REQ 7 says "Yellow fires Health-page banner only".
   - What's unclear: "banner" could mean the existing alert overlay (`alertOverlay` Alpine state) OR just the row colour in the TPMS section.
   - RESOLVED: just the row colour. The alert overlay is for transient bursts; persistent yellow PSI is a state, not a notification. Frontend already supports per-row state colour via `:class="'tpms-' + row.state"`.

3. **Should `tpms.enabled: false` skip the rtl_433 binary check entirely or still warn if missing?**
   - What we know: the daemon must boot even if SDR is unplugged (Phase 21 D-04).
   - What's unclear: with `enabled: false`, should the boot probe still log the SDR's PRESENT/MISSING state for monitoring?
   - RESOLVED: yes — manifest probes run regardless of feature toggles (existing pattern). HardwareSupervisor reports `tpms_radio` state independent of `tpms.enabled`. If enabled=false but SDR is plugged in, log INFO "tpms_disabled_but_sdr_present".

## Sources

### Primary (HIGH confidence)

- `/Users/tgreen/dev/shitbox/.planning/phases/28-tpms-integration/28-SPEC.md` (locked requirements)
- `/Users/tgreen/dev/shitbox/.planning/phases/28-tpms-integration/28-CONTEXT.md` (locked decisions)
- `/Users/tgreen/dev/shitbox/src/shitbox/capture/ring_buffer.py` (ffmpeg subprocess + stderr drain pattern, lines 740-1050)
- `/Users/tgreen/dev/shitbox/src/shitbox/health/alerts.py` (sustain + transition + recovery helper, all 235 lines)
- `/Users/tgreen/dev/shitbox/src/shitbox/capture/speaker.py` (TTS engine + speak_*() helpers + cached message dict)
- `/Users/tgreen/dev/shitbox/src/shitbox/dashboard/sse.py` (SSE payload assembly + _system_conditions_payload precedent)
- `/Users/tgreen/dev/shitbox/src/shitbox/storage/database.py` (schema migration pattern + cursor pattern; **SCHEMA_VERSION is 10**)
- `/Users/tgreen/dev/shitbox/src/shitbox/sync/batch_sync.py` (Prometheus remote_write cursor pattern, _readings_to_metrics structure)
- `/Users/tgreen/dev/shitbox/src/shitbox/sync/capture_sync.py` (sibling background-service shape)
- `/Users/tgreen/dev/shitbox/src/shitbox/utils/config.py` (TpmsConfig pattern fits existing dataclass model)
- `/Users/tgreen/dev/shitbox/src/shitbox/hardware/probes.py` (probe pattern; new probe_usb_vid_pid additions)
- `/Users/tgreen/dev/shitbox/src/shitbox/hardware/supervisor.py` (HardwareSupervisor dispatch lines 86-105)
- `/Users/tgreen/dev/shitbox/src/shitbox/dashboard/static/index.html` (Alpine x-for SYSTEM section, lines 412-422 — direct template for TPMS section)
- `/Users/tgreen/dev/shitbox/config/config.yaml` (current hardware: devices block + sensors structure)
- `/Users/tgreen/dev/shitbox/scripts/install.sh` (apt-get install line at line 62 — needs `rtl-433 librtlsdr-dev` appended)
- `/Users/tgreen/Brain/projects/shitbox-rally-2026.md` (2026-04-28 TPMS bench-validation log entry — sensor IDs, calibration findings, calculation showing × 2.45 correction)

### Secondary (MEDIUM confidence — verified against official sources)

- [rtl_433 README](https://github.com/merbanan/rtl_433/blob/master/README.md) — invocation flags, `-R`, `-F json`, `-g`, `-f`
- [rtl_433 Abarth-124 decoder source](https://github.com/merbanan/rtl_433/blob/master/src/devices/tpms_abarth124.c) — JSON output fields, pressure formula `× 1.38`, temperature formula `- 50.0`
- [Debian bookworm rtl-433 package](https://packages.debian.org/bookworm/rtl-433) — confirmed version 22.11-1
- [rtl_433 Debian manpages](https://manpages.debian.org/bookworm/rtl-433/rtl_433.1.en.html) — flag reference for the bookworm version
- [Python issue 15329](https://bugs.python.org/issue15329) — clarifies which deque methods are GIL-atomic (append/pop confirmed)

### Tertiary (LOW confidence — flagged for verification at hardware bring-up)

- [RTL-SDR USB ID](https://www.rtl-sdr.com/about-rtl-sdr/) — `0bda:2838` is the typical RTL2832U identifier; verify with actual `lsusb` output Thursday after the Nooelec arrives
- [rtl_433 USB hot-unplug behaviour](https://github.com/merbanan/rtl_433/issues/1899) — issue thread describes `usb_open error -4` on disconnect; covered by Pitfall 2

## Metadata

**Confidence breakdown:**

- **Standard stack:** HIGH — all components verified in package indexes or already in the repo.
- **Architecture:** HIGH — every pattern has a precedent in the existing codebase, cited by file:line.
- **Pitfalls:** HIGH for codebase pitfalls (drawn from shipped Phase 15/16 fixes); MEDIUM for rtl_433-specific quirks (verified via upstream issues but not yet in our hardware).
- **Validation:** HIGH — Wave 0 gap list is concrete; mocks reuse existing fixture patterns.
- **rtl_433 invocation:** HIGH — flags verified against bookworm manpage and master README; protocol 156 verified against decoder source.

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 (30 days — bookworm package versions are stable; only risk is upstream protocol-id reshuffle in a future apt upgrade — controlled by making `rtl433_protocol_id` configurable)

---

*Phase: 28-tpms-integration*
*Research complete; planner can now break this into PLAN files.*
