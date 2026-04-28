---
phase: 28
slug: tpms-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-28
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `28-RESEARCH.md § Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (already in `pyproject.toml [dev]`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (existing) |
| **Quick run command** | `pytest tests/test_tpms_*.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~5–10 sec (TPMS-only); ~30–45 sec (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_tpms_*.py -x`
- **After every plan wave:** Run `pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds (quick run)

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| 1 | rtl_433 frame parsed, dispatched | unit | `pytest tests/test_tpms_parser.py::test_valid_abarth_frame -x` | ❌ W0 | ⬜ pending |
| 1 | unknown sensor ID logged + dropped | unit | `pytest tests/test_tpms_parser.py::test_unknown_sensor_drop -x` | ❌ W0 | ⬜ pending |
| 1 | malformed JSON line tolerated | unit | `pytest tests/test_tpms_parser.py::test_malformed_json_skipped -x` | ❌ W0 | ⬜ pending |
| 2 | × 2.45 correction applied | unit | `pytest tests/test_tpms_parser.py::test_pressure_correction -x` | ❌ W0 | ⬜ pending |
| 2 | kPa → PSI conversion | unit | `pytest tests/test_tpms_parser.py::test_kpa_to_psi -x` | ❌ W0 | ⬜ pending |
| 3 | wheel position lookup | unit | `pytest tests/test_tpms_parser.py::test_wheel_mapping -x` | ❌ W0 | ⬜ pending |
| 4 | schema migration v10 → v11 | integration | `pytest tests/test_tpms_database.py::test_migrate_v11 -x` | ❌ W0 | ⬜ pending |
| 4 | insert + retrieve roundtrip | integration | `pytest tests/test_tpms_database.py::test_insert_retrieve -x` | ❌ W0 | ⬜ pending |
| 5 | metric format with wheel label | unit | `pytest tests/test_tpms_database.py::test_prometheus_metric_shape -x` | ❌ W0 | ⬜ pending |
| 5 | cursor advance | integration | `pytest tests/test_tpms_database.py::test_cursor_advance -x` | ❌ W0 | ⬜ pending |
| 6 | `_tpms_payload` always 4 rows | unit | `pytest tests/test_dashboard.py::test_tpms_payload_four_wheels -x` | ❌ W0 | ⬜ pending |
| 6 | NO DATA before first frame | unit | `pytest tests/test_dashboard.py::test_tpms_payload_no_data -x` | ❌ W0 | ⬜ pending |
| 7 | red threshold fires once on transition | unit | `pytest tests/test_tpms_alerts.py::test_low_pressure_red_fires -x` | ❌ W0 | ⬜ pending |
| 7 | yellow does NOT fire TTS | unit | `pytest tests/test_tpms_alerts.py::test_yellow_no_tts -x` | ❌ W0 | ⬜ pending |
| 7 | `_RESTORED` on re-inflation | unit | `pytest tests/test_tpms_alerts.py::test_low_pressure_restored -x` | ❌ W0 | ⬜ pending |
| 8 | leak fires on ≥5 PSI / 60s | unit | `pytest tests/test_tpms_leak.py::test_leak_detected -x` | ❌ W0 | ⬜ pending |
| 8 | slow deflation does not fire | unit | `pytest tests/test_tpms_leak.py::test_slow_deflation_no_leak -x` | ❌ W0 | ⬜ pending |
| 8 | `TPMS_LEAK` event written | integration | `pytest tests/test_tpms_leak.py::test_leak_writes_event_json -x` | ❌ W0 | ⬜ pending |
| 9 | wheel goes STALE after 5 min | unit | `pytest tests/test_tpms_alerts.py::test_stale_after_5min -x` | ❌ W0 | ⬜ pending |
| 9 | STALE clears on next frame | unit | `pytest tests/test_tpms_alerts.py::test_stale_clears -x` | ❌ W0 | ⬜ pending |
| 10 | `probe_usb_vid_pid` finds 0bda:2838 | unit | `pytest tests/test_tpms_subprocess.py::test_probe_finds_sdr -x` | ❌ W0 | ⬜ pending |
| 10 | probe returns False when missing | unit | `pytest tests/test_tpms_subprocess.py::test_probe_missing_sdr -x` | ❌ W0 | ⬜ pending |
| 1+10 | rtl_433 restart on death | integration | `pytest tests/test_tpms_subprocess.py::test_restart_on_exit -x` | ❌ W0 | ⬜ pending |
| 1+10 | stderr drain prevents block | integration | `pytest tests/test_tpms_subprocess.py::test_stderr_drained -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test files below are NEW. Existing `pytest` infrastructure + `conftest.py` fixture patterns from `test_alerts.py` and `test_thermal_monitor.py` cover what we need; no framework install required.

- [ ] `tests/test_tpms_parser.py` — JSON parsing, wheel mapping, pressure correction (REQ 1, 2, 3)
- [ ] `tests/test_tpms_database.py` — schema migration v11, insert/cursor, metric format (REQ 4, 5)
- [ ] `tests/test_tpms_alerts.py` — sustain + transition + recovery + stale (REQ 7, 9)
- [ ] `tests/test_tpms_leak.py` — deque-based leak detection + event recording (REQ 8)
- [ ] `tests/test_tpms_subprocess.py` — rtl_433 lifecycle, USB probe, stderr drain (REQ 1, 10)
- [ ] Extension to `tests/test_dashboard.py` — `_tpms_payload` shape (REQ 6)
- [ ] `tests/conftest.py` — `fake_rtl433_subprocess` and `fake_rtl433_frames` fixtures (shared across the new test files)

---

## Mock Strategies

**rtl_433 stdout simulation** — `FakeRtl433Process` test fixture emits canned JSON lines on stdout via a real OS pipe. Mirrors `test_ffmpeg_stall.py` simulation of ffmpeg.

**Deflation simulation** — feed a sequence of frames where one sensor's PSI drops by 6 PSI within 30 frames (≈30 seconds at 1 Hz/wheel). Assert `alerts.snapshot()` shows `TPMS_LEAK` fired exactly once.

**Stale-sensor simulation** — feed three frames for sensor X, then no frames for 360 simulated seconds. Use `time.monotonic` monkeypatch (existing project pattern in `test_thermal_monitor.py`). Assert wheel state == "stale".

**USB-missing simulation** — patch `subprocess.run` so `lsusb` returns output without `0bda:2838`. Assert `probe_usb_vid_pid` returns `False`, supervisor reports MISSING, daemon continues.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Driving UAT — all four wheels in Grafana while moving | SPEC Acceptance | RF reception varies in real driving | Plug in SDR, drive a familiar short loop, confirm all four wheels report regularly in Grafana with PSI matching a stick-gauge reference within ±3 PSI |
| Live deflation triggers banner + TTS | SPEC Acceptance | Real-time alert UAT requires the moving car loop | Deflate one tyre to <28 PSI mid-loop, confirm Health-page banner turns yellow/red and TTS speaks |
| RTL-SDR replug recovery | REQ 10 | Hardware-level USB hot-unplug behaviour | Unplug SDR for >30 sec while daemon running; replug; confirm Health page shows MISSING then PRESENT, no daemon restart needed |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency <10s (quick run)
- [ ] `nyquist_compliant: true` set in frontmatter (planner sets after Wave 0 design complete)

**Approval:** pending

---

## Assumptions to Verify at Hardware Bring-Up (Thursday 2026-04-30)

- **A4:** `lsusb` actually reports `0bda:2838` for the Nooelec NESDR Smart v5 (some Realtek 2832U variants report `0bda:2832`) — config field `tpms.usb_vid_pid` is configurable so this is a one-line YAML fix if it shifts.
- **A5:** `rtl_433 -R help` from the apt-installed 22.11 binary lists protocol 156 = Abarth-124Spider — verified against upstream master but apt version was tagged 2022-11.
