"""
Automated test suite for ISAAC Phase 11 Real-Time Live Prediction,
Sensor Telemetry Ingestion, Validation, Alert Triggering, and WebSocket Streaming.
"""

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, SensorData
from backend.app.websocket_manager import manager


@pytest.fixture
def realtime_test_env():
    """Create isolated SQLite database session and TestClient for real-time streaming tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Pre-seed a test machine
    m1 = Machine(
        machine_id="M14860",
        type="M",
        location="Bay 1 - Spindle Line A",
        status="OPERATIONAL",
    )
    session.add(m1)
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, session

    app.dependency_overrides.clear()
    session.close()


def test_telemetry_ingest_valid_nominal_event(realtime_test_env):
    """Test ingestion of valid nominal sensor event with real ML inference and DB persistence."""
    client, session = realtime_test_env

    payload = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 298.1,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": 42.8,
        "tool_wear_min": 10,
        "data_source": "TEST SENSOR AGENT",
    }

    response = client.post("/api/telemetry/ingest", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["success"] is True
    assert data["machine_id"] == "M14860"
    assert data["machine_type"] == "M"
    assert data["udi"] >= 1
    assert data["machine_status"] == "OPERATIONAL"
    assert data["data_source"] == "TEST SENSOR AGENT"

    # Verify actual ML prediction returned (no fake values)
    pred = data["prediction"]
    assert "failure_probability" in pred
    assert 0.0 <= pred["failure_probability"] <= 1.0
    assert pred["risk_level"] in ["NOMINAL", "MODERATE", "HIGH", "CRITICAL"]
    assert 0.0 <= pred["health_score"] <= 100.0
    assert len(pred["recommendation"]) > 0
    assert "1.0.0" in pred["model_version"]

    # Verify persistence to sensor_data table
    sensor_entry = session.query(SensorData).filter(SensorData.machine_id == "M14860").first()
    assert sensor_entry is not None
    assert sensor_entry.rotational_speed_rpm == 1551.0
    assert sensor_entry.torque_nm == 42.8


def test_telemetry_ingest_critical_event_triggers_alert_and_state(realtime_test_env):
    """Test ingestion of severe degradation telemetry creates active alert and updates machine status."""
    client, session = realtime_test_env

    # Overstrain + tool wear + thermal stress event
    payload = {
        "machine_id": "M14860",
        "machine_type": "L",
        "air_temperature_k": 304.5,
        "process_temperature_k": 313.8,
        "rotational_speed_rpm": 1200.0,
        "torque_nm": 75.0,
        "tool_wear_min": 245,
        "data_source": "TEST OVERSTRAIN EVENT",
    }

    response = client.post("/api/telemetry/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Risk level should be elevated
    pred = data["prediction"]
    assert pred["risk_level"] in ["HIGH", "CRITICAL"]
    assert pred["health_score"] < 75.0

    # Machine status updated in response and database
    assert data["machine_status"] in ["WARNING", "CRITICAL"]
    machine = session.query(Machine).filter(Machine.machine_id == "M14860").first()
    assert machine.status in ["WARNING", "CRITICAL"]

    # Verify alert created in database
    alerts = session.query(Alert).filter(Alert.machine_id == "M14860", Alert.status.in_(["OPEN", "ACTIVE"])).all()
    assert len(alerts) >= 1
    assert alerts[0].severity in ["WARNING", "CRITICAL"]


def test_telemetry_ingest_malformed_validation_errors(realtime_test_env):
    """Test rejection of malformed or out-of-range sensor readings."""
    client, _ = realtime_test_env

    # 1. Missing required air_temperature_k
    bad_payload_missing = {
        "machine_id": "M14860",
        "machine_type": "M",
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": 42.8,
        "tool_wear_min": 10,
    }
    res1 = client.post("/api/telemetry/ingest", json=bad_payload_missing)
    assert res1.status_code == 422

    # 2. Out-of-bounds air temperature (> 330 K)
    bad_payload_temp = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 550.0,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": 42.8,
        "tool_wear_min": 10,
    }
    res2 = client.post("/api/telemetry/ingest", json=bad_payload_temp)
    assert res2.status_code == 422

    # 3. Negative torque (< 0 Nm)
    bad_payload_torque = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 298.1,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": -15.0,
        "tool_wear_min": 10,
    }
    res3 = client.post("/api/telemetry/ingest", json=bad_payload_torque)
    assert res3.status_code == 422

    # 4. Out-of-bounds speed (< 500 RPM)
    bad_payload_speed = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 298.1,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 200.0,
        "torque_nm": 42.8,
        "tool_wear_min": 10,
    }
    res4 = client.post("/api/telemetry/ingest", json=bad_payload_speed)
    assert res4.status_code == 422

    # 5. Out-of-bounds tool wear (> 400 min)
    bad_payload_wear = {
        "machine_id": "M14860",
        "machine_type": "M",
        "air_temperature_k": 298.1,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": 42.8,
        "tool_wear_min": 850,
    }
    res5 = client.post("/api/telemetry/ingest", json=bad_payload_wear)
    assert res5.status_code == 422


def test_telemetry_websocket_connection_and_keepalive(realtime_test_env):
    """Test WebSocket connection establishment and PING-PONG keepalive."""
    client, _ = realtime_test_env

    with client.websocket_connect("/ws/telemetry") as websocket:
        # Initial greeting packet
        initial_msg = websocket.receive_json()
        assert initial_msg["type"] == "CONNECTION_ESTABLISHED"
        assert "ISAAC Live Telemetry Stream" in initial_msg["message"]

        # Send PING keepalive
        websocket.send_json({"type": "PING"})
        pong_msg = websocket.receive_json()
        assert pong_msg["type"] == "PONG"
        assert "timestamp" in pong_msg


def test_telemetry_ingest_broadcasts_to_websocket(realtime_test_env):
    """Test that ingesting telemetry immediately broadcasts the real ML prediction payload to WebSocket subscribers."""
    client, _ = realtime_test_env

    with client.websocket_connect("/ws/telemetry") as websocket:
        # Receive connection handshake
        handshake = websocket.receive_json()
        assert handshake["type"] == "CONNECTION_ESTABLISHED"

        # Ingest a live sensor reading
        payload = {
            "machine_id": "M14860",
            "machine_type": "M",
            "air_temperature_k": 298.2,
            "process_temperature_k": 308.7,
            "rotational_speed_rpm": 1600.0,
            "torque_nm": 38.5,
            "tool_wear_min": 25,
            "data_source": "LIVE TELEMETRY STREAM",
        }
        res = client.post("/api/telemetry/ingest", json=payload)
        assert res.status_code == 200

        # Receive real-time broadcast message on WebSocket
        broadcast_packet = websocket.receive_json()
        assert broadcast_packet["type"] == "TELEMETRY_UPDATE"
        assert broadcast_packet["machine_id"] == "M14860"
        assert broadcast_packet["sensor_values"]["rotational_speed_rpm"] == 1600.0
        assert broadcast_packet["sensor_values"]["torque_nm"] == 38.5
        assert "failure_probability" in broadcast_packet["prediction"]
        assert "health_score" in broadcast_packet["prediction"]
        assert "recommendation" in broadcast_packet["prediction"]
        assert broadcast_packet["data_source"] == "LIVE TELEMETRY STREAM"
