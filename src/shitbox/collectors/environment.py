"""Environment data collector for BME680 sensor."""

from collections import deque
from typing import Callable, Optional

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import EnvironmentReading, Reading
from shitbox.utils.config import EnvironmentConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Air-quality score constants (pimoroni indoor-air-quality approach, with a
# rolling baseline instead of a one-shot burn-in mean so it tracks sensor drift
# over a multi-day run). These are algorithm parameters, not field knobs.
_HUM_BASELINE_PCT = 40.0   # ideal indoor relative humidity
_HUM_WEIGHTING = 0.25      # humidity contributes 25% of the score, gas 75%
_GAS_BASELINE_WINDOW = 120  # gas-resistance samples kept for the rolling baseline


def compute_air_quality_score(
    gas_ohms: float, humidity_pct: float, gas_baseline_ohms: float
) -> float:
    """Relative indoor-air-quality score, 0-100 (higher = cleaner).

    Combines gas resistance against a rolling baseline (75%) with humidity's
    deviation from an ideal 40% (25%). This is a *relative* score — "cleaner or
    worse than the recent baseline" — not a calibrated Bosch IAQ index. Pure
    function so it can be unit-tested without hardware.
    """
    gas_weighting = 1.0 - _HUM_WEIGHTING

    # Humidity: full marks at 40%, tapering toward 0 at the dry/wet extremes.
    hum_offset = humidity_pct - _HUM_BASELINE_PCT
    if hum_offset > 0:
        hum_frac = (100.0 - _HUM_BASELINE_PCT - hum_offset) / (100.0 - _HUM_BASELINE_PCT)
    else:
        hum_frac = (_HUM_BASELINE_PCT + hum_offset) / _HUM_BASELINE_PCT
    hum_score = max(0.0, min(1.0, hum_frac)) * (_HUM_WEIGHTING * 100.0)

    # Gas: full marks at or above baseline, scaling down as resistance drops
    # below it (lower resistance = more VOCs = worse air).
    if gas_baseline_ohms <= 0:
        gas_score = gas_weighting * 100.0
    elif gas_ohms < gas_baseline_ohms:
        gas_score = (gas_ohms / gas_baseline_ohms) * (gas_weighting * 100.0)
    else:
        gas_score = gas_weighting * 100.0

    return round(hum_score + gas_score, 1)


class EnvironmentCollector(BaseCollector[EnvironmentReading]):
    """Collector for BME680 I2C environment sensor.

    Reads barometric pressure (hPa), relative humidity (%), temperature (C),
    and gas resistance (ohms) for VOC/air quality measurement.
    """

    def __init__(
        self,
        config: EnvironmentConfig,
        callback: Optional[Callable[[Reading], None]] = None,
    ):
        super().__init__(
            name="environment",
            sample_rate_hz=config.sample_rate_hz,
            callback=callback,
            role="environment",
        )
        self.config = config
        self._sensor = None
        self._i2c = None
        # Rolling window of recent gas-resistance readings for the air-quality
        # baseline. In-memory only — resets on restart, so the score re-warms
        # over the first ~2 min of samples (documented burn-in).
        self._gas_history: "deque[float]" = deque(maxlen=_GAS_BASELINE_WINDOW)

    def setup(self) -> None:
        """Initialise BME680 hardware. Single attempt — supervisor's exponential
        backoff ladder owns retry cadence (Plan 21-02), which also resolves the
        documented boot-timing race without the 5s boot delay that the prior
        inline 5×1s loop introduced.
        """
        try:
            import board
            import busio
            from adafruit_bme680 import Adafruit_BME680_I2C
        except ImportError as e:
            log.error("environment_import_failed", error=str(e))
            raise
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = Adafruit_BME680_I2C(self._i2c, address=self.config.address)
            log.info("environment_sensor_initialised")
        except Exception as e:
            log.error("environment_setup_error", error=str(e))
            raise

    def read(self) -> Optional[EnvironmentReading]:
        """Read current environment metrics."""
        if not self._sensor:
            return None

        try:
            pressure = self._sensor.pressure
            humidity = self._sensor.relative_humidity
            temperature = self._sensor.temperature
            gas = self._sensor.gas

            # Derive the relative air-quality score against a rolling gas
            # baseline. Skipped until gas is available.
            air_quality = None
            if gas is not None:
                self._gas_history.append(gas)
                gas_baseline = sum(self._gas_history) / len(self._gas_history)
                air_quality = compute_air_quality_score(gas, humidity, gas_baseline)

            reading = EnvironmentReading(
                timestamp=self.now_utc(),
                pressure_hpa=pressure,
                humidity_pct=humidity,
                env_temp_celsius=temperature,
                gas_resistance_ohms=gas,
                air_quality_score=air_quality,
            )

            log.debug(
                "environment_reading",
                pressure_hpa=f"{pressure:.1f}",
                humidity_pct=f"{humidity:.1f}",
                temp_c=f"{temperature:.1f}",
                gas_ohms=gas,
            )

            return reading

        except Exception as e:
            log.error("environment_read_error", error=str(e))
            raise

    def to_reading(self, data: EnvironmentReading) -> Reading:
        """Convert EnvironmentReading to generic Reading."""
        return Reading.from_environment(data)

    def cleanup(self) -> None:
        """Release I2C resources."""
        if self._i2c:
            self._i2c.deinit()
            self._i2c = None
            self._sensor = None
            log.info("environment_cleanup_complete")
