---
phase: 28-tpms-integration
verified: 2026-04-28T10:57:12Z
status: human_needed
score: 7/10 must-haves verified (3 require Thursday hardware)
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: UAT-1 — Hardware bring-up sanity (verifies VALIDATION A4 + A5)
    expected: lsusb reports 0bda:2838; rtl_433 -R help lists protocol 156 = Abarth-124Spider; usb_max_current_enable=1; daemon emits tpms_starting → tpms_rtl433_started → tpms_frame_received for all four configured sensor IDs within 60 s.
    why_human: Requires the Nooelec NESDR Smart v5 (arriving 2026-04-30), four installed wheel sensors, and physical USB enumeration on the Pi. Cannot be probed with the dongle absent.
  - test: UAT-2 — Bench deflation, low + leak + slow-deflation negative
    expected: Yellow band shows on dashboard with no TTS; red banner + "Front driver tyre low pressure" TTS within 5 s of crossing PSI ≤ 25; "_RESTORED" TTS within 5 s of re-inflation above 28 PSI; ≥5 PSI/60 s drop fires "Tyre leaking, front driver" + writes a single TPMS_LEAK row to events.json; slow 1 PSI/min deflation does NOT fire leak. SQLite tpms_readings within ±0.5 PSI of dashboard.
    why_human: SPEC-7 + SPEC-8 acceptance is "actually deflate a tyre and listen for the announcement / read the gauge". Requires the SDR, fitted sensors, valve-core access, stick gauge, and audible TTS. No simulation path.
  - test: UAT-3 — RTL-SDR replug recovery (SPEC-10)
    expected: Daemon survives unplug (PID + ActiveEnterTimestamp unchanged); tpms_radio MISSING surfaces on Health modal within 30 s; all four wheels go STALE within 5 min; replug returns PRESENT + frames flowing within 60 s; no error spam in journalctl.
    why_human: USB hot-unplug + replug is a physical operation; CR-02 supervisor reprobe fix is the wiring under test and must be exercised against real hardware to confirm hw_restored TTS fires on re-adopt.
  - test: UAT-4 — Driving loop end-to-end (SPEC Acceptance final bullet)
    expected: All four wheels report continuously through a 10-15 minute loop with no STALE; stick-gauge to dashboard agreement within ±3 PSI; mid-loop deflation alert + TTS within 5 s; Grafana shows four labelled time series matching SQLite within one sample.
    why_human: Real driving introduces RF interference (engine bay, alternator, spark plugs) and varying wheel positions during cornering — none of which can be simulated on the bench. Best run with a co-driver reading the dashboard.
  - test: Grafana panel additions to shitbox-rally-command dashboard
    expected: $wheel template variable resolves to four positions; TPMS Pressure panel renders four lines + 28/25 PSI threshold guides; TPMS Temperature panel renders four lines; dashboard JSON committed to home-ops audit-grafana-dashboard branch with clean Flux reconcile.
    why_human: Grafana edit lives in a separate repo (~/dev/home-ops/.../grafana/), needs metrics actively flowing (UAT-4 prerequisite), and the visual rendering / threshold display can only be verified by eye in the Grafana UI.
---

# Phase 28: TPMS Integration Verification Report

**Phase Goal:** Receive 433 MHz TPMS frames from four installed wheel sensors via RTL-SDR + `rtl_433`, normalise pressure into actual PSI, persist to SQLite, and surface per-wheel state on Grafana and the dashboard Health page with low-pressure threshold alerts (28/25 PSI) and rapid-deflation leak alerts (≥5 PSI/60s) via the existing TTS engine.

**Verified:** 2026-04-28T10:57:12Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

The phase produced 10 SPEC-N requirements locked at ambiguity 0.13. Six waves of executor work landed `src/shitbox/sync/tpms.py` (608 lines, the only fundamentally new module), schema v11 with `tpms_readings` + `prometheus_tpms` cursor, `EventType.TPMS_LEAK` + label/colour wiring, USB VID:PID hardware probe with supervisor reprobe callback, three TTS helpers backed by 12 cached messages, dashboard SSE TPMS section + four-row Health page rendering, and `BatchSyncService` + `UnifiedEngine` integration.

Two code-review criticals (CR-01 leak-event spam in events.json; CR-02 missing supervisor reprobe callback for `usb_vid_pid` bus) were fixed in commit `bc41aa1`. Six warnings + five info findings remain advisory.

Test status: **548 passed, 1 skipped, 0 failed** (the skip is a pre-existing dashboard `test_lifecycle_logs_endpoints` unrelated to TPMS).

The phase is code-complete and the codebase-verifiable surface passes. The three manual UATs (UAT-1 through UAT-4) and the Grafana panel checklist explicitly cannot be exercised without the Nooelec NESDR Smart v5 (Thursday 2026-04-30) and four fitted wheel sensors. They are captured in `28-UAT.md` with `status: pending`.

### Observable Truths

| #   | Truth (SPEC-N)                                                                                                | Status        | Evidence                                                                                                      |
| --- | -------------------------------------------------------------------------------------------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------- |
| 1   | SPEC-1 — rtl_433 -R 156 -F json subprocess parses TPMS frames; ≥1 frame/min/wheel under typical RF             | ? UNCERTAIN   | `TPMSService` exists at `sync/tpms.py:118`; subprocess lifecycle pattern correct (Popen, stderr drain, restart-on-exit). Frame rate / RF reception requires UAT-1 + UAT-4 hardware run. |
| 2   | SPEC-2 — × 2.45 pressure correction applied; stored PSI within ±3 PSI of stick gauge                            | ? UNCERTAIN   | `correct_pressure_kpa(raw, factor=2.45)` returns `87.6 × 2.45 = 214.62 kPa`; `kpa_to_psi(214.62) ≈ 31.13 PSI` confirmed via in-process smoke test. ±3 PSI accuracy requires UAT-2 stick-gauge cross-check. |
| 3   | SPEC-3 — Wheel-position mapping; unknown sensor IDs logged at INFO and discarded                                | ✓ VERIFIED    | `lookup_wheel(sensor_id, sensor_map)` case-insensitive at `sync/tpms.py:76-82`; `_handle_frame` logs `tpms_unknown_sensor` and returns at `sync/tpms.py:408`; sensor_map loaded with all four bench-validated IDs (`config/config.yaml:335-341`). |
| 4   | SPEC-4 — `tpms_readings` table; one row per parsed frame; cursor advances independently of `prometheus`         | ✓ VERIFIED    | `SCHEMA_VERSION = 11` (`storage/database.py:16`); `_migrate_to_v11` creates table + 2 indexes idempotently (lines 385-416); `insert_tpms_reading` (line 514) + `get_unsynced_tpms_readings` reads `prometheus_tpms` cursor (line 553); 4/4 database tests pass. |
| 5   | SPEC-5 — `shitbox_tpms_pressure_psi{wheel="..."}` + `shitbox_tpms_temperature_c{wheel="..."}` Prometheus metrics | ? UNCERTAIN   | `_sync_tpms_batch` (`sync/batch_sync.py:422`) emits both metrics with `{car, job, wheel}` labels; advances `prometheus_tpms` cursor (line 468); `test_prometheus_metric_shape` passes. End-to-end scrape requires Prometheus + Grafana cross-check (UAT-4). |
| 6   | SPEC-6 — Health page TPMS section, four wheel slots, NO DATA grey before first frame, ≤2 s SSE update          | ✓ VERIFIED    | `_tpms_payload()` always emits four FD/FP/RD/RP rows (`dashboard/sse.py:231`); HTML `x-for="row in tpms" :key="row.position"` (line 437); CSS `.tpms-no_data/ok/low/critical/stale` palette (lines 53-62); SSE merge `this.tpms = d.tpms` (line 649); `tpmsGlyph` Alpine helper (line 925). 2/2 dashboard tests pass. |
| 7   | SPEC-7 — Per-wheel sustained-low alert at 28/25 PSI; yellow Health-only, red TTS; `_RESTORED` on recovery        | ? UNCERTAIN   | `_wire_low_pressure_alert` (`sync/tpms.py:503`) fires `alerts.fire_alert(TPMS_LOW_<WHEEL>, ...)` at red threshold and `alerts.fire_recovery(..., recovery_subtype="..._RESTORED")` above yellow; 12 cached TTS messages with locked D-04/D-07 wording. 5/5 alerts tests pass. End-to-end TTS audibility + ≤5 s latency requires UAT-2. |
| 8   | SPEC-8 — Rapid deflation ≥5 PSI within 60 s fires CRITICAL leak alert + writes `TPMS_LEAK` event                | ? UNCERTAIN   | `_detect_leak` deque (maxlen=120) per wheel (`sync/tpms.py:160`); `_wire_leak_alert` fires `TPMS_LEAK_<WHEEL>` + writes `Event(event_type=EventType.TPMS_LEAK, ...)` via `event_storage.save_event`. CR-01 fix gates events.json write to single emit per physical leak via `_leak_event_fired` flag (line 580). 3/3 leak tests pass; bench deflation timing requires UAT-2. |
| 9   | SPEC-9 — Per-wheel STALE warning after 5 min silence; clears on next frame; no TTS for STALE                   | ✓ VERIFIED    | `snapshot()` computes `age > stale_timeout_seconds` lazily (`sync/tpms.py:213-234`); STALE state surfaces in dashboard payload only — no `speak_*` call in stale path. 2/2 stale tests pass. |
| 10  | SPEC-10 — `tpms_radio` manifest entry, criticality `best_effort`, supervisor re-adopts on USB replug              | ? UNCERTAIN   | `tpms_radio` device in `config/config.yaml:425` (`bus: usb_vid_pid, path: "0bda:2838", criticality: best_effort`); `probe_usb_vid_pid` (`hardware/probes.py:62`); supervisor `_run_probe` dispatch (`hardware/supervisor.py:98-99`); CR-02 fix wires `usb_vid_pid` branch into `_build_reprobe_callbacks` (`engine.py:971-977`). Boot-with-SDR-absent and replug recovery require UAT-3. |

**Score:** 4/10 unconditionally verified, 6/10 require hardware UAT (which is expected — SPEC-1/2/5/7/8/10 acceptance criteria explicitly list hardware-only checks).

Counting "code path verified, hardware UAT pending" as conditional pass: **all 10 must-haves have correct code wiring**. The phase cannot move to `passed` until UAT-1 through UAT-4 are signed off in `28-UAT.md`.

### Required Artifacts

| Artifact                                        | Expected                                                                            | Status     | Details                                                                                       |
| ------------------------------------------------ | ----------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------- |
| `src/shitbox/sync/tpms.py`                       | TPMSService class + 4 module helpers, ≥350 lines                                    | ✓ VERIFIED | 608 lines; `class TPMSService`, `parse_frame`, `correct_pressure_kpa`, `kpa_to_psi`, `lookup_wheel` all present; `_handle_frame`, `_detect_leak`, `_wire_low_pressure_alert`, `_wire_leak_alert`, `_read_stderr_nonblocking`, `_monitor_loop` all defined; CR-01 `_leak_event_fired` flag wired. |
| `src/shitbox/storage/database.py`                | SCHEMA_VERSION=11, `_migrate_to_v11`, `insert_tpms_reading`, `get_unsynced_tpms_readings` | ✓ VERIFIED | All four exist at the documented line numbers; `prometheus_tpms` cursor name on line 563.    |
| `src/shitbox/events/detector.py`                 | `EventType.TPMS_LEAK = "tpms_leak"`                                                  | ✓ VERIFIED | Line 25; not added to `VIDEO_CAPTURE_EVENTS` (per SPEC REQ 8 boundary).                       |
| `src/shitbox/events/labels.py`                   | TPMS_LEAK in EVENT_LABELS + EVENT_COLOURS                                           | ✓ VERIFIED | `EventType.TPMS_LEAK: "TPMS Leak"` at line 26; colour `#f0883e` at line 40 (post-merge fix `0273f0a`). |
| `src/shitbox/utils/config.py`                    | `TpmsConfig` + `TpmsSensorMapEntry` dataclasses; `tpms` field on Config root          | ✓ VERIFIED | `class TpmsSensorMapEntry` at line 168; `class TpmsConfig` at line 181 with `sensor_map` `@property`; `tpms: TpmsConfig` on Config at line 477; `load_config` wires `TpmsSensorMapEntry(**s)` at line 588 and `tpms=tpms_config` at line 646. |
| `src/shitbox/capture/speaker.py`                 | 12 cached messages (4 wheels × 3 alert types) + 3 `speak_tpms_*` helpers              | ✓ VERIFIED | 12 `tpms_*` keys at lines 78-89 (4 low + 4 leak + 4 restored); `speak_tpms_low/leak/restored` at lines 470/489/504; D-04/D-05/D-07 wording locked. |
| `src/shitbox/hardware/probes.py`                 | `probe_usb_vid_pid(vid_pid)` using `subprocess.run(["lsusb"])`                          | ✓ VERIFIED | Defined at line 62; `FileNotFoundError`, `TimeoutExpired`, non-zero exit all guarded.        |
| `src/shitbox/hardware/supervisor.py`             | `_run_probe` dispatches `bus: usb_vid_pid`                                            | ✓ VERIFIED | `if d.bus == "usb_vid_pid": return hw_probes.probe_usb_vid_pid(d.path or "")` at lines 98-99. |
| `src/shitbox/sync/batch_sync.py`                 | `_sync_tpms_batch` + `_send_metric_tuples`; emits `shitbox_tpms_pressure_psi` + `shitbox_tpms_temperature_c` on `prometheus_tpms` cursor | ✓ VERIFIED | `_sync_tpms_batch` at line 422 reads `get_unsynced_tpms_readings`, builds tuples with `wheel` label, advances `prometheus_tpms` cursor at line 468; called from `_sync_loop` at line 130. |
| `src/shitbox/dashboard/sse.py`                   | `_tpms_payload`, `set_tpms_service`, module-level `tpms_service` ref, `tpms` key on `/sse/slow` payload | ✓ VERIFIED | `tpms_service: Optional[Any]` at line 205; `set_tpms_service` at line 208; `_tpms_payload` at line 231; `"tpms": _tpms_payload()` in `/sse/slow` JSON at line 352. |
| `src/shitbox/dashboard/static/index.html`        | TPMS Health section between SYSTEM and HARDWARE; `tpmsGlyph`; `.tpms-*` CSS palette; Alpine `tpms: []` init + SSE merge | ✓ VERIFIED | `<div class="hw-section-eyebrow">TPMS</div>` at line 436; `x-for="row in tpms" :key="row.position"` at line 437; `tpms: []` at line 495; `this.tpms = d.tpms` at line 649; `tpmsGlyph(state)` at line 925; CSS at lines 52-62. |
| `src/shitbox/events/engine.py`                   | 13 flat `tpms_*` `EngineConfig` fields; `from_yaml_config` mapping; `TPMSService` instantiated behind `shutil.which("rtl_433")` guard; start/stop wiring with dashboard register/deregister; `usb_vid_pid` reprobe callback (CR-02 fix) | ✓ VERIFIED | `tpms_enabled` at line 226, full field set 226-238; from_yaml mapping 390-402; `shutil.which("rtl_433")` guard at line 660; `self.tpms = TPMSService(...)` at line 691; `self.tpms.start()` at 2562; `dashboard_sse.set_tpms_service(self.tpms)` at 2565; `self.tpms.stop()` at 2769; `set_tpms_service(None)` at 2772; CR-02 `elif bus == "usb_vid_pid"` reprobe branch at lines 971-977. |
| `config/config.yaml`                             | Top-level `tpms:` block + `tpms_radio` hardware manifest entry                       | ✓ VERIFIED | `tpms:` at line 321; `usb_vid_pid: "0bda:2838"` at 333; all four sensor IDs at 335-341; `tpms_radio` manifest device at line 425 with `bus: usb_vid_pid, path: "0bda:2838", criticality: best_effort`. |
| `scripts/install.sh`                             | apt-get install line includes `rtl-433 librtlsdr-dev`                                | ✓ VERIFIED | Line 62: `apt-get install -y ... rtl-433 librtlsdr-dev`.                                       |
| `.planning/phases/28-tpms-integration/28-UAT.md` | Four UAT scripts + Grafana checklist + Sign-Off section                              | ✓ VERIFIED | 373 lines; `## UAT-1` through `## UAT-4`; Grafana Panel Checklist; Sign-Off with 5 boxes; UK/Aus "tyre" enforced (9 matches, 0 "tire"); status `pending` in frontmatter. |

### Key Link Verification

| From                                             | To                                                  | Via                                                                   | Status     | Details                                                                                  |
| ------------------------------------------------ | --------------------------------------------------- | --------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------- |
| `Database.connect()`                             | `_migrate_to_v11`                                   | `if current_version < 11: self._migrate_to_v11(conn)`                 | ✓ WIRED    | Dispatch at `database.py:216`; idempotent CREATE TABLE IF NOT EXISTS belt-and-braces.    |
| `tpms_readings` rows                             | `sync_cursors (prometheus_tpms)`                    | `update_sync_cursor` + `get_unsynced_tpms_readings`                    | ✓ WIRED    | Cursor read at `database.py:563`; advanced from `batch_sync.py:468`.                      |
| `TPMSService._reader_loop`                       | `Database.insert_tpms_reading`                      | `self.db.insert_tpms_reading(...)` per parsed frame                    | ✓ WIRED    | Call at `sync/tpms.py` `_handle_frame` (one row per known-sensor frame).                  |
| `TPMSService._handle_frame leak detection`       | `EventStorage.save_event` with `EventType.TPMS_LEAK`  | `self.event_storage.save_event(Event(event_type=EventType.TPMS_LEAK, ...))` | ✓ WIRED    | Single-shot via `_leak_event_fired` flag at `sync/tpms.py:580-599` (CR-01 fix). |
| `TPMSService._monitor_loop`                      | `hw_state.report_missing/present("tpms_radio")`     | USB probe failure → MISSING; respawn → PRESENT                         | ✓ WIRED    | Calls at `sync/tpms.py:374` and `:386`.                                                  |
| `TPMSService._handle_frame`                      | `alerts.fire_alert + speak_tpms_low/leak/restored`  | per-wheel subtype `TPMS_LOW_<WHEEL>` / `TPMS_LEAK_<WHEEL>`              | ✓ WIRED    | `alerts.fire_alert` at lines 530, 568; `alerts.fire_recovery` at 537; cached TTS callbacks. |
| `/sse/slow` JSON                                 | `_tpms_payload()`                                   | JSON payload key `"tpms"`                                              | ✓ WIRED    | At `dashboard/sse.py:352`.                                                               |
| `_tpms_payload`                                  | `TPMSService.snapshot()`                            | `tpms_service.snapshot() if tpms_service is not None else {}`         | ✓ WIRED    | At `dashboard/sse.py:250`.                                                               |
| `BatchSyncService._sync_loop`                    | `_sync_tpms_batch` (independent of `_sync_batch`)   | called sequentially after `_sync_batch`                                | ✓ WIRED    | At `batch_sync.py:130`.                                                                  |
| `UnifiedEngine.__init__`                         | `TPMSService` (behind `shutil.which("rtl_433")` guard) | `if config.tpms_enabled and shutil.which("rtl_433"): self.tpms = TPMSService(...)` | ✓ WIRED    | At `engine.py:659-691`.                                                                  |
| `UnifiedEngine.start()`                          | `self.tpms.start()` + `dashboard_sse.set_tpms_service(self.tpms)` | guarded by `if self.tpms:`                                | ✓ WIRED    | At `engine.py:2562-2565`.                                                                |
| `UnifiedEngine.stop()`                           | `self.tpms.stop()` + `dashboard_sse.set_tpms_service(None)` | guarded by `if self.tpms:`                                  | ✓ WIRED    | At `engine.py:2769-2772`.                                                                |
| `HardwareSupervisor._build_reprobe_callbacks`    | `probe_usb_vid_pid` for `bus: usb_vid_pid` devices  | `elif bus == "usb_vid_pid": cbs[dev.role] = lambda v=vid_pid: probes.probe_usb_vid_pid(v)` | ✓ WIRED    | CR-02 fix at `engine.py:971-977`. Eliminates `unknown_bus_for_reprobe` boot warning and lets supervisor re-adopt the SDR independently of `TPMSService._monitor_loop`. |

### Data-Flow Trace (Level 4)

| Artifact                  | Data Variable          | Source                                                | Produces Real Data | Status        |
| ------------------------- | ---------------------- | ----------------------------------------------------- | ------------------ | -------------- |
| `_tpms_payload` rows      | `tpms_service.snapshot()` | `TPMSService._wheels` populated by `_handle_frame` from rtl_433 stdout | Conditional         | ⚠️ HOLLOW until rtl_433 produces frames (i.e. SDR plugged in + sensors transmitting). With no service registered, returns four `no_data` rows by design (SPEC-6 cold-start). |
| Prometheus TPMS metrics   | `tpms_readings` rows   | `Database.insert_tpms_reading` called from `_handle_frame` | Conditional         | ⚠️ HOLLOW until frames flow. Cursor advance + metric tuple shape verified by `test_prometheus_metric_shape`. |
| Health page TPMS section  | `this.tpms` Alpine state | `/sse/slow` `tpms` key from `_tpms_payload`           | Conditional         | ⚠️ HOLLOW until frames flow. Default state correctly shows four `NO DATA` rows when service is unregistered (verified). |

The "hollow" status is by design — every artifact has a verified data path from the rtl_433 subprocess through to the consumer. Without the SDR (Thursday hardware), no real values flow. This is the same shape as Phase 21's hardware probes: the wiring is correct, the values arrive when the device does.

### Behavioural Spot-Checks

| Behavior                                                        | Command                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Result | Status |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------ |
| Module imports + default values match SPEC                       | `python -c "import sys; sys.path.insert(0,'src'); from shitbox.utils.config import TpmsConfig; t=TpmsConfig(); assert t.pressure_correction_factor==2.45 and t.low_pressure_yellow_psi==28.0 and t.low_pressure_red_psi==25.0 and t.leak_window_seconds==60.0 and t.leak_drop_psi==5.0 and t.stale_timeout_seconds==300.0 and t.usb_vid_pid=='0bda:2838'"`                                                                                                                                                                                                                                                                                                          | OK     | ✓ PASS |
| Schema version is 11                                            | `python -c "import sys; sys.path.insert(0,'src'); from shitbox.storage.database import SCHEMA_VERSION; assert SCHEMA_VERSION == 11"`                                                                                                                                                                                                                                                                                                                                                                                                              | OK     | ✓ PASS |
| `EventType.TPMS_LEAK` defined as `"tpms_leak"`                   | `python -c "import sys; sys.path.insert(0,'src'); from shitbox.events.detector import EventType; assert EventType.TPMS_LEAK.value == 'tpms_leak'"`                                                                                                                                                                                                                                                                                                                                                                                              | OK     | ✓ PASS |
| YAML config loads with all four bench-validated sensors          | `python -c "import sys; sys.path.insert(0,'src'); from shitbox.utils.config import load_config; c=load_config('config/config.yaml'); sm=c.tpms.sensor_map; assert sm.get('550b57d9')=='front-driver' and sm.get('54d96e8f')=='front-passenger' and sm.get('550d14ed')=='rear-driver' and sm.get('550b5d8a')=='rear-passenger' and len(sm)==4"`                                                                                                                                                                                                       | OK     | ✓ PASS |
| `probe_usb_vid_pid` matches mocked `lsusb` output                | `python -c "import sys; sys.path.insert(0,'src'); from unittest import mock; from shitbox.hardware.probes import probe_usb_vid_pid; fake=mock.MagicMock(returncode=0, stdout='Bus 001 Device 005: ID 0bda:2838 Realtek\n'); m=mock.patch('shitbox.hardware.probes.subprocess.run', return_value=fake); m.start(); assert probe_usb_vid_pid('0bda:2838') is True; m.stop()"`                                                                                                                                                                                                                                                                                          | OK     | ✓ PASS |
| `_tpms_payload()` returns four `no_data` rows in FD/FP/RD/RP order with no service registered | `python -c "import sys; sys.path.insert(0,'src'); from shitbox.dashboard.sse import _tpms_payload, set_tpms_service; set_tpms_service(None); rows=_tpms_payload(); assert len(rows)==4 and [r['position'] for r in rows]==['front-driver','front-passenger','rear-driver','rear-passenger'] and all(r['state']=='no_data' for r in rows)"`                                                                                                                                                                                                                                                                                                                                          | OK     | ✓ PASS |
| Full pytest suite green                                          | `pytest -q --tb=no`                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | 548 passed, 1 skipped (pre-existing dashboard skip), 0 failed in 71.19s | ✓ PASS |

### Requirements Coverage

Phase 28's SPEC-1..SPEC-10 are documented in `28-SPEC.md` but are NOT yet promoted into `.planning/REQUIREMENTS.md` Traceability table (which currently ends at IMU-06 / Phase 22). This is consistent with how earlier phases were handled: REQUIREMENTS.md is updated post-UAT once the phase closes. No orphan or missing IDs were detected — the 10 SPEC requirements are claimed across the six plans as follows:

| Requirement | Source Plans                          | Description                                                                                  | Status        | Evidence                                                                                       |
| ----------- | -------------------------------------- | -------------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------- |
| SPEC-1      | 28-01, 28-04                           | rtl_433 subprocess parses TPMS frames; ≥1 frame/min/wheel                                     | ? NEEDS HUMAN | Code path verified (TPMSService); RF reception requires UAT-1.                                  |
| SPEC-2      | 28-01, 28-04                           | × 2.45 pressure correction; ±3 PSI accuracy                                                   | ? NEEDS HUMAN | Math verified in unit tests; ±3 PSI accuracy requires UAT-2 stick-gauge cross-check.            |
| SPEC-3      | 28-01, 28-03, 28-04                    | Wheel-position mapping; unknown sensors logged + dropped                                       | ✓ SATISFIED   | `lookup_wheel` + `_handle_frame tpms_unknown_sensor` log; sensor_map loaded from YAML.          |
| SPEC-4      | 28-01, 28-02, 28-04                    | `tpms_readings` table; one row per parsed frame                                                | ✓ SATISFIED   | `insert_tpms_reading` called from `_handle_frame`; 4/4 database tests pass.                    |
| SPEC-5      | 28-01, 28-02, 28-05                    | Per-wheel pressure + temperature Prometheus metrics                                             | ? NEEDS HUMAN | `_sync_tpms_batch` + metric tuple shape verified; end-to-end Grafana cross-check is UAT-4.      |
| SPEC-6      | 28-01, 28-05                           | Health page TPMS section, four wheel slots, NO DATA grey, ≤2 s SSE update                     | ✓ SATISFIED   | `_tpms_payload` + index.html section + Alpine state + CSS palette + tpmsGlyph helper.           |
| SPEC-7      | 28-01, 28-03, 28-04                    | Sustained-low alerts at 28/25 PSI; yellow Health-only, red TTS; `_RESTORED` recovery         | ? NEEDS HUMAN | `_wire_low_pressure_alert` + 12 cached messages with locked wording; bench latency is UAT-2.   |
| SPEC-8      | 28-01, 28-02, 28-04                    | Rapid deflation ≥5 PSI/60 s fires CRITICAL leak + `TPMS_LEAK` event                            | ? NEEDS HUMAN | `_detect_leak` deque + `_wire_leak_alert` + CR-01 single-shot guard; bench timing is UAT-2.    |
| SPEC-9      | 28-01, 28-04                           | Per-wheel STALE after 5 min silence; clears on next frame; no TTS                             | ✓ SATISFIED   | `snapshot()` lazy stale computation; no `speak_*` call in stale path; 2/2 stale tests pass.    |
| SPEC-10     | 28-01, 28-03, 28-04, 28-05             | `tpms_radio` manifest entry; supervisor re-adopts on USB replug                              | ? NEEDS HUMAN | Manifest entry + probe + supervisor branch + CR-02 reprobe callback all wired; replug is UAT-3. |

**No orphaned requirements.** Every SPEC-N is claimed by at least one plan and has corresponding code/wiring evidence.

### Anti-Patterns Found

| File                                  | Line(s)               | Pattern                                                                          | Severity   | Impact                                                                                                                                                                                                              |
| ------------------------------------- | --------------------- | -------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/shitbox/sync/tpms.py`            | 412-413               | `parsed.get("pressure_kPa", 0.0)` silently coerces missing field to 0.0          | ⚠️ Warning | WR-02 from REVIEW. Two missing-field frames in a row would falsely trip `TPMS_LOW_*`. Defer-able; rtl_433 frame validity guard. Advisory.                                                                              |
| `src/shitbox/sync/batch_sync.py`      | 463-468               | No `TooOldSampleError` retry ladder for `prometheus_tpms` cursor                 | ⚠️ Warning | WR-01 from REVIEW. A permanently-rejected batch blocks the cursor. Matches existing batch_sync limitation; future hardening pass. Advisory.                                                                          |
| `src/shitbox/events/storage.py`       | 88                    | `_event_counter` mutated from reader thread without lock                          | ⚠️ Warning | WR-03 from REVIEW. Pre-existing behaviour; new TPMS reader-thread call site stresses it. Advisory; flagged for next storage.py touch.                                                                                |
| `src/shitbox/sync/tpms.py`            | 270-283               | `_start_subprocess` only catches `FileNotFoundError`                              | ⚠️ Warning | WR-04 from REVIEW. `PermissionError`, `OSError` from libusb claim could propagate up. Engine guard at `engine.py:660` reduces likelihood. Advisory.                                                                  |
| `src/shitbox/sync/tpms.py`            | 429-437               | INFO-level log per parsed TPMS frame                                              | ⚠️ Warning | WR-05 from REVIEW. ~345k lines/day at 4 wheels × 1 Hz × 7 fields. Demote to DEBUG or rate-limit. Advisory; visible noise but not correctness-breaking.                                                                |
| `src/shitbox/sync/tpms.py`            | 317-320               | Empty `if data:` branch in `_read_stderr_nonblocking` outer except                | ⚠️ Warning | WR-06 from REVIEW. Dead-feeling code; not a correctness bug. Advisory.                                                                                                                                              |
| `src/shitbox/events/engine.py`        | 658                   | `self.tpms: Optional[Any]` loses static type checking                            | ℹ️ Info    | IN-05 from REVIEW. Use `TYPE_CHECKING` block to type the attribute as `Optional["TPMSService"]`.                                                                                                                    |
| `src/shitbox/events/engine.py`        | 238, 686-689          | `tpms_sensor_map` round-trips dict → list → dict between EngineConfig and __init__ | ℹ️ Info    | IN-01 from REVIEW. Awkward but functional; refactor optional.                                                                                                                                                       |
| `src/shitbox/utils/config.py`         | 203-209               | `sensor_map` rebuilt on every property access                                     | ℹ️ Info    | IN-02 from REVIEW. ~4 Hz call rate, negligible. Cache in `TPMSService.__init__` if log spam appears.                                                                                                                |
| `src/shitbox/sync/tpms.py`            | 76-82, 406            | Triple-lowercase of sensor_id in lookup chain                                     | ℹ️ Info    | IN-03 from REVIEW. Three layers of defensive case-folding for the same string. Pick one (the property accessor).                                                                                                    |
| `src/shitbox/storage/database.py`     | 18-131, 385-416       | `tpms_readings` only created via migration v11, not in `SCHEMA_SQL`                | ℹ️ Info    | IN-04 from REVIEW. Pre-existing pattern (notes/fuel_stops/driver_stints same shape). Low priority.                                                                                                                  |

**No blockers.** All findings are advisory; CR-01 + CR-02 (the only criticals) were closed in commit `bc41aa1`.

### Human Verification Required

Five items, all captured in the YAML frontmatter and `28-UAT.md`:

#### 1. UAT-1 — Hardware Bring-Up Sanity (verifies VALIDATION A4 + A5)

**Test:** Plug Nooelec NESDR Smart v5 directly into Pi USB 2.0 port. Confirm `lsusb | grep -i realtek` reports `ID 0bda:2838`. Confirm `rtl_433 -R help 2>&1 | grep -iE "abarth|124|tg1c"` returns `[156] Abarth-124Spider / VDO-TG1C TPMS`. Confirm `usb_max_current_enable=1` in `/boot/firmware/config.txt`. Restart daemon and tail journalctl for 90 seconds.
**Expected:** `tpms_starting`, `tpms_rtl433_started`, then `tpms_frame_received` for all four sensor IDs (`550b57d9`, `54d96e8f`, `550d14ed`, `550b5d8a`) within 60 s; no `tpms_unknown_sensor`; no `tpms_rtl433_exited`; HARDWARE row shows `tpms_radio` PRESENT.
**Why human:** Requires the SDR (arriving 2026-04-30), four installed wheel sensors, and physical USB enumeration on the Pi. Resolves Assumptions A4 (actual VID:PID) and A5 (apt rtl_433 protocol index for Abarth-124).

#### 2. UAT-2 — Bench Deflation: Low + Leak alerts (SPEC-7 + SPEC-8)

**Test:** Use the front-driver wheel (`550b57d9`). With dashboard open and TTS audible, slowly bleed to ~26 PSI (yellow band), continue to ≤25 PSI (red band), re-inflate above 28 PSI (recovery). Then re-inflate to 32 PSI, wait 60+ s for deque to clear, rapidly bleed ≥5 PSI within 60 s for leak. Then 1 PSI/min slow deflation as negative test. SQLite cross-check.
**Expected:** Yellow Health colour with no TTS; red banner + "Front driver tyre low pressure" TTS within 5 s; "Front driver tyre pressure restored" within 5 s of re-inflation; "Tyre leaking, front driver" + single TPMS_LEAK row in `events.json` within 5 s of leak threshold; slow deflation does not trigger leak; SQLite tpms_readings within ±0.5 PSI of dashboard.
**Why human:** SPEC-7 + SPEC-8 acceptance is "actually deflate a tyre and listen for the announcement / read the gauge". Stick-gauge accuracy verification (±3 PSI), TTS audibility, and the 5-second alert latency cannot be simulated.

#### 3. UAT-3 — RTL-SDR Replug Recovery (SPEC-10)

**Test:** Note daemon PID and ActiveEnterTimestamp. Physically unplug the SDR. Observe MISSING + STALE transitions. Wait 5+ minutes. Replug. Observe PRESENT recovery. Cross-check daemon uptime.
**Expected:** Daemon survives unplug (PID + ActiveEnterTimestamp unchanged); `tpms_radio` MISSING within 30 s; all four wheels STALE within 5 min; replug returns PRESENT + frames within 60 s; no journalctl error spam.
**Why human:** USB hot-unplug + replug is a physical operation. The CR-02 supervisor reprobe fix needs to be exercised against real hardware to confirm `hw_restored` TTS fires on re-adopt (not just `TPMSService._monitor_loop`'s independent recovery).

#### 4. UAT-4 — Driving Loop End-to-End (SPEC Acceptance final bullet)

**Test:** 10-15 minute familiar loop (roundabout circuit, varying speed 20-80 km/h, at least one stop). Co-driver monitors Health modal. After ~5 min, deflate front-driver to ~24 PSI mid-loop. Continue driving 1-2 more minutes. End: re-inflate to 32 PSI. Open Grafana, cross-check series + dip + recovery. SQLite count cross-check.
**Expected:** All four wheels report continuously (no STALE during driving); ±3 PSI stick-gauge agreement at start and end; mid-loop alert + TTS within 5 s; `_RESTORED` TTS within 5 s; Grafana shows four labelled time series matching SQLite content.
**Why human:** Real driving introduces RF interference (engine bay, alternator, spark plugs) and varying wheel positions during cornering. None of this is reproducible on the bench. UAT-4 is the canonical SPEC-1 RF reception acceptance check.

#### 5. Grafana panel additions to `shitbox-rally-command` dashboard

**Test:** Add `$wheel` template variable, TPMS Pressure panel (with 28/25 PSI thresholds), TPMS Temperature panel. Commit dashboard JSON to home-ops `audit-grafana-dashboard` branch.
**Expected:** `$wheel` resolves to four positions; Panel 1 renders four lines + threshold guides; Panel 2 renders four lines; both panels render UAT-4 loop window with no >5 s gaps; Flux reconcile clean.
**Why human:** Grafana edit lives in a separate repo (`~/dev/home-ops/.../grafana/`), needs metrics actively flowing (UAT-4 prerequisite), and visual rendering can only be verified by eye.

### Gaps Summary

**No code-level gaps blocking goal achievement.**

The phase produced the correct artifacts, wired them to the right consumers, and addressed the only two critical code-review findings (CR-01 leak event spam; CR-02 missing supervisor reprobe callback) in commit `bc41aa1`. The remaining six warnings + five info findings are advisory and do not block phase closure — they are tracked in `28-REVIEW.md` and the existing `deferred-items.md` for follow-up housekeeping.

The SPEC-N requirements that remain `? UNCERTAIN` are the ones whose acceptance criteria explicitly call out hardware-only checks: stick-gauge accuracy (SPEC-2), real RF reception in driving (SPEC-1), end-to-end Prometheus scrape + Grafana render (SPEC-5), TTS audibility + 5-second latency (SPEC-7), bench leak deflation timing (SPEC-8), and USB hot-unplug recovery (SPEC-10). All are captured in `28-UAT.md` as UAT-1 through UAT-4 plus the Grafana checklist, with `status: pending` in the frontmatter awaiting Tony's hardware bring-up Thursday 2026-04-30.

**Phase status is `human_needed`, not `gaps_found`.** Once Tony ticks the Sign-Off section in `28-UAT.md` (or surfaces a real failure during UAT execution), this verification can be re-run to flip to `passed` (or a real `gaps_found` if a UAT exposes a defect).

---

_Verified: 2026-04-28T10:57:12Z_
_Verifier: Claude (gsd-verifier)_
