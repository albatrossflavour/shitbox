"""Unified Shitbox Telemetry Engine.

Combines high-rate event detection with low-rate telemetry logging.

High-rate path (100 Hz):
- IMU sampling → ring buffer → event detection → burst storage

Low-rate path (1 Hz):
- GPS, IMU snapshot, temperature → SQLite → MQTT → Prometheus batch sync
"""

import math
import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

from shitbox.capture import buzzer, overlay, speaker
from shitbox.capture.button import ButtonHandler
from shitbox.capture.ring_buffer import VideoRingBuffer
from shitbox.capture.title_card import TitleCardRenderer
from shitbox.capture.video import VideoRecorder
from shitbox.collectors.imu_heading import IMUHeadingCollector
from shitbox.collectors.light import VEML7700Collector
from shitbox.collectors.particulate import SEN0460Collector
from shitbox.collectors.power import INA226Collector
from shitbox.collectors.temperature import DS18B20Collector
from shitbox.dashboard import driver_state, gps_state
from shitbox.dashboard.server import DashboardServer, build_dashboard_server
from shitbox.dashboard.snapshot import update_snapshot
from shitbox.dashboard.sse import push_event as dashboard_push_event
from shitbox.display.oled import OLEDDisplayService
from shitbox.events.detector import DetectorConfig, Event, EventDetector, EventType
from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.events.sampler import HighRateSampler
from shitbox.events.storage import EventStorage
from shitbox.gpsd_client import GpsdClient
from shitbox.hardware import probes
from shitbox.hardware import state as hw_state
from shitbox.hardware.supervisor import HardwareSupervisor
from shitbox.health.health_collector import HealthCollector
from shitbox.health.thermal_monitor import ThermalMonitorService
from shitbox.storage.database import Database
from shitbox.storage.driver import DriverStorage
from shitbox.storage.logbook import LogbookStorage
from shitbox.storage.models import Reading, SensorType
from shitbox.storage.route import RouteStorage
from shitbox.sync.batch_sync import BatchSyncService
from shitbox.sync.boot_recovery import BootRecoveryService, detect_unclean_shutdown
from shitbox.sync.capture_sync import CaptureSyncService
from shitbox.sync.connection import ConnectionMonitor
from shitbox.sync.grafana import GrafanaAnnotator
from shitbox.sync.mqtt_publisher import MQTTPublisher
from shitbox.sync.timelapse_compiler import TimelapseCompiler
from shitbox.utils.config import (
    CaptureSyncConfig,
    Config,
    GrafanaConfig,
    HardwareManifestConfig,
    IMUHeadingConfig,
    LightConfig,
    OLEDConfig,
    ParticulateConfig,
    PowerConfig,
    TemperatureConfig,
    load_config,
)
from shitbox.utils.logging import get_logger, setup_logging

log = get_logger(__name__)

# Trip tracking constants
TRIP_PERSIST_INTERVAL_S = 60.0
AEST_OFFSET = timedelta(hours=10)


def _current_aest_date() -> str:
    """Return today's date string in AEST (UTC+10), e.g. '2026-02-27'."""
    return (datetime.now(timezone.utc) + AEST_OFFSET).strftime("%Y-%m-%d")


@dataclass
class EngineConfig:
    """Configuration for the unified engine."""

    # High-rate IMU sampling (LSM6DSOX via circuitpython)
    # 22-07 retarget: 104.0 -> 25.0 Hz; matches LSM6DSOXConfig and config.yaml defaults.
    imu_sample_rate_hz: float = 25.0
    ring_buffer_seconds: float = 30.0
    accel_offset_x: float = 0.0
    accel_offset_y: float = 0.0
    accel_offset_z: float = 0.0

    # TCA4307 EN pin for software bus-recovery (None = pin not wired).
    # See sensors.tca4307 in config.yaml and the open thread in the project doc.
    tca_en_gpio: Optional[int] = None
    tca_en_pulse_low_ms: int = 10

    # Auto-zero (thermal drift compensation) — IMU-05, IMU-06.
    # Field names are authoritative per REQUIREMENTS.md IMU-05.
    auto_zero_enabled: bool = True
    auto_zero_stationary_kmh: float = 1.0   # speed gate; GPS fix also required
    auto_zero_window_seconds: float = 30.0  # window length; pulled from ring buffer
    auto_zero_tolerance_g: float = 0.05     # max |new-current| per axis, post-bootstrap
    auto_zero_motion_reject_g: float = 0.2  # per-sample raw combined-g reject
    auto_zero_motion_stddev_g: float = 0.20  # per-axis window stddev reject
    auto_zero_max_abs_g: float = 0.5        # absolute offset plausibility cap

    # Low-rate telemetry
    telemetry_interval_seconds: float = 1.0
    gps_enabled: bool = True
    gps_host: str = "localhost"
    gps_port: int = 2947
    environment_enabled: bool = False
    environment_i2c_address: int = 0x77

    # v2 sensor configs (phase 11)
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)
    light: LightConfig = field(default_factory=LightConfig)
    power: PowerConfig = field(default_factory=PowerConfig)
    particulate: ParticulateConfig = field(default_factory=ParticulateConfig)
    imu_heading: IMUHeadingConfig = field(default_factory=IMUHeadingConfig)

    # Event detection
    detector: DetectorConfig = field(default_factory=DetectorConfig)

    # Event storage
    events_dir: str = "/var/lib/shitbox/events"
    max_event_age_days: int = 14
    max_event_storage_mb: int = 500

    # Periodic data-deletion cleanup (events + capture videos). Disabled by
    # default — the 14-day age-out would silently nuke saved events and
    # videos we want to keep on the live site indefinitely. Re-enable once
    # a retention strategy that protects the keepers is in place.
    cleanup_old_data_enabled: bool = False

    # SQLite storage
    database_path: str = "/var/lib/shitbox/telemetry.db"
    home_lat: float = 0.0
    home_lng: float = 0.0
    home_exclusion_radius_m: float = 2000.0

    # MQTT
    mqtt_enabled: bool = True
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic_prefix: str = "shitbox"

    # Prometheus batch sync
    prometheus_enabled: bool = True
    prometheus_remote_write_url: str = ""
    prometheus_batch_size: int = 1000
    prometheus_batch_interval_seconds: int = 60

    # Connectivity
    connectivity_check_host: str = "192.168.8.21"
    connectivity_check_port: int = 9090
    connectivity_check_interval_seconds: int = 30

    # Uplink master switch
    uplink_enabled: bool = True

    # Manual capture (button + video)
    capture_enabled: bool = True
    buzzer_enabled: bool = True
    capture_gpio_pin: int = 17
    capture_debounce_ms: int = 50
    capture_pre_seconds: float = 30.0
    capture_post_seconds: float = 30.0
    capture_video_device: str = "/dev/video0"
    capture_video_duration: int = 60
    capture_video_resolution: str = "1280x720"
    capture_video_fps: int = 30
    capture_audio_device: str = "default"
    captures_dir: str = "/var/lib/shitbox/captures"
    max_capture_age_days: int = 14

    # Timelapse
    timelapse_enabled: bool = True
    timelapse_interval_seconds: int = 60
    timelapse_min_speed_kmh: float = 5.0
    timelapse_compile_fps: int = 24

    # Video ring buffer (primary)
    video_buffer_enabled: bool = True
    video_buffer_device: str = "/dev/video0"
    video_buffer_input_format: str = "mjpeg"
    video_buffer_resolution: str = "1280x720"
    video_buffer_fps: int = 30
    video_buffer_dir: str = "/var/lib/shitbox/video_buffer"
    video_buffer_segment_seconds: int = 10
    video_buffer_segments: int = 5
    overlay_enabled: bool = True
    video_buffer_intro_video: str = ""
    video_buffer_camera_controls: dict[str, int] = field(
        default_factory=dict,
    )

    # Video ring buffer (PIP / cabin cam)
    video_buffer_pip_enabled: bool = False
    video_buffer_pip_device: str = "/dev/video0"
    video_buffer_pip_input_format: str = "mjpeg"
    video_buffer_pip_resolution: str = "1280x720"
    video_buffer_pip_fps: int = 30
    video_buffer_pip_audio_device: str = ""
    video_buffer_pip_dir: str = "/var/lib/shitbox/video_buffer_pip"
    video_buffer_pip_position: str = "bottom_right"
    video_buffer_pip_scale: float = 0.25
    video_buffer_pip_camera_controls: dict[str, int] = field(
        default_factory=dict,
    )

    # Grafana annotations
    grafana_enabled: bool = False
    grafana_url: str = ""
    grafana_username: str = ""
    grafana_password_file: str = ""
    grafana_video_base_url: str = ""
    grafana_timeout_seconds: int = 5

    # Capture sync (rsync to NAS)
    capture_sync_enabled: bool = False
    capture_sync_remote_dest: str = ""
    capture_sync_rsync_path: str = "/opt/bin/rsync"
    capture_sync_interval_seconds: int = 300

    # TPMS service (Phase 28 — rtl_433 wrapper). Defaults match TpmsConfig
    # so a missing tpms: block in YAML doesn't break engine load.
    tpms_enabled: bool = False
    tpms_rtl433_protocol_id: int = 156
    tpms_rf_frequency_hz: int = 433920000
    tpms_rf_gain_db: int = 30
    tpms_pressure_correction_factor: float = 2.45
    tpms_low_pressure_yellow_psi: float = 28.0
    tpms_low_pressure_red_psi: float = 25.0
    tpms_leak_window_seconds: float = 60.0
    tpms_leak_drop_psi: float = 5.0
    tpms_stale_timeout_seconds: float = 300.0
    tpms_sustain_required: int = 2
    tpms_usb_vid_pid: str = "0bda:2838"
    tpms_sensor_map: Dict[str, str] = field(default_factory=dict)

    # Location resolution
    location_resolution_interval_seconds: int = 300

    # Rally coordinates
    rally_start_lat: float = -16.483831
    rally_start_lon: float = 145.467250
    rally_destination_lat: float = -37.819142
    rally_destination_lon: float = 144.960397

    # OLED display
    oled_enabled: bool = False
    oled_i2c_bus: int = 1
    oled_i2c_address: int = 0x3C
    oled_update_interval: float = 1.0

    # Speaker (USB TTS)
    speaker_enabled: bool = False
    speaker_model_path: str = "/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
    speaker_distance_announce_interval_km: float = 50.0
    speaker_volume: int = 75

    # Title-card slate (phase 26)
    title_card_enabled: bool = True
    title_card_duration_seconds: float = 3.0
    title_card_show_driver: bool = True
    title_card_whimsy_lines: list[str] = field(default_factory=list)

    # Route waypoints (WaypointConfig objects loaded from YAML)
    route_waypoints: list = field(default_factory=list)

    # Live dashboard (in-process FastAPI)
    dashboard_enabled: bool = False
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080
    dashboard_mbtiles_path: str = "/var/lib/shitbox/tiles/rally.mbtiles"

    # Driver roster (from config.drivers)
    drivers: list = field(default_factory=list)

    # Hardware manifest (from config.hardware — passed through for supervisor wiring)
    hardware: HardwareManifestConfig = field(default_factory=HardwareManifestConfig)

    @classmethod
    def from_yaml_config(cls, config: Config) -> "EngineConfig":
        """Create EngineConfig from the existing YAML config structure."""
        return cls(
            # IMU settings (LSM6DSOX — no i2c_bus/address params, circuitpython handles discovery)
            accel_offset_x=config.sensors.lsm6dsox.accel_offset_x,
            accel_offset_y=config.sensors.lsm6dsox.accel_offset_y,
            accel_offset_z=config.sensors.lsm6dsox.accel_offset_z,
            imu_sample_rate_hz=config.sensors.lsm6dsox.sample_rate_hz,
            # TCA4307 EN-pin recovery (None until wired)
            tca_en_gpio=config.sensors.tca4307.en_gpio,
            tca_en_pulse_low_ms=config.sensors.tca4307.pulse_low_ms,
            # Auto-zero (IMU-05, IMU-06) — 1:1 pass-through from LSM6DSOXConfig
            auto_zero_enabled=config.sensors.lsm6dsox.auto_zero_enabled,
            auto_zero_stationary_kmh=config.sensors.lsm6dsox.auto_zero_stationary_kmh,
            auto_zero_window_seconds=config.sensors.lsm6dsox.auto_zero_window_seconds,
            auto_zero_tolerance_g=config.sensors.lsm6dsox.auto_zero_tolerance_g,
            auto_zero_motion_reject_g=config.sensors.lsm6dsox.auto_zero_motion_reject_g,
            auto_zero_motion_stddev_g=config.sensors.lsm6dsox.auto_zero_motion_stddev_g,
            auto_zero_max_abs_g=config.sensors.lsm6dsox.auto_zero_max_abs_g,
            # v2 sensor configs
            temperature=config.sensors.temperature,
            light=config.sensors.light,
            power=config.sensors.power,
            particulate=config.sensors.particulate,
            imu_heading=config.sensors.imu_heading,
            # GPS settings
            gps_enabled=config.sensors.gps.enabled,
            gps_host=config.sensors.gps.host,
            gps_port=config.sensors.gps.port,
            # Environment settings (BME280 — legacy, kept for reference boards)
            environment_enabled=config.sensors.environment.enabled,
            environment_i2c_address=config.sensors.environment.address,
            # Storage
            database_path=config.storage.database_path,
            home_lat=config.storage.home_lat,
            home_lng=config.storage.home_lng,
            home_exclusion_radius_m=config.storage.home_exclusion_radius_m,
            # MQTT
            mqtt_enabled=config.sync.mqtt.enabled,
            mqtt_broker_host=config.sync.mqtt.broker_host,
            mqtt_broker_port=config.sync.mqtt.broker_port,
            mqtt_username=config.sync.mqtt.username,
            mqtt_password=config.sync.mqtt.password,
            mqtt_topic_prefix=config.sync.mqtt.topic_prefix,
            # Prometheus
            prometheus_enabled=config.sync.prometheus.enabled,
            prometheus_remote_write_url=config.sync.prometheus.remote_write_url,
            prometheus_batch_size=config.sync.prometheus.batch_size,
            prometheus_batch_interval_seconds=config.sync.prometheus.batch_interval_seconds,
            # Connectivity
            connectivity_check_host=config.sync.connectivity.check_host,
            connectivity_check_port=config.sync.connectivity.check_port,
            connectivity_check_interval_seconds=config.sync.connectivity.check_interval_seconds,
            # Uplink
            uplink_enabled=config.sync.uplink_enabled,
            # Capture
            capture_enabled=config.capture.enabled,
            buzzer_enabled=config.capture.buzzer_enabled,
            capture_gpio_pin=config.capture.gpio_pin,
            capture_debounce_ms=config.capture.debounce_ms,
            capture_pre_seconds=config.capture.pre_capture_seconds,
            capture_post_seconds=config.capture.post_capture_seconds,
            capture_video_device=config.capture.video.device,
            capture_video_duration=config.capture.video.duration_seconds,
            capture_video_resolution=config.capture.video.resolution,
            capture_video_fps=config.capture.video.fps,
            capture_audio_device=config.capture.video.audio_device,
            captures_dir=config.capture.captures_dir,
            max_capture_age_days=config.capture.max_capture_age_days,
            # Timelapse
            timelapse_enabled=config.capture.timelapse.enabled,
            timelapse_interval_seconds=config.capture.timelapse.interval_seconds,
            timelapse_min_speed_kmh=config.capture.timelapse.min_speed_kmh,
            timelapse_compile_fps=config.capture.timelapse.compile_fps,
            # Video ring buffer (primary)
            video_buffer_enabled=config.capture.video_buffer.enabled,
            video_buffer_device=config.capture.video_buffer.device,
            video_buffer_input_format=config.capture.video_buffer.input_format,
            video_buffer_resolution=config.capture.video_buffer.resolution,
            video_buffer_fps=config.capture.video_buffer.fps,
            video_buffer_dir=config.capture.video_buffer.buffer_dir,
            video_buffer_segment_seconds=config.capture.video_buffer.segment_seconds,
            video_buffer_segments=config.capture.video_buffer.buffer_segments,
            overlay_enabled=config.capture.video_buffer.overlay_enabled,
            video_buffer_intro_video=config.capture.video_buffer.intro_video,
            video_buffer_camera_controls=config.capture.video_buffer.camera_controls,
            # Video ring buffer (PIP / cabin cam)
            video_buffer_pip_enabled=config.capture.video_buffer.pip.enabled,
            video_buffer_pip_device=config.capture.video_buffer.pip.device,
            video_buffer_pip_input_format=config.capture.video_buffer.pip.input_format,
            video_buffer_pip_resolution=config.capture.video_buffer.pip.resolution,
            video_buffer_pip_fps=config.capture.video_buffer.pip.fps,
            video_buffer_pip_audio_device=config.capture.video_buffer.pip.audio_device,
            video_buffer_pip_dir=config.capture.video_buffer.pip.buffer_dir,
            video_buffer_pip_position=config.capture.video_buffer.pip.position,
            video_buffer_pip_scale=config.capture.video_buffer.pip.scale,
            video_buffer_pip_camera_controls=config.capture.video_buffer.pip.camera_controls,
            # Grafana annotations
            grafana_enabled=config.sync.grafana.enabled,
            grafana_url=config.sync.grafana.url,
            grafana_username=config.sync.grafana.username,
            grafana_password_file=config.sync.grafana.password_file,
            grafana_video_base_url=config.sync.grafana.video_base_url,
            grafana_timeout_seconds=config.sync.grafana.timeout_seconds,
            # Capture sync
            capture_sync_enabled=config.sync.capture_sync.enabled,
            capture_sync_remote_dest=config.sync.capture_sync.remote_dest,
            capture_sync_rsync_path=config.sync.capture_sync.rsync_path,
            capture_sync_interval_seconds=config.sync.capture_sync.interval_seconds,
            # TPMS (Phase 28) — flatten config.tpms.* onto EngineConfig
            tpms_enabled=config.tpms.enabled,
            tpms_rtl433_protocol_id=config.tpms.rtl433_protocol_id,
            tpms_rf_frequency_hz=config.tpms.rf_frequency_hz,
            tpms_rf_gain_db=config.tpms.rf_gain_db,
            tpms_pressure_correction_factor=config.tpms.pressure_correction_factor,
            tpms_low_pressure_yellow_psi=config.tpms.low_pressure_yellow_psi,
            tpms_low_pressure_red_psi=config.tpms.low_pressure_red_psi,
            tpms_leak_window_seconds=config.tpms.leak_window_seconds,
            tpms_leak_drop_psi=config.tpms.leak_drop_psi,
            tpms_stale_timeout_seconds=config.tpms.stale_timeout_seconds,
            tpms_sustain_required=config.tpms.sustain_required,
            tpms_usb_vid_pid=config.tpms.usb_vid_pid,
            tpms_sensor_map=dict(config.tpms.sensor_map),
            # Location resolution
            location_resolution_interval_seconds=config.sensors.gps.location_resolution_interval_seconds,
            # Rally coordinates
            rally_start_lat=config.sensors.gps.rally_start_lat,
            rally_start_lon=config.sensors.gps.rally_start_lon,
            rally_destination_lat=config.sensors.gps.rally_destination_lat,
            rally_destination_lon=config.sensors.gps.rally_destination_lon,
            # OLED display
            oled_enabled=config.display.oled.enabled,
            oled_i2c_bus=config.display.oled.i2c_bus,
            oled_i2c_address=config.display.oled.address,
            oled_update_interval=config.display.oled.update_interval_seconds,
            # Speaker
            speaker_enabled=config.capture.speaker.enabled,
            speaker_model_path=config.capture.speaker.model_path,
            speaker_distance_announce_interval_km=(
                config.capture.speaker.distance_announce_interval_km
            ),
            speaker_volume=config.capture.speaker.volume,
            # Title-card slate (phase 26)
            title_card_enabled=config.capture.title_card.enabled,
            title_card_duration_seconds=config.capture.title_card.duration_seconds,
            title_card_show_driver=config.capture.title_card.show_driver,
            title_card_whimsy_lines=list(config.capture.title_card.whimsy_lines),
            # Route waypoints
            route_waypoints=config.sensors.gps.route.waypoints,
            # Dashboard
            dashboard_enabled=config.dashboard.enabled,
            dashboard_host=config.dashboard.host,
            dashboard_port=config.dashboard.port,
            dashboard_mbtiles_path=config.dashboard.mbtiles_path,
            # Driver roster
            drivers=config.drivers,
            # Hardware manifest
            hardware=config.hardware,
        )


class UnifiedEngine:
    """Unified telemetry and event detection engine.

    Replaces the old separate main.py with a single daemon that handles:
    - High-rate IMU sampling and event detection
    - Low-rate GPS/temp telemetry
    - SQLite storage for offline operation
    - MQTT publishing for real-time
    - Prometheus batch sync when online
    """

    def __init__(self, config: EngineConfig):
        """Initialise the unified engine."""
        self.config = config

        # Seed module-level hw_state so collectors' role reports during __init__ land
        # on a registered role (D-04: module IS the singleton, mirrors gps_state).
        hw_state.initialise({d.role: d.criticality for d in config.hardware.devices})
        reprobe_callbacks = self._build_reprobe_callbacks(config.hardware)
        self.supervisor = HardwareSupervisor(config.hardware, reprobe_callbacks)

        # High-rate components
        self.ring_buffer = RingBuffer(
            max_seconds=config.ring_buffer_seconds,
            sample_rate_hz=config.imu_sample_rate_hz,
        )

        self.sampler = HighRateSampler(
            ring_buffer=self.ring_buffer,
            sample_rate_hz=config.imu_sample_rate_hz,
            accel_offset_x=config.accel_offset_x,
            accel_offset_y=config.accel_offset_y,
            accel_offset_z=config.accel_offset_z,
            on_sample=self._on_imu_sample,
            tca_en_gpio=config.tca_en_gpio,
            tca_en_pulse_low_ms=config.tca_en_pulse_low_ms,
        )

        # 22-07: detector's rolling-window sizes (e.g. _az_window_size for ROUGH_ROAD)
        # must scale with the application poll rate. Mirror imu_sample_rate_hz onto
        # the DetectorConfig so the two stay in lock-step, regardless of where
        # config.detector was constructed (default_factory or future from_yaml_config
        # wiring). This is the one source-of-truth invariant from 22-07's plan.
        config.detector.sample_rate_hz = config.imu_sample_rate_hz
        self.detector = EventDetector(
            ring_buffer=self.ring_buffer,
            config=config.detector,
            on_event=self._on_event,
            get_speed=lambda: self._current_speed_kmh,
        )

        self.event_storage = EventStorage(
            base_dir=config.events_dir,
            max_age_days=config.max_event_age_days,
            max_size_mb=config.max_event_storage_mb,
            captures_dir=config.captures_dir,
        )

        # Boot recovery (set up before database.connect() in start())
        self.boot_recovery: Optional[BootRecoveryService] = None

        # Low-rate components
        self.database = Database(config.database_path)

        # GPS collector (lazy init)
        self._gps: Optional[GpsdClient] = None
        self._gps_available = False

        # v2 sensor collectors (phase 11) — each uses BaseCollector.start/stop lifecycle
        self._ds18b20_collector: Optional[DS18B20Collector] = None
        if config.temperature.enabled:
            self._ds18b20_collector = DS18B20Collector(
                config=config.temperature,
                callback=self._on_reading,
            )
            # DS18B20 manages multiple probes; individual roles (temp_exterior,
            # temp_engine_bay) are reported per-probe inside the collector. The
            # collector-level role is not set here — per-probe reporting is in
            # DS18B20Collector.read() which calls report_present/missing per role.

        self._light_collector: Optional[VEML7700Collector] = None
        if config.light.enabled:
            self._light_collector = VEML7700Collector(
                config=config.light,
                callback=self._on_reading,
                role="light",
            )

        self._particulate_collector: Optional[SEN0460Collector] = None
        if config.particulate.enabled:
            self._particulate_collector = SEN0460Collector(
                config=config.particulate,
                callback=self._on_reading,
            )

        self._ina226_collector: Optional[INA226Collector] = None
        if config.power.enabled:
            self._ina226_collector = INA226Collector(
                config=config.power,
                callback=self._on_reading,
                role="power",
            )

        self._imu_heading_collector: Optional[IMUHeadingCollector] = None
        if config.imu_heading.enabled:
            self._imu_heading_collector = IMUHeadingCollector(
                config=config.imu_heading,
                latest_sample_fn=self.sampler.latest_sample,
                callback=self._on_reading,
            )

        # Legacy environment collector (BME280 on old boards — kept for graceful transition)
        self._environment_collector = None
        if config.environment_enabled:
            try:
                from shitbox.collectors.environment import EnvironmentCollector
                from shitbox.utils.config import EnvironmentConfig

                env_config = EnvironmentConfig(
                    enabled=True,
                    address=config.environment_i2c_address,
                )
                self._environment_collector = EnvironmentCollector(env_config)
            except Exception as e:
                log.error("environment_collector_init_failed", error=str(e))

        # Connection monitor
        from shitbox.utils.config import ConnectivityConfig
        connectivity_config = ConnectivityConfig(
            check_host=config.connectivity_check_host,
            check_port=config.connectivity_check_port,
            check_interval_seconds=config.connectivity_check_interval_seconds,
            timeout_seconds=3,
        )
        self.connection = ConnectionMonitor(connectivity_config)

        # MQTT publisher
        self.mqtt: Optional[MQTTPublisher] = None
        if config.mqtt_enabled and config.uplink_enabled:
            from shitbox.utils.config import MQTTConfig
            mqtt_config = MQTTConfig(
                enabled=True,
                broker_host=config.mqtt_broker_host,
                broker_port=config.mqtt_broker_port,
                username=config.mqtt_username or "",
                password=config.mqtt_password or "",
                client_id="shitbox-car",
                qos=1,
                topic_prefix=config.mqtt_topic_prefix,
            )
            self.mqtt = MQTTPublisher(mqtt_config)

        # Prometheus batch sync
        self.batch_sync: Optional[BatchSyncService] = None
        if (
            config.prometheus_enabled
            and config.uplink_enabled
            and config.prometheus_remote_write_url
        ):
            from shitbox.utils.config import PrometheusConfig
            prom_config = PrometheusConfig(
                enabled=True,
                remote_write_url=config.prometheus_remote_write_url,
                batch_size=config.prometheus_batch_size,
                batch_interval_seconds=config.prometheus_batch_interval_seconds,
            )
            self.batch_sync = BatchSyncService(
                prom_config, self.database, self.connection,
                event_storage=self.event_storage,
            )

        # Grafana annotator
        self.grafana: Optional[GrafanaAnnotator] = None
        if config.grafana_enabled and config.uplink_enabled and config.grafana_url:
            grafana_config = GrafanaConfig(
                enabled=True,
                url=config.grafana_url,
                username=config.grafana_username,
                password_file=config.grafana_password_file,
                video_base_url=config.grafana_video_base_url,
                timeout_seconds=config.grafana_timeout_seconds,
            )
            self.grafana = GrafanaAnnotator(grafana_config, config.captures_dir)

        # Timelapse compiler (compile previous days' frames at startup)
        self.timelapse_compiler: Optional[TimelapseCompiler] = None
        if config.timelapse_enabled and config.captures_dir:
            self.timelapse_compiler = TimelapseCompiler(
                captures_dir=config.captures_dir,
                fps=config.timelapse_compile_fps,
                intro_video=config.video_buffer_intro_video,
                db_path=config.database_path,
            )

        # Capture sync (rsync to NAS)
        self.capture_sync: Optional[CaptureSyncService] = None
        if (
            config.capture_sync_enabled
            and config.uplink_enabled
            and config.capture_sync_remote_dest
        ):
            capture_sync_config = CaptureSyncConfig(
                enabled=True,
                remote_dest=config.capture_sync_remote_dest,
                rsync_path=config.capture_sync_rsync_path,
                interval_seconds=config.capture_sync_interval_seconds,
            )
            self.capture_sync = CaptureSyncService(
                capture_sync_config,
                self.connection,
                config.captures_dir,
                self.event_storage,
                self.timelapse_compiler,
            )

        # TPMS service (Phase 28) — graceful degradation if rtl_433 binary
        # is missing. Pattern matches BatchSyncService / ButtonHandler:
        # service is None unless config flag is on AND the underlying
        # tooling is available on the host.
        self.tpms: Optional[Any] = None
        if config.tpms_enabled:
            if shutil.which("rtl_433") is None:
                log.warning(
                    "tpms_disabled_no_rtl433_binary",
                    hint="apt install rtl-433 librtlsdr-dev",
                )
            else:
                from shitbox.sync.tpms import TPMSService
                from shitbox.utils.config import (
                    TpmsConfig as _TpmsConfig,
                )
                from shitbox.utils.config import (
                    TpmsSensorMapEntry as _TpmsEntry,
                )
                tpms_config = _TpmsConfig(
                    enabled=True,
                    rtl433_protocol_id=config.tpms_rtl433_protocol_id,
                    rf_frequency_hz=config.tpms_rf_frequency_hz,
                    rf_gain_db=config.tpms_rf_gain_db,
                    pressure_correction_factor=config.tpms_pressure_correction_factor,
                    low_pressure_yellow_psi=config.tpms_low_pressure_yellow_psi,
                    low_pressure_red_psi=config.tpms_low_pressure_red_psi,
                    leak_window_seconds=config.tpms_leak_window_seconds,
                    leak_drop_psi=config.tpms_leak_drop_psi,
                    stale_timeout_seconds=config.tpms_stale_timeout_seconds,
                    sustain_required=config.tpms_sustain_required,
                    usb_vid_pid=config.tpms_usb_vid_pid,
                    sensors=[
                        _TpmsEntry(id=sid, position=pos)
                        for sid, pos in config.tpms_sensor_map.items()
                    ],
                )
                self.tpms = TPMSService(
                    tpms_config,
                    self.database,
                    self.event_storage,
                )

        # Logbook storage (notes + fuel stops) — REST-only, no thread
        self.logbook_storage = LogbookStorage(self.database)
        if self.capture_sync is not None:
            self.capture_sync.register_json_generator(
                "notes", self.logbook_storage.generate_notes_json
            )
            self.capture_sync.register_json_generator(
                "fuel", self.logbook_storage.generate_fuel_json
            )

        # Driver storage — REST-only, idempotent (same pattern as LogbookStorage)
        self.driver_storage = DriverStorage(self.database)
        if self.capture_sync is not None:
            self.capture_sync.register_json_generator(
                "driver-stats",
                self.driver_storage.get_driver_stats_payload,
            )

        # Route storage -- REST-less, GPS polyline generator
        self.route_storage = RouteStorage(
            self.database,
            home_lat=self.config.home_lat,
            home_lng=self.config.home_lng,
            home_exclusion_radius_m=self.config.home_exclusion_radius_m,
        )
        if self.capture_sync is not None:
            self.capture_sync.register_json_generator(
                "route",
                self.route_storage.generate_route_json,
            )

        # Thermal monitor
        self.thermal_monitor = ThermalMonitorService()

        # Health collector (wired in start() once batch_sync is known)
        self._health_collector: Optional[HealthCollector] = None

        # OLED display
        self.oled_display: Optional[OLEDDisplayService] = None
        if config.oled_enabled:
            oled_config = OLEDConfig(
                enabled=True,
                i2c_bus=config.oled_i2c_bus,
                address=config.oled_i2c_address,
                update_interval_seconds=config.oled_update_interval,
            )
            self.oled_display = OLEDDisplayService(oled_config, self)

        # Manual capture components
        self.button_handler: Optional[ButtonHandler] = None
        self.video_recorder: Optional[VideoRecorder] = None
        self.video_ring_buffer: Optional[VideoRingBuffer] = None

        if config.capture_enabled:
            if config.video_buffer_enabled:
                overlay_path = "drawtext" if config.overlay_enabled else None
                self.video_ring_buffer = VideoRingBuffer(
                    buffer_dir=config.video_buffer_dir,
                    output_dir=config.captures_dir,
                    device=config.video_buffer_device,
                    input_format=config.video_buffer_input_format,
                    resolution=config.video_buffer_resolution,
                    fps=config.video_buffer_fps,
                    audio_device=config.capture_audio_device,
                    segment_seconds=config.video_buffer_segment_seconds,
                    buffer_segments=config.video_buffer_segments,
                    post_event_seconds=int(config.capture_post_seconds),
                    overlay_path=overlay_path,
                    intro_video=config.video_buffer_intro_video,
                    pip_device=(
                        config.video_buffer_pip_device if config.video_buffer_pip_enabled else ""
                    ),
                    pip_input_format=config.video_buffer_pip_input_format,
                    pip_resolution=config.video_buffer_pip_resolution,
                    pip_fps=config.video_buffer_pip_fps,
                    pip_position=config.video_buffer_pip_position,
                    pip_scale=config.video_buffer_pip_scale,
                    camera_controls=config.video_buffer_camera_controls,
                    pip_camera_controls=config.video_buffer_pip_camera_controls,
                    role="camera_front",
                )
            else:
                self.video_recorder = VideoRecorder(
                    output_dir=config.captures_dir,
                    device=config.capture_video_device,
                    resolution=config.capture_video_resolution,
                    fps=config.capture_video_fps,
                    audio_device=config.capture_audio_device,
                )
            self.button_handler = ButtonHandler(
                gpio_pin=config.capture_gpio_pin,
                on_press=self.trigger_manual_capture,
                debounce_ms=config.capture_debounce_ms,
            )

        # Phase 26: title-card slate renderer. Built only when the slate is
        # enabled AND a video ring buffer exists to append it to. Injected
        # into the ring buffer alongside the geocoder adapter + driver-state
        # resolver so the renderer never touches either module directly
        # (decoupled — see 26-PATTERNS.md).
        self._title_card_renderer: Optional[TitleCardRenderer] = None
        if (
            config.video_buffer_enabled
            and config.title_card_enabled
            and self.video_ring_buffer is not None
        ):
            whimsy = (
                config.title_card_whimsy_lines
                if config.title_card_whimsy_lines
                else None
            )
            self._title_card_renderer = TitleCardRenderer(
                duration_seconds=config.title_card_duration_seconds,
                show_driver=config.title_card_show_driver,
                whimsy_lines=whimsy,
                resolution=config.video_buffer_resolution,
                fps=config.video_buffer_fps,
            )
            self.video_ring_buffer._title_card_renderer = self._title_card_renderer
            self.video_ring_buffer._geocoder_fn = self._resolve_place_for_slate
            self.video_ring_buffer._active_driver_fn = driver_state.get_active_driver
            log.info(
                "title_card_renderer_wired",
                duration_s=config.title_card_duration_seconds,
                show_driver=config.title_card_show_driver,
                whimsy_count=len(config.title_card_whimsy_lines) if whimsy else 0,
            )

        # Live dashboard (in-process FastAPI on daemon thread)
        # Snapshot counter decimates the 100 Hz IMU callback down to ~10 Hz
        # dashboard updates (RESEARCH Pitfall 3 — 100 dicts/sec is wasteful).
        self._snapshot_counter: int = 0
        self._dashboard: Optional[DashboardServer] = None
        if config.dashboard_enabled:
            try:
                self._dashboard = build_dashboard_server(
                    host=config.dashboard_host,
                    port=config.dashboard_port,
                    mbtiles_path=Path(config.dashboard_mbtiles_path),
                    recent_events_provider=lambda n: self.event_storage.recent(n),
                    logbook_storage=self.logbook_storage,
                    driver_storage=self.driver_storage,
                    drivers=config.drivers or [],
                    captures_path=Path(config.captures_dir) if config.captures_dir else None,
                    sync_trigger=self.capture_sync.trigger_sync if self.capture_sync else None,
                )
            except Exception as exc:
                log.error("dashboard_init_failed", error=str(exc))
                self._dashboard = None

        # State
        self._running = False
        self._telemetry_thread: Optional[threading.Thread] = None
        self._pending_post_capture: dict = {}
        self._pending_lock = threading.Lock()
        self._event_json_paths: dict[int, Path] = {}
        self._event_video_paths: dict[int, Path] = {}
        self._event_paths_lock = threading.Lock()
        # Phase 26 gap-closure (plan 26-05): poster PNG paths handed over from
        # the ring-buffer worker via the save callback's third argument. Same
        # lock as _event_video_paths — both arrive on the same callback, so one
        # critical section covers both. Consumed by _check_post_captures, which
        # renames the holding-dir PNG into the per-day dir before save_event.
        self._event_poster_paths: dict[int, Path] = {}
        self._manual_capture_count = 0
        self._last_timelapse_time = 0.0
        self._last_wal_checkpoint: float = 0.0
        self._current_speed_kmh = 0.0
        self._current_lat: Optional[float] = None
        self._current_lon: Optional[float] = None
        self._current_heading: Optional[float] = None
        self._current_altitude: Optional[float] = None
        self._current_satellites: Optional[int] = None
        self._cabin_temp_c: Optional[float] = None
        self._gps_has_fix = False
        self._clock_synced_from_gps = False

        # Auto-zero state (IMU-05, IMU-06). Counter ticks at 1 Hz telemetry
        # cadence; window data is pulled from the 100 Hz ring buffer on
        # evaluation. _current_accel_offsets tracks live offsets separately
        # from the static config seed so post-bootstrap tolerance compares
        # against current-known-good, not the one-time YAML value.
        self._stationary_elapsed_s: float = 0.0
        self._autozero_bootstrap_done: bool = False
        self._current_accel_offsets: tuple[float, float, float] = (
            config.accel_offset_x,
            config.accel_offset_y,
            config.accel_offset_z,
        )
        self._distance_from_start_km: Optional[float] = None
        self._distance_to_destination_km: Optional[float] = None

        # Trip tracking state (odometer + daily distance + waypoints)
        self._odometer_km: float = 0.0
        self._daily_km: float = 0.0
        self._last_known_lat: Optional[float] = None
        self._last_known_lon: Optional[float] = None
        self._last_trip_persist: float = 0.0
        self._reached_waypoints: set = set()
        # Last announced km threshold — reset on reboot, no DB persistence needed
        self._last_announced_km: float = 0.0

        # Location resolution state
        self._current_location_name: Optional[str] = None
        self._last_location_resolve_time: float = 0.0
        self._last_resolved_lat: Optional[float] = None
        self._last_resolved_lon: Optional[float] = None
        self._reverse_geocoder: Any = None
        try:
            import reverse_geocoder as rg
            self._reverse_geocoder = rg
            log.info("reverse_geocoder_available")
        except ImportError:
            log.warning("reverse_geocoder_not_installed")

        # Stats
        self.telemetry_readings = 0
        self.events_captured = 0
        self.timelapse_images = 0

        # Health watchdog
        self._last_health_time = 0.0
        self._last_sample_count = 0
        self._health_failures = 0
        self._engine_start_time = 0.0

    def _build_reprobe_callbacks(
        self, manifest: HardwareManifestConfig
    ) -> dict[str, Callable[[], bool]]:
        """Build per-role reprobe callbacks from the hardware manifest.

        Each callback is a closure over the device's bus-specific field, using
        default-argument capture to avoid late-binding bugs in the loop.
        Devices with None for their required field are skipped with a warning.
        """
        cbs: dict[str, Callable[[], bool]] = {}
        for dev in manifest.devices:
            bus = dev.bus
            if bus == "i2c-1":
                if dev.address is None:
                    log.warning("reprobe_skip_missing_address", role=dev.role)
                    continue
                addr: int = dev.address
                cbs[dev.role] = cast(Callable[[], bool], lambda a=addr: probes.probe_i2c(1, a))
            elif bus == "1-wire":
                if not dev.sensor_id:
                    log.warning("reprobe_skip_missing_sensor_id", role=dev.role)
                    continue
                sid: str = dev.sensor_id
                cbs[dev.role] = cast(Callable[[], bool], lambda s=sid: probes.probe_onewire(s))
            elif bus == "usb":
                if not dev.path:
                    log.warning("reprobe_skip_missing_path", role=dev.role)
                    continue
                path: str = dev.path
                cbs[dev.role] = cast(Callable[[], bool], lambda p=path: probes.probe_usb_path(p))
            elif bus == "audio":
                if not dev.label:
                    log.warning("reprobe_skip_missing_label", role=dev.role)
                    continue
                lbl: str = dev.label
                cbs[dev.role] = cast(
                    Callable[[], bool], lambda lbl=lbl: probes.probe_audio_label(lbl)
                )
            elif bus == "hdmi":
                if not dev.connector:
                    log.warning("reprobe_skip_missing_connector", role=dev.role)
                    continue
                conn: str = dev.connector
                cbs[dev.role] = cast(Callable[[], bool], lambda c=conn: probes.probe_hdmi(c))
            elif bus == "gpio":
                if dev.pin is None:
                    log.warning("reprobe_skip_missing_pin", role=dev.role)
                    continue
                pin: int = dev.pin
                cbs[dev.role] = cast(
                    Callable[[], bool], lambda p=pin: probes.probe_gpio_pin(p)
                )
            elif bus == "usb_vid_pid":
                if not dev.path:
                    log.warning("reprobe_skip_missing_vid_pid", role=dev.role)
                    continue
                vid_pid: str = dev.path
                cbs[dev.role] = cast(
                    Callable[[], bool], lambda v=vid_pid: probes.probe_usb_vid_pid(v)
                )
            else:
                log.warning("unknown_bus_for_reprobe", role=dev.role, bus=bus)
        return cbs

    def _start_service_graceful(
        self, name: str, start_fn: Callable[[], None]
    ) -> bool:
        """Start a service, catching any exception so a single failure cannot abort boot.

        Returns True if the service started cleanly, False if it raised.
        HW-05 relies on this: no collector failure can prevent the engine from booting.
        """
        try:
            start_fn()
            log.info("service_started", service=name)
            return True
        except Exception as e:
            log.error("service_start_failed", service=name, error=str(e))
            return False

    def _init_gps(self) -> bool:
        """Initialise GPS connection.

        Uses our own persistent gpsd JSON-stream client (see
        :mod:`shitbox.gpsd_client`). Unlike gpsd-py3's ``get_current()``, this
        tolerates SKY frames interleaved with TPV and survives socket drops
        via a background reconnect loop.
        """
        if not self.config.gps_enabled:
            return False

        try:
            client = GpsdClient(
                host=self.config.gps_host,
                port=self.config.gps_port,
                role="gps",
            )
            client.start()
            self._gps = client
            self._gps_available = True
            log.info("gps_client_started", host=self.config.gps_host)
            return True
        except Exception as e:
            log.error("gps_init_failed", error=str(e))
            self._gps_available = False
            return False

    def _wait_for_gps_fix(self, max_wait: int = 20) -> bool:
        """Poll GPS for a fix at startup, syncing the clock if needed.

        Args:
            max_wait: Maximum seconds to wait for a fix.

        Returns:
            True if a fix was obtained.
        """
        log.info("waiting_for_gps_fix", max_wait_seconds=max_wait)

        for i in range(max_wait):
            if not self._running:
                return False
            # Keep systemd watchdog fed during cold-start GPS acquisition.
            # WatchdogSec is shorter than max_wait, so without this a slow
            # cold fix burns the entire budget and the service gets killed.
            self._notify_systemd("WATCHDOG=1")
            try:
                reading = self._read_gps()
                if reading and reading.latitude is not None:
                    self._gps_has_fix = True
                    self._current_lat = reading.latitude
                    self._current_lon = reading.longitude
                    self._current_speed_kmh = (
                        reading.speed_kmh if reading.speed_kmh and reading.speed_kmh >= 3.0
                        else 0.0
                    )
                    self._current_heading = reading.heading_deg
                    self._current_altitude = reading.altitude_m
                    self._current_satellites = reading.satellites
                    log.info(
                        "gps_fix_acquired_at_startup",
                        wait_seconds=i + 1,
                        lat=round(reading.latitude, 4),
                        lon=round(reading.longitude, 4),
                        clock_synced=self._clock_synced_from_gps,
                    )
                    return True
            except Exception as e:
                log.debug("gps_fix_poll_error", error=str(e))
            time.sleep(1)

        log.warning("gps_fix_timeout_at_startup", waited_seconds=max_wait)
        return False

    def _on_reading(self, reading: Reading) -> None:
        """Callback for v2 sensor collectors — persists readings to SQLite.

        Called from collector background threads; database is thread-safe (WAL + write lock).
        """
        try:
            self.database.insert_reading(reading)
            self.telemetry_readings += 1
            if (
                reading.sensor_type == SensorType.ENVIRONMENT
                and reading.env_temp_celsius is not None
            ):
                self._cabin_temp_c = reading.env_temp_celsius
            elif (
                reading.sensor_type == SensorType.TEMPERATURE
                and reading.temp_celsius is not None
            ):
                # DS18B20 fallback — keeps the kiosk "cabin temp" tile populated until BME680
                # is reliable (D-09, Phase 17). Last-write wins if both sensors fire.
                self._cabin_temp_c = reading.temp_celsius
        except Exception as e:
            log.error("v2_collector_db_write_error", error=str(e))

    def _on_imu_sample(self, sample: IMUSample) -> None:
        """Called for each high-rate IMU sample."""
        self.detector.process_sample(sample)

        # Dashboard snapshot — update at 10 Hz, NOT 100 Hz (RESEARCH Pitfall 3).
        # Atomic dict rebind under the GIL (RESEARCH Pattern 2). Wrapped in
        # try/except so dashboard failures NEVER affect the sampler/detector.
        if self._dashboard is not None:
            self._snapshot_counter += 1
            if self._snapshot_counter % 10 == 0:
                try:
                    backlog = 0
                    if self.batch_sync is not None:
                        backlog = getattr(self.batch_sync, "pending_count", 0) or 0
                    update_snapshot({
                        "ts": sample.timestamp,
                        "speed_kmh": self._current_speed_kmh or 0.0,
                        "g_x": float(sample.ax),
                        "g_y": float(sample.ay),
                        "g_z": float(sample.az),
                        "heading_deg": self._current_heading or 0.0,
                        "lat": self._current_lat,
                        "lng": self._current_lon,
                        "gps_fix_mode": 3 if self._gps_has_fix else 0,
                        "gps_sat_count": self._current_satellites or 0,
                        "gps_hdop": None,
                        "imu_temp_c": self._cabin_temp_c,
                        "soc_temp_c": getattr(self.thermal_monitor, "current_temp_celsius", None),
                        "sync_connected": getattr(self.connection, "is_connected", False),
                        "sync_backlog": backlog,
                        "event_count_today": self.events_captured,
                        "active_driver": driver_state.get_active_driver(),
                        "recording_active": self._has_pending_captures()
                            or (
                                self.video_ring_buffer is not None
                                and self.video_ring_buffer.is_saving
                            )
                            or (
                                self.video_recorder is not None
                                and self.video_recorder.is_recording
                            ),
                    })
                except Exception as exc:
                    log.warning("dashboard_snapshot_update_failed", error=str(exc))

    # Event types that should trigger video recording
    VIDEO_CAPTURE_EVENTS = {
        EventType.HARD_BRAKE,
        EventType.HIGH_G,
        EventType.BIG_CORNER,
        EventType.ROUGH_ROAD,
        EventType.MANUAL_CAPTURE,
        EventType.BOOT,
        EventType.ROLLOVER,  # Phase 22 (IMU-03) - rollovers always save video
    }

    # Health watchdog
    HEALTH_CHECK_INTERVAL = 30.0
    HEALTH_GRACE_PERIOD = 60.0  # skip checks during startup
    DISK_LOW_PCT = 10.0
    DISK_CRITICAL_PCT = 5.0

    # WAL checkpoint interval (5 minutes)
    WAL_CHECKPOINT_INTERVAL_S = 300.0

    # Timelapse gap watchdog: alert if 3x interval passes with no capture
    TIMELAPSE_GAP_FACTOR = 3

    def _has_pending_captures(self) -> bool:
        with self._pending_lock:
            return bool(self._pending_post_capture)

    def _on_event(self, event: Event) -> None:
        """Called when an event is detected."""
        # Suppress events while a capture is already in progress.
        # Extends the active capture window instead, so consecutive events
        # (e.g. hard brake → high G → hard brake) produce one video, not many.
        # Manual captures also extend rather than starting overlapping saves.
        # Boot events always go through (only fires once).
        # Two suppression conditions: a pending post-capture window is open,
        # OR the previous video worker is still running. The window is
        # time-based and can release before the concat worker finishes; without
        # the second gate, a fresh event can spawn a second concurrent ffmpeg
        # concat and spike CPU.
        save_in_progress = bool(
            self.video_ring_buffer is not None and self.video_ring_buffer.is_saving
        )
        with self._pending_lock:
            if (
                (self._pending_post_capture or save_in_progress)
                and event.event_type != EventType.BOOT
            ):
                # Extend the post-capture window of the most recent pending event
                extension = self.config.detector.post_event_seconds
                for pending in self._pending_post_capture.values():
                    new_until = time.monotonic() + extension
                    if new_until > pending["capture_until"]:
                        pending["capture_until"] = new_until
                pending_count = len(self._pending_post_capture)
                is_suppressed = True
            else:
                pending_count = 0
                is_suppressed = False
        if is_suppressed:
            if event.event_type == EventType.MANUAL_CAPTURE:
                buzzer.beep_capture_busy()
            log.info(
                "event_suppressed_capture_active",
                suppressed_type=event.event_type.value,
                peak_g=round(event.peak_value, 2),
                pending_count=pending_count,
                save_in_progress=save_in_progress,
            )
            return

        # Attach current GPS state to the event
        event.lat = self._current_lat
        event.lng = self._current_lon
        event.speed_kmh = self._current_speed_kmh if self._current_speed_kmh else None
        event.location_name = self._current_location_name
        event.distance_from_start_km = self._distance_from_start_km
        event.distance_to_destination_km = self._distance_to_destination_km

        # Push to dashboard SSE immediately — same moment as audio so the kiosk
        # display updates in sync with the beep, not after the post-capture save.
        # Uppercase the type to match EVENT_COLOURS keys and CSS classes in the UI.
        if self._dashboard is not None:
            try:
                dashboard_push_event({
                    "id": int(event.start_time * 1000),
                    "type": event.event_type.value.upper(),
                    "timestamp": datetime.fromtimestamp(
                        event.start_time, tz=timezone.utc
                    ).isoformat(),
                    "peak_g": float(event.peak_value),
                    "duration_ms": int((event.end_time - event.start_time) * 1000),
                    "speed_kmh": event.speed_kmh,
                    "lat": event.lat,
                    "lng": event.lng,
                })
            except Exception as exc:
                log.warning("dashboard_event_push_failed", error=str(exc))

        # Start video recording/save for significant events
        video_path = None
        if event.event_type in self.VIDEO_CAPTURE_EVENTS:
            if self.video_ring_buffer and self.video_ring_buffer.is_running:
                buzzer.beep_capture_start()
                speaker.speak_capture_start(event.event_type.value)
                eid = id(event)
                self.video_ring_buffer.save_event(
                    prefix=event.event_type.value,
                    post_seconds=int(self.config.capture_post_seconds),
                    pre_seconds=int(self.config.capture_pre_seconds),
                    callback=lambda path, _cs, _pp, _eid=eid: self._on_video_complete(
                        _eid, path, _pp
                    ),
                    event=event,
                )
                log.info(
                    "video_save_triggered",
                    event_type=event.event_type.value,
                )
            elif self.video_recorder and not self.video_recorder.is_recording:
                video_path = self.video_recorder.start_recording(
                    duration_seconds=self.config.capture_video_duration,
                    filename_prefix=event.event_type.value,
                )
                log.info(
                    "auto_event_video_started",
                    event_type=event.event_type.value,
                    video_path=str(video_path) if video_path else None,
                )

        # Schedule post-event capture
        post_capture_until = time.monotonic() + self.config.detector.post_event_seconds
        with self._pending_lock:
            self._pending_post_capture[id(event)] = {
                "event": event,
                "capture_until": post_capture_until,
                "video_path": video_path,
            }
            pending_count = len(self._pending_post_capture)
        log.info(
            "event_queued_for_save",
            event_type=event.event_type.value,
            event_id=id(event),
            pending_count=pending_count,
            save_after_seconds=self.config.detector.post_event_seconds,
        )

        # MQTT event publish is parked. MQTT is config-disabled to avoid
        # duplicate metrics with the Prometheus path, and the ad-hoc call
        # here referenced a non-existent ``MQTTPublisher._publish`` (the
        # publisher exposes ``publish_reading`` / ``publish_health``, not
        # raw publish). If MQTT event publishing is wanted again, add a
        # ``publish_event`` queue method on MQTTPublisher and wire it here.

    def trigger_manual_capture(self) -> None:
        """Trigger manual capture via button press or API call.

        Creates a MANUAL_CAPTURE event and routes it through the
        standard _on_event pipeline.
        """
        # If ring buffer has stalled or crashed, restart it so the button press
        # captures post-event footage rather than silently saving nothing.
        if self.video_ring_buffer and not self.video_ring_buffer.is_running:
            log.warning("manual_capture_ring_buffer_not_running_restarting")
            self.video_ring_buffer._start_ffmpeg()

        self._manual_capture_count += 1
        now = time.time()

        log.info(
            "manual_capture_triggered",
            capture_number=self._manual_capture_count,
        )

        # Grab pre-event IMU samples from ring buffer
        pre_samples = self.ring_buffer.get_window(
            self.config.capture_pre_seconds
        )

        # Get current IMU reading for peak values
        latest = self.ring_buffer.get_latest(1)
        peak_ax = latest[0].ax if latest else 0.0
        peak_ay = latest[0].ay if latest else 0.0
        peak_az = latest[0].az if latest else 0.0

        event = Event(
            event_type=EventType.MANUAL_CAPTURE,
            start_time=now - self.config.capture_pre_seconds,
            end_time=now,
            peak_value=1.0,
            peak_ax=peak_ax,
            peak_ay=peak_ay,
            peak_az=peak_az,
            samples=list(pre_samples),
        )

        # Route through standard event pipeline
        self._on_event(event)

    def _on_video_complete(
        self,
        event_id: int,
        path: Optional[Path],
        poster_path: Optional[Path],
    ) -> None:
        """Called when a video ring buffer save finishes.

        Updates the saved event metadata with the video path and
        regenerates events.json. Also stashes the stable poster PNG
        path so _check_post_captures can rename it into the per-day dir.

        Args:
            event_id: id() of the source Event — lookup key for the
                      _event_json_paths and _event_poster_paths dicts.
            path: Saved MP4 path, or None on concat/save failure.
            poster_path: Stable holding-dir PNG path from the ring-buffer
                         worker (buffer_dir/pending_slates/<save_id>.png),
                         or None when no slate rendered or move to
                         holding failed.
        """
        buzzer.beep_capture_end()
        speaker.speak_capture_end()
        if not path:
            log.warning("capture_failed", event_id=event_id)
            # Poster may have rendered even though concat failed — stash it
            # so _check_post_captures can still emit poster_url.
            if poster_path is not None:
                with self._event_paths_lock:
                    self._event_poster_paths[event_id] = poster_path
                    log.info(
                        "event_poster_stashed",
                        event_id=event_id,
                        poster=str(poster_path),
                    )
            return

        log.info("capture_complete", path=str(path), event_id=event_id)

        # Phase 26-06 (G-01 + G-05): the lock covers the full
        # pop+rename+JSON-rewrite window for the late branch so a concurrent
        # _check_post_captures cannot observe a half-consumed state (PNG
        # renamed but JSON not yet updated). See threat_model T-26-06-01.
        with self._event_paths_lock:
            json_path = self._event_json_paths.get(event_id)
            if json_path is None:
                # EARLY branch: event not yet saved. Stash for
                # _check_post_captures to pop under the same lock.
                self._event_video_paths[event_id] = path
                if poster_path is not None:
                    self._event_poster_paths[event_id] = poster_path
                    log.info(
                        "event_poster_stashed",
                        event_id=event_id,
                        poster=str(poster_path),
                    )
                return

            # LATE branch (G-01): event already saved with poster_path=None.
            # Deliver the poster by renaming the stable PNG into the day
            # dir and patching the saved JSON. Key strictly on event_id —
            # no _find_capture_video type-scan fallback (G-05 refusal).
            # Source order: the poster_path parameter passed on THIS call wins
            # (standard late-callback shape); fall back to any previously
            # stashed path for the same event_id (belt-and-braces — e.g. a
            # prior call stashed via the EARLY branch and this call is a
            # redelivery with poster_path=None).
            src_png = poster_path
            if src_png is None:
                src_png = self._event_poster_paths.pop(event_id, None)
            else:
                # Drop any prior stash for this event so it doesn't leak.
                self._event_poster_paths.pop(event_id, None)
            self.event_storage.update_event_video(json_path, path)
            if src_png is not None:
                base_name = json_path.stem
                # G-07 (plan 26-08): place the poster next to the MP4 in
                # captures_dir — the tree rsync ships to the NAS. events_dir
                # (where json_path lives) is Pi-local JSON+CSV.
                day_str = json_path.parent.name
                if self.event_storage.captures_dir is not None:
                    day_dir = self.event_storage.captures_dir / day_str
                else:
                    day_dir = json_path.parent
                dest_png = day_dir / f"{base_name}_poster.png"
                try:
                    day_dir.mkdir(parents=True, exist_ok=True)
                    src_png.rename(dest_png)
                    self.event_storage.update_event_poster(json_path, dest_png)
                except OSError as move_err:
                    log.warning(
                        "late_poster_move_failed",
                        event_id=event_id,
                        src=str(src_png),
                        dst=str(dest_png),
                        error=str(move_err),
                    )
            self.event_storage.generate_events_json()
            if self.capture_sync:
                self.capture_sync.trigger_sync()

    def _check_post_captures(self) -> None:
        """Complete any pending post-event captures."""
        now = time.monotonic()
        completed = []

        with self._pending_lock:
            pending_snapshot = list(self._pending_post_capture.items())

        for event_id, pending in pending_snapshot:
            if now >= pending["capture_until"]:
                event = pending["event"]
                wait_seconds = now - pending["capture_until"]
                log.info(
                    "post_capture_processing",
                    event_type=event.event_type.value,
                    event_id=event_id,
                    waited_extra_seconds=round(wait_seconds, 1),
                )
                # Get additional samples since event ended
                additional = self.ring_buffer.get_window(
                    self.config.detector.post_event_seconds
                )
                event.samples.extend(
                    s for s in additional if s.timestamp > event.end_time
                )

                # Check if video callback already fired
                eid = id(event)
                with self._event_paths_lock:
                    video_path = self._event_video_paths.pop(eid, None)
                    src_png = self._event_poster_paths.pop(eid, None)
                if not video_path:
                    # G-06 (plan 26-07): EARLY branch refuses _find_capture_video
                    # type-scan. On slow Pi scheduling the stash is often empty
                    # at save time because the MP4 is still rendering; type-scan
                    # would return the PRIOR event's MP4 (most recent of the same
                    # type) and stamp a stale path into events.json. Save with
                    # video_path=None here — _on_video_complete will pair the
                    # real MP4 via event_id-strict lookup in the LATE branch.
                    # Symmetric with the LATE branch refusal (G-05, plan 26-06).
                    log.warning(
                        "event_video_update_orphan",
                        event_id=eid,
                        event_type=event.event_type.value,
                        reason="no_stash_type_scan_refused",
                    )

                # Phase 26 (plan 26-05): move the stable holding-dir PNG into
                # the per-day dir so generate_events_json can build a
                # /captures/<date>/<base>_poster.png URL. We pre-generate
                # base_name ONCE here and pass it into save_event via the
                # base_name= override to avoid a second _generate_filename
                # (counter double-bump — T-26-04-06).
                # src_png was popped from _event_poster_paths above (set on the
                # worker thread via _on_video_complete) — CR-01 fix.
                poster_path: Optional[Path] = None
                base_name: Optional[str] = None
                if self.video_ring_buffer is not None:
                    base_name = self.event_storage._generate_filename(event)
                    if src_png is not None and src_png.exists():
                        # G-07 (plan 26-08): place the poster next to the MP4
                        # in captures_dir — the tree rsync ships to the NAS.
                        day_dir = self.event_storage.get_captures_day_dir(
                            event.start_time
                        )
                        if day_dir is None:
                            day_dir = self.event_storage._get_day_dir(
                                event.start_time
                            )
                        dest_png = day_dir / f"{base_name}_poster.png"
                        try:
                            day_dir.mkdir(parents=True, exist_ok=True)
                            src_png.rename(dest_png)
                            poster_path = dest_png
                        except OSError as move_err:
                            log.warning("poster_move_failed", error=str(move_err))
                            poster_path = None
                    # _pending_slate_ts and _pending_slate_duration stay worker-local;
                    # do NOT reset them here — they are cleared at the top of the
                    # next save pass (CR-01 gap-closure, plan 26-05).

                # Save to disk
                try:
                    json_path, _ = self.event_storage.save_event(
                        event,
                        video_path=video_path,
                        driver_name=driver_state.get_active_driver(),
                        poster_path=poster_path,
                        base_name=base_name,
                    )
                    self.events_captured += 1
                    # Store json_path so late video callbacks can
                    # update this event.
                    with self._event_paths_lock:
                        self._event_json_paths[eid] = json_path
                    # G-06 (plan 26-07): defer events.json regen when
                    # video_path is None. The LATE branch's event_video_updated
                    # path regenerates events.json after pairing the real MP4,
                    # so skipping here avoids publishing a race-window no-video
                    # entry that browsers/NAS can cache past the corrective
                    # regen.
                    if video_path is not None:
                        self.event_storage.generate_events_json()
                    log.info(
                        "event_saved_to_disk",
                        event_type=event.event_type.value,
                        json_path=str(json_path),
                        has_video=video_path is not None,
                    )
                    # Trigger immediate connectivity check and sync
                    if self.config.uplink_enabled:
                        connected = self.connection.check_connectivity()
                        log.info("post_event_connectivity_check", connected=connected)
                        if connected and self.capture_sync:
                            self.capture_sync.trigger_sync()
                except Exception as e:
                    log.error(
                        "event_save_error",
                        event_type=event.event_type.value,
                        error=str(e),
                        events_dir=self.config.events_dir,
                        captures_dir=self.config.captures_dir,
                    )

                # Post Grafana annotation
                if self.grafana:
                    self.grafana.annotate_event(event, video_path)

                completed.append(event_id)

        if completed:
            with self._pending_lock:
                for event_id in completed:
                    self._pending_post_capture.pop(event_id, None)

    def _find_capture_video(self, event: Event) -> Optional[Path]:
        """Find the most recent video capture matching an event by TYPE.

        WARNING (G-05, plan 26-06): this is a type-scan fallback used only
        when _check_post_captures finds the in-memory video stash empty. It
        CANNOT distinguish between two same-type events in the same day
        directory and can also pick up prior-session files. Do NOT call this
        from the late-update branch of _on_video_complete — event_id-keyed
        lookup via _event_json_paths is the sole trusted source there.
        """
        captures = Path(self.config.captures_dir)
        event_date = datetime.fromtimestamp(event.start_time, tz=timezone.utc)
        date_dir = captures / event_date.strftime("%Y-%m-%d")
        if not date_dir.is_dir():
            log.debug("find_capture_video_empty", event_type=event.event_type.value)
            return None

        pattern = f"{event.event_type.value}_*.mp4"
        matches = sorted(date_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            log.debug("find_capture_video_empty", event_type=event.event_type.value)
            return None
        log.warning(
            "find_capture_video_type_scan",
            event_type=event.event_type.value,
            matched=str(matches[0]),
        )
        return matches[0]

    def _read_gps(self) -> Optional[Reading]:
        """Read current GPS data from the cached gpsd stream."""
        if not self._gps_available or self._gps is None:
            return None

        try:
            tpv, sky, tpv_mono = self._gps.get_latest()
            if tpv is None:
                return None

            # Drop stale fixes — gpsd can go quiet with no new TPV for a while
            # if the receiver loses lock; treat anything >5s old as no-fix.
            if tpv_mono > 0.0 and (time.monotonic() - tpv_mono) > 5.0:
                return None

            mode = int(tpv.get("mode", 0) or 0)
            if mode < 2:
                return None

            timestamp = datetime.now(timezone.utc)
            raw_time = tpv.get("time")
            if isinstance(raw_time, str):
                try:
                    timestamp = datetime.fromisoformat(
                        raw_time.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            if not self._clock_synced_from_gps:
                self._sync_clock_from_gps(timestamp)

            hspeed = tpv.get("speed")
            speed_kmh = hspeed * 3.6 if isinstance(hspeed, (int, float)) else None
            # Sanity cap: GPS multipath / cold-fix can spit out absurd speeds.
            # 2026-04-26 bench data hit 252 km/h with the antenna under foliage.
            # The Laser does not break the sound barrier; drop anything above
            # 250 km/h or negative as sensor noise rather than letting it
            # pollute SQLite + Prometheus + the dashboard.
            if speed_kmh is not None and (speed_kmh > 250.0 or speed_kmh < 0.0):
                log.warning("gps_speed_implausible_dropped", raw_kmh=round(speed_kmh, 1))
                speed_kmh = None

            satellites: Optional[int] = None
            if sky is not None:
                u = sky.get("uSat")
                if u is None:
                    u = sky.get("nSat")
                if isinstance(u, int):
                    satellites = u

            reading = Reading(
                timestamp_utc=timestamp,
                sensor_type=SensorType.GPS,
                latitude=tpv.get("lat"),
                longitude=tpv.get("lon"),
                altitude_m=tpv.get("alt") if mode >= 3 else None,
                speed_kmh=speed_kmh,
                heading_deg=tpv.get("track"),
                satellites=satellites,
                fix_quality=mode,
            )
            return reading

        except Exception as e:
            log.error("gps_read_error", error=str(e))
            return None

    def _sync_clock_from_gps(self, gps_time: datetime) -> None:
        """Set the system clock from GPS time on first fix.

        Runs once per boot to correct the clock when NTP is unavailable
        (e.g. no network). Only adjusts if the drift is >30 seconds to
        avoid fighting NTP when it is available.

        Uses clock_settime via ctypes — requires CAP_SYS_TIME capability
        on the systemd service.
        """
        import ctypes
        import ctypes.util

        try:
            drift = abs((gps_time - datetime.now(timezone.utc)).total_seconds())
            if drift < 30:
                log.info("clock_already_accurate", drift_seconds=round(drift, 1))
                self._clock_synced_from_gps = True
                return

            # clock_settime(CLOCK_REALTIME, timespec)
            CLOCK_REALTIME = 0
            ts = gps_time.timestamp()
            sec = int(ts)
            nsec = int((ts - sec) * 1e9)

            class Timespec(ctypes.Structure):
                _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]

            librt_name = ctypes.util.find_library("rt")
            if librt_name:
                librt = ctypes.CDLL(librt_name, use_errno=True)
            else:
                librt = ctypes.CDLL("libc.so.6", use_errno=True)

            timespec = Timespec(sec, nsec)
            ret = librt.clock_settime(CLOCK_REALTIME, ctypes.byref(timespec))
            if ret == 0:
                log.info(
                    "clock_synced_from_gps",
                    gps_time=gps_time.strftime("%Y-%m-%d %H:%M:%S"),
                    drift_seconds=round(drift, 1),
                )
                self._clock_synced_from_gps = True
            else:
                errno = ctypes.get_errno()
                log.error("clock_sync_failed", errno=errno)
        except Exception as e:
            log.error("clock_sync_error", error=str(e))

    def _sync_fake_hwclock(self) -> None:
        """Write current time to /etc/fake-hwclock.data.

        Keeps the saved time fresh so reboots without network start
        with a roughly correct clock (within ~1 hour).  Requires
        ReadWritePaths=/etc/fake-hwclock.data in the systemd unit.
        """
        FAKE_HWCLOCK_FILE = "/etc/fake-hwclock.data"
        try:
            time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            with open(FAKE_HWCLOCK_FILE, "w") as f:
                f.write(time_str + "\n")
            log.debug("fake_hwclock_saved", time=time_str)
        except Exception as e:
            log.debug("fake_hwclock_save_failed", error=str(e))

    def _read_imu_snapshot(self) -> Optional[Reading]:
        """Get current IMU reading from ring buffer."""
        samples = self.ring_buffer.get_latest(1)
        if not samples:
            return None

        sample = samples[0]
        return Reading(
            timestamp_utc=datetime.fromtimestamp(sample.timestamp, tz=timezone.utc),
            sensor_type=SensorType.IMU,
            accel_x=sample.ax,
            accel_y=sample.ay,
            accel_z=sample.az,
            gyro_x=sample.gx,
            gyro_y=sample.gy,
            gyro_z=sample.gz,
        )

    def _read_pi_temp(self) -> Optional[float]:
        """Read Raspberry Pi CPU temperature."""
        try:
            temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
            if temp_path.exists():
                temp_millidegrees = int(temp_path.read_text().strip())
                return temp_millidegrees / 1000.0
        except (IOError, ValueError) as e:
            log.debug("pi_temp_read_error", error=str(e))
        return None

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance between two points in km."""
        import math
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _resolve_place_for_slate(self, lat: float, lon: float) -> Optional[str]:
        """Geocoder adapter for TitleCardRenderer (phase 26).

        Mirrors timelapse_compiler._resolve_place_name's "Name, Admin1" shape,
        using the engine's shared _reverse_geocoder instance. Returns None
        when the geocoder is absent or no result is returned (D-09 / D-10
        fallback in the renderer).
        """
        if self._reverse_geocoder is None:
            return None
        try:
            results = self._reverse_geocoder.search((lat, lon))
            if not results:
                return None
            r = results[0]
            name = (r.get("name") or "").strip()
            admin1 = (r.get("admin1") or "").strip()
            if name and admin1:
                return f"{name}, {admin1}"
            return name or None
        except Exception as exc:
            log.debug("slate_geocode_failed", error=str(exc))
            return None

    def _resolve_location(self, lat: float, lon: float) -> None:
        """Resolve GPS coordinates to a human-readable location name.

        Prefixes with "Near" when the matched place is >5 km away.
        """
        if not self._reverse_geocoder:
            return

        now = time.monotonic()
        interval = self.config.location_resolution_interval_seconds

        # Check if enough time has elapsed
        time_elapsed = (now - self._last_location_resolve_time) >= interval

        # Check if position has moved >1km since last resolve
        moved = False
        if self._last_resolved_lat is not None and self._last_resolved_lon is not None:
            moved = self._haversine_km(
                lat, lon, self._last_resolved_lat, self._last_resolved_lon
            ) > 1.0
        else:
            moved = True  # First resolve

        if not time_elapsed and not moved:
            return

        try:
            results = self._reverse_geocoder.search((lat, lon))
            if results:
                result = results[0]
                name = result.get("name", "")
                admin1 = result.get("admin1", "")
                if name and admin1:
                    label = f"{name}, {admin1}"
                elif name:
                    label = name
                else:
                    return

                # "Near" prefix when >5 km from the matched place centre
                place_lat = float(result.get("lat", lat))
                place_lon = float(result.get("lon", lon))
                dist_km = self._haversine_km(lat, lon, place_lat, place_lon)
                if dist_km > 5.0:
                    label = f"Near {label}"

                self._current_location_name = label
                self._last_location_resolve_time = now
                self._last_resolved_lat = lat
                self._last_resolved_lon = lon
                log.debug(
                    "location_resolved",
                    location=self._current_location_name,
                    distance_km=round(dist_km, 1),
                    lat=round(lat, 4),
                    lon=round(lon, 4),
                )
        except Exception as e:
            log.error("location_resolve_error", error=str(e))

    def get_status(self) -> dict:
        """Return current system status for the OLED display."""
        # Peak G from latest IMU sample
        peak_g = 0.0
        samples = self.ring_buffer.get_latest(1)
        if samples:
            s = samples[0]
            peak_g = (s.ax**2 + s.ay**2 + s.az**2) ** 0.5

        return {
            "gps_available": self._gps_available,
            "gps_has_fix": self._gps_has_fix,
            "satellites": self._current_satellites,
            "speed_kmh": self._current_speed_kmh,
            "peak_g": peak_g,
            "imu_ok": self.sampler._running,
            "env_ok": self._environment_collector is not None,
            "pwr_ok": getattr(self, "_ina226_collector", None) is not None,
            "events_captured": self.events_captured,
            "recording": (
                self.video_ring_buffer is not None
                and self.video_ring_buffer.is_running
            )
            or (
                self.video_recorder is not None
                and self.video_recorder.is_recording
            ),
            "net_connected": self.connection.is_connected,
            "sync_backlog": (
                self.batch_sync.get_backlog_count() if self.batch_sync else 0
            ),
            "cpu_temp": self.thermal_monitor.current_temp_celsius,
            "recovery_was_crash": (
                self.boot_recovery.was_crash if self.boot_recovery else False
            ),
            "recovery_complete": (
                self.boot_recovery.recovery_complete.is_set() if self.boot_recovery else True
            ),
            "recovery_orphans_closed": (
                self.boot_recovery.orphans_closed if self.boot_recovery else 0
            ),
            # Trip tracking — progress is rally-leg only so the return-leg
            # waypoints (drive home) don't pollute the status screen count.
            # _reached_waypoints still tracks all crossings for announcement dedup.
            "odometer_km": round(self._odometer_km, 1),
            "daily_km": round(self._daily_km, 1),
            **self._rally_waypoint_progress(),
        }

    def _rally_waypoint_progress(self) -> dict:
        rally_indices = {
            i for i, w in enumerate(self.config.route_waypoints)
            if getattr(w, "leg", "rally") == "rally"
        }
        return {
            "waypoints_reached": len(self._reached_waypoints & rally_indices),
            "waypoints_total": len(rally_indices),
        }

    def _read_system_status(self) -> Optional[Reading]:
        """Get system status reading (Pi temp, etc)."""
        cpu_temp = self._read_pi_temp()
        if cpu_temp is None:
            return None

        return Reading(
            timestamp_utc=datetime.now(timezone.utc),
            sensor_type=SensorType.SYSTEM,
            cpu_temp_celsius=cpu_temp,
        )

    def _telemetry_loop(self) -> None:
        """Low-rate telemetry logging loop (1 Hz)."""
        last_telemetry = 0.0
        last_cleanup = time.monotonic()

        while self._running:
            try:
                now = time.monotonic()

                # Telemetry at configured interval
                if (now - last_telemetry) >= self.config.telemetry_interval_seconds:
                    self._record_telemetry()
                    # Auto-zero tick (IMU-05). Reads the ring buffer on window
                    # completion; wrapped so it can never crash the telemetry
                    # thread (T-22-06).
                    try:
                        self._maybe_auto_zero()
                    except Exception as e:
                        log.error("auto_zero_error", error=str(e))
                    last_telemetry = now

                # Check for completed event captures
                self._check_post_captures()

                # Timelapse capture when moving
                self._check_timelapse(now)

                # Periodic cleanup (every hour)
                if (now - last_cleanup) >= 3600:
                    self._do_cleanup()
                    last_cleanup = now

                # WAL TRUNCATE checkpoint every 5 minutes
                if (now - self._last_wal_checkpoint) >= self.WAL_CHECKPOINT_INTERVAL_S:
                    try:
                        self.database.checkpoint_wal()
                    except Exception as e:
                        log.error("wal_checkpoint_error", error=str(e))
                    self._last_wal_checkpoint = now
            except Exception as e:
                log.error("telemetry_loop_error", error=str(e))

            time.sleep(0.1)

    def _record_telemetry(self) -> None:
        """Record one telemetry cycle to SQLite and MQTT."""
        readings = []

        # GPS reading
        if self.config.gps_enabled:
            gps_reading = self._read_gps()
            if gps_reading:
                self._gps_has_fix = True
                readings.append(gps_reading)
                if gps_reading.speed_kmh is not None:
                    speed = gps_reading.speed_kmh if gps_reading.speed_kmh >= 3.0 else 0.0
                    self._current_speed_kmh = speed
                self._current_lat = gps_reading.latitude
                self._current_lon = gps_reading.longitude
                self._current_heading = gps_reading.heading_deg
                self._current_altitude = gps_reading.altitude_m
                self._current_satellites = gps_reading.satellites
                # Resolve location name from coordinates
                if gps_reading.latitude is not None and gps_reading.longitude is not None:
                    gps_state.update_last_known_position(
                        gps_reading.latitude, gps_reading.longitude
                    )
                    self._resolve_location(gps_reading.latitude, gps_reading.longitude)
                    self._distance_from_start_km = self._haversine_km(
                        self.config.rally_start_lat, self.config.rally_start_lon,
                        gps_reading.latitude, gps_reading.longitude,
                    )
                    self._distance_to_destination_km = self._haversine_km(
                        gps_reading.latitude, gps_reading.longitude,
                        self.config.rally_destination_lat, self.config.rally_destination_lon,
                    )
                    # Odometer: accumulate distance only when speed >= 5 km/h
                    if (
                        gps_reading.speed_kmh is not None
                        and gps_reading.speed_kmh >= 5.0
                    ):
                        if self._last_known_lat is not None:
                            delta_km = self._haversine_km(
                                self._last_known_lat, self._last_known_lon,  # type: ignore[arg-type]
                                gps_reading.latitude, gps_reading.longitude,
                            )
                            # Reject implausible deltas (> 1 km/s = 3600 km/h)
                            if delta_km <= 1.0:
                                self._odometer_km += delta_km
                                self._daily_km += delta_km
                                # Distance announcement at configurable interval
                                announce_interval = (
                                    self.config.speaker_distance_announce_interval_km
                                )
                                if announce_interval > 0 and (
                                    self._daily_km // announce_interval
                                    > self._last_announced_km // announce_interval
                                ):
                                    speaker.speak_distance_update(int(self._daily_km))
                                    self._last_announced_km = self._daily_km
                        self._last_known_lat = gps_reading.latitude
                        self._last_known_lon = gps_reading.longitude

                    # Persist odometer every 60 seconds
                    now_mono = time.monotonic()
                    if (now_mono - self._last_trip_persist) >= TRIP_PERSIST_INTERVAL_S:
                        try:
                            self.database.set_trip_state("odometer_km", self._odometer_km)
                            self.database.set_trip_state("daily_km", self._daily_km)
                        except Exception as e:
                            log.error("trip_state_persist_error", error=str(e))
                        self._last_trip_persist = now_mono

                    # Waypoint detection (regardless of speed)
                    self._check_waypoints(gps_reading.latitude, gps_reading.longitude)
            else:
                self._gps_has_fix = False

        # IMU snapshot
        imu_reading = self._read_imu_snapshot()
        if imu_reading:
            readings.append(imu_reading)

        # Power reading — v2 INA226 runs in its own collector thread (callback-driven);
        # no polling needed here.

        # Environment reading
        if self._environment_collector:
            try:
                env_data = self._environment_collector.read()
                if env_data:
                    env_reading = self._environment_collector.to_reading(env_data)
                    readings.append(env_reading)
                    if env_reading.env_temp_celsius is not None:
                        self._cabin_temp_c = env_reading.env_temp_celsius
            except Exception as e:
                log.error("environment_read_error", error=str(e))

        # System status (Pi health: cpu temp, disk, sync backlog, throttle flags)
        if self._health_collector is not None:
            try:
                system_reading = self._health_collector.collect()
                if system_reading:
                    readings.append(system_reading)
            except Exception as e:
                log.error("health_collector_error", error=str(e))
        else:
            # Fallback before start() completes
            system_reading = self._read_system_status()
            if system_reading:
                readings.append(system_reading)

        # Store to SQLite and publish to MQTT
        for reading in readings:
            try:
                self.database.insert_reading(reading)
                self.telemetry_readings += 1
            except Exception as e:
                log.error("database_store_error", error=str(e))

            if self.mqtt and self.mqtt.is_connected:
                try:
                    self.mqtt.publish_reading(reading)
                except Exception as e:
                    log.error("mqtt_publish_error", error=str(e))

        # Update video HUD overlay text files
        if self.config.overlay_enabled and self.video_ring_buffer:
            self._update_overlay()

    def _load_persisted_offsets(self) -> None:
        """Boot path: persisted accel offsets override the config seed. IMU-06.

        Called from ``start()`` BEFORE ``self.sampler.start()`` so the sampler
        thread never samples with stale config seeds when trip_state holds a
        better calibration from a previous drive.

        Partial persistence (one or two axes missing from trip_state but others
        present) falls back to the config seed per missing axis. A full-miss
        (all three None) is a clean no-op — the sampler keeps the seed it was
        constructed with and ``_current_accel_offsets`` stays at the seed.

        Database read failures are logged and swallowed — the sampler still
        starts on the config seed rather than blocking boot.
        """
        try:
            x = self.database.get_trip_state("accel_offset_x")
            y = self.database.get_trip_state("accel_offset_y")
            z = self.database.get_trip_state("accel_offset_z")
        except Exception as e:
            log.warning("autozero_offset_load_failed", error=str(e))
            return

        if x is None and y is None and z is None:
            log.info(
                "autozero_no_persisted_offsets",
                seed_x=self.config.accel_offset_x,
                seed_y=self.config.accel_offset_y,
                seed_z=self.config.accel_offset_z,
            )
            return

        fx = x if x is not None else self.config.accel_offset_x
        fy = y if y is not None else self.config.accel_offset_y
        fz = z if z is not None else self.config.accel_offset_z
        self.sampler.update_offsets(fx, fy, fz)
        self._current_accel_offsets = (fx, fy, fz)
        source = "trip_state" if (x is not None and y is not None and z is not None) else "mixed"
        log.info(
            "autozero_offsets_loaded",
            ax=round(fx, 4),
            ay=round(fy, 4),
            az=round(fz, 4),
            source=source,
        )

    def _maybe_auto_zero(self) -> None:
        """Stationary auto-zero state machine. Called once per telemetry tick (1 Hz).

        Implements IMU-05 guards:
          - GPS fix AND speed below stationary gate (both required)
          - Minimum 600 samples in window (= 20 Hz x 30 s — sized to actual
            sustained Pi rate ~22 Hz, not the 25 Hz configured target. Pi UAT
            on 2026-04-22 showed steady ~22 sps with spike windows down to ~18,
            so the previous 750 floor (25 x 30) blocked auto-zero in normal
            operation; 600 catches a real degraded window without being noise.)
          - Per-sample raw combined-g reject (any sample magnitude > motion_reject_g)
          - Per-axis window stddev reject (any stddev > motion_stddev_g)
          - Absolute offset plausibility cap (max abs > max_abs_g)
          - Tolerance gate vs current live offsets (skipped on bootstrap)

        IMU-06: first accept per boot is unconditional (bootstrap rule) so a
        cold start with a drifted sensor can self-correct once without
        operator action.

        Threat refs: T-22-03, T-22-04, T-22-06.
        """
        cfg = self.config
        if not cfg.auto_zero_enabled:
            return

        # Gate 1: GPS fix AND speed (both must pass — Checker Issue 5).
        # Speed=0 with a missing fix is treated as not-stationary.
        if not self._gps_has_fix:
            self._stationary_elapsed_s = 0.0
            return
        if (
            self._current_speed_kmh is None
            or self._current_speed_kmh >= cfg.auto_zero_stationary_kmh
        ):
            self._stationary_elapsed_s = 0.0
            return

        # Advance the stationary timer. Only evaluate the window once we've
        # accumulated enough stationary elapsed time at 1 Hz cadence.
        self._stationary_elapsed_s += 1.0
        if self._stationary_elapsed_s < cfg.auto_zero_window_seconds:
            return

        # Reset counter for the next attempt (regardless of outcome).
        self._stationary_elapsed_s = 0.0

        # Pull the window from the ring buffer. 600-sample floor = 20 Hz x 30 s,
        # sized to observed sustained rate (~22 sps) rather than the 25 Hz configured
        # target. Pi UAT on 2026-04-22 showed the 750 floor (target x window) blocked
        # auto-zero during normal operation because the loop runs ~12% behind whatever
        # target you give it (88% efficiency). Acceptance floor per IMU-02 stays at
        # 10 Hz; this 600 keeps healthy operation passing while still rejecting truly
        # degraded ring-buffer or sensor conditions.
        samples = self.ring_buffer.get_window(cfg.auto_zero_window_seconds)
        min_samples = 600
        if len(samples) < min_samples:
            log.info(
                "auto_zero_rejected",
                reason="insufficient_samples",
                sample_count=len(samples),
                min_required=min_samples,
            )
            return

        # Compute means first — both per-axis stddev and the per-sample
        # "sudden-move" gate are defined against the window mean (deviation-
        # from-mean), not raw magnitude. Raw magnitude of a stationary sample
        # is ~1 g (gravity), which would always trip a 0.2 g gate. The real
        # intent of IMU-05 / RESEARCH Pitfall 5 is to catch single-sample
        # bumps on top of an otherwise-quiet stationary window; that only
        # makes physical sense as deviation-from-mean. (Plan behaviour spec
        # test data assumed gravity-bearing samples pass per-sample gate —
        # that only holds if per-sample is measured as deviation-from-mean.
        # Deviation documented in SUMMARY under Rule 1.)
        n = len(samples)
        mean_x = sum(s.ax for s in samples) / n
        mean_y = sum(s.ay for s in samples) / n
        mean_z = sum(s.az for s in samples) / n
        sd_x = (sum((s.ax - mean_x) ** 2 for s in samples) / n) ** 0.5
        sd_y = (sum((s.ay - mean_y) ** 2 for s in samples) / n) ** 0.5
        sd_z = (sum((s.az - mean_z) ** 2 for s in samples) / n) ** 0.5

        # Gate 3: per-sample deviation-from-mean reject (IMU-05 / RESEARCH
        # Pitfall 5, Checker Issue 2). Any sample more than motion_reject_g
        # away from the window mean means the car wasn't actually stationary
        # for the whole window — a transient bump from the engine bay, road
        # settling, or a passenger shifting weight.
        reject_g = cfg.auto_zero_motion_reject_g
        for s in samples:
            dx_s = s.ax - mean_x
            dy_s = s.ay - mean_y
            dz_s = s.az - mean_z
            mag = math.sqrt(dx_s * dx_s + dy_s * dy_s + dz_s * dz_s)
            if mag > reject_g:
                log.info(
                    "auto_zero_rejected",
                    reason="motion_sample",
                    max_magnitude_g=round(mag, 4),
                    threshold_g=reject_g,
                )
                return

        # Gate 4: per-axis window stddev reject (separate from per-sample gate).
        if max(sd_x, sd_y, sd_z) > cfg.auto_zero_motion_stddev_g:
            log.info(
                "auto_zero_rejected",
                reason="motion_stddev",
                stddev_x=round(sd_x, 4),
                stddev_y=round(sd_y, 4),
                stddev_z=round(sd_z, 4),
            )
            return

        # Gate 5: implausibility cap (T-22-03, applies even during bootstrap).
        # Parked on a steep slope, sensor fault, etc. must not poison the
        # calibration even on a fresh boot. Z axis carries ~1 g gravity in
        # the car's installed orientation; the cap applies to drift-from-
        # gravity on z, not raw z. That matches the plan's test 10
        # behaviour (reject mean (0.9, 0.1, 1.05) — x=0.9 is the offender
        # not z=1.05 which is ~gravity). residual_z is also what we persist
        # — the sampler subtracts accel_offset_z raw from every read, so the
        # stored value must be the gravity-corrected bias residual or
        # stationary reads lose gravity entirely.
        residual_z = mean_z - 1.0
        if max(abs(mean_x), abs(mean_y), abs(residual_z)) > cfg.auto_zero_max_abs_g:
            log.warning(
                "auto_zero_rejected",
                reason="implausible",
                mean_x=round(mean_x, 4),
                mean_y=round(mean_y, 4),
                mean_z=round(mean_z, 4),
            )
            return

        # Gate 6: tolerance against current live offsets (skipped on bootstrap).
        # Compared in residual (gravity-corrected) space on Z because that's
        # the space _current_accel_offsets lives in.
        if self._autozero_bootstrap_done:
            cur_x, cur_y, cur_z = self._current_accel_offsets
            dx = abs(mean_x - cur_x)
            dy = abs(mean_y - cur_y)
            dz = abs(residual_z - cur_z)
            if max(dx, dy, dz) > cfg.auto_zero_tolerance_g:
                log.info(
                    "auto_zero_rejected",
                    reason="tolerance",
                    delta_x=round(dx, 4),
                    delta_y=round(dy, 4),
                    delta_z=round(dz, 4),
                )
                return

        # Accept path with rollback on persistence failure (T-22-06).
        prev_offsets = self._current_accel_offsets
        try:
            self.sampler.update_offsets(mean_x, mean_y, residual_z)
            self._current_accel_offsets = (mean_x, mean_y, residual_z)
            self.database.set_trip_state("accel_offset_x", mean_x)
            self.database.set_trip_state("accel_offset_y", mean_y)
            self.database.set_trip_state("accel_offset_z", residual_z)
        except Exception as e:
            # Rollback so the next window starts from a known-good baseline.
            self._current_accel_offsets = prev_offsets
            try:
                self.sampler.update_offsets(*prev_offsets)
            except Exception:
                pass  # rollback failure is already logged upstream
            log.error(
                "auto_zero_persist_failed",
                error=str(e),
                attempted_x=round(mean_x, 4),
                attempted_y=round(mean_y, 4),
                attempted_z=round(residual_z, 4),
            )
            return

        was_bootstrap = not self._autozero_bootstrap_done
        self._autozero_bootstrap_done = True
        log.info(
            "auto_zero_accepted",
            ax=round(mean_x, 4),
            ay=round(mean_y, 4),
            az=round(residual_z, 4),
            bootstrap=was_bootstrap,
            sample_count=n,
        )

    def _check_waypoints(self, lat: float, lon: float) -> None:
        """Check whether the current position is within 5 km of any unreached waypoint.

        Args:
            lat: Current latitude.
            lon: Current longitude.
        """
        for i, waypoint in enumerate(self.config.route_waypoints):
            if i in self._reached_waypoints:
                continue
            dist_km = self._haversine_km(lat, lon, waypoint.lat, waypoint.lon)
            if dist_km <= 5.0:
                self._reached_waypoints.add(i)
                try:
                    self.database.record_waypoint_reached(i, waypoint.name, lat, lon)
                except Exception as e:
                    log.error("waypoint_persist_error", index=i, error=str(e))
                log.info(
                    "waypoint_reached",
                    name=waypoint.name,
                    day=waypoint.day,
                    distance_km=round(dist_km, 2),
                )
                speaker.speak_waypoint_reached(waypoint.name, waypoint.day)

    def _update_overlay(self) -> None:
        """Write overlay text files for ffmpeg drawtext filters."""
        g_lat = 0.0
        g_lon = 0.0
        samples = self.ring_buffer.get_latest(1)
        if samples:
            s = samples[0]
            g_lat = s.ay  # lateral (left/right cornering)
            g_lon = s.ax  # longitudinal (braking/acceleration)

        overlay.update(
            speed=self._current_speed_kmh if self._current_speed_kmh else None,
            g_lat=g_lat,
            g_lon=g_lon,
            heading=self._current_heading,
            lat=self._current_lat,
            lon=self._current_lon,
            location_name=self._current_location_name,
            distance_from_start_km=self._distance_from_start_km,
            distance_to_destination_km=self._distance_to_destination_km,
        )

    def _check_timelapse(self, now: float) -> None:
        """Capture timelapse image if moving and interval elapsed."""
        if not self.config.timelapse_enabled:
            return

        has_capture_source = self.video_ring_buffer or self.video_recorder
        if not has_capture_source:
            return

        # Gap watchdog: detect stuck timelapse extraction
        elapsed = now - self._last_timelapse_time
        gap_threshold = self.config.timelapse_interval_seconds * UnifiedEngine.TIMELAPSE_GAP_FACTOR
        if (
            elapsed > gap_threshold
            and self._last_timelapse_time > 0.0
            and self._current_speed_kmh >= self.config.timelapse_min_speed_kmh
        ):
            log.warning(
                "timelapse_gap_detected",
                elapsed_seconds=round(elapsed),
                expected_interval=self.config.timelapse_interval_seconds,
            )
            # Don't restart ffmpeg here — ring_buffer health monitor owns restarts.
            # Killing from two threads simultaneously caused double-start races and
            # "Device or resource busy" cascades.
            self._last_timelapse_time = now  # Reset to avoid repeat alerts
            return  # Skip normal capture this iteration

        # Check if enough time has passed
        if (now - self._last_timelapse_time) < self.config.timelapse_interval_seconds:
            return

        # Check if we're moving fast enough
        if self._current_speed_kmh < self.config.timelapse_min_speed_kmh:
            return

        # Capture frame from ring buffer or camera directly
        path: Optional[Path] = None
        if self.video_ring_buffer and self.video_ring_buffer.is_running:
            path = self.video_ring_buffer.capture_frame()
        elif self.video_recorder:
            # Don't capture during video recording (camera busy)
            if self.video_recorder.is_recording:
                return
            path = self.video_recorder.capture_image()

        if path:
            self.timelapse_images += 1
            self._last_timelapse_time = now
            log.debug(
                "timelapse_captured",
                image_number=self.timelapse_images,
                speed_kmh=round(self._current_speed_kmh, 1),
            )

    def _do_cleanup(self) -> None:
        """Run periodic cleanup tasks."""
        # fake-hwclock sync is not destructive — always runs so reboots start
        # with a recent time even when data cleanup is disabled.
        self._sync_fake_hwclock()

        # Data-deletion cleanups are disabled by default — the 14-day age-out
        # would silently nuke saved events and capture videos that we want to
        # keep on the live site indefinitely. Re-enable via
        # cleanup_old_data_enabled=true once a retention strategy that keeps
        # the things we care about is in place. Methods kept intact.
        if not self.config.cleanup_old_data_enabled:
            log.debug(
                "data_cleanup_skipped",
                reason="cleanup_old_data_enabled=false",
            )
            return

        try:
            self.event_storage.cleanup_old_events()
            self.event_storage.cleanup_by_size()
        except Exception as e:
            log.error("cleanup_error", error=str(e))

        # Clean up old video captures
        if self.video_ring_buffer:
            try:
                self.video_ring_buffer.cleanup_old_saves(
                    max_age_days=self.config.max_capture_age_days
                )
            except Exception as e:
                log.error("video_cleanup_error", error=str(e))
        elif self.video_recorder:
            try:
                self.video_recorder.cleanup_old_captures(
                    max_age_days=self.config.max_capture_age_days
                )
            except Exception as e:
                log.error("video_cleanup_error", error=str(e))

    def start(self) -> None:
        """Start the unified engine."""
        if self._running:
            return

        self._engine_start_time = time.monotonic()

        log.info(
            "unified_engine_starting",
            imu_rate=self.config.imu_sample_rate_hz,
            telemetry_interval=self.config.telemetry_interval_seconds,
            mqtt=self.config.mqtt_enabled,
            prometheus=self.config.prometheus_enabled,
        )

        self._running = True

        # --- Boot recovery: detect crash BEFORE database.connect() creates the WAL ---
        was_crash = detect_unclean_shutdown(self.database.db_path)
        if was_crash:
            log.info("unclean_shutdown_detected", db_path=str(self.database.db_path))

        # Initialise database (this creates the WAL file — detection must be above)
        self.database.connect()

        # Load persisted trip state
        self._odometer_km = self.database.get_trip_state("odometer_km") or 0.0
        self._daily_km = self.database.get_trip_state("daily_km") or 0.0

        # Reset daily distance on AEST day boundary
        stored_date = self.database.get_trip_state_text("daily_reset_date")
        today_aest = _current_aest_date()
        if stored_date != today_aest:
            self._daily_km = 0.0
            self._last_announced_km = 0.0
            self.database.set_trip_state("daily_km", 0.0)
            self.database.set_trip_state_text("daily_reset_date", today_aest)
            log.info("daily_distance_reset", new_date=today_aest)

        # Load reached waypoints
        self._reached_waypoints = self.database.get_reached_waypoints()

        # Start boot recovery in background (does not block data capture)
        self.boot_recovery = BootRecoveryService(self.database, self.event_storage)
        self.boot_recovery.was_crash = was_crash
        self.boot_recovery.start()

        def _send_boot_metric() -> None:
            """Send boot_was_crash gauge after recovery completes."""
            if self.boot_recovery is None:
                return
            self.boot_recovery.recovery_complete.wait(timeout=30)
            try:
                import time as _time

                from shitbox.sync.prometheus_write import encode_remote_write

                metric_value = 1.0 if self.boot_recovery.was_crash else 0.0
                timestamp_ms = int(_time.time() * 1000)
                metrics = [
                    (
                        "shitbox_boot_was_crash",
                        {"instance": "shitbox-car", "car": "shitbox"},
                        metric_value,
                        timestamp_ms,
                    )
                ]
                if (
                    self.config.prometheus_enabled
                    and self.config.uplink_enabled
                    and self.config.prometheus_remote_write_url
                    and self.connection.is_connected
                ):
                    import requests

                    data = encode_remote_write(metrics)
                    requests.post(
                        self.config.prometheus_remote_write_url,
                        data=data,
                        headers={
                            "Content-Type": "application/x-protobuf",
                            "Content-Encoding": "snappy",
                            "X-Prometheus-Remote-Write-Version": "0.1.0",
                        },
                        timeout=10,
                    )
                    log.info("boot_metric_sent", was_crash=self.boot_recovery.was_crash)
            except Exception as e:
                log.warning("boot_metric_send_failed", error=str(e))

        threading.Thread(target=_send_boot_metric, daemon=True, name="boot-metric").start()

        # Initialise GPS and wait for fix (up to 20 seconds)
        if self.config.gps_enabled:
            self._init_gps()
            if self._gps_available:
                self._wait_for_gps_fix()

        # Initialise environment sensor
        if self._environment_collector:
            try:
                self._environment_collector.setup()
                log.info("environment_sensor_ready")
            except Exception as e:
                log.error("environment_sensor_setup_failed", error=str(e))
                self._environment_collector = None

        # Start connection monitor
        if self.config.uplink_enabled:
            self.connection.start()

        # Start MQTT
        if self.mqtt:
            self.mqtt.connect()

        # Start batch sync
        if self.batch_sync:
            self.batch_sync.start()

        # Start capture sync
        if self.capture_sync:
            self.capture_sync.start()

        # Start TPMS service (Phase 28) and register the snapshot
        # provider so /sse/slow's _tpms_payload can render four wheel
        # rows. The dashboard import is local to keep engine import
        # cheap when the dashboard module isn't loaded.
        if self.tpms:
            self.tpms.start()
            try:
                from shitbox.dashboard import sse as dashboard_sse
                dashboard_sse.set_tpms_service(self.tpms)
            except Exception as e:
                log.warning("tpms_dashboard_register_failed", error=str(e))

        # Start timelapse compiler (non-blocking background compilation)
        if self.timelapse_compiler:
            self.timelapse_compiler.start()

        # Start thermal monitor
        self.thermal_monitor.start()

        # Start live dashboard (after thermal monitor; before sampler so
        # the snapshot starts getting populated as soon as IMU comes up).
        if self._dashboard is not None:
            try:
                self._dashboard.start()
            except Exception as exc:
                log.error("dashboard_start_failed", error=str(exc))

        # Instantiate health collector (thermal_monitor and batch_sync now ready)
        data_dir = str(Path(self.config.database_path).parent)
        self._health_collector = HealthCollector(
            thermal_monitor=self.thermal_monitor,
            batch_sync=self.batch_sync,
            data_dir=data_dir,
        )

        # Start hardware supervisor BEFORE any collectors so the tick loop is
        # running when collector hooks fire their first report_present/missing calls.
        self.supervisor.start()
        log.info("hardware_supervisor_started")

        # Start OLED display
        if self.oled_display:
            self.oled_display.start()

        # Initialise overlay text files before ffmpeg starts
        if self.config.overlay_enabled and self.video_ring_buffer:
            overlay.init()

        # Start video ring buffers (primary + PIP) — graceful so a missing
        # camera device does not prevent the rest of the engine from booting.
        started: dict[str, bool] = {}
        if self.video_ring_buffer:
            started["camera_front"] = self._start_service_graceful(
                "video_ring_buffer", self.video_ring_buffer.start
            )

        # IMU-06: load persisted accel offsets BEFORE the sampler thread
        # starts so the sampler samples with the correct offsets from the
        # very first tick. Pulling from trip_state overrides the static
        # config seed when a previous drive's auto-zero accepted a better
        # calibration. Safe to call even if trip_state is empty — falls
        # back to config seed silently.
        self._load_persisted_offsets()

        # Start high-rate sampler — graceful per HW-05. A setup() failure here
        # is caught and logged; _force_reboot remains reachable only from the
        # runtime i2c_max_resets ladder inside the sampler, not from boot-time
        # setup failure (pitfall 5).
        started["imu"] = self._start_service_graceful("imu_sampler", self.sampler.start)

        # Start v2 sensor collectors (phase 11) — graceful per HW-05
        started["light"] = self._start_service_graceful(
            "light_collector",
            self._light_collector.start if self._light_collector else lambda: None,
        )
        started["power"] = self._start_service_graceful(
            "power_collector",
            self._ina226_collector.start if self._ina226_collector else lambda: None,
        )
        for collector in (
            self._ds18b20_collector,
            self._particulate_collector,
            self._imu_heading_collector,
        ):
            if collector is not None:
                self._start_service_graceful(collector.name, collector.start)

        log.info("unified_engine_started", collectors=started)

        # Start telemetry loop
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop, daemon=True
        )
        self._telemetry_thread.start()

        # Start button handler (if GPIO available)
        if self.button_handler:
            self.button_handler.start()

        # Initialise buzzer
        if self.config.buzzer_enabled:
            buzzer.init()
            buzzer.set_boot_start_time(time.monotonic())
            buzzer.beep_boot()
            # Recovery-specific beep after boot tone
            if self.boot_recovery and self.boot_recovery.was_crash:
                buzzer.beep_crash_recovery()
            else:
                buzzer.beep_clean_boot()

        # Initialise speaker (after buzzer so boot tones precede spoken announcement)
        if self.config.speaker_enabled:
            self._notify_systemd("WATCHDOG=1")  # Piper model load takes ~5-7s
            speaker.init(self.config.speaker_model_path, volume=self.config.speaker_volume)
            speaker.set_boot_start_time(time.monotonic())
            was_crash = self.boot_recovery.was_crash if self.boot_recovery else False
            speaker.speak_boot(was_crash=was_crash)

        # Regenerate events.json from any previously stored events
        try:
            self.event_storage.generate_events_json()
        except Exception as e:
            log.warning("events_json_boot_generate_error", error=str(e))

        # Boot capture — wait for the ring buffer to accumulate enough
        # segments before firing, since ffmpeg needs startup time for
        # camera detection, audio fallback, and PiP compositor setup.
        if self.video_ring_buffer and self.video_ring_buffer.is_running:
            threading.Thread(
                target=self._fire_boot_capture, daemon=True, name="boot-capture"
            ).start()

        log.info("unified_engine_started")

    def _fire_boot_capture(self) -> None:
        """Wait for ring buffer segments then fire a BOOT event.

        Runs in a daemon thread. Returns without firing if the deadline
        expires before enough segments are available on disk.
        """
        ring = self.video_ring_buffer
        assert ring is not None
        seg_seconds = self.config.video_buffer_segment_seconds
        deadline_seconds = seg_seconds * 5
        deadline = time.monotonic() + deadline_seconds
        log.info(
            "boot_capture_waiting",
            deadline_seconds=deadline_seconds,
            segment_seconds=seg_seconds,
            buffer_dir=str(ring.buffer_dir),
        )
        while time.monotonic() < deadline:
            segments = ring._get_buffer_segments()
            if len(segments) >= 2:
                log.info(
                    "boot_capture_segments_ready",
                    segment_count=len(segments),
                )
                break
            time.sleep(2.0)
        else:
            segments = ring._get_buffer_segments()
            log.warning(
                "boot_capture_skipped",
                reason="deadline_expired",
                segment_count=len(segments),
                deadline_seconds=deadline_seconds,
            )
            return

        boot_now = time.time()
        boot_event = Event(
            event_type=EventType.BOOT,
            start_time=boot_now,
            end_time=boot_now,
            peak_value=0.0,
            peak_ax=0.0,
            peak_ay=0.0,
            peak_az=0.0,
        )
        self._on_event(boot_event)
        log.info("boot_capture_triggered")

    def stop(self) -> None:
        """Stop the unified engine."""
        log.info("unified_engine_stopping")

        self._running = False

        # Stop dashboard FIRST so it releases its port before anything else.
        # Dashboard failures here must never prevent the rest of the shutdown.
        if self._dashboard is not None:
            try:
                self._dashboard.stop()
            except Exception as exc:
                log.error("dashboard_stop_failed", error=str(exc))

        # Stop OLED display early so it can show final state
        if self.oled_display:
            self.oled_display.stop()

        # Stop button handler
        if self.button_handler:
            self.button_handler.stop()

        # Stop video ring buffers and active recording
        if self.video_ring_buffer:
            self.video_ring_buffer.stop()
        if self.video_recorder and self.video_recorder.is_recording:
            self.video_recorder.stop_recording()

        # Clean up overlay text files
        if self.config.overlay_enabled:
            overlay.cleanup()

        # Clean up buzzer and speaker
        buzzer.cleanup()
        speaker.cleanup()

        # Stop components
        self.sampler.stop()

        # Stop v2 sensor collectors (phase 11)
        for collector in (
            self._ds18b20_collector,
            self._light_collector,
            self._particulate_collector,
            self._ina226_collector,
            self._imu_heading_collector,
        ):
            if collector is not None:
                try:
                    collector.stop()
                except Exception as e:
                    log.error("v2_collector_stop_failed", collector=collector.name, error=str(e))

        if self.batch_sync:
            self.batch_sync.stop()

        if self.capture_sync:
            self.capture_sync.stop()

        if self.tpms:
            self.tpms.stop()
            try:
                from shitbox.dashboard import sse as dashboard_sse
                dashboard_sse.set_tpms_service(None)
            except Exception:
                pass

        if self.timelapse_compiler:
            self.timelapse_compiler.stop()

        self.thermal_monitor.stop()

        if self.mqtt:
            self.mqtt.disconnect()

        if self._environment_collector:
            self._environment_collector.cleanup()

        if self._gps is not None:
            try:
                self._gps.stop()
            except Exception as e:
                log.error("gps_client_stop_failed", error=str(e))

        self.connection.stop()

        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=2.0)

        # Save any pending events
        with self._pending_lock:
            pending_shutdown = list(self._pending_post_capture.values())
        for pending in pending_shutdown:
            try:
                self.event_storage.save_event(
                    pending["event"],
                    driver_name=driver_state.get_active_driver(),
                    poster_path=None,  # shutdown flush: no slate render path
                )
            except Exception as e:
                log.error("event_save_error_on_shutdown", error=str(e))

        log.info(
            "unified_engine_stopped",
            telemetry_readings=self.telemetry_readings,
            events_captured=self.events_captured,
            timelapse_images=self.timelapse_images,
            imu_samples=self.sampler.samples_total,
            imu_dropped=self.sampler.samples_dropped,
        )

        # Stop hardware supervisor LAST so final MISSING transitions during
        # teardown are still observed by the tick loop.
        try:
            self.supervisor.stop()
            log.info("hardware_supervisor_stopped")
        except Exception as e:
            log.error("hardware_supervisor_stop_failed", error=str(e))

    def run(self) -> None:
        """Run until interrupted."""
        def signal_handler(signum, frame):
            log.info("received_signal", signal=signum)
            self._running = False

        def capture_signal_handler(signum, frame):
            log.info("manual_capture_signal_received")
            self.trigger_manual_capture()

        def test_alert_handler(signum, frame):
            log.info("test_alert_signal_received")
            buzzer.beep_capture_start()
            speaker.speak_capture_start("high_g")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGUSR1, capture_signal_handler)
        signal.signal(signal.SIGUSR2, test_alert_handler)

        # Notify systemd we're ready
        self._notify_systemd("READY=1")

        self.start()

        # Main loop with watchdog
        while self._running:
            self._notify_systemd("WATCHDOG=1")
            now = time.monotonic()
            elapsed = now - self._engine_start_time
            if elapsed > self.HEALTH_GRACE_PERIOD:
                if (now - self._last_health_time) >= self.HEALTH_CHECK_INTERVAL:
                    self._health_check()
                    self._last_health_time = now
            time.sleep(1.0)

        self.stop()

    def _health_check(self) -> None:
        """Check subsystem health and attempt recovery."""
        issues: list[str] = []
        recovered: list[str] = []

        # 1. IMU sampler data flow
        current_count = self.sampler.samples_total
        if current_count == self._last_sample_count:
            if self.sampler._thread and self.sampler._thread.is_alive():
                log.warning("imu_sampler_stalled", samples_total=current_count)
                issues.append("imu_stalled")
            else:
                log.error("imu_sampler_thread_dead", restarting=True)
                issues.append("imu_thread_dead")
                try:
                    self.sampler.stop()
                    self.sampler.start()
                    recovered.append("imu_sampler")
                except Exception as e:
                    log.error("imu_sampler_restart_failed", error=str(e))
        self._last_sample_count = current_count

        # 2. Telemetry thread
        if self._telemetry_thread and not self._telemetry_thread.is_alive():
            log.error("telemetry_thread_dead", restarting=True)
            issues.append("telemetry_thread_dead")
            self._telemetry_thread = threading.Thread(
                target=self._telemetry_loop, daemon=True
            )
            self._telemetry_thread.start()
            recovered.append("telemetry_thread")

        # 3. Video ring buffer
        if self.video_ring_buffer and not self.video_ring_buffer.is_running:
            log.error("video_ring_buffer_dead", restarting=True)
            issues.append("video_ring_buffer_dead")
            try:
                self.video_ring_buffer.stop()
                self.video_ring_buffer.start()
                recovered.append("video_ring_buffer")
            except Exception as e:
                log.error("video_ring_buffer_restart_failed", error=str(e))

        # 4. GPS reconnection
        if self.config.gps_enabled and not self._gps_available:
            issues.append("gps_unavailable")
            if self._init_gps():
                recovered.append("gps")

        # 5. Disk space
        try:
            usage = shutil.disk_usage(self.config.captures_dir)
            free_pct = (usage.free / usage.total) * 100.0
            if free_pct < self.DISK_CRITICAL_PCT:
                log.error("disk_space_critical", free_pct=round(free_pct, 1))
                issues.append("disk_critical")
                self._do_cleanup()
            elif free_pct < self.DISK_LOW_PCT:
                log.warning("disk_space_low", free_pct=round(free_pct, 1))
                issues.append("disk_low")
                self._do_cleanup()
        except OSError as e:
            log.warning("disk_usage_check_failed", error=str(e))

        # 6. Speaker worker health (HEAL-01)
        if self.config.speaker_enabled:
            if (
                speaker._voice is not None
                and speaker._worker is not None
                and not speaker._worker.is_alive()
            ):
                log.warning("speaker_worker_dead", restarting=True)
                issues.append("speaker_worker_dead")
                try:
                    speaker.cleanup()
                    if speaker.init(
                        self.config.speaker_model_path, volume=self.config.speaker_volume
                    ):
                        recovered.append("speaker")
                        log.info("speaker_reinitialised")
                    else:
                        log.error("speaker_reinit_failed_no_device")
                except Exception as e:
                    log.error("speaker_reinit_exception", error=str(e))

        # Alarm logic
        if issues:
            self._health_failures += 1
            log.warning(
                "health_check_issues",
                issues=issues,
                consecutive_failures=self._health_failures,
            )
            if self._health_failures >= 2:
                buzzer.beep_alarm()
                speaker.speak_health_alarm()
        else:
            if self._health_failures > 0:
                log.info(
                    "health_check_all_clear",
                    previous_failures=self._health_failures,
                )
            self._health_failures = 0

        if recovered:
            log.info("health_check_recovered", subsystems=recovered)
            buzzer.beep_service_recovered("subsystem")
            speaker.speak_service_recovered()

    @staticmethod
    def _notify_systemd(state: str) -> None:
        """Send notification to systemd."""
        try:
            import os
            import socket as sock

            notify_socket = os.environ.get("NOTIFY_SOCKET")
            if not notify_socket:
                return

            s = sock.socket(sock.AF_UNIX, sock.SOCK_DGRAM)
            try:
                s.connect(notify_socket)
                s.sendall(state.encode())
            finally:
                s.close()
        except Exception:
            pass


def main():
    """Entry point for the unified engine."""
    import argparse

    parser = argparse.ArgumentParser(description="Shitbox Unified Telemetry Engine")
    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to config file",
    )
    parser.add_argument(
        "--no-uplink",
        action="store_true",
        help="Disable all network uplink (MQTT, Prometheus)",
    )
    args = parser.parse_args()

    # Load config
    yaml_config = load_config(args.config)
    setup_logging(yaml_config.app.log_level)

    # Create engine config from YAML
    config = EngineConfig.from_yaml_config(yaml_config)

    if args.no_uplink:
        config.uplink_enabled = False

    engine = UnifiedEngine(config)
    engine.run()


if __name__ == "__main__":
    main()
