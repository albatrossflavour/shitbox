---
phase: 19
slug: website-narrative-rebuild
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7+ (backend Pi code) — no JS test framework (locked by Phase 18 no-build-step constraint) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/test_route_storage.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~15 seconds (full suite), <2 seconds (route storage only) |

**Web-side reality:** all browser behaviour is verified manually. The planner must supply a detailed manual-QA checklist (below) and a `curl` smoke script for nginx-level assertions.

---

## Sampling Rate

- **After every task commit (Pi-side):** Run `pytest tests/test_route_storage.py -x && ruff check src/ && mypy src/`
- **After every plan wave (Pi-side):** Run `pytest`
- **Before `/gsd-verify-work`:** Full suite must be green AND manual browser walkthrough of all three modes completed on staging/test instance
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

*Populated during planning — each task's `<automated>` command lands here. REQ IDs below are the proposed NARR-01..NARR-10 from 19-RESEARCH.md.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 19-01-XX | 01 | 0 | NARR-08 | — | Route.json never includes `cost_*` or PII; Douglas-Peucker output bounded | unit | `pytest tests/test_route_storage.py -x` | ❌ W0 | ⬜ pending |
| 19-01-XX | 01 | 0 | NARR-08b | — | Route generator registers with CaptureSyncService; filename is `route.json` | integration | `pytest tests/test_capture_sync_generators.py::test_route_generator -x` | ❌ W0 (extend) | ⬜ pending |
| 19-02-XX | 02 | 1 | NARR-02 | — | `/day/YYYY-MM-DD` returns 200 via SPA fallback (`try_files`) | smoke | `curl -s -o /dev/null -w "%{http_code}" https://shit-of-theseus.com/day/2026-05-01` | N/A | ⬜ pending |
| 19-03-XX | 03 | 1 | NARR-10 | — | `/agenda.json` served with expected schema (`rally.start_date`, `rally.end_date`, `days[]`) | smoke | `curl -s https://shit-of-theseus.com/agenda.json \| jq -e '.rally.start_date and .rally.end_date and (.days \| length > 0)'` | N/A | ⬜ pending |
| 19-04-XX | 04 | 2 | NARR-01 | — | Mode detection returns `before`/`live`/`archive` correctly across agenda + freshness boundaries | manual | — (browser + devtools) | N/A | ⬜ pending |
| 19-05-XX | 05 | 2 | NARR-03 | — | Timeline spine interleaves events + notes + fuel + driver changes + agenda markers + stage bookends in chronological order | manual | — (golden-dataset DOM inspection) | N/A | ⬜ pending |
| 19-06-XX | 06 | 2 | NARR-04 | — | Day page renders agenda context block before telemetry | manual | — (DOM inspection) | N/A | ⬜ pending |
| 19-07-XX | 07 | 2 | NARR-05 | — | Day-nav progress bar renders correct segment states (filled/current/future) site-wide | manual | — (browser) | N/A | ⬜ pending |
| 19-08-XX | 08 | 2 | NARR-06 | — | Videos/Timelapse/Map/Route/Drivers/Car nav entries removed; content folded into day pages or /about | manual | — (browser + grep) | N/A | ⬜ pending |
| 19-09-XX | 09 | 2 | NARR-07 | — | Grafana link remains one click from home | manual | — (browser) | N/A | ⬜ pending |
| 19-10-XX | 10 | 2 | NARR-09 | — | Day-page map renders full-rally polyline backdrop + day-slice highlight | manual | — (browser) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_route_storage.py` — covers NARR-08 (Douglas-Peucker correctness on synthetic point sets, per-day grouping, size-budget assertion `len(json.dumps(payload)) < 1_048_576`, empty/sparse GPS handling, recursion depth safety)
- [ ] Extend `tests/test_capture_sync_generators.py` — add `test_route_generator_registers_and_writes` covering NARR-08b, mirroring existing `test_generators_run_before_rsync`
- [ ] No new framework install needed — pytest already in `pyproject.toml`

---

## Manual-Only Verifications

These behaviours are browser-only. The phase close gate requires walking through this checklist on a staging instance (or behind a feature branch + Flux reconcile) before `/gsd-verify-work` passes.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mode detection cross-boundary | NARR-01 | Client-side JS; no JS test harness | 1. Set laptop clock to day-before rally start_date → load home → verify `before` mode 2. Roll clock forward to rally start_date → verify `live` 3. Fake stale `events.json` (mtime > 6 h) → verify `archive` |
| Timeline spine ordering | NARR-03 | Vanilla JS merge logic | Load `/day/YYYY-MM-DD` with fixture data containing out-of-order timestamps across all six streams (events, notes, fuel, driver changes, agenda, stage bookends) → inspect DOM order matches sorted timestamps |
| Day-nav progress bar | NARR-05 | CSS states + click handlers | Load home + any day page → verify filled segments for past days, bright for current, grey for future. Click filled/current → navigates. Click future → inert. Tab through with keyboard → focus states visible |
| Nav collapse | NARR-06 | Negative space check | Load home → confirm nav = Home / Grafana / About / Donate only. `grep -E '#status\|#videos\|#timelapse\|#map\|#route\|#drivers\|#car'` returns no live href |
| Grafana accessibility | NARR-07 | UX assertion | Home → Grafana link visible and one click away. Verify iframe/link renders |
| Day-page map | NARR-09 | Leaflet polyline layers | Load `/day/YYYY-MM-DD` → verify full-rally polyline rendered as grey backdrop, day slice highlighted in orange, day event pins shown, no cross-day pins |
| Archive overview | NARR-01 (archive mode) | Post-rally UX | Set clock after `end_date` → home renders stats row + linear day grid (not calendar) with thumbnails and working day links |
| nginx SPA fallback | NARR-02 | Infra assertion | `curl -s -o /dev/null -w "%{http_code}" https://shit-of-theseus.com/day/2026-05-01` → 200. Refresh on `/day/*` URL → page loads (no 404) |
| Flux reconcile post-deploy | all | Deploy pipeline | After merging home-ops commit: `flux reconcile kustomization shit-of-theseus` → pod restarts cleanly; site serves new `index.html` and `nginx.conf` |
| Rollback drill | all | Regression insurance | In a scratch clone of home-ops: `git reset --hard shitbox-pre-phase-19` → `flux reconcile` (dry-run or on a staging instance) → site reverts to Phase 18 state with no errors |
| Share-button URL rewrite | NARR-03 (follow-on) | Anchor scroll | Click share on a day-page event → URL should be `/day/{date}#event-{id}` → paste into new tab → page loads and scrolls to the event |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or land in Manual-Only Verifications with a concrete checklist entry
- [ ] Sampling continuity: no 3 consecutive Pi-side tasks without automated verify
- [ ] Wave 0 (Pi-side) covers NARR-08 / NARR-08b before any day-page JS consumes `route.json`
- [ ] No watch-mode flags (`pytest -f`, `pytest-watch`, etc.)
- [ ] Feedback latency < 15 s on Pi-side
- [ ] Manual checklist walked end-to-end on staging or via Flux before phase close
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
