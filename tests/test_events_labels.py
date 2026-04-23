"""Tests for shitbox.events.labels — canonical event label and colour lookups."""

from __future__ import annotations

import pytest

from shitbox.events.detector import EventType
from shitbox.events.labels import (
    EVENT_COLOURS,
    EVENT_LABELS,
    ROLLOVER_STRIPE_COLOUR,
    colour_for,
    label_for,
)


# ---------------------------------------------------------------------------
# Parametrised coverage of every EventType member
# ---------------------------------------------------------------------------

EXPECTED_LABELS = [
    (EventType.HARD_BRAKE, "Hard Brake"),
    (EventType.BIG_CORNER, "Big Corner"),
    (EventType.HIGH_G, "High G"),
    (EventType.ROUGH_ROAD, "Rough Road"),
    (EventType.MANUAL_CAPTURE, "Manual Capture"),
    (EventType.BOOT, "System Start"),
    (EventType.ROLLOVER, "Rollover"),
]

EXPECTED_COLOURS = [
    (EventType.HIGH_G, "#da3633"),
    (EventType.BIG_CORNER, "#d29922"),
    (EventType.HARD_BRAKE, "#f85149"),
    (EventType.ROUGH_ROAD, "#8957e5"),
    (EventType.MANUAL_CAPTURE, "#238636"),
    (EventType.BOOT, "#1f6feb"),
    (EventType.ROLLOVER, "#e74c3c"),
]


@pytest.mark.parametrize("event_type, expected", EXPECTED_LABELS)
def test_label_for_known_types(event_type: EventType, expected: str) -> None:
    assert label_for(event_type) == expected


@pytest.mark.parametrize("event_type, expected", EXPECTED_COLOURS)
def test_colour_for_known_types(event_type: EventType, expected: str) -> None:
    assert colour_for(event_type) == expected


# ---------------------------------------------------------------------------
# Dict coverage — every EventType member must appear in both tables
# ---------------------------------------------------------------------------

def test_event_labels_covers_all_members() -> None:
    """Every EventType member has an entry in EVENT_LABELS."""
    missing = [et for et in EventType if et not in EVENT_LABELS]
    assert missing == [], f"EventType members missing from EVENT_LABELS: {missing}"


def test_event_colours_covers_all_members() -> None:
    """Every EventType member has an entry in EVENT_COLOURS."""
    missing = [et for et in EventType if et not in EVENT_COLOURS]
    assert missing == [], f"EventType members missing from EVENT_COLOURS: {missing}"


# ---------------------------------------------------------------------------
# Module-level constant
# ---------------------------------------------------------------------------

def test_rollover_stripe_colour() -> None:
    assert ROLLOVER_STRIPE_COLOUR == "#000000"


# ---------------------------------------------------------------------------
# Fallback paths (synthetic enum-like stub, not a real EventType member)
# ---------------------------------------------------------------------------

class _Dummy:
    """Minimal stub with .value to exercise the fallback branches."""

    value = "weird_case"


def test_label_for_fallback_title_cases_value() -> None:
    """Unknown type falls back to title-cased enum value with underscores replaced."""
    result = label_for(_Dummy())  # type: ignore[arg-type]
    assert result == "Weird Case"


def test_colour_for_fallback_returns_grey() -> None:
    """Unknown type falls back to the neutral grey sentinel."""
    result = colour_for(_Dummy())  # type: ignore[arg-type]
    assert result == "#6e7681"
