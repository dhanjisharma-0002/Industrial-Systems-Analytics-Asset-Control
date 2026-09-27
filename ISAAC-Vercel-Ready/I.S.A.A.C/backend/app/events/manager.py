"""
Unified Event Stream Manager for ISAAC (Phase 16).
Orchestrates Kafka producer, Kafka consumer, and resilient Local Fallback stream.
"""

from typing import Any, Callable, Dict, Optional
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..logger import logger
from ..websocket_manager import WebSocketManager, manager as default_ws_manager
from .consumer import KafkaTelemetryConsumer
from .processor import process_telemetry_event
from .producer import KafkaTelemetryProducer
from .schemas import IndustrialEventEnvelope, StreamStatusResponse


class EventStreamManager:
    """
    Singleton manager coordinating the entire industrial event streaming pipeline:
    Sensor Simulator / Ingestion -> Kafka Producer -> Kafka Topic -> Consumer -> Prediction Service -> WebSocket -> Dashboard
    With automatic, graceful local in-memory fallback.
    """

    def __init__(
        self,
        db_session_factory: Optional[Callable[[], Session]] = None,
        ws_manager: Optional[WebSocketManager] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.db_session_factory = db_session_factory
        self.ws_manager = ws_manager or default_ws_manager

        self.producer = KafkaTelemetryProducer(settings=self.settings)
        self.consumer = KafkaTelemetryConsumer(
            event_handler=self._handle_stream_event,
            settings=self.settings,
        )

        self._is_active = True
        logger.info(
            f"EventStreamManager initialized. Mode: {'KAFKA' if self.producer.is_connected else 'LOCAL_FALLBACK'} "
            f"(Kafka Enabled: {self.settings.kafka_enabled})"
        )

    def bind_dependencies(
        self,
        db_session_factory: Callable[[], Session],
        ws_manager: Optional[WebSocketManager] = None,
    ) -> None:
        """Dynamically bind or update database session factory and websocket manager."""
        self.db_session_factory = db_session_factory
        if ws_manager is not None:
            self.ws_manager = ws_manager

    def start(self) -> None:
        """Start streaming layer components."""
        self._is_active = True
        if self.settings.kafka_enabled:
            self.consumer.start()

    def stop(self) -> None:
        """Stop streaming layer components cleanly."""
        self._is_active = False
        self.consumer.stop()
        self.producer.close()
        logger.info("EventStreamManager stopped.")

    def publish_telemetry(
        self,
        event: Dict[str, Any] | IndustrialEventEnvelope,
    ) -> Dict[str, Any]:
        """
        Publish telemetry reading into the streaming pipeline.
        If Kafka is active, dispatches over the wire to Kafka topic.
        If Kafka is inactive or fails, executes local fallback handler synchronously.
        """
        return self.producer.publish(
            event=event,
            fallback_handler=self._handle_stream_event,
        )

    def _handle_stream_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal event sink that runs ML prediction, alert evaluations, DB persistence,
        and WebSocket broadcasting.
        """
        if self.db_session_factory is None:
            # Fallback lazy database import if not explicitly bound
            from ..database import get_session_factory, create_database_engine
            engine = create_database_engine(self.settings)
            self.db_session_factory = get_session_factory(engine)

        return process_telemetry_event(
            event=event_data,
            db_session_factory=self.db_session_factory,
            ws_manager=self.ws_manager,
        )

    def get_status(self) -> StreamStatusResponse:
        """Retrieve real-time event streaming metrics and operational mode."""
        is_kafka = self.producer.is_connected and self.consumer.is_connected
        mode_str = "KAFKA" if is_kafka else ("LOCAL_FALLBACK" if self._is_active else "DISABLED")

        return StreamStatusResponse(
            streaming_active=self._is_active,
            mode=mode_str,
            kafka_enabled=self.settings.kafka_enabled,
            kafka_connected=self.producer.is_connected,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            telemetry_topic=self.settings.kafka_topic_telemetry,
            predictions_topic=self.settings.kafka_topic_predictions,
            consumer_group=self.settings.kafka_consumer_group,
            messages_published=self.producer.messages_sent,
            messages_consumed=self.consumer.messages_consumed,
            messages_failed=self.producer.messages_failed + self.consumer.messages_failed,
            fallback_messages_routed=self.producer.fallback_messages_sent,
            latest_event_id=self.producer.last_event_id or self.consumer.last_consumed_event_id,
            latest_event_timestamp=self.producer.last_event_timestamp or self.consumer.last_consumed_timestamp,
            details=(
                "Operating with live Apache Kafka broker cluster"
                if is_kafka
                else "Operating with resilient in-memory local fallback stream (KAFKA_ENABLED=False or Broker Unreachable)"
            ),
        )


# Singleton Instance
_EVENT_STREAM_MANAGER: Optional[EventStreamManager] = None


def get_event_stream_manager() -> EventStreamManager:
    """Singleton getter for EventStreamManager."""
    global _EVENT_STREAM_MANAGER
    if _EVENT_STREAM_MANAGER is None:
        _EVENT_STREAM_MANAGER = EventStreamManager()
    return _EVENT_STREAM_MANAGER
