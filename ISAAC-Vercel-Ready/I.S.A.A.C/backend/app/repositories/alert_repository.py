"""
Repository layer for supervisory anomaly alerts.
Provides database access, querying, state transitions, deduplication, and summary aggregations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Alert, utc_now


class AlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_alert_id(self, alert_id: str) -> Optional[Alert]:
        """Fetch alert by unique alert_id string."""
        return self.db.query(Alert).filter(Alert.alert_id == alert_id).first()

    def get_active_alerts_by_machine(self, machine_id: str) -> List[Alert]:
        """Fetch all active (OPEN / ACTIVE / ACKNOWLEDGED) alerts for a specific machine."""
        return (
            self.db.query(Alert)
            .filter(
                Alert.machine_id == machine_id,
                Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
            )
            .order_by(Alert.id.desc())
            .all()
        )

    def get_all_alerts_by_machine(self, machine_id: str) -> List[Alert]:
        """Fetch all alerts (including resolved) for a specific machine."""
        return (
            self.db.query(Alert)
            .filter(Alert.machine_id == machine_id)
            .order_by(Alert.id.desc())
            .all()
        )

    def find_existing_active_alert(self, machine_id: str, alert_type: str) -> Optional[Alert]:
        """
        Check if an active (OPEN / ACTIVE / ACKNOWLEDGED) alert of the same type
        already exists for the given machine to prevent duplicate alert storms (Task 9).
        """
        return (
            self.db.query(Alert)
            .filter(
                Alert.machine_id == machine_id,
                Alert.alert_type == alert_type,
                Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
            )
            .first()
        )

    def get_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        machine_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Alert], int]:
        """
        Query alerts with optional status, severity, and machine filters, returning paginated results and total count.
        """
        query = self.db.query(Alert)

        if machine_id:
            query = query.filter(Alert.machine_id == machine_id)

        if status:
            s = status.upper()
            if s == "ACTIVE":
                query = query.filter(Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"]))
            elif s == "OPEN":
                query = query.filter(Alert.status.in_(["OPEN", "ACTIVE"]))
            elif s != "ALL":
                query = query.filter(Alert.status == s)

        if severity and severity.upper() != "ALL":
            query = query.filter(Alert.severity == severity.upper())

        total = query.count()
        records = query.order_by(Alert.id.desc()).offset(offset).limit(limit).all()
        return records, total

    def get_active_alerts(
        self,
        severity: Optional[str] = None,
        machine_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Alert], int]:
        """Fetch active/open alerts across the fleet."""
        return self.get_alerts(status="ACTIVE", severity=severity, machine_id=machine_id, limit=limit, offset=offset)

    def get_alert_history(
        self,
        severity: Optional[str] = None,
        machine_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Alert], int]:
        """Fetch resolved/historical alerts across the fleet."""
        return self.get_alerts(status="RESOLVED", severity=severity, machine_id=machine_id, limit=limit, offset=offset)

    def create_alert(
        self,
        alert_id: str,
        machine_id: str,
        severity: str,
        alert_type: str,
        message: str,
        status: str = "OPEN",
        source: str = "TELEMETRY_RULE",
        notes: Optional[str] = None,
        check_duplicate: bool = True,
    ) -> Tuple[Alert, bool]:
        """
        Create and persist a new supervisory anomaly alert with de-duplication (Task 2 & Task 9).
        Returns: (alert, created_new_bool)
        """
        if check_duplicate:
            existing = self.find_existing_active_alert(machine_id, alert_type)
            if existing:
                # If existing active alert already exists, do not duplicate
                return existing, False

        # If an alert with this exact alert_id already exists in DB
        existing_by_id = self.get_by_alert_id(alert_id)
        if existing_by_id:
            if existing_by_id.status in ["OPEN", "ACTIVE", "ACKNOWLEDGED"]:
                return existing_by_id, False
            # If resolved or historical with exact same ID, make unique with timestamp
            import time
            alert_id = f"{alert_id}-{int(time.time() * 1000)}"

        alert = Alert(
            alert_id=alert_id,
            machine_id=machine_id,
            severity=severity.upper(),
            alert_type=alert_type,
            message=message,
            status=status.upper(),
            source=source.upper(),
            notes=notes,
            created_at=utc_now(),
        )
        try:
            self.db.add(alert)
            self.db.commit()
            self.db.refresh(alert)
            return alert, True
        except Exception:
            self.db.rollback()
            raise

    def acknowledge_alert(
        self,
        alert_id: str,
        performed_by: str = "Plant Operator",
        notes: Optional[str] = None,
    ) -> Optional[Alert]:
        """Transition alert to ACKNOWLEDGED state and persist audit details (Task 5)."""
        alert = self.get_by_alert_id(alert_id)
        if not alert:
            return None

        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_by = performed_by
        alert.acknowledged_at = utc_now()
        if notes:
            alert.notes = (alert.notes + "\n" + notes) if alert.notes else notes

        self.db.commit()
        self.db.refresh(alert)
        return alert

    def get_by_id(self, alert_id: str) -> Optional[Alert]:
        """Alias for get_by_alert_id."""
        return self.get_by_alert_id(alert_id)

    def resolve_alert(
        self,
        alert_id: str,
        performed_by: Optional[str] = None,
        resolved_by: Optional[str] = None,
        notes: Optional[str] = None,
        resolution_action: Optional[str] = None,
    ) -> Optional[Alert]:
        """Transition alert to RESOLVED state and persist resolution details (Task 6)."""
        alert = self.get_by_alert_id(alert_id)
        if not alert:
            return None

        actor = resolved_by or performed_by or "Plant Lead"
        alert.status = "RESOLVED"
        alert.resolved_by = actor
        alert.resolved_at = utc_now()

        res_note = f"Resolution: {notes or 'Anomaly verified resolved.'}"
        if resolution_action:
            res_note += f" Action taken: {resolution_action}"
        alert.notes = (alert.notes + "\n" + res_note) if alert.notes else res_note

        self.db.commit()
        self.db.refresh(alert)
        return alert

    def resolve_alerts_for_machine(
        self,
        machine_id: str,
        performed_by: str = "Plant Lead",
        notes: Optional[str] = None,
    ) -> int:
        """Mark all active/acknowledged alerts as RESOLVED when machine maintenance is completed."""
        alerts = (
            self.db.query(Alert)
            .filter(
                Alert.machine_id == machine_id,
                Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
            )
            .all()
        )
        now = utc_now()
        for a in alerts:
            a.status = "RESOLVED"
            a.resolved_by = performed_by
            a.resolved_at = now
            if notes:
                a.notes = (a.notes + "\n" + notes) if a.notes else notes

        self.db.commit()
        return len(alerts)

    def get_critical_count(self) -> int:
        """Get count of un-resolved critical alerts (Task 7)."""
        return (
            self.db.query(Alert)
            .filter(
                Alert.severity == "CRITICAL",
                Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
            )
            .count()
        )

    def get_alert_summary(self) -> Dict[str, int]:
        """Aggregate summary counts across all alert categories and severities."""
        total = self.db.query(Alert).count()
        open_count = self.db.query(Alert).filter(Alert.status.in_(["OPEN", "ACTIVE"])).count()
        ack_count = self.db.query(Alert).filter(Alert.status == "ACKNOWLEDGED").count()
        res_count = self.db.query(Alert).filter(Alert.status == "RESOLVED").count()

        active_crit = self.db.query(Alert).filter(
            Alert.severity == "CRITICAL",
            Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
        ).count()

        active_warn = self.db.query(Alert).filter(
            Alert.severity == "WARNING",
            Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
        ).count()

        active_info = self.db.query(Alert).filter(
            Alert.severity == "INFO",
            Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])
        ).count()

        return {
            "total_alerts": total,
            "open_alerts": open_count,
            "acknowledged_alerts": ack_count,
            "resolved_alerts": res_count,
            "critical_alerts": active_crit,
            "warning_alerts": active_warn,
            "info_alerts": active_info,
        }
