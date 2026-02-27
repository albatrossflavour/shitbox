"""Configuration loading and validation."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml


@dataclass
class WaypointConfig:
    """A single named waypoint on the rally route."""

    name: str = ""
    day: int = 1
    lat: float = 0.0
    lon: float = 0.0


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
class IMUConfig:
    """IMU sensor configuration."""

    enabled: bool = True
    i2c_bus: int = 1
    address: int = 0x68
    sample_rate_hz: float = 10.0
    accel_range: int = 4  # +/- g
    gyro_range: int = 500  # +/- deg/s


@dataclass
class TemperatureConfig:
    """Temperature sensor configuration."""

    enabled: bool = False
    i2c_bus: int = 1
    address: int = 0x18
    sample_rate_hz: float = 0.1


@dataclass
class PowerConfig:
    """INA219 power sensor configuration."""

    enabled: bool = False
    i2c_bus: int = 1
    address: int = 0x40
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
    imu: IMUConfig = field(default_factory=IMUConfig)
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)
    power: PowerConfig = field(default_factory=PowerConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)


@dataclass
class StorageConfig:
    """Local storage configuration."""

    database_path: str = "/var/lib/shitbox/telemetry.db"
    backup_enabled: bool = True
    backup_interval_hours: int = 6
    max_backups: int = 10


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
    api_token: str = ""
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


@dataclass
class VideoBufferConfig:
    """Video ring buffer configuration for dashcam-style pre-event capture."""

    enabled: bool = True
    buffer_dir: str = "/var/lib/shitbox/video_buffer"
    segment_seconds: int = 10
    buffer_segments: int = 5
    overlay_enabled: bool = True
    intro_video: str = ""


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

    return Config(
        app=_dict_to_dataclass(AppConfig, data.get("app", {})),
        sensors=SensorsConfig(
            gps=gps_config,
            imu=_dict_to_dataclass(IMUConfig, data.get("sensors", {}).get("imu", {})),
            temperature=_dict_to_dataclass(
                TemperatureConfig, data.get("sensors", {}).get("temperature", {})
            ),
            power=_dict_to_dataclass(
                PowerConfig, data.get("sensors", {}).get("power", {})
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
    )
