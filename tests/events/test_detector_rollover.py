"""ROLLOVER detection and BIG_CORNER yaw refinement (phase 22 plan 22-02).

Note on peak_gx/gy/gz semantics: these fields are the gyro values sampled at
the peak_value sample for the tracked axis — i.e. a point-in-time snapshot,
not per-axis maxima. See the Event dataclass docstring in detector.py and
the inline comment at the _update_event update site for the full contract.
"""

import pytest

from shitbox.events.detector import (
    DetectorConfig,
    Event,  # noqa: F401  (exported for downstream test modules)
    EventDetector,
    EventType,
)
from shitbox.events.ring_buffer import IMUSample, RingBuffer


def _sample(
    t: float,
    *,
    gx: float = 0.0,
    gy: float = 0.0,
    gz: float = 0.0,
    ax: float = 0.0,
    ay: float = 0.0,
    az: float = 1.0,
) -> IMUSample:
    return IMUSample(timestamp=t, ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz)


@pytest.fixture
def detector() -> EventDetector:
    buf = RingBuffer(max_seconds=5.0, sample_rate_hz=100.0)
    return EventDetector(
        ring_buffer=buf,
        config=DetectorConfig(),
        get_speed=lambda: 20.0,
    )


def test_rollover_fires_on_sustained_roll_rate(detector: EventDetector) -> None:
    t0 = 100.0
    for i in range(20):
        detector.process_sample(_sample(t0 + i * 0.01, gx=300.0))
    completed = detector.process_sample(_sample(t0 + 0.25, gx=0.0))
    assert completed is not None
    assert completed.event_type == EventType.ROLLOVER


def test_rollover_ignores_transient_spike(detector: EventDetector) -> None:
    t0 = 100.0
    for i in range(5):
        detector.process_sample(_sample(t0 + i * 0.01, gx=300.0))
    completed = detector.process_sample(_sample(t0 + 0.10, gx=0.0))
    assert completed is None or completed.event_type != EventType.ROLLOVER


def test_rollover_fires_on_pitch_axis_gy(detector: EventDetector) -> None:
    t0 = 100.0
    for i in range(20):
        detector.process_sample(_sample(t0 + i * 0.01, gy=-280.0))
    completed = detector.process_sample(_sample(t0 + 0.25, gy=0.0))
    assert completed is not None
    assert completed.event_type == EventType.ROLLOVER


def test_rollover_records_peak_gyro(detector: EventDetector) -> None:
    """peak_gx is the gx value AT the peak_value sample. Because gx is the
    tracked axis here and ramps monotonically, the snapshot coincides with
    the maximum observed gx. Tolerance is deliberately wide — this test
    does not commit the detector to 'independent per-axis max' semantics
    (it is a point-in-time snapshot, not per-axis maxima).
    """
    t0 = 100.0
    for i, gx in enumerate(range(260, 360, 5)):
        detector.process_sample(_sample(t0 + i * 0.01, gx=float(gx)))
    completed = detector.process_sample(_sample(t0 + 0.25, gx=0.0))
    assert completed is not None
    assert completed.event_type == EventType.ROLLOVER
    assert 300.0 <= abs(completed.peak_gx) <= 360.0


def test_big_corner_fires_on_yaw_alone(detector: EventDetector) -> None:
    t0 = 100.0
    for i in range(30):
        detector.process_sample(_sample(t0 + i * 0.01, gz=80.0, ay=0.0))
    completed = detector.process_sample(_sample(t0 + 0.35, gz=0.0, ay=0.0))
    assert completed is not None
    assert completed.event_type == EventType.BIG_CORNER


def test_big_corner_still_fires_on_ay(detector: EventDetector) -> None:
    t0 = 100.0
    for i in range(30):
        detector.process_sample(_sample(t0 + i * 0.01, ay=0.5, gz=0.0))
    completed = detector.process_sample(_sample(t0 + 0.35, ay=0.0, gz=0.0))
    assert completed is not None
    assert completed.event_type == EventType.BIG_CORNER


def test_event_to_dict_includes_peak_gyro(detector: EventDetector) -> None:
    t0 = 100.0
    for i in range(20):
        detector.process_sample(_sample(t0 + i * 0.01, gx=300.0))
    completed = detector.process_sample(_sample(t0 + 0.25, gx=0.0))
    assert completed is not None
    d = completed.to_dict()
    assert "peak_gx" in d
    assert "peak_gy" in d
    assert "peak_gz" in d
    assert isinstance(d["peak_gx"], float)
