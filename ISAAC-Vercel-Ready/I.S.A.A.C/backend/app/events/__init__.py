"""
ISAAC Industrial Event Streaming Package (Phase 16).
Provides configurable Kafka producer/consumer layer with resilient local in-memory fallback.
"""

from .schemas import IndustrialEventEnvelope, StreamStatusResponse
from .processor import process_telemetry_event
from .producer import KafkaTelemetryProducer
from .consumer import KafkaTelemetryConsumer
from .manager import EventStreamManager, get_event_stream_manager

__all__ = [
    "IndustrialEventEnvelope",
    "StreamStatusResponse",
    "process_telemetry_event",
    "KafkaTelemetryProducer",
    "KafkaTelemetryConsumer",
    "EventStreamManager",
    "get_event_stream_manager",
]
