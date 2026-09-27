"""
Unit tests for Exploratory Data Analysis (EDA) scripts and artifacts.
"""

import json
from pathlib import Path

import pytest

from scripts.run_eda import compute_statistical_summary, load_dataset, run_eda_pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CHARTS_DIR = PROJECT_ROOT / "docs" / "analysis" / "charts"
EDA_SUMMARY_JSON = PROJECT_ROOT / "docs" / "analysis" / "eda_summary.json"
EDA_REPORT_MD = PROJECT_ROOT / "docs" / "analysis" / "EDA_REPORT.md"

EXPECTED_CHARTS = [
    "failure_distribution.png",
    "temperature_distribution.png",
    "mechanical_distribution.png",
    "machine_comparison.png",
    "correlation_heatmap.png",
    "overstrain_boundary.png",
]


def test_load_dataset():
    """Verify EDA data loading correctly extracts rows and columns."""
    df = load_dataset()
    assert len(df) == 10000
    assert "machine_failure" in df.columns
    assert "air_temperature_k" in df.columns
    assert "torque_nm" in df.columns


def test_compute_statistical_summary():
    """Verify statistical summary metrics are correctly calculated."""
    df = load_dataset()
    stats = compute_statistical_summary(df)

    assert "air_temperature_k" in stats
    assert "torque_nm" in stats
    assert "rotational_speed_rpm" in stats
    assert "mechanical_power_w" in stats

    # Verify bounds
    assert stats["air_temperature_k"]["mean"] == pytest.approx(300.0, abs=0.5)
    assert stats["torque_nm"]["mean"] == pytest.approx(40.0, abs=0.5)
    assert stats["rotational_speed_rpm"]["iqr_outliers_count"] == 418


def test_eda_artifacts_and_charts():
    """Verify that all generated charts exist, are non-empty, and have valid PNG headers."""
    assert CHARTS_DIR.exists()

    for chart_name in EXPECTED_CHARTS:
        chart_path = CHARTS_DIR / chart_name
        assert chart_path.exists(), f"Chart {chart_name} must exist"
        assert chart_path.stat().st_size > 5000, f"Chart {chart_name} is too small (<5KB)"

        with open(chart_path, "rb") as f:
            header = f.read(8)
            assert header == b"\x89PNG\r\n\x1a\n", f"File {chart_name} is not a valid PNG image"


def test_eda_report_and_summary_files():
    """Verify that EDA_REPORT.md and eda_summary.json exist and contain key findings."""
    assert EDA_SUMMARY_JSON.exists()
    with open(EDA_SUMMARY_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) >= 7

    assert EDA_REPORT_MD.exists()
    content = EDA_REPORT_MD.read_text(encoding="utf-8")
    assert "Class Imbalance" in content
    assert "Correlation vs. Causation" in content
    assert "Data Leakage" in content
    assert "3.39%" in content
