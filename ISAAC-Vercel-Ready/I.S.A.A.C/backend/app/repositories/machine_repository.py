"""
Repository layer for machine asset data access.
"""

from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Machine


class MachineRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, machine_id: str) -> Optional[Machine]:
        """Fetch machine record by machine_id string."""
        return self.db.query(Machine).filter(Machine.machine_id == machine_id).first()

    def list_all(self) -> List[Machine]:
        """Fetch all registered machine records."""
        return self.db.query(Machine).order_by(Machine.id.asc()).all()

    def list_machines(
        self,
        limit: int = 50,
        offset: int = 0,
        machine_type: Optional[str] = None,
    ) -> Tuple[List[Machine], int]:
        """List machines with optional type filter, pagination, and total count."""
        query = self.db.query(Machine)
        if machine_type:
            query = query.filter(Machine.type == machine_type.strip().upper())
        total = query.count()
        machines = query.order_by(Machine.id.asc()).offset(offset).limit(limit).all()
        return machines, total

    def count_total(self) -> int:
        """Count total registered machines."""
        return self.db.query(func.count(Machine.id)).scalar() or 0

    def update_status(self, machine_id: str, new_status: str) -> Optional[Machine]:
        """Update operational status of an industrial machine."""
        machine = self.get_by_id(machine_id)
        if not machine:
            return None
        machine.status = new_status
        self.db.commit()
        self.db.refresh(machine)
        return machine

    def update_location(self, machine_id: str, new_location: str) -> Optional[Machine]:
        """Update facility location of an industrial machine."""
        machine = self.get_by_id(machine_id)
        if not machine:
            return None
        machine.location = new_location
        self.db.commit()
        self.db.refresh(machine)
        return machine
