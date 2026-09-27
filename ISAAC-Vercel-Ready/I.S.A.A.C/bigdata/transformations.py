"""
Feature transformations and engineering module for PySpark Big Data layer.
Computes thermodynamic, kinematic, tool wear, and failure mode features from industrial sensor telemetry.
"""

import math
import pyspark.sql.functions as F
from pyspark.sql import DataFrame

PI_VAL = math.pi


def apply_feature_transformations(df: DataFrame) -> DataFrame:
    """
    Apply predictive maintenance feature engineering on industrial telemetry.

    Engineers:
    - Temperature features: delta T, ratio, thermal gradients.
    - Mechanical / Kinematic features: angular velocity, mechanical power (Watts/kW).
    - Tool wear & strain features: overstrain indicator (wear * torque), normalized tool life.
    - Physical failure risk flags derived from domain physics (HDF, PWF, OSF).
    - Preserves all binary target flags and derives descriptive composite failure mode labels.
    """
    # 1. Temperature features
    df_transformed = df.withColumn(
        "temp_diff_k",
        F.round(F.col("process_temperature_k") - F.col("air_temperature_k"), 4),
    ).withColumn(
        "temp_ratio",
        F.round(F.col("process_temperature_k") / F.col("air_temperature_k"), 6),
    )

    # 2. Kinematic & Mechanical Power features
    # Angular velocity: omega = RPM * 2*pi / 60
    df_transformed = df_transformed.withColumn(
        "angular_velocity_rad_s",
        F.round(F.col("rotational_speed_rpm") * (2.0 * PI_VAL / 60.0), 4),
    ).withColumn(
        "mechanical_power_w",
        F.round(F.col("torque_nm") * (F.col("rotational_speed_rpm") * (2.0 * PI_VAL / 60.0)), 2),
    ).withColumn(
        "mechanical_power_kw",
        F.round(F.col("mechanical_power_w") / 1000.0, 4),
    ).withColumn(
        "torque_to_speed_ratio",
        F.round(F.col("torque_nm") / F.col("rotational_speed_rpm"), 6),
    )

    # 3. Tool wear and overstrain features
    # Overstrain product = tool_wear_min * torque_nm
    df_transformed = df_transformed.withColumn(
        "overstrain_product",
        F.round(F.col("tool_wear_min") * F.col("torque_nm"), 2),
    ).withColumn(
        "tool_wear_normalized",
        F.round(F.col("tool_wear_min") / 240.0, 4),
    ).withColumn(
        "is_high_tool_wear",
        (F.col("tool_wear_min") >= 200).cast("int"),
    )

    # 4. Domain-specific physical risk indicators
    # Heat Dissipation Failure (HDF) condition: delta T < 8.6 K and speed < 1380 RPM
    # Power Failure (PWF) condition: mechanical power < 3500 W or > 9000 W
    # Overstrain Failure (OSF) condition: product of tool wear and torque exceeds machine variant threshold
    df_transformed = df_transformed.withColumn(
        "hdf_risk_flag",
        ((F.col("temp_diff_k") < 8.6) & (F.col("rotational_speed_rpm") < 1380.0)).cast("int"),
    ).withColumn(
        "pwf_risk_flag",
        ((F.col("mechanical_power_w") < 3500.0) | (F.col("mechanical_power_w") > 9000.0)).cast("int"),
    ).withColumn(
        "osf_risk_flag",
        (
            ((F.col("machine_type") == "L") & (F.col("overstrain_product") > 11000.0))
            | ((F.col("machine_type") == "M") & (F.col("overstrain_product") > 12000.0))
            | ((F.col("machine_type") == "H") & (F.col("overstrain_product") > 13000.0))
        ).cast("int"),
    )

    # 5. Composite target label preservation
    df_transformed = df_transformed.withColumn(
        "failure_mode_label",
        F.when(F.col("machine_failure") == 0, "NORMAL")
        .when(F.col("twf") == 1, "TWF")
        .when(F.col("hdf") == 1, "HDF")
        .when(F.col("pwf") == 1, "PWF")
        .when(F.col("osf") == 1, "OSF")
        .when(F.col("rnf") == 1, "RNF")
        .otherwise("UNSPECIFIED_FAILURE"),
    )

    return df_transformed
