"""DFRobot SEN0460 air quality sensor (PM1/PM2.5/PM10) over I2C at 0x19.

Protocol reference (register addresses, mode bytes) taken from the
upstream DFRobot driver:
    https://github.com/DFRobot/DFRobot_AirQualitySensor
    python/raspberrypi/dfrobot_airqualitysensor.py
    pinned at upstream SHA be5351c0c37e5c5f6fa7b026e202556f07f7fd0f

This is NOT a verbatim port. The upstream driver:
    - imports `smbus` (we use smbus2), plus unused `spidev` and `RPi.GPIO`
    - has an undefined `I2C_MODE` reference that crashes __init__
      for any non-zero bus
    - returns -1 from read_reg on error, which then crashes the
      byte-indexing call site
    - uses while/print/sleep retry loops in write_reg
We only carry forward the protocol facts (register addresses, mode bytes,
big-endian 16-bit reads). Everything else is rewritten.

Critical fix vs the prior stub: the SEN0460 ships idle. Until something
writes 0x02 to the mode register, the fan and laser do not run and the
PM concentration registers return zero or stale values. The constructor
now issues `awake()` so the sensor starts measuring; the fan needs
~15-30 s to stabilise before readings are meaningful.

Cable pinout (Gravity 4-pin):
    red   = VCC (5V)
    black = GND
    cyan  = SDA
    blue  = SCL
"""

from typing import Any

# Particle type identifiers (interface compatibility — preserved from
# the prior stub so the collector keeps using string keys).
PARTICLE_PM1_0_STANDARD = 0x01
PARTICLE_PM2_5_STANDARD = 0x02
PARTICLE_PM10_STANDARD = 0x03

_PARTICLE_MAP = {
    "PM1.0": PARTICLE_PM1_0_STANDARD,
    "PM2.5": PARTICLE_PM2_5_STANDARD,
    "PM10":  PARTICLE_PM10_STANDARD,
}

# I2C register addresses from the upstream DFRobot driver
_REG_MODE       = 0x01
_REG_PART_PM1_0 = 0x05
_REG_PART_PM2_5 = 0x07
_REG_PART_PM10  = 0x09

_REG_MAP = {
    PARTICLE_PM1_0_STANDARD: _REG_PART_PM1_0,
    PARTICLE_PM2_5_STANDARD: _REG_PART_PM2_5,
    PARTICLE_PM10_STANDARD:  _REG_PART_PM10,
}

# Mode register payloads
_MODE_LOWPOWER = 0x01
_MODE_AWAKE    = 0x02


class DFRobot_AirQualitySensor:
    """smbus2-based DFRobot SEN0460 driver.

    On construction the sensor is woken (mode -> awake). The fan and
    laser need ~15-30 s to stabilise before PM concentrations are
    meaningful — early readings may still be 0.
    """

    def __init__(self, bus: Any, address: int = 0x19) -> None:
        self._bus = bus
        self._address = address
        self.awake()

    def awake(self) -> None:
        """Wake the sensor — fan + laser on, periodic measurement."""
        self._bus.write_i2c_block_data(self._address, _REG_MODE, [_MODE_AWAKE])

    def set_lowpower(self) -> None:
        """Put the sensor into low-power mode (fan + laser off)."""
        self._bus.write_i2c_block_data(self._address, _REG_MODE, [_MODE_LOWPOWER])

    def _read_u16_be(self, reg: int) -> int:
        """Read a big-endian 16-bit unsigned register."""
        data = self._bus.read_i2c_block_data(self._address, reg, 2)
        return (data[0] << 8) | data[1]

    def read_particle_concentration(self, particle_type: str) -> float:
        """Read particle concentration in µg/m³.

        Args:
            particle_type: "PM1.0", "PM2.5", or "PM10"

        Returns:
            Concentration in µg/m³.
        """
        type_id = _PARTICLE_MAP.get(particle_type)
        if type_id is None:
            raise ValueError(f"Unknown particle type: {particle_type!r}")
        reg = _REG_MAP[type_id]
        return float(self._read_u16_be(reg))

    def gain_particle_num(self, particle_type: str) -> int:
        """Alias for read_particle_concentration returning int (upstream API compat)."""
        return int(self.read_particle_concentration(particle_type))
