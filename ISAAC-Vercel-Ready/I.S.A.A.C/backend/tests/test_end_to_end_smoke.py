"""
Comprehensive End-to-End System Smoke Test for ISAAC (Phase 18 Testing Pass).

Tests complete pipeline:
Sensor Event
  → ML Inference & Prediction
  → Database Persistence
  → Supervisory Alert Generation
  → Real-Time WebSocket Streaming
  → Maintenance Request & Workflow Execution
  → Resolution & Machine Health Restoration
  → Dashboard Operational Aggregates Verification
"""

import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, MaintenanceWorkOrder, SensorData, WorkflowLog, utc_now
from backend.app.websocket_manager import manager


@pytest.fixture
def smoke_test_env():
    """Setup in-memory SQLite database and authenticated TestClient for full E2E smoke test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Pre-seed industrial machine
    machine = Machine(
        machine_id="M_E2E_SMOKE",
        type="M",
        location="Bay 7 - High-Precision Milling Unit",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    session.add(machine)
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


def test_complete_end_to_end_operational_pipeline_smoke(smoke_test_env):
    """
    Full End-to-End Smoke Test:
    1. Connect WebSocket client.
    2. Post severe sensor telemetry event.
    3. Verify real-time ML prediction and response payload.
    4. Verify DB persistence of telemetry and machine status transition.
    5. Verify supervisory alert generation in database.
    6. Verify WebSocket broadcast packet delivered with full prediction and alert payload.
    7. Acknowledge alert.
    8. Create maintenance work order linked to alert.
    9. Progress work order to IN_PROGRESS.
    10. Complete maintenance work order with resolution notes.
    11. Verify alert is auto-resolved and machine status restored to OPERATIONAL.
    12. Verify dashboard analytics reflect all persisted records.
    """
    client, session = smoke_test_env

    # 1. Establish WebSocket connection to stream
    with client.websocket_connect("/ws/telemetry") as websocket:
        init_greeting = websocket.receive_json()
        assert init_greeting["type"] == "CONNECTION_ESTABLISHED"

        # 2. Ingest critical overstrain / thermal anomaly telemetry event
        sensor_payload = {
            "machine_id": "M_E2E_SMOKE",
            "machine_type": "M",
            "air_temperature_k": 303.5,
            "process_temperature_k": 313.8,
            "rotational_speed_rpm": 1250.0,
            "torque_nm": 76.5,
            "tool_wear_min": 240,
            "data_source": "E2E_SMOKE_TEST_GENERATOR",
        }

        ingest_res = client.post("/api/telemetry/ingest", json=sensor_payload)
        assert ingest_res.status_code == 200, ingest_res.text
        ingest_data = ingest_res.json()

        # 3. Verify ML Inference & Risk Analysis
        assert ingest_data["success"] is True
        assert ingest_data["machine_id"] == "M_E2E_SMOKE"
        assert ingest_data["machine_status"] in ["WARNING", "CRITICAL"]

        pred = ingest_data["prediction"]
        assert pred["risk_level"] in ["HIGH", "CRITICAL"]
        assert pred["failure_probability"] > 0.0
        assert pred["health_score"] < 75.0
        assert len(pred["recommendation"]) > 0

        # 4. Verify DB persistence
        db_sensor = (
            session.query(SensorData)
            .filter(SensorData.machine_id == "M_E2E_SMOKE")
            .order_by(SensorData.id.desc())
            .first()
        )
        assert db_sensor is not None
        assert db_sensor.torque_nm == 76.5
        assert db_sensor.tool_wear_min == 240

        db_machine = session.query(Machine).filter(Machine.machine_id == "M_E2E_SMOKE").first()
        assert db_machine.status in ["WARNING", "CRITICAL"]

        # 5. Verify Supervisory Alert Generation
        db_alerts = (
            session.query(Alert)
            .filter(Alert.machine_id == "M_E2E_SMOKE", Alert.status.in_(["OPEN", "ACTIVE"]))
            .all()
        )
        assert len(db_alerts) >= 1
        active_alert = db_alerts[0]
        assert active_alert.severity in ["WARNING", "CRITICAL"]
        assert active_alert.alert_id.startswith("ALT-") or active_alert.alert_id.startswith("ALT_")

        # 6. Verify WebSocket broadcast packet
        ws_broadcast = websocket.receive_json()
        assert ws_broadcast["type"] == "TELEMETRY_UPDATE"
        assert ws_broadcast["machine_id"] == "M_E2E_SMOKE"
        assert ws_broadcast["sensor_values"]["torque_nm"] == 76.5
        assert ws_broadcast["prediction"]["risk_level"] == pred["risk_level"]

        # 7. Acknowledge Alert via REST API
        ack_res = client.post(
            f"/api/alerts/{active_alert.alert_id}/acknowledge",
            json={"performed_by": "Senior Plant Operator", "notes": "Identified high torque overstrain"},
        )
        assert ack_res.status_code == 200
        ack_data = ack_res.json()
        assert ack_data["success"] is True
        assert ack_data["new_status"] == "ACKNOWLEDGED"

        # 8. Create Maintenance Work Order from Alert
        req_payload = {
            "machine_id": "M_E2E_SMOKE",
            "alert_id": active_alert.alert_id,
            "issue": "Severe torque overstrain and elevated tool wear",
            "risk": "CRITICAL",
            "recommendation": "Inspect tool bit and calibrate torque limiters",
            "priority": "HIGH",
            "requested_by": "Reliability Lead",
        }
        create_wo_res = client.post("/api/maintenance/requests", json=req_payload)
        assert create_wo_res.status_code in [200, 201], create_wo_res.text
        wo_data = create_wo_res.json()
        assert wo_data["status"] == "PENDING"
        work_order_id = wo_data["request_id"]

        # 9. Start Maintenance Execution -> IN_PROGRESS
        start_res = client.post(
            f"/api/maintenance/requests/{work_order_id}/start",
            json={"assigned_to": "Field Technician John", "notes": "Started inspection on Bay 7"},
        )
        assert start_res.status_code == 200
        assert start_res.json()["new_status"] == "IN_PROGRESS"
        assert start_res.json()["success"] is True

        # 10. Complete Maintenance Execution -> COMPLETED
        complete_res = client.post(
            f"/api/maintenance/requests/{work_order_id}/complete",
            json={
                "resolution_notes": "Replaced worn milling tool bit and recalibrated spindle drive",
                "completed_by": "Field Technician John",
            },
        )
        assert complete_res.status_code == 200
        comp_data = complete_res.json()
        assert comp_data["new_status"] == "COMPLETED"
        assert comp_data["success"] is True

        # 11. Verify Alert is now RESOLVED and Machine is restored
        session.expire_all()
        reloaded_alert = session.query(Alert).filter(Alert.alert_id == active_alert.alert_id).first()
        assert reloaded_alert.status == "RESOLVED"

        reloaded_machine = session.query(Machine).filter(Machine.machine_id == "M_E2E_SMOKE").first()
        assert reloaded_machine.status == "OPERATIONAL"

        # 12. Verify Dashboard & Query Endpoints
        machines_res = client.get("/api/machines")
        assert machines_res.status_code == 200
        machines_list = machines_res.json()
        assert len(machines_list) >= 1
        smoke_m = next(m for m in machines_list if m["machine_id"] == "M_E2E_SMOKE")
        assert smoke_m["status"] == "OPERATIONAL"

        alert_summary_res = client.get("/api/alerts/summary")
        assert alert_summary_res.status_code == 200
        summary_data = alert_summary_res.json()
        assert summary_data["resolved_alerts"] >= 1

        # Check maintenance dashboard sections
        maint_dash_res = client.get("/api/maintenance/dashboard")
        assert maint_dash_res.status_code == 200
        maint_dash = maint_dash_res.json()
        assert "completed" in maint_dash
        assert any(w["request_id"] == work_order_id for w in maint_dash["completed"])
