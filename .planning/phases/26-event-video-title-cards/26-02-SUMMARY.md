---
phase: 26-event-video-title-cards
plan: "02"
subsystem: config
tags: [config, title-card, dataclass, tdd]
dependency_graph:
  requires: []
  provides: [TitleCardConfig, capture.title_card]
  affects: [src/shitbox/utils/config.py, config/config.yaml]
tech_stack:
  added: []
  patterns: [_dict_to_dataclass, field(default_factory=...), TDD RED/GREEN]
key_files:
  created:
    - tests/test_config_title_card.py
  modified:
    - src/shitbox/utils/config.py
    - config/config.yaml
decisions:
  - "whimsy_lines defaults to [] in Python so renderer uses its own hardcoded pool when operator has not overridden it (D-16 semantics)"
  - "title_card block sits at two-space indent as sibling of video/timelapse/video_buffer/speaker under capture:"
  - "mypy errors on yaml stubs and type annotation syntax are pre-existing baseline noise — not introduced by this plan"
metrics:
  duration_seconds: 104
  completed_date: "2026-04-23"
  tasks_completed: 1
  files_modified: 3
---

# Phase 26 Plan 02: TitleCardConfig Dataclass and YAML Block Summary

Added `TitleCardConfig` dataclass to `config.py`, wired it into `CaptureConfig` and `load_config()`, populated the `capture.title_card` YAML block with a 5-entry whimsy pool, and proved the round-trip with 17 unit tests.

## What Was Built

### TitleCardConfig dataclass (`src/shitbox/utils/config.py`)

```python
@dataclass
class TitleCardConfig:
    """Event video title-card slate configuration (phase 26)."""

    enabled: bool = True
    duration_seconds: float = 3.0
    show_driver: bool = True
    whimsy_lines: List[str] = field(default_factory=list)
```

Placed immediately before `CaptureConfig`. Uses the existing `List` import -- no new imports.

### CaptureConfig wiring

```python
speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
title_card: TitleCardConfig = field(default_factory=TitleCardConfig)
```

### load_config() hook

```python
title_card=_dict_to_dataclass(
    TitleCardConfig, capture_data.get("title_card", {})
),
```

### YAML block (`config/config.yaml`)

```yaml
  title_card:
    enabled: true
    duration_seconds: 3.0
    show_driver: true
    whimsy_lines:
      - "Here be dragons"
      - "GPS off having a lie down"
      - "Somewhere between A and B"
      - "The map ends here"
      - "Lost, but enthusiastic"
```

Two-space indent -- sibling of `video:`, `timelapse:`, `video_buffer:`, `speaker:` under `capture:`.

## Test Coverage (`tests/test_config_title_card.py`)

17 tests across 5 test classes:

| Class | Coverage |
|---|---|
| `TestTitleCardConfigDefaults` | All four field defaults verified individually |
| `TestCaptureConfigTitleCardField` | Field presence, instance type, all defaults via CaptureConfig() |
| `TestLoadConfigYamlRoundTrip` | Full override round-trip; enabled=false; whimsy order preservation |
| `TestLoadConfigEmptyCaptureBlock` | `capture: {}` yields TitleCardConfig defaults |
| `TestLoadConfigMissingTitleCardKey` | Missing title_card key and missing capture key both fall back to defaults |

## Key Decision: whimsy_lines defaults to `[]`

`whimsy_lines` is an empty list at the Python level. When the operator has not set any
entries in YAML, the renderer (plan 26-03) falls back to its own hardcoded pool. When the
operator sets entries in YAML, those override the renderer's defaults. This matches D-16
semantics: the YAML pool is opt-in, not mandatory.

The `config/config.yaml` ships with the canonical 5 lines from D-09 so field-ops can edit
them without touching code. The Python default remains `[]` so a minimal config (no capture
block, no title_card key) still produces a renderer-usable config.

## TDD Gate Compliance

| Gate | Commit | Message |
|---|---|---|
| RED | 5aa118e | `test(26-02): add failing tests for TitleCardConfig` |
| GREEN | 06546dd | `feat(26-02): add TitleCardConfig dataclass and wire into CaptureConfig` |

Tests failed at RED (ImportError -- TitleCardConfig did not exist). Tests passed at GREEN (17/17).

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None. `TitleCardConfig` fields are all primitive types or `List[str]` -- no placeholder data, no hardcoded empty values that flow to UI.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. YAML config is repo-controlled. Threat register (T-26-02-01 through T-26-02-03) fully covered -- no unregistered surface introduced.

## Self-Check

Files exist:

- `src/shitbox/utils/config.py` -- modified (TitleCardConfig + CaptureConfig.title_card + load_config hook)
- `config/config.yaml` -- modified (title_card block with 5 whimsy lines)
- `tests/test_config_title_card.py` -- created (17 tests)

Commits exist:

- `5aa118e` -- RED test commit
- `06546dd` -- GREEN implementation commit

## Self-Check: PASSED
