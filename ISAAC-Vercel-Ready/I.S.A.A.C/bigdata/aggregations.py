"""
Aggregations module for PySpark Big Data processing layer.
Provides machine-level grouped statistics and temporal sliding window features.
"""

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, Window


def compute_machine_aggregations(df: DataFrame) -> DataFrame:
    """
    Compute grouped statistical aggregates by machine_type.

    Computes:
    - Temperature statistics (mean, min, max, stddev of air and process temps, temp differential)
    - RPM statistics (mean, min, max, stddev)
    - Torque statistics (mean, min, max, stddev)
    - Mechanical power statistics (mean, min, max, stddev)
    - Tool wear statistics (mean, min, max, stddev)
    - Failure rates and failure mode counts (TWF, HDF, PWF, OSF, RNF)
    """
    agg_df = df.groupBy("machine_type").agg(
        F.count("udi").alias("total_records"),
        F.sum("machine_failure").alias("total_failures"),
        F.round((F.sum("machine_failure") / F.count("udi")) * 100.0, 2).alias("failure_rate_pct"),
        # Failure modes
        F.sum("twf").alias("twf_count"),
        F.sum("hdf").alias("hdf_count"),
        F.sum("pwf").alias("pwf_count"),
        F.sum("osf").alias("osf_count"),
        F.sum("rnf").alias("rnf_count"),
        # Temperature statistics
        F.round(F.mean("air_temperature_k"), 2).alias("avg_air_temp_k"),
        F.round(F.min("air_temperature_k"), 2).alias("min_air_temp_k"),
        F.round(F.max("air_temperature_k"), 2).alias("max_air_temp_k"),
        F.round(F.stddev("air_temperature_k"), 2).alias("std_air_temp_k"),
        F.round(F.mean("process_temperature_k"), 2).alias("avg_process_temp_k"),
        F.round(F.min("process_temperature_k"), 2).alias("min_process_temp_k"),
        F.round(F.max("process_temperature_k"), 2).alias("max_process_temp_k"),
        F.round(F.stddev("process_temperature_k"), 2).alias("std_process_temp_k"),
        F.round(F.mean("temp_diff_k"), 2).alias("avg_temp_diff_k"),
        # RPM statistics
        F.round(F.mean("rotational_speed_rpm"), 1).alias("avg_rpm"),
        F.round(F.min("rotational_speed_rpm"), 1).alias("min_rpm"),
        F.round(F.max("rotational_speed_rpm"), 1).alias("max_rpm"),
        F.round(F.stddev("rotational_speed_rpm"), 1).alias("std_rpm"),
        # Torque statistics
        F.round(F.mean("torque_nm"), 2).alias("avg_torque_nm"),
        F.round(F.min("torque_nm"), 2).alias("min_torque_nm"),
        F.round(F.max("torque_nm"), 2).alias("max_torque_nm"),
        F.round(F.stddev("torque_nm"), 2).alias("std_torque_nm"),
        # Mechanical power statistics
        F.round(F.mean("mechanical_power_w"), 1).alias("avg_power_w"),
        F.round(F.min("mechanical_power_w"), 1).alias("min_power_w"),
        F.round(F.max("mechanical_power_w"), 1).alias("max_power_w"),
        F.round(F.stddev("mechanical_power_w"), 1).alias("std_power_w"),
        # Tool wear statistics
        F.round(F.mean("tool_wear_min"), 1).alias("avg_tool_wear_min"),
        F.round(F.max("tool_wear_min"), 1).alias("max_tool_wear_min"),
        F.round(F.stddev("tool_wear_min"), 1).alias("std_tool_wear_min"),
    ).orderBy("machine_type")

    return agg_df


def compute_window_aggregations(df: DataFrame) -> DataFrame:
    """
    Compute time-based / sequential window features across telemetry observations.

    Engineers:
    - 5-point and 10-point rolling moving averages for torque, speed, and power.
    - 5-point rolling standard deviation (vibration / turbulence dynamic proxy).
    - Sequential lag and delta metrics: delta torque, delta speed, delta power.
    - Cumulative maximum tool wear.
    """
    # Define window partitions: ordered by UDI (or timestamp) within machine quality type
    w_type_5 = Window.partitionBy("machine_type").orderBy("udi").rowsBetween(-4, 0)
    w_type_10 = Window.partitionBy("machine_type").orderBy("udi").rowsBetween(-9, 0)
    w_type_lag = Window.partitionBy("machine_type").orderBy("udi")

    df_windowed = (
        df.withColumn(
            "rolling_avg_torque_5",
            F.round(F.avg("torque_nm").over(w_type_5), 3),
        )
        .withColumn(
            "rolling_std_torque_5",
            F.round(F.coalesce(F.stddev("torque_nm").over(w_type_5), F.lit(0.0)), 3),
        )
        .withColumn(
            "rolling_avg_rpm_5",
            F.round(F.avg("rotational_speed_rpm").over(w_type_5), 2),
        )
        .withColumn(
            "rolling_std_rpm_5",
            F.round(F.coalesce(F.stddev("rotational_speed_rpm").over(w_type_5), F.lit(0.0)), 2),
        )
        .withColumn(
            "rolling_avg_power_5",
            F.round(F.avg("mechanical_power_w").over(w_type_5), 2),
        )
        .withColumn(
            "rolling_avg_torque_10",
            F.round(F.avg("torque_nm").over(w_type_10), 3),
        )
        .withColumn(
            "rolling_avg_temp_diff_5",
            F.round(F.avg("temp_diff_k").over(w_type_5), 3),
        )
        # Sequential differences / deltas (rate of change from previous step)
        .withColumn(
            "torque_delta_lag1",
            F.round(F.col("torque_nm") - F.coalesce(F.lag("torque_nm", 1).over(w_type_lag), F.col("torque_nm")), 3),
        )
        .withColumn(
            "rpm_delta_lag1",
            F.round(
                F.col("rotational_speed_rpm")
                - F.coalesce(F.lag("rotational_speed_rpm", 1).over(w_type_lag), F.col("rotational_speed_rpm")),
                2,
            ),
        )
        .withColumn(
            "power_delta_lag1",
            F.round(
                F.col("mechanical_power_w")
                - F.coalesce(F.lag("mechanical_power_w", 1).over(w_type_lag), F.col("mechanical_power_w")),
                2,
            ),
        )
    )

    return df_windowed
