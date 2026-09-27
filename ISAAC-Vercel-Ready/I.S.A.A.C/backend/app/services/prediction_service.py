from __future__ import annotations

"""
Operational Prediction Service and Decision Support Engine for ISAAC.

Provides:
- Real ML failure probability estimation (via Phase 5 champion model)
- Standardized Health Scoring (0 to 100 continuous index)
- Documented Risk Tier Categorization (NOMINAL, MODERATE, HIGH, CRITICAL)
- Decoupled, transparent rule-based maintenance recommendations
- Sensor-level engineering risk explanations
"""

import math
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from ml.inference import PredictiveMaintenanceInference, get_inference_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class RiskLevel(str, Enum):
    NOMINAL = "NOMINAL"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HealthScoreEngine:
    """
    Calculates composite machinery Health Score (0 - 100).

    Methodology:
    1. Base Score = 100.0 * (1.0 - failure_probability)
    2. Telemetry Degradation Penalties:
       - Tool wear degradation penalty (wear > 180 min)
       - Thermal margin penalty (temp_diff < 9.0 K)
       - Mechanical torque load penalty (torque > 55.0 Nm)
       - Power variance envelope penalty (power < 4000 W or > 8500 W)
    3. Final Health Score = clamp(Base Score - Sum(Penalties), 0.0, 100.0)
    """

    @staticmethod
    def calculate_health_score(
        failure_probability: float,
        tool_wear_min: float,
        temp_diff_k: float,
        torque_nm: float,
        mechanical_power_w: float,
    ) -> float:
        base_score = 100.0 * (1.0 - max(0.0, min(1.0, failure_probability)))
        penalties = 0.0

        # Tool wear degradation penalty (up to 10 points for wear > 180 min)
        if tool_wear_min > 180.0:
            wear_excess = min(60.0, tool_wear_min - 180.0)
            penalties += (wear_excess / 60.0) * 10.0

        # Thermal margin penalty (up to 8 points when delta T < 9.0 K)
        if temp_diff_k < 9.0:
            thermal_deficit = min(2.0, 9.0 - temp_diff_k)
            penalties += (thermal_deficit / 2.0) * 8.0

        # Torque overload penalty (up to 8 points when torque > 55.0 Nm)
        if torque_nm > 55.0:
            torque_excess = min(20.0, torque_nm - 55.0)
            penalties += (torque_excess / 20.0) * 8.0

        # Power variance penalty (up to 6 points outside nominal 4000 - 8500 W band)
        if mechanical_power_w < 4000.0:
            power_deficit = min(1000.0, 4000.0 - mechanical_power_w)
            penalties += (power_deficit / 1000.0) * 6.0
        elif mechanical_power_w > 8500.0:
            power_excess = min(1500.0, mechanical_power_w - 8500.0)
            penalties += (power_excess / 1500.0) * 6.0

        final_score = max(0.0, min(100.0, base_score - penalties))
        return round(float(final_score), 1)


class RecommendationEngine:
    """
    Transparent, deterministic rule-based maintenance recommendation engine.
    Decoupled strictly from the ML probability estimator.
    """

    OVERSTRAIN_THRESHOLDS = {
        "L": 11000.0,
        "M": 12000.0,
        "H": 13000.0,
    }

    @classmethod
    def evaluate_recommendations(
        cls,
        machine_type: str,
        air_temperature_k: float,
        process_temperature_k: float,
        temp_diff_k: float,
        rotational_speed_rpm: float,
        torque_nm: float,
        mechanical_power_w: float,
        tool_wear_min: float,
        overstrain_product: float,
        risk_level: RiskLevel,
    ) -> Tuple_Recommendation_and_Explanations:
        mtype = str(machine_type).upper()
        os_threshold = cls.OVERSTRAIN_THRESHOLDS.get(mtype, 11000.0)

        explanations: List[Dict[str, Any]] = []
        actionable_recommendations: List[str] = []

        # 1. Evaluate Overstrain Risk
        if overstrain_product > os_threshold:
            explanations.append({
                "sensor_name": "Overstrain Factor (Tool Wear x Torque)",
                "observed_value": f"{overstrain_product:.1f} min·Nm",
                "threshold": f"<= {os_threshold:.0f} min·Nm (Type-{mtype})",
                "severity": "CRITICAL",
                "description": f"Overstrain limit breached for Type-{mtype} structural tolerance.",
            })
            actionable_recommendations.append(
                "CRITICAL: Immediate Spindle Halt. Severe mechanical overstrain detected. "
                "Inspect cutting tool inserts, spindle bearings, and workpiece clamping before resuming operation."
            )
        elif overstrain_product > os_threshold * 0.85:
            explanations.append({
                "sensor_name": "Overstrain Factor (Tool Wear x Torque)",
                "observed_value": f"{overstrain_product:.1f} min·Nm",
                "threshold": f"<= {os_threshold:.0f} min·Nm (Type-{mtype})",
                "severity": "WARNING",
                "description": f"Overstrain approaching Type-{mtype} safety limit.",
            })

        # 2. Evaluate Heat Dissipation / Thermal Margin
        if temp_diff_k < 8.6 and rotational_speed_rpm < 1380.0:
            explanations.append({
                "sensor_name": "Thermal Gradient (Process - Air)",
                "observed_value": f"{temp_diff_k:.2f} K (at {rotational_speed_rpm:.0f} RPM)",
                "threshold": ">= 8.60 K (when RPM < 1380)",
                "severity": "CRITICAL",
                "description": "Insufficient convective thermal dissipation; high risk of thermal seizure.",
            })
            actionable_recommendations.append(
                "URGENT: Cooling System Flush. Thermal dissipation boundary degraded. "
                "Inspect coolant lines, verify pump flow rate, and clear chip accumulations from heat exchangers."
            )
        elif temp_diff_k < 9.0:
            explanations.append({
                "sensor_name": "Thermal Gradient (Process - Air)",
                "observed_value": f"{temp_diff_k:.2f} K",
                "threshold": ">= 9.00 K (nominal)",
                "severity": "WARNING",
                "description": "Thermal margin is constrained.",
            })

        # 3. Evaluate Spindle Mechanical Power Envelope
        if mechanical_power_w < 3500.0 or mechanical_power_w > 9000.0:
            explanations.append({
                "sensor_name": "Spindle Mechanical Power",
                "observed_value": f"{mechanical_power_w:.1f} W",
                "threshold": "[3,500 W - 9,000 W]",
                "severity": "CRITICAL",
                "description": "Spindle mechanical power is outside nominal operating boundaries.",
            })
            actionable_recommendations.append(
                "URGENT: Spindle Drive Electrical Fault. Power delivery outside nominal 3.5 kW - 9.0 kW envelope. "
                "Inspect drive inverter, motor windings, and mechanical drive belt tension."
            )

        # 4. Evaluate Tool Wear Lifespan
        if tool_wear_min >= 200.0:
            explanations.append({
                "sensor_name": "Tool Wear Duration",
                "observed_value": f"{tool_wear_min:.0f} min",
                "threshold": "< 200 min",
                "severity": "CRITICAL" if tool_wear_min >= 220.0 else "WARNING",
                "description": f"Cumulative cutting tool wear ({tool_wear_min:.0f} min) exceeds nominal 200 min lifespan.",
            })
            actionable_recommendations.append(
                f"SCHEDULED: Tool Replacement Required. Cumulative tool wear at {tool_wear_min:.0f} min exceeds nominal 200 min lifespan. "
                "Replace cutting tool inserts during the next scheduled cycle pause."
            )

        # Synthesize primary recommendation
        if actionable_recommendations:
            primary_rec = " | ".join(actionable_recommendations)
        elif risk_level in (RiskLevel.HIGH, RiskLevel.MODERATE):
            primary_rec = (
                "ADVISORY: Elevated Operational Stress. Telemetry parameters indicate sub-optimal operating envelope. "
                "Monitor spindle vibration and schedule inspection during upcoming shift change."
            )
        else:
            primary_rec = (
                "ROUTINE OPERATION: Equipment operating within optimal nominal parameters. "
                "Continue standard scheduled lubrication and sensor health monitoring."
            )

        return primary_rec, explanations


# Type alias
Tuple_Recommendation_and_Explanations = Any


class PredictionService:
    """Production prediction and operational decision-support service."""

    def __init__(self, inference_engine: Optional[PredictiveMaintenanceInference] = None):
        self.inference = inference_engine or get_inference_engine()
        self.metadata = self.inference.get_metadata()
        self.model_version = self.metadata.get("model_version", "1.0.0")

    @staticmethod
    def categorize_risk_level(probability: float) -> RiskLevel:
        """Map failure probability into standardized operational risk tier."""
        if probability >= 0.70:
            return RiskLevel.CRITICAL
        elif probability >= 0.40:
            return RiskLevel.HIGH
        elif probability >= 0.15:
            return RiskLevel.MODERATE
        else:
            return RiskLevel.NOMINAL

    def evaluate_telemetry(
        self,
        machine_id: str,
        machine_type: str,
        air_temperature_k: float,
        process_temperature_k: float,
        rotational_speed_rpm: float,
        torque_nm: float,
        tool_wear_min: int,
    ) -> Dict[str, Any]:
        """
        Execute full predictive maintenance scoring and decision-support pipeline.

        Returns structured operational intelligence payload.
        """
        # Validate input boundaries
        if not (280.0 <= air_temperature_k <= 330.0):
            raise ValueError(f"Air temperature {air_temperature_k} K is out of physical sensor bounds [280, 330]")
        if not (290.0 <= process_temperature_k <= 340.0):
            raise ValueError(f"Process temperature {process_temperature_k} K is out of physical sensor bounds [290, 340]")
        if process_temperature_k < air_temperature_k:
            raise ValueError("Process temperature cannot be lower than ambient air temperature")
        if not (500.0 <= rotational_speed_rpm <= 4000.0):
            raise ValueError(f"Rotational speed {rotational_speed_rpm} RPM is out of physical bounds [500, 4000]")
        if not (0.0 <= torque_nm <= 120.0):
            raise ValueError(f"Torque {torque_nm} Nm is out of physical bounds [0, 120]")
        if not (0 <= tool_wear_min <= 400):
            raise ValueError(f"Tool wear {tool_wear_min} min is out of physical bounds [0, 400]")

        mtype = str(machine_type).strip().upper()
        if mtype not in ("L", "M", "H"):
            raise ValueError(f"Invalid machine type '{machine_type}'. Must be 'L', 'M', or 'H'.")

        # 1. Derive physical features
        temp_diff_k = round(process_temperature_k - air_temperature_k, 4)
        angular_vel = rotational_speed_rpm * (2.0 * math.pi / 60.0)
        mechanical_power_w = round(torque_nm * angular_vel, 2)
        overstrain_product = round(tool_wear_min * torque_nm, 2)

        input_payload = {
            "machine_type": mtype,
            "air_temperature_k": air_temperature_k,
            "process_temperature_k": process_temperature_k,
            "temp_diff_k": temp_diff_k,
            "rotational_speed_rpm": rotational_speed_rpm,
            "torque_nm": torque_nm,
            "mechanical_power_w": mechanical_power_w,
            "tool_wear_min": tool_wear_min,
            "overstrain_product": overstrain_product,
        }

        # 2. Run real ML inference (Phase 5 champion model)
        ml_result = self.inference.predict(input_payload)
        failure_prob = float(ml_result["failure_probability"])

        # 3. Derive risk tier
        risk_level = self.categorize_risk_level(failure_prob)

        # 4. Compute Health Score
        health_score = HealthScoreEngine.calculate_health_score(
            failure_probability=failure_prob,
            tool_wear_min=tool_wear_min,
            temp_diff_k=temp_diff_k,
            torque_nm=torque_nm,
            mechanical_power_w=mechanical_power_w,
        )

        # 5. Evaluate decoupled engineering recommendations & sensor explanations
        recommendation, sensor_explanations = RecommendationEngine.evaluate_recommendations(
            machine_type=mtype,
            air_temperature_k=air_temperature_k,
            process_temperature_k=process_temperature_k,
            temp_diff_k=temp_diff_k,
            rotational_speed_rpm=rotational_speed_rpm,
            torque_nm=torque_nm,
            mechanical_power_w=mechanical_power_w,
            tool_wear_min=tool_wear_min,
            overstrain_product=overstrain_product,
            risk_level=risk_level,
        )

        return {
            "machine_id": machine_id,
            "failure_probability": failure_prob,
            "risk_level": risk_level.value,
            "health_score": health_score,
            "recommendation": recommendation,
            "model_version": self.model_version,
            "sensor_risk_explanations": sensor_explanations,
        }


_PREDICTION_SERVICE_INSTANCE: Optional[PredictionService] = None


def get_prediction_service() -> PredictionService:
    """Singleton getter for prediction service."""
    global _PREDICTION_SERVICE_INSTANCE
    if _PREDICTION_SERVICE_INSTANCE is None:
        _PREDICTION_SERVICE_INSTANCE = PredictionService()
    return _PREDICTION_SERVICE_INSTANCE
