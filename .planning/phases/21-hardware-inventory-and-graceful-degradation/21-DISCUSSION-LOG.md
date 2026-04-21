# Phase 21: Hardware Inventory and Graceful Degradation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 21-hardware-inventory-and-graceful-degradation
**Areas discussed:** Manifest source of truth, Per-device criticality policy, Runtime loss detection + recovery, Status surface (OLED / dashboard / TTS / sync / website)

---

## Manifest source of truth

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: declared in config.yaml, verified at boot | Each expected device listed with role, bus, address/path, criticality. Boot probes and marks PRESENT/MISSING. Matches existing DS18B20 pattern. | ✓ |
| Pure dynamic: probe and adopt whatever is there | Scan i2cdetect + lsusb at boot, register every responsive device. Simpler, but 'new random device appeared' can't be distinguished from 'expected device present'. | |
| Pure static: declared only, no verification | Code assumes what config says. No new machinery, but doesn't actually solve boot-time presence validation — basically today's state. | |

**User's choice:** Hybrid. Recommended option.

| Option | Description | Selected |
|--------|-------------|----------|
| New top-level `hardware:` block | One place lists every device. Collectors read from this block. Existing sensor configs stay for tuning knobs. | ✓ |
| Augment existing sensor sections | Each sensor block gets a 'presence:' subsection. No new top-level key. Keeps device metadata next to its tuning. | |
| Derive from code + a presence override file | Canonical list lives in a Python module. config.yaml only overrides. Less config boilerplate but hardware additions require code changes. | |

**User's choice:** New top-level `hardware:` block. Recommended option.

---

## Per-device criticality policy

| Option | Description | Selected |
|--------|-------------|----------|
| Never refuse to boot — always start, degrade loudly | A rally car that won't start the logger is worse than one that logs partial data. Matches 'offline-first, survive everything' ethos. | ✓ |
| Refuse to boot without LSM6DSOX | IMU is the core — without it there's no events, no video triggers, no point. Simpler, harder recovery in the field. | |
| Configurable per-device via 'require_at_boot: true' | Each hardware entry can opt into boot-block. Default false. Adds config surface. | |

**User's choice:** Never refuse to boot. Recommended option.

| Option | Description | Selected |
|--------|-------------|----------|
| Accept proposed mapping (LSM6DSOX critical; INA226/GPS/front camera important; rest best_effort) | Captures what actually matters and matches existing code. | |
| Also promote INA226 to critical | Undervoltage is a systemic failure mode. | |
| Also promote front camera to critical | Video capture on events is the point of the whole capture path. | ✓ |
| I'll describe the adjustments | Freeform. | |

**User's choice:** Promote front camera to critical. Final mapping:
- **critical:** LSM6DSOX, front camera
- **important:** INA226, GPS
- **best_effort:** BME680, LIS3MDL, VEML7700, OLED, DS18B20×2, cabin camera, mic, button, HDMI

---

## Runtime loss detection + recovery

| Option | Description | Selected |
|--------|-------------|----------|
| Distributed detection + central HardwareState | Each collector keeps its own error handling; reports into a central state. A single HardwareSupervisor thread owns alert cadence. | ✓ |
| Central supervisor with periodic rescan | Supervisor re-probes the I2C bus every N seconds. Heavier but catches 'disconnected and collector already backed off' cases. | |
| Keep distributed, no new central state | Collectors keep doing what they do. Add a 'dump current hardware status' helper. Lightest touch. | |

**User's choice:** Distributed detection + central HardwareState. Recommended option.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — retry on a backoff for all tiers (5s → 15s → 60s → 5min cap) | Every device's collector retries setup on backoff. Crew can replug and carry on. | ✓ |
| Yes, but only for USB devices | USB unplug/replug is realistic; I2C locks get reset ladder. | |
| No — missing devices stay missing until restart | Simpler mental model. Replug does nothing without restart. | |

**User's choice:** Retry on backoff for all tiers. Recommended option.

---

## Status surface (OLED / dashboard / TTS / sync / website)

| Option | Description | Selected |
|--------|-------------|----------|
| Prometheus per-device up gauge | `shitbox_hardware_up{device,tier}` emitted every batch sync. Low effort, high payoff for remote monitoring. | |
| hardware.json rsynced to website | New JSON generator via CaptureSyncService. Could power a 'what's online' widget on the site. | |
| Include in events.json alongside existing fields | Every event payload carries hardware snapshot. Useful for post-mortem, adds noise. | |
| Pi-local only — don't leak hardware status off-box | Operational detail; crew sees it on OLED/dashboard, nobody else needs to know. Simpler. | ✓ |

**User's choice:** Pi-local only. (Multi-select question — no other options chosen.)
**Notes:** Deferred Prometheus gauge and hardware.json to potential future phases — explicitly listed in CONTEXT.md `<deferred>` section so they're not lost.

---

## Claude's Discretion

- Exact YAML shape of the `hardware:` block
- How `HardwareState` is threaded to consumers (singleton vs passed)
- OLED line layout within the 4-line budget
- TTS wording
- Dashboard panel visual treatment
- Exponential backoff implementation detail

## Deferred Ideas

- Prometheus `shitbox_hardware_up` gauge
- `hardware.json` rsynced to website + "what's online" badge
- Hardware status embedded in `events.json`
- Magnetometer (LIS3MDL) ellipsoid calibration (already deferred upstream)
- ESP32-based I2C buffering / TCA4307 hardening (separate memory)
- Manual recovery trigger (button long-press to force re-probe)
