"""
Database engine, session management, and schema initialization layer.
"""

from typing import Any, Generator
from pathlib import Path
import shutil

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import Base


def create_database_engine(settings: Settings) -> Engine:
    """Create a database engine from settings; credentials are never hardcoded."""
    connect_args: dict[str, Any] = {}
    if settings.mysql_url.startswith("mysql"):
        connect_args["connect_timeout"] = settings.mysql_connect_timeout
    elif settings.mysql_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Vercel's deployed filesystem is read-only outside /tmp. Seed the
        # writable SQLite database from the bundled demo database once per
        # warm function instance. External MySQL can still be used in production.
        sqlite_path = settings.mysql_url.replace("sqlite:///", "", 1)
        if sqlite_path.startswith("/tmp/"):
            target = Path(sqlite_path)
            if not target.exists():
                bundled = Path(__file__).resolve().parents[2] / "isaac.db"
                if bundled.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(bundled, target)

    return create_engine(
        settings.mysql_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def init_db(engine: Engine) -> None:
    """Safely create all tables and indexes if they do not exist and migrate existing tables."""
    Base.metadata.create_all(bind=engine)

    # Safe column migration for existing tables (SQLite & MySQL compatible)
    with engine.begin() as connection:
        # Check maintenance_work_orders columns
        try:
            inspector_work_orders = [
                row[1] if isinstance(row, (tuple, list)) else (row["name"] if hasattr(row, "__getitem__") else str(row))
                for row in connection.execute(text("PRAGMA table_info(maintenance_work_orders)")).fetchall()
            ]
        except Exception:
            inspector_work_orders = []

        if inspector_work_orders:
            columns_to_add = [
                ("technician_id", "VARCHAR(50)"),
                ("assigned_by", "VARCHAR(100)"),
                ("alert_created_at", "DATETIME"),
                ("maintenance_requested_at", "DATETIME"),
                ("technician_assigned_at", "DATETIME"),
                ("technician_arrived_at", "DATETIME"),
                ("inspection_started_at", "DATETIME"),
                ("repair_started_at", "DATETIME"),
                ("repair_completed_at", "DATETIME"),
                ("maintenance_closed_at", "DATETIME"),
                ("problem_description", "TEXT"),
                ("diagnosis", "TEXT"),
                ("work_performed", "TEXT"),
                ("root_cause", "TEXT"),
                ("parts_used", "TEXT"),
                ("repair_notes", "TEXT"),
                ("completion_notes", "TEXT"),
                ("estimated_cost", "FLOAT"),
                ("labour_cost", "FLOAT"),
                ("parts_cost", "FLOAT"),
                ("other_cost", "FLOAT"),
                ("total_cost", "FLOAT"),
            ]
            for col_name, col_type in columns_to_add:
                if col_name not in inspector_work_orders:
                    try:
                        connection.execute(text(f"ALTER TABLE maintenance_work_orders ADD COLUMN {col_name} {col_type}"))
                    except Exception:
                        pass

        # Check workflow_logs columns
        try:
            inspector_workflow = [
                row[1] if isinstance(row, (tuple, list)) else (row["name"] if hasattr(row, "__getitem__") else str(row))
                for row in connection.execute(text("PRAGMA table_info(workflow_logs)")).fetchall()
            ]
        except Exception:
            inspector_workflow = []

        if inspector_workflow and "maintenance_id" not in inspector_workflow:
            try:
                connection.execute(text("ALTER TABLE workflow_logs ADD COLUMN maintenance_id VARCHAR(50)"))
            except Exception:
                pass

        # Check SQLite check constraint on maintenance_work_orders (Phase 6 status lifecycle)
        if engine.dialect.name == "sqlite":
            try:
                raw_conn = connection.connection
                cur = raw_conn.cursor()
                schema_row = cur.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='maintenance_work_orders'"
                ).fetchone()
                if schema_row and schema_row[0] and "ASSIGNED" not in schema_row[0] and "ck_work_order_status" in schema_row[0]:
                    cur.execute("PRAGMA foreign_keys=OFF")
                    cur.execute("DROP TABLE IF EXISTS maintenance_work_orders_new")
                    cur.execute("UPDATE maintenance_work_orders SET maintenance_requested_at = created_at WHERE maintenance_requested_at IS NULL")
                    cols = [r[1] for r in cur.execute("PRAGMA table_info(maintenance_work_orders)").fetchall()]
                    cols_joined = ", ".join(cols)
                    new_sql = """
                    CREATE TABLE maintenance_work_orders_new (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        request_id VARCHAR(50) NOT NULL UNIQUE,
                        machine_id VARCHAR(50) NOT NULL,
                        alert_id VARCHAR(50),
                        technician_id VARCHAR(50),
                        issue TEXT NOT NULL,
                        risk VARCHAR(50) NOT NULL,
                        recommendation TEXT NOT NULL,
                        priority VARCHAR(20) NOT NULL,
                        status VARCHAR(30) NOT NULL,
                        work_type VARCHAR(50) NOT NULL,
                        requested_by VARCHAR(100) NOT NULL,
                        assigned_by VARCHAR(100),
                        assigned_to VARCHAR(100),
                        alert_created_at DATETIME,
                        maintenance_requested_at DATETIME NOT NULL,
                        technician_assigned_at DATETIME,
                        technician_arrived_at DATETIME,
                        inspection_started_at DATETIME,
                        repair_started_at DATETIME,
                        repair_completed_at DATETIME,
                        maintenance_closed_at DATETIME,
                        created_at DATETIME NOT NULL,
                        completed_at DATETIME,
                        scheduled_for DATETIME,
                        problem_description TEXT,
                        diagnosis TEXT,
                        work_performed TEXT,
                        root_cause TEXT,
                        parts_used TEXT,
                        repair_notes TEXT,
                        completion_notes TEXT,
                        estimated_cost FLOAT,
                        labour_cost FLOAT,
                        parts_cost FLOAT,
                        other_cost FLOAT,
                        total_cost FLOAT,
                        resolution_notes TEXT,
                        cancellation_reason TEXT,
                        CONSTRAINT ck_work_order_status CHECK (status IN ('PENDING', 'ASSIGNED', 'TECHNICIAN_ARRIVED', 'INSPECTION', 'REPAIR_IN_PROGRESS', 'IN_PROGRESS', 'COMPLETED', 'CLOSED', 'CANCELLED')),
                        CONSTRAINT ck_work_order_priority CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
                        FOREIGN KEY(machine_id) REFERENCES machines (machine_id) ON DELETE CASCADE,
                        FOREIGN KEY(alert_id) REFERENCES alerts (alert_id) ON DELETE SET NULL,
                        FOREIGN KEY(technician_id) REFERENCES technicians (technician_id) ON DELETE SET NULL
                    )
                    """
                    cur.execute(new_sql)
                    cur.execute(f"INSERT INTO maintenance_work_orders_new ({cols_joined}) SELECT {cols_joined} FROM maintenance_work_orders")
                    cur.execute("DROP TABLE maintenance_work_orders")
                    cur.execute("ALTER TABLE maintenance_work_orders_new RENAME TO maintenance_work_orders")
                    cur.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_work_orders_request_id ON maintenance_work_orders (request_id)")
                    cur.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_work_orders_machine_id ON maintenance_work_orders (machine_id)")
                    cur.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_work_orders_priority ON maintenance_work_orders (priority)")
                    cur.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_work_orders_status ON maintenance_work_orders (status)")
                    cur.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_work_orders_created_at ON maintenance_work_orders (created_at)")
                    cur.execute("PRAGMA foreign_keys=ON")
                    raw_conn.commit()
            except Exception:
                pass



def check_database_connectivity(engine: Engine) -> tuple[bool, str]:
    """Return an explicit connectivity result without raising to the API."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "connected"
    except SQLAlchemyError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a configured session factory bound to the given engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
