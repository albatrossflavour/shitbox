"""Phase 22 / plan 22-02 scaffold: ROLLOVER + BIG_CORNER yaw tests.

Tests are added in plan 22-02. This file exists as a Wave 0 scaffold
so the plan 22-02 executor can write tests RED-first without
touching Wave 0 boundaries.
"""
from unittest.mock import MagicMock  # noqa: F401

import pytest  # noqa: F401

from shitbox.events.detector import (  # noqa: F401
    DetectorConfig,
    Event,
    EventDetector,
    EventType,
)
from shitbox.events.ring_buffer import IMUSample, RingBuffer  # noqa: F401


def test_scaffold_importable() -> None:
    """Placeholder — confirms the scaffold imports without error."""
    assert EventType.HARD_BRAKE is not None
