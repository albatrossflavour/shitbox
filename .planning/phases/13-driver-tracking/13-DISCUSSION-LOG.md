# Phase 13: Driver Tracking — Discussion Log

**Date:** 2026-04-09
**Format:** Q&A via /gsd:discuss-phase

---

## Area: Driver Roster

**Q:** Where do driver names come from?
**Options:** Config file / Freeform text entry / Fixed list in UI
**Selected:** Config file — names in `config.yaml`, no edit UI on the Pi

**Q:** How is the driver selector presented in the UI?
**Options:** Dropdown in top bar / Modal overlay
**Selected:** Dropdown in top bar — fast single-tap switch, replaces "Driver: —" placeholder

---

## Area: Stint Model + Event Attribution

**Q:** How should driver stints be stored?
**Options:** New driver_stints table / trip_state key/value
**Selected:** New driver_stints table — schema v7, proper time-range queries, clean sync export

**Q:** How should events be attributed to the active driver?
**Options:** Column on events table / Join via stints at query time
**Selected:** Column on events table — driver_name TEXT NULLABLE added in v7 migration, set at record time

---

## Area: Stats Display Format

**Q:** Where does the driver stats breakdown live?
**Options:** Modal on driver name click / Always-visible section / Separate tab
**Selected:** Modal on driver name click — consistent with Phase 12 modal pattern

**Q:** What level of detail in the stats modal?
**Options:** Time + percentage per driver / Time + percentage + event count
**Selected:** Time + percentage per driver — Name | Time driven | % of total

---

*Log generated: 2026-04-09*
