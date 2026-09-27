"""
Service layer for software workflow state transitions, alerts, and audit ledgers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from ..logger import logger
from ..models import MaintenanceRecord
from ..repositories.alert_repository import AlertRepository
from ..repositories.machine_repository import MachineRepository
from ..repositories.maintenance_repository import MaintenanceRepository
from ..repositories.workflow_repository import WorkflowRepository


class WorkflowService:
    def __init__(self, db: Session):
        self.db = db
        self.machine_repo = MachineRepository(db)
        self.alert_repo = AlertRepository(db)
        self.workflow_repo = WorkflowRepository(db)
        self.maintenance_repo = MaintenanceRepository(db)

    def acknowledge_alert(
        self,
        alert_id: str,
        performed_by: str = "Plant Operator",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Acknowledge an active anomaly alert and record audit log."""
        logger.info(f"Acknowledging alert '{alert_id}' by '{performed_by}'")
        alert = self.alert_repo.acknowledge_alert(alert_id=alert_id, performed_by=performed_by)
        if not alert:
            raise ValueError(f"Alert with ID '{alert_id}' was not found.")

        # Log workflow event
        log = self.workflow_repo.log_action(
            machine_id=alert.machine_id,
            action_type="ACKNOWLEDGE_ALERT",
            performed_by=performed_by,
            notes=notes or f"Acknowledged alert {alert_id} ({alert.alert_type}): {alert.message}",
            previous_status="ACTIVE",
            new_status="ACKNOWLEDGED",
        )

        return {
            "success": True,
            "message": f"Alert '{alert_id}' acknowledged successfully.",
            "machine_id": alert.machine_id,
            "action_type": "ACKNOWLEDGE_ALERT",
            "new_status": "ACKNOWLEDGED",
            "timestamp": datetime.now(timezone.utc),
        }

    def create_maintenance_request(
        self,
        machine_id: str,
        performed_by: str = "Reliability Engineer",
        notes: str = "Scheduled maintenance request initiated.",
        urgency: str = "MEDIUM",
    ) -> Dict[str, Any]:
        """Initiate software maintenance request for a machine, setting status to MAINTENANCE_REQUIRED."""
        logger.info(f"Creating maintenance request for '{machine_id}' (Urgency: {urgency}) by '{performed_by}'")
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine '{machine_id}' was not found.")

        prev_status = machine.status
        new_status = "MAINTENANCE_REQUIRED"
        self.machine_repo.update_status(machine_id, new_status)

        # Create maintenance request record
        maint_record = MaintenanceRecord(
            machine_id=machine_id,
            failure_occurred=True if urgency in ("HIGH", "CRITICAL") else False,
            failure_type="MAINT_REQUEST",
            notes=f"[{urgency} PRIORITY] {notes} (Requested by {performed_by})",
            recorded_at=datetime.now(timezone.utc),
        )
        self.db.add(maint_record)
        self.db.commit()

        # Log audit trail
        self.workflow_repo.log_action(
            machine_id=machine_id,
            action_type="MAINTENANCE_REQUEST",
            performed_by=performed_by,
            notes=f"Priority: {urgency}. {notes}",
            previous_status=prev_status,
            new_status=new_status,
        )

        return {
            "success": True,
            "message": f"Maintenance request logged. Machine {machine_id} status updated to {new_status}.",
            "machine_id": machine_id,
            "action_type": "MAINTENANCE_REQUEST",
            "new_status": new_status,
            "timestamp": datetime.now(timezone.utc),
        }

    def start_inspection(
        self,
        machine_id: str,
        performed_by: str = "Maintenance Technician",
        notes: str = "Physical inspection initiated.",
    ) -> Dict[str, Any]:
        """Transition machine state to INSPECTION_IN_PROGRESS and record technician inspection start."""
        logger.info(f"Starting inspection on '{machine_id}' by '{performed_by}'")
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine '{machine_id}' was not found.")

        prev_status = machine.status
        new_status = "INSPECTION_IN_PROGRESS"
        self.machine_repo.update_status(machine_id, new_status)

        # Log audit trail
        self.workflow_repo.log_action(
            machine_id=machine_id,
            action_type="START_INSPECTION",
            performed_by=performed_by,
            notes=notes,
            previous_status=prev_status,
            new_status=new_status,
        )

        return {
            "success": True,
            "message": f"Inspection started. Machine {machine_id} status updated to {new_status}.",
            "machine_id": machine_id,
            "action_type": "START_INSPECTION",
            "new_status": new_status,
            "timestamp": datetime.now(timezone.utc),
        }

    def complete_maintenance(
        self,
        machine_id: str,
        performed_by: str = "Maintenance Lead",
        notes: str = "Maintenance completed successfully.",
        resolution_details: Optional[str] = "Service procedures completed.",
    ) -> Dict[str, Any]:
        """
        Complete maintenance workflow:
        1. Update machine status back to OPERATIONAL.
        2. Create completed maintenance event record.
        3. Resolve all active/acknowledged alerts for this machine.
        4. Record audit ledger entry.
        """
        logger.info(f"Completing maintenance on '{machine_id}' by '{performed_by}'")
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine '{machine_id}' was not found.")

        prev_status = machine.status
        new_status = "OPERATIONAL"
        self.machine_repo.update_status(machine_id, new_status)

        # Add completed maintenance record
        maint_record = MaintenanceRecord(
            machine_id=machine_id,
            failure_occurred=False,
            failure_type="MAINT_COMPLETE",
            notes=f"Maintenance completed by {performed_by}. {notes} | {resolution_details}",
            recorded_at=datetime.now(timezone.utc),
        )
        self.db.add(maint_record)
        self.db.commit()

        # Resolve active alerts for machine
        resolved_count = self.alert_repo.resolve_alerts_for_machine(machine_id)
        logger.info(f"Resolved {resolved_count} active alerts for machine {machine_id}")

        # Log audit trail
        self.workflow_repo.log_action(
            machine_id=machine_id,
            action_type="COMPLETE_MAINTENANCE",
            performed_by=performed_by,
            notes=f"{notes} ({resolved_count} alerts resolved)",
            previous_status=prev_status,
            new_status=new_status,
        )

        return {
            "success": True,
            "message": f"Maintenance completed. Machine {machine_id} restored to {new_status}. {resolved_count} alerts resolved.",
            "machine_id": machine_id,
            "action_type": "COMPLETE_MAINTENANCE",
            "new_status": new_status,
            "timestamp": datetime.now(timezone.utc),
        }

    def get_machine_alerts(self, machine_id: str) -> List[Any]:
        """Fetch all alerts for a machine."""
        return self.alert_repo.get_active_alerts_by_machine(machine_id)

    def get_machine_workflow_history(self, machine_id: str) -> List[Any]:
        """Fetch workflow audit logs for a machine."""
        return self.workflow_repo.get_logs_by_machine(machine_id)
