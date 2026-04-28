"""rtl_433 subprocess lifecycle + lsusb VID:PID probe.

SPEC-1 (frame ingestion via subprocess), SPEC-10 (hardware manifest probe).
Wave 0 stubs — bodies activate when Plan 28-03 lands probe_usb_vid_pid and
Plan 28-04 lands the TPMSService subprocess wrapper.
"""
from __future__ import annotations

from unittest import mock

import pytest


def test_probe_finds_sdr():
    """SPEC-10: probe_usb_vid_pid returns True when lsusb output contains the ID."""
    try:
        from shitbox.hardware.probes import probe_usb_vid_pid
    except ImportError:
        pytest.skip("Plan 28-03 — probe_usb_vid_pid not yet implemented")
    fake = mock.MagicMock(returncode=0, stdout="Bus 001 Device 005: ID 0bda:2838 Realtek\n")
    with mock.patch("shitbox.hardware.probes.subprocess.run", return_value=fake):
        assert probe_usb_vid_pid("0bda:2838") is True


def test_probe_missing_sdr():
    """SPEC-10: probe_usb_vid_pid returns False when the VID:PID is absent."""
    try:
        from shitbox.hardware.probes import probe_usb_vid_pid
    except ImportError:
        pytest.skip("Plan 28-03 — probe_usb_vid_pid not yet implemented")
    fake = mock.MagicMock(returncode=0, stdout="Bus 001 Device 002: ID 1d6b:0002 Linux\n")
    with mock.patch("shitbox.hardware.probes.subprocess.run", return_value=fake):
        assert probe_usb_vid_pid("0bda:2838") is False


def test_restart_on_exit():
    """SPEC-1+10: TPMSService monitor restarts rtl_433 when the process exits."""
    pytest.skip("Plan 28-04 — TPMSService._monitor_loop not yet implemented")


def test_stderr_drained():
    """SPEC-1: monitor thread drains stderr non-blockingly to avoid pipe-full block."""
    pytest.skip("Plan 28-04 — TPMSService._read_stderr_nonblocking not yet implemented")
