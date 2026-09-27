"""
Standalone Predictive Maintenance Inference Engine.

Provides real-time scoring, failure probability estimation, risk tier classification,
and root-cause diagnostic factor explanations for industrial telemetry.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = PROJECT_ROOT / "ml" / "models"


class PredictiveMaintenanceInference:
    """Production inference engine for machine failure prediction."""

    def __init__(self, models_dir: Optional[Union[str, Path]] = None):
        self.models_dir = Path(models_dir) if models_dir else DEFAULT_MODELS_DIR
        self.model_path = self.models_dir / "model.pkl"
        self.preprocessor_path = self.models_dir / "preprocessor.pkl"
        self.metadata_path = self.models_dir / "model_metadata.json"

        if not self.model_path.exists() or not self.preprocessor_path.exists():
            raise FileNotFoundError(
                f"Model artifacts not found in {self.models_dir}. "
                "Ensure `python ml/training.py` has been executed."
            )

        self.model = joblib.load(self.model_path)
        self.preprocessor = joblib.load(self.preprocessor_path)

        if self.metadata_path.exists():
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {}

        self.required_inputs = [
            "air_temperature_k",
            "process_temperature_k",
            "rotational_speed_rpm",
            "torque_nm",
            "tool_wear_min",
            "machine_type",
        ]

    def _prepare_dataframe(self, input_data: Union[Dict[str, Any], List[Dict[str, Any]], pd.DataFrame]) -> pd.DataFrame:
        """Convert input data into a validated DataFrame with derived physical features."""
        if isinstance(input_data, dict):
            df = pd.DataFrame([input_data])
        elif isinstance(input_data, list):
            df = pd.DataFrame(input_data)
        elif isinstance(input_data, pd.DataFrame):
            df = input_data.copy()
        else:
            raise TypeError("Input data must be a dict, list of dicts, or pandas DataFrame.")

        # Verify required input telemetry exists
        for col in self.required_inputs:
            if col not in df.columns:
                raise ValueError(f"Missing required telemetry feature: '{col}'")

        # Automatically calculate engineered features if missing
        if "temp_diff_k" not in df.columns:
            df["temp_diff_k"] = df["process_temperature_k"] - df["air_temperature_k"]

        if "angular_velocity_rad_s" not in df.columns or "mechanical_power_w" not in df.columns:
            df["angular_velocity_rad_s"] = df["rotational_speed_rpm"] * (2.0 * np.pi / 60.0)
            df["mechanical_power_w"] = df["torque_nm"] * df["angular_velocity_rad_s"]

        if "overstrain_product" not in df.columns:
            df["overstrain_product"] = df["tool_wear_min"] * df["torque_nm"]

        # Ensure machine_type is capitalized
        df["machine_type"] = df["machine_type"].astype(str).str.upper()

        return df

    def _diagnose_risk_factors(self, row: pd.Series) -> List[str]:
        """Derive engineering risk factors explaining the prediction."""
        factors = []
        # 1. Overstrain diagnostic
        mtype = str(row["machine_type"])
        overstrain = float(row["overstrain_product"])
        thresholds = {"L": 11000.0, "M": 12000.0, "H": 13000.0}
        thresh = thresholds.get(mtype, 11000.0)
        if overstrain > thresh:
            factors.append(f"Overstrain critical: Wear x Torque ({overstrain:.1f} min·Nm) exceeds Type-{mtype} limit ({thresh:.0f})")
        elif overstrain > thresh * 0.85:
            factors.append(f"Overstrain warning: Wear x Torque ({overstrain:.1f} min·Nm) approaching Type-{mtype} limit ({thresh:.0f})")

        # 2. Power diagnostic
        power = float(row["mechanical_power_w"])
        if power < 3500.0:
            factors.append(f"Power fault: Low power draw ({power:.1f} W < 3,500 W limit)")
        elif power > 9000.0:
            factors.append(f"Power overload: High power draw ({power:.1f} W > 9,000 W limit)")

        # 3. Heat dissipation diagnostic
        delta_t = float(row["temp_diff_k"])
        rpm = float(row["rotational_speed_rpm"])
        if delta_t < 8.6 and rpm < 1380.0:
            factors.append(f"Thermal dissipation stall: ΔT={delta_t:.2f} K (< 8.6 K) at low RPM ({rpm:.1f} < 1,380)")

        # 4. Tool wear diagnostic
        wear = float(row["tool_wear_min"])
        if wear >= 200.0:
            factors.append(f"Tool wear critical: Blade wear at {wear:.0f} min (exceeds nominal 200 min lifespan)")

        return factors

    def predict(
        self, input_data: Union[Dict[str, Any], List[Dict[str, Any]], pd.DataFrame]
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Execute prediction on single record or batch.

        Returns structured payload:
        - failure_predicted: bool
        - failure_probability: float (0.0 to 1.0)
        - risk_level: 'LOW' | 'MEDIUM' | 'HIGH'
        - risk_factors: List[str]
        """
        df = self._prepare_dataframe(input_data)
        X_proc = self.preprocessor.transform(df)

        predictions = self.model.predict(X_proc)
        if hasattr(self.model, "predict_proba"):
            probabilities = self.model.predict_proba(X_proc)[:, 1]
        else:
            probabilities = predictions.astype(float)

        results = []
        for idx, (_, row) in enumerate(df.iterrows()):
            prob = round(float(probabilities[idx]), 4)
            pred = bool(predictions[idx] == 1)

            if prob >= 0.50 or pred:
                risk_level = "HIGH"
            elif prob >= 0.20:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            risk_factors = self._diagnose_risk_factors(row)

            res = {
                "failure_predicted": pred,
                "failure_probability": prob,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
            }
            results.append(res)

        return results[0] if isinstance(input_data, dict) else results

    def get_metadata(self) -> Dict[str, Any]:
        """Return model metadata, version, and performance benchmarks."""
        return self.metadata


_INFERENCE_ENGINE_INSTANCE: Optional[PredictiveMaintenanceInference] = None


def get_inference_engine(models_dir: Optional[Union[str, Path]] = None) -> PredictiveMaintenanceInference:
    """Singleton getter for inference engine instance."""
    global _INFERENCE_ENGINE_INSTANCE
    if _INFERENCE_ENGINE_INSTANCE is None or models_dir is not None:
        _INFERENCE_ENGINE_INSTANCE = PredictiveMaintenanceInference(models_dir=models_dir)
    return _INFERENCE_ENGINE_INSTANCE
