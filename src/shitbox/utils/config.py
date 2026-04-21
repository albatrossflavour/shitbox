"""Configuration loading and validation."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import yaml


@dataclass
class WaypointConfig:
    """A single named waypoint on the rally route."""

    name: str = ""
    day: int = 1
    lat: float = 0.0
    lon: float = 0.0
    leg: str = "rally"  # "rally" counts toward progress; "return" is nav-only (e.g. drive home)


@dataclass
class RouteConfig:
    """Ordered list of waypoints defining the rally route."""

    waypoints: List[WaypointConfig] = field(default_factory=list)


@dataclass
class GPSConfig:
    """GPS sensor configuration (via gpsd)."""

    enabled: bool = True
    host: str = "localhost"
    port: int = 2947  # gpsd default port
    sample_rate_hz: float = 1.0
    location_resolution_interval_seconds: int = 300
    rally_start_lat: float = -16.483831
    rally_start_lon: float = 145.467250
    rally_destination_lat: float = -37.819142
    rally_destination_lon: float = 144.960397
    route: RouteConfig = field(default_factory=RouteConfig)


@dataclass
class LSM6DSOXConfig:
    """LSM6DSOX accel+gyro (replaces MPU6050)."""

    enabled: bool = True
    i2c_bus: int = 1
    address: int = 0x6A
    sample_rate_hz: float = 104.0  # LSM6DSOX Rate.RATE_104_HZ default
    accel_offset_x: float = 0.0   # g, subtracted after unit conversion
    accel_offset_y: float = 0.0
    accel_offset_z: float = 0.0


@dataclass
class LIS3MDLConfig:
    """LIS3MDL magnetometer configuration."""

    enabled: bool = True
    i2c_bus: int = 1
    address: int = 0x1C


@dataclass
class IMUHeadingConfig:
    """IMU heading (complementary filter) collector configuration."""

    enabled: bool = True
    sample_rate_hz: float = 10.0
    complementary_alpha: float = 0.98


@dataclass
class DS18B20ProbeConfig:
    """Single DS18B20 probe config (role + 1-Wire sensor ID)."""

    role: str = ""
    sensor_id: str = ""


@dataclass
class TemperatureConfig:
    """DS18B20 1-Wire config (replaces MCP9808)."""

    enabled: bool = True
    sample_rate_hz: float = 1.0
    probes: List[DS18B20ProbeConfig] = field(default_factory=list)

    @property
    def sensor_ids(self) -> dict:
        """Return {role: sensor_id} dict for DS18B20Collector."""
        return {p.role: p.sensor_id for p in self.probes if p.role and p.sensor_id}


@dataclass
class HardwareDeviceConfig:
    """Single expected device in the hardware manifest."""

    role: str = ""
    bus: str = ""                      # i2c-1 | 1-wire | usb | gpio | hdmi | audio
    criticality: str = "best_effort"   # critical | important | best_effort
    description: str = ""
    # Bus-specific fields (all optional; the right one is set per bus type)
    address: Optional[int] = None      # i2c: 0x6a style
    path: Optional[str] = None         # usb: /dev/camera-front
    sensor_id: Optional[str] = None    # 1-wire: 28-00000024263a
    pin: Optional[int] = None          # gpio: 17
    label: Optional[str] = None        # audio: UACDemo (/proc/asound/cards)
    connector: Optional[str] = None    # hdmi: HDMI-A-1


@dataclass
class HardwareManifestConfig:
    """Hardware manifest: expected devices declared in config and verified at boot."""

    devices: List[HardwareDeviceConfig] = field(default_factory=list)


@dataclass
class LightConfig:
    """VEML7700 ambient light sensor configuration."""

    enabled: bool = True
    sample_rate_hz: float = 1.0
    i2c_bus: int = 1
    address: int = 0x10


@dataclass
class PowerConfig:
    """INA226 power monitor (D-06, ships disabled)."""

    enabled: bool = False
    i2c_bus: int = 1
    address: int = 0x40
    shunt_ohms: float = 0.1
    sample_rate_hz: float = 1.0


@dataclass
class ParticulateConfig:
    """SEN0460 PM2.5 particulate sensor (I2C 0x19)."""

    enabled: bool = True
    i2c_bus: int = 1
    address: int = 0x19
    sample_rate_hz: float = 1.0


@dataclass
class EnvironmentConfig:
    """BME280 environment sensor configuration."""

    enabled: bool = False
    i2c_bus: int = 1
    address: int = 0x77
    sample_rate_hz: float = 1.0


@dataclass
class SensorsConfig:
    """All sensors configuration."""

    gps: GPSConfig = field(default_factory=GPSConfig)
    lsm6dsox: LSM6DSOXConfig = field(default_factory=LSM6DSOXConfig)
    lis3mdl: LIS3MDLConfig = field(default_factory=LIS3MDLConfig)
    imu_heading: IMUHeadingConfig = field(default_factory=IMUHeadingConfig)
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)
    light: LightConfig = field(default_factory=LightConfig)
    power: PowerConfig = field(default_factory=PowerConfig)
    particulate: ParticulateConfig = field(default_factory=ParticulateConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)


@dataclass
class StorageConfig:
    """Local storage configuration."""

    database_path: str = "/var/lib/shitbox/telemetry.db"
    backup_enabled: bool = True
    backup_interval_hours: int = 6
    max_backups: int = 10
    home_lat: float = 0.0
    home_lng: float = 0.0
    home_exclusion_radius_m: float = 2000.0


@dataclass
class MQTTConfig:
    """MQTT sync configuration."""

    enabled: bool = True
    broker_host: str = "mqtt.homelab.local"
    broker_port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "shitbox-car"
    qos: int = 1
    topic_prefix: str = "shitbox"
    reconnect_delay_min: int = 1
    reconnect_delay_max: int = 120


@dataclass
class PrometheusConfig:
    """Prometheus sync configuration."""

    enabled: bool = True
    remote_write_url: str = "http://prometheus.homelab.local:9090/api/v1/write"
    batch_size: int = 1000
    batch_interval_seconds: int = 60


@dataclass
class ConnectivityConfig:
    """Network connectivity check configuration."""

    check_host: str = "8.8.8.8"
    check_port: int = 53
    check_interval_seconds: int = 30
    timeout_seconds: int = 3


@dataclass
class GrafanaConfig:
    """Grafana annotation configuration."""

    enabled: bool = False
    url: str = ""
    username: str = ""
    password_file: str = ""
    video_base_url: str = ""
    timeout_seconds: int = 5


@dataclass
class CaptureSyncConfig:
    """Capture rsync configuration."""

    enabled: bool = False
    remote_dest: str = ""
    rsync_path: str = "/opt/bin/rsync"
    interval_seconds: int = 300


@dataclass
class SyncConfig:
    """Sync services configuration."""

    uplink_enabled: bool = True  # Master switch for all uplink
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    prometheus: PrometheusConfig = field(default_factory=PrometheusConfig)
    connectivity: ConnectivityConfig = field(default_factory=ConnectivityConfig)
    grafana: GrafanaConfig = field(default_factory=GrafanaConfig)
    capture_sync: CaptureSyncConfig = field(default_factory=CaptureSyncConfig)


@dataclass
class HealthConfig:
    """Health monitoring configuration."""

    enabled: bool = True
    report_interval_seconds: int = 60
    temp_warning_celsius: int = 70
    temp_critical_celsius: int = 80
    disk_warning_percent: int = 80
    disk_critical_percent: int = 95


@dataclass
class VideoConfig:
    """Video capture configuration."""

    device: str = "/dev/video0"
    duration_seconds: int = 60
    resolution: str = "1280x720"
    fps: int = 30
    audio_device: str = "default"


@dataclass
class TimelapseConfig:
    """Timelapse image capture configuration."""

    enabled: bool = True
    interval_seconds: int = 60
    min_speed_kmh: float = 5.0
    compile_fps: int = 24


@dataclass
class PipConfig:
    """Secondary (cabin) ring buffer for picture-in-picture composite."""

    enabled: bool = False
    device: str = "/dev/video0"
    input_format: str = "mjpeg"
    resolution: str = "1280x720"
    fps: int = 30
    audio_device: str = ""  # empty = video-only (no audio retry loop)
    buffer_dir: str = "/var/lib/shitbox/video_buffer_pip"
    position: str = "bottom_right"  # bottom_right | bottom_left | top_right | top_left
    scale: float = 0.25
    camera_controls: dict[str, int] = field(default_factory=dict)


@dataclass
class VideoBufferConfig:
    """Video ring buffer configuration for dashcam-style pre-event capture."""

    enabled: bool = True
    device: str = "/dev/video0"
    input_format: str = "mjpeg"
    resolution: str = "1280x720"
    fps: int = 30
    buffer_dir: str = "/var/lib/shitbox/video_buffer"
    segment_seconds: int = 10
    buffer_segments: int = 3
    overlay_enabled: bool = True
    intro_video: str = ""
    camera_controls: dict[str, int] = field(default_factory=dict)
    pip: PipConfig = field(default_factory=PipConfig)


@dataclass
class SpeakerConfig:
    """USB TTS speaker configuration."""

    enabled: bool = False
    model_path: str = "/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
    distance_announce_interval_km: float = 50.0
    volume: int = 75


@dataclass
class CaptureConfig:
    """Manual capture (button + video) configuration."""

    enabled: bool = True
    gpio_pin: int = 17
    debounce_ms: int = 50
    pre_capture_seconds: float = 30.0
    post_capture_seconds: float = 30.0
    captures_dir: str = "/var/lib/shitbox/captures"
    max_capture_age_days: int = 14
    buzzer_enabled: bool = True
    video: VideoConfig = field(default_factory=VideoConfig)
    timelapse: TimelapseConfig = field(default_factory=TimelapseConfig)
    video_buffer: VideoBufferConfig = field(default_factory=VideoBufferConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)


@dataclass
class OLEDConfig:
    """OLED display configuration."""

    enabled: bool = False
    i2c_bus: int = 1
    address: int = 0x3C
    update_interval_seconds: float = 1.0


@dataclass
class DisplayConfig:
    """Display configuration."""

    oled: OLEDConfig = field(default_factory=OLEDConfig)


@dataclass
class DashboardConfig:
    """In-process FastAPI dashboard configuration."""

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    mbtiles_path: str = "/var/lib/shitbox/tiles/rally.mbtiles"
    max_sse_clients: int = 8


@dataclass
class AppConfig:
    """Application configuration."""

    name: str = "shitbox-telemetry"
    log_level: str = "INFO"
    data_dir: str = "/var/lib/shitbox"


@dataclass
class Config:
    """Root configuration object."""

    app: AppConfig = field(default_factory=AppConfig)
    sensors: SensorsConfig = field(default_factory=SensorsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    drivers: List[str] = field(default_factory=list)
    hardware: HardwareManifestConfig = field(default_factory=HardwareManifestConfig)


def _dict_to_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """Recursively convert a dictionary to a dataclass instance."""
    if data is None:
        return cls()

    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}

    for key, value in data.items():
        if key not in field_types:
            continue

        field_type = field_types[key]

        # Handle nested dataclasses
        if hasattr(field_type, "__dataclass_fields__") and isinstance(value, dict):
            kwargs[key] = _dict_to_dataclass(field_type, value)
        else:
            kwargs[key] = value

    return cls(**kwargs)


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from a YAML file.

    Args:
        config_path: Path to config file. If None, searches default locations.

    Returns:
        Config object with all settings.
    """
    search_paths = [
        Path(config_path) if config_path else None,
        Path("config/config.yaml"),
        Path("/etc/shitbox/config.yaml"),
        Path.home() / ".config" / "shitbox" / "config.yaml",
    ]

    config_file = None
    for path in search_paths:
        if path and path.exists():
            config_file = path
            break

    if config_file is None:
        # Return defaults if no config file found
        return Config()

    with open(config_file) as f:
        data = yaml.safe_load(f) or {}

    # Build config from nested dataclasses
    capture_data = data.get("capture", {})
    capture_config = CaptureConfig(
        enabled=capture_data.get("enabled", True),
        gpio_pin=capture_data.get("gpio_pin", 17),
        debounce_ms=capture_data.get("debounce_ms", 50),
        pre_capture_seconds=capture_data.get("pre_capture_seconds", 30.0),
        post_capture_seconds=capture_data.get("post_capture_seconds", 30.0),
        captures_dir=capture_data.get("captures_dir", "/var/lib/shitbox/captures"),
        max_capture_age_days=capture_data.get("max_capture_age_days", 14),
        buzzer_enabled=capture_data.get("buzzer_enabled", True),
        video=_dict_to_dataclass(VideoConfig, capture_data.get("video", {})),
        timelapse=_dict_to_dataclass(TimelapseConfig, capture_data.get("timelapse", {})),
        video_buffer=_dict_to_dataclass(
            VideoBufferConfig, capture_data.get("video_buffer", {})
        ),
        speaker=_dict_to_dataclass(SpeakerConfig, capture_data.get("speaker", {})),
    )

    gps_dict = data.get("sensors", {}).get("gps", {})
    gps_config = _dict_to_dataclass(GPSConfig, gps_dict)
    # Explicitly convert waypoints list — _dict_to_dataclass does not handle
    # lists of dataclasses, so we do it here.
    route_data = gps_dict.get("route", {}) if isinstance(gps_dict, dict) else {}
    waypoints = [
        WaypointConfig(**w)
        for w in (route_data.get("waypoints", []) if isinstance(route_data, dict) else [])
    ]
    gps_config.route = RouteConfig(waypoints=waypoints)

    # Explicitly convert DS18B20 probes list — same reason as waypoints above.
    temp_dict = data.get("sensors", {}).get("temperature", {})
    temp_config = _dict_to_dataclass(TemperatureConfig, temp_dict)
    probes_data = temp_dict.get("probes", []) if isinstance(temp_dict, dict) else []
    temp_config.probes = [
        DS18B20ProbeConfig(**p) for p in (probes_data if isinstance(probes_data, list) else [])
    ]

    # Explicitly convert hardware manifest devices list — same pattern as DS18B20 probes.
    # Absent or malformed hardware: block yields an empty list (D-04: boot never refuses).
    hw_dict = data.get("hardware", {})
    hw_config = HardwareManifestConfig()
    devices_data = hw_dict.get("devices", []) if isinstance(hw_dict, dict) else []
    hw_config.devices = [
        HardwareDeviceConfig(**d) for d in (devices_data if isinstance(devices_data, list) else [])
    ]

    return Config(
        app=_dict_to_dataclass(AppConfig, data.get("app", {})),
        sensors=SensorsConfig(
            gps=gps_config,
            lsm6dsox=_dict_to_dataclass(
                LSM6DSOXConfig, data.get("sensors", {}).get("lsm6dsox", {})
            ),
            lis3mdl=_dict_to_dataclass(
                LIS3MDLConfig, data.get("sensors", {}).get("lis3mdl", {})
            ),
            imu_heading=_dict_to_dataclass(
                IMUHeadingConfig, data.get("sensors", {}).get("imu_heading", {})
            ),
            temperature=temp_config,
            power=_dict_to_dataclass(
                PowerConfig, data.get("sensors", {}).get("power", {})
            ),
            particulate=_dict_to_dataclass(
                ParticulateConfig, data.get("sensors", {}).get("particulate", {})
            ),
            light=_dict_to_dataclass(
                LightConfig, data.get("sensors", {}).get("light", {})
            ),
            environment=_dict_to_dataclass(
                EnvironmentConfig, data.get("sensors", {}).get("environment", {})
            ),
        ),
        storage=_dict_to_dataclass(StorageConfig, data.get("storage", {})),
        sync=SyncConfig(
            uplink_enabled=data.get("sync", {}).get("uplink_enabled", True),
            mqtt=_dict_to_dataclass(MQTTConfig, data.get("sync", {}).get("mqtt", {})),
            prometheus=_dict_to_dataclass(
                PrometheusConfig, data.get("sync", {}).get("prometheus", {})
            ),
            connectivity=_dict_to_dataclass(
                ConnectivityConfig, data.get("sync", {}).get("connectivity", {})
            ),
            grafana=_dict_to_dataclass(
                GrafanaConfig, data.get("sync", {}).get("grafana", {})
            ),
            capture_sync=_dict_to_dataclass(
                CaptureSyncConfig, data.get("sync", {}).get("capture_sync", {})
            ),
        ),
        health=_dict_to_dataclass(HealthConfig, data.get("health", {})),
        capture=capture_config,
        display=DisplayConfig(
            oled=_dict_to_dataclass(
                OLEDConfig, data.get("display", {}).get("oled", {})
            ),
        ),
        dashboard=_dict_to_dataclass(DashboardConfig, data.get("dashboard", {})),
        drivers=data.get("drivers", []),
        hardware=hw_config,
    )
