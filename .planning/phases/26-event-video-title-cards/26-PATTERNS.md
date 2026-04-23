# Phase 26: Event Video Title Cards - Pattern Map

**Mapped:** 2026-04-23
**Files analysed:** 6 (2 CREATE, 4 MODIFY)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/shitbox/capture/title_card.py` (CREATE) | renderer / utility | transform (struct → PNG → TS) | `src/shitbox/capture/ring_buffer.py::_prepare_intro` + `src/shitbox/sync/timelapse_compiler.py::_generate_title_card` | role+flow match (hybrid) |
| `src/shitbox/events/labels.py` (CREATE) | data module (lookup table) | static mapping | `src/shitbox/events/detector.py::EventType` (enum) + `shit-of-theseus` website badge palette | role-match |
| `src/shitbox/capture/ring_buffer.py` (MODIFY) | orchestration / ffmpeg driver | request-response (concat + PiP composite) | itself (`_concatenate_segments`, `_build_dual_concat_reencode_cmd`) | exact |
| `src/shitbox/utils/config.py` (MODIFY) | config dataclass | static | `TimelapseConfig` / `PipConfig` / `SpeakerConfig` | exact |
| `src/shitbox/events/storage.py` (MODIFY) | storage / JSON emitter | transform (meta dict → feed dict) | `generate_events_json()` itself (lines 383+) | exact |
| `config/config.yaml` (MODIFY) | YAML config block | static | existing `capture.video_buffer.pip` block (lines 281-289) | exact |

> **Path correction for planner:** CONTEXT.md refers to `src/shitbox/storage/events.py`, but the actual location is `src/shitbox/events/storage.py` (class `EventStorage`). Storage of telemetry readings lives in `src/shitbox/storage/database.py`; event JSON is a separate module in `events/`. Use the real path.

## Pattern Assignments

### `src/shitbox/capture/title_card.py` (renderer, transform)

**Primary analogs:**
- `src/shitbox/capture/ring_buffer.py::_prepare_intro` (lines 374–443) — PNG/MP4 → MPEG-TS conversion, ffprobe duration readback, structured logging
- `src/shitbox/sync/timelapse_compiler.py::_generate_title_card` (lines 123–196) — existing card-rendering service with reverse-geocode + ffmpeg drive
- `src/shitbox/display/oled.py::start` (lines 42–56) — how Pillow is imported/used in-tree
- `src/shitbox/capture/overlay.py` lines 48, 110–111 — font names and logo asset path

**Imports pattern** (mirror what's already in the tree, `display/oled.py:42–45` and `capture/overlay.py:13–24`):

```python
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Match overlay.py font choices (D-04)
FONT_DISPLAY = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
LOGO_PATH = str(Path(__file__).parent / "assets" / "shitbox_rally_logo.png")
```

> Gotcha: `oled.py` uses `ImageFont.load_default()` which is a bitmap font unsuitable for 140pt. This renderer needs `ImageFont.truetype(FONT_DISPLAY, 140)`. DejaVu ships on the Pi image (used by `overlay.py`'s `font=DejaVu Sans`) but the full filesystem path is not referenced anywhere in-tree today, so the planner has to introduce it. Fall back to `ImageFont.load_default()` only to keep unit tests import-safe.

**PNG → MPEG-TS conversion pattern** (copy from `ring_buffer.py::_prepare_intro` lines 406–443):

```python
# Scale/pad to match capture resolution, lock fps, yuv420p.
w, h = self.resolution.split("x")
vf = (
    f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
    f"fps={self.fps},format=yuv420p"
)

cmd = ["ffmpeg", "-y", "-i", str(intro_path), "-vf", vf]
cmd += self._video_encoder
cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000"]
cmd += ["-f", "mpegts", str(self._intro_ts)]
```

> Gotcha: the slate has **no audio**. Intro TS carries AAC stereo 48 kHz because the segments do too; if slate.ts is audio-less, the concat demuxer will error on AAC track presence/absence mismatch between entries. Two options for the planner to choose: (a) synthesize silent AAC on the slate with `-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 -shortest`, same codec/profile as intro, or (b) generate the slate audio-less and handle the concat demuxer's "different streams" failure mode. Option (a) matches the "intro → slate → buffer" all-have-AAC assumption and is safest.

**Ffmpeg loop-and-encode pattern for a still image** (adapt from `timelapse_compiler.py::_generate_title_card` lines 170–178; use `-loop 1 -i <png>` instead of `lavfi color=`):

```python
cmd = [
    "ffmpeg", "-y",
    "-loop", "1", "-i", str(png_path),
    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
    "-t", str(duration_seconds),
    "-vf", f"fps={fps},format=yuv420p",
    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "128k",
    "-shortest",
    "-f", "mpegts", str(ts_path),
]
try:
    result = subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60
    )
    if result.returncode == 0 and ts_path.exists() and ts_path.stat().st_size > 0:
        log.info("slate_ts_rendered", ts=str(ts_path), duration_s=duration_seconds)
        return ts_path
    stderr = result.stderr.decode()[-500:] if result.stderr else ""
    log.error("slate_ts_failed", stderr=stderr)
    return None
except subprocess.TimeoutExpired:
    log.error("slate_ts_timeout")
    return None
```

**Escape pattern** (only relevant if the planner keeps any drawtext fallback; ring_buffer.py + timelapse_compiler.py both use this):

```python
# src/shitbox/sync/timelapse_compiler.py:119-121
@staticmethod
def _escape_drawtext(s: str) -> str:
    """Escape characters that are special to ffmpeg drawtext ``text=`` values."""
    return s.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")
```

(Pillow renders text natively, so escape logic is probably unnecessary — noted for completeness.)

**Structured logging pattern** (follow project convention):

```python
log.info(
    "slate_rendered",
    event_type=event.event_type.value,
    place=place_name,
    coords=f"{lat:.4f},{lon:.4f}" if lat is not None else None,
    png=str(png_path),
    duration_s=duration_seconds,
)
```

---

### `src/shitbox/events/labels.py` (data module, static mapping)

**Analog:** `src/shitbox/events/detector.py` (the `EventType` enum at lines 15–24) + the website badge palette described in CONTEXT.md D-07 (currently duplicated in `.../shit-of-theseus/app/webroot/index.html`).

**Imports + table pattern** (small, dependency-light, pure data):

```python
"""Human-readable labels and display colours for event types.

Shared by slate rendering (capture/title_card.py), the website event feed
(currently duplicated in shit-of-theseus/webroot/index.html), and the TTS
path. Importing this module must NOT require hardware or IO — it is a
pure lookup table.
"""

from __future__ import annotations

from typing import Dict

from shitbox.events.detector import EventType

# Human-readable label (D-08). MANUAL/BUTTON both map to "Manual Capture"
# so the slate composition collapses them into one concept (D-11).
EVENT_LABELS: Dict[EventType, str] = {
    EventType.HARD_BRAKE: "Hard Brake",
    EventType.BIG_CORNER: "Big Corner",
    EventType.HIGH_G: "High G",
    EventType.ROUGH_ROAD: "Rough Road",
    EventType.MANUAL_CAPTURE: "Manual Capture",
    EventType.BOOT: "System Start",
    EventType.ROLLOVER: "Rollover",
}

# Badge colours (D-07); mirrors webroot/index.html palette exactly.
# ROLLOVER renders with diagonal hazard stripes overlaid — colour alone is
# consumed by the slate renderer; stripe overlay is slate-only.
EVENT_COLOURS: Dict[EventType, str] = {
    EventType.HIGH_G: "#da3633",
    EventType.BIG_CORNER: "#d29922",
    EventType.HARD_BRAKE: "#f85149",
    EventType.ROUGH_ROAD: "#8957e5",
    EventType.MANUAL_CAPTURE: "#238636",
    EventType.BOOT: "#1f6feb",
    EventType.ROLLOVER: "#e74c3c",
}

ROLLOVER_STRIPE_COLOUR = "#000000"


def label_for(event_type: EventType) -> str:
    """Return the display label for an event type; falls back to the enum value."""
    return EVENT_LABELS.get(event_type, event_type.value.replace("_", " ").title())


def colour_for(event_type: EventType) -> str:
    """Return the badge background colour for an event type (hex with leading #)."""
    return EVENT_COLOURS.get(event_type, "#6e7681")
```

> Gotcha 1: `EventType.MANUAL_CAPTURE` is the actual enum member (`detector.py:22`), not `MANUAL` or `BUTTON`. CONTEXT.md D-08 lists `MANUAL` and `BUTTON` as separate keys — that is website-feed terminology, not Python-side. D-11 ("no badge on manual captures") is enforced by `title_card.py`, not by the table.
>
> Gotcha 2: "Where exactly `labels.py` lives" is explicitly Claude's Discretion in CONTEXT.md. Putting it in `src/shitbox/events/` (not `storage/` or `utils/`) means importing it is `from shitbox.events.labels import ...`, which is already the shape of imports elsewhere (e.g. `events/engine.py:32`). It cleanly pairs with `detector.EventType` and avoids introducing a circular import back into `utils/` for something that is inherently event-domain data.
>
> Gotcha 3: do **not** import Pillow at the top of this module. It has to stay import-safe for the website-side/TTS reuse use-case even when Pillow is not installed.

---

### `src/shitbox/capture/ring_buffer.py` (orchestration, modify)

**Analog: itself.** The patterns to extend are already in the file.

#### Concat insertion point — `_concatenate_segments` (lines 1337–1391)

Current code:

```python
# src/shitbox/capture/ring_buffer.py:1372-1391
# Build file list for the front concat demuxer (intro + live segments)
files: list[Path] = []
if self._intro_ts and self._intro_ts.exists():
    files.append(self._intro_ts)
files.extend(segments)

total_input_bytes = sum(f.stat().st_size for f in files if f.exists())
if total_input_bytes == 0:
    log.warning("concat_no_data", segment_count=len(segments))
    return None

# concat.txt lives in the save_N/ tmp dir and is cleaned up with it
concat_list = segments[0].parent / "concat.txt"
try:
    with open(concat_list, "w") as f:
        for p in files:
            f.write(f"file '{p}'\n")
except Exception as e:
    log.error("concat_list_write_error", error=str(e))
    return None
```

**Pattern to apply (D-13, D-14):** between the `_intro_ts` append and `files.extend(segments)`, insert the slate TS, written into `segments[0].parent` (the per-save tmp dir) so it's cleaned up with `concat.txt`.

> Gotcha: `segments[0].parent` is the `save_N/` tmp dir (per the docstring at line 1383). Slate TS must live there too; writing into `self.buffer_dir` would survive the save and confuse subsequent events. The planner should mirror where `concat.txt` is written.

#### PiP sync offset — `_build_dual_concat_reencode_cmd` (lines 1260–1293)

Current code:

```python
# src/shitbox/capture/ring_buffer.py:1260, 1283-1294
intro_duration = getattr(self, "_intro_duration_seconds", 0.0) or 0.0
...
# PTS-STARTPTS zero-resets the cabin stream's timeline (it can start
# well above zero when segment_wrap has cycled), then +intro_duration
# shifts it past the intro on the output timeline.
pip_chain = (
    f"[1:v]scale=iw*{self.pip_scale}:-2,"
    "pad=iw+4:ih+20:2:18:color=black@0.7,"
    "drawtext=text='Cabin':fontsize=13:fontcolor=white@0.9:x=6:y=3,"
    f"setpts=PTS-STARTPTS+{intro_duration}/TB[pip]"
)
overlay_chain = (
    f"[0:v][pip]overlay={x}:{y}:enable='gte(t,{intro_duration})'[base]"
)
```

**Pattern to apply (D-15):** compute `total_head_offset = intro_duration + slate_duration`, substitute it into both the `setpts` term and the `enable='gte(t,...)'` gate. Slate has no cabin equivalent — both expressions shift uniformly.

> Gotcha 1: the existing pattern already used `intro_duration` as a single first-class offset. Extending to `total_head_offset` is a one-line change per chain, not a structural refactor. Name the new local `head_offset_s` or similar — don't reassign `intro_duration`, since it's also used downstream for logging (`intro_s=round(intro_duration, 2)` at line 1273).
>
> Gotcha 2: `_build_concat_reencode_cmd` (the single-camera path used when no cabin PiP) at `_concatenate_segments` line 1432 has its own equivalent filter chain — the planner MUST check whether it also references `intro_duration` and extend it the same way. Read that method before writing the plan.
>
> Gotcha 3: `overlay.py::generate_ass_overlay` is called at line 1263 with `intro_duration=intro_duration`. ASS subtitle timestamps are shifted against the output timeline; they will also drift by `slate_duration` unless the call at line 1267 becomes `intro_duration=head_offset_s` or an equivalent sum. CONTEXT.md says "no changes to the existing ASS/HUD subtitle overlay" — that's about the ASS *generator*, not the ASS *shift*. The ASS shift input has to change or the HUD will burn into the wrong frames.

#### Structured logging pattern (match existing style)

```python
# src/shitbox/capture/ring_buffer.py:1270-1276
log.info(
    "concat_overlay_generated",
    entries=len(history),
    intro_s=round(intro_duration, 2),
    clip_s=round(clip_end_wall - clip_start_wall, 2),
    mode="dual",
)
```

New slate entries should look like `log.info("slate_inserted", ts=str(slate_ts), slate_s=round(slate_duration, 2), head_offset_s=round(head_offset_s, 2))`.

---

### `src/shitbox/utils/config.py` (config dataclass, modify)

**Analogs** (all in the same file):
- `TimelapseConfig` (lines 298–305) — simplest nested dataclass, three primitive fields
- `PipConfig` (lines 308–321) — shows how to hold a list-like default (`camera_controls: dict[str, int] = field(default_factory=dict)`)
- `SpeakerConfig` (lines 342–349) — demonstrates an enabled-flag + primitives

**Dataclass pattern** (copy the `TimelapseConfig`+`SpeakerConfig` shape):

```python
# Add near PipConfig/SpeakerConfig, before CaptureConfig.
@dataclass
class TitleCardConfig:
    """Event video title-card slate configuration (phase 26)."""

    enabled: bool = True
    duration_seconds: float = 3.0
    show_driver: bool = True
    whimsy_lines: List[str] = field(default_factory=list)
```

> Gotcha: `List` is already imported in this module (used at line 419 `drivers: List[str] = field(...)`). Check the top of the file before adding a new import. Default to `field(default_factory=list)` (empty) so the renderer falls back to its hardcoded pool when the user hasn't overridden — matches D-16's "overrides the defaults in code if set".

**Hook-into-CaptureConfig pattern** (mirror the existing field list at lines 363–367):

```python
# src/shitbox/utils/config.py:352-367
@dataclass
class CaptureConfig:
    """Manual capture (button + video) configuration."""
    ...
    video: VideoConfig = field(default_factory=VideoConfig)
    timelapse: TimelapseConfig = field(default_factory=TimelapseConfig)
    video_buffer: VideoBufferConfig = field(default_factory=VideoBufferConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
    # ADD: title_card: TitleCardConfig = field(default_factory=TitleCardConfig)
```

**Hook-into-load_config pattern** (mirror lines 486–491):

```python
# src/shitbox/utils/config.py:477-492
capture_config = CaptureConfig(
    enabled=capture_data.get("enabled", True),
    ...
    video=_dict_to_dataclass(VideoConfig, capture_data.get("video", {})),
    timelapse=_dict_to_dataclass(TimelapseConfig, capture_data.get("timelapse", {})),
    video_buffer=_dict_to_dataclass(
        VideoBufferConfig, capture_data.get("video_buffer", {})
    ),
    speaker=_dict_to_dataclass(SpeakerConfig, capture_data.get("speaker", {})),
    # ADD: title_card=_dict_to_dataclass(
    #     TitleCardConfig, capture_data.get("title_card", {})
    # ),
)
```

> Gotcha: `_dict_to_dataclass` does *not* recurse into lists (see the explicit waypoints + probes handling at lines 499–511). `whimsy_lines` is `List[str]`, not `List[SomeDataclass]`, so it will pass through untouched — no special handling needed. If the planner ever wants structured whimsy (e.g. categories), that would need the waypoints treatment.

---

### `src/shitbox/events/storage.py` (JSON emitter, modify)

**Analog: itself** — extend the dict-build loop in `generate_events_json` (lines 383–467) and the `save_event` signature (lines 76–121).

**Current `save_event` signature** (lines 76–121):

```python
def save_event(
    self,
    event: Event,
    video_path: Optional[Path] = None,
    *,
    driver_name: Optional[str] = None,
) -> tuple[Path, Path]:
    ...
    metadata = event.to_dict()
    metadata["csv_file"] = csv_path.name
    metadata["saved_at"] = datetime.now(timezone.utc).isoformat()
    if video_path:
        metadata["video_path"] = str(video_path)
    if driver_name is not None:
        metadata["driver_name"] = driver_name

    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)
```

**Pattern to apply (D-17):** add a `poster_path: Optional[Path] = None` keyword-only parameter to `save_event`; persist it the same way as `video_path`; the engine call sites at `events/engine.py:1249` and `events/engine.py:2484` have to pass the new arg.

> Gotcha: `save_event` is called from three sites (grep confirmed):
> - `events/engine.py:1249` (main event save path, has video_path already)
> - `events/engine.py:2484` (shutdown flush — no video_path)
> - Any test harnesses in `tests/`
> The signature is already keyword-only for `driver_name` (note the `*,`). `poster_path` should go beside it.
> Also: `storage.py::update_event_video` at lines 123–144 mutates JSON in place after the fact when video lands late. If the slate is rendered on the same path that produces the poster, the poster path is known *at render time* (before save), not late-binding. No matching `update_event_poster` helper is needed for the common case — but the planner should decide whether late-binding support is worth the few lines given that rendering can fail.

**Current `generate_events_json` entry-dict build** (lines 427–465):

```python
entry: dict = {
    "id": int(start_time * 1000),
    "type": meta.get("type", "unknown").upper(),
    "timestamp": dt.isoformat(),
    "peak_g": meta.get("peak_value"),
    "duration_ms": meta.get("duration_ms"),
}
...
if video_url:
    entry["video_url"] = video_url
```

**Pattern to apply (D-17):** alongside `video_url`, emit `poster_path` (URL-relative, same prefix computation). Copy the "exists?" guard pattern from lines 417–425:

```python
# Mirror the video_url pattern: only surface if the file exists on disk.
stored_poster = meta.get("poster_path")
if stored_poster:
    pp = Path(stored_poster)
    if pp.exists():
        entry["poster_url"] = (
            f"{video_base_url}/{pp.parent.name}/{pp.name}"
        )
```

> Gotcha 1: CONTEXT.md D-17 says *"adds a `poster_path` field"*, but every other path in `generate_events_json` is emitted as a `*_url` (`video_url` at line 463). Pick one shape consistently. Given the website convention and D-17's "Website consumption is deferred", the field on the *saved metadata JSON* should be `poster_path` (filesystem path), and the field on the *events.json feed* should be `poster_url` (URL the website can fetch). This matches how `video_path` in the metadata becomes `video_url` in the feed. The planner should document this split.
>
> Gotcha 2: the `recent()` helper (lines 323–359) builds a parallel dict for the SSE seed. If the website ends up wanting posters in the live stream too, that helper needs the same treatment. CONTEXT.md says website consumption is deferred — don't extend `recent()` unless explicitly scoped in.
>
> Gotcha 3: `count_events_by_type` (lines 361–381) does not need changing, but the planner should note that *any* scan of `self.base_dir.rglob("*.json")` will pick up the new metadata — so poster paths must not collide with the JSON naming convention (`<event>_poster.png`, not `.json`).

---

### `config/config.yaml` (YAML config, modify)

**Analog:** the existing `capture.video_buffer.pip` block (lines 281–289) shows the indent + comment style. `capture.timelapse` (lines 260–263) is a closer shape-match for what TitleCardConfig needs.

**Pattern to apply:**

```yaml
# Insert under capture:, alongside video:/timelapse:/video_buffer:/speaker:.
  title_card:
    enabled: true
    duration_seconds: 3.0
    show_driver: true
    # Whimsy pool used when GPS has no fix at save time (D-09). Overrides
    # the defaults baked into title_card.py if set. One line is picked per
    # slate; no round-robin state.
    whimsy_lines:
      - "Here be dragons"
      - "GPS off having a lie down"
      - "Somewhere between A and B"
      - "The map ends here"
      - "Lost, but enthusiastic"
```

> Gotcha: YAML indent in this file is two-space, no tabs. The `capture:` keys are all at column 2. The `pip:` sub-block at lines 281–289 is under `video_buffer:` (column 4), so don't accidentally put `title_card:` there. It belongs as a sibling of `video:`, `timelapse:`, `video_buffer:`, `speaker:` — column 2.

---

## Shared Patterns

### Pillow usage in this repo

**Source:** `src/shitbox/display/oled.py:42–56`

```python
import adafruit_ssd1306
import board
import busio
from PIL import Image, ImageDraw, ImageFont

self._image = Image.new("1", (128, 64))
self._draw = ImageDraw.Draw(self._image)
self._font = ImageFont.load_default()
```

**Apply to:** `capture/title_card.py`.

> Gotcha: this is the only Pillow site in-tree and it's inside a `try/except Exception` that `start()` uses to gracefully degrade when PIL is absent (lines 42, 63–66). The slate renderer should do the same — import Pillow at module scope, but wrap the render call site so a missing PIL bubbles up as a clean `slate_render_failed` log and the concat path proceeds without a slate (just like `_prepare_intro` degrades when `intro_video` is empty). Pillow is in `pyproject.toml` already (check before committing), but a graceful degrade is consistent with `CLAUDE.md`'s "Hardware graceful degradation" convention.

### Structured logging with structlog kwargs

**Source:** applies everywhere; canonical examples in `ring_buffer.py:1270–1276`, `storage.py:114–119`, `timelapse_compiler.py:183–189`

```python
log.info(
    "event_verb_past_tense",
    kw1=value1,
    kw2=value2,
)
# Errors include last ~500 bytes of subprocess stderr:
stderr = result.stderr.decode()[-500:] if result.stderr else ""
log.error("something_failed", stderr=stderr)
```

**Apply to:** every new log line in `title_card.py` and every new log line in the modified ring_buffer sections. Event-verb naming convention (snake_case, past tense): `slate_rendered`, `slate_render_failed`, `slate_inserted`, `slate_ts_failed`, `slate_ts_timeout`.

### Reverse geocoder reuse (D-09, D-10 fallbacks)

**Source:** `src/shitbox/sync/timelapse_compiler.py:92–116` (full lazy-init + optional-import + None-safe pattern)

```python
def _resolve_place_name(self, lat: float, lon: float) -> Optional[str]:
    """Reverse-geocode (lat, lon) to a place name. Lazy-inits the library."""
    if not self._geocoder_tried:
        self._geocoder_tried = True
        try:
            import reverse_geocoder as rg  # type: ignore[import-untyped]
            self._geocoder = rg
        except Exception as exc:
            log.debug("timelapse_geocoder_unavailable", error=str(exc))
            self._geocoder = None
    if self._geocoder is None:
        return None
    try:
        results = self._geocoder.search((lat, lon))
        if not results:
            return None
        r = results[0]
        name = r.get("name", "") or ""
        admin1 = r.get("admin1", "") or ""
        if name and admin1:
            return f"{name}, {admin1}"
        return name or None
    except Exception as exc:
        log.debug("timelapse_geocode_failed", error=str(exc))
        return None
```

**Apply to:** slate rendering in `title_card.py`. This pattern returns `None` in the two failure branches that map directly onto CONTEXT.md D-09 and D-10:
- No geocoder / ImportError → behave as "no GPS" → use whimsy line (D-09).
- Geocoder returns empty list → behave as "GPS present, no place" → coords-only (D-10).

> Gotcha: the existing `UnifiedEngine` already imports and holds a `_reverse_geocoder` instance (`events/engine.py:776–782`). The slate renderer should be passed a *function* (or the engine's resolver) rather than doing its own lazy import, so there's only one place that decides whether geocoding is available. This matches the CaptureSyncService pattern of receiving an injected callable. The planner should think about whether `TitleCardRenderer(geocoder=engine._reverse_geocoder)` or a slimmer `resolve_place_name=engine._resolve_location_for_slate` injection is cleanest — don't spawn a second `import reverse_geocoder` path.

### Driver name lookup (D-12)

**Source:** `src/shitbox/dashboard/driver_state.py:20–21`

```python
def get_active_driver() -> Optional[str]:
    return _active_driver
```

**Apply to:** slate renderer. The callers at `events/engine.py:1252` and `engine.py:2486` already resolve `driver_state.get_active_driver()` before passing into `save_event`. Route the same value into the slate — do not call `driver_state.get_active_driver()` from inside `title_card.py`, because (a) it couples the renderer to the dashboard module and (b) it race-reads the driver during a long render. Pass it in as a parameter.

### ffmpeg subprocess pattern (timeout + stderr tail)

**Source:** `src/shitbox/capture/ring_buffer.py:418–443` and `src/shitbox/sync/timelapse_compiler.py:179–196`

```python
try:
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if result.returncode == 0 and path.exists():
        log.info("verb_past", size_mb=round(...), duration_s=...)
        return path
    stderr = result.stderr.decode()[-500:] if result.stderr else ""
    log.error("verb_failed", stderr=stderr)
    return None
except subprocess.TimeoutExpired:
    log.error("verb_timeout")
    return None
```

**Apply to:** every ffmpeg spawn in `title_card.py`. Keep timeout modest (60s is fine for a 3s slate render at 10–30 fps).

---

## No Analog Found

None. Every component of this phase has at least one direct in-tree analog.

---

## Metadata

**Analog search scope:**
- `src/shitbox/capture/` (overlay.py, ring_buffer.py, assets/, video.py)
- `src/shitbox/events/` (detector.py, engine.py, storage.py)
- `src/shitbox/sync/timelapse_compiler.py` (closest rendering analog)
- `src/shitbox/utils/config.py` (dataclass patterns)
- `src/shitbox/display/oled.py` (only other Pillow site)
- `src/shitbox/dashboard/driver_state.py` (driver lookup)
- `config/config.yaml` (YAML style)
- Graph report: `graphify-out/GRAPH_REPORT.md` (confirms `EventStorage`, `RingBuffer`, `VideoRingBuffer`, `UnifiedEngine` as god nodes — all touched)

**Files scanned (targeted reads, no full-file loads):** 9

**Pattern extraction date:** 2026-04-23
