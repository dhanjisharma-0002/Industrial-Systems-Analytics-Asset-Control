"""
Comprehensive automated unit & integration tests for Phase 13 Alert-Management System.
Tests condition triggers, duplicate prevention, persistence, lifecycle workflows (OPEN -> ACKNOWLEDGED -> RESOLVED),
critical alert counts, timestamps, and REST API endpoints.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, WorkflowLog, utc_now
from backend.app.services.alert_service import AlertService
from backend.app.repositories.alert_repository import AlertRepository


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

    # Seed Machines
    m1 = Machine(
        machine_id="M_ALERT_01",
        type="L",
        location="Bay 1 - Spindle Alpha",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    m2 = Machine(
        machine_id="M_ALERT_02",
        type="M",
        location="Bay 2 - Spindle Beta",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    session.add_all([m1, m2])
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(test_db_session):
    """TestClient configured with in-memory database dependency override."""
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def alert_test_env(client: TestClient, test_db_session: Session):
    """Fixture providing clean test environment with client and db session."""
    yield client, test_db_session


# =========================================================================
# 1. Condition-Based Alert Generation (Task 1)
# =========================================================================

def test_overstrain_condition_triggers_critical_alert(alert_test_env):
    """Test that tool wear * torque exceeding safety threshold generates a CRITICAL OSF alert."""
    _, session = alert_test_env
    svc = AlertService(session)

    # For Type L: limit is 11,000 min·Nm. Test value: 200 min * 65 Nm = 13,000 min·Nm (breach)
    alerts = svc.evaluate_and_trigger_alerts(
        machine_id="M_ALERT_01",
        machine_type="L",
        air_temperature_k=298.15,
        process_temperature_k=308.65,
        rotational_speed_rpm=1500.0,
        torque_nm=65.0,
        tool_wear_min=200.0,
    )

    assert len(alerts) >= 1
    osf_alert = next((a for a in alerts if a.alert_type == "OVERSTRAIN_FAILURE"), None)
    assert osf_alert is not None
    assert osf_alert.severity == "CRITICAL"
    assert osf_alert.status == "OPEN"
    assert "Overstrain limit breached" in osf_alert.message
    assert osf_alert.source == "TELEMETRY_RULE"


def test_heat_dissipation_collapse_triggers_critical_alert(alert_test_env):
    """Test that constrained thermal delta (<8.6K) at low speed (<1380 RPM) triggers HDF alert."""
    _, session = alert_test_env
    svc = AlertService(session)

    # Process: 304.0 K, Air: 298.0 K -> ΔT = 6.0 K (< 8.6 K) at 1200 RPM (< 1380 RPM)
    alerts = svc.evaluate_and_trigger_alerts(
        machine_id="M_ALERT_02",
        machine_type="M",
        air_temperature_k=298.0,
        process_temperature_k=304.0,
        rotational_speed_rpm=1200.0,
        torque_nm=40.0,
        tool_wear_min=50.0,
    )

    hdf_alert = next((a for a in alerts if a.alert_type == "HEAT_DISSIPATION_FAILURE"), None)
    assert hdf_alert is not None
    assert hdf_alert.severity == "CRITICAL"
    assert hdf_alert.status == "OPEN"
    assert "Heat dissipation collapse" in hdf_alert.message


def test_power_failure_envelope_breach_triggers_critical_alert(alert_test_env):
    """Test that mechanical power outside 3,500 - 9,000 W triggers PWF alert."""
    _, session = alert_test_env
    svc = AlertService(session)

    # Torque 80 Nm * 1800 RPM * 2*pi/60 = 15,079 W (exceeds 9,000 W limit)
    alerts = svc.evaluate_and_trigger_alerts(
        machine_id="M_ALERT_01",
        machine_type="L",
        air_temperature_k=298.0,
        process_temperature_k=308.0,
        rotational_speed_rpm=1800.0,
        torque_nm=80.0,
        tool_wear_min=30.0,
    )

    pwf_alert = next((a for a in alerts if a.alert_type == "POWER_FAILURE"), None)
    assert pwf_alert is not None
    assert pwf_alert.severity == "CRITICAL"
    assert "Mechanical power envelope breach" in pwf_alert.message


def test_tool_wear_threshold_alerts(alert_test_env):
    """Test warning at 200 min and critical at 240 min tool wear."""
    _, session = alert_test_env
    svc = AlertService(session)

    # 1. Warning tier (210 min)
    alerts_warn = svc.evaluate_and_trigger_alerts(
        machine_id="M_ALERT_02",
        machine_type="M",
        air_temperature_k=298.0,
        process_temperature_k=308.0,
        rotational_speed_rpm=1500.0,
        torque_nm=40.0,
        tool_wear_min=210.0,
    )
    twf_warn = next((a for a in alerts_warn if a.alert_type == "TOOL_WEAR_FAILURE"), None)
    assert twf_warn is not None
    assert twf_warn.severity == "WARNING"

    # 2. Critical tier (245 min)
    alerts_crit = svc.evaluate_and_trigger_alerts(
        machine_id="M_ALERT_01",
        machine_type="L",
        air_temperature_k=298.0,
        process_temperature_k=308.0,
        rotational_speed_rpm=1500.0,
        torque_nm=40.0,
        tool_wear_min=245.0,
    )
    twf_crit = next((a for a in alerts_crit if a.alert_type == "TOOL_WEAR_FAILURE"), None)
    assert twf_crit is not None
    assert twf_crit.severity == "CRITICAL"


def test_nominal_conditions_produce_no_false_alerts(alert_test_env):
    """Test that machines operating within nominal physical bounds trigger zero false alerts."""
    _, session = alert_test_env
    svc = AlertService(session)

    alerts = svc.evaluate_and_trigger_alerts(
        machine_id="M_ALERT_01",
        machine_type="L",
        air_temperature_k=298.15,
        process_temperature_k=308.65,
        rotational_speed_rpm=1550.0,
        torque_nm=42.0,
        tool_wear_min=25.0,
        prediction={"risk_level": "NOMINAL", "failure_probability": 0.01, "health_score": 98.5},
    )
    assert len(alerts) == 0


# =========================================================================
# 2. Duplicate Prevention (Task 9)
# =========================================================================

def test_duplicate_prevention_on_repeated_telemetry_ticks(alert_test_env):
    """Verify that multiple consecutive ticks with the same breach condition generate ONLY 1 open alert."""
    _, session = alert_test_env
    svc = AlertService(session)

    # Ingest 5 consecutive ticks with overstrain breach
    for _ in range(5):
        alerts = svc.evaluate_and_trigger_alerts(
            machine_id="M_ALERT_01",
            machine_type="L",
            air_temperature_k=298.0,
            process_temperature_k=308.0,
            rotational_speed_rpm=1500.0,
            torque_nm=70.0,
            tool_wear_min=200.0,
        )
        assert len(alerts) >= 1

    # Verify only 1 alert of type OVERSTRAIN_FAILURE exists in DB for this machine
    db_alerts = session.query(Alert).filter(
        Alert.machine_id == "M_ALERT_01",
        Alert.alert_type == "OVERSTRAIN_FAILURE"
    ).all()
    assert len(db_alerts) == 1
    assert db_alerts[0].status == "OPEN"


# =========================================================================
# 3. Alert Lifecycle Workflow (OPEN -> ACKNOWLEDGED -> RESOLVED) (Tasks 5 & 6)
# =========================================================================

def test_alert_lifecycle_workflow(alert_test_env):
    """Test full workflow transitions: OPEN -> ACKNOWLEDGED -> RESOLVED with audit timestamps."""
    client, session = alert_test_env
    svc = AlertService(session)

    # 1. Create initial OPEN alert
    alert, _ = svc.alert_repo.create_alert(
        alert_id="ALT-WORKFLOW-TEST-01",
        machine_id="M_ALERT_01",
        severity="CRITICAL",
        alert_type="OVERSTRAIN_FAILURE",
        message="Critical overstrain hazard detected.",
        status="OPEN",
    )
    assert alert.status == "OPEN"
    assert alert.acknowledged_at is None
    assert alert.resolved_at is None

    # 2. Transition to ACKNOWLEDGED (Task 5)
    ack_res = svc.acknowledge_alert(
        alert_id="ALT-WORKFLOW-TEST-01",
        performed_by="Engineer Jordan",
        notes="Inspecting spindle tool clamps.",
    )
    assert ack_res["success"] is True
    assert ack_res["new_status"] == "ACKNOWLEDGED"

    updated_alert = svc.get_by_alert_id("ALT-WORKFLOW-TEST-01")
    assert updated_alert.status == "ACKNOWLEDGED"
    assert updated_alert.acknowledged_by == "Engineer Jordan"
    assert updated_alert.acknowledged_at is not None

    # Verify audit log
    logs = session.query(WorkflowLog).filter(WorkflowLog.machine_id == "M_ALERT_01").all()
    assert any(l.action_type == "ACKNOWLEDGE_ALERT" and l.performed_by == "Engineer Jordan" for l in logs)

    # 3. Transition to RESOLVED (Task 6)
    res_res = svc.resolve_alert(
        alert_id="ALT-WORKFLOW-TEST-01",
        performed_by="Lead Technician Dave",
        notes="Tool insert replaced and torque calibrated.",
        resolution_action="Tool insert replacement",
    )
    assert res_res["success"] is True
    assert res_res["new_status"] == "RESOLVED"

    resolved_alert = svc.get_by_alert_id("ALT-WORKFLOW-TEST-01")
    assert resolved_alert.status == "RESOLVED"
    assert resolved_alert.resolved_by == "Lead Technician Dave"
    assert resolved_alert.resolved_at is not None
    assert "Tool insert replaced" in resolved_alert.notes


# =========================================================================
# 4. Critical Alert Count & Summary Aggregations (Task 7 & 8)
# =========================================================================

def test_critical_alert_count_and_summary(alert_test_env):
    """Test critical alert counts and summary breakdown computation."""
    _, session = alert_test_env
    repo = AlertRepository(session)

    # Seed diverse alerts
    repo.create_alert("ALT-S1", "M_ALERT_01", "CRITICAL", "OSF", "Crit 1", status="OPEN")
    repo.create_alert("ALT-S2", "M_ALERT_01", "CRITICAL", "HDF", "Crit 2", status="ACKNOWLEDGED")
    repo.create_alert("ALT-S3", "M_ALERT_02", "WARNING", "TWF", "Warn 1", status="OPEN")
    repo.create_alert("ALT-S4", "M_ALERT_02", "INFO", "HEARTBEAT", "Info 1", status="OPEN")
    repo.create_alert("ALT-S5", "M_ALERT_01", "CRITICAL", "OLD_PWF", "Crit Resolved", status="RESOLVED")

    # Critical count should only include active (OPEN/ACKNOWLEDGED) critical alerts: ALT-S1 and ALT-S2
    crit_count = repo.get_critical_count()
    assert crit_count == 2

    # Summary
    summary = repo.get_alert_summary()
    assert summary["total_alerts"] == 5
    assert summary["open_alerts"] == 3
    assert summary["acknowledged_alerts"] == 1
    assert summary["resolved_alerts"] == 1
    assert summary["critical_alerts"] == 2
    assert summary["warning_alerts"] == 1
    assert summary["info_alerts"] == 1


# =========================================================================
# 5. REST API Endpoints Verification (Tasks 3, 4, 5, 6, 7, 8)
# =========================================================================

def test_alert_api_endpoints(alert_test_env):
    """Test all Alert Management REST API endpoints."""
    client, session = alert_test_env
    repo = AlertRepository(session)

    # Seed sample alert
    repo.create_alert(
        alert_id="ALT-API-001",
        machine_id="M_ALERT_01",
        severity="CRITICAL",
        alert_type="OVERSTRAIN_FAILURE",
        message="API endpoint test alert.",
        status="OPEN",
    )

    # 1. GET /api/alerts (list with pagination)
    resp = client.get("/api/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data
    assert data["total"] >= 1
    assert any(a["alert_id"] == "ALT-API-001" for a in data["data"])

    # 2. GET /api/alerts/active
    resp_active = client.get("/api/alerts/active")
    assert resp_active.status_code == 200
    active_data = resp_active.json()
    assert any(a["alert_id"] == "ALT-API-001" for a in active_data)

    # 3. GET /api/alerts/summary
    resp_summary = client.get("/api/alerts/summary")
    assert resp_summary.status_code == 200
    sum_data = resp_summary.json()
    assert sum_data["critical_alerts"] >= 1

    # 4. GET /api/alerts/critical/count
    resp_cnt = client.get("/api/alerts/critical/count")
    assert resp_cnt.status_code == 200
    assert resp_cnt.json()["count"] >= 1

    # 5. GET /api/alerts/{alert_id}
    resp_detail = client.get("/api/alerts/ALT-API-001")
    assert resp_detail.status_code == 200
    assert resp_detail.json()["machine_id"] == "M_ALERT_01"

    # 6. POST /api/alerts/{alert_id}/acknowledge
    ack_payload = {
        "performed_by": "Operator Alex",
        "notes": "Acknowledged via REST API.",
    }
    resp_ack = client.post("/api/alerts/ALT-API-001/acknowledge", json=ack_payload)
    assert resp_ack.status_code == 200
    assert resp_ack.json()["new_status"] == "ACKNOWLEDGED"

    # 7. POST /api/alerts/{alert_id}/resolve
    res_payload = {
        "performed_by": "Lead Dhananjay Sharma",
        "notes": "Resolved via REST API after inspection.",
        "resolution_action": "Clamp adjusted",
    }
    resp_res = client.post("/api/alerts/ALT-API-001/resolve", json=res_payload)
    assert resp_res.status_code == 200
    assert resp_res.json()["new_status"] == "RESOLVED"

    # 8. GET /api/alerts/history
    resp_hist = client.get("/api/alerts/history")
    assert resp_hist.status_code == 200
    hist_data = resp_hist.json()
    assert any(a["alert_id"] == "ALT-API-001" for a in hist_data)
