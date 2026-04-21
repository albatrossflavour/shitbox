---
phase: 21
slug: hardware-inventory-and-graceful-degradation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/hardware/ -x -q` |
| **Full suite command** | `pytest --cov=shitbox` |
| **Estimated runtime** | ~30 seconds (quick), ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/hardware/ -x -q`
- **After every plan wave:** Run `pytest --cov=shitbox`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | HW-01..HW-05 | — | N/A | unit/integration | `pytest tests/hardware/` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*The planner will populate this table once task IDs are assigned.*

---

## Wave 0 Requirements

- [ ] `tests/hardware/__init__.py` — package marker
- [ ] `tests/hardware/conftest.py` — fixtures for fake I2C bus, fake USB devices, fake 1-wire probes, fake GPIO, fake HDMI sysfs
- [ ] `tests/hardware/test_manifest.py` — HW-01: `hardware:` block loads into typed dataclass with all declared devices
- [ ] `tests/hardware/test_boot_probe.py` — HW-02: boot probe correctly distinguishes present vs absent per bus
- [ ] `tests/hardware/test_state.py` — state transitions (PRESENT → MISSING → PRESENT) and observer notification
- [ ] `tests/hardware/test_supervisor.py` — HW-03 + HW-04: alert cadence per tier + exponential backoff schedule (5s → 15s → 60s → 5 min cap)
- [ ] `tests/hardware/test_bme680_recovery.py` — canonical acceptance case from HW-04 (BME680 cold-boot init failure → supervised retry → recovered TTS)
- [ ] `tests/hardware/test_daemon_boot.py` — HW-05: UnifiedEngine boots with all critical devices absent, no crash loop

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OLED status line legibility | HW-02/HW-03 | Physical display; font rendering quality not verifiable in unit test | Boot Pi with camera unplugged, confirm OLED line 3 shows inverted MISSING token within one refresh |
| Piper TTS wording audible | HW-03/HW-04 | Audio output device and speech intelligibility | Disconnect front camera mid-drive, confirm TTS speaks "camera offline" within critical-tier cadence; reconnect, confirm "camera restored" |
| Dashboard hardware panel render | HW-02/HW-03 | Browser rendering + SSE live behaviour | Load dashboard in Chromium kiosk, unplug USB GPS, confirm panel flips orange with badge + last-seen timestamp within one SSE tick |
| BME680 cold-boot end-to-end | HW-04 (canonical) | Reproduces a real boot-timing race; needs physical cold boot, not warm reboot | Power-cycle Pi (full off → on), observe logs for BME680 initial setup failure, observe supervisor retry on 5s/15s/60s backoff, confirm successful init and "env sensor restored" TTS |
| Daemon boots with all critical hardware absent | HW-05 | Requires physically disconnecting IMU + front camera | Power Pi with hat removed and front camera unplugged, confirm systemd status `active (running)`, no crash loop, OLED shows missing tokens |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
