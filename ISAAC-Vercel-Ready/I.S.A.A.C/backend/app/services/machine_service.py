"""
Service layer for industrial machine management and telemetry inspection.
"""

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from ..logger import logger
from ..repositories.alert_repository import AlertRepository
from ..repositories.machine_repository import MachineRepository
from ..repositories.maintenance_repository import MaintenanceRepository
from ..repositories.sensor_repository import SensorRepository
from ..repositories.workflow_repository import WorkflowRepository
from .prediction_service import PredictionService, get_prediction_service


class MachineService:
    def __init__(self, db: Session, prediction_service: Optional[PredictionService] = None):
        self.db = db
        self.machine_repo = MachineRepository(db)
        self.sensor_repo = SensorRepository(db)
        self.maintenance_repo = MaintenanceRepository(db)
        self.alert_repo = AlertRepository(db)
        self.workflow_repo = WorkflowRepository(db)
        self.prediction_service = prediction_service or get_prediction_service()

    def list_machines(
        self,
        limit: int = 50,
        offset: int = 0,
        machine_type: Optional[str] = None,
    ) -> Tuple[List[Any], int]:
        """Fetch list of registered machines with total count."""
        logger.info(f"Listing machines with limit={limit}, offset={offset}, type={machine_type}")
        return self.machine_repo.list_machines(limit=limit, offset=offset, machine_type=machine_type)

    def get_machine_detail(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch comprehensive machine profile including location, status, sensor count,
        maintenance count, latest reading, active alerts, workflow logs, and computed health score/failure probability.
        """
        logger.info(f"Fetching machine details for ID='{machine_id}'")
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            return None

        sensor_count = self.sensor_repo.count_by_machine(machine_id)
        maint_count = self.maintenance_repo.count_by_machine(machine_id)
        latest_reading = self.sensor_repo.get_latest_reading(machine_id)
        maint_records, _ = self.maintenance_repo.get_maintenance_history(machine_id, limit=50)
        active_alerts = self.alert_repo.get_active_alerts_by_machine(machine_id)
        workflow_history = self.workflow_repo.get_logs_by_machine(machine_id, limit=50)

        # If latest sensor reading exists, calculate current health score, failure probability, and risk level
        current_health_score = None
        current_failure_prob = None
        current_risk_level = None

        if latest_reading:
            try:
                pred = self.prediction_service.evaluate_telemetry(
                    machine_id=machine_id,
                    machine_type=machine.type,
                    air_temperature_k=latest_reading.air_temperature_k,
                    process_temperature_k=latest_reading.process_temperature_k,
                    rotational_speed_rpm=latest_reading.rotational_speed_rpm,
                    torque_nm=latest_reading.torque_nm,
                    tool_wear_min=latest_reading.tool_wear_min,
                )
                current_health_score = pred["health_score"]
                current_failure_prob = pred["failure_probability"]
                current_risk_level = pred["risk_level"]

                # If critical risk detected and no active alert exists, automatically log an alert
                if (current_risk_level == "CRITICAL" or pred["health_score"] < 40.0) and len(active_alerts) == 0:
                    explanations = pred.get("sensor_risk_explanations", [])
                    alert_msg = explanations[0]["description"] if explanations else "Critical health score degradation detected."
                    alert_type = explanations[0]["sensor_name"] if explanations else "HEALTH_SCORE_CRITICAL"
                    import time
                    now_ts = int(time.time() * 1000)
                    new_alert, created = self.alert_repo.create_alert(
                        alert_id=f"ALT-{machine_id}-{int(latest_reading.udi)}-{now_ts}",
                        machine_id=machine_id,
                        severity="CRITICAL",
                        alert_type=alert_type,
                        message=alert_msg,
                    )
                    if new_alert and new_alert.status in ["OPEN", "ACTIVE", "ACKNOWLEDGED"]:
                        active_alerts = [new_alert]
            except Exception as e:
                self.db.rollback()
                logger.warning(f"Could not compute real-time health score for {machine_id}: {e}")

        return {
            "id": machine.id,
            "machine_id": machine.machine_id,
            "type": machine.type,
            "location": machine.location or "Bay 1 - Spindle Line A",
            "status": machine.status or "OPERATIONAL",
            "created_at": machine.created_at,
            "sensor_readings_count": sensor_count,
            "maintenance_records_count": maint_count,
            "latest_sensor_reading": latest_reading,
            "maintenance_records": maint_records,
            "current_health_score": current_health_score,
            "current_failure_probability": current_failure_prob,
            "current_risk_level": current_risk_level,
            "active_alerts": active_alerts,
            "workflow_history": workflow_history,
        }

    def get_sensor_history(
        self,
        machine_id: str,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> Optional[Tuple[List[Any], int]]:
        """Fetch paginated telemetry time-series for a machine."""
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            return None
        return self.sensor_repo.get_sensor_history(machine_id=machine_id, limit=limit, offset=offset, order=order)

    def get_maintenance_history(
        self,
        machine_id: str,
        limit: int = 50,
        offset: int = 0,
        failure_only: bool = False,
    ) -> Optional[Tuple[List[Any], int]]:
        """Fetch paginated maintenance history for a machine."""
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            return None
        return self.maintenance_repo.get_maintenance_history(
            machine_id=machine_id, limit=limit, offset=offset, failure_only=failure_only
        )
