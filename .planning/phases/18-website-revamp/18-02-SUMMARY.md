---
phase: 18
plan: "02"
subsystem: website
tags: [website, ui, drivers, notes, status]
dependency_graph:
  requires: [18-01]
  provides: [notes-feed, drivers-tab, current-driver-card, note-badges]
  affects: [shit-of-theseus.com]
tech_stack:
  added: []
  patterns: [parallel-fetch, iife-var-only, progressive-enhancement]
key_files:
  created: []
  modified:
    - ~/dev/home-ops/kubernetes/apps/default/shit-of-theseus/app/webroot/index.html
decisions:
  - Notes feed placed inside status-content so it only renders when data is present
  - Three fetches fire in parallel and degrade silently on 404 (files may not exist pre-rally)
  - notes.slice().reverse() gives newest-first display without mutating the source array
  - Note badges injected lazily: once after notes load, once after events render (handles race)
  - active_driver marker uses middle-dot suffix rather than a separate badge to stay compact
metrics:
  duration: "~10 minutes"
  completed: "2026-04-11"
  tasks_completed: 2
  files_modified: 1
---

# Phase 18 Plan 02: Drivers Tab, Notes Feed, and Status Enhancements Summary

Adds three new UI features to the single-file SPA at `shit-of-theseus.com` and wires three new parallel JSON fetches to back them.

## What Was Built

### Current Driver card

A new status card labelled "Current Driver" is the last child of the `.status-grid` on the Status tab. It reads `active_driver` from `driver-stats.json` and falls back to an em dash. The `renderStatus` function also updates it on every status refresh in case the fetch order races.

### Field Notes feed

A "Field Notes" section sits below the mini-map on the Status tab. It reads `notes.json` in newest-first order (`slice().reverse()`). Each note renders as a `.note-card` with timestamp, optional location link (suppressed if `gps_stale`), body text, and an optional footer linking to the related event card when `event_id` is present.

### Note icon badges

A pencil SVG badge (`.note-badge`) is injected into any `.event-card` that has a linked note. Badges are injected in two passes: once when `notes.json` loads, and once when `events.json` finishes rendering cards. This handles whichever fetch completes first. The badge is positioned absolutely in the top-right corner and highlights amber on hover.

### Drivers tab

A new "Drivers" nav link and `#drivers-section` sit between Status and Videos. The section contains a `drivers-table` showing each driver's name, total time driven (formatted as `Xh Ym`), and percentage of total drive time. The active driver's name cell carries the `.active-driver` class (amber colour) and a middle-dot suffix. The section degrades gracefully: loading state shown by default, error state shown if the fetch fails.

### Three parallel fetches

`notes.json`, `fuel.json`, and `driver-stats.json` are fetched in parallel using independent fire-and-forget fetch chains. All three swallow errors silently with an empty `.catch()` (or a UI error state in the drivers case), so a missing file during pre-rally setup causes no visible breakage.

## CSS Added

- `.note-card` and child selectors (`note-meta`, `note-body`, `note-footer`)
- `.event-card { position: relative; }` (required for badge absolute positioning)
- `.note-badge` and hover state
- `.drivers-table`, `th`, `td`, `.active-driver`

## JS Added

- `var notesData`, `var fuelData`, `var driverStatsData` globals
- `formatDriveTime(seconds)` — formats seconds to "Xh Ym"
- `renderNotes(notes)` — renders note cards into `#notes-container`
- `injectNoteBadges(notes)` — injects SVG pencil badges into event cards
- `renderDrivers(data)` — renders drivers table or error state
- Three fetch blocks for `notes.json`, `fuel.json`, `driver-stats.json`
- `if (notesData) injectNoteBadges(notesData)` added to events fetch handler

## Deviations from Plan

None. Plan executed exactly as written.

## Self-Check: PASSED

- `ddd362cb` commit exists in home-ops repo (confirmed by git output)
- All acceptance criteria grep checks returned expected counts
- No `const` or `let` introduced
- No `cost` field referenced
