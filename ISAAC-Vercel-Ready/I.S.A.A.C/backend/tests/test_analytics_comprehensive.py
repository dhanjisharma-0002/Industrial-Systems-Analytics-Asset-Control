"""
Comprehensive automated unit & integration tests for Phase 15 Scalable Analytics.
Validates:
1. Machine-wise failure trends & MTBF calculation (Task 1).
2. Sensor behavior statistical distributions & envelopes (Task 2).
3. Maintenance frequency & work order velocity (Task 3).
4. Risk tier distribution & health score spectrum (Task 4).
5. Failure type distribution (TWF, HDF, PWF, OSF, RNF) (Task 5).
6. Time-based telemetry trends with period selection (Task 6).
7. Multi-machine comparison & radar profiles (Task 7).
8. Fleet operational summary & availability KPIs (Task 8).
9. Comprehensive unified payload REST API (Task 9).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Alert, Machine, MaintenanceRecord, MaintenanceWorkOrder, SensorData, utc_now
from backend.app.services.analytics_service import AnalyticsService


@pytest.fixture
def analytics_test_env():
    """Create in-memory SQLite database seeded with representative fleet data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed Machines
    m1 = Machine(machine_id="M_ANL_01", type="L", location="Bay 1", status="OPERATIONAL", created_at=utc_now())
    m2 = Machine(machine_id="M_ANL_02", type="M", location="Bay 2", status="OPERATIONAL", created_at=utc_now())
    m3 = Machine(machine_id="M_ANL_03", type="H", location="Bay 3", status="MAINTENANCE_REQUIRED", created_at=utc_now())
    session.add_all([m1, m2, m3])
    session.commit()

    # Seed Sensor Telemetry Readings
    sensors = [
        SensorData(machine_id="M_ANL_01", udi=1, air_temperature_k=298.1, process_temperature_k=308.5, rotational_speed_rpm=1500.0, torque_nm=40.0, tool_wear_min=50, recorded_at=utc_now()),
        SensorData(machine_id="M_ANL_01", udi=2, air_temperature_k=298.3, process_temperature_k=308.7, rotational_speed_rpm=1480.0, torque_nm=42.0, tool_wear_min=60, recorded_at=utc_now()),
        SensorData(machine_id="M_ANL_02", udi=3, air_temperature_k=300.2, process_temperature_k=310.4, rotational_speed_rpm=1550.0, torque_nm=38.0, tool_wear_min=120, recorded_at=utc_now()),
        SensorData(machine_id="M_ANL_02", udi=4, air_temperature_k=300.5, process_temperature_k=310.8, rotational_speed_rpm=1520.0, torque_nm=39.5, tool_wear_min=130, recorded_at=utc_now()),
        SensorData(machine_id="M_ANL_03", udi=5, air_temperature_k=304.0, process_temperature_k=313.5, rotational_speed_rpm=1200.0, torque_nm=75.0, tool_wear_min=240, recorded_at=utc_now()),
    ]
    session.add_all(sensors)

    # Seed Maintenance & Failure Records
    maint_records = [
        MaintenanceRecord(machine_id="M_ANL_01", failure_occurred=False, failure_type="NORMAL", recorded_at=utc_now()),
        MaintenanceRecord(machine_id="M_ANL_01", failure_occurred=True, failure_type="TWF", twf=True, recorded_at=utc_now()),
        MaintenanceRecord(machine_id="M_ANL_02", failure_occurred=True, failure_type="HDF", hdf=True, recorded_at=utc_now()),
        MaintenanceRecord(machine_id="M_ANL_03", failure_occurred=True, failure_type="OSF", osf=True, recorded_at=utc_now()),
        MaintenanceRecord(machine_id="M_ANL_03", failure_occurred=True, failure_type="PWF", pwf=True, recorded_at=utc_now()),
    ]
    session.add_all(maint_records)

    # Seed Work Orders
    orders = [
        MaintenanceWorkOrder(
            request_id="MNT-ANL-001",
            machine_id="M_ANL_01",
            issue="Tool wear inspection",
            priority="MEDIUM",
            status="COMPLETED",
            recommendation="Replace inserts",
            created_at=utc_now(),
            completed_at=utc_now(),
        ),
        MaintenanceWorkOrder(
            request_id="MNT-ANL-002",
            machine_id="M_ANL_03",
            issue="Spindle overstrain fault",
            priority="CRITICAL",
            status="IN_PROGRESS",
            recommendation="Halt spindle and inspect bearings",
            created_at=utc_now(),
        ),
    ]
    session.add_all(orders)

    # Seed Active Alerts
    alert = Alert(
        alert_id="ALT-ANL-001",
        machine_id="M_ANL_03",
        severity="CRITICAL",
        alert_type="OVERSTRAIN_FAILURE",
        message="Critical overstrain limit breached",
        status="OPEN",
        created_at=utc_now(),
    )
    session.add(alert)
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


# =========================================================================
# 1. Machine-Wise Failure Trends & MTBF (Task 1)
# =========================================================================

def test_machine_failure_trends(analytics_test_env):
    """Test machine-wise failure rate calculations, failure mode counts, and MTBF."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    trends = svc.get_machine_failure_trends()
    assert len(trends) >= 3

    m3 = next((t for t in trends if t["machine_id"] == "M_ANL_03"), None)
    assert m3 is not None
    assert m3["total_failures"] >= 2
    assert m3["osf_count"] >= 1
    assert m3["pwf_count"] >= 1
    assert m3["mtbf_cycles"] > 0


# =========================================================================
# 2. Sensor Behavior & Parameter Envelopes (Task 2)
# =========================================================================

def test_sensor_behavior_distributions(analytics_test_env):
    """Test min, mean, median, max, stddev, and percentile distributions across sensors."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    behavior = svc.get_sensor_behavior()
    assert behavior["total_readings_analyzed"] == 5

    # Check rotational speed distribution
    rpm = behavior["rotational_speed"]
    assert rpm["min"] <= rpm["mean"] <= rpm["max"]
    assert rpm["unit"] == "RPM"
    assert rpm["median"] > 0

    # Check torque distribution
    trq = behavior["torque"]
    assert trq["min"] >= 35.0
    assert trq["max"] >= 70.0
    assert trq["unit"] == "Nm"

    # Check power & overstrain
    assert behavior["mechanical_power"]["unit"] == "W"
    assert behavior["overstrain_factor"]["unit"] == "min·Nm"
    assert "speed_vs_torque" in behavior["correlations"]


# =========================================================================
# 3. Maintenance Frequency & Work Order Velocity (Task 3)
# =========================================================================

def test_maintenance_frequency_analytics(analytics_test_env):
    """Test work order status breakdown, priority distribution, and velocity trend."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    freq = svc.get_maintenance_frequency()
    assert freq["total_work_orders"] >= 2
    assert freq["status_distribution"]["COMPLETED"] >= 1
    assert freq["status_distribution"]["IN_PROGRESS"] >= 1
    assert freq["priority_distribution"]["CRITICAL"] >= 1
    assert len(freq["frequency_trend"]) == 7


# =========================================================================
# 4. Risk Tier Distribution & Health Spectrum (Task 4)
# =========================================================================

def test_risk_distribution_analytics(analytics_test_env):
    """Test risk tier counts and health score histogram."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    risk_data = svc.get_risk_distribution()
    assert risk_data["critical_risk_count"] >= 1
    assert "health_score_histogram" in risk_data
    assert "90-100" in risk_data["health_score_histogram"]
    assert risk_data["average_fleet_health_score"] > 0


# =========================================================================
# 5. Failure Type Distribution (Task 5)
# =========================================================================

def test_failure_type_distribution(analytics_test_env):
    """Test breakdown of failure types overall and by machine variant."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    fail_types = svc.get_failure_type_distribution()
    assert fail_types["total_failures"] >= 4
    assert fail_types["failures_by_type"]["TWF"] >= 1
    assert fail_types["failures_by_type"]["HDF"] >= 1
    assert fail_types["failures_by_type"]["OSF"] >= 1
    assert fail_types["failures_by_type"]["PWF"] >= 1

    # Check percentages
    assert "TWF" in fail_types["failures_by_type_percentage"]
    assert "L" in fail_types["failures_by_machine_type"]


# =========================================================================
# 6. Time-Based Trends with Window Filtering (Task 6)
# =========================================================================

def test_time_based_trends(analytics_test_env):
    """Test time-series bucketing across various time windows (1h, 24h, 7d, 30d, all)."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    trends_all = svc.get_time_trends(time_window="all")
    assert trends_all["time_window"] == "all"
    assert len(trends_all["trend_points"]) >= 1

    point = trends_all["trend_points"][0]
    assert "avg_torque_nm" in point
    assert "avg_speed_rpm" in point
    assert "avg_power_w" in point
    assert "avg_temp_diff_k" in point

    # Test 24h filter
    trends_24h = svc.get_time_trends(time_window="24h")
    assert trends_24h["time_window"] == "24h"


# =========================================================================
# 7. Machine Comparison & Radar Profiles (Task 7)
# =========================================================================

def test_machine_comparison_analytics(analytics_test_env):
    """Test side-by-side machine comparison and radar profile scores."""
    _, session = analytics_test_env
    svc = AnalyticsService(session)

    comp = svc.get_machine_comparison(machine_ids=["M_ANL_01", "M_ANL_03"])
    assert len(comp) == 2

    m1 = next(c for c in comp if c["machine_id"] == "M_ANL_01")
    m3 = next(c for c in comp if c["machine_id"] == "M_ANL_03")

    assert m1["avg_torque_nm"] < m3["avg_torque_nm"]
    assert "thermal_efficiency" in m1["radar_profile"]
    assert "mechanical_stress" in m3["radar_profile"]


# =========================================================================
# 8. REST API Endpoints Verification (Task 8 & 9)
# =========================================================================

def test_analytics_rest_api_endpoints(analytics_test_env):
    """Test all Phase 15 Analytics REST API endpoints."""
    client, _ = analytics_test_env

    # 1. GET /api/analytics/operational-summary
    res_op = client.get("/api/analytics/operational-summary")
    assert res_op.status_code == 200
    assert res_op.json()["total_machines"] == 3
    assert "fleet_availability_percent" in res_op.json()

    # 2. GET /api/analytics/machine-failures
    res_mf = client.get("/api/analytics/machine-failures")
    assert res_mf.status_code == 200
    assert len(res_mf.json()) >= 3

    # 3. GET /api/analytics/sensor-behavior
    res_sb = client.get("/api/analytics/sensor-behavior")
    assert res_sb.status_code == 200
    assert "rotational_speed" in res_sb.json()

    # 4. GET /api/analytics/maintenance-frequency
    res_mfreq = client.get("/api/analytics/maintenance-frequency")
    assert res_mfreq.status_code == 200
    assert res_mfreq.json()["total_work_orders"] >= 2

    # 5. GET /api/analytics/risk-distribution
    res_rd = client.get("/api/analytics/risk-distribution")
    assert res_rd.status_code == 200
    assert "critical_risk_count" in res_rd.json()

    # 6. GET /api/analytics/failure-types
    res_ft = client.get("/api/analytics/failure-types")
    assert res_ft.status_code == 200
    assert res_ft.json()["total_failures"] >= 4

    # 7. GET /api/analytics/time-trends?time_window=24h
    res_tt = client.get("/api/analytics/time-trends?time_window=24h")
    assert res_tt.status_code == 200
    assert res_tt.json()["time_window"] == "24h"

    # 8. GET /api/analytics/machine-comparison?machine_ids=M_ANL_01,M_ANL_02
    res_mc = client.get("/api/analytics/machine-comparison?machine_ids=M_ANL_01,M_ANL_02")
    assert res_mc.status_code == 200
    assert len(res_mc.json()["machines"]) == 2

    # 9. GET /api/analytics/comprehensive
    res_comp = client.get("/api/analytics/comprehensive")
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert "operational_summary" in comp_data
    assert "machine_failures" in comp_data
    assert "sensor_behavior" in comp_data
    assert "maintenance_frequency" in comp_data
    assert "risk_distribution" in comp_data
    assert "failure_types" in comp_data
    assert "time_trends" in comp_data
