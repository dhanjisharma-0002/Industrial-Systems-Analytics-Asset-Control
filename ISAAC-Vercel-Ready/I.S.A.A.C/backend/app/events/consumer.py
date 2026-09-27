"""
Industrial Kafka Telemetry Consumer for ISAAC.
Background consumer daemon that subscribes to industrial telemetry topic,
deserializes event envelopes, and dispatches to the shared prediction & alert processor.
"""

import json
import threading
import time
from typing import Any, Callable, Dict, Optional

from ..config import Settings, get_settings
from ..logger import logger


class KafkaTelemetryConsumer:
    """
    Asynchronous daemon consumer for industrial sensor telemetry from Apache Kafka.
    Reuses the centralized telemetry processor for ML prediction and WebSocket broadcasting.
    """

    def __init__(
        self,
        event_handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.bootstrap_servers = self.settings.kafka_bootstrap_servers
        self.topic = self.settings.kafka_topic_telemetry
        self.group_id = self.settings.kafka_consumer_group
        self.auto_offset_reset = self.settings.kafka_auto_offset_reset
        self.enabled = self.settings.kafka_enabled
        self.timeout_ms = self.settings.kafka_timeout_ms

        self.event_handler = event_handler
        self._consumer_instance: Any = None
        self._is_running = False
        self._is_connected = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.messages_consumed = 0
        self.messages_failed = 0
        self.last_consumed_event_id: Optional[str] = None
        self.last_consumed_timestamp: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        """Check if Kafka consumer is actively connected."""
        return self._is_connected and self._consumer_instance is not None

    @property
    def is_running(self) -> bool:
        """Check if consumer background thread is active."""
        return self._is_running

    def _initialize_kafka_consumer(self) -> bool:
        """Attempt to instantiate real Kafka consumer client."""
        try:
            from kafka import KafkaConsumer  # type: ignore

            self._consumer_instance = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            self._is_connected = True
            logger.info(
                f"Kafka consumer initialized on '{self.bootstrap_servers}' "
                f"(Topic: '{self.topic}', Group: '{self.group_id}')"
            )
            return True
        except ImportError:
            logger.info("Kafka client library not installed. Consumer operating in idle mode.")
            self._is_connected = False
            return False
        except Exception as e:
            logger.warning(
                f"Kafka consumer connection failed at '{self.bootstrap_servers}': {e}. "
                f"Operating in idle fallback mode."
            )
            self._is_connected = False
            return False

    def start(self) -> bool:
        """Start consumer background daemon thread."""
        with self._lock:
            if self._is_running:
                return True

            if not self.enabled:
                logger.info("Kafka consumer disabled in configuration. Skipping consumer daemon startup.")
                return False

            connected = self._initialize_kafka_consumer()
            if not connected:
                return False

            self._is_running = True
            self._thread = threading.Thread(target=self._consume_loop, daemon=True)
            self._thread.start()

        logger.info(f"Kafka consumer thread started for group '{self.group_id}' on topic '{self.topic}'.")
        return True

    def stop(self) -> None:
        """Stop consumer background daemon thread."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        if self._consumer_instance is not None:
            try:
                self._consumer_instance.close()
            except Exception as e:
                logger.warning(f"Error closing Kafka consumer: {e}")
            self._consumer_instance = None
            self._is_connected = False

        logger.info(f"Kafka consumer stopped. Total messages consumed: {self.messages_consumed}")

    def _consume_loop(self) -> None:
        """Background consumption execution loop."""
        while True:
            with self._lock:
                if not self._is_running:
                    break

            if self._consumer_instance is None:
                time.sleep(1.0)
                continue

            try:
                # Poll messages with 1-second timeout
                for message in self._consumer_instance:
                    with self._lock:
                        if not self._is_running:
                            break

                    try:
                        event_data = message.value
                        if not isinstance(event_data, dict):
                            continue

                        event_id = event_data.get("event_id", "UNKNOWN")
                        machine_id = event_data.get("machine_id", "UNKNOWN")
                        ts = event_data.get("timestamp_utc", event_data.get("timestamp"))

                        self.messages_consumed += 1
                        self.last_consumed_event_id = event_id
                        self.last_consumed_timestamp = str(ts)

                        logger.info(
                            f"[KAFKA_CONSUMED] topic={message.topic} | partition={message.partition} | "
                            f"offset={message.offset} | event_id={event_id} | machine={machine_id}"
                        )

                        # Dispatch to shared telemetry processor
                        if self.event_handler is not None:
                            self.event_handler(event_data)

                    except Exception as item_err:
                        self.messages_failed += 1
                        logger.error(f"Error processing consumed Kafka message: {item_err}")

            except Exception as loop_err:
                logger.debug(f"Consumer loop poll timeout or error: {loop_err}")
                time.sleep(0.5)
