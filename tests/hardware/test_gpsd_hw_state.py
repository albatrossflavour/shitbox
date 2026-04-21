"""Tests for GpsdClient hw_state.report_present hook (Phase 21 follow-up).

The GpsdClient caches TPV/SKY frames coming off the gpsd socket. When a TPV
is successfully decoded and cached, the device is effectively 'present' --
the HardwareSupervisor probe can't detect this directly (gpsd doesn't expose
USB-path state over the JSON stream), so the client itself reports PRESENT
via hw_state. That keeps the dashboard HARDWARE panel honest for the gps
role.
"""
from __future__ import annotations

import pytest

from shitbox.gpsd_client import GpsdClient
from shitbox.hardware import state as hw_state


def test_handle_line_tpv_reports_gps_present():
    hw_state.initialise({"gps": "important"})
    assert hw_state.snapshot()["gps"].state == hw_state.DeviceState.MISSING

    client = GpsdClient()
    client._handle_line(
        b'{"class":"TPV","mode":3,"lat":-27.47,"lon":153.03,"alt":25.0}'
    )

    assert hw_state.snapshot()["gps"].state == hw_state.DeviceState.PRESENT


def test_handle_line_sky_does_not_report_present():
    """SKY frames carry satellite counts only -- no position fix. Don't treat
    them as presence. The supervisor/USB probe owns 'device attached'; we only
    report on a real TPV.
    """
    hw_state.initialise({"gps": "important"})
    client = GpsdClient()
    client._handle_line(b'{"class":"SKY","satellites":[]}')
    assert hw_state.snapshot()["gps"].state == hw_state.DeviceState.MISSING


def test_handle_line_malformed_json_does_not_raise_or_report():
    hw_state.initialise({"gps": "important"})
    client = GpsdClient()
    client._handle_line(b"not json at all")
    client._handle_line(b"")
    assert hw_state.snapshot()["gps"].state == hw_state.DeviceState.MISSING


def test_empty_role_disables_reporting():
    """role='' -> no-op. Keeps the client usable from tests/CLI without
    polluting hw_state."""
    hw_state.initialise({"gps": "important"})
    client = GpsdClient(role="")
    client._handle_line(b'{"class":"TPV","mode":3,"lat":0,"lon":0}')
    assert hw_state.snapshot()["gps"].state == hw_state.DeviceState.MISSING


def test_report_no_op_when_role_not_in_manifest():
    """If hw_state has not been initialised with 'gps' (dev env, test env),
    report_present is a harmless no-op."""
    hw_state.clear_state()
    client = GpsdClient()
    client._handle_line(b'{"class":"TPV","mode":3,"lat":0,"lon":0}')
    assert hw_state.snapshot() == {}


@pytest.mark.parametrize("custom_role", ["gps_primary", "external_gps"])
def test_custom_role_kwarg(custom_role: str):
    hw_state.initialise({custom_role: "best_effort"})
    client = GpsdClient(role=custom_role)
    client._handle_line(b'{"class":"TPV","mode":3,"lat":0,"lon":0}')
    assert hw_state.snapshot()[custom_role].state == hw_state.DeviceState.PRESENT
