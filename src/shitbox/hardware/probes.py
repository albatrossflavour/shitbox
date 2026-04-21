"""Per-bus hardware probe functions.

Each probe is a single-shot boolean check — no state, no background threads.
Returns True if the device is present and responding, False otherwise.

All probes are safe to call from any thread. They open and close resources
within the call (no held handles).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import smbus2

from shitbox.utils.logging import get_logger

log = get_logger(__name__)


def probe_i2c(bus: int, address: int) -> bool:
    """Return True if a device responds at (bus, address).

    Reads a single byte from register 0x00. Any successful read confirms a
    device ACKed. OSError means no ACK → absent. The SMBus handle is closed
    in the ``with`` block (Pitfall 5 — do not hold the bus open).
    """
    try:
        with smbus2.SMBus(bus) as smb:
            smb.read_byte_data(address, 0x00)
        return True
    except OSError:
        return False
    except Exception as e:
        log.warning("i2c_probe_unexpected_error", bus=bus, address=hex(address), error=str(e))
        return False


def probe_usb_path(path: str) -> bool:
    """Return True if the USB device node / symlink exists."""
    return os.path.exists(path)


def probe_onewire(sensor_id: str) -> bool:
    """Return True if the DS18B20 slave file is present.

    sensor_id is the bare kernel ID (e.g. '28-00000024263a').
    """
    return Path(f"/sys/bus/w1/devices/{sensor_id}/w1_slave").exists()


def probe_audio_label(label: str) -> bool:
    """Return True if the given label appears in /proc/asound/cards."""
    try:
        return label in Path("/proc/asound/cards").read_text()
    except OSError:
        return False


def probe_hdmi(connector: str) -> bool:
    """Return True if the named HDMI connector reports 'connected'.

    connector: e.g. 'HDMI-A-1' (matches /sys/class/drm/*HDMI-A-1*/status).
    """
    try:
        for path in Path("/sys/class/drm").glob(f"*{connector}"):
            status = path / "status"
            try:
                if status.read_text().strip() == "connected":
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def probe_gpio_pin(pin: int) -> bool:  # noqa: ARG001
    """Return True if RPi.GPIO (or rpi-lgpio shim) is importable.

    The pin arg is accepted for manifest dispatch symmetry and future extension;
    the current check is module availability, matching the GPIO_AVAILABLE flag
    pattern in capture/button.py.
    """
    try:
        import RPi.GPIO  # noqa: F401
        return True
    except ImportError:
        return False
    except Exception:
        return False


def probe_i2c_bus_is_bitbang(bus: int) -> bool:
    """Return True if the I2C adapter is the bit-bang (i2c-gpio) driver.

    Reads /sys/class/i2c-adapter/i2c-{bus}/name and checks it starts with
    'i2c-gpio'. Logs critical when it does not — this is the same failure mode
    that caused a 3-day diagnosis in April 2026 (STATE.md out-of-band note).
    """
    name: Optional[str] = None
    try:
        name = Path(f"/sys/class/i2c-adapter/i2c-{bus}/name").read_text().strip()
        if name.startswith("i2c-gpio"):
            return True
    except OSError:
        pass
    log.critical(
        "hw_manifest_bus_check_failed",
        bus=bus,
        expected="i2c-gpio",
        got=name or "",
    )
    return False
