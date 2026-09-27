"""
Dataset ingestion module for PySpark Big Data processing layer.
Enforces explicit StructType schemas on industrial telemetry data.
"""

from pathlib import Path
from typing import Optional, Union

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)


def get_dataset_schema() -> StructType:
    """Return explicit StructType schema for cleaned AI4I 2020 predictive maintenance dataset."""
    return StructType(
        [
            StructField("udi", IntegerType(), nullable=False),
            StructField("product_id", StringType(), nullable=False),
            StructField("machine_type", StringType(), nullable=False),
            StructField("air_temperature_k", DoubleType(), nullable=False),
            StructField("process_temperature_k", DoubleType(), nullable=False),
            StructField("rotational_speed_rpm", DoubleType(), nullable=False),
            StructField("torque_nm", DoubleType(), nullable=False),
            StructField("tool_wear_min", IntegerType(), nullable=False),
            StructField("machine_failure", IntegerType(), nullable=False),
            StructField("twf", IntegerType(), nullable=False),
            StructField("hdf", IntegerType(), nullable=False),
            StructField("pwf", IntegerType(), nullable=False),
            StructField("osf", IntegerType(), nullable=False),
            StructField("rnf", IntegerType(), nullable=False),
        ]
    )


def read_industrial_dataset(
    spark: SparkSession,
    file_path: Union[str, Path],
    schema: Optional[StructType] = None,
) -> DataFrame:
    """
    Read industrial CSV dataset into a Spark DataFrame with explicit schema enforcement.
    Handles header parsing and strict data typing.
    """
    path_str = str(file_path)
    if schema is None:
        schema = get_dataset_schema()

    df = (
        spark.read.format("csv")
        .option("header", "true")
        .option("mode", "PERMISSIVE")
        .schema(schema)
        .load(path_str)
    )

    return df
