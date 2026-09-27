"""
Service layer for Repeat Failure Detector.
Identifies recurring failures, multi-repair assets, and potential ineffective repairs
across the industrial fleet using actual maintenance work orders, maintenance records,
supervisory alerts, and ML predictive health telemetry.

Transparent Configurable Business Rules:
- REPEAT_FAILURE_THRESHOLD: Minimum failure count to qualify as repeated failure (Default: 2)
- RAPID_RECURRENCE_DAYS: Maximum interval between repair and subsequent failure to flag
  potential ineffective repair (Default: 14.0 days)
- Compliance phrasing: "Potential ineffective repair — review recommended" (Never definitively
  claims that a repair was ineffective).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..logger import logger
from ..models import Alert, Machine, MaintenanceRecord, MaintenanceWorkOrder, SensorData, utc_now
from ..repositories.machine_repository import MachineRepository
from ..repositories.sensor_repository import SensorRepository
from ..repositories.alert_repository import AlertRepository
from ..repositories.work_order_repository import WorkOrderRepository
from .prediction_service import get_prediction_service


# Configurable defaults
REPEAT_FAILURE_THRESHOLD: int = 2
RAPID_RECURRENCE_DAYS: float = 14.0


class RepeatFailureService:
    def __init__(
        self,
        db: Session,
        repeat_threshold: int = REPEAT_FAILURE_THRESHOLD,
        rapid_recurrence_days: float = RAPID_RECURRENCE_DAYS,
    ):
        self.db = db
        self.repeat_threshold = repeat_threshold
        self.rapid_recurrence_days = rapid_recurrence_days
        self.machine_repo = MachineRepository(db)
        self.sensor_repo = SensorRepository(db)
        self.alert_repo = AlertRepository(db)
        self.work_order_repo = WorkOrderRepository(db)
        self.prediction_svc = get_prediction_service()

    def _parse_time_cutoff(self, time_range: str) -> Optional[datetime]:
        """Convert time_range string (30d, 90d, 6m, 12m, ALL) to timezone-aware UTC cutoff."""
        if not time_range or time_range.upper() == "ALL":
            return None
        now = utc_now()
        tr = time_range.lower()
        if "30" in tr or tr == "30d":
            return now - timedelta(days=30)
        elif "90" in tr or tr == "90d":
            return now - timedelta(days=90)
        elif "6" in tr or tr == "6m":
            return now - timedelta(days=180)
        elif "12" in tr or tr == "12m":
            return now - timedelta(days=365)
        return None

    def evaluate_machine_failures(
        self,
        risk_filter: str = "ALL",
        time_range: str = "ALL",
        plant_filter: str = "ALL",
    ) -> List[Dict[str, Any]]:
        """
        Scan all machines and calculate real repeat failure metrics:
        - failure count
        - repair count
        - last repair date
        - next failure date
        - days after repair
        - pattern categorization
        - health score and failure probability from ML
        """
        time_cutoff = self._parse_time_cutoff(time_range)
        all_machines = self.machine_repo.list_all()

        # Query all records
        maint_records = self.db.query(MaintenanceRecord).order_by(MaintenanceRecord.recorded_at.asc()).all()
        work_orders = self.db.query(MaintenanceWorkOrder).order_by(MaintenanceWorkOrder.created_at.asc()).all()
        all_alerts = self.db.query(Alert).order_by(Alert.created_at.asc()).all()

        # Group by machine_id
        records_by_machine: Dict[str, List[MaintenanceRecord]] = {}
        for r in maint_records:
            records_by_machine.setdefault(r.machine_id, []).append(r)

        orders_by_machine: Dict[str, List[MaintenanceWorkOrder]] = {}
        for wo in work_orders:
            orders_by_machine.setdefault(wo.machine_id, []).append(wo)

        alerts_by_machine: Dict[str, List[Alert]] = {}
        for a in all_alerts:
            alerts_by_machine.setdefault(a.machine_id, []).append(a)

        recurring_assets: List[Dict[str, Any]] = []

        for m in all_machines:
            # Plant / Location filter
            if plant_filter and plant_filter.upper() != "ALL":
                if plant_filter.lower() not in (m.location or "").lower():
                    continue

            m_records = records_by_machine.get(m.machine_id, [])
            m_orders = orders_by_machine.get(m.machine_id, [])
            m_alerts = alerts_by_machine.get(m.machine_id, [])

            # Filter by time cutoff if specified
            if time_cutoff:
                def is_after_cutoff(dt):
                    if not dt:
                        return False
                    # Make aware if naive
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt >= time_cutoff

                m_records = [r for r in m_records if is_after_cutoff(r.recorded_at)]
                m_orders = [wo for wo in m_orders if is_after_cutoff(wo.created_at or wo.maintenance_requested_at)]
                m_alerts = [a for a in m_alerts if is_after_cutoff(a.created_at)]

            # Identify all failure events
            # 1. MaintenanceRecord with failure_occurred == True or specific failure type
            failure_events: List[Dict[str, Any]] = []
            for r in m_records:
                if r.failure_occurred or (r.failure_type and r.failure_type not in ["NORMAL", "MAINT_COMPLETE"]):
                    failure_events.append({
                        "source": "MAINTENANCE_RECORD",
                        "id": f"REC-{r.id}",
                        "type": r.failure_type or "FAILURE",
                        "timestamp": r.recorded_at,
                        "notes": r.notes,
                    })

            # 2. Critical & warning alerts indicating failures
            for a in m_alerts:
                if a.severity in ["CRITICAL", "WARNING"]:
                    # Deduplicate if within 60 seconds of an existing failure record
                    a_dt = a.created_at
                    already_recorded = False
                    for fe in failure_events:
                        fe_dt = fe["timestamp"]
                        if fe_dt and a_dt:
                            diff = abs((fe_dt.replace(tzinfo=timezone.utc) if fe_dt.tzinfo is None else fe_dt) -
                                       (a_dt.replace(tzinfo=timezone.utc) if a_dt.tzinfo is None else a_dt)).total_seconds()
                            if diff < 120.0:
                                already_recorded = True
                                break
                    if not already_recorded:
                        failure_events.append({
                            "source": "ALERT",
                            "id": a.alert_id,
                            "type": a.alert_type,
                            "timestamp": a.created_at,
                            "notes": a.message,
                        })

            # Sort failures chronologically
            failure_events.sort(key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min.replace(tzinfo=timezone.utc))

            # Identify all completed repair events
            repair_events: List[Dict[str, Any]] = []
            # From MaintenanceWorkOrder
            for wo in m_orders:
                if wo.status in ["CLOSED", "COMPLETED"]:
                    rep_time = wo.repair_completed_at or wo.completed_at or wo.maintenance_closed_at or wo.created_at
                    repair_events.append({
                        "source": "WORK_ORDER",
                        "id": wo.request_id,
                        "timestamp": rep_time,
                        "issue": wo.issue,
                        "work_performed": wo.work_performed or wo.diagnosis,
                        "total_cost": wo.total_cost,
                    })

            # From MaintenanceRecord (e.g. MAINT_COMPLETE)
            for r in m_records:
                if r.failure_type == "MAINT_COMPLETE" or (not r.failure_occurred and r.notes and ("completed" in r.notes.lower() or "servicing" in r.notes.lower())):
                    # Check deduplication with work orders
                    r_dt = r.recorded_at
                    is_dup = False
                    for re in repair_events:
                        re_dt = re["timestamp"]
                        if re_dt and r_dt:
                            diff = abs((re_dt.replace(tzinfo=timezone.utc) if re_dt.tzinfo is None else re_dt) -
                                       (r_dt.replace(tzinfo=timezone.utc) if r_dt.tzinfo is None else r_dt)).total_seconds()
                            if diff < 120.0:
                                is_dup = True
                                break
                    if not is_dup:
                        repair_events.append({
                            "source": "MAINTENANCE_RECORD",
                            "id": f"REC-REP-{r.id}",
                            "timestamp": r.recorded_at,
                            "issue": "Maintenance Servicing Completed",
                            "work_performed": r.notes,
                            "total_cost": None,
                        })

            # Sort repairs chronologically
            repair_events.sort(key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min.replace(tzinfo=timezone.utc))

            failure_count = len(failure_events)
            repair_count = len(repair_events)

            # Scan all repairs for potential ineffective repair pairs
            ineffective_pairs = []
            for rep in repair_events:
                r_ts = rep["timestamp"]
                if not r_ts:
                    continue
                r_aware = r_ts.replace(tzinfo=timezone.utc) if r_ts.tzinfo is None else r_ts
                for fe in failure_events:
                    f_ts = fe["timestamp"]
                    if not f_ts:
                        continue
                    f_aware = f_ts.replace(tzinfo=timezone.utc) if f_ts.tzinfo is None else f_ts
                    if f_aware > r_aware:
                        diff_sec = (f_aware - r_aware).total_seconds()
                        diff_days = diff_sec / 86400.0
                        if diff_days <= self.rapid_recurrence_days:
                            ineffective_pairs.append((r_ts, f_ts, round(diff_days, 2)))
                        break

            has_rapid_recurrence_after_repair = len(ineffective_pairs) > 0

            # Determine last_repair, next_failure, and days_after_repair
            last_repair_dt: Optional[datetime] = repair_events[-1]["timestamp"] if repair_events else None
            next_failure_dt: Optional[datetime] = None
            days_after_repair: Optional[float] = None

            if has_rapid_recurrence_after_repair:
                # Use the most recent ineffective repair pair
                pair = ineffective_pairs[-1]
                last_repair_dt = pair[0]
                next_failure_dt = pair[1]
                days_after_repair = pair[2]
            elif last_repair_dt:
                lr_aware = last_repair_dt.replace(tzinfo=timezone.utc) if last_repair_dt.tzinfo is None else last_repair_dt
                for fe in failure_events:
                    fe_dt = fe["timestamp"]
                    if fe_dt:
                        fe_aware = fe_dt.replace(tzinfo=timezone.utc) if fe_dt.tzinfo is None else fe_dt
                        if fe_aware > lr_aware:
                            next_failure_dt = fe_dt
                            seconds = (fe_aware - lr_aware).total_seconds()
                            days_after_repair = max(0.0, round(seconds / 86400.0, 2))
                            break


            # Check if failures happened in rapid succession
            has_rapid_failure_interval = False
            if len(failure_events) >= 2:
                for i in range(len(failure_events) - 1):
                    t1 = failure_events[i]["timestamp"]
                    t2 = failure_events[i + 1]["timestamp"]
                    if t1 and t2:
                        t1_a = t1.replace(tzinfo=timezone.utc) if t1.tzinfo is None else t1
                        t2_a = t2.replace(tzinfo=timezone.utc) if t2.tzinfo is None else t2
                        diff_days = abs((t2_a - t1_a).total_seconds()) / 86400.0
                        if diff_days <= self.rapid_recurrence_days:
                            has_rapid_failure_interval = True
                            break

            pattern: str = "Nominal"
            pattern_color: str = "blue"

            if has_rapid_recurrence_after_repair:
                # MANDATORY SPEC: "Potential ineffective repair — review recommended"
                pattern = "Potential ineffective repair — review recommended"
                pattern_color = "red"
            elif has_rapid_failure_interval:
                pattern = "Rapid recurrence"
                pattern_color = "amber"
            elif failure_count >= self.repeat_threshold:
                pattern = "Repeated failure"
                pattern_color = "purple"
            elif repair_count >= 2:
                pattern = "Multiple repairs"
                pattern_color = "amber"

            # Machine risk & ML prediction
            latest_reading = self.sensor_repo.get_latest_reading(m.machine_id)
            health_score = 98.0
            failure_prob = 0.05
            risk_level = "NOMINAL"

            if latest_reading:
                try:
                    pred = self.prediction_svc.evaluate_telemetry(
                        machine_id=m.machine_id,
                        machine_type=m.type,
                        air_temperature_k=latest_reading.air_temperature_k,
                        process_temperature_k=latest_reading.process_temperature_k,
                        rotational_speed_rpm=latest_reading.rotational_speed_rpm,
                        torque_nm=latest_reading.torque_nm,
                        tool_wear_min=latest_reading.tool_wear_min,
                    )
                    health_score = float(pred.get("health_score", 98.0))
                    failure_prob = float(pred.get("failure_probability", 0.05))
                    pred_risk = pred.get("risk_level", "LOW")
                    risk_level = "CRITICAL" if pred_risk == "CRITICAL" else ("HIGH" if pred_risk in ["HIGH", "ELEVATED"] else ("MODERATE" if pred_risk == "MEDIUM" else "NOMINAL"))
                except Exception as err:
                    logger.warning(f"Prediction failed for {m.machine_id}: {err}")

            # Overrides if pattern is critical or open critical alerts exist
            active_alerts = [a for a in m_alerts if a.status in ["OPEN", "ACTIVE"]]
            has_crit_alert = any(a.severity == "CRITICAL" for a in active_alerts)
            if has_crit_alert or pattern == "Potential ineffective repair — review recommended":
                risk_level = "CRITICAL"
                health_score = min(health_score, 38.0)
                failure_prob = max(failure_prob, 0.85)
            elif pattern in ["Rapid recurrence", "Repeated failure"] and risk_level == "NOMINAL":
                risk_level = "HIGH"
                health_score = min(health_score, 55.0)
                failure_prob = max(failure_prob, 0.65)

            # Check if this qualifies as a recurring failure asset
            is_recurring = (
                failure_count >= self.repeat_threshold
                or repair_count >= 2
                or pattern in [
                    "Potential ineffective repair — review recommended",
                    "Rapid recurrence",
                    "Repeated failure",
                ]
            )

            if not is_recurring:
                continue

            # Risk filter
            if risk_filter == "CRITICAL" and risk_level != "CRITICAL":
                continue
            if risk_filter == "HIGH" and risk_level not in ["CRITICAL", "HIGH"]:
                continue

            # Active work orders
            has_active_wo = any(wo.status not in ["CLOSED", "CANCELLED"] for wo in m_orders)

            # Distinct failure types
            failure_types = list({fe["type"] for fe in failure_events if fe["type"]})

            recurring_assets.append({
                "machine_id": m.machine_id,
                "machine_type": m.type,
                "location": m.location or "Spindle Bay 1",
                "failure_count": failure_count,
                "repair_count": repair_count,
                "last_repair": last_repair_dt.isoformat() if last_repair_dt else None,
                "next_failure": next_failure_dt.isoformat() if next_failure_dt else None,
                "days_after_repair": days_after_repair,
                "current_risk": risk_level,
                "health_score": round(health_score, 1),
                "failure_probability": round(failure_prob, 3),
                "pattern": pattern,
                "pattern_badge_color": pattern_color,
                "action": "View Machine",
                "has_active_work_order": has_active_wo,
                "active_alerts_count": len(active_alerts),
                "failure_types": failure_types,
                "notes": (
                    f"Asset exhibited {failure_count} failures across lifecycle. "
                    f"Status: {pattern}."
                ),
            })

        # Sort: Potential ineffective repairs first, then highest failure_count, then risk
        risk_weights = {"CRITICAL": 3, "HIGH": 2, "MODERATE": 1, "NOMINAL": 0}
        pattern_weights = {
            "Potential ineffective repair — review recommended": 4,
            "Rapid recurrence": 3,
            "Repeated failure": 2,
            "Multiple repairs": 1,
        }

        recurring_assets.sort(
            key=lambda x: (
                pattern_weights.get(x["pattern"], 0),
                risk_weights.get(x["current_risk"], 0),
                x["failure_count"],
                x["repair_count"],
            ),
            reverse=True,
        )

        return recurring_assets

    def get_summary(
        self,
        risk_filter: str = "ALL",
        time_range: str = "ALL",
        plant_filter: str = "ALL",
    ) -> Dict[str, Any]:
        """
        Generate high-level Repeat Failure Detector KPIs, recurrence trend timeline,
        and pattern distribution based strictly on project database records.
        """
        assets = self.evaluate_machine_failures(
            risk_filter=risk_filter,
            time_range=time_range,
            plant_filter=plant_filter,
        )

        total_machines = self.machine_repo.count_total()

        # KPI 1: Machines with repeated failures
        machines_with_repeated_failures = len([a for a in assets if a["failure_count"] >= self.repeat_threshold])

        # KPI 2: Machines repaired multiple times
        machines_repaired_multiple_times = len([a for a in assets if a["repair_count"] >= 2])

        # KPI 3: Potential ineffective repairs
        potential_ineffective_repairs = len([
            a for a in assets
            if a["pattern"] == "Potential ineffective repair — review recommended"
        ])

        # KPI 4: Repeat-failure alerts
        # Count total active alerts across these assets
        repeat_failure_alerts = sum(a["active_alerts_count"] for a in assets)

        # Failure Recurrence Trend points (Timeline breakdown)
        # Group failure and repair events by date/period from actual project records
        trend_map: Dict[str, Dict[str, int]] = {}
        for a in assets:
            if a.get("last_repair"):
                rep_date = a["last_repair"][:10]
                entry = trend_map.setdefault(rep_date, {"failures": 0, "repairs": 0, "repeats": 0})
                entry["repairs"] += 1

            if a.get("next_failure"):
                fail_date = a["next_failure"][:10]
                entry = trend_map.setdefault(fail_date, {"failures": 0, "repairs": 0, "repeats": 0})
                entry["failures"] += 1
                entry["repeats"] += 1

        # Build chronological trend data
        sorted_dates = sorted(trend_map.keys())
        trend_data = []
        if sorted_dates:
            for d in sorted_dates:
                trend_data.append({
                    "period": d,
                    "failure_count": trend_map[d]["failures"],
                    "repair_count": trend_map[d]["repairs"],
                    "repeat_count": trend_map[d]["repeats"],
                })
        else:
            # Fallback based on asset failure counts
            trend_data = [
                {"period": "Recent Period", "failure_count": sum(a["failure_count"] for a in assets), "repair_count": sum(a["repair_count"] for a in assets), "repeat_count": machines_with_repeated_failures}
            ]

        # Pattern distribution breakdown
        pattern_counts: Dict[str, int] = {}
        for a in assets:
            pat = a["pattern"]
            pattern_counts[pat] = pattern_counts.get(pat, 0) + 1

        pattern_colors = {
            "Potential ineffective repair — review recommended": "#ef4444",
            "Rapid recurrence": "#f59e0b",
            "Repeated failure": "#a855f7",
            "Multiple repairs": "#38bdf8",
        }

        pattern_distribution = [
            {
                "pattern": pat,
                "count": count,
                "color": pattern_colors.get(pat, "#38bdf8"),
            }
            for pat, count in pattern_counts.items()
        ]

        return {
            "machines_with_repeated_failures": machines_with_repeated_failures,
            "machines_repaired_multiple_times": machines_repaired_multiple_times,
            "potential_ineffective_repairs": potential_ineffective_repairs,
            "repeat_failure_alerts": repeat_failure_alerts,
            "total_evaluated_machines": total_machines,
            "threshold_settings": {
                "repeat_failure_threshold": self.repeat_threshold,
                "rapid_recurrence_days": self.rapid_recurrence_days,
                "risk_filter": risk_filter,
                "time_range": time_range,
                "plant_filter": plant_filter,
            },
            "trend_data": trend_data,
            "pattern_distribution": pattern_distribution,
            "assets": assets,
        }

    def get_asset_detail(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """
        Deep diagnostic trace for a specific machine asset:
        Full timeline of maintenance records, work orders, telemetry, and alerts.
        """
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            return None

        # Run evaluation for this asset
        all_evals = {a["machine_id"]: a for a in self.evaluate_machine_failures()}
        asset_info = all_evals.get(machine_id)

        # Retrieve all history items
        records = (
            self.db.query(MaintenanceRecord)
            .filter(MaintenanceRecord.machine_id == machine_id)
            .order_by(MaintenanceRecord.recorded_at.desc())
            .all()
        )
        work_orders = (
            self.db.query(MaintenanceWorkOrder)
            .filter(MaintenanceWorkOrder.machine_id == machine_id)
            .order_by(MaintenanceWorkOrder.created_at.desc())
            .all()
        )
        alerts = (
            self.db.query(Alert)
            .filter(Alert.machine_id == machine_id)
            .order_by(Alert.created_at.desc())
            .all()
        )

        timeline = []
        for r in records:
            timeline.append({
                "type": "MAINTENANCE_RECORD",
                "timestamp": r.recorded_at.isoformat() if r.recorded_at else None,
                "title": f"Record #{r.id} ({r.failure_type or 'Status'})",
                "is_failure": r.failure_occurred,
                "notes": r.notes,
            })
        for wo in work_orders:
            timeline.append({
                "type": "WORK_ORDER",
                "timestamp": (wo.repair_completed_at or wo.completed_at or wo.created_at).isoformat() if (wo.repair_completed_at or wo.completed_at or wo.created_at) else None,
                "title": f"Work Order {wo.request_id} ({wo.status})",
                "is_failure": False,
                "notes": f"{wo.issue} | Technician: {wo.assigned_to or 'Unassigned'}",
                "cost": wo.total_cost,
            })
        for a in alerts:
            timeline.append({
                "type": "ALERT",
                "timestamp": a.created_at.isoformat() if a.created_at else None,
                "title": f"Alert: {a.alert_type} ({a.severity})",
                "is_failure": a.severity in ["CRITICAL", "WARNING"],
                "notes": a.message,
            })

        timeline.sort(key=lambda x: x["timestamp"] or "", reverse=True)

        return {
            "machine_id": machine.machine_id,
            "machine_type": machine.type,
            "location": machine.location,
            "status": machine.status,
            "current_risk": asset_info["current_risk"] if asset_info else "NOMINAL",
            "health_score": asset_info["health_score"] if asset_info else 98.0,
            "failure_probability": asset_info["failure_probability"] if asset_info else 0.05,
            "failure_count": asset_info["failure_count"] if asset_info else 0,
            "repair_count": asset_info["repair_count"] if asset_info else 0,
            "last_repair": asset_info.get("last_repair") if asset_info else None,
            "next_failure": asset_info.get("next_failure") if asset_info else None,
            "days_after_repair": asset_info.get("days_after_repair") if asset_info else None,
            "pattern": asset_info["pattern"] if asset_info else "Nominal",
            "timeline": timeline,
            "work_orders": [
                {
                    "request_id": wo.request_id,
                    "status": wo.status,
                    "issue": wo.issue,
                    "total_cost": wo.total_cost,
                    "created_at": wo.created_at.isoformat() if wo.created_at else None,
                }
                for wo in work_orders
            ],
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "status": a.status,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in alerts
            ],
            "failure_records": [
                {
                    "id": r.id,
                    "failure_type": r.failure_type,
                    "notes": r.notes,
                    "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                }
                for r in records if r.failure_occurred
            ],
        }
