"""Unified Shitbox Telemetry Engine.

Combines high-rate event detection with low-rate telemetry logging.

High-rate path (100 Hz):
- IMU sampling → ring buffer → event detection → burst storage

Low-rate path (1 Hz):
- GPS, IMU snapshot, temperature → SQLite → MQTT → Prometheus batch sync
"""

import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from shitbox.capture import buzzer, overlay, speaker
from shitbox.capture.button import ButtonHandler
from shitbox.capture.ring_buffer import VideoRingBuffer
from shitbox.capture.video import VideoRecorder
from shitbox.display.oled import OLEDDisplayService
from shitbox.events.detector import DetectorConfig, Event, EventDetector, EventType
from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.events.sampler import HighRateSampler
from shitbox.events.storage import EventStorage
from shitbox.health.health_collector import HealthCollector
from shitbox.health.thermal_monitor import ThermalMonitorService
from shitbox.storage.database import Database
from shitbox.storage.models import Reading, SensorType
from shitbox.sync.batch_sync import BatchSyncService
from shitbox.sync.boot_recovery import BootRecoveryService, detect_unclean_shutdown
from shitbox.sync.capture_sync import CaptureSyncService
from shitbox.sync.connection import ConnectionMonitor
from shitbox.sync.grafana import GrafanaAnnotator
from shitbox.sync.mqtt_publisher import MQTTPublisher
from shitbox.utils.config import (
    CaptureSyncConfig,
    Config,
    GrafanaConfig,
    OLEDConfig,
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

    # High-rate IMU sampling
    imu_sample_rate_hz: float = 100.0
    ring_buffer_seconds: float = 30.0
    i2c_bus: int = 1
    mpu6050_address: int = 0x68
    accel_range: int = 4  # ±4g
    gyro_range: int = 500  # ±500 deg/s

    # Low-rate telemetry
    telemetry_interval_seconds: float = 1.0
    gps_enabled: bool = True
    gps_host: str = "localhost"
    gps_port: int = 2947
    temp_enabled: bool = False
    temp_i2c_address: int = 0x18
    power_enabled: bool = False
    power_i2c_address: int = 0x40
    environment_enabled: bool = False
    environment_i2c_address: int = 0x77

    # Event detection
    detector: DetectorConfig = field(default_factory=DetectorConfig)

    # Event storage
    events_dir: str = "/var/lib/shitbox/events"
    max_event_age_days: int = 14
    max_event_storage_mb: int = 500

    # SQLite storage
    database_path: str = "/var/lib/shitbox/telemetry.db"

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

    # Video ring buffer
    video_buffer_enabled: bool = True
    video_buffer_dir: str = "/var/lib/shitbox/video_buffer"
    video_buffer_segment_seconds: int = 10
    video_buffer_segments: int = 5
    overlay_enabled: bool = True
    video_buffer_intro_video: str = ""

    # Grafana annotations
    grafana_enabled: bool = False
    grafana_url: str = ""
    grafana_api_token: str = ""
    grafana_video_base_url: str = ""
    grafana_timeout_seconds: int = 5

    # Capture sync (rsync to NAS)
    capture_sync_enabled: bool = False
    capture_sync_remote_dest: str = ""
    capture_sync_rsync_path: str = "/opt/bin/rsync"
    capture_sync_interval_seconds: int = 300

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

    # Route waypoints (WaypointConfig objects loaded from YAML)
    route_waypoints: list = field(default_factory=list)

    @classmethod
    def from_yaml_config(cls, config: Config) -> "EngineConfig":
        """Create EngineConfig from the existing YAML config structure."""
        return cls(
            # IMU settings
            i2c_bus=config.sensors.imu.i2c_bus,
            mpu6050_address=config.sensors.imu.address,
            accel_range=config.sensors.imu.accel_range,
            gyro_range=config.sensors.imu.gyro_range,
            # GPS settings
            gps_enabled=config.sensors.gps.enabled,
            gps_host=config.sensors.gps.host,
            gps_port=config.sensors.gps.port,
            # Temp settings
            temp_enabled=config.sensors.temperature.enabled,
            temp_i2c_address=config.sensors.temperature.address,
            # Power settings
            power_enabled=config.sensors.power.enabled,
            power_i2c_address=config.sensors.power.address,
            # Environment settings
            environment_enabled=config.sensors.environment.enabled,
            environment_i2c_address=config.sensors.environment.address,
            # Storage
            database_path=config.storage.database_path,
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
            # Video ring buffer
            video_buffer_enabled=config.capture.video_buffer.enabled,
            video_buffer_dir=config.capture.video_buffer.buffer_dir,
            video_buffer_segment_seconds=config.capture.video_buffer.segment_seconds,
            video_buffer_segments=config.capture.video_buffer.buffer_segments,
            overlay_enabled=config.capture.video_buffer.overlay_enabled,
            video_buffer_intro_video=config.capture.video_buffer.intro_video,
            # Grafana annotations
            grafana_enabled=config.sync.grafana.enabled,
            grafana_url=config.sync.grafana.url,
            grafana_api_token=config.sync.grafana.api_token,
            grafana_video_base_url=config.sync.grafana.video_base_url,
            grafana_timeout_seconds=config.sync.grafana.timeout_seconds,
            # Capture sync
            capture_sync_enabled=config.sync.capture_sync.enabled,
            capture_sync_remote_dest=config.sync.capture_sync.remote_dest,
            capture_sync_rsync_path=config.sync.capture_sync.rsync_path,
            capture_sync_interval_seconds=config.sync.capture_sync.interval_seconds,
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
            # Route waypoints
            route_waypoints=config.sensors.gps.route.waypoints,
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

        # High-rate components
        self.ring_buffer = RingBuffer(
            max_seconds=config.ring_buffer_seconds,
            sample_rate_hz=config.imu_sample_rate_hz,
        )

        self.sampler = HighRateSampler(
            ring_buffer=self.ring_buffer,
            i2c_bus=config.i2c_bus,
            address=config.mpu6050_address,
            sample_rate_hz=config.imu_sample_rate_hz,
            accel_range=config.accel_range,
            gyro_range=config.gyro_range,
            on_sample=self._on_imu_sample,
        )

        self.detector = EventDetector(
            ring_buffer=self.ring_buffer,
            config=config.detector,
            on_event=self._on_event,
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
        self._gps = None
        self._gps_available = False

        # Power collector (lazy init)
        self._power_collector = None
        if config.power_enabled:
            try:
                from shitbox.collectors.power import PowerCollector
                from shitbox.utils.config import PowerConfig

                power_config = PowerConfig(
                    enabled=True,
                    i2c_bus=config.i2c_bus,
                    address=config.power_i2c_address,
                )
                self._power_collector = PowerCollector(power_config)
            except Exception as e:
                log.error("power_collector_init_failed", error=str(e))

        # Environment collector (lazy init)
        self._environment_collector = None
        if config.environment_enabled:
            try:
                from shitbox.collectors.environment import EnvironmentCollector
                from shitbox.utils.config import EnvironmentConfig

                env_config = EnvironmentConfig(
                    enabled=True,
                    i2c_bus=config.i2c_bus,
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
        if config.prometheus_enabled and config.uplink_enabled and config.prometheus_remote_write_url:
            from shitbox.utils.config import PrometheusConfig
            prom_config = PrometheusConfig(
                enabled=True,
                remote_write_url=config.prometheus_remote_write_url,
                batch_size=config.prometheus_batch_size,
                batch_interval_seconds=config.prometheus_batch_interval_seconds,
            )
            self.batch_sync = BatchSyncService(prom_config, self.database, self.connection)

        # Grafana annotator
        self.grafana: Optional[GrafanaAnnotator] = None
        if config.grafana_enabled and config.uplink_enabled and config.grafana_url:
            grafana_config = GrafanaConfig(
                enabled=True,
                url=config.grafana_url,
                api_token=config.grafana_api_token,
                video_base_url=config.grafana_video_base_url,
                timeout_seconds=config.grafana_timeout_seconds,
            )
            self.grafana = GrafanaAnnotator(grafana_config, config.captures_dir)

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
                    device=config.capture_video_device,
                    resolution=config.capture_video_resolution,
                    fps=config.capture_video_fps,
                    audio_device=config.capture_audio_device,
                    segment_seconds=config.video_buffer_segment_seconds,
                    buffer_segments=config.video_buffer_segments,
                    post_event_seconds=int(config.capture_post_seconds),
                    overlay_path=overlay_path,
                    intro_video=config.video_buffer_intro_video,
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

        # State
        self._running = False
        self._telemetry_thread: Optional[threading.Thread] = None
        self._pending_post_capture: dict = {}
        self._event_json_paths: dict[int, Path] = {}
        self._event_video_paths: dict[int, Path] = {}
        self._manual_capture_count = 0
        self._last_timelapse_time = 0.0
        self._last_wal_checkpoint: float = 0.0
        self._current_speed_kmh = 0.0
        self._current_lat: Optional[float] = None
        self._current_lon: Optional[float] = None
        self._current_heading: Optional[float] = None
        self._current_altitude: Optional[float] = None
        self._current_satellites: Optional[int] = None
        self._gps_has_fix = False
        self._clock_synced_from_gps = False
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

    def _init_gps(self) -> bool:
        """Initialise GPS connection."""
        if not self.config.gps_enabled:
            return False

        try:
            import gpsd
            gpsd.connect(host=self.config.gps_host, port=self.config.gps_port)
            self._gps = gpsd
            self._gps_available = True
            log.info("gps_connected", host=self.config.gps_host)
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

    def _on_imu_sample(self, sample: IMUSample) -> None:
        """Called for each high-rate IMU sample."""
        self.detector.process_sample(sample)

    # Event types that should trigger video recording
    VIDEO_CAPTURE_EVENTS = {
        EventType.HARD_BRAKE,
        EventType.HIGH_G,
        EventType.BIG_CORNER,
        EventType.ROUGH_ROAD,
        EventType.MANUAL_CAPTURE,
        EventType.BOOT,
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

    def _on_event(self, event: Event) -> None:
        """Called when an event is detected."""
        # Suppress events while a capture is already in progress.
        # Extends the active capture window instead, so consecutive events
        # (e.g. hard brake → high G → hard brake) produce one video, not many.
        # Manual captures also extend rather than starting overlapping saves.
        # Boot events always go through (only fires once).
        if self._pending_post_capture and event.event_type != EventType.BOOT:
            # Extend the post-capture window of the most recent pending event
            extension = self.config.detector.post_event_seconds
            for pending in self._pending_post_capture.values():
                new_until = time.monotonic() + extension
                if new_until > pending["capture_until"]:
                    pending["capture_until"] = new_until
            log.info(
                "event_suppressed_capture_active",
                suppressed_type=event.event_type.value,
                peak_g=round(event.peak_value, 2),
                pending_count=len(self._pending_post_capture),
            )
            return

        # Attach current GPS state to the event
        event.lat = self._current_lat
        event.lng = self._current_lon
        event.speed_kmh = self._current_speed_kmh if self._current_speed_kmh else None
        event.location_name = self._current_location_name
        event.distance_from_start_km = self._distance_from_start_km
        event.distance_to_destination_km = self._distance_to_destination_km

        # Start video recording/save for significant events
        video_path = None
        if event.event_type in self.VIDEO_CAPTURE_EVENTS:
            if self.video_ring_buffer and self.video_ring_buffer.is_running:
                # Skip boot capture if buffer has no complete segments
                if event.event_type == EventType.BOOT:
                    segments = self.video_ring_buffer._get_buffer_segments()
                    if len(segments) < 2:
                        log.info(
                            "boot_capture_skipped_no_segments",
                            segment_count=len(segments),
                        )
                        # Still save event metadata without video
                        self.event_storage.save_event(event)
                        return

                buzzer.beep_capture_start()
                speaker.speak_capture_start(event.event_type.value)
                eid = id(event)
                self.video_ring_buffer.save_event(
                    prefix=event.event_type.value,
                    post_seconds=int(self.config.capture_post_seconds),
                    callback=lambda path, _eid=eid: self._on_video_complete(
                        _eid, path
                    ),
                )
                log.info(
                    "auto_event_video_save_triggered",
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
        self._pending_post_capture[id(event)] = {
            "event": event,
            "capture_until": post_capture_until,
            "video_path": video_path,
        }
        log.info(
            "event_queued_for_save",
            event_type=event.event_type.value,
            event_id=id(event),
            pending_count=len(self._pending_post_capture),
            save_after_seconds=self.config.detector.post_event_seconds,
        )

        # Publish event to MQTT
        if self.mqtt and self.mqtt.is_connected:
            event_payload = event.to_dict()
            topic = f"{self.config.mqtt_topic_prefix}/event"
            try:
                import json
                self.mqtt._publish(topic, json.dumps(event_payload))
            except Exception as e:
                log.error("mqtt_event_publish_error", error=str(e))

    def trigger_manual_capture(self) -> None:
        """Trigger manual capture via button press or API call.

        Creates a MANUAL_CAPTURE event and routes it through the
        standard _on_event pipeline.
        """
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
        self, event_id: int, path: Optional[Path]
    ) -> None:
        """Called when a video ring buffer save finishes.

        Updates the saved event metadata with the video path and
        regenerates events.json.

        Args:
            event_id: The id() of the Event object, used to look up
                      the saved JSON path.
            path: Path to the saved video file, or None on failure.
        """
        buzzer.beep_capture_end()
        speaker.speak_capture_end()
        if not path:
            log.warning("capture_failed", event_id=event_id)
            return

        log.info("capture_complete", path=str(path), event_id=event_id)

        json_path = self._event_json_paths.get(event_id)
        if json_path:
            self.event_storage.update_event_video(json_path, path)
            self.event_storage.generate_events_json()
        else:
            # Event hasn't been saved yet — stash path for
            # _check_post_captures to pick up.
            self._event_video_paths[event_id] = path

    def _check_post_captures(self) -> None:
        """Complete any pending post-event captures."""
        now = time.monotonic()
        completed = []

        for event_id, pending in self._pending_post_capture.items():
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
                video_path = self._event_video_paths.pop(eid, None)
                if not video_path:
                    video_path = self._find_capture_video(event)

                # Save to disk
                try:
                    json_path, _ = self.event_storage.save_event(
                        event, video_path=video_path
                    )
                    self.events_captured += 1
                    # Store json_path so late video callbacks can
                    # update this event.
                    self._event_json_paths[eid] = json_path
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
                            try:
                                self.capture_sync._do_sync()
                            except Exception as e:
                                log.error("post_event_sync_error", error=str(e))
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

        for event_id in completed:
            del self._pending_post_capture[event_id]

    def _find_capture_video(self, event: Event) -> Optional[Path]:
        """Find the most recent video capture matching an event."""
        captures = Path(self.config.captures_dir)
        event_date = datetime.fromtimestamp(event.start_time, tz=timezone.utc)
        date_dir = captures / event_date.strftime("%Y-%m-%d")
        if not date_dir.is_dir():
            return None

        pattern = f"{event.event_type.value}_*.mp4"
        matches = sorted(date_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        return matches[0] if matches else None

    def _read_gps(self) -> Optional[Reading]:
        """Read current GPS data."""
        if not self._gps_available:
            return None

        try:
            import json
            import socket
            packet = self._gps.get_current()

            if packet.mode < 2:
                return None

            # Get satellite count via direct socket (gpsd-py3 bug workaround)
            satellites = self._get_satellite_count()

            timestamp = datetime.now(timezone.utc)
            if hasattr(packet, "time") and packet.time:
                try:
                    timestamp = datetime.fromisoformat(
                        packet.time.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            # Sync system clock from GPS on first fix
            if not self._clock_synced_from_gps:
                self._sync_clock_from_gps(timestamp)

            reading = Reading(
                timestamp_utc=timestamp,
                sensor_type=SensorType.GPS,
                latitude=packet.lat if hasattr(packet, "lat") else None,
                longitude=packet.lon if hasattr(packet, "lon") else None,
                altitude_m=packet.alt if packet.mode >= 3 and hasattr(packet, "alt") else None,
                speed_kmh=(packet.hspeed * 3.6) if hasattr(packet, "hspeed") and packet.hspeed else None,
                heading_deg=packet.track if hasattr(packet, "track") else None,
                satellites=satellites,
                fix_quality=packet.mode if hasattr(packet, "mode") else 0,
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

    def _get_satellite_count(self) -> Optional[int]:
        """Get satellite count directly from gpsd."""
        import json
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((self.config.gps_host, self.config.gps_port))
            sock.send(b'?WATCH={"enable":true,"json":true}\n')

            data = b""
            for _ in range(15):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                for line in data.decode(errors="ignore").split("\n"):
                    if '"class":"SKY"' in line:
                        try:
                            sky = json.loads(line)
                            return sky.get("uSat", sky.get("nSat", 0))
                        except json.JSONDecodeError:
                            pass
        except (socket.error, socket.timeout, OSError):
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
        return None

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
            "pwr_ok": self._power_collector is not None,
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
            # Trip tracking
            "odometer_km": round(self._odometer_km, 1),
            "daily_km": round(self._daily_km, 1),
            "waypoints_reached": len(self._reached_waypoints),
            "waypoints_total": len(self.config.route_waypoints),
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

        # Power reading
        if self._power_collector:
            try:
                power_data = self._power_collector.read()
                if power_data:
                    readings.append(self._power_collector.to_reading(power_data))
            except Exception as e:
                log.error("power_read_error", error=str(e))

        # Environment reading
        if self._environment_collector:
            try:
                env_data = self._environment_collector.read()
                if env_data:
                    readings.append(self._environment_collector.to_reading(env_data))
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
            # Attempt recovery: restart ffmpeg
            if self.video_ring_buffer and self.video_ring_buffer.is_running:
                self.video_ring_buffer._kill_current()
                self.video_ring_buffer._start_ffmpeg()
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
        try:
            self.event_storage.cleanup_old_events()
            self.event_storage.cleanup_by_size()
        except Exception as e:
            log.error("cleanup_error", error=str(e))

        # Update fake-hwclock so reboots start with a recent time
        self._sync_fake_hwclock()

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

        # Initialise power sensor
        if self._power_collector:
            try:
                self._power_collector.setup()
                log.info("power_sensor_ready")
            except Exception as e:
                log.error("power_sensor_setup_failed", error=str(e))
                self._power_collector = None

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

        # Start thermal monitor
        self.thermal_monitor.start()

        # Instantiate health collector (thermal_monitor and batch_sync now ready)
        data_dir = str(Path(self.config.database_path).parent)
        self._health_collector = HealthCollector(
            thermal_monitor=self.thermal_monitor,
            batch_sync=self.batch_sync,
            data_dir=data_dir,
        )

        # Start OLED display
        if self.oled_display:
            self.oled_display.start()

        # Initialise overlay text files before ffmpeg starts
        if self.config.overlay_enabled and self.video_ring_buffer:
            overlay.init()

        # Start video ring buffer
        if self.video_ring_buffer:
            self.video_ring_buffer.start()

        # Start high-rate sampler
        self.sampler.start()

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
            speaker.init(self.config.speaker_model_path)
            speaker.set_boot_start_time(time.monotonic())
            was_crash = self.boot_recovery.was_crash if self.boot_recovery else False
            speaker.speak_boot(was_crash=was_crash)

        # Regenerate events.json from any previously stored events
        try:
            self.event_storage.generate_events_json()
        except Exception as e:
            log.warning("events_json_boot_generate_error", error=str(e))

        # Boot capture — video ring buffer has had ~20s to fill during GPS wait
        if self.video_ring_buffer and self.video_ring_buffer.is_running:
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

        log.info("unified_engine_started")

    def stop(self) -> None:
        """Stop the unified engine."""
        log.info("unified_engine_stopping")

        self._running = False

        # Stop OLED display early so it can show final state
        if self.oled_display:
            self.oled_display.stop()

        # Stop button handler
        if self.button_handler:
            self.button_handler.stop()

        # Stop video ring buffer or active recording
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

        if self.batch_sync:
            self.batch_sync.stop()

        if self.capture_sync:
            self.capture_sync.stop()

        self.thermal_monitor.stop()

        if self.mqtt:
            self.mqtt.disconnect()

        if self._power_collector:
            self._power_collector.cleanup()

        if self._environment_collector:
            self._environment_collector.cleanup()

        self.connection.stop()

        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=2.0)

        # Save any pending events
        for pending in self._pending_post_capture.values():
            try:
                self.event_storage.save_event(pending["event"])
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
                    if speaker.init(self.config.speaker_model_path):
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
