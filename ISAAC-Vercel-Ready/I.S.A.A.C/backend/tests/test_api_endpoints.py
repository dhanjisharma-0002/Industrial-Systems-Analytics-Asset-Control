"""
Comprehensive automated API tests for ISAAC Phase 7 REST API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Machine, MaintenanceRecord, SensorData


@pytest.fixture
def test_db_session():
    """Create an isolated in-memory SQLite database session populated with test fixtures."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed 3 Machines
    m1 = Machine(machine_id="M1001", type="M")
    m2 = Machine(machine_id="L2002", type="L")
    m3 = Machine(machine_id="H3003", type="H")
    session.add_all([m1, m2, m3])
    session.commit()

    # Seed Sensor Telemetry
    s1 = SensorData(
        machine_id="M1001",
        udi=1,
        air_temperature_k=298.1,
        process_temperature_k=308.6,
        rotational_speed_rpm=1500.0,
        torque_nm=40.0,
        tool_wear_min=10,
    )
    s2 = SensorData(
        machine_id="M1001",
        udi=2,
        air_temperature_k=298.5,
        process_temperature_k=309.0,
        rotational_speed_rpm=1520.0,
        torque_nm=42.0,
        tool_wear_min=15,
    )
    s3 = SensorData(
        machine_id="L2002",
        udi=3,
        air_temperature_k=300.0,
        process_temperature_k=310.0,
        rotational_speed_rpm=1400.0,
        torque_nm=65.0,
        tool_wear_min=210,
    )
    session.add_all([s1, s2, s3])
    session.commit()

    # Seed Maintenance Records
    rec1 = MaintenanceRecord(
        machine_id="M1001",
        sensor_reading_id=s2.id,
        failure_occurred=False,
        failure_type="NORMAL",
        notes="Routine inspection",
    )
    rec2 = MaintenanceRecord(
        machine_id="L2002",
        sensor_reading_id=s3.id,
        failure_occurred=True,
        failure_type="OSF",
        osf=True,
        notes="Overstrain failure detected",
    )
    session.add_all([rec1, rec2])
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(test_db_session):
    """FastAPI TestClient with overridden get_db dependency."""
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
# 1. GET /api/health
# =========================================================================

def test_get_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "status" in data
    assert "version" in data
    assert "database" in data
    assert "environment" in data


# =========================================================================
# 2. GET /api/machines
# =========================================================================

def test_list_machines_all(client: TestClient):
    response = client.get("/api/machines")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    machine_ids = [m["machine_id"] for m in data]
    assert "M1001" in machine_ids
    assert "L2002" in machine_ids
    assert "H3003" in machine_ids


def test_list_machines_filtering(client: TestClient):
    response = client.get("/api/machines?type=L")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["machine_id"] == "L2002"
    assert data[0]["type"] == "L"


def test_list_machines_pagination(client: TestClient):
    response = client.get("/api/machines?limit=2&offset=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


# =========================================================================
# 3. GET /api/machines/{machine_id}
# =========================================================================

def test_get_machine_by_id_success(client: TestClient):
    response = client.get("/api/machines/M1001")
    assert response.status_code == 200
    data = response.json()
    assert data["machine_id"] == "M1001"
    assert data["type"] == "M"
    assert data["sensor_readings_count"] == 2
    assert data["maintenance_records_count"] == 1
    assert data["latest_sensor_reading"]["udi"] == 2
    assert data["current_health_score"] is not None
    assert 0.0 <= data["current_health_score"] <= 100.0
    assert data["current_risk_level"] in ("NOMINAL", "MODERATE", "HIGH", "CRITICAL")


def test_get_machine_by_id_not_found(client: TestClient):
    response = client.get("/api/machines/NONEXISTENT_999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


# =========================================================================
# 4. GET /api/machines/{machine_id}/sensor-history
# =========================================================================

def test_get_sensor_history_success(client: TestClient):
    response = client.get("/api/machines/M1001/sensor-history?order=desc")
    assert response.status_code == 200
    data = response.json()
    assert data["machine_id"] == "M1001"
    assert data["total_records"] == 2
    assert len(data["data"]) == 2
    # Descending order by UDI
    assert data["data"][0]["udi"] == 2
    assert data["data"][1]["udi"] == 1


def test_get_sensor_history_ascending(client: TestClient):
    response = client.get("/api/machines/M1001/sensor-history?order=asc")
    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["udi"] == 1
    assert data["data"][1]["udi"] == 2


def test_get_sensor_history_not_found(client: TestClient):
    response = client.get("/api/machines/NONEXISTENT/sensor-history")
    assert response.status_code == 404


# =========================================================================
# 5. GET /api/machines/{machine_id}/maintenance-history
# =========================================================================

def test_get_maintenance_history_success(client: TestClient):
    response = client.get("/api/machines/L2002/maintenance-history")
    assert response.status_code == 200
    data = response.json()
    assert data["machine_id"] == "L2002"
    assert data["total_records"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["failure_occurred"] is True
    assert data["data"][0]["osf"] is True


def test_get_maintenance_history_failure_only_filter(client: TestClient):
    # Machine M1001 has 1 maintenance record with failure_occurred=False
    resp_all = client.get("/api/machines/M1001/maintenance-history?failure_only=false")
    assert resp_all.json()["total_records"] == 1

    resp_fail = client.get("/api/machines/M1001/maintenance-history?failure_only=true")
    assert resp_fail.json()["total_records"] == 0


def test_get_maintenance_history_not_found(client: TestClient):
    response = client.get("/api/machines/NONEXISTENT/maintenance-history")
    assert response.status_code == 404


# =========================================================================
# 6. POST /api/predict
# =========================================================================

def test_post_predict_success(client: TestClient):
    payload = {
        "machine_id": "M1001",
        "machine_type": "M",
        "air_temperature_k": 298.1,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": 42.8,
        "tool_wear_min": 0,
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["machine_id"] == "M1001"
    assert 0.0 <= data["failure_probability"] <= 1.0
    assert data["risk_level"] in ("NOMINAL", "MODERATE", "HIGH", "CRITICAL")
    assert 0.0 <= data["health_score"] <= 100.0
    assert isinstance(data["recommendation"], str)
    assert isinstance(data["model_version"], str)
    assert isinstance(data["sensor_risk_explanations"], list)


def test_post_predict_validation_failure(client: TestClient):
    payload = {
        "machine_id": "M1001",
        "machine_type": "INVALID",
        "air_temperature_k": 298.1,
        "process_temperature_k": 308.6,
        "rotational_speed_rpm": 1551.0,
        "torque_nm": 42.8,
        "tool_wear_min": 0,
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 400


# =========================================================================
# 7. GET /api/analytics/summary
# =========================================================================

def test_get_analytics_summary(client: TestClient):
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["total_machines"] == 3
    assert data["machines_by_type"]["M"] == 1
    assert data["machines_by_type"]["L"] == 1
    assert data["machines_by_type"]["H"] == 1

    assert data["total_sensor_readings"] == 3
    assert data["total_maintenance_records"] == 2
    assert data["total_failures"] == 1
    assert data["failure_rate_percent"] > 0.0

    assert data["failures_by_type"]["OSF"] == 1
    assert data["failures_by_type"]["TWF"] == 0

    assert data["average_sensor_metrics"]["air_temperature_k"] > 290.0
    assert data["average_sensor_metrics"]["process_temperature_k"] > 300.0
    assert data["average_sensor_metrics"]["rotational_speed_rpm"] > 1000.0
    assert data["average_sensor_metrics"]["torque_nm"] > 0.0
    assert data["average_sensor_metrics"]["tool_wear_min"] >= 0.0
