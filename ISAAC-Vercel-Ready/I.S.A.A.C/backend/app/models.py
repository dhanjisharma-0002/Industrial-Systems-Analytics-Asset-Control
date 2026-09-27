"""
SQLAlchemy ORM models for ISAAC database foundation and asset workflow engine.

Tables:
- machines: Master registry of industrial machines, location, status, and quality variants.
- sensor_data: Time-series telemetry readings (temperatures, speed, torque, wear).
- maintenance_records: Failure logs, maintenance events, and specific failure modes.
- alerts: Supervisory anomaly alerts, active warnings, and acknowledgment state.
- workflow_logs: Audit ledger of software workflow actions (inspection, maintenance request, completion).
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Machine(Base):
    """Machine asset registry with location and operational status."""
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    machine_id = Column(String(50), unique=True, nullable=False, index=True)
    type = Column(String(10), nullable=False)  # 'L', 'M', 'H'
    location = Column(String(100), default="Bay 1 - Spindle Line A", nullable=False)
    status = Column(String(50), default="OPERATIONAL", nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    sensor_readings = relationship(
        "SensorData",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="SensorData.udi",
    )
    maintenance_records = relationship(
        "MaintenanceRecord",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="MaintenanceRecord.id",
    )
    alerts = relationship(
        "Alert",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="Alert.id.desc()",
    )
    workflow_logs = relationship(
        "WorkflowLog",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="WorkflowLog.id.desc()",
    )
    work_orders = relationship(
        "MaintenanceWorkOrder",
        back_populates="machine",
        cascade="all, delete-orphan",
        order_by="MaintenanceWorkOrder.id.desc()",
    )

    def __repr__(self) -> str:
        return f"<Machine(machine_id='{self.machine_id}', type='{self.type}', status='{self.status}')>"


class SensorData(Base):
    """Operational sensor telemetry."""
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    machine_id = Column(String(50), ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False, index=True)
    udi = Column(Integer, nullable=False, index=True)
    air_temperature_k = Column(Float, nullable=False)
    process_temperature_k = Column(Float, nullable=False)
    rotational_speed_rpm = Column(Float, nullable=False)
    torque_nm = Column(Float, nullable=False)
    tool_wear_min = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, default=utc_now, nullable=False, index=True)

    # Relationships
    machine = relationship("Machine", back_populates="sensor_readings")
    maintenance_records = relationship("MaintenanceRecord", back_populates="sensor_reading")

    def __repr__(self) -> str:
        return (
            f"<SensorData(id={self.id}, machine_id='{self.machine_id}', udi={self.udi}, "
            f"rpm={self.rotational_speed_rpm}, torque={self.torque_nm})>"
        )


class MaintenanceRecord(Base):
    """Maintenance history, failure occurrences, and diagnosis flags."""
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    machine_id = Column(String(50), ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_reading_id = Column(Integer, ForeignKey("sensor_data.id", ondelete="SET NULL"), nullable=True, index=True)
    failure_occurred = Column(Boolean, default=False, nullable=False, index=True)
    failure_type = Column(String(50), nullable=True)  # e.g., 'TWF', 'HDF', 'PWF', 'OSF', 'RNF', or 'NORMAL'
    twf = Column(Boolean, default=False, nullable=False)
    hdf = Column(Boolean, default=False, nullable=False)
    pwf = Column(Boolean, default=False, nullable=False)
    osf = Column(Boolean, default=False, nullable=False)
    rnf = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    machine = relationship("Machine", back_populates="maintenance_records")
    sensor_reading = relationship("SensorData", back_populates="maintenance_records")

    def __repr__(self) -> str:
        return (
            f"<MaintenanceRecord(id={self.id}, machine_id='{self.machine_id}', "
            f"failure={self.failure_occurred}, type='{self.failure_type}')>"
        )


class Alert(Base):
    """Supervisory anomaly alerts and active status."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(50), unique=True, nullable=False, index=True)
    machine_id = Column(String(50), ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False, index=True)
    severity = Column(String(20), default="WARNING", nullable=False)  # 'CRITICAL', 'WARNING', 'INFO'
    alert_type = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="OPEN", nullable=False, index=True)  # 'OPEN', 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'
    source = Column(String(50), default="TELEMETRY_RULE", nullable=False)  # 'TELEMETRY_RULE', 'PREDICTIVE_AI', 'SIMULATION', 'MANUAL'
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    machine = relationship("Machine", back_populates="alerts")
    work_orders = relationship("MaintenanceWorkOrder", back_populates="alert", order_by="MaintenanceWorkOrder.id.desc()")

    def __repr__(self) -> str:
        return f"<Alert(alert_id='{self.alert_id}', machine='{self.machine_id}', severity='{self.severity}', status='{self.status}', source='{self.source}')>"


class WorkflowLog(Base):
    """Audit ledger of software workflow actions and machine state transitions."""
    __tablename__ = "workflow_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    machine_id = Column(String(50), ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False, index=True)
    maintenance_id = Column(String(50), nullable=True, index=True)
    action_type = Column(String(50), nullable=False)  # 'ACKNOWLEDGE_ALERT', 'MAINTENANCE_REQUEST', 'ASSIGN_TECHNICIAN', 'TECHNICIAN_ARRIVED', 'START_INSPECTION', 'START_REPAIR', 'COMPLETE_MAINTENANCE', 'CLOSE_MAINTENANCE', 'CANCEL_MAINTENANCE'
    performed_by = Column(String(100), nullable=False)
    notes = Column(Text, nullable=True)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    machine = relationship("Machine", back_populates="workflow_logs")

    def __repr__(self) -> str:
        return f"<WorkflowLog(id={self.id}, machine='{self.machine_id}', action='{self.action_type}', by='{self.performed_by}')>"


class Technician(Base):
    """
    Industrial Maintenance Technician registry entity (Phase 6).
    Tracks field service technicians, specializations, and real-time operational status.
    """
    __tablename__ = "technicians"

    id = Column(Integer, primary_key=True, autoincrement=True)
    technician_id = Column(String(50), unique=True, nullable=False, index=True)
    technician_name = Column(String(100), nullable=False)
    specialization = Column(String(50), nullable=False, default="General Maintenance")  # 'Mechanical', 'Electrical', 'Electronics', 'Automation', 'CNC', 'Hydraulics', 'General Maintenance'
    company = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    experience_years = Column(Integer, nullable=True, default=0)
    certification = Column(String(100), nullable=True)
    status = Column(String(30), default="AVAILABLE", nullable=False, index=True)  # 'AVAILABLE', 'ASSIGNED', 'ON_SITE', 'UNAVAILABLE'
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    work_orders = relationship("MaintenanceWorkOrder", back_populates="technician", order_by="MaintenanceWorkOrder.id.desc()")

    def __repr__(self) -> str:
        return f"<Technician(technician_id='{self.technician_id}', name='{self.technician_name}', specialization='{self.specialization}', status='{self.status}')>"


class MaintenanceWorkOrder(Base):
    """
    Formal maintenance work order and lifecycle execution management (Phase 6 CMMS).
    Lifecycle workflow:
    PENDING -> ASSIGNED -> TECHNICIAN_ARRIVED -> INSPECTION -> REPAIR_IN_PROGRESS -> COMPLETED -> CLOSED (or CANCELLED).
    """
    __tablename__ = "maintenance_work_orders"

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ASSIGNED', 'TECHNICIAN_ARRIVED', 'INSPECTION', 'REPAIR_IN_PROGRESS', 'IN_PROGRESS', 'COMPLETED', 'CLOSED', 'CANCELLED')",
            name="ck_work_order_status",
        ),
        CheckConstraint(
            "priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="ck_work_order_priority",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(50), unique=True, nullable=False, index=True)
    machine_id = Column(String(50), ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False, index=True)
    alert_id = Column(String(50), ForeignKey("alerts.alert_id", ondelete="SET NULL"), nullable=True, index=True)
    technician_id = Column(String(50), ForeignKey("technicians.technician_id", ondelete="SET NULL"), nullable=True, index=True)

    issue = Column(Text, nullable=False)
    risk = Column(String(50), default="MEDIUM", nullable=False)
    recommendation = Column(Text, nullable=False)
    priority = Column(String(20), default="MEDIUM", nullable=False, index=True)
    status = Column(String(30), default="PENDING", nullable=False, index=True)
    work_type = Column(String(50), default="CONFIRMED_WORK_ORDER", nullable=False)

    # Assignment & Identity
    requested_by = Column(String(100), default="Reliability Engineer", nullable=False)
    assigned_by = Column(String(100), nullable=True)  # e.g., "Anu Sharma (Maintenance Lead)"
    assigned_to = Column(String(100), nullable=True)  # Legacy / Technician display name

    # Workflow Timestamps (Actual Action-driven, None until real action happens)
    alert_created_at = Column(DateTime, nullable=True)
    maintenance_requested_at = Column(DateTime, default=utc_now, nullable=False)
    technician_assigned_at = Column(DateTime, nullable=True)
    technician_arrived_at = Column(DateTime, nullable=True)
    inspection_started_at = Column(DateTime, nullable=True)
    repair_started_at = Column(DateTime, nullable=True)
    repair_completed_at = Column(DateTime, nullable=True)
    maintenance_closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    scheduled_for = Column(DateTime, nullable=True)

    # Repair & Diagnostic Details
    problem_description = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    work_performed = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    parts_used = Column(Text, nullable=True)
    repair_notes = Column(Text, nullable=True)
    completion_notes = Column(Text, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Real Cost Tracking (INR ₹)
    estimated_cost = Column(Float, nullable=True)
    labour_cost = Column(Float, nullable=True)
    parts_cost = Column(Float, nullable=True)
    other_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)

    # Relationships
    machine = relationship("Machine", back_populates="work_orders")
    alert = relationship("Alert", back_populates="work_orders")
    technician = relationship("Technician", back_populates="work_orders")

    def __repr__(self) -> str:
        return (
            f"<MaintenanceWorkOrder(request_id='{self.request_id}', machine='{self.machine_id}', "
            f"priority='{self.priority}', status='{self.status}')>"
        )


class User(Base):
    """System user accounts and role-based permissions (Phase 17)."""
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('VIEWER', 'OPERATOR', 'ENGINEER', 'ADMIN')",
            name="ck_user_role",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(30), default="OPERATOR", nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    last_login = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<User(username='{self.username}', role='{self.role}', is_active={self.is_active})>"

