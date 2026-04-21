"""Tests for BaseCollector hardware state reporting hooks.

Verifies that:
- role=None makes _report_present / _report_missing no-ops
- successful read calls hw_state.report_present via _report_present
- read errors call hw_state.report_missing via _report_missing
- setup failure calls hw_state.report_missing before re-raising
- _max_errors safety valve behaviour is unchanged
- role attribute is stored correctly
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from shitbox.collectors.base import BaseCollector
from shitbox.hardware import state as hw_state
from shitbox.hardware.state import DeviceState
from shitbox.storage.models import Reading


# ---------------------------------------------------------------------------
# Fake collector for testing
# ---------------------------------------------------------------------------


class FakeCollector(BaseCollector[int]):
    """Minimal concrete subclass for testing BaseCollector hooks."""

    def __init__(self, name: str = "fake", sample_rate_hz: float = 1.0, **kwargs) -> None:
        super().__init__(name=name, sample_rate_hz=sample_rate_hz, **kwargs)
        self._setup_should_raise: Optional[Exception] = None
        self._read_should_raise: Optional[Exception] = None
        self._read_return: Optional[int] = 42

    def setup(self) -> None:
        if self._setup_should_raise is not None:
            raise self._setup_should_raise

    def read(self) -> Optional[int]:
        if self._read_should_raise is not None:
            raise self._read_should_raise
        return self._read_return

    def to_reading(self, data: int) -> Reading:
        mock_reading = MagicMock(spec=Reading)
        return mock_reading


# ---------------------------------------------------------------------------
# Helper: drive one successful or failing read iteration
# ---------------------------------------------------------------------------


def _drive_one_success(collector: FakeCollector) -> None:
    """Simulate one successful iteration of the run loop."""
    data = collector.read()
    if data is not None:
        collector._last_reading = data
        collector._error_count = 0
        collector._report_present()


def _drive_one_failure(collector: FakeCollector, exc: Exception) -> None:
    """Simulate one failing iteration of the run loop."""
    collector._read_should_raise = exc
    try:
        collector.read()
    except Exception:
        collector._error_count += 1
        collector._report_missing()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_role_attribute_set() -> None:
    """role kwarg is stored on the instance."""
    c = FakeCollector(name="t", sample_rate_hz=1.0, role="foo")
    assert c.role == "foo"


def test_no_role_makes_hooks_noop() -> None:
    """_report_present and _report_missing are no-ops when role is None."""
    c = FakeCollector(role=None)
    c._report_present()
    c._report_missing()
    # State should be completely empty — no side effects
    assert hw_state.snapshot() == {}


def test_report_present_on_successful_read() -> None:
    """Successful read triggers hw_state.report_present for the collector's role."""
    hw_state.initialise({"env_test": "best_effort"})
    c = FakeCollector(role="env_test")
    _drive_one_success(c)
    snap = hw_state.snapshot()
    assert snap["env_test"].state == DeviceState.PRESENT


def test_report_missing_on_read_error() -> None:
    """Read error triggers hw_state.report_missing for the collector's role."""
    hw_state.initialise({"env_test": "best_effort"})
    c = FakeCollector(role="env_test")
    _drive_one_failure(c, OSError("sensor gone"))
    snap = hw_state.snapshot()
    assert snap["env_test"].state == DeviceState.MISSING
    assert snap["env_test"].consecutive_misses == 1


def test_report_missing_on_setup_failure() -> None:
    """Setup failure triggers hw_state.report_missing before re-raising."""
    hw_state.initialise({"env_test": "best_effort"})
    c = FakeCollector(role="env_test")
    c._setup_should_raise = OSError("I2C init fail")

    with pytest.raises(OSError):
        c.start()

    snap = hw_state.snapshot()
    assert snap["env_test"].state == DeviceState.MISSING


def test_max_errors_safety_valve_unchanged() -> None:
    """_max_errors safety valve still flips _running=False after 10 consecutive errors."""
    hw_state.initialise({"env_test": "best_effort"})
    # Run at very high rate so loop iterates quickly; patch time.sleep in the loop only
    c = FakeCollector(role="env_test", sample_rate_hz=100_000.0)
    c._read_should_raise = OSError("persistent error")
    c._setup_should_raise = None  # setup succeeds

    # Patch the module-level time.sleep used inside _run_loop so the loop doesn't
    # actually wait between iterations, but join the actual thread to wait for it.
    with patch("shitbox.collectors.base.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        mock_time.sleep = MagicMock()
        c.start()
        # Thread started — join with a generous timeout to let it exhaust _max_errors
        assert c._thread is not None
        c._thread.join(timeout=5.0)

    assert not c._running, "Collector should have stopped after max errors"
    snap = hw_state.snapshot()
    assert snap["env_test"].state == DeviceState.MISSING
