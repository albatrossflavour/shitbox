"""Thin INA226 driver over smbus2.

Written in-tree because there is no maintained Adafruit CircuitPython
INA226 package on PyPI (researcher confirmed). Register map from the
TI INA226 datasheet (SBOS547).
"""

from typing import Tuple

REG_CONFIG = 0x00
REG_SHUNT_VOLTAGE = 0x01
REG_BUS_VOLTAGE = 0x02
REG_POWER = 0x03
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05

BUS_LSB_V = 0.00125        # 1.25 mV/bit per datasheet
SHUNT_LSB_V = 0.0000025    # 2.5 µV/bit


class INA226:
    """Minimal smbus2-based INA226 driver.

    Uses read_word_data / write_word_data for register access. smbus2
    returns little-endian 16-bit values from read_word_data; the INA226
    register map is big-endian, so bytes are swapped on read.
    """

    def __init__(
        self,
        bus: object,
        address: int = 0x40,
        shunt_ohms: float = 0.1,
        max_expected_amps: float = 3.0,
    ) -> None:
        self._bus = bus
        self._address = address
        self._shunt_ohms = shunt_ohms
        self._current_lsb = max_expected_amps / 32768.0
        self._configure()

    def _read_u16(self, reg: int) -> int:
        """Read a 16-bit unsigned register, byte-swapped from little-endian smbus2."""
        raw = self._bus.read_word_data(self._address, reg)
        # smbus2 read_word_data returns little-endian; swap to big-endian
        return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)

    def _read_s16(self, reg: int) -> int:
        val = self._read_u16(reg)
        return val - 0x10000 if val & 0x8000 else val

    def _write_u16(self, reg: int, value: int) -> None:
        # Swap to little-endian for smbus2 write_word_data
        swapped = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
        self._bus.write_word_data(self._address, reg, swapped)

    def _configure(self) -> None:
        """Write default config and calibration registers.

        16 averages, 1.1 ms conversion time, continuous shunt+bus mode.
        """
        self._write_u16(REG_CONFIG, 0x4527)
        cal = int(0.00512 / (self._current_lsb * self._shunt_ohms))
        self._write_u16(REG_CALIBRATION, cal)

    def read(self) -> Tuple[float, float]:
        """Return (bus_voltage_v, current_a)."""
        bus_v = self._read_u16(REG_BUS_VOLTAGE) * BUS_LSB_V
        current_a = self._read_s16(REG_CURRENT) * self._current_lsb
        return bus_v, current_a
