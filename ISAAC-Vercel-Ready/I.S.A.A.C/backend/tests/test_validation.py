"""
Unit tests for data validation logic and schema integrity.
"""

from pathlib import Path

import pytest

from backend.app.validation import (
    VALID_SENSOR_RANGES,
    ValidationIssue,
    validate_dataset_file,
    validate_record,
)

SAMPLE_VALID_ROW = {
    "udi": "1",
    "product_id": "M14860",
    "machine_type": "M",
    "air_temperature_k": "298.1",
    "process_temperature_k": "308.6",
    "rotational_speed_rpm": "1551",
    "torque_nm": "42.8",
    "tool_wear_min": "0",
    "machine_failure": "0",
    "twf": "0",
    "hdf": "0",
    "pwf": "0",
    "osf": "0",
    "rnf": "0",
}


def test_validate_record_valid_row():
    issues = validate_record(SAMPLE_VALID_ROW, row_idx=1)
    assert len(issues) == 0


def test_validate_record_missing_field():
    bad_row = dict(SAMPLE_VALID_ROW)
    del bad_row["torque_nm"]
    issues = validate_record(bad_row, row_idx=2)
    assert any(i.issue_type == "MISSING_COLUMN" and i.field_name == "torque_nm" for i in issues)


def test_validate_record_null_value():
    bad_row = dict(SAMPLE_VALID_ROW, air_temperature_k="")
    issues = validate_record(bad_row, row_idx=3)
    assert any(i.issue_type == "NULL_VALUE" and i.field_name == "air_temperature_k" for i in issues)


def test_validate_record_invalid_machine_type():
    bad_row = dict(SAMPLE_VALID_ROW, machine_type="Z")
    issues = validate_record(bad_row, row_idx=4)
    assert any(i.issue_type == "INVALID_VALUE" and i.field_name == "machine_type" for i in issues)


def test_validate_record_sensor_out_of_range():
    # Torque negative
    bad_row = dict(SAMPLE_VALID_ROW, torque_nm="-10.5")
    issues = validate_record(bad_row, row_idx=5)
    assert any(i.issue_type == "OUT_OF_RANGE" and i.field_name == "torque_nm" for i in issues)

    # RPM exceeding physical limit
    bad_row2 = dict(SAMPLE_VALID_ROW, rotational_speed_rpm="9999")
    issues2 = validate_record(bad_row2, row_idx=6)
    assert any(i.issue_type == "OUT_OF_RANGE" and i.field_name == "rotational_speed_rpm" for i in issues2)


def test_validate_record_temperature_inversion():
    # Process temperature lower than air temperature
    bad_row = dict(SAMPLE_VALID_ROW, air_temperature_k="305.0", process_temperature_k="299.0")
    issues = validate_record(bad_row, row_idx=7)
    assert any(i.issue_type == "LOGIC_ERROR" and i.field_name == "process_temperature_k" for i in issues)


def test_validate_record_invalid_target_label():
    bad_row = dict(SAMPLE_VALID_ROW, machine_failure="5")
    issues = validate_record(bad_row, row_idx=8)
    assert any(i.issue_type == "INVALID_TARGET" and i.field_name == "machine_failure" for i in issues)


def test_validate_dataset_sample_file():
    sample_path = Path(__file__).resolve().parent.parent.parent / "data" / "sample" / "sample_ai4i2020.csv"
    assert sample_path.exists(), "Sample dataset file must exist"
    report = validate_dataset_file(sample_path)
    assert report.is_valid
    assert report.total_records == 100
    assert report.valid_records == 100
    assert report.invalid_records == 0
    assert len(report.issues) == 0
    assert report.stats["failure_count"] > 0


def test_validate_dataset_cleaned_full_file():
    cleaned_path = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "ai4i2020_cleaned.csv"
    assert cleaned_path.exists(), "Cleaned dataset file must exist"
    report = validate_dataset_file(cleaned_path)
    assert report.is_valid
    assert report.total_records == 10000
    assert report.valid_records == 10000
    assert report.invalid_records == 0
    assert len(report.issues) == 0
    assert report.stats["failure_count"] == 339
    assert report.stats["machine_type_distribution"] == {"L": 6000, "M": 2997, "H": 1003}
