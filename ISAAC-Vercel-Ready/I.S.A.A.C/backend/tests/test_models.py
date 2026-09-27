"""
Unit tests for SQLAlchemy database models, relationships, and schema initialization.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from backend.app.database import init_db
from backend.app.models import Base, Machine, MaintenanceRecord, SensorData


@pytest.fixture
def db_session():
    """Create a temporary in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_schema_initialization(db_session):
    """Verify that tables are created and can be queried."""
    assert db_session.query(Machine).count() == 0
    assert db_session.query(SensorData).count() == 0
    assert db_session.query(MaintenanceRecord).count() == 0


def test_create_machine_and_telemetry(db_session):
    """Verify relational persistence of Machine, SensorData, and MaintenanceRecord."""
    machine = Machine(machine_id="M14860", type="M")
    db_session.add(machine)
    db_session.commit()

    assert machine.id is not None

    sensor = SensorData(
        machine_id="M14860",
        udi=1,
        air_temperature_k=298.1,
        process_temperature_k=308.6,
        rotational_speed_rpm=1551.0,
        torque_nm=42.8,
        tool_wear_min=0,
    )
    db_session.add(sensor)
    db_session.commit()

    maint = MaintenanceRecord(
        machine_id="M14860",
        sensor_reading_id=sensor.id,
        failure_occurred=False,
        failure_type=None,
        twf=False,
        hdf=False,
        pwf=False,
        osf=False,
        rnf=False,
        notes="Normal baseline check",
    )
    db_session.add(maint)
    db_session.commit()

    # Query back and verify relationships
    queried_machine = db_session.query(Machine).filter(Machine.machine_id == "M14860").first()
    assert queried_machine is not None
    assert len(queried_machine.sensor_readings) == 1
    assert queried_machine.sensor_readings[0].torque_nm == 42.8
    assert len(queried_machine.maintenance_records) == 1
    assert queried_machine.maintenance_records[0].sensor_reading.udi == 1


def test_cascade_delete_machine(db_session):
    """Verify that deleting a Machine cascades to its sensor data and maintenance records."""
    machine = Machine(machine_id="L47181", type="L")
    db_session.add(machine)
    db_session.commit()

    sensor = SensorData(
        machine_id="L47181",
        udi=2,
        air_temperature_k=298.2,
        process_temperature_k=308.7,
        rotational_speed_rpm=1408.0,
        torque_nm=46.3,
        tool_wear_min=3,
    )
    db_session.add(sensor)
    db_session.commit()

    maint = MaintenanceRecord(
        machine_id="L47181",
        sensor_reading_id=sensor.id,
        failure_occurred=True,
        failure_type="TWF",
        twf=True,
    )
    db_session.add(maint)
    db_session.commit()

    assert db_session.query(SensorData).filter(SensorData.machine_id == "L47181").count() == 1

    # Delete machine
    db_session.delete(machine)
    db_session.commit()

    assert db_session.query(Machine).filter(Machine.machine_id == "L47181").count() == 0
    assert db_session.query(SensorData).filter(SensorData.machine_id == "L47181").count() == 0
    assert db_session.query(MaintenanceRecord).filter(MaintenanceRecord.machine_id == "L47181").count() == 0
