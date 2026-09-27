"""
Repository layer for Technician entity management (Phase 6).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from ..models import Technician, utc_now


class TechnicianRepository:
    def __init__(self, db: Session):
        self.db = db

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
        """Register and persist a new field maintenance technician."""
        if not technician_id:
            count = self.db.query(Technician).count() + 1
            technician_id = f"TECH-{count:03d}"

        existing = self.get_by_technician_id(technician_id)
        if existing:
            existing.technician_name = technician_name.strip()
            existing.specialization = specialization.strip()
            existing.company = company.strip() if company else None
            existing.phone = phone.strip() if phone else None
            existing.email = email.strip() if email else None
            existing.experience_years = experience_years or 0
            existing.certification = certification.strip() if certification else None
            existing.status = status.upper()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        tech = Technician(
            technician_id=technician_id,
            technician_name=technician_name.strip(),
            specialization=specialization.strip(),
            company=company.strip() if company else None,
            phone=phone.strip() if phone else None,
            email=email.strip() if email else None,
            experience_years=experience_years or 0,
            certification=certification.strip() if certification else None,
            status=status.upper(),
            created_at=utc_now(),
        )
        self.db.add(tech)
        self.db.commit()
        self.db.refresh(tech)
        return tech

    def get_by_technician_id(self, technician_id: str) -> Optional[Technician]:
        """Fetch technician by unique technician_id."""
        return (
            self.db.query(Technician)
            .filter(Technician.technician_id == technician_id)
            .first()
        )

    def get_by_id(self, id: int) -> Optional[Technician]:
        """Fetch technician by database primary key."""
        return self.db.query(Technician).filter(Technician.id == id).first()

    def list_technicians(
        self,
        specialization: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Technician], int]:
        """List technicians with optional specialization and availability filtering."""
        query = self.db.query(Technician)

        if specialization and specialization.upper() != "ALL":
            query = query.filter(Technician.specialization == specialization)

        if status and status.upper() != "ALL":
            query = query.filter(Technician.status == status.upper())

        total = query.count()
        records = (
            query.order_by(Technician.technician_name.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return records, total

    def update_status(self, technician_id: str, new_status: str) -> Optional[Technician]:
        """Update technician operational status (e.g., AVAILABLE, ASSIGNED, ON_SITE)."""
        tech = self.get_by_technician_id(technician_id)
        if not tech:
            return None
        tech.status = new_status.upper()
        self.db.commit()
        self.db.refresh(tech)
        return tech

    def count_total(self) -> int:
        return self.db.query(Technician).count()
