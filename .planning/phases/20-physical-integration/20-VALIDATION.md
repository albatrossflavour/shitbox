---
phase: 20
slug: physical-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Physical verification (caliper measurements, visual inspection, boot tests) |
| **Config file** | none — no software test infrastructure needed |
| **Quick run command** | `ssh laser "systemctl is-active shitbox-telemetry"` |
| **Full suite command** | `ssh laser "systemctl is-active shitbox-telemetry && python3 -c 'from shitbox.utils.config import load_config; c = load_config(); print(\"config OK\")'"` |
| **Estimated runtime** | ~5 seconds (remote commands); physical verification is manual |

---

## Sampling Rate

- **After every task commit:** Visual inspection of SCAD renders / STL output
- **After every plan wave:** Physical measurement verification against SCAD parameters
- **Before `/gsd-verify-work`:** Full system boot test in car
- **Max feedback latency:** N/A (physical integration — feedback is measurement-based)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 0 | — | — | N/A | manual | `caliper measurements recorded` | N/A | pending |
| 20-01-02 | 01 | 1 | — | — | N/A | manual | `openscad -o pi-case.stl hardware/pi-case.scad` | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] Physical measurements taken with calipers: Pi stack height, screen dimensions, GX12 body diameter, SMA bulkhead diameter
- [ ] Verify bench wiring is complete (GPS to perma-proto, all I2C devices, 1-Wire)
- [ ] Confirm fan model (resolve 30mm vs 40mm NF-A4 discrepancy from D-04)

*Physical prerequisites — no software test infrastructure needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pi case fits assembled stack | SC-1 | Physical fit check | Insert Pi stack, verify clearance on all sides, fan seated |
| Screen bezel fits Waveshare 7" | SC-4 | Physical fit check | Insert screen, verify edge grip and VESA alignment |
| Cable loom routes cleanly | SC-3 | Visual inspection | Check no pinch points, strain relief at connectors |
| System boots in car | SC-7 | Integration test | Power on from car battery, verify telemetry service starts |
| Fan provides airflow | SC-1 | Thermal test | Run under load for 30min, check temps stay below 70C |

---

## Validation Sign-Off

- [ ] All tasks have manual verify steps or Wave 0 dependencies
- [ ] Sampling continuity: measurement checkpoints between design tasks
- [ ] Wave 0 covers all physical measurement prerequisites
- [ ] No software test gaps (phase is physical integration only)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
