"""Shared fixtures for hardware tests."""
from __future__ import annotations

import pytest

from shitbox.hardware import state as hw_state


@pytest.fixture(autouse=True)
def _clear_hw_state():
    hw_state.clear_state()
    yield
    hw_state.clear_state()
