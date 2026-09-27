"""
Automated unit and integration test suite for Database Integrity, Constraints,
Relationships, and CRUD Workflows in ISAAC (Phase 18 Testing Pass).
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.models import (
    Alert,
    Base,
    Machine,
    MaintenanceRecord,
    MaintenanceWorkOrder,
    SensorData,
    User,
    WorkflowLog,
    utc_now,
)


@pytest.fixture
def test_db_session():
    """Provides an isolated in-memory SQLite database with fresh schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def test_unique_machine_id_constraint(test_db_session):
    """Verify that creating two machines with the same machine_id raises IntegrityError."""
    m1 = Machine(machine_id="M_DUP_01", type="M", location="Bay 1", status="OPERATIONAL")
    test_db_session.add(m1)
    test_db_session.commit()

    m2 = Machine(machine_id="M_DUP_01", type="L", location="Bay 2", status="OPERATIONAL")
    test_db_session.add(m2)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()


def test_unique_alert_id_constraint(test_db_session):
    """Verify that duplicate alert_id triggers an IntegrityError."""
    m = Machine(machine_id="M_ALT_01", type="H", location="Bay 1", status="OPERATIONAL")
    test_db_session.add(m)
    test_db_session.commit()

    a1 = Alert(alert_id="ALT_1001", machine_id="M_ALT_01", severity="WARNING", alert_type="OVERHEAT", message="Test alert")
    test_db_session.add(a1)
    test_db_session.commit()

    a2 = Alert(alert_id="ALT_1001", machine_id="M_ALT_01", severity="CRITICAL", alert_type="OVERHEAT", message="Duplicate alert")
    test_db_session.add(a2)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()


def test_unique_user_constraints(test_db_session):
    """Verify unique constraints on username and email in User model."""
    u1 = User(
        username="operator_bob",
        email="bob@plant.com",
        hashed_password="hash_bob_secret",
        role="OPERATOR",
    )
    test_db_session.add(u1)
    test_db_session.commit()

    # Duplicate username
    u2 = User(
        username="operator_bob",
        email="other_bob@plant.com",
        hashed_password="hash_bob_secret_2",
        role="OPERATOR",
    )
    test_db_session.add(u2)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()

    # Duplicate email
    u3 = User(
        username="operator_bob_2",
        email="bob@plant.com",
        hashed_password="hash_bob_secret_3",
        role="ENGINEER",
    )
    test_db_session.add(u3)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()


def test_work_order_check_constraints(test_db_session):
    """Verify database check constraints on MaintenanceWorkOrder status and priority."""
    m = Machine(machine_id="M_WO_01", type="M", location="Bay 1", status="OPERATIONAL")
    test_db_session.add(m)
    test_db_session.commit()

    # Invalid status should fail check constraint
    wo_bad_status = MaintenanceWorkOrder(
        request_id="REQ_BAD_01",
        machine_id="M_WO_01",
        issue="Test issue",
        risk="HIGH",
        recommendation="Fix now",
        priority="HIGH",
        status="INVALID_STATUS",
        requested_by="QA Tester",
    )
    test_db_session.add(wo_bad_status)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()

    # Invalid priority should fail check constraint
    wo_bad_priority = MaintenanceWorkOrder(
        request_id="REQ_BAD_02",
        machine_id="M_WO_01",
        issue="Test issue",
        risk="HIGH",
        recommendation="Fix now",
        priority="EXTREME_DANGER",  # not in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
        status="PENDING",
        requested_by="QA Tester",
    )
    test_db_session.add(wo_bad_priority)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()


def test_user_role_check_constraint(test_db_session):
    """Verify database check constraint on User role."""
    u_bad_role = User(
        username="super_user",
        email="super@plant.com",
        hashed_password="hash_password_str",
        role="SUPER_ADMIN_INVALID",  # not in ('VIEWER', 'OPERATOR', 'ENGINEER', 'ADMIN')
    )
    test_db_session.add(u_bad_role)
    with pytest.raises(IntegrityError):
        test_db_session.commit()
    test_db_session.rollback()


def test_relational_cascade_and_navigation(test_db_session):
    """Verify full ORM relationship traversal from Machine to all child tables."""
    machine = Machine(machine_id="M_REL_01", type="L", location="Bay 3", status="OPERATIONAL")
    test_db_session.add(machine)
    test_db_session.commit()

    sensor = SensorData(
        machine_id="M_REL_01",
        udi=101,
        air_temperature_k=298.1,
        process_temperature_k=308.6,
        rotational_speed_rpm=1500.0,
        torque_nm=40.0,
        tool_wear_min=15,
    )
    test_db_session.add(sensor)
    test_db_session.commit()

    alert = Alert(
        alert_id="ALT_REL_01",
        machine_id="M_REL_01",
        severity="WARNING",
        alert_type="THERMAL_STRESS",
        message="High temperature detected",
        status="OPEN",
        source="TELEMETRY_RULE",
    )
    test_db_session.add(alert)
    test_db_session.commit()

    work_order = MaintenanceWorkOrder(
        request_id="REQ_REL_01",
        machine_id="M_REL_01",
        alert_id="ALT_REL_01",
        issue="High temperature reading",
        risk="HIGH",
        recommendation="Inspect cooling system",
        priority="HIGH",
        status="PENDING",
        requested_by="Lead Engineer",
    )
    test_db_session.add(work_order)

    workflow_log = WorkflowLog(
        machine_id="M_REL_01",
        action_type="MAINTENANCE_REQUEST",
        performed_by="Lead Engineer",
        notes="Created work order REQ_REL_01",
        previous_status="WARNING",
        new_status="MAINTENANCE_SCHEDULED",
    )
    test_db_session.add(workflow_log)
    test_db_session.commit()

    # Verify parent-to-children relationships
    q_machine = test_db_session.query(Machine).filter(Machine.machine_id == "M_REL_01").first()
    assert len(q_machine.sensor_readings) == 1
    assert q_machine.sensor_readings[0].udi == 101
    assert len(q_machine.alerts) == 1
    assert q_machine.alerts[0].alert_id == "ALT_REL_01"
    assert len(q_machine.work_orders) == 1
    assert q_machine.work_orders[0].request_id == "REQ_REL_01"
    assert len(q_machine.workflow_logs) == 1
    assert q_machine.workflow_logs[0].action_type == "MAINTENANCE_REQUEST"

    # Verify child-to-parent relationships
    q_wo = test_db_session.query(MaintenanceWorkOrder).filter(MaintenanceWorkOrder.request_id == "REQ_REL_01").first()
    assert q_wo.machine.machine_id == "M_REL_01"
    assert q_wo.alert.alert_id == "ALT_REL_01"

    # Verify cascade deletion on machine removal
    test_db_session.delete(q_machine)
    test_db_session.commit()

    assert test_db_session.query(Machine).filter(Machine.machine_id == "M_REL_01").count() == 0
    assert test_db_session.query(SensorData).filter(SensorData.machine_id == "M_REL_01").count() == 0
    assert test_db_session.query(Alert).filter(Alert.machine_id == "M_REL_01").count() == 0
    assert test_db_session.query(MaintenanceWorkOrder).filter(MaintenanceWorkOrder.machine_id == "M_REL_01").count() == 0
    assert test_db_session.query(WorkflowLog).filter(WorkflowLog.machine_id == "M_REL_01").count() == 0


def test_full_crud_lifecycle_workflow(test_db_session):
    """Verify complete CRUD lifecycle: Create -> Read -> Update -> Delete for operational data."""
    # 1. CREATE
    m = Machine(machine_id="M_CRUD_01", type="M", location="Bay 4", status="OPERATIONAL")
    test_db_session.add(m)
    test_db_session.commit()

    # 2. READ
    created = test_db_session.query(Machine).filter(Machine.machine_id == "M_CRUD_01").first()
    assert created is not None
    assert created.status == "OPERATIONAL"

    # 3. UPDATE
    created.status = "MAINTENANCE_IN_PROGRESS"
    created.location = "Bay 4 - Servicing Area"
    test_db_session.commit()

    updated = test_db_session.query(Machine).filter(Machine.machine_id == "M_CRUD_01").first()
    assert updated.status == "MAINTENANCE_IN_PROGRESS"
    assert updated.location == "Bay 4 - Servicing Area"

    # 4. DELETE
    test_db_session.delete(updated)
    test_db_session.commit()

    deleted = test_db_session.query(Machine).filter(Machine.machine_id == "M_CRUD_01").first()
    assert deleted is None
