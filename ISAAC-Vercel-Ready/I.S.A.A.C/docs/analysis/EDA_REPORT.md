# ISAAC Phase 4: Exploratory Data Analysis (EDA) Report

## 1. Executive Summary & Dataset Profile

This report provides a comprehensive exploratory data analysis of the **AI4I 2020 Predictive Maintenance Dataset** (UCI Machine Learning Repository, Matzka 2020), containing 10,000 authentic industrial telemetry records from CNC machining centers.

### Dataset High-Level Attributes
- **Total Observations ($N$):** 10,000
- **Missing / Null Values:** 0 across all features (100% data completeness)
- **Duplicate Records:** 0 (Unique `udi` from 1 to 10,000; unique `product_id` across all units)
- **Feature Space:** 14 base fields expanded to 38 engineered thermodynamic, kinematic, and windowed features.

---

## 2. Target Distribution & Class Imbalance

The operational health target (`machine_failure`) exhibits severe **class imbalance** characteristic of real-world industrial systems where failures are rare but catastrophic events.

```
Total Observations:   10,000
├── Normal Operation:  9,661 (96.61%)
└── Machine Failures:    339 ( 3.39%)
    ├── Heat Dissipation Failure (HDF): 115 (33.9% of failures)
    ├── Overstrain Failure (OSF):        98 (28.9% of failures)
    ├── Power Failure (PWF):             95 (28.0% of failures)
    ├── Tool Wear Failure (TWF):         46 (13.6% of failures)
    └── Random Failure (RNF):            19 ( 5.6% of failures)
    *(Note: Total failure mode instances = 373 due to multi-mode concurrency in 34 cases)*
```

- **Imbalance Ratio:** **28.5 : 1** (96.61% negative class vs. 3.39% positive class).
- **ML Evaluation Implication:** Standard accuracy is completely misleading (a trivial dummy classifier predicting "No Failure" achieves 96.61% accuracy). Model evaluation in Phase 5 must strictly optimize **Precision-Recall Area Under Curve (PR-AUC)**, **F1-Score on Minority Class**, **Recall / Sensitivity**, and **Cost-Weighted Confusion Matrix**.

---

## 3. Sensor Telemetry Distributions & Outlier Profiles

Statistical distribution parameters computed across all continuous operational sensors ($N = 10,000$):

| Sensor Metric | Mean | Std Dev | Min | Q1 (25%) | Median (50%) | Q3 (75%) | Max | Skewness | IQR Outliers |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Air Temp ($K$)** | 300.00 | 2.00 | 295.30 | 298.30 | 300.10 | 301.50 | 304.50 | +0.114 | 0 (0.0%) |
| **Process Temp ($K$)**| 310.01 | 1.48 | 305.70 | 308.80 | 310.10 | 311.10 | 313.80 | +0.015 | 0 (0.0%) |
| **$\Delta T$ Difference ($K$)**| 10.00 | 1.00 | 7.60 | 9.30 | 9.80 | 11.00 | 12.10 | -0.072 | 0 (0.0%) |
| **Rotational Speed ($RPM$)**| 1538.78 | 179.28 | 1168.00 | 1423.00 | 1503.00 | 1612.00 | 2886.00 | +1.993 | 418 (4.18%) |
| **Torque ($Nm$)** | 39.99 | 9.97 | 3.80 | 33.20 | 40.10 | 46.80 | 76.60 | -0.010 | 69 (0.69%) |
| **Mechanical Power ($W$)**| 6279.74 | 1067.42 | 1148.44 | 5561.18 | 6271.03 | 7003.01 | 10469.92 | +0.008 | 60 (0.60%) |
| **Tool Wear ($min$)** | 107.95 | 63.65 | 0.00 | 53.00 | 108.00 | 162.00 | 253.00 | +0.027 | 0 (0.0%) |

### Outlier Characterization
- **Rotational Speed (RPM):** Highly right-skewed ($+1.993$), exhibiting 418 upper-tail outliers ($> 1895.5\text{ RPM}$) up to 2,886 RPM. These high-speed bursts correspond to light-load idling conditions and correlate strongly with low torque.
- **Torque (Nm):** Symmetrically distributed ($Mean = 39.99\text{ Nm}$, $Median = 40.10\text{ Nm}$) with 69 outliers located in the extreme tails ($< 12.8\text{ Nm}$ or $> 67.2\text{ Nm}$). Extreme high torque is the primary catalyst for Overstrain Failure (OSF).
- **Mechanical Power (W):** Centered at 6,279.7 W with 60 outliers falling outside the nominal band ($[3498.5\text{ W}, 9165.7\text{ W}]$). These outliers align directly with Power Failures (PWF).
- **Tool Wear (min):** Uniform rectangular distribution spanning 0 to 253 minutes without outliers, reflecting continuous wear accumulation across tool lifecycle.

---

## 4. Machine Quality Variant Comparison

The dataset partitions equipment assets into three quality variants based on build grade and component tolerances:

| Machine Variant | Total Units | Failure Count | Failure Rate (%) | Avg Mechanical Power (W) | Avg RPM | Failure Mode Dominance |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **L (Low Variant)** | 6,000 (60%) | 235 | **3.92%** | 6,282.8 W | 1,539.5 | OSF: 87, HDF: 76, PWF: 59, TWF: 25 |
| **M (Medium Variant)** | 2,997 (30%) | 83 | **2.77%** | 6,279.1 W | 1,537.6 | HDF: 31, PWF: 31, TWF: 14, OSF: 9 |
| **H (High Variant)** | 1,003 (10%) | 21 | **2.09%** | 6,263.6 W | 1,538.1 | HDF: 8, TWF: 7, PWF: 5, OSF: 2 |

### Key Variant Observations
- **Failure Resilience:** High-variant (`H`) machines demonstrate **nearly half the failure incidence rate (2.09%)** compared to Low-variant (`L`) machines (3.92%).
- **Overstrain Susceptibility:** Low-variant machines account for **88.8% of all Overstrain Failures (87 out of 98)** due to lower structural material tolerance thresholds ($11,000\text{ min}\cdot\text{Nm}$ vs $13,000\text{ min}\cdot\text{Nm}$).

---

## 5. Correlation vs. Causation Analysis

A rigorous distinction between observational statistical correlation and true physical causation is essential for robust predictive modeling:

| Observed Correlation | Statistical Value ($r$) | Physical Causation Mechanism | Engineering Diagnosis |
| :--- | :--- | :--- | :--- |
| **Torque vs. Rotational Speed** | **$-0.875$ (Strong Negative)** | In continuous cutting at constant motor drive power $P = \tau \cdot \omega$, torque and speed are inversely constrained by electromagnetic back-EMF and motor torque-speed curves. | High speed inherently implies low torque under constant power constraints. |
| **Torque vs. Machine Failure** | **$+0.191$ (Positive)** | High torque causes mechanical shear stress on the cutting spindle and cutter inserts, leading to plastic deformation and catastrophic fracture (OSF). | True causal driver of structural failure. |
| **$\Delta T$ Temp Diff vs. Failure** | **$-0.279$ (Negative)** | When ambient-to-process temperature gradient $\Delta T < 8.6\text{ K}$ and spindle speed is low ($< 1380\text{ RPM}$), forced convection convective heat dissipation stalls, resulting in thermal seizure (HDF). | Thermal dissipation boundary collapse causes thermal seizure. |
| **Tool Wear vs. Failure** | **$+0.105$ (Moderate Positive)** | Friction abrasively removes tool coating over time ($TWF$), which simultaneously increases machining resistance and cutting force requirements ($OSF = Wear \times Torque$). | Cumulative wear is a necessary pre-condition for wear and strain failures. |
| **UDI / Timestamp vs. Failure** | **$-0.023$ (Zero Correlation)** | Observation index has no physical connection to machine failure. | Statistical artifact; must be excluded to avoid temporal leakage. |

---

## 6. Predictive Feature Ranking for ML (Phase 5)

Based on information gain, physical boundary alignment, and variance separation, the top predictive features are:

1. **`overstrain_product` ($Tool\ Wear \times Torque$):** Directly isolates Overstrain Failures ($OSF$) across machine variants.
2. **`mechanical_power_w` ($Torque \times \omega$):** Directly captures electrical and mechanical power overload/underload conditions ($PWF$).
3. **`temp_diff_k` ($\Delta T = T_{process} - T_{air}$):** Primary indicator for Heat Dissipation Failure ($HDF$).
4. **`torque_nm`:** Critical operational stress telemetry.
5. **`tool_wear_min`:** Fundamental indicator of blade degradation life.
6. **`rotational_speed_rpm`:** Essential for convective airflow and angular velocity calculation.
7. **`machine_type` (Categorical L/M/H):** Modulates structural resilience thresholds.
8. **`rolling_std_torque_5` / `rolling_std_rpm_5`:** Dynamic instability proxies capturing micro-vibrations prior to tripping.

---

## 7. Data Leakage Prevention Matrix

> [!CAUTION]
> **Strict Machine Learning Leakage Guardrails:**

| Feature Candidate | Permitted in ML Input? | Justification & Risk |
| :--- | :--- | :--- |
| `air_temperature_k`, `process_temperature_k` | **YES** | Real-time observable telemetry. |
| `rotational_speed_rpm`, `torque_nm`, `tool_wear_min` | **YES** | Real-time observable telemetry. |
| `temp_diff_k`, `mechanical_power_w`, `overstrain_product` | **YES** | Domain feature engineering derived strictly from available telemetry. |
| `rolling_avg_*`, `rolling_std_*` | **YES** | Lagged causal window features without future lookahead. |
| `twf`, `hdf`, `pwf`, `osf`, `rnf` | **FORBIDDEN (TARGET LEAKAGE)** | These flags represent the direct decomposition of the target `machine_failure`. Including them as inputs produces 100% artificial test accuracy and zero generalization on real unlabelled telemetry. |
| `udi`, `product_id` | **FORBIDDEN (ID LEAKAGE)** | Arbitrary identifiers that risk memorization rather than physical pattern learning. |

---

## 8. Analytical Charts Directory

All high-resolution figures are generated and stored under `docs/analysis/charts/`:

- **Figure 1:** [Failure Distribution & Sub-mode Breakdown](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/charts/failure_distribution.png)
- **Figure 2:** [Temperature Distributions & HDF Thermal Threshold](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/charts/temperature_distribution.png)
- **Figure 3:** [Rotational Speed vs. Torque Mechanical Scatter & PWF Bounds](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/charts/mechanical_distribution.png)
- **Figure 4:** [Machine Quality Variant Failure Comparison](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/charts/machine_comparison.png)
- **Figure 5:** [Pearson Correlation Heatmap](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/charts/correlation_heatmap.png)
- **Figure 6:** [Overstrain Failure (OSF) Physical Boundaries](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/charts/overstrain_boundary.png)
