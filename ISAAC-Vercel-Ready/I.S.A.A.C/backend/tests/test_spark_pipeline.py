"""
Automated unit and integration tests for PySpark Big Data processing layer.
"""

import os
import sys
from pathlib import Path

# Ensure worker processes use sys.executable
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

import pytest
import pyspark.sql.functions as F
from pyspark.sql import SparkSession
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from bigdata.aggregations import (
    compute_machine_aggregations,
    compute_window_aggregations,
)
from bigdata.cleaning import clean_dataset
from bigdata.ingestion import get_dataset_schema, read_industrial_dataset
from bigdata.pipeline import run_bigdata_pipeline
from bigdata.spark_session import get_spark_session, stop_spark_session
from bigdata.transformations import apply_feature_transformations

SAMPLE_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sample" / "sample_ai4i2020.csv"


@pytest.fixture(scope="module")
def spark():
    """Create a shared SparkSession for test suite."""
    session = get_spark_session(app_name="ISAAC-PySpark-Tests", master="local[2]")
    yield session
    stop_spark_session(session)


def test_spark_session_initialization(spark: SparkSession):
    """Verify PySpark session is alive and responsive."""
    assert spark is not None
    assert spark.version is not None
    test_schema = StructType([
        StructField("id", IntegerType(), False),
        StructField("name", StringType(), False),
    ])
    test_df = spark.createDataFrame([(1, "test")], schema=test_schema)
    assert test_df.count() == 1


def test_spark_schema_ingestion(spark: SparkSession):
    """Verify strict schema loading on sample dataset."""
    assert SAMPLE_CSV_PATH.exists()
    schema = get_dataset_schema()
    df = read_industrial_dataset(spark, SAMPLE_CSV_PATH, schema=schema)

    assert df.count() == 100
    assert len(df.columns) == 14
    assert "air_temperature_k" in df.columns
    assert "torque_nm" in df.columns
    assert "machine_failure" in df.columns


def test_spark_cleaning_filters(spark: SparkSession):
    """Verify null handling, deduplication, and invalid range filtering."""
    raw_df = read_industrial_dataset(spark, SAMPLE_CSV_PATH)
    cleaned_df, metrics = clean_dataset(raw_df)

    assert metrics["final_clean_records"] == 100
    assert metrics["null_records_dropped"] == 0
    assert metrics["duplicate_records_dropped"] == 0
    assert metrics["invalid_records_dropped"] == 0
    assert "timestamp" in cleaned_df.columns


def test_spark_feature_transformations(spark: SparkSession):
    """Verify feature engineering transformations on telemetry."""
    raw_df = read_industrial_dataset(spark, SAMPLE_CSV_PATH)
    cleaned_df, _ = clean_dataset(raw_df)
    transformed_df = apply_feature_transformations(cleaned_df)

    # Check that new engineered columns exist
    expected_new_cols = [
        "temp_diff_k",
        "temp_ratio",
        "angular_velocity_rad_s",
        "mechanical_power_w",
        "mechanical_power_kw",
        "overstrain_product",
        "tool_wear_normalized",
        "is_high_tool_wear",
        "hdf_risk_flag",
        "pwf_risk_flag",
        "osf_risk_flag",
        "failure_mode_label",
    ]
    for col in expected_new_cols:
        assert col in transformed_df.columns, f"Engineered column '{col}' missing"

    # Verify physical calculations on first row
    first_row = transformed_df.filter(F.col("udi") == 1).first()
    assert first_row is not None
    # temp_diff = 308.6 - 298.1 = 10.5
    assert abs(first_row["temp_diff_k"] - 10.5) < 0.1
    # mechanical power = torque * (rpm * 2*pi / 60)
    expected_power = 42.8 * (1551.0 * (2.0 * 3.141592653589793 / 60.0))
    assert abs(first_row["mechanical_power_w"] - expected_power) < 2.0


def test_spark_aggregations(spark: SparkSession):
    """Verify machine-level grouped statistics and window features."""
    raw_df = read_industrial_dataset(spark, SAMPLE_CSV_PATH)
    cleaned_df, _ = clean_dataset(raw_df)
    transformed_df = apply_feature_transformations(cleaned_df)

    # Machine aggregates
    machine_aggs = compute_machine_aggregations(transformed_df)
    agg_rows = machine_aggs.collect()
    assert len(agg_rows) == 3  # L, M, H
    for r in agg_rows:
        assert r["machine_type"] in ["L", "M", "H"]
        assert r["total_records"] > 0
        assert r["avg_rpm"] > 1000.0

    # Window features
    windowed_df = compute_window_aggregations(transformed_df)
    assert "rolling_avg_torque_5" in windowed_df.columns
    assert "rolling_std_torque_5" in windowed_df.columns
    assert "torque_delta_lag1" in windowed_df.columns
    assert windowed_df.count() == 100


def test_spark_pipeline_end_to_end(spark: SparkSession, tmp_path):
    """Verify full pipeline execution on sample dataset using active spark session."""
    output_dir = tmp_path / "spark_test_output"
    report = run_bigdata_pipeline(
        input_path=SAMPLE_CSV_PATH,
        output_dir=output_dir,
        spark=spark,
        stop_session_on_finish=False,
    )

    assert report["input_records"] == 100
    assert report["output_records"] == 100
    assert report["duration_seconds"] >= 0
    assert (output_dir / "features.csv").exists()
    assert (output_dir / "machine_aggregates.csv").exists()
