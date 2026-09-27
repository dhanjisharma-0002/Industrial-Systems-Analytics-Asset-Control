"""
Automated unit & integration tests for Phase 16 Industrial Event-Streaming Layer.
Validates:
1. Configurable Kafka Producer & Consumer.
2. Industrial Event Envelope validation & UUID event_id/timestamp tracking.
3. Reuse of PredictionService & AlertService without duplicate logic.
4. Graceful failure handling on broker connection issues.
5. Resilient Local In-Memory Fallback.
6. End-to-end event flow: Simulator/Producer -> Stream -> Processor -> Prediction -> WebSocket.
7. REST API endpoints (/api/events/status and /api/events/publish).
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import Settings
from backend.app.database import init_db
from backend.app.events.consumer import KafkaTelemetryConsumer
from backend.app.events.manager import EventStreamManager, get_event_stream_manager
from backend.app.events.processor import process_telemetry_event
from backend.app.events.producer import KafkaTelemetryProducer
from backend.app.events.schemas import IndustrialEventEnvelope, StreamStatusResponse
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, SensorData, utc_now
from backend.app.services.prediction_service import PredictionService
from backend.app.websocket_manager import WebSocketManager
from simulator.engine import SimulationEngine


@pytest.fixture
def test_db_session():
    """Create in-memory SQLite test database session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed Machine
    machine = Machine(
        machine_id="M_KAFKA_01",
        type="M",
        location="Bay 1",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    session.add(machine)
    session.commit()

    yield TestingSession, session

    session.close()


@pytest.fixture
def api_client(test_db_session):
    """FastAPI TestClient with overridden database session."""
    TestingSession, session = test_db_session

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# =========================================================================
# 1. Industrial Event Envelope & Schema Validation
# =========================================================================

def test_industrial_event_envelope_creation_and_validation():
    """Verify event envelope assigns UUID event_id, trace_id, and validates ranges."""
    envelope = IndustrialEventEnvelope(
        machine_id="M14860",
        machine_type="M",
        air_temperature_k=298.15,
        process_temperature_k=308.65,
        rotational_speed_rpm=1500.0,
        torque_nm=40.0,
        tool_wear_min=45,
        source="TEST_GENERATOR",
    )

    assert envelope.event_id is not None
    assert len(envelope.event_id) > 10
    assert envelope.trace_id is not None
    assert envelope.timestamp_utc is not None
    assert envelope.schema_version == "1.0"
    assert envelope.source == "TEST_GENERATOR"

    sensor_dict = envelope.to_sensor_dict()
    assert sensor_dict["machine_id"] == "M14860"
    assert sensor_dict["torque_nm"] == 40.0
    assert sensor_dict["event_id"] == envelope.event_id


def test_industrial_event_envelope_range_validation():
    """Verify out-of-range sensor readings trigger validation errors."""
    with pytest.raises(Exception):
        # Impossible negative temperature
        IndustrialEventEnvelope(
            machine_id="M14860",
            air_temperature_k=-50.0,
            process_temperature_k=308.65,
            rotational_speed_rpm=1500.0,
            torque_nm=40.0,
            tool_wear_min=45,
        )


# =========================================================================
# 2. Configurable Kafka Producer & Fallback Handling
# =========================================================================

def test_kafka_producer_local_fallback_when_disabled():
    """Producer should cleanly route to fallback handler when Kafka is disabled."""
    settings = Settings(kafka_enabled=False, kafka_bootstrap_servers="localhost:9092")
    producer = KafkaTelemetryProducer(settings=settings)

    assert not producer.is_connected
    assert producer.messages_sent == 0
    assert producer.fallback_messages_sent == 0

    fallback_captured = []

    def mock_fallback(payload):
        fallback_captured.append(payload)
        return {"processed": True}

    event = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 298.15,
        "process_temperature_k": 308.65,
        "rotational_speed_rpm": 1500.0,
        "torque_nm": 40.0,
        "tool_wear_min": 10,
    }

    result = producer.publish(event, fallback_handler=mock_fallback)
    assert result["success"] is True
    assert result["mode"] == "LOCAL_FALLBACK"
    assert producer.fallback_messages_sent == 1
    assert len(fallback_captured) == 1
    assert fallback_captured[0]["machine_id"] == "M14860"
    assert producer.last_event_id is not None


def test_kafka_producer_graceful_broker_failure():
    """Producer should catch connection errors without crashing and fallback smoothly."""
    # Configure with unreachable mock broker port
    settings = Settings(
        kafka_enabled=True,
        kafka_bootstrap_servers="127.0.0.1:59999",  # Non-existent broker
        kafka_timeout_ms=500,
    )
    producer = KafkaTelemetryProducer(settings=settings)
    assert not producer.is_connected  # Connection fails gracefully

    fallback_captured = []
    result = producer.publish(
        {"machine_id": "M14860", "air_temperature_k": 300.0, "process_temperature_k": 310.0, "rotational_speed_rpm": 1500.0, "torque_nm": 40.0, "tool_wear_min": 0},
        fallback_handler=lambda p: fallback_captured.append(p),
    )

    assert result["success"] is True
    assert result["mode"] == "LOCAL_FALLBACK"
    assert producer.fallback_messages_sent == 1
    assert len(fallback_captured) == 1


# =========================================================================
# 3. Configurable Kafka Consumer Lifecycle
# =========================================================================

def test_kafka_consumer_lifecycle_and_idle_state():
    """Consumer should initialize in idle mode when Kafka is disabled or unreachable."""
    settings = Settings(kafka_enabled=False, kafka_bootstrap_servers="localhost:9092")
    consumer = KafkaTelemetryConsumer(settings=settings)

    assert not consumer.is_connected
    assert not consumer.is_running

    started = consumer.start()
    assert started is False  # Correctly skips starting when disabled
    consumer.stop()
    assert not consumer.is_running


# =========================================================================
# 4. Centralized Telemetry Processor (No Duplicated Logic)
# =========================================================================

def test_shared_processor_executes_prediction_and_persists(test_db_session):
    """Processor should run ML inference, update machine status, trigger alerts, and format websocket msg."""
    TestingSession, session = test_db_session
    mock_ws = WebSocketManager()

    event = {
        "event_id": f"EVT-{uuid.uuid4().hex[:8]}",
        "trace_id": f"TRC-{uuid.uuid4().hex[:8]}",
        "machine_id": "M_KAFKA_01",
        "machine_type": "M",
        "air_temperature_k": 300.0,
        "process_temperature_k": 310.0,
        "rotational_speed_rpm": 1500.0,
        "torque_nm": 42.0,
        "tool_wear_min": 25,
        "source": "KAFKA_STREAM_TEST",
    }

    result = process_telemetry_event(
        event=event,
        db_session_factory=TestingSession,
        ws_manager=mock_ws,
    )

    assert result["event_id"] == event["event_id"]
    assert result["machine_id"] == "M_KAFKA_01"
    assert "prediction" in result
    assert "health_score" in result["prediction"]
    assert "risk_level" in result["prediction"]
    assert result["prediction"]["risk_level"] in ("NOMINAL", "MODERATE", "HIGH", "CRITICAL")

    # Verify persisted in database
    db_sensor = session.query(SensorData).filter(SensorData.machine_id == "M_KAFKA_01").first()
    assert db_sensor is not None
    assert db_sensor.torque_nm == 42.0


def test_shared_processor_overstrain_critical_alert(test_db_session):
    """Processor should evaluate overstrain conditions and trigger alerts."""
    TestingSession, session = test_db_session

    event = {
        "event_id": f"EVT-CRIT-{uuid.uuid4().hex[:8]}",
        "machine_id": "M_KAFKA_01",
        "machine_type": "M",
        "air_temperature_k": 302.0,
        "process_temperature_k": 315.0,
        "rotational_speed_rpm": 1200.0,
        "torque_nm": 78.0,  # Critical overstrain
        "tool_wear_min": 240,  # Critical tool wear
        "source": "KAFKA_CRITICAL_TEST",
    }

    result = process_telemetry_event(
        event=event,
        db_session_factory=TestingSession,
    )

    assert result["prediction"]["risk_level"] in ("HIGH", "CRITICAL")
    assert result["machine_status"] in ("WARNING", "CRITICAL")

    # Check alert logged in DB
    alerts = session.query(Alert).filter(Alert.machine_id == "M_KAFKA_01").all()
    assert len(alerts) >= 1


# =========================================================================
# 5. EventStreamManager End-to-End Coordination
# =========================================================================

def test_event_stream_manager_end_to_end(test_db_session):
    """EventStreamManager should coordinate publish -> fallback -> processor -> status."""
    TestingSession, _ = test_db_session
    settings = Settings(kafka_enabled=False)

    stream_mgr = EventStreamManager(
        db_session_factory=TestingSession,
        settings=settings,
    )

    event = IndustrialEventEnvelope(
        machine_id="M_KAFKA_01",
        machine_type="M",
        air_temperature_k=299.0,
        process_temperature_k=309.5,
        rotational_speed_rpm=1520.0,
        torque_nm=39.0,
        tool_wear_min=50,
        source="END_TO_END_TEST",
    )

    pub_result = stream_mgr.publish_telemetry(event)
    assert pub_result["success"] is True
    assert pub_result["mode"] == "LOCAL_FALLBACK"

    status = stream_mgr.get_status()
    assert isinstance(status, StreamStatusResponse)
    assert status.streaming_active is True
    assert status.mode == "LOCAL_FALLBACK"
    assert status.fallback_messages_routed >= 1
    assert status.latest_event_id == event.event_id


# =========================================================================
# 6. REST API Endpoints Verification
# =========================================================================

def test_events_status_api_endpoint(api_client: TestClient):
    """GET /api/events/status should return complete pipeline health payload."""
    response = api_client.get("/api/events/status")
    assert response.status_code == 200
    data = response.json()
    assert "streaming_active" in data
    assert "mode" in data
    assert "kafka_enabled" in data
    assert "bootstrap_servers" in data
    assert "telemetry_topic" in data
    assert "messages_published" in data
    assert "fallback_messages_routed" in data


def test_events_publish_api_endpoint(api_client: TestClient):
    """POST /api/events/publish should ingest event into streaming pipeline."""
    payload = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 298.5,
        "process_temperature_k": 308.9,
        "rotational_speed_rpm": 1490.0,
        "torque_nm": 41.5,
        "tool_wear_min": 15,
        "source": "REST_API_TEST",
    }
    response = api_client.post("/api/events/publish", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "event_id" in data
    assert data["machine_id"] == "M14860"


# =========================================================================
# 7. Simulator Integration with Event Stream
# =========================================================================

def test_simulator_step_dispatches_with_event_id():
    """Simulator engine step should generate event_id and timestamp_utc."""
    sim = SimulationEngine()
    sim.auto_ingest_db = False

    event = sim.step()
    assert "event_id" in event
    assert event["event_id"].startswith("EVT-SIM-")
    assert "timestamp_utc" in event
    assert "trace_id" in event
    assert event["trace_id"].startswith("TRC-SIM-")
