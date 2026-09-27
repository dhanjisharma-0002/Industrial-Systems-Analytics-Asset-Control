"""
Spark session manager for ISAAC Big Data processing layer.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

# Ensure PySpark workers use the active Python interpreter on Windows
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE_DIR = PROJECT_ROOT / "data" / "spark_warehouse"
HADOOP_HOME = PROJECT_ROOT / "hadoop"

# Set up HADOOP_HOME for Windows compatibility if present
if HADOOP_HOME.exists():
    os.environ["HADOOP_HOME"] = str(HADOOP_HOME)
    os.environ["PATH"] = f"{HADOOP_HOME / 'bin'};{os.environ.get('PATH', '')}"

from pyspark.sql import SparkSession


def get_spark_session(
    app_name: str = "ISAAC-BigData-Pipeline",
    master: str = "local[*]",
    driver_memory: str = "2g",
    shuffle_partitions: int = 4,
) -> SparkSession:
    """
    Create or retrieve a configured local PySpark session.
    Optimized for multi-core local execution and predictable Windows operation.
    """
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)

    builder = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.sql.warehouse.dir", str(WAREHOUSE_DIR.as_uri()))
        .config("spark.ui.enabled", "false")
        .config("spark.pyspark.python", sys.executable)
        .config("spark.pyspark.driver.python", sys.executable)
        .config("spark.sql.execution.arrow.pyspark.enabled", "false")
    )

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def stop_spark_session(spark: Optional[SparkSession] = None) -> None:
    """Safely terminate the Spark session."""
    if spark is not None:
        try:
            spark.stop()
        except Exception:
            pass


@contextmanager
def spark_session_scope(
    app_name: str = "ISAAC-BigData-Pipeline",
) -> Generator[SparkSession, None, None]:
    """Context manager for ephemeral PySpark session lifecycle."""
    spark = get_spark_session(app_name=app_name)
    try:
        yield spark
    finally:
        stop_spark_session(spark)
