"""Unit tests for the systemd shitbox-telemetry.service unit file.

Validates that the service unit is correctly hardened for unlimited
restarts and a 10-second watchdog timeout.
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


def test_watchdog_unit_file_has_10s() -> None:
    """[Service] section must declare WatchdogSec=10."""
    section = _parse_service_section()
    assert section.get("watchdogsec") == "10", (
        f"Expected WatchdogSec=10, got {section.get('watchdogsec')!r}"
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
