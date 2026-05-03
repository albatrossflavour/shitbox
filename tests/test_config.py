"""Tests for config loading."""
from __future__ import annotations

from shitbox.utils.config import load_config


def test_load_config_drivers_list(tmp_path):
    yaml_text = "drivers:\n  - Tony\n  - Smithy\n  - Nav\n"
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml_text)
    cfg = load_config(cfg_path)
    assert cfg.drivers == ["Tony", "Smithy", "Nav"]


def test_full_config_roundtrip_includes_hardware():
    """Production config/config.yaml loads 16 hardware devices correctly (HW-01).

    Phase 28 added tpms_radio; S02 added audio_cabin_mic (Blue Snowball).
    """
    cfg = load_config("config/config.yaml")
    assert len(cfg.hardware.devices) == 16

    # Spot-check: IMU must be critical with the correct I2C address
    imu_devices = [d for d in cfg.hardware.devices if d.role == "imu"]
    assert len(imu_devices) == 1
    imu = imu_devices[0]
    assert imu.criticality == "critical"
    assert imu.address == 0x6A
