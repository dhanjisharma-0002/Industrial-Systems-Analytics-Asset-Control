# ISAAC Decision Support Engine & Operational Intelligence (Phase 6)

## 1. Executive Overview

The **ISAAC Decision Support Engine** translates machine learning failure probability outputs into transparent, explainable, and actionable operational guidance for plant operators, reliability engineers, and automated supervisory control systems.

Crucially, ISAAC enforces a strict **separation of concerns** between:
1. **Statistical ML Prediction**: Probabilistic anomaly/failure classification trained on high-dimensional multi-sensor patterns.
2. **Physics-Based Rule Engine**: Deterministic mechanical, thermal, and electrical safety constraints grounded in physical laws.

---

## 2. Architecture: ML Prediction vs. Rule-Based Recommendations

```
+-----------------------------------------------------------------------------------------+
|                                    Incoming Telemetry                                   |
| (Machine Type, Air Temp, Process Temp, Rotational Speed, Torque, Tool Wear, Machine ID) |
+-----------------------------------------------------------------------------------------+
                                           |
                    +----------------------+----------------------+
                    |                                             |
                    v                                             v
+---------------------------------------+     +---------------------------------------+
|        Statistical ML Engine          |     |    Deterministic Rule & Risk Engine   |
|   (HistGradientBoosting Classifier)   |     |    (Physical & Electrical Limits)     |
+---------------------------------------+     +---------------------------------------+
                    |                                             |
                    v                                             v
         Failure Probability (%)                      Physics Explanations:
                    |                                 - Overstrain limit (Wear x Torque)
                    v                                 - Heat dissipation limit (ΔT vs RPM)
         Standardized Risk Tier                       - Spindle power envelope (Power W)
      (NOMINAL / MODERATE / HIGH /                    - Tool life limit (Cumulative min)
               CRITICAL)                                          |
                    |                                             |
                    +----------------------+----------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
|                             Composite Health Score Engine                               |
|       Health Score = clamp(100 * (1 - P_fail) - Sum(Sensor Penalties), 0.0, 100.0)      |
+-----------------------------------------------------------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------------+
|                                Structured API Response                                 |
| { machine_id, failure_probability, risk_level, health_score, recommendation, ... }      |
+-----------------------------------------------------------------------------------------+
```

### Why Decouple ML from Engineering Rules?
- **Explainability**: Black-box models output probabilities ($P_{\text{failure}} = 0.82$), but operators need explicit mechanical justifications (e.g., *"Overstrain limit breached: $12,450\text{ min}\cdot\text{Nm} > 11,000\text{ min}\cdot\text{Nm}$"*).
- **Safety Interlocks**: Regulatory and equipment protection standards require deterministic shutdown triggers that execute regardless of ML confidence scores.
- **Root-Cause Isolation**: Pinpoints the exact sensor channel (temperature delta, torque spike, motor underpower) requiring technician intervention.

---

## 3. Mathematical Health Score Methodology

The machinery **Health Score** ($H \in [0.0, 100.0]$) represents a continuous asset health index.

$$\text{Health Score} = \max\left(0.0, \min\left(100.0, 100 \times (1.0 - P_{\text{failure}}) - \sum \text{Penalties}\right)\right)$$

### Degradation Penalty Formulas

1. **Tool Wear Degradation Penalty ($P_{\text{wear}} \le 10.0$)**:
   $$\text{Excess Wear} = \min(60.0, \max(0.0, \text{ToolWear} - 180.0))$$
   $$P_{\text{wear}} = \left(\frac{\text{Excess Wear}}{60.0}\right) \times 10.0$$

2. **Thermal Margin Penalty ($P_{\text{thermal}} \le 8.0$)**:
   $$\text{Thermal Deficit} = \min(2.0, \max(0.0, 9.0 - \Delta T)) \quad \text{where } \Delta T = T_{\text{process}} - T_{\text{air}}$$
   $$P_{\text{thermal}} = \left(\frac{\text{Thermal Deficit}}{2.0}\right) \times 8.0$$

3. **Torque Overload Penalty ($P_{\text{torque}} \le 8.0$)**:
   $$\text{Torque Excess} = \min(20.0, \max(0.0, \text{Torque} - 55.0))$$
   $$P_{\text{torque}} = \left(\frac{\text{Torque Excess}}{20.0}\right) \times 8.0$$

4. **Power Variance Penalty ($P_{\text{power}} \le 6.0$)**:
   - If $P_{\text{mech}} < 4000\text{ W}$:
     $$P_{\text{power}} = \left(\frac{\min(1000.0, 4000.0 - P_{\text{mech}})}{1000.0}\right) \times 6.0$$
   - If $P_{\text{mech}} > 8500\text{ W}$:
     $$P_{\text{power}} = \left(\frac{\min(1500.0, P_{\text{mech}} - 8500.0)}{1500.0}\right) \times 6.0$$

---

## 4. Standardized Risk Tier Categories

| Risk Tier | Failure Probability ($P_{\text{fail}}$) | Operational Status | Prescribed Action |
|---|---|---|---|
| **`NOMINAL`** | $0.00 \le P < 0.15$ | Normal / Optimal | Standard continuous production. Routine scheduled lubrication. |
| **`MODERATE`** | $0.15 \le P < 0.40$ | Elevated Watch | Increase telemetry sampling. Inspect during next scheduled shift change. |
| **`HIGH`** | $0.40 \le P < 0.70$ | Impending Degradation | Plan maintenance within 8 operating hours. Reduce spindle feed rate. |
| **`CRITICAL`** | $P \ge 0.70$ | Imminent Failure Risk | Immediate emergency spindle stop. Execute diagnostic and repair protocol. |

---

## 5. Transparent Maintenance Recommendation Rules

The recommendation engine evaluates physical failure modes independently from the ML probability:

### A. Overstrain Failure (OSF) Rule
- **Physical Formula**: $\text{Overstrain} = \text{ToolWear} \times \text{Torque}$
- **Variant Thresholds**:
  - **Type L**: $> 11,000\text{ min}\cdot\text{Nm}$
  - **Type M**: $> 12,000\text{ min}\cdot\text{Nm}$
  - **Type H**: $> 13,000\text{ min}\cdot\text{Nm}$
- **Action**: *CRITICAL: Immediate Spindle Halt. Severe mechanical overstrain detected. Inspect cutting tool inserts, spindle bearings, and workpiece clamping before resuming operation.*

### B. Heat Dissipation Failure (HDF) Rule
- **Physical Formula**: $\Delta T = T_{\text{process}} - T_{\text{air}}$
- **Condition**: $\Delta T < 8.60\text{ K}$ **AND** $\text{RotationalSpeed} < 1380\text{ RPM}$
- **Action**: *URGENT: Cooling System Flush. Thermal dissipation boundary degraded. Inspect coolant lines, verify pump flow rate, and clear chip accumulations from heat exchangers.*

### C. Power Failure (PWF) Rule
- **Physical Formula**: $P_{\text{mech}} = \text{Torque} \times \left(\text{RPM} \times \frac{2\pi}{60}\right)$
- **Condition**: $P_{\text{mech}} < 3,500\text{ W}$ **OR** $P_{\text{mech}} > 9,000\text{ W}$
- **Action**: *URGENT: Spindle Drive Electrical Fault. Power delivery outside nominal 3.5 kW - 9.0 kW envelope. Inspect drive inverter, motor windings, and mechanical drive belt tension.*

### D. Tool Wear Failure (TWF) Rule
- **Condition**: $\text{ToolWear} \ge 200\text{ min}$
- **Action**: *SCHEDULED: Tool Replacement Required. Cumulative tool wear at [N] min exceeds nominal 200 min lifespan. Replace cutting tool inserts during the next scheduled cycle pause.*

---

## 6. Sensor-Level Risk Explanation Schema

When telemetry triggers physical thresholds, a list of `SensorRiskExplanation` objects is returned:

```json
{
  "sensor_name": "Overstrain Factor (Tool Wear x Torque)",
  "observed_value": "12450.0 min·Nm",
  "threshold": "<= 11000 min·Nm (Type-L)",
  "severity": "CRITICAL",
  "description": "Overstrain limit breached for Type-L structural tolerance."
}
```

---

## 7. Physical Sensor Input Validation Boundaries

| Parameter | Type | Valid Range | Physical Units | Validation Rule |
|---|---|---|---|---|
| `air_temperature_k` | `float` | $[280.0, 330.0]$ | Kelvin (K) | Ambient workshop air temperature |
| `process_temperature_k` | `float` | $[290.0, 340.0]$ | Kelvin (K) | Must satisfy $T_{\text{process}} \ge T_{\text{air}}$ |
| `rotational_speed_rpm` | `float` | $[500.0, 4000.0]$ | RPM | Spindle angular rotational speed |
| `torque_nm` | `float` | $[0.0, 120.0]$ | $\text{N}\cdot\text{m}$ | Spindle drive shaft mechanical torque |
| `tool_wear_min` | `int` | $[0, 400]$ | Minutes (min) | Cumulative tool active cutting time |
| `machine_type` | `str` | `L`, `M`, `H` | Categorical | Machine variant quality grade |
| `machine_id` | `str` | Non-empty | Alphanumeric | Machine identifier |

---

## 8. API Specification: `POST /api/predict`

### Request Payload Example
```json
{
  "machine_id": "L47180",
  "machine_type": "L",
  "air_temperature_k": 298.1,
  "process_temperature_k": 308.6,
  "rotational_speed_rpm": 1400.0,
  "torque_nm": 65.0,
  "tool_wear_min": 190
}
```

### Response Payload Example
```json
{
  "machine_id": "L47180",
  "failure_probability": 0.8421,
  "risk_level": "CRITICAL",
  "health_score": 11.3,
  "recommendation": "CRITICAL: Immediate Spindle Halt. Severe mechanical overstrain detected. Inspect cutting tool inserts, spindle bearings, and workpiece clamping before resuming operation.",
  "model_version": "1.0.0",
  "sensor_risk_explanations": [
    {
      "sensor_name": "Overstrain Factor (Tool Wear x Torque)",
      "observed_value": "12350.0 min·Nm",
      "threshold": "<= 11000 min·Nm (Type-L)",
      "severity": "CRITICAL",
      "description": "Overstrain limit breached for Type-L structural tolerance."
    },
    {
      "sensor_name": "Tool Wear Duration",
      "observed_value": "190 min",
      "threshold": "< 200 min",
      "severity": "WARNING",
      "description": "Cumulative cutting tool wear (190 min) approaching nominal 200 min lifespan."
    }
  ]
}
```
