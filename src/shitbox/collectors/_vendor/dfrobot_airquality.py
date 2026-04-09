"""DFRobot SEN0460 air quality sensor (PM1/PM2.5/PM10) over I2C at 0x19.

Minimal stub implementation — replace with the full DFRobot driver before
enabling on Pi 5. The full upstream driver is at:
https://github.com/DFRobot/DFRobot_AirQualitySensor/blob/master/python/raspberrypi/DFRobot_AirQualitySensor.py

# TODO: replace with full DFRobot driver before enabling on Pi 5

Cable pinout (Gravity 4-pin):
    red   = VCC (5V)
    black = GND
    cyan  = SDA
    blue  = SCL
"""

# Particle type identifiers matching the DFRobot upstream API
PARTICLE_PM1_0_STANDARD = 0x01
PARTICLE_PM2_5_STANDARD = 0x02
PARTICLE_PM10_STANDARD = 0x03

_PARTICLE_MAP = {
    "PM1.0": PARTICLE_PM1_0_STANDARD,
    "PM2.5": PARTICLE_PM2_5_STANDARD,
    "PM10":  PARTICLE_PM10_STANDARD,
}

# I2C register addresses (from DFRobot upstream)
_REG_PART_PM1_0 = 0x05
_REG_PART_PM2_5 = 0x07
_REG_PART_PM10  = 0x09

_REG_MAP = {
    PARTICLE_PM1_0_STANDARD: _REG_PART_PM1_0,
    PARTICLE_PM2_5_STANDARD: _REG_PART_PM2_5,
    PARTICLE_PM10_STANDARD:  _REG_PART_PM10,
}


class DFRobot_AirQualitySensor:
    """Minimal smbus2 driver for the DFRobot SEN0460 air quality sensor.

    Matches the interface of the upstream DFRobot Python driver so that
    the full driver can be dropped in as a replacement without changing
    the collector code.
    """

    def __init__(self, bus: object, address: int = 0x19) -> None:
        self._bus = bus
        self._address = address

    def _read_u16_be(self, reg: int) -> int:
        """Read a big-endian 16-bit unsigned register."""
        data = self._bus.read_i2c_block_data(self._address, reg, 2)  # type: ignore[attr-defined]
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
