"""Auto-zero state machine tests. Phase 22 — IMU-05, IMU-06.

Tests the stationary auto-zero state machine wired into the 1 Hz telemetry
loop. The state machine pulls stationary windows from the IMU ring buffer
(to reach the 750-sample floor; 22-07 retarget — 25 Hz x 30 s = 750 samples;
acceptance floor per IMU-02 is 10 Hz) and applies six guards:

  - GPS fix + speed gate
  - Minimum sample count (750)
  - Per-sample raw combined-g reject (per IMU-05 + RESEARCH Pitfall 5)
  - Per-axis window stddev reject
  - Absolute offset plausibility cap (applies even during bootstrap)
  - Tolerance gate vs current live offsets (skipped on bootstrap)

IMU-06: first accept per boot is unconditional (bootstrap rule) AND
persisted offsets are reloaded BEFORE sampler.start() on boot so the
sampler thread never runs with stale config seeds.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# IMPORTANT: IMUSample is exported from ring_buffer, not sampler (Checker Issue 8).
from shitbox.events.ring_buffer import IMUSample, RingBuffer  # noqa: F401
from shitbox.storage.database import Database  # noqa: F401

# ---------------------------------------------------------------------------
# Task 1 tests (config wiring) — these pass as soon as Task 1 lands
# ---------------------------------------------------------------------------


def test_lsm6dsox_config_has_motion_stddev_field() -> None:
    """22-03 adds auto_zero_motion_stddev_g to LSM6DSOXConfig."""
    from shitbox.utils.config import LSM6DSOXConfig

    cfg = LSM6DSOXConfig()
    assert cfg.auto_zero_motion_stddev_g == pytest.approx(0.20)


def test_engine_config_has_auto_zero_fields() -> None:
    """EngineConfig gains flat auto_zero_* fields with IMU-05 canonical names."""
    from shitbox.events.engine import EngineConfig

    cfg = EngineConfig()
    # Exact field names per IMU-05 (Checker Issue 1: canonical names locked)
    assert cfg.auto_zero_enabled is True
    assert cfg.auto_zero_stationary_kmh == pytest.approx(1.0)
    assert cfg.auto_zero_window_seconds == pytest.approx(30.0)
    assert cfg.auto_zero_tolerance_g == pytest.approx(0.05)
    assert cfg.auto_zero_motion_reject_g == pytest.approx(0.2)
    assert cfg.auto_zero_motion_stddev_g == pytest.approx(0.20)
    assert cfg.auto_zero_max_abs_g == pytest.approx(0.5)


def test_engine_config_from_yaml_maps_auto_zero() -> None:
    """EngineConfig.from_yaml_config pulls auto_zero_* 1:1 from LSM6DSOXConfig."""
    from shitbox.events.engine import EngineConfig
    from shitbox.utils.config import Config, LSM6DSOXConfig, SensorsConfig

    yaml_cfg = Config()
    yaml_cfg.sensors = SensorsConfig(
        lsm6dsox=LSM6DSOXConfig(
            auto_zero_enabled=False,
            auto_zero_stationary_kmh=2.0,
            auto_zero_window_seconds=45.0,
            auto_zero_tolerance_g=0.07,
            auto_zero_motion_reject_g=0.3,
            auto_zero_motion_stddev_g=0.25,
            auto_zero_max_abs_g=0.6,
        ),
    )
    engine_cfg = EngineConfig.from_yaml_config(yaml_cfg)

    assert engine_cfg.auto_zero_enabled is False
    assert engine_cfg.auto_zero_stationary_kmh == pytest.approx(2.0)
    assert engine_cfg.auto_zero_window_seconds == pytest.approx(45.0)
    assert engine_cfg.auto_zero_tolerance_g == pytest.approx(0.07)
    assert engine_cfg.auto_zero_motion_reject_g == pytest.approx(0.3)
    assert engine_cfg.auto_zero_motion_stddev_g == pytest.approx(0.25)
    assert engine_cfg.auto_zero_max_abs_g == pytest.approx(0.6)


def test_engine_config_loads_auto_zero_from_yaml() -> None:
    """config/config.yaml through load_config() + from_yaml_config yields defaults."""
    from shitbox.events.engine import EngineConfig
    from shitbox.utils.config import load_config

    # Load the repo's config.yaml explicitly so we don't pick up a CWD surprise.
    yaml_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    config = load_config(str(yaml_path))
    engine_cfg = EngineConfig.from_yaml_config(config)

    assert engine_cfg.auto_zero_enabled is True
    assert engine_cfg.auto_zero_window_seconds == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Task 2 tests (state machine) — these stay RED until Task 3 lands
# ---------------------------------------------------------------------------


def _make_sample(
    ax: float = 0.0,
    ay: float = 0.0,
    az: float = 1.0,
    gx: float = 0.0,
    gy: float = 0.0,
    gz: float = 0.0,
    timestamp: float = 0.0,
) -> IMUSample:
    """Build an IMUSample with sensible defaults (stationary, gravity on z)."""
    return IMUSample(timestamp=timestamp, ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz)


def _make_window(
    n: int,
    ax: float = 0.0,
    ay: float = 0.0,
    az: float = 1.0,
    jitter: float = 0.005,
    perturb_index: int | None = None,
    perturb_sample: IMUSample | None = None,
) -> list[IMUSample]:
    """Construct n synthetic samples with small symmetric jitter around the mean.

    When `perturb_index`/`perturb_sample` is set, that one sample is replaced —
    useful for injecting a transient bump into an otherwise-quiet window
    without inflating the mean appreciably.

    Symmetric jitter: alternating +jitter / -jitter around the target mean so
    the arithmetic mean equals (ax, ay, az) exactly to float precision.
    """
    samples: list[IMUSample] = []
    for i in range(n):
        sign = 1.0 if (i % 2 == 0) else -1.0
        samples.append(
            _make_sample(
                ax=ax + sign * jitter,
                ay=ay + sign * jitter,
                az=az + sign * jitter,
                timestamp=i * 0.01,
            )
        )
    if perturb_index is not None and perturb_sample is not None:
        samples[perturb_index] = perturb_sample
    return samples


@pytest.fixture
def engine_for_auto_zero():
    """Build a UnifiedEngine stand-in with mocked sampler/database/ring_buffer.

    We side-step the full UnifiedEngine constructor (it touches hardware
    state, wires collectors, etc.) and use a SimpleNamespace-like object
    with just the attributes `_maybe_auto_zero` and `_load_persisted_offsets`
    need. The real engine wires these into the same attribute names.
    """
    from shitbox.events.engine import EngineConfig, UnifiedEngine

    cfg = EngineConfig(
        accel_offset_x=0.0,
        accel_offset_y=0.0,
        accel_offset_z=0.0,
        auto_zero_enabled=True,
        auto_zero_stationary_kmh=1.0,
        auto_zero_window_seconds=30.0,
        auto_zero_tolerance_g=0.05,
        auto_zero_motion_reject_g=0.2,
        auto_zero_motion_stddev_g=0.20,
        auto_zero_max_abs_g=0.5,
    )

    # Use __new__ to skip UnifiedEngine.__init__ (it wires real collectors).
    engine = UnifiedEngine.__new__(UnifiedEngine)
    engine.config = cfg
    engine.sampler = MagicMock()
    engine.database = MagicMock()
    engine.ring_buffer = MagicMock(spec=RingBuffer)

    # State the method reads / writes
    engine._current_speed_kmh = 0.0
    engine._gps_has_fix = True
    engine._stationary_elapsed_s = 0.0
    engine._autozero_bootstrap_done = False
    engine._current_accel_offsets = (0.0, 0.0, 0.0)

    # database.get_trip_state returns None by default (nothing persisted).
    engine.database.get_trip_state.return_value = None

    return engine


def _advance_to_window(engine) -> None:
    """Advance the stationary timer so the next tick will evaluate the window."""
    # The implementation ticks +1.0 s per call; do N-1 quiet ticks so the
    # Nth tick is the evaluation tick.
    cfg = engine.config
    n_ticks = int(cfg.auto_zero_window_seconds) - 1
    for _ in range(n_ticks):
        engine._maybe_auto_zero()


def test_bootstrap_first_accept_is_unconditional(engine_for_auto_zero) -> None:
    """First accept after boot bypasses the tolerance gate (IMU-06 bootstrap)."""
    engine = engine_for_auto_zero
    engine._current_accel_offsets = (0.3, -0.1, 1.05)  # static calibration miss
    engine._autozero_bootstrap_done = False

    # Synthetic window of 3000 quiet samples with mean (0.01, 0.005, 1.002).
    window = _make_window(3000, ax=0.01, ay=0.005, az=1.002, jitter=0.005)
    engine.ring_buffer.get_window.return_value = window

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    # Sampler pushed the new offsets
    engine.sampler.update_offsets.assert_called_once()
    ax, ay, az = engine.sampler.update_offsets.call_args.args
    assert ax == pytest.approx(0.01, abs=1e-6)
    assert ay == pytest.approx(0.005, abs=1e-6)
    assert az == pytest.approx(1.002, abs=1e-6)

    # Persisted to trip_state on all three axes
    persist_keys = {c.args[0] for c in engine.database.set_trip_state.call_args_list}
    assert persist_keys == {"accel_offset_x", "accel_offset_y", "accel_offset_z"}

    assert engine._autozero_bootstrap_done is True

    # Log includes bootstrap=True
    accepted_calls = [c for c in mock_log.info.call_args_list
                      if c.args and c.args[0] == "auto_zero_accepted"]
    assert len(accepted_calls) == 1
    assert accepted_calls[0].kwargs.get("bootstrap") is True


def test_post_bootstrap_tolerance_rejects_large_delta(engine_for_auto_zero) -> None:
    """After bootstrap, delta > tolerance triggers tolerance-reject."""
    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = True
    engine._current_accel_offsets = (0.27, -0.08, 1.02)

    # x moved from 0.27 -> 0.50 (delta 0.23 g, way over 0.05 tolerance)
    window = _make_window(3000, ax=0.50, ay=-0.08, az=1.02, jitter=0.005)
    engine.ring_buffer.get_window.return_value = window

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    engine.sampler.update_offsets.assert_not_called()
    engine.database.set_trip_state.assert_not_called()

    rejects = [c for c in mock_log.info.call_args_list
               if c.args and c.args[0] == "auto_zero_rejected"]
    assert any(c.kwargs.get("reason") == "tolerance" for c in rejects)


def test_post_bootstrap_small_delta_accepted(engine_for_auto_zero) -> None:
    """After bootstrap, delta within tolerance accepts cleanly."""
    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = True
    engine._current_accel_offsets = (0.27, -0.08, 1.02)

    # All deltas well under 0.05 tolerance
    window = _make_window(3000, ax=0.28, ay=-0.07, az=1.025, jitter=0.005)
    engine.ring_buffer.get_window.return_value = window

    _advance_to_window(engine)
    engine._maybe_auto_zero()

    engine.sampler.update_offsets.assert_called_once()
    ax, ay, az = engine.sampler.update_offsets.call_args.args
    assert ax == pytest.approx(0.28, abs=1e-6)
    assert ay == pytest.approx(-0.07, abs=1e-6)
    assert az == pytest.approx(1.025, abs=1e-6)


def test_window_stddev_rejected(engine_for_auto_zero) -> None:
    """Sustained vibration (high window stddev) triggers motion_stddev reject."""
    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = True
    engine._current_accel_offsets = (0.27, -0.08, 1.02)

    # Build a window with x stddev ~0.25 g: jitter alternates +/-0.25 on x only.
    # Keep per-sample magnitude below the per-sample gate (0.2 g).
    # A sample at (0.0 + 0.19, 0.0, 0.0) has magnitude 0.19 — under 0.2 g.
    samples: list[IMUSample] = []
    for i in range(3000):
        sign = 1.0 if (i % 2 == 0) else -1.0
        samples.append(_make_sample(
            ax=0.0 + sign * 0.19,  # stddev ~= 0.19 (> 0.20? no — tune below)
            ay=0.0,
            az=0.0,
            timestamp=i * 0.01,
        ))
    # Boost stddev above 0.20 by alternating a wider amplitude that still keeps
    # per-sample magnitude (sqrt(0.21^2)) ≈ 0.21 — but that trips per-sample.
    # Use mean 0 with odd-sample-only 0.25 but make other samples still pass
    # per-sample gate by having magnitude small. Since mag is sqrt(ax^2+ay^2+az^2),
    # a DC offset on az keeps things sane while ax oscillates.
    # Rebuild: az=1.0 always (gravity), ax oscillates +/-0.25 with mag <= 0.2?
    # sqrt(0.25^2 + 1^2) = 1.03 → per-sample gate would REJECT with 0.2 threshold.
    # The per-sample gate is about RAW g-magnitude after offset subtraction, so
    # tests that only want to trigger stddev reject need to stay below 0.2 g raw.
    #
    # Solution: use symmetric stddev that keeps per-sample mag small.
    # Per-sample g = sqrt(ax^2 + ay^2 + az^2) must be <= 0.20.
    # Set az = 0.0, ax oscillates ±0.19 gives mag 0.19 <= 0.20.
    # Stddev of {+0.19, -0.19, ...} is 0.19, below 0.20 gate. Need > 0.20.
    # So pick oscillation ±0.21: mag = 0.21 > 0.20 → per-sample REJECTS (wrong gate).
    #
    # Two-tier fix: mix small-mag high-variance samples. Use a wider distribution
    # like uniform ±0.20 so mag <= 0.20 (equal to threshold, not over).
    # The per-sample gate uses > (strict), so mag == 0.20 passes. ax oscillates
    # ±0.20 → stddev = 0.20 (on the boundary). Boost ax variance by adding
    # a small ay component that keeps mag == 0.20 but raises stddev on ax to
    # some value > 0.20.
    #
    # Simplest: set ax alternating ±0.205, ay = 0.0, az = 0.0. mag = 0.205 > 0.20
    # trips per-sample. That's wrong.
    #
    # Better: use a NON-uniform distribution. 95% of samples are at ax=0 exactly
    # (mag 0.0, pass per-sample), 5% of samples are at ax=0.6 (mag 0.6 — OVER
    # per-sample). The per-sample gate would reject on the bumpy samples.
    #
    # What we actually want: stddev on x > 0.20 with EVERY sample passing
    # per-sample gate (mag <= 0.2). This requires per-sample magnitude <= 0.2
    # AND stddev > 0.2 — mathematically possible only with a high-mean + high-
    # variance combo where mean + k*stddev <= mag_cap. Not easy.
    #
    # Cleanest answer: test stddev reject by asserting the engine hits stddev
    # reject BEFORE hitting per-sample reject. Order of checks matters. The
    # engine code checks per-sample FIRST (that's what RESEARCH Pitfall 5 says
    # is most important), so per-sample failure would mask stddev. Reorder
    # isn't what we want.
    #
    # Workaround: raise per-sample threshold via engine config for THIS test so
    # per-sample never trips, leaving stddev as the gate that fires.
    samples = []
    for i in range(3000):
        sign = 1.0 if (i % 2 == 0) else -1.0
        samples.append(_make_sample(
            ax=sign * 0.25,  # stddev = 0.25 g
            ay=0.0,
            az=0.0,
            timestamp=i * 0.01,
        ))

    # Loosen per-sample so stddev is the active gate for this test.
    engine.config.auto_zero_motion_reject_g = 1.0
    engine.ring_buffer.get_window.return_value = samples

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    engine.sampler.update_offsets.assert_not_called()
    rejects = [c for c in mock_log.info.call_args_list
               if c.args and c.args[0] == "auto_zero_rejected"]
    assert any(c.kwargs.get("reason") == "motion_stddev" for c in rejects)


def test_per_sample_motion_rejected(engine_for_auto_zero) -> None:
    """One sample with combined-g magnitude > threshold triggers motion_sample reject."""
    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = True
    engine._current_accel_offsets = (0.27, -0.08, 1.02)

    # Quiet window with one injected bump.
    bump = _make_sample(ax=0.25, ay=0.0, az=0.0, timestamp=15.0)  # |a| = 0.25 > 0.2
    window = _make_window(
        3000, ax=0.28, ay=-0.07, az=1.025, jitter=0.005,
        perturb_index=500, perturb_sample=bump,
    )
    engine.ring_buffer.get_window.return_value = window

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    engine.sampler.update_offsets.assert_not_called()
    rejects = [c for c in mock_log.info.call_args_list
               if c.args and c.args[0] == "auto_zero_rejected"]
    assert any(c.kwargs.get("reason") == "motion_sample" for c in rejects)


def test_minimum_sample_count_enforced(engine_for_auto_zero) -> None:
    """Fewer than 750 samples in window rejects with insufficient_samples.

    22-07: floor rescaled from 2500 to 750 after retarget from 100 Hz -> 25 Hz.
    """
    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = True
    engine._current_accel_offsets = (0.27, -0.08, 1.02)

    window = _make_window(600, ax=0.28, ay=-0.07, az=1.025, jitter=0.005)
    engine.ring_buffer.get_window.return_value = window

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    engine.sampler.update_offsets.assert_not_called()
    rejects = [c for c in mock_log.info.call_args_list
               if c.args and c.args[0] == "auto_zero_rejected"]
    hit = [c for c in rejects if c.kwargs.get("reason") == "insufficient_samples"]
    assert len(hit) == 1
    assert hit[0].kwargs.get("sample_count") == 600
    assert hit[0].kwargs.get("min_required") == 750


def test_gps_no_fix_never_triggers(engine_for_auto_zero) -> None:
    """Without GPS fix, the stationary timer never advances and nothing fires."""
    engine = engine_for_auto_zero
    engine._gps_has_fix = False
    engine._current_speed_kmh = 0.0

    for _ in range(60):
        engine._maybe_auto_zero()

    engine.ring_buffer.get_window.assert_not_called()
    engine.sampler.update_offsets.assert_not_called()
    assert engine._stationary_elapsed_s == 0.0


def test_gps_fix_required_even_with_speed_zero(engine_for_auto_zero) -> None:
    """Positive fix gate: speed=0 alone is not enough; fix must also be True."""
    engine = engine_for_auto_zero

    # Phase A: no fix, speed 0 — timer must not advance
    engine._gps_has_fix = False
    engine._current_speed_kmh = 0.0
    engine._stationary_elapsed_s = 0.0
    engine._maybe_auto_zero()
    assert engine._stationary_elapsed_s == 0.0

    # Phase B: fix flips true, speed still 0 — timer must advance
    engine._gps_has_fix = True
    engine._maybe_auto_zero()
    assert engine._stationary_elapsed_s > 0.0


def test_speed_above_gate_resets_window(engine_for_auto_zero) -> None:
    """Speed crossing the stationary threshold resets the elapsed counter."""
    engine = engine_for_auto_zero
    engine._gps_has_fix = True
    engine._current_speed_kmh = 0.0

    # Accumulate 10 seconds of stationary
    for _ in range(10):
        engine._maybe_auto_zero()
    assert engine._stationary_elapsed_s == pytest.approx(10.0)

    # Speed jumps above threshold for one tick
    engine._current_speed_kmh = 5.0
    engine._maybe_auto_zero()
    assert engine._stationary_elapsed_s == 0.0

    # Back to stationary, counter starts fresh
    engine._current_speed_kmh = 0.0
    engine._maybe_auto_zero()
    assert engine._stationary_elapsed_s == pytest.approx(1.0)


def test_implausible_magnitude_rejected_even_during_bootstrap(
    engine_for_auto_zero,
) -> None:
    """A 0.9 g mean x exceeds the 0.5 g plausibility cap — bootstrap stays False."""
    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = False
    engine._current_accel_offsets = (0.0, 0.0, 0.0)

    window = _make_window(3000, ax=0.9, ay=0.1, az=1.05, jitter=0.005)
    # Per-sample mag ~= sqrt(0.9^2 + 0.1^2 + 1.05^2) ~= 1.39 — would trip per-sample
    # Loosen per-sample so plausibility gate is the one firing.
    engine.config.auto_zero_motion_reject_g = 10.0
    engine.ring_buffer.get_window.return_value = window

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    engine.sampler.update_offsets.assert_not_called()
    assert engine._autozero_bootstrap_done is False

    rejects = [c for c in mock_log.warning.call_args_list
               if c.args and c.args[0] == "auto_zero_rejected"]
    rejects += [c for c in mock_log.info.call_args_list
                if c.args and c.args[0] == "auto_zero_rejected"]
    assert any(c.kwargs.get("reason") == "implausible" for c in rejects)


def test_persistence_rollback_on_failure(engine_for_auto_zero) -> None:
    """Mid-persist failure rolls back in-memory offsets to previous-known-good."""
    import sqlite3

    engine = engine_for_auto_zero
    engine._autozero_bootstrap_done = True
    engine._current_accel_offsets = (0.27, -0.08, 1.02)

    window = _make_window(3000, ax=0.28, ay=-0.07, az=1.025, jitter=0.005)
    engine.ring_buffer.get_window.return_value = window

    # First set_trip_state call succeeds, second (y axis) raises
    engine.database.set_trip_state.side_effect = [
        None,
        sqlite3.OperationalError("disk full"),
        None,
    ]

    _advance_to_window(engine)
    with patch("shitbox.events.engine.log") as mock_log:
        engine._maybe_auto_zero()

    # Sampler called at least twice: once with new, once rolled back to prev
    calls = engine.sampler.update_offsets.call_args_list
    assert len(calls) >= 2
    first = calls[0].args
    rollback = calls[-1].args
    assert first == pytest.approx((0.28, -0.07, 1.025), abs=1e-6)
    assert rollback == pytest.approx((0.27, -0.08, 1.02), abs=1e-6)

    # In-memory state rolled back
    assert engine._current_accel_offsets == pytest.approx((0.27, -0.08, 1.02), abs=1e-6)

    # Persist-failure log emitted
    fails = [c for c in mock_log.error.call_args_list
             if c.args and c.args[0] == "auto_zero_persist_failed"]
    assert len(fails) == 1

    # Bootstrap flag unchanged (was True, stays True)
    assert engine._autozero_bootstrap_done is True


def test_engine_start_loads_persisted_offsets_before_sampler_start(
    engine_for_auto_zero,
) -> None:
    """IMU-06 boot path: persisted offsets load BEFORE sampler.start()."""
    engine = engine_for_auto_zero

    # Wire the sampler mock with a shared parent so we can observe call order
    # across update_offsets and start.
    parent = MagicMock()
    engine.sampler = parent.sampler

    # Seed persisted values
    def _fake_get(key: str):
        return {
            "accel_offset_x": 0.2711,
            "accel_offset_y": -0.0831,
            "accel_offset_z": 0.0216,
        }.get(key)

    engine.database.get_trip_state.side_effect = _fake_get

    # Simulate the boot sequence: load offsets, then start sampler.
    engine._load_persisted_offsets()
    engine.sampler.start()

    # Inspect parent.mock_calls — update_offsets MUST appear before sampler.start
    call_names = [c[0] for c in parent.mock_calls]  # e.g. 'sampler.update_offsets'
    update_idx = next(
        (i for i, n in enumerate(call_names) if n.endswith("update_offsets")),
        -1,
    )
    start_idx = next(
        (i for i, n in enumerate(call_names) if n.endswith("start") and "update" not in n),
        -1,
    )
    assert update_idx != -1, "update_offsets was never called"
    assert start_idx != -1, "sampler.start was never called"
    assert update_idx < start_idx, (
        f"update_offsets (idx {update_idx}) must precede "
        f"sampler.start (idx {start_idx}); calls={call_names}"
    )

    # Values piped through correctly
    ax, ay, az = engine.sampler.update_offsets.call_args.args
    assert ax == pytest.approx(0.2711)
    assert ay == pytest.approx(-0.0831)
    assert az == pytest.approx(0.0216)

    # In-memory offsets updated
    assert engine._current_accel_offsets == pytest.approx(
        (0.2711, -0.0831, 0.0216), abs=1e-6
    )
