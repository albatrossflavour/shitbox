"""Unified Shitbox Telemetry Engine.

Combines high-rate event detection with low-rate telemetry logging.

High-rate path (100 Hz):
- IMU sampling → ring buffer → event detection → burst storage

Low-rate path (1 Hz):
- GPS, IMU snapshot, temperature → SQLite → MQTT → Prometheus batch sync
"""

import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shitbox.capture.button import ButtonHandler
from shitbox.capture.video import VideoRecorder
from shitbox.events.detector import DetectorConfig, Event, EventDetector, EventType
from shitbox.events.ring_buffer import IMUSample, RingBuffer
from shitbox.events.sampler import HighRateSampler
from shitbox.events.storage import EventStorage
from shitbox.storage.database import Database
from shitbox.storage.models import Reading, SensorType
from pathlib import Path
from shitbox.sync.batch_sync import BatchSyncService
from shitbox.sync.connection import ConnectionMonitor
from shitbox.sync.mqtt_publisher import MQTTPublisher
from shitbox.utils.config import load_config, Config
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


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
        )

        # Low-rate components
        self.database = Database(config.database_path)

        # GPS collector (lazy init)
        self._gps = None
        self._gps_available = False

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

        # Manual capture components
        self.button_handler: Optional[ButtonHandler] = None
        self.video_recorder: Optional[VideoRecorder] = None

        if config.capture_enabled:
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
        self._manual_capture_count = 0
        self._last_timelapse_time = 0.0
        self._current_speed_kmh = 0.0

        # Stats
        self.telemetry_readings = 0
        self.events_captured = 0
        self.timelapse_images = 0

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
            log.warning("gps_init_failed", error=str(e))
            self._gps_available = False
            return False

    def _on_imu_sample(self, sample: IMUSample) -> None:
        """Called for each high-rate IMU sample."""
        self.detector.process_sample(sample)

    # Event types that should trigger video recording
    VIDEO_CAPTURE_EVENTS = {EventType.HIGH_G, EventType.BIG_CORNER}

    def _on_event(self, event: Event) -> None:
        """Called when an event is detected."""
        # Start video recording for significant events
        video_path = None
        if event.event_type in self.VIDEO_CAPTURE_EVENTS and self.video_recorder:
            if not self.video_recorder.is_recording:
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
        post_capture_until = time.time() + self.config.detector.post_event_seconds
        self._pending_post_capture[id(event)] = {
            "event": event,
            "capture_until": post_capture_until,
            "video_path": video_path,
        }

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

        Captures:
        - Video from webcam (configurable duration)
        - IMU data from ring buffer (pre + post capture)
        """
        self._manual_capture_count += 1
        now = time.time()

        log.info(
            "manual_capture_triggered",
            capture_number=self._manual_capture_count,
        )

        # Start video recording
        video_path = None
        if self.video_recorder:
            video_path = self.video_recorder.start_recording(
                duration_seconds=self.config.capture_video_duration,
                filename_prefix="manual_capture",
            )

        # Grab pre-event IMU samples from ring buffer
        pre_samples = self.ring_buffer.get_window(self.config.capture_pre_seconds)

        # Get current IMU reading for peak values
        latest = self.ring_buffer.get_latest(1)
        peak_ax = latest[0].ax if latest else 0.0
        peak_ay = latest[0].ay if latest else 0.0
        peak_az = latest[0].az if latest else 0.0

        # Create manual capture event
        event = Event(
            event_type=EventType.MANUAL_CAPTURE,
            start_time=now - self.config.capture_pre_seconds,
            end_time=now,  # Will be updated when post-capture completes
            peak_value=1.0,  # Placeholder for manual captures
            peak_ax=peak_ax,
            peak_ay=peak_ay,
            peak_az=peak_az,
            samples=list(pre_samples),
        )

        # Schedule post-event capture (same pattern as auto-detected events)
        post_capture_until = now + self.config.capture_post_seconds
        self._pending_post_capture[id(event)] = {
            "event": event,
            "capture_until": post_capture_until,
            "video_path": video_path,
        }

        # Publish to MQTT
        if self.mqtt and self.mqtt.is_connected:
            try:
                import json
                payload = {
                    "type": "manual_capture",
                    "timestamp": now,
                    "capture_number": self._manual_capture_count,
                    "video_path": str(video_path) if video_path else None,
                }
                self.mqtt._publish(
                    f"{self.config.mqtt_topic_prefix}/manual_capture",
                    json.dumps(payload),
                )
            except Exception as e:
                log.error("mqtt_manual_capture_publish_error", error=str(e))

    def _check_post_captures(self) -> None:
        """Complete any pending post-event captures."""
        now = time.time()
        completed = []

        for event_id, pending in self._pending_post_capture.items():
            if now >= pending["capture_until"]:
                event = pending["event"]
                # Get additional samples since event ended
                additional = self.ring_buffer.get_window(
                    self.config.detector.post_event_seconds
                )
                event.samples.extend(
                    s for s in additional if s.timestamp > event.end_time
                )

                # Save to disk
                try:
                    self.event_storage.save_event(event)
                    self.events_captured += 1
                except Exception as e:
                    log.error("event_save_error", error=str(e))

                completed.append(event_id)

        for event_id in completed:
            del self._pending_post_capture[event_id]

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
        last_telemetry = 0
        last_cleanup = time.time()

        while self._running:
            now = time.time()

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

            time.sleep(0.1)

    def _record_telemetry(self) -> None:
        """Record one telemetry cycle to SQLite and MQTT."""
        readings = []

        # GPS reading
        if self.config.gps_enabled:
            gps_reading = self._read_gps()
            if gps_reading:
                readings.append(gps_reading)
                # Track current speed for timelapse
                if gps_reading.speed_kmh is not None:
                    self._current_speed_kmh = gps_reading.speed_kmh

        # IMU snapshot
        imu_reading = self._read_imu_snapshot()
        if imu_reading:
            readings.append(imu_reading)

        # System status (Pi temp)
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

    def _check_timelapse(self, now: float) -> None:
        """Capture timelapse image if moving and interval elapsed."""
        if not self.config.timelapse_enabled:
            return

        if not self.video_recorder:
            return

        # Check if enough time has passed
        if (now - self._last_timelapse_time) < self.config.timelapse_interval_seconds:
            return

        # Check if we're moving fast enough
        if self._current_speed_kmh < self.config.timelapse_min_speed_kmh:
            return

        # Don't capture during video recording (camera busy)
        if self.video_recorder.is_recording:
            return

        # Capture image
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

        # Clean up old video captures
        if self.video_recorder:
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

        log.info(
            "unified_engine_starting",
            imu_rate=self.config.imu_sample_rate_hz,
            telemetry_interval=self.config.telemetry_interval_seconds,
            mqtt=self.config.mqtt_enabled,
            prometheus=self.config.prometheus_enabled,
        )

        self._running = True

        # Initialise database
        self.database.connect()

        # Initialise GPS
        if self.config.gps_enabled:
            self._init_gps()

        # Start connection monitor
        if self.config.uplink_enabled:
            self.connection.start()

        # Start MQTT
        if self.mqtt:
            self.mqtt.connect()

        # Start batch sync
        if self.batch_sync:
            self.batch_sync.start()

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

        log.info("unified_engine_started")

    def stop(self) -> None:
        """Stop the unified engine."""
        log.info("unified_engine_stopping")

        self._running = False

        # Stop button handler
        if self.button_handler:
            self.button_handler.stop()

        # Stop any active video recording
        if self.video_recorder and self.video_recorder.is_recording:
            self.video_recorder.stop_recording()

        # Stop components
        self.sampler.stop()

        if self.batch_sync:
            self.batch_sync.stop()

        if self.mqtt:
            self.mqtt.disconnect()

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

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Notify systemd we're ready
        self._notify_systemd("READY=1")

        self.start()

        # Main loop with watchdog
        while self._running:
            self._notify_systemd("WATCHDOG=1")
            time.sleep(1.0)

        self.stop()

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

    # Create engine config from YAML
    config = EngineConfig.from_yaml_config(yaml_config)

    if args.no_uplink:
        config.uplink_enabled = False

    engine = UnifiedEngine(config)
    engine.run()


if __name__ == "__main__":
    main()
