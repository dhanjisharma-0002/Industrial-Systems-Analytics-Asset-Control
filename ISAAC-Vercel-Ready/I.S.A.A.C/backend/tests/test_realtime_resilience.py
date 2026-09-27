"""
Automated unit & integration test suite for Real-Time Telemetry Streaming,
WebSocket connection lifecycles, reconnect handling, dead-socket resilience,
and error recovery in ISAAC (Phase 18 Testing Pass).
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, SensorData
from backend.app.websocket_manager import ConnectionManager, manager


@pytest.fixture
def resilience_test_env():
    """Setup isolated SQLite DB session and TestClient for WebSocket and real-time streaming."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Pre-seed machine
    m = Machine(
        machine_id="M_RES_01",
        type="M",
        location="Bay 5 - Spindle C",
        status="OPERATIONAL",
    )
    session.add(m)
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


def test_websocket_multiple_subscribers_broadcast(resilience_test_env):
    """Verify that multiple concurrent WebSocket subscribers receive real-time telemetry broadcasts."""
    client, _ = resilience_test_env

    with client.websocket_connect("/ws/telemetry") as ws1:
        # Handshake ws1
        msg1 = ws1.receive_json()
        assert msg1["type"] == "CONNECTION_ESTABLISHED"

        with client.websocket_connect("/ws/telemetry") as ws2:
            # Handshake ws2
            msg2 = ws2.receive_json()
            assert msg2["type"] == "CONNECTION_ESTABLISHED"

            # Ingest live telemetry
            payload = {
                "machine_id": "M_RES_01",
                "machine_type": "M",
                "air_temperature_k": 298.5,
                "process_temperature_k": 308.8,
                "rotational_speed_rpm": 1520.0,
                "torque_nm": 41.5,
                "tool_wear_min": 12,
                "data_source": "CONCURRENT STREAM TEST",
            }
            res = client.post("/api/telemetry/ingest", json=payload)
            assert res.status_code == 200

            # Both subscribers should receive the TELEMETRY_UPDATE packet
            b1 = ws1.receive_json()
            b2 = ws2.receive_json()

            assert b1["type"] == "TELEMETRY_UPDATE"
            assert b1["machine_id"] == "M_RES_01"
            assert b2["type"] == "TELEMETRY_UPDATE"
            assert b2["machine_id"] == "M_RES_01"


def test_websocket_reconnect_simulation(resilience_test_env):
    """Verify client reconnect behavior: connecting, disconnecting, and cleanly reconnecting."""
    client, _ = resilience_test_env

    # 1. Connect first time
    with client.websocket_connect("/ws/telemetry") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTION_ESTABLISHED"
        ws.send_json({"type": "PING"})
        pong = ws.receive_json()
        assert pong["type"] == "PONG"

    # 2. Reconnect immediately
    with client.websocket_connect("/ws/telemetry") as ws_reconnected:
        msg_re = ws_reconnected.receive_json()
        assert msg_re["type"] == "CONNECTION_ESTABLISHED"

        # Stream an event to verify reconnected socket is active
        payload = {
            "machine_id": "M_RES_01",
            "machine_type": "M",
            "air_temperature_k": 298.6,
            "process_temperature_k": 309.0,
            "rotational_speed_rpm": 1500.0,
            "torque_nm": 42.0,
            "tool_wear_min": 14,
            "data_source": "RECONNECTED_CLIENT",
        }
        res = client.post("/api/telemetry/ingest", json=payload)
        assert res.status_code == 200

        broadcast = ws_reconnected.receive_json()
        assert broadcast["type"] == "TELEMETRY_UPDATE"
        assert broadcast["data_source"] == "RECONNECTED_CLIENT"


def test_websocket_unknown_or_malformed_message_handling(resilience_test_env):
    """Verify WebSocket safely ignores or handles invalid/unknown message types without crashing."""
    client, _ = resilience_test_env

    with client.websocket_connect("/ws/telemetry") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "CONNECTION_ESTABLISHED"

        # Send an unexpected action/payload
        ws.send_json({"type": "UNKNOWN_ACTION_99", "data": "random_payload"})

        # Connection should remain alive and respond to valid PING
        ws.send_json({"type": "PING"})
        pong = ws.receive_json()
        assert pong["type"] == "PONG"


def test_connection_manager_dead_socket_resilience():
    """Verify ConnectionManager handles dead sockets gracefully during broadcast without failing."""
    mgr = ConnectionManager()

    class MockDeadWebSocket:
        def __init__(self):
            self.closed = False

        async def send_text(self, data: str):
            raise RuntimeError("Socket disconnected unexpectedly")

    dead_ws = MockDeadWebSocket()
    mgr.active_connections.add(dead_ws)
    assert len(mgr.active_connections) == 1

    # Broadcast should catch the exception, remove the dead socket, and not raise
    asyncio.run(mgr.broadcast({"type": "SYSTEM_HEARTBEAT"}))
    assert len(mgr.active_connections) == 0
