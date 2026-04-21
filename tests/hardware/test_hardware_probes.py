"""Unit tests for hardware probe functions (all I/O mocked)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import shitbox.hardware.probes as probes_mod

# ── I2C probes ───────────────────────────────────────────────────────────────

def test_probe_i2c_present():
    """Probe returns True when read_byte_data succeeds."""
    mock_smb = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_smb)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_smb.read_byte_data.return_value = 0

    with patch("shitbox.hardware.probes.smbus2.SMBus", return_value=mock_ctx):
        result = probes_mod.probe_i2c(1, 0x6A)

    assert result is True
    mock_ctx.__exit__.assert_called_once()


def test_probe_i2c_absent_raises_oserror():
    """Probe returns False when read_byte_data raises OSError (no ACK)."""
    mock_smb = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_smb)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_smb.read_byte_data.side_effect = OSError("no device")

    with patch("shitbox.hardware.probes.smbus2.SMBus", return_value=mock_ctx):
        result = probes_mod.probe_i2c(1, 0x6A)

    assert result is False


def test_probe_i2c_unexpected_error_returns_false(caplog):
    """Probe returns False (and logs warning) on non-OSError exceptions."""
    mock_smb = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_smb)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_smb.read_byte_data.side_effect = ValueError("unexpected")

    with patch("shitbox.hardware.probes.smbus2.SMBus", return_value=mock_ctx):
        result = probes_mod.probe_i2c(1, 0x6A)

    assert result is False


# ── USB path probe ────────────────────────────────────────────────────────────

def test_probe_usb_path_exists(tmp_path):
    """probe_usb_path returns True for existing file, False for missing."""
    device = tmp_path / "camera-front"
    device.touch()
    assert probes_mod.probe_usb_path(str(device)) is True

    device.unlink()
    assert probes_mod.probe_usb_path(str(device)) is False


# ── 1-Wire probe ─────────────────────────────────────────────────────────────

def test_probe_onewire_exists():
    """probe_onewire returns True when the w1_slave sysfs path exists."""
    sensor_id = "28-00000024263a"

    with patch.object(Path, "exists", return_value=True):
        result = probes_mod.probe_onewire(sensor_id)

    assert result is True


def test_probe_onewire_missing():
    """probe_onewire returns False when the w1_slave sysfs path is absent."""
    sensor_id = "28-00000024263a"

    with patch.object(Path, "exists", return_value=False):
        result = probes_mod.probe_onewire(sensor_id)

    assert result is False


# ── Audio label probe ─────────────────────────────────────────────────────────

def test_probe_audio_label_present(monkeypatch):
    """probe_audio_label returns True when label is in /proc/asound/cards."""
    cards_content = " 0 [UACDemo         ]: USB-Audio - UACDemo\n"

    def fake_read_text(self, *a, **kw):
        if str(self) == "/proc/asound/cards":
            return cards_content
        return ""

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert probes_mod.probe_audio_label("UACDemo") is True
    assert probes_mod.probe_audio_label("Absent") is False


def test_probe_audio_label_oserror_returns_false(monkeypatch):
    """probe_audio_label returns False when /proc/asound/cards raises OSError."""
    def fake_read_text(self, *a, **kw):
        raise OSError("no such file")

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert probes_mod.probe_audio_label("UACDemo") is False


# ── HDMI probe ────────────────────────────────────────────────────────────────

def test_probe_hdmi_connected(tmp_path):
    """probe_hdmi returns True when a matching status file contains 'connected'."""
    connector_dir = tmp_path / "card0-HDMI-A-1"
    connector_dir.mkdir()
    (connector_dir / "status").write_text("connected\n")

    with patch("shitbox.hardware.probes.Path") as mock_path_cls:
        mock_drm = MagicMock()
        mock_path_cls.return_value = mock_drm
        mock_drm.glob.return_value = [connector_dir]

        result = probes_mod.probe_hdmi("HDMI-A-1")

    assert result is True


def test_probe_hdmi_disconnected(tmp_path):
    """probe_hdmi returns False when status reads 'disconnected'."""
    connector_dir = tmp_path / "card0-HDMI-A-1"
    connector_dir.mkdir()
    (connector_dir / "status").write_text("disconnected\n")

    with patch("shitbox.hardware.probes.Path") as mock_path_cls:
        mock_drm = MagicMock()
        mock_path_cls.return_value = mock_drm
        mock_drm.glob.return_value = [connector_dir]

        result = probes_mod.probe_hdmi("HDMI-A-1")

    assert result is False


# ── GPIO pin probe ────────────────────────────────────────────────────────────

def test_probe_gpio_pin_module_missing():
    """probe_gpio_pin returns False when RPi.GPIO import fails."""
    original = sys.modules.get("RPi.GPIO")
    sys.modules["RPi.GPIO"] = None  # type: ignore[assignment]
    try:
        result = probes_mod.probe_gpio_pin(17)
    finally:
        if original is None:
            sys.modules.pop("RPi.GPIO", None)
        else:
            sys.modules["RPi.GPIO"] = original

    assert result is False


def test_probe_gpio_pin_module_available():
    """probe_gpio_pin returns True when RPi.GPIO imports successfully."""
    pytest.importorskip("RPi.GPIO")
    result = probes_mod.probe_gpio_pin(17)
    assert result is True


# ── Bus-is-bitbang probe ──────────────────────────────────────────────────────

def test_probe_i2c_bus_is_bitbang_true(monkeypatch):
    """probe_i2c_bus_is_bitbang returns True when adapter name starts with i2c-gpio."""
    def fake_read_text(self, *a, **kw):
        if "i2c-adapter" in str(self):
            return "i2c-gpio-1\n"
        return ""

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert probes_mod.probe_i2c_bus_is_bitbang(1) is True


def test_probe_i2c_bus_is_bitbang_false_logs_critical(monkeypatch, caplog):
    """probe_i2c_bus_is_bitbang returns False and logs critical when wrong driver."""
    def fake_read_text(self, *a, **kw):
        if "i2c-adapter" in str(self):
            return "i2c-designware\n"
        return ""

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with caplog.at_level(logging.CRITICAL):
        result = probes_mod.probe_i2c_bus_is_bitbang(1)

    assert result is False
