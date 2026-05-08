"""Driver for the INA228 DC power monitor (TI SBOSAB6).

20-bit ADC, 85 V bus, ±163.84 mV shunt range at ADCRANGE=0. Written
in-tree because there's no maintained Python driver for the chip on
PyPI. Only VBUS and CURRENT are read; the on-chip energy/charge
accumulators and die temperature are available but unused.

Originally the module also carried an INA237 sibling class (16-bit
register layout). It was removed when the INA237 chip was physically
pulled from the I2C chain — the 5 V Pi rail is now monitored via the
Pi 5 PMIC (`vcgencmd pmic_read_adc`) instead. If a future build needs
the INA237 again, the shared `_INABase` makes it a ~10-line addition.
"""

from typing import Tuple

REG_CONFIG     = 0x00
REG_ADC_CONFIG = 0x01
REG_SHUNT_CAL  = 0x02
REG_VSHUNT     = 0x04
REG_VBUS       = 0x05
REG_DIETEMP    = 0x06
REG_CURRENT    = 0x07

# ADC_CONFIG: continuous shunt+bus+temp, 1052 µs each, 16-sample averaging.
# Layout: MODE[15:12]=0xF, VBUSCT[11:9]=4, VSHCT[8:6]=4, VTCT[5:3]=4, AVG[2:0]=2
ADC_CONFIG_DEFAULT = 0xF922

# CONFIG: defaults — RST=0, RSTACC=0, CONVDLY=0, TEMPCOMP=0, ADCRANGE=0.
# ADCRANGE=0 keeps the wider ±163.84 mV shunt range, which matches the
# Adafruit 15 mΩ breakouts (±10 A range).
CONFIG_DEFAULT = 0x0000


def _bswap16(value: int) -> int:
    return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)


class _INABase:
    """Shared INA228/INA237 logic. Subclasses fill in chip-specific constants."""

    # Subclass overrides
    SHUNT_CAL_FACTOR: float = 0.0    # SHUNT_CAL = factor × CURRENT_LSB × R_SHUNT
    CURRENT_LSB_BITS: int = 0        # 19 for INA228, 15 for INA237
    VBUS_LSB_V: float = 0.0
    CURRENT_REG_BYTES: int = 0       # 3 (INA228) or 2 (INA237)
    VBUS_REG_BYTES: int = 0
    DATA_BITS: int = 0               # bits of actual data inside the register

    def __init__(
        self,
        bus: object,
        address: int,
        shunt_ohms: float,
        max_expected_amps: float,
    ) -> None:
        self._bus = bus
        self._address = address
        self._shunt_ohms = shunt_ohms
        self._current_lsb = max_expected_amps / (1 << self.CURRENT_LSB_BITS)
        self._configure()

    def _write_u16(self, reg: int, value: int) -> None:
        # smbus2 write_word_data uses little-endian on the wire; INA chips
        # expect big-endian, so swap before writing.
        self._bus.write_word_data(self._address, reg, _bswap16(value))

    def _read_block_be(self, reg: int, n: int) -> int:
        data = self._bus.read_i2c_block_data(self._address, reg, n)
        v = 0
        for b in data:
            v = (v << 8) | b
        return v

    def _read_unsigned(self, reg: int, n: int) -> int:
        raw = self._read_block_be(reg, n)
        shift = (n * 8) - self.DATA_BITS
        return raw >> shift

    def _read_signed(self, reg: int, n: int) -> int:
        raw = self._read_block_be(reg, n)
        shift = (n * 8) - self.DATA_BITS
        val = raw >> shift
        sign_bit = 1 << (self.DATA_BITS - 1)
        return (val - (1 << self.DATA_BITS)) if (val & sign_bit) else val

    def _configure(self) -> None:
        self._write_u16(REG_CONFIG, CONFIG_DEFAULT)
        self._write_u16(REG_ADC_CONFIG, ADC_CONFIG_DEFAULT)
        cal = int(round(self.SHUNT_CAL_FACTOR * self._current_lsb * self._shunt_ohms))
        cal = max(0, min(cal, 0x7FFF))
        self._write_u16(REG_SHUNT_CAL, cal)

    def read(self) -> Tuple[float, float]:
        """Return (bus_voltage_v, current_a)."""
        bus_v = self._read_unsigned(REG_VBUS, self.VBUS_REG_BYTES) * self.VBUS_LSB_V
        current_a = self._read_signed(REG_CURRENT, self.CURRENT_REG_BYTES) * self._current_lsb
        return bus_v, current_a


class INA228(_INABase):
    """20-bit precision power monitor, 0–85 V bus."""

    SHUNT_CAL_FACTOR = 13107.2e6
    CURRENT_LSB_BITS = 19
    VBUS_LSB_V = 195.3125e-6
    CURRENT_REG_BYTES = 3
    VBUS_REG_BYTES = 3
    DATA_BITS = 20
