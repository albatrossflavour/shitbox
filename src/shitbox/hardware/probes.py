"""Per-bus hardware probe functions.

Each probe is a single-shot boolean check — no state, no background threads.
Returns True if the device is present and responding, False otherwise.

All probes are safe to call from any thread. They open and close resources
within the call (no held handles).
"""
from __future__ import annotations

import os
import subprocess
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


def probe_usb_vid_pid(vid_pid: str) -> bool:
    """Return True if a USB device with the given VID:PID is enumerated.

    `vid_pid` is the lowercase "VVVV:PPPP" hex form (e.g. "0bda:2838"
    for the RTL2832U + R820T2 chipset family). Multiple matches return
    True — we don't care which physical port. Used by the TPMS hardware
    manifest entry (`bus: usb_vid_pid`, Phase 28 SPEC-10).

    Returns False on any failure (lsusb missing, timeout, non-zero exit)
    so the supervisor reports MISSING and continues. The daemon never
    refuses to boot.
    """
    try:
        result = subprocess.run(
            ["lsusb"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except FileNotFoundError:
        log.warning("lsusb_not_found", hint="apt install usbutils")
        return False
    except subprocess.TimeoutExpired:
        log.warning("lsusb_timeout", vid_pid=vid_pid)
        return False
    if result.returncode != 0:
        log.warning("lsusb_failed", returncode=result.returncode)
        return False
    # lsusb format: "Bus 001 Device 005: ID 0bda:2838 Realtek Semiconductor Corp."
    return f"ID {vid_pid.lower()}" in result.stdout


def probe_hdmi(connector: str) -> bool:
    """Return True if a matching HDMI connector is attached and driving output.

    connector:
      - Explicit name, e.g. 'HDMI-A-1' — matches /sys/class/drm/*HDMI-A-1.
      - Wildcard pattern, e.g. 'HDMI-A-*' — port-agnostic, matches any HDMI-A-N.
      - Empty string / None / sentinel ('*', 'any', 'auto') — treated as
        port-agnostic (equivalent to 'HDMI-A-*'). Survives cable swaps between
        HDMI-A-1 and HDMI-A-2 without a config edit.

    Status file values come from the kernel DRM driver. 'connected' is the
    explicit hot-plug-detected case. 'unknown' is common on Pi 5 once the
    framebuffer is driving a monitor whose EDID has already been read and
    cached (hot-plug no longer fires) -- treating it as missing was wrong,
    hence the check is inverted: anything *other than* 'disconnected' counts
    as present, provided the connector node exists at all.
    """
    spec = (connector or "").strip()
    # Port-agnostic sentinels — match ANY HDMI-A-N. Anchored to HDMI-A
    # explicitly so an empty connector spec doesn't accidentally glob DP/eDP.
    if spec.lower() in ("", "*", "any", "auto"):
        pattern = "*HDMI-A-*"
    else:
        pattern = f"*{spec}"

    try:
        matches = list(Path("/sys/class/drm").glob(pattern))
    except OSError:
        return False
    if not matches:
        return False
    for path in matches:
        status = path / "status"
        try:
            value = status.read_text().strip().lower()
        except OSError:
            continue
        if value and value != "disconnected":
            return True
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
    """Return True if the I2C adapter is a known-good driver.

    Accepts i2c-gpio (bit-bang) and Synopsys DesignWare (Pi 5 hardware I2C).
    Logs critical for anything else — unexpected driver is the failure mode that
    caused a 3-day diagnosis in April 2026 (STATE.md out-of-band note).

    Sysfs path: /sys/bus/i2c/devices/i2c-{bus}/name (not /sys/class/i2c-adapter
    which does not exist on Pi 5 kernels).
    """
    name: Optional[str] = None
    try:
        name = Path(f"/sys/bus/i2c/devices/i2c-{bus}/name").read_text().strip()
        if name.startswith("i2c-gpio") or name.startswith("Synopsys DesignWare"):
            return True
    except OSError:
        pass
    log.critical(
        "hw_manifest_bus_check_failed",
        bus=bus,
        expected="i2c-gpio or Synopsys DesignWare",
        got=name or "",
    )
    return False
