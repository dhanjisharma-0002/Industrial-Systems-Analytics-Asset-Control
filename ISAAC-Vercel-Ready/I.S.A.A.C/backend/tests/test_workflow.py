"""
Comprehensive automated tests for ISAAC Phase 9 Software Workflow Actions,
State Transitions, Alert Acknowledgment, and Maintenance Lifecycle.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, MaintenanceRecord, SensorData, WorkflowLog


@pytest.fixture
def test_db_session():
    """Create an isolated in-memory SQLite database session with seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed Machine
    m1 = Machine(
        machine_id="M1001",
        type="M",
        location="Bay 2 - CNC Spindle Unit",
        status="OPERATIONAL",
    )
    session.add(m1)
    session.commit()

    # Seed Telemetry
    s1 = SensorData(
        machine_id="M1001",
        udi=10,
        air_temperature_k=298.5,
        process_temperature_k=308.8,
        rotational_speed_rpm=1520.0,
        torque_nm=42.0,
        tool_wear_min=45,
    )
    session.add(s1)
    session.commit()

    # Seed Alert
    alt1 = Alert(
        alert_id="ALT-M1001-01",
        machine_id="M1001",
        severity="WARNING",
        alert_type="THERMAL_MARGIN_WARNING",
        message="Process temperature elevated during roughing cycle.",
        status="ACTIVE",
    )
    session.add(alt1)
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(test_db_session):
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()



# =========================================================================
# 1. Machine Detail Workflow Profile
# =========================================================================

def test_machine_detail_workflow_fields(client: TestClient):
    response = client.get("/api/machines/M1001")
    assert response.status_code == 200
    data = response.json()
    assert data["machine_id"] == "M1001"
    assert data["type"] == "M"
    assert data["location"] == "Bay 2 - CNC Spindle Unit"
    assert data["status"] == "OPERATIONAL"
    assert data["current_health_score"] is not None
    assert data["current_failure_probability"] is not None
    assert len(data["active_alerts"]) == 1
    assert data["active_alerts"][0]["alert_id"] == "ALT-M1001-01"


# =========================================================================
# 2. Workflow Action: Acknowledge Alert
# =========================================================================

def test_acknowledge_alert_action(client: TestClient, test_db_session):
    payload = {
        "alert_id": "ALT-M1001-01",
        "performed_by": "Dhananjay Sharma (Reliability Eng)",
        "notes": "Reviewed telemetry; thermal margin is stabilizing.",
    }
    response = client.post("/api/machines/M1001/workflow/acknowledge-alert", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action_type"] == "ACKNOWLEDGE_ALERT"

    # Verify Alert status in DB
    alert = test_db_session.query(Alert).filter(Alert.alert_id == "ALT-M1001-01").first()
    assert alert.status == "ACKNOWLEDGED"
    assert alert.acknowledged_by == "Dhananjay Sharma (Reliability Eng)"
    assert alert.acknowledged_at is not None

    # Verify Workflow Log in DB
    logs = test_db_session.query(WorkflowLog).filter(WorkflowLog.machine_id == "M1001").all()
    assert len(logs) >= 1
    assert any(l.action_type == "ACKNOWLEDGE_ALERT" for l in logs)


def test_acknowledge_alert_not_found(client: TestClient):
    payload = {
        "alert_id": "NONEXISTENT_ALERT",
        "performed_by": "Operator",
    }
    response = client.post("/api/machines/M1001/workflow/acknowledge-alert", json=payload)
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


# =========================================================================
# 3. Workflow Action: Create Maintenance Request
# =========================================================================

def test_create_maintenance_request_action(client: TestClient, test_db_session):
    payload = {
        "performed_by": "Elena Rostova (Lead)",
        "notes": "Spindle drive vibration increasing; request scheduled maintenance.",
        "urgency": "HIGH",
    }
    response = client.post("/api/machines/M1001/workflow/maintenance-request", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action_type"] == "MAINTENANCE_REQUEST"
    assert data["new_status"] == "MAINTENANCE_REQUIRED"

    # Verify Machine status in DB
    machine = test_db_session.query(Machine).filter(Machine.machine_id == "M1001").first()
    assert machine.status == "MAINTENANCE_REQUIRED"

    # Verify MaintenanceRecord in DB
    records = test_db_session.query(MaintenanceRecord).filter(MaintenanceRecord.machine_id == "M1001").all()
    assert any(r.failure_type == "MAINT_REQUEST" for r in records)


# =========================================================================
# 4. Workflow Action: Start Inspection
# =========================================================================

def test_start_inspection_action(client: TestClient, test_db_session):
    payload = {
        "performed_by": "Marcus Brody (Technician)",
        "notes": "Initiated visual and acoustic inspection of spindle housing.",
    }
    response = client.post("/api/machines/M1001/workflow/start-inspection", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action_type"] == "START_INSPECTION"
    assert data["new_status"] == "INSPECTION_IN_PROGRESS"

    machine = test_db_session.query(Machine).filter(Machine.machine_id == "M1001").first()
    assert machine.status == "INSPECTION_IN_PROGRESS"


# =========================================================================
# 5. Workflow Action: Complete Maintenance
# =========================================================================

def test_complete_maintenance_action(client: TestClient, test_db_session):
    payload = {
        "performed_by": "Elena Rostova (Lead)",
        "notes": "Spindle bearings lubricated, tool inserts replaced, coolant flushed.",
        "resolution_details": "Asset test-run nominal; ready for production load.",
    }
    response = client.post("/api/machines/M1001/workflow/complete-maintenance", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action_type"] == "COMPLETE_MAINTENANCE"
    assert data["new_status"] == "OPERATIONAL"

    # Verify Machine status restored to OPERATIONAL
    machine = test_db_session.query(Machine).filter(Machine.machine_id == "M1001").first()
    assert machine.status == "OPERATIONAL"

    # Verify active alerts are resolved
    active_alerts = test_db_session.query(Alert).filter(
        Alert.machine_id == "M1001",
        Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
    ).all()
    assert len(active_alerts) == 0


# =========================================================================
# 6. Workflow History & Alerts Endpoints
# =========================================================================

def test_get_machine_alerts_and_workflow_history_endpoints(client: TestClient):
    # Fetch alerts
    resp_alerts = client.get("/api/machines/M1001/alerts")
    assert resp_alerts.status_code == 200
    assert isinstance(resp_alerts.json(), list)

    # Fetch workflow logs
    resp_logs = client.get("/api/machines/M1001/workflow-history")
    assert resp_logs.status_code == 200
    assert isinstance(resp_logs.json(), list)
