"""Phase 22 / plan 22-03 scaffold: stationary auto-zero tests.

Tests are added in plan 22-03. This file exists as a Wave 0 scaffold
so the plan 22-03 executor can write tests RED-first without
touching Wave 0 boundaries.
"""
from pathlib import Path  # noqa: F401
from unittest.mock import MagicMock, patch  # noqa: F401

import pytest  # noqa: F401

from shitbox.events.ring_buffer import IMUSample, RingBuffer  # noqa: F401
from shitbox.storage.database import Database  # noqa: F401


def test_scaffold_importable() -> None:
    """Placeholder — confirms the scaffold imports without error."""
    assert Database is not None
