# Phase 11 — Hardware IDs (recorded 2026-04-09)

## DS18B20 1-Wire probes

- exterior: `28-00000024263a` (22.6°C at time of recording — cooler probe)
- engine_bay: `28-0000002405b1` (28.4°C at time of recording — warmer probe)

## ELP 4K front camera

- USB ID: `32e4:0298` (reported as "16MP USB Camera")
- Current device: `/dev/video0`

## Brio 100 cabin camera

- USB ID: not captured (not connected during discovery)
- Note: D-14 says unchanged from v1 — confirm VID:PID before writing udev rule in plan 03
