"""
Service layer for real alert evaluation, condition triggers, persistence, duplicate prevention, and lifecycle workflows.
"""

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..logger import logger
from ..models import Alert, Machine, utc_now
from ..repositories.alert_repository import AlertRepository
from ..repositories.machine_repository import MachineRepository
from ..repositories.workflow_repository import WorkflowRepository


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self.alert_repo = AlertRepository(db)
        self.machine_repo = MachineRepository(db)
        self.workflow_repo = WorkflowRepository(db)

    def evaluate_and_trigger_alerts(
        self,
        machine_id: str,
        machine_type: str,
        air_temperature_k: float,
        process_temperature_k: float,
        rotational_speed_rpm: float,
        torque_nm: float,
        tool_wear_min: float,
        prediction: Optional[Dict[str, Any]] = None,
        source: str = "TELEMETRY_RULE",
    ) -> List[Alert]:
        """
        Evaluate live telemetry against actual physical limits and predictive risk scores.
        Generates and persists alerts while preventing duplicate open alerts for the same condition (Task 1 & 9).
        """
        triggered_alerts: List[Alert] = []
        m_type = machine_type.upper() if machine_type else "M"
        now_ts = int(time.time() * 1000)

        # 1. Physical Condition: Overstrain Failure (OSF)
        os_limit = 11000 if m_type == "L" else 12000 if m_type == "M" else 13000
        overstrain_val = tool_wear_min * torque_nm
        if overstrain_val > os_limit:
            alert_id = f"ALT-{machine_id}-OSF-{now_ts}"
            msg = (
                f"Overstrain limit breached on {machine_id} (Grade {m_type}): "
                f"Tool Wear × Torque = {overstrain_val:.0f} min·Nm (Safety Limit: {os_limit} min·Nm). "
                f"Immediate spindle stress relief required."
            )
            alert, created = self.alert_repo.create_alert(
                alert_id=alert_id,
                machine_id=machine_id,
                severity="CRITICAL",
                alert_type="OVERSTRAIN_FAILURE",
                message=msg,
                status="OPEN",
                source=source,
                check_duplicate=True,
            )
            triggered_alerts.append(alert)
            if created:
                logger.warning(f"Generated new OSF alert: {alert.alert_id} for machine {machine_id}")

        # 2. Physical Condition: Heat Dissipation Failure (HDF)
        temp_diff = process_temperature_k - air_temperature_k
        if temp_diff < 8.6 and rotational_speed_rpm < 1380:
            alert_id = f"ALT-{machine_id}-HDF-{now_ts}"
            msg = (
                f"Heat dissipation collapse on {machine_id}: "
                f"Temperature gradient constrained (ΔT = {temp_diff:.2f} K < 8.6 K) at {rotational_speed_rpm:.0f} RPM. "
                f"Coolant thermal boundary layer failure detected."
            )
            alert, created = self.alert_repo.create_alert(
                alert_id=alert_id,
                machine_id=machine_id,
                severity="CRITICAL",
                alert_type="HEAT_DISSIPATION_FAILURE",
                message=msg,
                status="OPEN",
                source=source,
                check_duplicate=True,
            )
            triggered_alerts.append(alert)
            if created:
                logger.warning(f"Generated new HDF alert: {alert.alert_id} for machine {machine_id}")

        # 3. Physical Condition: Power Failure (PWF)
        power_w = torque_nm * (rotational_speed_rpm * 2 * math.pi / 60.0)
        if power_w < 3500.0 or power_w > 9000.0:
            alert_id = f"ALT-{machine_id}-PWF-{now_ts}"
            msg = (
                f"Mechanical power envelope breach on {machine_id}: "
                f"Calculated drive power {power_w:.0f} W is outside safe operating margins (3,500 W - 9,000 W)."
            )
            alert, created = self.alert_repo.create_alert(
                alert_id=alert_id,
                machine_id=machine_id,
                severity="CRITICAL",
                alert_type="POWER_FAILURE",
                message=msg,
                status="OPEN",
                source=source,
                check_duplicate=True,
            )
            triggered_alerts.append(alert)
            if created:
                logger.warning(f"Generated new PWF alert: {alert.alert_id} for machine {machine_id}")

        # 4. Physical Condition: Tool Wear Limit (TWF)
        if tool_wear_min >= 240:
            alert_id = f"ALT-{machine_id}-TWF-{now_ts}"
            msg = (
                f"Tool wear critical lifetime reached on {machine_id}: "
                f"Cumulative wear is {tool_wear_min:.0f} min (Critical limit: 240 min). Flank insert failure imminent."
            )
            alert, created = self.alert_repo.create_alert(
                alert_id=alert_id,
                machine_id=machine_id,
                severity="CRITICAL",
                alert_type="TOOL_WEAR_FAILURE",
                message=msg,
                status="OPEN",
                source=source,
                check_duplicate=True,
            )
            triggered_alerts.append(alert)
            if created:
                logger.warning(f"Generated new TWF critical alert: {alert.alert_id} for machine {machine_id}")
        elif tool_wear_min >= 200:
            alert_id = f"ALT-{machine_id}-TWF-{now_ts}"
            msg = (
                f"Tool wear replacement threshold approaching on {machine_id}: "
                f"Cumulative wear {tool_wear_min:.0f} min exceeds warning threshold (200 min)."
            )
            alert, created = self.alert_repo.create_alert(
                alert_id=alert_id,
                machine_id=machine_id,
                severity="WARNING",
                alert_type="TOOL_WEAR_FAILURE",
                message=msg,
                status="OPEN",
                source=source,
                check_duplicate=True,
            )
            triggered_alerts.append(alert)

        # 5. Predictive ML Anomaly / Risk Degradation
        if prediction:
            risk_level = prediction.get("risk_level", "NOMINAL")
            failure_prob = prediction.get("failure_probability", 0.0)
            health_score = prediction.get("health_score", 100.0)

            if risk_level == "CRITICAL" or failure_prob >= 0.50 or health_score < 40.0:
                alert_id = f"ALT-{machine_id}-RISK-{now_ts}"
                rec = prediction.get("recommendation", "Execute immediate engineering inspection.")
                msg = (
                    f"Severe predictive failure risk ({failure_prob:.1%}) on {machine_id}. "
                    f"Health score degraded to {health_score:.1f}/100. Recommendation: {rec}"
                )
                alert, created = self.alert_repo.create_alert(
                    alert_id=alert_id,
                    machine_id=machine_id,
                    severity="CRITICAL",
                    alert_type="HIGH_FAILURE_RISK",
                    message=msg,
                    status="OPEN",
                    source="PREDICTIVE_AI",
                    check_duplicate=True,
                )
                triggered_alerts.append(alert)
            elif risk_level in ("HIGH", "MODERATE") or failure_prob >= 0.25:
                alert_id = f"ALT-{machine_id}-RISK-{now_ts}"
                msg = (
                    f"Elevated sub-optimal risk profile ({failure_prob:.1%}) on {machine_id}. "
                    f"Health score at {health_score:.1f}/100."
                )
                alert, created = self.alert_repo.create_alert(
                    alert_id=alert_id,
                    machine_id=machine_id,
                    severity="WARNING",
                    alert_type="PREDICTIVE_RISK_WARNING",
                    message=msg,
                    status="OPEN",
                    source="PREDICTIVE_AI",
                    check_duplicate=True,
                )
                triggered_alerts.append(alert)

        return triggered_alerts

    def acknowledge_alert(
        self,
        alert_id: str,
        performed_by: str = "Plant Operator",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Acknowledge an open anomaly alert and record audit log (Task 5)."""
        logger.info(f"Acknowledging alert '{alert_id}' by '{performed_by}'")
        alert = self.alert_repo.acknowledge_alert(
            alert_id=alert_id,
            performed_by=performed_by,
            notes=notes,
        )
        if not alert:
            raise ValueError(f"Alert with ID '{alert_id}' was not found.")

        # Record in Workflow Audit Log
        self.workflow_repo.log_action(
            machine_id=alert.machine_id,
            action_type="ACKNOWLEDGE_ALERT",
            performed_by=performed_by,
            notes=notes or f"Acknowledged alert {alert_id} ({alert.alert_type}): {alert.message}",
            previous_status="OPEN",
            new_status="ACKNOWLEDGED",
        )

        return {
            "success": True,
            "message": f"Alert '{alert_id}' acknowledged successfully.",
            "alert": alert,
            "machine_id": alert.machine_id,
            "action_type": "ACKNOWLEDGE_ALERT",
            "new_status": "ACKNOWLEDGED",
            "timestamp": utc_now(),
        }

    def resolve_alert(
        self,
        alert_id: str,
        performed_by: str = "Plant Lead",
        notes: Optional[str] = None,
        resolution_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve an open/acknowledged alert and record audit log (Task 6)."""
        logger.info(f"Resolving alert '{alert_id}' by '{performed_by}'")
        alert = self.alert_repo.resolve_alert(
            alert_id=alert_id,
            performed_by=performed_by,
            notes=notes,
            resolution_action=resolution_action,
        )
        if not alert:
            raise ValueError(f"Alert with ID '{alert_id}' was not found.")

        # Record in Workflow Audit Log
        self.workflow_repo.log_action(
            machine_id=alert.machine_id,
            action_type="RESOLVE_ALERT",
            performed_by=performed_by,
            notes=f"Resolved alert {alert_id}. {notes or ''} {resolution_action or ''}".strip(),
            previous_status=alert.status,
            new_status="RESOLVED",
        )

        return {
            "success": True,
            "message": f"Alert '{alert_id}' marked as RESOLVED.",
            "alert": alert,
            "machine_id": alert.machine_id,
            "action_type": "RESOLVE_ALERT",
            "new_status": "RESOLVED",
            "timestamp": utc_now(),
        }

    def get_active_alerts(
        self,
        severity: Optional[str] = None,
        machine_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Alert], int]:
        """Retrieve all active (OPEN / ACKNOWLEDGED) alerts."""
        return self.alert_repo.get_active_alerts(
            severity=severity,
            machine_id=machine_id,
            limit=limit,
            offset=offset,
        )

    def get_alert_history(
        self,
        severity: Optional[str] = None,
        machine_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Alert], int]:
        """Retrieve all historical (RESOLVED) alerts."""
        return self.alert_repo.get_alert_history(
            severity=severity,
            machine_id=machine_id,
            limit=limit,
            offset=offset,
        )

    def get_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        machine_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Alert], int]:
        """Retrieve paginated alerts with flexible filtering."""
        return self.alert_repo.get_alerts(
            status=status,
            severity=severity,
            machine_id=machine_id,
            limit=limit,
            offset=offset,
        )

    def get_by_alert_id(self, alert_id: str) -> Optional[Alert]:
        """Fetch alert by unique ID."""
        return self.alert_repo.get_by_alert_id(alert_id)

    def get_critical_count(self) -> int:
        """Get count of un-resolved critical alerts (Task 7)."""
        return self.alert_repo.get_critical_count()

    def get_alert_summary(self) -> Dict[str, int]:
        """Get summary breakdown counts for alerts."""
        return self.alert_repo.get_alert_summary()
