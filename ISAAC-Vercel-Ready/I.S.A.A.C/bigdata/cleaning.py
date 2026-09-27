"""
Data cleaning, validation, and normalization module for PySpark.
"""

from typing import Dict, Tuple

import pyspark.sql.functions as F
from pyspark.sql import DataFrame


def clean_dataset(df: DataFrame) -> Tuple[DataFrame, Dict[str, int]]:
    """
    Apply strict cleaning, deduplication, invalid-value filtering, and timestamp normalization.

    Returns:
        Tuple[DataFrame, Dict[str, int]]: Cleaned Spark DataFrame and cleaning metrics dictionary.
    """
    initial_count = df.count()

    # 1. Null handling: drop rows with null in any critical field
    required_cols = [
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
    df_no_nulls = df.dropna(subset=required_cols)
    nulls_dropped = initial_count - df_no_nulls.count()

    # 2. Duplicate handling: drop duplicate UDIs or Product IDs
    df_dedup = df_no_nulls.dropDuplicates(["udi"]).dropDuplicates(["product_id"])
    duplicates_dropped = df_no_nulls.count() - df_dedup.count()

    # 3. Invalid-value validation filters
    valid_type_cond = F.col("machine_type").isin(["L", "M", "H"])
    valid_air_temp = F.col("air_temperature_k").between(290.0, 315.0)
    valid_proc_temp = F.col("process_temperature_k").between(300.0, 325.0)
    valid_temp_diff = F.col("process_temperature_k") >= F.col("air_temperature_k")
    valid_speed = F.col("rotational_speed_rpm").between(1000.0, 3500.0)
    valid_torque = F.col("torque_nm").between(0.0, 100.0)
    valid_wear = F.col("tool_wear_min").between(0, 350)
    valid_failure = F.col("machine_failure").isin([0, 1])
    valid_twf = F.col("twf").isin([0, 1])
    valid_hdf = F.col("hdf").isin([0, 1])
    valid_pwf = F.col("pwf").isin([0, 1])
    valid_osf = F.col("osf").isin([0, 1])
    valid_rnf = F.col("rnf").isin([0, 1])

    validity_filter = (
        valid_type_cond
        & valid_air_temp
        & valid_proc_temp
        & valid_temp_diff
        & valid_speed
        & valid_torque
        & valid_wear
        & valid_failure
        & valid_twf
        & valid_hdf
        & valid_pwf
        & valid_osf
        & valid_rnf
    )

    df_valid = df_dedup.filter(validity_filter)
    invalid_dropped = df_dedup.count() - df_valid.count()

    # 4. Timestamp normalization
    # Base timestamp: 2024-01-01 00:00:00 UTC (1704067200 seconds epoch), 5-minute telemetry intervals based on UDI
    base_epoch = 1704067200
    df_cleaned = df_valid.withColumn(
        "timestamp",
        F.to_timestamp(F.from_unixtime(F.lit(base_epoch) + (F.col("udi") * 300))),
    )

    final_count = df_cleaned.count()

    metrics = {
        "initial_records": initial_count,
        "null_records_dropped": nulls_dropped,
        "duplicate_records_dropped": duplicates_dropped,
        "invalid_records_dropped": invalid_dropped,
        "final_clean_records": final_count,
    }

    return df_cleaned, metrics
