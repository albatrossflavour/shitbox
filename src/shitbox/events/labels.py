"""Human-readable labels and display colours for event types.

Shared by slate rendering (capture/title_card.py), the website event feed
(currently duplicated in shit-of-theseus/webroot/index.html), and the TTS
path. Importing this module must NOT require hardware or IO — it is a
pure lookup table.
"""

from __future__ import annotations

from typing import Dict

from shitbox.events.detector import EventType

# Human-readable label (D-08). MANUAL_CAPTURE collapses both MANUAL and
# BUTTON website tokens into one concept so the slate composition is
# balanced (D-11 — no badge on manual, driver credit fills the slot).
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
