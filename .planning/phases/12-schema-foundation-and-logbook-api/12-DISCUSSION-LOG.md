# Phase 12: Schema Foundation and Logbook API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-04-09
**Phase:** 12 — Schema Foundation and Logbook API

---

## Area: Logbook UI Shape

**Q: Where should the notes and fuel entry forms live?**
Options presented: Separate /logbook page / Modal in existing dashboard / Tab in existing dashboard
User response (freeform): "The entry stuff should be on the PI UI, and then display on the external website"
Clarification: Asked to confirm layout preference specifically
Selected: Modal in existing dashboard

**Q: How should the modal be triggered?**
Options: Buttons in the dashboard (Recommended) / Keyboard shortcuts / Both
Selected: Buttons in the dashboard

---

## Area: No-fix GPS Handling

**Q: When saving a note or fuel stop with no GPS fix, what should happen?**
Options: Save with null location / Save with last-known position / Block until fix
Selected: Save with last-known position

**Q: Should the UI indicate when the saved location is stale?**
Options: Yes — show a warning in the modal (Recommended) / No — save silently
Selected: Yes — show a warning in the modal

---

## Area: Sync Extension Approach

**Q: How should CaptureSyncService be extended for the new JSON exports?**
Options: Registry pattern now (Recommended) / Add inline, refactor later
Selected: Registry pattern now

---

## Deferred

- Temperature sensors missing from SSE stream (todo) → Phase 15
- simple-keyboard for on-screen entry → Phase 17 consideration
