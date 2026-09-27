# ISAAC Data Dictionary: AI4I 2020 Predictive Maintenance Dataset

## 1. Overview & Provenance

- **Dataset Name**: AI4I 2020 Predictive Maintenance Dataset
- **Primary Source**: UCI Machine Learning Repository
- **URL**: [https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset)
- **Author**: Stephan Matzka, School of Engineering - Technology and Life, Hochschule für Technik und Wirtschaft Berlin, Germany
- **Citation**: Matzka, S. (2020). *Explainable Artificial Intelligence for Predictive Maintenance Applications with High Dimensional Temporal Data*. IEEE International Conference on Emerging Technologies and Factory Automation (ETFA), pp. 1010-1016.
- **License**: [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- **Total Records**: 10,000 observations
- **Total Features**: 14 (1 identifier, 1 product ID, 1 quality variant, 5 operational sensor metrics, 1 binary failure target, 5 specific failure mode labels)

---

## 2. Directory Locations

| Artifact | Path | Description |
| :--- | :--- | :--- |
| **Raw Dataset** | [`data/raw/ai4i2020.csv`](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/data/raw/ai4i2020.csv) | Original unedited CSV downloaded directly from UCI repository. |
| **Processed Dataset** | [`data/processed/ai4i2020_cleaned.csv`](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/data/processed/ai4i2020_cleaned.csv) | Standardized snake_case column names and normalized types (10,000 rows). |
| **Sample Dataset** | [`data/sample/sample_ai4i2020.csv`](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/data/sample/sample_ai4i2020.csv) | Verified 100-row sample containing representative normal and failure modes. |

---

## 3. Schema & Field Definitions

| Raw Field Name | Processed Field Name | Data Type | Physical Unit | Valid Range | Nullable | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `UDI` | `udi` | Integer | — | `[1, 10000]` | No | Unique row index / observation sequence number. |
| `Product ID` | `product_id` | String | — | Letter + 5 digits (e.g., `M14860`) | No | Identifier of the machine asset consisting of quality variant prefix and serial number. |
| `Type` | `machine_type` | String | — | `{'L', 'M', 'H'}` | No | Machine product quality variant: **L** (Low, 50% of all products), **M** (Medium, 30%), **H** (High, 20%). |
| `Air temperature [K]` | `air_temperature_k` | Float | Kelvin ($K$) | `[295.0, 305.0]` (nominal `[290, 315]`) | No | Ambient air temperature measured by operational sensors around the machine. |
| `Process temperature [K]` | `process_temperature_k` | Float | Kelvin ($K$) | `[305.0, 315.0]` (nominal `[300, 325]`) | No | Generated internal process temperature during machine milling/machining. |
| `Rotational speed [rpm]` | `rotational_speed_rpm` | Float / Int | Revolutions per min ($RPM$) | `[1100, 3000]` (nominal `[1000, 3500]`) | No | Spindle rotational speed calculated from power consumption and torque. |
| `Torque [Nm]` | `torque_nm` | Float | Newton-meters ($Nm$) | `[3.0, 80.0]` (nominal `[0.0, 100.0]`) | No | Torque applied during the machining process, normally distributed around 40 Nm. |
| `Tool wear [min]` | `tool_wear_min` | Integer | Minutes ($min$) | `[0, 300]` | No | Cumulative operating duration of the cutting tool before replacement/maintenance. |
| `Machine failure` | `machine_failure` | Integer / Bool | Binary | `{0, 1}` | No | Primary operational target indicating whether a machine failure occurred in this observation. |
| `TWF` | `twf` | Integer / Bool | Binary | `{0, 1}` | No | **Tool Wear Failure**: Tool wear exceeded failure limit (typically between 200–240 minutes). |
| `HDF` | `hdf` | Integer / Bool | Binary | `{0, 1}` | No | **Heat Dissipation Failure**: Process-to-air temperature difference $< 8.6 K$ combined with speed $< 1380 RPM$. |
| `PWF` | `pwf` | Integer / Bool | Binary | `{0, 1}` | No | **Power Failure**: Process power ($Torque \times \omega$) $< 3500 W$ or $> 9000 W$. |
| `OSF` | `osf` | Integer / Bool | Binary | `{0, 1}` | No | **Overstrain Failure**: Product of tool wear and torque exceeded threshold variant limits. |
| `RNF` | `rnf` | Integer / Bool | Binary | `{0, 1}` | No | **Random Failure**: Uncorrelated failure event occurring with a low background probability ($0.1\%$). |

---

## 4. Relational Database Mapping

In ISAAC's normalized relational schema, these fields are partitioned into three dedicated tables:

1. **`machines`**:
   - `machine_id` $\leftarrow$ `product_id` (Unique, Index)
   - `type` $\leftarrow$ `machine_type` (`'L'`, `'M'`, `'H'`)
   - `created_at` $\leftarrow$ Ingestion timestamp

2. **`sensor_data`**:
   - `machine_id` $\leftarrow$ Foreign Key to `machines.machine_id`
   - `udi` $\leftarrow$ Sequence index
   - `air_temperature_k`, `process_temperature_k`, `rotational_speed_rpm`, `torque_nm`, `tool_wear_min`
   - `recorded_at` $\leftarrow$ Telemetry observation timestamp

3. **`maintenance_records`**:
   - `machine_id` $\leftarrow$ Foreign Key to `machines.machine_id`
   - `sensor_data_id` $\leftarrow$ Foreign Key to `sensor_data.id`
   - `failure_occurred` $\leftarrow$ `machine_failure`
   - `failure_type` $\leftarrow$ Computed composite string (e.g., `'TWF'`, `'HDF'`, `'PWF'`, `'OSF'`, `'RNF'`, or `'None'`)
   - `twf`, `hdf`, `pwf`, `osf`, `rnf` $\leftarrow$ Individual binary flags
   - `recorded_at` $\leftarrow$ Event record timestamp

---

## 5. Dataset Statistics Summary

- **Total Rows**: 10,000
- **Missing / Null Values**: 0 (100% complete)
- **Unique Product IDs**: 10,000
- **Machine Type Split**:
  - `L` (Low): 6,000 (60.0%)
  - `M` (Medium): 2,997 (29.97%)
  - `H` (High): 1,003 (10.03%)
- **Target Distribution**:
  - Normal operation (`0`): 9,661 (96.61%)
  - Machine failure (`1`): 339 (3.39%)
- **Failure Breakdown by Mode**:
  - `HDF` (Heat Dissipation Failure): 115
  - `OSF` (Overstrain Failure): 98
  - `PWF` (Power Failure): 95
  - `TWF` (Tool Wear Failure): 46
  - `RNF` (Random Failure): 19
