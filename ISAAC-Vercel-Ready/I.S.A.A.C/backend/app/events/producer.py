"""
Industrial Kafka Telemetry Producer for ISAAC.
Provides JSON serialization, partition routing by machine_id, retry logic,
structured logging, and automatic graceful fallback to local in-memory stream.
"""

import json
import time
from typing import Any, Callable, Dict, Optional

from ..config import Settings, get_settings
from ..logger import logger
from .schemas import IndustrialEventEnvelope


class KafkaTelemetryProducer:
    """
    Configurable Apache Kafka producer for streaming industrial telemetry events.
    Gracefully falls back to local processing if Kafka is disabled or unavailable.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.bootstrap_servers = self.settings.kafka_bootstrap_servers
        self.topic = self.settings.kafka_topic_telemetry
        self.client_id = self.settings.kafka_client_id
        self.enabled = self.settings.kafka_enabled
        self.max_retries = self.settings.kafka_max_retries
        self.timeout_ms = self.settings.kafka_timeout_ms

        self._producer_instance: Any = None
        self._is_connected = False
        self.messages_sent = 0
        self.messages_failed = 0
        self.fallback_messages_sent = 0
        self.last_event_id: Optional[str] = None
        self.last_event_timestamp: Optional[str] = None

        if self.enabled:
            self._initialize_kafka_producer()
        else:
            logger.info("Kafka producer is disabled (KAFKA_ENABLED=False). Local fallback stream will be used.")

    def _initialize_kafka_producer(self) -> bool:
        """Attempt to instantiate real Kafka producer client if libraries are installed."""
        # Try kafka-python
        try:
            from kafka import KafkaProducer  # type: ignore

            self._producer_instance = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: str(k).encode("utf-8") if k else None,
                retries=self.max_retries,
                request_timeout_ms=self.timeout_ms,
            )
            self._is_connected = True
            logger.info(
                f"Kafka producer successfully initialized and connected to '{self.bootstrap_servers}' "
                f"(Topic: '{self.topic}', Client: '{self.client_id}')"
            )
            return True
        except ImportError:
            logger.info("Kafka client library ('kafka-python') not installed. Using local fallback stream.")
            self._is_connected = False
            return False
        except Exception as e:
            logger.warning(
                f"Kafka broker connection failed at '{self.bootstrap_servers}': {e}. "
                f"Operating in graceful local fallback mode."
            )
            self._is_connected = False
            return False

    @property
    def is_connected(self) -> bool:
        """Check if Kafka producer is actively connected to broker."""
        return self._is_connected and self._producer_instance is not None

    def publish(
        self,
        event: Dict[str, Any] | IndustrialEventEnvelope,
        fallback_handler: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        """
        Publish an industrial sensor event to Kafka topic or route to local fallback handler.
        """
        # Ensure event is validated envelope dict
        if isinstance(event, IndustrialEventEnvelope):
            event_payload = event.model_dump()
        elif isinstance(event, dict):
            try:
                envelope = IndustrialEventEnvelope(**event)
                event_payload = envelope.model_dump()
            except Exception:
                # If schema validation fails on custom fields, pass original dict with event_id
                event_payload = dict(event)
                if "event_id" not in event_payload:
                    event_payload["event_id"] = f"EVT-{int(time.time() * 1000)}"
                if "timestamp_utc" not in event_payload:
                    event_payload["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        else:
            raise ValueError(f"Invalid event object type: {type(event)}")

        event_id = event_payload.get("event_id", "UNKNOWN")
        machine_id = str(event_payload.get("machine_id", "M14860"))
        timestamp = event_payload.get("timestamp_utc", event_payload.get("timestamp"))

        self.last_event_id = event_id
        self.last_event_timestamp = str(timestamp)

        # 1. Real Kafka Publishing Path
        if self.is_connected:
            try:
                future = self._producer_instance.send(
                    self.topic,
                    key=machine_id,
                    value=event_payload,
                )
                # Flush or wait if needed
                self.messages_sent += 1
                logger.info(
                    f"[KAFKA_PRODUCED] topic={self.topic} | key={machine_id} | "
                    f"event_id={event_id} | total_sent={self.messages_sent}"
                )
                return {
                    "success": True,
                    "mode": "KAFKA",
                    "event_id": event_id,
                    "topic": self.topic,
                    "machine_id": machine_id,
                    "timestamp": timestamp,
                }
            except Exception as exc:
                self.messages_failed += 1
                logger.error(
                    f"Kafka publishing error on topic '{self.topic}' for event {event_id}: {exc}. "
                    f"Activating graceful fallback handler."
                )
                # Fall through to fallback handler

        # 2. Local Fallback Routing Path
        self.fallback_messages_sent += 1
        logger.debug(
            f"[FALLBACK_ROUTED] event_id={event_id} | machine={machine_id} | "
            f"total_fallback={self.fallback_messages_sent}"
        )

        result = None
        if fallback_handler is not None:
            try:
                result = fallback_handler(event_payload)
            except Exception as fb_err:
                logger.error(f"Fallback handler error for event {event_id}: {fb_err}")

        return {
            "success": True,
            "mode": "LOCAL_FALLBACK",
            "event_id": event_id,
            "topic": self.topic,
            "machine_id": machine_id,
            "timestamp": timestamp,
            "fallback_result": result,
        }

    def flush(self) -> None:
        """Flush pending producer messages if connected."""
        if self.is_connected:
            try:
                self._producer_instance.flush(timeout=2.0)
            except Exception as e:
                logger.warning(f"Error flushing Kafka producer: {e}")

    def close(self) -> None:
        """Close producer connection cleanly."""
        if self._producer_instance is not None:
            try:
                self._producer_instance.close(timeout=2.0)
            except Exception as e:
                logger.warning(f"Error closing Kafka producer: {e}")
            self._producer_instance = None
            self._is_connected = False
            logger.info("Kafka producer closed.")
