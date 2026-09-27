"""
Comprehensive automated unit & integration tests for Phase 14 Maintenance-Management Workflow.
Tests:
1. Generation of Predicted Maintenance Recommendations (Task 1 & 8).
2. Creation of Confirmed Maintenance Requests with all required fields (Task 2 & 3).
3. Status Lifecycle Workflow: PENDING -> IN_PROGRESS -> COMPLETED (Task 4).
4. Cancellation workflow with justified reason: CANCELLED (Task 4).
5. Maintenance History recording (Task 5).
6. Linking Anomaly Alerts to Maintenance Requests and Auto-Resolution (Task 6).
7. 4-Section Dashboard assembly: Due, Pending, In Progress, Completed (Task 7).
8. Clear distinction between Predicted Needs and Confirmed Work (Task 8).
9. Database check constraints on status and priority (Task 9).
10. REST API Endpoints verification (Task 10).
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, MaintenanceWorkOrder, SensorData, WorkflowLog, utc_now
from backend.app.services.maintenance_service import MaintenanceService
from backend.app.repositories.work_order_repository import WorkOrderRepository
from backend.app.repositories.alert_repository import AlertRepository


@pytest.fixture
def maint_test_env():
    """Create an isolated in-memory SQLite database session with seed machines and test client."""
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
        machine_id="M_MNT_01",
        type="L",
        location="Bay 1 - Spindle Alpha",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    m2 = Machine(
        machine_id="M_MNT_02",
        type="M",
        location="Bay 2 - Spindle Beta",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    m3 = Machine(
        machine_id="M_MNT_03",
        type="H",
        location="Bay 3 - Heavy Mill",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    session.add_all([m1, m2, m3])
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, session, engine

    app.dependency_overrides.clear()
    session.close()


# =========================================================================
# 1. Predicted Maintenance Recommendations (Task 1 & Task 8)
# =========================================================================

def test_predicted_maintenance_recommendation_generation(maint_test_env):
    """Test that machines with active alerts or high ML risk generate structured Predicted Needs."""
    _, session, _ = maint_test_env
    maint_svc = MaintenanceService(session)
    alert_repo = AlertRepository(session)

    # 1. Initially with nominal machines, recommendations list is empty
    recs = maint_svc.get_predicted_recommendations()
    assert len(recs) == 0

    # 2. Trigger an active alert on M_MNT_01
    alert_repo.create_alert(
        alert_id="ALT-MNT-OSF-01",
        machine_id="M_MNT_01",
        severity="CRITICAL",
        alert_type="OVERSTRAIN_FAILURE",
        message="Spindle overstrain detected: 14000 min*Nm",
        status="OPEN",
        source="TELEMETRY_RULE",
    )

    # 3. Seed high-risk telemetry reading on M_MNT_02
    sensor = SensorData(
        machine_id="M_MNT_02",
        udi=9001,
        air_temperature_k=304.5,
        process_temperature_k=313.8,
        rotational_speed_rpm=1200.0,
        torque_nm=75.0,
        tool_wear_min=240,
        recorded_at=utc_now(),
    )
    session.add(sensor)
    session.commit()

    # 4. Evaluate predicted recommendations
    recs = maint_svc.get_predicted_recommendations()
    assert len(recs) >= 2

    # Verify fields of condition-alert recommendation
    rec_osf = next((r for r in recs if r["machine_id"] == "M_MNT_01"), None)
    assert rec_osf is not None
    assert rec_osf["priority"] == "CRITICAL"
    assert rec_osf["status"] == "DUE"
    assert rec_osf["source"] == "CONDITION_ALERT"
    assert rec_osf["linked_alert_id"] == "ALT-MNT-OSF-01"
    assert "Immediate Spindle Halt" in rec_osf["recommendation"]

    # Verify fields of ML-based recommendation
    rec_ml = next((r for r in recs if r["machine_id"] == "M_MNT_02"), None)
    assert rec_ml is not None
    assert rec_ml["status"] == "DUE"
    assert rec_ml["source"] == "PREDICTIVE_ML"
    assert rec_ml["health_score"] < 70.0


# =========================================================================
# 2. Create Maintenance Request with Required Fields (Task 2 & 3)
# =========================================================================

def test_create_maintenance_request_with_required_fields(maint_test_env):
    """Test creating a confirmed maintenance work order with all required fields."""
    _, session, _ = maint_test_env
    maint_svc = MaintenanceService(session)

    # Required fields: machine, issue, risk, recommendation, priority, status, created_at
    wo = maint_svc.create_maintenance_request(
        machine_id="M_MNT_01",
        issue="Spindle vibration and tool chatter observed.",
        risk="HIGH (78%)",
        recommendation="Replace spindle bearings and calibrate cutting tool offsets.",
        priority="HIGH",
        requested_by="Operator Miller",
    )

    assert wo.id is not None
    assert wo.request_id.startswith("MNT-M_MNT_01-")
    assert wo.machine_id == "M_MNT_01"
    assert wo.issue == "Spindle vibration and tool chatter observed."
    assert wo.risk == "HIGH (78%)"
    assert wo.recommendation == "Replace spindle bearings and calibrate cutting tool offsets."
    assert wo.priority == "HIGH"
    assert wo.status == "PENDING"
    assert wo.work_type == "CONFIRMED_WORK_ORDER"
    assert wo.created_at is not None
    assert wo.completed_at is None

    # Machine status should be updated to MAINTENANCE_REQUIRED
    machine = session.query(Machine).filter(Machine.machine_id == "M_MNT_01").first()
    assert machine.status == "MAINTENANCE_REQUIRED"

    # Verify audit log was recorded in WorkflowLog
    logs = session.query(WorkflowLog).filter(WorkflowLog.machine_id == "M_MNT_01").all()
    assert len(logs) >= 1
    assert logs[-1].action_type == "MAINTENANCE_REQUEST"


# =========================================================================
# 3. Status Lifecycle: PENDING -> IN_PROGRESS -> COMPLETED (Task 4 & 5)
# =========================================================================

def test_maintenance_lifecycle_workflow(maint_test_env):
    """Test full workflow transitions: PENDING -> IN_PROGRESS -> COMPLETED."""
    _, session, _ = maint_test_env
    maint_svc = MaintenanceService(session)

    # 1. Create PENDING work order
    wo = maint_svc.create_maintenance_request(
        machine_id="M_MNT_02",
        issue="Overheated spindle motor.",
        priority="CRITICAL",
        requested_by="Reliability Lead",
    )
    req_id = wo.request_id
    assert wo.status == "PENDING"

    # 2. Start work order -> IN_PROGRESS
    start_res = maint_svc.start_work_order(
        request_id=req_id,
        assigned_to="Technician Dave",
        notes="Safety lockouts engaged. Spindle disassembled.",
    )
    assert start_res["success"] is True
    assert start_res["new_status"] == "IN_PROGRESS"

    wo_in_prog = maint_svc.work_order_repo.get_by_request_id(req_id)
    assert wo_in_prog.status == "IN_PROGRESS"
    assert wo_in_prog.assigned_to == "Technician Dave"
    assert "Safety lockouts" in wo_in_prog.resolution_notes

    # Machine status should be updated
    machine = session.query(Machine).filter(Machine.machine_id == "M_MNT_02").first()
    assert machine.status == "INSPECTION_IN_PROGRESS"

    # 3. Complete work order -> COMPLETED
    complete_res = maint_svc.complete_work_order(
        request_id=req_id,
        performed_by="Technician Dave",
        resolution_notes="Coolant channels flushed and drive belts replaced.",
        action_taken="Replaced drive belts & coolant pump.",
    )
    assert complete_res["success"] is True
    assert complete_res["new_status"] == "COMPLETED"

    wo_completed = maint_svc.work_order_repo.get_by_request_id(req_id)
    assert wo_completed.status == "COMPLETED"
    assert wo_completed.completed_at is not None
    assert "drive belts replaced" in wo_completed.resolution_notes
    assert "Replaced drive belts" in wo_completed.resolution_notes

    # Machine status should be restored to OPERATIONAL
    machine = session.query(Machine).filter(Machine.machine_id == "M_MNT_02").first()
    assert machine.status == "OPERATIONAL"

    # 4. Verify in history (Task 5)
    hist, total = maint_svc.get_history(machine_id="M_MNT_02")
    assert total >= 1
    assert any(h["request_id"] == req_id for h in hist)
    assert hist[0]["duration_minutes"] is not None


# =========================================================================
# 4. Cancellation Workflow with Justification: CANCELLED (Task 4)
# =========================================================================

def test_maintenance_cancellation_workflow(maint_test_env):
    """Test cancelling a work order with mandatory justification reason."""
    _, session, _ = maint_test_env
    maint_svc = MaintenanceService(session)

    wo = maint_svc.create_maintenance_request(
        machine_id="M_MNT_03",
        issue="Suspected torque sensor drift.",
        priority="LOW",
        requested_by="Junior Operator",
    )
    req_id = wo.request_id

    # Cancel work order
    cancel_res = maint_svc.cancel_work_order(
        request_id=req_id,
        performed_by="Plant Supervisor",
        cancellation_reason="Sensor recalibrated remotely; physical disassembly not needed.",
    )
    assert cancel_res["success"] is True
    assert cancel_res["new_status"] == "CANCELLED"

    wo_cancelled = maint_svc.work_order_repo.get_by_request_id(req_id)
    assert wo_cancelled.status == "CANCELLED"
    assert wo_cancelled.completed_at is not None
    assert "Sensor recalibrated remotely" in wo_cancelled.cancellation_reason

    # Machine restored to OPERATIONAL
    machine = session.query(Machine).filter(Machine.machine_id == "M_MNT_03").first()
    assert machine.status == "OPERATIONAL"


# =========================================================================
# 5. Link Alerts to Maintenance and Auto-Resolution (Task 6)
# =========================================================================

def test_link_alerts_to_maintenance_and_auto_resolution(maint_test_env):
    """Test linking an active alert to a work order and auto-resolving it upon work completion."""
    _, session, _ = maint_test_env
    maint_svc = MaintenanceService(session)
    alert_repo = AlertRepository(session)

    # 1. Create an active alert
    alert, _ = alert_repo.create_alert(
        alert_id="ALT-LINK-001",
        machine_id="M_MNT_01",
        severity="CRITICAL",
        alert_type="TOOL_WEAR_FAILURE",
        message="Tool wear reached 245 minutes.",
        status="OPEN",
    )
    assert alert.status == "OPEN"

    # 2. Create work order linked to this alert
    wo = maint_svc.create_maintenance_request(
        machine_id="M_MNT_01",
        issue="Critical tool wear breach.",
        priority="CRITICAL",
        alert_id="ALT-LINK-001",
        requested_by="Lead Engineer",
    )
    assert wo.alert_id == "ALT-LINK-001"

    # 3. Start work order
    maint_svc.start_work_order(
        request_id=wo.request_id,
        assigned_to="Tech Sarah",
    )

    # 4. Complete work order with resolve_linked_alerts=True
    maint_svc.complete_work_order(
        request_id=wo.request_id,
        performed_by="Tech Sarah",
        resolution_notes="Tool insert replaced and zeroed.",
        action_taken="New Carbide Insert Installed.",
        resolve_linked_alerts=True,
    )

    # 5. Verify alert status is automatically updated to RESOLVED
    updated_alert = alert_repo.get_by_alert_id("ALT-LINK-001")
    assert updated_alert.status == "RESOLVED"
    assert updated_alert.resolved_by == "Tech Sarah"
    assert updated_alert.resolved_at is not None
    assert "Resolved via Work Order" in updated_alert.notes


# =========================================================================
# 6. Clearly Distinguish Predicted Needs vs Confirmed Work (Task 8)
# =========================================================================

def test_distinguish_predicted_need_from_confirmed_work(maint_test_env):
    """Test clear structural distinction between predicted recommendations and confirmed work orders."""
    _, session, _ = maint_test_env
    maint_svc = MaintenanceService(session)
    alert_repo = AlertRepository(session)

    # Create an alert to trigger a predicted recommendation
    alert_repo.create_alert(
        alert_id="ALT-PRED-DIFF-01",
        machine_id="M_MNT_01",
        severity="WARNING",
        alert_type="HEAT_DISSIPATION_FAILURE",
        message="Delta T < 8.6K thermal collapse",
        status="OPEN",
    )

    # Create a confirmed work order on M_MNT_02
    wo = maint_svc.create_maintenance_request(
        machine_id="M_MNT_02",
        issue="Scheduled motor greasing.",
        priority="LOW",
    )

    dashboard = maint_svc.get_dashboard_data()

    # Verify 'due' contains predicted recommendations (recommendation items)
    assert len(dashboard["due"]) >= 1
    pred_item = dashboard["due"][0]
    assert pred_item["status"] == "DUE"
    assert pred_item["source"] in ["CONDITION_ALERT", "PREDICTIVE_ML"]
    assert "recommendation_id" in pred_item

    # Verify 'pending' contains confirmed work orders
    assert len(dashboard["pending"]) >= 1
    confirmed_item = dashboard["pending"][0]
    assert confirmed_item["status"] == "PENDING"
    assert confirmed_item["work_type"] == "CONFIRMED_WORK_ORDER"
    assert "request_id" in confirmed_item


# =========================================================================
# 7. Database Constraints Validation (Task 9)
# =========================================================================

def test_database_constraints(maint_test_env):
    """Test database check constraints on status and priority fields."""
    _, session, _ = maint_test_env

    # 1. Invalid status should fail constraint
    with pytest.raises(IntegrityError):
        bad_status_wo = MaintenanceWorkOrder(
            request_id="MNT-BAD-STATUS-01",
            machine_id="M_MNT_01",
            issue="Test bad status",
            priority="MEDIUM",
            status="INVALID_STATUS",  # Constraint breach
            created_at=utc_now(),
        )
        session.add(bad_status_wo)
        session.commit()

    session.rollback()

    # 2. Invalid priority should fail constraint
    with pytest.raises(IntegrityError):
        bad_pri_wo = MaintenanceWorkOrder(
            request_id="MNT-BAD-PRI-01",
            machine_id="M_MNT_01",
            issue="Test bad priority",
            priority="SUPER_CRITICAL",  # Constraint breach
            status="PENDING",
            created_at=utc_now(),
        )
        session.add(bad_pri_wo)
        session.commit()

    session.rollback()


# =========================================================================
# 8. REST API Endpoints & 4-Section Dashboard Verification (Task 7 & 10)
# =========================================================================

def test_maintenance_dashboard_and_summary_api(maint_test_env):
    """Test all Phase 14 REST API endpoints."""
    client, session, _ = maint_test_env
    alert_repo = AlertRepository(session)

    # 1. Seed alert on M_MNT_01 -> generates Due recommendation
    alert_repo.create_alert(
        alert_id="ALT-API-MNT-01",
        machine_id="M_MNT_01",
        severity="CRITICAL",
        alert_type="OVERSTRAIN_FAILURE",
        message="Spindle overload condition.",
        status="OPEN",
    )

    # 2. POST /api/maintenance/requests (Create confirmed work order)
    payload_create = {
        "machine_id": "M_MNT_02",
        "issue": "Drive belt slip detected via torque drop.",
        "risk": "HIGH",
        "priority": "HIGH",
        "requested_by": "Engineer Jack",
    }
    resp_create = client.post("/api/maintenance/requests", json=payload_create)
    assert resp_create.status_code == 200
    wo_data = resp_create.json()
    req_id = wo_data["request_id"]
    assert wo_data["status"] == "PENDING"
    assert wo_data["machine_id"] == "M_MNT_02"

    # 3. GET /api/maintenance/dashboard (Check all 4 sections)
    resp_dash = client.get("/api/maintenance/dashboard")
    assert resp_dash.status_code == 200
    dash_data = resp_dash.json()
    assert "summary" in dash_data
    assert "due" in dash_data
    assert "pending" in dash_data
    assert "in_progress" in dash_data
    assert "completed" in dash_data

    assert len(dash_data["due"]) >= 1
    assert len(dash_data["pending"]) >= 1
    assert dash_data["summary"]["pending_count"] >= 1

    # 4. POST /api/maintenance/requests/{request_id}/start
    resp_start = client.post(f"/api/maintenance/requests/{req_id}/start", json={"assigned_to": "Tech Carlos"})
    assert resp_start.status_code == 200
    assert resp_start.json()["new_status"] == "IN_PROGRESS"

    # 5. POST /api/maintenance/requests/{request_id}/complete
    resp_comp = client.post(
        f"/api/maintenance/requests/{req_id}/complete",
        json={
            "performed_by": "Tech Carlos",
            "resolution_notes": "Tensioner pulley replaced.",
            "action_taken": "Replaced Pulley Unit",
        },
    )
    assert resp_comp.status_code == 200
    assert resp_comp.json()["new_status"] == "COMPLETED"

    # 6. GET /api/maintenance/history
    resp_hist = client.get("/api/maintenance/history")
    assert resp_hist.status_code == 200
    hist_list = resp_hist.json()
    assert any(h["request_id"] == req_id for h in hist_list)

    # 7. GET /api/maintenance/summary
    resp_sum = client.get("/api/maintenance/summary")
    assert resp_sum.status_code == 200
    sum_res = resp_sum.json()
    assert sum_res["completed_count"] >= 1
