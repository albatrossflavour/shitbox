"""Data models for telemetry readings."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SensorType(str, Enum):
    """Types of sensor readings."""

    GPS = "gps"
    IMU = "imu"
    TEMPERATURE = "temp"
    SYSTEM = "system"


@dataclass
class GPSReading:
    """GPS sensor reading."""

    timestamp: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    satellites: Optional[int] = None
    fix_quality: Optional[int] = None

    @property
    def has_fix(self) -> bool:
        """Check if we have a valid GPS fix."""
        return self.latitude is not None and self.longitude is not None


@dataclass
class IMUReading:
    """IMU (accelerometer + gyroscope) reading."""

    timestamp: datetime
    accel_x: float  # g-force
    accel_y: float
    accel_z: float
    gyro_x: float  # degrees per second
    gyro_y: float
    gyro_z: float

    @property
    def accel_magnitude(self) -> float:
        """Calculate total acceleration magnitude in g."""
        return (self.accel_x**2 + self.accel_y**2 + self.accel_z**2) ** 0.5

    @property
    def gyro_magnitude(self) -> float:
        """Calculate total rotation rate magnitude in deg/s."""
        return (self.gyro_x**2 + self.gyro_y**2 + self.gyro_z**2) ** 0.5


@dataclass
class TemperatureReading:
    """Temperature sensor reading."""

    timestamp: datetime
    temp_celsius: float


@dataclass
class Reading:
    """Generic reading that can hold any sensor type's data.

    This is the format used for database storage and sync.
    """

    id: Optional[int] = None
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sensor_type: SensorType = SensorType.GPS

    # GPS fields
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    satellites: Optional[int] = None
    fix_quality: Optional[int] = None

    # IMU fields
    accel_x: Optional[float] = None
    accel_y: Optional[float] = None
    accel_z: Optional[float] = None
    gyro_x: Optional[float] = None
    gyro_y: Optional[float] = None
    gyro_z: Optional[float] = None

    # Temperature fields
    temp_celsius: Optional[float] = None

    # System fields (Pi health)
    cpu_temp_celsius: Optional[float] = None

    # Sync tracking (set by database)
    synced_mqtt: bool = False
    synced_prometheus: bool = False

    @classmethod
    def from_gps(cls, reading: GPSReading) -> "Reading":
        """Create a Reading from a GPSReading."""
        return cls(
            timestamp_utc=reading.timestamp,
            sensor_type=SensorType.GPS,
            latitude=reading.latitude,
            longitude=reading.longitude,
            altitude_m=reading.altitude_m,
            speed_kmh=reading.speed_kmh,
            heading_deg=reading.heading_deg,
            satellites=reading.satellites,
            fix_quality=reading.fix_quality,
        )

    @classmethod
    def from_imu(cls, reading: IMUReading) -> "Reading":
        """Create a Reading from an IMUReading."""
        return cls(
            timestamp_utc=reading.timestamp,
            sensor_type=SensorType.IMU,
            accel_x=reading.accel_x,
            accel_y=reading.accel_y,
            accel_z=reading.accel_z,
            gyro_x=reading.gyro_x,
            gyro_y=reading.gyro_y,
            gyro_z=reading.gyro_z,
        )

    @classmethod
    def from_temperature(cls, reading: TemperatureReading) -> "Reading":
        """Create a Reading from a TemperatureReading."""
        return cls(
            timestamp_utc=reading.timestamp,
            sensor_type=SensorType.TEMPERATURE,
            temp_celsius=reading.temp_celsius,
        )

    def to_mqtt_payload(self) -> dict:
        """Convert to MQTT JSON payload."""
        ts = self.timestamp_utc.isoformat()

        if self.sensor_type == SensorType.GPS:
            return {
                "ts": ts,
                "lat": self.latitude,
                "lon": self.longitude,
                "alt": self.altitude_m,
                "spd": self.speed_kmh,
                "hdg": self.heading_deg,
                "sat": self.satellites,
                "fix": self.fix_quality,
            }
        elif self.sensor_type == SensorType.IMU:
            return {
                "ts": ts,
                "ax": self.accel_x,
                "ay": self.accel_y,
                "az": self.accel_z,
                "gx": self.gyro_x,
                "gy": self.gyro_y,
                "gz": self.gyro_z,
            }
        elif self.sensor_type == SensorType.TEMPERATURE:
            return {
                "ts": ts,
                "temp": self.temp_celsius,
            }
        elif self.sensor_type == SensorType.SYSTEM:
            return {
                "ts": ts,
                "cpu_temp": self.cpu_temp_celsius,
            }
        else:
            return {"ts": ts}


@dataclass
class SyncCursor:
    """Tracks sync progress for a destination."""

    cursor_name: str
    last_synced_id: int = 0
    last_synced_at: Optional[datetime] = None


@dataclass
class HealthStatus:
    """System health status."""

    timestamp: datetime
    cpu_temp_celsius: Optional[float] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    sync_backlog: int = 0
    mqtt_connected: bool = False
    gps_has_fix: bool = False

    def to_mqtt_payload(self) -> dict:
        """Convert to MQTT JSON payload."""
        return {
            "ts": self.timestamp.isoformat(),
            "cpu_temp": self.cpu_temp_celsius,
            "cpu_pct": self.cpu_percent,
            "mem_pct": self.memory_percent,
            "disk_pct": self.disk_percent,
            "backlog": self.sync_backlog,
            "mqtt": self.mqtt_connected,
            "gps_fix": self.gps_has_fix,
        }
