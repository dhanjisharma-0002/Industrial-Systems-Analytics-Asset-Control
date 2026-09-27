"""
Repository layer for MaintenanceWorkOrder entity and Phase 6 lifecycle state tracking.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import Alert, MaintenanceWorkOrder, Technician, utc_now


class WorkOrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_work_order(
        self,
        request_id: str,
        machine_id: str,
        issue: str,
        risk: str = "MEDIUM",
        recommendation: str = "",
        priority: str = "MEDIUM",
        status: str = "PENDING",
        work_type: str = "CONFIRMED_WORK_ORDER",
        requested_by: str = "Reliability Engineer",
        alert_id: Optional[str] = None,
        technician_id: Optional[str] = None,
        assigned_by: Optional[str] = None,
        assigned_to: Optional[str] = None,
        alert_created_at: Optional[datetime] = None,
        scheduled_for: Optional[datetime] = None,
        estimated_cost: Optional[float] = None,
    ) -> MaintenanceWorkOrder:
        """Create and persist a new formal maintenance work order."""
        now = utc_now()
        wo = MaintenanceWorkOrder(
            request_id=request_id,
            machine_id=machine_id,
            alert_id=alert_id,
            technician_id=technician_id,
            issue=issue,
            risk=risk,
            recommendation=recommendation,
            priority=priority.upper(),
            status=status.upper(),
            work_type=work_type,
            requested_by=requested_by,
            assigned_by=assigned_by,
            assigned_to=assigned_to,
            alert_created_at=alert_created_at,
            maintenance_requested_at=now,
            scheduled_for=scheduled_for,
            estimated_cost=estimated_cost,
            created_at=now,
        )
        self.db.add(wo)
        self.db.commit()
        self.db.refresh(wo)
        return wo

    def get_by_request_id(self, request_id: str) -> Optional[MaintenanceWorkOrder]:
        """Fetch a work order by unique request_id with joined technician and machine."""
        return (
            self.db.query(MaintenanceWorkOrder)
            .options(joinedload(MaintenanceWorkOrder.technician), joinedload(MaintenanceWorkOrder.machine))
            .filter(MaintenanceWorkOrder.request_id == request_id)
            .first()
        )

    def get_work_orders(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        machine_id: Optional[str] = None,
        technician_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[MaintenanceWorkOrder], int]:
        """Query work orders with flexible status, priority, and entity filtering."""
        query = self.db.query(MaintenanceWorkOrder).options(
            joinedload(MaintenanceWorkOrder.technician),
            joinedload(MaintenanceWorkOrder.machine),
        )

        if status and status.upper() != "ALL":
            st = status.upper()
            if st == "ACTIVE":
                query = query.filter(
                    MaintenanceWorkOrder.status.in_([
                        "PENDING",
                        "ASSIGNED",
                        "TECHNICIAN_ARRIVED",
                        "INSPECTION",
                        "REPAIR_IN_PROGRESS",
                        "IN_PROGRESS",
                    ])
                )
            elif st == "HISTORY":
                query = query.filter(MaintenanceWorkOrder.status.in_(["COMPLETED", "CLOSED", "CANCELLED"]))
            elif st == "IN_PROGRESS":
                query = query.filter(
                    MaintenanceWorkOrder.status.in_([
                        "INSPECTION",
                        "REPAIR_IN_PROGRESS",
                        "IN_PROGRESS",
                        "TECHNICIAN_ARRIVED",
                    ])
                )
            else:
                query = query.filter(MaintenanceWorkOrder.status == st)

        if priority and priority.upper() != "ALL":
            query = query.filter(MaintenanceWorkOrder.priority == priority.upper())

        if machine_id:
            query = query.filter(MaintenanceWorkOrder.machine_id == machine_id)

        if technician_id:
            query = query.filter(MaintenanceWorkOrder.technician_id == technician_id)

        total = query.count()
        records = (
            query.order_by(MaintenanceWorkOrder.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return records, total

    def get_active_work_orders(self, machine_id: Optional[str] = None) -> List[MaintenanceWorkOrder]:
        """Fetch all non-terminal work orders (PENDING, ASSIGNED, TECHNICIAN_ARRIVED, INSPECTION, REPAIR_IN_PROGRESS, IN_PROGRESS)."""
        active_statuses = [
            "PENDING",
            "ASSIGNED",
            "TECHNICIAN_ARRIVED",
            "INSPECTION",
            "REPAIR_IN_PROGRESS",
            "IN_PROGRESS",
        ]
        query = self.db.query(MaintenanceWorkOrder).filter(MaintenanceWorkOrder.status.in_(active_statuses))
        if machine_id:
            query = query.filter(MaintenanceWorkOrder.machine_id == machine_id)
        return query.order_by(MaintenanceWorkOrder.id.desc()).all()

    def get_history(
        self,
        machine_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[MaintenanceWorkOrder], int]:
        """Fetch historical completed, closed, and cancelled work orders."""
        query = self.db.query(MaintenanceWorkOrder).options(
            joinedload(MaintenanceWorkOrder.technician),
            joinedload(MaintenanceWorkOrder.machine),
        ).filter(
            MaintenanceWorkOrder.status.in_(["COMPLETED", "CLOSED", "CANCELLED"])
        )
        if machine_id:
            query = query.filter(MaintenanceWorkOrder.machine_id == machine_id)

        total = query.count()
        records = (
            query.order_by(
                func.coalesce(
                    MaintenanceWorkOrder.maintenance_closed_at,
                    MaintenanceWorkOrder.completed_at,
                    MaintenanceWorkOrder.created_at,
                ).desc(),
                MaintenanceWorkOrder.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return records, total

    def assign_technician(
        self,
        request_id: str,
        technician_id: str,
        technician_name: str,
        assigned_by: str = "Anu Sharma (Maintenance Lead)",
        priority: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order from PENDING to ASSIGNED."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        wo.status = "ASSIGNED"
        wo.technician_id = technician_id
        wo.assigned_to = technician_name
        wo.assigned_by = assigned_by
        wo.technician_assigned_at = utc_now()
        if priority:
            wo.priority = priority.upper()
        if notes:
            wo.resolution_notes = (wo.resolution_notes + "\n" + notes) if wo.resolution_notes else notes

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def mark_technician_arrived(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order from ASSIGNED to TECHNICIAN_ARRIVED."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        wo.status = "TECHNICIAN_ARRIVED"
        wo.technician_arrived_at = utc_now()
        if notes:
            wo.resolution_notes = (wo.resolution_notes + "\n" + notes) if wo.resolution_notes else notes

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def start_inspection(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order to INSPECTION."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        wo.status = "INSPECTION"
        wo.inspection_started_at = utc_now()
        if performed_by and not wo.assigned_to:
            wo.assigned_to = performed_by
        if notes:
            wo.resolution_notes = (wo.resolution_notes + "\n" + notes) if wo.resolution_notes else notes

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def start_work_order(
        self,
        request_id: str,
        assigned_to: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Direct transition to IN_PROGRESS."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        wo.status = "IN_PROGRESS"
        wo.repair_started_at = utc_now()
        if assigned_to:
            wo.assigned_to = assigned_to
        if notes:
            wo.resolution_notes = (wo.resolution_notes + "\n" + notes) if wo.resolution_notes else notes

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def start_repair(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        diagnosis: Optional[str] = None,
        problem_description: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order to REPAIR_IN_PROGRESS."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        wo.status = "REPAIR_IN_PROGRESS"
        wo.repair_started_at = utc_now()
        if diagnosis:
            wo.diagnosis = diagnosis
        if problem_description:
            wo.problem_description = problem_description
        if performed_by and not wo.assigned_to:
            wo.assigned_to = performed_by
        if notes:
            wo.resolution_notes = (wo.resolution_notes + "\n" + notes) if wo.resolution_notes else notes

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def complete_repair(
        self,
        request_id: str,
        performed_by: Optional[str] = None,
        diagnosis: Optional[str] = None,
        work_performed: Optional[str] = None,
        root_cause: Optional[str] = None,
        parts_used: Optional[str] = None,
        repair_notes: Optional[str] = None,
        completion_notes: Optional[str] = None,
        labour_cost: Optional[float] = None,
        parts_cost: Optional[float] = None,
        other_cost: Optional[float] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order from REPAIR_IN_PROGRESS to COMPLETED with real cost tracking."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        now = utc_now()
        wo.status = "COMPLETED"
        wo.repair_completed_at = now
        wo.completed_at = now

        if performed_by and not wo.assigned_to:
            wo.assigned_to = performed_by

        if diagnosis:
            wo.diagnosis = diagnosis
        if work_performed:
            wo.work_performed = work_performed
        if root_cause:
            wo.root_cause = root_cause
        if parts_used:
            wo.parts_used = parts_used
        if repair_notes:
            wo.repair_notes = repair_notes
        if completion_notes:
            wo.completion_notes = completion_notes

        # Cost calculation
        wo.labour_cost = round(labour_cost, 2) if labour_cost is not None else None
        wo.parts_cost = round(parts_cost, 2) if parts_cost is not None else None
        wo.other_cost = round(other_cost, 2) if other_cost is not None else None

        # Total Cost = Labour + Parts + Other
        costs = [c for c in [wo.labour_cost, wo.parts_cost, wo.other_cost] if c is not None]
        if costs:
            wo.total_cost = round(sum(costs), 2)

        combined_res = []
        if work_performed:
            combined_res.append(f"Work: {work_performed}")
        if diagnosis:
            combined_res.append(f"Diagnosis: {diagnosis}")
        if completion_notes:
            combined_res.append(f"Notes: {completion_notes}")
        if combined_res:
            wo.resolution_notes = " | ".join(combined_res)

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def close_maintenance(
        self,
        request_id: str,
        performed_by: str = "Anu Sharma (Maintenance Lead)",
        closure_notes: Optional[str] = None,
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order from COMPLETED to CLOSED."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        wo.status = "CLOSED"
        wo.maintenance_closed_at = utc_now()
        if closure_notes:
            wo.resolution_notes = (
                f"{wo.resolution_notes}\nClosure by {performed_by}: {closure_notes}"
                if wo.resolution_notes
                else f"Closed by {performed_by}: {closure_notes}"
            )

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def cancel_work_order(
        self,
        request_id: str,
        performed_by: str = "Maintenance Lead",
        cancellation_reason: str = "Cancelled by lead.",
    ) -> Optional[MaintenanceWorkOrder]:
        """Transition work order to CANCELLED with justification."""
        wo = self.get_by_request_id(request_id)
        if not wo:
            return None

        now = utc_now()
        wo.status = "CANCELLED"
        wo.cancellation_reason = f"Cancelled by {performed_by}: {cancellation_reason}"
        wo.completed_at = now
        wo.maintenance_closed_at = now

        self.db.commit()
        self.db.refresh(wo)
        return wo

    def get_summary_counts(self) -> Dict[str, Any]:
        """Aggregate work order counts across all Phase 6 operational states and compute total maintenance cost."""
        all_orders = self.db.query(MaintenanceWorkOrder).all()

        pending = sum(1 for o in all_orders if o.status == "PENDING")
        assigned = sum(1 for o in all_orders if o.status == "ASSIGNED")
        en_route = sum(1 for o in all_orders if o.status == "TECHNICIAN_ARRIVED")
        in_progress = sum(1 for o in all_orders if o.status in ["INSPECTION", "REPAIR_IN_PROGRESS", "IN_PROGRESS"])
        completed = sum(1 for o in all_orders if o.status == "COMPLETED")
        closed = sum(1 for o in all_orders if o.status == "CLOSED")
        cancelled = sum(1 for o in all_orders if o.status == "CANCELLED")

        crit_pri = sum(
            1 for o in all_orders
            if o.priority == "CRITICAL" and o.status in ["PENDING", "ASSIGNED", "TECHNICIAN_ARRIVED", "INSPECTION", "REPAIR_IN_PROGRESS", "IN_PROGRESS"]
        )
        high_pri = sum(
            1 for o in all_orders
            if o.priority == "HIGH" and o.status in ["PENDING", "ASSIGNED", "TECHNICIAN_ARRIVED", "INSPECTION", "REPAIR_IN_PROGRESS", "IN_PROGRESS"]
        )

        total_cost_sum = sum(o.total_cost for o in all_orders if o.total_cost is not None)
        total_labour_sum = sum(o.labour_cost for o in all_orders if o.labour_cost is not None)
        total_parts_sum = sum(o.parts_cost for o in all_orders if o.parts_cost is not None)
        total_other_sum = sum(o.other_cost for o in all_orders if o.other_cost is not None)
        completed_total = completed + closed
        avg_cost = round(total_cost_sum / completed_total, 2) if completed_total > 0 else 0.0

        return {
            "pending_count": pending,
            "assigned_count": assigned,
            "technicians_en_route_count": en_route,
            "in_progress_count": in_progress,
            "active_repairs_count": in_progress,
            "completed_count": completed_total,
            "closed_count": closed,
            "cancelled_count": cancelled,
            "critical_priority_count": crit_pri,
            "high_priority_count": high_pri,
            "total_confirmed_orders": len(all_orders),
            "total_maintenance_cost": round(total_cost_sum, 2),
            "total_labour_cost": round(total_labour_sum, 2),
            "total_parts_cost": round(total_parts_sum, 2),
            "total_other_cost": round(total_other_sum, 2),
            "average_repair_cost": avg_cost,
        }

    def get_recent_repairs(self, limit: int = 10) -> List[MaintenanceWorkOrder]:
        """Fetch newest completed or closed work orders with technician and machine details."""
        return (
            self.db.query(MaintenanceWorkOrder)
            .options(
                joinedload(MaintenanceWorkOrder.technician),
                joinedload(MaintenanceWorkOrder.machine),
            )
            .filter(MaintenanceWorkOrder.status.in_(["COMPLETED", "CLOSED"]))
            .order_by(
                func.coalesce(
                    MaintenanceWorkOrder.maintenance_closed_at,
                    MaintenanceWorkOrder.completed_at,
                    MaintenanceWorkOrder.created_at,
                ).desc(),
                MaintenanceWorkOrder.id.desc(),
            )
            .limit(limit)
            .all()
        )

    def get_cost_analytics(self) -> Dict[str, Any]:
        """Compute fleet repair cost analytics grouped by machine quality type."""
        completed_orders = (
            self.db.query(MaintenanceWorkOrder)
            .options(joinedload(MaintenanceWorkOrder.machine))
            .filter(MaintenanceWorkOrder.status.in_(["COMPLETED", "CLOSED"]))
            .all()
        )

        total_labour = sum(o.labour_cost for o in completed_orders if o.labour_cost is not None)
        total_parts = sum(o.parts_cost for o in completed_orders if o.parts_cost is not None)
        total_other = sum(o.other_cost for o in completed_orders if o.other_cost is not None)
        total_cost = sum(o.total_cost for o in completed_orders if o.total_cost is not None)
        count = len(completed_orders)
        avg_cost = round(total_cost / count, 2) if count > 0 else 0.0

        by_type: Dict[str, Dict[str, Any]] = {}
        for o in completed_orders:
            mtype = (o.machine.type if o.machine else None) or "M"
            if mtype not in by_type:
                by_type[mtype] = {
                    "machine_type": mtype,
                    "repair_count": 0,
                    "total_cost": 0.0,
                    "labour_cost": 0.0,
                    "parts_cost": 0.0,
                    "other_cost": 0.0,
                }
            by_type[mtype]["repair_count"] += 1
            by_type[mtype]["total_cost"] = round(by_type[mtype]["total_cost"] + (o.total_cost or 0.0), 2)
            by_type[mtype]["labour_cost"] = round(by_type[mtype]["labour_cost"] + (o.labour_cost or 0.0), 2)
            by_type[mtype]["parts_cost"] = round(by_type[mtype]["parts_cost"] + (o.parts_cost or 0.0), 2)
            by_type[mtype]["other_cost"] = round(by_type[mtype]["other_cost"] + (o.other_cost or 0.0), 2)

        return {
            "total_repairs": count,
            "total_maintenance_cost": round(total_cost, 2),
            "total_labour_cost": round(total_labour, 2),
            "total_parts_cost": round(total_parts, 2),
            "total_other_cost": round(total_other, 2),
            "average_repair_cost": avg_cost,
            "cost_by_machine_type": list(by_type.values()),
        }
