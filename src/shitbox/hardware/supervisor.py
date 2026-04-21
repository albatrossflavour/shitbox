"""HardwareSupervisor daemon thread.

Owns alert cadence and re-adoption backoff for all manifest devices.
Reads HardwareState (Plan 01), calls per-bus probes on retry schedule,
and speaks via the TTS layer — but duplicates none of the sampler's
existing I2C recovery logic (Pitfall 6 in RESEARCH.md).

No engine wiring in this module. Plan 05 owns that.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

from shitbox.capture import speaker
from shitbox.hardware import probes as hw_probes
from shitbox.hardware import state as hw_state
from shitbox.utils.config import HardwareDeviceConfig, HardwareManifestConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class HardwareSupervisor:
    """Daemon thread: probes at boot, then ticks every second to drive
    re-adoption + alert cadence. Composes HardwareState, per-bus probes, and
    TTS — but duplicates none of the sampler's existing recovery logic."""

    TICK_INTERVAL_SECONDS: float = 1.0
    CRITICAL_RENAG_SECONDS: float = 30.0

    def __init__(
        self,
        manifest: HardwareManifestConfig,
        reprobe_callbacks: Dict[str, Callable[[], bool]],
    ) -> None:
        self.manifest = manifest
        self.reprobe = reprobe_callbacks
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._last_nag: Dict[str, float] = {}
        self._prev_state: Dict[str, hw_state.DeviceState] = {}

    def start(self) -> None:
        """Initialise state, boot-probe all devices, spawn the tick thread.

        Idempotent — a second call while already running is a no-op.
        """
        if self._running:
            return
        devices = {d.role: d.criticality for d in self.manifest.devices}
        hw_state.initialise(devices)
        self._probe_all()
        self._running = True
        self._thread = threading.Thread(
            target=self._tick_loop, daemon=True, name="hw-supervisor"
        )
        self._thread.start()
        log.info("hw_supervisor_started", device_count=len(devices))

    def stop(self) -> None:
        """Signal the tick loop to exit and join the thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        log.info("hw_supervisor_stopped")

    def _probe_all(self) -> None:
        """Boot probe: verify all manifest devices and seed HardwareState.

        If the i2c-1 bus is not bit-bang, all i2c-1 devices are marked MISSING
        without calling probe_i2c (Pitfall 1 guard).
        """
        i2c_ok = hw_probes.probe_i2c_bus_is_bitbang(1)
        if not i2c_ok:
            log.critical("hw_i2c_bus_not_bitbang", bus=1)
        for d in self.manifest.devices:
            present = self._run_probe(d, i2c_ok=i2c_ok)
            if present:
                hw_state.report_present(d.role)
            else:
                hw_state.report_missing(d.role)
        log.info("hw_probe_all_complete", i2c_bus_ok=i2c_ok)

    def _run_probe(self, d: HardwareDeviceConfig, i2c_ok: bool) -> bool:
        """Dispatch a single-shot probe for the device's bus type."""
        if d.bus == "i2c-1":
            if not i2c_ok:
                return False
            if d.address is None:
                return False
            return hw_probes.probe_i2c(1, d.address)
        if d.bus == "1-wire":
            return hw_probes.probe_onewire(d.sensor_id or "")
        if d.bus == "usb":
            return hw_probes.probe_usb_path(d.path or "")
        if d.bus == "audio":
            return hw_probes.probe_audio_label(d.label or "")
        if d.bus == "hdmi":
            return hw_probes.probe_hdmi(d.connector or "")
        if d.bus == "gpio":
            return hw_probes.probe_gpio_pin(d.pin or 0)
        log.warning("hw_unknown_bus", role=d.role, bus=d.bus)
        return False

    def _tick_loop(self) -> None:
        """Main loop: runs _tick() once per TICK_INTERVAL_SECONDS, swallowing exceptions."""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                log.error("hw_supervisor_tick_error", error=str(e))
            time.sleep(self.TICK_INTERVAL_SECONDS)

    def _tick(self) -> None:
        """One supervisor iteration.

        Walk the current snapshot:
        1. If MISSING and retry is due: call reprobe callback.
           - Success: flip PRESENT, speak restored, clear nag timer.
           - Failure: call report_missing to advance the backoff ladder.
        2. If MISSING and first detection (prev != MISSING): speak once per tier.
        3. If critical + MISSING and 30s since last nag: re-speak.
        4. If PRESENT and was MISSING (external recovery without our retry): speak restored.
        """
        now = time.monotonic()
        for role, st in hw_state.snapshot().items():
            prev = self._prev_state.get(role)

            # --- Retry branch ---
            # next_retry_at > 0 means a retry has been scheduled by report_missing.
            # next_retry_at == 0.0 on a MISSING device means it was just marked MISSING
            # and the first report_missing hasn't been called yet — no retry due.
            if (
                st.state == hw_state.DeviceState.MISSING
                and st.consecutive_misses > 0
                and now >= st.next_retry_at
            ):
                cb = self.reprobe.get(role)
                if cb is not None:
                    try:
                        if cb():
                            hw_state.report_present(role)
                            speaker.speak_hardware_restored(role, st.tier)
                            log.info("hw_restored", role=role, tier=st.tier)
                            self._last_nag.pop(role, None)
                            self._prev_state[role] = hw_state.DeviceState.PRESENT
                            continue
                    except Exception as e:
                        log.warning("hw_reprobe_error", role=role, error=str(e))
                # Reprobe failed (or no callback) — advance backoff
                hw_state.report_missing(role)

            # --- Transition / cadence branch ---
            if st.state == hw_state.DeviceState.MISSING:
                if prev != hw_state.DeviceState.MISSING:
                    # First detection: one-shot speak per tier policy.
                    # best_effort is log-only except environment (speaker enforces this too,
                    # but supervisor gates so mocked tests behave correctly).
                    if st.tier != "best_effort" or role == "environment":
                        speaker.speak_hardware_missing(role, st.tier)
                    log.info(
                        "hw_state_changed", role=role, tier=st.tier, state="missing"
                    )
                    self._last_nag[role] = now
                elif (
                    st.tier == "critical"
                    and now - self._last_nag.get(role, 0.0) >= self.CRITICAL_RENAG_SECONDS
                ):
                    # Critical re-nag every 30s
                    speaker.speak_hardware_missing(role, st.tier)
                    self._last_nag[role] = now

            elif st.state == hw_state.DeviceState.PRESENT:
                if prev == hw_state.DeviceState.MISSING:
                    # External recovery (collector reported PRESENT without supervisor retry)
                    if st.tier != "best_effort" or role == "environment":
                        speaker.speak_hardware_restored(role, st.tier)
                    log.info("hw_restored", role=role, tier=st.tier)
                    self._last_nag.pop(role, None)

            self._prev_state[role] = st.state
