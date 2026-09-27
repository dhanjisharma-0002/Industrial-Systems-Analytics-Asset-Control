"""
Unit and Integration Tests for:
- Repeat Failure Detector (Summary, Assets, Recurrence Pattern, Ineffective Repair Logic)
- Scenario-Based Budget Planner (Recalculation, Scenarios, Plan Creation, Duplication Prevention)
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import get_settings
from backend.app.database import create_database_engine, get_session_factory
from backend.app.models import Machine, MaintenanceRecord, MaintenanceWorkOrder, Alert, utc_now
from backend.app.services.repeat_failure_service import RepeatFailureService
from backend.app.services.budget_planner_service import BudgetPlannerService


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_repeat_failure_summary_endpoint(client):
    """Test GET /api/repeat-failure/summary returns valid structure and project data."""
    response = client.get("/api/repeat-failure/summary")
    assert response.status_code == 200
    data = response.json()

    assert "machines_with_repeated_failures" in data
    assert "machines_repaired_multiple_times" in data
    assert "potential_ineffective_repairs" in data
    assert "repeat_failure_alerts" in data
    assert "total_evaluated_machines" in data
    assert "trend_data" in data
    assert "pattern_distribution" in data
    assert "assets" in data

    assert data["total_evaluated_machines"] > 0
    assert isinstance(data["assets"], list)
    assert len(data["assets"]) > 0

    # Verify at least one known recurring failure asset (M14860 or L47249)
    machine_ids = [a["machine_id"] for a in data["assets"]]
    assert "M14860" in machine_ids or "L47249" in machine_ids


def test_repeat_failure_assets_endpoint_and_filters(client):
    """Test GET /api/repeat-failure/assets with risk, plant, and time filters."""
    # 1. Default ALL
    res_all = client.get("/api/repeat-failure/assets")
    assert res_all.status_code == 200
    all_assets = res_all.json()
    assert len(all_assets) > 0

    first = all_assets[0]
    assert "machine_id" in first
    assert "machine_type" in first
    assert "failure_count" in first
    assert "repair_count" in first
    assert "current_risk" in first
    assert "pattern" in first
    assert first["pattern"] in [
        "Potential ineffective repair — review recommended",
        "Rapid recurrence",
        "Repeated failure",
        "Multiple repairs",
    ]

    # 2. Risk filter = CRITICAL
    res_crit = client.get("/api/repeat-failure/assets?risk_filter=CRITICAL")
    assert res_crit.status_code == 200
    crit_assets = res_crit.json()
    for a in crit_assets:
        assert a["current_risk"] == "CRITICAL"

    # 3. Time filter = 30d
    res_time = client.get("/api/repeat-failure/assets?time_range=30d")
    assert res_time.status_code == 200


def test_repeat_failure_asset_detail_endpoint(client):
    """Test GET /api/repeat-failure/assets/{machine_id}."""
    res = client.get("/api/repeat-failure/assets/M14860")
    assert res.status_code == 200
    detail = res.json()
    assert detail["machine_id"] == "M14860"
    assert "timeline" in detail
    assert "work_orders" in detail
    assert "failure_records" in detail
    assert "alerts" in detail

    # 404 on nonexistent machine
    res_404 = client.get("/api/repeat-failure/assets/NONEXISTENT_9999")
    assert res_404.status_code == 404


def test_potential_ineffective_repair_classification(client):
    """Verify strictly compliant wording 'Potential ineffective repair — review recommended'."""
    res = client.get("/api/repeat-failure/summary")
    assert res.status_code == 200
    data = res.json()

    # M14860 had repairs completed and failures within seconds/days
    m14860 = next((a for a in data["assets"] if a["machine_id"] == "M14860"), None)
    if m14860:
        assert m14860["pattern"] == "Potential ineffective repair — review recommended"
        assert m14860["days_after_repair"] is not None
        assert m14860["days_after_repair"] <= 14.0


def test_budget_planner_summary_endpoint(client):
    """Test GET /api/budget-planner/summary returns 3 scenarios and comparison."""
    res = client.get("/api/budget-planner/summary?available_budget=300000")
    assert res.status_code == 200
    data = res.json()

    assert data["available_budget"] == 300000.0
    assert "scenarios" in data
    assert len(data["scenarios"]) == 3

    scenario_codes = [s["code"] for s in data["scenarios"]]
    assert "SCENARIO_A" in scenario_codes
    assert "SCENARIO_B" in scenario_codes
    assert "SCENARIO_C" in scenario_codes

    assert "comparison" in data
    assert len(data["comparison"]) == 3


def test_budget_planner_recalculation_on_budget_change(client):
    """Test changing available budget dynamically recalculates utilization and status."""
    # High budget
    res_high = client.get("/api/budget-planner/summary?available_budget=1000000")
    assert res_high.status_code == 200
    data_high = res_high.json()
    scen_a_high = next(s for s in data_high["scenarios"] if s["code"] == "SCENARIO_A")
    assert scen_a_high["budget_utilization_pct"] < 100.0
    assert scen_a_high["budget_status"] in ["Within Budget", "Near Budget Limit"]

    # Low budget
    res_low = client.get("/api/budget-planner/summary?available_budget=10000")
    assert res_low.status_code == 200
    data_low = res_low.json()
    scen_a_low = next(s for s in data_low["scenarios"] if s["code"] == "SCENARIO_A")
    assert scen_a_low["budget_utilization_pct"] > 100.0
    assert scen_a_low["budget_status"] == "Exceeds Budget"


def test_budget_planner_invalid_budget(client):
    """Test negative or invalid budget values are handled safely."""
    res_neg = client.get("/api/budget-planner/summary?available_budget=-500")
    assert res_neg.status_code in [400, 422]  # Validation error


def test_budget_planner_scenario_assets_endpoint(client):
    """Test GET /api/budget-planner/scenarios/{scenario_id}/assets."""
    res = client.get("/api/budget-planner/scenarios/repair_all_high_risk/assets")
    assert res.status_code == 200
    assets = res.json()
    assert isinstance(assets, list)
    if len(assets) > 0:
        first = assets[0]
        assert "machine_id" in first
        assert "estimated_repair_cost" in first
        assert "expected_downtime_hours" in first
        assert "failure_exposure" in first


def test_budget_planner_create_plan_and_duplicate_prevention(client):
    """Test confirmed maintenance plan creation and duplicate active work order prevention."""
    # Query high-risk assets
    res_assets = client.get("/api/budget-planner/scenarios/repair_top_critical/assets")
    assert res_assets.status_code == 200
    assets = res_assets.json()
    assert len(assets) > 0

    target_machine_ids = [a["machine_id"] for a in assets[:2]]

    payload = {
        "scenario_id": "repair_top_critical",
        "scenario_name": "Repair only top 3 critical assets",
        "selected_machine_ids": target_machine_ids,
        "planning_month": "Next Month",
        "requested_by": "Senior Reliability Engineer",
        "estimated_budget": 300000.0,
    }

    # 1. Create maintenance plan
    res_plan = client.post("/api/budget-planner/maintenance-plan", json=payload)
    assert res_plan.status_code in [200, 201]
    data = res_plan.json()
    assert data["success"] is True
    assert "created_count" in data
    assert "skipped_count" in data

    # 2. Re-submitting the same assets should skip them (duplicate prevention)
    res_dup = client.post("/api/budget-planner/maintenance-plan", json=payload)
    assert res_dup.status_code == 200
    data_dup = res_dup.json()
    # At least some or all should be skipped due to existing active work orders
    assert data_dup["skipped_count"] >= 1
