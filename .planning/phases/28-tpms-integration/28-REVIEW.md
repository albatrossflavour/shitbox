---
phase: 28-tpms-integration
reviewed: 2026-04-28T10:46:04Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - src/shitbox/storage/database.py
  - src/shitbox/events/detector.py
  - src/shitbox/events/labels.py
  - src/shitbox/utils/config.py
  - src/shitbox/capture/speaker.py
  - src/shitbox/hardware/probes.py
  - src/shitbox/hardware/supervisor.py
  - src/shitbox/sync/tpms.py
  - src/shitbox/sync/batch_sync.py
  - src/shitbox/dashboard/sse.py
  - src/shitbox/dashboard/static/index.html
  - src/shitbox/events/engine.py
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-04-28T10:46:04Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

The TPMS integration cleanly reuses the established subprocess-supervisor pattern from `capture/ring_buffer.py` (non-blocking stderr drain) and the Phase 15 alerts FSM. Threading discipline is sound — single-writer per wheel state, GIL-atomic deque appends, snapshot under lock. Schema migration is idempotent, and graceful degradation when `rtl_433` is missing works as advertised at engine wiring level.

The two material problems are both in leak handling. First, the leak detector fires every frame the spike is still inside the 60-second window (~60 events per real leak), and `_wire_leak_alert` writes a fresh `events.json` row for each — `alerts.fire_alert` collapses the TTS, but `event_storage.save_event` does not. Second, the TPMS USB SDR has no entry in `_build_reprobe_callbacks` (the `usb_vid_pid` bus type is only handled in the boot-time `_run_probe` path), so once the supervisor marks the radio MISSING after a USB reseat, it never re-checks — recovery only happens via `TPMSService._monitor_loop`, which means the supervisor's `hw_restored` TTS will not fire and the dashboard Health row will stay red until reboot.

Beyond those, batch sync has no `TooOldSampleError` ladder for the TPMS cursor (a permanently-rejected batch blocks the cursor forever), and pressure-field validation drops to 0.0 on missing fields, which will trip the LOW-PSI alert after two frames.

## Critical Issues

### CR-01: Leak alert writes duplicate `events.json` rows for every frame inside the leak window

**File:** `src/shitbox/sync/tpms.py:472-487, 537-590`
**Issue:** `_detect_leak` returns `True` whenever `max(in_window) - psi_now >= leak_drop_psi`. Once a real leak drops PSI below the threshold, the spike value remains inside the 60-second sliding window for the full `leak_window_seconds`. At ~1 Hz per wheel that means ~60 calls to `_wire_leak_alert` for a single physical leak. The Phase 15 `alerts.fire_alert` helper collapses repeated `active=True` calls so TTS only speaks once — but `event_storage.save_event` is called unconditionally inside `_wire_leak_alert`, which writes a new JSON row, bumps the shared `_event_counter`, and re-renders `events.json` every iteration. The result: roughly sixty TPMS_LEAK rows per real event in events.json and on the website, with sequential filenames competing with any other events firing in parallel (counter mutated without a lock from the reader thread).

**Fix:**
```python
def _wire_leak_alert(self, position: str, psi: float) -> None:
    subtype = self._position_to_subtype("LEAK", position)
    # Single-shot: only write the event the FIRST time we cross threshold
    # for this wheel. Reset when the deque rolls past the spike.
    if self._leak_event_fired.get(position, False):
        # Still firing alerts.fire_alert is fine — it dedupes — but skip
        # the events.json write so we get one row per physical leak.
        alerts.fire_alert(subtype, True, ..., sustain_required=1)
        return
    self._leak_event_fired[position] = True
    # ... existing fire_alert + save_event path ...

def _detect_leak(self, position: str, psi_now: float, now_mono: float) -> bool:
    window = self._leak_windows[position]
    window.append((now_mono, psi_now))
    cutoff = now_mono - self.config.leak_window_seconds
    in_window = [psi for ts, psi in window if ts >= cutoff]
    if not in_window:
        self._leak_event_fired[position] = False  # window cleared, allow next leak
        return False
    spiked = (max(in_window) - psi_now) >= self.config.leak_drop_psi
    if not spiked:
        self._leak_event_fired[position] = False
    return spiked
```
Initialise `self._leak_event_fired: Dict[str, bool] = {p: False for p in WHEEL_POSITIONS}` in `__init__`.

### CR-02: TPMS USB SDR has no reprobe callback wired into `HardwareSupervisor`

**File:** `src/shitbox/events/engine.py:919-973`, `src/shitbox/hardware/supervisor.py:96-99`
**Issue:** The `_build_reprobe_callbacks` factory in engine.py walks the manifest and dispatches per `dev.bus` value: it has branches for `i2c-1`, `1-wire`, `usb`, `audio`, `hdmi`, `gpio`. There is no branch for `usb_vid_pid`, which is the bus type Phase 28 introduced for the SDR (used in `supervisor._run_probe` at line 99). Devices with bus `usb_vid_pid` fall through to the `else: log.warning("unknown_bus_for_reprobe", ...)` branch, so the supervisor's reprobe map has no entry for the `tpms_radio` role. The supervisor's tick loop then takes the `cb is not None` branch as False and only calls `report_missing` to advance the backoff ladder — never actually re-probing. Recovery only happens via `TPMSService._monitor_loop` calling `report_present` on its own restart cycle, which means:

1. The supervisor's hw_restored TTS for the SDR never fires (no `prev == MISSING -> PRESENT` transition observed by the supervisor on its own retry).
2. Worse, if `TPMSService._monitor_loop` is itself stuck (e.g. process restarting in a tight loop) the supervisor cannot independently confirm the SDR is back.
3. The "unknown_bus_for_reprobe" warning will fire on every boot with TPMS enabled — silent log noise telling you something is wrong.

**Fix:** Add a `usb_vid_pid` branch to `_build_reprobe_callbacks`. Note that `HardwareDeviceConfig` reuses the `path` field for the VID:PID string when `bus == "usb_vid_pid"` (per the `supervisor._run_probe` precedent at line 99 — `probe_usb_vid_pid(d.path or "")`).
```python
elif bus == "usb_vid_pid":
    if not dev.path:
        log.warning("reprobe_skip_missing_vid_pid", role=dev.role)
        continue
    vid_pid: str = dev.path
    cbs[dev.role] = cast(
        Callable[[], bool], lambda v=vid_pid: probes.probe_usb_vid_pid(v)
    )
```
Consider also adding a dedicated `vid_pid: Optional[str]` field on `HardwareDeviceConfig` instead of overloading `path`, for clarity.

## Warnings

### WR-01: TPMS sync has no `TooOldSampleError` retry ladder; bad batches block forever

**File:** `src/shitbox/sync/batch_sync.py:422-474`
**Issue:** `_sync_tpms_batch` calls `_send_metric_tuples`, which raises a plain `RuntimeError` for any non-200 response (including 400 "too old sample"). The caller wraps the call in `try/except Exception` and `return`s without advancing the `prometheus_tpms` cursor. The main `_sync_batch` path has a dedicated `TooOldSampleError` ladder (`MAX_TOO_OLD_RETRIES = 20` cycles, then skip the batch) so a permanently-too-old batch is eventually moved past and not blocked forever. TPMS has no such fallback — if the Pi is offline long enough that the oldest TPMS row falls outside Prometheus's `out_of_order_time_window`, the cursor will block forever and every subsequent sync cycle will re-encode and re-send the same batch.

**Fix:** Either reuse the same `TooOldSampleError` mechanism (parse the response text in `_send_metric_tuples` and raise the typed error), or accept the simpler approach: track consecutive failures on the TPMS cursor and advance past after N tries with an ERROR-level skip log mirroring `batch_sync_too_old_abandoned`.

### WR-02: Missing `pressure_kPa` field defaults to 0.0 PSI and trips LOW alert

**File:** `src/shitbox/sync/tpms.py:412-419`
**Issue:** `parsed.get("pressure_kPa", 0.0)` silently returns 0.0 if the field is missing or null. Two such frames in a row (sustain_required=2) will fire `TPMS_LOW_*` for that wheel. rtl_433 has been observed (per the comment on line 48) to emit non-standard frames; the docstring at line 391 says "rtl_433 may emit non-TPMS frames if other decoders match" which is filtered, but a malformed TPMS frame with no pressure passes through. Same issue for `temperature_C`.

**Fix:**
```python
pressure_raw = parsed.get("pressure_kPa")
if pressure_raw is None:
    log.warning("tpms_frame_missing_pressure", wheel=position, sensor_id=sensor_id)
    return
try:
    raw_kpa = float(pressure_raw)
    temperature_c = float(parsed.get("temperature_C", 0.0))  # temp default OK
except (TypeError, ValueError) as e:
    log.warning("tpms_frame_field_error", error=str(e), wheel=position)
    return
```
Also consider rejecting nonsensical values (raw_kpa <= 0 or > 1000) — a flat tyre at sea level is not 0 kPa absolute, the sensor can't read that.

### WR-03: `event_storage._event_counter` mutated from reader thread without lock

**File:** `src/shitbox/sync/tpms.py:569-581`, `src/shitbox/events/storage.py:88`
**Issue:** `EventStorage.save_event` calls `_generate_filename` which does `self._event_counter += 1` on a non-atomic instance attribute. Before Phase 28 this was only ever called from the engine main thread (via `_on_event` from the detector callback). With CR-01 still active or even fixed, `TPMSService._wire_leak_alert` calls `save_event` from the reader thread. If a non-TPMS event fires concurrently (e.g. a hard brake during a leak), the counter increment races. Filenames may collide or skip a number. Not corruption-grade but definitely wrong.

**Fix:** Either add a lock around `_event_counter` in `EventStorage`, or have `TPMSService` post leak events back to the engine main thread via an existing event queue. The lock fix is smallest:
```python
# In EventStorage.__init__
self._counter_lock = threading.Lock()

def _generate_filename(self, event: Event) -> str:
    dt = datetime.fromtimestamp(event.start_time, tz=timezone.utc)
    time_str = dt.strftime("%H%M%S")
    with self._counter_lock:
        self._event_counter += 1
        counter = self._event_counter
    return f"{event.event_type.value}_{time_str}_{counter:03d}"
```

### WR-04: `_start_subprocess` only catches `FileNotFoundError`; other Popen failures crash engine boot

**File:** `src/shitbox/sync/tpms.py:265-283`
**Issue:** Engine guards with `shutil.which("rtl_433")` (engine.py:660) before constructing `TPMSService`, so `FileNotFoundError` is largely unreachable in practice. But other failure modes are not caught: `PermissionError` if the user lacks rw on `/dev/bus/usb/...`, `OSError` if the udev rule for `0bda:2838` isn't installed, an exception from rtl_433's libusb claim if another process holds the SDR. These propagate out of `_start_subprocess` → `start()` → `engine.start()` and abort engine boot. The "graceful degradation" claim in the docstring of `start()` is conditional on `self.config.enabled` only.

**Fix:**
```python
def _start_subprocess(self) -> None:
    cmd = self._build_cmd()
    try:
        self._process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except FileNotFoundError:
        log.warning("tpms_rtl433_binary_missing", hint="apt install rtl-433")
        self._process = None
        return
    except (OSError, PermissionError) as e:
        log.warning("tpms_rtl433_spawn_failed", error=str(e), hint="check usb perms / udev")
        self._process = None
        return
    log.info("tpms_rtl433_started", pid=self._process.pid, cmd=" ".join(cmd))
```

### WR-05: INFO-level log per parsed TPMS frame floods structlog

**File:** `src/shitbox/sync/tpms.py:429-437`
**Issue:** Every parsed TPMS frame logs at INFO with seven fields. The docstring says ~4 Hz, so a 24-hour drive logs ~345 600 lines from this single call site. This is noisy enough to make every other INFO log harder to grep, and on the Pi's flash it adds up.

**Fix:** Demote to DEBUG, or rate-limit to one log per wheel per N seconds. Keep INFO for state transitions (PSI crossing yellow/red, leak detection) only.

### WR-06: Empty `if data:` branch in `_read_stderr_nonblocking` exception handler

**File:** `src/shitbox/sync/tpms.py:317-320`
**Issue:** The fallback path `return data.decode(errors="replace")[-500:] if data else ""` references `data` after the inner `try` may have re-raised a non-`BlockingIOError` exception during `os.read`. If `os.set_blocking(fd, False)` itself raises (rare but possible if the fd was closed by another thread), `data` is `b""` from line 299 and we return `""` — fine. But if `os.read` raises something other than `BlockingIOError` mid-loop (e.g. `OSError` after partial reads), `data` may have some bytes but the `finally` branch executes `os.set_blocking(fd, flags)` and the outer `except Exception` returns the partial data — same intent as the inner `except` path. Not a correctness bug, just dead-feeling code given the comment claims this is a "last-ditch" path. The outer except shadows what is otherwise clean structured handling.

**Fix:** Either remove the outer try/except (let the loop raise, monitor will log via `tpms_monitor_error`), or document explicitly which exception types it's catching:
```python
except (OSError, ValueError) as e:
    log.warning("tpms_stderr_drain_unexpected", error=str(e))
    return data.decode(errors="replace")[-500:] if data else ""
```

## Info

### IN-01: `EngineConfig.tpms_sensor_map: Dict[str, str]` round-trips through dataclass twice

**File:** `src/shitbox/events/engine.py:238, 686-689`
**Issue:** `EngineConfig.from_yaml_config` flattens `config.tpms.sensor_map` (already a dict by the property accessor) into `tpms_sensor_map: Dict[str, str]`, then `UnifiedEngine.__init__` rebuilds it back into `[_TpmsEntry(id=sid, position=pos) for sid, pos in config.tpms_sensor_map.items()]` to construct a `TpmsConfig`. Net effect: dataclass → property → dict → rebuild dataclass. Works, but the round-trip is awkward and loses any future fields you might add to `TpmsSensorMapEntry`.

**Fix:** Pass the original `config.tpms` through directly, or store `tpms_sensors: List[TpmsSensorMapEntry]` on `EngineConfig`.

### IN-02: `TpmsConfig.sensor_map` recomputed on every frame

**File:** `src/shitbox/utils/config.py:203-209`, `src/shitbox/sync/tpms.py:407`
**Issue:** `sensor_map` is a `@property` that rebuilds the dict from `self.sensors` on every access. Called from `_handle_frame` for every parsed frame (~4 Hz). Negligible CPU cost (4-entry list) but technically redundant.

**Fix:** Cache once in `TPMSService.__init__`: `self._sensor_map = dict(self.config.sensor_map)`, then look up against `self._sensor_map` in `_handle_frame`. Not worth a refactor unless you hit log spam from `tpms_unknown_sensor` first.

### IN-03: Triple-lowercase of sensor_id in lookup chain

**File:** `src/shitbox/sync/tpms.py:76-82, 406`
**Issue:** `_handle_frame` does `sensor_id_raw.lower()` (line 406), then `lookup_wheel(sensor_id, ...)` which does `sensor_id.lower()` again (line 82). And the keys in `TpmsConfig.sensor_map` are already lowercased by the property accessor (config.py:209). Three layers of defensive case-folding for the same string.

**Fix:** Pick one (the property accessor is the right place — author authority is the YAML config). Drop the `.lower()` from the other two.

### IN-04: `tpms_readings` table not in `SCHEMA_SQL` block — only created via migration v11

**File:** `src/shitbox/storage/database.py:18-131, 385-416`
**Issue:** Fresh installs run `executescript(SCHEMA_SQL)` first (line 179), then walk the migration ladder. `tpms_readings` is created only by `_migrate_to_v11`. This works because migrations run on every connect when `current_version < SCHEMA_VERSION`, and `_migrate_to_v11` uses `CREATE TABLE IF NOT EXISTS`. But the canonical schema is now split between two places, and a future cleanup (e.g. squashing migrations) could miss it. Same applies to `notes`, `fuel_stops`, and `driver_stints` — pre-existing pattern.

**Fix (low priority):** Mirror `tpms_readings` into `SCHEMA_SQL` so a fresh install gets the table from `executescript` directly. Migration v11 still needs to run for upgraded databases, so leave it in place. No behavioural change, just a clearer single source of truth.

### IN-05: `self.tpms: Optional[Any]` in engine loses type checking

**File:** `src/shitbox/events/engine.py:658`
**Issue:** Annotated as `Optional[Any]` to avoid an import cycle (TPMSService imports from `shitbox.events.detector`, engine imports both). Every call site (`self.tpms.start()`, `self.tpms.stop()`, `dashboard_sse.set_tpms_service(self.tpms)`) is now untyped to mypy.

**Fix:** Use `TYPE_CHECKING` block:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from shitbox.sync.tpms import TPMSService

class UnifiedEngine:
    def __init__(...):
        self.tpms: Optional["TPMSService"] = None
```
The runtime import inside the `if config.tpms_enabled:` branch (line 666) stays as-is.

---

_Reviewed: 2026-04-28T10:46:04Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
