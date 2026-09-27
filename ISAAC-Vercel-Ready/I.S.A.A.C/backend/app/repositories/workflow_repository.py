"""
Repository layer for software workflow logs and state transition audit trails.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models import WorkflowLog


class WorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        machine_id: str,
        action_type: str,
        performed_by: str,
        notes: Optional[str] = None,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        maintenance_id: Optional[str] = None,
    ) -> WorkflowLog:
        """Create and persist an audit ledger entry for a workflow state transition."""
        log = WorkflowLog(
            machine_id=machine_id,
            maintenance_id=maintenance_id,
            action_type=action_type,
            performed_by=performed_by,
            notes=notes,
            previous_status=previous_status,
            new_status=new_status,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_logs_by_machine(self, machine_id: str, limit: int = 50) -> List[WorkflowLog]:
        """Fetch chronological workflow audit logs for a specific machine."""
        return (
            self.db.query(WorkflowLog)
            .filter(WorkflowLog.machine_id == machine_id)
            .order_by(WorkflowLog.id.desc())
            .limit(limit)
            .all()
        )

    def get_logs_by_maintenance(self, maintenance_id: str, limit: int = 50) -> List[WorkflowLog]:
        """Fetch chronological workflow audit logs for a specific maintenance work order."""
        return (
            self.db.query(WorkflowLog)
            .filter(WorkflowLog.maintenance_id == maintenance_id)
            .order_by(WorkflowLog.id.desc())
            .limit(limit)
            .all()
        )

