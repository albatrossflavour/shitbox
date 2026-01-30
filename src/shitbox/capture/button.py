"""GPIO button handler for manual capture trigger."""

import threading
import time
from typing import Callable, Optional

from shitbox.utils.logging import get_logger

log = get_logger(__name__)

# Try to import GPIO, gracefully handle if not available
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    log.warning("RPi.GPIO not available - button handler will be disabled")


class ButtonHandler:
    """Monitor physical GPIO button for capture trigger.

    Uses polling with debounce to detect button presses.
    Gracefully handles missing GPIO (e.g., on dev machine).
    """

    def __init__(
        self,
        gpio_pin: int = 17,
        on_press: Optional[Callable[[], None]] = None,
        debounce_ms: int = 50,
    ):
        """Initialise button handler.

        Args:
            gpio_pin: BCM GPIO pin number (default 17).
            on_press: Callback function when button is pressed.
            debounce_ms: Debounce time in milliseconds.
        """
        self.gpio_pin = gpio_pin
        self.on_press = on_press
        self.debounce_ms = debounce_ms

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_press_time = 0.0
        self._gpio_setup = False

    @property
    def is_available(self) -> bool:
        """Check if GPIO is available."""
        return GPIO_AVAILABLE

    def start(self) -> None:
        """Start monitoring button."""
        if not GPIO_AVAILABLE:
            log.info("button_handler_disabled", reason="GPIO not available")
            return

        if self._running:
            return

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio_setup = True
        except Exception as e:
            log.error("gpio_setup_failed", pin=self.gpio_pin, error=str(e))
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

        log.info("button_handler_started", gpio_pin=self.gpio_pin)

    def stop(self) -> None:
        """Stop monitoring button."""
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self._gpio_setup:
            try:
                GPIO.cleanup(self.gpio_pin)
            except Exception:
                pass
            self._gpio_setup = False

        log.info("button_handler_stopped")

    def _monitor_loop(self) -> None:
        """Main button monitoring loop."""
        was_pressed = False

        while self._running:
            try:
                # Read button state (active low - pressed = False/0)
                is_pressed = not GPIO.input(self.gpio_pin)

                # Detect rising edge (button just pressed)
                if is_pressed and not was_pressed:
                    now = time.time()
                    time_since_last = (now - self._last_press_time) * 1000

                    if time_since_last > self.debounce_ms:
                        log.info("button_pressed", gpio_pin=self.gpio_pin)
                        self._last_press_time = now

                        if self.on_press:
                            try:
                                self.on_press()
                            except Exception as e:
                                log.error("button_callback_error", error=str(e))

                was_pressed = is_pressed

            except Exception as e:
                log.error("button_read_error", error=str(e))

            # Poll at 100 Hz
            time.sleep(0.01)

    def simulate_press(self) -> None:
        """Simulate a button press (for testing without hardware)."""
        log.info("button_simulated_press")
        if self.on_press:
            self.on_press()
