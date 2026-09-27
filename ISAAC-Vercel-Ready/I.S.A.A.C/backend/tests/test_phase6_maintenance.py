"""
Automated unit and integration test suite for Phase 6:
Maintenance Technician + Repair Workflow + Cost Tracking in ISAAC.
"""

import time
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from backend.app.config import get_settings
from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Base, Machine, MaintenanceRecord, MaintenanceWorkOrder, Technician, User, WorkflowLog, utc_now
from backend.app.repositories.technician_repository import TechnicianRepository
from backend.app.repositories.work_order_repository import WorkOrderRepository
from backend.app.services.maintenance_service import MaintenanceService


@pytest.fixture(scope="module")
def test_db_session():
    """Create an isolated in-memory SQLite database with StaticPool for Phase 6 test execution."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()

    # Seed test machine M14860
    machine = Machine(
        machine_id="M14860",
        type="M",
        location="Bay 1 - Spindle Line A",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    session.add(machine)

    # Seed initial test technician TECH-001
    tech = Technician(
        technician_id="TECH-001",
        technician_name="Ramesh Kumar",
        specialization="Mechanical",
        company="Precision Machine Works",
        phone="+91-9876543210",
        email="ramesh.kumar@precisionworks.in",
        experience_years=8,
        certification="ISO 18436 Vibration Cat II",
        status="AVAILABLE",
    )
    session.add(tech)
    session.commit()

    # Override get_db in FastAPI app
    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client(test_db_session):
    return TestClient(app)


def test_technician_management(client, test_db_session):
    """Test technician registration, listing, and ID query."""
    # 1. Register Technician
    payload = {
        "technician_name": "Ramesh Kumar",
        "specialization": "Mechanical",
        "technician_id": "TECH-001",
        "company": "Precision Machine Works",
        "phone": "+91-9876543210",
        "email": "ramesh.kumar@precisionworks.in",
        "experience_years": 8,
        "certification": "ISO 18436 Vibration Cat II",
        "status": "AVAILABLE",
    }
    response = client.post("/api/technicians", json=payload)
    assert response.status_code == 201, response.text
    tech_data = response.json()
    assert tech_data["technician_id"] == "TECH-001"
    assert tech_data["technician_name"] == "Ramesh Kumar"
    assert tech_data["specialization"] == "Mechanical"
    assert tech_data["status"] == "AVAILABLE"

    # Register second technician (Electrical)
    payload2 = {
        "technician_name": "Pooja Verma",
        "specialization": "Electrical",
        "technician_id": "TECH-002",
        "company": "In-House Reliability Team",
        "experience_years": 5,
        "certification": "Certified Maintenance & Reliability Professional (CMRP)",
    }
    res2 = client.post("/api/technicians", json=payload2)
    assert res2.status_code == 201

    # 2. List Technicians
    list_res = client.get("/api/technicians")
    assert list_res.status_code == 200
    techs = list_res.json()
    assert len(techs) >= 2
    assert any(t["technician_id"] == "TECH-001" for t in techs)
    assert any(t["technician_id"] == "TECH-002" for t in techs)

    # 3. Filter by Specialization
    filter_res = client.get("/api/technicians?specialization=Electrical")
    assert filter_res.status_code == 200
    filtered = filter_res.json()
    assert len(filtered) == 1
    assert filtered[0]["technician_id"] == "TECH-002"

    # 4. Get by ID
    get_res = client.get("/api/technicians/TECH-001")
    assert get_res.status_code == 200
    assert get_res.json()["technician_name"] == "Ramesh Kumar"


def test_complete_phase6_maintenance_workflow_on_m14860(client, test_db_session):
    """
    Test the complete 7-step industrial maintenance workflow on machine M14860:
    1. Create Work Order (PENDING)
    2. Anu Sharma assigns Technician (ASSIGNED)
    3. Mark Technician Arrived (TECHNICIAN_ARRIVED)
    4. Start Inspection (INSPECTION)
    5. Start Repair (REPAIR_IN_PROGRESS)
    6. Complete Repair with Test Costs: Labour ₹1500 + Parts ₹2500 + Other ₹500 = ₹4500 (COMPLETED)
    7. Close Maintenance by Anu Sharma (CLOSED)
    """
    machine_id = "M14860"

    # =========================================================================
    # Step 1: Create Maintenance Request
    # =========================================================================
    req_payload = {
        "machine_id": machine_id,
        "issue": "High tool wear index and excessive spindle vibration during 5000 RPM milling cycle.",
        "risk": "HIGH",
        "priority": "HIGH",
        "recommendation": "Inspect spindle drive bearings, clean cooling radiator, and calibrate cutting tool offset.",
        "requested_by": "Dhananjay Sharma (Reliability Engineer)",
        "estimated_cost": 5000.0,
    }
    create_res = client.post("/api/maintenance/requests", json=req_payload)
    assert create_res.status_code == 200, create_res.text
    wo = create_res.json()
    request_id = wo["request_id"]
    assert request_id.startswith("MNT-M14860-")
    assert wo["status"] == "PENDING"
    assert wo["priority"] == "HIGH"
    assert wo["maintenance_requested_at"] is not None
    assert wo["technician_assigned_at"] is None
    assert wo["technician_arrived_at"] is None
    assert wo["repair_started_at"] is None
    assert wo["repair_completed_at"] is None
    assert wo["maintenance_closed_at"] is None

    # Check machine status updated to MAINTENANCE_REQUIRED
    mach_res = client.get(f"/api/machines/{machine_id}")
    assert mach_res.status_code == 200
    assert mach_res.json()["status"] == "MAINTENANCE_REQUIRED"

    # =========================================================================
    # Step 2: Anu Sharma (Maintenance Lead) assigns Technician
    # =========================================================================
    assign_payload = {
        "technician_id": "TECH-001",
        "assigned_by": "Anu Sharma (Maintenance Lead)",
        "priority": "HIGH",
        "notes": "Dispatched Ramesh Kumar (Mechanical) for spindle overhaul and tool inspection.",
    }
    assign_res = client.post(f"/api/maintenance/requests/{request_id}/assign-technician", json=assign_payload)
    assert assign_res.status_code == 200, assign_res.text
    assert assign_res.json()["new_status"] == "ASSIGNED"

    # Verify order state & technician status
    detail_res = client.get(f"/api/maintenance/requests/{request_id}")
    wo_assigned = detail_res.json()
    assert wo_assigned["status"] == "ASSIGNED"
    assert wo_assigned["technician_id"] == "TECH-001"
    assert wo_assigned["assigned_by"] == "Anu Sharma (Maintenance Lead)"
    assert wo_assigned["assigned_to"] == "Ramesh Kumar"
    assert wo_assigned["technician_assigned_at"] is not None
    assert wo_assigned["technician_arrived_at"] is None

    # Verify technician status updated to ASSIGNED
    tech_res = client.get("/api/technicians/TECH-001")
    assert tech_res.json()["status"] == "ASSIGNED"

    # =========================================================================
    # Step 3: Mark Technician Arrived
    # =========================================================================
    arrived_payload = {
        "performed_by": "Ramesh Kumar",
        "notes": "Arrived at Bay 1 - Spindle Line A with replacement bearing kit.",
    }
    arrived_res = client.post(f"/api/maintenance/requests/{request_id}/technician-arrived", json=arrived_payload)
    assert arrived_res.status_code == 200, arrived_res.text
    assert arrived_res.json()["new_status"] == "TECHNICIAN_ARRIVED"

    detail_arrived = client.get(f"/api/maintenance/requests/{request_id}").json()
    assert detail_arrived["status"] == "TECHNICIAN_ARRIVED"
    assert detail_arrived["technician_arrived_at"] is not None

    # Verify technician status is now ON_SITE
    tech_res2 = client.get("/api/technicians/TECH-001")
    assert tech_res2.json()["status"] == "ON_SITE"

    # =========================================================================
    # Step 4: Start Inspection
    # =========================================================================
    inspect_payload = {
        "performed_by": "Ramesh Kumar",
        "notes": "Lockout-tagout procedure completed. Disassembled spindle protective shroud.",
    }
    inspect_res = client.post(f"/api/maintenance/requests/{request_id}/start-inspection", json=inspect_payload)
    assert inspect_res.status_code == 200, inspect_res.text
    assert inspect_res.json()["new_status"] == "INSPECTION"

    detail_inspect = client.get(f"/api/maintenance/requests/{request_id}").json()
    assert detail_inspect["status"] == "INSPECTION"
    assert detail_inspect["inspection_started_at"] is not None

    # Check machine status is now INSPECTION_IN_PROGRESS
    assert client.get(f"/api/machines/{machine_id}").json()["status"] == "INSPECTION_IN_PROGRESS"

    # =========================================================================
    # Step 5: Start Repair
    # =========================================================================
    repair_start_payload = {
        "performed_by": "Ramesh Kumar",
        "diagnosis": "Worn spindle drive bearing cage and chipped carbide tool insert.",
        "problem_description": "High tool wear index and excessive vibration.",
        "notes": "Replacing bearing unit and cutting tool insert.",
    }
    start_rep_res = client.post(f"/api/maintenance/requests/{request_id}/start-repair", json=repair_start_payload)
    assert start_rep_res.status_code == 200, start_rep_res.text
    assert start_rep_res.json()["new_status"] == "REPAIR_IN_PROGRESS"

    detail_rep_start = client.get(f"/api/maintenance/requests/{request_id}").json()
    assert detail_rep_start["status"] == "REPAIR_IN_PROGRESS"
    assert detail_rep_start["repair_started_at"] is not None
    assert detail_rep_start["repair_completed_at"] is None

    # =========================================================================
    # Step 6: Complete Repair with Test Costs: ₹1500 (Labour) + ₹2500 (Parts) + ₹500 (Other) = ₹4500
    # =========================================================================
    time.sleep(0.05)  # brief tick so duration > 0
    complete_payload = {
        "performed_by": "Ramesh Kumar",
        "diagnosis": "Micro-cracks in bearing cage assembly; insert flank wear at 0.45mm.",
        "work_performed": "Installed SKF precision spindle bearing; replaced 2x carbide inserts; calibrated tool offset.",
        "root_cause": "High-torque machining cycle without sufficient coolant flow.",
        "parts_used": "1x SKF Precision Spindle Bearing, 2x Carbide Cutting Inserts, 2L Synthetic Coolant",
        "repair_notes": "Spindle runout tolerance measured at 0.002mm (within OEM specification).",
        "completion_notes": "Assembly rebuilt, tested at 5000 RPM without vibration or heat rise.",
        "labour_cost": 1500.0,
        "parts_cost": 2500.0,
        "other_cost": 500.0,
    }
    comp_res = client.post(f"/api/maintenance/requests/{request_id}/complete-repair", json=complete_payload)
    assert comp_res.status_code == 200, comp_res.text
    comp_data = comp_res.json()
    assert comp_data["new_status"] == "COMPLETED"

    detail_comp = client.get(f"/api/maintenance/requests/{request_id}").json()
    assert detail_comp["status"] == "COMPLETED"
    assert detail_comp["repair_completed_at"] is not None
    assert detail_comp["labour_cost"] == 1500.0
    assert detail_comp["parts_cost"] == 2500.0
    assert detail_comp["other_cost"] == 500.0
    assert detail_comp["total_cost"] == 4500.0
    assert detail_comp["duration_minutes"] is not None
    assert detail_comp["parts_used"] == "1x SKF Precision Spindle Bearing, 2x Carbide Cutting Inserts, 2L Synthetic Coolant"

    # =========================================================================
    # Step 7: Close Maintenance by Anu Sharma (Maintenance Lead)
    # =========================================================================
    close_payload = {
        "performed_by": "Anu Sharma (Maintenance Lead)",
        "closure_notes": "Maintenance verified on-site. Spindle dynamics normal. Approved return to production.",
        "resolve_linked_alerts": True,
    }
    close_res = client.post(f"/api/maintenance/requests/{request_id}/close", json=close_payload)
    assert close_res.status_code == 200, close_res.text
    assert close_res.json()["new_status"] == "CLOSED"

    # Verify final closed order
    detail_closed = client.get(f"/api/maintenance/requests/{request_id}").json()
    assert detail_closed["status"] == "CLOSED"
    assert detail_closed["maintenance_closed_at"] is not None
    assert detail_closed["total_cost"] == 4500.0

    # Verify Machine is restored to OPERATIONAL
    mach_restored = client.get(f"/api/machines/{machine_id}").json()
    assert mach_restored["status"] == "OPERATIONAL"

    # Verify Technician is freed back to AVAILABLE
    tech_freed = client.get("/api/technicians/TECH-001").json()
    assert tech_freed["status"] == "AVAILABLE"

    # Verify summary total maintenance cost includes ₹4500
    summary_res = client.get("/api/maintenance/summary").json()
    assert summary_res["total_maintenance_cost"] >= 4500.0
    assert summary_res["completed_count"] >= 1


def test_invalid_state_transitions(client, test_db_session):
    """Verify strict validation preventing invalid lifecycle transitions."""
    # Create fresh order
    create_res = client.post("/api/maintenance/requests", json={
        "machine_id": "M14860",
        "issue": "Test transition validation order",
        "priority": "MEDIUM",
    })
    assert create_res.status_code == 200
    req_id = create_res.json()["request_id"]

    # 1. Cannot mark arrived before assigning technician
    arrived_invalid = client.post(f"/api/maintenance/requests/{req_id}/technician-arrived", json={})
    assert arrived_invalid.status_code == 400
    assert "must be ASSIGNED" in arrived_invalid.json()["detail"]

    # 2. Cannot complete repair before starting repair
    comp_invalid = client.post(f"/api/maintenance/requests/{req_id}/complete-repair", json={
        "diagnosis": "Premature",
        "work_performed": "None",
    })
    assert comp_invalid.status_code == 400
    assert "Repair must be started first" in comp_invalid.json()["detail"]

    # 3. Cannot close maintenance before completing repair
    close_invalid = client.post(f"/api/maintenance/requests/{req_id}/close", json={})
    assert close_invalid.status_code == 400
    assert "COMPLETED state" in close_invalid.json()["detail"]
