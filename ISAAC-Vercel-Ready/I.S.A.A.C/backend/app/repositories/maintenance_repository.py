"""
Repository layer for maintenance and failure event data access.
"""

from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import MaintenanceRecord


class MaintenanceRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_total(self) -> int:
        """Count total maintenance records across all machines."""
        return self.db.query(func.count(MaintenanceRecord.id)).scalar() or 0

    def count_failures(self) -> int:
        """Count total failure events."""
        return (
            self.db.query(func.count(MaintenanceRecord.id))
            .filter(MaintenanceRecord.failure_occurred == True)
            .scalar()
            or 0
        )

    def count_by_machine(self, machine_id: str) -> int:
        """Count maintenance records for a specific machine."""
        return (
            self.db.query(func.count(MaintenanceRecord.id))
            .filter(MaintenanceRecord.machine_id == machine_id)
            .scalar()
            or 0
        )

    def get_maintenance_history(
        self,
        machine_id: str,
        limit: int = 50,
        offset: int = 0,
        failure_only: bool = False,
    ) -> Tuple[List[MaintenanceRecord], int]:
        """Retrieve paginated maintenance records for a machine."""
        query = self.db.query(MaintenanceRecord).filter(MaintenanceRecord.machine_id == machine_id)
        if failure_only:
            query = query.filter(MaintenanceRecord.failure_occurred == True)
        
        total = query.count()
        records = (
            query.order_by(MaintenanceRecord.recorded_at.desc(), MaintenanceRecord.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return records, total

    def create_record(
        self,
        machine_id: str,
        failure_occurred: bool = False,
        failure_type: Optional[str] = "NORMAL",
        twf: bool = False,
        hdf: bool = False,
        pwf: bool = False,
        osf: bool = False,
        rnf: bool = False,
        notes: Optional[str] = None,
        sensor_reading_id: Optional[int] = None,
    ) -> MaintenanceRecord:
        """Create and persist a historical maintenance record."""
        record = MaintenanceRecord(
            machine_id=machine_id,
            sensor_reading_id=sensor_reading_id,
            failure_occurred=failure_occurred,
            failure_type=failure_type or ("NORMAL" if not failure_occurred else "OTHER"),
            twf=twf,
            hdf=hdf,
            pwf=pwf,
            osf=osf,
            rnf=rnf,
            notes=notes,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

