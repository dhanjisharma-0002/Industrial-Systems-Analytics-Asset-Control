"""
Service layer for fleet analytics, aggregate telemetry metrics, PySpark aggregations, and health statistics.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from ..logger import logger
from ..repositories.analytics_repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_repo = AnalyticsRepository(db)

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Compute and return aggregate fleet analytics summary."""
        logger.info("Computing fleet-wide analytics summary from database")
        return self.analytics_repo.get_fleet_summary()

    def get_machine_failure_trends(
        self,
        machine_type: Optional[str] = None,
        machine_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Compute machine-wise failure rates and MTBF."""
        return self.analytics_repo.get_machine_failure_trends(
            machine_type=machine_type,
            machine_id=machine_id,
        )

    def get_sensor_behavior(
        self,
        machine_type: Optional[str] = None,
        machine_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate sensor behavior distributions and parameter envelopes."""
        return self.analytics_repo.get_sensor_behavior(
            machine_type=machine_type,
            machine_id=machine_id,
        )

    def get_maintenance_frequency(self) -> Dict[str, Any]:
        """Aggregate maintenance work order frequency and priority distribution."""
        return self.analytics_repo.get_maintenance_frequency()

    def get_risk_distribution(self) -> Dict[str, Any]:
        """Calculate risk tier distribution and health score spectrum."""
        return self.analytics_repo.get_risk_distribution()

    def get_failure_type_distribution(self) -> Dict[str, Any]:
        """Break down failure mode distribution across fleet."""
        return self.analytics_repo.get_failure_type_distribution()

    def get_time_trends(
        self,
        time_window: str = "all",
        machine_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate telemetry observations into uniform time-series buckets."""
        return self.analytics_repo.get_time_trends(
            time_window=time_window,
            machine_id=machine_id,
        )

    def get_machine_comparison(
        self,
        machine_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Compare 2 or more machines side-by-side."""
        return self.analytics_repo.get_machine_comparison(machine_ids=machine_ids)

    def get_operational_summary(self) -> Dict[str, Any]:
        """Calculate fleet health index, MTBF, and availability percentage."""
        return self.analytics_repo.get_operational_summary()

    def get_comprehensive_analytics(self) -> Dict[str, Any]:
        """Assemble all 8 analytics dimensions for unified dashboard loading."""
        return self.analytics_repo.get_comprehensive_analytics()
