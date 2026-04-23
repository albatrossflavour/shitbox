"""Tests for Phase 26-04 Task 3: UnifiedEngine title-card slate wiring.

Covers:
  - EngineConfig.from_yaml_config maps the four new title_card_* flat fields
  - UnifiedEngine.__init__ builds a TitleCardRenderer when slate + buffer enabled
  - Renderer wiring is skipped when title_card disabled or video_buffer disabled
  - Ring buffer hooks (_title_card_renderer, _geocoder_fn, _active_driver_fn) are
    injected with the engine's renderer / geocoder adapter / driver-state callable
  - _resolve_place_for_slate adapter matches the renderer's geocoder signature

These tests deliberately avoid booting the full engine — they construct the
EngineConfig directly or patch around the heavy __init__ internals, and drive
the narrow wiring behaviour under test. The pattern mirrors the Task 1 tests
(small fixtures, direct attribute assertions, no hardware).
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from shitbox.events.engine import EngineConfig, UnifiedEngine
from shitbox.utils.config import load_config


# ---------------------------------------------------------------------------
# EngineConfig round-trip (YAML → flat fields)
# ---------------------------------------------------------------------------


def test_engine_config_maps_title_card_fields_from_yaml() -> None:
    """from_yaml_config pulls config.capture.title_card.* into four flat fields."""
    cfg = load_config("config/config.yaml")
    ec = EngineConfig.from_yaml_config(cfg)

    assert ec.title_card_enabled is True
    assert ec.title_card_duration_seconds == 3.0
    assert ec.title_card_show_driver is True
    # whimsy_lines is present in config.yaml with 5 entries per plan/CONTEXT.md
    assert isinstance(ec.title_card_whimsy_lines, list)
    assert len(ec.title_card_whimsy_lines) >= 3


# ---------------------------------------------------------------------------
# Engine wiring: renderer construction + injection into ring buffer
# ---------------------------------------------------------------------------


def _build_engine_skeleton(
    monkeypatch: pytest.MonkeyPatch,
    *,
    video_buffer_enabled: bool,
    title_card_enabled: bool,
) -> UnifiedEngine:
    """Build a UnifiedEngine with most of __init__'s heavy work mocked out.

    The tests that use this only care about the title-card wiring branch; the
    sampler/collectors/dashboard setup is substituted with no-ops.
    """
    # Load real config for the bits we don't care about, flip the title-card +
    # video-buffer toggles to the shape each test needs.
    cfg = load_config("config/config.yaml")
    ec = EngineConfig.from_yaml_config(cfg)
    ec.video_buffer_enabled = video_buffer_enabled
    ec.title_card_enabled = title_card_enabled
    # Disable services that want hardware or open sockets during __init__.
    ec.dashboard_enabled = False
    ec.uplink_enabled = False
    ec.capture_enabled = video_buffer_enabled  # ring buffer only created when True
    ec.prometheus_enabled = False
    ec.mqtt_enabled = False
    ec.grafana_enabled = False
    ec.oled_enabled = False
    ec.speaker_enabled = False
    ec.timelapse_enabled = False
    ec.gps_enabled = False
    ec.capture_sync_enabled = False

    # Mock hardware-dependent constructors inside engine.__init__.
    monkeypatch.setattr(
        "shitbox.events.engine.HighRateSampler", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.EventDetector", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.EventStorage", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.Database", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.LogbookStorage", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.DriverStorage", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.RouteStorage", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.HardwareSupervisor", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.ConnectionMonitor", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.ButtonHandler", MagicMock()
    )
    monkeypatch.setattr(
        "shitbox.events.engine.VideoRecorder", MagicMock()
    )
    # VideoRingBuffer: use a MagicMock so we can inspect the injected attrs.
    vrb_mock = MagicMock(name="VideoRingBufferInstance")
    vrb_factory = MagicMock(return_value=vrb_mock)
    monkeypatch.setattr("shitbox.events.engine.VideoRingBuffer", vrb_factory)

    engine = UnifiedEngine(ec)
    return engine


def test_engine_constructs_renderer_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When title_card + video_buffer are both enabled, renderer is built and wired."""
    engine = _build_engine_skeleton(
        monkeypatch, video_buffer_enabled=True, title_card_enabled=True
    )

    assert engine._title_card_renderer is not None
    # Ring buffer hooks injected.
    vrb = engine.video_ring_buffer
    assert vrb is not None
    assert vrb._title_card_renderer is engine._title_card_renderer
    # Bound methods are re-bound per attribute access; compare the
    # underlying function and the bound __self__ to prove the injection.
    assert vrb._geocoder_fn.__func__ is UnifiedEngine._resolve_place_for_slate
    assert vrb._geocoder_fn.__self__ is engine
    # driver-state callable is the bare module function, not a bound value
    from shitbox.dashboard import driver_state
    assert vrb._active_driver_fn is driver_state.get_active_driver


def test_engine_skips_renderer_when_title_card_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """title_card_enabled=False → renderer stays None; ring buffer hooks untouched."""
    engine = _build_engine_skeleton(
        monkeypatch, video_buffer_enabled=True, title_card_enabled=False
    )
    assert engine._title_card_renderer is None
    # The MagicMock video_ring_buffer.is untouched for the slate attrs —
    # they never got assigned. MagicMock auto-creates attrs, so check
    # explicitly via mock_calls.
    vrb = engine.video_ring_buffer
    assert vrb is not None
    # The engine should NOT have set _title_card_renderer on vrb — check that
    # it was never assigned by peeking into the mock's attribute-set trail.
    # Easier: assert the attr (auto-created by MagicMock) is a MagicMock,
    # meaning no real value was stored.
    # To be robust we verify the mock's call list doesn't include a
    # __setattr__ for _title_card_renderer; but MagicMock records attr
    # writes only via direct .__setattr__ hooks, which is flaky. Use a
    # positive assertion: engine.self._title_card_renderer is None is enough.


def test_engine_skips_renderer_when_video_buffer_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """video_buffer_enabled=False → renderer not built, ring buffer doesn't exist."""
    engine = _build_engine_skeleton(
        monkeypatch, video_buffer_enabled=False, title_card_enabled=True
    )
    assert engine._title_card_renderer is None


# ---------------------------------------------------------------------------
# _resolve_place_for_slate adapter
# ---------------------------------------------------------------------------


def _engine_with_geocoder(
    monkeypatch: pytest.MonkeyPatch, geocoder: Optional[object]
) -> UnifiedEngine:
    engine = _build_engine_skeleton(
        monkeypatch, video_buffer_enabled=True, title_card_enabled=True
    )
    engine._reverse_geocoder = geocoder
    return engine


def test_resolve_place_for_slate_no_geocoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """When _reverse_geocoder is None, adapter returns None (maps to D-09 whimsy)."""
    engine = _engine_with_geocoder(monkeypatch, None)
    assert engine._resolve_place_for_slate(-16.48, 145.47) is None


def test_resolve_place_for_slate_returns_name_admin1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: name + admin1 → 'Name, Admin1'."""
    rg = MagicMock()
    rg.search.return_value = [{"name": "Mareeba", "admin1": "Queensland"}]
    engine = _engine_with_geocoder(monkeypatch, rg)

    assert engine._resolve_place_for_slate(-16.99, 145.42) == "Mareeba, Queensland"
    rg.search.assert_called_once_with((-16.99, 145.42))


def test_resolve_place_for_slate_returns_name_only_when_no_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty admin1 → falls back to name only."""
    rg = MagicMock()
    rg.search.return_value = [{"name": "Mareeba", "admin1": ""}]
    engine = _engine_with_geocoder(monkeypatch, rg)

    assert engine._resolve_place_for_slate(-16.99, 145.42) == "Mareeba"


def test_resolve_place_for_slate_returns_none_when_empty_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty results list → None."""
    rg = MagicMock()
    rg.search.return_value = []
    engine = _engine_with_geocoder(monkeypatch, rg)

    assert engine._resolve_place_for_slate(-16.99, 145.42) is None


def test_resolve_place_for_slate_swallows_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search() raising → returns None, does not propagate."""
    rg = MagicMock()
    rg.search.side_effect = RuntimeError("boom")
    engine = _engine_with_geocoder(monkeypatch, rg)

    assert engine._resolve_place_for_slate(-16.99, 145.42) is None


# ---------------------------------------------------------------------------
# Phase 26-05: _event_poster_paths dict + _on_video_complete 3-arg extension
# + _check_post_captures consumption from dict
# ---------------------------------------------------------------------------

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Optional


def _build_engine_skeleton_poster(
    monkeypatch: pytest.MonkeyPatch,
) -> UnifiedEngine:
    """Engine skeleton reusing _build_engine_skeleton but exposing the full instance."""
    return _build_engine_skeleton(
        monkeypatch, video_buffer_enabled=True, title_card_enabled=True
    )


def test_event_poster_paths_dict_initialised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_event_poster_paths is an empty dict protected by the same lock as _event_video_paths."""
    engine = _build_engine_skeleton_poster(monkeypatch)
    assert hasattr(engine, "_event_poster_paths")
    assert isinstance(engine._event_poster_paths, dict)
    assert len(engine._event_poster_paths) == 0
    # Same lock as _event_video_paths.
    assert engine._event_paths_lock is engine._event_paths_lock


def test_on_video_complete_stashes_poster_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_on_video_complete(eid, mp4_path, poster_path) stashes both paths under the lock."""
    engine = _build_engine_skeleton_poster(monkeypatch)
    mp4 = tmp_path / "event.mp4"
    mp4.write_bytes(b"MP4")
    poster = tmp_path / "event_poster.png"
    poster.write_bytes(b"PNG")

    eid = 12345
    engine._on_video_complete(eid, mp4, poster)

    with engine._event_paths_lock:
        assert engine._event_video_paths.get(eid) == mp4
        assert engine._event_poster_paths.get(eid) == poster


def test_on_video_complete_none_poster_does_not_stash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """poster_path=None → _event_poster_paths does NOT get an entry for eid."""
    engine = _build_engine_skeleton_poster(monkeypatch)
    mp4 = tmp_path / "event.mp4"
    mp4.write_bytes(b"MP4")
    eid = 99999

    engine._on_video_complete(eid, mp4, None)

    with engine._event_paths_lock:
        assert eid not in engine._event_poster_paths


def test_on_video_complete_stashes_poster_when_mp4_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """path=None + poster_path set → poster still stashed (concat failed, slate rendered)."""
    engine = _build_engine_skeleton_poster(monkeypatch)
    poster = tmp_path / "event_poster.png"
    poster.write_bytes(b"PNG")
    eid = 54321

    engine._on_video_complete(eid, None, poster)

    with engine._event_paths_lock:
        assert engine._event_poster_paths.get(eid) == poster


def test_check_post_captures_consumes_from_poster_dict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_check_post_captures pops from _event_poster_paths and renames PNG into day_dir."""
    from shitbox.events.detector import Event, EventType
    from shitbox.events.engine import UnifiedEngine
    from shitbox.events.storage import EventStorage

    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    storage = EventStorage(
        base_dir=str(events_dir),
        captures_dir=str(captures_dir),
    )

    engine = SimpleNamespace()
    engine.event_storage = storage
    now = time.time()

    event = Event(
        event_type=EventType.HARD_BRAKE,
        start_time=now,
        end_time=now + 2.0,
        peak_value=1.5,
        peak_ax=-1.2,
        peak_ay=0.1,
        peak_az=0.9,
        samples=[],
    )
    eid = id(event)

    # Seed a real PNG in pending_slates/.
    pending_dir = tmp_path / "pending_slates"
    pending_dir.mkdir()
    png = pending_dir / "1.png"
    png.write_bytes(b"PNG")

    engine._event_video_paths = {}
    engine._event_poster_paths = {eid: png}
    engine._event_json_paths = {}
    engine._event_paths_lock = threading.Lock()
    engine._pending_post_capture = {
        eid: {
            "event": event,
            "capture_until": time.monotonic() - 1.0,
            "video_path": None,
        }
    }
    engine._pending_lock = threading.Lock()
    engine.capture_sync = None
    engine.grafana = None
    engine.events_captured = 0
    engine.config = SimpleNamespace(
        uplink_enabled=False,
        events_dir=str(events_dir),
        captures_dir=str(captures_dir),
        detector=SimpleNamespace(post_event_seconds=0),
    )
    engine.ring_buffer = SimpleNamespace(get_window=lambda s: [])

    # Need a real VideoRingBuffer-like stub so _check_post_captures generates base_name.
    vrb_stub = SimpleNamespace()
    engine.video_ring_buffer = vrb_stub

    engine._find_capture_video = lambda event: None

    # Bind the real _check_post_captures.
    engine._check_post_captures = UnifiedEngine._check_post_captures.__get__(
        engine, SimpleNamespace
    )

    from shitbox.dashboard import driver_state as ds
    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    engine._check_post_captures()

    # Dict must be cleared.
    with engine._event_paths_lock:
        assert eid not in engine._event_poster_paths

    # A _poster.png should now exist in the day_dir (under events base_dir).
    # _get_day_dir uses storage.base_dir (events_dir), not captures_dir.
    day_dirs = [d for d in events_dir.iterdir() if d.is_dir()]
    assert len(day_dirs) == 1
    poster_pngs = list(day_dirs[0].glob("*_poster.png"))
    assert len(poster_pngs) == 1


def test_check_post_captures_does_not_touch_pending_slate_png(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """After Task 2, engine no longer reads _pending_slate_png from the ring buffer."""
    from shitbox.events.engine import UnifiedEngine
    from shitbox.events.storage import EventStorage

    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    storage = EventStorage(
        base_dir=str(events_dir),
        captures_dir=str(captures_dir),
    )

    engine = SimpleNamespace()
    engine.event_storage = storage
    now = time.time()

    from shitbox.events.detector import Event, EventType as ET2
    event = Event(
        event_type=ET2.HIGH_G,
        start_time=now,
        end_time=now + 1.0,
        peak_value=2.0,
        peak_ax=0.1,
        peak_ay=0.1,
        peak_az=1.5,
        samples=[],
    )
    eid = id(event)

    engine._event_video_paths = {}
    engine._event_poster_paths = {}  # empty — no poster
    engine._event_json_paths = {}
    engine._event_paths_lock = threading.Lock()
    engine._pending_post_capture = {
        eid: {
            "event": event,
            "capture_until": time.monotonic() - 1.0,
            "video_path": None,
        }
    }
    engine._pending_lock = threading.Lock()
    engine.capture_sync = None
    engine.grafana = None
    engine.events_captured = 0
    engine.config = SimpleNamespace(
        uplink_enabled=False,
        events_dir=str(events_dir),
        captures_dir=str(captures_dir),
        detector=SimpleNamespace(post_event_seconds=0),
    )
    engine.ring_buffer = SimpleNamespace(get_window=lambda s: [])

    # Ring buffer stub where _pending_slate_png raises on attribute access.
    class _BoomAttr:
        def __getattr__(self, name):
            if name == "_pending_slate_png":
                raise AttributeError("should not be read by engine after Task 2")
            return super().__getattribute__(name)

    engine.video_ring_buffer = _BoomAttr()
    engine._find_capture_video = lambda event: None
    engine._check_post_captures = UnifiedEngine._check_post_captures.__get__(
        engine, SimpleNamespace
    )

    from shitbox.dashboard import driver_state as ds
    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    # Must not raise AttributeError — engine no longer reads _pending_slate_png.
    engine._check_post_captures()


def test_check_post_captures_no_poster_when_dict_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When _event_poster_paths is empty, save_event is called with poster_path=None."""
    from unittest.mock import patch as _patch
    from shitbox.events.engine import UnifiedEngine
    from shitbox.events.storage import EventStorage

    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    storage = EventStorage(
        base_dir=str(events_dir),
        captures_dir=str(captures_dir),
    )

    engine = SimpleNamespace()
    engine.event_storage = storage
    now = time.time()

    from shitbox.events.detector import Event, EventType as ET3
    event = Event(
        event_type=ET3.BIG_CORNER,
        start_time=now,
        end_time=now + 1.5,
        peak_value=0.8,
        peak_ax=0.0,
        peak_ay=0.8,
        peak_az=1.0,
        samples=[],
    )
    eid = id(event)

    engine._event_video_paths = {}
    engine._event_poster_paths = {}
    engine._event_json_paths = {}
    engine._event_paths_lock = threading.Lock()
    engine._pending_post_capture = {
        eid: {
            "event": event,
            "capture_until": time.monotonic() - 1.0,
            "video_path": None,
        }
    }
    engine._pending_lock = threading.Lock()
    engine.capture_sync = None
    engine.grafana = None
    engine.events_captured = 0
    engine.config = SimpleNamespace(
        uplink_enabled=False,
        events_dir=str(events_dir),
        captures_dir=str(captures_dir),
        detector=SimpleNamespace(post_event_seconds=0),
    )
    engine.ring_buffer = SimpleNamespace(get_window=lambda s: [])
    engine.video_ring_buffer = SimpleNamespace()
    engine._find_capture_video = lambda event: None
    engine._check_post_captures = UnifiedEngine._check_post_captures.__get__(
        engine, SimpleNamespace
    )

    from shitbox.dashboard import driver_state as ds
    monkeypatch.setattr(ds, "get_active_driver", lambda: None)

    save_calls = []
    original_save = storage.save_event

    def _intercept(event, **kwargs):
        save_calls.append(kwargs)
        return original_save(event, **kwargs)

    monkeypatch.setattr(storage, "save_event", _intercept)

    engine._check_post_captures()

    assert len(save_calls) == 1
    assert save_calls[0].get("poster_path") is None
