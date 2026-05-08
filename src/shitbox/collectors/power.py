"""INA228 power monitor collector.

Single chip on the I2C bus at 0x40, monitoring the 12 V battery rail.
15 mΩ shunt on the Adafruit breakout (±10 A range at ADCRANGE=0).
Readings land in the `power` SensorType tagged with sensor_id=role
(= "battery") so they coexist cleanly with the PMIC-derived Pi rails.

The collector is chip-pluggable — selecting `chip = ina228` in config
picks the INA228 driver. Earlier builds also supported the INA237 (5 V
Pi rail) but that chip was physically pulled when its inline shunt cost
too much voltage headroom and tripped the Pi 5's undervoltage detector;
Pi-side telemetry now comes from `vcgencmd pmic_read_adc`.
"""

from typing import Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading, SensorType
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Module-level imports — patched in tests.
try:
    import smbus2

    from shitbox.collectors._vendor.ina_modern import INA228
    _HAS_INA = True
except ImportError:
    smbus2 = None  # type: ignore[assignment]
    INA228 = None  # type: ignore[assignment]
    _HAS_INA = False


_CHIP_CLASSES = {
    "ina228": INA228,
}


class INAReading:
    """Bus voltage + current from one INA monitor, tagged with role."""

    def __init__(self, voltage_v: float, current_a: float, role: str) -> None:
        self.voltage_v: float = voltage_v
        self.current_a: float = current_a
        self.role: str = role
        # Generic value accessor for collector plumbing.
        self.value: float = voltage_v


class INACollector(BaseCollector["INAReading"]):
    """Collector for an INA228 chip, one role per instance."""

    def __init__(
        self,
        config: object,
        callback: Optional[object] = None,
        role: Optional[str] = None,
    ) -> None:
        super().__init__(
            name=f"ina_{role}" if role else "ina",
            sample_rate_hz=getattr(config, "sample_rate_hz", 1.0),
            callback=callback,
            role=role,
        )
        self._enabled: bool = bool(getattr(config, "enabled", False))
        self._chip: str = str(getattr(config, "chip", "ina228")).lower()
        self._i2c_bus: int = int(getattr(config, "i2c_bus", 1))
        self._address: int = int(getattr(config, "address", 0x40))
        self._shunt_ohms: float = float(getattr(config, "shunt_ohms", 0.015))
        self._max_amps: float = float(getattr(config, "max_expected_amps", 10.0))
        self._disconnected_threshold_v: float = float(
            getattr(config, "disconnected_threshold_v", 1.0)
        )
        self._role: str = role or "power"
        self._sensor: Optional[object] = None

    def setup(self) -> None:
        if not self._enabled:
            log.info("ina_disabled", role=self._role, chip=self._chip)
            return
        if smbus2 is None or INA228 is None:
            log.warning("ina_lib_missing", role=self._role)
            return
        chip_cls = _CHIP_CLASSES.get(self._chip)
        if chip_cls is None:
            log.warning("ina_unknown_chip", role=self._role, chip=self._chip)
            return
        try:
            bus = smbus2.SMBus(self._i2c_bus)
            self._sensor = chip_cls(
                bus=bus,
                address=self._address,
                shunt_ohms=self._shunt_ohms,
                max_expected_amps=self._max_amps,
            )
            log.info(
                "ina_sensor_init",
                role=self._role,
                chip=self._chip,
                address=hex(self._address),
            )
        except Exception as e:
            log.warning(
                "ina_sensor_init_failed",
                role=self._role,
                chip=self._chip,
                error=str(e),
            )
            self._sensor = None

    def collect(self) -> Optional["INAReading"]:
        if not self._enabled or self._sensor is None:
            return None
        try:
            voltage_v, current_a = self._sensor.read()
        except Exception as e:
            log.warning("ina_read_error", role=self._role, error=str(e))
            return None
        # Gate against a floating-input chip: when V+/V- aren't wired to
        # a real rail the ADC reads its own noise floor (~mV). Anything
        # below the threshold is treated as "rail not connected" and
        # dropped silently — no DB row, no Prometheus metric, no panel
        # noise. Real rails (12 V, 5 V, 3.3 V) all sit comfortably above.
        if voltage_v < self._disconnected_threshold_v:
            return None
        return INAReading(voltage_v=voltage_v, current_a=current_a, role=self._role)

    def read(self) -> Optional["INAReading"]:
        """Alias for collect — satisfies BaseCollector ABC."""
        return self.collect()

    def to_reading(self, data: "INAReading") -> Reading:
        return Reading(
            sensor_type=SensorType.POWER,
            bus_voltage_v=data.voltage_v,
            current_ma=data.current_a * 1000.0,
            sensor_id=data.role,
        )
