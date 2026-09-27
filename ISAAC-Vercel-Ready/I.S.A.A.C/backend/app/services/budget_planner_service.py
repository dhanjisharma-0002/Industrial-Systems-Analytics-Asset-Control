"""
Service layer for Scenario-Based Maintenance Budget Planner.
Provides dynamic simulation of maintenance strategies for next-month budgeting:
- Scenario A: Repair all high-risk assets
- Scenario B: Repair only top 3 critical assets
- Scenario C: Delay maintenance by 30 days (Failure exposure estimation)

Integrates directly with:
- MachineRepository & SensorRepository
- AlertRepository & WorkOrderRepository
- PredictionService (ML health scoring & failure probability)
- MaintenanceService (for creating validated maintenance work orders without duplicates)
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from ..logger import logger
from ..models import Alert, Machine, MaintenanceRecord, MaintenanceWorkOrder, SensorData, utc_now
from ..repositories.alert_repository import AlertRepository
from ..repositories.machine_repository import MachineRepository
from ..repositories.sensor_repository import SensorRepository
from ..repositories.work_order_repository import WorkOrderRepository
from .maintenance_service import MaintenanceService
from .prediction_service import get_prediction_service


# =============================================================================
# Industrial Benchmark Constants (Documented Domain Assumptions)
# Reference: ISAAC CMMS & Predictive Maintenance Asset Economics
# =============================================================================

# Base scheduled preventative repair costs by machine grade (in INR ₹)
# Variant H (Heavy duty / CNC Turning): Higher part tolerances & tooling costs
# Variant M (Medium duty / Milling Centre): Standard industrial grade
# Variant L (Light duty / Grinding / Drill): Compact variant
BASE_REPAIR_COST_BY_TYPE: Dict[str, float] = {
    "H": 48000.0,
    "M": 32000.0,
    "L": 22000.0,
}

# Severity cost multiplier
# CRITICAL conditions require emergency tooling calibration and sensor flush
SEVERITY_COST_MULTIPLIER: Dict[str, float] = {
    "CRITICAL": 1.25,
    "HIGH": 1.0,
    "MEDIUM": 0.75,
    "LOW": 0.50,
}

# Expected downtime avoided per machine through scheduled proactive intervention (Hours)
# Unplanned failure averages 14 to 18 hours of lost production line throughput.
# Proactive service avoids catastrophic stoppage.
DOWNTIME_AVOIDED_HOURS_BY_PRIORITY: Dict[str, float] = {
    "CRITICAL": 14.0,
    "HIGH": 10.0,
    "MEDIUM": 6.0,
    "LOW": 3.0,
}

# Financial exposure constants per hour of unplanned stoppage
UNPLANNED_DOWNTIME_COST_PER_HOUR: float = 5000.0  # ₹5,000 / hr lost throughput
EMERGENCY_DISPATCH_SURCHARGE: float = 8000.0      # Emergency field technician rush fee
COLLATERAL_DAMAGE_COST_BY_TYPE: Dict[str, float] = {
    "H": 35000.0,  # Scrap workpieces & damaged spindle bearings
    "M": 25000.0,
    "L": 15000.0,
}


class BudgetPlannerService:
    def __init__(self, db: Session):
        self.db = db
        self.machine_repo = MachineRepository(db)
        self.sensor_repo = SensorRepository(db)
        self.alert_repo = AlertRepository(db)
        self.work_order_repo = WorkOrderRepository(db)
        self.maintenance_service = MaintenanceService(db)
        self.prediction_svc = get_prediction_service()

    # -------------------------------------------------------------------------
    # Asset Evaluation & Metric Aggregation
    # -------------------------------------------------------------------------

    def _get_evaluated_assets(
        self,
        risk_filter: str = "ALL",
        asset_type: str = "ALL",
        location: str = "ALL",
    ) -> List[Dict[str, Any]]:
        """
        Evaluate real fleet machines with live condition alerts, latest sensor
        telemetry, and ML health scores to produce enriched budget asset models.
        """
        all_machines = self.machine_repo.list_all()
        evaluated_assets: List[Dict[str, Any]] = []

        # Pre-fetch active work orders to prevent duplication
        active_orders, _ = self.work_order_repo.get_work_orders(limit=500)
        active_order_map: Dict[str, MaintenanceWorkOrder] = {}
        for order in active_orders:
            if order.status not in ["CLOSED", "CANCELLED"]:
                active_order_map[order.machine_id] = order

        for m in all_machines:
            # Asset type filter
            if asset_type and asset_type != "ALL" and m.type.upper() != asset_type.upper():
                continue

            # Location filter
            if location and location != "ALL" and location.lower() not in (m.location or "").lower():
                continue

            active_alerts = self.alert_repo.get_active_alerts_by_machine(m.machine_id)
            latest_reading = self.sensor_repo.get_latest_reading(m.machine_id)

            has_critical_alert = any(a.severity == "CRITICAL" for a in active_alerts)
            has_warning_alert = any(a.severity == "WARNING" for a in active_alerts)

            # ML Telemetry evaluation
            risk_level = "LOW"
            failure_prob = 0.05
            health_score = 98.0
            primary_issue = "Nominal operation"
            recommendation = "Maintain regular lubrication and operational inspection."
            primary_failure_type = "NORMAL"

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
                    risk_level = pred.get("risk_level", "LOW")
                    failure_prob = float(pred.get("failure_probability", 0.05))
                    health_score = float(pred.get("health_score", 98.0))
                    primary_failure_type = pred.get("primary_failure_type", "NORMAL")
                    if pred.get("recommendations"):
                        recommendation = pred["recommendations"][0]
                except Exception as err:
                    logger.warning(f"Prediction evaluation failed for {m.machine_id}: {err}")

            # Alert overrides take operational precedence
            if has_critical_alert:
                risk_level = "CRITICAL"
                failure_prob = max(failure_prob, 0.95)
                health_score = min(health_score, 32.0)
                crit_alert = next(a for a in active_alerts if a.severity == "CRITICAL")
                primary_issue = f"Critical Alert: {crit_alert.alert_type} ({crit_alert.message})"
                recommendation = self.maintenance_service._get_prescriptive_protocol(crit_alert.alert_type, m.type)
            elif has_warning_alert:
                if risk_level not in ["CRITICAL", "HIGH"]:
                    risk_level = "HIGH"
                failure_prob = max(failure_prob, 0.70)
                health_score = min(health_score, 54.0)
                warn_alert = next(a for a in active_alerts if a.severity == "WARNING")
                primary_issue = f"Warning: {warn_alert.alert_type} ({warn_alert.message})"
                recommendation = self.maintenance_service._get_prescriptive_protocol(warn_alert.alert_type, m.type)
            elif risk_level in ["CRITICAL", "HIGH"]:
                primary_issue = f"Elevated Sensor Degradation ({primary_failure_type}): Health Score {health_score:.1f}"

            # Check for repeat failure history
            m_records = self.db.query(MaintenanceRecord).filter(MaintenanceRecord.machine_id == m.machine_id).all()
            failure_count = sum(1 for r in m_records if r.failure_occurred or (r.failure_type and r.failure_type not in ["NORMAL", "MAINT_COMPLETE"]))
            
            is_repeat_failure = False
            repeat_pattern = None
            if failure_count >= 2:
                is_repeat_failure = True
                repeat_pattern = "Repeated failure"

            # Check if any repair was followed by a failure
            repairs = [
                wo for wo in active_orders
                if wo.machine_id == m.machine_id and wo.status in ["CLOSED", "COMPLETED"]
            ]
            if repairs:
                last_rep = repairs[-1]
                last_rep_dt = last_rep.repair_completed_at or last_rep.completed_at
                if last_rep_dt:
                    subsequent_failures = [
                        r for r in m_records
                        if r.failure_occurred and r.recorded_at and r.recorded_at > last_rep_dt
                    ]
                    if subsequent_failures:
                        is_repeat_failure = True
                        repeat_pattern = "Potential ineffective repair — review recommended"
                        risk_level = "CRITICAL"
                        priority = "CRITICAL"
                        health_score = min(health_score, 35.0)
                        failure_prob = max(failure_prob, 0.92)
                        primary_issue = f"Repeat Failure: Ineffective repair review recommended ({len(subsequent_failures)} recurring failures)"

            # Priority assignment
            priority = "CRITICAL" if risk_level == "CRITICAL" else ("HIGH" if risk_level == "HIGH" else ("MEDIUM" if risk_level == "MEDIUM" else "LOW"))

            # Risk filter check
            if risk_filter == "CRITICAL" and priority != "CRITICAL":
                continue
            if risk_filter == "HIGH" and priority not in ["CRITICAL", "HIGH"]:
                continue

            # Calculate repair cost
            base_cost = BASE_REPAIR_COST_BY_TYPE.get(m.type, 30000.0)
            cost_mult = SEVERITY_COST_MULTIPLIER.get(priority, 1.0)
            estimated_repair_cost = round(base_cost * cost_mult, 2)

            # Calculate downtime avoided
            downtime_avoided = DOWNTIME_AVOIDED_HOURS_BY_PRIORITY.get(priority, 6.0)

            # Calculate failure exposure (Financial risk under delay/inaction)
            # Exposure = Fail Prob * (Downtime Hrs * Rate + Collateral Parts Damage + Emergency Surcharge)
            collateral_damage = COLLATERAL_DAMAGE_COST_BY_TYPE.get(m.type, 25000.0)
            unmitigated_loss = (downtime_avoided * UNPLANNED_DOWNTIME_COST_PER_HOUR) + collateral_damage + EMERGENCY_DISPATCH_SURCHARGE
            failure_exposure = round(failure_prob * unmitigated_loss, 2)

            active_wo = active_order_map.get(m.machine_id)

            evaluated_assets.append({
                "machine_id": m.machine_id,
                "machine_type": m.type,
                "location": m.location,
                "status": m.status,
                "risk_level": risk_level,
                "priority": priority,
                "health_score": round(health_score, 1),
                "failure_probability": round(failure_prob, 3),
                "primary_failure_type": primary_failure_type,
                "primary_issue": primary_issue,
                "recommended_action": recommendation,
                "estimated_repair_cost": estimated_repair_cost,
                "expected_downtime_hours": downtime_avoided,
                "failure_exposure": failure_exposure,
                "has_active_work_order": active_wo is not None,
                "active_work_order_id": active_wo.request_id if active_wo else None,
                "active_work_order_status": active_wo.status if active_wo else None,
                "is_repeat_failure": is_repeat_failure,
                "repeat_failure_pattern": repeat_pattern,
            })


        # Sort descending by priority, failure probability, and repair cost
        priority_rank = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
        evaluated_assets.sort(
            key=lambda x: (
                priority_rank.get(x["priority"], 0),
                x["failure_probability"],
                x["estimated_repair_cost"],
            ),
            reverse=True,
        )

        return evaluated_assets

    # -------------------------------------------------------------------------
    # Scenario Generation & Comparison
    # -------------------------------------------------------------------------

    def generate_budget_summary(
        self,
        available_budget: float = 300000.0,
        risk_filter: str = "ALL",
        asset_type: str = "ALL",
        location: str = "ALL",
    ) -> Dict[str, Any]:
        """
        Generate complete Scenario-Based Budget Planner summary including
        three strategic scenarios, comparison matrix, and asset counts.
        """
        assets = self._get_evaluated_assets(
            risk_filter=risk_filter,
            asset_type=asset_type,
            location=location,
        )

        critical_assets = [a for a in assets if a["priority"] == "CRITICAL"]
        high_risk_assets = [a for a in assets if a["priority"] in ["CRITICAL", "HIGH"]]

        # Scenario A: Repair all high-risk assets
        scenario_a_assets = high_risk_assets
        scenario_a_cost = round(sum(a["estimated_repair_cost"] for a in scenario_a_assets), 2)
        scenario_a_downtime_avoided = round(sum(a["expected_downtime_hours"] for a in scenario_a_assets), 1)
        # Residual exposure under full repair is minimal (~5% unforeseen residual)
        scenario_a_residual_exposure = round(sum(a["failure_exposure"] * 0.05 for a in scenario_a_assets), 2)
        scenario_a_utilization = round((scenario_a_cost / available_budget * 100.0), 1) if available_budget > 0 else 0.0

        # Scenario B: Repair only top 3 critical assets
        # Prioritize top 3 critical assets (or top 3 high-risk if < 3 critical)
        scenario_b_assets = critical_assets[:3] if len(critical_assets) >= 3 else high_risk_assets[:3]
        scenario_b_cost = round(sum(a["estimated_repair_cost"] for a in scenario_b_assets), 2)
        scenario_b_downtime_avoided = round(sum(a["expected_downtime_hours"] for a in scenario_b_assets), 1)
        # Exposure includes residual of repaired plus 100% of unserviced at-risk assets
        serviced_ids = {a["machine_id"] for a in scenario_b_assets}
        unserviced_assets = [a for a in high_risk_assets if a["machine_id"] not in serviced_ids]
        scenario_b_residual_exposure = round(
            sum(a["failure_exposure"] for a in unserviced_assets) +
            sum(a["failure_exposure"] * 0.05 for a in scenario_b_assets),
            2,
        )
        scenario_b_utilization = round((scenario_b_cost / available_budget * 100.0), 1) if available_budget > 0 else 0.0

        # Scenario C: Delay maintenance by 30 days
        scenario_c_assets = high_risk_assets
        scenario_c_cost = 0.0
        scenario_c_downtime_avoided = 0.0
        # Total unmitigated failure exposure across all at-risk machines
        scenario_c_exposure = round(sum(a["failure_exposure"] for a in high_risk_assets), 2)
        scenario_c_utilization = 0.0

        # Helper to determine budget status badge
        def get_budget_status(cost: float, budget: float) -> str:
            if budget <= 0:
                return "Exceeds Budget"
            pct = (cost / budget) * 100.0
            if pct <= 85.0:
                return "Within Budget"
            elif pct <= 100.0:
                return "Near Budget Limit"
            return "Exceeds Budget"

        scenarios = [
            {
                "scenario_id": "repair_all_high_risk",
                "code": "SCENARIO_A",
                "title": "Repair all high-risk assets",
                "subtitle": "Comprehensive proactive overhaul for fleet maximum reliability",
                "description": "Proactively service all machines exhibiting critical condition breaches or elevated ML wear probabilities. Eliminates imminent downtime and preserves maximum operational throughput.",
                "estimated_cost": scenario_a_cost,
                "downtime_avoided_hours": scenario_a_downtime_avoided,
                "failure_exposure": scenario_a_residual_exposure,
                "assets_affected_count": len(scenario_a_assets),
                "affected_machine_ids": [a["machine_id"] for a in scenario_a_assets],
                "budget_utilization_pct": scenario_a_utilization,
                "budget_status": get_budget_status(scenario_a_cost, available_budget),
                "risk_indicator": "Minimal Residual Risk",
                "risk_color": "green",
                "action_label": "View Impact",
            },
            {
                "scenario_id": "repair_top_critical",
                "code": "SCENARIO_B",
                "title": "Repair only top 3 critical assets",
                "subtitle": "Targeted triage for core production line assets",
                "description": "Concentrate available capital on the 3 highest severity machines to secure critical path uptime while deferring secondary assets to optimize immediate cash flow.",
                "estimated_cost": scenario_b_cost,
                "downtime_avoided_hours": scenario_b_downtime_avoided,
                "failure_exposure": scenario_b_residual_exposure,
                "assets_affected_count": len(scenario_b_assets),
                "affected_machine_ids": [a["machine_id"] for a in scenario_b_assets],
                "budget_utilization_pct": scenario_b_utilization,
                "budget_status": get_budget_status(scenario_b_cost, available_budget),
                "risk_indicator": "Moderate Residual Risk",
                "risk_color": "amber",
                "action_label": "View Impact",
            },
            {
                "scenario_id": "delay_maintenance_30_days",
                "code": "SCENARIO_C",
                "title": "Delay maintenance by 30 days",
                "subtitle": "Run-to-breakdown deferral with high contingency risk",
                "description": "Defer immediate scheduled interventions by one calendar month. Yields zero upfront maintenance draw but exposes operations to emergency outage penalties and catastrophic spindle wear.",
                "estimated_cost": scenario_c_cost,
                "downtime_avoided_hours": scenario_c_downtime_avoided,
                "failure_exposure": scenario_c_exposure,
                "assets_affected_count": len(scenario_c_assets),
                "affected_machine_ids": [a["machine_id"] for a in scenario_c_assets],
                "budget_utilization_pct": scenario_c_utilization,
                "budget_status": "Within Budget (Upfront)",
                "risk_indicator": "Extreme Failure Exposure",
                "risk_color": "red",
                "action_label": "View Impact",
            },
        ]

        comparison = [
            {
                "scenario_id": s["scenario_id"],
                "strategy": s["title"],
                "code": s["code"],
                "estimated_cost": s["estimated_cost"],
                "downtime_avoided": f"{s['downtime_avoided_hours']} hrs",
                "downtime_avoided_raw": s["downtime_avoided_hours"],
                "failure_exposure": s["failure_exposure"],
                "assets_covered": s["assets_affected_count"],
                "budget_utilization": f"{s['budget_utilization_pct']}%",
                "budget_utilization_raw": s["budget_utilization_pct"],
                "status": s["budget_status"],
            }
            for s in scenarios
        ]

        # Explicit assumptions disclosure for auditability
        assumptions = {
            "planning_horizon": "Next Month",
            "currency": "INR (₹)",
            "calculation_basis": "Empirical historical repairs + machine variant baseline + ML failure probability",
            "rates": {
                "unplanned_downtime_rate_per_hour": UNPLANNED_DOWNTIME_COST_PER_HOUR,
                "emergency_technician_surcharge": EMERGENCY_DISPATCH_SURCHARGE,
                "base_scheduled_repair_cost": BASE_REPAIR_COST_BY_TYPE,
            },
            "disclaimer": "Scenario estimates are operational projections based on active condition breaches, ML health scoring, and historical repair cost benchmarks.",
        }

        return {
            "available_budget": available_budget,
            "planning_horizon": "Next Month",
            "total_fleet_count": len(assets),
            "high_risk_count": len(high_risk_assets),
            "critical_count": len(critical_assets),
            "currency_symbol": "₹",
            "scenarios": scenarios,
            "comparison": comparison,
            "assumptions": assumptions,
        }

    # -------------------------------------------------------------------------
    # Scenario Asset Breakdown
    # -------------------------------------------------------------------------

    def get_scenario_assets(
        self,
        scenario_id: str,
        risk_filter: str = "ALL",
        asset_type: str = "ALL",
        location: str = "ALL",
    ) -> List[Dict[str, Any]]:
        """
        Return the exact list of machines and diagnostic specifics corresponding
        to a selected scenario.
        """
        all_assets = self._get_evaluated_assets(
            risk_filter=risk_filter,
            asset_type=asset_type,
            location=location,
        )

        critical_assets = [a for a in all_assets if a["priority"] == "CRITICAL"]
        high_risk_assets = [a for a in all_assets if a["priority"] in ["CRITICAL", "HIGH"]]

        if scenario_id == "repair_top_critical":
            return critical_assets[:3] if len(critical_assets) >= 3 else high_risk_assets[:3]
        elif scenario_id == "repair_all_high_risk":
            return high_risk_assets
        elif scenario_id == "delay_maintenance_30_days":
            return high_risk_assets
        else:
            # Default fallback: return all high-risk assets
            return high_risk_assets

    # -------------------------------------------------------------------------
    # Confirmed Maintenance Plan Creation
    # -------------------------------------------------------------------------

    def create_maintenance_plan(
        self,
        scenario_id: str,
        scenario_name: str,
        selected_machine_ids: List[str],
        planning_month: str = "Next Month",
        requested_by: str = "Maintenance Manager",
        estimated_budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Create official confirmed maintenance work orders in the database for
        the selected scenario assets.
        - Validates asset IDs against machine registry
        - Prevents duplicate active work orders
        - Maintains full audit trail via WorkflowLog
        """
        if not selected_machine_ids:
            raise ValueError("No machine assets were specified for maintenance plan creation.")

        # Pre-fetch existing active work orders
        active_orders, _ = self.work_order_repo.get_work_orders(limit=500)
        active_machine_ids = {
            wo.machine_id: wo
            for wo in active_orders
            if wo.status not in ["CLOSED", "CANCELLED"]
        }

        # Fetch candidate asset metadata
        all_evaluated = {
            a["machine_id"]: a
            for a in self._get_evaluated_assets()
        }

        created_orders: List[Dict[str, Any]] = []
        skipped_existing_active: List[Dict[str, Any]] = []
        total_scheduled_cost: float = 0.0

        for mid in selected_machine_ids:
            machine = self.machine_repo.get_by_id(mid)
            if not machine:
                logger.warning(f"Machine asset '{mid}' not found in registry during plan creation.")
                continue

            # Check for existing active work order (Prevent duplicates)
            if mid in active_machine_ids:
                existing_wo = active_machine_ids[mid]
                skipped_existing_active.append({
                    "machine_id": mid,
                    "existing_request_id": existing_wo.request_id,
                    "status": existing_wo.status,
                    "reason": f"Active work order '{existing_wo.request_id}' is already in status {existing_wo.status}.",
                })
                continue

            asset_meta = all_evaluated.get(mid, {})
            est_cost = asset_meta.get("estimated_repair_cost") or BASE_REPAIR_COST_BY_TYPE.get(machine.type, 30000.0)
            priority = asset_meta.get("priority", "HIGH")
            risk = asset_meta.get("risk_level", "HIGH")
            recommendation = asset_meta.get("recommended_action") or f"Scheduled preventative overhaul ({planning_month})"
            issue = f"Budget Plan [{scenario_name}]: {asset_meta.get('primary_issue', 'Scheduled Maintenance Interception')}"

            # Create work order through existing enterprise MaintenanceService
            wo = self.maintenance_service.create_maintenance_request(
                machine_id=mid,
                issue=issue,
                risk=risk,
                recommendation=recommendation,
                priority=priority,
                requested_by=f"{requested_by} (Budget Planner)",
                estimated_cost=est_cost,
            )

            created_orders.append(self.maintenance_service._serialize_work_order(wo))
            total_scheduled_cost += est_cost

        return {
            "success": True,
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "planning_month": planning_month,
            "total_requested": len(selected_machine_ids),
            "created_count": len(created_orders),
            "skipped_count": len(skipped_existing_active),
            "total_scheduled_cost": round(total_scheduled_cost, 2),
            "created_work_orders": created_orders,
            "skipped_active_assets": skipped_existing_active,
            "message": (
                f"Successfully created {len(created_orders)} maintenance work orders for {planning_month} "
                f"totalling ₹{total_scheduled_cost:,.2f}."
                + (f" ({len(skipped_existing_active)} assets skipped due to active work orders)." if skipped_existing_active else "")
            ),
        }
