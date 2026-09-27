"""
Reproducible data ingestion script for ISAAC database foundation.

Loads validated sample or full predictive maintenance datasets into MySQL / SQLite database tables:
- machines
- sensor_data
- maintenance_records

Usage:
    python scripts/ingest_data.py --file data/sample/sample_ai4i2020.csv
    python scripts/ingest_data.py --file data/processed/ai4i2020_cleaned.csv
"""

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.database import create_database_engine, init_db
from backend.app.models import Base, Machine, MaintenanceRecord, SensorData
from backend.app.validation import validate_dataset_file


def determine_failure_type(row: Dict[str, str]) -> Optional[str]:
    """Derive descriptive failure type label based on active failure mode flags."""
    if row.get("machine_failure") != "1":
        return None

    modes = []
    if row.get("twf") == "1":
        modes.append("TWF")
    if row.get("hdf") == "1":
        modes.append("HDF")
    if row.get("pwf") == "1":
        modes.append("PWF")
    if row.get("osf") == "1":
        modes.append("OSF")
    if row.get("rnf") == "1":
        modes.append("RNF")

    return "+".join(modes) if modes else "FAILURE_UNSPECIFIED"


def ingest_dataset(file_path: Path, engine: Engine, batch_size: int = 500) -> Dict[str, int]:
    """Ingest CSV records into normalized relational tables."""
    print(f"1. Validating source dataset '{file_path.name}' before ingestion...")
    report = validate_dataset_file(file_path)
    if not report.is_valid:
        raise ValueError(f"Dataset failed validation with {len(report.issues)} issues. Ingestion aborted.")

    print(f"   Validation passed: {report.total_records} records verified clean.")

    print("2. Initializing database tables and indexes...")
    init_db(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session: Session = SessionLocal()

    base_time = datetime.now(timezone.utc) - timedelta(days=30)

    machines_created = 0
    sensors_created = 0
    maintenance_created = 0
    failures_recorded = 0

    existing_machine_ids = set(m[0] for m in session.query(Machine.machine_id).all())

    try:
        with open(file_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn.lstrip("\ufeff").strip() for fn in (reader.fieldnames or [])]
            reader.fieldnames = fieldnames

            rows_to_insert = list(reader)

        print(f"3. Ingesting {len(rows_to_insert)} records into relational schema...")

        # A. Register distinct machines first
        for row in rows_to_insert:
            m_id = row["product_id"].strip()
            if m_id not in existing_machine_ids:
                machine = Machine(
                    machine_id=m_id,
                    type=row["machine_type"].strip().upper(),
                    created_at=base_time,
                )
                session.add(machine)
                existing_machine_ids.add(m_id)
                machines_created += 1

        session.commit()
        print(f"   Registered {machines_created} new machines (Total unique: {len(existing_machine_ids)}).")

        # B. Ingest Sensor Telemetry and Maintenance Records in batches
        for idx, row in enumerate(rows_to_insert):
            m_id = row["product_id"].strip()
            udi_val = int(row["udi"])
            record_time = base_time + timedelta(minutes=udi_val * 5)

            sensor = SensorData(
                machine_id=m_id,
                udi=udi_val,
                air_temperature_k=float(row["air_temperature_k"]),
                process_temperature_k=float(row["process_temperature_k"]),
                rotational_speed_rpm=float(row["rotational_speed_rpm"]),
                torque_nm=float(row["torque_nm"]),
                tool_wear_min=int(row["tool_wear_min"]),
                recorded_at=record_time,
            )
            session.add(sensor)
            session.flush()  # Populates sensor.id for FK reference

            sensors_created += 1

            # Determine failure & maintenance record
            is_failure = row["machine_failure"] == "1"
            f_type = determine_failure_type(row)

            maint = MaintenanceRecord(
                machine_id=m_id,
                sensor_reading_id=sensor.id,
                failure_occurred=is_failure,
                failure_type=f_type,
                twf=row["twf"] == "1",
                hdf=row["hdf"] == "1",
                pwf=row["pwf"] == "1",
                osf=row["osf"] == "1",
                rnf=row["rnf"] == "1",
                notes=f"Telemetry event UDI={udi_val}, Type={row['machine_type']}" + (f" - Mode: {f_type}" if is_failure else ""),
                recorded_at=record_time,
            )
            session.add(maint)
            maintenance_created += 1
            if is_failure:
                failures_recorded += 1

            if (idx + 1) % batch_size == 0:
                session.commit()
                print(f"   Processed {idx + 1}/{len(rows_to_insert)} records...")

        session.commit()

    except Exception as exc:
        session.rollback()
        raise exc
    finally:
        session.close()

    return {
        "machines_created": machines_created,
        "total_machines": len(existing_machine_ids),
        "sensor_records_created": sensors_created,
        "maintenance_records_created": maintenance_created,
        "failures_recorded": failures_recorded,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest predictive maintenance dataset into database.")
    parser.add_argument(
        "--file",
        type=str,
        default="data/sample/sample_ai4i2020.csv",
        help="Path to CSV dataset to ingest (defaults to verified sample).",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Custom SQLAlchemy database URL (e.g. sqlite:///isaac_local.db or mysql+pymysql://...).",
    )
    args = parser.parse_args()

    target_file = (PROJECT_ROOT / args.file).resolve() if not Path(args.file).is_absolute() else Path(args.file)
    if not target_file.exists():
        print(f"ERROR: Dataset file '{target_file}' not found.", file=sys.stderr)
        sys.exit(1)

    if args.db_url:
        print(f"Using custom database URL: {args.db_url}")
        connect_args = {"check_same_thread": False} if args.db_url.startswith("sqlite") else {}
        engine = create_engine(args.db_url, connect_args=connect_args)
    else:
        settings = get_settings()
        print(f"Connecting using application settings ({settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database})...")
        engine = create_database_engine(settings)

    try:
        metrics = ingest_dataset(target_file, engine)
        print("\n" + "=" * 60)
        print("INGESTION COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"Target File:                  {target_file.name}")
        print(f"New Machines Created:         {metrics['machines_created']}")
        print(f"Total Machines Registered:    {metrics['total_machines']}")
        print(f"Sensor Records Ingested:      {metrics['sensor_records_created']}")
        print(f"Maintenance Records Ingested: {metrics['maintenance_records_created']}")
        print(f"Failures Logged:              {metrics['failures_recorded']}")
    except Exception as exc:
        print(f"\nINGESTION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
