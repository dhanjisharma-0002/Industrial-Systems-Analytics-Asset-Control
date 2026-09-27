"""
Integration tests for machine and sensor verification endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.app.database import init_db
from backend.app.main import app, get_db
from backend.app.models import Machine, MaintenanceRecord, SensorData


@pytest.fixture
def client_with_db():
    """Create a FastAPI test client backed by a shared in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed initial test data
    db = TestingSessionLocal()
    m1 = Machine(machine_id="M1001", type="M")
    m2 = Machine(machine_id="L2002", type="L")
    m3 = Machine(machine_id="H3003", type="H")
    db.add_all([m1, m2, m3])
    db.commit()

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
        machine_id="L2002",
        udi=2,
        air_temperature_k=299.0,
        process_temperature_k=309.5,
        rotational_speed_rpm=1450.0,
        torque_nm=45.0,
        tool_wear_min=20,
    )
    db.add_all([s1, s2])
    db.commit()

    rec1 = MaintenanceRecord(
        machine_id="M1001",
        sensor_reading_id=s1.id,
        failure_occurred=True,
        failure_type="TWF",
        twf=True,
        notes="Tool wear limit reached",
    )
    db.add(rec1)
    db.commit()
    db.close()

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()



def test_get_machine_count(client_with_db):
    response = client_with_db.get("/api/machines/count")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert data["entity"] == "machines"


def test_get_sensor_count(client_with_db):
    response = client_with_db.get("/api/sensors/count")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["entity"] == "sensors"


def test_list_machines(client_with_db):
    response = client_with_db.get("/api/machines")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["machine_id"] == "M1001"

    # Test filtering by type
    filter_resp = client_with_db.get("/api/machines?type=L")
    assert filter_resp.status_code == 200
    filtered_data = filter_resp.json()
    assert len(filtered_data) == 1
    assert filtered_data[0]["machine_id"] == "L2002"


def test_get_machine_by_id(client_with_db):
    response = client_with_db.get("/api/machines/M1001")
    assert response.status_code == 200
    data = response.json()
    assert data["machine_id"] == "M1001"
    assert data["type"] == "M"
    assert data["sensor_readings_count"] == 1
    assert data["maintenance_records_count"] == 1
    assert data["latest_sensor_reading"]["torque_nm"] == 40.0
    assert len(data["maintenance_records"]) == 1
    assert data["maintenance_records"][0]["failure_type"] == "TWF"


def test_get_machine_not_found(client_with_db):
    response = client_with_db.get("/api/machines/NONEXISTENT_9999")
    assert response.status_code == 404
