"""
End-to-end Big Data ETL and feature engineering pipeline for ISAAC.
Executes scalable data ingestion, cleaning, transformation, and aggregation with PySpark.

Usage:
    python bigdata/pipeline.py
    python bigdata/pipeline.py --input data/sample/sample_ai4i2020.csv --output data/processed/spark_sample_features
"""

import argparse
import csv
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure PySpark workers use the active Python interpreter on Windows
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

# Configure HADOOP_HOME for Windows support
HADOOP_HOME = PROJECT_ROOT / "hadoop"
if HADOOP_HOME.exists():
    os.environ["HADOOP_HOME"] = str(HADOOP_HOME)
    os.environ["PATH"] = f"{HADOOP_HOME / 'bin'};{os.environ.get('PATH', '')}"

from bigdata.aggregations import (
    compute_machine_aggregations,
    compute_window_aggregations,
)
from bigdata.cleaning import clean_dataset
from bigdata.ingestion import read_industrial_dataset
from bigdata.spark_session import get_spark_session, stop_spark_session
from bigdata.transformations import apply_feature_transformations
from pyspark.sql import SparkSession


def display_path(path: Path) -> str:
    """Safely format path for logs whether inside or outside project root."""
    try:
        if path.is_relative_to(PROJECT_ROOT):
            return str(path.relative_to(PROJECT_ROOT))
    except Exception:
        pass
    return str(path)


def save_spark_df_to_csv(df, target_csv_path: Path) -> None:
    """Save a Spark DataFrame directly to a single standard CSV file."""
    target_csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = target_csv_path.parent / f"_temp_{target_csv_path.stem}"

    try:
        # Attempt native Spark coalesce write
        df.coalesce(1).write.mode("overwrite").option("header", "true").csv(str(temp_dir))
        part_files = list(temp_dir.glob("part-*.csv"))
        if part_files:
            if target_csv_path.exists():
                target_csv_path.unlink()
            shutil.move(str(part_files[0]), str(target_csv_path))
    except Exception:
        # Resilient fallback across all environments
        fieldnames = df.columns
        with open(target_csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fieldnames)
            for row in df.toLocalIterator():
                writer.writerow([row[c] for c in fieldnames])
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def run_bigdata_pipeline(
    input_path: Path,
    output_dir: Path,
    spark: Optional[SparkSession] = None,
    spark_app_name: str = "ISAAC-BigData-Pipeline",
    stop_session_on_finish: bool = True,
) -> Dict[str, Any]:
    """
    Execute full PySpark ETL, validation, feature engineering, and aggregation pipeline.
    """
    start_wall_time = datetime.now(timezone.utc)
    t0 = time.time()

    print("=" * 70)
    print("ISAAC BIG DATA PIPELINE (APACHE SPARK / PYSPARK)")
    print("=" * 70)
    print(f"Start Time:     {start_wall_time.isoformat()}")
    print(f"Input Dataset:  {display_path(input_path)}")
    print(f"Output Target:  {display_path(output_dir)}")
    print("-" * 70)

    should_stop = False
    if spark is None:
        spark = get_spark_session(app_name=spark_app_name)
        should_stop = stop_session_on_finish

    try:
        # Step 1: Ingestion with strict StructType schema
        print("1. Ingesting dataset with explicit StructType schema...")
        raw_df = read_industrial_dataset(spark, input_path)
        input_count = raw_df.count()
        print(f"   [OK] Ingested {input_count} raw records.")

        # Step 2: Cleaning, null handling, duplicate removal, invalid-value filtering
        print("2. Performing data cleaning, null handling, and domain validation...")
        cleaned_df, clean_metrics = clean_dataset(raw_df)
        print(f"   [OK] Clean records: {clean_metrics['final_clean_records']} "
              f"(Nulls dropped: {clean_metrics['null_records_dropped']}, "
              f"Duplicates dropped: {clean_metrics['duplicate_records_dropped']}, "
              f"Invalid dropped: {clean_metrics['invalid_records_dropped']})")

        # Step 3: Predictive maintenance feature engineering
        print("3. Applying thermodynamic, kinematic, and risk transformations...")
        transformed_df = apply_feature_transformations(cleaned_df)
        features_count = len(transformed_df.columns)
        print(f"   [OK] Transformed dataset schema: {features_count} columns.")

        # Step 4: Time-based / sequential window aggregations
        print("4. Computing rolling window features (moving averages, stddev, deltas)...")
        windowed_df = compute_window_aggregations(transformed_df)
        total_feature_cols = len(windowed_df.columns)
        print(f"   [OK] Window feature engineering complete ({total_feature_cols} columns total).")

        # Step 5: Machine-level grouped aggregations
        print("5. Computing machine-type summary statistics & failure distributions...")
        machine_agg_df = compute_machine_aggregations(windowed_df)
        machine_aggregates = [row.asDict() for row in machine_agg_df.collect()]

        # Step 6: Save output
        print("6. Persisting processed feature dataset and machine aggregates...")
        output_dir.mkdir(parents=True, exist_ok=True)

        features_output_csv = output_dir / "features.csv"
        save_spark_df_to_csv(windowed_df, features_output_csv)
        print(f"   [OK] Saved features to {display_path(features_output_csv)}")

        agg_output_file = output_dir / "machine_aggregates.csv"
        save_spark_df_to_csv(machine_agg_df, agg_output_file)
        print(f"   [OK] Saved machine aggregates to {display_path(agg_output_file)}")

        output_count = windowed_df.count()

    finally:
        if should_stop:
            stop_spark_session(spark)

    t1 = time.time()
    end_wall_time = datetime.now(timezone.utc)
    duration_sec = round(t1 - t0, 2)

    pipeline_report = {
        "start_time": start_wall_time.isoformat(),
        "end_time": end_wall_time.isoformat(),
        "duration_seconds": duration_sec,
        "input_records": input_count,
        "output_records": output_count,
        "cleaning_metrics": clean_metrics,
        "total_columns": total_feature_cols,
        "machine_aggregates": machine_aggregates,
    }

    print("-" * 70)
    print("PIPELINE EXECUTION SUMMARY")
    print("-" * 70)
    print(f"Processing Status:    SUCCESS")
    print(f"Processing Start:     {start_wall_time.isoformat()}")
    print(f"Processing End:       {end_wall_time.isoformat()}")
    print(f"Elapsed Time:         {duration_sec} s")
    print(f"Input Records:        {input_count}")
    print(f"Output Records:       {output_count}")
    print(f"Dropped / Failed:     {input_count - output_count}")
    print(f"Engineered Features:  {total_feature_cols} columns")
    print("\nMachine Aggregations Breakdown:")
    for agg in machine_aggregates:
        print(f"  Type {agg['machine_type']}: {agg['total_records']} machines | "
              f"{agg['total_failures']} failures ({agg['failure_rate_pct']}%) | "
              f"Avg Power: {agg['avg_power_w']} W | Avg RPM: {agg['avg_rpm']} | "
              f"Failures breakdown: TWF={agg['twf_count']}, HDF={agg['hdf_count']}, PWF={agg['pwf_count']}, OSF={agg['osf_count']}, RNF={agg['rnf_count']}")
    print("=" * 70)

    return pipeline_report


def main():
    parser = argparse.ArgumentParser(description="Run ISAAC PySpark Big Data Processing Pipeline.")
    parser.add_argument(
        "--input",
        type=str,
        default="data/processed/ai4i2020_cleaned.csv",
        help="Input CSV dataset file path.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/processed/spark_features",
        help="Output directory for generated features and aggregates.",
    )
    args = parser.parse_args()

    input_path = (PROJECT_ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    output_dir = (PROJECT_ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input dataset file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        run_bigdata_pipeline(input_path, output_dir)
    except Exception as exc:
        print(f"\nFATAL: Pipeline execution failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
