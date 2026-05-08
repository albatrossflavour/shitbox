"""Pi 5 PMIC rail telemetry via `vcgencmd pmic_read_adc`.

The Pi 5's PMIC measures voltage and current on every internal rail
(EXT5V input, 3V3_SYS, VDD_CORE, DDR_VDD2, HDMI, ...) and exposes the
readings via the `vcgencmd` userspace tool. We shell out, parse the
output, and emit one Reading per rail per cycle, tagged by sensor_id
so battery (INA228) and Pi rails coexist on the same `power` SensorType.

Replaces the abandoned INA237 attempt — putting an external shunt in
the 5 V path cost too much voltage headroom and tripped undervoltage
warnings under load. The PMIC measures everything an INA237 would and
more, with zero added series resistance.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from shitbox.collectors.base import BaseCollector
from shitbox.storage.models import Reading, SensorType
from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Lines look like:
#   EXT5V_V volt(23)=5.07812500V
#   3V3_SYS_A current(1)=0.51914219A
# Capture: (rail_name, kind ∈ {V, A}, value)
_LINE_RE = re.compile(
    r"^(?P<rail>[A-Z0-9_]+)_(?P<kind>[VA])\s+(?:volt|current)\(\d+\)=(?P<value>-?\d+\.\d+)[VA]$"
)


@dataclass
class PMICRailReading:
    """One Pi 5 PMIC rail at one moment — voltage and/or current."""

    rail: str                            # e.g. "EXT5V", "3V3_SYS", "VDD_CORE"
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None

    @property
    def value(self) -> float:
        # BaseCollector plumbing wants a single scalar; voltage is the
        # natural "primary" here. Falls back to current if voltage-less.
        if self.voltage_v is not None:
            return self.voltage_v
        if self.current_a is not None:
            return self.current_a
        return 0.0


class PMICCollector(BaseCollector["PMICRailReading"]):
    """Polls `vcgencmd pmic_read_adc` and emits a Reading per rail.

    Graceful degradation: if vcgencmd is missing (dev laptop, container
    without the Pi userland) or fails, the collector logs once and emits
    nothing. The engine carries on.
    """

    def __init__(
        self,
        config: object,
        callback: Optional[object] = None,
    ) -> None:
        super().__init__(
            name="pmic",
            sample_rate_hz=getattr(config, "sample_rate_hz", 1.0),
            callback=callback,
        )
        self._enabled: bool = bool(getattr(config, "enabled", True))
        self._vcgencmd_path: str = str(getattr(config, "vcgencmd_path", "vcgencmd"))
        self._available: bool = False

    def setup(self) -> None:
        if not self._enabled:
            log.info("pmic_disabled")
            return
        # Resolve the binary once; if it's not on PATH the collector silently
        # disables itself rather than spamming subprocess errors every cycle.
        resolved = shutil.which(self._vcgencmd_path)
        if not resolved:
            log.warning("pmic_vcgencmd_missing", path=self._vcgencmd_path)
            return
        self._vcgencmd_path = resolved
        self._available = True
        log.info("pmic_collector_init", vcgencmd=self._vcgencmd_path)

    def _run_vcgencmd(self) -> Optional[str]:
        try:
            result = subprocess.run(
                [self._vcgencmd_path, "pmic_read_adc"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning("pmic_vcgencmd_failed", error=str(e))
            return None
        if result.returncode != 0:
            log.warning("pmic_vcgencmd_nonzero", rc=result.returncode, err=result.stderr.strip())
            return None
        return result.stdout

    @staticmethod
    def _parse(output: str) -> List[PMICRailReading]:
        """Parse vcgencmd output into per-rail readings.

        Pairs `<rail>_V` and `<rail>_A` lines into one PMICRailReading.
        Rails with only one of V or A still get emitted with the other
        field None (e.g. EXT5V is voltage-only on Pi 5; HDMI is
        current-only).
        """
        per_rail: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _LINE_RE.match(line)
            if not m:
                continue
            rail = m.group("rail")
            kind = m.group("kind")
            value = float(m.group("value"))
            v, a = per_rail.get(rail, (None, None))
            if kind == "V":
                v = value
            else:
                a = value
            per_rail[rail] = (v, a)
        return [
            PMICRailReading(rail=rail, voltage_v=v, current_a=a)
            for rail, (v, a) in sorted(per_rail.items())
        ]

    def collect(self) -> Optional[List[PMICRailReading]]:
        if not self._enabled or not self._available:
            return None
        raw = self._run_vcgencmd()
        if raw is None:
            return None
        readings = self._parse(raw)
        return readings if readings else None

    def read(self) -> Optional["PMICRailReading"]:
        """BaseCollector expects one item; PMIC has many rails per cycle.

        Mirrors the DS18B20 pattern: fan out via the callback ourselves
        and return None so the base loop doesn't try to wrap the list.
        """
        readings = self.collect()
        if readings and self.callback:
            for r in readings:
                self.callback(self.to_reading(r))
        return None

    def to_reading(self, data: "PMICRailReading") -> Reading:
        # Rail name lower-cased so it lines up with the existing
        # sensor_id convention (battery, pi, ...).
        return Reading(
            sensor_type=SensorType.POWER,
            bus_voltage_v=data.voltage_v,
            current_ma=(data.current_a * 1000.0) if data.current_a is not None else None,
            sensor_id=data.rail.lower(),
        )
