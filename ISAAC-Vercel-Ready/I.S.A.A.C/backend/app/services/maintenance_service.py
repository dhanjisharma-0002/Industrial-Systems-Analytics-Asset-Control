"""
Service layer for Phase 6 Maintenance Technician, Repair Workflow & Cost Tracking.
Enforces realistic industrial CMMS lifecycle:
PENDING -> ASSIGNED -> TECHNICIAN_ARRIVED -> INSPECTION -> REPAIR_IN_PROGRESS -> COMPLETED -> CLOSED (or CANCELLED).
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from ..logger import logger
from ..models import Alert, Machine, MaintenanceRecord, MaintenanceWorkOrder, Technician, utc_now
from ..repositories.alert_repository import AlertRepository
from ..repositories.machine_repository import MachineRepository
from ..repositories.maintenance_repository import MaintenanceRepository
from ..repositories.sensor_repository import SensorRepository
from ..repositories.technician_repository import TechnicianRepository
from ..repositories.workflow_repository import WorkflowRepository
from ..repositories.work_order_repository import WorkOrderRepository
from .prediction_service import get_prediction_service


class MaintenanceService:
    def __init__(self, db: Session):
        self.db = db
        self.work_order_repo = WorkOrderRepository(db)
        self.technician_repo = TechnicianRepository(db)
        self.machine_repo = MachineRepository(db)
        self.alert_repo = AlertRepository(db)
        self.workflow_repo = WorkflowRepository(db)
        self.maintenance_record_repo = MaintenanceRepository(db)
        self.sensor_repo = SensorRepository(db)
        self.prediction_svc = get_prediction_service()

    def _serialize_work_order(self, wo: MaintenanceWorkOrder) -> Dict[str, Any]:
        """Convert MaintenanceWorkOrder ORM instance to enriched dictionary."""
        duration = None
        if wo.repair_started_at and wo.repair_completed_at:
            duration = round((wo.repair_completed_at - wo.repair_started_at).total_seconds() / 60.0, 1)
        elif wo.completed_at and wo.created_at:
            duration = round((wo.completed_at - wo.created_at).total_seconds() / 60.0, 1)

        # Enriched technician info
        tech_dict = None
        if wo.technician:
            tech_dict = {
                "id": wo.technician.id,
                "technician_id": wo.technician.technician_id,
                "technician_name": wo.technician.technician_name,
                "specialization": wo.technician.specialization,
                "company": wo.technician.company,
                "phone": wo.technician.phone,
                "email": wo.technician.email,
                "experience_years": wo.technician.experience_years,
                "certification": wo.technician.certification,
                "status": wo.technician.status,
                "created_at": wo.technician.created_at,
            }

        # Enriched machine info
        machine_type = wo.machine.type if wo.machine else None
        machine_loc = wo.machine.location if wo.machine else None

        return {
            "id": wo.id,
            "request_id": wo.request_id,
            "machine_id": wo.machine_id,
            "alert_id": wo.alert_id,
            "technician_id": wo.technician_id,
            "issue": wo.issue,
            "risk": wo.risk,
            "recommendation": wo.recommendation,
            "priority": wo.priority,
            "status": wo.status,
            "work_type": wo.work_type,
            "requested_by": wo.requested_by,
            "assigned_by": wo.assigned_by,
            "assigned_to": wo.assigned_to,
            "alert_created_at": wo.alert_created_at,
            "maintenance_requested_at": wo.maintenance_requested_at or wo.created_at,
            "technician_assigned_at": wo.technician_assigned_at,
            "technician_arrived_at": wo.technician_arrived_at,
            "inspection_started_at": wo.inspection_started_at,
            "repair_started_at": wo.repair_started_at,
            "repair_completed_at": wo.repair_completed_at,
            "maintenance_closed_at": wo.maintenance_closed_at,
            "created_at": wo.created_at,
            "completed_at": wo.completed_at,
            "scheduled_for": wo.scheduled_for,
            "duration_minutes": duration,
            "problem_description": wo.problem_description,
            "diagnosis": wo.diagnosis,
            "work_performed": wo.work_performed,
            "root_cause": wo.root_cause,
            "parts_used": wo.parts_used,
            "repair_notes": wo.repair_notes,
            "completion_notes": wo.completion_notes,
            "resolution_notes": wo.resolution_notes,
            "cancellation_reason": wo.cancellation_reason,
            "estimated_cost": wo.estimated_cost,
            "labour_cost": wo.labour_cost,
            "parts_cost": wo.parts_cost,
            "other_cost": wo.other_cost,
            "total_cost": wo.total_cost,
            "technician": tech_dict,
            "machine_type": machine_type,
            "machine_location": machine_loc,
        }

    # -------------------------------------------------------------------------
    # Technician Management APIs
    # -------------------------------------------------------------------------

    def create_technician(
        self,
        technician_name: str,
        specialization: str = "General Maintenance",
        technician_id: Optional[str] = None,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        experience_years: Optional[int] = 0,
        certification: Optional[str] = None,
        status: str = "AVAILABLE",
    ) -> Technician:
        """Register a new field maintenance technician."""
        return self.technician_repo.create_technician(
            technician_name=technician_name,
            specialization=specialization,
            technician_id=technician_id,
            company=company,
            phone=phone,
            email=email,
            experience_years=experience_years,
            certification=certification,
            status=status,
        )

    def list_technicians(
        self,
        specialization: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Technician], int]:
        """List registered technicians with optional filtering."""
        return self.technician_repo.list_technicians(
            specialization=specialization,
            status=status,
            limit=limit,
            offset=offset,
        )

    def get_technician_by_id(self, technician_id: str) -> Optional[Technician]:
        """Fetch a specific technician profile."""
        return self.technician_repo.get_by_technician_id(technician_id)

    # -------------------------------------------------------------------------
    # Predictive Recommendations (Due Maintenance Needs)
    # -------------------------------------------------------------------------

    def get_predicted_recommendations(self) -> List[Dict[str, Any]]:
        """
        Scan active machines, predictive failure risk, and active alerts to generate
        deterministic PREDICTED MAINTENANCE NEEDS.
        """
        recommendations: List[Dict[str, Any]] = []
        machines = self.machine_repo.list_all()

        for m in machines:
            active_alerts = self.alert_repo.get_active_alerts_by_machine(m.machine_id)
            latest_reading = self.sensor_repo.get_latest_reading(m.machine_id)

            if active_alerts:
                top_alert = active_alerts[0]
                priority = "CRITICAL" if top_alert.severity == "CRITICAL" else "HIGH"
                recommendations.append({
                    "recommendation_id": f"REC-ALT-{top_alert.alert_id}",
                    "machine_id": m.machine_id,
                    "machine_type": m.type,
                    "issue": f"Active {top_alert.alert_type}: {top_alert.message}",
                    "risk": f"{top_alert.severity} Condition Breach",
                    "failure_probability": 0.95 if top_alert.severity == "CRITICAL" else 0.75,
                    "health_score": 35.0 if top_alert.severity == "CRITICAL" else 55.0,
                    "recommendation": self._get_prescriptive_protocol(top_alert.alert_type, m.type),
                    "priority": priority,
                    "status": "DUE",
                    "due_status": "IMMEDIATE" if top_alert.severity == "CRITICAL" else "DUE_SOON",
                    "source": "CONDITION_ALERT",
                    "linked_alert_id": top_alert.alert_id,
                    "suggested_action": f"Create Work Order for {top_alert.alert_type} on {m.machine_id}",
                    "created_at": top_alert.created_at,
                })
                continue

            if latest_reading:
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
                fail_prob = pred.get("failure_probability", 0.0)
                health_score = pred.get("health_score", 100.0)

                if risk_level in ["HIGH", "CRITICAL"] or fail_prob >= 0.50 or health_score < 70.0:
                    pri = "CRITICAL" if risk_level == "CRITICAL" else "HIGH"
                    action_rec = (
                        pred.get("recommendations", ["Inspect cutting tool inserts and spindle tolerances."])[0]
                        if pred.get("recommendations")
                        else "Execute preventative maintenance protocol."
                    )

                    recommendations.append({
                        "recommendation_id": f"REC-ML-{m.machine_id}-{latest_reading.id}",
                        "machine_id": m.machine_id,
                        "machine_type": m.type,
                        "issue": f"Elevated Failure Risk ({risk_level}): Health Score {health_score:.1f}/100",
                        "risk": f"{risk_level} ({fail_prob * 100:.1f}%)",
                        "failure_probability": round(fail_prob, 3),
                        "health_score": health_score,
                        "recommendation": action_rec,
                        "priority": pri,
                        "status": "DUE",
                        "due_status": "IMMEDIATE" if risk_level == "CRITICAL" else "DUE_SOON",
                        "source": "PREDICTIVE_ML",
                        "linked_alert_id": None,
                        "suggested_action": "Schedule preventative work order before failure probability reaches 100%",
                        "created_at": latest_reading.recorded_at,
                    })

        return recommendations

    def _get_prescriptive_protocol(self, alert_type: str, machine_type: str) -> str:
        """Helper to retrieve domain-specific prescriptive engineering protocols."""
        at = str(alert_type).upper()
        if "OVERSTRAIN" in at or "OSF" in at:
            return f"Immediate Spindle Halt. Halt spindle rotation; inspect cutting tool inserts, spindle bearings, and workpiece clamping (Grade {machine_type})."
        elif "HEAT" in at or "HDF" in at:
            return "Flush heat dissipation channels, verify coolant flow rate >= 12 L/min, and clean spindle radiator fins."
        elif "POWER" in at or "PWF" in at:
            return "Inspect motor drive electrical inverter, check supply phase balance, and measure torque draw across operating range."
        elif "TOOL" in at or "TWF" in at:
            return "Replace worn cutting tool inserts and perform automated tool offset calibration."
        return "Conduct full mechanical and electrical diagnostic inspection according to standard SOP."

    # -------------------------------------------------------------------------
    # Phase 6 Maintenance Lifecycle Execution
    # -------------------------------------------------------------------------

    def create_maintenance_request(
        self,
        machine_id: str,
        issue: str,
        risk: str = "MEDIUM",
        recommendation: Optional[str] = None,
        priority: str = "MEDIUM",
        requested_by: str = "Reliability Engineer",
        alert_id: Optional[str] = None,
        technician_id: Optional[str] = None,
        assigned_by: Optional[str] = None,
        assigned_to: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        estimated_cost: Optional[float] = None,
    ) -> MaintenanceWorkOrder:
        """Step 1: Create a formal confirmed maintenance work order in PENDING status."""
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine asset '{machine_id}' was not found.")

        now_ms = int(time.time() * 1000)
        request_id = f"MNT-{machine_id}-{now_ms}"

        rec = recommendation or self._get_prescriptive_protocol(issue, machine.type)
        pri = priority.upper()
        if pri not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            pri = "MEDIUM"

        alert_created_time = None
        if alert_id:
            alert = self.alert_repo.get_by_alert_id(alert_id)
            if alert:
                alert_created_time = alert.created_at

        # Persist work order
        wo = self.work_order_repo.create_work_order(
            request_id=request_id,
            machine_id=machine_id,
            issue=issue,
            risk=risk,
            recommendation=rec,
            priority=pri,
            status="PENDING",
            work_type="CONFIRMED_WORK_ORDER",
            requested_by=requested_by,
            alert_id=alert_id,
            technician_id=technician_id,
            assigned_by=assigned_by,
            assigned_to=assigned_to,
            alert_created_at=alert_created_time,
            scheduled_for=scheduled_for,
            estimated_cost=estimated_cost,
        )

        # Update machine status to MAINTENANCE_REQUIRED if operational
        prev_status = machine.status
        if prev_status == "OPERATIONAL":
            self.machine_repo.update_status(machine_id, "MAINTENANCE_REQUIRED")

        # Record in Workflow Audit Log
        self.workflow_repo.log_action(
            machine_id=machine_id,
            maintenance_id=request_id,
            action_type="MAINTENANCE_REQUEST",
            performed_by=requested_by,
            notes=f"Work Order {request_id} created. Priority: {pri}. Issue: {issue}",
            previous_status=prev_status,
            new_status="MAINTENANCE_REQUIRED" if prev_status == "OPERATIONAL" else prev_status,
        )

        return wo

    def assign_technician(
        self,
        request_id: str,
        technician_id: str,
        assigned_by: str = "Anu Sharma (Maintenance Lead)",
        priority: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Step 2: Maintenance Lead assigns a technician (PENDING -> ASSIGNED)."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status != "PENDING":
            raise ValueError(f"Cannot assign technician to work order in '{wo.status}' status. Must be PENDING.")

        tech = self.technician_repo.get_by_technician_id(technician_id)
        if not tech:
            raise ValueError(f"Technician with ID '{technician_id}' was not found.")

        logger.info(f"Assigning technician '{tech.technician_name}' ({tech.technician_id}) to '{request_id}' by '{assigned_by}'")

        # Update work order
        updated_wo = self.work_order_repo.assign_technician(
            request_id=request_id,
            technician_id=tech.technician_id,
            technician_name=tech.technician_name,
            assigned_by=assigned_by,
            priority=priority,
            notes=notes,
        )

        # Update technician status to ASSIGNED
        self.technician_repo.update_status(tech.technician_id, "ASSIGNED")

        # Log audit entry
        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="ASSIGN_TECHNICIAN",
            performed_by=assigned_by,
            notes=f"Technician {tech.technician_name} ({tech.specialization}) assigned by {assigned_by}. {notes or ''}".strip(),
            previous_status="PENDING",
            new_status="ASSIGNED",
        )

        return {
            "success": True,
            "message": f"Technician '{tech.technician_name}' successfully assigned to work order '{request_id}'.",
            "machine_id": wo.machine_id,
            "action_type": "ASSIGN_TECHNICIAN",
            "new_status": "ASSIGNED",
            "timestamp": updated_wo.technician_assigned_at,
        }

    def mark_technician_arrived(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Step 3: Real technician on-site arrival (ASSIGNED -> TECHNICIAN_ARRIVED)."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status != "ASSIGNED":
            raise ValueError(f"Cannot mark technician arrival from status '{wo.status}'. Work order must be ASSIGNED.")

        actor = performed_by or wo.assigned_to or "Maintenance Technician"
        logger.info(f"Technician arrived for work order '{request_id}' (Actor: {actor})")

        updated_wo = self.work_order_repo.mark_technician_arrived(
            request_id=request_id,
            performed_by=actor,
            notes=notes,
        )

        if wo.technician_id:
            self.technician_repo.update_status(wo.technician_id, "ON_SITE")

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="TECHNICIAN_ARRIVED",
            performed_by=actor,
            notes=f"Technician arrived on-site at asset {wo.machine_id}. {notes or ''}".strip(),
            previous_status="ASSIGNED",
            new_status="TECHNICIAN_ARRIVED",
        )

        return {
            "success": True,
            "message": f"Technician arrival confirmed for work order '{request_id}'.",
            "machine_id": wo.machine_id,
            "action_type": "TECHNICIAN_ARRIVED",
            "new_status": "TECHNICIAN_ARRIVED",
            "timestamp": updated_wo.technician_arrived_at,
        }

    def start_inspection(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Step 4: Technician begins machine physical inspection (TECHNICIAN_ARRIVED -> INSPECTION)."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status not in ["TECHNICIAN_ARRIVED", "ASSIGNED"]:
            raise ValueError(f"Cannot start inspection from status '{wo.status}'. Work order must be TECHNICIAN_ARRIVED or ASSIGNED.")

        actor = performed_by or wo.assigned_to or "Maintenance Technician"
        logger.info(f"Starting inspection for work order '{request_id}' by '{actor}'")

        updated_wo = self.work_order_repo.start_inspection(
            request_id=request_id,
            performed_by=actor,
            notes=notes,
        )

        # Update machine status to INSPECTION_IN_PROGRESS
        machine = self.machine_repo.get_by_id(wo.machine_id)
        prev_m_status = machine.status if machine else "UNKNOWN"
        if machine:
            self.machine_repo.update_status(wo.machine_id, "INSPECTION_IN_PROGRESS")

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="START_INSPECTION",
            performed_by=actor,
            notes=notes or f"Physical machine inspection commenced by {actor}.",
            previous_status=prev_m_status,
            new_status="INSPECTION_IN_PROGRESS",
        )

        return {
            "success": True,
            "message": f"Inspection started for work order '{request_id}'.",
            "machine_id": wo.machine_id,
            "action_type": "START_INSPECTION",
            "new_status": "INSPECTION",
            "timestamp": updated_wo.inspection_started_at,
        }

    def start_repair(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        diagnosis: Optional[str] = None,
        problem_description: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Step 5: Technician commences physical repair work (INSPECTION -> REPAIR_IN_PROGRESS)."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status not in ["INSPECTION", "TECHNICIAN_ARRIVED", "ASSIGNED"]:
            raise ValueError(f"Cannot start repair from status '{wo.status}'. Work order must be INSPECTION or TECHNICIAN_ARRIVED.")

        actor = performed_by or wo.assigned_to or "Maintenance Technician"
        logger.info(f"Starting repair for work order '{request_id}' by '{actor}'")

        updated_wo = self.work_order_repo.start_repair(
            request_id=request_id,
            performed_by=actor,
            diagnosis=diagnosis,
            problem_description=problem_description,
            notes=notes,
        )

        # Update machine status to MAINTENANCE_IN_PROGRESS
        machine = self.machine_repo.get_by_id(wo.machine_id)
        prev_m_status = machine.status if machine else "UNKNOWN"
        if machine:
            self.machine_repo.update_status(wo.machine_id, "MAINTENANCE_IN_PROGRESS")

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="START_REPAIR",
            performed_by=actor,
            notes=f"Repair started. Diagnosis: {diagnosis or 'In progress'}. {notes or ''}".strip(),
            previous_status=prev_m_status,
            new_status="MAINTENANCE_IN_PROGRESS",
        )

        return {
            "success": True,
            "message": f"Repair work commenced for work order '{request_id}'.",
            "machine_id": wo.machine_id,
            "action_type": "START_REPAIR",
            "new_status": "REPAIR_IN_PROGRESS",
            "timestamp": updated_wo.repair_started_at,
        }

    def complete_repair(
        self,
        request_id: str,
        performed_by: str = "Maintenance Technician",
        diagnosis: Optional[str] = None,
        work_performed: Optional[str] = None,
        root_cause: Optional[str] = None,
        parts_used: Optional[str] = None,
        repair_notes: Optional[str] = None,
        completion_notes: Optional[str] = "Maintenance procedures completed successfully.",
        labour_cost: Optional[float] = None,
        parts_cost: Optional[float] = None,
        other_cost: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Step 6: Technician completes repair and logs parts, labour, and root cause (REPAIR_IN_PROGRESS -> COMPLETED).
        Enforces strict state validation: CANNOT complete repair before starting repair!
        """
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status != "REPAIR_IN_PROGRESS" and wo.status != "IN_PROGRESS":
            raise ValueError(f"Cannot complete repair from status '{wo.status}'. Repair must be started first (REPAIR_IN_PROGRESS).")

        actor = performed_by or wo.assigned_to or "Maintenance Technician"
        logger.info(f"Completing repair for work order '{request_id}' by '{actor}'")

        updated_wo = self.work_order_repo.complete_repair(
            request_id=request_id,
            performed_by=actor,
            diagnosis=diagnosis,
            work_performed=work_performed,
            root_cause=root_cause,
            parts_used=parts_used,
            repair_notes=repair_notes,
            completion_notes=completion_notes,
            labour_cost=labour_cost,
            parts_cost=parts_cost,
            other_cost=other_cost,
        )

        # Calculate duration
        duration_min = None
        if updated_wo.repair_started_at and updated_wo.repair_completed_at:
            duration_min = round((updated_wo.repair_completed_at - updated_wo.repair_started_at).total_seconds() / 60.0, 1)

        cost_note = f"Total Cost: ₹{updated_wo.total_cost:,.2f}" if updated_wo.total_cost is not None else "Cost: Not recorded"
        dur_note = f"Duration: {duration_min} min" if duration_min is not None else ""

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="COMPLETE_REPAIR",
            performed_by=actor,
            notes=f"Repair completed by {actor}. {work_performed or ''} | {cost_note} | {dur_note}".strip(),
            previous_status="REPAIR_IN_PROGRESS",
            new_status="COMPLETED",
        )

        return {
            "success": True,
            "message": f"Repair completed successfully for work order '{request_id}'. Total Cost: ₹{updated_wo.total_cost or 0:,.2f}.",
            "machine_id": wo.machine_id,
            "action_type": "COMPLETE_REPAIR",
            "new_status": "COMPLETED",
            "duration_minutes": duration_min,
            "total_cost": updated_wo.total_cost,
            "timestamp": updated_wo.repair_completed_at,
        }

    def close_maintenance(
        self,
        request_id: str,
        performed_by: str = "Anu Sharma (Maintenance Lead)",
        closure_notes: Optional[str] = "Maintenance verified and approved for return to service.",
        resolve_linked_alerts: bool = True,
    ) -> Dict[str, Any]:
        """
        Step 7: Maintenance Lead verifies repair and signs off maintenance (COMPLETED -> CLOSED).
        Restores machine to OPERATIONAL and updates permanent maintenance history.
        """
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status != "COMPLETED":
            raise ValueError(f"Cannot close maintenance from status '{wo.status}'. Work order must be in COMPLETED state.")

        logger.info(f"Closing maintenance for work order '{request_id}' by '{performed_by}'")

        updated_wo = self.work_order_repo.close_maintenance(
            request_id=request_id,
            performed_by=performed_by,
            closure_notes=closure_notes,
        )

        # Free technician back to AVAILABLE
        if wo.technician_id:
            self.technician_repo.update_status(wo.technician_id, "AVAILABLE")

        # Auto-resolve linked alert or active alerts for machine
        resolved_alerts_count = 0
        if resolve_linked_alerts:
            if wo.alert_id:
                res = self.alert_repo.resolve_alert(
                    alert_id=wo.alert_id,
                    performed_by=performed_by,
                    notes=f"Resolved via Work Order {request_id}. {closure_notes}",
                    resolution_action=wo.work_performed or "Maintenance completed",
                )
                if res:
                    resolved_alerts_count += 1
            else:
                resolved_alerts_count = self.alert_repo.resolve_alerts_for_machine(
                    machine_id=wo.machine_id,
                    performed_by=performed_by,
                    notes=f"Resolved via Work Order {request_id}. {closure_notes}",
                )

        # Restore machine to OPERATIONAL if no other active work orders exist
        other_active = self.work_order_repo.get_active_work_orders(wo.machine_id)
        machine = self.machine_repo.get_by_id(wo.machine_id)
        prev_status = machine.status if machine else "UNKNOWN"
        new_m_status = "OPERATIONAL" if not other_active else prev_status
        if machine and not other_active:
            self.machine_repo.update_status(wo.machine_id, "OPERATIONAL")

        # Persist permanent historical record in maintenance_records table
        history_note = (
            f"Maintenance completed and closed by {performed_by}. "
            f"Technician: {wo.assigned_to or 'N/A'}. "
            f"Work: {wo.work_performed or wo.issue}. "
            f"Cost: ₹{wo.total_cost or 0:,.2f}"
        )
        self.maintenance_record_repo.create_record(
            machine_id=wo.machine_id,
            failure_occurred=True if (wo.priority in ["CRITICAL", "HIGH"] or "Failure" in wo.issue) else False,
            failure_type="NORMAL",
            notes=history_note,
        )

        # Log audit ledger
        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="CLOSE_MAINTENANCE",
            performed_by=performed_by,
            notes=f"Maintenance closed by {performed_by}: {closure_notes} ({resolved_alerts_count} alerts resolved).",
            previous_status=prev_status,
            new_status=new_m_status,
        )

        return {
            "success": True,
            "message": f"Maintenance closed and approved by {performed_by}. Asset {wo.machine_id} restored to {new_m_status}.",
            "machine_id": wo.machine_id,
            "action_type": "CLOSE_MAINTENANCE",
            "new_status": "CLOSED",
            "timestamp": updated_wo.maintenance_closed_at,
        }

    def cancel_work_order(
        self,
        request_id: str,
        performed_by: str = "Maintenance Lead",
        cancellation_reason: str = "Cancelled by lead upon inspection.",
    ) -> Dict[str, Any]:
        """Cancel a work order with justification."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        if wo.status in ["COMPLETED", "CLOSED", "CANCELLED"]:
            raise ValueError(f"Work order '{request_id}' is already in terminal state '{wo.status}'.")

        logger.info(f"Cancelling work order '{request_id}' by '{performed_by}'")
        cancelled_wo = self.work_order_repo.cancel_work_order(
            request_id=request_id,
            performed_by=performed_by,
            cancellation_reason=cancellation_reason,
        )

        if wo.technician_id:
            self.technician_repo.update_status(wo.technician_id, "AVAILABLE")

        # Restore machine status if no other active orders exist
        other_active = self.work_order_repo.get_active_work_orders(wo.machine_id)
        machine = self.machine_repo.get_by_id(wo.machine_id)
        prev_status = machine.status if machine else "UNKNOWN"
        if machine and not other_active and machine.status in ["MAINTENANCE_REQUIRED", "INSPECTION_IN_PROGRESS", "MAINTENANCE_IN_PROGRESS"]:
            self.machine_repo.update_status(wo.machine_id, "OPERATIONAL")

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="CANCEL_MAINTENANCE",
            performed_by=performed_by,
            notes=f"Work Order {request_id} cancelled: {cancellation_reason}",
            previous_status=prev_status,
            new_status="OPERATIONAL" if not other_active else prev_status,
        )

        return {
            "success": True,
            "message": f"Work order '{request_id}' has been cancelled.",
            "machine_id": wo.machine_id,
            "action_type": "CANCEL_MAINTENANCE",
            "new_status": "CANCELLED",
            "timestamp": utc_now(),
        }

    def start_work_order(
        self,
        request_id: str,
        assigned_to: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Legacy / direct start transition (PENDING -> IN_PROGRESS)."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        updated_wo = self.work_order_repo.start_work_order(
            request_id=request_id,
            assigned_to=assigned_to,
            notes=notes,
        )

        machine = self.machine_repo.get_by_id(wo.machine_id)
        prev_status = machine.status if machine else "UNKNOWN"
        if machine:
            self.machine_repo.update_status(wo.machine_id, "INSPECTION_IN_PROGRESS")

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="START_MAINTENANCE",
            performed_by=assigned_to or "Technician",
            notes=notes,
            previous_status=prev_status,
            new_status="INSPECTION_IN_PROGRESS",
        )

        return {
            "success": True,
            "message": f"Work order '{request_id}' started by {assigned_to or 'Technician'}.",
            "machine_id": wo.machine_id,
            "action_type": "START_MAINTENANCE",
            "new_status": "IN_PROGRESS",
            "timestamp": updated_wo.repair_started_at or utc_now(),
        }

    def complete_work_order(
        self,
        request_id: str,
        performed_by: str = "Technician",
        resolution_notes: Optional[str] = None,
        action_taken: Optional[str] = None,
        parts_used: Optional[str] = None,
        labour_cost: Optional[float] = None,
        parts_cost: Optional[float] = None,
        other_cost: Optional[float] = None,
        resolve_linked_alerts: bool = True,
    ) -> Dict[str, Any]:
        """Legacy / direct completion transition (-> COMPLETED)."""
        wo = self.work_order_repo.get_by_request_id(request_id)
        if not wo:
            raise ValueError(f"Work order with ID '{request_id}' was not found.")

        full_resolution = f"{resolution_notes or ''} {action_taken or ''}".strip()
        updated_wo = self.work_order_repo.complete_repair(
            request_id=request_id,
            work_performed=action_taken or resolution_notes or "Maintenance performed.",
            parts_used=parts_used,
            repair_notes=resolution_notes,
            completion_notes=full_resolution,
            labour_cost=labour_cost,
            parts_cost=parts_cost,
            other_cost=other_cost,
        )

        if resolve_linked_alerts:
            if wo.alert_id:
                alert = self.alert_repo.get_by_alert_id(wo.alert_id)
                if alert and alert.status in ["OPEN", "ACTIVE", "ACKNOWLEDGED"]:
                    self.alert_repo.resolve_alert(
                        alert_id=wo.alert_id,
                        resolved_by=performed_by,
                        notes=f"Resolved via Work Order {request_id}. {resolution_notes or ''}",
                        resolution_action=action_taken or "MAINTENANCE_COMPLETED",
                    )
            else:
                self.alert_repo.resolve_alerts_for_machine(
                    machine_id=wo.machine_id,
                    performed_by=performed_by,
                    notes=f"Resolved via Work Order {request_id}. {resolution_notes or ''}",
                )

        other_active = self.work_order_repo.get_active_work_orders(wo.machine_id)
        machine = self.machine_repo.get_by_id(wo.machine_id)
        prev_status = machine.status if machine else "UNKNOWN"
        if machine and not other_active:
            self.machine_repo.update_status(wo.machine_id, "OPERATIONAL")

        self.maintenance_record_repo.create_record(
            machine_id=wo.machine_id,
            failure_occurred=True if (wo.priority in ["CRITICAL", "HIGH"] or "Failure" in wo.issue) else False,
            failure_type="NORMAL",
            notes=f"Completed by {performed_by}: {full_resolution}",
        )

        self.workflow_repo.log_action(
            machine_id=wo.machine_id,
            maintenance_id=request_id,
            action_type="COMPLETE_MAINTENANCE",
            performed_by=performed_by,
            notes=full_resolution,
            previous_status=prev_status,
            new_status="OPERATIONAL" if not other_active else prev_status,
        )

        return {
            "success": True,
            "message": f"Work order '{request_id}' completed.",
            "machine_id": wo.machine_id,
            "action_type": "COMPLETE_MAINTENANCE",
            "new_status": "COMPLETED",
            "timestamp": updated_wo.repair_completed_at or utc_now(),
        }

    def get_history(
        self,
        machine_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieve completed and closed maintenance work orders history."""
        records, total = self.work_order_repo.get_history(
            machine_id=machine_id,
            limit=limit,
            offset=offset,
        )
        return [self._serialize_work_order(r) for r in records], total

    # -------------------------------------------------------------------------

    # Dashboard & Queue Retrieval
    # -------------------------------------------------------------------------

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Assemble the Maintenance Lead Operations Board with real metrics:
        - Due (Predicted maintenance needs)
        - Pending (Unassigned or queued orders)
        - Assigned (Technician assigned / en route)
        - In Progress (Inspection & active repairs)
        - Completed (Finished / closed jobs)
        - Technicians (Registered technicians list)
        """
        due_items = self.get_predicted_recommendations()

        pending_orders, _ = self.work_order_repo.get_work_orders(status="PENDING", limit=100)
        assigned_orders, _ = self.work_order_repo.get_work_orders(status="ASSIGNED", limit=100)
        en_route_orders, _ = self.work_order_repo.get_work_orders(status="TECHNICIAN_ARRIVED", limit=100)
        in_prog_orders, _ = self.work_order_repo.get_work_orders(status="IN_PROGRESS", limit=100)
        completed_orders, _ = self.work_order_repo.get_work_orders(status="HISTORY", limit=50)

        technicians, _ = self.technician_repo.list_technicians(limit=100)

        summary = self.work_order_repo.get_summary_counts()
        summary["due_count"] = len(due_items)

        # Combine assigned + en_route for assigned section if needed
        all_assigned = [self._serialize_work_order(o) for o in (assigned_orders + en_route_orders)]

        return {
            "summary": summary,
            "due": due_items,
            "pending": [self._serialize_work_order(o) for o in pending_orders],
            "assigned": all_assigned,
            "in_progress": [self._serialize_work_order(o) for o in in_prog_orders],
            "completed": [self._serialize_work_order(o) for o in completed_orders],
            "technicians": [
                {
                    "id": t.id,
                    "technician_id": t.technician_id,
                    "technician_name": t.technician_name,
                    "specialization": t.specialization,
                    "company": t.company,
                    "phone": t.phone,
                    "email": t.email,
                    "experience_years": t.experience_years,
                    "certification": t.certification,
                    "status": t.status,
                    "created_at": t.created_at,
                }
                for t in technicians
            ],
        }

    def get_technician_work_queue(self, technician_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch active queue items assigned to technicians."""
        orders = self.work_order_repo.get_active_work_orders()
        if technician_id:
            orders = [o for o in orders if o.technician_id == technician_id]
        return [self._serialize_work_order(o) for o in orders]

    def get_history(
        self,
        machine_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch historical completed and cancelled work orders."""
        orders, total = self.work_order_repo.get_history(machine_id=machine_id, limit=limit, offset=offset)
        return [self._serialize_work_order(o) for o in orders], total

    def get_recent_repairs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch newest completed and closed repairs serialized with full machine, technician, and cost details."""
        orders = self.work_order_repo.get_recent_repairs(limit=limit)
        return [self._serialize_work_order(o) for o in orders]

    def get_cost_analytics(self) -> Dict[str, Any]:
        """Compute fleet repair cost analytics grouped by machine quality type."""
        return self.work_order_repo.get_cost_analytics()
