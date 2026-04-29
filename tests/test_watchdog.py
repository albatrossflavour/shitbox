"""Unit tests for the systemd shitbox-telemetry.service unit file.

Validates that the service unit is correctly hardened for unlimited
restarts and a 30-second watchdog timeout. The 30s budget gives cold-start
GPS acquisition (max_wait_seconds=20) plus the rest of startup enough
headroom; engine.py also pings WATCHDOG=1 inside the GPS-wait loop so a
slow cold fix can't burn the whole budget on its own.
"""

import configparser
from pathlib import Path


SERVICE_FILE = Path(__file__).parent.parent / "systemd" / "shitbox-telemetry.service"


def _read_service_file() -> str:
    """Return the raw contents of the service unit file."""
    return SERVICE_FILE.read_text()


def _parse_service_section() -> configparser.SectionProxy:
    """Parse the [Service] section of the unit file using configparser."""
    contents = _read_service_file()
    parser = configparser.ConfigParser(allow_no_value=True)
    # configparser treats lines starting with # as comments by default,
    # but systemd unit files use ; for inline comments. We read as-is.
    parser.read_string(contents)
    return parser["Service"]


def test_watchdog_unit_file_has_30s() -> None:
    """[Service] section must declare WatchdogSec=30.

    Bumped from 10s after cold-start GPS acquisition was burning the entire
    budget before engine.py reached the main loop. Engine now also pings
    WATCHDOG=1 inside _wait_for_gps_fix; 30s gives belt-and-braces headroom.
    """
    section = _parse_service_section()
    assert section.get("watchdogsec") == "30", (
        f"Expected WatchdogSec=30, got {section.get('watchdogsec')!r}"
    )


def test_service_unit_restart_policy() -> None:
    """[Service] section must have Restart=always and StartLimitIntervalSec=0."""
    section = _parse_service_section()
    assert section.get("restart") == "always", (
        f"Expected Restart=always, got {section.get('restart')!r}"
    )
    assert section.get("startlimitintervalsec") == "0", (
        f"Expected StartLimitIntervalSec=0, got {section.get('startlimitintervalsec')!r}"
    )


def test_service_unit_type_notify() -> None:
    """[Service] section must have Type=notify for sd_notify watchdog petting."""
    section = _parse_service_section()
    assert section.get("type") == "notify", (
        f"Expected Type=notify, got {section.get('type')!r}"
    )
