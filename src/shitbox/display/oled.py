"""OLED status display service for SSD1306 128x64."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any, Optional

from shitbox.utils.config import OLEDConfig
from shitbox.utils.logging import get_logger

if TYPE_CHECKING:
    from shitbox.events.engine import UnifiedEngine

log = get_logger(__name__)


class OLEDDisplayService:
    """Daemon thread that renders system status to an SSD1306 OLED.

    Follows the BatchSyncService pattern: start()/stop() lifecycle,
    hardware imports inside start() so missing libs don't crash the engine.
    """

    def __init__(self, config: OLEDConfig, engine: UnifiedEngine) -> None:
        self.config = config
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._display: Any = None
        self._image: Any = None
        self._draw: Any = None
        self._font: Any = None

    def start(self) -> None:
        """Initialise I2C + SSD1306 and start the render thread."""
        if self._running:
            return

        try:
            import adafruit_ssd1306
            import board
            import busio
            from PIL import Image, ImageDraw, ImageFont

            i2c = busio.I2C(board.SCL, board.SDA)
            self._display = adafruit_ssd1306.SSD1306_I2C(
                128, 64, i2c, addr=self.config.address
            )
            self._display.fill(0)
            self._display.show()

            self._image = Image.new("1", (128, 64))
            self._draw = ImageDraw.Draw(self._image)
            self._font = ImageFont.load_default()

            log.info(
                "oled_display_started",
                address=hex(self.config.address),
                interval=self.config.update_interval_seconds,
            )
        except Exception as e:
            log.error("oled_display_init_failed", error=str(e))
            self._display = None
            return

        self._running = True
        self._thread = threading.Thread(target=self._display_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the render thread and clear the display."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        if self._display:
            try:
                self._display.fill(0)
                self._display.show()
            except Exception:
                pass

        log.info("oled_display_stopped")

    def _display_loop(self) -> None:
        """Main render loop."""
        while self._running:
            try:
                self._render()
            except Exception as e:
                log.error("oled_render_error", error=str(e))
            time.sleep(self.config.update_interval_seconds)

    def _draw_text(
        self, x: int, y: int, text: str, inverted: bool = False
    ) -> None:
        """Draw text, optionally inverted (white bg, black text)."""
        if inverted:
            bbox = self._font.getbbox(text)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            self._draw.rectangle((x, y, x + w + 1, y + h + 3), fill=255)
            self._draw.text((x + 1, y), text, font=self._font, fill=0)
        else:
            self._draw.text((x, y), text, font=self._font, fill=255)

    def _render(self) -> None:
        """Fetch status from engine and draw 4 lines to the OLED."""
        if not self._display or not self._draw:
            return

        status = self.engine.get_status()

        # Clear
        self._draw.rectangle((0, 0, 127, 63), fill=0)

        # Line 1: GPS + speed
        #   gpsd down       → inverted "GPS:---"
        #   gpsd up, no fix → inverted "GPS:NO FIX"
        #   has fix         → normal "GPS:5sat  45km/h"
        gps_connected = status["gps_available"]
        gps_fix = status["gps_has_fix"]
        if gps_fix:
            sats = status["satellites"]
            sat_str = f"GPS:{sats}sat" if sats is not None else "GPS:OK"
            speed = status["speed_kmh"]
            speed_str = f"{speed:.0f}km/h" if speed else "0km/h"
            self._draw_text(0, 0, sat_str)
            self._draw_text(90, 0, speed_str)
        elif gps_connected:
            self._draw_text(0, 0, "GPS:NO FIX", inverted=True)
        else:
            self._draw_text(0, 0, "GPS:---", inverted=True)

        # Line 2: peak G, event count, recording — REC inverted when active
        peak_g = status.get("peak_g", 0.0)
        events = status["events_captured"]
        recording = status["recording"]
        self._draw_text(0, 16, f"{peak_g:.1f}g")
        self._draw_text(42, 16, f"EVT:{events}")
        if recording:
            self._draw_text(96, 16, "REC", inverted=True)

        # Line 3: sensor health — each inverted when failed
        imu_ok = status["imu_ok"]
        env_ok = status["env_ok"]
        pwr_ok = status["pwr_ok"]
        self._draw_text(0, 32, "IMU" if imu_ok else "IMU", inverted=not imu_ok)
        self._draw_text(44, 32, "ENV" if env_ok else "ENV", inverted=not env_ok)
        self._draw_text(88, 32, "PWR" if pwr_ok else "PWR", inverted=not pwr_ok)

        # Line 4: network, sync backlog, CPU temp — NET inverted when down
        net_ok = status["net_connected"]
        backlog = status["sync_backlog"]
        cpu_temp = status["cpu_temp"]
        temp_str = f"{cpu_temp:.0f}C" if cpu_temp is not None else "---"
        self._draw_text(0, 48, "NET", inverted=not net_ok)
        self._draw_text(36, 48, f"BKL:{backlog}")
        self._draw_text(96, 48, temp_str)

        self._display.image(self._image)
        self._display.show()
