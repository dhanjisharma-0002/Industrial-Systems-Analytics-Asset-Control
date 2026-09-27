"""
Data validation module for ISAAC predictive maintenance datasets.

Validates:
- Column names & required fields
- Data types & parsing
- Null / missing values
- Duplicate identifiers
- Physical sensor ranges & invariants
- Target failure labels and multi-mode flags
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ValidationIssue:
    row_number: Optional[int]
    field_name: str
    issue_type: str  # e.g. "MISSING_COLUMN", "NULL_VALUE", "OUT_OF_RANGE", "INVALID_TYPE", "DUPLICATE", "LOGIC_ERROR"
    message: str
    value: Any = None


@dataclass
class ValidationReport:
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0 and self.total_records > 0


# Physical boundary definitions for industrial CNC/machining equipment
VALID_SENSOR_RANGES = {
    "air_temperature_k": (290.0, 315.0),       # Ambient room temperature in Kelvin (17°C to 42°C)
    "process_temperature_k": (300.0, 325.0),   # Process temperature in Kelvin (27°C to 52°C)
    "rotational_speed_rpm": (1000.0, 3500.0),  # Spindle rotational speed in RPM
    "torque_nm": (0.0, 100.0),                 # Applied torque in Nm
    "tool_wear_min": (0, 350),                 # Tool wear duration in minutes
}

VALID_MACHINE_TYPES = {"L", "M", "H"}
REQUIRED_FIELDS = [
    "udi",
    "product_id",
    "machine_type",
    "air_temperature_k",
    "process_temperature_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
    "machine_failure",
    "twf",
    "hdf",
    "pwf",
    "osf",
    "rnf",
]


def validate_record(row: Dict[str, Any], row_idx: Optional[int] = None) -> List[ValidationIssue]:
    """Validate a single dictionary record against schema and physical domain rules."""
    issues: List[ValidationIssue] = []

    # 1. Missing / Null checks
    for req_field in REQUIRED_FIELDS:
        if req_field not in row:
            issues.append(
                ValidationIssue(
                    row_number=row_idx,
                    field_name=req_field,
                    issue_type="MISSING_COLUMN",
                    message=f"Missing required field '{req_field}'",
                )
            )
        elif row[req_field] is None or str(row[req_field]).strip() == "":
            issues.append(
                ValidationIssue(
                    row_number=row_idx,
                    field_name=req_field,
                    issue_type="NULL_VALUE",
                    message=f"Field '{req_field}' contains empty/null value",
                    value=row[req_field],
                )
            )

    if issues:
        # Stop early if required fields are completely missing
        return issues

    # 2. Identifier validation
    try:
        udi_val = int(row["udi"])
        if udi_val <= 0:
            issues.append(
                ValidationIssue(
                    row_number=row_idx,
                    field_name="udi",
                    issue_type="OUT_OF_RANGE",
                    message="UDI must be a positive integer",
                    value=udi_val,
                )
            )
    except (ValueError, TypeError):
        issues.append(
            ValidationIssue(
                row_number=row_idx,
                field_name="udi",
                issue_type="INVALID_TYPE",
                message=f"UDI must be integer convertible, got '{row['udi']}'",
                value=row["udi"],
            )
        )

    product_id_str = str(row["product_id"]).strip()
    if len(product_id_str) < 2:
        issues.append(
            ValidationIssue(
                row_number=row_idx,
                field_name="product_id",
                issue_type="INVALID_VALUE",
                message="Product ID is malformed",
                value=product_id_str,
            )
        )

    machine_type = str(row["machine_type"]).strip().upper()
    if machine_type not in VALID_MACHINE_TYPES:
        issues.append(
            ValidationIssue(
                row_number=row_idx,
                field_name="machine_type",
                issue_type="INVALID_VALUE",
                message=f"Machine type '{machine_type}' not in valid set {VALID_MACHINE_TYPES}",
                value=machine_type,
            )
        )

    # 3. Numeric conversions and range validation
    parsed_sensors: Dict[str, float] = {}
    for num_field, (min_val, max_val) in VALID_SENSOR_RANGES.items():
        try:
            val = float(row[num_field])
            parsed_sensors[num_field] = val
            if not (min_val <= val <= max_val):
                issues.append(
                    ValidationIssue(
                        row_number=row_idx,
                        field_name=num_field,
                        issue_type="OUT_OF_RANGE",
                        message=f"{num_field} value {val} is outside physical range [{min_val}, {max_val}]",
                        value=val,
                    )
                )
        except (ValueError, TypeError):
            issues.append(
                ValidationIssue(
                    row_number=row_idx,
                    field_name=num_field,
                    issue_type="INVALID_TYPE",
                    message=f"{num_field} must be numeric, got '{row[num_field]}'",
                    value=row[num_field],
                )
            )

    # Physical thermal invariant: process temperature must be >= air temperature
    if "air_temperature_k" in parsed_sensors and "process_temperature_k" in parsed_sensors:
        if parsed_sensors["process_temperature_k"] < parsed_sensors["air_temperature_k"]:
            issues.append(
                ValidationIssue(
                    row_number=row_idx,
                    field_name="process_temperature_k",
                    issue_type="LOGIC_ERROR",
                    message="Process temperature cannot be lower than ambient air temperature",
                    value=parsed_sensors["process_temperature_k"],
                )
            )

    # 4. Target failure label validation
    for target_field in ["machine_failure", "twf", "hdf", "pwf", "osf", "rnf"]:
        try:
            val = int(row[target_field])
            if val not in (0, 1):
                issues.append(
                    ValidationIssue(
                        row_number=row_idx,
                        field_name=target_field,
                        issue_type="INVALID_TARGET",
                        message=f"{target_field} must be binary 0 or 1, got {val}",
                        value=val,
                    )
                )
        except (ValueError, TypeError):
            issues.append(
                ValidationIssue(
                    row_number=row_idx,
                    field_name=target_field,
                    issue_type="INVALID_TYPE",
                    message=f"{target_field} must be binary convertible, got '{row[target_field]}'",
                    value=row[target_field],
                )
            )

    return issues


def validate_dataset_file(file_path: Path) -> ValidationReport:
    """Read a CSV dataset file, validate all rows and constraints, and return a ValidationReport."""
    report = ValidationReport()
    seen_udis: Set[int] = set()
    seen_product_ids: Set[str] = set()

    failure_count = 0
    type_counts: Dict[str, int] = {}
    failure_mode_counts: Dict[str, int] = {"twf": 0, "hdf": 0, "pwf": 0, "osf": 0, "rnf": 0}

    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn.lstrip("\ufeff").strip() for fn in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames

        # Check required columns
        for req_col in REQUIRED_FIELDS:
            if req_col not in fieldnames:
                report.issues.append(
                    ValidationIssue(
                        row_number=0,
                        field_name=req_col,
                        issue_type="MISSING_COLUMN",
                        message=f"Required column '{req_col}' is missing from CSV header",
                    )
                )

        if report.issues:
            return report

        for row_idx, row in enumerate(reader, start=1):
            report.total_records += 1
            row_issues = validate_record(row, row_idx=row_idx)

            # Check duplicate UDI
            try:
                udi_val = int(row["udi"])
                if udi_val in seen_udis:
                    row_issues.append(
                        ValidationIssue(
                            row_number=row_idx,
                            field_name="udi",
                            issue_type="DUPLICATE",
                            message=f"Duplicate UDI value detected: {udi_val}",
                            value=udi_val,
                        )
                    )
                else:
                    seen_udis.add(udi_val)
            except (ValueError, TypeError):
                pass

            # Check duplicate Product ID
            pid = str(row.get("product_id", "")).strip()
            if pid:
                if pid in seen_product_ids:
                    row_issues.append(
                        ValidationIssue(
                            row_number=row_idx,
                            field_name="product_id",
                            issue_type="DUPLICATE",
                            message=f"Duplicate Product ID detected: {pid}",
                            value=pid,
                        )
                    )
                else:
                    seen_product_ids.add(pid)

            if row_issues:
                report.invalid_records += 1
                report.issues.extend(row_issues)
            else:
                report.valid_records += 1

                # Track valid stats
                mtype = row.get("machine_type", "")
                type_counts[mtype] = type_counts.get(mtype, 0) + 1

                if row.get("machine_failure") == "1":
                    failure_count += 1

                for fm in ["twf", "hdf", "pwf", "osf", "rnf"]:
                    if row.get(fm) == "1":
                        failure_mode_counts[fm] += 1

    report.stats = {
        "total_records": report.total_records,
        "valid_records": report.valid_records,
        "invalid_records": report.invalid_records,
        "machine_type_distribution": type_counts,
        "failure_count": failure_count,
        "failure_rate_percent": round((failure_count / report.total_records) * 100, 2) if report.total_records else 0,
        "failure_mode_counts": failure_mode_counts,
    }

    return report
