# Phase 19 fix-up plan

Post-execution fixes identified during UAT. Do these in one session, then
close out verification.

## 1. Restore "Car" tab in nav

19-11 over-pruned. Add Car back as a 5th nav entry: **Home / Car / Grafana / About / Donate**.

File: `~/dev/home-ops/.../webroot/index.html`

- Add `<a href="/car" onclick="event.preventDefault(); navigateToCar();">Car</a>` between Home and Grafana in `<nav>`
- Add `var CAR_URL_RE = /^\/car\/?$/;` alongside the other URL constants
- Add `navigateToCar()` function (same pushState pattern as `navigateToAbout`)
- Wire `CAR_URL_RE` into `route()` before the About check
- Create `renderCar()` — recover the old `#car-section` content from git (commit `5d8f7428^`), which has The Car, Why "Shit of Theseus", The Telemetry, The Hardware, and The Software sections. This is rich existing content, not a stub.
- Expose `navigateToCar` to `window` alongside `navigateToDay`, `navigateHome`, `navigateToAbout`

Source content (recover from `git show 5d8f7428^:kubernetes/apps/default/shit-of-theseus/app/webroot/index.html`, lines ~1148-1270): the full `#car-section` div with car gallery, hardware specs (MPU-6050, GPS, BME680, INA219, dashcam, Big Red Button, OLED), and software architecture (high-rate, low-rate, capture, timelapse, sync paths).

## 2. Fix About page — recover Steve and Tony bios from git

The current `renderAbout()` has a generic `_renderDriversForAbout(driverStatsData)` that pulls from live JSON. Replace with the actual bios from the old `#about-section`.

Recover from `git show 5d8f7428^:...index.html` (lines ~1282-1325), the `.team-grid` containing:

**Steve** — CFO (Chief Fermentation Officer):
- Program manager by day
- In charge of money, planning, music, and beer
- "Tony bolts sensors to things and worries about graphs. I make sure we've got fuel, a plan, and something decent playing when the car starts making noises it shouldn't."

**Tony** — CTO (Chief Telemetry Overbuilder):
- Gravatar: `https://www.gravatar.com/avatar/4fce033d079d9cb954f6ac0f2117523f?s=160`
- Built the telemetry because "the car can't be trusted" and "data makes me feel less helpless"
- Cancer context: dad died 2011, mum living with terminal cancer
- "If you're entertained by a $1,500 car running better monitoring than some enterprise environments..."

Replace `_renderDriversForAbout(driverStatsData)` with hardcoded HTML matching the old about-section team-grid. Keep the existing CSS classes (`.team-grid`, `.team-member`, `.member-avatar`, `.member-role`). Recover the CSS for these classes from the same commit if 19-11 deleted them.

## 3. Remove "Team" stat card from before-mode homepage

In `renderHomepageBefore()`, find and remove the "team" stat card. Keep: distance (3534 km), days (10), start date. Remove: team name card.

## 4. Remove redundant headings

- `renderHomepageBefore()`: remove any "Shit of Theseus" `<h1>` heading — the site header already shows it
- `renderAbout()`: remove the hero section `<h1>The Shit of Theseus</h1>` — redundant with site header. Keep the logo image and subtitle if present.
- Check `renderCar()` (from step 1): same — no need for "The Shit of Theseus" hero heading

## 5. Add secret `/videos` page (old events viewer)

Recover the old video/events rendering code from `git show 5d8f7428^:...index.html`:
- `renderEvents(events)` function (around line 2197)
- The rally progress bar, day filter bar, day filter select
- `jumpToEvent()` function
- Associated CSS for `.event-card`, `.event-badge`, `.day-filter`, `.rally-progress`, etc.

Wire to a hidden route:
- Add `var VIDEOS_URL_RE = /^\/videos\/?$/;` constant
- Wire into `route()` → `renderLegacyVideos()`
- `renderLegacyVideos()` wraps the recovered `renderEvents` code, rendering into `#dynamic-route`
- Do NOT add a nav link — access via direct URL `/videos` only
- Expose nothing extra to `window` (no nav function needed — direct URL only)

## 6. Push home-ops (if not already done)

```bash
cd ~/dev/home-ops && git push
```

Pushes the already-committed fixes:
- `agenda.json` added to kustomization ConfigMap
- Navigation functions exposed to `window`

## 7. Close NARR-08b gap (home-address exclusion in route.py)

`RouteStorage.generate_route_json()` publishes all GPS points without proximity filtering. Add:
- `home_lat` / `home_lng` / `exclusion_radius_m` config params (config.yaml + dataclass)
- Haversine distance check in `generate_route_json()` dropping points within radius
- Test asserting the filter works

```bash
/gsd-plan-phase 19 --gaps
/gsd-execute-phase 19 --gaps-only
```

## 8. Walk the 6 human UAT items

```bash
/gsd-verify-work 19
```

Test: countdown, SPA routing, live-mode (DevTools date override), archive-mode, About content, Pi route.json generation.

## Reference commits

- Pre-19-11 content: `git show 5d8f7428^:kubernetes/apps/default/shit-of-theseus/app/webroot/index.html`
- 19-11 removal commit: `5d8f7428` (refactor: shrink nav + purge legacy)
- Rollback checkpoint: `shitbox-pre-phase-19` tag at `b9f9ff6638f` in home-ops
