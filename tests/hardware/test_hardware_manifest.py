"""Unit tests for HardwareManifestConfig YAML round-trip loading."""
from __future__ import annotations

import textwrap

from shitbox.utils.config import load_config

_MINIMAL_HARDWARE_YAML = textwrap.dedent("""\
    hardware:
      devices:
        - role: imu
          bus: i2c-1
          address: 0x6a
          criticality: critical
          description: "LSM6DSOX accel+gyro"
        - role: camera_front
          bus: usb
          path: /dev/camera-front
          criticality: critical
          description: "UGREEN USB webcam (front dashcam)"
        - role: power
          bus: i2c-1
          address: 0x40
          criticality: important
          description: "INA226 power monitor"
        - role: gps
          bus: usb
          path: /dev/gps0
          criticality: important
          description: "U-blox USB GPS via gpsd"
        - role: environment
          bus: i2c-1
          address: 0x77
          criticality: best_effort
          description: "BME680 temperature/humidity/pressure/gas"
        - role: magnetometer
          bus: i2c-1
          address: 0x1c
          criticality: best_effort
          description: "LIS3MDL"
        - role: light
          bus: i2c-1
          address: 0x10
          criticality: best_effort
          description: "VEML7700 ambient light"
        - role: oled
          bus: i2c-1
          address: 0x3c
          criticality: best_effort
          description: "SSD1306 128x64 status display"
        - role: temp_exterior
          bus: 1-wire
          sensor_id: "28-00000024263a"
          criticality: best_effort
          description: "DS18B20 exterior probe"
        - role: temp_engine_bay
          bus: 1-wire
          sensor_id: "28-0000002405b1"
          criticality: best_effort
          description: "DS18B20 engine bay probe"
        - role: camera_cabin
          bus: usb
          path: /dev/camera-cabin
          criticality: best_effort
          description: "Logitech Brio 100 (cabin)"
        - role: audio_mic
          bus: audio
          label: UACDemo
          criticality: best_effort
          description: "USB mic for TTS speaker"
        - role: button
          bus: gpio
          pin: 17
          criticality: best_effort
          description: "Manual capture button"
        - role: display_hdmi
          bus: hdmi
          connector: HDMI-A-1
          criticality: best_effort
          description: "7in kiosk display"
""")


def test_hardware_manifest_loads_all_14_devices(tmp_path):
    """14 hardware devices round-trip correctly through load_config."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_HARDWARE_YAML)
    cfg = load_config(cfg_path)
    assert len(cfg.hardware.devices) == 14


def test_hardware_manifest_device_field_round_trip(tmp_path):
    """IMU device fields all round-trip to the correct values."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_HARDWARE_YAML)
    cfg = load_config(cfg_path)

    imu = next(d for d in cfg.hardware.devices if d.role == "imu")
    assert imu.bus == "i2c-1"
    assert imu.criticality == "critical"
    assert imu.address == 0x6A
    assert imu.description == "LSM6DSOX accel+gyro"


def test_hardware_manifest_absent_block_yields_empty_list(tmp_path):
    """A config with no hardware: key returns empty devices list — no exception."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("app:\n  name: test\n")
    cfg = load_config(cfg_path)
    assert cfg.hardware.devices == []


def test_hardware_manifest_bus_specific_fields(tmp_path):
    """Bus-specific optional fields do not cross-pollinate between device types."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_MINIMAL_HARDWARE_YAML)
    cfg = load_config(cfg_path)

    # USB device has path, not address
    cam = next(d for d in cfg.hardware.devices if d.role == "camera_front")
    assert cam.path == "/dev/camera-front"
    assert cam.address is None

    # 1-Wire device has sensor_id, not path or address
    ext = next(d for d in cfg.hardware.devices if d.role == "temp_exterior")
    assert ext.sensor_id == "28-00000024263a"
    assert ext.path is None
    assert ext.address is None
