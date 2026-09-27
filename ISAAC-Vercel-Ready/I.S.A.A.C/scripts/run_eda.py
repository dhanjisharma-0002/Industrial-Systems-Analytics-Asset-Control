"""
Comprehensive Exploratory Data Analysis (EDA) Script for ISAAC.
Generates publication-quality charts and statistical summaries for predictive maintenance.

Usage:
    python scripts/run_eda.py
"""

import json
from pathlib import Path
from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "spark_features" / "features.csv"
CLEANED_FALLBACK = PROJECT_ROOT / "data" / "processed" / "ai4i2020_cleaned.csv"
CHARTS_DIR = PROJECT_ROOT / "docs" / "analysis" / "charts"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "docs" / "analysis"

# Set styling
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = "DejaVu Sans, Arial, Helvetica, sans-serif"
plt.rcParams["axes.edgecolor"] = "#2c3e50"
plt.rcParams["axes.linewidth"] = 0.8


def load_dataset() -> pd.DataFrame:
    """Load the processed feature dataset or fallback to cleaned dataset."""
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
    elif CLEANED_FALLBACK.exists():
        df = pd.read_csv(CLEANED_FALLBACK)
        # Compute basic feature additions if reading raw cleaned
        df["temp_diff_k"] = df["process_temperature_k"] - df["air_temperature_k"]
        df["angular_velocity_rad_s"] = df["rotational_speed_rpm"] * (2 * np.pi / 60.0)
        df["mechanical_power_w"] = df["torque_nm"] * df["angular_velocity_rad_s"]
        df["overstrain_product"] = df["tool_wear_min"] * df["torque_nm"]
    else:
        raise FileNotFoundError("Neither spark features nor cleaned dataset found.")
    return df


def generate_failure_distribution_chart(df: pd.DataFrame, output_path: Path) -> None:
    """Generate overall failure vs normal distribution and failure mode decomposition chart."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Plot 1: Binary Class Imbalance
    failure_counts = df["machine_failure"].value_counts()
    labels = ["Normal Operational\n(96.61%)", "Machine Failure\n(3.39%)"]
    colors = ["#2ecc71", "#e74c3c"]
    bars = ax1.bar([0, 1], [failure_counts[0], failure_counts[1]], color=colors, width=0.55, edgecolor="#111", linewidth=1)
    ax1.set_xticks([0, 1])
    ax1.set_xticklabels(labels, fontsize=11, fontweight="bold")
    ax1.set_ylabel("Observation Count", fontsize=11)
    ax1.set_title("Binary Target Distribution (Class Imbalance: ~28.5:1)", fontsize=13, fontweight="bold", pad=12)

    for bar in bars:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2.0, yval + 120, f"{yval:,} records", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax1.set_ylim(0, 11000)

    # Plot 2: Failure Mode Breakdown
    mode_cols = ["hdf", "osf", "pwf", "twf", "rnf"]
    mode_labels = [
        "Heat Dissipation (HDF)",
        "Overstrain (OSF)",
        "Power Failure (PWF)",
        "Tool Wear (TWF)",
        "Random (RNF)",
    ]
    mode_counts = [df[col].sum() for col in mode_cols]
    mode_colors = ["#e67e22", "#9b59b6", "#3498db", "#e74c3c", "#95a5a6"]

    y_pos = np.arange(len(mode_cols))
    hbars = ax2.barh(y_pos, mode_counts, color=mode_colors, edgecolor="#111", linewidth=1, height=0.6)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(mode_labels, fontsize=11, fontweight="bold")
    ax2.invert_yaxis()
    ax2.set_xlabel("Occurrences Count", fontsize=11)
    ax2.set_title("Failure Decomposition by Mode (N = 339 failures)", fontsize=13, fontweight="bold", pad=12)

    for bar in hbars:
        xval = bar.get_width()
        pct = (xval / len(df)) * 100
        ax2.text(xval + 2, bar.get_y() + bar.get_height() / 2.0, f"{xval} ({pct:.2f}%)", ha="left", va="center", fontsize=10, fontweight="bold")
    ax2.set_xlim(0, 140)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"   [Saved] {output_path.name}")


def generate_temperature_distribution_chart(df: pd.DataFrame, output_path: Path) -> None:
    """Generate temperature distributions and differential density plot."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Plot 1: Air Temp vs Process Temp Distributions
    sns.kdeplot(df["air_temperature_k"], ax=ax1, label="Air Temperature (K)", color="#3498db", fill=True, alpha=0.35, linewidth=2)
    sns.kdeplot(df["process_temperature_k"], ax=ax1, label="Process Temperature (K)", color="#e74c3c", fill=True, alpha=0.35, linewidth=2)
    ax1.set_xlabel("Temperature (Kelvin)", fontsize=11)
    ax1.set_ylabel("Density", fontsize=11)
    ax1.set_title("Thermal Dynamics: Air vs. Process Temperature", fontsize=13, fontweight="bold", pad=12)
    ax1.legend(frameon=True, fontsize=10)

    # Plot 2: Temp Difference Distribution separated by HDF failure
    sns.histplot(
        data=df,
        x="temp_diff_k",
        hue="hdf",
        bins=35,
        ax=ax2,
        palette={0: "#2ecc71", 1: "#e74c3c"},
        legend=True,
        alpha=0.6,
        edgecolor="#111",
    )
    ax2.axvline(8.6, color="#c0392b", linestyle="--", linewidth=2, label="HDF Threshold (ΔT < 8.6 K)")
    ax2.set_xlabel("Temperature Difference ΔT (Process - Air, K)", fontsize=11)
    ax2.set_ylabel("Observation Count", fontsize=11)
    ax2.set_title("Heat Dissipation Failure (HDF) Threshold Boundary", fontsize=13, fontweight="bold", pad=12)
    ax2.legend(title="HDF Status", labels=["HDF Active (1)", "Normal (0)", "HDF Boundary (8.6 K)"], frameon=True)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"   [Saved] {output_path.name}")


def generate_mechanical_distribution_chart(df: pd.DataFrame, output_path: Path) -> None:
    """Generate Rotational Speed vs Torque scatter plot highlighting Power Failure bounds."""
    fig, ax = plt.subplots(figsize=(10, 6.5))

    # Scatter of normal vs failure
    normal_df = df[df["machine_failure"] == 0]
    failure_df = df[df["machine_failure"] == 1]

    ax.scatter(normal_df["rotational_speed_rpm"], normal_df["torque_nm"], color="#95a5a6", alpha=0.35, s=18, label="Normal Operation (0)")
    ax.scatter(failure_df["rotational_speed_rpm"], failure_df["torque_nm"], color="#e74c3c", alpha=0.85, s=36, edgecolor="#111", linewidth=0.5, label="Machine Failure (1)")

    # Power boundary curves: Power = Torque * (RPM * 2*pi / 60)
    # Power bounds: 3500 W (lower bound) and 9000 W (upper bound)
    rpm_range = np.linspace(1100, 2900, 200)
    torque_3500w = 3500.0 / (rpm_range * (2 * np.pi / 60.0))
    torque_9000w = 9000.0 / (rpm_range * (2 * np.pi / 60.0))

    ax.plot(rpm_range, torque_3500w, color="#2980b9", linestyle="--", linewidth=2, label="PWF Lower Bound (3,500 W)")
    ax.plot(rpm_range, torque_9000w, color="#8e44ad", linestyle="--", linewidth=2, label="PWF Upper Bound (9,000 W)")

    ax.set_xlabel("Rotational Speed (RPM)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Torque (Nm)", fontsize=11, fontweight="bold")
    ax.set_title("Mechanical Telemetry: Rotational Speed vs. Torque (PWF Failure Envelope)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(1100, 2900)
    ax.set_ylim(0, 80)
    ax.legend(frameon=True, loc="upper right", fontsize=10)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"   [Saved] {output_path.name}")


def generate_machine_comparison_chart(df: pd.DataFrame, output_path: Path) -> None:
    """Generate comparative failure rate and mode distribution across machine types L, M, H."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Plot 1: Failure Rates by Machine Type
    type_stats = df.groupby("machine_type")["machine_failure"].agg(["count", "sum", "mean"]).reset_index()
    type_stats["failure_rate_pct"] = type_stats["mean"] * 100

    colors = ["#e74c3c", "#f39c12", "#2ecc71"]
    bars = ax1.bar(type_stats["machine_type"], type_stats["failure_rate_pct"], color=colors, width=0.5, edgecolor="#111", linewidth=1)
    ax1.set_xlabel("Machine Quality Variant", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Failure Rate (%)", fontsize=11, fontweight="bold")
    ax1.set_title("Machine Failure Rate by Quality Variant", fontsize=13, fontweight="bold", pad=12)
    ax1.set_ylim(0, 5)

    for bar, (_, row) in zip(bars, type_stats.iterrows()):
        yval = bar.get_height()
        ax1.text(
            bar.get_x() + bar.get_width() / 2.0,
            yval + 0.12,
            f"{yval:.2f}%\n({int(row['sum'])}/{int(row['count'])})",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    # Plot 2: Failure Modes Breakdown per Machine Type
    modes_by_type = df.groupby("machine_type")[["twf", "hdf", "pwf", "osf", "rnf"]].sum().reset_index()
    modes_melted = pd.melt(modes_by_type, id_vars=["machine_type"], var_name="failure_mode", value_name="count")
    modes_melted["failure_mode"] = modes_melted["failure_mode"].str.upper()

    sns.barplot(data=modes_melted, x="failure_mode", y="count", hue="machine_type", ax=ax2, palette={"L": "#e74c3c", "M": "#f39c12", "H": "#2ecc71"}, edgecolor="#111")
    ax2.set_xlabel("Failure Mode", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Total Occurrences", fontsize=11, fontweight="bold")
    ax2.set_title("Failure Mode Frequencies Across Machine Types", fontsize=13, fontweight="bold", pad=12)
    ax2.legend(title="Machine Type", frameon=True)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"   [Saved] {output_path.name}")


def generate_correlation_heatmap(df: pd.DataFrame, output_path: Path) -> None:
    """Generate correlation heatmap across numeric sensors, features, and target."""
    cols = [
        "air_temperature_k",
        "process_temperature_k",
        "temp_diff_k",
        "rotational_speed_rpm",
        "torque_nm",
        "mechanical_power_w",
        "tool_wear_min",
        "overstrain_product",
        "machine_failure",
        "twf",
        "hdf",
        "pwf",
        "osf",
    ]
    corr = df[cols].corr()

    fig, ax = plt.subplots(figsize=(11, 9))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    cmap = sns.diverging_palette(230, 20, as_cmap=True)

    sns.heatmap(
        corr,
        mask=mask,
        cmap=cmap,
        vmax=1.0,
        vmin=-1.0,
        center=0,
        annot=True,
        fmt=".2f",
        square=True,
        linewidths=0.5,
        cbar_kws={"shrink": 0.8},
        ax=ax,
    )
    ax.set_title("Telemetry & Failure Correlation Matrix (Pearson)", fontsize=13, fontweight="bold", pad=15)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"   [Saved] {output_path.name}")


def generate_overstrain_boundary_chart(df: pd.DataFrame, output_path: Path) -> None:
    """Generate Tool Wear vs Torque scatter plot illustrating Overstrain Failure (OSF) boundaries."""
    fig, ax = plt.subplots(figsize=(10, 6.5))

    normal_df = df[df["osf"] == 0]
    osf_df = df[df["osf"] == 1]

    ax.scatter(normal_df["tool_wear_min"], normal_df["torque_nm"], color="#95a5a6", alpha=0.3, s=18, label="Normal / Non-OSF (0)")
    ax.scatter(osf_df["tool_wear_min"], osf_df["torque_nm"], color="#9b59b6", alpha=0.9, s=40, edgecolor="#111", linewidth=0.6, label="Overstrain Failure OSF (1)")

    # Overstrain curve: Wear * Torque = Threshold
    wear_range = np.linspace(100, 255, 200)
    t_l = 11000.0 / wear_range
    t_m = 12000.0 / wear_range
    t_h = 13000.0 / wear_range

    ax.plot(wear_range, t_l, color="#e74c3c", linestyle="--", linewidth=2, label="Type L Threshold (11,000 min·Nm)")
    ax.plot(wear_range, t_m, color="#f39c12", linestyle="--", linewidth=2, label="Type M Threshold (12,000 min·Nm)")
    ax.plot(wear_range, t_h, color="#27ae60", linestyle="--", linewidth=2, label="Type H Threshold (13,000 min·Nm)")

    ax.set_xlabel("Tool Wear (Minutes)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Torque (Nm)", fontsize=11, fontweight="bold")
    ax.set_title("Overstrain Failure (OSF) Physical Boundary: Tool Wear vs. Torque", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(0, 260)
    ax.set_ylim(10, 80)
    ax.legend(frameon=True, loc="upper left", fontsize=10)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"   [Saved] {output_path.name}")


def compute_statistical_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute detailed dataset statistics and outlier summaries."""
    sensor_cols = [
        "air_temperature_k",
        "process_temperature_k",
        "temp_diff_k",
        "rotational_speed_rpm",
        "torque_nm",
        "mechanical_power_w",
        "tool_wear_min",
    ]

    stats = {}
    for col in sensor_cols:
        series = df[col]
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outliers_count = int(((series < lower_bound) | (series > upper_bound)).sum())

        stats[col] = {
            "mean": round(float(series.mean()), 2),
            "std": round(float(series.std()), 2),
            "min": round(float(series.min()), 2),
            "q25": round(float(q1), 2),
            "median": round(float(series.median()), 2),
            "q75": round(float(q3), 2),
            "max": round(float(series.max()), 2),
            "skewness": round(float(series.skew()), 3),
            "kurtosis": round(float(series.kurtosis()), 3),
            "iqr": round(float(iqr), 2),
            "iqr_outliers_count": outliers_count,
            "iqr_outliers_pct": round((outliers_count / len(df)) * 100, 2),
        }

    return stats


def run_eda_pipeline() -> Dict[str, Any]:
    """Run full EDA pipeline and output charts and stats."""
    print("=" * 60)
    print("RUNNING ISAAC EXPLORATORY DATA ANALYSIS (EDA)")
    print("=" * 60)

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_dataset()
    print(f"Loaded {len(df)} records with {len(df.columns)} columns.")

    print("\n1. Generating analytical visualization charts...")
    generate_failure_distribution_chart(df, CHARTS_DIR / "failure_distribution.png")
    generate_temperature_distribution_chart(df, CHARTS_DIR / "temperature_distribution.png")
    generate_mechanical_distribution_chart(df, CHARTS_DIR / "mechanical_distribution.png")
    generate_machine_comparison_chart(df, CHARTS_DIR / "machine_comparison.png")
    generate_correlation_heatmap(df, CHARTS_DIR / "correlation_heatmap.png")
    generate_overstrain_boundary_chart(df, CHARTS_DIR / "overstrain_boundary.png")

    print("\n2. Computing statistical metrics and outlier profiles...")
    stats = compute_statistical_summary(df)

    summary_file = OUTPUT_REPORT_DIR / "eda_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"   [Saved] {summary_file.name}")

    print("\nEDA completed successfully.")
    return stats


if __name__ == "__main__":
    run_eda_pipeline()
