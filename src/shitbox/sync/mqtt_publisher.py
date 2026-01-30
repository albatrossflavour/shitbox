"""MQTT publisher for real-time telemetry streaming."""

import json
import queue
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

from shitbox.storage.models import HealthStatus, Reading
from shitbox.utils.config import MQTTConfig
from shitbox.utils.logging import get_logger

log = get_logger(__name__)


class MQTTPublisher:
    """Publish telemetry data to MQTT broker.

    Handles connection management, reconnection, and message queuing.
    Uses QoS 1 (at least once) for reliable delivery.
    """

    def __init__(self, config: MQTTConfig):
        """Initialise MQTT publisher.

        Args:
            config: MQTT configuration.
        """
        self.config = config
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.Lock()
        self._message_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._publish_thread: Optional[threading.Thread] = None
        self._running = False

    def connect(self) -> None:
        """Connect to MQTT broker."""
        if self._client is not None:
            return

        log.info(
            "connecting_to_mqtt",
            broker=self.config.broker_host,
            port=self.config.broker_port,
        )

        # Create client with MQTTv5 or fall back to v3.1.1
        try:
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.config.client_id,
                protocol=mqtt.MQTTv5,
            )
        except TypeError:
            # Older paho-mqtt version
            self._client = mqtt.Client(
                client_id=self.config.client_id,
                protocol=mqtt.MQTTv311,
            )

        # Set up callbacks
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish = self._on_publish

        # Set Last Will and Testament
        self._client.will_set(
            topic=f"{self.config.topic_prefix}/status/online",
            payload=json.dumps({"online": False}),
            qos=1,
            retain=True,
        )

        # Set credentials if provided
        if self.config.username:
            self._client.username_pw_set(
                self.config.username, self.config.password
            )

        # Configure reconnect behaviour
        self._client.reconnect_delay_set(
            min_delay=self.config.reconnect_delay_min,
            max_delay=self.config.reconnect_delay_max,
        )

        # Start network loop in background
        self._client.loop_start()

        # Connect (non-blocking)
        try:
            self._client.connect_async(
                self.config.broker_host,
                self.config.broker_port,
                keepalive=60,
            )
        except Exception as e:
            log.error("mqtt_connect_error", error=str(e))

        # Start publish thread
        self._running = True
        self._publish_thread = threading.Thread(
            target=self._publish_loop, daemon=True
        )
        self._publish_thread.start()

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        self._running = False

        if self._client:
            # Publish offline status
            self._client.publish(
                topic=f"{self.config.topic_prefix}/status/online",
                payload=json.dumps({"online": False}),
                qos=1,
                retain=True,
            )

            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

        if self._publish_thread and self._publish_thread.is_alive():
            self._publish_thread.join(timeout=2.0)

        log.info("mqtt_disconnected")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle connection established."""
        # Handle both MQTTv5 and v3.1.1 callback signatures
        if hasattr(reason_code, "is_failure"):
            # MQTTv5
            if reason_code.is_failure:
                log.error("mqtt_connect_failed", reason=str(reason_code))
                return
        elif reason_code != 0:
            # MQTTv3.1.1
            log.error("mqtt_connect_failed", reason_code=reason_code)
            return

        with self._lock:
            self._connected = True

        log.info("mqtt_connected")

        # Publish online status
        client.publish(
            topic=f"{self.config.topic_prefix}/status/online",
            payload=json.dumps({"online": True}),
            qos=1,
            retain=True,
        )

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        """Handle disconnection."""
        with self._lock:
            self._connected = False

        log.warning("mqtt_connection_lost", reason=str(reason_code))

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        """Handle publish acknowledgement."""
        log.debug("mqtt_message_published", mid=mid)

    def publish_reading(self, reading: Reading) -> bool:
        """Queue a reading for publishing.

        Args:
            reading: Reading to publish.

        Returns:
            True if queued, False if queue is full.
        """
        if not self._running:
            return False

        topic = f"{self.config.topic_prefix}/{reading.sensor_type.value}"
        payload = json.dumps(reading.to_mqtt_payload())

        try:
            self._message_queue.put_nowait((topic, payload))
            return True
        except queue.Full:
            log.warning("mqtt_queue_full", dropped_sensor=reading.sensor_type.value)
            return False

    def publish_health(self, health: HealthStatus) -> bool:
        """Queue a health status for publishing.

        Args:
            health: Health status to publish.

        Returns:
            True if queued, False if queue is full.
        """
        if not self._running:
            return False

        topic = f"{self.config.topic_prefix}/status/health"
        payload = json.dumps(health.to_mqtt_payload())

        try:
            self._message_queue.put_nowait((topic, payload))
            return True
        except queue.Full:
            return False

    def _publish_loop(self) -> None:
        """Background thread for publishing queued messages."""
        while self._running:
            try:
                topic, payload = self._message_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if not self.is_connected:
                # Re-queue if disconnected (or drop if queue full)
                try:
                    self._message_queue.put_nowait((topic, payload))
                except queue.Full:
                    pass
                time.sleep(0.1)
                continue

            try:
                result = self._client.publish(
                    topic=topic,
                    payload=payload,
                    qos=self.config.qos,
                )
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    log.warning("mqtt_publish_failed", rc=result.rc)
            except Exception as e:
                log.error("mqtt_publish_error", error=str(e))

    @property
    def is_connected(self) -> bool:
        """Check if connected to broker."""
        with self._lock:
            return self._connected

    @property
    def queue_size(self) -> int:
        """Get number of messages waiting to be published."""
        return self._message_queue.qsize()
