"""
Repository layer for sensor telemetry data access.
"""

from typing import List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..models import SensorData


class SensorRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_total(self) -> int:
        """Count total sensor records across all machines."""
        return self.db.query(func.count(SensorData.id)).scalar() or 0

    def count_by_machine(self, machine_id: str) -> int:
        """Count sensor records for a specific machine."""
        return (
            self.db.query(func.count(SensorData.id))
            .filter(SensorData.machine_id == machine_id)
            .scalar()
            or 0
        )

    def get_latest_reading(self, machine_id: str) -> Optional[SensorData]:
        """Get most recent sensor reading for a machine by UDI or recorded_at."""
        return (
            self.db.query(SensorData)
            .filter(SensorData.machine_id == machine_id)
            .order_by(SensorData.udi.desc())
            .first()
        )

    def get_sensor_history(
        self,
        machine_id: str,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> Tuple[List[SensorData], int]:
        """Retrieve paginated time-series telemetry history for a machine."""
        query = self.db.query(SensorData).filter(SensorData.machine_id == machine_id)
        total = query.count()

        if order.lower() == "asc":
            query = query.order_by(SensorData.udi.asc())
        else:
            query = query.order_by(SensorData.udi.desc())

        readings = query.offset(offset).limit(limit).all()
        return readings, total
