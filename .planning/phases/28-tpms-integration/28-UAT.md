---
status: pending
phase: 28-tpms-integration
source:
  - 28-VALIDATION.md (Manual-Only Verifications)
  - 28-SPEC.md (Acceptance Criteria, last 3 bullets)
  - 28-04-SUMMARY.md (TPMSService, alert subtypes)
  - 28-05-SUMMARY.md (/sse/slow shape, Prometheus metrics, engine wiring)
hardware_required:
  - "Nooelec NESDR Smart v5 (RTL2832U + R820T2, expected VID:PID 0bda:2838)"
  - "Four Abarth-124 / VDO TG1C TPMS sensors fitted to wheels"
  - "Pi 5 (laser, 10.10.20.107) running latest shitbox daemon"
  - "Stick gauge (digital preferred, analog acceptable)"
  - "USB speaker active for audible TTS"
expected_run_date: 2026-04-30
owner: Tony
---

# Phase 28 — TPMS Integration: Manual UAT Scripts

**Status:** pending hardware bring-up (Thursday 2026-04-30 — Nooelec NESDR Smart v5 arrival).

This file scripts the three manual checks called out in `28-VALIDATION.md § Manual-Only Verifications`, plus a hardware-bring-up sanity gate that runs first and a Grafana panel checklist that runs last. Every other Phase 28 acceptance criterion has automated coverage (548 pytest tests green at end of Plan 28-05). What's left needs a real RF environment, a real SDR, and a real tyre to deflate.

## Pre-Reqs

- [ ] Plans 28-01 through 28-05 shipped + green pytest suite on the Pi.
- [ ] `systemctl status shitbox-telemetry` shows `active (running)`.
- [ ] `rtl_433 -V` reports `22.11-1` or newer (apt-installed, Pi OS bookworm).
- [ ] All four TPMS sensors fitted to wheels, vehicle stationary on level ground.
- [ ] Stick gauge to hand. Note its reading style (psi vs kPa) and accuracy class.
- [ ] USB speaker audible from outside the car (for TTS verification under UAT-2).
- [ ] Phone or laptop on the rally wifi with browser open to `http://10.10.20.107:8080/` Health modal.

## Wheel Reference

| Label | Position         | Sensor ID  |
| ----- | ---------------- | ---------- |
| FD    | front-driver     | `550b57d9` |
| FP    | front-passenger  | `54d96e8f` |
| RD    | rear-driver      | `550d14ed` |
| RP    | rear-passenger   | `550b5d8a` |

Sensor IDs map via the `tpms.sensors` block in `config/config.yaml`. If a frame arrives with a different ID, the daemon logs `tpms_unknown_sensor` and discards the frame — that's a sign an aftermarket sensor was swapped without updating config.

---

## UAT-1 — Hardware Bring-Up Sanity (verifies VALIDATION A4 + A5)

**Why first:** the apt-installed `rtl_433` and the Nooelec NESDR's actual VID:PID need to be checked against the assumptions baked into `config.yaml` before anything else will work. Without this, UAT-2/3/4 can fail for trivial reasons that mask real issues.

### UAT-1 steps

1. Plug the Nooelec NESDR Smart v5 into a direct USB 2.0 port on the Pi. Not behind a hub — bus contention causes sample drops (project memory `reference_brain_note`).
2. SSH to the Pi: `ssh tgreen@10.10.20.107`.
3. Confirm the chipset enumerates:

   ```bash
   lsusb | grep -i realtek
   ```

   Expected: a line containing `ID 0bda:2838 Realtek Semiconductor Corp.`. Some Realtek 2832U variants report `0bda:2832`. If the VID:PID differs, update `tpms.usb_vid_pid` in `config/config.yaml` and restart the daemon. Resolves Assumption A4.
4. Confirm protocol 156 is the Abarth-124 decoder:

   ```bash
   rtl_433 -R help 2>&1 | grep -iE "abarth|124|tg1c"
   ```

   Expected: `[156]  Abarth-124Spider / VDO-TG1C TPMS`. If the index has shifted in the apt-packaged build, update `tpms.rtl433_protocol_id` in `config/config.yaml`. Resolves Assumption A5.
5. Confirm the Pi 5 USB current cap is lifted:

   ```bash
   grep usb_max_current_enable /boot/firmware/config.txt
   ```

   Expected: `usb_max_current_enable=1`. If absent, append it and reboot before continuing — the default 600 mA Pi 5 cap will drop the SDR under load.
6. Restart the daemon and tail the log for 90 seconds:

   ```bash
   sudo systemctl restart shitbox-telemetry
   sudo journalctl -u shitbox-telemetry -f --since "30 seconds ago"
   ```

   Expected log keywords (in order): `tpms_starting`, `tpms_rtl433_started`, then `tpms_frame_received` lines for each of the four configured sensor IDs within ~60 seconds.

### UAT-1 — Pass criteria

- [ ] All four sensor IDs (`550b57d9`, `54d96e8f`, `550d14ed`, `550b5d8a`) appear in at least one `tpms_frame_received` log line within 2 minutes.
- [ ] No `tpms_unknown_sensor` lines (the configured map matches reality).
- [ ] No `tpms_rtl433_exited` lines (subprocess stable; if it dies the monitor thread restarts within 5 s).
- [ ] Health modal HARDWARE section shows `tpms_radio` PRESENT, criticality `best_effort`.

Result: [ ] pass [ ] fail [ ] blocked. Notes (observed VID:PID, observed protocol index, anything unexpected): _____.

---

## UAT-2 — Bench Deflation: Low + Leak Alerts (verifies SPEC-7 + SPEC-8)

**Why:** SPEC-7 (red banner + TTS at PSI ≤ 25 sustained) and SPEC-8 (≥5 PSI / 60 s leak detection) are unverifiable without actually deflating a tyre. Use the front-driver wheel (sensor `550b57d9`) as the test target — closest to the kerb if you're working solo. Yellow-band behaviour (Health-page colour only, no TTS) is exercised on the way to the red threshold.

### UAT-2 setup

- Stick gauge (digital preferred for tighter ±3 PSI assertion).
- Browser open to `http://10.10.20.107:8080/` → Health modal, scroll to TPMS section.
- USB speaker audible. Set volume so cabin TTS is clear from outside the car.
- A second SSH session running `sudo journalctl -u shitbox-telemetry -f` so alert log lines can be cross-referenced as they fire.

### UAT-2 steps

1. Baseline snapshot. Note the starting front-driver PSI from the dashboard (should be 31–32 PSI). Compare against stick-gauge — record the delta. Expected: dashboard PSI within ±3 PSI of stick-gauge.
2. Sustained-low test (SPEC-7 yellow band):
   1. Slowly bleed the FD tyre via the valve core. Aim for ~26 PSI (yellow band, 25 < PSI ≤ 28) over 30–60 seconds.
   2. Expected: FD row on the dashboard turns yellow with `LOW` status (glyph ▲, colour `#d29922`). No TTS. Yellow is intentionally a Health-page colour only — see `28-04-SUMMARY.md § Alert Subtype Naming Convention`, "Yellow band ... is NOT wired into `alerts.fire_alert`".
3. Sustained-low test (SPEC-7 red band):
   1. Continue bleeding until PSI ≤ 25.
   2. Expected within ~5 seconds (sustain_required = 2 frames at ~1 Hz):
      - FD row turns red with `CRITICAL` status (glyph ✖, colour `#da3633`).
      - TTS speaks: "Front driver tyre low pressure" (utterance D-04).
      - Log line: `tpms_alert_fired subtype=TPMS_LOW_FRONT_DRIVER`.
4. Recovery:
   1. Re-inflate above 28 PSI.
   2. Expected within ~5 seconds:
      - TTS speaks: "Front driver tyre pressure restored" (utterance D-07).
      - FD row returns to green `OK`.
      - Log line: `tpms_alert_recovered subtype=TPMS_LOW_FRONT_DRIVER_RESTORED`.
5. Leak test (SPEC-8 ≥5 PSI / 60 s):
   1. Re-inflate to ~32 PSI. Wait 60 + seconds for the per-wheel deque (60-frame window) to clear stale samples.
   2. Open the valve core fully and bleed rapidly so the wheel drops ≥5 PSI within 60 seconds (down to ~27 PSI is enough — no need to go below 25).
   3. Expected within ~5 seconds of crossing the 5 PSI delta:
      - TTS speaks: "Tyre leaking, front driver" (utterance D-05).
      - FD row turns red with `CRITICAL`.
      - Log line: `tpms_leak_detected wheel=front-driver`.
      - `events.json` on the Pi (`/var/lib/shitbox/captures/events.json`) gets a new entry of type `TPMS_LEAK` for FD, with `peak_value` set to the PSI that triggered the alarm and `peak_ax/ay/az = 0.0` (synthetic, no IMU sample — see `28-04-SUMMARY.md § Event Required Fields`).
   4. Re-inflate to ~32 PSI; wait 60+ seconds for the deque window to clear.
   5. Expected: FD row returns to green. No `_RESTORED` TTS for the leak — leak alerts are single-shot by design (`28-04-SUMMARY.md § Leak alert has no recovery wiring`).
6. Slow-deflation negative test (SPEC-8 false-positive guard):
   1. Re-inflate to ~32 PSI.
   2. Bleed very slowly — aim for 1 PSI lost over 60+ seconds. Roughly the rate a cold tyre warms up at, not a leak.
   3. Expected: no TTS, no `tpms_leak_detected` log line, no red banner. PSI drifts down by 1–2 over 2–3 minutes; row stays green or transitions to yellow only.
7. Storage cross-check:

   ```bash
   sqlite3 /var/lib/shitbox/telemetry.db \
     'SELECT wheel, pressure_psi, datetime(timestamp,"unixepoch","localtime") FROM tpms_readings ORDER BY id DESC LIMIT 8'
   ```

   Expected: the most recent FD readings line up with the dashboard values within ±0.5 PSI (one sample's worth of jitter).

### UAT-2 — Pass criteria

- [ ] Dashboard PSI within ±3 PSI of stick-gauge at every checkpoint (resolves SPEC Acceptance bullet 2).
- [ ] Yellow band (25 < PSI ≤ 28) shows on dashboard but no TTS fires.
- [ ] Red banner + TTS fires within 5 s of crossing PSI ≤ 25.
- [ ] `_RESTORED` TTS fires within 5 s of re-inflating above 28 PSI.
- [ ] Leak alert fires within 5 s of crossing the 5 PSI / 60 s threshold.
- [ ] `events.json` contains a `TPMS_LEAK` event for the front-driver wheel.
- [ ] Slow 1 PSI / minute deflation does not trigger the leak alert.
- [ ] Stored PSI matches dashboard within one sample (SQLite cross-check).

Result: [ ] pass [ ] fail [ ] blocked. Notes (measured PSI deltas, TTS clarity, dashboard render time): _____.

---

## UAT-3 — RTL-SDR Replug Recovery (verifies SPEC-10)

**Why:** SPEC-10 requires graceful degradation. The daemon must keep running when the SDR vanishes mid-flight (loose USB connector, bus enumeration glitch, antenna pulled), and it must re-adopt within the `HardwareSupervisor` exponential-backoff window when the device returns. The 5-second backoff inside `TPMSService._monitor_loop` plus the manifest-level supervisor combine for the recovery path.

### UAT-3 steps

1. Confirm the daemon is running and TPMS frames are flowing:

   ```bash
   sudo journalctl -u shitbox-telemetry -f | grep tpms_frame_received
   ```

   Frames should arrive at roughly 1 / second / wheel.
2. On the Health modal, confirm the `tpms_radio` row in the HARDWARE section shows `PRESENT` (criticality `best_effort`, glyph green).
3. Note the daemon PID and start time:

   ```bash
   systemctl show -p MainPID,ActiveEnterTimestamp shitbox-telemetry
   ```

4. Physical unplug. Unplug the SDR from the Pi USB port.
5. Expected within ~30 seconds:
   - Log lines (in order):
     - `tpms_rtl433_exited` (subprocess died because its USB device disappeared).
     - `tpms_sdr_missing` (probe_usb_vid_pid returned False on the next monitor tick).
     - `hw_state_changed role=tpms_radio state=missing`.
   - HARDWARE row `tpms_radio` flips to `MISSING` (orange glyph for `best_effort` criticality — degraded, not critical).
   - The daemon does NOT restart. `MainPID` and `ActiveEnterTimestamp` from step 3 are unchanged.
6. Wait at least 5 minutes so the per-wheel STALE timeout (`stale_timeout_seconds: 300`) elapses. Expected: all four TPMS rows on the Health modal go to `STALE` (glyph ◌, amber `#d29922`). No TTS — STALE is a Health-page-only state per SPEC-9.
7. Replug. Plug the SDR back into the same USB port.
8. Expected within ~30–60 seconds:
   - `lsusb | grep -i realtek` shows `0bda:2838` (or whatever VID:PID UAT-1 confirmed).
   - `hw_state_changed role=tpms_radio state=present` log line.
   - `tpms_rtl433_started` followed by fresh `tpms_frame_received` lines for each wheel.
   - Dashboard FD/FP/RD/RP rows return to `OK` / `LOW` / `CRITICAL` based on actual current PSI; STALE clears on the next received frame per SPEC-9 ("clears within one heartbeat ≤ 2 s").
9. Daemon-uptime cross-check:

   ```bash
   systemctl show -p MainPID,ActiveEnterTimestamp shitbox-telemetry
   ```

   Expected: `MainPID` and `ActiveEnterTimestamp` identical to step 3 — the daemon never restarted, only the rtl_433 child subprocess did.

### UAT-3 — Pass criteria

- [ ] Daemon does not exit or restart during the unplug window (PID + start time unchanged).
- [ ] `tpms_radio` MISSING surfaces on the HARDWARE row within 30 seconds of unplug.
- [ ] All four TPMS rows go STALE within 5 minutes of unplug.
- [ ] Replug results in PRESENT + frames flowing again within 1 minute.
- [ ] No journalctl error spam during the missing window (back-off working — at most one `tpms_sdr_missing` log per ~5 s monitor tick).

Result: [ ] pass [ ] fail [ ] blocked. Notes (time to MISSING, time to PRESENT, any error spam observed): _____.

---

## UAT-4 — Driving Loop End-to-End (the canonical SPEC Acceptance final gate)

**Why:** the last bullet of `28-SPEC.md § Acceptance Criteria`. RF reception in real driving (engine vibration, RF interference from spark plugs / alternator, varying wheel positions during cornering) is meaningfully different from a stationary bench. Without this UAT, "code green" doesn't mean "rally ready". Best run with a co-driver — the driver should not be reading the dashboard.

### UAT-4 setup

- UAT-1 + UAT-2 already passed (no point driving with broken bench coverage).
- Stick gauge in the car.
- Co-driver (or stationary-and-watch crew) on the rally wifi with the Health modal open.
- Phone with cellular to bring up Grafana when the loop ends.

### UAT-4 steps

1. Pre-drive baseline. With the engine running and the car stationary on level ground, stick-gauge all four tyres and note the values. Confirm the Health modal shows the same values (±3 PSI). Confirm all four states are `OK`.
2. Drive a familiar 10–15 minute loop — local roundabout circuit, ideally including at least one stop sign and varying surface (smooth tarmac plus some coarse chip). Vary speed: 20–80 km/h.
3. Mid-loop monitoring. Co-driver glances at the Health modal every 2–3 minutes. Confirm all four wheels keep showing `OK` with PSI within ±3 PSI of the pre-drive stick-gauge readings. No wheel should go STALE during driving — RF reception in motion is the single biggest unknown going into this UAT.
4. Mid-loop deflation. After ~5 minutes of driving, stop in a safe place. Deflate one wheel (front-driver again — easiest to access from the driver's side) via the valve core to ~24 PSI (below the 25 PSI red threshold).
5. Expected within ~5 seconds of crossing PSI ≤ 25:
   - TTS speaks: "Front driver tyre low pressure".
   - FD dashboard row turns red `CRITICAL`.
6. Resume driving for 1–2 more minutes. Confirm the alert sticks — no flapping back to `OK` on weaker signal during cornering or under engine bay RF noise.
7. End of loop. Stop, re-inflate FD to ~32 PSI, wait for `_RESTORED` TTS.
8. Grafana cross-check. Open `http://grafana.homelab.local/d/shitbox-rally-command` (the existing dashboard, panels added per the checklist below). Confirm:
   - `shitbox_tpms_pressure_psi` shows four time series (one per wheel) covering the loop duration.
   - FD's series shows the deflation dip and recovery.
   - `shitbox_tpms_temperature_c` shows four time series (informational, no alert thresholds).
9. SQLite-vs-Grafana sanity:

   ```bash
   sqlite3 /var/lib/shitbox/telemetry.db \
     'SELECT wheel, COUNT(*) FROM tpms_readings WHERE timestamp > strftime("%s","now","-30 minutes") GROUP BY wheel'
   ```

   Expected: four rows, each with hundreds of samples (~1 sample / wheel / second over a 10–15 minute drive). Counts within ~10 % of each other (RF reception evenly balanced).

### UAT-4 — Pass criteria

- [ ] All four wheels report frames continuously through the loop (no wheel goes STALE during driving).
- [ ] Stick-gauge to dashboard PSI agreement within ±3 PSI at start and end of loop.
- [ ] Mid-loop deflation alert + TTS fires within 5 seconds.
- [ ] Re-inflation `_RESTORED` TTS fires within 5 seconds.
- [ ] Grafana panels show four labelled time series matching SQLite content within one sample.

Result: [ ] pass [ ] fail [ ] blocked. Notes (route, RF anomalies, wheel-count balance, mid-loop alert latency): _____.

---

## Grafana Panel Checklist (separate-repo task)

The home-ops Grafana repo lives at `~/dev/home-ops/kubernetes/apps/observability/grafana/app/dashboards/`. The dashboard JSON file is `shitbox-rally-command.json`. The standing audit-Grafana-dashboard todo from 2026-04-26 dovetails with this — fold the TPMS panel additions into that pass.

The panels are added by hand (Grafana UI → Dashboard settings → JSON model, or direct edit in the JSON file followed by Flux reconcile). Keep the existing dashboard structure; insert the new panels under a dedicated "TPMS" row.

### Template variable

Add a single template variable `$wheel` so the panels can be filtered to one wheel or stay on `All`:

```json
{
  "name": "wheel",
  "label": "Wheel",
  "type": "query",
  "datasource": "Prometheus",
  "query": "label_values(shitbox_tpms_pressure_psi, wheel)",
  "refresh": 2,
  "includeAll": true,
  "multi": true,
  "current": { "selected": false, "text": "All", "value": "$__all" }
}
```

`refresh: 2` re-resolves on dashboard load, which is what we want when wheel labels are stable but rare changes happen (e.g. swapping a sensor mid-rally, future work).

### Panel 1: TPMS Pressure (PSI)

| Field          | Value                                                           |
| -------------- | --------------------------------------------------------------- |
| Title          | `TPMS Pressure (PSI)`                                           |
| Type           | Time series                                                     |
| PromQL         | `shitbox_tpms_pressure_psi{wheel=~"$wheel"}`                    |
| Legend         | `{{wheel}}`                                                     |
| Y-axis unit    | `pressureppsi` (Grafana built-in; "PSI" as fallback label)      |
| Y-axis range   | min 20, max 40 (auto override OK)                               |
| Thresholds     | Yellow line at `28` (low), Red line at `25` (critical)          |
| Threshold mode | `absolute`                                                      |
| Stacking       | None                                                            |

PromQL fragment for direct paste:

```promql
shitbox_tpms_pressure_psi{wheel=~"$wheel"}
```

Threshold JSON snippet (paste into the panel's `fieldConfig.defaults.thresholds`):

```json
{
  "mode": "absolute",
  "steps": [
    { "color": "red",   "value": null },
    { "color": "yellow","value": 25 },
    { "color": "green", "value": 28 }
  ]
}
```

The thresholds match the SPEC-7 cut-points (28 PSI yellow, 25 PSI red). Colours invert the dashboard glyph palette so the band is visible behind the line.

### Panel 2: TPMS Temperature (°C)

| Field          | Value                                                           |
| -------------- | --------------------------------------------------------------- |
| Title          | `TPMS Temperature (°C)`                                         |
| Type           | Time series                                                     |
| PromQL         | `shitbox_tpms_temperature_c{wheel=~"$wheel"}`                   |
| Legend         | `{{wheel}}`                                                     |
| Y-axis unit    | `celsius`                                                       |
| Y-axis range   | auto                                                            |
| Thresholds     | None — temperature is informational only (SPEC § Out of scope)  |

PromQL fragment for direct paste:

```promql
shitbox_tpms_temperature_c{wheel=~"$wheel"}
```

### Workflow

1. After UAT-4 confirms metrics flowing into Prometheus, open the Grafana UI: Dashboards → `shitbox-rally-command` → Edit.
2. Add a new row called "TPMS" between the existing IMU row and the Telemetry row (or wherever fits the dashboard's current top-down narrative).
3. Add Panel 1 + Panel 2 inside that row, half-width each.
4. Add the `$wheel` template variable via Dashboard settings → Variables.
5. Save dashboard with note `Phase 28 TPMS panels`.
6. Export as JSON: Dashboard settings → JSON model → copy into `~/dev/home-ops/kubernetes/apps/observability/grafana/app/dashboards/shitbox-rally-command.json`.
7. Commit on the `audit-grafana-dashboard` branch (the standing todo opened that branch — reuse it). Push; Flux reconciles within a few minutes; grafana-operator survives the reload.

### Grafana — Pass criteria

- [ ] `$wheel` template variable resolves to four values: `front-driver`, `front-passenger`, `rear-driver`, `rear-passenger`.
- [ ] Panel 1 (Pressure) shows four lines when `$wheel = All`, plus the 28 PSI yellow and 25 PSI red threshold lines.
- [ ] Panel 2 (Temperature) shows four lines when `$wheel = All`, no threshold lines.
- [ ] Both panels render data covering the UAT-4 loop window with no gaps wider than 5 seconds (RF reception sanity).
- [ ] Dashboard JSON committed to home-ops `audit-grafana-dashboard` branch; Flux reconcile clean.

---

## Sign-Off

- [ ] UAT-1 passed (hardware bring-up sanity)
- [ ] UAT-2 passed (bench deflation: low + leak + slow)
- [ ] UAT-3 passed (RTL-SDR replug recovery)
- [ ] UAT-4 passed (driving loop end-to-end)
- [ ] Grafana panels added + committed to home-ops

Once all five boxes are ticked, Phase 28 closes. Bump `.planning/STATE.md` (advance plan counter, mark requirements complete via `gsd-sdk query requirements.mark-complete`), update ROADMAP.md, and add an entry to the "Recently completed" table. The post-UAT 28-06-SUMMARY captures the pass/fail outcomes, the actual VID:PID and protocol index seen on the Nooelec dongle, the observed PSI accuracy against the stick gauge, and the Grafana commit reference.
